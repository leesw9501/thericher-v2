"""Bounded first KIS intraday CPU campaign for one selected symbol."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Timeframe
from thericher_v2.data import (
    CatalogedBars,
    SessionWindow,
    select_complete_kis_paper_private_intraday_sessions,
    us_equity_2026_session,
)

from .campaign import (
    CampaignContract,
    CampaignCosts,
    CampaignFold,
    CampaignWindow,
    CatalogDatasetRef,
    ExecutableTarget,
)
from .validation import NaiveBaselineRun, run_naive_cpu_baseline

KIS_INTRADAY_CPU_CAMPAIGN_ID = "kis-intraday-cpu-naive-20-session-v1"
KIS_INTRADAY_SESSION_COUNT = 20
KIS_INTRADAY_DEVELOPMENT_SESSION_COUNT = 10
KIS_INTRADAY_PURGE_SESSION_COUNT = 1
KIS_INTRADAY_VALIDATION_SESSION_COUNT = 9
KIS_INTRADAY_REGULAR_SESSION_MINUTES = 390
KIS_INTRADAY_FIRST_SIGNAL_OFFSET = 89
KIS_INTRADAY_LAST_SIGNAL_OFFSET = 387
KIS_INTRADAY_NAIVE_BASELINES = (
    "flat",
    "always_long",
    "previous_bar_direction",
)

KisIntradayCampaignPhase = Literal["development", "validation"]


@dataclass(frozen=True)
class KisIntradayCpuCampaignPlan:
    """One KIS-only, development-scoped 20-session intraday campaign."""

    campaign: CampaignContract
    cataloged_bars: CatalogedBars
    session_dates: tuple[date, ...]
    session_windows: tuple[SessionWindow, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_dates", tuple(self.session_dates))
        object.__setattr__(self, "session_windows", tuple(self.session_windows))
        if len(self.session_dates) != KIS_INTRADAY_SESSION_COUNT:
            raise ValueError("KIS intraday campaign requires exactly 20 selected sessions")
        if len(self.session_windows) != KIS_INTRADAY_SESSION_COUNT:
            raise ValueError("KIS intraday campaign session windows are incomplete")

    @property
    def development_session_dates(self) -> tuple[date, ...]:
        return self.session_dates[:KIS_INTRADAY_DEVELOPMENT_SESSION_COUNT]

    @property
    def purge_session_date(self) -> date:
        return self.session_dates[KIS_INTRADAY_DEVELOPMENT_SESSION_COUNT]

    @property
    def validation_session_dates(self) -> tuple[date, ...]:
        return self.session_dates[
            KIS_INTRADAY_DEVELOPMENT_SESSION_COUNT + KIS_INTRADAY_PURGE_SESSION_COUNT :
        ]

    def phase_session_windows(self, phase: KisIntradayCampaignPhase) -> tuple[SessionWindow, ...]:
        if phase == "development":
            return self.session_windows[:KIS_INTRADAY_DEVELOPMENT_SESSION_COUNT]
        if phase == "validation":
            return self.session_windows[
                KIS_INTRADAY_DEVELOPMENT_SESSION_COUNT
                + KIS_INTRADAY_PURGE_SESSION_COUNT :
            ]
        raise ValueError("KIS intraday campaign phase is invalid")

    def eligible_signal_starts(self, phase: KisIntradayCampaignPhase) -> frozenset[datetime]:
        return frozenset(
            window.open_ts + Timeframe.M1.duration * offset
            for window in self.phase_session_windows(phase)
            for offset in range(
                KIS_INTRADAY_FIRST_SIGNAL_OFFSET,
                KIS_INTRADAY_LAST_SIGNAL_OFFSET + 1,
            )
        )

@dataclass(frozen=True)
class KisIntradayCpuBaselineRun:
    phase: KisIntradayCampaignPhase
    baseline: NaiveBaselineRun
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class KisIntradayCpuCampaignRun:
    """Replay evidence only; this result makes no model or PnL claim."""

    plan: KisIntradayCpuCampaignPlan
    baseline_runs: tuple[KisIntradayCpuBaselineRun, ...]
    schema_version: int = SCHEMA_VERSION


def build_kis_intraday_cpu_campaign_plan(
    catalog: CatalogedBars,
    *,
    session_dates: Sequence[date],
    campaign_id: str = KIS_INTRADAY_CPU_CAMPAIGN_ID,
) -> KisIntradayCpuCampaignPlan:
    """Select and freeze the fixed 10 / 1 / 9 regular-session geometry."""

    selected_dates = _selected_regular_session_dates(session_dates)
    selected = select_complete_kis_paper_private_intraday_sessions(
        catalog,
        session_dates=selected_dates,
    )
    windows = tuple(_regular_session_window(session_date) for session_date in selected_dates)
    _validate_selected_sessions(selected, windows)

    development = CampaignWindow(
        windows[0].open_ts,
        windows[KIS_INTRADAY_DEVELOPMENT_SESSION_COUNT - 1].close_ts,
    )
    validation_start = KIS_INTRADAY_DEVELOPMENT_SESSION_COUNT + KIS_INTRADAY_PURGE_SESSION_COUNT
    validation = CampaignWindow(windows[validation_start].open_ts, windows[-1].close_ts)
    contract = CampaignContract(
        campaign_id=campaign_id,
        catalog=CatalogDatasetRef(
            catalog_id=f"{selected.dataset_id}:kis-intraday-20-session-cpu",
            dataset_id=selected.dataset_id,
            dataset_hash=selected.dataset_hash,
            constructed_as_of_utc=windows[-1].close_ts,
            ranking_eligible=False,
            sealed_holdout_eligible=False,
        ),
        timeframe=Timeframe.M1,
        folds=(CampaignFold("fold-1", development, validation),),
        target=ExecutableTarget(),
        costs=CampaignCosts(
            fee_bps=Decimal("1"),
            slippage_bps=Decimal("2"),
            slippage_source_id="kis-intraday-cpu-screen-costs-v1",
        ),
        purge=Timeframe.M1.duration,
        embargo=Timeframe.M1.duration,
        evidence_use="development",
        sealed_holdout=None,
        naive_baselines=KIS_INTRADAY_NAIVE_BASELINES,
        deterministic_seed=71,
    )
    return KisIntradayCpuCampaignPlan(
        campaign=contract,
        cataloged_bars=selected,
        session_dates=selected_dates,
        session_windows=windows,
    )


def run_kis_intraday_cpu_naive_baselines(
    plan: KisIntradayCpuCampaignPlan,
    *,
    artifact_root: Path,
    work_root: Path,
    repo_root: Path | None = None,
    starting_cash: Decimal = Decimal("10000"),
    quantity: Decimal = Decimal("1"),
    run_label: str | None = None,
) -> KisIntradayCpuCampaignRun:
    """Run the frozen naive paths through local-paper replay only.

    ``run_label`` creates a distinct immutable attempt when an earlier attempt
    stopped after writing partial external evidence.
    """

    runs: list[KisIntradayCpuBaselineRun] = []
    for phase in ("development", "validation"):
        eligible_signal_starts = plan.eligible_signal_starts(phase)
        allowed_session_windows = plan.phase_session_windows(phase)
        for baseline_id in plan.campaign.naive_baselines:
            baseline = run_naive_cpu_baseline(
                plan.cataloged_bars,
                campaign=plan.campaign,
                artifact_root=artifact_root,
                work_dir=work_root / phase / baseline_id,
                phase=phase,
                fold_id="fold-1",
                baseline_id=baseline_id,
                repo_root=repo_root,
                starting_cash=starting_cash,
                quantity=quantity,
                run_label=run_label,
                eligible_signal_starts=eligible_signal_starts,
                allowed_session_windows=allowed_session_windows,
            )
            if (
                baseline.fill_source != "local_paper"
                or baseline.replay_evidence.fill_source != "local_paper"
            ):
                raise RuntimeError("KIS intraday CPU campaign requires local-paper replay")
            runs.append(KisIntradayCpuBaselineRun(phase=phase, baseline=baseline))
    return KisIntradayCpuCampaignRun(plan=plan, baseline_runs=tuple(runs))


def _selected_regular_session_dates(session_dates: Sequence[date]) -> tuple[date, ...]:
    selected = tuple(session_dates)
    if len(selected) != KIS_INTRADAY_SESSION_COUNT:
        raise ValueError("KIS intraday campaign requires exactly 20 selected sessions")
    if any(type(session_date) is not date for session_date in selected):
        raise ValueError("KIS intraday campaign session dates are invalid")
    if selected != tuple(sorted(selected)) or len(set(selected)) != len(selected):
        raise ValueError("KIS intraday campaign session dates must be unique and chronological")
    for session_date in selected:
        _regular_session_window(session_date)
    return selected


def _regular_session_window(session_date: date) -> SessionWindow:
    session = us_equity_2026_session(session_date)
    if (
        session is None
        or session.kind != "regular"
        or session.window.duration
        != Timeframe.M1.duration * KIS_INTRADAY_REGULAR_SESSION_MINUTES
    ):
        raise ValueError("KIS intraday campaign requires regular full sessions")
    return session.window


def _validate_selected_sessions(
    catalog: CatalogedBars,
    windows: tuple[SessionWindow, ...],
) -> None:
    if not isinstance(catalog, CatalogedBars):
        raise TypeError("KIS intraday campaign requires Data-selected CatalogedBars")
    bars = tuple(sorted(catalog.bars, key=lambda bar: bar.start_ts))
    if not bars or any(bar.timeframe != Timeframe.M1 or not bar.complete for bar in bars):
        raise ValueError("KIS intraday campaign requires complete 1m bars")
    expected_starts = tuple(
        window.open_ts + Timeframe.M1.duration * offset
        for window in windows
        for offset in range(KIS_INTRADAY_REGULAR_SESSION_MINUTES)
    )
    if tuple(bar.start_ts for bar in bars) != expected_starts:
        raise ValueError(
            "KIS intraday campaign requires complete contiguous minutes in each selected session"
        )
