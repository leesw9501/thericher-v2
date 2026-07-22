from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_daily_spy_input import KisPaperDailySpyInput
from thericher_v2.execution import kis_paper_daily_spy_session as session_module
from thericher_v2.execution.kis_paper_quote import KisPaperSpyLimitInput
from thericher_v2.execution.kis_readonly import (
    KisPaperAccountIdentity,
    KisPaperCashSnapshot,
    KisPaperOpenOrdersSnapshot,
    KisPaperOrderableFundsSnapshot,
    KisPaperPosition,
    KisPaperReadOnlySnapshot,
)

NOW = datetime(2026, 7, 22, 14, 30, tzinfo=UTC)


class NoCredentialEnvironment(Mapping[str, str]):
    def __getitem__(self, key: str) -> str:
        raise AssertionError(f"unexpected environment access: {key}")

    def __iter__(self) -> Iterator[str]:
        return iter(())

    def __len__(self) -> int:
        return 0


@dataclass
class FakePaperClient:
    limit_input: KisPaperSpyLimitInput
    observed_at: datetime | None = None
    account_snapshot: KisPaperReadOnlySnapshot | None = None

    def snapshot(self) -> KisPaperReadOnlySnapshot:
        return self.account_snapshot or _account_snapshot()

    def fetch_spy_limit_input(
        self, *, observed_at: datetime | None = None
    ) -> KisPaperSpyLimitInput:
        self.observed_at = observed_at
        return self.limit_input


@dataclass(frozen=True)
class FakeCanaryOutcome:
    run_id: str = "receipt-" + "a" * 64
    phase: str = "submitted"
    reason_code: str = "reconciliation_unresolved"

    def safe_payload(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "phase": self.phase,
            "reason_code": self.reason_code,
            "paper_only": True,
        }


def test_stale_daily_input_records_no_intent_without_credentials_or_transport(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        session_module,
        "load_kis_paper_daily_spy_input",
        lambda **_kwargs: _input(last_session=date(2026, 7, 17)),
    )

    outcome = session_module.run_kis_paper_daily_spy_session(
        environment=NoCredentialEnvironment(),
        execute=True,
        cancel_after_submit=False,
        now=NOW,
        session_id="stale-daily-input",
        **_paths(tmp_path),
    )

    assert outcome.status == "no_intent"
    assert outcome.reason_code == "daily_receipt_not_current"
    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    assert '"paper_only": true' in evidence
    assert "KIS_LIVE" not in evidence


def test_eligible_daily_receipt_reaches_only_the_receipt_canary_boundary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    daily_input = _input(last_session=date(2026, 7, 21))
    client = FakePaperClient(
        limit_input=KisPaperSpyLimitInput(
            last=Decimal("500.25"),
            decimal_places=2,
            tick_size=Decimal("0.01"),
            quoted_at=NOW,
        )
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        session_module,
        "load_kis_paper_daily_spy_input",
        lambda **_kwargs: daily_input,
    )

    def run_canary(prepared, **kwargs):
        captured["prepared"] = prepared
        captured["kwargs"] = kwargs
        return FakeCanaryOutcome()

    monkeypatch.setattr(session_module, "run_kis_paper_receipt_canary", run_canary)
    outcome = session_module.run_kis_paper_daily_spy_session(
        environment=NoCredentialEnvironment(),
        execute=True,
        cancel_after_submit=False,
        client=client,  # type: ignore[arg-type]
        now=NOW,
        session_id="eligible-daily-input",
        **_paths(tmp_path),
    )

    prepared = captured["prepared"]
    assert outcome.status == "canary_completed"
    assert client.observed_at == NOW
    assert prepared.status == "ready"
    assert prepared.route == "kis_paper"
    assert captured["kwargs"]["environment"].__class__ is NoCredentialEnvironment
    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    for forbidden in ("500.25", "D:/external/input.json", "KIS_LIVE"):
        assert forbidden not in evidence


def test_exit_receipt_with_one_current_spy_share_reaches_only_the_sell_boundary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    daily_input = _input(
        last_session=date(2026, 7, 21),
        closes=(Decimal("101"), Decimal("100")),
    )
    client = FakePaperClient(
        limit_input=KisPaperSpyLimitInput(
            last=Decimal("500.25"),
            decimal_places=2,
            tick_size=Decimal("0.01"),
            quoted_at=NOW,
        ),
        account_snapshot=_account_snapshot(positions=(_spy_position(),)),
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        session_module,
        "load_kis_paper_daily_spy_input",
        lambda **_kwargs: daily_input,
    )
    monkeypatch.setattr(
        session_module,
        "run_kis_paper_receipt_canary",
        lambda prepared, **kwargs: captured.update(prepared=prepared, kwargs=kwargs)
        or FakeCanaryOutcome(),
    )

    outcome = session_module.run_kis_paper_daily_spy_session(
        environment=NoCredentialEnvironment(),
        execute=True,
        cancel_after_submit=False,
        client=client,  # type: ignore[arg-type]
        now=NOW,
        session_id="eligible-daily-exit",
        **_paths(tmp_path),
    )

    prepared = captured["prepared"]
    assert outcome.status == "canary_completed"
    assert prepared.kis_paper_decision is not None
    assert prepared.kis_paper_decision.side == "sell"
    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    assert '"action": "sell"' in evidence
    assert '"pnl_status": "not_observed"' in evidence
    for forbidden in ("500.25", "D:/external/input.json", "KIS_LIVE", "****5678-**"):
        assert forbidden not in evidence


