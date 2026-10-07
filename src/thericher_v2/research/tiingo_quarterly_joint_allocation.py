"""One fixed, seen-data quarterly three-ETF allocation experiment.

Numeric inputs, targets and daily ledger paths stay in process. This is revised
adjusted-mark development, not a factor replication, broker replay or holdout.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import itertools
import json
import platform
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as day_time
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path

import numpy as np

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import tiingo_adjusted_etf_daily as data
from thericher_v2.research import tiingo_month_start_development as base
from thericher_v2.research.artifact_paths import reject_repo_artifact_path
from thericher_v2.research.campaign_registry import register_campaign_outcome
from thericher_v2.research.joint_portfolio_covariance import (
    CONTEXT_CLOSES,
    SYMBOLS,
    JointPortfolioInputUnavailable,
    build_joint_portfolio_covariance,
)

NAME = "joint-etf-quarterly-allocation-development-v1"
ARTIFACT_NAME = NAME + "-r2"
REPO, FAMILY_SECONDS, SECONDS, MEMORY_BYTES = base.REPO, 600, 570, 2 * 1024**3
TRAIN = ("2002-01-01", "2012-12-31")
PERIODS = (("2013-2019", "2013-01-01", "2019-12-31"), ("2020-2026-07", "2020-01-01", "2026-07-31"))
COSTS = ("2.5", "5", "10")
POLICIES = ("blend", "equal_weight", "minvar", "momentum", "beta_matched_basket_cash")
TOL = Decimal("1e-10")
EPS = Decimal("1e-40")
LEDGER_MODULE = "thericher_v2.research.three_asset_nav"
LEDGER_CODE = "src/thericher_v2/research/three_asset_nav.py"
WEIGHT_QUANTUM = Decimal("1e-45")
CPU_IMAGE = "sha256:846a900b8e1488f5018fecee2024276fe8fd33a3235c0fef4232298b96b4616f"
CODE = tuple(
    dict.fromkeys(
        (
            *base.CODE,
            "src/thericher_v2/contracts.py",
            "src/thericher_v2/serialization.py",
            "src/thericher_v2/data/tiingo_eod.py",
            "src/thericher_v2/data/tiingo_adjusted_etf_daily.py",
            "src/thericher_v2/research/joint_portfolio_covariance.py",
            "src/thericher_v2/research/tiingo_quarterly_joint_allocation.py",
            "scripts/run_tiingo_quarterly_joint_allocation.py",
            LEDGER_CODE,
        )
    )
)
encode, digest, require, atomic_new = base.encode, base.digest, base.require, base.atomic_new
METRICS = ("final_nav", "utility", "fees_initial_nav", "turnover_initial_nav")
HASH = r"sha256:[0-9a-f]{64}"


def configuration() -> dict:
    """Static, source-free plan; default CLI does not inspect files or calendars."""
    return dict(
        symbols=list(SYMBOLS),
        train=list(TRAIN),
        periods=[list(p) for p in PERIODS],
        policies=list(POLICIES),
        costs_per_side_bps=list(COSTS),
        cells=30,
        context_closes=253,
        context_returns=252,
        momentum_returns=231,
        covariance="population; 0.9*C+0.1*diag(diag(C)); fixed engineering recipe",
        minvar="long-only simplex; enumerate seven faces; zero-diagonal tie -> equal zero assets",
        minvar_numeric="max-absolute covariance scaling; face feasibility/dust1e-12; "
        "KKT1e-10; minimum objective then lexicographic tie; no eigenvalue repair",
        momentum="close[231]/close[0]-1; ascending average ranks / sum ranks; no cash switch",
        blend="0.5*minvar+0.5*momentum; no parameter or cost selection",
        timing="first scheduled NYSE OPEN of quarter; prior253 completed sessions; overnight carry",
        ledger="three positions/shared cash; simultaneous post-fee weights; NAV1 per period",
        ledger_api=LEDGER_MODULE + ".replay(days,targets,cost_bps); fixed NAV1/final CLOSE exit",
        target_numeric="Decimal50 HALF_EVEN; all but last positive weight quantized45dp; "
        "last positive residual exact; basket first two45dp/third residual; "
        "beta fraction quantized45dp then residual rechecked",
        fees="actual traded notional; initial fee in first return; "
        "final fee in final existing return",
        beta_control="quarterly equal-weight basket + cash; same fixed c across costs and periods",
        beta_matching="TRAIN0cost aligned daily simple NAV returns vs SPY; endpoint sign bracket; "
        "64 bisections; best residual <=1e-10; not monotonic assumed; no clipping",
        beta_unresolved="only matched comparison unavailable; no outcome-based substitute",
        utility="252*(mean(daily log NAV returns)-5*population variance(daily log NAV returns))",
        improvement_tolerance="1e-10 absolute NAV/utility, before output rounding",
        missing="keep scheduled quarters; required past gap -> scoped input unavailable; "
        "payoff/mark gap -> affected period unavailable; no impute or opportunity shift",
        strongest_kill="10bps BOTH periods: NAV+utility beat EW and matched control; "
        "utility beats both components by >1e-10",
        budget=dict(
            cpu_threads=1,
            container_cpus=2,
            memory_bytes=MEMORY_BYTES,
            wall_seconds=FAMILY_SECONDS,
            gpu=False,
            passes=1,
            retries=False,
            training=False,
        ),
        runtime=dict(
            image=CPU_IMAGE,
            python="3.12.15",
            numpy="2.5.1",
            calendar="5.4.0",
            network="none",
            swap_bytes=0,
        ),
        prior_families=[
            "tiingo-adjusted-monthly-holding-development-v1",
            "firstrate-paired-allocation-development-20261005-v1",
        ],
        scope=dict(
            holdout_access="none",
            selection=False,
            promotion=False,
            paper_input=False,
            execution_parity=False,
            profitability_claim=False,
        ),
        assumptions=[
            "revised seen non-PIT marks; conditional availability, not contemporaneous proof",
            "fractional adjusted NAV proxy; no extra dividends/splits; cash interest zero",
            "fixed surviving correlated ETFs; no short/leverage/volatility cash switch",
            "231-return quarterly three-ETF ranks NOT Fama-French CRSP factor replication",
            "10% diagonal shrinkage not a paper-optimal estimator claim",
        ],
        weights_retained=False,
        train_matching_parameter_retained=True,
        technical_repair=dict(
            artifact_name=ARTIFACT_NAME,
            original_artifact_name=NAME,
            original_contract_sha256="sha256:379a8131032dfe8fa3c06a4d111e68506a3edf436a7c08cf2f26da9123ba6b13",
            original_result_sha256="sha256:85fef576a0171d44c211a25e9654af12cc73b284ca18a08ed3ce74fc3e41595a",
            reason="matched_fraction",
            version=2,
            numeric_fix="apply existing45dp HALF_EVEN fraction lattice "
            "before every basket construction",
            attempt_wall_seconds=SECONDS,
            family_wall_seconds=FAMILY_SECONDS,
            prior_recorded_seconds="19.50",
            fresh_budget=False,
            comparison_outcomes_observed=False,
            recovery="same-family contract/result-pinned registry-only; "
            "original failed attempt retained",
        ),
    )


def runtime_identity() -> dict:
    actual = dict(
        python=platform.python_version(),
        numpy=np.__version__,
        calendar=importlib.metadata.version("pandas-market-calendars"),
    )
    require(all(actual[k] == configuration()["runtime"][k] for k in actual), "runtime_version")
    return actual


def calendar_schedule() -> list[dict]:
    require(importlib.metadata.version("pandas-market-calendars") == "5.4.0", "calendar_version")
    import pandas_market_calendars as calendars

    schedule = calendars.get_calendar("NYSE").schedule(
        start_date="2000-12-01", end_date="2026-07-31"
    )
    return [
        dict(
            session_date=stamp.date().isoformat(),
            open_at=row["market_open"].to_pydatetime().astimezone(UTC).isoformat(),
        )
        for stamp, row in schedule.iterrows()
    ]


def _quarter(day: str) -> tuple[int, int]:
    d = date.fromisoformat(day)
    return d.year, (d.month - 1) // 3


def build_plan(schedule: Sequence[Mapping]) -> dict:
    require(bool(schedule), "calendar_support")
    require(all(set(s) == {"session_date", "open_at"} for s in schedule), "calendar_fields")
    days = [s["session_date"] for s in schedule]
    require(
        all(type(d) is str and date.fromisoformat(d).isoformat() == d for d in days),
        "calendar_date",
    )
    require(all(a < b for a, b in zip(days, days[1:], strict=False)), "calendar_order")
    require(days[0] >= "2000-12-01" and days[-1] <= "2026-07-31", "calendar_scope")
    for item in schedule:
        opened = datetime.fromisoformat(item["open_at"])
        require(
            opened.tzinfo is not None
            and opened.utcoffset() == timedelta(0)
            and opened.date().isoformat() == item["session_date"],
            "calendar_open",
        )
    periods = []
    for name, start, end in (("TRAIN", *TRAIN), *PERIODS):
        indices = [i for i, d in enumerate(days) if start <= d <= end]
        require(bool(indices), "calendar_period_support")
        first, stop = indices[0], indices[-1] + 1
        require(
            first >= CONTEXT_CLOSES and _quarter(days[first]) != _quarter(days[first - 1]),
            "calendar_prior_support",
        )
        decisions = [i for i in range(first, stop) if _quarter(days[i]) != _quarter(days[i - 1])]
        periods.append(
            dict(
                period=name,
                bounds=[first, stop],
                decisions=[
                    dict(
                        index=i,
                        session_date=days[i],
                        decision_at=schedule[i]["open_at"],
                        scheduled_dates=days[i - CONTEXT_CLOSES : i],
                    )
                    for i in decisions
                ],
            )
        )
    return dict(schedule=[dict(s) for s in schedule], days=days, periods=periods)


def source_identity() -> dict:
    return dict(
        base.source_identity(),
        view="provider_adjusted_OHLC_from_immutable_raw",
        raw_sha256=dict(data.RAW_SHA256),
    )


def proposed_contract(_market_data_root=None) -> dict:
    config, source = configuration(), source_identity()
    return dict(
        name=NAME,
        config=config,
        config_sha256=digest(encode(config)),
        source=source,
        source_sha256=digest(encode(source)),
        runtime=runtime_identity(),
        plan=build_plan(calendar_schedule()),
        code_sha256={p: digest((REPO / p).read_bytes()) for p in CODE},
    )


def header(contract: dict, pin: str) -> dict:
    require(
        set(contract)
        == {
            "name",
            "config",
            "config_sha256",
            "source",
            "source_sha256",
            "runtime",
            "plan",
            "code_sha256",
        },
        "contract_fields",
    )
    require(contract["name"] == NAME and digest(encode(contract)) == pin, "contract_binding")
    require(
        contract["config"] == configuration()
        and contract["config_sha256"] == digest(encode(configuration())),
        "config_changed",
    )
    require(
        contract["source"] == source_identity()
        and contract["source_sha256"] == digest(encode(source_identity())),
        "source_changed",
    )
    require(contract["runtime"] == runtime_identity(), "runtime_changed")
    require(contract["plan"] == build_plan(contract["plan"]["schedule"]), "plan_changed")
    require(
        set(contract["code_sha256"]) == set(CODE)
        and all(type(p) is str and re.fullmatch(HASH, p) for p in contract["code_sha256"].values()),
        "code_pins",
    )
    return dict(
        name=NAME,
        contract_sha256=pin,
        config_sha256=contract["config_sha256"],
        source_sha256=contract["source_sha256"],
        scope=configuration()["scope"],
    )


def _read(path: Path) -> bytes:
    return base._read(path, limit=8 * 1024**2)


def _output(root: Path) -> Path:
    path = Path(root).absolute() / "research" / ARTIFACT_NAME
    reject_repo_artifact_path(path, REPO)
    require(all(not p.is_symlink() for p in (path, *path.parents)), "artifact_link")
    require(path.is_dir(), "artifact_missing")
    return path


def register_contract(root: Path, contract: dict, pin: str) -> None:
    header(contract, pin)
    base.register_frozen_campaign(
        contract_hash=pin,
        dataset_hash=digest(encode(contract["source"])),
        split_hash=digest(encode(contract["plan"])),
        cost_model_hash=digest(encode(COSTS)),
        trial_family=NAME,
        holdout_access="none",
        artifact_root=root,
        repo_root=REPO,
    )


def freeze(artifact_root: Path, market_data_root: Path) -> str:
    base.verify_metadata(artifact_root, market_data_root)
    contract = proposed_contract()
    parent = base.ensure_external_artifact_directory(artifact_root, REPO, "research")
    output = parent / ARTIFACT_NAME
    output.mkdir()
    atomic_new(output / "precommit.json", contract)
    pin = digest(encode(contract))
    register_contract(artifact_root, contract, pin)
    return pin


def verify(artifact_root: Path, market_data_root: Path, pin: str) -> tuple[Path, dict]:
    output = _output(artifact_root)
    raw = _read(output / "precommit.json")
    require(digest(raw) == pin and raw == encode(proposed_contract()), "precommit_changed")
    base.verify_metadata(artifact_root, market_data_root)
    contract = json.loads(raw)
    header(contract, pin)
    return output, contract


def _normalized(values: Sequence[Decimal]) -> tuple[Decimal, ...]:
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 50, ROUND_HALF_EVEN
        total = sum(values, Decimal(0))
        require(total > 0 and all(v.is_finite() and v >= 0 for v in values), "allocation_values")
        result = [(v / total).quantize(WEIGHT_QUANTUM) for v in values]
        last = max(i for i, v in enumerate(values) if v > 0)
        result[last] = 1 - sum((v for i, v in enumerate(result) if i != last), Decimal(0))
        require(all(v >= 0 for v in result), "allocation_residual")
        return tuple(result)


def minimum_variance_weights(covariance: Sequence[Sequence[float]]) -> tuple[Decimal, ...]:
    """Solve the fixed three-dimensional simplex problem without a fitted estimator."""
    c = np.asarray(covariance, dtype=np.float64)
    require(
        c.shape == (3, 3) and np.isfinite(c).all() and np.array_equal(c, c.T), "covariance_values"
    )
    scale = float(np.abs(c).max())
    if scale == 0:
        return _normalized((Decimal(1),) * 3)
    c = c / scale
    require(
        np.linalg.eigvalsh(c)[0] >= -64 * np.finfo(float).eps and np.all(np.diag(c) >= 0),
        "covariance_psd",
    )
    zeros = np.flatnonzero(np.diag(c) == 0)
    if len(zeros):
        require(np.all(c[zeros] == 0), "covariance_zero_diagonal")
        return _normalized(tuple(Decimal(int(i in zeros)) for i in range(3)))
    shrunk = 0.9 * c + 0.1 * np.diag(np.diag(c))
    candidates = []
    try:
        for count in range(1, 4):
            for face in itertools.combinations(range(3), count):
                x = np.linalg.solve(shrunk[np.ix_(face, face)], np.ones(count))
                if not np.isfinite(x).all() or x.sum() <= 0:
                    continue
                x = x / x.sum()
                if np.min(x) < -1e-12:
                    continue
                x = np.maximum(x, 0)
                x = x / x.sum()
                w = np.zeros(3)
                w[list(face)] = x
                candidates.append((float(w @ shrunk @ w), w))
    except np.linalg.LinAlgError:
        raise JointPortfolioInputUnavailable("allocation_not_representable") from None
    require(bool(candidates), "allocation_faces")
    _, w = min(candidates, key=lambda item: (item[0], tuple(item[1])))
    gradient, value = shrunk @ w, float(w @ shrunk @ w)
    if (
        not np.isfinite(gradient).all()
        or np.min(gradient - value) < -1e-10
        or np.max(np.abs(gradient[w > 1e-12] - value)) > 1e-10
    ):
        raise JointPortfolioInputUnavailable("allocation_not_representable")
    return _normalized(tuple(Decimal.from_float(float(v)) for v in w))


def momentum_rank_weights(scores: Sequence[Decimal]) -> tuple[Decimal, ...]:
    require(
        len(scores) == 3 and all(type(v) is Decimal and v.is_finite() for v in scores),
        "momentum_values",
    )
    ranks = tuple(
        Decimal(1 + sum(x < v for x in scores)) + Decimal(sum(x == v for x in scores) - 1) / 2
        for v in scores
    )
    return _normalized(ranks)


@dataclass(frozen=True, slots=True, repr=False)
class QuarterAllocation:
    decision_at: datetime
    minvar: tuple[Decimal, ...]
    momentum: tuple[Decimal, ...]
    blend: tuple[Decimal, ...]

    def safe_facts(self) -> dict:
        return dict(
            status="ready",
            symbol_count=3,
            close_count=253,
            return_count=252,
            decision_at=self.decision_at.isoformat(),
        )


def quarter_allocation(rows_by_symbol: Mapping[str, Sequence], spec: Mapping) -> QuarterAllocation:
    require(set(rows_by_symbol) == set(SYMBOLS), "symbol_set")
    dates = tuple(date.fromisoformat(d) for d in spec["scheduled_dates"])
    required = frozenset(dates)
    bars, closes = {}, {}
    for symbol in SYMBOLS:
        selected = [r for r in rows_by_symbol[symbol] if r.session_date in required]
        try:
            bars[symbol] = tuple(
                Bar(
                    symbol=symbol,
                    market="US",
                    timeframe=Timeframe.D1,
                    start_ts=datetime.combine(r.session_date, day_time(), UTC),
                    open=r.adj_open,
                    high=r.adj_high,
                    low=r.adj_low,
                    close=r.adj_close,
                    volume=Decimal(0),
                    complete=True,
                )
                for r in selected
            )
        except (ValueError, TypeError, ArithmeticError):
            raise JointPortfolioInputUnavailable("required_bar_values_invalid") from None
        if any(r.symbol != symbol for r in selected):
            raise JointPortfolioInputUnavailable("required_bar_identity")
        closes[symbol] = tuple(r.adj_close for r in selected)
    cov = build_joint_portfolio_covariance(
        bars,
        vintage_ref_by_symbol=dict.fromkeys(SYMBOLS, data.DATASET_SHA256),
        scheduled_dates=dates,
        decision_at=datetime.fromisoformat(spec["decision_at"]),
    )
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 50, ROUND_HALF_EVEN
        ranks = momentum_rank_weights(tuple(closes[s][231] / closes[s][0] - 1 for s in SYMBOLS))
        minimum = minimum_variance_weights(cov.covariance)
        blend = _normalized(tuple((a + b) / 2 for a, b in zip(minimum, ranks, strict=True)))
    return QuarterAllocation(cov.decision_at, minimum, ranks, blend)


@dataclass(frozen=True, slots=True, repr=False)
class PeriodInputs:
    period: str
    rows: Mapping
    actions: Mapping
    facts: Mapping


def prepare_inputs(
    rows_by_symbol: Mapping[str, Sequence], plan: Mapping, *, deadline: float
) -> tuple[PeriodInputs, ...]:
    """Check every fixed input/mark scope before any ledger outcome is computed."""
    require(set(rows_by_symbol) == set(SYMBOLS), "symbol_set")
    prepared = []
    for period in plan["periods"]:
        require(time.monotonic() < deadline, "hard_timeout")
        first, stop = period["bounds"]
        days = plan["days"][first:stop]
        needed = frozenset(date.fromisoformat(d) for d in days)
        rows, missing, invalid = {}, 0, 0
        for symbol in SYMBOLS:
            stream = [r for r in rows_by_symbol[symbol] if r.session_date in needed]
            mapping = {r.session_date.isoformat(): r for r in stream}
            rows[symbol] = mapping
            missing += len(days) - len(mapping)
            invalid += len(stream) - len(mapping)
            for row in stream:
                values = (row.adj_open, row.adj_high, row.adj_low, row.adj_close)
                if not (
                    row.symbol == symbol
                    and all(type(v) is Decimal and v.is_finite() and v > 0 for v in values)
                    and row.adj_low
                    <= min(row.adj_open, row.adj_close)
                    <= max(row.adj_open, row.adj_close)
                    <= row.adj_high
                ):
                    invalid += 1
        actions = {p: {} for p in POLICIES[:4]}
        quarter_facts = []
        for spec in period["decisions"]:
            require(time.monotonic() < deadline, "hard_timeout")
            i = spec["index"]
            actions["equal_weight"][i] = _normalized((Decimal(1),) * 3)
            try:
                weights = quarter_allocation(rows_by_symbol, spec)
                for p in ("blend", "minvar", "momentum"):
                    actions[p][i] = getattr(weights, p)
                quarter_facts.append(dict(session_date=spec["session_date"], status="ready"))
            except JointPortfolioInputUnavailable as exc:
                quarter_facts.append(dict(session_date=spec["session_date"], **exc.safe_facts()))
        facts = dict(
            period=period["period"],
            sessions=stop - first,
            quarters=len(period["decisions"]),
            missing_marks=missing,
            invalid_marks=invalid,
            inputs=quarter_facts,
        )
        prepared.append(PeriodInputs(period["period"], rows, actions, facts))
    return tuple(prepared)


def replay_joint(rows, days, bounds, actions, cost_bps, *, deadline):
    """Narrow integration point; no single-asset or synthetic-account fallback."""
    ledger = importlib.import_module(LEDGER_MODULE)
    require(tuple(ledger.SYMBOLS) == SYMBOLS, "ledger_columns")
    records = []
    for i in range(*bounds):
        require(time.monotonic() < deadline, "hard_timeout")
        records.append(
            ledger.ThreeAssetDay(
                date.fromisoformat(days[i]),
                tuple(rows[s][days[i]].adj_open for s in SYMBOLS),
                tuple(rows[s][days[i]].adj_close for s in SYMBOLS),
            )
        )
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 50, ROUND_HALF_EVEN
        targets = {
            date.fromisoformat(days[i]): ledger.ThreeAssetTarget(
                tuple(weights), 1 - sum(weights, Decimal(0))
            )
            for i, weights in actions.items()
        }
    path = ledger.replay(tuple(records), targets, Decimal(cost_bps))
    require(time.monotonic() < deadline, "hard_timeout")
    require(
        tuple(d.date.isoformat() for d in path.daily) == tuple(days[slice(*bounds)])
        and path.daily[-1].flat is True
        and all(q == 0 for q in path.final_state.quantities)
        and path.final_state.cash == path.final_nav,
        "ledger_scope_or_closure",
    )
    return dict(
        navs=path.navs,
        returns=path.simple_returns,
        final_nav=path.final_nav,
        fees_initial_nav=path.total_fees,
        turnover_initial_nav=path.total_traded_notional,
        trades=sum(d.traded_notional > 0 for d in path.daily),
    )


@dataclass(frozen=True, slots=True, repr=False)
class LedgerPath:
    navs: tuple[Decimal, ...]
    returns: tuple[Decimal, ...]
    fees: Decimal
    turnover: Decimal
    trades: int


def checked_path(raw: Mapping, sessions: int, cost_bps: str) -> LedgerPath:
    navs, returns = tuple(raw["navs"]), tuple(raw["returns"])
    require(len(navs) == len(returns) == sessions and sessions > 1, "ledger_alignment")
    require(all(type(v) is Decimal and v.is_finite() and v > 0 for v in navs), "ledger_nav")
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 50, ROUND_HALF_EVEN
        expected = tuple(b / a - 1 for a, b in zip((Decimal(1), *navs[:-1]), navs, strict=True))
        require(
            all(
                type(r) is Decimal and r.is_finite() and r > -1 and abs(r - e) <= EPS * (1 + abs(e))
                for r, e in zip(returns, expected, strict=True)
            ),
            "ledger_returns",
        )
        fees, turnover = raw["fees_initial_nav"], raw["turnover_initial_nav"]
        require(
            all(type(v) is Decimal and v.is_finite() and v >= 0 for v in (fees, turnover))
            and abs(fees - Decimal(cost_bps) * turnover / 10000) <= EPS * (1 + fees),
            "ledger_fees",
        )
    require(
        raw["final_nav"] == navs[-1] and type(raw["trades"]) is int and raw["trades"] >= 0,
        "ledger_terminal",
    )
    return LedgerPath(navs, returns, fees, turnover, raw["trades"])


def _variance(values: Sequence[Decimal]) -> Decimal:
    mean = sum(values, Decimal(0)) / len(values)
    return sum(((v - mean) ** 2 for v in values), Decimal(0)) / len(values)


def utility(navs: Sequence[Decimal]) -> Decimal:
    require(
        len(navs) > 1 and all(type(v) is Decimal and v.is_finite() and v > 0 for v in navs),
        "utility_nav",
    )
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 50, ROUND_HALF_EVEN
        logs = tuple((b / a).ln() for a, b in zip((Decimal(1), *navs[:-1]), navs, strict=True))
        return 252 * (sum(logs, Decimal(0)) / len(logs) - 5 * _variance(logs))


def beta(returns: Sequence[Decimal], reference: Sequence[Decimal]) -> Decimal:
    require(len(returns) == len(reference) and len(returns) > 1, "beta_alignment")
    require(
        all(
            type(v) is Decimal and v.is_finite() and v > -1
            for series in (returns, reference)
            for v in series
        ),
        "beta_returns",
    )
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 50, ROUND_HALF_EVEN
        var = _variance(reference)
        require(var > 0, "beta_reference_zero_variance")
        left = sum(returns, Decimal(0)) / len(returns)
        right = sum(reference, Decimal(0)) / len(reference)
        return (
            sum(
                ((a - left) * (b - right) for a, b in zip(returns, reference, strict=True)),
                Decimal(0),
            )
            / len(returns)
            / var
        )


@dataclass(frozen=True, slots=True, repr=False)
class BetaMatch:
    fraction: Decimal | None
    status: str
    reason: str | None
    iterations: int
    residual_probe: Decimal | None = None

    def safe_facts(self) -> dict:
        return dict(
            status=self.status,
            reason_code=self.reason,
            iterations=self.iterations,
            calibration_sha256=None
            if self.fraction is None
            else digest(encode(str(self.fraction))),
            residual_probe_sha256=None
            if self.residual_probe is None
            else digest(encode(str(self.residual_probe))),
        )


def match_beta(target: Decimal, beta_at_fraction: Callable[[Decimal], Decimal]) -> BetaMatch:
    require(type(target) is Decimal and target.is_finite(), "beta_target")
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 50, ROUND_HALF_EVEN

        def residual(c):
            value = beta_at_fraction(c)
            require(type(value) is Decimal and value.is_finite(), "beta_callback")
            return value - target

        lo, hi = Decimal(0), Decimal(1)
        left, right = residual(lo), residual(hi)
        if abs(left) <= TOL:
            return BetaMatch(lo, "matched", None, 0)
        if abs(right) <= TOL:
            return BetaMatch(hi, "matched", None, 0)
        if (left > 0) == (right > 0):
            return BetaMatch(None, "comparison_unresolved", "beta_not_bracketed", 0)
        best, error = (lo, left) if abs(left) <= abs(right) else (hi, right)
        for _ in range(64):
            center = (lo + hi) / 2
            middle = residual(center)
            if abs(middle) < abs(error):
                best, error = center, middle
            if middle == 0:
                lo = hi = center
                left = right = middle
            elif (middle > 0) == (left > 0):
                lo, left = center, middle
            else:
                hi, right = center, middle
        best = best.quantize(WEIGHT_QUANTUM)
        error = residual(best)
        if abs(error) > TOL:
            return BetaMatch(None, "comparison_unresolved", "beta_residual_exceeded", 64, best)
        return BetaMatch(best, "matched", None, 64)


def _scaled_equal_weight(fraction: Decimal) -> tuple[Decimal, ...]:
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 50, ROUND_HALF_EVEN
        # The ledger interprets the unallocated fraction as cash.
        require(
            type(fraction) is Decimal and fraction.is_finite() and 0 <= fraction <= 1,
            "matched_fraction",
        )
        # Search points can exceed45dp; use the same frozen target lattice as final c.
        fraction = fraction.quantize(WEIGHT_QUANTUM)
        one = (fraction / 3).quantize(WEIGHT_QUANTUM)
        return one, one, fraction - 2 * one


def calibrate(
    prepared: PeriodInputs,
    plan: dict,
    replay: Callable,
    *,
    deadline: float,
    frozen_match: BetaMatch | None = None,
) -> BetaMatch:
    training = plan["periods"][0]
    if (
        prepared.facts["missing_marks"]
        or prepared.facts["invalid_marks"]
        or len(prepared.actions["blend"]) != prepared.facts["quarters"]
    ):
        answer = BetaMatch(None, "comparison_unresolved", "train_input_unavailable", 0)
        require(frozen_match is None or frozen_match == answer, "matching_replay_changed")
        return answer
    days, bounds = plan["days"], training["bounds"]
    count = bounds[1] - bounds[0]

    def path(actions):
        require(time.monotonic() < deadline, "hard_timeout")
        return checked_path(
            replay(prepared.rows, days, bounds, actions, "0", deadline=deadline), count, "0"
        )

    candidate = path(prepared.actions["blend"])
    reference = path({bounds[0]: (Decimal(1), Decimal(0), Decimal(0))})
    if _variance(reference.returns) == 0:
        answer = BetaMatch(None, "comparison_unresolved", "beta_reference_zero_variance", 0)
        require(frozen_match is None or frozen_match == answer, "matching_replay_changed")
        return answer
    target = beta(candidate.returns, reference.returns)

    def comparator(c):
        actions = {i: _scaled_equal_weight(c) for i in prepared.actions["equal_weight"]}
        return beta(path(actions).returns, reference.returns)

    if frozen_match is not None:
        if frozen_match.fraction is not None:
            require(
                abs(comparator(frozen_match.fraction) - target) <= TOL, "matching_replay_residual"
            )
        elif frozen_match.reason == "beta_not_bracketed":
            left, right = comparator(Decimal(0)) - target, comparator(Decimal(1)) - target
            require(
                abs(left) > TOL and abs(right) > TOL and (left > 0) == (right > 0),
                "matching_replay_bracket",
            )
        elif frozen_match.reason == "beta_residual_exceeded":
            left, right = comparator(Decimal(0)) - target, comparator(Decimal(1)) - target
            require(
                frozen_match.iterations == 64
                and frozen_match.residual_probe is not None
                and abs(left) > TOL
                and abs(right) > TOL
                and (left > 0) != (right > 0)
                and abs(comparator(frozen_match.residual_probe) - target) > TOL,
                "matching_replay_residual_failure",
            )
        else:
            require(False, "matching_replay_reason")
        return frozen_match
    return match_beta(target, comparator)


def _numeric(value: Decimal) -> str:
    require(type(value) is Decimal and value.is_finite(), "metric_finite")
    return str(value)


def verdict(cells: Sequence[Mapping]) -> str:
    primary = [c for c in cells if c["cost_per_side_bps"] == "10"]
    if len(primary) != 10 or any(c["status"] != "evaluated" for c in primary):
        return "input_unavailable"
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 50, ROUND_HALF_EVEN
        for period, _, _ in PERIODS:
            group = {c["policy"]: c for c in primary if c["period"] == period}
            candidate = group["blend"]
            for control in ("equal_weight", "beta_matched_basket_cash", "minvar", "momentum"):
                fields = (
                    ("final_nav", "utility")
                    if control in POLICIES[1:2] + POLICIES[4:]
                    else ("utility",)
                )
                if any(Decimal(candidate[k]) - Decimal(group[control][k]) <= TOL for k in fields):
                    return "rejected"
    return "supported_with_limits"


def evaluate(
    rows_by_symbol,
    contract: dict,
    pin: str,
    *,
    deadline: float,
    ledger_replay: Callable | None = None,
    frozen_match: BetaMatch | None = None,
) -> dict:
    result = header(contract, pin)
    plan = contract["plan"]
    prepared = prepare_inputs(rows_by_symbol, plan, deadline=deadline)
    replay = replay_joint if ledger_replay is None else ledger_replay
    matched = calibrate(prepared[0], plan, replay, deadline=deadline, frozen_match=frozen_match)
    cells = []
    for inputs, period in zip(prepared[1:], plan["periods"][1:], strict=True):
        for cost in COSTS:
            for policy in POLICIES:
                require(time.monotonic() < deadline, "hard_timeout")
                if policy == "beta_matched_basket_cash":
                    actions = (
                        None
                        if matched.fraction is None
                        else {
                            i: _scaled_equal_weight(matched.fraction)
                            for i in inputs.actions["equal_weight"]
                        }
                    )
                else:
                    actions = inputs.actions[policy]
                available = (
                    not inputs.facts["missing_marks"]
                    and not inputs.facts["invalid_marks"]
                    and actions is not None
                    and len(actions) == inputs.facts["quarters"]
                )
                cell = dict(
                    period=inputs.period,
                    policy=policy,
                    cost_per_side_bps=cost,
                    status="evaluated" if available else "input_unavailable",
                    trades=None,
                    action_sha256=None,
                    **dict.fromkeys(METRICS),
                )
                if available:
                    cell["action_sha256"] = digest(
                        encode(
                            [
                                [i, [str(v) for v in weights]]
                                for i, weights in sorted(actions.items())
                            ]
                        )
                    )
                    path = checked_path(
                        replay(
                            inputs.rows,
                            plan["days"],
                            period["bounds"],
                            actions,
                            cost,
                            deadline=deadline,
                        ),
                        inputs.facts["sessions"],
                        cost,
                    )
                    cell.update(
                        final_nav=_numeric(path.navs[-1]),
                        utility=_numeric(utility(path.navs)),
                        fees_initial_nav=_numeric(path.fees),
                        turnover_initial_nav=_numeric(path.turnover),
                        trades=path.trades,
                    )
                cells.append(cell)
    result.update(
        status="complete"
        if all(c["status"] == "evaluated" for c in cells)
        else "input_unavailable",
        criterion=verdict(cells),
        coverage=[dict(p.facts) for p in prepared],
        matching=dict(
            matched.safe_facts(),
            invested_fraction=None if matched.fraction is None else str(matched.fraction),
            residual_probe=None if matched.residual_probe is None else str(matched.residual_probe),
        ),
        cells=cells,
    )
    validate_result(result, contract, pin)
    return result


def failure(contract: dict, pin: str, reason: str) -> dict:
    require(reason in base.FAILURES, "failure_category")
    return dict(
        header(contract, pin),
        status="failed",
        criterion="not_evaluable",
        reason=reason,
        coverage=[],
        matching=None,
        cells=[],
    )


def validate_result(result: dict, contract: dict, pin: str) -> None:
    expected = header(contract, pin)
    if result.get("status") == "failed":
        require(result == failure(contract, pin, result.get("reason")), "failure_shape")
        return
    require(
        set(result) == set(expected) | {"status", "criterion", "coverage", "matching", "cells"}
        and {k: result[k] for k in expected} == expected,
        "result_binding",
    )
    require(len(result["coverage"]) == 3, "coverage_count")
    for facts, period in zip(result["coverage"], contract["plan"]["periods"], strict=True):
        require(
            set(facts)
            == {"period", "sessions", "quarters", "missing_marks", "invalid_marks", "inputs"},
            "coverage_fields",
        )
        require(
            all(
                type(facts[k]) is int and facts[k] >= 0
                for k in ("sessions", "quarters", "missing_marks", "invalid_marks")
            ),
            "coverage_counts",
        )
        require(
            facts["period"] == period["period"]
            and facts["sessions"] == period["bounds"][1] - period["bounds"][0]
            and facts["quarters"] == len(period["decisions"])
            and [i["session_date"] for i in facts["inputs"]]
            == [i["session_date"] for i in period["decisions"]],
            "coverage_binding",
        )
        for inputs in facts["inputs"]:
            require(
                (set(inputs) == {"session_date", "status"} and inputs["status"] == "ready")
                or (
                    set(inputs) == {"session_date", "status", "reason_code"}
                    and inputs["status"] == "input_unavailable"
                    and inputs["reason_code"]
                    in {
                        "required_bar_values_invalid",
                        "required_bar_identity",
                        "required_session_duplicate",
                        "required_session_missing",
                        "required_session_alignment_or_order",
                        "required_bar_incomplete",
                        "returns_not_representable",
                        "covariance_not_representable",
                        "covariance_not_psd",
                        "allocation_not_representable",
                    }
                ),
                "input_facts",
            )
    matched = result["matching"]
    require(
        set(matched)
        == {
            "status",
            "reason_code",
            "iterations",
            "calibration_sha256",
            "invested_fraction",
            "residual_probe",
            "residual_probe_sha256",
        }
        and type(matched["iterations"]) is int
        and matched["iterations"] in {0, 64},
        "matching_fields",
    )
    require(
        (
            matched["status"] == "matched"
            and matched["reason_code"] is None
            and type(matched["calibration_sha256"]) is str
            and re.fullmatch(HASH, matched["calibration_sha256"])
            and type(matched["invested_fraction"]) is str
            and len(matched["invested_fraction"]) <= 55
            and Decimal(matched["invested_fraction"]).is_finite()
            and 0 <= Decimal(matched["invested_fraction"]) <= 1
            and digest(encode(matched["invested_fraction"])) == matched["calibration_sha256"]
        )
        or (
            matched["status"] == "comparison_unresolved"
            and matched["calibration_sha256"] is None
            and matched["invested_fraction"] is None
            and matched["reason_code"]
            in {
                "train_input_unavailable",
                "beta_not_bracketed",
                "beta_residual_exceeded",
                "beta_reference_zero_variance",
            }
        ),
        "matching_status",
    )
    probe = matched["residual_probe"]
    if matched["reason_code"] == "beta_residual_exceeded":
        require(
            type(probe) is str
            and len(probe) <= 55
            and Decimal(probe).is_finite()
            and 0 <= Decimal(probe) <= 1
            and matched["iterations"] == 64
            and matched["residual_probe_sha256"] == digest(encode(probe)),
            "matching_probe",
        )
    else:
        require(probe is None and matched["residual_probe_sha256"] is None, "matching_probe")
    cells = result["cells"]
    require(
        [(c["period"], c["cost_per_side_bps"], c["policy"]) for c in cells]
        == [(p, cost, policy) for p, _, _ in PERIODS for cost in COSTS for policy in POLICIES],
        "cell_matrix",
    )
    hashes = {}
    for cell in cells:
        require(
            set(cell)
            == {"period", "cost_per_side_bps", "policy", "status", "trades", "action_sha256"}
            | set(METRICS),
            "cell_fields",
        )
        require(cell["status"] in {"evaluated", "input_unavailable"}, "cell_status")
        facts = next(g for g in result["coverage"] if g["period"] == cell["period"])
        feature_ready = cell["policy"] in {"equal_weight", "beta_matched_basket_cash"} or all(
            q["status"] == "ready" for q in facts["inputs"]
        )
        available = not (facts["missing_marks"] or facts["invalid_marks"]) and feature_ready
        if cell["policy"] == "beta_matched_basket_cash":
            available = available and matched["status"] == "matched"
        require(
            cell["status"] == ("evaluated" if available else "input_unavailable"),
            "availability_binding",
        )
        key = cell["period"], cell["policy"]
        require(
            hashes.setdefault(key, cell["action_sha256"]) == cell["action_sha256"],
            "cost_changes_targets",
        )
        if cell["status"] == "input_unavailable":
            require(
                cell["trades"] is None
                and cell["action_sha256"] is None
                and all(cell[k] is None for k in METRICS),
                "unavailable_metrics",
            )
            continue
        require(
            type(cell["action_sha256"]) is str and re.fullmatch(HASH, cell["action_sha256"]),
            "action_hash",
        )
        require(
            all(
                type(cell[k]) is str and len(cell[k]) <= 180 and Decimal(cell[k]).is_finite()
                for k in METRICS
            ),
            "metric_shape",
        )
        nav, _, fees, turnover = (Decimal(cell[k]) for k in METRICS)
        require(
            nav > 0
            and fees >= 0
            and turnover >= 0
            and type(cell["trades"]) is int
            and cell["trades"] >= 0,
            "metric_domain",
        )
        with localcontext() as ctx:
            ctx.prec, ctx.rounding = 50, ROUND_HALF_EVEN
            require(
                abs(fees - Decimal(cell["cost_per_side_bps"]) * turnover / 10000)
                <= EPS * (1 + fees),
                "fee_identity",
            )
        if cell["policy"] == "beta_matched_basket_cash":
            require(matched["status"] == "matched", "matched_input_unavailable")
    require(
        result["status"]
        == ("complete" if all(c["status"] == "evaluated" for c in cells) else "input_unavailable")
        and result["criterion"] == verdict(cells),
        "result_status",
    )


def safe_result(result: dict) -> dict:
    return dict(
        status=result["status"],
        criterion=result["criterion"],
        cells=len(result["cells"]),
        contract_sha256=result["contract_sha256"],
        result_sha256=digest(encode(result)),
    )


def load_adjusted(market_data_root: Path):
    return data.load_verified_adjusted_etf_snapshot(
        market_data_root / data.SNAPSHOT_RELATIVE_PATH,
        market_data_root=market_data_root,
        repo_root=REPO,
    )


def run_worker(artifact_root, market_data_root, pin, path, deadline):
    output, contract = verify(artifact_root, market_data_root, pin)
    require(
        path == output / "worker-result.json"
        and not path.exists()
        and not path.is_symlink()
        and not (output / "summary.json").exists(),
        "worker_path",
    )
    require(
        json.loads(_read(output / "started.json")) == {"contract_sha256": pin}, "attempt_binding"
    )
    try:
        result = evaluate(load_adjusted(market_data_root), contract, pin, deadline=deadline)
        verify(artifact_root, market_data_root, pin)
    except Exception:
        result = failure(contract, pin, "runtime_or_invariant_failure")
    atomic_new(path, result)


def worker_entry(*args):
    try:
        run_worker(*args)
    except BaseException:
        raise SystemExit(1) from None


def readback(artifact_root, market_data_root, pin, *, result_sha256, deadline):
    """All-read-only exact deterministic replay; no fit, registry or file writes."""
    output, contract = verify(artifact_root, market_data_root, pin)
    require(
        json.loads(_read(output / "started.json")) == {"contract_sha256": pin}, "attempt_binding"
    )
    raw = _read(output / "summary.json")
    require(digest(raw) == result_sha256, "result_hash")
    retained = json.loads(raw)
    validate_result(retained, contract, pin)
    require(retained["status"] != "failed", "failed_attempt_not_replayed")
    require(_read(output / "worker-result.json") == raw, "worker_summary_binding")
    match = retained["matching"]
    restored = BetaMatch(
        None if match["invested_fraction"] is None else Decimal(match["invested_fraction"]),
        match["status"],
        match["reason_code"],
        match["iterations"],
        None if match["residual_probe"] is None else Decimal(match["residual_probe"]),
    )
    rebuilt = evaluate(
        load_adjusted(market_data_root), contract, pin, deadline=deadline, frozen_match=restored
    )
    verify(artifact_root, market_data_root, pin)
    require(encode(rebuilt) == raw, "zero_refit_replay_mismatch")
    return dict(safe_result(retained), replay="exact", refits=0, writes=0)


def recover_registry(artifact_root, market_data_root, pin, *, result_sha256, deadline):
    """Replay an existing terminal result, then reattach only its original outcome.

    Registry append failure does not consume another attempt. Repeating this
    operation uses the same contract/result identity and idempotent registry API.
    """
    replayed = readback(
        artifact_root, market_data_root, pin, result_sha256=result_sha256, deadline=deadline
    )
    require(replayed["status"] in {"complete", "input_unavailable"}, "recovery_status")
    # Recheck the immutable terminal binding at the sole write boundary.
    output, contract = verify(artifact_root, market_data_root, pin)
    raw = _read(output / "summary.json")
    require(
        digest(raw) == result_sha256 and _read(output / "worker-result.json") == raw,
        "recovery_result_changed",
    )
    require(
        json.loads(_read(output / "started.json")) == {"contract_sha256": pin}, "attempt_binding"
    )
    validate_result(json.loads(raw), contract, pin)
    require(time.monotonic() < deadline, "hard_timeout")
    entry = register_campaign_outcome(
        contract_hash=pin,
        outcome_class="non_promoting_completed",
        outcome_reference_sha256=result_sha256,
        artifact_root=artifact_root,
        repo_root=REPO,
    )
    return dict(
        status=replayed["status"],
        criterion=replayed["criterion"],
        cells=replayed["cells"],
        contract_sha256=pin,
        result_sha256=result_sha256,
        recovery="registry_only",
        replay="exact",
        refits=0,
        attempt_artifact_writes=0,
        outcome_record_sha256=entry.record_sha256,
    )
