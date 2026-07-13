from __future__ import annotations

import json
import re
import shutil
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from migration_manifest import (
    DATA_MEMBERS,
    FILE_METADATA_KEYS,
    FORBIDDEN_SECRET_NAMES,
    SHA256_PATTERN,
    blocked_termination_signals,
    run_process_group,
    sha256_file,
    validate_upload_archive,
)

SNAPSHOT_MEMBERS = frozenset({*DATA_MEMBERS, "manifest.json"})
MANIFEST_KEYS = frozenset(
    {"timestamp_utc", "git_commit", "schema_state", "alembic_revision", "files"}
)
GIT_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
SUPPORTED_SCHEMA_STATES = frozenset({"versioned"})


class SnapshotValidationError(ValueError):
    pass


def write_snapshot_manifest(
    snapshot_directory: Path,
    *,
    git_commit: str,
    schema_state: str,
    alembic_revision: str | None,
) -> None:
    _validate_identity(git_commit, schema_state, alembic_revision)
    manifest = {
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "git_commit": git_commit,
        "schema_state": schema_state,
        "alembic_revision": alembic_revision,
        "files": {
            name: {
                "size_bytes": (snapshot_directory / name).stat().st_size,
                "sha256": sha256_file(snapshot_directory / name),
            }
            for name in sorted(DATA_MEMBERS)
        },
    }
    (snapshot_directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def validate_snapshot_directory(snapshot_directory: Path) -> dict[str, Any]:
    if snapshot_directory.is_symlink() or not snapshot_directory.is_dir():
        raise SnapshotValidationError("快照必须是普通目录")
    members = {path.name for path in snapshot_directory.iterdir()}
    if members != SNAPSHOT_MEMBERS:
        raise SnapshotValidationError("快照成员不正确")
    if any(
        not path.is_file() or path.is_symlink() for path in snapshot_directory.iterdir()
    ):
        raise SnapshotValidationError("快照成员必须是普通文件")
    try:
        manifest = json.loads(
            (snapshot_directory / "manifest.json").read_text(encoding="utf-8")
        )
        _validate_manifest(manifest)
        for name in DATA_MEMBERS:
            metadata = manifest["files"][name]
            path = snapshot_directory / name
            if path.stat().st_size != metadata["size_bytes"]:
                raise SnapshotValidationError(f"{name} 文件大小校验失败")
            if sha256_file(path) != metadata["sha256"]:
                raise SnapshotValidationError(f"{name} SHA-256 校验失败")
        validate_upload_archive(snapshot_directory / "knowledge-base-uploads.tar")
    except SnapshotValidationError:
        raise
    except (OSError, ValueError, tarfile.TarError) as error:
        raise SnapshotValidationError("快照校验失败") from error
    return manifest


def publish_snapshot(staging: Path, snapshot_root: Path, snapshot_id: str) -> Path:
    validate_snapshot_directory(staging)
    destination = snapshot_root / snapshot_id
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"快照已经存在：{destination}")
    with blocked_termination_signals():
        staging.replace(destination)
    return destination


def rotate_snapshots(snapshot_root: Path, *, keep: int = 3) -> list[Path]:
    if keep < 1:
        raise ValueError("快照保留数量必须至少为 1")
    complete: list[tuple[str, Path]] = []
    for path in snapshot_root.iterdir():
        if path.name.startswith("."):
            continue
        try:
            manifest = validate_snapshot_directory(path)
        except SnapshotValidationError:
            continue
        complete.append((manifest["timestamp_utc"], path))
    complete.sort(key=lambda item: (item[0], item[1].name), reverse=True)
    removed: list[Path] = []
    for _timestamp, path in complete[keep:]:
        with blocked_termination_signals():
            shutil.rmtree(path)
        removed.append(path)
    return removed


def assert_git_commit(manifest: dict[str, Any], repository: Path) -> None:
    result = run_process_group(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip() != manifest["git_commit"]:
        raise SnapshotValidationError("当前 Git commit 与快照不一致")


def assert_repository_clean(repository: Path) -> None:
    result = run_process_group(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        raise SnapshotValidationError("Git 工作树、索引或未跟踪文件不干净")


def validate_backup_paths(uploads_source: Path, snapshot_root: Path) -> None:
    if uploads_source == snapshot_root:
        raise SnapshotValidationError("教材目录与快照目录不得相同")
    if (
        uploads_source in snapshot_root.parents
        or snapshot_root in uploads_source.parents
    ):
        raise SnapshotValidationError("教材目录与快照目录不得互为祖先或后代")


def reject_symlink_backup_paths(uploads_source: Path, snapshot_root: Path) -> None:
    if uploads_source.is_symlink() or snapshot_root.is_symlink():
        raise SnapshotValidationError("教材源与快照根目录不得是 symlink")


def _validate_manifest(manifest: object) -> None:
    serialized = json.dumps(manifest, ensure_ascii=False)
    if any(name in serialized for name in FORBIDDEN_SECRET_NAMES):
        raise SnapshotValidationError("manifest 不得包含 secret 配置名")
    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS:
        raise SnapshotValidationError("manifest 字段不正确")
    _validate_timestamp(manifest["timestamp_utc"])
    _validate_identity(
        manifest["git_commit"],
        manifest["schema_state"],
        manifest["alembic_revision"],
    )
    files = manifest["files"]
    if not isinstance(files, dict) or set(files) != DATA_MEMBERS:
        raise SnapshotValidationError("manifest 文件成员不正确")
    for metadata in files.values():
        if not isinstance(metadata, dict) or set(metadata) != FILE_METADATA_KEYS:
            raise SnapshotValidationError("manifest 文件元数据不正确")
        size = metadata["size_bytes"]
        checksum = metadata["sha256"]
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise SnapshotValidationError("manifest 文件大小不正确")
        if not isinstance(checksum, str) or SHA256_PATTERN.fullmatch(checksum) is None:
            raise SnapshotValidationError("manifest SHA-256 不正确")


def _validate_timestamp(timestamp: object) -> None:
    if not isinstance(timestamp, str) or not timestamp.endswith("Z"):
        raise SnapshotValidationError("manifest UTC timestamp 不正确")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise SnapshotValidationError("manifest UTC timestamp 不正确") from error
    if parsed.tzinfo != UTC:
        raise SnapshotValidationError("manifest UTC timestamp 不正确")


def _validate_identity(
    git_commit: object, schema_state: object, alembic_revision: object
) -> None:
    if (
        not isinstance(git_commit, str)
        or GIT_COMMIT_PATTERN.fullmatch(git_commit) is None
    ):
        raise SnapshotValidationError("manifest Git commit 不正确")
    if schema_state not in SUPPORTED_SCHEMA_STATES:
        raise SnapshotValidationError("生产快照必须来自 versioned schema")
    if not isinstance(alembic_revision, str) or not alembic_revision:
        raise SnapshotValidationError("生产快照必须包含 Alembic revision")
