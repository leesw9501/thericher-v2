"""Pure causal inputs, seals and analytical replay for the fixed component task.

Callbacks own already pinned source access. Past access requests scheduled Bar
observations only; target access happens after a snapshot or prediction seal.
The caller owns opaque-key/source identity; keys are never parsed as symbols.
An eagerly validated upstream panel establishes logical, not physical, read
isolation. This module performs no loading, scaling, fitting or persistence.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType

from thericher_v2.contracts import Bar, Timeframe, require_utc

SESSION_COUNT = 800
TOP_K = 10
FIT_COUNT = 10
FAMILY_SECONDS = 600
ROUND_TRIP_BPS = (5, 10, 20)
TRAIN_ENTRIES = range(61, 520)
OOF_ENTRIES = range(156, 520)
DEV_VIEWS = (range(540, 670), range(670, 800))
RANK_CONTROLS = ("ridge", "component", "momentum5", "momentum20", "momentum60")
ECONOMIC_CONTROLS = (*RANK_CONTROLS, "equal_weight", "cash")
POLICIES = ("tcn", *ECONOMIC_CONTROLS)
CELL_COUNT = len(POLICIES) * len(ROUND_TRIP_BPS) * len(DEV_VIEWS)


@dataclass(frozen=True, slots=True)
class PrefixFold:
    fit_target_cutoff: int
    score_entries: range

    @property
    def fit_entries(self) -> range:
        return range(61, self.fit_target_cutoff + 1)


OOF_FOLDS = tuple(
    PrefixFold(cutoff, range(start, stop))
    for cutoff, start, stop in (
        (154, 156, 247),
        (245, 247, 338),
        (336, 338, 429),
        (427, 429, 520),
    )
)


@dataclass(frozen=True, slots=True)
class ComponentPlan:
    sessions: tuple[date, ...]
    keys: tuple[str, ...]
    open_clocks: tuple[datetime, ...]
    close_clocks: tuple[datetime, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "sessions", tuple(self.sessions))
        object.__setattr__(self, "keys", tuple(self.keys))
        object.__setattr__(
            self,
            "open_clocks",
            tuple(require_utc(value, "open_clock") for value in self.open_clocks),
        )
        object.__setattr__(
            self,
            "close_clocks",
            tuple(require_utc(value, "close_clock") for value in self.close_clocks),
        )
        if (
            len(self.sessions) != SESSION_COUNT
            or any(type(day) is not date for day in self.sessions)
            or any(a >= b for a, b in zip(self.sessions, self.sessions[1:], strict=False))
        ):
            raise ValueError("exact_800_scheduled_sessions_required")
        if (
            not 1 <= len(self.keys) <= 128
            or any(not isinstance(key, str) or not key for key in self.keys)
            or self.keys != tuple(sorted(set(self.keys)))
        ):
            raise ValueError("frozen_unique_lexicographic_keys_required")
        if (
            len(self.open_clocks) != SESSION_COUNT
            or len(self.close_clocks) != SESSION_COUNT
            or any(
                opening >= closing
                for opening, closing in zip(self.open_clocks, self.close_clocks, strict=True)
            )
            or any(
                closing >= opening
                for closing, opening in zip(
                    self.close_clocks[:-1], self.open_clocks[1:], strict=True
                )
            )
        ):
            raise ValueError("explicit_ordered_session_clocks_required")


@dataclass(frozen=True, slots=True)
class FeatureRow:
    key: str
    components: tuple[tuple[float, ...], tuple[float, ...]]
    momentum: tuple[float, float, float]
    component_score: float

    def __post_init__(self) -> None:
        components = tuple(tuple(_number(value) for value in row) for row in self.components)
        momentum = tuple(_number(value) for value in self.momentum)
        if len(components) != 2 or any(len(row) != 20 for row in components) or len(momentum) != 3:
            raise ValueError("fixed_component_feature_geometry")
        object.__setattr__(self, "components", components)
        object.__setattr__(self, "momentum", momentum)
        object.__setattr__(self, "component_score", _number(self.component_score))

    @property
    def flattened(self) -> tuple[float, ...]:
        return self.components[0] + self.components[1]


@dataclass(frozen=True, slots=True)
class EligibilitySnapshot:
    entry_index: int
    decision_session: date
    entry_session: date
    rows: tuple[FeatureRow, ...]
    unavailable_keys: tuple[str, ...]
    decision_at: datetime
    entry_open_at: datetime
    target_close_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", tuple(self.rows))
        object.__setattr__(self, "unavailable_keys", tuple(self.unavailable_keys))
        for name in ("decision_at", "entry_open_at", "target_close_at"):
            object.__setattr__(self, name, require_utc(getattr(self, name), name))
        if (
            type(self.entry_index) is not int
            or not 61 <= self.entry_index < SESSION_COUNT
            or type(self.decision_session) is not date
            or type(self.entry_session) is not date
            or self.decision_session >= self.entry_session
            or not self.decision_at < self.entry_open_at < self.target_close_at
            or any(not isinstance(row, FeatureRow) for row in self.rows)
            or self.eligible_keys != tuple(sorted(set(self.eligible_keys)))
            or self.unavailable_keys != tuple(sorted(set(self.unavailable_keys)))
            or set(self.eligible_keys) & set(self.unavailable_keys)
            or not 1 <= len(self.rows) + len(self.unavailable_keys) <= 128
        ):
            raise ValueError("eligibility_snapshot_binding")

    @property
    def eligible_keys(self) -> tuple[str, ...]:
        return tuple(row.key for row in self.rows)


@dataclass(frozen=True, slots=True)
class OpenClose:
    """Only execution fields; invalid/missing values are assessed after sealing."""

    open: Decimal | float
    close: Decimal | float


PastSource = Callable[[str, date], Bar | None]
TargetSource = Callable[[str, date], OpenClose | Bar | None]
Score = Decimal | int | float | str


def _score(value: Score) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, float, str)):
        raise ValueError("finite_score_required")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except ArithmeticError as exc:
        raise ValueError("finite_score_required") from exc
    if not result.is_finite():
        raise ValueError("finite_score_required")
    return result


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, float)):
        raise ValueError("finite_numeric_required")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("finite_numeric_required")
    return result


def _past_bar(bar: Bar | None, session: date) -> bool:
    if (
        not isinstance(bar, Bar)
        or bar.timeframe is not Timeframe.D1
        or not bar.complete
        or bar.start_ts.date() != session
    ):
        return False
    try:
        values = tuple(_number(v) for v in (bar.open, bar.high, bar.low, bar.close))
        return all(v > 0 for v in values) and bar.high / bar.low <= Decimal(2)
    except (ValueError, ArithmeticError):
        return False


def snapshot(plan: ComponentPlan, entry_index: int, past_source: PastSource) -> EligibilitySnapshot:
    """Read exactly the preceding 61 scheduled sessions, never the entry bar."""
    if type(entry_index) is not int or not 61 <= entry_index < SESSION_COUNT:
        raise ValueError("entry_index_outside_supported_calendar")
    sessions = plan.sessions[entry_index - 61 : entry_index]
    rows, unavailable = [], []
    for key in plan.keys:
        bars = tuple(past_source(key, day) for day in sessions)
        if not all(_past_bar(bar, day) for bar, day in zip(bars, sessions, strict=True)):
            unavailable.append(key)
            continue
        if len({(bar.symbol, bar.market) for bar in bars}) != 1:
            unavailable.append(key)
            continue
        try:
            overnight = tuple(
                math.log(_number(bars[i].open)) - math.log(_number(bars[i - 1].close))
                for i in range(41, 61)
            )
            intraday = tuple(
                math.log(_number(bars[i].close)) - math.log(_number(bars[i].open))
                for i in range(41, 61)
            )
            # Match the existing momentum control: L completed bars, L-1 intervals.
            momentum = tuple(
                _number(bars[-1].close / bars[-lookback].close - 1) for lookback in (5, 20, 60)
            )
        except (ValueError, ArithmeticError):
            unavailable.append(key)
            continue
        rows.append(
            FeatureRow(
                key,
                (overnight, intraday),
                momentum,
                math.fsum(intraday) - math.fsum(overnight),
            )
        )
    return EligibilitySnapshot(
        entry_index,
        plan.sessions[entry_index - 1],
        plan.sessions[entry_index],
        tuple(rows),
        tuple(unavailable),
        plan.close_clocks[entry_index - 1],
        plan.open_clocks[entry_index],
        plan.close_clocks[entry_index],
    )


@dataclass(frozen=True, slots=True)
class PredictionSeal:
    snapshot: EligibilitySnapshot
    scores: tuple[tuple[str, Decimal], ...]
    allocation: str = "top10"
    selected_keys: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        scores = tuple((key, _score(score)) for key, score in self.scores)
        if tuple(key for key, _ in scores) != self.snapshot.eligible_keys:
            raise ValueError("scores_must_match_entire_eligible_snapshot")
        if self.allocation not in {"top10", "equal_weight", "cash"}:
            raise ValueError("unknown_fixed_allocation")
        selected = ()
        if len(scores) >= TOP_K and self.allocation != "cash":
            selected = (
                tuple(
                    key for key, _ in sorted(scores, key=lambda item: item[1], reverse=True)[:TOP_K]
                )
                if self.allocation == "top10"
                else self.snapshot.eligible_keys
            )
        object.__setattr__(self, "scores", scores)
        object.__setattr__(self, "selected_keys", selected)


def seal(
    state: EligibilitySnapshot,
    scores: Mapping[str, Score] | Sequence[Score],
    *,
    allocation: str = "top10",
) -> PredictionSeal:
    if isinstance(scores, Mapping):
        if set(scores) != set(state.eligible_keys):
            raise ValueError("scores_must_match_entire_eligible_snapshot")
        bound = tuple((key, scores[key]) for key in state.eligible_keys)
    else:
        if isinstance(scores, (str, bytes)) or len(scores) != len(state.eligible_keys):
            raise ValueError("scores_must_match_entire_eligible_snapshot")
        bound = tuple(zip(state.eligible_keys, scores, strict=True))
    return PredictionSeal(state, bound, allocation)


def controls(state: EligibilitySnapshot) -> Mapping[str, PredictionSeal]:
    scores = {"component": {row.key: row.component_score for row in state.rows}}
    scores.update(
        {
            f"momentum{lookback}": {row.key: row.momentum[i] for row in state.rows}
            for i, lookback in enumerate((5, 20, 60))
        }
    )
    result = {name: seal(state, values) for name, values in scores.items()}
    zero = dict.fromkeys(state.eligible_keys, 0.0)
    result["equal_weight"] = seal(state, zero, allocation="equal_weight")
    result["cash"] = seal(state, zero, allocation="cash")
    return MappingProxyType(result)


def _target_return(source: TargetSource, key: str, session: date) -> float | None:
    value = source(key, session)
    if value is None:
        return None
    if isinstance(value, Bar) and (
        not value.complete
        or value.timeframe is not Timeframe.D1
        or value.start_ts.date() != session
    ):
        return None
    if not isinstance(value, (OpenClose, Bar)):
        raise TypeError("target_source_requires_open_close_or_bar")
    try:
        opening, closing = _number(value.open), _number(value.close)
        if opening <= 0 or closing <= 0:
            return None
        result = closing / opening - 1
        return result if math.isfinite(result) else None
    except (ValueError, ArithmeticError):
        return None


def _midranks(values: Sequence[float]) -> tuple[float, ...]:
    result = [0.0] * len(values)
    order = sorted(range(len(values)), key=values.__getitem__)
    start = 0
    while start < len(order):
        stop = start + 1
        while stop < len(order) and values[order[stop]] == values[order[start]]:
            stop += 1
        for index in order[start:stop]:
            result[index] = (start + stop - 1) / 2
        start = stop
    return tuple(result)


@dataclass(frozen=True, slots=True)
class RankLabels:
    snapshot: EligibilitySnapshot
    observed_returns: tuple[tuple[str, float], ...]
    missing_keys: tuple[str, ...]
    labels: tuple[tuple[str, float], ...] | None

    def __post_init__(self) -> None:
        observed = tuple((key, _number(value)) for key, value in self.observed_returns)
        missing = tuple(self.missing_keys)
        if (
            tuple(key for key, _ in observed)
            != tuple(key for key in self.snapshot.eligible_keys if key not in missing)
            or missing != tuple(key for key in self.snapshot.eligible_keys if key in missing)
            or len(observed) + len(missing) != len(self.snapshot.eligible_keys)
        ):
            raise ValueError("target_cross_section_coverage_binding")
        labels = None
        if not missing and len(observed) >= TOP_K:
            ranks = _midranks(tuple(value for _, value in observed))
            labels = tuple(
                (key, rank / (len(observed) - 1) - 0.5)
                for (key, _), rank in zip(observed, ranks, strict=True)
            )
        if self.labels != labels:
            raise ValueError("complete_cross_section_rank_labels_required")
        object.__setattr__(self, "observed_returns", observed)
        object.__setattr__(self, "missing_keys", missing)
        object.__setattr__(self, "labels", labels)

    @property
    def coverage(self) -> tuple[int, int]:
        return len(self.observed_returns), len(self.snapshot.eligible_keys)

    @property
    def available_at(self) -> datetime:
        return self.snapshot.target_close_at


def target_labels(state: EligibilitySnapshot, target_source: TargetSource) -> RankLabels:
    """Future target ranks are supervision only, available after target CLOSE."""
    observed, missing = [], []
    for key in state.eligible_keys:
        value = _target_return(target_source, key, state.entry_session)
        (missing if value is None else observed).append(key if value is None else (key, value))
    labels = None
    if not missing and len(observed) >= TOP_K:
        ranks = _midranks(tuple(value for _, value in observed))
        labels = tuple(
            (key, rank / (len(observed) - 1) - 0.5)
            for (key, _), rank in zip(observed, ranks, strict=True)
        )
    return RankLabels(state, tuple(observed), tuple(missing), labels)


@dataclass(frozen=True, slots=True)
class DayReplay:
    seal: PredictionSeal
    round_trip_bps: int
    observed_returns: tuple[tuple[str, float], ...]
    missing_selected: tuple[str, ...]
    entry_turnover: float
    exit_turnover: float
    gross_return: float | None
    net_return: float | None
    reason: str | None = None

    @property
    def complete(self) -> bool:
        return self.net_return is not None


def replay_day(
    prediction: PredictionSeal, target_source: TargetSource, *, round_trip_bps: int = 10
) -> DayReplay:
    if type(round_trip_bps) is not int or round_trip_bps not in ROUND_TRIP_BPS:
        raise ValueError("cost_stress_not_frozen")
    observed, missing = [], []
    for key in prediction.selected_keys:
        value = _target_return(target_source, key, prediction.snapshot.entry_session)
        (missing if value is None else observed).append(key if value is None else (key, value))
    # Cash -> equal-weight allocation -> cash on every day, even unchanged names.
    turnover = 1.0 if prediction.selected_keys else 0.0
    gross = net = None
    reason = "selected_target_missing" if missing else None
    if not missing:
        gross = math.fsum(value / len(observed) for _, value in observed) if observed else 0.0
        net = gross - round_trip_bps / 10000 * ((turnover + turnover) / 2)
        if not math.isfinite(net) or 1 + net <= 0:
            net, reason = None, "net_nav_nonpositive_or_nonfinite"
    return DayReplay(
        prediction,
        round_trip_bps,
        tuple(observed),
        tuple(missing),
        turnover,
        turnover,
        gross,
        net,
        reason,
    )


@dataclass(frozen=True, slots=True)
class DayEvaluation:
    labels: RankLabels
    policies: tuple[tuple[str, PredictionSeal], ...]
    replays: tuple[tuple[str, int, DayReplay], ...]


def evaluate_day(
    state: EligibilitySnapshot,
    learned_scores: Mapping[str, Mapping[str, Score] | Sequence[Score]],
    target_source: TargetSource,
) -> DayEvaluation:
    """Seal all eight cached policies before the first numeric target callback."""
    if set(learned_scores) != {"tcn", "ridge"}:
        raise ValueError("exactly_two_cached_learned_scores_required")
    policies = dict(controls(state))
    for name in ("tcn", "ridge"):
        policies[name] = seal(state, learned_scores[name])
    targets = {key: target_source(key, state.entry_session) for key in state.eligible_keys}

    def cached(key: str, session: date) -> OpenClose | Bar | None:
        if session != state.entry_session:
            raise ValueError("target_session_binding")
        return targets[key]

    return DayEvaluation(
        target_labels(state, cached),
        tuple((name, policies[name]) for name in POLICIES),
        tuple(
            (name, cost, replay_day(policies[name], cached, round_trip_bps=cost))
            for name in POLICIES
            for cost in ROUND_TRIP_BPS
        ),
    )


@dataclass(frozen=True, slots=True)
class PortfolioMetrics:
    session_count: int
    missing_entries: tuple[int, ...]
    growth: float | None
    utility: float | None
    maximum_drawdown: float | None

    @property
    def complete(self) -> bool:
        return not self.missing_entries and self.growth is not None


def portfolio_metrics(
    days: Sequence[DayReplay], *, expected_entries: Sequence[int]
) -> PortfolioMetrics:
    expected = tuple(expected_entries)
    indices = tuple(day.seal.snapshot.entry_index for day in days)
    if not expected or expected != tuple(sorted(set(expected))):
        raise ValueError("unique_chronological_expected_entries_required")
    if indices != tuple(sorted(set(indices))) or not set(indices) <= set(expected):
        raise ValueError("replay_session_binding")
    if len({day.round_trip_bps for day in days}) > 1:
        raise ValueError("mixed_replay_cost_stress")
    by_index = dict(zip(indices, days, strict=True))
    missing = tuple(
        index for index in expected if index not in by_index or not by_index[index].complete
    )
    if missing:
        return PortfolioMetrics(len(expected), missing, None, None, None)
    logs = tuple(math.log1p(by_index[index].net_return) for index in expected)
    mean = math.fsum(logs) / len(logs)
    variance = math.fsum((value - mean) ** 2 for value in logs) / len(logs)
    peak = cumulative = drawdown = 0.0
    for value in logs:
        cumulative += value
        peak = max(peak, cumulative)
        drawdown = max(drawdown, -math.expm1(cumulative - peak))
    try:
        growth = math.expm1(math.fsum(logs))
        utility = 252 * (mean - 5 * variance)
        if not math.isfinite(growth) or not math.isfinite(utility):
            raise OverflowError
    except OverflowError:
        return PortfolioMetrics(len(expected), expected, None, None, None)
    return PortfolioMetrics(len(expected), (), growth, utility, drawdown)


def view_metrics(days: Sequence[DayReplay]) -> tuple[PortfolioMetrics, PortfolioMetrics]:
    if any(day.seal.snapshot.entry_index not in range(540, 800) for day in days):
        raise ValueError("dev_replay_outside_fixed_views")
    return tuple(
        portfolio_metrics(
            tuple(day for day in days if day.seal.snapshot.entry_index in view),
            expected_entries=view,
        )
        for view in DEV_VIEWS
    )


@dataclass(frozen=True, slots=True)
class OOFRankMetric:
    session_count: int
    missing_entries: tuple[int, ...]
    mean_spearman: float | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "missing_entries", tuple(self.missing_entries))
        if (
            type(self.session_count) is not int
            or self.session_count <= 0
            or len(self.missing_entries) > self.session_count
        ):
            raise ValueError("oof_metric_coverage")
        if self.mean_spearman is not None:
            mean = _number(self.mean_spearman)
            if not -1.000000000000001 <= mean <= 1.000000000000001:
                raise ValueError("spearman_domain")
            object.__setattr__(self, "mean_spearman", mean)

    @property
    def complete(self) -> bool:
        return not self.missing_entries and self.mean_spearman is not None


def session_equal_spearman(
    pairs: Sequence[tuple[PredictionSeal, RankLabels]],
    *,
    expected_entries: Sequence[int] = OOF_ENTRIES,
) -> OOFRankMetric:
    expected = tuple(expected_entries)
    if not expected or expected != tuple(sorted(set(expected))):
        raise ValueError("unique_chronological_expected_entries_required")
    correlations = {}
    seen = set()
    for prediction, targets in pairs:
        index = prediction.snapshot.entry_index
        if index in seen or index not in expected or targets.snapshot != prediction.snapshot:
            raise ValueError("oof_session_cross_section_binding")
        seen.add(index)
        if targets.labels is None:
            continue
        if tuple(key for key, _ in targets.labels) != prediction.snapshot.eligible_keys:
            raise ValueError("rank_labels_must_match_entire_eligible_snapshot")
        x = _midranks(tuple(score for _, score in prediction.scores))
        y = _midranks(tuple(label for _, label in targets.labels))
        mx, my = math.fsum(x) / len(x), math.fsum(y) / len(y)
        xx = math.fsum((v - mx) ** 2 for v in x)
        yy = math.fsum((v - my) ** 2 for v in y)
        if xx > 0 and yy > 0:
            correlations[index] = math.fsum(
                (a - mx) * (b - my) for a, b in zip(x, y, strict=True)
            ) / math.sqrt(xx * yy)
    missing = tuple(index for index in expected if index not in correlations)
    mean = math.fsum(correlations.values()) / len(correlations) if correlations else None
    return OOFRankMetric(len(expected), missing, mean)


@dataclass(frozen=True, slots=True)
class KillResult:
    survives: bool
    reasons: tuple[str, ...]


def strongest_kill(
    oof: Mapping[str, OOFRankMetric], dev: Mapping[str, Sequence[DayReplay]]
) -> KillResult:
    """Seen-development diagnostic only; never a promotion or execution gate."""
    reasons = []
    required_rank = ("tcn", *RANK_CONTROLS)
    required_economics = ("tcn", *ECONOMIC_CONTROLS)
    if any(
        name not in oof or not oof[name].complete or oof[name].session_count != len(OOF_ENTRIES)
        for name in required_rank
    ):
        reasons.append("required_oof_evidence_missing")
    elif any(oof["tcn"].mean_spearman <= oof[name].mean_spearman for name in RANK_CONTROLS):
        reasons.append("oof_rank_not_incremental")
    if any(name not in dev for name in required_economics):
        reasons.append("required_dev_evidence_missing")
    else:
        if any(day.round_trip_bps != 10 for name in required_economics for day in dev[name]):
            raise ValueError("strongest_kill_requires_primary_10bps")
        snapshots = {}
        for name in required_economics:
            for day in dev[name]:
                state = day.seal.snapshot
                if state.entry_index in snapshots and snapshots[state.entry_index] != state:
                    raise ValueError("matched_policy_eligibility_required")
                snapshots[state.entry_index] = state
        views = {name: view_metrics(dev[name]) for name in required_economics}
        for index in range(2):
            if not all(views[name][index].complete for name in required_economics):
                reasons.append(f"view{index + 1}_evidence_missing")
                continue
            candidate = views["tcn"][index]
            if candidate.growth <= 0:
                reasons.append(f"view{index + 1}_growth_nonpositive")
            if any(
                candidate.utility - views[name][index].utility <= 1e-10
                for name in ECONOMIC_CONTROLS
            ):
                reasons.append(f"view{index + 1}_utility_not_incremental")
    return KillResult(not reasons, tuple(reasons))
