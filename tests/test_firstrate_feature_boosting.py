"""Synthetic boosting integration, exact control replay and single-pass custody."""

import builtins
import copy
import importlib
import io
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
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from threadpoolctl import threadpool_limits

# Keep the transition ancestor named parent_result for bound's transitive dependency.
from test_firstrate_causal_features import (  # noqa: F401
    bound,
    inputs,
    integrated,
    parent_result,
    source,
)
from test_firstrate_causal_features import result as prior_result  # noqa: F401
from test_firstrate_m5_h30_lstm_dev_20260921 import synthetic_receipt
from thericher_v2.research import firstrate_feature_boosting as s


def forbidden(*args, **kwargs):
    pytest.fail("unexpected retained data, credential, network or ancestor refit access")


@pytest.fixture(scope="module", autouse=True)
def isolated():
    def guard(opener):
        def safe_open(file, *args, **kwargs):
            if not isinstance(file, int):
                path = Path(os.fsdecode(file)).resolve()
                normalized = path.as_posix().lower()
                assert not normalized.startswith(
                    ("d:/market_data", "d:/thericher-v2/model-artifacts")
                )
                assert not any(part.lower().startswith(".env") for part in path.parts)
            return opener(file, *args, **kwargs)

        return safe_open

    with pytest.MonkeyPatch.context() as patch, threadpool_limits(limits=1):
        for module in (builtins, io, os):
            patch.setattr(module, "open", guard(module.open))
        patch.setattr(s.h30, "load_streams", forbidden)
        patch.setattr(socket, "create_connection", forbidden)
        patch.setattr(socket, "getaddrinfo", forbidden)
        patch.setattr(socket.socket, "connect", forbidden)
        patch.setattr(socket.socket, "connect_ex", forbidden)
        yield


@pytest.fixture(scope="module")
def contract(prior_result):  # noqa: F811
    config = s.configuration()
    value = dict(
        name=s.NAME,
        config=config,
        config_sha256=s.digest(s.encode(config)),
        reference=s.references(prior_result[0]),
    )
    return value, s.digest(s.encode(value))


@pytest.fixture(scope="module")
def result(contract, inputs, tmp_path_factory):  # noqa: F811
    frozen, pin = contract
    schedule, streams = inputs
    root = tmp_path_factory.mktemp("boost-integration")
    fits, pairs, events, pending, targets_by_policy = [], [], [], {}, {}
    ridge_fit, boost_fit = Ridge.fit, GradientBoostingRegressor.fit
    decide, outcomes, replay = s.decisions, s.sessions.outcomes, s.compare_policy
    eval_starts = {plan[1][0] for plan in s.sessions.plans(schedule, 30)}

    def ridge(model, x, y, *args, **kwargs):
        assert x.shape[1] == 15 and len(x) == len(y) >= 128
        fits.append("ridge")
        return ridge_fit(model, x, y, *args, **kwargs)

    def boost(model, x, y, *args, **kwargs):
        assert x.shape[1] == 15 and len(x) == len(y) >= 128
        fits.append("boost")
        return boost_fit(model, x, y, *args, **kwargs)

    def decisions(*args):
        targets, facts, controls = decide(*args)
        assert not pending and tuple(targets) == s.POLICIES
        assert all(t.dtype == np.dtype(bool) and not t.flags.writeable for t in targets.values())
        assert facts["forecast_distribution"]["above_hurdle"] == int(targets["boost_hurdle"].sum())
        pending["times"] = tuple(o.at for o in args[1])
        events.append("targets")
        return targets, facts, controls

    def read_outcomes(index, observations, horizon):
        if observations and observations[0].at in eval_starts:
            assert pending.pop("times", None) == tuple(o.at for o in observations)
            events.append("outcomes")
        return outcomes(index, observations, horizon)

    def pair(**kwargs):
        ident = kwargs["ident"]
        key = ident["symbol"], ident["fold"], ident["candidate"]
        selected = kwargs["selected"]
        assert targets_by_policy.setdefault(key, selected) is selected
        assert not selected.flags.writeable
        pairs.append((*key, kwargs["cost"]))
        return replay(**kwargs)

    models = s.prior_study.parent_study.models
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(s.sessions, "regular_sessions", lambda _: schedule)
        patch.setattr(Ridge, "fit", ridge)
        patch.setattr(GradientBoostingRegressor, "fit", boost)
        patch.setattr(s, "decisions", decisions)
        patch.setattr(s.sessions, "outcomes", read_outcomes)
        patch.setattr(s, "compare_policy", pair)
        patch.setattr(s, "parent", forbidden)
        for ancestor in (s.prior_study, s.prior_study.parent_study, s.base):
            patch.setattr(ancestor, "compare", forbidden)
        patch.setattr(models, "_ridge_predict", forbidden)
        patch.setattr(models, "fit_predict_graph", forbidden)
        patch.setattr(models, "DecisionTreeRegressor", forbidden)
        value = s.compare(
            streams,
            frozen,
            pin,
            s.h30.EmergencyStore(root / "emergency.json"),
            time.monotonic() + 120,
        )
    assert fits == ["ridge", "boost"] * 4
    assert events == ["targets", "outcomes"] * 4 and not pending
    assert len(pairs) == len(set(pairs)) == 64
    assert sum(p[2] in s.CONTROLS for p in pairs) == 32
    return value, frozen, pin


