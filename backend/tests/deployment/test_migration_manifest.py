from __future__ import annotations

import errno
import hashlib
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import pytest

DEPLOY_LIB = Path(__file__).resolve().parents[3] / "deploy" / "lib"
sys.path.insert(0, str(DEPLOY_LIB))

import migration_manifest as migration_manifest_module  # noqa: E402
from migration_manifest import (  # noqa: E402
    BundleValidationError,
    TerminationRequested,
    assert_manifest_repository_revision,
    begin_directory_replacement,
    blocked_termination_signals,
    create_bundle_archive,
    extract_verified_bundle,
    replace_database_name,
    run_process_group,
    set_directory_ownership,
    termination_signal_guard,
    validate_replacement_target,
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


def test_set_directory_ownership_updates_root_directories_and_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "uploads"
    nested = target / "chapter"
    nested.mkdir(parents=True)
    textbook = nested / "textbook.pdf"
    textbook.write_bytes(b"pdf")
    ownership_calls: list[tuple[Path, int, int, bool]] = []

    def record_chown(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        uid: int,
        gid: int,
        *,
        follow_symlinks: bool = True,
    ) -> None:
        ownership_calls.append((Path(path), uid, gid, follow_symlinks))

    monkeypatch.setattr(migration_manifest_module.os, "chown", record_chown)

    set_directory_ownership(target, uid=10001, gid=10001)

    assert set(ownership_calls) == {
        (target, 10001, 10001, False),
        (nested, 10001, 10001, False),
        (textbook, 10001, 10001, False),
    }


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


def test_versioned_manifest_revision_must_exist_in_repository(tmp_path: Path) -> None:
    bundle = tmp_path / "migration.tar"
    verified = tmp_path / "verified"
    _bundle(bundle)
    manifest = extract_verified_bundle(bundle, verified)
    backend_directory = Path(__file__).resolve().parents[2]

    assert_manifest_repository_revision(manifest, backend_directory)
    manifest["alembic_revision"] = "not-a-repository-revision"

    with pytest.raises(BundleValidationError):
        assert_manifest_repository_revision(manifest, backend_directory)


def test_verify_bundle_cli_rejects_revision_not_in_repository(tmp_path: Path) -> None:
    bundle = tmp_path / "migration.tar"
    _bundle(
        bundle,
        manifest_updates={"alembic_revision": "not-a-repository-revision"},
    )
    verify_script = (
        Path(__file__).resolve().parents[3] / "deploy" / "bin" / "verify-bundle"
    )

    result = subprocess.run(
        [str(verify_script), str(bundle)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0


@pytest.mark.parametrize("existing_kind", ["file", "symlink"])
def test_bundle_creation_never_overwrites_existing_output(
    tmp_path: Path, existing_kind: str
) -> None:
    source_bundle = tmp_path / "source.tar"
    bundle_directory = tmp_path / "bundle-directory"
    _bundle(source_bundle)
    extract_verified_bundle(source_bundle, bundle_directory)
    output = tmp_path / "migration.tar"
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("untouched", encoding="utf-8")
    if existing_kind == "file":
        output.write_text("existing", encoding="utf-8")
    else:
        output.symlink_to(sentinel)

    with pytest.raises(FileExistsError):
        create_bundle_archive(bundle_directory, output)

    assert sentinel.read_text(encoding="utf-8") == "untouched"
    if existing_kind == "symlink":
        assert output.is_symlink()
    else:
        assert output.read_text(encoding="utf-8") == "existing"


def test_replacement_target_symlink_is_rejected_before_resolution(
    tmp_path: Path,
) -> None:
    real_target = tmp_path / "real-uploads"
    real_target.mkdir()
    (real_target / "old.txt").write_text("old", encoding="utf-8")
    target_symlink = tmp_path / "uploads"
    target_symlink.symlink_to(real_target, target_is_directory=True)

    with pytest.raises(BundleValidationError):
        validate_replacement_target(target_symlink)

    assert target_symlink.is_symlink()
    assert (real_target / "old.txt").read_text(encoding="utf-8") == "old"


@pytest.mark.parametrize("signal_number", [signal.SIGINT, signal.SIGTERM])
def test_signal_during_directory_rename_restores_old_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    signal_number: signal.Signals,
) -> None:
    target = tmp_path / "uploads"
    target.mkdir()
    (target / "old.txt").write_text("old", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "new.txt").write_text("new", encoding="utf-8")
    original_replace = Path.replace
    signal_sent = False

    def interrupt_after_first_rename(source: Path, destination: Path) -> Path:
        nonlocal signal_sent
        result = original_replace(source, destination)
        if source == target and not signal_sent:
            signal_sent = True
            os.kill(os.getpid(), signal_number)
        return result

    monkeypatch.setattr(Path, "replace", interrupt_after_first_rename)

    with termination_signal_guard(), pytest.raises(TerminationRequested):
        begin_directory_replacement(staging, target)

    assert target.is_dir()
    assert (target / "old.txt").read_text(encoding="utf-8") == "old"
    assert not (target / "new.txt").exists()
    assert not (tmp_path / ".uploads.previous").exists()


def test_database_failure_rolls_back_begun_directory_replacement(
    tmp_path: Path,
) -> None:
    target = tmp_path / "uploads"
    target.mkdir()
    (target / "old.txt").write_text("old", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "new.txt").write_text("new", encoding="utf-8")

    replacement = begin_directory_replacement(staging, target)
    assert (target / "new.txt").read_text(encoding="utf-8") == "new"

    replacement.rollback()

    assert (target / "old.txt").read_text(encoding="utf-8") == "old"
    assert not (target / "new.txt").exists()


def test_signal_is_deferred_until_directory_replacement_is_committed(
    tmp_path: Path,
) -> None:
    target = tmp_path / "uploads"
    target.mkdir()
    (target / "old.txt").write_text("old", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "new.txt").write_text("new", encoding="utf-8")

    with termination_signal_guard(), pytest.raises(TerminationRequested):
        with blocked_termination_signals():
            replacement = begin_directory_replacement(staging, target)
            os.kill(os.getpid(), signal.SIGTERM)
            replacement.commit()

    assert (target / "new.txt").read_text(encoding="utf-8") == "new"
    assert not (target / "old.txt").exists()


def test_repeated_signal_during_handler_does_not_interrupt_callback() -> None:
    callback_calls = 0

    def callback() -> None:
        nonlocal callback_calls
        callback_calls += 1
        os.kill(os.getpid(), signal.SIGTERM)

    with termination_signal_guard(callback), pytest.raises(TerminationRequested):
        os.kill(os.getpid(), signal.SIGTERM)

    assert callback_calls == 1


def test_process_group_signal_stops_shell_descendant(tmp_path: Path) -> None:
    script = tmp_path / "spawn-descendant.sh"
    child_pid_file = tmp_path / "child-pid"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "sleep 30 &\n"
        "child=$!\n"
        'printf "%s\\n" "$child" > "$CHILD_PID_FILE"\n'
        'kill -TERM "$PPID"\n'
        'wait "$child"\n',
        encoding="utf-8",
    )
    script.chmod(0o700)
    environment = os.environ.copy()
    environment["CHILD_PID_FILE"] = str(child_pid_file)

    with pytest.raises(TerminationRequested):
        run_process_group([str(script)], check=True, env=environment)

    child_pid = int(child_pid_file.read_text(encoding="utf-8"))
    for _ in range(100):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.01)
    else:
        pytest.fail("process-group descendant remained alive")


