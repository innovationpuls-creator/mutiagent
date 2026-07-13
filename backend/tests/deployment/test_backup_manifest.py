from __future__ import annotations

import sys
import tarfile
from pathlib import Path

import pytest

DEPLOY_LIB = Path(__file__).resolve().parents[3] / "deploy" / "lib"
sys.path.insert(0, str(DEPLOY_LIB))

from backup_manifest import (  # noqa: E402
    SnapshotValidationError,
    publish_snapshot,
    rotate_snapshots,
    validate_snapshot_directory,
    write_snapshot_manifest,
)

GIT_COMMIT = "1d6495cb9a54b559893c27fc8da8b1de8c79a9ca"
REVISION = "0002_ingestion_job_leases"


def _snapshot(directory: Path, *, marker: str = "data") -> None:
    directory.mkdir()
    (directory / "database.dump").write_bytes(f"database-{marker}".encode())
    upload = directory / f"textbook-{marker}.txt"
    upload.write_text(f"uploads-{marker}", encoding="utf-8")
    with tarfile.open(directory / "knowledge-base-uploads.tar", mode="w") as archive:
        archive.add(upload, arcname=upload.name)
    upload.unlink()
    write_snapshot_manifest(
        directory,
        git_commit=GIT_COMMIT,
        schema_state="versioned",
        alembic_revision=REVISION,
    )


def test_snapshot_manifest_validates_exact_members_and_identity(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    _snapshot(snapshot)

    manifest = validate_snapshot_directory(snapshot)

    assert set(path.name for path in snapshot.iterdir()) == {
        "database.dump",
        "knowledge-base-uploads.tar",
        "manifest.json",
    }
    assert manifest["git_commit"] == GIT_COMMIT
    assert manifest["schema_state"] == "versioned"
    assert manifest["alembic_revision"] == REVISION


@pytest.mark.parametrize("failure", ["missing", "hash", "secret", "git"])
def test_invalid_snapshot_is_rejected(tmp_path: Path, failure: str) -> None:
    snapshot = tmp_path / "snapshot"
    _snapshot(snapshot)
    if failure == "missing":
        (snapshot / "database.dump").unlink()
    elif failure == "hash":
        (snapshot / "database.dump").write_bytes(b"tampered")
    else:
        manifest_path = snapshot / "manifest.json"
        text = manifest_path.read_text(encoding="utf-8")
        if failure == "secret":
            text = text.replace('"files":', '"DATABASE_URL": "secret", "files":')
        else:
            text = text.replace(GIT_COMMIT, "not-a-git-commit")
        manifest_path.write_text(text, encoding="utf-8")

    with pytest.raises(SnapshotValidationError):
        validate_snapshot_directory(snapshot)


def test_publish_is_atomic_and_rotation_keeps_three_complete_snapshots(
    tmp_path: Path,
) -> None:
    root = tmp_path / "backups"
    root.mkdir()
    source_uploads = tmp_path / "knowledge-base-uploads"
    source_uploads.mkdir()
    (source_uploads / "textbook.txt").write_text("source", encoding="utf-8")
    for index in range(4):
        staging = tmp_path / f"staging-{index}"
        _snapshot(staging, marker=str(index))
        publish_snapshot(staging, root, f"20260713T00000{index}Z")
        rotate_snapshots(root, keep=3)

    incomplete = root / "incomplete"
    incomplete.mkdir()
    (incomplete / "database.dump").write_bytes(b"partial")
    rotate_snapshots(root, keep=3)

    complete = [path.name for path in root.iterdir() if path.name.startswith("2026")]
    assert sorted(complete) == [
        "20260713T000001Z",
        "20260713T000002Z",
        "20260713T000003Z",
    ]
    assert incomplete.exists()
    assert (source_uploads / "textbook.txt").read_text(encoding="utf-8") == "source"


def test_publish_rejects_invalid_staging_without_visible_snapshot(
    tmp_path: Path,
) -> None:
    root = tmp_path / "backups"
    root.mkdir()
    staging = tmp_path / "staging"
    _snapshot(staging)
    (staging / "database.dump").write_bytes(b"tampered")

    with pytest.raises(SnapshotValidationError):
        publish_snapshot(staging, root, "20260713T000000Z")

    assert not (root / "20260713T000000Z").exists()


def test_snapshot_directory_symlink_is_rejected(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    _snapshot(snapshot)
    snapshot_link = tmp_path / "snapshot-link"
    snapshot_link.symlink_to(snapshot, target_is_directory=True)

    with pytest.raises(SnapshotValidationError):
        validate_snapshot_directory(snapshot_link)