def test_eight_fits_64_pairs_32_exact_controls_without_parent_refits(result, prior_result):  # noqa: F811
    value, contract, pin = result
    s.validate_result(value, contract, pin)
    assert len(value["folds"]) == 4 and len(value["cells"]) == 64
    controls = [c for c in value["cells"] if c["candidate"] in s.CONTROLS]
    assert s.encode(controls) == s.encode(prior_result[0]["cells"])
    assert value["parent_controls_reproduced"] == len(controls) == 32
    ref = contract["reference"]
    assert len(ref["cells"]) == 32
    assert all(len(ref[k]) == 4 for k in ("folds", "support", "train_rows", "terminal"))
    assert contract["config"]["fit_budget"] == dict(
        feature_ridge=4, boosted_tree=4, passes=1, wall_seconds=900, gpu=False
    )
    assert all(
        contract["config"][k] is False
        for k in ("promotion", "holdout", "selection", "broker_input", "fitted_weights_retained")
    )
    assert all(
        key not in s.encode(value).decode()
        for key in ('"baseline_replay":', '"raw_rows":', '"predictions":', '"weights":')
    )


def test_fixed_targets_support_and_replay_paths_across_costs(result):
    value, contract, _ = result
    paths = {}
    for fold in value["folds"]:
        key = f"{fold['symbol']}:{fold['fold']}"
        ref = contract["reference"]
        assert fold["train_rows"] == ref["train_rows"][key]
        assert fold["terminal_decisions"] == ref["terminal"][key] == 10
        assert fold["control_facts_sha256"] == ref["folds"][key]
        dist = fold["forecast_distribution"]
        assert dist["min_bps"] <= dist["mean_bps"] <= dist["max_bps"]
        assert dist["std_bps"] >= 0
    for cell in value["cells"]:
        support = contract["reference"]["support"][f"{cell['symbol']}:{cell['fold']}"]
        assert support["eligible_decisions"] == support["common_scored_decisions"] == 60
        assert cell["selected_censored"] == support["common_censored_decisions"] == 0
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


def test_future_changes_payoff_not_prior_features_fitted_models_or_targets(inputs, tmp_path):  # noqa: F811
    schedule, streams = inputs
    index = {b.start_ts: b for b in streams[0][1]}
    plan = s.sessions.plans(schedule, 30)[0]
    arrays, observations, _ = s.base.training_arrays(index, plan)
    keys = s.positions.session_keys(observations, schedule)
    before, old_tree, old_control = s.decisions(
        arrays, observations, keys, schedule, time.monotonic() + 30
    )
    old_outcomes, _ = s.sessions.outcomes(index, observations, 30)
    for i in range(6):
        at = observations[0].at + i * s.h30.STEP
        index[at] = replace(
            index[at],
            **{
                k: getattr(index[at], k) * (i + 2)
                for k in ("open", "high", "low", "close", "volume")
            },
        )
    changed, new_observations, _ = s.base.training_arrays(index, plan)
    for key in ("train_x", "train_closes", "train_y", "train_net_y"):
        np.testing.assert_array_equal(arrays[key], changed[key])
    for key in ("eval_x", "eval_closes"):
        np.testing.assert_array_equal(arrays[key][0], changed[key][0])
        assert not np.array_equal(arrays[key][1], changed[key][1])
    np.testing.assert_array_equal(
        s.learner.feature_matrix(arrays["eval_x"], arrays["eval_closes"])[0],
        s.learner.feature_matrix(changed["eval_x"], changed["eval_closes"])[0],
    )
    after, new_tree, new_control = s.decisions(
        changed, new_observations, keys, schedule, time.monotonic() + 30
    )
    assert old_tree["model"] == new_tree["model"]
    assert old_control["model"] == new_control["model"]
    assert all(before[p][0] == after[p][0] for p in s.POLICIES)
    new_outcomes, _ = s.sessions.outcomes(index, new_observations, 30)
    emergency = s.h30.EmergencyStore(tmp_path / "emergency.json")
    old_gross, old_fees = s.sessions.payoff(observations[0], old_outcomes[0], 3, emergency)
    new_gross, new_fees = s.sessions.payoff(new_observations[0], new_outcomes[0], 3, emergency)
    assert old_gross - old_fees != new_gross - new_fees


