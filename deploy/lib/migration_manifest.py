from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

BUNDLE_MEMBERS = frozenset(
    {"database.dump", "knowledge-base-uploads.tar", "manifest.json"}
)
DATA_MEMBERS = frozenset({"database.dump", "knowledge-base-uploads.tar"})
MANIFEST_KEYS = frozenset(
    {"timestamp_utc", "schema_state", "alembic_revision", "files"}
)
FILE_METADATA_KEYS = frozenset({"size_bytes", "sha256"})
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
SERVICE_KEY_PATTERN = re.compile(r"[a-z_]+")
FORBIDDEN_SECRET_NAMES = ("DATABASE_URL", "JWT_SECRET", "LLM_API_KEY")
SUPPORTED_SCHEMA_STATES = frozenset(
    {"versioned", "baseline_unversioned", "current_unversioned"}
)
SCHEMA_INSPECTION_CODE = """
import json
import os

from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app.migration_state import inspect_schema_state

engine = create_engine(os.environ["ONETREE_SCHEMA_DATABASE_URL"])
state = inspect_schema_state(engine)
revision = None
if state == "versioned":
    with engine.connect() as connection:
        heads = MigrationContext.configure(connection).get_current_heads()
    if len(heads) != 1:
        raise RuntimeError("versioned 数据库必须精确包含一个 Alembic revision")
    revision = heads[0]
print(json.dumps({"schema_state": state, "alembic_revision": revision}))
"""


class BundleValidationError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_manifest(
    bundle_directory: Path,
    schema_state: str,
    alembic_revision: str | None,
) -> dict[str, Any]:
    _validate_schema_identity(schema_state, alembic_revision)
    return {
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "schema_state": schema_state,
        "alembic_revision": alembic_revision,
        "files": {
            name: {
                "size_bytes": (bundle_directory / name).stat().st_size,
                "sha256": sha256_file(bundle_directory / name),
            }
            for name in sorted(DATA_MEMBERS)
        },
    }


def write_manifest(
    bundle_directory: Path,
    schema_state: str,
    alembic_revision: str | None,
) -> None:
    manifest = create_manifest(bundle_directory, schema_state, alembic_revision)
    (bundle_directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def create_bundle_archive(bundle_directory: Path, bundle_path: Path) -> None:
    if set(path.name for path in bundle_directory.iterdir()) != BUNDLE_MEMBERS:
        raise BundleValidationError("迁移包目录成员不正确")
    temporary_path = bundle_path.with_name(f".{bundle_path.name}.tmp")
    try:
        with tarfile.open(temporary_path, mode="w") as archive:
            for name in sorted(BUNDLE_MEMBERS):
                archive.add(bundle_directory / name, arcname=name, recursive=False)
        temporary_path.replace(bundle_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def extract_verified_bundle(
    bundle_path: Path, target_directory: Path
) -> dict[str, Any]:
    if target_directory.exists():
        raise BundleValidationError("校验目标目录已经存在")
    target_directory.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{target_directory.name}.", dir=target_directory.parent
        )
    )
    try:
        _extract_outer_archive(bundle_path, staging)
        manifest = validate_bundle_directory(staging)
        staging.replace(target_directory)
        return manifest
    except (BundleValidationError, OSError, tarfile.TarError, json.JSONDecodeError):
        shutil.rmtree(staging, ignore_errors=True)
        raise


def validate_bundle_directory(bundle_directory: Path) -> dict[str, Any]:
    members = {path.name for path in bundle_directory.iterdir()}
    if members != BUNDLE_MEMBERS:
        raise BundleValidationError("迁移包成员不正确")
    if any(
        not path.is_file() or path.is_symlink() for path in bundle_directory.iterdir()
    ):
        raise BundleValidationError("迁移包成员必须是普通文件")

    manifest = json.loads(
        (bundle_directory / "manifest.json").read_text(encoding="utf-8")
    )
    _validate_manifest(manifest)
    for name in DATA_MEMBERS:
        metadata = manifest["files"][name]
        path = bundle_directory / name
        if path.stat().st_size != metadata["size_bytes"]:
            raise BundleValidationError(f"{name} 文件大小校验失败")
        if sha256_file(path) != metadata["sha256"]:
            raise BundleValidationError(f"{name} SHA-256 校验失败")
    validate_upload_archive(bundle_directory / "knowledge-base-uploads.tar")
    return manifest


def validate_upload_archive(archive_path: Path) -> None:
    with tarfile.open(archive_path, mode="r:*") as archive:
        for member in archive.getmembers():
            _validate_tar_member(member)


def extract_upload_archive(archive_path: Path, target_directory: Path) -> None:
    if target_directory.exists():
        raise BundleValidationError("教材 staging 目录已经存在")
    target_directory.mkdir(parents=True)
    try:
        with tarfile.open(archive_path, mode="r:*") as archive:
            members = archive.getmembers()
            for member in members:
                _validate_tar_member(member)
            for member in members:
                destination = target_directory.joinpath(
                    *PurePosixPath(member.name).parts
                )
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise BundleValidationError("无法读取教材归档成员")
                with destination.open("wb") as output:
                    shutil.copyfileobj(source, output)
    except (OSError, tarfile.TarError, BundleValidationError):
        shutil.rmtree(target_directory, ignore_errors=True)
        raise


