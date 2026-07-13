from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

DEPLOY_LIB = Path(__file__).resolve().parents[3] / "deploy" / "lib"
sys.path.insert(0, str(DEPLOY_LIB))

from migration_manifest import (  # noqa: E402
    BundleValidationError,
    extract_verified_bundle,
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _uploads_tar(*, member_name: str = "教材/第一章.txt") -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        payload = "第一章".encode()
        info = tarfile.TarInfo(member_name)
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    return output.getvalue()


def _bundle(
    path: Path,
    *,
    uploads_member: str = "教材/第一章.txt",
    manifest_updates: dict[str, object] | None = None,
    omitted_member: str | None = None,
    extra_member: str | None = None,
) -> None:
    database_dump = b"postgres-custom-dump"
    uploads_tar = _uploads_tar(member_name=uploads_member)
    manifest: dict[str, object] = {
        "timestamp_utc": "2026-07-13T08:00:00Z",
        "schema_state": "versioned",
        "alembic_revision": "0002_ingestion_job_leases",
        "files": {
            "database.dump": {
                "size_bytes": len(database_dump),
                "sha256": _sha256(database_dump),
            },
            "knowledge-base-uploads.tar": {
                "size_bytes": len(uploads_tar),
                "sha256": _sha256(uploads_tar),
            },
        },
    }
    if manifest_updates:
        manifest.update(manifest_updates)
    members = {
        "database.dump": database_dump,
        "knowledge-base-uploads.tar": uploads_tar,
        "manifest.json": json.dumps(manifest).encode(),
    }
    if omitted_member:
        del members[omitted_member]
    if extra_member:
        members[extra_member] = b"extra"
    with tarfile.open(path, mode="w") as archive:
        for name, payload in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))


def test_valid_bundle_extracts_exact_members(tmp_path: Path) -> None:
    bundle = tmp_path / "migration.tar"
    target = tmp_path / "verified"
    _bundle(bundle)

    manifest = extract_verified_bundle(bundle, target)

    assert set(path.name for path in target.iterdir()) == {
        "database.dump",
        "knowledge-base-uploads.tar",
        "manifest.json",
    }
    assert manifest["alembic_revision"] == "0002_ingestion_job_leases"
    assert manifest["schema_state"] == "versioned"


def test_current_unversioned_bundle_records_null_revision(tmp_path: Path) -> None:
    bundle = tmp_path / "migration.tar"
    target = tmp_path / "verified"
    _bundle(
        bundle,
        manifest_updates={
            "schema_state": "current_unversioned",
            "alembic_revision": None,
        },
    )

    manifest = extract_verified_bundle(bundle, target)

    assert manifest["schema_state"] == "current_unversioned"
    assert manifest["alembic_revision"] is None


@pytest.mark.parametrize(
    "manifest_updates",
    [
        {"schema_state": "versioned", "alembic_revision": None},
        {
            "schema_state": "current_unversioned",
            "alembic_revision": "0002_ingestion_job_leases",
        },
        {"schema_state": "legacy", "alembic_revision": None},
        {"schema_state": "empty", "alembic_revision": None},
    ],
)
def test_schema_state_and_revision_must_be_consistent(
    tmp_path: Path, manifest_updates: dict[str, object]
) -> None:
    bundle = tmp_path / "migration.tar"
    target = tmp_path / "verified"
    _bundle(bundle, manifest_updates=manifest_updates)

    with pytest.raises(BundleValidationError):
        extract_verified_bundle(bundle, target)

    assert not target.exists()


@pytest.mark.parametrize(
    ("change", "value"),
    [
        ("omitted_member", "database.dump"),
        ("extra_member", "extra.txt"),
        ("extra_member", "/absolute.txt"),
        ("extra_member", "../outside.txt"),
        ("uploads_member", "/absolute.txt"),
        ("uploads_member", "../outside.txt"),
    ],
)
def test_invalid_bundle_does_not_write_target(
    tmp_path: Path, change: str, value: str
) -> None:
    bundle = tmp_path / "migration.tar"
    target = tmp_path / "verified"
    _bundle(bundle, **{change: value})

    with pytest.raises(BundleValidationError):
        extract_verified_bundle(bundle, target)

    assert not target.exists()


@pytest.mark.parametrize("field_name", ["DATABASE_URL", "JWT_SECRET", "LLM_API_KEY"])
def test_manifest_with_secret_field_does_not_write_target(
    tmp_path: Path, field_name: str
) -> None:
    bundle = tmp_path / "migration.tar"
    target = tmp_path / "verified"
    _bundle(bundle, manifest_updates={field_name: "secret-value"})

    with pytest.raises(BundleValidationError):
        extract_verified_bundle(bundle, target)

    assert not target.exists()


@pytest.mark.parametrize("field_name", ["DATABASE_URL", "JWT_SECRET", "LLM_API_KEY"])
def test_manifest_with_secret_name_in_value_does_not_write_target(
    tmp_path: Path, field_name: str
) -> None:
    bundle = tmp_path / "migration.tar"
    target = tmp_path / "verified"
    _bundle(bundle, manifest_updates={"alembic_revision": field_name})

    with pytest.raises(BundleValidationError):
        extract_verified_bundle(bundle, target)

    assert not target.exists()


@pytest.mark.parametrize("invalid_metadata", ["hash", "size"])
def test_invalid_file_metadata_does_not_write_target(
    tmp_path: Path, invalid_metadata: str
) -> None:
    bundle = tmp_path / "migration.tar"
    target = tmp_path / "verified"
    database_dump = b"postgres-custom-dump"
    file_metadata = {
        "size_bytes": len(database_dump),
        "sha256": _sha256(database_dump),
    }
    if invalid_metadata == "hash":
        file_metadata["sha256"] = "0" * 64
    else:
        file_metadata["size_bytes"] += 1
    _bundle(
        bundle,
        manifest_updates={
            "files": {
                "database.dump": file_metadata,
                "knowledge-base-uploads.tar": {
                    "size_bytes": len(_uploads_tar()),
                    "sha256": _sha256(_uploads_tar()),
                },
            }
        },
    )

    with pytest.raises(BundleValidationError):
        extract_verified_bundle(bundle, target)

    assert not target.exists()
