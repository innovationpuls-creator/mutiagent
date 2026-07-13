from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.parse import parse_qsl, quote, unquote, urlsplit, urlunsplit

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
SCHEMA_MIGRATION_CODE = """
import json
import os

from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app.migration_state import (
    _matches_current_metadata,
    inspect_schema_state,
    migrate_to_head,
)

engine = create_engine(os.environ["ONETREE_SCHEMA_DATABASE_URL"])
migrate_to_head(engine)
if not _matches_current_metadata(engine):
    raise RuntimeError("迁移后数据库结构与当前 metadata 不一致")
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
REPOSITORY_REVISIONS_CODE = """
import json

from alembic.config import Config
from alembic.script import ScriptDirectory

script = ScriptDirectory.from_config(Config("alembic.ini"))
print(json.dumps({
    "heads": sorted(script.get_heads()),
    "revisions": sorted(revision.revision for revision in script.walk_revisions()),
}))
"""


class BundleValidationError(ValueError):
    pass


class TerminationRequested(RuntimeError):
    pass


_termination_guard_depth = 0
_termination_callbacks: list[Callable[[], None] | None] = []
_termination_previous_handlers: dict[signal.Signals, Any] = {}
_termination_handling = False


@contextmanager
def termination_signal_guard(on_signal: Callable[[], None] | None = None):
    global _termination_guard_depth
    global _termination_handling
    global _termination_previous_handlers

    watched_signals = (signal.SIGINT, signal.SIGTERM)

    def handle_signal(signal_number: int, _frame: object) -> None:
        global _termination_handling

        if _termination_handling:
            return
        _termination_handling = True
        callback = next(
            (
                current
                for current in reversed(_termination_callbacks)
                if current is not None
            ),
            None,
        )
        if callback is not None:
            callback()
        raise TerminationRequested(f"收到终止信号 {signal_number}")

    if _termination_guard_depth == 0:
        _termination_previous_handlers = {
            signal_number: signal.getsignal(signal_number)
            for signal_number in watched_signals
        }
        _termination_handling = False
        for signal_number in watched_signals:
            signal.signal(signal_number, handle_signal)
    _termination_guard_depth += 1
    _termination_callbacks.append(on_signal)
    try:
        yield
    finally:
        _termination_callbacks.pop()
        _termination_guard_depth -= 1
        if _termination_guard_depth == 0:
            for (
                signal_number,
                previous_handler,
            ) in _termination_previous_handlers.items():
                signal.signal(signal_number, previous_handler)
            _termination_previous_handlers = {}
            _termination_handling = False


@contextmanager
def blocked_termination_signals():
    watched_signals = {signal.SIGINT, signal.SIGTERM}
    previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, watched_signals)
    try:
        yield previous_mask
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)


def _request_process_group_termination(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass


def _finish_process_group_termination(process: subprocess.Popen[Any]) -> None:
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def run_process_group(
    command: Sequence[str],
    *,
    check: bool,
    cwd: Path | None = None,
    capture_output: bool = False,
    text: bool = False,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[Any]:
    stdout = subprocess.PIPE if capture_output else None
    stderr = subprocess.PIPE if capture_output else None
    process: subprocess.Popen[Any] | None = None
    process_guard = None
    try:
        with blocked_termination_signals() as inherited_mask:

            def restore_inherited_mask() -> None:
                signal.pthread_sigmask(signal.SIG_SETMASK, inherited_mask)

            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=stdout,
                stderr=stderr,
                text=text,
                start_new_session=True,
                preexec_fn=restore_inherited_mask,
            )
            process_guard = termination_signal_guard(
                lambda: _request_process_group_termination(process)
            )
            process_guard.__enter__()
        try:
            process_stdout, process_stderr = process.communicate()
        except TerminationRequested:
            _request_process_group_termination(process)
            _finish_process_group_termination(process)
            raise
    finally:
        if process_guard is not None:
            process_guard.__exit__(*sys.exc_info())
    if process is None:
        raise RuntimeError("子进程未启动")
    result = subprocess.CompletedProcess(
        process.args,
        process.returncode,
        process_stdout,
        process_stderr,
    )
    if check:
        result.check_returncode()
    return result


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
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{bundle_path.name}.", suffix=".tmp", dir=bundle_path.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    bundle_linked = False
    try:
        with tarfile.open(temporary_path, mode="w") as archive:
            for name in sorted(BUNDLE_MEMBERS):
                archive.add(bundle_directory / name, arcname=name, recursive=False)
        previous_mask = signal.pthread_sigmask(
            signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM}
        )
        try:
            os.link(temporary_path, bundle_path, follow_symlinks=False)
            bundle_linked = True
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
    except BaseException:
        if bundle_linked:
            bundle_path.unlink(missing_ok=True)
        raise
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
    database_url: str,
    service_file: Path,
    service_name: str,
    database_name: str | None = None,
) -> dict[str, str]:
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL 必须使用 postgres 或 postgresql scheme")
    if not parsed.path or parsed.path == "/":
        raise ValueError("DATABASE_URL 必须包含数据库名")
    values: dict[str, str] = {
        "dbname": database_name or unquote(parsed.path.removeprefix("/"))
    }
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
    environment = os.environ.copy()
    environment["ONETREE_SCHEMA_DATABASE_URL"] = database_url
    identity = _run_backend_json(
        backend_directory,
        SCHEMA_INSPECTION_CODE,
        environment,
        "无法通过 inspect_schema_state 精确检查数据库结构",
    )
    if not isinstance(identity, dict):
        raise RuntimeError("数据库结构检查结果不正确")
    schema_state = identity.get("schema_state")
    revision = identity.get("alembic_revision")
    _validate_schema_identity(schema_state, revision)
    return {"schema_state": schema_state, "alembic_revision": revision}


def migrate_database_to_head(
    backend_directory: Path, database_url: str
) -> dict[str, str | None]:
    environment = os.environ.copy()
    environment["ONETREE_SCHEMA_DATABASE_URL"] = database_url
    identity = _run_backend_json(
        backend_directory,
        SCHEMA_MIGRATION_CODE,
        environment,
        "验证数据库 Alembic 迁移失败",
    )
    if not isinstance(identity, dict):
        raise RuntimeError("数据库迁移检查结果不正确")
    schema_state = identity.get("schema_state")
    revision = identity.get("alembic_revision")
    _validate_schema_identity(schema_state, revision)
    return {"schema_state": schema_state, "alembic_revision": revision}


def repository_revision_sets(backend_directory: Path) -> dict[str, set[str]]:
    result = _run_backend_json(
        backend_directory,
        REPOSITORY_REVISIONS_CODE,
        os.environ.copy(),
        "无法读取仓库 Alembic revision 集合",
    )
    if not isinstance(result, dict):
        raise RuntimeError("仓库 Alembic revision 集合不正确")
    heads = result.get("heads")
    revisions = result.get("revisions")
    if not isinstance(heads, list) or not all(isinstance(item, str) for item in heads):
        raise RuntimeError("仓库 Alembic head 集合不正确")
    if not isinstance(revisions, list) or not all(
        isinstance(item, str) for item in revisions
    ):
        raise RuntimeError("仓库 Alembic revision 集合不正确")
    return {"heads": set(heads), "revisions": set(revisions)}


def assert_manifest_repository_revision(
    manifest: dict[str, Any], backend_directory: Path
) -> None:
    if manifest["schema_state"] != "versioned":
        return
    revision = manifest["alembic_revision"]
    revisions = repository_revision_sets(backend_directory)["revisions"]
    if revision not in revisions:
        raise BundleValidationError("manifest Alembic revision 不属于当前仓库")


def replace_database_name(database_url: str, database_name: str) -> str:
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL 必须使用 postgres 或 postgresql scheme")
    encoded_name = quote(database_name, safe="")
    if not parsed.netloc:
        query = f"?{parsed.query}" if parsed.query else ""
        return f"{parsed.scheme}:///{encoded_name}{query}"
    return urlunsplit(
        (parsed.scheme, parsed.netloc, f"/{encoded_name}", parsed.query, "")
    )


def validate_replacement_target(target: Path) -> None:
    if target.is_symlink():
        raise BundleValidationError(f"教材目标不得是 symlink：{target}")
    if target.exists() and not target.is_dir():
        raise BundleValidationError(f"教材目标必须是普通目录：{target}")


@dataclass
class DirectoryReplacement:
    target: Path
    previous: Path | None
    old_moved: bool = False
    new_installed: bool = False
    active: bool = True

    def rollback(self) -> None:
        if not self.active:
            return
        if self.new_installed and self.target.exists():
            shutil.rmtree(self.target)
        if self.old_moved and self.previous is not None and self.previous.exists():
            self.previous.replace(self.target)
        self.active = False

    def commit(self) -> None:
        if not self.active:
            return
        self.active = False
        if self.previous is not None and self.previous.exists():
            shutil.rmtree(self.previous)


def begin_directory_replacement(staging: Path, target: Path) -> DirectoryReplacement:
    validate_replacement_target(target)
    previous: Path | None = None
    if target.exists():
        previous = Path(
            tempfile.mkdtemp(prefix=f".{target.name}.previous.", dir=target.parent)
        )
        previous.rmdir()
    replacement = DirectoryReplacement(target=target, previous=previous)
    try:
        if previous is not None:
            with blocked_termination_signals():
                target.replace(previous)
                replacement.old_moved = True
        with blocked_termination_signals():
            staging.replace(target)
            replacement.new_installed = True
        return replacement
    except BaseException:
        replacement.rollback()
        if previous is not None and previous.exists():
            previous.rmdir()
        raise


def replace_directory_atomically(staging: Path, target: Path) -> None:
    replacement = begin_directory_replacement(staging, target)
    replacement.commit()


def _run_backend_json(
    backend_directory: Path,
    code: str,
    environment: dict[str, str],
    failure_message: str,
) -> object:
    dependency_check = run_process_group(
        [sys.executable, "-c", "import alembic, sqlalchemy, sqlmodel"],
        cwd=backend_directory,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if dependency_check.returncode == 0:
        command = [sys.executable, "-c", code]
    else:
        uv_path = shutil.which("uv")
        if uv_path is None:
            raise RuntimeError("后端依赖不可导入且未找到 uv")
        command = [
            uv_path,
            "--directory",
            str(backend_directory),
            "run",
            "--no-env-file",
            "python",
            "-c",
            code,
        ]
    result = run_process_group(
        command,
        cwd=backend_directory,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if result.returncode != 0:
        raise RuntimeError(failure_message)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(failure_message) from error


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
