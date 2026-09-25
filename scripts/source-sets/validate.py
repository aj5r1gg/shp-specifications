#!/usr/bin/env python3

"""
SHP source-set manifest validator.

Non-normative repository tooling.

This validator checks manifest structure, repository binding and
artifact integrity. It does not determine SHP authority, lifecycle
status, platform support, certification eligibility, tier status,
supersession, or any other normative SHP fact.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


MANIFEST_SCHEMA = "SHP/SourceSetManifest/v1"
INVENTORY_SCHEMA = "SHP/CorpusInventoryDiagnostic/v1"

SCHEMA_PATH = Path(
    "source-sets/schema/source-set-manifest-v1.schema.json"
)

INVENTORY_PATH = Path(
    "source-sets/generated/corpus-inventory.json"
)

INVENTORY_GENERATOR = Path(
    "scripts/source-sets/inventory.py"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(
            f"file does not exist: {path}"
        ) from None
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON in {path}: "
            f"line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from None


def git_head(repository_root: Path) -> str:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repository_root),
            "rev-parse",
            "--verify",
            "HEAD",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise ValueError(
            "repository has no resolvable HEAD commit"
        )

    value = result.stdout.strip()

    if len(value) != 40:
        raise ValueError(
            "repository HEAD is not a 40-character SHA-1 object ID"
        )

    return value


def schema_errors(schema, manifest):
    validator = Draft202012Validator(
        schema,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )

    return sorted(
        validator.iter_errors(manifest),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.message,
        ),
    )


def format_schema_error(error) -> str:
    if error.absolute_path:
        location = ".".join(
            str(part)
            for part in error.absolute_path
        )
    else:
        location = "<root>"

    return (
        f"schema:{location}: {error.message}"
    )


def validate_manifest(manifest_path: Path) -> list[str]:
    failures = []

    repository_root = Path.cwd().resolve()

    try:
        schema = load_json(SCHEMA_PATH)
    except ValueError as exc:
        return [f"schema:{exc}"]

    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        return [
            "schema:invalid Draft 2020-12 schema: "
            + str(exc)
        ]

    try:
        manifest = load_json(manifest_path)
    except ValueError as exc:
        return [f"manifest:{exc}"]

    errors = schema_errors(schema, manifest)

    if errors:
        return [
            format_schema_error(error)
            for error in errors
        ]

    if manifest["schema"] != MANIFEST_SCHEMA:
        failures.append(
            "manifest schema identifier mismatch"
        )

    # Duplicate paths are semantically ambiguous even though each
    # individual artifact object may be schema-valid.
    seen_paths = set()

    for artifact in manifest["artifacts"]:
        relative = artifact["path"]

        if relative in seen_paths:
            failures.append(
                f"artifact:{relative}: duplicate path"
            )
            continue

        seen_paths.add(relative)

        candidate = (
            repository_root / relative
        ).resolve()

        try:
            candidate.relative_to(repository_root)
        except ValueError:
            failures.append(
                f"artifact:{relative}: path escapes repository"
            )
            continue

        if not candidate.exists():
            failures.append(
                f"artifact:{relative}: file does not exist"
            )
            continue

        if not candidate.is_file():
            failures.append(
                f"artifact:{relative}: not a regular file"
            )
            continue

        actual_hash = sha256(candidate)
        expected_hash = artifact["sha256"]

        if actual_hash != expected_hash:
            failures.append(
                f"artifact:{relative}: SHA-256 mismatch: "
                f"expected={expected_hash} actual={actual_hash}"
            )

    # The inventory is diagnostic input. Binding to it does not make
    # inventory observations normative SHP facts.
    try:
        inventory = load_json(INVENTORY_PATH)
    except ValueError as exc:
        failures.append(f"inventory:{exc}")
    else:
        summary = inventory.get("summary")

        if not isinstance(summary, dict):
            actual_inventory_schema = None
        else:
            actual_inventory_schema = summary.get("schema")

        if actual_inventory_schema != INVENTORY_SCHEMA:
            failures.append(
                "inventory:schema mismatch: "
                f"expected={INVENTORY_SCHEMA!r} "
                f"actual={actual_inventory_schema!r}"
            )

    if not INVENTORY_GENERATOR.is_file():
        failures.append(
            "inventory:generator does not exist: "
            f"{INVENTORY_GENERATOR}"
        )
    else:
        actual_generator_hash = sha256(
            INVENTORY_GENERATOR
        )
        expected_generator_hash = (
            manifest["inventory"]["generator_sha256"]
        )

        if actual_generator_hash != expected_generator_hash:
            failures.append(
                "inventory:generator SHA-256 mismatch: "
                f"expected={expected_generator_hash} "
                f"actual={actual_generator_hash}"
            )

    # A v1 source-set manifest is pinned. No development-mode
    # exception is permitted here.
    try:
        actual_head = git_head(repository_root)
    except ValueError as exc:
        failures.append(f"repository:{exc}")
    else:
        expected_head = manifest["repository"]["commit"]

        if actual_head != expected_head:
            failures.append(
                "repository:HEAD mismatch: "
                f"expected={expected_head} actual={actual_head}"
            )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate an SHP source-set manifest against "
            "repository and integrity constraints."
        )
    )

    parser.add_argument(
        "manifest",
        type=Path,
        help="path to an SHP source-set manifest",
    )

    args = parser.parse_args()

    failures = validate_manifest(args.manifest)

    result = {
        "schema": "SHP/SourceSetValidationResult/v1",
        "manifest": str(args.manifest),
        "valid": not failures,
        "failure_count": len(failures),
        "failures": failures,
    }

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