def _extract_outer_archive(bundle_path: Path, staging: Path) -> None:
    with tarfile.open(bundle_path, mode="r:*") as archive:
        members = archive.getmembers()
        if {member.name for member in members} != BUNDLE_MEMBERS:
            raise BundleValidationError("迁移包成员不正确")
        if len(members) != len(BUNDLE_MEMBERS):
            raise BundleValidationError("迁移包包含重复成员")
        for member in members:
            if not member.isfile() or PurePosixPath(member.name).name != member.name:
                raise BundleValidationError("迁移包成员路径不正确")
            source = archive.extractfile(member)
            if source is None:
                raise BundleValidationError("无法读取迁移包成员")
            with (staging / member.name).open("wb") as destination:
                shutil.copyfileobj(source, destination)


def _validate_manifest(manifest: object) -> None:
    serialized = json.dumps(manifest, ensure_ascii=False)
    if any(name in serialized for name in FORBIDDEN_SECRET_NAMES):
        raise BundleValidationError("manifest 不得包含 secret 配置名")
    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS:
        raise BundleValidationError("manifest 字段不正确")
    _validate_timestamp(manifest["timestamp_utc"])
    schema_state = manifest["schema_state"]
    revision = manifest["alembic_revision"]
    _validate_schema_identity(schema_state, revision)
    _validate_file_metadata(manifest["files"])


def _validate_timestamp(timestamp: object) -> None:
    if not isinstance(timestamp, str) or not timestamp.endswith("Z"):
        raise BundleValidationError("manifest UTC timestamp 不正确")
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise BundleValidationError("manifest UTC timestamp 不正确") from error


def _validate_file_metadata(files: object) -> None:
    if not isinstance(files, dict) or set(files) != DATA_MEMBERS:
        raise BundleValidationError("manifest 文件成员不正确")
    for metadata in files.values():
        if not isinstance(metadata, dict) or set(metadata) != FILE_METADATA_KEYS:
            raise BundleValidationError("manifest 文件元数据不正确")
        size = metadata["size_bytes"]
        checksum = metadata["sha256"]
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise BundleValidationError("manifest 文件大小不正确")
        if not isinstance(checksum, str) or SHA256_PATTERN.fullmatch(checksum) is None:
            raise BundleValidationError("manifest SHA-256 不正确")


def _validate_schema_identity(schema_state: object, revision: object) -> None:
    if not isinstance(schema_state, str) or schema_state not in SUPPORTED_SCHEMA_STATES:
        raise BundleValidationError("manifest schema_state 不受支持")
    if schema_state == "versioned":
        if not isinstance(revision, str) or not revision:
            raise BundleValidationError("versioned manifest 必须包含 Alembic revision")
        return
    if revision is not None:
        raise BundleValidationError("未版本化 manifest 的 Alembic revision 必须为 null")


def _validate_tar_member(member: tarfile.TarInfo) -> None:
    path = PurePosixPath(member.name)
    if path.is_absolute() or ".." in path.parts:
        raise BundleValidationError("教材归档包含越界路径")
    if not (member.isfile() or member.isdir()):
        raise BundleValidationError("教材归档包含不支持的成员类型")


def postgres_service_environment(
    database_url: str, service_file: Path, service_name: str
) -> dict[str, str]:
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL 必须使用 postgres 或 postgresql scheme")
    if not parsed.path or parsed.path == "/":
        raise ValueError("DATABASE_URL 必须包含数据库名")
    values: dict[str, str] = {"dbname": unquote(parsed.path.removeprefix("/"))}
    if parsed.username is not None:
        values["user"] = unquote(parsed.username)
    if parsed.password is not None:
        values["password"] = unquote(parsed.password)
    if parsed.hostname is not None:
        values["host"] = parsed.hostname
    if parsed.port is not None:
        values["port"] = str(parsed.port)
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if SERVICE_KEY_PATTERN.fullmatch(key) is None or key in values:
            raise ValueError("DATABASE_URL query 参数不正确")
        values[key] = value
    _write_service_file(service_file, service_name, values)
    environment = os.environ.copy()
    environment["PGSERVICEFILE"] = str(service_file)
    return environment


def inspect_database_identity(
    backend_directory: Path, database_url: str
) -> dict[str, str | None]:
    python_path = backend_directory / ".venv" / "bin" / "python"
    if not python_path.is_file():
        raise RuntimeError(f"后端 Python 环境不存在：{python_path}")
    environment = os.environ.copy()
    environment["ONETREE_SCHEMA_DATABASE_URL"] = database_url
    result = subprocess.run(
        [str(python_path), "-c", SCHEMA_INSPECTION_CODE],
        cwd=backend_directory,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if result.returncode != 0:
        raise RuntimeError("无法通过 inspect_schema_state 精确检查数据库结构")
    try:
        identity = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("数据库结构检查未返回有效 JSON") from error
    if not isinstance(identity, dict):
        raise RuntimeError("数据库结构检查结果不正确")
    schema_state = identity.get("schema_state")
    revision = identity.get("alembic_revision")
    _validate_schema_identity(schema_state, revision)
    return {"schema_state": schema_state, "alembic_revision": revision}


def _write_service_file(
    service_file: Path, service_name: str, values: Mapping[str, str]
) -> None:
    if SERVICE_KEY_PATTERN.fullmatch(service_name) is None:
        raise ValueError("PostgreSQL service name 不正确")
    lines = [f"[{service_name}]"]
    for key, value in values.items():
        if "\n" in value or "\r" in value:
            raise ValueError("DATABASE_URL 包含不支持的换行")
        lines.append(f"{key}={value}")
    service_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    service_file.chmod(0o600)
