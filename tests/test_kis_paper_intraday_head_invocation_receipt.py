from __future__ import annotations

import hashlib
import importlib.util
import json
import socket
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest

from thericher_v2.ops import kis_paper_intraday_head_invocation_receipt as receipts

_PROJECTOR = (
    Path(__file__).parents[1] / "scripts" / "project_kis_paper_intraday_head_invocation_receipt.py"
)


def test_started_and_terminal_receipts_are_external_idempotent_and_networkless(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository_root, artifact_root = _roots(tmp_path)

    def network_forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("invocation receipt writer must stay networkless")

    monkeypatch.setattr(socket, "create_connection", network_forbidden)
    started_at = datetime(2026, 8, 19, 15, 29, tzinfo=UTC)
    started = receipts.write_started_kis_paper_intraday_head_invocation_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id="head-unit",
        started_at=started_at,
    )
    terminal = receipts.write_terminal_kis_paper_intraday_head_invocation_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id="head-unit",
        started_at=started_at,
        schedule_observed_at=started_at + timedelta(minutes=1),
        completed_at=started_at + timedelta(minutes=2),
        collection_exit_code=0,
        schedule_receipt_status="complete",
        terminal_exit_code=0,
    )
    duplicate = receipts.write_terminal_kis_paper_intraday_head_invocation_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id="head-unit",
        started_at=started_at,
        schedule_observed_at=started_at + timedelta(minutes=1),
        completed_at=started_at + timedelta(minutes=2),
        collection_exit_code=0,
        schedule_receipt_status="complete",
        terminal_exit_code=0,
    )

    assert started.status == "written"
    assert terminal.status == "written"
    assert duplicate.status == "already_written"
    runtime = receipts.read_current_kis_paper_intraday_head_invocation_runtime_fact(
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    start_path = _receipt_path(artifact_root, "head-unit", "started")
    terminal_path = _receipt_path(artifact_root, "head-unit", "terminal")
    payload = json.loads(terminal_path.read_text(encoding="ascii"))
    assert payload["started_receipt_sha256"] == started.receipt_sha256
    assert payload["collection_outcome"] == "succeeded"
    assert payload["collection_failure_category"] == "reason_unavailable"
    assert payload["schedule_receipt_outcome"] == "complete"
    assert payload["terminal_outcome"] == "succeeded"
    assert runtime.phase == "terminal"
    assert runtime.run_id == "head-unit"
    assert runtime.receipt_sha256 == terminal.receipt_sha256
    terminal_fact = receipts.read_current_kis_paper_intraday_head_invocation_terminal_fact(
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    assert terminal_fact.schedule_observed_at == started_at + timedelta(minutes=1)
    assert terminal_fact.completed_at == started_at + timedelta(minutes=2)
    assert terminal_fact.collection_failure_category == "reason_unavailable"
    assert start_path.is_relative_to(artifact_root)
    assert terminal_path.is_relative_to(artifact_root)
    assert not any(repository_root.rglob("*.json"))


def test_terminal_receipt_requires_matching_started_marker(tmp_path: Path) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    started_at = datetime(2026, 8, 19, 15, 29, tzinfo=UTC)

    result = receipts.write_terminal_kis_paper_intraday_head_invocation_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id="head-unit",
        started_at=started_at,
        schedule_observed_at=started_at + timedelta(seconds=30),
        completed_at=started_at + timedelta(minutes=1),
        collection_exit_code=1,
        schedule_receipt_status="unavailable",
        terminal_exit_code=21,
    )

    assert result.status == "not_written"
    assert result.reason == "started_receipt_unavailable"


def test_terminal_receipt_retains_only_allowlisted_failure_categories(tmp_path: Path) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    started_at = datetime(2026, 8, 19, 15, 29, tzinfo=UTC)
    receipts.write_started_kis_paper_intraday_head_invocation_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id="head-unit",
        started_at=started_at,
    )
    result = receipts.write_terminal_kis_paper_intraday_head_invocation_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id="head-unit",
        started_at=started_at,
        schedule_observed_at=started_at + timedelta(seconds=1),
        completed_at=started_at + timedelta(seconds=2),
        collection_exit_code=1,
        collection_failure_category="dispatcher_config",
        schedule_receipt_status="recovery",
        terminal_exit_code=1,
    )

    assert result.status == "written"
    terminal_path = _receipt_path(artifact_root, "head-unit", "terminal")
    before_invalid = terminal_path.read_bytes()
    invalid = receipts.write_terminal_kis_paper_intraday_head_invocation_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id="head-unit",
        started_at=started_at,
        schedule_observed_at=started_at + timedelta(seconds=1),
        completed_at=started_at + timedelta(seconds=2),
        collection_exit_code=1,
        collection_failure_category="token=synthetic-secret",
        schedule_receipt_status="recovery",
        terminal_exit_code=1,
    )

    assert invalid.status == "not_written"
    assert invalid.reason == "collection_failure_category_invalid"
    assert terminal_path.read_bytes() == before_invalid
    assert b"synthetic-secret" not in terminal_path.read_bytes()
    terminal_fact = receipts.read_current_kis_paper_intraday_head_invocation_terminal_fact(
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    assert terminal_fact.collection_failure_category == "dispatcher_config"
    receipts.write_started_kis_paper_intraday_head_invocation_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id="head-zero",
        started_at=started_at,
    )
    zero_exit = receipts.write_terminal_kis_paper_intraday_head_invocation_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id="head-zero",
        started_at=started_at,
        schedule_observed_at=started_at + timedelta(seconds=1),
        completed_at=started_at + timedelta(seconds=2),
        collection_exit_code=0,
        collection_failure_category="collector_provider",
        schedule_receipt_status="complete",
        terminal_exit_code=0,
    )
    assert zero_exit.reason == "collection_failure_category_invalid"


