"""A deterministic three-ETF daily local-paper baseline.

This is a small research reference, not a claim of profitability. It consumes
only a hash-attested KIS daily panel and submits orders exclusively to the
broker-free local-paper simulator.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import Bar, OrderIntent, non_negative, positive, require_utc
from thericher_v2.data.kis_paper_daily import KisPaperPrivateDailyCatalog
from thericher_v2.execution import (
    EmergencyStore,
    FillEventArtifact,
    LocalPaperBroker,
    LocalPaperFill,
    collect_fill_source_evidence,
    replay_local_paper_account,
)
from thericher_v2.state import Event, EventStore

DAILY_THREE_ETF_RELATIVE_STRENGTH_ID = "daily-three-etf-relative-strength-v0"
DAILY_THREE_ETF_RELATIVE_STRENGTH_PANEL_SYMBOL = "QQQ-SPY-IWM"
DEFAULT_DAILY_THREE_ETF_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/daily-three-etf-relative-strength-v0"
)
_SYMBOLS = ("QQQ", "SPY", "IWM")


@dataclass(frozen=True)
class DailyThreeEtfRelativeStrengthConfig:
    run_id: str = DAILY_THREE_ETF_RELATIVE_STRENGTH_ID
    lookback_sessions: int = 20
    decision_stride_sessions: int = 2
    starting_cash: Decimal = Decimal("10000")
    quantity: Decimal = Decimal("1")
    fee_bps: Decimal = Decimal("1")
    slippage_bps: Decimal = Decimal("0")
    comparative_contract_hash: str | None = None
    comparative_phase: Literal["development", "validation"] | None = None

    def __post_init__(self) -> None:
        if not _valid_run_id(self.run_id):
            raise ValueError("daily relative-strength run_id is invalid")
        if self.lookback_sessions <= 0:
            raise ValueError("daily relative-strength lookback must be positive")
        if self.decision_stride_sessions < 2:
            raise ValueError("daily relative-strength decision stride must avoid overlap")
        object.__setattr__(self, "starting_cash", positive(self.starting_cash, "starting_cash"))
        object.__setattr__(self, "quantity", positive(self.quantity, "quantity"))
        object.__setattr__(self, "fee_bps", non_negative(self.fee_bps, "fee_bps"))
        object.__setattr__(self, "slippage_bps", non_negative(self.slippage_bps, "slippage_bps"))
        if (self.comparative_contract_hash is None) != (self.comparative_phase is None):
            raise ValueError("daily relative-strength comparative evidence is incomplete")
        if self.comparative_contract_hash is not None:
            _require_sha256(self.comparative_contract_hash, "comparative_contract_hash")


@dataclass(frozen=True)
class DailyThreeEtfDecision:
    decision_id: str
    decided_at: datetime
    selected_symbol: str | None
    action: Literal["enter", "abstain"]
    strengths: tuple[tuple[str, Decimal], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "decided_at", require_utc(self.decided_at, "decided_at"))
        if self.action == "enter" and self.selected_symbol not in _SYMBOLS:
            raise ValueError("entry decision requires a supported symbol")
        if self.action == "abstain" and self.selected_symbol is not None:
            raise ValueError("abstain decision cannot select a symbol")
        if tuple(symbol for symbol, _value in self.strengths) != _SYMBOLS:
            raise ValueError("daily relative-strength strengths must cover the fixed ETF panel")


@dataclass(frozen=True)
class DailyThreeEtfTrade:
    client_order_id: str
    decision_id: str
    symbol: str
    side: Literal["buy", "sell"]
    quantity: Decimal
    price: Decimal
    fee: Decimal
    filled_at: datetime
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "filled_at", require_utc(self.filled_at, "filled_at"))


@dataclass(frozen=True)
class DailyThreeEtfRelativeStrengthResult:
    run_id: str
    dataset_id: str
    dataset_hash: str
    common_session_count: int
    decisions: tuple[DailyThreeEtfDecision, ...]
    trades: tuple[DailyThreeEtfTrade, ...]
    starting_cash: Decimal
    ending_cash: Decimal
    total_fees: Decimal
    total_slippage: Decimal
    final_position_count: int
    replayed_final_position_count: int
    local_paper_fill_count: int
    all_fills_local_paper: bool
    event_jsonl_path: Path
    event_jsonl_sha256: str
    event_count: int
    run_manifest_path: Path
    run_manifest_sha256: str
    comparative_contract_hash: str | None
    comparative_phase: Literal["development", "validation"] | None

    @property
    def pnl(self) -> Decimal:
        return self.ending_cash - self.starting_cash

    @property
    def abstain_count(self) -> int:
        return sum(1 for decision in self.decisions if decision.action == "abstain")


def run_daily_three_etf_relative_strength(
    catalog: KisPaperPrivateDailyCatalog,
    *,
    config: DailyThreeEtfRelativeStrengthConfig | None = None,
    artifact_root: Path | str = DEFAULT_DAILY_THREE_ETF_ARTIFACT_ROOT,
    repo_root: Path | str | None = None,
) -> DailyThreeEtfRelativeStrengthResult:
    """Execute a causal daily baseline through local-paper fills only.

    On decision session ``t``, choose the highest strictly positive 20-session
    close return. Entry uses ``t+1`` open and flattening uses ``t+2`` open. A
    two-session cadence guarantees a single-cash account has no overlapping
    position.
    """

    config = config or DailyThreeEtfRelativeStrengthConfig()
    streams = _validated_streams(catalog)
    work_dir = _prepare_work_dir(
        artifact_root=artifact_root,
        repo_root=repo_root,
        run_id=config.run_id,
    )
    event_store = EventStore(
        db_path=work_dir / "state.sqlite",
        jsonl_path=work_dir / "events.jsonl",
        rebuild_sqlite_on_append=False,
    )
    broker = LocalPaperBroker(
        event_store=event_store,
        emergency_store=EmergencyStore(work_dir / "emergency.json"),
        starting_cash=config.starting_cash,
        fee_bps=config.fee_bps,
        slippage_bps=config.slippage_bps,
    )

    decisions: list[DailyThreeEtfDecision] = []
    trades: list[DailyThreeEtfTrade] = []
    total_fees = Decimal("0")
    total_slippage = Decimal("0")
    session_count = len(catalog.common_sessions)
    for index in range(
        config.lookback_sessions,
        session_count - 2,
        config.decision_stride_sessions,
    ):
        decision, signal_bars = _decision_for_index(
            streams=streams,
            index=index,
            config=config,
        )
        panel_market = signal_bars[_SYMBOLS[0]].market
        decisions.append(decision)
        event_store.append(
            Event(
                event_type="daily_relative_strength_decision",
                created_at=decision.decided_at,
                payload={
                    "source": DAILY_THREE_ETF_RELATIVE_STRENGTH_ID,
                    "run_id": config.run_id,
                    "decision_id": decision.decision_id,
                    "market": panel_market,
                    "symbol": DAILY_THREE_ETF_RELATIVE_STRENGTH_PANEL_SYMBOL,
                    "action": decision.action,
                    "selected_symbol": decision.selected_symbol,
                    "dataset_id": catalog.dataset_id,
                    "dataset_hash": catalog.dataset_hash,
                },
            )
        )
        if decision.selected_symbol is None:
            continue

        symbol = decision.selected_symbol
        signal_bar = signal_bars[symbol]
        entry_bar = streams[symbol][index + 1]
        exit_bar = streams[symbol][index + 2]
        entry_order = OrderIntent(
            client_order_id=f"{config.run_id}-{len(decisions):04d}-entry",
            symbol=symbol,
            market=signal_bar.market,
            side="buy",
            quantity=config.quantity,
            limit_price=None,
            decision_id=decision.decision_id,
            created_at=signal_bar.end_ts,
        )
        entry = broker.submit_and_fill_next_bar(
            entry_order,
            signal_bar=signal_bar,
            execution_bar=entry_bar,
        )
        if entry.fill is None:
            raise RuntimeError("daily relative-strength entry did not produce a local-paper fill")
        trades.append(_trade_from_fill(entry.fill, decision_id=decision.decision_id))
        total_fees += entry.fill.fee
        total_slippage += _slippage_cost(
            fill_price=entry.fill.price,
            reference_open=entry_bar.open,
            quantity=entry.fill.quantity,
            side="buy",
        )

        exit_order = OrderIntent(
            client_order_id=f"{config.run_id}-{len(decisions):04d}-exit",
            symbol=symbol,
            market=signal_bar.market,
            side="sell",
            quantity=entry.fill.quantity,
            limit_price=None,
            decision_id=f"{decision.decision_id}:flatten",
            created_at=entry_bar.end_ts,
        )
        exit_execution = broker.submit_and_fill_next_bar(
            exit_order,
            signal_bar=entry_bar,
            execution_bar=exit_bar,
        )
        if exit_execution.fill is None:
            raise RuntimeError("daily relative-strength exit did not produce a local-paper fill")
        trades.append(
            _trade_from_fill(exit_execution.fill, decision_id=f"{decision.decision_id}:flatten")
        )
        total_fees += exit_execution.fill.fee
        total_slippage += _slippage_cost(
            fill_price=exit_execution.fill.price,
            reference_open=exit_bar.open,
            quantity=exit_execution.fill.quantity,
            side="sell",
        )

    fill_evidence = collect_fill_source_evidence(
        (
            FillEventArtifact(
                path=event_store.jsonl_path,
                expected_fill_count=len(trades),
                label=config.run_id,
            ),
        )
    )
    if not fill_evidence.local_paper_replay_invariant_passed:
        raise RuntimeError("daily relative-strength baseline must use replayable local-paper fills")
    account = broker.account()
    replayed_account = replay_local_paper_account(
        event_store,
        starting_cash=config.starting_cash,
    )
    if account != replayed_account or account.positions:
        raise RuntimeError("daily relative-strength baseline must finish flat and replayable")
    event_store.rebuild_sqlite()
    try:
        event_payload = event_store.jsonl_path.read_bytes()
    except OSError as error:
        raise RuntimeError("daily relative-strength event evidence is unreadable") from error

    event_jsonl_sha256 = _sha256(event_payload)
    event_count = len(tuple(event_store.iter_events()))
    run_manifest_path, run_manifest_sha256 = _write_run_manifest(
        work_dir=work_dir,
        catalog=catalog,
        config=config,
        event_jsonl_sha256=event_jsonl_sha256,
        event_count=event_count,
        repo_root=repo_root,
    )

    return DailyThreeEtfRelativeStrengthResult(
        run_id=config.run_id,
        dataset_id=catalog.dataset_id,
        dataset_hash=catalog.dataset_hash,
        common_session_count=session_count,
        decisions=tuple(decisions),
        trades=tuple(trades),
        starting_cash=config.starting_cash,
        ending_cash=account.cash,
        total_fees=total_fees,
        total_slippage=total_slippage,
        final_position_count=len(account.positions),
        replayed_final_position_count=len(replayed_account.positions),
        local_paper_fill_count=len(fill_evidence.local_paper_fills),
        all_fills_local_paper=fill_evidence.all_fills_local_paper,
        event_jsonl_path=event_store.jsonl_path,
        event_jsonl_sha256=event_jsonl_sha256,
        event_count=event_count,
        run_manifest_path=run_manifest_path,
        run_manifest_sha256=run_manifest_sha256,
        comparative_contract_hash=config.comparative_contract_hash,
        comparative_phase=config.comparative_phase,
    )


def _validated_streams(catalog: KisPaperPrivateDailyCatalog) -> dict[str, tuple[Bar, ...]]:
    if tuple(catalog.bars_by_symbol) != _SYMBOLS:
        raise ValueError("daily relative-strength catalog must contain QQQ, SPY, and IWM")
    if len(catalog.common_sessions) < 23:
        raise ValueError("daily relative-strength catalog needs at least 23 common sessions")
    streams = {symbol: stream.bars for symbol, stream in catalog.bars_by_symbol.items()}
    for symbol in _SYMBOLS:
        bars = streams[symbol]
        if (
            not bars
            or len(bars) != len(catalog.common_sessions)
            or any(bar.symbol != symbol or bar.timeframe.value != "1d" for bar in bars)
            or any(not bar.complete for bar in bars)
            or tuple(bar.start_ts.date() for bar in bars) != catalog.common_sessions
            or catalog.bars_by_symbol[symbol].dataset_id != catalog.dataset_id
            or catalog.bars_by_symbol[symbol].dataset_hash != catalog.dataset_hash
        ):
            raise ValueError("daily relative-strength catalog streams are incompatible")
    return streams


def _decision_for_index(
    *,
    streams: dict[str, tuple[Bar, ...]],
    index: int,
    config: DailyThreeEtfRelativeStrengthConfig,
) -> tuple[DailyThreeEtfDecision, dict[str, Bar]]:
    signal_bars = {symbol: streams[symbol][index] for symbol in _SYMBOLS}
    strengths = tuple(
        (
            symbol,
            (signal_bars[symbol].close / streams[symbol][index - config.lookback_sessions].close)
            - Decimal("1"),
        )
        for symbol in _SYMBOLS
    )
    candidates = tuple((symbol, value) for symbol, value in strengths if value > 0)
    selected_symbol = max(candidates, key=lambda item: item[1])[0] if candidates else None
    signal_bar = signal_bars[_SYMBOLS[0]]
    decision_id = f"{config.run_id}-{index:04d}"
    return (
        DailyThreeEtfDecision(
            decision_id=decision_id,
            decided_at=signal_bar.end_ts,
            selected_symbol=selected_symbol,
            action="enter" if selected_symbol is not None else "abstain",
            strengths=strengths,
        ),
        signal_bars,
    )


def _trade_from_fill(fill: LocalPaperFill, *, decision_id: str) -> DailyThreeEtfTrade:
    return DailyThreeEtfTrade(
        client_order_id=fill.client_order_id,
        decision_id=decision_id,
        symbol=fill.symbol,
        side=fill.side,
        quantity=fill.quantity,
        price=fill.price,
        fee=fill.fee,
        filled_at=fill.filled_at,
        source=fill.source,
    )


def _slippage_cost(
    *,
    fill_price: Decimal,
    reference_open: Decimal,
    quantity: Decimal,
    side: Literal["buy", "sell"],
) -> Decimal:
    return (
        (fill_price - reference_open) * quantity
        if side == "buy"
        else (reference_open - fill_price) * quantity
    )


def _prepare_work_dir(
    *,
    artifact_root: Path | str,
    repo_root: Path | str | None,
    run_id: str,
) -> Path:
    root = Path(artifact_root)
    if root.is_symlink():
        raise ValueError("daily relative-strength artifact root is invalid")
    root.mkdir(parents=True, exist_ok=True)
    resolved_root = root.resolve()
    if repo_root is not None and resolved_root.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("daily relative-strength artifacts must stay outside Git")
    work_dir = resolved_root / run_id
    if work_dir.exists() or work_dir.is_symlink():
        raise FileExistsError("daily relative-strength run directory already exists")
    work_dir.mkdir()
    return work_dir


def _valid_run_id(value: str) -> bool:
    return bool(value) and all(
        character.isalnum() or character in {"-", "_", "."} for character in value
    )


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _require_sha256(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ValueError(f"{label} must use the sha256: prefix")
    digest = value.removeprefix("sha256:")
    if len(digest) != 64:
        raise ValueError(f"{label} must contain a 64-character SHA-256 digest")
    try:
        int(digest, 16)
    except ValueError as error:
        raise ValueError(f"{label} must contain a hexadecimal SHA-256 digest") from error


def _write_run_manifest(
    *,
    work_dir: Path,
    catalog: KisPaperPrivateDailyCatalog,
    config: DailyThreeEtfRelativeStrengthConfig,
    event_jsonl_sha256: str,
    event_count: int,
    repo_root: Path | str | None,
) -> tuple[Path, str]:
    document = {
        "kind": "daily_three_etf_relative_strength_run",
        "strategy_id": DAILY_THREE_ETF_RELATIVE_STRENGTH_ID,
        "run_id": config.run_id,
        "code_revision": _code_revision(repo_root),
        "dataset": {
            "dataset_id": catalog.dataset_id,
            "dataset_hash": catalog.dataset_hash,
            "index_hash": catalog.index_hash,
            "common_session_count": len(catalog.common_sessions),
            "raw_price_limitations": list(catalog.raw_price_limitations),
        },
        "strategy": {
            "lookback_sessions": config.lookback_sessions,
            "decision_stride_sessions": config.decision_stride_sessions,
            "panel_symbol": DAILY_THREE_ETF_RELATIVE_STRENGTH_PANEL_SYMBOL,
        },
        "comparative_contract": (
            None
            if config.comparative_contract_hash is None
            else {
                "contract_hash": config.comparative_contract_hash,
                "phase": config.comparative_phase,
            }
        ),
        "execution": {
            "broker": "local_paper",
            "starting_cash": str(config.starting_cash),
            "quantity": str(config.quantity),
            "fee_bps": str(config.fee_bps),
            "slippage_bps": str(config.slippage_bps),
            "entry": "next_session_open",
            "exit": "following_session_open",
        },
        "evidence": {
            "event_jsonl_sha256": event_jsonl_sha256,
            "event_count": event_count,
        },
    }
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path = work_dir / "run.json"
    staging = work_dir / ".run.json.stage"
    try:
        staging.write_bytes(payload)
        staging.replace(path)
    finally:
        if staging.exists():
            staging.unlink()
    return path, _sha256(payload)


def _code_revision(repo_root: Path | str | None) -> str:
    root = (
        Path(repo_root).resolve()
        if repo_root is not None
        else Path(__file__).resolve().parents[3]
    )
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "diff", "--quiet"],
            cwd=root,
            check=False,
            capture_output=True,
        ).returncode != 0
    except (OSError, subprocess.SubprocessError):
        return "git:unavailable"
    return f"git:{revision}" + ("+dirty" if dirty else "")
