from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.execution.kis_paper_console_bridge import (
    recover_kis_paper_console_bridge_evidence,
    run_kis_paper_console_bridge,
    write_kis_paper_console_bridge_evidence,
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


@dataclass
class FakeKisTransport:
    runtime_snapshot_path: Path
    reject_open_orders: bool = False
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
                        "msg_cd": "raw-server-code-must-not-persist",
                        "msg1": "raw-response-text-must-not-persist",
                    },
                    status_code=403,
                )
            return KisHttpResponse.from_payload({"rt_cd": "0", "output": []})
        if tr_id == KIS_PAPER_BALANCE_ENDPOINT.tr_id:
            exchange = request.query["OVRS_EXCG_CD"]
            rows = [_position_payload()] if exchange == "NASD" else []
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


def test_snapshot_schema_rejects_legacy_cash_and_unpinned_funds_source(tmp_path) -> None:
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


def test_bridge_publishes_only_a_sanitized_complete_snapshot_and_evidence(tmp_path) -> None:
    runtime_snapshot_path = tmp_path / "runtime" / "paper_account_snapshot.json"
    transport = FakeKisTransport(runtime_snapshot_path)
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
        Decimal("1"),
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
    assert read_paper_account_snapshot(runtime_snapshot_path, now=NOW).status == "unavailable"
    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    assert "raw-response-text-must-not-persist" not in evidence
    assert "12345678" not in evidence
    assert "SPY" not in evidence


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
            Decimal("1"),
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
                Decimal("510"),
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
        "pchs_avg_pric": "500",
        "now_pric2": "510",
    }
