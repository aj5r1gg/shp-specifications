#!/usr/bin/env python3

from pathlib import Path
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree as ET
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "source-sets" / "generated" / "corpus-inventory.json"

TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"

METADATA_LABELS = [
    "Document Identifier",
    "Document ID",
    "Version",
    "Status",
    "Document Class",
    "Specification Class",
    "Authority Level",
    "Authority Layer",
    "Constitutional Classification",
    "Constitutional Authority",
    "Amendment Classification",
    "Supersedes",
    "Effective Date",
    "Publication Date",
    "Platform",
    "Platform Scope",
    "Tier",
    "Dependencies",
    "Referenced By",
]

FIELD_LABELS = {
    "document_identifier": [
        "Document Identifier",
        "Document ID",
    ],
    "version": [
        "Version",
    ],
    "status": [
        "Status",
    ],
    "document_class": [
        "Document Class",
        "Specification Class",
    ],
    "authority_level": [
        "Authority Level",
        "Authority Layer",
    ],
    "constitutional_classification": [
        "Constitutional Classification",
    ],
    "constitutional_authority": [
        "Constitutional Authority",
    ],
    "amendment_classification": [
        "Amendment Classification",
    ],
    "supersedes": [
        "Supersedes",
    ],
    "effective_date": [
        "Effective Date",
    ],
    "publication_date": [
        "Publication Date",
    ],
    "platform": [
        "Platform",
        "Platform Scope",
    ],
    "tier": [
        "Tier",
    ],
    "dependencies": [
        "Dependencies",
    ],
    "referenced_by": [
        "Referenced By",
    ],
}

# Observed legacy/local front-matter labels used solely as lexical
# delimiters.  They are not inventory fields and confer no SHP
# authority, lifecycle state, platform support, certification
# eligibility, or other normative meaning.
DELIMITER_ONLY_LABELS = (
    "Additive to",
    "Amendment Authority",
    "Applies To",
    "Audience",
    "Authority",
    "Authority Type",
    "Certification Class",
    "Certification Scope",
    "Change Classification",
    "Classification",
    "Governance Authority",
    "Governed by",
    "Non-Retroactive",
    "Normative Cross-Reference",
    "Normative Cross-References (External Policies Only)",
    "Preserves",
    "Publication Year",
    "Referenced By (future)",
    "Scope",
    "Tier Relationship",
    "Total controls",
    "Verification Tool",
)

LEXICAL_LABELS = (
    tuple(METADATA_LABELS)
    + DELIMITER_ONLY_LABELS
)