def test_pending_startup_signal_reaps_leader_and_descendant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "startup-window.sh"
    leader_pid_file = tmp_path / "leader-pid"
    child_pid_file = tmp_path / "child-pid"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'printf "%s\\n" "$$" > "$LEADER_PID_FILE"\n'
        "sleep 30 &\n"
        "child=$!\n"
        'printf "%s\\n" "$child" > "$CHILD_PID_FILE"\n'
        'wait "$child"\n',
        encoding="utf-8",
    )
    script.chmod(0o700)
    environment = os.environ.copy()
    environment["LEADER_PID_FILE"] = str(leader_pid_file)
    environment["CHILD_PID_FILE"] = str(child_pid_file)
    original_popen = subprocess.Popen

    def popen_then_queue_signal(*args: object, **kwargs: object):
        process = original_popen(*args, **kwargs)
        for _ in range(200):
            if leader_pid_file.exists() and child_pid_file.exists():
                break
            time.sleep(0.005)
        else:
            process.kill()
            process.wait()
            pytest.fail("startup process did not publish its process ids")
        os.kill(os.getpid(), signal.SIGTERM)
        return process

    monkeypatch.setattr(subprocess, "Popen", popen_then_queue_signal)

    with pytest.raises(TerminationRequested):
        run_process_group([str(script)], check=True, env=environment)

    process_ids = (
        int(leader_pid_file.read_text(encoding="utf-8")),
        int(child_pid_file.read_text(encoding="utf-8")),
    )
    alive_process_ids: list[int] = []
    for process_id in process_ids:
        for _ in range(100):
            try:
                os.kill(process_id, 0)
            except ProcessLookupError:
                break
            time.sleep(0.01)
        else:
            alive_process_ids.append(process_id)
    for process_id in alive_process_ids:
        try:
            os.kill(process_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
    assert alive_process_ids == []


def test_process_group_signal_propagates_permission_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny_process_group_signal(_process_group_id: int, _signal_number: int) -> None:
        raise PermissionError(errno.EPERM, "injected process-group permission error")

    monkeypatch.setattr(os, "killpg", deny_process_group_signal)

    with pytest.raises(PermissionError) as error:
        migration_manifest_module._signal_process_group(1234, signal.SIGTERM)

    assert error.value.errno == errno.EPERM


def test_process_group_kills_term_ignoring_descendant_after_leader_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "leader-exits.sh"
    child_pid_file = tmp_path / "child-pid"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'bash -c \'trap "" TERM; printf "%s\\n" "$$" > '
        '"$CHILD_PID_FILE"; while true; do sleep 1; done\' &\n'
        'while [[ ! -s "$CHILD_PID_FILE" ]]; do sleep 0.01; done\n'
        'kill -TERM "$PPID"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    script.chmod(0o700)
    environment = os.environ.copy()
    environment["CHILD_PID_FILE"] = str(child_pid_file)
    monkeypatch.setattr(
        migration_manifest_module,
        "PROCESS_GROUP_TERMINATION_TIMEOUT_SECONDS",
        0.05,
        raising=False,
    )

    with pytest.raises(TerminationRequested):
        run_process_group([str(script)], check=True, env=environment)

    child_pid = int(child_pid_file.read_text(encoding="utf-8"))
    child_alive = True
    for _ in range(100):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            child_alive = False
            break
        time.sleep(0.01)
    if child_alive:
        os.kill(child_pid, signal.SIGKILL)
    assert not child_alive


def test_previous_cleanup_failure_does_not_block_next_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "uploads"
    target.mkdir()
    (target / "old.txt").write_text("old", encoding="utf-8")
    first_staging = tmp_path / "first-staging"
    first_staging.mkdir()
    (first_staging / "first.txt").write_text("first", encoding="utf-8")
    first_replacement = begin_directory_replacement(first_staging, target)
    original_rmtree = shutil.rmtree

    def fail_previous_cleanup(path: Path, *args: object, **kwargs: object) -> None:
        if Path(path) == first_replacement.previous:
            raise OSError("injected previous cleanup failure")
        original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", fail_previous_cleanup)
    with pytest.raises(OSError, match="injected previous cleanup failure"):
        first_replacement.commit()
    monkeypatch.setattr(shutil, "rmtree", original_rmtree)

    second_staging = tmp_path / "second-staging"
    second_staging.mkdir()
    (second_staging / "second.txt").write_text("second", encoding="utf-8")
    second_replacement = begin_directory_replacement(second_staging, target)
    second_replacement.rollback()

    assert (target / "first.txt").read_text(encoding="utf-8") == "first"


def test_replacing_unix_socket_database_name_preserves_three_slashes() -> None:
    assert (
        replace_database_name("postgresql:///source", "validation")
        == "postgresql:///validation"
    )
