"""Offline synthetic-only tests; never read a market artifact or dispatch Docker/CUDA."""

import copy
import importlib.util
import json
import socket
import subprocess
import sys
import time
from contextlib import nullcontext
from dataclasses import replace
from decimal import Decimal, localcontext
from pathlib import Path

import numpy as np
import pytest

from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.research import kis_pooled_patch_return_development as r

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_kis_pooled_patch_return_development.py"
spec = importlib.util.spec_from_file_location("pooled_patch_launcher", SCRIPT)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
PIN = "sha256:" + "1" * 64


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", lambda *_: pytest.fail("network forbidden"))
    monkeypatch.setattr(socket, "create_connection", lambda *_: pytest.fail("network forbidden"))


@pytest.fixture(scope="module")
def panel():
    return r.synthetic_panel()


@pytest.fixture(scope="module")
def feedback(panel):
    return tuple(r.payoffs(*panel, dates) for dates in (r.TRAIN, r.COMPARISON))


@pytest.fixture(scope="module")
def actions(panel, feedback):
    controls = r.controls(panel[0], feedback[0])
    return tuple(
        controls.get(p, tuple(i % (j + 2) == 0 for i in range(72)))
        for j, p in enumerate(r.POLICIES)
    )


def test_frozen_geometry_recipe_and_shared_blocks(panel):
    windows, catalogs = panel
    config = r.configuration()
    assert len(windows) == 1032 and len(catalogs) == 40
    assert len(r.split(windows, r.TRAIN)) == 960 and len(r.split(windows, r.COMPARISON)) == 72
    assert str(r.EMBARGO) == "2026-09-17" and len(r.COMPARISON) == 9
    assert config["cells"] == 42 and config["shared_session_blocks"] == 9
    assert config["shared_train_session_blocks"] == 10
    assert r.TRAIN_OFFSETS == tuple(range(120, 356, 5)) and r.COMPARISON_OFFSETS == (
        120,
        180,
        240,
        300,
    )
    assert config["neural"] == dict(
        seed=107,
        epochs=128,
        batch=960,
        optimizer="Adam",
        lr=0.001,
        weight_decay=0,
        loss="Huber",
        delta=0.1,
        final_epoch_only=True,
        lstm_hidden=16,
        patch_hidden=16,
        patch_heads=2,
        patch_length=6,
        patch_layers=1,
        patch_dropout=0,
        channel_aggregation="equal mean",
    )
    assert config["budget"]["actual_fits"] == 3 and config["budget"]["attempts"] == 1
    assert set(config["kills"]) == set(r.KILLS)
    assert len({w.key.dataset_hash for w in windows}) == 38
    for w in windows:
        assert w.source_minute_starts[-1] + r.MINUTE == w.key.cutoff
        assert len(w.sequence) == 24 and len(w.sequence[0]) == 4
        assert w.key.entry == w.key.cutoff + r.MINUTE and w.key.exit == w.key.cutoff + 31 * r.MINUTE
        assert w.key.session_date != r.EMBARGO and w.key.exit.date() == w.key.session_date
        assert w.key.exit < r.dated.us_equity_2026_session(w.key.session_date).window.close_ts
    assert {w.key.session_date for w in r.split(windows, r.TRAIN)} == set(r.TRAIN)
    assert {w.key.session_date for w in r.split(windows, r.COMPARISON)} == set(r.COMPARISON)


@pytest.mark.parametrize(
    "kind",
    (
        "subset",
        "duplicate",
        "order",
        "symbol",
        "date",
        "exchange",
        "hash",
        "cutoff",
        "entry",
        "exit",
        "shape",
        "nonfinite",
    ),
)
def test_exact_full_cohort_no_subsets_or_geometry_substitution(panel, kind):
    windows = list(panel[0])
    w = windows[0]
    if kind == "subset":
        windows.pop()
    elif kind == "duplicate":
        windows[0] = windows[1]
    elif kind == "order":
        windows.reverse()
    elif kind == "shape":
        windows[0] = replace(w, sequence=w.sequence[:-1])
    elif kind == "nonfinite":
        windows[0] = replace(w, features=(np.nan, *w.features[1:]))
    else:
        changes = (
            dict(symbol="IWM")
            if kind == "symbol"
            else dict(session_date=r.EMBARGO)
            if kind == "date"
            else (
                dict(dataset_id=w.key.dataset_id.replace("nas", "ams"))
                if kind == "exchange"
                else dict(dataset_hash=PIN)
                if kind == "hash"
                else {kind: getattr(w.key, kind) + r.MINUTE}
            )
        )
        windows[0] = replace(w, key=replace(w.key, **changes))
    with pytest.raises(ValueError):
        r.check_cohort(tuple(windows))


