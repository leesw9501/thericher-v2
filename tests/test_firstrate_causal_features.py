"""Synthetic causal-feature integration, replay custody and immutable boundaries."""

import copy
import importlib
import json
import os
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
from test_firstrate_transition_policy import inputs, integrated, source  # noqa: F401
from test_firstrate_transition_policy import result as parent_result  # noqa: F401
from thericher_v2.research import firstrate_causal_features as s


@pytest.fixture(scope="module", autouse=True)
def isolated():
    original = Path.open

    def safe_open(path, *args, **kwargs):
        normalized = str(path.resolve()).replace("\\", "/").lower()
        assert not normalized.startswith(("d:/market_data", "d:/thericher-v2/model-artifacts"))
        assert not path.name.startswith(".env")
        return original(path, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("retained data, network or credential access")

    with pytest.MonkeyPatch.context() as patch, threadpool_limits(limits=1):
        patch.setattr(Path, "open", safe_open)
        patch.setattr(s.h30, "load_streams", forbidden)
        patch.setattr(socket, "create_connection", forbidden)
        patch.setattr(socket.socket, "connect", forbidden)
        patch.setattr(socket.socket, "connect_ex", forbidden)
        yield


@pytest.fixture(scope="module")
def bound(parent_result):  # noqa: F811
    value, parent_contract, parent_pin = parent_result
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(s, "PARENT_PIN", parent_pin)
        patch.setattr(s, "PARENT_RESULT", s.digest(s.encode(value)))
        cfg = s.configuration()
        contract = dict(
            name=s.NAME,
            config=cfg,
            config_sha256=s.digest(s.encode(cfg)),
            parent_contract=parent_contract,
        )
        yield contract, s.digest(s.encode(contract))


@pytest.fixture(scope="module")
def result(bound, inputs, integrated, tmp_path_factory):  # noqa: F811
    contract, pin = bound
    schedule, streams = inputs
    root = tmp_path_factory.mktemp("feature-integration")
    calls, events = [], []
    pending = {}
    phase = {"features": False}
    eval_starts = {plan[1][0] for plan in s.sessions.plans(schedule, 30)}
    raw_predict = s.parent_study.models._ridge_predict
    feature_predict = s.learner.fit_predict
    parent_compare = s.parent_study.compare
    decide, outcomes = s.decisions, s.sessions.outcomes

    def raw(*args):
        calls.append("raw")
        return raw_predict(*args)

    def features(**kwargs):
        calls.append("feature")
        return feature_predict(**kwargs)

    def baseline(*args):
        value = parent_compare(*args)
        phase["features"] = True
        return value

    def decisions(*args):
        targets, facts = decide(*args)
        assert not pending
        assert tuple(targets) == s.POLICIES
        assert all(v.dtype == np.dtype(bool) and not v.flags.writeable for v in targets.values())
        pending["times"] = tuple(o.at for o in args[1])
        events.append("targets")
        return targets, facts

    def read_outcomes(index, observations, horizon):
        if phase["features"] and observations and observations[0].at in eval_starts:
            assert pending.pop("times", None) == tuple(o.at for o in observations)
            events.append("outcomes")
        return outcomes(index, observations, horizon)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(s.sessions, "regular_sessions", lambda _: schedule)
        patch.setattr(s.parent_study.models, "_ridge_predict", raw)
        patch.setattr(s.learner, "fit_predict", features)
        patch.setattr(s.parent_study, "compare", baseline)
        patch.setattr(s, "decisions", decisions)
        patch.setattr(s.sessions, "outcomes", read_outcomes)
        value = s.compare(
            streams,
            contract,
            pin,
            integrated[0],
            s.h30.EmergencyStore(root / "emergency.json"),
            time.monotonic() + 120,
        )
    assert calls == ["raw"] * 4 + ["feature"] * 4
    assert events == ["targets", "outcomes"] * 4 and not pending
    return value, contract, pin


def test_real_four_plus_four_fits_exact_parent96_and_new32(result, parent_result):  # noqa: F811
    value, contract, pin = result
    s.validate_result(value, contract, pin)
    baseline = value["baseline_replay"]
    assert s.encode(baseline) == s.encode(parent_result[0])
    assert len(baseline["cells"]) == 96 and len(baseline["comparisons"]) == 192
    assert len(value["cells"]) == 32 and len(value["folds"]) == 4
    assert {c["candidate"] for c in value["cells"]} == set(s.POLICIES)
    assert contract["config"]["fit_budget"] == dict(
        raw_ridge=4, feature_ridge=4, wall_seconds=900, passes=1, gpu=False
    )
    assert all(
        contract["config"][k] is False
        for k in ("promotion", "holdout", "selection", "broker_input", "fitted_weights_retained")
    )
    assert all(
        key not in s.encode(value).decode()
        for key in ('"predictions":', '"weights":', '"raw_rows":', '"open":', '"account":')
    )


def test_same_support_and_fixed_decisions_across_every_cost(result):
    value, _, _ = result
    prior = {(f["symbol"], f["fold"]): f for f in value["baseline_replay"]["folds"]}
    paths = {}
    for fold in value["folds"]:
        parent = prior[fold["symbol"], fold["fold"]]
        counts = fold["action_counts"]
        assert fold["terminal_decisions"] == parent["terminal_decisions"] == 10
        assert counts["enter"] == counts["exit"] + counts["expiry_exit"]
        assert sum(counts[k] for k in ("enter", "hold", "exit", "flat")) == 60
    for cell in value["cells"]:
        support = prior[cell["symbol"], cell["fold"]]["support"]
        assert support["eligible_decisions"] == support["common_scored_decisions"] == 60
        assert cell["selected_censored"] == support["common_censored_decisions"] == 0
        assert 0 <= cell["selected_decisions"] <= support["eligible_decisions"]
        for kind in ("repeated", "persistent"):
            totals = cell[kind]
            assert totals["terminal_flat"] is totals["local_paper_replay_parity"] is True
            assert Decimal(totals["net_dollars"]) == (
                Decimal(totals["gross_dollars"]) - Decimal(totals["fees_dollars"])
            )
            key = cell["symbol"], cell["fold"], cell["candidate"], kind
            path = (
                cell["decision_sha256"],
                cell["selected_decisions"],
                *(
                    totals[k]
                    for k in (
                        "gross_dollars",
                        "turnover_dollars",
                        "exposure_minutes",
                        "exposure_sha256",
                        "roundtrips",
                        "fills",
                    )
                ),
            )
            assert paths.setdefault(key, path) == path


def test_future_mutation_changes_payoff_not_earlier_features_or_targets(inputs, tmp_path):  # noqa: F811
    schedule, streams = inputs
    index = {b.start_ts: b for b in streams[0][1]}
    plan = s.sessions.plans(schedule, 30)[0]
    arrays, observations, _ = s.base.training_arrays(index, plan)
    keys = s.positions.session_keys(observations, schedule)
    before, before_facts = s.decisions(arrays, observations, keys, schedule, time.monotonic() + 30)
    old_outcomes, _ = s.sessions.outcomes(index, observations, 30)
    at = observations[0].at
    for i in range(6):
        stamp = at + i * s.h30.STEP
        index[stamp] = replace(
            index[stamp],
            **{
                k: getattr(index[stamp], k) * (i + 2)
                for k in (
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                )
            },
        )
    changed, new_observations, _ = s.base.training_arrays(index, plan)
    for key in ("train_x", "train_closes", "train_y", "train_net_y"):
        np.testing.assert_array_equal(arrays[key], changed[key])
    for key in ("eval_x", "eval_closes"):
        np.testing.assert_array_equal(arrays[key][0], changed[key][0])
        assert not np.array_equal(arrays[key][1], changed[key][1])
    after, after_facts = s.decisions(
        changed, new_observations, keys, schedule, time.monotonic() + 30
    )
    assert before_facts["model"] == after_facts["model"]
    assert all(before[p][0] == after[p][0] for p in s.POLICIES)
    np.testing.assert_array_equal(
        s.learner.feature_matrix(arrays["eval_x"], arrays["eval_closes"])[0],
        s.learner.feature_matrix(changed["eval_x"], changed["eval_closes"])[0],
    )
    new_outcomes, _ = s.sessions.outcomes(index, new_observations, 30)
    emergency = s.h30.EmergencyStore(tmp_path / "emergency.json")
    old_gross, old_fees = s.sessions.payoff(observations[0], old_outcomes[0], 3, emergency)
    new_gross, new_fees = s.sessions.payoff(new_observations[0], new_outcomes[0], 3, emergency)
    assert old_gross - old_fees != new_gross - new_fees


@pytest.mark.parametrize(
    "path,value",
    [
        (("raw_rows",), [1]),
        (("predictions",), [0.5]),
        (("folds", 0, "predictions"), [0.5]),
        (("folds", 0, "model", "weights"), [1]),
        (("folds", 0, "model", "model_sha256"), {"weights": [1]}),
        (("folds", 0, "model", "scaler_sha256"), [1]),
        (("folds", 0, "forecast_sha256"), {"predictions": [1]}),
        (("folds", 0, "action_counts", "enter"), [1]),
        (("folds", 0, "action_counts", "raw_rows"), [1]),
        (("folds", 0, "terminal_decisions"), [10]),
        (("cells", 0, "selected_decisions"), {"raw_rows": [1]}),
        (("cells", 0, "repeated", "raw_rows"), [1]),
        (("cells", 0, "persistent", "net_dollars"), ["0"]),
        (("cells", 0, "risk", "raw_rows"), [1]),
        (("cells", 0, "risk", "persistent", "predictions"), [1]),
        (("cells", 0, "risk", "persistent", "max_holding_minutes"), [30]),
        (("baseline_replay", "folds", 0, "model", "predictions"), [1]),
    ],
)
def test_nested_extras_predictions_and_scalar_containers_rejected(result, path, value):
    original, contract, pin = result
    candidate = copy.deepcopy(original)
    target = candidate
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        s.validate_result(candidate, contract, pin)


@pytest.mark.parametrize(
    "change",
    [
        "cell_missing",
        "cell_duplicate",
        "cell_order",
        "fold_missing",
        "fold_duplicate",
        "parent",
        "terminal",
        "action_total",
        "action_balance",
        "action_replay",
        "support",
        "cost_target",
        "cost_exposure",
        "risk",
        "horizon",
        "seed",
    ],
)
def test_matrix_actions_support_and_parent_identity_rejected(result, change):
    original, contract, pin = result
    value = copy.deepcopy(original)
    cell, fold = value["cells"][0], value["folds"][0]
    if change == "cell_missing":
        value["cells"].pop()
    elif change == "cell_duplicate":
        value["cells"][1] = copy.deepcopy(cell)
    elif change == "cell_order":
        value["cells"].reverse()
    elif change == "fold_missing":
        value["folds"].pop()
    elif change == "fold_duplicate":
        value["folds"][1] = copy.deepcopy(fold)
    elif change == "parent":
        value["baseline_replay"]["parent_controls_reproduced"] -= 1
    elif change == "terminal":
        fold["terminal_decisions"] -= 1
    elif change == "action_total":
        fold["action_counts"]["flat"] += 1
    elif change == "action_balance":
        fold["action_counts"]["expiry_exit"] += 1
    elif change == "action_replay":
        counts = fold["action_counts"]
        shift = 1 if counts["flat"] else -1
        counts["hold"] += shift
        counts["flat"] -= shift
    elif change == "support":
        cell["selected_censored"] += 1
    elif change == "cost_target":
        value["cells"][2]["decision_sha256"] = "sha256:" + "0" * 64
    elif change == "cost_exposure":
        value["cells"][2]["persistent"]["exposure_sha256"] = "sha256:" + "0" * 64
    elif change == "risk":
        cell["risk"]["persistent"]["max_mark_to_market_drawdown_dollars"] = "-1"
    elif change == "horizon":
        cell["horizon_minutes"] = 60
    else:
        cell["seed"] = 1
    with pytest.raises(ValueError):
        s.validate_result(value, contract, pin)


def test_parent_contract_hash_rejected_before_replay(bound, inputs, integrated, tmp_path):  # noqa: F811
    contract = copy.deepcopy(bound[0])
    contract["parent_contract"]["unexpected"] = True
    with pytest.raises(ValueError, match="parent_contract"):
        s.compare(
            inputs[1],
            contract,
            s.digest(s.encode(contract)),
            integrated[0],
            s.h30.EmergencyStore(tmp_path / "emergency.json"),
            time.monotonic() + 30,
        )


@pytest.fixture
def frozen(tmp_path, monkeypatch, parent_result):  # noqa: F811
    market, artifact = tmp_path / "market", tmp_path / "artifacts"
    receipt = artifact / s.h30.RECEIPT
    receipt.parent.mkdir(parents=True)
    receipt.write_bytes(synthetic_receipt(market))

    # Replace only the ancestor artifact read, preserving current code/source/runtime reads.
    def proposed_parent(root):
        metadata = s.base.proposed_contract(root)
        cfg = s.parent_study.configuration()
        return dict(
            **{
                k: metadata[k]
                for k in ("schema_version", "source_pins", "receipt_sha256", "runtime")
            },
            name=s.parent_study.NAME,
            config=cfg,
            config_sha256=s.digest(s.encode(cfg)),
            code_sha256={p: s.digest((s.REPO / p).read_bytes()) for p in s.parent_study.CODE},
        )

    monkeypatch.setattr(s.parent_study, "proposed_contract", proposed_parent)
    parent_contract = proposed_parent(artifact)
    parent_pin = s.digest(s.encode(parent_contract))
    prior = copy.deepcopy(parent_result[0])
    prior["contract_sha256"] = parent_pin
    directory = artifact / "research" / s.parent_study.NAME
    directory.mkdir(parents=True)
    s.atomic_new(directory / "precommit.json", parent_contract)
    s.atomic_new(directory / "summary.json", prior)
    monkeypatch.setattr(s, "PARENT_PIN", parent_pin)
    monkeypatch.setattr(s, "PARENT_RESULT", s.digest(s.encode(prior)))
    pin = s.freeze(artifact, market)
    output, contract = s.verify(artifact, market, pin)
    return SimpleNamespace(
        market=market,
        artifact=artifact,
        receipt=receipt,
        parent=directory,
        output=output,
        contract=contract,
        pin=pin,
    )


def test_freeze_is_metadata_only_external_immutable_and_exactly_pinned(frozen):
    assert set(frozen.contract["code_sha256"]) == set(s.CODE)
    assert frozen.contract["parent_contract"]["source_pins"] == frozen.contract["source_pins"]
    assert {p.name for p in frozen.output.iterdir()} == {"precommit.json"}
    raw = (frozen.output / "precommit.json").read_bytes()
    with pytest.raises(FileExistsError):
        s.freeze(frozen.artifact, frozen.market)
    assert (frozen.output / "precommit.json").read_bytes() == raw
    with pytest.raises(ValueError):
        s.freeze(s.REPO / "unused-artifacts", s.REPO / "unused-market")


@pytest.mark.parametrize("change", ["source", "code", "runtime", "precommit.json", "summary.json"])
def test_binding_mismatch_fails_worker_before_loader(frozen, monkeypatch, change):
    if change in ("precommit.json", "summary.json"):
        (frozen.parent / change).write_bytes(b"{}")
    elif change == "source":
        receipt = json.loads(frozen.receipt.read_bytes())
        receipt["normalizations"][0]["canonical_sha256"] = "sha256:" + "0" * 64
        frozen.receipt.write_bytes(s.encode(receipt))
    elif change == "code":
        original = Path.read_bytes

        def changed_code(path):
            raw = original(path)
            return raw + b"\n# changed" if path == Path(s.__file__) else raw

        monkeypatch.setattr(Path, "read_bytes", changed_code)
    else:
        original = s.base.importlib.metadata.version
        monkeypatch.setattr(
            s.base.importlib.metadata,
            "version",
            lambda name: original(name) + ".changed" if name == "numpy" else original(name),
        )
    s.atomic_new(frozen.output / "started.json", {"contract_sha256": frozen.pin})
    calls = []

    def loader(*args):
        calls.append(args)
        pytest.fail("loader reached after binding mismatch")

    monkeypatch.setattr(s.h30, "load_streams", loader)
    path = frozen.output / "worker-result.json"
    with pytest.raises(ValueError):
        s.run_worker(frozen.artifact, frozen.market, frozen.pin, path, time.monotonic() + 30)
    assert calls == [] and not path.exists()


@pytest.mark.parametrize("partial", [False, True])
def test_existing_runner_one_attempt_and_no_raw_error(frozen, monkeypatch, capsys, partial):
    runner = runpy.run_path(str(s.REPO / "scripts/run_tiingo_month_start_development.py"))
    namespace = runner["main"].__globals__
    namespace["study"], namespace["worker"] = s, s.worker_entry
    calls = []

    def supervise(target, args, *, seconds):
        calls.append(args)
        assert target is s.worker_entry and 0 < seconds <= s.SECONDS
        raise RuntimeError("PRIVATE_EXCEPTION_BODY")

    namespace["supervise"] = supervise
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        monkeypatch.setenv(name, os.environ.get(name, "1"))
    if partial:
        s.atomic_new(frozen.output / "started.json", {"contract_sha256": frozen.pin})
    argv = [
        "--run",
        "--artifact-root",
        str(frozen.artifact),
        "--market-data-root",
        str(frozen.market),
        "--contract-sha256",
        frozen.pin,
    ]
    assert runner["main"](argv) == 1
    files = {p.name: p.read_bytes() for p in frozen.output.iterdir()}
    assert runner["main"](argv) == 1
    assert {p.name: p.read_bytes() for p in frozen.output.iterdir()} == files
    assert len(calls) == (0 if partial else 1)
    if not partial:
        summary = json.loads(files["summary.json"])
        assert summary == s.failure(frozen.contract, frozen.pin, "worker_result_invalid")
        s.validate_result(summary, frozen.contract, frozen.pin)
    captured = capsys.readouterr()
    assert "PRIVATE_EXCEPTION_BODY" not in captured.out + captured.err
    assert all(b"PRIVATE_EXCEPTION_BODY" not in raw for raw in files.values())


def test_cli_binds_existing_runner_to_importable_feature_worker(monkeypatch):
    wrapper = runpy.run_path(str(s.REPO / "scripts/run_firstrate_causal_features.py"))
    namespace = {}
    exec("def main(argv):\n return (study, worker, argv)", namespace)

    def runner(path):
        assert Path(path) == s.REPO / "scripts/run_tiingo_month_start_development.py"
        return namespace

    monkeypatch.setattr(wrapper["runpy"], "run_path", runner)
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "BLIS_NUM_THREADS",
    ):
        monkeypatch.setenv(name, "2")
    assert wrapper["main"](["--freeze"]) == (s, s.worker_entry, ["--freeze"])
    module = importlib.import_module(s.worker_entry.__module__)
    assert getattr(module, s.worker_entry.__name__) is s.worker_entry
