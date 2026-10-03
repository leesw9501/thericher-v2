"""Original zero-fit, seen-data noise-band DEVELOPMENT study, not paper replication."""

from __future__ import annotations

import importlib.metadata
import json
import re
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from thericher_v2.market.resample import SessionWindow
from thericher_v2.research import firstrate_opening_range as orb
from thericher_v2.research.intraday_noise_band import (
    NoiseBandHistoryEntry,
    build_intraday_noise_band,
)

sessions, h30, require = orb.sessions, orb.h30, orb.require
REPO, STEP, GRADE = orb.REPO, orb.STEP, orb.GRADE
FAMILY = "firstrate-time-of-day-band-development-20261003-v1"
NAME = "firstrate-time-of-day-band-development-20261003-v2"
SECONDS, MIN_SESSIONS, MIN_TRADES = 300, 16, 8
COSTS, SYMBOLS, METRICS = orb.COSTS, orb.SYMBOLS, orb.METRICS
FLAGS = (*orb.FLAGS, "weights")
HELPER = "src/thericher_v2/research/intraday_noise_band.py"
HELPER_HASH = "sha256:191bbe38e29b2c5a88d9b83e408527f67e34f4c445336c75bc0f77820db3ba2a"
CODE = ("src/thericher_v2/research/firstrate_time_of_day_band.py",
        "scripts/run_firstrate_time_of_day_band.py", HELPER, *orb.CODE)
DECISIONS = ("selected", "no_breakout", "current_unavailable", "history_unavailable")
COUNTS = (*DECISIONS, *orb.COUNTS[len(orb.DECISIONS):])


def contract(receipt):
    payload = orb.contract(receipt)
    require(h30.digest((REPO / HELPER).read_bytes()) == HELPER_HASH, "helper_changed")
    for key in ("range", "prior_diagnostic_summary_sha256"):
        payload.pop(key)
    payload.update(
        name=NAME, family=FAMILY, prior_seen_family=[orb.FAMILY, h30.FAMILY],
        runtime_repair="same v1 recipe/family; only archive-readback control locks "
        "move to scratch; "
        "original result/failed readback retained, no selection or changed data/costs",
        predecessor_contract_sha256="sha256:64baa2808cd0a35be77685f3fe752dc7d7067f5ea3babb40cc6cc49b73c7c5b8",
        source_mechanism="https://concretumgroup.com/wp-content/uploads/2026/02/Beat-the-Market.pdf",
        interpretation="original source-local DEVELOPMENT variant; not author-paper reproduction",
        code_sha256={p: h30.digest((REPO / p).read_bytes()) for p in CODE},
        history="exactly last14 SCHEDULED NYSE sessions before current, including missing days; "
        "prior close<=current open; only complete contiguous same-elapsed M5 prefixes",
        band="current OPEN*(1+mean14(abs(prior completed CLOSE/prior OPEN-1))); no gap anchor",
        signal="ONE first semi-hourly completed CLOSE STRICTLY above upper band; "
        "cutoffs open+30,60,... strictly before scheduled close-5min",
        entry="next M5 OPEN at completed cutoff; long only, one share, no leverage/reentry",
        exit="scheduled close-5min OPEN, DST/early closes; no VWAP stop or overnight carry",
        missing_rule="current/history prefix gap, incomplete or unaligned bar ends scan with "
        "explicit unavailable and cutoff; never skip/substitute scheduled sessions",
        outcome_rule="freeze ALL four fold decision tuples before ANY complete-session mask; "
        "then common full-session outcome mask for band/matched long/cash; no zero/backfill",
        control=payload["control"].replace("ORB", "band"),
        training_rule="none; fourteen rolling past observations are not fitting; no search",
        minimums=dict(complete_sessions_per_symbol_fold=MIN_SESSIONS,
                      scored_band_trades_per_symbol_fold=MIN_TRADES),
        budget=dict(cpu_seconds=SECONDS, cpu_threads=1, memory_gib=2, network="none", fits=0,
                    gpu=0, weights=0, holdout=0, promotion=0, cells=12, retries=0,
                    max_m1_rows_per_symbol=250000, max_source_bytes=134217728),
        strongest_kill_test="future-dependent action or replay/identity mismatch invalidates "
        "all cells; fewer than16 complete sessions or8 trades in any symbol/fold is "
        "input_unavailable, not hypothesis rejection; at3bps/side any nonpositive band net "
        "OR increment over matched long in ANY of four symbol/folds kills this recipe; "
        "no1/5bps rescue, threshold/sample search, independent-performance or promotion claim",
        **dict.fromkeys(FLAGS, False),
    )
    return payload


