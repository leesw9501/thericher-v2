"""Synthetic-only frozen inference, storage binding and bounded failure tests."""

import copy
import importlib.util
import io
import json
import socket
import sys
import time
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.data.tiingo_adjusted_etf_daily import AdjustedEtfRow

SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts/run_tiingo_monthly_frozen_policy_readback.py"
)
SPEC = importlib.util.spec_from_file_location("synthetic_frozen_readback", SCRIPT)
r = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = r
SPEC.loader.exec_module(r)


def forbidden(*_args, **_kwargs):
    pytest.fail("unassigned actual IO, fitting or weight writing")


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(r, "load_verified_adjusted_etf_vintage", forbidden)
    for name in (
        "fit_policy",
        "write_weights",
        "cpu_smoke",
        "execute",
        "run_worker",
        "register_contract",
        "load_adjusted",
    ):
        monkeypatch.setattr(r.study, name, forbidden)
    with localcontext() as context:
        context.prec = 50
        yield


@pytest.fixture(scope="module")
def torch():
    t = pytest.importorskip("torch")
    threads, deterministic = t.get_num_threads(), t.are_deterministic_algorithms_enabled()
    t.set_num_threads(2)
    yield t
    t.set_num_threads(threads)
    t.use_deterministic_algorithms(deterministic)


@pytest.fixture(scope="module")
def synthetic():
    days, d = [], date(2000, 12, 1)
    while d <= date(2026, 10, 1):
        if d.weekday() < 5 and (
            d.year <= 2001
            or d.day <= 3
            or (d + timedelta(days=1)).month != d.month
            or d >= date(2025, 7, 1)
        ):
            days.append(d.isoformat())
        d += timedelta(days=1)
    rows = {}
    for symbol in r.SYMBOLS:
        previous, stream = Decimal(100), []
        for i, stamp in enumerate(days):
            opening = previous + Decimal(i % 3 - 1) / 10
            closing = Decimal(100) + Decimal(i) / 100 + Decimal(i % 11 - 5) / 10
            stream.append(
                AdjustedEtfRow(
                    symbol,
                    date.fromisoformat(stamp),
                    opening,
                    max(opening, closing) + 1,
                    min(opening, closing) - 1,
                    closing,
                )
            )
            previous = closing
        rows[symbol] = tuple(stream)
    old_days = [d for d in days if d <= "2026-08-03"]
    old_rows = {
        s: tuple(v for v in rows[s] if v.session_date <= date(2026, 8, 3)) for s in r.SYMBOLS
    }
    new_days = [d for d in days if d >= "2025-07-01"]
    new_rows = {
        s: tuple(v for v in rows[s] if date(2025, 7, 1) <= v.session_date <= date(2026, 9, 30))
        for s in r.SYMBOLS
    }
    plan = r.study.build_plan(old_days)
    train_plan = dict(days=old_days, train=plan["train"], periods=[])
    prepared = r.study.prepare(old_rows, train_plan)
    predictions = {(a, s): np.full(132, 0.5) for a in r.ARCHITECTURES for s in r.SYMBOLS}
    with localcontext() as context:
        context.prec = 50
        risks = r.study.risk_constants(
            prepared, train_plan, predictions, deadline=time.monotonic() + 30
        )
    return SimpleNamespace(
        old_days=old_days, new_days=new_days, old_rows=old_rows, new_rows=new_rows, risks=risks
    )