def test_future_bar_mutation_cannot_change_current_completed_features(panel):
    windows, catalogs = panel
    first = windows[0]
    catalog = catalogs["QQQ", r.DATES[0]]
    mutated = tuple(
        replace(b, open=b.open * 2, high=b.high * 2, low=b.low * 2, close=b.close * 2)
        if b.start_ts >= first.key.cutoff
        else b
        for b in catalog.bars
    )
    revised = _cataloged_bars_from_verified_loader(
        dataset_id=catalog.dataset_id,
        dataset_hash=PIN,
        source_path=Path("synthetic.json"),
        bars=mutated,
    )
    prepared = r.data.prepare_kis_paper_intraday_feature_input(revised, session_dates=(r.DATES[0],))
    changed = r.build_windows(prepared)[0]
    assert changed.features == first.features and changed.sequence == first.sequence
    assert changed.source_minute_starts == first.source_minute_starts


@pytest.mark.parametrize("kind", ("missing", "symbol", "calendar"))
def test_session_geometry_failures_before_targets(panel, kind):
    catalog = panel[1]["QQQ", r.DATES[0]]
    bars = (
        catalog.bars[:-1]
        if kind == "missing"
        else (
            tuple(replace(b, symbol="IWM") for b in catalog.bars)
            if kind == "symbol"
            else catalog.bars
        )
    )
    revised = _cataloged_bars_from_verified_loader(
        dataset_id=catalog.dataset_id,
        dataset_hash=PIN,
        source_path=Path("synthetic.json"),
        bars=bars,
    )
    with pytest.raises(ValueError):
        prepared = r.data.prepare_kis_paper_intraday_feature_input(
            revised, session_dates=(r.DATES[0],)
        )
        if kind == "calendar":
            prepared = replace(prepared, session_windows=())
        r.build_windows(prepared)


def test_payoff_exact_m1_opens_and_source_identity(panel):
    w = panel[0][0]
    catalog = panel[1]["QQQ", r.DATES[0]]
    bars = {b.start_ts: b for b in catalog.bars}
    with localcontext() as ctx:
        ctx.prec = 50
        expected = 10000 * (bars[w.key.exit].open / bars[w.key.entry].open - 1)
    assert r.gross_bps(w, catalog) == expected
    with pytest.raises(ValueError, match="payoff_source"):
        r.gross_bps(w, panel[1]["SPY", r.DATES[0]])


@pytest.mark.parametrize("shape", ((960, 4), (960, 24, 4)))
def test_train_only_norm_floor_no_comparison_statistics_or_clipping(shape):
    train = np.arange(np.prod(shape), dtype=np.float64).reshape(shape)
    train[..., -1] = 7
    future = train[:72].copy()
    original_train, original_future = train.copy(), future.copy()
    a, b = r.standardized(train, future)
    changed = future.copy() + 1e7
    c, d = r.standardized(train, changed)
    np.testing.assert_array_equal(a, c)
    np.testing.assert_array_equal(train, original_train)
    np.testing.assert_array_equal(future, original_future)
    np.testing.assert_array_equal(a[..., -1], 0)
    assert np.max(d[..., -1]) > 1e18 and not np.array_equal(b, d)


@pytest.mark.parametrize("kind", ("trainshape", "compshape", "nan", "inf"))
def test_normalization_strict_shapes_and_finiteness(kind):
    train, future = np.zeros((960, 4)), np.zeros((72, 4))
    if kind == "trainshape":
        train = train[:-1]
    elif kind == "compshape":
        future = future[:-1]
    else:
        future[0, 0] = np.nan if kind == "nan" else np.inf
    with pytest.raises(ValueError):
        r.standardized(train, future)


