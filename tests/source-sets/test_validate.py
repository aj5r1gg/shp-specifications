#!/usr/bin/env python3

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPOSITORY_ROOT = Path.cwd().resolve()
VALIDATOR_SOURCE = (
    REPOSITORY_ROOT / "scripts/source-sets/validate.py"
)
SCHEMA_SOURCE = (
    REPOSITORY_ROOT
    / "source-sets/schema/source-set-manifest-v1.schema.json"
)

MANIFEST_SCHEMA = "SHP/SourceSetManifest/v1"
INVENTORY_SCHEMA = "SHP/CorpusInventoryDiagnostic/v1"


def run(command, cwd, check=True):
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
    )

    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed: {command!r}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    return result


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8")


def commit(repo, message):
    run(["git", "add", "."], repo)
    run(["git", "commit", "-m", message], repo)

    return run(
        ["git", "rev-parse", "HEAD"],
        repo,
    ).stdout.strip()


def manifest_for(
    commit_id,
    artifact_hash,
    generator_hash,
    *,
    artifact_path="artifact.txt",
    created_at=None,
):
    source_set = {
        "id": "qualification",
        "version": 1,
        "purpose": "Validator regression qualification",
    }

    if created_at is not None:
        source_set["created_at"] = created_at

    return {
        "schema": MANIFEST_SCHEMA,
        "source_set": source_set,
        "repository": {
            "commit": commit_id,
        },
        "inventory": {
            "schema": INVENTORY_SCHEMA,
            "generator_sha256": generator_hash,
        },
        "artifacts": [
            {
                "path": artifact_path,
                "sha256": artifact_hash,
            }
        ],
    }


def validate(repo, manifest):
    manifest_path = repo / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    result = run(
        [
            sys.executable,
            str(repo / "scripts/source-sets/validate.py"),
            str(manifest_path),
        ],
        repo,
        check=False,
    )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            "validator did not emit JSON\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        ) from exc

    return result.returncode, payload


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def failure_text(payload):
    return "\n".join(payload.get("failures", []))


