"""Synthetic equal-exposure/cost checks; no retained market data or model access."""

import copy
import json
import socket
import time
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from test_firstrate_m5_h30_lstm_dev_20260921 import fast_payoff
from test_firstrate_session_research import source  # noqa: F401
from thericher_v2.research import firstrate_position_policy as s

HASH = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64


@pytest.fixture(autouse=True)
def no_external_io(monkeypatch):
    original = Path.open

    def safe_open(path, *args, **kwargs):
        normalized = str(path).replace("\\", "/").lower()
        assert not normalized.startswith(("d:/market_data", "d:/thericher-v2/model-artifacts"))
        assert not path.name.startswith(".env")
        return original(path, *args, **kwargs)

    def forbidden(*_args, **_kwargs):
        pytest.fail("network not allowed")

    monkeypatch.setattr(Path, "open", safe_open)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def day(source):  # noqa: F811
    schedule, bars = source
    index = {b.start_ts: b for b in bars}
    obs, _ = s.h30.observe(index, s.sessions.session_grid(schedule[:1], 30, training=False))
    outcomes, _ = s.sessions.outcomes(index, obs, 30)
    return SimpleNamespace(
        index=index,
        obs=obs,
        outcomes=outcomes,
        keys=s.session_keys(obs, schedule),
        schedule=schedule,
    )


def pair(day, selected, cost=3, replay=fast_payoff, emergency=None):
    selected = np.asarray(selected, dtype=bool)
    return s.paired_cell(
        {},
        day.obs,
        day.outcomes,
        selected,
        s.plan_positions(day.obs, selected, day.keys),
        (True,) * len(selected),
        cost,
        emergency,
        time.monotonic() + 30,
        replay,
    )


@pytest.mark.parametrize(
    "selected,roundtrips,removed",
    [
        ([True] * 6, 1, 5),
        ([False] * 6, 0, 0),
        ([True, False, True, False, True, False], 3, 0),
        ([True, True, False, True, True, True], 2, 3),
        ([False, True, True, False, False, True], 2, 1),
    ],
)
@pytest.mark.parametrize("cost", (1, 3, 5))
def test_equal_exposure_gross_and_exact_saved_boundary_fees(
    day, selected, roundtrips, removed, cost
):
    cell = pair(day, selected, cost)
    a, b = cell["repeated"], cell["persistent"]
    assert b["roundtrips"] == roundtrips
    assert a["roundtrips"] == sum(selected)
    assert cell["removed_boundary_pairs"] == removed
    assert a["exposure_minutes"] == b["exposure_minutes"] == sum(selected) * 30
    assert a["exposure_sha256"] == b["exposure_sha256"]
    assert a["gross_dollars"] == b["gross_dollars"]
    assert Decimal(b["net_dollars"]) - Decimal(a["net_dollars"]) == Decimal(
        cell["saved_fees_dollars"]
    )


@pytest.mark.parametrize("cost", (1, 3, 5))
def test_real_local_paper_parity_uses_next_open_and_terminal_flat(day, tmp_path, cost):
    calls = []

    def observed(obs, outcome, rate, emergency):
        calls.append((obs.signal.end_ts, outcome.bars[0].start_ts, outcome.bars[-1].start_ts))
        return s.sessions.payoff(obs, outcome, rate, emergency)

    result = pair(
        day, [True] * 6, cost, observed, s.h30.EmergencyStore(tmp_path / "emergency.json")
    )
    assert len(calls) == 7
    assert all(signal == entry for signal, entry, _ in calls)
    assert calls[-1][0] == day.obs[0].at
    assert calls[-1][2] == day.obs[-1].at + s.h30.HOLD < day.schedule[0][1]
    assert result["persistent"]["terminal_flat"] is True


def test_constant_rounded_prices_prove_improvement_is_only_fees(day):
    index = {
        t: replace(
            b,
            open=Decimal("100.123456"),
            close=Decimal("100.123456"),
            high=Decimal("101"),
            low=Decimal("99"),
        )
        for t, b in day.index.items()
    }
    day.outcomes, _ = s.sessions.outcomes(index, day.obs, 30)
    cell = pair(day, [True] * 6)
    assert Decimal(cell["repeated"]["gross_dollars"]) == 0
    assert Decimal(cell["persistent"]["gross_dollars"]) == 0
    expected = 10 * (Decimal("100.1235") * 3 / 10000).quantize(Decimal("0.0001"))
    assert Decimal(cell["saved_fees_dollars"]) == expected


def test_ineligible_decision_gap_never_carried_over(day):
    obs = day.obs[:2] + day.obs[3:]
    repeated, persistent = s.plan_positions(
        obs, np.ones(len(obs), dtype=bool), day.keys[:2] + day.keys[3:]
    )
    assert repeated == ((0, 0), (1, 1), (2, 2), (3, 3), (4, 4))
    assert persistent == ((0, 1), (2, 4))