def test_ridge_unpenalized_intercept_exact_penalty():
    train = np.arange(3840, dtype=np.float64).reshape(960, 4)
    future, y = train[:72] + 3, np.full(960, 37.0)
    np.testing.assert_allclose(r.fit_ridge(train, y, future), 37, atol=1e-11)
    y = np.arange(960, dtype=np.float64)
    x, z = r.standardized(train, future)
    x, z = np.column_stack((x, np.ones(960))), np.column_stack((z, np.ones(72)))
    expected = z @ np.linalg.solve(x.T @ x + np.diag([1.0] * 4 + [0.0]), x.T @ y)
    np.testing.assert_array_equal(r.fit_ridge(train, y, future), expected)


def test_exact_three_fits_ridge_cpu_first_two_128_epoch_models(panel, feedback, monkeypatch):
    torch = pytest.importorskip("torch")
    calls, steps = [], []
    ridge, network, step = r.fit_ridge, r.fit_network, torch.optim.Adam.step

    def fit_ridge(*args):
        calls.append("ridge")
        return ridge(*args)

    def fit_network(*args, **kwargs):
        calls.append(args[1])
        assert args[5] == "cpu"
        return network(*args, **kwargs)

    def adam_step(self, *args, **kwargs):
        assert self.param_groups[0]["lr"] == 0.001 and self.param_groups[0]["weight_decay"] == 0
        steps.append(1)
        return step(self, *args, **kwargs)

    monkeypatch.setattr(r, "fit_ridge", fit_ridge)
    monkeypatch.setattr(r, "fit_network", fit_network)
    monkeypatch.setattr(torch.optim.Adam, "step", adam_step)
    counts, progress = dict.fromkeys(r.MODELS, 0), {}
    result = r.fit_actions(panel[0], feedback[0], counts, time.monotonic() + 60, progress=progress)
    assert calls == list(r.MODELS) and len(steps) == 256 and counts == dict.fromkeys(r.MODELS, 1)
    assert type(result) is tuple and r.commitment(result).startswith("sha256:")
    assert progress["stage"] == "inference"
    with pytest.raises(ValueError, match="fit_retry"):
        r.fit_actions(panel[0], feedback[0], counts, time.monotonic() + 60)


def test_cpu_smoke_synthetic_only_and_deterministic():
    pytest.importorskip("torch")
    assert r.cpu_smoke(time.monotonic() + 90) == dict(
        synthetic_windows=1032, synthetic_fits=6, actual_fits=0, cells=42, verified=True
    )


def test_comparison_feature_mutation_never_enters_fit_or_train_normalization(
    panel, feedback, monkeypatch
):
    pytest.importorskip("torch")
    observed = []

    def ridge(train, y, comparison):
        observed.append(("ridge", train.copy(), y.copy()))
        return np.zeros(72)

    def network(torch, name, train, y, comparison, device, deadline, **kwargs):
        observed.append((name, train.copy(), y.copy()))
        return np.zeros(72)

    monkeypatch.setattr(r, "fit_ridge", ridge)
    monkeypatch.setattr(r, "fit_network", network)
    r.fit_actions(panel[0], feedback[0], dict.fromkeys(r.MODELS, 0), time.monotonic() + 30)
    revised = tuple(
        replace(
            w,
            features=tuple(v + 1e6 for v in w.features),
            sequence=tuple(tuple(v + 1e6 for v in row) for row in w.sequence),
        )
        if w.key.session_date in r.COMPARISON
        else w
        for w in panel[0]
    )
    r.fit_actions(revised, feedback[0], dict.fromkeys(r.MODELS, 0), time.monotonic() + 30)
    for before, after in zip(observed[:3], observed[3:], strict=True):
        assert before[0] == after[0]
        np.testing.assert_array_equal(before[1], after[1])
        np.testing.assert_array_equal(before[2], after[2])
        assert len(before[1]) == len(before[2]) == 960
    assert (
        max((w.key.exit - w.key.session_open) / r.MINUTE for w in r.split(panel[0], r.TRAIN)) == 386
    )


@pytest.mark.parametrize(
    "counts", (dict(ridge=True, lstm=1, patch=1), dict(ridge=2, lstm=1, patch=1), {})
)
def test_result_rejects_bool_extra_or_missing_actual_fits(panel, feedback, actions, counts):
    value = complete_result(panel, feedback, actions)
    value["fits_started"] = counts
    with pytest.raises(ValueError):
        cli.validate_result(value, PIN, "cuda")