def main():
    tests = []

    def test(name, function):
        tests.append((name, function))

    with tempfile.TemporaryDirectory(
        prefix="shp-validator-qualification-"
    ) as temporary:
        repo = Path(temporary)

        run(["git", "init", "-b", "main"], repo)
        run(
            ["git", "config", "user.name", "SHP Qualification"],
            repo,
        )
        run(
            [
                "git",
                "config",
                "user.email",
                "qualification@example.invalid",
            ],
            repo,
        )

        write(
            repo / "scripts/source-sets/validate.py",
            VALIDATOR_SOURCE.read_bytes(),
        )
        write(
            repo
            / "source-sets/schema/source-set-manifest-v1.schema.json",
            SCHEMA_SOURCE.read_bytes(),
        )

        artifact_v1 = b"artifact version one\n"
        generator_v1 = b"inventory generator version one\n"

        write(repo / "artifact.txt", artifact_v1)
        write(
            repo / "scripts/source-sets/inventory.py",
            generator_v1,
        )

        baseline = commit(repo, "qualification baseline")

        artifact_hash_v1 = digest(artifact_v1)
        generator_hash_v1 = digest(generator_v1)

        valid_manifest = manifest_for(
            baseline,
            artifact_hash_v1,
            generator_hash_v1,
        )

        def valid_baseline():
            status, payload = validate(repo, valid_manifest)
            require(status == 0, failure_text(payload))
            require(payload["valid"] is True, payload)
            require(payload["failure_count"] == 0, payload)

        test("valid baseline commit tree", valid_baseline)

        def nonexistent_commit():
            manifest = manifest_for(
                "0" * 40,
                artifact_hash_v1,
                generator_hash_v1,
            )
            status, payload = validate(repo, manifest)
            text = failure_text(payload)
            require(status == 1, payload)
            require(
                "declared commit does not resolve as a commit"
                in text,
                payload,
            )

        test("nonexistent commit rejected", nonexistent_commit)

        def wrong_artifact_hash():
            manifest = manifest_for(
                baseline,
                "0" * 64,
                generator_hash_v1,
            )
            status, payload = validate(repo, manifest)
            text = failure_text(payload)
            require(status == 1, payload)
            require("artifact:artifact.txt" in text, payload)
            require("SHA-256 mismatch" in text, payload)

        test("artifact hash mismatch rejected", wrong_artifact_hash)

        def missing_committed_path():
            manifest = manifest_for(
                baseline,
                artifact_hash_v1,
                generator_hash_v1,
                artifact_path="missing.txt",
            )
            status, payload = validate(repo, manifest)
            text = failure_text(payload)
            require(status == 1, payload)
            require(
                "path is not a blob in declared commit: missing.txt"
                in text,
                payload,
            )

        test("missing committed path rejected", missing_committed_path)

        def duplicate_path():
            manifest = json.loads(json.dumps(valid_manifest))
            manifest["artifacts"].append(
                dict(manifest["artifacts"][0])
            )
            status, payload = validate(repo, manifest)
            text = failure_text(payload)
            require(status == 1, payload)
            require("duplicate path" in text, payload)

        test("duplicate artifact path rejected", duplicate_path)

        def wrong_generator_hash():
            manifest = manifest_for(
                baseline,
                artifact_hash_v1,
                "0" * 64,
            )
            status, payload = validate(repo, manifest)
            text = failure_text(payload)
            require(status == 1, payload)
            require(
                "inventory:generator SHA-256 mismatch"
                in text,
                payload,
            )

        test("generator hash mismatch rejected", wrong_generator_hash)

        def invalid_datetime():
            manifest = manifest_for(
                baseline,
                artifact_hash_v1,
                generator_hash_v1,
                created_at="definitely-not-a-date",
            )
            status, payload = validate(repo, manifest)
            text = failure_text(payload)
            require(status == 1, payload)
            require("is not a 'date-time'" in text, payload)

        test("invalid date-time rejected", invalid_datetime)

        def dirty_artifact_irrelevant():
            write(
                repo / "artifact.txt",
                b"dirty working tree artifact\n",
            )
            status, payload = validate(repo, valid_manifest)
            require(status == 0, failure_text(payload))
            require(payload["valid"] is True, payload)

        test(
            "dirty working-tree artifact ignored",
            dirty_artifact_irrelevant,
        )

        def dirty_generator_irrelevant():
            write(
                repo / "scripts/source-sets/inventory.py",
                b"dirty working tree generator\n",
            )
            status, payload = validate(repo, valid_manifest)
            require(status == 0, failure_text(payload))
            require(payload["valid"] is True, payload)

        test(
            "dirty working-tree generator ignored",
            dirty_generator_irrelevant,
        )

        # Restore working files before creating a later commit.
        write(repo / "artifact.txt", artifact_v1)
        write(
            repo / "scripts/source-sets/inventory.py",
            generator_v1,
        )

        write(repo / "later.txt", "later commit\n")
        later = commit(repo, "later commit")

        require(
            later != baseline,
            "qualification setup failed to advance HEAD",
        )

        def historical_commit_with_new_head():
            current_head = run(
                ["git", "rev-parse", "HEAD"],
                repo,
            ).stdout.strip()

            require(current_head == later, current_head)
            require(current_head != baseline, current_head)

            status, payload = validate(repo, valid_manifest)
            require(status == 0, failure_text(payload))
            require(payload["valid"] is True, payload)

        test(
            "historical commit valid when HEAD differs",
            historical_commit_with_new_head,
        )

        passed = 0

        for name, function in tests:
            try:
                function()
            except Exception as exc:
                print(f"FAIL  {name}")
                print(f"      {exc}")
            else:
                passed += 1
                print(f"PASS  {name}")

        print()
        print(f"tests={len(tests)}")
        print(f"passed={passed}")
        print(f"failed={len(tests) - passed}")

        if passed != len(tests):
            return 1

        print("qualification=PASS")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
