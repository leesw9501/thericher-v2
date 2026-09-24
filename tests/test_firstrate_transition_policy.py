"""Synthetic state-policy integration and immutable-run boundary checks."""

import copy
import json
import runpy
import socket
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from threadpoolctl import threadpool_limits

from test_firstrate_m5_h30_lstm_dev_20260921 import synthetic_receipt
from test_firstrate_policy_graph import integrated  # noqa: F401
from test_firstrate_session_research import source  # noqa: F401
from thericher_v2.research import firstrate_transition_policy as s


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    original = Path.open

    def safe_open(path, *args, **kwargs):
        normalized = str(path).replace("\\", "/").lower()
        assert not normalized.startswith(("d:/market_data", "d:/thericher-v2/model-artifacts"))
        assert not path.name.startswith(".env")
        return original(path, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("retained data, network or credential access")

    monkeypatch.setattr(Path, "open", safe_open)
    monkeypatch.setattr(s.h30, "load_streams", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    with threadpool_limits(limits=1):
        yield


@pytest.fixture(scope="module")
def inputs(source):  # noqa: F811
    schedule, bars = source
    schedule = schedule[:40]
    bars = tuple(b for b in bars if b.start_ts < schedule[-1][1])
    streams = [(symbol, tuple(replace(b, symbol=symbol) for b in bars)) for symbol in s.h30.SYMBOLS]
    return schedule, streams


@pytest.fixture(scope="module")
def result(inputs, integrated, tmp_path_factory):  # noqa: F811
    schedule, streams = inputs
    cfg = s.configuration()
    contract = dict(name=s.NAME, config=cfg, config_sha256=s.digest(s.encode(cfg)))
    pin = s.digest(s.encode(contract))
    root = tmp_path_factory.mktemp("state-integration")
    calls = []
    original = s.models._ridge_predict

    def predict(*args):
        calls.append(len(args[0]))
        return original(*args)

    with pytest.MonkeyPatch.context() as patch, threadpool_limits(limits=1):
        patch.setattr(s.sessions, "regular_sessions", lambda _: schedule)
        patch.setattr(s.models, "_ridge_predict", predict)
        evaluated = s.compare(
            streams,
            contract,
            pin,
            integrated[0],
            s.h30.EmergencyStore(root / "emergency.json"),
            time.monotonic() + 60,
        )
    assert len(calls) == 4
    return evaluated, contract, pin


def test_all_96_pairs_parent48_exact_and_no_new_forecast_family(result):
    value, contract, pin = result
    s.validate_result(value, contract, pin)
    assert len(value["cells"]) == 96 and len(value["comparisons"]) == 192
    assert value["parent_controls_reproduced"] == 48
    for fold in value["folds"]:
        assert fold["terminal_decisions"] == 10
        for counts in fold["action_counts"].values():
            assert counts["enter"] == counts["exit"] + counts["expiry_exit"]
            assert sum(counts[k] for k in ("enter", "hold", "exit", "flat")) == 60
    assert contract["config"]["fit_budget"]["ridge"] == 4
    assert (
        "cross_policy_exposure_may_differ_not_pure_fee_attribution" in contract["config"]["limits"]
    )


@pytest.mark.parametrize(
    "change",
    [
        "extra",
        "matrix",
        "controls",
        "weights",
        "scalar_container",
        "risk",
        "cost_sequence",
        "delta",
        "actions",
        "support",
    ],
)
def test_result_rejects_false_or_private_evidence(result, change):
    value, contract, pin = result
    r = copy.deepcopy(value)
    if change == "extra":
        r["raw_rows"] = [1]
    elif change == "matrix":
        r["cells"].pop()
    elif change == "controls":
        r["parent_controls_reproduced"] -= 1
    elif change == "weights":
        r["folds"][0]["model"]["weights"] = [1]
    elif change == "scalar_container":
        r["folds"][0]["model"]["model_sha256"] = {"weights": [1]}
    elif change == "risk":
        r["cells"][0]["risk"]["persistent"]["max_mark_to_market_drawdown_dollars"] = "-1"
    elif change == "cost_sequence":
        r["cells"][6]["decision_sha256"] = "sha256:" + "0" * 64
    elif change == "delta":
        r["comparisons"][0]["persistent_net_delta"] = "99"
    elif change == "support":
        r["folds"][0]["support"]["eligible_decisions"] += 1
    else:
        r["folds"][0]["action_counts"]["ridge_stateful"]["enter"] += 1
    with pytest.raises(ValueError):
        s.validate_result(r, contract, pin)


def test_calendar_terminal_is_not_last_available_row(inputs, monkeypatch):
    schedule, streams = inputs
    index = {b.start_ts: b for b in streams[0][1]}
    obs, _ = s.h30.observe(index, s.sessions.session_grid(schedule[:1], 30, training=False)[:5])
    arrays = dict(
        train_x=np.zeros((2, 36, 4)),
        train_y=np.zeros(2),
        eval_x=np.zeros((5, 36, 4)),
        eval_times=tuple(o.at for o in obs),
    )
    monkeypatch.setattr(
        s.models, "_ridge_predict", lambda *args: (np.array([0.0, 0.0, 0.0, 0.0, 4.0]), {})
    )
    targets, facts = s.decisions(
        arrays, obs, s.positions.session_keys(obs, schedule), schedule, time.monotonic() + 30
    )
    assert facts["terminal_decisions"] == 0
    assert targets["ridge_stateful"].tolist() == [False, False, False, False, True]
    assert facts["action_counts"]["ridge_stateful"]["expiry_exit"] == 1


def test_future_ohlc_changes_no_earlier_forecast_or_target(inputs):
    schedule, streams = inputs
    index = {b.start_ts: b for b in streams[0][1]}
    plan = s.sessions.plans(schedule, 30)[0]
    a, obs, _ = s.base.training_arrays(index, plan)
    keys = s.positions.session_keys(obs, schedule)
    old, old_facts = s.decisions(a, obs, keys, schedule, time.monotonic() + 30)
    at = obs[0].at
    for i in range(6):
        stamp = at + i * s.h30.STEP
        index[stamp] = replace(
            index[stamp],
            **{k: getattr(index[stamp], k) * 2 for k in ("open", "high", "low", "close", "volume")},
        )
    b, obs2, _ = s.base.training_arrays(index, plan)
    new, new_facts = s.decisions(b, obs2, keys, schedule, time.monotonic() + 30)
    assert old_facts["model"] == new_facts["model"]
    assert all(old[p][0] == new[p][0] for p in s.POLICIES)


def test_all_stateful_targets_precede_outcomes(inputs, integrated, monkeypatch, tmp_path):  # noqa: F811
    schedule, streams = inputs
    index = {b.start_ts: b for b in streams[0][1]}
    prepared = s.base.training_arrays(index, s.sessions.plans(schedule, 30)[0])
    seen = []
    original = s.decisions

    def decide(*args):
        answer = original(*args)
        seen.extend(answer[0])
        return answer

    class Checked(Exception):
        pass

    def future(*args):
        assert tuple(seen) == s.POLICIES
        raise Checked

    monkeypatch.setattr(s.base, "training_arrays", lambda *_: prepared)
    monkeypatch.setattr(s.sessions, "regular_sessions", lambda _: schedule)
    monkeypatch.setattr(s, "decisions", decide)
    monkeypatch.setattr(s.sessions, "outcomes", future)
    cfg = s.configuration()
    contract = dict(name=s.NAME, config=cfg, config_sha256=s.digest(s.encode(cfg)))
    with pytest.raises(Checked):
        s.compare(
            streams,
            contract,
            s.digest(s.encode(contract)),
            integrated[0],
            s.h30.EmergencyStore(tmp_path / "emergency.json"),
            time.monotonic() + 30,
        )


@pytest.fixture
def frozen(tmp_path, monkeypatch, integrated):  # noqa: F811
    market, artifact = tmp_path / "market", tmp_path / "artifacts"
    receipt = artifact / s.h30.RECEIPT
    receipt.parent.mkdir(parents=True)
    receipt.write_bytes(synthetic_receipt(market))
    parent_contract = s.base.proposed_contract(artifact)
    pin = s.digest(s.encode(parent_contract))
    prior = copy.deepcopy(integrated[0])
    prior["contract_sha256"] = pin
    directory = artifact / "research" / s.base.NAME
    directory.mkdir(parents=True)
    s.atomic_new(directory / "precommit.json", parent_contract)
    s.atomic_new(directory / "summary.json", prior)
    monkeypatch.setattr(s, "PARENT_PIN", pin)
    monkeypatch.setattr(s, "PARENT_RESULT", s.digest(s.encode(prior)))
    scope = s.freeze(artifact, market)
    output, contract = s.verify(artifact, market, scope)
    return SimpleNamespace(
        artifact=artifact,
        market=market,
        output=output,
        pin=scope,
        contract=contract,
        parent=directory,
    )


def test_freeze_is_metadata_only_immutable_external_with_exact_code(frozen):
    assert set(frozen.contract["code_sha256"]) == set(s.CODE)
    assert {p.name for p in frozen.output.iterdir()} == {"precommit.json"}
    with pytest.raises(FileExistsError):
        s.freeze(frozen.artifact, frozen.market)
    with pytest.raises(ValueError):
        s.freeze(s.REPO / "unused", s.REPO / "unused-market")


@pytest.mark.parametrize("file", ["precommit.json", "summary.json"])
def test_parent_tamper_stops_before_any_loader(frozen, file):
    (frozen.parent / file).write_bytes(b"{}")
    with pytest.raises(ValueError, match="parent_hash"):
        s.verify(frozen.artifact, frozen.market, frozen.pin)


def test_worker_supervisor_failure_is_single_pass_and_sanitized(frozen, capsys):
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
    assert json.loads(raw)["criterion"] == "worker_result_invalid" and b"PRIVATE" not in raw
    assert ns["main"](argv) == 1 and (frozen.output / "summary.json").read_bytes() == raw
    capsys.readouterr()


def test_cli_uses_existing_runner_and_importable_worker(monkeypatch):
    ns = runpy.run_path(str(s.REPO / "scripts/run_firstrate_transition_policy.py"))
    namespace = {}
    exec("def main(argv):\n return (study, worker, argv)", namespace)
    monkeypatch.setattr(ns["runpy"], "run_path", lambda _: namespace)
    assert ns["main"](["--freeze"]) == (s, s.worker_entry, ["--freeze"])