def test_smoke_cannot_claim_actual_fit_or_touch_gpu_custody(tmp_path, monkeypatch):
    broken = cli.failure(PIN, "cpu-smoke", "fit", dict(ridge=1, lstm=0, patch=0))
    with pytest.raises(ValueError, match="smoke_actual_fits"):
        cli.validate_result(broken, PIN, "cpu-smoke")
    dispatch_setup(tmp_path, monkeypatch, False)
    monkeypatch.setattr(cli, "GpuFileLock", lambda *_: pytest.fail("CPU smoke GPU lock"))
    monkeypatch.setattr(cli, "resolve_agent_root", lambda *_: pytest.fail("CPU smoke GPU path"))

    def supervise(*_, **__):
        cli.atomic(tmp_path / "cpu-smoke-worker.json", smoke_result())
        return dict(timed_out=False, exit_code=0)

    monkeypatch.setattr(cli.runpy, "run_path", lambda *_: dict(supervise=supervise))
    assert cli.dispatch(tmp_path, tmp_path, PIN, "cpu-smoke")["status"] == "complete"


@pytest.mark.parametrize(
    "counts", (dict(ridge=True, lstm=0, patch=0), dict(ridge=1, lstm=0, patch=0), {})
)
def test_fit_retry_and_bool_counters_rejected(panel, feedback, counts):
    pytest.importorskip("torch")
    with pytest.raises(ValueError, match="fit_retry"):
        r.fit_actions(panel[0], feedback[0], counts, time.monotonic() + 60)


def test_timeout_before_any_actual_fit(panel, feedback):
    pytest.importorskip("torch")
    counts = dict.fromkeys(r.MODELS, 0)
    with pytest.raises(ValueError, match="hard_timeout"):
        r.fit_actions(panel[0], feedback[0], counts, time.monotonic() - 1)
    assert counts == dict.fromkeys(r.MODELS, 0)


def test_42_cells_cost_invariant_actions_math_and_readback(panel, feedback, actions, monkeypatch):
    value = r.aggregate(panel[0], feedback[1], actions)
    assert len(value["cells"]) == 42 and len(value["daily"]) == 18
    assert value["descriptive"]["shared_session_blocks"] == 9
    for symbol, _ in r.TARGETS:
        for policy in r.POLICIES:
            cells = [c for c in value["cells"] if c["symbol"] == symbol and c["policy"] == policy]
            assert len({c["action_sha256"] for c in cells}) == 1
            assert len({c["trades"] for c in cells}) == 1
            for c in cells:
                with localcontext() as ctx:
                    ctx.prec = 50
                    assert (
                        Decimal(c["mean_net_unit_bps"])
                        == (
                            Decimal(c["gross_sum_unit_bps"])
                            - 2 * Decimal(c["cost_per_side_bps"]) * c["trades"]
                        )
                        / 36
                    )
    monkeypatch.setattr(r, "fit_actions", lambda *_: pytest.fail("readback must not fit"))
    r.verify_evaluation(panel[0], feedback[0], feedback[1], value)
    assert not any(k in r.encode(value).decode() for k in ("forecast", "weights", "labels"))


def test_shared_day_and_etf_deletion_kill_calculations(panel, feedback, actions):
    value = r.aggregate(panel[0], feedback[1], actions)
    with localcontext() as ctx:
        ctx.prec = 50
        nets = {}
        for row in value["daily"]:
            nets[row["symbol"], row["date"]] = {
                p["policy"]: (Decimal(p["gross_sum_unit_bps"]) - 12 * p["trades"]) / 4
                for p in row["policies"]
            }
        for baseline in ("ridge", "lstm"):
            delta = {key: v["patch"] - v[baseline] for key, v in nets.items()}
            expected_day = min(
                sum(v for (s, d), v in delta.items() if d != str(day)) / 16 for day in r.COMPARISON
            )
            expected_etf = min(
                sum(v for (s, d), v in delta.items() if s != symbol) / 9 for symbol, _ in r.TARGETS
            )
            assert (
                Decimal(value["descriptive"]["min_leave_one_shared_day_out_increments"][baseline])
                == expected_day
            )
            assert (
                Decimal(value["descriptive"]["min_leave_one_ETF_out_increments"][baseline])
                == expected_etf
            )