LABEL_PATTERN = re.compile(
    r"(?P<label>"
    + "|".join(
        sorted(
            (re.escape(label) for label in LEXICAL_LABELS),
            key=len,
            reverse=True,
        )
    )
    + r")\s*:\s*",
    flags=re.IGNORECASE,
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def extract_text_elements(path: Path):
    """Extract ordered ODT paragraphs while preserving element type."""
    with ZipFile(path) as zf:
        xml = zf.read("content.xml")

    root = ET.fromstring(xml)

    elements = []

    for elem in root.iter():
        if elem.tag not in {
            f"{{{TEXT_NS}}}p",
            f"{{{TEXT_NS}}}h",
        }:
            continue

        value = "".join(elem.itertext())
        value = re.sub(r"[ \t]+", " ", value).strip()

        if not value:
            continue

        elements.append(
            {
                "type": elem.tag.rsplit("}", 1)[-1],
                "text": value,
            }
        )

    return elements

def extract_labelled_metadata(text, metadata_elements):
    matches = list(LABEL_PATTERN.finditer(text))
    found = {}
    provenance = {}

    element_ranges = []
    cursor = 0

    for index, element in enumerate(metadata_elements):
        element_text = element["text"]

        start = cursor
        end = start + len(element_text)

        element_ranges.append(
            {
                "index": index,
                "type": element["type"],
                "start": start,
                "end": end,
            }
        )

        # metadata_searchable joins elements with one newline.
        cursor = end + 1

    def locate_element(offset):
        for item in element_ranges:
            if item["start"] <= offset <= item["end"]:
                return item

        return None

    for i, match in enumerate(matches):
        literal_label = match.group("label").strip()
        label = literal_label.lower()

        value_start = match.end()
        value_end = (
            matches[i + 1].start()
            if i + 1 < len(matches)
            else len(text)
        )

        raw_value = text[value_start:value_end]
        value = re.sub(r"\s+", " ", raw_value).strip()

        if not value or label in found:
            continue

        found[label] = value

        element = locate_element(match.start())

        if element is not None:
            provenance[label] = {
                "label": literal_label,
                "element_index": element["index"],
                "element_type": element["type"],
                "start": match.start() - element["start"],
                "end": value_end - element["start"],
                "method": "labelled-front-matter",
            }
        else:
            provenance[label] = {
                "label": literal_label,
                "element_index": None,
                "element_type": None,
                "start": match.start(),
                "end": value_end,
                "method": "labelled-front-matter",
            }

    return found, provenance


def metadata_value(labelled, labels):
    for label in labels:
        value = labelled.get(label.lower())
        if value:
            return value
    return None


def inspect(path: Path):
    rel = path.relative_to(ROOT)

    record = {
        "path": str(rel),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
        "metadata": {},
        "warnings": [],
    }

    try:
        text_elements = extract_text_elements(path)
    except (BadZipFile, KeyError, ET.ParseError) as exc:
        record["warnings"].append(
            f"ODT extraction failed: {type(exc).__name__}: {exc}"
        )
        return record

    paragraphs = [
        element["text"]
        for element in text_elements
    ]

    # Metadata extraction is restricted to structural ODT front matter.
    #
    # SHP documents may use text:h for metadata as well as substantive
    # headings.  Therefore text:h alone is not a boundary.
    #
    # Stop before the first text:h whose text begins with a numbered
    # substantive section marker.  Style names and outline levels are
    # deliberately ignored.
    #
    # This is repository diagnostic logic only.  It does not confer
    # authority, lifecycle status, platform support or certification
    # meaning.
    metadata_element_limit = 30
    metadata_elements = []
    boundary_reason = "element-limit"

    substantive_heading = re.compile(
        r"^(?:"
        r"PART\s+[0-9IVXLC]+(?:\s|$)"
        r"|(?:0|[1-9]\d*)(?:\.\d+)*\.?\s+\S"
        r")",
        flags=re.IGNORECASE,
    )

    appendix_heading = re.compile(
        r"^[A-Z]\.\d+(?:\.\d+)*\.?\s+\S",
        flags=re.IGNORECASE,
    )

    control_heading = re.compile(
        r"^CONTROL\s+[A-Z][A-Z0-9]*-\d+\b",
        flags=re.IGNORECASE,
    )

    family_heading = re.compile(
        r"^FAMILY\s+[1-9]\d*\s+(?:—|-|:)\s*\S",
        flags=re.IGNORECASE,
    )

    tier_catalogue_heading = re.compile(
        r"^TIER\s+[1-9]\d*\s+"
        r"(?:CORE|CONTROL|CONTROLS|CATALOG|CATALOGUE|INDEX)"
        r"\b",
        flags=re.IGNORECASE,
    )

    for element in text_elements[:metadata_element_limit]:
        element_type = element["type"]
        element_text = element["text"].strip()

        boundary_kind = None

        if metadata_elements and element_type == "h":
            prior_metadata_text = "\n".join(
                item["text"]
                for item in metadata_elements
            )
            recognised_metadata_seen = bool(
                LABEL_PATTERN.search(prior_metadata_text)
            )

            if (
                recognised_metadata_seen
                and element_text.casefold()
                in {"abstract", "front matter"}
            ):
                boundary_kind = "legacy-front-matter-text-h"
            elif substantive_heading.match(element_text):
                boundary_kind = "numbered-text-h"
            elif appendix_heading.match(element_text):
                boundary_kind = "appendix-text-h"
            elif control_heading.match(element_text):
                boundary_kind = "control-text-h"
            elif family_heading.match(element_text):
                boundary_kind = "family-text-h"
            elif tier_catalogue_heading.match(element_text):
                boundary_kind = "tier-catalogue-text-h"

        if boundary_kind is not None:
            boundary_reason = (
                boundary_kind
                + ":"
                + element_text
            )
            break

        metadata_elements.append(element)

    metadata_paragraphs = [
        element["text"]
        for element in metadata_elements
    ]

    metadata_searchable = "\n".join(metadata_paragraphs)

    record["metadata_diagnostic"] = {
        "method": "odt-structural-front-matter",
        "element_limit": metadata_element_limit,
        "elements_examined": len(metadata_elements),
        "boundary_reason": boundary_reason,
        "opening_region": metadata_elements,
    }

    labelled, label_provenance = extract_labelled_metadata(
        metadata_searchable,
        metadata_elements,
    )

    # Modern SHP front matter sometimes represents Version without a
    # colon, e.g. "Version 2.0Status: Draft Standard".  Parse that
    # narrowly from structural front matter only.
    if not labelled.get("version"):
        version_match = re.search(
            r"(?:^|\n|\s)Version\s+"
            r"(?P<value>[0-9]+(?:\.[0-9]+)+)"
            r"(?=Status\s*:|\s|$)",
            metadata_searchable,
            flags=re.IGNORECASE,
        )

        if version_match:
            labelled["version"] = version_match.group("value")

            match_start = version_match.start()
            cursor = 0
            located = None

            for index, element in enumerate(metadata_elements):
                element_text = element["text"]
                start = cursor
                end = start + len(element_text)

                if start <= match_start <= end:
                    located = {
                        "index": index,
                        "type": element["type"],
                        "start": start,
                    }
                    break

                cursor = end + 1

            if located is not None:
                label_provenance["version"] = {
                    "label": "Version",
                    "element_index": located["index"],
                    "element_type": located["type"],
                    "start": (
                        version_match.start()
                        - located["start"]
                    ),
                    "end": (
                        version_match.end()
                        - located["start"]
                    ),
                    "method": "colonless-version-front-matter",
                }

    record["metadata_provenance"] = {}

    for field, labels in FIELD_LABELS.items():
        record["metadata"][field] = metadata_value(
            labelled,
            labels,
        )

        for label in labels:
            key = label.lower()

            if (
                labelled.get(key)
                and key in label_provenance
            ):
                record["metadata_provenance"][field] = (
                    label_provenance[key]
                )
                break

    if paragraphs:
        record["opening_text"] = paragraphs[:12]

    required = (
        "document_identifier",
        "version",
        "status",
    )

    for field in required:
        if not record["metadata"].get(field):
            record["warnings"].append(
                f"missing_or_unparsed:{field}"
            )

    authority = record["metadata"].get("authority_level")
    constitutional = record["metadata"].get(
        "constitutional_classification"
    )

    if not authority and not constitutional:
        record["warnings"].append(
            "missing_or_unparsed:authority_classification"
        )

    if "Superseded" in rel.parts:
        status = record["metadata"].get("status")

        if status and status.lower() != "superseded":
            record["warnings"].append(
                "path_status_mismatch:"
                "under_Superseded_but_metadata_not_Superseded"
            )

    return record

def main():
    documents = sorted(ROOT.rglob("*.odt"))

    records = [inspect(path) for path in documents]

    summary = {
        "schema": "SHP/CorpusInventoryDiagnostic/v1",
        "classification": "non-normative-generated-diagnostic",
        "document_count": len(records),
        "documents_with_warnings": sum(
            bool(r["warnings"]) for r in records
        ),
        "documents_without_warnings": sum(
            not r["warnings"] for r in records
        ),
    }

    output = {
        "summary": summary,
        "documents": records,
    }

    OUTPUT.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("===== SHP CORPUS INVENTORY DIAGNOSTIC =====")
    print(f"documents={summary['document_count']}")
    print(
        "documents_without_warnings="
        f"{summary['documents_without_warnings']}"
    )
    print(
        "documents_with_warnings="
        f"{summary['documents_with_warnings']}"
    )
    print(f"output={OUTPUT.relative_to(ROOT)}")

    print("\n===== WARNINGS =====")

    warning_count = 0

    for record in records:
        if not record["warnings"]:
            continue

        warning_count += len(record["warnings"])

        print(f"\n{record['path']}")
        for warning in record["warnings"]:
            print(f"  - {warning}")

    print(f"\nwarning_count={warning_count}")

if __name__ == "__main__":
    main()