@pytest.mark.parametrize(
    "field,reason",
    [
        ("folds", "parent_model_changed"),
        ("cells", "parent_cell_changed"),
        ("support", "parent_support_changed"),
    ],
)
def test_parent_reference_mismatch(contract, inputs, monkeypatch, tmp_path, field, reason):  # noqa: F811
    candidate = copy.deepcopy(contract[0])
    reference = candidate["reference"][field]
    first = next(iter(reference))
    if field == "support":
        reference[first]["eligible_decisions"] += 1
    else:
        reference[first] = "sha256:" + "0" * 64
    monkeypatch.setattr(s.sessions, "regular_sessions", lambda _: inputs[0])
    monkeypatch.setattr(s, "parent", forbidden)
    with pytest.raises(ValueError, match=reason):
        s.compare(
            inputs[1],
            candidate,
            s.digest(s.encode(candidate)),
            s.h30.EmergencyStore(tmp_path / "emergency.json"),
            time.monotonic() + 30,
        )


@pytest.mark.parametrize(
    "path,replacement",
    [
        (("raw_rows",), [1]),
        (("folds", 0, "model", "weights"), [1]),
        (("folds", 0, "model", "training_features_sha256"), {"raw_rows": [1]}),
        (("folds", 0, "forecast_distribution", "predictions"), [1]),
        (("folds", 0, "forecast_distribution", "mean_bps"), [0.0]),
        (("folds", 0, "forecast_distribution", "std_bps"), float("inf")),
        (("folds", 0, "action_counts", "enter"), [1]),
        (("cells", 2, "selected_decisions"), {"predictions": [1]}),
        (("cells", 2, "repeated", "raw_rows"), [1]),
        (("cells", 2, "persistent", "net_dollars"), ["0"]),
        (("cells", 2, "risk", "persistent", "max_holding_minutes"), [30]),
    ],
)
def test_nested_output_weights_and_scalar_containers_rejected(result, path, replacement):
    original, contract, pin = result
    candidate = copy.deepcopy(original)
    target = candidate
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    with pytest.raises(ValueError):
        s.validate_result(candidate, contract, pin)


@pytest.mark.parametrize(
    "change",
    [
        "cell_matrix",
        "fold_matrix",
        "train_rows",
        "terminal",
        "hurdle_count",
        "support",
        "cost_target",
        "cost_exposure",
    ],
)
def test_matrix_parent_counts_support_and_cost_tampering_rejected(result, change):
    original, contract, pin = result
    candidate = copy.deepcopy(original)
    fold = candidate["folds"][0]
    if change == "cell_matrix":
        candidate["cells"].pop()
    elif change == "fold_matrix":
        candidate["folds"][1] = copy.deepcopy(fold)
    elif change in ("train_rows", "terminal"):
        fold["train_rows" if change == "train_rows" else "terminal_decisions"] += 1
    elif change == "hurdle_count":
        dist = fold["forecast_distribution"]
        dist["above_hurdle"] += -1 if dist["above_hurdle"] else 1
    elif change == "support":
        candidate["cells"][2]["selected_censored"] += 1
    elif change == "cost_target":
        candidate["cells"][6]["decision_sha256"] = "sha256:" + "0" * 64
    else:
        candidate["cells"][6]["persistent"]["exposure_sha256"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError):
        s.validate_result(candidate, contract, pin)


@pytest.fixture
def frozen(tmp_path, monkeypatch, prior_result):  # noqa: F811
    market, artifact = tmp_path / "market", tmp_path / "artifacts"
    receipt = artifact / s.h30.RECEIPT
    receipt.parent.mkdir(parents=True)
    receipt.write_bytes(synthetic_receipt(market))
    prior = copy.deepcopy(prior_result[0])

    # Only the ancestor read is synthetic; source, code and runtime binding remain real.
    def parent(root):
        return s.base.proposed_contract(root), prior

    monkeypatch.setattr(s, "parent", parent)
    pin = s.freeze(artifact, market)
    output, contract = s.verify(artifact, market, pin)
    return SimpleNamespace(
        market=market,
        artifact=artifact,
        receipt=receipt,
        prior=prior,
        output=output,
        contract=contract,
        pin=pin,
    )