@pytest.mark.parametrize(
    "field", ("cells", "daily", "commit", "cost", "mean", "trades", "kill", "control", "order")
)
def test_readback_rejects_tampered_math_actions_or_schema(panel, feedback, actions, field):
    value = r.aggregate(panel[0], feedback[1], actions)
    if field in ("cells", "daily"):
        value[field].pop()
    elif field == "commit":
        value["commit_sha256"] = PIN
    elif field == "cost":
        value["cells"][0]["cost_per_side_bps"] = "2"
    elif field == "mean":
        value["cells"][0]["mean_net_unit_bps"] = "999"
    elif field == "trades":
        value["daily"][0]["policies"][0]["trades"] = True
    elif field == "kill":
        value["descriptive"]["kill_categories"] = []
    elif field == "control":
        revised = list(actions)
        revised[-1] = (False,) * 72
        value = r.aggregate(panel[0], feedback[1], tuple(revised))
    else:
        value["daily"].reverse()
    with pytest.raises(ValueError):
        r.verify_evaluation(panel[0], feedback[0], feedback[1], value)


def source_contract():
    return dict(
        name=cli.NAME,
        config=cli.configuration(),
        runtime={"torch": "pinned"},
        sources=[
            dict(
                date=str(d),
                root=f"{s.lower()}-{d:%Y%m%d}",
                index_sha256=PIN,
                dataset_id=f"kis.paper.private.intraday.{s.lower()}.{ex.lower()}.m1.v1",
                dataset_sha256=PIN,
                manifests={},
                symbol=s,
                exchange=ex,
            )
            for (s, ex), d in r.product(r.TARGETS, r.DATES)
        ],
        code_sha256={"owned": PIN},
    )


def test_source_metadata_reused_both_targets_before_raw_or_writes(monkeypatch):
    seen = []

    def metadata(inputs, pins, *, target):
        seen.append(target)
        assert len(pins) == 20
        return [dict(s) for s in source_contract()["sources"] if s["symbol"] == target[0]]

    monkeypatch.setattr(cli.q, "source_metadata", metadata)
    monkeypatch.setattr(cli, "runtime", lambda: {"torch": "pinned"})
    monkeypatch.setattr(cli.h, "_read", lambda *_: b"public code")
    monkeypatch.setattr(
        cli.q.data,
        "load_verified_kis_paper_private_intraday_catalog",
        lambda **_: pytest.fail("metadata raw access"),
    )
    monkeypatch.setattr(cli, "atomic", lambda *_: pytest.fail("projection write"))
    value = cli.proposed(
        Path("/synthetic"), {s: {str(d): PIN for d in r.DATES} for s, _ in r.TARGETS}
    )
    assert seen == list(r.TARGETS) and len(value["sources"]) == 40
    assert all(s["manifests"] == {} for s in value["sources"])
    assert "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py" in cli.CODE


@pytest.mark.parametrize(
    "field", ("config", "runtime", "code_sha256", "sources", "order", "subset", "foreign")
)
def test_closed_contract_rejects_code_source_runtime_and_cohort_changes(
    tmp_path, monkeypatch, field
):
    contract = source_contract()
    cli.atomic(tmp_path / "precommit.json", contract)
    monkeypatch.setattr(cli, "paths", lambda *_: tmp_path)
    monkeypatch.setattr(cli, "proposed", lambda *_: copy.deepcopy(contract))
    pin = r.digest(r.encode(contract))
    assert cli.verify_contract(tmp_path, tmp_path, pin)[1] == contract
    if field in ("order", "subset", "foreign"):
        broken = copy.deepcopy(contract)
        if field == "order":
            broken["sources"].reverse()
        elif field == "subset":
            broken["sources"].pop()
        else:
            broken["sources"][0]["exchange"] = "AMS"
        cli.atomic(tmp_path / "broken.json", broken)
        monkeypatch.setattr(cli.h, "_json", lambda *_: broken)
    else:
        broken = copy.deepcopy(contract)
        broken[field] = {}
        monkeypatch.setattr(cli, "proposed", lambda *_: broken)
    with pytest.raises(ValueError):
        cli.verify_contract(tmp_path, tmp_path, pin)