def directory(root):
    return h30.within(h30.ensure_external_artifact_directory(root, REPO), Path("research") / NAME)


def freeze(root):
    output = directory(root)
    payload = contract(h30.within(root, h30.RECEIPT).read_bytes())
    output.mkdir(parents=True, exist_ok=False)
    raw = h30.encode(payload)
    with (output / "contract.json").open("xb") as handle:
        handle.write(raw)
    h30.register_frozen_campaign(
        contract_hash=h30.digest(raw), dataset_hash=h30.digest(h30.encode(payload["source_pins"])),
        split_hash=h30.digest(h30.encode([payload["split"], payload["history"]])),
        cost_model_hash=h30.digest(h30.encode([COSTS, payload["control"]])),
        trial_family=FAMILY, holdout_access="none", artifact_root=root, repo_root=REPO,
    )
    return h30.digest(raw)


def verify(root, scope_hash):
    output = directory(root)
    raw = (output / "contract.json").read_bytes()
    require(h30.digest(raw) == scope_hash and
            raw == h30.encode(contract(h30.within(root, h30.RECEIPT).read_bytes())),
            "contract_changed")
    return output


@dataclass(frozen=True)
class Decision(orb.Decision):
    cutoff: datetime | None = None


def prefix(index, symbol, session, cutoff):
    if cutoff > session.close_ts:
        return None
    bars = []
    for i in range((cutoff - session.open_ts) // STEP):
        at = session.open_ts + i * STEP
        bar = index.get(at)
        if (bar is None or bar.complete is not True or
                (bar.start_ts, bar.symbol, bar.market, bar.timeframe)
                != (at, symbol, "US", h30.Timeframe.M5)):
            return None
        bars.append(bar)
    return tuple(bars)


def decide(index, symbol, calendar, position, deadline):
    session = SessionWindow(*calendar[position])
    opening, closing = session.open_ts, session.close_ts
    require(8 * STEP < closing - opening <= 78 * STEP and
            (closing - opening) % STEP == STEP * 0, "session_geometry")
    history = calendar[max(0, position - 14):position]
    for offset in range(6, (closing - opening) // STEP - 1, 6):
        h30.check_time(deadline)
        cutoff = opening + offset * STEP
        current = prefix(index, symbol, session, cutoff)
        if current is None:
            return Decision(opening, closing, "current_unavailable", cutoff=cutoff)
        if len(history) != 14 or any(c > opening for _, c in history):
            return Decision(opening, closing, "history_unavailable", cutoff=cutoff)
        entries = []
        for o, c in history:
            prior = SessionWindow(o, c)
            bars = prefix(index, symbol, prior, o + offset * STEP)
            if bars is None:
                return Decision(opening, closing, "history_unavailable", cutoff=cutoff)
            entries.append(NoiseBandHistoryEntry(prior, bars))
        band = build_intraday_noise_band(current, history=entries, session=session, as_of=cutoff)
        if current[-1].close > band.upper:
            return Decision(opening, closing, "selected", current[-1], cutoff)
    return Decision(opening, closing, "no_breakout")


def compare_fold(symbol, number, index, decisions, emergency, deadline, replay):
    paths = tuple(orb.complete_path(index, symbol, d.opening, d.closing) for d in decisions)
    counts = dict.fromkeys(COUNTS, 0)
    counts.update(Counter(d.status for d in decisions))
    counts.update(sessions=len(decisions), observed=sum(p is not None for p in paths))
    counts["censored"] = counts["sessions"] - counts["observed"]
    selected = [(d, p) for d, p in zip(decisions, paths, strict=True)
                if d.status == "selected" and p is not None]
    counts["selected_observed"] = len(selected)
    counts["selected_censored"] = counts["selected"] - len(selected)
    facts = dict(symbol=symbol, fold=number, counts=counts,
                 decision_sha256=h30.digest(h30.encode([
                     [d.opening.isoformat(), d.status,
                      None if d.cutoff is None else d.cutoff.isoformat()] for d in decisions])),
                 outcome_mask_sha256=h30.digest(h30.encode([p is not None for p in paths])))
    if counts["observed"] < MIN_SESSIONS or len(selected) < MIN_TRADES:
        return facts, []
    pools = {(len(p), (d.at - d.opening) // STEP):
             [q for q in paths if q is not None and len(q) == len(p)] for d, p in selected}
    facts["control_pool_sizes"] = [dict(session_bars=n, entry_offset_bars=t, sessions=len(p))
                                   for (n, t), p in sorted(pools.items())]
    cells = []
    for cost in COSTS:
        cache, means, noise, controls = {}, {}, [], []
        def payoff(path, offset, *, cost=cost, cache=cache):
            key = (path[0].start_ts, offset)
            if key not in cache:
                h30.check_time(deadline)
                obs = h30.Observation(at=path[offset - 1].end_ts,
                                      signal=path[offset - 1], features=())
                out = h30.Outcome(path[offset:])
                require(out.entry.is_finite() and out.exit.is_finite() and
                        out.entry > 0 and out.exit > 0, "rounded_price")
                gross, fees = replay(obs, out, cost, emergency)
                cache[key] = orb.metric(gross, fees, out.entry)
            return cache[key]

        for d, p in selected:
            offset = (d.at - d.opening) // STEP
            key = (len(p), offset)
            noise.append(payoff(p, offset))
            if key not in means:
                totals = orb.sum_metrics([payoff(q, offset) for q in pools[key]])
                means[key] = {k: v / len(pools[key]) for k, v in totals.items()}
            controls.append(means[key])
        a, b = orb.sum_metrics(noise), orb.sum_metrics(controls)
        cells.append(dict(symbol=symbol, fold=number, cost_bps_per_side=cost, trades=len(selected),
                          band=orb.strings(a), matched_long=orb.strings(b),
                          cash=orb.strings(orb.sum_metrics([])),
                          decision_sha256=facts["decision_sha256"],
                          paired_net_bps_delta=str(a["net_bps_sum"] - b["net_bps_sum"])))
    return facts, cells


def failure(scope_hash, reason):
    return dict(name=NAME, family=FAMILY, evidence_grade=GRADE, contract_sha256=scope_hash,
                status="failed_all_cells", reason=reason, folds=[], cells=[],
                **dict.fromkeys(FLAGS, False))


def conclusion(cells):
    primary = [c for c in cells if c["cost_bps_per_side"] == 3]
    require([(c["symbol"], c["fold"]) for c in primary] ==
            [(s, f) for s in SYMBOLS for f in (1, 2)], "primary_matrix")
    passes = all(Decimal(c["band"]["net_bps_sum"]) > 0 and
                 Decimal(c["paired_net_bps_delta"]) > 0 for c in primary)
    return "recipe_not_killed" if passes else "recipe_killed"


def compare(streams, emergency, deadline, scope_hash, *, schedule=None, replay=sessions.payoff):
    result = failure(scope_hash, None)
    del result["reason"]
    prepared, seen = [], []
    for symbol, bars in streams:
        h30.check_time(deadline)
        require(symbol in SYMBOLS and symbol not in seen, "source_identity")
        seen.append(symbol)
        require(bool(bars) and all(a.start_ts < b.start_ts
                for a, b in zip(bars, bars[1:], strict=False)), "source_order")
        require(all((b.symbol, b.market, b.timeframe) == (symbol, "US", h30.Timeframe.M5)
                    for b in bars), "source_identity")
        index = {b.start_ts: b for b in bars}
        calendar = sessions.regular_sessions(bars) if schedule is None else schedule
        for number, part in enumerate(orb.folds(calendar), 1):
            left = len(calendar) // 2 if number == 1 else 3 * len(calendar) // 4
            decisions = tuple(decide(index, symbol, calendar, i, deadline)
                              for i in range(left, left + len(part)))
            prepared.append((symbol, number, index, decisions))
    require(seen == list(SYMBOLS), "source_identity")
    # No full-session outcome read occurs until every symbol/fold decision is frozen.
    for symbol, number, index, decisions in prepared:
        h30.check_time(deadline)
        facts, cells = compare_fold(symbol, number, index, decisions, emergency, deadline, replay)
        result["folds"].append(facts)
        result["cells"].extend(cells)
    if len(result["cells"]) != 12:
        result.update(status="input_unavailable", cells=[], conclusion="insufficient_support")
    else:
        result.update(status="complete", conclusion=conclusion(result["cells"]))
    validate_result(result, scope_hash)
    h30.check_time(deadline)
    return result


def validate_result(result, scope_hash):
    expected = failure(scope_hash, None)
    require(set(result) == (set(expected) - {"reason"}) | {"conclusion"}, "result_fields")
    require(all(type(result[k]) is type(expected[k]) and result[k] == expected[k]
                for k in ("name", "family", "evidence_grade", "contract_sha256", *FLAGS)),
            "result_identity")
    require([(f["symbol"], f["fold"]) for f in result["folds"]] ==
            [(s, f) for s in SYMBOLS for f in (1, 2)], "fold_matrix")
    shortfall = False
    for f in result["folds"]:
        n = f["counts"]
        require(type(f["fold"]) is int and set(n) == set(COUNTS) and
                all(type(v) is int and 0 <= v <= 250000 for v in n.values()), "support_counts")
        require(sum(n[k] for k in DECISIONS) == n["sessions"] and
                n["observed"] + n["censored"] == n["sessions"] and
                n["selected_observed"] + n["selected_censored"] == n["selected"] and
                n["selected_observed"] <= n["observed"] and
                n["selected_censored"] <= n["censored"], "support_counts")
        require(all(re.fullmatch(r"sha256:[0-9a-f]{64}", f[k]) for k in
                    ("decision_sha256", "outcome_mask_sha256")), "support_hash")
        low = n["observed"] < MIN_SESSIONS or n["selected_observed"] < MIN_TRADES
        shortfall |= low
        require(set(f) == {"symbol", "fold", "counts", "decision_sha256", "outcome_mask_sha256"}
                | (set() if low else {"control_pool_sizes"}), "fold_fields")
        if not low:
            pools = f["control_pool_sizes"]
            require(bool(pools) and all(set(p) == {"session_bars", "entry_offset_bars", "sessions"}
                    and all(type(v) is int for v in p.values()) and
                    9 <= p["session_bars"] <= 78 and 6 <= p["entry_offset_bars"] <
                    p["session_bars"] - 1 and p["entry_offset_bars"] % 6 == 0 and
                    1 <= p["sessions"] <= n["observed"] for p in pools) and
                    len({(p["session_bars"], p["entry_offset_bars"]) for p in pools}) == len(pools),
                    "control_pool")
    if shortfall:
        require(result["status"] == "input_unavailable" and result["cells"] == [] and
                result["conclusion"] == "insufficient_support", "shortfall_result")
        return
    require(result["status"] == "complete" and len(result["cells"]) == 12, "cell_matrix")
    previous = {}
    for c, key in zip(result["cells"], [(s, f, v) for s in SYMBOLS for f in (1, 2) for v in COSTS],
                      strict=True):
        require(set(c) == {"symbol", "fold", "cost_bps_per_side", "trades", "band", "matched_long",
                           "cash", "paired_net_bps_delta", "decision_sha256"} and
                type(c["fold"]) is int and type(c["cost_bps_per_side"]) is int and
                (c["symbol"], c["fold"], c["cost_bps_per_side"]) == key, "cell_matrix")
        f = next(f for f in result["folds"] if (f["symbol"], f["fold"]) == key[:2])
        require(type(c["trades"]) is int and c["trades"] == f["counts"]["selected_observed"] and
                c["decision_sha256"] == f["decision_sha256"], "cell_support")
        for candidate in ("band", "matched_long", "cash"):
            m = c[candidate]
            require(set(m) == set(METRICS) and all(isinstance(v, str) and Decimal(v).is_finite()
                    for v in m.values()), "metric_fields")
            g, fees, net, bps = (Decimal(m[k]) for k in METRICS)
            require(fees >= 0 and abs(g - fees - net) < Decimal("1e-20"), "cell_accounting")
            require(candidate != "cash" or all(Decimal(v) == 0 for v in m.values()), "cash_nonzero")
            identity = (*key[:2], candidate)
            if identity in previous:
                pg, pf, pn, pb = previous[identity]
                require(g == pg and fees >= pf and net <= pn and bps <= pb and
                        (fees == pf) == (bps == pb), "cross_cost_consistency")
            previous[identity] = (g, fees, net, bps)
        delta = Decimal(c["paired_net_bps_delta"])
        require(delta.is_finite() and delta == Decimal(c["band"]["net_bps_sum"]) -
                Decimal(c["matched_long"]["net_bps_sum"]), "cell_delta")
    require(result["conclusion"] == conclusion(result["cells"]), "result_conclusion")


def worker(root, market, scope_hash, result_path):
    deadline = time.monotonic() + SECONDS
    try:
        verify(root, scope_hash)
        require(importlib.metadata.version("pandas-market-calendars") == "5.4.0",
                "calendar_version")
        streams = h30.load_streams(market, h30.within(root, h30.RECEIPT).read_bytes(), deadline)
        emergency = h30.EmergencyStore(result_path.parent / "emergency.json")
        result = compare(streams, emergency, deadline, scope_hash)
        verify(root, scope_hash)
        h30.check_time(deadline)
    except Exception:
        result = failure(scope_hash, "runtime_or_invariant_failure")
    with result_path.open("xb") as handle:
        handle.write(h30.encode(result))


def readback(root, market, scope_hash, summary_hash):
    output = verify(root, scope_hash)
    raw = (output / "summary.json").read_bytes()
    require(h30.digest(raw) == summary_hash, "summary_changed")
    result = json.loads(raw)
    result.pop("job")
    validate_result(result, scope_hash)
    deadline = time.monotonic() + SECONDS
    streams = h30.load_streams(market, h30.within(root, h30.RECEIPT).read_bytes(), deadline)
    # EmergencyStore needs a lock even when reading its default control state.
    with tempfile.TemporaryDirectory(prefix="band-replay-") as scratch:
        control = Path(scratch) / "emergency.json"
        archived_control = output / "emergency.json"
        if archived_control.exists() or archived_control.is_symlink():
            require(archived_control.is_file() and not archived_control.is_symlink(),
                    "replay_control_invalid")
            control.write_bytes(archived_control.read_bytes())
        replayed = compare(streams, h30.EmergencyStore(control),
                           deadline, scope_hash)
    require(h30.encode(replayed) == h30.encode(result), "readback_mismatch")
    verify(root, scope_hash)
    return dict(status="verified", contract_sha256=scope_hash, summary_sha256=summary_hash)