def test_freeze_metadata_only_external_immutable_and_exactly_pinned(frozen):
    assert set(frozen.contract["code_sha256"]) == set(s.CODE)
    assert frozen.contract["reference"] == s.references(frozen.prior)
    assert {p.name for p in frozen.output.iterdir()} == {"precommit.json"}
    raw = (frozen.output / "precommit.json").read_bytes()
    with pytest.raises(FileExistsError):
        s.freeze(frozen.artifact, frozen.market)
    assert (frozen.output / "precommit.json").read_bytes() == raw
    with pytest.raises(ValueError):
        s.freeze(s.REPO / "unused-artifacts", s.REPO / "unused-market")


@pytest.mark.parametrize("change", ["source", "code", "runtime", "parent", "pin"])
def test_binding_mismatch_fails_worker_before_loading(frozen, monkeypatch, change):
    pin = frozen.pin
    if change == "source":
        receipt = json.loads(frozen.receipt.read_bytes())
        receipt["normalizations"][0]["canonical_sha256"] = "sha256:" + "0" * 64
        frozen.receipt.write_bytes(s.encode(receipt))
    elif change == "code":
        original = Path.read_bytes

        def changed_code(path):
            raw = original(path)
            return raw + b"\n# changed" if path == Path(s.__file__) else raw

        monkeypatch.setattr(Path, "read_bytes", changed_code)
    elif change == "runtime":
        original = s.base.importlib.metadata.version
        monkeypatch.setattr(
            s.base.importlib.metadata,
            "version",
            lambda name: original(name) + ".changed" if name == "numpy" else original(name),
        )
    elif change == "parent":
        frozen.prior["folds"][0]["terminal_decisions"] += 1
    else:
        pin = "sha256:" + "0" * 64
    s.atomic_new(frozen.output / "started.json", {"contract_sha256": frozen.pin})
    path = frozen.output / "worker-result.json"
    with pytest.raises(ValueError):
        s.run_worker(frozen.artifact, frozen.market, pin, path, time.monotonic() + 30)
    assert not path.exists()


def test_worker_runtime_failure_is_categorical_and_cannot_overwrite(frozen, monkeypatch):
    calls = []

    def fail_loader(*args):
        calls.append(args)
        raise RuntimeError("PRIVATE_EXCEPTION_BODY")

    monkeypatch.setattr(s.h30, "load_streams", fail_loader)
    s.atomic_new(frozen.output / "started.json", {"contract_sha256": frozen.pin})
    path = frozen.output / "worker-result.json"
    args = frozen.artifact, frozen.market, frozen.pin, path, time.monotonic() + 30
    s.run_worker(*args)
    raw = path.read_bytes()
    assert json.loads(raw) == s.failure(frozen.contract, frozen.pin, "runtime_or_invariant_failure")
    assert b"PRIVATE_EXCEPTION_BODY" not in raw
    with pytest.raises(ValueError, match="worker_path"):
        s.run_worker(*args)
    assert len(calls) == 1 and path.read_bytes() == raw


@pytest.mark.parametrize("partial", [False, True])
def test_runner_one_attempt_immutable_and_no_raw_error(frozen, monkeypatch, capsys, partial):
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
        monkeypatch.setenv(name, "1")
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


def test_cli_reuses_runner_and_importable_worker_with_one_thread(monkeypatch):
    wrapper = runpy.run_path(str(s.REPO / "scripts/run_firstrate_feature_boosting.py"))
    namespace = {}
    exec("def main(argv):\n return (study, worker, argv)", namespace)

    def runner(path):
        assert Path(path) == s.REPO / "scripts/run_tiingo_month_start_development.py"
        return namespace

    monkeypatch.setattr(wrapper["runpy"], "run_path", runner)
    names = (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "BLIS_NUM_THREADS",
    )
    for name in names:
        monkeypatch.setenv(name, "2")
    assert wrapper["main"](["--freeze"]) == (s, s.worker_entry, ["--freeze"])
    assert all(os.environ[name] == "1" for name in names)
    module = importlib.import_module(s.worker_entry.__module__)
    assert getattr(module, s.worker_entry.__name__) is s.worker_entry
