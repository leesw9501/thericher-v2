"""Honest, local-paper comparative baselines for the private KIS daily panel.

This module has no credential, KIS client, or network dependency. It freezes
the session geometry before running deterministic development/validation
references and writes all evidence outside the repository.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import Bar, OrderIntent, non_negative, positive
from thericher_v2.data.kis_paper_daily import (
    KisPaperPrivateDailyCatalog,
    slice_kis_paper_private_daily_catalog,
)
from thericher_v2.execution import (
    EmergencyStore,
    FillEventArtifact,
    LocalPaperBroker,
    collect_fill_source_evidence,
    replay_local_paper_account,
)
from thericher_v2.state import Event, EventStore

from .daily_three_etf_relative_strength import (
    DailyThreeEtfRelativeStrengthConfig,
    DailyThreeEtfRelativeStrengthResult,
    run_daily_three_etf_relative_strength,
)

KIS_DAILY_COMPARATIVE_VALIDATION_ID = "kis-daily-comparative-validation-v1"
DEFAULT_KIS_DAILY_COMPARATIVE_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/kis-daily-comparative-validation-v1"
)
_SYMBOLS = ("QQQ", "SPY", "IWM")
_PHASES = ("development", "validation")

ComparativePhase = Literal["development", "validation"]
HoldoutState = Literal["sealed", "burned_precontract"]
ComparatorKind = Literal["cash", "always_invested"]


@dataclass(frozen=True)
class DailySessionSegment:
    label: str
    start_index: int
    stop_index: int
    first_session: date
    last_session: date
    session_hash: str
    state: HoldoutState | None = None

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("daily segment label is required")
        if not 0 <= self.start_index < self.stop_index:
            raise ValueError("daily segment indices are invalid")
        if self.last_session < self.first_session:
            raise ValueError("daily segment sessions are invalid")
        if self.state is not None:
            if self.label != "sealed_holdout" or self.state not in {
                "sealed",
                "burned_precontract",
            }:
                raise ValueError("daily segment state is invalid")
        _require_sha256(self.session_hash, "daily segment session_hash")

    @property
    def session_count(self) -> int:
        return self.stop_index - self.start_index

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "label": self.label,
            "start_index": self.start_index,
            "stop_index": self.stop_index,
            "session_count": self.session_count,
            "first_session": self.first_session.isoformat(),
            "last_session": self.last_session.isoformat(),
            "session_hash": self.session_hash,
        }
        if self.state is not None:
            payload["state"] = self.state
        return payload


@dataclass(frozen=True)
class PrecontractExposure:
    """A historical run range that prevents a new claim of a sealed holdout."""

    source_id: str
    first_observed_session: date
    last_observed_session: date
    evidence_sha256: str
    evidence_reference: str

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("precontract exposure source_id is required")
        if self.last_observed_session < self.first_observed_session:
            raise ValueError("precontract exposure session range is invalid")
        _require_sha256(self.evidence_sha256, "precontract exposure evidence_sha256")
        if not self.evidence_reference.strip():
            raise ValueError("precontract exposure evidence_reference is required")

    def to_payload(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "first_observed_session": self.first_observed_session.isoformat(),
            "last_observed_session": self.last_observed_session.isoformat(),
            "evidence_sha256": self.evidence_sha256,
            "evidence_reference": self.evidence_reference,
        }


@dataclass(frozen=True)
class KisDailyComparativeContract:
    """A fixed 60/20/20 chronological geometry and its evidence status."""

    contract_id: str
    dataset_id: str
    dataset_hash: str
    index_hash: str
    common_session_count: int
    development: DailySessionSegment
    purge: DailySessionSegment
    validation: DailySessionSegment
    embargo: DailySessionSegment
    sealed_holdout: DailySessionSegment
    precontract_exposure: PrecontractExposure | None = None

    def __post_init__(self) -> None:
        if not _valid_identifier(self.contract_id):
            raise ValueError("comparative contract_id is invalid")
        if self.common_session_count <= 0:
            raise ValueError("comparative common_session_count must be positive")
        _require_sha256(self.dataset_hash, "comparative dataset_hash")
        _require_sha256(self.index_hash, "comparative index_hash")
        if (
            self.sealed_holdout.label != "sealed_holdout"
            or self.sealed_holdout.state is None
        ):
            raise ValueError("comparative sealed holdout is invalid")
        expected = (
            self.development.start_index == 0
            and self.development.stop_index == self.purge.start_index
            and self.purge.stop_index == self.validation.start_index
            and self.validation.stop_index == self.embargo.start_index
            and self.embargo.stop_index == self.sealed_holdout.start_index
            and self.sealed_holdout.stop_index == self.common_session_count
        )
        if not expected:
            raise ValueError("comparative session segments are not chronological")
        usable = self.common_session_count - self.purge.session_count - self.embargo.session_count
        if usable <= 0 or (
            self.development.session_count,
            self.validation.session_count,
            self.sealed_holdout.session_count,
        ) != (usable * 3 // 5, usable // 5, usable // 5):
            raise ValueError("comparative session ratios are invalid")

    @property
    def contract_hash(self) -> str:
        return _sha256_json(self.to_payload())

    @property
    def historical_interpretation(self) -> str:
        return (
            "sealed_holdout_available"
            if self.sealed_holdout.state == "sealed"
            else "historical_comparison_only_prospective_holdout_required"
        )

    def segment_for(self, phase: ComparativePhase) -> DailySessionSegment:
        if phase == "development":
            return self.development
        if phase == "validation":
            return self.validation
        raise ValueError("comparative phase is invalid")

    def verify_catalog(self, catalog: KisPaperPrivateDailyCatalog) -> None:
        if (
            catalog.dataset_id != self.dataset_id
            or catalog.dataset_hash != self.dataset_hash
            or catalog.index_hash != self.index_hash
            or len(catalog.common_sessions) != self.common_session_count
        ):
            raise ValueError("comparative contract does not match the KIS daily catalog")

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": KIS_DAILY_COMPARATIVE_VALIDATION_ID,
            "contract_id": self.contract_id,
            "dataset": {
                "dataset_id": self.dataset_id,
                "dataset_hash": self.dataset_hash,
                "index_hash": self.index_hash,
                "common_session_count": self.common_session_count,
            },
            "geometry": {
                "usable_ratio": {"development": 60, "validation": 20, "holdout": 20},
                "purge_sessions": self.purge.session_count,
                "embargo_sessions": self.embargo.session_count,
                "development": self.development.to_payload(),
                "purge": self.purge.to_payload(),
                "validation": self.validation.to_payload(),
                "embargo": self.embargo.to_payload(),
                "sealed_holdout": self.sealed_holdout.to_payload(),
            },
            "precontract_exposure": (
                None
                if self.precontract_exposure is None
                else self.precontract_exposure.to_payload()
            ),
            "historical_interpretation": self.historical_interpretation,
        }


@dataclass(frozen=True)
class KisDailyComparativeBaselineConfig:
    run_id: str
    starting_cash: Decimal = Decimal("10000")
    quantity: Decimal = Decimal("1")
    fee_bps: Decimal = Decimal("1")
    slippage_bps: Decimal = Decimal("0")
    lookback_sessions: int = 20
    decision_stride_sessions: int = 2

    def __post_init__(self) -> None:
        if not _valid_identifier(self.run_id):
            raise ValueError("comparative baseline run_id is invalid")
        if self.lookback_sessions <= 0 or self.decision_stride_sessions < 2:
            raise ValueError("comparative relative-strength configuration is invalid")
        object.__setattr__(self, "starting_cash", positive(self.starting_cash, "starting_cash"))
        object.__setattr__(self, "quantity", positive(self.quantity, "quantity"))
        object.__setattr__(self, "fee_bps", non_negative(self.fee_bps, "fee_bps"))
        object.__setattr__(self, "slippage_bps", non_negative(self.slippage_bps, "slippage_bps"))


@dataclass(frozen=True)
class DailyComparatorResult:
    run_id: str
    phase: ComparativePhase
    comparator: ComparatorKind
    symbol: str | None
    dataset_id: str
    dataset_hash: str
    common_session_count: int
    starting_cash: Decimal
    ending_cash: Decimal
    total_fees: Decimal
    total_slippage: Decimal
    local_paper_fill_count: int
    all_fills_local_paper: bool
    event_jsonl_path: Path
    event_jsonl_sha256: str
    event_count: int
    run_manifest_path: Path
    run_manifest_sha256: str

    @property
    def pnl(self) -> Decimal:
        return self.ending_cash - self.starting_cash


@dataclass(frozen=True)
class KisDailyComparativeBaselineResult:
    contract: KisDailyComparativeContract
    contract_path: Path
    contract_sha256: str
    relative_strength_runs: tuple[DailyThreeEtfRelativeStrengthResult, ...]
    comparator_runs: tuple[DailyComparatorResult, ...]
    summary_path: Path
    summary_sha256: str


def freeze_kis_daily_comparative_contract(
    catalog: KisPaperPrivateDailyCatalog,
    *,
    contract_id: str = KIS_DAILY_COMPARATIVE_VALIDATION_ID,
    precontract_exposure: PrecontractExposure | None = None,
) -> KisDailyComparativeContract:
    """Freeze 60/20/20 session geometry without reading a holdout outcome."""

    _validate_catalog(catalog)
    total = len(catalog.common_sessions)
    gaps = 4
    usable = total - gaps
    if usable <= 0 or usable % 5:
        raise ValueError("comparative catalog cannot form an exact 60/20/20 split")
    development_count = usable * 3 // 5
    validation_count = usable // 5
    holdout_count = usable // 5
    if development_count < 23 or validation_count < 23 or holdout_count <= 0:
        raise ValueError("comparative catalog is too short for the daily baseline contract")

    development = _segment(catalog.common_sessions, "development", 0, development_count)
    purge = _segment(
        catalog.common_sessions,
        "purge_after_development",
        development.stop_index,
        development.stop_index + 2,
    )
    validation = _segment(
        catalog.common_sessions,
        "validation",
        purge.stop_index,
        purge.stop_index + validation_count,
    )
    embargo = _segment(
        catalog.common_sessions,
        "embargo_after_validation",
        validation.stop_index,
        validation.stop_index + 2,
    )
    holdout_sessions = catalog.common_sessions[
        embargo.stop_index : embargo.stop_index + holdout_count
    ]
    if len(holdout_sessions) != holdout_count:
        raise ValueError("comparative holdout session count is invalid")
    holdout_state: HoldoutState = "sealed"
    if precontract_exposure is not None and not (
        precontract_exposure.last_observed_session < holdout_sessions[0]
        or precontract_exposure.first_observed_session > holdout_sessions[-1]
    ):
        holdout_state = "burned_precontract"
    holdout = _segment(
        catalog.common_sessions,
        "sealed_holdout",
        embargo.stop_index,
        embargo.stop_index + holdout_count,
        state=holdout_state,
    )
    return KisDailyComparativeContract(
        contract_id=contract_id,
        dataset_id=catalog.dataset_id,
        dataset_hash=catalog.dataset_hash,
        index_hash=catalog.index_hash,
        common_session_count=total,
        development=development,
        purge=purge,
        validation=validation,
        embargo=embargo,
        sealed_holdout=holdout,
        precontract_exposure=precontract_exposure,
    )


def run_kis_daily_comparative_cpu_baselines(
    catalog: KisPaperPrivateDailyCatalog,
    *,
    contract: KisDailyComparativeContract,
    config: KisDailyComparativeBaselineConfig,
    artifact_root: Path | str = DEFAULT_KIS_DAILY_COMPARATIVE_ARTIFACT_ROOT,
    repo_root: Path | str | None = None,
) -> KisDailyComparativeBaselineResult:
    """Run fixed development/validation references without opening the holdout."""

    contract.verify_catalog(catalog)
    work_dir = _prepare_work_dir(
        artifact_root=artifact_root,
        repo_root=repo_root,
        run_id=config.run_id,
    )
    contract_path, contract_sha256 = _write_json(
        work_dir / "contract.json",
        {
            **contract.to_payload(),
            "contract_hash": contract.contract_hash,
        },
    )

    relative_strength_runs: list[DailyThreeEtfRelativeStrengthResult] = []
    comparator_runs: list[DailyComparatorResult] = []
    for phase in _PHASES:
        segment = contract.segment_for(phase)
        phase_catalog = slice_kis_paper_private_daily_catalog(
            catalog,
            start_index=segment.start_index,
            stop_index=segment.stop_index,
        )
        relative_strength = run_daily_three_etf_relative_strength(
            phase_catalog,
            config=DailyThreeEtfRelativeStrengthConfig(
                run_id=f"{config.run_id}-{phase}-relative-strength",
                lookback_sessions=config.lookback_sessions,
                decision_stride_sessions=config.decision_stride_sessions,
                starting_cash=config.starting_cash,
                quantity=config.quantity,
                fee_bps=config.fee_bps,
                slippage_bps=config.slippage_bps,
                comparative_contract_hash=contract.contract_hash,
                comparative_phase=phase,
            ),
            artifact_root=work_dir / "relative-strength",
            repo_root=repo_root,
        )
        relative_strength_runs.append(relative_strength)
        comparator_runs.append(
            _run_daily_comparator(
                phase_catalog,
                phase=phase,
                comparator="cash",
                symbol=None,
                config=config,
                work_root=work_dir / "comparators",
                repo_root=repo_root,
                contract=contract,
            )
        )
        for symbol in _SYMBOLS:
            comparator_runs.append(
                _run_daily_comparator(
                    phase_catalog,
                    phase=phase,
                    comparator="always_invested",
                    symbol=symbol,
                    config=config,
                    work_root=work_dir / "comparators",
                    repo_root=repo_root,
                    contract=contract,
                )
            )

    summary_path, summary_sha256 = _write_json(
        work_dir / "summary.json",
        {
            "kind": "kis_daily_comparative_cpu_baseline_summary",
            "run_id": config.run_id,
            "contract_path": str(contract_path),
            "contract_sha256": contract_sha256,
            "contract_hash": contract.contract_hash,
            "historical_interpretation": contract.historical_interpretation,
            "relative_strength_runs": [
                _relative_strength_payload(run) for run in relative_strength_runs
            ],
            "comparator_runs": [_comparator_payload(run) for run in comparator_runs],
        },
    )
    return KisDailyComparativeBaselineResult(
        contract=contract,
        contract_path=contract_path,
        contract_sha256=contract_sha256,
        relative_strength_runs=tuple(relative_strength_runs),
        comparator_runs=tuple(comparator_runs),
        summary_path=summary_path,
        summary_sha256=summary_sha256,
    )


def _run_daily_comparator(
    catalog: KisPaperPrivateDailyCatalog,
    *,
    phase: ComparativePhase,
    comparator: ComparatorKind,
    symbol: str | None,
    config: KisDailyComparativeBaselineConfig,
    work_root: Path,
    repo_root: Path | str | None,
    contract: KisDailyComparativeContract,
) -> DailyComparatorResult:
    _validate_catalog(catalog)
    if comparator == "cash":
        if symbol is not None:
            raise ValueError("cash comparator cannot select a symbol")
        label = "cash"
    elif comparator == "always_invested":
        if symbol not in _SYMBOLS:
            raise ValueError("always-invested comparator requires a supported symbol")
        label = f"always-invested-{symbol.lower()}"
    else:  # pragma: no cover - Literal plus callers cover this branch.
        raise ValueError("daily comparator is invalid")

    run_id = f"{config.run_id}-{phase}-{label}"
    work_dir = _prepare_work_dir(artifact_root=work_root, repo_root=repo_root, run_id=run_id)
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
    event_store.append(
        Event(
            event_type="daily_comparator_decision",
            created_at=_panel_bars(catalog, "QQQ")[0].end_ts,
            payload={
                "source": KIS_DAILY_COMPARATIVE_VALIDATION_ID,
                "run_id": run_id,
                "decision_id": f"{run_id}-decision",
                "market": "US",
                "symbol": "QQQ-SPY-IWM" if symbol is None else symbol,
                "action": "stay_cash" if comparator == "cash" else "enter_and_hold",
                "comparator": comparator,
                "dataset_id": catalog.dataset_id,
                "dataset_hash": catalog.dataset_hash,
                "contract_hash": contract.contract_hash,
            },
        )
    )

    total_fees = Decimal("0")
    total_slippage = Decimal("0")
    expected_fill_count = 0
    if comparator == "always_invested":
        assert symbol is not None
        bars = _panel_bars(catalog, symbol)
        entry_order = OrderIntent(
            client_order_id=f"{run_id}-entry",
            symbol=symbol,
            market=bars[0].market,
            side="buy",
            quantity=config.quantity,
            limit_price=None,
            decision_id=f"{run_id}-decision",
            created_at=bars[0].end_ts,
        )
        entry = broker.submit_and_fill_next_bar(
            entry_order,
            signal_bar=bars[0],
            execution_bar=bars[1],
        )
        if entry.fill is None:
            raise RuntimeError("daily always-invested comparator did not enter local paper")
        total_fees += entry.fill.fee
        total_slippage += _slippage_cost(entry.fill.price, bars[1].open, entry.fill.quantity)

        exit_order = OrderIntent(
            client_order_id=f"{run_id}-exit",
            symbol=symbol,
            market=bars[-1].market,
            side="sell",
            quantity=entry.fill.quantity,
            limit_price=None,
            decision_id=f"{run_id}-terminal-exit",
            created_at=bars[-2].end_ts,
        )
        exit_execution = broker.submit_and_fill_next_bar(
            exit_order,
            signal_bar=bars[-2],
            execution_bar=bars[-1],
        )
        if exit_execution.fill is None:
            raise RuntimeError("daily always-invested comparator did not exit local paper")
        total_fees += exit_execution.fill.fee
        total_slippage += _slippage_cost(
            exit_execution.fill.price,
            bars[-1].open,
            exit_execution.fill.quantity,
        )
        expected_fill_count = 2

    fill_evidence = collect_fill_source_evidence(
        (
            FillEventArtifact(
                path=event_store.jsonl_path,
                expected_fill_count=expected_fill_count,
                label=run_id,
            ),
        )
    )
    if not fill_evidence.local_paper_replay_invariant_passed:
        raise RuntimeError("daily comparator must use replayable local-paper fills")
    account = broker.account()
    replayed_account = replay_local_paper_account(event_store, starting_cash=config.starting_cash)
    if account != replayed_account or account.positions:
        raise RuntimeError("daily comparator must finish flat and replayable")
    event_store.rebuild_sqlite()
    event_payload = event_store.jsonl_path.read_bytes()
    event_jsonl_sha256 = _sha256(event_payload)
    event_count = len(tuple(event_store.iter_events()))
    run_manifest_path, run_manifest_sha256 = _write_json(
        work_dir / "run.json",
        {
            "kind": "kis_daily_local_paper_comparator_run",
            "run_id": run_id,
            "code_revision": _code_revision(repo_root),
            "contract_hash": contract.contract_hash,
            "phase": phase,
            "comparator": {"kind": comparator, "symbol": symbol},
            "dataset": {
                "dataset_id": catalog.dataset_id,
                "dataset_hash": catalog.dataset_hash,
                "common_session_count": len(catalog.common_sessions),
                "raw_price_limitations": list(catalog.raw_price_limitations),
            },
            "execution": {
                "broker": "local_paper",
                "starting_cash": str(config.starting_cash),
                "quantity": str(config.quantity),
                "fee_bps": str(config.fee_bps),
                "slippage_bps": str(config.slippage_bps),
                "entry": None if comparator == "cash" else "next_session_open",
                "exit": None if comparator == "cash" else "last_observable_session_open",
            },
            "evidence": {
                "event_jsonl_sha256": event_jsonl_sha256,
                "event_count": event_count,
                "expected_local_paper_fill_count": expected_fill_count,
            },
        },
    )
    return DailyComparatorResult(
        run_id=run_id,
        phase=phase,
        comparator=comparator,
        symbol=symbol,
        dataset_id=catalog.dataset_id,
        dataset_hash=catalog.dataset_hash,
        common_session_count=len(catalog.common_sessions),
        starting_cash=config.starting_cash,
        ending_cash=account.cash,
        total_fees=total_fees,
        total_slippage=total_slippage,
        local_paper_fill_count=len(fill_evidence.local_paper_fills),
        all_fills_local_paper=fill_evidence.all_fills_local_paper,
        event_jsonl_path=event_store.jsonl_path,
        event_jsonl_sha256=event_jsonl_sha256,
        event_count=event_count,
        run_manifest_path=run_manifest_path,
        run_manifest_sha256=run_manifest_sha256,
    )


def _validate_catalog(catalog: KisPaperPrivateDailyCatalog) -> None:
    if tuple(catalog.bars_by_symbol) != _SYMBOLS or len(catalog.common_sessions) < 3:
        raise ValueError("comparative validation requires the fixed KIS daily ETF panel")
    for symbol in _SYMBOLS:
        _panel_bars(catalog, symbol)


def _panel_bars(catalog: KisPaperPrivateDailyCatalog, symbol: str) -> tuple[Bar, ...]:
    stream = catalog.bars_by_symbol.get(symbol)
    if stream is None:
        raise ValueError("comparative validation catalog symbol is missing")
    bars = stream.bars
    if (
        len(bars) != len(catalog.common_sessions)
        or any(
            bar.symbol != symbol or bar.timeframe.value != "1d" or not bar.complete
            for bar in bars
        )
        or tuple(bar.start_ts.date() for bar in bars) != catalog.common_sessions
    ):
        raise ValueError("comparative validation catalog stream is invalid")
    return bars


def _segment(
    sessions: tuple[date, ...],
    label: str,
    start_index: int,
    stop_index: int,
    state: HoldoutState | None = None,
) -> DailySessionSegment:
    selected = sessions[start_index:stop_index]
    if not selected:
        raise ValueError("comparative session segment is empty")
    return DailySessionSegment(
        label=label,
        start_index=start_index,
        stop_index=stop_index,
        first_session=selected[0],
        last_session=selected[-1],
        session_hash=_session_hash(selected),
        state=state,
    )


def _session_hash(sessions: tuple[date, ...]) -> str:
    return _sha256("\n".join(session.isoformat() for session in sessions).encode("ascii"))


def _slippage_cost(fill_price: Decimal, reference_open: Decimal, quantity: Decimal) -> Decimal:
    return abs(fill_price - reference_open) * quantity


def _relative_strength_payload(result: DailyThreeEtfRelativeStrengthResult) -> dict[str, object]:
    if result.comparative_phase is None:
        raise ValueError("comparative relative-strength run is missing its phase")
    return {
        "phase": result.comparative_phase,
        "run_id": result.run_id,
        "dataset_id": result.dataset_id,
        "dataset_hash": result.dataset_hash,
        "common_session_count": result.common_session_count,
        "pnl": str(result.pnl),
        "total_fees": str(result.total_fees),
        "total_slippage": str(result.total_slippage),
        "local_paper_fill_count": result.local_paper_fill_count,
        "all_fills_local_paper": result.all_fills_local_paper,
        "event_jsonl_path": str(result.event_jsonl_path),
        "event_jsonl_sha256": result.event_jsonl_sha256,
        "run_manifest_path": str(result.run_manifest_path),
        "run_manifest_sha256": result.run_manifest_sha256,
    }


def _comparator_payload(result: DailyComparatorResult) -> dict[str, object]:
    return {
        "phase": result.phase,
        "run_id": result.run_id,
        "comparator": result.comparator,
        "symbol": result.symbol,
        "dataset_id": result.dataset_id,
        "dataset_hash": result.dataset_hash,
        "common_session_count": result.common_session_count,
        "pnl": str(result.pnl),
        "total_fees": str(result.total_fees),
        "total_slippage": str(result.total_slippage),
        "local_paper_fill_count": result.local_paper_fill_count,
        "all_fills_local_paper": result.all_fills_local_paper,
        "event_jsonl_path": str(result.event_jsonl_path),
        "event_jsonl_sha256": result.event_jsonl_sha256,
        "run_manifest_path": str(result.run_manifest_path),
        "run_manifest_sha256": result.run_manifest_sha256,
    }


def _prepare_work_dir(
    *,
    artifact_root: Path | str,
    repo_root: Path | str | None,
    run_id: str,
) -> Path:
    root = Path(artifact_root)
    if root.is_symlink():
        raise ValueError("comparative validation artifact root is invalid")
    root.mkdir(parents=True, exist_ok=True)
    resolved_root = root.resolve()
    if repo_root is not None and resolved_root.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("comparative validation artifacts must stay outside Git")
    work_dir = resolved_root / run_id
    if work_dir.exists() or work_dir.is_symlink():
        raise FileExistsError("comparative validation run directory already exists")
    work_dir.mkdir()
    return work_dir


def _write_json(path: Path, document: dict[str, object]) -> tuple[Path, str]:
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    staging = path.with_name(f".{path.name}.stage")
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


def _sha256_json(document: dict[str, object]) -> str:
    return _sha256(json.dumps(document, separators=(",", ":"), sort_keys=True).encode("utf-8"))


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


def _valid_identifier(value: str) -> bool:
    return bool(value) and all(
        character.isalnum() or character in {"-", "_", "."} for character in value
    )
