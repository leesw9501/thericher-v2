"""Fixed CPU-only KIS raw-price rule comparison, supervised/frozen by the parent.

No credentials, provider, broker, model, GPU, acquisition or registry ownership.
Logical CLOSE selection precedes the immutable decision seal; forward numeric
marks follow it. Hashing/CSV decoding is not target-isolated physical byte IO.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.metadata
import io
import json
import math
import os
import platform
import stat
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from pathlib import Path

from thericher_v2.research import three_asset_nav as nav
from thericher_v2.research.artifact_paths import reject_repo_artifact_path
from thericher_v2.research.cross_asset_etf_input import INSTRUMENT_ORDER, CrossAssetSession
from thericher_v2.research.cross_asset_monthly_momentum import (
    PRICE_BASIS,
    THIRD,
    PriceClose,
    build_monthly_momentum,
    plan_monthly_momentum,
)
from thericher_v2.research.cross_asset_monthly_roundtrip import (
    MonthlyBoundary,
    replay_monthly_roundtrips,
)

NAME = "kis-cross-asset-monthly-momentum-development-v1"
REPO = Path(__file__).resolve().parents[3]
POLICIES = ("candidate", "cash", "monthly_balanced", "buyhold")
COSTS = (Decimal("2.5"), Decimal(5), Decimal(10))
SECONDS, TOLERANCE = 120, Decimal("1e-10")
CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN)
IMAGE = "sha256:d6b43213ee3877653e3c1e79c7238fb5caa71241abf238838fa0c3332cf4f039"
RUNTIME = {"python": "3.12.14", "pandas-market-calendars": "5.4.0"}
INPUT_PIN = "sha256:02dcc0007a5aa2804c4b0ce497dfb51e21387122869f1ef90f539d597158e516"
CALENDAR_PIN = "sha256:d2dab6f2ab27a7439ed4be91bacefc68b04908d0b3b7d509e4a2b19925a42721"
INPUT_RELATIVE = (
    "research/kis-cross-asset-d1-input-foundation-v1/input/"
    "cross-asset-d1-input-20261008-v1/input-commitment.json"
)
COLUMNS = ("symbol", "exchange", "session_date", "open", "close", "source_chunk_id")
EXCHANGES = {"SPY": "AMS", "TLT": "NAS", "GLD": "AMS"}
CORE = tuple(
    "src/thericher_v2/" + name
    for name in (
        "research/kis_cross_asset_monthly_momentum.py",
        "research/cross_asset_monthly_momentum.py",
        "research/cross_asset_monthly_roundtrip.py",
        "research/cross_asset_etf_input.py",
        "research/three_asset_nav.py",
        "research/artifact_paths.py",
        "contracts.py",
    )
)


class StudyFault(ValueError):
    """Fixed categorical failures only; no dynamic source body in output."""


def require(condition, code):
    if not condition:
        raise StudyFault(code)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def configuration():
    return dict(
        name=NAME,
        symbols=list(INSTRUMENT_ORDER),
        policies=list(POLICIES),
        months=["2022-09", "2026-09"],
        blocks=[["2022-09", "2023-12", 16], ["2024-01", "2026-09", 33]],
        cells=24,
        costs_bps_side=[str(c) for c in COSTS],
        input_commitment_sha256=INPUT_PIN,
        input_commitment_artifact_relative=INPUT_RELATIVE,
        calendar_sha256=CALENDAR_PIN,
        signal="previous scheduled CLOSE/exact prior-calendar-year cutoff; Feb29 clamp; "
        "latest scheduled anchor<=cutoff; exact row required; positive fixed THIRD sleeves/cash",
        third=str(THIRD),
        decision="all49 monthly actions sealed before forward numeric marks",
        accounting="three_asset_nav Decimal50 HALF_EVEN, actual-notional post-fee NAV; "
        "candidate/cash/monthly_balanced first OPEN->last CLOSE flat; buyhold initial/final only",
        capital="NAV1 once per policy/cost; both blocks are views with previous marked NAV basis; "
        "buyhold retains inventory across boundary, no synthetic boundary liquidation",
        utility="252*(mean daily log return-5*population variance), all scheduled days",
        kill="10bps both blocks positive candidate growth and growth/utility > every control "
        "by >1e-10; no rescue",
        missing="missing required past/mark => study input_unavailable; "
        "no date deletion/substitution/observed-support cohort or parameter selection",
        runtime=dict(RUNTIME),
        image=IMAGE,
        seconds=SECONDS,
        cpu=2,
        memory_bytes=2 * 1024**3,
        network="none",
        actual_fits=0,
        gpu=False,
        holdout_access="none",
        paper_input=False,
        grade="RAW_PRICE_ONLY_SEEN_SOURCE_DEVELOPMENT",
        limitations=[
            "MODP0 opaque",
            "distinct chunk observation times",
            "splits/dividends not applied",
            "PIT/finality/decision-time availability not observed",
            "ideal fractional fills",
            "49 monthly decisions, not independent daily samples",
            "buyhold different cost/gap path",
        ],
    )


@dataclass(frozen=True, slots=True)
class StudyPlan:
    sessions: tuple[CrossAssetSession, ...] = field(repr=False)
    dates: tuple[date, ...]
    boundaries: tuple[MonthlyBoundary, ...]
    block_cut: int

    @property
    def sha256(self):
        return digest(
            encode(
                dict(
                    sessions=[
                        [s.session_date.isoformat(), s.open_at.isoformat(), s.close_at.isoformat()]
                        for s in self.sessions
                    ],
                    dates=[d.isoformat() for d in self.dates],
                    block_cut=self.block_cut,
                )
            )
        )


def build_plan(sessions):
    require(type(sessions) is tuple and len(sessions) > 1, "calendar_scope")
    for session in sessions:
        require(type(session) is CrossAssetSession, "calendar_type")
        session.__post_init__()
    require(
        all(
            a.session_date < b.session_date and a.close_at < b.open_at
            for a, b in zip(sessions, sessions[1:], strict=False)
        ),
        "calendar_order",
    )
    dates = tuple(
        s.session_date for s in sessions if date(2022, 9, 1) <= s.session_date <= date(2026, 9, 30)
    )
    months = tuple((2022 + (8 + i) // 12, (8 + i) % 12 + 1) for i in range(49))
    groups = tuple(tuple(d for d in dates if (d.year, d.month) == month) for month in months)
    require(all(groups) and sum(map(len, groups)) == len(dates), "month_geometry")
    boundaries = tuple(MonthlyBoundary(group[0], group[-1]) for group in groups)
    for boundary in boundaries:
        index = tuple(s.session_date for s in sessions).index(boundary.entry_session_date)
        require(index > 0, "previous_close_missing")
        plan_monthly_momentum(
            sessions,
            entry_session_date=boundary.entry_session_date,
            decision_at=sessions[index - 1].close_at,
        )
    cut = sum(len(group) for group in groups[:16])
    require(0 < cut < len(dates) and dates[cut].year == 2024, "block_geometry")
    return StudyPlan(sessions, dates, boundaries, cut)


def calendar_sessions():
    import pandas_market_calendars as calendars

    schedule = calendars.get_calendar("NYSE").schedule(
        start_date="2007-08-21", end_date="2026-10-07"
    )
    return tuple(
        CrossAssetSession(
            index.date(),
            row.market_open.to_pydatetime().astimezone(UTC),
            row.market_close.to_pydatetime().astimezone(UTC),
        )
        for index, row in schedule.iterrows()
    )


def required_past_dates(plan):
    selected = set()
    indices = {s.session_date: i for i, s in enumerate(plan.sessions)}
    for boundary in plan.boundaries:
        signal = plan_monthly_momentum(
            plan.sessions,
            entry_session_date=boundary.entry_session_date,
            decision_at=plan.sessions[indices[boundary.entry_session_date] - 1].close_at,
        )
        selected.update((signal.anchor_session_date, signal.decision_session_date))
    return selected


@dataclass(frozen=True, slots=True)
class ActionSeal:
    plan: StudyPlan = field(repr=False)
    candidate: tuple[nav.ThreeAssetTarget, ...] = field(repr=False)
    past_input_sha256: str
    vintage_ref: str = field(repr=False)

    def __post_init__(self):
        require(
            type(self.plan) is StudyPlan
            and type(self.candidate) is tuple
            and len(self.candidate) == 49,
            "action_geometry",
        )
        require(type(self.vintage_ref) is str and bool(self.vintage_ref), "action_vintage")
        require(
            type(self.past_input_sha256) is str
            and self.past_input_sha256.startswith("sha256:")
            and len(self.past_input_sha256) == 71,
            "action_input_hash",
        )
        with localcontext(CONTEXT):
            for target in self.candidate:
                require(type(target) is nav.ThreeAssetTarget, "action_target")
                target.__post_init__()
                require(
                    all(w in (Decimal(0), THIRD) for w in target.weights3)
                    and target.cash_weight == 1 - sum(target.weights3, Decimal(0)),
                    "action_target",
                )

    def record(self):
        full, cash = allocation(), allocation((Decimal(0),) * 3)
        return dict(
            plan_sha256=self.plan.sha256,
            past_input_sha256=self.past_input_sha256,
            vintage_ref=self.vintage_ref,
            actions={
                policy: [
                    [
                        boundary.entry_session_date.isoformat(),
                        *map(str, target.weights3),
                        str(target.cash_weight),
                    ]
                    for i, (boundary, target) in enumerate(
                        zip(
                            self.plan.boundaries,
                            self.candidate
                            if policy == "candidate"
                            else (cash if policy == "cash" else full,) * 49,
                            strict=True,
                        )
                    )
                    if policy != "buyhold" or i == 0
                ]
                for policy in POLICIES
            },
        )

    @property
    def sha256(self):
        return digest(encode(self.record()))


def allocation(weights=None):
    with localcontext(CONTEXT):
        weights = (THIRD,) * 3 if weights is None else weights
        return nav.ThreeAssetTarget(weights, 1 - sum(weights, Decimal(0)))


def prepare_actions(rows_by_symbol: Mapping[str, Sequence[PriceClose]], plan, vintage_ref):
    require(build_plan(plan.sessions) == plan, "plan_changed")
    signals = []
    indices = {s.session_date: i for i, s in enumerate(plan.sessions)}
    for boundary in plan.boundaries:
        signals.append(
            build_monthly_momentum(
                rows_by_symbol,
                scheduled_sessions=plan.sessions,
                entry_session_date=boundary.entry_session_date,
                decision_at=plan.sessions[indices[boundary.entry_session_date] - 1].close_at,
                vintage_ref=vintage_ref,
            )
        )
    selected = required_past_dates(plan)
    facts = [
        [symbol, row.session_date.isoformat(), str(row.close)]
        for symbol in INSTRUMENT_ORDER
        for row in sorted(
            (r for r in rows_by_symbol[symbol] if r.session_date in selected),
            key=lambda r: r.session_date,
        )
    ]
    return ActionSeal(plan, tuple(s.target for s in signals), digest(encode(facts)), vintage_ref)


def _metrics(daily, initial, months):
    with localcontext(CONTEXT):
        logs = tuple(day.log_return for day in daily)
        mean = sum(logs, Decimal(0)) / len(logs)
        variance = sum((value - mean) ** 2 for value in logs) / len(logs)
        return dict(
            entering_nav=str(initial),
            nav=str(daily[-1].nav),
            growth=str(daily[-1].nav / initial - 1),
            utility=str(252 * (mean - 5 * variance)),
            fees=str(sum((d.fees for d in daily), Decimal(0))),
            traded_notional=str(sum((d.traded_notional for d in daily), Decimal(0))),
            days=len(daily),
            months=months,
            trace_sha256=digest(
                encode(
                    [
                        [d.date.isoformat(), str(d.nav), str(d.fees), str(d.log_return)]
                        for d in daily
                    ]
                )
            ),
        )


def evaluate_sealed(days, seal, *, deadline=float("inf")):
    require(type(seal) is ActionSeal and len(seal.candidate) == 49, "action_geometry")
    seal.__post_init__()
    require(build_plan(seal.plan.sessions) == seal.plan, "plan_changed")
    original = seal.sha256
    require(tuple(d.date for d in days) == seal.plan.dates, "forward_mark_gap")
    actions = seal.record()["actions"]
    cells = []
    for cost in COSTS:
        for policy in POLICIES:
            require(time.monotonic() < deadline, "compute_stop")
            targets = {
                date.fromisoformat(row[0]): nav.ThreeAssetTarget(
                    tuple(Decimal(w) for w in row[1:4]), Decimal(row[4])
                )
                for row in actions[policy]
            }
            ledger = (
                nav.replay(days, targets, cost)
                if policy == "buyhold"
                else replay_monthly_roundtrips(
                    days,
                    targets,
                    scheduled_dates=seal.plan.dates,
                    month_boundaries=seal.plan.boundaries,
                    cost_bps=cost,
                )
            )
            cut = seal.plan.block_cut
            for block, subset, initial, months in (
                (0, ledger.daily[:cut], Decimal(1), 16),
                (1, ledger.daily[cut:], ledger.daily[cut - 1].nav, 33),
            ):
                cells.append(
                    dict(
                        block=block,
                        policy=policy,
                        cost_bps=str(cost),
                        status="complete",
                        metrics=_metrics(subset, initial, months),
                    )
                )
    require(seal.sha256 == original, "action_seal_changed")
    return tuple(cells)


def criterion(cells):
    expected = {(b, p, str(c)) for b in (0, 1) for p in POLICIES for c in COSTS}
    require(
        len(cells) == 24
        and {(c["block"], c["policy"], c["cost_bps"]) for c in cells} == expected
        and all(c["status"] == "complete" for c in cells),
        "cell_matrix",
    )
    with localcontext(CONTEXT):
        require(
            all(
                type(c["metrics"][k]) is str and Decimal(c["metrics"][k]).is_finite()
                for c in cells
                for k in ("growth", "utility")
            ),
            "cell_metrics",
        )
        for block in (0, 1):
            group = {
                c["policy"]: c["metrics"]
                for c in cells
                if c["block"] == block and c["cost_bps"] == "10"
            }
            own = group["candidate"]
            if Decimal(own["growth"]) <= 0 or any(
                Decimal(own[k]) - Decimal(other[k]) <= TOLERANCE
                for policy, other in group.items()
                if policy != "candidate"
                for k in ("growth", "utility")
            ):
                return "rejected"
    return "development_survivor"


def _read(path):
    path = Path(path).absolute()
    for item in (*reversed(path.parents), path):
        info = item.lstat()
        require(
            not stat.S_ISLNK(info.st_mode)
            and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
            "artifact_link",
        )
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "artifact_not_regular")
    return path.read_bytes()


def _json(path, pin=None, *, canonical=False):
    raw = _read(path)
    require(pin is None or digest(raw) == pin, "artifact_hash")
    value = json.loads(raw)
    require(not canonical or raw == encode(value), "artifact_encoding")
    return value


def _relative(root, value):
    require(
        type(value) is str
        and bool(value)
        and "\\" not in value
        and ":" not in value
        and not Path(value).anchor
        and ".." not in Path(value).parts,
        "input_path",
    )
    return Path(root) / value


def atomic_new(path, value):
    with Path(path).open("xb") as stream:
        stream.write(encode(value))
        stream.flush()
        os.fsync(stream.fileno())


def runtime_identity():
    return {
        "python": platform.python_version(),
        "pandas-market-calendars": importlib.metadata.version("pandas-market-calendars"),
    }


def read_contract(precommit, pin, artifact_root):
    contract = _json(precommit, pin)
    require(contract["name"] == NAME and contract["config"] == configuration(), "contract_config")
    require(contract["runtime"] == runtime_identity() == RUNTIME, "runtime_identity")
    require(set(contract["code_sha256"]) >= set(CORE), "code_pins")
    for relative, expected in contract["code_sha256"].items():
        require(digest(_read(_relative(REPO, relative))) == expected, "code_changed")
    require(contract["input_commitment_sha256"] == INPUT_PIN, "input_commitment_binding")
    commitment = _json(_relative(artifact_root, INPUT_RELATIVE), INPUT_PIN)
    require(
        commitment["calendar_sha256"] == CALENDAR_PIN
        and commitment["kind"] == "kis-cross-asset-d1-price-only-input-v1"
        and commitment["no_date_fill"] is True,
        "input_identity",
    )
    for relative, expected in commitment["source_pins"].items():
        require(contract["code_sha256"].get(relative) == expected, "producer_code_pins")
    return contract, commitment


@dataclass(frozen=True, slots=True)
class SourceInputs:
    files: tuple[tuple[str, bytes], ...] = field(repr=False)
    commitment: dict = field(repr=False)
    plan: StudyPlan = field(repr=False)


def load_committed_source(commitment, artifact_root, market_root, *, deadline=float("inf")):
    bindings = commitment["source_bindings"]
    require(
        len(bindings) == 136 and len({(b["root"], b["path"]) for b in bindings}) == 136,
        "source_bindings",
    )
    calendar = None
    for item in bindings:
        require(time.monotonic() < deadline, "compute_stop")
        require(item["root"] in {"MARKET", "ARTIFACT"}, "source_root")
        root = market_root if item["root"] == "MARKET" else artifact_root
        raw = _read(_relative(root, item["path"]))
        require(digest(raw) == item["sha256"], "source_changed")
        if item["sha256"] == CALENDAR_PIN:
            require(calendar is None, "calendar_binding")
            calendar = json.loads(raw)
    sessions = calendar_sessions()
    require(
        calendar is not None
        and calendar["kind"] == "caller_nyse_session_dates_v1"
        and tuple(calendar["session_dates"]) == tuple(s.session_date.isoformat() for s in sessions),
        "calendar_binding",
    )
    require(calendar_matches(calendar, sessions), "calendar_clock_binding")
    files = commitment["price_only_files"]
    require(set(files) == set(INSTRUMENT_ORDER), "output_symbols")
    contents = []
    parents = set()
    for symbol in INSTRUMENT_ORDER:
        item = files[symbol]
        path = _relative(market_root, item["market_relative_path"])
        raw = _read(path)
        require(
            digest(raw) == item["sha256"]
            and len(raw) == item["size_bytes"]
            and item["row_count"] == 1288,
            "output_binding",
        )
        parents.add(path.parent)
        contents.append((symbol, raw))
    require(
        len(parents) == 1 and digest(_read(next(iter(parents)) / "manifest.json")) == INPUT_PIN,
        "market_manifest_binding",
    )
    return SourceInputs(tuple(contents), commitment, build_plan(sessions))


def calendar_matches(calendar, sessions):
    """Compare absolute instants: retained *_utc fields actually use +09:00."""
    rows = calendar["scheduled_sessions"]
    return (
        calendar["calendar_name"] == "NYSE"
        and calendar["library_version"] == "5.4.0"
        and len(rows) == len(sessions)
        and all(
            row["date"] == session.session_date.isoformat()
            and datetime.fromisoformat(row["open_at_utc"]).astimezone(UTC) == session.open_at
            and datetime.fromisoformat(row["close_at_utc"]).astimezone(UTC) == session.close_at
            for row, session in zip(rows, sessions, strict=True)
        )
    )


def _selected(source, dates, columns):
    selected = {}
    for symbol, raw in source.files:
        values = {}
        reader = csv.DictReader(io.StringIO(gzip.decompress(raw).decode("utf-8")))
        require(tuple(reader.fieldnames or ()) == COLUMNS, "price_columns")
        for row in reader:
            text = row["session_date"]
            if text not in dates:
                continue
            require(
                text not in values
                and row["symbol"] == symbol
                and row["exchange"] == EXCHANGES[symbol],
                "required_row_binding",
            )
            values[text] = {key: Decimal(row[key]) for key in columns}
            require(all(v.is_finite() and v > 0 for v in values[text].values()), "required_price")
        require(set(values) == dates, "required_date_gap")
        selected[symbol] = values
    return selected


def load_past_closes(source):
    wanted = {d.isoformat() for d in required_past_dates(source.plan)}
    rows = _selected(source, wanted, ("close",))
    return {
        symbol: tuple(
            PriceClose(symbol, date.fromisoformat(day), INPUT_PIN, values["close"], PRICE_BASIS)
            for day, values in sorted(rows[symbol].items())
        )
        for symbol in INSTRUMENT_ORDER
    }


def load_forward_marks(source):
    rows = _selected(source, {d.isoformat() for d in source.plan.dates}, ("open", "close"))
    return tuple(
        nav.ThreeAssetDay(
            day,
            tuple(rows[s][day.isoformat()]["open"] for s in INSTRUMENT_ORDER),
            tuple(rows[s][day.isoformat()]["close"] for s in INSTRUMENT_ORDER),
        )
        for day in source.plan.dates
    )


def _output(root):
    output = Path(root) / "research" / NAME
    reject_repo_artifact_path(output, REPO)
    require(output.is_dir() and not output.is_symlink(), "output_directory")
    _read(output / "precommit.json")
    return output


def safe_result(result):
    return {
        key: result[key]
        for key in (
            "status",
            "criterion",
            "contract_sha256",
            "phase",
            "reason",
            "actual_fits",
            "elapsed_seconds",
            "actions_sha256",
        )
    } | {
        "cells": len(result["cells"]),
        "result_sha256": digest(encode(result)),
        "gpu": False,
        "holdout_access": "none",
        "paper_input": False,
    }


def run_campaign(precommit, pin, artifact_root, market_root):
    """Parent owns custody and 120s containment; child never registers an outcome."""
    start = time.monotonic()
    deadline = start + SECONDS
    _contract, commitment = read_contract(precommit, pin, artifact_root)
    output = _output(artifact_root)
    require(digest(_read(output / "precommit.json")) == pin, "output_contract_binding")
    require(
        not any(
            (output / name).exists()
            for name in ("started.json", "actions.json", "worker-result.json")
        ),
        "attempt_already_exists",
    )
    atomic_new(
        output / "started.json", {"contract_sha256": pin, "input_commitment_sha256": INPUT_PIN}
    )
    phase, cells, action_pin = "source_input", (), None
    result = dict(
        status="failed",
        criterion="runtime_failure",
        contract_sha256=pin,
        phase=phase,
        reason="worker_failed",
        actual_fits=0,
        elapsed_seconds=0,
        cells=[],
        actions_sha256=None,
    )
    try:
        source = load_committed_source(commitment, artifact_root, market_root, deadline=deadline)
        phase = "decision_seal"
        seal = prepare_actions(load_past_closes(source), source.plan, INPUT_PIN)
        require(time.monotonic() < deadline, "compute_stop")
        atomic_new(output / "actions.json", seal.record())
        action_pin = seal.sha256
        phase = "forward_input"
        days = load_forward_marks(source)
        phase = "evaluate"
        cells = evaluate_sealed(days, seal, deadline=deadline)
        require(time.monotonic() < deadline, "compute_stop")
        phase = "validate"
        verdict = criterion(cells)
        require(
            load_committed_source(commitment, artifact_root, market_root, deadline=deadline).files
            == source.files,
            "source_changed",
        )
        require(time.monotonic() < deadline, "compute_stop")
        result.update(status="complete", criterion=verdict, reason=None)
    except Exception as error:
        allowed = {
            "compute_stop",
            "required_date_gap",
            "source_changed",
            "output_binding",
            "calendar_binding",
            "required_price",
            "forward_mark_gap",
            "action_seal_changed",
        }
        code = (
            str(error) if type(error) is StudyFault and str(error) in allowed else "worker_failed"
        )
        result["reason"] = code
        if code in {"required_date_gap", "required_price", "forward_mark_gap"}:
            result.update(status="input_unavailable", criterion="input_unavailable")
        if (output / "actions.json").exists():
            action_pin = digest(_read(output / "actions.json"))
        cells = ()
    result.update(
        phase=phase,
        elapsed_seconds=time.monotonic() - start,
        cells=list(cells),
        actions_sha256=action_pin,
    )
    atomic_new(output / "worker-result.json", result)
    return safe_result(result)


def verify_result(precommit, pin, artifact_root, market_root, result_pin):
    start = time.monotonic()
    deadline = start + SECONDS
    _contract, commitment = read_contract(precommit, pin, artifact_root)
    output = _output(artifact_root)
    require(digest(_read(output / "precommit.json")) == pin, "output_contract_binding")
    result = _json(output / "worker-result.json", result_pin, canonical=True)
    require(
        set(result)
        == {
            "status",
            "criterion",
            "contract_sha256",
            "phase",
            "reason",
            "actual_fits",
            "elapsed_seconds",
            "cells",
            "actions_sha256",
        }
        and result["contract_sha256"] == pin
        and type(result["actual_fits"]) is int
        and result["actual_fits"] == 0
        and result["phase"]
        in {"source_input", "decision_seal", "forward_input", "evaluate", "validate"}
        and type(result["elapsed_seconds"]) in (int, float)
        and math.isfinite(result["elapsed_seconds"])
        and result["elapsed_seconds"] >= 0,
        "result_binding",
    )
    require(
        _json(output / "started.json", canonical=True)
        == {"contract_sha256": pin, "input_commitment_sha256": INPUT_PIN},
        "start_binding",
    )
    if result["status"] in {"failed", "input_unavailable"}:
        require(
            result["cells"] == []
            and result["reason"] is not None
            and result["criterion"]
            == ("runtime_failure" if result["status"] == "failed" else "input_unavailable"),
            "failure_binding",
        )
        action = output / "actions.json"
        require(
            (not action.exists())
            if result["actions_sha256"] is None
            else digest(_read(action)) == result["actions_sha256"],
            "failure_action_binding",
        )
        return safe_result(result) | {"replay": "failure_binding_only", "writes": 0, "searches": 0}
    require(
        result["status"] == "complete"
        and result["phase"] == "validate"
        and result["reason"] is None,
        "result_status",
    )
    source = load_committed_source(commitment, artifact_root, market_root, deadline=deadline)
    seal = prepare_actions(load_past_closes(source), source.plan, INPUT_PIN)
    require(
        _read(output / "actions.json") == encode(seal.record())
        and seal.sha256 == result["actions_sha256"],
        "actions_replay",
    )
    cells = evaluate_sealed(load_forward_marks(source), seal, deadline=deadline)
    require(
        encode(list(cells)) == encode(result["cells"]) and criterion(cells) == result["criterion"],
        "numeric_replay",
    )
    require(
        load_committed_source(commitment, artifact_root, market_root, deadline=deadline).files
        == source.files,
        "source_changed",
    )
    require(time.monotonic() < deadline, "compute_stop")
    return safe_result(result) | {"replay": "exact", "writes": 0, "searches": 0}


def synthetic_smoke():
    plan = build_plan(calendar_sessions())
    selected = required_past_dates(plan)
    rows = {
        symbol: tuple(
            PriceClose(symbol, day, "synthetic", Decimal(100 + day.year - 2007))
            for day in sorted(selected)
        )
        for symbol in INSTRUMENT_ORDER
    }
    seal = prepare_actions(rows, plan, "synthetic")
    days = tuple(
        nav.ThreeAssetDay(day, (Decimal(100),) * 3, (Decimal(100),) * 3) for day in plan.dates
    )
    cells = evaluate_sealed(days, seal)
    require(len(cells) == 24 and criterion(cells) == "rejected", "smoke_matrix")
    return dict(
        status="smoke_passed",
        months=49,
        blocks=[16, 33],
        cells=24,
        actual_fits=0,
        actual_market_reads=0,
        gpu=False,
        paper_input=False,
    )


def main(argv=None):
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    for name in ("smoke", "run", "verify"):
        mode.add_argument("--" + name, action="store_true")
    parser.add_argument("--precommit", type=Path)
    parser.add_argument("--contract-sha256")
    parser.add_argument("--result-sha256")
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--market-root", type=Path)
    args = parser.parse_args(argv)
    bound = not args.smoke
    if any(
        bool(v) != bound
        for v in (args.precommit, args.contract_sha256, args.artifact_root, args.market_root)
    ) or bool(args.result_sha256) != bool(args.verify):
        parser.error(
            "run/verify require exact roots/precommit/contract; verify requires result pin"
        )
    try:
        value = (
            synthetic_smoke()
            if args.smoke
            else verify_result(
                args.precommit,
                args.contract_sha256,
                args.artifact_root,
                args.market_root,
                args.result_sha256,
            )
            if args.verify
            else run_campaign(
                args.precommit, args.contract_sha256, args.artifact_root, args.market_root
            )
        )
        print(json.dumps(value, sort_keys=True, allow_nan=False))
        return 0 if value["status"] in {"complete", "smoke_passed"} else 2
    except Exception:
        print(json.dumps({"status": "failed", "reason": "study_unavailable", "actual_fits": 0}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