def test_legacy_terminal_receipt_remains_immutable_and_defaults_reason_unavailable(
    tmp_path: Path,
) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    started_at = datetime(2026, 8, 19, 15, 29, tzinfo=UTC)
    receipts.write_started_kis_paper_intraday_head_invocation_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id="head-legacy",
        started_at=started_at,
    )
    receipts.write_terminal_kis_paper_intraday_head_invocation_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id="head-legacy",
        started_at=started_at,
        schedule_observed_at=started_at + timedelta(seconds=1),
        completed_at=started_at + timedelta(seconds=2),
        collection_exit_code=1,
        collection_failure_category="collector_provider",
        schedule_receipt_status="recovery",
        terminal_exit_code=1,
    )
    terminal_path = _receipt_path(artifact_root, "head-legacy", "terminal")
    legacy_payload = json.loads(terminal_path.read_text(encoding="ascii"))
    legacy_payload.pop("collection_failure_category")
    legacy_bytes = receipts._canonical_json(legacy_payload)
    terminal_path.write_bytes(legacy_bytes)
    runtime_path = (
        artifact_root
        / receipts.KIS_PAPER_INTRADAY_HEAD_INVOCATION_RECEIPT_DIRECTORY
        / receipts.KIS_PAPER_INTRADAY_HEAD_INVOCATION_RUNTIME_ARTIFACT_NAME
    )
    runtime_payload = json.loads(runtime_path.read_text(encoding="ascii"))
    runtime_payload["receipt_sha256"] = "sha256:" + hashlib.sha256(legacy_bytes).hexdigest()
    runtime_path.write_bytes(receipts._canonical_json(runtime_payload))

    fact = receipts.read_current_kis_paper_intraday_head_invocation_terminal_fact(
        artifact_root=artifact_root,
        repository_root=repository_root,
    )

    assert fact.collection_failure_category == "reason_unavailable"
    assert terminal_path.read_bytes() == legacy_bytes


