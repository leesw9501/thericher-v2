from __future__ import annotations

import json
import multiprocessing
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest

import thericher_v2.execution.kis_paper_console_bridge as console_bridge
from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.execution.kis_paper_console_bridge import (
    read_kis_paper_snapshot_observer_evidence,
    recover_kis_paper_console_bridge_evidence,
    run_kis_paper_console_bridge,
    write_kis_paper_console_bridge_evidence,
    write_kis_paper_snapshot_observer_evidence,
)
from thericher_v2.execution.kis_readonly import (
    KIS_PAPER_BALANCE_ENDPOINT,
    KIS_PAPER_OPEN_ORDERS_ENDPOINT,
    KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT,
    KisHttpRequest,
    KisHttpResponse,
)
from thericher_v2.execution.paper_account_snapshot import (
    PAPER_ACCOUNT_SNAPSHOT_TTL,
    PaperAccountOpenOrder,
    PaperAccountOrderableForeignFunds,
    PaperAccountPosition,
    PaperAccountReferenceOrderability,
    PaperAccountSnapshot,
    read_paper_account_snapshot,
    write_paper_account_snapshot,
)

NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _hold_runtime_snapshot_lock(path: str, ready: object, release: object) -> None:
    with console_bridge._exclusive_runtime_snapshot_refresh_lock(Path(path)) as acquired:
        assert acquired
        ready.set()
        assert release.wait(10)


@dataclass
class FakeKisTransport:
    runtime_snapshot_path: Path
    reject_open_orders: bool = False
    flat_account: bool = False
    include_open_order: bool = False
    reject_open_orders_code: object = "raw-server-code-must-not-persist"
    reject_open_orders_message: str = "raw-response-text-must-not-persist"
    requests: list[KisHttpRequest] = field(default_factory=list)
    saw_unavailable_before_token: bool = False

    def request(self, request: KisHttpRequest) -> KisHttpResponse:
        self.requests.append(request)
        if request.method == "POST":
            state = read_paper_account_snapshot(self.runtime_snapshot_path, now=NOW)
            self.saw_unavailable_before_token = state.status == "unavailable"
            return KisHttpResponse.from_payload({"access_token": "temporary-access-token"})
        tr_id = request.headers["tr_id"]
        if tr_id == KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id:
            if self.reject_open_orders:
                return KisHttpResponse.from_payload(
                    {
                        "rt_cd": "1",
                        "msg_cd": self.reject_open_orders_code,
                        "msg1": self.reject_open_orders_message,
                    },
                    status_code=403,
                )
            return KisHttpResponse.from_payload(
                {"rt_cd": "0", "output": [_open_order_payload()] if self.include_open_order else []}
            )
        if tr_id == KIS_PAPER_BALANCE_ENDPOINT.tr_id:
            exchange = request.query["OVRS_EXCG_CD"]
            rows = [] if self.flat_account or exchange != "NASD" else [_position_payload()]
            return KisHttpResponse.from_payload({"rt_cd": "0", "output1": rows})
        if tr_id == KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.tr_id:
            return KisHttpResponse.from_payload(
                {
                    "rt_cd": "0",
                    "output": {
                        "tr_crcy_cd": "USD",
                        "ord_psbl_frcr_amt": "1200.50",
                        "ovrs_ord_psbl_amt": "1199.75",
                    },
                }
            )
        raise AssertionError("unexpected KIS request")


def test_snapshot_reader_distinguishes_unknown_complete_stale_and_malformed(tmp_path) -> None:
    path = tmp_path / "runtime" / "paper_account_snapshot.json"

    assert read_paper_account_snapshot(path, now=NOW).status == "unknown"

    complete = _complete_snapshot(NOW)
    write_paper_account_snapshot(complete, path)
    current = read_paper_account_snapshot(path, now=NOW + timedelta(minutes=1))
    assert current.status == "available"
    assert current.snapshot is not None
    assert current.snapshot.positions == (
        PaperAccountPosition("NASD", "SPY", "USD", Decimal("2")),
    )

    stale = read_paper_account_snapshot(path, now=NOW + PAPER_ACCOUNT_SNAPSHOT_TTL + timedelta(1))
    assert stale.status == "unavailable"
    assert stale.snapshot is None

    path.write_text('{"account_number":"12345678"}\n', encoding="utf-8")
    malformed = read_paper_account_snapshot(path, now=NOW)
    assert malformed.status == "unavailable"
    assert malformed.snapshot is None