def test_different_session_key_never_merged_even_if_times_adjacent(day):
    keys = (day.keys[0],) * 3 + (day.keys[0] + s.h30.HOLD,) * 3
    _, persistent = s.plan_positions(day.obs, np.ones(6, dtype=bool), keys)
    assert persistent == ((0, 2), (3, 5))


@pytest.mark.parametrize("case", ("off_grid", "duplicate", "backwards", "early_close"))
def test_session_grid_rejects_unsupported_decision_and_terminal(day, case):
    obs, schedule = day.obs, day.schedule
    if case == "off_grid":
        obs = (replace(obs[0], at=obs[0].at + s.h30.STEP),)
    elif case == "duplicate":
        obs = (obs[0], obs[0])
    elif case == "backwards":
        obs = obs[::-1]
    else:
        schedule = ((schedule[0][0], schedule[0][0] + 42 * s.h30.STEP),)
    with pytest.raises(s.h30.StudyFailure, match="decision_grid"):
        s.session_keys(obs, schedule)


@pytest.mark.parametrize("selected", ([1] * 6, [True] * 5))
def test_position_plan_rejects_non_boolean_or_wrong_length(day, selected):
    with pytest.raises(s.h30.StudyFailure, match="decision_shape"):
        s.plan_positions(day.obs, selected, day.keys)


def test_common_session_censor_is_after_decisions_and_excludes_both_policies(source):  # noqa: F811
    schedule, bars = source
    obs, _ = s.h30.observe(
        {b.start_ts: b for b in bars}, s.sessions.session_grid(schedule[:12], 30, training=False)
    )
    keys = s.session_keys(obs, schedule)
    selected = np.ones(len(obs), dtype=bool)
    spans = s.plan_positions(obs, selected, keys)
    outcomes, _ = s.sessions.outcomes({b.start_ts: b for b in bars}, obs, 30)
    changed = list(outcomes)
    changed[2] = None
    keep, facts = s.common_support(obs, changed, keys)
    assert keep[:6] == (False,) * 6 and all(keep[6:])
    assert facts["raw_future_missing"] == 1 and facts["common_censored_decisions"] == 6
    assert facts["censored_sessions"] == 1
    assert s.plan_positions(obs, selected, keys) == spans
    cell = s.paired_cell(
        {}, obs, changed, selected, spans, keep, 3, None, time.monotonic() + 30, fast_payoff
    )
    assert cell["selected_decisions"] == 72 and cell["selected_censored"] == 6
    assert cell["repeated"]["roundtrips"] == 66
    assert cell["persistent"]["roundtrips"] == 11


def test_missing_session_support_is_not_zero_return_success(day):
    with pytest.raises(s.sessions.OutcomeSupportShortfall) as caught:
        s.common_support(day.obs, (None,) * 6, day.keys)
    assert caught.value.support == {"eligible": 6, "observed": 0, "censored": 6, "blocks": 0}


@pytest.mark.parametrize(
    "case", ("gross", "exposure", "cost", "removed", "turnover", "parity", "nan")
)
def test_strong_kill_test_detects_exposure_or_cost_advantage(day, case):
    cell = pair(day, [True] * 6)
    b = cell["persistent"]
    if case == "gross":
        b["gross_dollars"] = str(Decimal(b["gross_dollars"]) + 1)
        b["net_dollars"] = str(Decimal(b["net_dollars"]) + 1)
    elif case == "exposure":
        b["exposure_sha256"] = OTHER
    elif case == "cost":
        cell["saved_fees_dollars"] = "0"
    elif case == "removed":
        cell["removed_boundary_pairs"] += 1
    elif case == "turnover":
        cell["saved_turnover_dollars"] = "0"
    elif case == "parity":
        b["local_paper_replay_parity"] = False
    else:
        b["gross_dollars"] = "NaN"
    with pytest.raises(s.h30.StudyFailure):
        s.validate_pair(cell)