@pytest.fixture
def package(tmp_path, monkeypatch, synthetic, torch):
    artifacts, market = tmp_path / "a", tmp_path / "m"
    parent = artifacts / "research" / r.study.NAME
    parent.mkdir(parents=True)
    market.mkdir()
    monkeypatch.setattr(r.study, "calendar_days", lambda: synthetic.old_days)
    monkeypatch.setattr(r, "calendar_days", lambda: synthetic.new_days)
    versions = r.study.runtime_versions()
    versions["torch"] = str(torch.__version__)
    monkeypatch.setattr(r.study, "runtime_versions", lambda: dict(versions))
    monkeypatch.setattr(r, "runtime_constraints", r.study.runtime_versions)
    contract = r.study.proposed_contract()
    models = []
    for architecture in r.ARCHITECTURES:
        values = {
            k: np.zeros(shape, dtype=np.float32)
            for k, shape in r.study.weight_shapes(architecture).items()
        }
        buffer = io.BytesIO()
        np.savez(buffer, **values)
        raw = buffer.getvalue()
        filename = f"weights-{architecture}.npz"
        (parent / filename).write_bytes(raw)
        models.append(
            dict(
                architecture=architecture,
                file=filename,
                weights_sha256=r.digest(raw),
                epochs=128,
                seed=101,
                reconstructed=True,
            )
        )
    raw = r.encode(contract)
    (parent / "precommit.json").write_bytes(raw)
    monkeypatch.setattr(r, "PARENT_CONTRACT", r.digest(raw))
    summary = dict(
        r.study.header(contract, r.PARENT_CONTRACT),
        status="complete",
        models=models,
        groups=[
            dict(
                symbol=s,
                period=p,
                status="evaluated",
                train=dict(months=132, missing=0, invalid=0),
                risk_sha256={
                    a: r.digest(r.encode(str(synthetic.risks[s][a]))) for a in r.ARCHITECTURES
                },
            )
            for s in r.SYMBOLS
            for p, _, _ in r.study.PERIODS
        ],
    )
    (parent / "summary.json").write_bytes(r.encode(summary))
    monkeypatch.setattr(r, "PARENT_SUMMARY", r.digest(r.encode(summary)))
    snapshot = "snapshot=20261003T000000Z-tiingo-etf-d1-r1"
    vintage = market / "us_equities/tiingo_etf_daily/canonical" / snapshot
    vintage.mkdir(parents=True)
    manifest = dict(
        kind="tiingo_etf_raw_d1_snapshot",
        version="tiingo-etf-d1-r1",
        immutable_snapshot=True,
        dataset_id="us_equities.tiingo_etf_daily." + snapshot,
        dataset_hash="sha256:" + "a" * 64,
        symbols=list(r.SYMBOLS),
        requested_window=dict(start="2025-07-01", end="2026-09-30"),
        files=dict(
            raw_sources=[
                dict(symbol=s, filename=s + ".json", sha256="sha256:" + str(i + 1) * 64)
                for i, s in enumerate(r.SYMBOLS)
            ]
        ),
        per_symbol={
            s: dict(
                session_count=len(synthetic.new_rows[s]),
                first_session="2025-07-01",
                last_session="2026-09-30",
            )
            for s in r.SYMBOLS
        },
    )
    (vintage / "manifest.json").write_bytes(r.encode(manifest))
    custody = artifacts / "research_campaign_custody.json"
    custody.write_bytes(b"synthetic immutable prior custody")
    return SimpleNamespace(
        artifacts=artifacts,
        market=market,
        parent=parent,
        output=artifacts / "research" / r.NAME,
        vintage=vintage,
        manifest=manifest,
        snapshot=snapshot,
        contract=contract,
        manifest_pin=r.digest(r.encode(manifest)),
        custody=custody,
        source=synthetic,
    )


def freeze(p):
    pin = r.freeze(p.artifacts, p.market, p.snapshot, p.manifest_pin)
    _, contract, parent_contract = r.verify(p.artifacts, p.market, pin)
    return pin, contract, parent_contract


def sources(p, monkeypatch):
    def load(market, source):
        assert market == p.market
        if source == p.contract["source"]:
            return p.source.old_rows
        assert source == r.vintage_metadata(p.market, p.snapshot, p.manifest_pin)
        return p.source.new_rows

    monkeypatch.setattr(r, "_load_source", load)


@pytest.fixture
def evaluated(package, torch, monkeypatch):
    pin, contract, parent = freeze(package)
    counts = r._counts()
    calls = []
    original = r.study.rebuild_policy

    def rebuild(*args, **kwargs):
        model = original(*args, **kwargs)
        model.register_forward_pre_hook(
            lambda _model, inputs: calls.append(
                (tuple(inputs[0].shape), inputs[0].device.type, torch.is_grad_enabled())
            )
        )
        return model

    monkeypatch.setattr(r.study, "rebuild_policy", rebuild)
    result = r.evaluate(
        torch,
        package.source.old_rows,
        package.source.new_rows,
        package.parent,
        contract,
        parent,
        pin,
        counts,
        time.monotonic() + 90,
    )
    assert len(calls) == 36 and sum(shape[0] for shape, _, _ in calls) == 1608
    assert all(
        shape[1:] == (252, 1) and device == "cpu" and not gradient
        for shape, device, gradient in calls
    )
    return package, pin, contract, result