def test_freeze_metadata_immutable_external_lineage_before_registry(tmp_path, monkeypatch):
    artifacts, inputs = tmp_path / "artifacts", tmp_path / "inputs"
    (artifacts / "research").mkdir(parents=True)
    inputs.mkdir()
    contract, calls = source_contract(), []
    monkeypatch.setattr(cli, "proposed", lambda *_: contract)
    monkeypatch.setattr(cli.q, "register_frozen_campaign", lambda **kw: calls.append(kw))
    pin = cli.freeze(artifacts, inputs, {})
    output = artifacts / "research" / cli.NAME
    assert set(p.name for p in output.iterdir()) == {"precommit.json"}
    assert json.loads((output / "precommit.json").read_bytes()) == contract
    assert calls[0]["holdout_access"] == "none" and calls[0]["contract_hash"] == pin
    with pytest.raises(FileExistsError):
        cli.freeze(artifacts, inputs, {})


def test_outside_git_and_nonoverlap_paths(tmp_path):
    with pytest.raises(ValueError, match="external_root"):
        cli.paths(cli.REPO, tmp_path)
    with pytest.raises(ValueError, match="root_overlap"):
        cli.paths(tmp_path, tmp_path)


def test_preview_no_operational_io_private_errors_or_gpu(monkeypatch, capsys):
    def forbidden(*_, **__):
        pytest.fail("preview operational IO")

    for name in ("freeze", "dispatch", "readback", "runtime", "proposed", "paths"):
        monkeypatch.setattr(cli, name, forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    assert cli.main([]) == 0
    assert json.loads(capsys.readouterr().out)["actual_fits"] == 3
    assert cli.main(["--cuda", "--contract-sha256", "private-value"]) == 1
    text = capsys.readouterr().out
    assert "private-value" not in text and "unavailable" in text


def test_native_console_import_preview_only():
    process = subprocess.run(
        [sys.executable, "-B", str(SCRIPT)], capture_output=True, text=True, timeout=15, check=False
    )
    assert process.returncode == 0 and json.loads(process.stdout)["status"] == "preview"
    assert not process.stderr


def complete_result(panel, feedback, actions):
    return dict(
        name=cli.NAME,
        contract_sha256=PIN,
        phase="cuda",
        status="complete",
        fits_started=dict.fromkeys(r.MODELS, 1),
        cohort_sha256=cli.cohort_hash(panel[0]),
        evaluation=r.aggregate(panel[0], feedback[1], actions),
    )


@pytest.mark.parametrize("stage", cli.STAGES)
def test_closed_failure_stage_and_counts(stage):
    value = cli.failure(PIN, "cuda", stage, dict(ridge=1, lstm=0, patch=0))
    cli.validate_result(value, PIN, "cuda")
    value["failure_stage"] = "private-error-string"
    with pytest.raises(ValueError):
        cli.validate_result(value, PIN, "cuda")


@pytest.mark.parametrize(
    "kills", ({}, set(), [dict(nonpositive_increment=True)], ["foreign"], [True])
)
def test_strict_whitelisted_kill_strings(panel, feedback, actions, kills):
    value = complete_result(panel, feedback, actions)
    value["evaluation"]["descriptive"]["kill_categories"] = kills
    with pytest.raises(ValueError):
        cli.validate_result(value, PIN, "cuda")


def test_worker_commits_all_inference_before_comparison_payoffs(
    tmp_path, panel, feedback, actions, monkeypatch
):
    torch = pytest.importorskip("torch")
    calls = []
    monkeypatch.setattr(cli, "paths", lambda *_: tmp_path)
    monkeypatch.setattr(cli, "verify_contract", lambda *_: (tmp_path, {}))
    monkeypatch.setattr(cli.h, "_json", lambda *_: dict(contract_sha256=PIN))
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(cli, "load_panel", lambda *_: panel)

    def fit(windows, train, counts, deadline, **kwargs):
        calls.append("fit_infer")
        assert train == feedback[0] and kwargs["device"] == "cuda"
        counts.update(dict.fromkeys(r.MODELS, 1))
        return actions

    def payoffs(windows, catalogs, dates):
        if dates == r.TRAIN:
            calls.append("TRAIN")
            return feedback[0]
        assert calls == ["TRAIN", "fit_infer", "commit"]
        calls.append("COMPARE")
        return feedback[1]

    commit = r.commitment

    def seal(value):
        if not calls or calls[-1] != "COMPARE":
            calls.append("commit")
        return commit(value)

    monkeypatch.setattr(r, "fit_actions", fit)
    monkeypatch.setattr(r, "payoffs", payoffs)
    monkeypatch.setattr(r, "commitment", seal)
    cli.worker(tmp_path, tmp_path, PIN, "cuda", time.monotonic() + 30)
    result = json.loads((tmp_path / "cuda-worker.json").read_bytes())
    assert calls[:4] == ["TRAIN", "fit_infer", "commit", "COMPARE"]
    assert result["status"] == "complete" and result["fits_started"] == dict.fromkeys(r.MODELS, 1)


def test_worker_source_failure_no_subset_fits_or_private_error(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    monkeypatch.setattr(cli, "paths", lambda *_: tmp_path)
    monkeypatch.setattr(cli, "verify_contract", lambda *_: (tmp_path, {}))
    monkeypatch.setattr(cli.h, "_json", lambda *_: dict(contract_sha256=PIN))
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(
        cli, "load_panel", lambda *_: (_ for _ in ()).throw(ValueError("private text"))
    )
    monkeypatch.setattr(r, "fit_actions", lambda *_: pytest.fail("no subset fits"))
    cli.worker(tmp_path, tmp_path, PIN, "cuda", time.monotonic() + 30)
    result = json.loads((tmp_path / "cuda-worker.json").read_bytes())
    assert result["failure_stage"] == "load" and result["fits_started"] == dict.fromkeys(
        r.MODELS, 0
    )
    assert "private text" not in r.encode(result).decode()


def smoke_result():
    return dict(
        name=cli.NAME,
        contract_sha256=PIN,
        phase="cpu-smoke",
        status="complete",
        fits_started=dict.fromkeys(r.MODELS, 0),
        smoke=dict(
            synthetic_windows=1032, synthetic_fits=6, actual_fits=0, cells=42, verified=True
        ),
    )


def dispatch_setup(tmp_path, monkeypatch, cuda):
    cli.atomic(tmp_path / "precommit.json", {})
    smoke = smoke_result()
    if cuda:
        cli.atomic(tmp_path / "cpu-smoke-started.json", dict(contract_sha256=PIN))
        cli.atomic(tmp_path / "cpu-smoke-worker.json", smoke)
        cli.atomic(tmp_path / "cpu-smoke-summary.json", smoke)
    monkeypatch.setattr(cli, "verify_contract", lambda *_: (tmp_path, {}))
    monkeypatch.setattr(
        cli, "resolve_agent_root", lambda _: tmp_path.parent / (tmp_path.name + "-control")
    )
    monkeypatch.setattr(cli.q, "register_campaign_outcome", lambda **_: None)
    return r.digest(r.encode(smoke))


@pytest.mark.parametrize("candidate", (False, True))
def test_timeout_preserves_verified_counts_or_unobserved_and_single_attempt(
    tmp_path, monkeypatch, candidate
):
    smoke_pin = dispatch_setup(tmp_path, monkeypatch, True)
    monkeypatch.setattr(cli, "GpuFileLock", lambda _: nullcontext())

    def supervisor(*_, **__):
        if candidate:
            cli.atomic(
                tmp_path / "cuda-worker.json",
                cli.failure(PIN, "cuda", "fit", dict(ridge=1, lstm=0, patch=0)),
            )
        return dict(timed_out=True, exit_code=-1)

    monkeypatch.setattr(cli.runpy, "run_path", lambda *_: dict(supervise=supervisor))
    value = cli.dispatch(tmp_path, tmp_path, PIN, "cuda", smoke_pin)
    assert value["status"] == "failed"
    assert value["fits_started"] == (dict(ridge=1, lstm=0, patch=0) if candidate else "unobserved")
    with pytest.raises(ValueError, match="single_attempt"):
        cli.dispatch(tmp_path, tmp_path, PIN, "cuda", smoke_pin)


@pytest.mark.parametrize("bad", (False, True))
def test_gpu_lock_held_until_supervisor_reaped_and_replay_verified(
    tmp_path, panel, feedback, actions, monkeypatch, bad
):
    smoke_pin = dispatch_setup(tmp_path, monkeypatch, True)
    events = []

    class Lock:
        def __init__(self, path):
            assert path == cli.resolve_agent_root(tmp_path) / "locks/gpu.lock"

        def __enter__(self):
            events.append("locked")

        def __exit__(self, *_):
            assert "reaped" in events
            events.append("released")

    value = complete_result(panel, feedback, actions)
    if bad:
        value["evaluation"]["cells"][0]["mean_net_unit_bps"] = "999"

    def supervisor(*_, **kwargs):
        assert events == ["locked"] and 0 < kwargs["seconds"] <= 300
        cli.atomic(tmp_path / "cuda-worker.json", value)
        events.append("reaped")
        return dict(timed_out=False, exit_code=0)

    monkeypatch.setattr(cli, "GpuFileLock", Lock)
    monkeypatch.setattr(cli, "load_panel", lambda *_: panel)
    monkeypatch.setattr(cli.runpy, "run_path", lambda *_: dict(supervise=supervisor))
    result = cli.dispatch(tmp_path, tmp_path, PIN, "cuda", smoke_pin)
    assert events == ["locked", "reaped", "released"]
    assert result["status"] == ("failed" if bad else "complete")
    assert result["fits_started"] == dict.fromkeys(r.MODELS, 1)


def test_verify_exact_replay_no_fit_and_admits_unretained_inference(
    tmp_path, panel, feedback, actions, monkeypatch
):
    value = complete_result(panel, feedback, actions)
    dispatch_setup(tmp_path, monkeypatch, True)
    cli.atomic(tmp_path / "cuda-started.json", dict(contract_sha256=PIN))
    cli.atomic(tmp_path / "cuda-worker.json", value)
    cli.atomic(tmp_path / "cuda-summary.json", value)
    monkeypatch.setattr(cli, "verify_contract", lambda *_: (tmp_path, {}))
    monkeypatch.setattr(cli, "load_panel", lambda *_: panel)
    monkeypatch.setattr(r, "fit_actions", lambda *_: pytest.fail("readback fit"))
    result = cli.readback(tmp_path, tmp_path, PIN, r.digest(r.encode(value)))
    assert result["status"] == "verified_complete" and result["cells"] == 42
    assert result["learned_inference_reconstructed"] is False


def test_failed_readback_unobserved_counts_never_reads_payoffs(tmp_path, monkeypatch):
    dispatch_setup(tmp_path, monkeypatch, True)
    value = cli.failure(PIN, "cuda", "dispatch")
    cli.atomic(tmp_path / "cuda-started.json", dict(contract_sha256=PIN))
    cli.atomic(tmp_path / "cuda-summary.json", value)
    monkeypatch.setattr(cli, "load_panel", lambda *_: pytest.fail("failed payoff access"))
    result = cli.readback(tmp_path, tmp_path, PIN, r.digest(r.encode(value)))
    assert result["status"] == "verified_failed" and result["cells"] == 0


@pytest.mark.parametrize("interrupt", (False, True))
def test_existing_supervisor_reaps_before_return_or_interrupt(monkeypatch, interrupt):
    supervisor = cli.runpy.run_path(
        str(cli.REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py")
    )
    events = []

    class Process:
        pid, exitcode = 42, -1
        alive = True

        def start(self):
            events.append("start")

        def join(self, timeout=None):
            events.append("join")
            if len(events) == 2 and interrupt:
                raise KeyboardInterrupt

        def is_alive(self):
            return self.alive

        def terminate(self):
            events.append("terminate")

        def kill(self):
            events.append("kill")
            self.alive = False

        def close(self):
            assert not self.alive
            events.append("close")

    class Context:
        def Process(self, **kwargs):
            assert kwargs["daemon"] is False
            return Process()

    monkeypatch.setattr(supervisor["multiprocessing"], "get_context", lambda kind: Context())
    if interrupt:
        with pytest.raises(KeyboardInterrupt):
            supervisor["supervise"](lambda: None, (), seconds=0.01, name="synthetic")
    else:
        value = supervisor["supervise"](lambda: None, (), seconds=0.01, name="synthetic")
        assert value["timed_out"] is True and value["exit_code"] == -1
        assert events[-1] == "close"
    assert events.index("terminate") < events.index("kill") < len(events) - 1
