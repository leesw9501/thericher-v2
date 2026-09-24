"""Synthetic composed-engine integration; no retained rows, credentials or broker."""

import copy
import json
import runpy
import socket
import time
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from threadpoolctl import threadpool_limits

from test_firstrate_m5_h30_lstm_dev_20260921 import synthetic_receipt
from test_firstrate_session_research import source  # noqa: F401
from thericher_v2.research import firstrate_policy_graph as s


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    original = Path.open

    def safe_open(path, *args, **kwargs):
        normalized = str(path).replace("\\", "/").lower()
        assert not normalized.startswith(("d:/market_data", "d:/thericher-v2/model-artifacts"))
        assert not path.name.startswith(".env")
        return original(path, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("retained data or network access")

    monkeypatch.setattr(Path, "open", safe_open)
    monkeypatch.setattr(s.h30, "load_streams", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    with threadpool_limits(limits=1):
        yield


@pytest.fixture
def frozen(tmp_path):
    market, artifact = tmp_path / "market", tmp_path / "artifacts"
    receipt = artifact / s.h30.RECEIPT
    receipt.parent.mkdir(parents=True)
    receipt.write_bytes(synthetic_receipt(market))
    pin = s.freeze(artifact, market)
    output, contract = s.verify(artifact, market, pin)
    return SimpleNamespace(
        market=market, artifact=artifact, output=output, receipt=receipt, contract=contract, pin=pin
    )


@pytest.fixture
def prepared(source):  # noqa: F811
    schedule, bars = source
    index = {b.start_ts: b for b in bars if b.start_ts < schedule[39][1]}
    schedule = schedule[:40]
    plan = s.sessions.plans(schedule, 30)[0]
    arrays, obs, facts = s.training_arrays(index, plan)
    return SimpleNamespace(
        index=index, schedule=schedule, plan=plan, arrays=arrays, obs=obs, facts=facts
    )


def test_metadata_only_freeze_exact_budget_and_existing_code_pins(frozen):
    cfg = frozen.contract["config"]
    assert cfg["fit_budget"] == dict(ridge=16, tree=4, gpu=False, wall_seconds=900, passes=1)
    assert cfg["paired_cells"] == 160 and cfg["policy_cells"] == 320
    assert cfg["costs_bps_per_side"] == [1, 3, 5, 10]
    assert cfg["selection"] is cfg["promotion"] is cfg["broker_input"] is False
    assert "re-accounts fixed targets" in cfg["decision_basis"]
    assert set(frozen.contract["code_sha256"]) == set(s.CODE)
    assert {p.name for p in frozen.output.iterdir()} == {"precommit.json"}
    with pytest.raises(FileExistsError):
        s.freeze(frozen.artifact, frozen.market)


def test_repo_data_and_artifacts_rejected_before_loading():
    with pytest.raises(ValueError):
        s.freeze(s.REPO / "unused-artifacts", s.REPO / "unused-data")


@pytest.mark.parametrize("change", ["receipt", "code", "runtime"])
def test_changed_contract_input_fails_before_loader(frozen, monkeypatch, change):
    if change == "receipt":
        frozen.receipt.write_bytes(b"{}")
    else:
        original = s.proposed_contract

        def altered(root):
            result = original(root)
            result["code_sha256" if change == "code" else "runtime"] = {}
            return result

        monkeypatch.setattr(s, "proposed_contract", altered)
    with pytest.raises(ValueError):
        s.verify(frozen.artifact, frozen.market, frozen.pin)


def test_training_label_fee_matches_actual_paper_and_purge(prepared, tmp_path):
    arrays = prepared.arrays
    obs, _ = s.h30.observe(prepared.index, arrays["train_times"][:1])
    out, _ = s.sessions.outcomes(prepared.index, obs, 30)
    gross, fees = s.sessions.payoff(
        obs[0], out[0], 3, s.h30.EmergencyStore(tmp_path / "emergency.json")
    )
    assert arrays["train_net_y"][0] == float((gross - fees) / out[0].entry * 10000)
    assert arrays["train_times"][-1] + s.h30.HOLD < prepared.plan[2]
    assert arrays["train_x"].shape[1:] == (36, 4)
    assert arrays["train_closes"].shape[1:] == (36,)
    assert all(t + s.h30.HOLD < prepared.schedule[29][1] for t in arrays["eval_times"])


def test_future_change_does_not_change_first_decision_inputs(prepared):
    from thericher_v2.research.policy_graph_models import fit_predict_graph

    at = prepared.obs[0].at
    index = dict(prepared.index)
    for i in range(4):
        t = at + i * s.h30.STEP
        index[t] = replace(
            index[t],
            volume=index[t].volume * 100,
            **{k: getattr(index[t], k) * 2 for k in ("open", "high", "low", "close")},
        )
    arrays, _, _ = s.training_arrays(index, prepared.plan)
    for key in ("train_x", "train_closes", "train_y", "train_net_y"):
        np.testing.assert_array_equal(arrays[key], prepared.arrays[key])
    np.testing.assert_array_equal(arrays["eval_x"][0], prepared.arrays["eval_x"][0])
    np.testing.assert_array_equal(arrays["eval_closes"][0], prepared.arrays["eval_closes"][0])
    original = fit_predict_graph(**prepared.arrays, deadline=time.monotonic() + 30)
    changed = fit_predict_graph(**arrays, deadline=time.monotonic() + 30)
    assert all(original.targets[k][0] == changed.targets[k][0] for k in s.POLICIES)


@pytest.fixture(scope="module")
def integrated(source, tmp_path_factory):  # noqa: F811
    schedule, bars = source
    schedule = schedule[:40]
    bars = tuple(b for b in bars if b.start_ts < schedule[-1][1])
    streams = [(symbol, tuple(replace(b, symbol=symbol) for b in bars)) for symbol in s.h30.SYMBOLS]
    contract = dict(config=s.configuration(), config_sha256=s.digest(s.encode(s.configuration())))
    pin = s.digest(s.encode(contract))
    root = tmp_path_factory.mktemp("graph-integrated")
    with pytest.MonkeyPatch.context() as patch, threadpool_limits(limits=1):
        patch.setattr(s.sessions, "regular_sessions", lambda _: schedule)
        result = s.compare(
            streams,
            contract,
            pin,
            s.h30.EmergencyStore(root / "emergency.json"),
            time.monotonic() + 120,
        )
    return result, contract, pin


def test_full_real_ridge_tree_local_paper_matrix_and_cost_invariance(integrated):
    result, contract, pin = integrated
    s.validate_result(result, contract, pin)
    assert len(result["cells"]) == len(result["comparisons"]) == 160
    assert sum(f["model_facts"]["ridge_fits"] for f in result["folds"]) == 16
    assert sum(f["model_facts"]["tree_fits"] for f in result["folds"]) == 4
    for cell in result["cells"]:
        assert cell["repeated"]["local_paper_replay_parity"] is True
        assert cell["persistent"]["terminal_flat"] is True
        if cell["candidate"] == "always_flat":
            assert cell["selected_decisions"] == 0
            assert Decimal(cell["persistent"]["net_dollars"]) == 0
        if cell["candidate"] == "always_long":
            assert cell["repeated"]["roundtrips"] == 60
            assert cell["persistent"]["roundtrips"] == 10
            assert cell["risk"]["persistent"]["max_holding_minutes"] == 180
    assert all(
        key not in s.encode(result).decode()
        for key in ('"open":', '"close":', '"predictions":', '"weights":', '"account":')
    )


@pytest.mark.parametrize(
    "change",
    [
        "matrix",
        "fits",
        "risk",
        "cost_decision",
        "delta",
        "raw",
        "weights",
        "nested_rows",
        "inner_rows",
        "cost_exposure",
        "hash_container",
        "count_container",
    ],
)
def test_result_rejects_broken_accounting_contract(integrated, change):
    original, contract, pin = integrated
    result = copy.deepcopy(original)
    if change == "matrix":
        result["cells"].pop()
    elif change == "fits":
        result["folds"][0]["model_facts"]["ridge_fits"] = 5
    elif change == "risk":
        result["cells"][0]["risk"]["persistent"]["max_mark_to_market_drawdown_dollars"] = "-1"
    elif change == "cost_decision":
        result["cells"][10]["decision_sha256"] = "sha256:" + "0" * 64
    elif change == "delta":
        result["comparisons"][0]["persistent_net_delta_vs_majority"] = "999999"
    elif change == "weights":
        result["folds"][0]["model_facts"]["weights"] = [1.0]
    elif change == "inner_rows":
        result["folds"][0]["model_facts"]["inner"][0]["raw_rows"] = [1.0]
    elif change == "hash_container":
        result["folds"][0]["model_facts"]["final"]["model_sha256"] = {"weights": [1.0]}
    elif change == "count_container":
        result["folds"][0]["training_inputs"]["eligible"] = {"raw_rows": [1.0]}
    elif change == "nested_rows":
        result["cells"][0]["repeated"]["raw_rows"] = [1.0]
    elif change == "cost_exposure":
        for kind in ("repeated", "persistent"):
            result["cells"][10][kind]["exposure_sha256"] = "sha256:" + "0" * 64
    else:
        result["raw_rows"] = "forbidden"
    with pytest.raises(ValueError):
        s.validate_result(result, contract, pin)


def test_all_targets_frozen_before_future_outcome_read(prepared, monkeypatch, tmp_path):
    from thericher_v2.research import policy_graph_models as models

    contract = dict(config=s.configuration(), config_sha256=s.digest(s.encode(s.configuration())))
    state = {"frozen": False}

    def fit(**kwargs):
        state["frozen"] = True
        return SimpleNamespace(
            targets={p: np.zeros(len(prepared.obs), dtype=bool) for p in s.POLICIES}
        )

    class Checked(Exception):
        pass

    def future(*args):
        assert state["frozen"]
        raise Checked

    monkeypatch.setattr(s.sessions, "regular_sessions", lambda _: prepared.schedule)
    monkeypatch.setattr(s, "training_arrays", lambda *_: (prepared.arrays, prepared.obs, {}))
    monkeypatch.setattr(models, "fit_predict_graph", fit)
    monkeypatch.setattr(s.sessions, "outcomes", future)
    with pytest.raises(Checked):
        s.compare(
            [("SPY", tuple(prepared.index.values()))],
            contract,
            s.digest(s.encode(contract)),
            s.h30.EmergencyStore(tmp_path / "emergency.json"),
            time.monotonic() + 30,
        )


def test_reused_supervisor_attempt_once_and_failure_sanitized(frozen, monkeypatch, capsys):
    ns = runpy.run_path(str(s.REPO / "scripts/run_tiingo_month_start_development.py"))
    g = ns["main"].__globals__
    g["study"], g["worker"] = s, s.worker_entry

    def supervise(target, args, *, seconds):
        assert target is s.worker_entry and 0 < seconds <= 900
        raise RuntimeError("PRIVATE")

    g["supervise"] = supervise
    argv = [
        "--run",
        "--artifact-root",
        str(frozen.artifact),
        "--market-data-root",
        str(frozen.market),
        "--contract-sha256",
        frozen.pin,
    ]
    assert ns["main"](argv) == 1
    raw = (frozen.output / "summary.json").read_bytes()
    assert json.loads(raw)["criterion"] == "worker_result_invalid"
    assert b"PRIVATE" not in raw
    assert ns["main"](argv) == 1
    assert raw == (frozen.output / "summary.json").read_bytes()
    capsys.readouterr()


def test_cli_binds_new_study_importable_worker(monkeypatch):
    ns = runpy.run_path(str(s.REPO / "scripts/run_firstrate_policy_graph.py"))
    namespace = {}
    exec("def main(argv):\n return (study, worker, argv)", namespace)
    monkeypatch.setattr(ns["runpy"], "run_path", lambda _: namespace)
    assert ns["main"](["--freeze"]) == (s, s.worker_entry, ["--freeze"])