def test_preview_has_no_io_environment_or_runtime_reads(monkeypatch, capsys):
    for name in ("freeze", "dispatch", "runtime_constraints", "calendar_days", "_paths", "_json"):
        monkeypatch.setattr(r, name, forbidden)
    for name in ("resolve", "read_bytes", "read_text", "open", "is_file", "exists"):
        monkeypatch.setattr(Path, name, forbidden)
    monkeypatch.setattr(r.signal, "signal", forbidden)
    assert r.main([]) == 0
    assert json.loads(capsys.readouterr().out) == dict(
        status="preview",
        image=r.IMAGE,
        windows=6,
        cells=126,
        matched_checks=36,
        fits=0,
        new_weights=0,
        gpu=False,
        wall_seconds=120,
        cpu_threads=2,
        memory_bytes=r.MEMORY_BYTES,
        network="none",
    )


@pytest.mark.parametrize(
    "arguments",
    [
        ["--run"],
        ["--freeze"],
        ["--run", "--freeze"],
        ["--run", "--contract-sha256", "private-secret", "--vintage-snapshot", "private-secret"],
        ["--private-secret"],
    ],
)
def test_invalid_cli_does_not_echo_arguments_or_read_data(arguments, monkeypatch, capsys):
    monkeypatch.setattr(r, "dispatch", forbidden)
    monkeypatch.setattr(r, "freeze", forbidden)
    assert r.main(arguments) == 1
    assert json.loads(capsys.readouterr().out) == dict(
        status="dispatch_unavailable", raw_error_suppressed=True
    )


def test_freeze_metadata_only_exact_lineage_no_custody_write(package, monkeypatch):
    before = {p.name: p.read_bytes() for p in package.parent.iterdir()}
    monkeypatch.setattr(r.study, "read_weights", forbidden)
    monkeypatch.setattr(r, "_load_source", forbidden)
    pin, contract, _ = freeze(package)
    assert r.digest((package.output / "precommit.json").read_bytes()) == pin
    assert contract["config"]["cells"] == 126 and contract["config"]["matched_checks"] == 36
    assert contract["config"]["budget"] == dict(
        seconds=120,
        cpu_threads=2,
        memory_bytes=2 * 1024**3,
        gpu=False,
        forward_calls=36,
        replay_calls=171,
        attempts=1,
    )
    assert contract["parent"]["contract_sha256"] == r.PARENT_CONTRACT
    assert contract["parent"]["summary_sha256"] == r.PARENT_SUMMARY
    assert len(contract["plan"]["windows"]) == 2
    assert {p.name for p in package.output.iterdir()} == {"precommit.json"}
    assert before == {p.name: p.read_bytes() for p in package.parent.iterdir()}
    assert package.custody.read_bytes() == b"synthetic immutable prior custody"
    with pytest.raises(ValueError, match="freeze_output_not_empty"):
        r.freeze(package.artifacts, package.market, package.snapshot, package.manifest_pin)


def test_freeze_supports_only_empty_existing_output_mount(package):
    package.output.mkdir()
    freeze(package)
    assert {p.name for p in package.output.iterdir()} == {"precommit.json"}


def test_full_real_calendar_six_windows_and_no_october_outcome_needed():
    plan = r.build_plan(r.calendar_days())
    assert [w["month"] for w in plan["windows"]] == list(r.MONTHS)
    for window in plan["windows"]:
        a, b = window["bounds"]
        assert len(plan["days"][a - 253 : a]) == 253
        assert plan["days"][a - 1] < plan["days"][a]
        assert all(d[:7] == window["month"] for d in plan["days"][a:b])
        assert plan["days"][b][:7] != window["month"]
        assert max(window["support"]) <= "2026-09-30"


@pytest.mark.parametrize("change", ["duplicate", "bracket", "history", "format"])
def test_calendar_rejects_incomplete_or_ambiguous_plan(synthetic, change):
    days = synthetic.new_days.copy()
    if change == "duplicate":
        days.insert(1, days[0])
    elif change == "bracket":
        days.pop()
    elif change == "history":
        days = [days[0], *[d for d in days if d >= "2026-07-01"]]
    else:
        days[0] = "2025-7-1"
    with pytest.raises(ValueError):
        r.build_plan(days)


