"""Synthetic ORB/session and local-only replay tests; no retained market inputs."""

import copy
import json
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from test_firstrate_m5_h30_lstm_dev_20260921 import fast_payoff, synthetic_receipt
from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.execution import EmergencyStore
from thericher_v2.research import firstrate_opening_range as s

HASH = "sha256:" + "a" * 64
OPEN = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)


def day(opening=OPEN, *, count=78, signal=6, symbol="SPY", exit_price="102"):
    bars = []
    for i in range(count):
        price = Decimal(exit_price) if i == count - 1 else Decimal(100)
        close = Decimal(102) if i == signal else price
        bars.append(
            Bar(
                symbol=symbol,
                market="US",
                timeframe=Timeframe.M5,
                start_ts=opening + i * s.STEP,
                open=price,
                close=close,
                high=max(price, close) + 1,
                low=min(price, close) - 1,
                volume=Decimal(100),
                complete=True,
            )
        )
    return tuple(bars)


def decision(bars):
    return s.decide({b.start_ts: b for b in bars}, "SPY", OPEN, OPEN + len(bars) * s.STEP)


@pytest.mark.parametrize("count", (42, 78))
@pytest.mark.parametrize("signal", (6, 12, 39))
@pytest.mark.parametrize("cost", s.COSTS)
def test_next_open_first_breakout_fixed_preclose_and_replay(count, signal, cost, tmp_path):
    bars = day(count=count, signal=signal)
    obs = decision(bars)
    assert obs.at == OPEN + (signal + 1) * s.STEP
    assert obs.signal == bars[signal]
    outcome = s.h30.Outcome(bars[signal + 1 :])
    observation = s.h30.Observation(at=obs.at, features=(), signal=obs.signal)
    actual = s.sessions.payoff(observation, outcome, cost, EmergencyStore(tmp_path / "e.json"))
    assert actual == fast_payoff(observation, outcome, cost, None)
    assert outcome.bars[-1].start_ts == obs.closing - s.STEP
    assert outcome.bars[0].start_ts < outcome.bars[-1].start_ts


def test_strict_high_not_close_or_intrabar_touch_and_one_entry():
    bars = list(day(signal=10))
    bars[1] = replace(bars[1], high=Decimal(105))
    bars[6] = replace(bars[6], high=Decimal(106), close=Decimal(105))
    bars[8] = replace(bars[8], high=Decimal(107), close=Decimal(106))
    assert decision(bars).signal == bars[8]


@pytest.mark.parametrize("signal,selected", ((75, True), (76, False), (77, False), (None, False)))
def test_last_entry_is_strictly_before_exit(signal, selected):
    obs = decision(day(signal=signal))
    assert (obs.status == "selected") == selected
    if selected:
        assert obs.at == obs.closing - 2 * s.STEP


@pytest.mark.parametrize(
    "i,status",
    (
        (0, "opening_unavailable"),
        (5, "opening_unavailable"),
        (6, "scan_unavailable"),
        (9, "scan_unavailable"),
    ),
)
@pytest.mark.parametrize("missing", (True, False))
def test_gap_before_first_signal_ends_scan_no_reentry(i, status, missing):
    bars = day(signal=10)
    index = {b.start_ts: b for b in bars}
    at = bars[i].start_ts
    if missing:
        del index[at]
    else:
        index[at] = replace(index[at], complete=False)
    assert s.decide(index, "SPY", OPEN, OPEN + 78 * s.STEP).status == status


@pytest.mark.parametrize("i", (7, 20, 76, 77))
def test_future_deletion_never_changes_frozen_decision(i):
    bars = day()
    index = {b.start_ts: b for b in bars}
    before = s.decide(index, "SPY", OPEN, OPEN + 78 * s.STEP)
    del index[bars[i].start_ts]
    assert s.decide(index, "SPY", OPEN, OPEN + 78 * s.STEP) == before
    assert s.complete_path(index, "SPY", OPEN, OPEN + 78 * s.STEP) is None


def test_scan_never_reads_future_or_other_session():
    bars = day()

    class Prefix(dict):
        def get(self, key):
            assert OPEN <= key < OPEN + 7 * s.STEP
            return super().get(key)

    assert s.decide(
        Prefix({b.start_ts: b for b in bars}), "SPY", OPEN, OPEN + 78 * s.STEP
    ) == decision(bars)


