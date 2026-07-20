from __future__ import annotations

import ast
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from thericher_v2.execution.paper_account_snapshot import (
    PAPER_ACCOUNT_SNAPSHOT_TTL,
    PaperAccountOpenOrder,
    PaperAccountOrderableForeignFunds,
    PaperAccountPosition,
    PaperAccountReferenceOrderability,
    PaperAccountSnapshot,
    PaperAccountSnapshotRead,
    read_paper_account_snapshot,
    write_paper_account_snapshot,
)
from thericher_v2.execution.paper_capital_proposal import (
    PaperCapitalPolicy,
    main,
    propose_paper_capital,
    read_paper_capital_proposal,
)

NOW = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)


def test_fresh_empty_snapshot_proposes_only_same_currency_cash_ceiling() -> None:
    proposal = propose_paper_capital(
        _available(_snapshot(funds="1200", reference="1")),
        policy=PaperCapitalPolicy("USD", Decimal("500")),
        now=NOW + timedelta(minutes=1),
    )

    assert proposal.status == "awaiting_operator_approval"
    assert proposal.candidate_ceiling == Decimal("500")
    assert proposal.currency == "USD"
    assert proposal.basis == "orderable_foreign_funds"
    assert proposal.reference_orderability_used is False
    assert proposal.operator_approval_required is True
    assert proposal.submission_capability is False
    assert proposal.valid_until == NOW + PAPER_ACCOUNT_SNAPSHOT_TTL


def test_reference_orderability_never_changes_the_cash_basis_candidate() -> None:
    policy = PaperCapitalPolicy("USD", Decimal("500"))
    first = propose_paper_capital(
        _available(_snapshot(funds="900", reference="1")),
        policy=policy,
        now=NOW + timedelta(minutes=1),
    )
    second = propose_paper_capital(
        _available(_snapshot(funds="900", reference="700")),
        policy=policy,
        now=NOW + timedelta(minutes=1),
    )

    assert first.candidate_ceiling == Decimal("500")
    assert second.candidate_ceiling == Decimal("500")


def test_proposal_abstains_for_missing_stale_future_or_bad_policy() -> None:
    policy = PaperCapitalPolicy("USD", Decimal("500"))
    snapshot = _snapshot()

    assert propose_paper_capital(
        PaperAccountSnapshotRead(status="unknown"), policy=policy, now=NOW
    ).reason_codes == ("snapshot_unknown",)
    assert propose_paper_capital(
        PaperAccountSnapshotRead(status="unavailable"), policy=policy, now=NOW
    ).reason_codes == ("snapshot_unavailable",)
    assert propose_paper_capital(
        _available(snapshot), policy=None, now=NOW + timedelta(minutes=1)
    ).reason_codes == ("operator_ceiling_missing",)
    assert propose_paper_capital(
        _available(snapshot),
        policy=PaperCapitalPolicy("KRW", Decimal("500")),
        now=NOW + timedelta(minutes=1),
    ).reason_codes == ("currency_mismatch",)
    assert propose_paper_capital(
        _available(snapshot), policy=policy, now=NOW - timedelta(seconds=1)
    ).reason_codes == ("snapshot_time_invalid",)
    assert propose_paper_capital(
        _available(snapshot), policy=policy, now=NOW + PAPER_ACCOUNT_SNAPSHOT_TTL
    ).reason_codes == ("snapshot_expired",)


def test_proposal_abstains_for_existing_exposure_or_unqualified_funds() -> None:
    policy = PaperCapitalPolicy("USD", Decimal("500"))
    cases = (
        (
            _snapshot(
                positions=(PaperAccountPosition("NASD", "SPY", "USD", Decimal("1")),)
            ),
            "positions_present",
        ),
        (
            _snapshot(
                open_orders=(
                    PaperAccountOpenOrder(
                        "NASD",
                        "SPY",
                        "USD",
                        "buy",
                        Decimal("2"),
                        Decimal("0"),
                        Decimal("2"),
                        Decimal("500"),
                    ),
                )
            ),
            "open_orders_present",
        ),
        (_snapshot(funds="0"), "orderable_foreign_funds_unavailable"),
        (_snapshot(reference="0"), "reference_orderability_unavailable"),
        (_snapshot(reference_currency="KRW"), "reference_currency_mismatch"),
    )

    for snapshot, expected_reason in cases:
        proposal = propose_paper_capital(
            _available(snapshot), policy=policy, now=NOW + timedelta(minutes=1)
        )
        assert proposal.status == "abstain"
        assert proposal.reason_codes == (expected_reason,)
        assert proposal.candidate_ceiling is None


def test_reader_and_command_fail_closed_at_exact_expiry_without_credentials(
    tmp_path, capsys
) -> None:
    path = tmp_path / "paper_account_snapshot.json"
    snapshot = _snapshot()
    write_paper_account_snapshot(snapshot, path)

    assert (
        read_paper_account_snapshot(path, now=snapshot.expires_at).status == "unavailable"
    )
    stale = read_paper_capital_proposal(
        runtime_snapshot_path=path,
        policy=PaperCapitalPolicy("USD", Decimal("500")),
        now=snapshot.expires_at,
    )
    assert stale.reason_codes == ("snapshot_unavailable",)

    expired_for_command = _snapshot(observed_at=datetime(2020, 1, 1, tzinfo=UTC))
    write_paper_account_snapshot(expired_for_command, path)
    assert (
        main(
            [
                "--runtime-snapshot",
                str(path),
                "--currency",
                "USD",
                "--operator-ceiling",
                "500",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "abstain"
    assert payload["submission_capability"] is False


def test_proposal_module_has_no_kis_broker_environment_or_network_dependency() -> None:
    module_path = (
        Path(__file__).parents[1]
        / "src"
        / "thericher_v2"
        / "execution"
        / "paper_capital_proposal.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert all("kis" not in module for module in imported_modules)
    assert all("broker" not in module for module in imported_modules)
    assert all(module not in {"os", "urllib", "requests", "socket"} for module in imported_modules)
    source = module_path.read_text(encoding="utf-8")
    assert "OrderIntent" not in source
    assert "BrokerOrderRequest" not in source
    assert "os.environ" not in source


def _available(snapshot: PaperAccountSnapshot) -> PaperAccountSnapshotRead:
    return PaperAccountSnapshotRead(status="available", snapshot=snapshot)


def _snapshot(
    *,
    observed_at: datetime = NOW,
    funds: str = "1200",
    reference: str = "1199",
    reference_currency: str = "USD",
    positions: tuple[PaperAccountPosition, ...] = (),
    open_orders: tuple[PaperAccountOpenOrder, ...] = (),
) -> PaperAccountSnapshot:
    return PaperAccountSnapshot(
        status="complete",
        observed_at=observed_at,
        expires_at=observed_at + PAPER_ACCOUNT_SNAPSHOT_TTL,
        orderable_foreign_funds=PaperAccountOrderableForeignFunds("USD", Decimal(funds)),
        reference_orderability=PaperAccountReferenceOrderability(
            reference_currency,
            Decimal(reference),
            "NASD",
            "SPY",
            Decimal("1"),
        ),
        positions=positions,
        open_orders=open_orders,
    )