@pytest.mark.parametrize(
    "change",
    ["config", "boolean", "runtime", "parent", "calendar", "code", "vintage", "field", "pin"],
)
def test_contract_mutations_reject_before_target_io(package, change, monkeypatch):
    pin, contract, _ = freeze(package)
    monkeypatch.setattr(r, "_load_source", forbidden)
    if change == "config":
        contract["config"]["cells"] = 127
    elif change == "boolean":
        contract["config"]["fits"] = False
    elif change == "runtime":
        contract["runtime"]["torch"] = "foreign"
    elif change == "parent":
        contract["parent"]["models"][0]["file"] = "../foreign.npz"
    elif change == "calendar":
        contract["plan"]["days"].pop()
    elif change == "code":
        contract["code_sha256"][r.CODE[0]] = "sha256:" + "b" * 64
    elif change == "vintage":
        contract["vintage"]["dataset_sha256"] = "sha256:" + "b" * 64
    elif change == "field":
        contract["extra"] = True
    else:
        pin = "sha256:" + "b" * 64
    if change != "pin":
        (package.output / "precommit.json").write_bytes(r.encode(contract))
        pin = r.digest(r.encode(contract))
    with pytest.raises(ValueError):
        r.dispatch(package.artifacts, package.market, pin)
    assert not (package.output / "started.json").exists()


@pytest.mark.parametrize("change", ["parent_contract", "parent_summary", "manifest"])
def test_metadata_hash_changes_fail_closed(package, change):
    pin, _, _ = freeze(package)
    path = {
        "parent_contract": package.parent / "precommit.json",
        "parent_summary": package.parent / "summary.json",
        "manifest": package.vintage / "manifest.json",
    }[change]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="metadata_hash"):
        r.verify(package.artifacts, package.market, pin)