def test_calendar_dst_early_close_and_pre_mask_fold_boundaries():
    dates = (
        datetime(2025, 3, 7, tzinfo=UTC),
        datetime(2025, 3, 10, tzinfo=UTC),
        datetime(2025, 11, 28, tzinfo=UTC),
    )
    calendar = s.sessions.regular_sessions([replace(day()[0], start_ts=d) for d in dates])
    by_date = {o.date(): (o, c) for o, c in calendar}
    assert by_date[dates[0].date()][0].hour == 14
    assert by_date[dates[1].date()][0].hour == 13
    o, c = by_date[dates[-1].date()]
    assert (c - o) // s.STEP == 42
    assert s.folds(calendar) == (
        calendar[len(calendar) // 2 : 3 * len(calendar) // 4],
        calendar[3 * len(calendar) // 4 :],
    )


@pytest.fixture(scope="module")
def source():
    schedule, bars = [], []
    for i in range(80):
        opening = OPEN + timedelta(days=i)
        count = 42 if i % 10 == 0 else 78
        schedule.append((opening, opening + count * s.STEP))
        # Half the sessions never break out, so a same-trade control cannot pass.
        bars.extend(
            day(
                opening,
                count=count,
                signal=6 if i % 2 == 0 else None,
                exit_price="102" if i % 2 == 0 else "99",
            )
        )
    return tuple(schedule), tuple(bars)


def run(source, *, replay=fast_payoff):
    schedule, bars = source
    return s.compare(
        ((symbol, tuple(replace(b, symbol=symbol) for b in bars)) for symbol in s.SYMBOLS),
        None,
        time.monotonic() + 60,
        HASH,
        schedule=schedule,
        replay=replay,
    )


def test_matched_time_controls_include_nonsignal_sessions_and_match_early_closes(source):
    calls = []

    def replay(obs, out, cost, emergency):
        calls.append((obs.at, out.bars[-1].start_ts, cost))
        return fast_payoff(obs, out, cost, emergency)

    result = run(source, replay=replay)
    assert result["status"] == "complete" and len(result["cells"]) == 12
    assert result["conclusion"] == "descriptive_criterion_met"
    assert result["promotion"] is False
    for fold in result["folds"]:
        assert fold["counts"]["observed"] == 20
        assert fold["counts"]["selected_observed"] == 10
        assert fold["control_pool_sizes"] == [
            dict(session_bars=42, entry_offset_bars=7, sessions=2),
            dict(session_bars=78, entry_offset_bars=7, sessions=18),
        ]
    for cell in result["cells"]:
        assert cell["trades"] == 10
        assert Decimal(cell["orb"]["gross_dollars"]) == 20
        expected = Decimal(4) + Decimal(8) * Decimal(6) / Decimal(18)
        assert abs(Decimal(cell["matched_long"]["gross_dollars"]) - expected) < Decimal("1e-20")
        assert Decimal(cell["paired_net_bps_delta"]) > 0
    assert len(calls) == 2 * 2 * 20 * 3  # One replay per pooled day/offset/cost, reused for ORB.


def test_outcome_mask_is_post_decision_common_and_missing_is_not_zero(source):
    before = run(source)
    schedule, bars = source
    missing = schedule[40][1] - s.STEP
    after = run((schedule, tuple(b for b in bars if b.start_ts != missing)))
    for old, new in zip(before["folds"], after["folds"], strict=True):
        assert old["decision_sha256"] == new["decision_sha256"]
        if new["fold"] == 1:
            assert new["counts"]["selected"] == 10
            assert new["counts"]["selected_observed"] == 9
            assert new["counts"]["selected_censored"] == 1
            assert new["counts"]["censored"] == 1


def test_shortfall_removes_all_comparison_cells_but_keeps_every_support_count(source):
    schedule, bars = source
    missing = {schedule[i][1] - s.STEP for i in range(40, 50)}
    result = run((schedule, tuple(b for b in bars if b.start_ts not in missing)))
    assert result["status"] == "input_unavailable" and result["cells"] == []
    assert len(result["folds"]) == 4
    assert result["folds"][0]["counts"]["observed"] == 10


def test_no_breakout_and_sparse_trades_are_support_shortfalls(source):
    schedule, bars = source
    result = run((schedule, tuple(replace(b, close=b.open) for b in bars)))
    assert result["status"] == "input_unavailable"
    assert all(f["counts"]["selected"] == 0 for f in result["folds"])


@pytest.mark.parametrize("defect", ("duplicate", "reversed", "symbol", "timeframe", "deadline"))
def test_input_and_budget_invariants(source, defect):
    schedule, bars = source
    if defect == "duplicate":
        bars = (*bars[:1], *bars)
    elif defect == "reversed":
        bars = bars[::-1]
    elif defect == "symbol":
        bars = (replace(bars[0], symbol="QQQ"), *bars[1:])
    elif defect == "timeframe":
        bars = (replace(bars[0], timeframe=Timeframe.M1), *bars[1:])
    with pytest.raises(ValueError):
        s.compare(
            (("SPY", bars),),
            None,
            0 if defect == "deadline" else time.monotonic() + 60,
            HASH,
            schedule=schedule,
            replay=fast_payoff,
        )


@pytest.mark.parametrize(
    "defect",
    (
        "identity",
        "private",
        "flag",
        "count",
        "partial",
        "metric",
        "delta",
        "cash",
        "conclusion",
        "duplicate",
        "pool",
    ),
)
def test_worker_payload_validation_rejects_mutation(source, defect):
    result = copy.deepcopy(run(source))
    if defect == "identity":
        result["contract_sha256"] = "wrong"
    elif defect == "private":
        result["raw_rows"] = "PRIVATE"
    elif defect == "flag":
        result["promotion"] = 0
    elif defect == "count":
        result["folds"][0]["counts"]["selected"] = -1
    elif defect == "partial":
        result["cells"].pop()
    elif defect == "metric":
        result["cells"][0]["orb"]["fees_dollars"] = "NaN"
    elif defect == "delta":
        result["cells"][0]["paired_net_bps_delta"] = "0"
    elif defect == "cash":
        result["cells"][0]["cash"]["fees_dollars"] = "1"
    elif defect == "conclusion":
        result["conclusion"] = "promoted"
    elif defect == "duplicate":
        result["cells"][1] = result["cells"][0]
    elif defect == "pool":
        result["folds"][0]["control_pool_sizes"][0]["sessions"] = True
    with pytest.raises(ValueError):
        s.validate_result(result, HASH)


@pytest.mark.parametrize("field", ("fold_record", "cell_fold", "cell_cost"))
def test_boolean_identities_cannot_alias_integer_one(source, field):
    result = run(source)
    if field == "fold_record":
        result["folds"][0]["fold"] = True
    else:
        result["cells"][0]["fold" if field == "cell_fold" else "cost_bps_per_side"] = True
    with pytest.raises(ValueError, match="identity_type"):
        s.validate_result(result, HASH)


@pytest.mark.parametrize("candidate", ("orb", "matched_long"))
@pytest.mark.parametrize("defect", ("gross", "fees", "bps", "tied_fees"))
def test_cross_cost_mutations_fail_despite_valid_cell_accounting(source, candidate, defect):
    result = run(source)
    cell = result["cells"][1]
    prior, values = result["cells"][0][candidate], cell[candidate]
    if defect == "gross":
        values["gross_dollars"] = str(Decimal(values["gross_dollars"]) + 1)
    elif defect in ("fees", "tied_fees"):
        values["fees_dollars"] = str(
            Decimal(prior["fees_dollars"]) - (Decimal(".01") if defect == "fees" else 0)
        )
    else:
        values["net_bps_sum"] = str(Decimal(prior["net_bps_sum"]) + 1)
    values["net_dollars"] = str(Decimal(values["gross_dollars"]) - Decimal(values["fees_dollars"]))
    cell["paired_net_bps_delta"] = str(
        Decimal(cell["orb"]["net_bps_sum"]) - Decimal(cell["matched_long"]["net_bps_sum"])
    )
    with pytest.raises(ValueError, match="cross_cost_consistency"):
        s.validate_result(result, HASH)


def test_contract_freeze_is_metadata_only_immutable_and_identity_bound(tmp_path, monkeypatch):
    receipt = synthetic_receipt(tmp_path / "synthetic-market")
    specs = s.h30.parse_firstrate_normalization_receipt(receipt)
    monkeypatch.setattr(
        s, "SOURCE_PINS", {p.symbol: (p.canonical_sha256[7:], p.bar_count) for p in specs}
    )
    root = tmp_path / "artifacts"
    path = root / s.h30.RECEIPT
    path.parent.mkdir(parents=True)
    path.write_bytes(receipt)
    registered = []
    monkeypatch.setattr(s.h30, "register_frozen_campaign", lambda **kw: registered.append(kw))
    monkeypatch.setattr(s.h30, "load_streams", lambda *_: pytest.fail("dataset run forbidden"))
    read_bytes = Path.read_bytes

    def guarded(path):
        assert path.suffix != ".csv"
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded)
    pin = s.freeze(root)
    output = s.verify(root, pin)
    payload = json.loads((output / "contract.json").read_bytes())
    assert payload["budget"]["fits"] == 0 and payload["fees_bps_per_side"] == [1, 3, 5]
    assert payload["interpretation"] == "descriptive source-local implementation/comparison only"
    assert payload["strongest_kill_test"].endswith(
        "fixed descriptive 3bps comparison across four symbol/folds, not economic "
        "rejection/survival, confidence or evidence against ORB mechanism"
    )
    assert payload["minimums"] == {
        "complete_sessions_per_symbol_fold": 16,
        "scored_orb_trades_per_symbol_fold": 8,
    }
    assert "source_clock_boundary_unverified" in payload["limitations"]
    assert "complete_session_posthoc_censoring" in payload["limitations"]
    assert all(payload[f] is False for f in s.FLAGS)
    assert registered[0]["trial_family"] == s.FAMILY
    with pytest.raises(FileExistsError):
        s.freeze(root)
    with pytest.raises(ValueError, match="contract_changed"):
        s.verify(root, HASH)
    monkeypatch.setattr(s, "SOURCE_PINS", {})
    with pytest.raises(ValueError, match="source_pins_changed"):
        s.verify(root, pin)


def test_unexpected_receipt_and_repo_output_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="source_pins_changed"):
        s.contract(synthetic_receipt(tmp_path / "synthetic-market"))
    with pytest.raises(ValueError):
        s.directory(s.REPO / "should-not-create")


