from __future__ import annotations

import importlib.util
import json
import socket
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest

from thericher_v2.execution.kis_paper_console_bridge import (
    write_kis_paper_console_bridge_evidence,
    write_kis_paper_snapshot_observer_evidence,
)
from thericher_v2.execution.paper_account_snapshot import (
    PaperAccountOpenOrder,
    PaperAccountOrderableForeignFunds,
    PaperAccountPosition,
    PaperAccountReferenceOrderability,
    PaperAccountSnapshot,
)

NOW = datetime(2026, 8, 7, 13, 32, tzinfo=UTC)
INVOCATION_ID = "11b1d3e5-67d9-4a4d-a9ee-08cb7d54d889"
SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "reattest_kis_paper_snapshot_observer.py"
)


def _load_script() -> ModuleType:
    specification = importlib.util.spec_from_file_location(
        "reattest_kis_paper_snapshot_observer_for_test",
        SCRIPT_PATH,
    )
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _observer_receipt(tmp_path: Path) -> tuple[Path, Path, Path]:
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    snapshot = PaperAccountSnapshot.unavailable(
        observed_at=NOW,
        reason_code="auth_rejected",
    )
    bridge_path = write_kis_paper_console_bridge_evidence(
        snapshot,
        snapshot_digest="0" * 64,
        artifact_root=artifact_root,
        repository_root=repository_root,
        observer_invocation_id=INVOCATION_ID,
    )
    observer_path = write_kis_paper_snapshot_observer_evidence(
        status="unavailable",
        observed_at=NOW,
        reason_code="auth_rejected",
        observer_invocation_id=INVOCATION_ID,
        bridge_evidence_path=bridge_path,
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    return observer_path, artifact_root, repository_root


def _complete_observer_receipt(tmp_path: Path) -> tuple[Path, Path, Path]:
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    snapshot = PaperAccountSnapshot(
        status="complete",
        observed_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
        orderable_foreign_funds=PaperAccountOrderableForeignFunds("USD", Decimal("1200.50")),
        reference_orderability=PaperAccountReferenceOrderability(
            "USD",
            Decimal("1199.75"),
            "NASD",
            "SPY",
        ),
        positions=(PaperAccountPosition("NASD", "SPY", "USD", Decimal("2")),),
        open_orders=(
            PaperAccountOpenOrder(
                "NASD",
                "SPY",
                "USD",
                "buy",
                Decimal("5"),
                Decimal("2"),
                Decimal("3"),
            ),
        ),
    )
    bridge_path = write_kis_paper_console_bridge_evidence(
        snapshot,
        snapshot_digest="1" * 64,
        artifact_root=artifact_root,
        repository_root=repository_root,
        observer_invocation_id=INVOCATION_ID,
    )
    observer_path = write_kis_paper_snapshot_observer_evidence(
        status="complete",
        observed_at=NOW,
        reason_code=None,
        observer_invocation_id=INVOCATION_ID,
        bridge_evidence_path=bridge_path,
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    return observer_path, artifact_root, repository_root


def test_reattaches_one_explicit_fact_minimized_observer_receipt(tmp_path, capsys) -> None:
    observer_path, artifact_root, repository_root = _observer_receipt(tmp_path)

    exit_code = _load_script().main(
        [
            "--evidence-path",
            str(observer_path),
            "--artifact-root",
            str(artifact_root),
            "--repository-root",
            str(repository_root),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "bridge_evidence_path": "execution/kis-paper-console-bridge/"
        + f"{NOW.strftime('%Y%m%dT%H%M%S%fZ')}-unavailable.json",
        "kind": "kis_paper_snapshot_observer_reattachment",
        "observed_at": NOW.isoformat(),
        "observer_invocation_id": INVOCATION_ID,
        "reason_code": "auth_rejected",
        "scope": "read_only",
        "status": "unavailable",
        "submit_capability": False,
    }
    serialized = json.dumps(payload, sort_keys=True)
    for forbidden in ("facts", "account", "balance", "price", "position", "order"):
        assert forbidden not in serialized


def test_reattachment_is_categorical_for_missing_or_tampered_evidence(tmp_path, capsys) -> None:
    observer_path, artifact_root, repository_root = _observer_receipt(tmp_path)
    observer_path.write_text("{}\n", encoding="utf-8")

    exit_code = _load_script().main(
        [
            "--evidence-path",
            str(observer_path),
            "--artifact-root",
            str(artifact_root),
            "--repository-root",
            str(repository_root),
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().out) == {
        "kind": "kis_paper_snapshot_observer_reattachment",
        "reason_code": "observer_evidence_unavailable",
        "scope": "read_only",
        "status": "unavailable",
        "submit_capability": False,
    }


def test_reattachment_never_exposes_complete_account_facts(tmp_path, capsys) -> None:
    observer_path, artifact_root, repository_root = _complete_observer_receipt(tmp_path)

    exit_code = _load_script().main(
        [
            "--evidence-path",
            str(observer_path),
            "--artifact-root",
            str(artifact_root),
            "--repository-root",
            str(repository_root),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "complete"
    assert payload["scope"] == "read_only"
    assert payload["submit_capability"] is False
    serialized = json.dumps(payload, sort_keys=True)
    for forbidden in (
        "facts",
        "USD",
        "NASD",
        "SPY",
        "1200.50",
        "1199.75",
        "position_count",
        "open_order_count",
    ):
        assert forbidden not in serialized


def test_reattachment_does_not_reach_network(tmp_path, capsys, monkeypatch) -> None:
    observer_path, artifact_root, repository_root = _observer_receipt(tmp_path)

    def forbid_network(*_args, **_kwargs):
        raise AssertionError("reattachment must not reach network")

    monkeypatch.setattr(socket, "create_connection", forbid_network)
    exit_code = _load_script().main(
        [
            "--evidence-path",
            str(observer_path),
            "--artifact-root",
            str(artifact_root),
            "--repository-root",
            str(repository_root),
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "unavailable"


def test_reattachment_requires_an_explicit_evidence_path() -> None:
    with pytest.raises(SystemExit):
        _load_script().build_parser().parse_args([])


def test_reattachment_script_has_no_live_network_or_credential_surface() -> None:
    source = SCRIPT_PATH.read_text(encoding="ascii").lower()

    for forbidden in (
        "kis_live",
        "os.environ",
        "urllib",
        "requests",
        "socket",
        "subprocess",
        "docker",
        "http",
        "order",
        "quote",
        "market_data",
    ):
        assert forbidden not in source