@pytest.mark.parametrize("payload", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'])
def test_strict_json_rejects_duplicates_and_nonfinite(tmp_path, payload):
    path = tmp_path / "metadata.json"
    path.write_bytes(payload)
    with pytest.raises(ValueError):
        r._json(path)


def test_source_loader_is_exactly_bound_to_fixed_loader(package, monkeypatch):
    _, contract, _ = freeze(package)
    calls = []

    def loader(path, **kwargs):
        calls.append((path, kwargs))
        return package.source.new_rows

    monkeypatch.setattr(r, "load_verified_adjusted_etf_vintage", loader)
    assert r._load_source(package.market, contract["vintage"]) is package.source.new_rows
    source = contract["vintage"]
    assert calls == [
        (
            package.market / source["snapshot"],
            dict(
                dataset_id=source["dataset_id"],
                expected_dataset_hash=source["dataset_sha256"],
                expected_manifest_hash=source["manifest_sha256"],
                expected_raw_hashes=source["raw_sha256"],
                market_data_root=package.market,
                repo_root=r.REPO,
            ),
        )
    ]


def test_actual_cpu_reconstruction_and_126_cells_36_matches(evaluated):
    p, pin, contract, result = evaluated
    r.validate_result(result, contract, pin)
    assert result["compute"] == dict(
        forward_calls=36, replay_calls=171, fits=0, new_weights=0, gpu=False
    )
    assert len(result["cells"]) == 126 and len(result["matched_checks"]) == 36
    assert len(result["groups"]) == 6 and len(result["models"]) == 2
    assert all(g["training_months"] == 132 and g["months"] == 1 for g in result["groups"])
    for model in result["models"]:
        values = r.study.read_weights(
            p.parent / model["file"], model["architecture"], model["weights_sha256"]
        )
        assert set(values) == set(r.study.weight_shapes(model["architecture"]))
    assert all(
        all(
            check[k] is True
            for k in ("exposure_matched", "turnover_matched", "cost_matched", "numpy_parity")
        )
        for check in result["matched_checks"]
    )
    assert {p.name for p in p.output.iterdir()} == {"precommit.json"}


@pytest.mark.parametrize("change", ["shape", "dtype", "nonfinite", "pickle", "foreign_keys"])
def test_numeric_weight_schema_cannot_dispatch_foreign_values(package, torch, change):
    pin, contract, parent = freeze(package)
    values = {
        k: np.zeros(shape, dtype=np.float32) for k, shape in r.study.weight_shapes("linear").items()
    }
    if change == "shape":
        values["head_weight"] = np.zeros((1, 251), dtype=np.float32)
    elif change == "dtype":
        values["head_weight"] = values["head_weight"].astype(np.float64)
    elif change == "nonfinite":
        values["head_bias"][0] = np.nan
    elif change == "pickle":
        values["head_bias"] = np.array([dict(synthetic="not executable")], dtype=object)
    else:
        values["foreign"] = np.zeros(1, dtype=np.float32)
    buffer = io.BytesIO()
    np.savez(buffer, **values)
    raw = buffer.getvalue()
    (package.parent / "weights-linear.npz").write_bytes(raw)
    contract["parent"]["models"][0]["weights_sha256"] = r.digest(raw)
    counts = r._counts()
    with pytest.raises(ValueError):
        r.evaluate(
            torch,
            package.source.old_rows,
            package.source.new_rows,
            package.parent,
            contract,
            parent,
            pin,
            counts,
            time.monotonic() + 90,
        )
    assert counts == r._counts()


@pytest.mark.parametrize(
    "change",
    [
        "cells",
        "checks",
        "groups",
        "model",
        "count",
        "boolcount",
        "boolgroup",
        "boolcheck",
        "reference",
        "action",
        "cash",
        "fee",
        "nonfinite",
        "privatefield",
    ],
)
def test_strict_result_negative_controls(evaluated, change):
    _, pin, contract, original = evaluated
    result = copy.deepcopy(original)
    if change in ("cells", "groups"):
        result[change].pop()
    elif change == "checks":
        result["matched_checks"].pop()
    elif change == "model":
        result["models"][0]["file"] = "foreign.npz"
    elif change == "count":
        result["compute"]["forward_calls"] = 35
    elif change == "boolcount":
        result["compute"]["fits"] = False
    elif change == "boolgroup":
        result["groups"][0]["months"] = True
    elif change == "boolcheck":
        result["matched_checks"][0]["cost_matched"] = 1
    elif change == "reference":
        result["cells"][0][r.METRICS[-1]] = "123"
    elif change == "action":
        result["matched_checks"][0]["action_sha256"] = "sha256:" + "b" * 64
    elif change == "cash":
        result["cells"][6]["final_nav"] = "1.1"
    elif change == "fee":
        result["cells"][0]["fees_initial_nav"] = "123"
    elif change == "nonfinite":
        result["cells"][0]["net_utility"] = "NaN"
    else:
        result["private"] = "must-not-be-accepted"
    with pytest.raises((ValueError, KeyError)):
        r.validate_result(result, contract, pin)


@pytest.mark.parametrize("architecture", r.ARCHITECTURES)
@pytest.mark.parametrize("target_month", (8, 9))
def test_month_payoffs_cannot_change_own_features_or_frozen_action(
    package, torch, architecture, target_month
):
    _, contract, _ = freeze(package)
    calendar = tuple(date.fromisoformat(d) for d in contract["plan"]["days"])
    changed = tuple(
        replace(
            row,
            adj_open=row.adj_open * 2,
            adj_high=row.adj_high * 3,
            adj_close=row.adj_close * 3,
        )
        if row.session_date.month == target_month and row.session_date.year == 2026
        else row
        for row in package.source.new_rows["SPY"]
    )
    values = {
        k: np.full(shape, 0.001, dtype=np.float32)
        for k, shape in r.study.weight_shapes(architecture).items()
    }
    model = r.study.rebuild_policy(torch, values, architecture)
    for window in contract["plan"]["windows"]:
        if int(window["month"][-2:]) > target_month:
            continue
        records = [
            r.study.inputs.build_adjusted_monthly_policy_inputs(
                stream, symbol="SPY", calendar=calendar, month_bounds=tuple(window["bounds"])
            )
            for stream in (package.source.new_rows["SPY"], changed)
        ]
        arrays = [r.study.math.prepare_monthly_utility_arrays((record,)) for record in records]
        np.testing.assert_array_equal(arrays[0].features, arrays[1].features)
        np.testing.assert_array_equal(
            r.study.predict(torch, model, arrays[0]), r.study.predict(torch, model, arrays[1])
        )
        if int(window["month"][-2:]) == target_month:
            assert not np.array_equal(arrays[0].close_growth, arrays[1].close_growth)


@pytest.mark.parametrize("change", ["risk", "missing", "weights", "deadline", "zero_risk"])
def test_evaluation_invariants_cannot_claim_complete(package, torch, monkeypatch, change):
    pin, contract, parent = freeze(package)
    new_rows = package.source.new_rows
    deadline = time.monotonic() + 90
    if change == "risk":
        contract["parent"]["risk_sha256"]["SPY"]["linear"] = "sha256:" + "b" * 64
    elif change == "missing":
        new_rows = dict(new_rows)
        new_rows["SPY"] = new_rows["SPY"][:-1]
    elif change == "weights":
        path = package.parent / "weights-linear.npz"
        path.write_bytes(path.read_bytes() + b"foreign")
    elif change == "deadline":
        deadline = 0
    else:
        monkeypatch.setattr(
            r.study,
            "risk_constants",
            lambda *a, **k: {s: dict.fromkeys(r.ARCHITECTURES) for s in r.SYMBOLS},
        )
    with pytest.raises(ValueError):
        r.evaluate(
            torch,
            package.source.old_rows,
            new_rows,
            package.parent,
            contract,
            parent,
            pin,
            r._counts(),
            deadline,
        )


@pytest.mark.parametrize("field,amount", [("forward_calls", 37), ("replay_calls", 172)])
def test_budget_rejection_keeps_valid_failure_counts(field, amount):
    counts = r._counts()
    with pytest.raises(ValueError, match="compute_budget"):
        r._tick(counts, field, amount, time.monotonic() + 30)
    assert counts == r._counts()


def test_dispatch_complete_once_and_preserves_parent_and_custody(package, torch, monkeypatch):
    pin, contract, _ = freeze(package)
    before = {p.name: p.read_bytes() for p in package.parent.iterdir()}
    sources(package, monkeypatch)
    jobs = []

    def supervise(target, arguments, *, seconds):
        assert target is r.worker and 0 < seconds <= 120
        jobs.append(arguments)
        target(*arguments)
        return dict(timed_out=False, exit_code=0)

    monkeypatch.setattr(r, "supervise", supervise)
    public = r.dispatch(package.artifacts, package.market, pin)
    assert public["status"] == "complete" and public["cells"] == 126
    assert public["matched_checks"] == 36 and public["gpu"] is False
    result = r._json(package.output / "summary.json", public["summary_sha256"])
    r.validate_result(result, contract, pin)
    assert len(jobs) == 1
    assert {p.name for p in package.output.iterdir()} == {
        "precommit.json",
        "started.json",
        "worker-result.json",
        "summary.json",
    }
    saved = {p.name: p.read_bytes() for p in package.output.iterdir()}
    with pytest.raises(ValueError, match="attempt_already_exists"):
        r.dispatch(package.artifacts, package.market, pin)
    assert saved == {p.name: p.read_bytes() for p in package.output.iterdir()}
    assert before == {p.name: p.read_bytes() for p in package.parent.iterdir()}
    assert package.custody.read_bytes() == b"synthetic immutable prior custody"


@pytest.mark.parametrize(
    "case",
    [
        "timeout",
        "nonzero",
        "unknown_exit",
        "bool_exit",
        "bad_timeout",
        "bad_cells",
        "weight_changed",
        "extra_file",
        "interrupted",
    ],
)
def test_supervisor_failure_rejects_even_complete_candidate(evaluated, monkeypatch, case):
    p, pin, contract, candidate = evaluated

    def supervise(_target, args, *, seconds):
        assert 0 < seconds <= 120
        result = copy.deepcopy(candidate)
        if case == "bad_cells":
            result["cells"].pop()
        r.study.atomic_new(args[3], result)
        if case == "weight_changed":
            path = p.parent / "weights-linear.npz"
            path.write_bytes(path.read_bytes() + b"changed")
        if case == "extra_file":
            (p.output / "foreign.npz").write_bytes(b"synthetic")
        if case == "interrupted":
            raise KeyboardInterrupt
        return dict(
            timed_out=(True if case == "timeout" else 0 if case == "bad_timeout" else False),
            exit_code={"nonzero": 1, "unknown_exit": None, "bool_exit": False}.get(case, 0),
        )

    monkeypatch.setattr(r, "supervise", supervise)
    public = r.dispatch(p.artifacts, p.market, pin)
    assert public["status"] == "failed" and public["cells"] == public["matched_checks"] == 0
    result = r._json(p.output / "summary.json")
    r.validate_result(result, contract, pin)
    assert result["reason"] == (
        {"timeout": "hard_timeout", "interrupted": "execution_preempted"}.get(
            case,
            "worker_failed"
            if case in ("nonzero", "unknown_exit", "bool_exit")
            else "worker_result_invalid",
        )
    )


@pytest.mark.parametrize("case", ["unreserved", "wrong_pin", "wrong_path", "extra_file"])
def test_worker_identity_before_target_io(package, monkeypatch, case):
    pin, _, _ = freeze(package)
    monkeypatch.setattr(r, "_load_source", forbidden)
    if case != "unreserved":
        r.study.atomic_new(
            package.output / "started.json",
            dict(contract_sha256="sha256:" + "b" * 64 if case == "wrong_pin" else pin),
        )
    if case == "extra_file":
        (package.output / "foreign.json").write_bytes(b"{}")
    path = package.output / (
        "foreign-result.json" if case == "wrong_path" else "worker-result.json"
    )
    with pytest.raises((ValueError, FileNotFoundError)):
        r.worker(package.artifacts, package.market, pin, path, time.monotonic() + 30)


def test_worker_suppresses_private_errors(package, torch, monkeypatch):
    pin, contract, _ = freeze(package)
    r.study.atomic_new(package.output / "started.json", dict(contract_sha256=pin))

    def fail(*_a, **_k):
        raise ValueError("synthetic-private-secret-value")

    monkeypatch.setattr(r, "_load_source", fail)
    path = package.output / "worker-result.json"
    r.worker(package.artifacts, package.market, pin, path, time.monotonic() + 30)
    raw = path.read_bytes()
    assert b"synthetic-private-secret-value" not in raw
    result = r._json(path)
    r.validate_result(result, contract, pin)
    assert result["status"] == "failed" and result["compute"] == r._counts()


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "torch",
        "calendar",
        "docker",
        "cpu",
        "unlimited_cpu",
        "memory",
        "unlimited_memory",
        "swap",
        "network",
    ],
)
def test_cpu_container_contract_requires_pins_and_resource_limits(monkeypatch, case):
    versions = dict(
        torch="2.7.0+cu128", numpy="synthetic-pinned", **{"pandas-market-calendars": "5.4.0"}
    )
    if case == "torch":
        versions["torch"] = "2.13.0+cpu"
    if case == "calendar":
        versions["pandas-market-calendars"] = "foreign"
    monkeypatch.setattr(r.study, "runtime_versions", lambda: versions)
    monkeypatch.setattr(
        Path, "is_file", lambda p: str(p).endswith(".dockerenv") and case != "docker"
    )
    values = {"cpu.max": "200000 100000", "memory.max": str(r.MEMORY_BYTES), "memory.swap.max": "0"}
    if case in ("cpu", "unlimited_cpu"):
        values["cpu.max"] = "300000 100000" if case == "cpu" else "max 100000"
    if case in ("memory", "unlimited_memory"):
        values["memory.max"] = str(r.MEMORY_BYTES + 1) if case == "memory" else "max"
    if case == "swap":
        values["memory.swap.max"] = "1"
    monkeypatch.setattr(Path, "read_text", lambda p, *a, **k: values[p.name])
    monkeypatch.setattr(
        socket,
        "if_nameindex",
        lambda: [(1, "lo"), (2, "eth0")] if case == "network" else [(1, "lo")],
    )
    if case == "valid":
        assert r.runtime_constraints() == versions
    else:
        with pytest.raises(ValueError):
            r.runtime_constraints()


def test_supervisor_reuses_code_pinned_bounded_cpu_helper(monkeypatch):
    calls = []

    def existing(target, args, **kwargs):
        calls.append((target, args, kwargs))
        return dict(timed_out=False, exit_code=0)

    monkeypatch.setattr(r.runpy, "run_path", lambda path: {"supervise": existing})
    assert "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py" in r.CODE
    assert r.supervise(r.worker, ("synthetic",), seconds=119)["exit_code"] == 0
    assert calls == [(r.worker, ("synthetic",), dict(seconds=119, name=r.NAME))]
    for seconds in (0, -1, 121):
        with pytest.raises(ValueError):
            r.supervise(r.worker, (), seconds=seconds)