def test_snapshot_schema_rejects_legacy_cash_unpinned_funds_and_price_bearing_shapes(
    tmp_path,
) -> None:
    path = tmp_path / "runtime" / "paper_account_snapshot.json"
    legacy = _complete_snapshot(NOW).to_dict()
    legacy["schema_version"] = 1
    facts = legacy["facts"]
    assert isinstance(facts, dict)
    funds = facts.pop("orderable_foreign_funds")
    assert isinstance(funds, dict)
    facts["cash"] = {
        "currency": funds["currency"],
        "available_cash": funds["amount"],
    }
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(legacy), encoding="utf-8")

    assert read_paper_account_snapshot(path, now=NOW).status == "unavailable"
    with pytest.raises(ValueError, match="orderable_foreign_funds_source_invalid"):
        PaperAccountOrderableForeignFunds("USD", Decimal("1"), "other")

    price_bearing = _complete_snapshot(NOW).to_dict()
    price_facts = price_bearing["facts"]
    assert isinstance(price_facts, dict)
    reference = price_facts["reference_orderability"]
    assert isinstance(reference, dict)
    reference["reference_price"] = "1"
    open_orders = price_facts["open_orders"]
    assert isinstance(open_orders, list)
    assert isinstance(open_orders[0], dict)
    open_orders[0]["limit_price"] = "731.29"
    path.write_text(json.dumps(price_bearing), encoding="utf-8")

    assert read_paper_account_snapshot(path, now=NOW).status == "unavailable"


def test_bridge_publishes_only_a_sanitized_complete_snapshot_and_evidence(tmp_path) -> None:
    runtime_snapshot_path = tmp_path / "runtime" / "paper_account_snapshot.json"
    transport = FakeKisTransport(runtime_snapshot_path, include_open_order=True)
    environment = _paper_environment()

    outcome = run_kis_paper_console_bridge(
        environment=environment,
        runtime_snapshot_path=runtime_snapshot_path,
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        transport=transport,
        clock=lambda: NOW,
    )

    assert outcome.status == "complete"
    assert outcome.reason_code is None
    assert transport.saw_unavailable_before_token
    assert [request.headers.get("tr_id") for request in transport.requests[1:]] == [
        KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id,
        KIS_PAPER_BALANCE_ENDPOINT.tr_id,
        KIS_PAPER_BALANCE_ENDPOINT.tr_id,
        KIS_PAPER_BALANCE_ENDPOINT.tr_id,
        KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.tr_id,
    ]

    runtime = runtime_snapshot_path.read_text(encoding="utf-8")
    assert "12345678" not in runtime
    assert "test-app-key" not in runtime
    assert "test-app-secret" not in runtime
    assert "live-secret-must-not-be-read" not in runtime
    assert "ORD-" not in runtime
    assert "****" not in runtime
    assert "913.37" not in runtime
    assert "914.42" not in runtime
    assert "731.29" not in runtime

    current = read_paper_account_snapshot(runtime_snapshot_path, now=NOW)
    assert current.status == "available"
    assert current.snapshot is not None
    assert current.snapshot.orderable_foreign_funds == PaperAccountOrderableForeignFunds(
        "USD", Decimal("1200.50")
    )
    assert current.snapshot.reference_orderability == PaperAccountReferenceOrderability(
        "USD",
        Decimal("1199.75"),
        "NASD",
        "SPY",
    )
    assert current.snapshot.open_orders == (
        PaperAccountOpenOrder(
            "NASD",
            "SPY",
            "USD",
            "buy",
            Decimal("5"),
            Decimal("2"),
            Decimal("3"),
        ),
    )

    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    for forbidden in (
        "12345678",
        "test-app-key",
        "test-app-secret",
        "live-secret-must-not-be-read",
        "SPY",
        "1200.50",
        "1199.75",
        "ORD-",
    ):
        assert forbidden not in evidence