def test_module_entrypoint_writes_a_source_safe_started_receipt(tmp_path: Path) -> None:
    repository_root, artifact_root = _roots(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "thericher_v2.ops.kis_paper_intraday_head_invocation_receipt",
            "started",
            "--run-id",
            "head-entrypoint",
            "--started-at",
            "2026-08-19T15:29:00Z",
            "--artifact-root",
            str(artifact_root),
            "--repository-root",
            str(repository_root),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "written"
    assert payload["phase"] == "started"


def test_terminal_receipt_rejects_invalid_time_or_status(tmp_path: Path) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    started_at = datetime(2026, 8, 19, 15, 29, tzinfo=UTC)
    receipts.write_started_kis_paper_intraday_head_invocation_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id="head-unit",
        started_at=started_at,
    )

    before_start = receipts.write_terminal_kis_paper_intraday_head_invocation_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id="head-unit",
        started_at=started_at,
        schedule_observed_at=started_at,
        completed_at=started_at - timedelta(seconds=1),
        collection_exit_code=0,
        schedule_receipt_status="complete",
        terminal_exit_code=0,
    )
    invalid_status = receipts.write_terminal_kis_paper_intraday_head_invocation_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id="head-unit",
        started_at=started_at,
        schedule_observed_at=started_at,
        completed_at=started_at + timedelta(seconds=1),
        collection_exit_code=0,
        schedule_receipt_status="invalid",
        terminal_exit_code=0,
    )

    assert before_start.reason == "terminal_before_start"
    assert invalid_status.reason == "schedule_receipt_status_invalid"

    invalid_schedule_time = receipts.write_terminal_kis_paper_intraday_head_invocation_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id="head-unit",
        started_at=started_at,
        schedule_observed_at=started_at + timedelta(seconds=2),
        completed_at=started_at + timedelta(seconds=1),
        collection_exit_code=0,
        schedule_receipt_status="complete",
        terminal_exit_code=0,
    )

    assert invalid_schedule_time.reason == "schedule_observed_time_invalid"