def test_descriptive_criterion_requires_both_symbols_both_folds(source):
    cells = run(source)["cells"]
    assert s.conclusion(cells) == "descriptive_criterion_met"
    cells[1]["paired_net_bps_delta"] = "0"
    assert s.conclusion(cells) == "descriptive_criterion_not_met"


def test_prices_after_signal_change_only_payoff_not_entry():
    bars = day()
    before = decision(bars)
    changed = tuple(
        replace(b, open=b.open + 5, high=b.high + 5, low=b.low + 5, close=b.close + 5)
        if i >= 7
        else b
        for i, b in enumerate(bars)
    )
    assert decision(changed) == before


def test_each_session_resets_range_and_premarket_is_ignored():
    first = day(signal=6)
    second_open = OPEN + timedelta(days=1)
    second = day(second_open, signal=None)
    premarket = replace(first[0], start_ts=OPEN - s.STEP, high=Decimal(10000))
    index = {b.start_ts: b for b in (*first, *second, premarket)}
    assert s.decide(index, "SPY", OPEN, OPEN + 78 * s.STEP).status == "selected"
    assert s.decide(index, "SPY", second_open, second_open + 78 * s.STEP).status == "no_breakout"


def test_worker_suppresses_invariant_failure_and_partial_output(tmp_path, monkeypatch):
    def reject(*args):
        raise ValueError("PRIVATE")

    monkeypatch.setattr(s, "verify", reject)
    monkeypatch.setattr(s.h30, "load_streams", lambda *_: pytest.fail("panel forbidden"))
    path = tmp_path / "result.json"
    s.worker(tmp_path, tmp_path / "no-market", HASH, path)
    result = json.loads(path.read_bytes())
    assert result == s.failure(HASH, "runtime_or_invariant_failure")
    assert "PRIVATE" not in path.read_text()
