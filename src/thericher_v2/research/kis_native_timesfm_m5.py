"""One fixed KIS-native zero-shot development comparison; no broker consumer.

The parent freezes inputs/code and supervises the single 300-second worker.
This module never acquires data or weights. Readback replays sealed predictions,
not inference. Source-file decoding is not a claim of target-isolated physical IO.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import stat
import struct
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from datetime import time as clock_time
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from pathlib import Path
from zoneinfo import ZoneInfo

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research.clock_portfolio_nav import ClockOpportunity, ClockTarget, replay
from thericher_v2.research.paired_completed_context import build_paired_completed_context

NAME = "kis-native-timesfm-m5-24-development-v1"
REPO = Path(__file__).resolve().parents[3]
SYMBOLS = ("QQQ", "SPY")
CLOCKS = ((11, 30), (13, 0), (14, 30))
POLICIES = ("timesfm", "cash", "unconditional_long", "rolling_mean", "last_return")
COSTS = (Decimal("2.5"), Decimal(5), Decimal(10))
CONTEXT, HORIZON, SECONDS = 24, 8, 300
THRESHOLD, TOLERANCE = Decimal(20), Decimal("1e-10")
MINUTE, EASTERN = timedelta(minutes=1), ZoneInfo("America/New_York")
DECIMAL_CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN)
REVISION = "1d952420fba87f3c6dee4f240de0f1a0fbc790e3"
MODEL_PINS = {
    "config.json": "cd3315b760d5cc7e278d7afdf41b897031ced888fc6c115bd9b3ac0ea2c47408",
    "model.safetensors": "2f776efe6245e42b24bc4153ffdf61810140210e4bd3b01fb21f7aa779ab6ce8",
}
IMAGE = "sha256:d6b43213ee3877653e3c1e79c7238fb5caa71241abf238838fa0c3332cf4f039"
RUNTIME = {
    "python": "3.12.14", "torch": "2.7.0+cu128", "timesfm": "2.0.2",
    "numpy": "2.5.1", "pandas-market-calendars": "5.4.0",
    "safetensors": "0.8.0", "huggingface-hub": "0.36.2",
}
INPUT_PIN = "sha256:5a717d52d23f9a5af9a4e4b240e8cebaa631734033fcd9c88a41e847570d33d9"


class StudyFault(ValueError):
    """Only fixed categorical reason codes, never source values."""


def require(condition, code):
    if not condition:
        raise StudyFault(code)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def configuration():
    return dict(
        name=NAME, symbols=list(SYMBOLS), clocks_eastern=[list(c) for c in CLOCKS],
        context=CONTEXT, horizon=HORIZON, policies=list(POLICIES),
        costs_bps_side=[str(c) for c in COSTS], blocks=[12, 13], cells=30,
        input="float32 10000*ln(M5 OPEN/last past M5 OPEN), exact120 past M1",
        forecast="point[1]=D+5; point[7]=D+35; raw marginal-median point difference SCORE; "
        "not conditional expectation or joint-return median; strict point[7]-point[1]>20 log-bps",
        controls="mean23 past OPEN log returns*6, last OPEN log return*6; strict>20; "
        "unconditional long bypasses filter; cash always flat",
        accounting="clock_portfolio_nav; QQQ/SPY <=.5 each; shared post-entry-fee NAV; "
        "quantity ROUND_DOWN1e-40; actual-notional fees; local_paper analytical OPEN fills",
        capital="one continuous25-session NAV1 per policy/cost; second block enters at first "
        "final NAV; block growth relative to entering NAV; flat after every slot",
        utility="252*(mean daily log return-5*population variance); Decimal50 HALF_EVEN",
        kill="10bps: positive TimesFM growth/trades; growth AND utility exceed every "
        "control in BOTH blocks by >1e-10; no rescue",
        missing="required past or forward endpoint gap => entire affected block unavailable; "
        "no date deletion, whole-session eligibility mask, imputation or renormalization",
        model_id="google/timesfm-2.5-200m-pytorch", revision=REVISION, model_pins=dict(MODEL_PINS),
        runtime=dict(RUNTIME), image=IMAGE, seconds=SECONDS, cpu=2, memory_bytes=6 * 1024**3,
        network="none", actual_fits=0, holdout_access="none", paper_input=False,
        grade="POST_CHECKPOINT_SEEN_DATA_DEVELOPMENT",
        limitations=["corpus/instrument scope not_disclosed", "25 seen session clusters",
                     "revised raw KIS values", "ex-post coverage", "historical availability "
                     "and provider finality unobserved", "five-minute latency assumed",
                     "fractional endpoint fills not broker parity"],
    )


@dataclass(frozen=True, slots=True)
class Slot:
    session_date: date
    decision_at: datetime
    session: SessionWindow

    @property
    def entry_at(self):
        return self.decision_at + 5 * MINUTE

    @property
    def exit_at(self):
        return self.decision_at + 35 * MINUTE


def build_plan(dates: Sequence[date], sessions: Sequence[SessionWindow]) -> tuple[Slot, ...]:
    require(len(dates) == len(sessions) == 25 and all(type(d) is date for d in dates)
            and all(a < b for a, b in zip(dates, dates[1:], strict=False)), "scheduled_dates")
    slots = []
    for day, session in zip(dates, sessions, strict=True):
        require(isinstance(session, SessionWindow)
                and session.open_ts == datetime.combine(day, clock_time(9, 30), EASTERN)
                .astimezone(UTC)
                and session.close_ts == datetime.combine(day, clock_time(16), EASTERN)
                .astimezone(UTC), "regular_session_geometry")
        for hour, minute in CLOCKS:
            at = datetime.combine(day, clock_time(hour, minute), EASTERN).astimezone(UTC)
            slots.append(Slot(day, at, session))
    return tuple(slots)


def _validate_plan(plan):
    require(len(plan) == 75 and all(type(s) is Slot for s in plan), "slot_plan")
    dates = tuple(s.session_date for s in plan[::3])
    require(tuple(plan) == build_plan(dates, tuple(s.session for s in plan[::3])), "slot_plan")


def _block(index):
    return 0 if index < 36 else 1


@dataclass(frozen=True, slots=True)
class PreparedInputs:
    plan: tuple[Slot, ...]
    contexts: tuple[tuple[float, ...] | None, ...] = field(repr=False)
    controls: tuple[tuple[Decimal, Decimal] | None, ...] = field(repr=False)
    unavailable_blocks: tuple[int, ...]

    def __post_init__(self):
        _validate_plan(self.plan)
        require(type(self.contexts) is tuple and type(self.controls) is tuple
                and len(self.contexts) == len(self.controls) == 150, "prepared_geometry")
        for context, control in zip(self.contexts, self.controls, strict=True):
            require((context is None and control is None) or (
                type(context) is tuple and len(context) == CONTEXT
                and all(type(v) is float and math.isfinite(v) for v in context)
                and type(control) is tuple and len(control) == 2
                and all(type(v) is Decimal and v.is_finite() for v in control)),
                "prepared_geometry")
        missing = tuple(sorted({_block(i // 2) for i, c in enumerate(self.contexts) if c is None}))
        require(self.unavailable_blocks == missing and all(
            (self.contexts[i] is None) == (self.contexts[i + 1] is None)
            for i in range(0, 150, 2)), "prepared_geometry")

    @property
    def ready_rows(self):
        # Later input failures invalidate evaluation, never an earlier decision.
        return tuple(i for i, context in enumerate(self.contexts) if context is not None)

    @property
    def input_sha256(self):
        return digest(encode(dict(
            slots=[s.decision_at.isoformat() for s in self.plan], contexts=self.contexts,
            controls=[None if c is None else [str(v) for v in c] for c in self.controls],
            unavailable_blocks=self.unavailable_blocks,
        )))


def prepare_inputs(bars_by_symbol: Mapping[str, Sequence[Bar]], plan, *,
                   deadline=float("inf")) -> PreparedInputs:
    _validate_plan(plan)
    require(set(bars_by_symbol) == set(SYMBOLS), "input_symbols")
    contexts, controls, unavailable = [], [], set()
    for index, slot in enumerate(plan):
        require(time.monotonic() < deadline, "compute_stop")
        try:
            paired = build_paired_completed_context(
                bars_by_symbol["QQQ"], bars_by_symbol["SPY"], own_symbol="QQQ",
                peer_symbol="SPY", session=slot.session, observed_at=slot.decision_at,
                timeframe=Timeframe.M5, context_bars=CONTEXT,
            )
            values = []
            with localcontext(DECIMAL_CONTEXT):
                for bars in (paired.own_bars, paired.peer_bars):
                    opens = tuple(b.open for b in bars)
                    context = tuple(struct.unpack("f", struct.pack("f", float(
                        10000 * (v / opens[-1]).ln())))[0] for v in opens)
                    logs = tuple(10000 * (b / a).ln()
                                 for a, b in zip(opens, opens[1:], strict=False))
                    require(all(math.isfinite(v) for v in context), "input_nonfinite")
                    values.append((context, (sum(logs) / 23 * 6, logs[-1] * 6)))
            for context, control in values:
                contexts.append(context)
                controls.append(control)
        except (ValueError, ArithmeticError, OverflowError):
            contexts.extend((None, None))
            controls.extend((None, None))
            unavailable.add(_block(index))
    return PreparedInputs(tuple(plan), tuple(contexts), tuple(controls), tuple(sorted(unavailable)))


@dataclass(frozen=True, slots=True)
class ActionSeal:
    prepared: PreparedInputs = field(repr=False)
    predictions: tuple[tuple[float, ...] | None, ...] = field(repr=False)
    targets: tuple[tuple[tuple[Decimal, Decimal] | None, ...], ...] = field(repr=False)

    def record(self):
        return dict(
            input_sha256=self.prepared.input_sha256, predictions=self.predictions,
            targets=[[[str(w) for w in target] if target is not None else None
                      for target in policy] for policy in self.targets],
        )

    @property
    def sha256(self):
        return digest(encode(self.record()))


def seal_decisions(prepared: PreparedInputs, points) -> ActionSeal:
    rows = points.tolist() if hasattr(points, "tolist") else points
    require(isinstance(rows, Sequence) and len(rows) == len(prepared.ready_rows),
            "forecast_shape")
    expanded = [None] * 150
    for index, values in zip(prepared.ready_rows, rows, strict=True):
        require(isinstance(values, Sequence) and len(values) == HORIZON
                and all(type(v) in (int, float) and math.isfinite(v) for v in values),
                "forecast_values")
        expanded[index] = tuple(float(v) for v in values)
    targets = [[] for _ in POLICIES]
    with localcontext(DECIMAL_CONTEXT):
        for index, _slot in enumerate(prepared.plan):
            if prepared.contexts[2 * index] is None:
                for target in targets:
                    target.append(None)
                continue
            pair = []
            for row_index in (2 * index, 2 * index + 1):
                point, control = expanded[row_index], prepared.controls[row_index]
                require(point is not None and control is not None, "prepared_geometry")
                signals = (Decimal.from_float(point[7]) - Decimal.from_float(point[1]),
                           control[0], control[1])
                selected = tuple(Decimal(".5") if v > THRESHOLD else Decimal(0)
                                 for v in signals)
                pair.append((selected[0], Decimal(0), Decimal(".5"), selected[1], selected[2]))
            for policy_index, target in enumerate(targets):
                target.append((pair[0][policy_index], pair[1][policy_index]))
    return ActionSeal(prepared, tuple(expanded), tuple(tuple(t) for t in targets))


def _marks(bars_by_symbol, slots):
    required = {at for slot in slots for at in (slot.entry_at, slot.exit_at)}
    prices = {}
    for symbol in SYMBOLS:
        selected = [bar for bar in bars_by_symbol[symbol] if bar.start_ts in required]
        require(len(selected) == len(required), "forward_mark_unavailable")
        require(len({b.start_ts for b in selected}) == len(required), "forward_mark_unavailable")
        for bar in selected:
            require(type(bar) is Bar and bar.symbol == symbol and bar.market == "US"
                    and bar.timeframe is Timeframe.M1 and bar.complete is True
                    and type(bar.open) is Decimal and bar.open.is_finite() and bar.open > 0,
                    "forward_mark_unavailable")
            prices[symbol, bar.start_ts] = bar.open
    return tuple(ClockOpportunity(
        s.session_date, s.entry_at, s.exit_at,
        tuple(prices[symbol, s.entry_at] for symbol in SYMBOLS),
        tuple(prices[symbol, s.exit_at] for symbol in SYMBOLS),
    ) for s in slots)


def _metrics(ledger, initial_cash):
    with localcontext(DECIMAL_CONTEXT):
        logs = ledger.log_returns
        mean = sum(logs) / len(logs)
        variance = sum((value - mean) ** 2 for value in logs) / len(logs)
        return dict(nav=str(ledger.final_nav), entering_nav=str(initial_cash),
                    growth=str(ledger.final_nav / initial_cash - 1),
                    utility=str(252 * (mean - 5 * variance)),
                    fees=str(ledger.total_fees), traded_notional=str(ledger.total_traded_notional),
                    trades=sum(len(s.fills) for s in ledger.slots), sessions=len(logs))


def evaluate_sealed(bars_by_symbol, seal: ActionSeal):
    """Never called until every policy action has been sealed; no forecast calls."""
    _validate_plan(seal.prepared.plan)
    require(set(bars_by_symbol) == set(SYMBOLS), "input_symbols")
    original = seal.sha256
    rebuilt = seal_decisions(seal.prepared,
                             [seal.predictions[i] for i in seal.prepared.ready_rows])
    require(rebuilt.sha256 == original, "action_seal_changed")
    cells, ending_cash = [], {}
    for block, (start, end) in enumerate(((0, 36), (36, 75))):
        slots = seal.prepared.plan[start:end]
        reason, opportunities = None, None
        if block == 1 and len(ending_cash) != 15:
            reason = "prior_block_unavailable"
        elif block in seal.prepared.unavailable_blocks:
            reason = "past_input_unavailable"
        else:
            try:
                opportunities = _marks(bars_by_symbol, slots)
            except StudyFault:
                reason = "forward_mark_unavailable"
        dates = tuple(s.session_date for s in slots[::3])
        for cost in COSTS:
            for policy_index, policy in enumerate(POLICIES):
                cell = dict(block=block, policy=policy, cost_bps=str(cost),
                            status="input_unavailable" if reason else "complete", reason=reason)
                if reason is None:
                    targets = {slot.entry_at: ClockTarget(target) for slot, target in zip(
                        slots, seal.targets[policy_index][start:end], strict=True)}
                    initial = ending_cash[cost, policy] if block else Decimal(1)
                    ledger = replay(opportunities, targets, cost,
                                    session_dates=dates, initial_cash=initial)
                    cell["metrics"] = _metrics(ledger, initial)
                    ending_cash[cost, policy] = ledger.final_nav
                cells.append(cell)
    require(seal.sha256 == original, "action_seal_changed")
    return tuple(cells)


def criterion(cells):
    expected = {(b, p, str(c)) for b in (0, 1) for c in COSTS for p in POLICIES}
    require(len(cells) == 30 and {(c["block"], c["policy"], c["cost_bps"])
                                for c in cells} == expected, "cell_matrix")
    require(all(c["status"] in {"complete", "input_unavailable"} for c in cells), "cell_status")
    if any(c["status"] != "complete" for c in cells):
        return "input_unavailable"
    with localcontext(DECIMAL_CONTEXT):
        for block in (0, 1):
            group = {c["policy"]: c["metrics"] for c in cells
                     if c["block"] == block and c["cost_bps"] == "10"}
            require(all(type(m["trades"]) is int and m["trades"] >= 0
                        and all(isinstance(m[key], str) and Decimal(m[key]).is_finite()
                                for key in ("growth", "utility")) for m in group.values()),
                    "cell_metrics")
            own = group["timesfm"]
            if Decimal(own["growth"]) <= TOLERANCE or own["trades"] == 0:
                return "rejected"
            if any(Decimal(own[key]) - Decimal(other[key]) <= TOLERANCE
                   for policy, other in group.items() if policy != "timesfm"
                   for key in ("growth", "utility")):
                return "rejected"
    return "development_survivor"


def _read(path):
    path = Path(path).absolute()
    for item in (*reversed(path.parents), path):
        info = item.lstat()
        require(not stat.S_ISLNK(info.st_mode)
                and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                "artifact_link")
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "artifact_not_regular")
    return path.read_bytes()


def _read_json(path, pin=None, *, canonical=False):
    raw = _read(path)
    require(pin is None or digest(raw) == pin, "artifact_hash")
    value = json.loads(raw)
    require(not canonical or raw == encode(value), "artifact_encoding")
    return value


def atomic_new(path, value):
    with Path(path).open("xb") as stream:
        stream.write(encode(value))
        stream.flush()
        os.fsync(stream.fileno())


def runtime_identity():
    return {"python": platform.python_version(),
            **{name: importlib.metadata.version(name) for name in RUNTIME if name != "python"}}


def _relative(root, value):
    require(isinstance(value, str) and value and "\\" not in value and ":" not in value
            and not Path(value).is_absolute() and ".." not in Path(value).parts,
            "input_path")
    path = Path(root) / value
    require(path.resolve().is_relative_to(Path(root).resolve()), "input_path")
    return path


def _table(table):
    columns, rows = table["columns"], table["rows"]
    require(isinstance(columns, list) and columns and len(columns) == len(set(columns))
            and all(isinstance(key, str) for key in columns)
            and isinstance(rows, list) and all(isinstance(row, list) and len(row) == len(columns)
                                               for row in rows), "commitment_table")
    return tuple(dict(zip(columns, row, strict=True)) for row in rows)


def commitment_plan(commitment):
    from thericher_v2.data.us_equity_session import us_equity_2026_session

    rows = _table(commitment["sessions"])
    dates = tuple(date.fromisoformat(row["session_date"]) for row in rows)
    expected = tuple(day for i in range(36)
                     if (session := us_equity_2026_session(day := date(2026, 8, 28)
                                                           + timedelta(days=i))) is not None
                     and session.kind == "regular")
    require(dates == expected, "cohort_scope")
    windows = []
    for row, day in zip(rows, dates, strict=True):
        session = us_equity_2026_session(day)
        require(row["open_utc"] == session.window.open_ts.isoformat().replace("+00:00", "Z")
                and row["close_utc"] == session.window.close_ts.isoformat().replace("+00:00", "Z")
                and row["expected_regular_m1_count"] == 390, "calendar_session")
        windows.append(session.window)
    return build_plan(dates, tuple(windows))


def read_contract(precommit, pin, market_root):
    contract = _read_json(precommit, pin)
    require(contract["name"] == NAME and contract["config"] == configuration(), "contract_config")
    require(contract["runtime"] == runtime_identity() == RUNTIME, "runtime_identity")
    require(set(contract["code_sha256"]) >= {
        "src/thericher_v2/research/kis_native_timesfm_m5.py",
        "src/thericher_v2/research/timesfm_local.py",
        "src/thericher_v2/research/paired_completed_context.py",
        "src/thericher_v2/research/clock_portfolio_nav.py",
    }, "code_pins")
    for relative, expected in contract["code_sha256"].items():
        require(digest(_read(_relative(REPO, relative))) == expected, "code_changed")
    require(contract["input_commitment_sha256"] == INPUT_PIN, "input_commitment_binding")
    commitment = _read_json(Path(precommit).parent / "input-commitment.json", INPUT_PIN)
    for relative, expected in commitment["loader_source_pins"].items():
        require(contract["code_sha256"].get(relative) == expected, "loader_code_pins")
    plan = commitment_plan(commitment)
    return contract, commitment, plan


def load_committed_bars(commitment, market_root):
    """One named pinned KIS catalog per source; duplicate starts are never overwritten."""
    from thericher_v2.data.kis_paper_intraday import (
        load_verified_kis_paper_private_intraday_catalog,
    )

    plan = commitment_plan(commitment)
    dates = {s.session_date for s in plan}
    sources = _table(commitment["sources"])
    require(len(sources) == 50, "source_partition")
    keys = {(date.fromisoformat(s["session_date"]), s["symbol"]) for s in sources}
    require(keys == {(day, symbol) for day in dates for symbol in SYMBOLS}, "source_partition")
    snapshots = _table(commitment["snapshots"])
    require(len(snapshots) == 51 and {s["source_ordinal"] for s in snapshots} == set(range(50)),
            "source_snapshots")
    for snapshot in snapshots:
        for path_key, hash_key in (("manifest_path_market_relative", "manifest_sha256"),
                                   ("raw_path_market_relative", "raw_sha256")):
            require(digest(_read(_relative(market_root, snapshot[path_key]))) == snapshot[hash_key],
                    "source_snapshot_changed")
    bars = {symbol: [] for symbol in SYMBOLS}
    for source in sources:
        require(source["symbol"] in SYMBOLS, "source_scope")
        day = date.fromisoformat(source["session_date"])
        catalog = load_verified_kis_paper_private_intraday_catalog(
            cache_root=_relative(market_root, source["cache_root_market_relative"]),
            repo_root=REPO, symbol=source["symbol"],
            exchange=source["exchange"], expected_index_metadata_sha256=source["index_sha256"],
        )
        require(catalog.dataset_hash == source["catalog_dataset_hash"], "catalog_identity")
        bars[source["symbol"]].extend(b for b in catalog.bars
                                      if b.start_ts.astimezone(EASTERN).date() == day)
    return {symbol: tuple(sorted(values, key=lambda b: b.start_ts))
            for symbol, values in bars.items()}


def _output(root):
    from thericher_v2.research.artifact_paths import reject_repo_artifact_path

    output = Path(root) / "research" / NAME
    reject_repo_artifact_path(output, REPO)
    require(output.is_dir() and not output.is_symlink(), "output_directory")
    return output


def safe_result(result):
    return {key: result[key] for key in (
        "status", "criterion", "contract_sha256", "phase", "reason", "actual_fits",
        "inference_calls", "elapsed_seconds", "peak_vram_bytes",
    )} | {"cells": len(result["cells"]), "result_sha256": digest(encode(result))}


def run_campaign(precommit, pin, artifact_root, market_root, *, deadline=None):
    """Parent-supervised worker. A blocked C++/CUDA call needs the external hard timer."""
    started = time.monotonic()
    deadline = min(deadline or float("inf"), started + SECONDS)
    _contract, commitment, plan = read_contract(precommit, pin, market_root)
    output = _output(artifact_root)
    require(not any((output / name).exists() for name in (
        "started.json", "actions.json", "worker-result.json")), "attempt_already_exists")
    atomic_new(output / "started.json", dict(contract_sha256=pin))
    phase, calls, peak, cells, action_pin = "source_input", 0, None, (), None
    result = dict(status="failed", criterion="runtime_failure", contract_sha256=pin,
                  phase=phase, reason="worker_failed", actual_fits=0, inference_calls=0,
                  elapsed_seconds=0.0, peak_vram_bytes=None, cells=[], actions_sha256=None)
    try:
        bars = load_committed_bars(commitment, market_root)
        prepared = prepare_inputs(bars, plan, deadline=deadline)
        require(time.monotonic() < deadline, "compute_stop")
        points = []
        if prepared.ready_rows:
            from thericher_v2.research.timesfm_local import forecast_timesfm_2p5

            phase = "inference"
            import torch

            # The parent holds the canonical lease through child exit and reaping.
            require(torch.cuda.is_available(), "cuda_unavailable")
            require(os.environ.get("CUBLAS_WORKSPACE_CONFIG") == ":4096:8", "cuda_configuration")
            torch.use_deterministic_algorithms(True)
            torch.cuda.reset_peak_memory_stats()
            calls = 1
            points, _ = forecast_timesfm_2p5(
                Path(artifact_root) / "foundation-models/timesfm-2.5-200m" / REVISION,
                dict(MODEL_PINS), [prepared.contexts[i] for i in prepared.ready_rows],
                HORIZON, "cuda",
            )
            torch.cuda.synchronize()
            peak = torch.cuda.max_memory_allocated()
        require(time.monotonic() < deadline, "compute_stop")
        phase = "decision_seal"
        seal = seal_decisions(prepared, points)
        atomic_new(output / "actions.json", seal.record())
        action_pin = seal.sha256
        phase = "evaluate"
        cells = evaluate_sealed(bars, seal)
        require(time.monotonic() < deadline, "compute_stop")
        phase = "validate"
        verdict = criterion(cells)
        result.update(status="input_unavailable" if verdict == "input_unavailable" else "complete",
                      criterion=verdict, reason=None)
    except Exception as error:
        allowed = {"compute_stop", "cuda_unavailable", "cuda_configuration",
                   "forecast_shape", "forecast_values",
                   "input_nonfinite", "action_seal_changed", "cell_matrix"}
        result["reason"] = str(error) if type(error) is StudyFault and str(error) in allowed \
            else "worker_failed"
        cells = ()
        action_path = output / "actions.json"
        action_pin = digest(_read(action_path)) if action_path.exists() else None
    result.update(phase=phase, inference_calls=calls, elapsed_seconds=time.monotonic() - started,
                  peak_vram_bytes=peak, cells=list(cells), actions_sha256=action_pin)
    atomic_new(output / "worker-result.json", result)
    return safe_result(result)


def verify_result(precommit, pin, artifact_root, market_root, result_pin):
    """ALL-RO: no GPU, inference, registry write, refit, or outcome selection."""
    _contract, commitment, plan = read_contract(precommit, pin, market_root)
    output = _output(artifact_root)
    result = _read_json(output / "worker-result.json", result_pin, canonical=True)
    require(set(result) == {"status", "criterion", "contract_sha256", "phase", "reason",
                            "actual_fits", "inference_calls", "elapsed_seconds", "peak_vram_bytes",
                            "cells", "actions_sha256"}
            and result["phase"] in {"source_input", "inference", "decision_seal", "evaluate",
                                    "validate"}
            and type(result["inference_calls"]) is int and result["inference_calls"] in (0, 1)
            and type(result["elapsed_seconds"]) in (int, float)
            and math.isfinite(result["elapsed_seconds"]) and result["elapsed_seconds"] >= 0
            and (result["peak_vram_bytes"] is None or type(result["peak_vram_bytes"]) is int
                 and result["peak_vram_bytes"] >= 0), "result_header")
    require(_read_json(output / "started.json", canonical=True) == {"contract_sha256": pin}
            and result["contract_sha256"] == pin
            and type(result["actual_fits"]) is int and result["actual_fits"] == 0,
            "result_binding")
    if result["status"] == "failed":
        require(result["cells"] == [] and result["criterion"] == "runtime_failure",
                "failure_binding")
        action_path = output / "actions.json"
        if result["actions_sha256"] is None:
            require(not action_path.exists(), "failure_action_binding")
        else:
            require(digest(_read(action_path)) == result["actions_sha256"],
                    "failure_action_binding")
        return safe_result(result) | {"replay": "failure_binding_only"}
    require(result["status"] in {"complete", "input_unavailable"}, "result_status")
    bars = load_committed_bars(commitment, market_root)
    prepared = prepare_inputs(bars, plan)
    saved = _read_json(output / "actions.json", result["actions_sha256"], canonical=True)
    seal = seal_decisions(prepared, [saved["predictions"][i] for i in prepared.ready_rows])
    require(encode(seal.record()) == encode(saved), "actions_replay")
    cells = evaluate_sealed(bars, seal)
    require(encode(list(cells)) == encode(result["cells"])
            and criterion(cells) == result["criterion"] and result["phase"] == "validate"
            and result["reason"] is None and result["inference_calls"] == bool(prepared.ready_rows)
            and result["status"] == ("input_unavailable"
                                      if result["criterion"] == "input_unavailable"
                                      else "complete"),
            "numeric_replay")
    return safe_result(result) | {"replay": "exact", "inference_calls_readback": 0}


def synthetic_smoke():
    dates = tuple(date(2026, 8, 28) + timedelta(days=i) for i in range(25))
    sessions = tuple(SessionWindow(
        datetime.combine(day, clock_time(9, 30), EASTERN).astimezone(UTC),
        datetime.combine(day, clock_time(16), EASTERN).astimezone(UTC)) for day in dates)
    plan = build_plan(dates, sessions)
    bars = {symbol: tuple(Bar(symbol, "US", Timeframe.M1, s.open_ts + i * MINUTE,
                             Decimal(100), Decimal(100), Decimal(100), Decimal(100), Decimal(0))
                          for s in sessions for i in range(390)) for symbol in SYMBOLS}
    prepared = prepare_inputs(bars, plan)
    points = [(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 21.0)] * 150
    seal = seal_decisions(prepared, points)
    cells = evaluate_sealed(bars, seal)
    require(not prepared.unavailable_blocks and len(cells) == 30
            and criterion(cells) == "rejected", "synthetic_smoke")
    return dict(status="synthetic_smoke_passed", cells=30, actual_fits=0,
                model_inference_calls=0, actual_source_reads=0, gpu=False,
                input_sha256=prepared.input_sha256, actions_sha256=seal.sha256,
                result_sha256=digest(encode(list(cells))))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    for mode in ("smoke", "run", "verify"):
        modes.add_argument("--" + mode, action="store_true")
    parser.add_argument("--precommit", type=Path)
    parser.add_argument("--contract-sha256")
    parser.add_argument("--result-sha256")
    parser.add_argument("--artifact-root", type=Path,
                        default=Path("D:/thericher-v2/model-artifacts"))
    parser.add_argument("--market-data-root", type=Path, default=Path("D:/market_data"))
    args = parser.parse_args(argv)
    bound = bool(args.run or args.verify)
    if bool(args.precommit) != bound or bool(args.contract_sha256) != bound \
            or bool(args.result_sha256) != bool(args.verify):
        parser.error("run/replay require exact precommit, contract and result pins")
    try:
        if args.smoke:
            value = synthetic_smoke()
        elif args.run:
            value = run_campaign(args.precommit, args.contract_sha256, args.artifact_root,
                                 args.market_data_root)
        elif args.verify:
            value = verify_result(args.precommit, args.contract_sha256, args.artifact_root,
                                  args.market_data_root, args.result_sha256)
        else:
            value = dict(status="static_plan", config=configuration())
    except Exception:
        value = dict(status="operation_unavailable", raw_error_suppressed=True)
    print(json.dumps(value, sort_keys=True))
    return 0 if value["status"] in {"static_plan", "synthetic_smoke_passed", "complete",
                                    "input_unavailable"} or value.get("replay") == \
        "failure_binding_only" else 1


if __name__ == "__main__":
    raise SystemExit(main())