def test_started_receipt_rejects_a_repository_artifact_root(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()

    with pytest.raises(ValueError, match="artifact root"):
        receipts.write_started_kis_paper_intraday_head_invocation_receipt(
            artifact_root=repository_root / "artifacts",
            repository_root=repository_root,
            run_id="head-unit",
            started_at=datetime(2026, 8, 19, 15, 29, tzinfo=UTC),
        )


def test_projector_reads_only_a_validated_current_pointer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    script = _load_projector()
    monkeypatch.setattr(script, "_REPOSITORY_ROOT", repository_root)

    assert script.main(["--artifact-root", str(artifact_root)]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "kind": receipts.KIS_PAPER_INTRADAY_HEAD_INVOCATION_RUNTIME_KIND,
        "status": "unavailable",
    }
    started_at = datetime(2026, 8, 19, 15, 29, tzinfo=UTC)
    receipts.write_started_kis_paper_intraday_head_invocation_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id="head-unit",
        started_at=started_at,
    )

    assert script.main(["--artifact-root", str(artifact_root)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "complete"
    assert payload["phase"] == "started"
    assert payload["run_id"] == "head-unit"


def test_current_pointer_rejects_a_tampered_receipt_hash(tmp_path: Path) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    started_at = datetime(2026, 8, 19, 15, 29, tzinfo=UTC)
    receipts.write_started_kis_paper_intraday_head_invocation_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id="head-unit",
        started_at=started_at,
    )
    runtime_path = (
        artifact_root
        / receipts.KIS_PAPER_INTRADAY_HEAD_INVOCATION_RECEIPT_DIRECTORY
        / receipts.KIS_PAPER_INTRADAY_HEAD_INVOCATION_RUNTIME_ARTIFACT_NAME
    )
    payload = json.loads(runtime_path.read_text(encoding="ascii"))
    payload["receipt_sha256"] = "sha256:" + "0" * 64
    runtime_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="ascii",
    )

    with pytest.raises(ValueError, match="runtime"):
        receipts.read_current_kis_paper_intraday_head_invocation_runtime_fact(
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def test_reader_rejects_a_terminal_before_its_started_marker(tmp_path: Path) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    started_at = datetime(2026, 8, 19, 15, 29, tzinfo=UTC)
    receipts.write_started_kis_paper_intraday_head_invocation_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id="head-unit",
        started_at=started_at,
    )
    receipts.write_terminal_kis_paper_intraday_head_invocation_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id="head-unit",
        started_at=started_at,
        schedule_observed_at=started_at + timedelta(seconds=1),
        completed_at=started_at + timedelta(seconds=1),
        collection_exit_code=0,
        schedule_receipt_status="complete",
        terminal_exit_code=0,
    )
    terminal_path = _receipt_path(artifact_root, "head-unit", "terminal")
    terminal_payload = json.loads(terminal_path.read_text(encoding="ascii"))
    terminal_payload["completed_at"] = "2026-08-19T15:28:59Z"
    terminal_path.write_text(
        json.dumps(terminal_payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="ascii",
    )
    runtime_path = (
        artifact_root
        / receipts.KIS_PAPER_INTRADAY_HEAD_INVOCATION_RECEIPT_DIRECTORY
        / receipts.KIS_PAPER_INTRADAY_HEAD_INVOCATION_RUNTIME_ARTIFACT_NAME
    )
    runtime_payload = json.loads(runtime_path.read_text(encoding="ascii"))
    runtime_payload["observed_at"] = terminal_payload["completed_at"]
    runtime_payload["receipt_sha256"] = "sha256:" + hashlib.sha256(
        terminal_path.read_bytes()
    ).hexdigest()
    runtime_path.write_bytes(receipts._canonical_json(runtime_payload))

    with pytest.raises(ValueError, match="terminal receipt"):
        receipts.read_current_kis_paper_intraday_head_invocation_runtime_fact(
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def test_reader_rejects_a_schedule_time_after_terminal_completion(tmp_path: Path) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    started_at = datetime(2026, 8, 19, 15, 29, tzinfo=UTC)
    receipts.write_started_kis_paper_intraday_head_invocation_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id="head-unit",
        started_at=started_at,
    )
    receipts.write_terminal_kis_paper_intraday_head_invocation_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id="head-unit",
        started_at=started_at,
        schedule_observed_at=started_at + timedelta(seconds=1),
        completed_at=started_at + timedelta(seconds=2),
        collection_exit_code=0,
        schedule_receipt_status="complete",
        terminal_exit_code=0,
    )
    terminal_path = _receipt_path(artifact_root, "head-unit", "terminal")
    terminal_payload = json.loads(terminal_path.read_text(encoding="ascii"))
    terminal_payload["schedule_observed_at"] = "2026-08-19T15:29:03Z"
    terminal_path.write_text(
        json.dumps(terminal_payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="ascii",
    )
    runtime_path = (
        artifact_root
        / receipts.KIS_PAPER_INTRADAY_HEAD_INVOCATION_RECEIPT_DIRECTORY
        / receipts.KIS_PAPER_INTRADAY_HEAD_INVOCATION_RUNTIME_ARTIFACT_NAME
    )
    runtime_payload = json.loads(runtime_path.read_text(encoding="ascii"))
    runtime_payload["receipt_sha256"] = "sha256:" + hashlib.sha256(
        terminal_path.read_bytes()
    ).hexdigest()
    runtime_path.write_bytes(receipts._canonical_json(runtime_payload))

    with pytest.raises(ValueError, match="terminal receipt"):
        receipts.read_current_kis_paper_intraday_head_invocation_terminal_fact(
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    repository_root = tmp_path / "repository"
    artifact_root = tmp_path / "model-artifacts"
    repository_root.mkdir()
    artifact_root.mkdir()
    return repository_root, artifact_root


def _receipt_path(artifact_root: Path, run_id: str, phase: str) -> Path:
    return (
        artifact_root
        / receipts.KIS_PAPER_INTRADAY_HEAD_INVOCATION_RECEIPT_DIRECTORY
        / run_id
        / f"{phase}.json"
    )


def _load_projector() -> ModuleType:
    spec = importlib.util.spec_from_file_location("invocation_receipt_projector", _PROJECTOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