def test_stale_account_snapshot_does_not_fetch_a_quote_or_submit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client = FakePaperClient(
        limit_input=KisPaperSpyLimitInput(
            last=Decimal("500.25"),
            decimal_places=2,
            tick_size=Decimal("0.01"),
            quoted_at=NOW,
        ),
        account_snapshot=_account_snapshot(
            positions=(_spy_position(),),
            captured_at=NOW.replace(minute=27),
        ),
    )
    monkeypatch.setattr(
        session_module,
        "load_kis_paper_daily_spy_input",
        lambda **_kwargs: _input(last_session=date(2026, 7, 21)),
    )

    outcome = session_module.run_kis_paper_daily_spy_session(
        environment=NoCredentialEnvironment(),
        execute=True,
        cancel_after_submit=False,
        client=client,  # type: ignore[arg-type]
        now=NOW,
        session_id="stale-account-fact",
        **_paths(tmp_path),
    )

    assert outcome.status == "no_intent"
    assert outcome.reason_code == "account_snapshot_not_current"
    assert client.observed_at is None


def test_preview_is_offline_even_for_an_eligible_daily_receipt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        session_module,
        "load_kis_paper_daily_spy_input",
        lambda **_kwargs: _input(last_session=date(2026, 7, 21)),
    )

    outcome = session_module.run_kis_paper_daily_spy_session(
        environment=NoCredentialEnvironment(),
        execute=False,
        cancel_after_submit=False,
        now=NOW,
        session_id="preview-daily-input",
        **_paths(tmp_path),
    )

    assert outcome.status == "preview"
    assert outcome.reason_code == "preview"


def test_preferred_input_chooses_one_newer_head_source_without_row_mixing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    head_input = _input(last_session=date(2026, 7, 21))
    history_input = _input(last_session=date(2026, 7, 17))
    head = type(
        "Head",
        (),
        {
            "bars": head_input.bars,
            "dataset_id": head_input.catalog_dataset_id,
            "dataset_hash": head_input.catalog_dataset_hash,
        },
    )()
    monkeypatch.setattr(
        session_module,
        "load_verified_kis_paper_daily_spy_head",
        lambda **_kwargs: head,
    )
    monkeypatch.setattr(
        session_module,
        "attest_kis_paper_daily_spy_bars",
        lambda **_kwargs: head_input,
    )
    monkeypatch.setattr(
        session_module,
        "load_kis_paper_daily_spy_input",
        lambda **_kwargs: history_input,
    )

    selected = session_module._load_preferred_daily_spy_input(
        cache_root=tmp_path / "history",
        head_cache_root=tmp_path / "head",
        availability_root=tmp_path / "availability",
        repository_root=tmp_path / "repo",
        attested_at=NOW,
    )

    assert selected is head_input
    assert selected.bars == head_input.bars
    assert selected.last_consumed_session != history_input.last_consumed_session


def _input(
    *,
    last_session: date,
    closes: tuple[Decimal, Decimal] = (Decimal("100"), Decimal("101")),
) -> KisPaperDailySpyInput:
    previous_session = date(2026, 7, 20) if last_session == date(2026, 7, 21) else date(2026, 7, 16)
    return KisPaperDailySpyInput(
        bars=(
            _bar(previous_session, closes[0]),
            _bar(last_session, closes[1]),
        ),
        catalog_dataset_id="kis.paper.private.daily.backfill-v1.common-panel",
        catalog_dataset_hash="sha256:" + "a" * 64,
        last_consumed_session=last_session,
        first_available_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        input_manifest_ref="sha256:" + "b" * 64,
        availability_record_path=Path("D:/external/input.json"),
    )


def _bar(session: date, close: Decimal) -> Bar:
    return Bar(
        symbol="SPY",
        market="US",
        timeframe=Timeframe.D1,
        start_ts=datetime(session.year, session.month, session.day, tzinfo=UTC),
        open=close,
        high=close + Decimal("1"),
        low=close - Decimal("1"),
        close=close,
        volume=Decimal("1000"),
        complete=True,
    )


def _account_snapshot(
    *,
    positions: tuple[KisPaperPosition, ...] = (),
    captured_at: datetime = NOW,
) -> KisPaperReadOnlySnapshot:
    return KisPaperReadOnlySnapshot(
        identity=KisPaperAccountIdentity("****5678-**", captured_at),
        cash=KisPaperCashSnapshot("USD", Decimal("1000"), captured_at),
        orderable_funds=KisPaperOrderableFundsSnapshot(
            "USD",
            Decimal("1000"),
            "NASD",
            "SPY",
            Decimal("1"),
            captured_at,
        ),
        positions=positions,
        open_orders=KisPaperOpenOrdersSnapshot((), captured_at),
        captured_at=captured_at,
    )


def _spy_position() -> KisPaperPosition:
    return KisPaperPosition(
        symbol="SPY",
        exchange="AMEX",
        currency="USD",
        quantity=Decimal("1"),
        average_price=Decimal("500.25"),
        market_price=Decimal("500.50"),
        captured_at=NOW,
    )


def _paths(tmp_path: Path) -> dict[str, Path]:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    return {
        "cache_root": tmp_path / "cache",
        "head_cache_root": tmp_path / "daily-head",
        "availability_root": tmp_path / "availability",
        "state_root": tmp_path / "private",
        "runtime_projection_path": tmp_path / "runtime" / "canary.json",
        "paper_account_snapshot_path": tmp_path / "runtime" / "account.json",
        "emergency_state_path": tmp_path / "emergency" / "state.json",
        "artifact_root": tmp_path / "artifacts",
        "repository_root": repository_root,
        "execution_control_path": tmp_path / "emergency" / "control.json",
    }