@pytest.fixture
def matrix(source, monkeypatch):  # noqa: F811
    schedules, all_bars = source
    schedules = schedules[:40]
    bars = tuple(b for b in all_bars if b.start_ts < schedules[-1][1])
    streams = tuple(
        (symbol, tuple(replace(b, symbol=symbol) for b in bars)) for symbol in s.h30.SYMBOLS
    )
    monkeypatch.setattr(s.sessions, "HORIZONS", (30,))
    monkeypatch.setattr(s.sessions, "regular_sessions", lambda _bars: schedules)

    def predict(fold, _context=36):
        return np.full(len(fold.evaluation), 0.25)

    def trainer(torch, fold, context, seed, deadline):
        return (
            predict(fold),
            {},
            dict(
                epochs=8,
                updates=8 * ((len(fold.train_y) + 127) // 128),
                train_rows=len(fold.train_y),
            ),
        )

    kwargs = dict(schedules=schedules, replay=fast_payoff, ridge=predict)
    cpu, _ = s.sessions.compare(streams, "cpu", None, time.monotonic() + 30, **kwargs)
    cuda, _ = s.sessions.compare(
        streams, "cuda", None, time.monotonic() + 30, reference=cpu, trainer=trainer, **kwargs
    )
    monkeypatch.setattr(s.family, "parent_prediction", lambda torch, fold, *args: predict(fold))
    original_score, original_pair = s.family.score, s.paired_cell
    monkeypatch.setattr(s.family, "score", lambda *args: original_score(*args, replay=fast_payoff))
    monkeypatch.setattr(s, "paired_cell", lambda *args: original_pair(*args, replay=fast_payoff))
    return streams, {"cpu": cpu, "cuda": cuda}


def run(matrix):
    streams, prior = matrix
    return s.compare(streams, None, time.monotonic() + 60, None, None, prior, HASH)


def test_complete_fixed_matrix_no_fit_and_parent72_match(matrix):
    result = run(matrix)
    s.validate_result(result, HASH)
    assert len(result["cells"]) == 72 and len(result["folds"]) == 4
    assert result["parent_controls_reproduced"] == 72
    assert all(
        result[k] is False for k in ("selection", "holdout_access", "promotion", "training", "gpu")
    )
    assert all(
        c["persistent"]["roundtrips"] == 10
        for c in result["cells"]
        if c["candidate"] == "always_long"
    )
    for group in range(0, len(result["cells"]), 18):
        for candidate in range(6):
            assert (
                len(
                    {
                        result["cells"][group + candidate + cost * 6]["decision_sha256"]
                        for cost in range(3)
                    }
                )
                == 1
            )


@pytest.mark.parametrize("case", ("cohort", "control", "normalizer"))
def test_existing_result_or_input_mismatch_stops_comparison(matrix, case):
    _, prior = matrix
    if case == "control":
        prior["cpu"]["cells"][0]["selected_decisions"] += 1
    else:
        prior["cpu"]["folds"][0][case + "_sha256"] = OTHER
    with pytest.raises(s.h30.StudyFailure, match="parent_control_mismatch"):
        run(matrix)


def test_all_candidate_decisions_precede_evaluation_outcomes(matrix, monkeypatch):
    first_eval = matrix[1]["cpu"]["folds"][0]
    assert first_eval["fold"] == 1
    calls = []
    original = s.family.parent_prediction

    def prediction(torch, fold, seed, *args):
        calls.append(seed)
        return original(torch, fold, seed, *args)

    def scored(*_args, **_kwargs):
        assert calls == [101, 103]
        raise RuntimeError("synthetic stop before future outcomes")

    monkeypatch.setattr(s.family, "parent_prediction", prediction)
    monkeypatch.setattr(s.family, "score", scored)
    with pytest.raises(RuntimeError, match="synthetic stop"):
        run(matrix)


def test_lstm_threshold_strictly_greater_than_six_unchanged_across_seeds(day, monkeypatch):
    fold = SimpleNamespace(symbol="SPY", fold=1, evaluation=day.obs, y_mean=2, y_scale=4)
    values = np.array([1, 1 + 1e-7, 0, 2, -1, 1])
    monkeypatch.setattr(s.family, "parent_prediction", lambda *args: values)
    results = s.decisions(fold, day.index, None, None, None)
    assert len(results) == 6
    for ident, selected in results[-2:]:
        assert (ident["context"], ident["horizon_minutes"]) == (36, 30)
        np.testing.assert_array_equal(selected, [False, True, False, True, False, False])
        assert not selected.flags.writeable


@pytest.mark.parametrize(
    "case", ("eligible", "censor", "blocks", "cost_decision", "interpretation")
)
def test_common_support_and_interpretation_remain_bound(matrix, case):
    result = run(matrix)
    support = result["folds"][0]["position_support"]
    if case == "eligible":
        support["eligible_decisions"] += 1
    elif case == "censor":
        support["common_censored_decisions"] += 1
    elif case == "blocks":
        support["common_scored_blocks"] = 0
    elif case == "cost_decision":
        result["cells"][6]["decision_sha256"] = OTHER
    else:
        result["interpretation"] = "discovered_alpha"
    with pytest.raises(s.h30.StudyFailure):
        s.validate_result(result, HASH)


@pytest.mark.parametrize("case", ("cell", "fold", "pin", "training", "count", "selection"))
def test_summary_binding_and_finite_matrix_reject_mutations(matrix, case):
    result = run(matrix)
    if case == "cell":
        result["cells"].pop()
    elif case == "fold":
        result["folds"][-1] = copy.deepcopy(result["folds"][0])
    elif case == "pin":
        result["contract_sha256"] = OTHER
    elif case == "count":
        result["parent_controls_reproduced"] -= 1
    else:
        result[case] = True
    with pytest.raises(s.h30.StudyFailure):
        s.validate_result(result, HASH)


def test_metadata_freeze_pins_sources_models_results_and_rejects_code_change(tmp_path, monkeypatch):
    monkeypatch.setattr(
        s, "lineage", lambda root: (root, b"receipt", {}, [{"weights_sha256": HASH}])
    )
    monkeypatch.setattr(
        s.sessions, "contract", lambda receipt: {"source_pins": [{"sha256": OTHER}]}
    )
    calls = []
    monkeypatch.setattr(s.h30, "register_frozen_campaign", lambda **kwargs: calls.append(kwargs))
    pin = s.freeze(tmp_path)
    output = s.verify(tmp_path, pin)
    cfg = json.loads((output / "contract.json").read_bytes())
    assert cfg["parent_models"] == [{"weights_sha256": HASH}]
    assert cfg["parent_summary_sha256"] == s.family.PARENT_HASHES
    assert cfg["budget"] == {"cpu_seconds": 600, "paired_cells": 72, "policy_cells": 144}
    assert calls[0]["holdout_access"] == "none"
    monkeypatch.setattr(s, "SECONDS", 601)
    with pytest.raises(s.h30.StudyFailure, match="contract_changed"):
        s.verify(tmp_path, pin)
    with pytest.raises(FileExistsError):
        s.freeze(tmp_path)


def test_repo_artifact_root_rejected_before_metadata_read(monkeypatch):
    monkeypatch.setattr(s, "lineage", lambda *_: pytest.fail("must reject path before reads"))
    with pytest.raises(ValueError):
        s.freeze(s.REPO / "generated-position-artifacts")


@pytest.fixture
def lineage_files(tmp_path, monkeypatch):
    parent = tmp_path / "parent"
    models = parent / "models"
    models.mkdir(parents=True)
    refs = []
    for symbol in s.h30.SYMBOLS:
        for fold in (1, 2):
            for seed in s.h30.SEEDS:
                name = f"{symbol}-{fold}-{seed}"
                (models / f"{name}.npz").write_bytes(b"synthetic numeric archive placeholder")
                ref = dict(
                    symbol=symbol,
                    fold=fold,
                    horizon_minutes=30,
                    context=36,
                    seed=seed,
                    config_file=f"{name}.json",
                    weights_file=f"{name}.npz",
                    weights_sha256=s.h30.digest((models / f"{name}.npz").read_bytes()),
                )
                cfg = dict(ref, name=s.sessions.NAME, contract_sha256=s.family.PARENT_CONTRACT)
                (models / ref["config_file"]).write_bytes(s.h30.encode(cfg))
                ref["config_sha256"] = s.h30.digest((models / ref["config_file"]).read_bytes())
                refs.append(ref)
    summaries = {"cpu": {}, "cuda": {"models": refs}}
    pins = {}
    for phase, result in summaries.items():
        raw = s.h30.encode(result)
        (parent / f"{phase}-summary.json").write_bytes(raw)
        pins[phase] = s.h30.digest(raw)
    monkeypatch.setattr(s.family, "PARENT_HASHES", pins)
    monkeypatch.setattr(s.sessions, "verify", lambda root, pin: (parent, b"receipt", {}))
    monkeypatch.setattr(s.sessions, "validate_result", lambda *args: None)
    return tmp_path, parent, refs


def test_lineage_pins_all_eight_context36_h30_models_without_loading_runtime(lineage_files):
    root, parent, refs = lineage_files
    output, receipt, _, actual = s.lineage(root)
    assert (output, receipt, actual) == (parent, b"receipt", refs)


@pytest.mark.parametrize("case", ("weights", "config", "summary", "identity", "matrix"))
def test_lineage_rejects_model_or_parent_result_substitution(lineage_files, case):
    root, parent, refs = lineage_files
    if case in ("weights", "config"):
        path = parent / "models" / refs[0][case + "_file"]
        path.write_bytes(path.read_bytes() + b"tampered")
    elif case == "summary":
        path = parent / "cpu-summary.json"
        path.write_bytes(path.read_bytes() + b"tampered")
    else:
        if case == "identity":
            path = parent / "models" / refs[0]["config_file"]
            cfg = json.loads(path.read_bytes())
            cfg["context"] = 12
            path.write_bytes(s.h30.encode(cfg))
            refs[0]["config_sha256"] = s.h30.digest(path.read_bytes())
        else:
            refs.pop()
        path = parent / "cuda-summary.json"
        path.write_bytes(s.h30.encode({"models": refs}))
        s.family.PARENT_HASHES["cuda"] = s.h30.digest(path.read_bytes())
    with pytest.raises(s.h30.StudyFailure):
        s.lineage(root)