def test_busy_bridge_lock_preserves_the_prior_snapshot_without_credential_or_network_access(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_snapshot_path = tmp_path / "runtime" / "paper_account_snapshot.json"
    write_paper_account_snapshot(
        _complete_snapshot(NOW - timedelta(minutes=1)), runtime_snapshot_path
    )
    prior_snapshot = runtime_snapshot_path.read_bytes()
    transport = FakeKisTransport(runtime_snapshot_path)

    @contextmanager
    def unavailable_refresh_lock(_: Path):
        yield False

    class PoisonEnvironment:
        def get(self, *_args: object, **_kwargs: object) -> str:
            raise AssertionError("busy bridge must not read credentials")

    monkeypatch.setattr(
        console_bridge,
        "_exclusive_runtime_snapshot_refresh_lock",
        unavailable_refresh_lock,
    )

    outcome = run_kis_paper_console_bridge(
        environment=PoisonEnvironment(),  # type: ignore[arg-type]
        runtime_snapshot_path=runtime_snapshot_path,
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        transport=transport,
        clock=lambda: NOW,
    )

    assert outcome.status == "busy"
    assert outcome.reason_code == "refresh_busy"
    assert outcome.evidence_path is None
    assert outcome.diagnostic == {}
    assert transport.requests == []
    assert runtime_snapshot_path.read_bytes() == prior_snapshot
    assert not (tmp_path / "artifacts").exists()


def test_runtime_volume_lock_rejects_a_second_bridge_process_without_side_effects(
    tmp_path,
) -> None:
    runtime_snapshot_path = tmp_path / "runtime" / "paper_account_snapshot.json"
    write_paper_account_snapshot(
        _complete_snapshot(NOW - timedelta(minutes=1)), runtime_snapshot_path
    )
    prior_snapshot = runtime_snapshot_path.read_bytes()
    transport = FakeKisTransport(runtime_snapshot_path)

    class PoisonEnvironment:
        def get(self, *_args: object, **_kwargs: object) -> str:
            raise AssertionError("busy bridge must not read credentials")

    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    process = context.Process(
        target=_hold_runtime_snapshot_lock,
        args=(str(runtime_snapshot_path), ready, release),
    )
    process.start()
    try:
        assert ready.wait(10)
        outcome = run_kis_paper_console_bridge(
            environment=PoisonEnvironment(),  # type: ignore[arg-type]
            runtime_snapshot_path=runtime_snapshot_path,
            artifact_root=tmp_path / "artifacts",
            repository_root=tmp_path / "repo",
            transport=transport,
            clock=lambda: NOW,
        )
    finally:
        release.set()
        process.join(10)
        if process.is_alive():
            process.terminate()
            process.join(10)

    assert process.exitcode == 0
    assert outcome.status == "busy"
    assert outcome.reason_code == "refresh_busy"
    assert outcome.evidence_path is None
    assert transport.requests == []
    assert runtime_snapshot_path.read_bytes() == prior_snapshot
    assert not (tmp_path / "artifacts").exists()


def test_busy_bridge_cli_emits_a_source_safe_non_error_outcome(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    @contextmanager
    def unavailable_refresh_lock(_: Path):
        yield False

    monkeypatch.setattr(
        console_bridge,
        "_exclusive_runtime_snapshot_refresh_lock",
        unavailable_refresh_lock,
    )

    exit_code = console_bridge.main(
        [
            "--execute",
            "--runtime-snapshot",
            str(tmp_path / "runtime" / "paper_account_snapshot.json"),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--repository-root",
            str(tmp_path / "repo"),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "busy"
    assert payload["reason_code"] == "refresh_busy"
    assert payload["account_snapshot_complete"] is False
    assert payload["evidence_path"] is None
    assert payload["observer_evidence_path"] is None
    assert payload["observer_invocation_id"] is None
    assert payload["scope"] == "read_only"
    assert isinstance(payload["observed_at"], str)
    assert not (tmp_path / "runtime").exists()
    assert not (tmp_path / "artifacts").exists()


def test_bridge_accepts_a_valid_flat_account_without_exposing_account_facts(tmp_path) -> None:
    runtime_snapshot_path = tmp_path / "runtime" / "paper_account_snapshot.json"
    outcome = run_kis_paper_console_bridge(
        environment=_paper_environment(),
        runtime_snapshot_path=runtime_snapshot_path,
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        transport=FakeKisTransport(runtime_snapshot_path, flat_account=True),
        clock=lambda: NOW,
    )

    assert outcome.status == "complete"
    snapshot = read_paper_account_snapshot(runtime_snapshot_path, now=NOW)
    assert snapshot.status == "available"
    assert snapshot.snapshot is not None
    assert snapshot.snapshot.positions == ()
    assert snapshot.snapshot.open_orders == ()

    payload = json.loads(outcome.evidence_path.read_text(encoding="utf-8"))
    assert payload["status"] == "complete"
    assert payload["paper_only"] is True
    assert payload["submit_capability"] is False
    assert payload["facts"]["position_count"] == 0
    assert payload["facts"]["open_order_count"] == 0
    assert "observer_invocation_id" not in payload
    assert outcome.observer_evidence_path is None
    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    for forbidden in ("12345678", "test-app-key", "test-app-secret", "SPY", "1200.50"):
        assert forbidden not in evidence


def test_bridge_records_only_a_canonical_observer_invocation_id(tmp_path) -> None:
    runtime_snapshot_path = tmp_path / "runtime" / "paper_account_snapshot.json"
    invocation_id = "79c1f5dd-b7e5-4f30-875c-4d59ce6e88c3"
    outcome = run_kis_paper_console_bridge(
        environment={
            **_paper_environment(),
            "THERICHER_KIS_PAPER_SNAPSHOT_OBSERVER_INVOCATION_ID": invocation_id,
        },
        runtime_snapshot_path=runtime_snapshot_path,
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        transport=FakeKisTransport(runtime_snapshot_path),
        clock=lambda: NOW,
    )

    assert outcome.status == "complete"
    assert outcome.observer_evidence_path is not None
    bridge_payload = json.loads(outcome.evidence_path.read_text(encoding="utf-8"))
    assert bridge_payload["observer_invocation_id"] == invocation_id
    payload = json.loads(outcome.observer_evidence_path.read_text(encoding="utf-8"))
    assert payload == {
        "bridge_evidence": {
            "relative_path": "execution/kis-paper-console-bridge/"
            + outcome.evidence_path.name,
            "sha256": sha256(outcome.evidence_path.read_bytes()).hexdigest(),
        },
        "kind": "kis_paper_snapshot_observer",
        "observed_at": NOW.isoformat(),
        "observer_invocation_id": invocation_id,
        "schema_version": SCHEMA_VERSION,
        "scope": "read_only",
        "status": "complete",
        "submit_capability": False,
    }
    assert "facts" not in payload
    assert read_kis_paper_snapshot_observer_evidence(
        evidence_path=outcome.observer_evidence_path,
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
    ) == {
        "bridge_evidence_path": "execution/kis-paper-console-bridge/"
        + outcome.evidence_path.name,
        "observed_at": NOW.isoformat(),
        "observer_invocation_id": invocation_id,
        "scope": "read_only",
        "status": "complete",
        "submit_capability": False,
    }
    with pytest.raises(ValueError, match="already exists"):
        write_kis_paper_snapshot_observer_evidence(
            status="complete",
            observed_at=NOW,
            reason_code=None,
            observer_invocation_id=invocation_id,
            bridge_evidence_path=outcome.evidence_path,
            artifact_root=tmp_path / "artifacts",
            repository_root=tmp_path / "repo",
        )


def test_tagged_bridge_cli_revalidates_observer_evidence_before_emitting_marker(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runtime_snapshot_path = tmp_path / "runtime" / "paper_account_snapshot.json"
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    invocation_id = "9f19cfc1-a07c-438a-9142-ef89c6bca7a9"
    original_run = console_bridge.run_kis_paper_console_bridge
    original_reader = console_bridge.read_kis_paper_snapshot_observer_evidence
    read_calls: list[Path] = []

    def tagged_fake_run(**_kwargs: object) -> console_bridge.KisPaperConsoleBridgeOutcome:
        return original_run(
            environment={
                **_paper_environment(),
                "THERICHER_KIS_PAPER_SNAPSHOT_OBSERVER_INVOCATION_ID": invocation_id,
            },
            runtime_snapshot_path=runtime_snapshot_path,
            artifact_root=artifact_root,
            repository_root=repository_root,
            transport=FakeKisTransport(runtime_snapshot_path),
            clock=lambda: NOW,
        )

    def recording_reader(**kwargs: object) -> dict[str, object]:
        evidence_path = kwargs["evidence_path"]
        assert isinstance(evidence_path, Path)
        read_calls.append(evidence_path)
        return original_reader(
            evidence_path=evidence_path,
            artifact_root=artifact_root,
            repository_root=repository_root,
        )

    monkeypatch.setattr(console_bridge, "run_kis_paper_console_bridge", tagged_fake_run)
    monkeypatch.setattr(
        console_bridge,
        "read_kis_paper_snapshot_observer_evidence",
        recording_reader,
    )

    exit_code = console_bridge.main(
        [
            "--execute",
            "--runtime-snapshot",
            str(runtime_snapshot_path),
            "--artifact-root",
            str(artifact_root),
            "--repository-root",
            str(repository_root),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["observer_invocation_id"] == invocation_id
    assert payload["observer_evidence_path"] is not None
    assert len(read_calls) == 1


def test_observer_evidence_rejects_a_mutated_bridge_receipt(tmp_path) -> None:
    runtime_snapshot_path = tmp_path / "runtime" / "paper_account_snapshot.json"
    outcome = run_kis_paper_console_bridge(
        environment={
            **_paper_environment(),
            "THERICHER_KIS_PAPER_SNAPSHOT_OBSERVER_INVOCATION_ID": (
                "8b81f5dd-b7e5-4f30-875c-4d59ce6e88c3"
            ),
        },
        runtime_snapshot_path=runtime_snapshot_path,
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        transport=FakeKisTransport(runtime_snapshot_path),
        clock=lambda: NOW,
    )

    assert outcome.evidence_path is not None
    assert outcome.observer_evidence_path is not None
    outcome.evidence_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="digest does not match"):
        read_kis_paper_snapshot_observer_evidence(
            evidence_path=outcome.observer_evidence_path,
            artifact_root=tmp_path / "artifacts",
            repository_root=tmp_path / "repo",
        )


def test_observer_evidence_requires_a_matching_tagged_bridge_receipt(tmp_path) -> None:
    bridge_evidence_path = write_kis_paper_console_bridge_evidence(
        _complete_snapshot(NOW),
        snapshot_digest="0" * 64,
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
    )

    with pytest.raises(ValueError, match="bridge evidence contract"):
        write_kis_paper_snapshot_observer_evidence(
            status="complete",
            observed_at=NOW,
            reason_code=None,
            observer_invocation_id="603a4aed-6c95-4654-a084-4bbdb8183c1b",
            bridge_evidence_path=bridge_evidence_path,
            artifact_root=tmp_path / "artifacts",
            repository_root=tmp_path / "repo",
        )

    assert not (tmp_path / "artifacts" / "execution" / "kis-paper-snapshot-observer").exists()


def test_observer_evidence_rejects_busy_status_before_writing(tmp_path) -> None:
    with pytest.raises(ValueError, match="status is invalid"):
        write_kis_paper_snapshot_observer_evidence(
            status="busy",  # type: ignore[arg-type]
            observed_at=NOW,
            reason_code="refresh_busy",
            observer_invocation_id="5539f147-c892-42a7-acfc-c0b2b8bccf9d",
            bridge_evidence_path=tmp_path / "missing.json",
            artifact_root=tmp_path / "artifacts",
            repository_root=tmp_path / "repo",
        )

    assert not (tmp_path / "artifacts").exists()


def test_bridge_evidence_is_create_only(tmp_path) -> None:
    snapshot = _complete_snapshot(NOW)
    write_kis_paper_console_bridge_evidence(
        snapshot,
        snapshot_digest="0" * 64,
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
    )

    with pytest.raises(ValueError, match="evidence already exists"):
        write_kis_paper_console_bridge_evidence(
            snapshot,
            snapshot_digest="0" * 64,
            artifact_root=tmp_path / "artifacts",
            repository_root=tmp_path / "repo",
        )


def test_bridge_evidence_rejects_an_intermediate_reparse_namespace(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        console_bridge,
        "_path_is_link_or_reparse_point",
        lambda path: path.name == "execution",
    )

    with pytest.raises(ValueError, match="link or reparse point"):
        write_kis_paper_console_bridge_evidence(
            _complete_snapshot(NOW),
            snapshot_digest="0" * 64,
            artifact_root=tmp_path / "artifacts",
            repository_root=tmp_path / "repo",
        )


def test_tagged_unavailable_observer_evidence_excludes_diagnostics(tmp_path) -> None:
    runtime_snapshot_path = tmp_path / "runtime" / "paper_account_snapshot.json"
    invocation_id = "160e0ed0-4088-41c2-b1dd-ffdf61fe3fdf"
    outcome = run_kis_paper_console_bridge(
        environment={
            **_paper_environment(),
            "THERICHER_KIS_PAPER_SNAPSHOT_OBSERVER_INVOCATION_ID": invocation_id,
        },
        runtime_snapshot_path=runtime_snapshot_path,
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        transport=FakeKisTransport(runtime_snapshot_path, reject_open_orders=True),
        clock=lambda: NOW,
    )

    assert outcome.status == "unavailable"
    assert outcome.reason_code == "open_orders_rejected"
    assert outcome.observer_evidence_path is not None
    payload = json.loads(outcome.observer_evidence_path.read_text(encoding="utf-8"))
    assert payload["reason_code"] == "open_orders_rejected"
    assert "diagnostic" not in payload
    assert read_kis_paper_snapshot_observer_evidence(
        evidence_path=outcome.observer_evidence_path,
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
    )["reason_code"] == "open_orders_rejected"


def test_bridge_rejects_a_noncanonical_observer_invocation_id_before_snapshot_io(tmp_path) -> None:
    runtime_snapshot_path = tmp_path / "runtime" / "paper_account_snapshot.json"

    with pytest.raises(ValueError, match="UUIDv4"):
        run_kis_paper_console_bridge(
            environment={
                "THERICHER_KIS_PAPER_SNAPSHOT_OBSERVER_INVOCATION_ID": "not-a-uuid",
            },
            runtime_snapshot_path=runtime_snapshot_path,
            artifact_root=tmp_path / "artifacts",
            repository_root=tmp_path / "repo",
            clock=lambda: NOW,
        )

    assert not runtime_snapshot_path.exists()
    assert not (tmp_path / "artifacts").exists()


def test_bridge_overwrites_a_prior_complete_view_when_the_read_is_rejected(tmp_path) -> None:
    runtime_snapshot_path = tmp_path / "runtime" / "paper_account_snapshot.json"
    write_paper_account_snapshot(
        _complete_snapshot(NOW - timedelta(minutes=1)),
        runtime_snapshot_path,
    )
    transport = FakeKisTransport(runtime_snapshot_path, reject_open_orders=True)

    outcome = run_kis_paper_console_bridge(
        environment=_paper_environment(),
        runtime_snapshot_path=runtime_snapshot_path,
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        transport=transport,
        clock=lambda: NOW,
    )

    assert outcome.status == "unavailable"
    assert outcome.reason_code == "open_orders_rejected"
    assert outcome.diagnostic == {
        "endpoint": "open_orders",
        "tr_id": "VTTS3018R",
        "http_status": "403",
    }
    assert read_paper_account_snapshot(runtime_snapshot_path, now=NOW).status == "unavailable"
    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    payload = json.loads(evidence)
    assert payload["diagnostic"] == outcome.diagnostic
    assert "raw-response-text-must-not-persist" not in evidence
    assert "raw-server-code-must-not-persist" not in evidence
    assert "12345678" not in evidence
    assert "SPY" not in evidence


def test_bridge_retains_only_a_safe_upstream_code_from_a_rejected_read(tmp_path) -> None:
    runtime_snapshot_path = tmp_path / "runtime" / "paper_account_snapshot.json"
    transport = FakeKisTransport(
        runtime_snapshot_path,
        reject_open_orders=True,
        reject_open_orders_code="EGW00201",
        reject_open_orders_message="raw-message-12345678-ORD-123456789-must-not-persist",
    )

    outcome = run_kis_paper_console_bridge(
        environment=_paper_environment(),
        runtime_snapshot_path=runtime_snapshot_path,
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        transport=transport,
        clock=lambda: NOW,
    )

    expected_diagnostic = {
        "endpoint": "open_orders",
        "tr_id": KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id,
        "http_status": "403",
        "upstream_code": "EGW00201",
    }
    assert outcome.diagnostic == expected_diagnostic
    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    assert json.loads(evidence)["diagnostic"] == expected_diagnostic
    assert "raw-message-12345678-ORD-123456789-must-not-persist" not in evidence
    assert "12345678" not in evidence


def test_bridge_evidence_rejects_an_untrusted_upstream_code(tmp_path) -> None:
    with pytest.raises(ValueError, match="upstream code"):
        write_kis_paper_console_bridge_evidence(
            PaperAccountSnapshot.unavailable(
                observed_at=NOW,
                reason_code="open_orders_rejected",
            ),
            snapshot_digest="0" * 64,
            artifact_root=tmp_path / "artifacts",
            repository_root=tmp_path / "repo",
            diagnostic={
                "endpoint": "open_orders",
                "tr_id": KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id,
                "http_status": "403",
                "upstream_code": "raw-response-text-must-not-persist",
            },
        )


def test_recovery_uses_only_a_fresh_sanitized_snapshot_and_rejects_repo_artifacts(
    tmp_path,
) -> None:
    runtime_snapshot_path = tmp_path / "runtime" / "paper_account_snapshot.json"
    snapshot = _complete_snapshot(NOW)
    write_paper_account_snapshot(snapshot, runtime_snapshot_path)

    outcome = recover_kis_paper_console_bridge_evidence(
        runtime_snapshot_path=runtime_snapshot_path,
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        clock=lambda: NOW + timedelta(minutes=1),
    )

    assert outcome.status == "complete"
    assert outcome.reason_code is None
    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    for forbidden in ("SPY", "1200.50", "1199.75", "ORD-", "12345678"):
        assert forbidden not in evidence

    with pytest.raises(ValueError, match="snapshot_not_recoverable"):
        recover_kis_paper_console_bridge_evidence(
            runtime_snapshot_path=runtime_snapshot_path,
            artifact_root=tmp_path / "another-artifacts",
            repository_root=tmp_path / "repo",
            clock=lambda: NOW + PAPER_ACCOUNT_SNAPSHOT_TTL + timedelta(seconds=1),
        )

    with pytest.raises(ValueError, match="artifact_root_inside_repository"):
        write_kis_paper_console_bridge_evidence(
            snapshot,
            snapshot_digest="0" * 64,
            artifact_root=tmp_path / "repo" / "model_artifacts",
            repository_root=tmp_path / "repo",
        )


def _complete_snapshot(observed_at: datetime) -> PaperAccountSnapshot:
    return PaperAccountSnapshot(
        status="complete",
        observed_at=observed_at,
        expires_at=observed_at + PAPER_ACCOUNT_SNAPSHOT_TTL,
        orderable_foreign_funds=PaperAccountOrderableForeignFunds(
            "USD", Decimal("1200.50")
        ),
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


def _paper_environment() -> dict[str, str]:
    return {
        "KIS_PAPER_APP_KEY": "test-app-key",
        "KIS_PAPER_APP_SECRET": "test-app-secret",
        "KIS_PAPER_ACCOUNT_NO": "12345678",
        "KIS_PAPER_ACCOUNT_PRODUCT_CODE": "01",
        "KIS_LIVE_APP_KEY": "live-secret-must-not-be-read",
    }


def _position_payload() -> dict[str, str]:
    return {
        "ovrs_pdno": "SPY",
        "ovrs_excg_cd": "NASD",
        "tr_crcy_cd": "USD",
        "ovrs_cblc_qty": "2",
        "pchs_avg_pric": "913.37",
        "now_pric2": "914.42",
    }


def _open_order_payload() -> dict[str, str]:
    return {
        "odno": "ORD-123456789",
        "pdno": "SPY",
        "ovrs_excg_cd": "NASD",
        "tr_crcy_cd": "USD",
        "sll_buy_dvsn_cd": "02",
        "ft_ord_qty": "5",
        "ft_ccld_qty": "2",
        "nccs_qty": "3",
        "ft_ord_unpr3": "731.29",
    }
