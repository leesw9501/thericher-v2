"""Synthetic zero-shot checks; no provider, retained rows, weights, or CUDA."""

from __future__ import annotations

import copy
import json
import runpy
import socket
import time
from contextlib import contextmanager
from dataclasses import replace
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pandas_market_calendars as calendars
import pytest

from thericher_v2.data import tiingo_etf_daily as daily
from thericher_v2.research import timesfm_return_development as s

HASH = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64


def forbidden(*args, **kwargs):
    raise AssertionError("external data, weights, credentials, network, or CUDA forbidden")


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(daily, "read_tiingo_api_token", forbidden)
    monkeypatch.setattr(s.base, "load_verified_tiingo_etf_d1_snapshot", forbidden)
    monkeypatch.setattr(s.base, "verify_metadata", forbidden)
    monkeypatch.setattr(s.base, "register_frozen_campaign", forbidden)
    monkeypatch.setattr(s, "verify_assets", forbidden)
    monkeypatch.setattr(s, "forecast_timesfm_2p5", forbidden)
    monkeypatch.setattr(
        s,
        "public_assets",
        lambda: dict(
            NAME="synthetic-timesfm-runtime-study",
            MODEL_ID="synthetic/model",
            REVISION="a" * 40,
            PINS={"config.json": HASH, "model.safetensors": OTHER},
            IMAGE=HASH,
            verify_files=forbidden,
        ),
    )
    versions = {"torch": "2.7.0+cu128", "timesfm": "2.0.2"}
    monkeypatch.setattr(
        s.importlib.metadata, "version", lambda name: versions.get(name, "synthetic")
    )


@pytest.fixture(scope="module")
def days():
    schedule = calendars.get_calendar("NYSE").schedule(
        start_date="2025-01-01", end_date="2026-07-31"
    )
    return [d.date().isoformat() for d in schedule.index]


@pytest.fixture
def contract(days, monkeypatch):
    monkeypatch.setattr(s.geometry, "calendar_days", lambda: days)
    return s.proposed_contract()


@pytest.fixture(scope="module")
def rows(days):
    return {
        symbol: tuple(
            daily.TiingoEtfDailyRow(
                symbol=symbol,
                session_date=date.fromisoformat(day),
                open=Decimal(100),
                high=Decimal(103),
                low=Decimal(97),
                close=Decimal("100.3"),
                volume=Decimal(1000),
                div_cash=Decimal(0),
                split_factor=Decimal(1),
            )
            for day in days
        )
        for symbol in s.SYMBOLS
    }


def predictor(model, pins, x, *, horizon, device):
    assert set(pins) == {"config.json", "model.safetensors"}
    assert x.dtype == np.float32 and x.ndim == 2 and x.shape[1] == 128
    assert horizon == 1 and device == "cuda"
    return np.full((len(x), 1), -7.0, dtype=np.float32), None


def runtime(prepared):
    return dict(
        torch="2.7.0+cu128",
        cuda="12.8",
        device="synthetic CUDA device",
        peak_allocated_bytes=1024,
        memory_budget_bytes=2048,
        point_count=sum(len(g["x"]) for g in prepared),
        training=False,
        predictions_retained=False,
    )


def scored(rows, contract, *, predict=predictor):
    prepared = s.prepare(rows, contract["plan"])
    frozen = s.forecast_all(prepared, "synthetic-model", predictor=predict)
    pin = s.digest(s.encode(contract))
    return s.score(prepared, frozen, contract, pin, runtime(prepared))


@pytest.fixture
def frozen(tmp_path, monkeypatch, contract):
    root, market = tmp_path / "artifacts", tmp_path / "market"
    checks, registrations = [], []
    monkeypatch.setattr(s.base, "verify_metadata", lambda *args: checks.append(args))
    monkeypatch.setattr(s, "verify_assets", lambda _: tmp_path / "synthetic-model")
    monkeypatch.setattr(s.base, "register_frozen_campaign", lambda **kw: registrations.append(kw))
    pin = s.freeze(root, market)
    output, actual = s.verify(root, market, pin)
    assert actual == contract
    return SimpleNamespace(
        root=root,
        market=market,
        pin=pin,
        output=output,
        contract=actual,
        checks=checks,
        registrations=registrations,
    )


def test_calendar_first_128_contexts_and_fixed_two_periods(days):
    plan = s.build_plan(days)
    assert len(plan) == 145
    assert [sum(p["period"] == name for p in plan) for name, _, _ in s.PERIODS] == [61, 84]
    assert plan[0]["target"] == "2026-01-02" and plan[-1]["target"] == "2026-07-31"
    assert plan[0]["history"][0] == "2025-07-01"
    assert plan[0]["history"][-1] == "2025-12-31"
    for p in plan:
        idx = days.index(p["target"])
        assert p["history"] == days[idx - 128 : idx]
        assert len(p["history"]) == 128 and p["history"][-1] < p["target"]
        assert p["target"] > s.PUBLIC_BEFORE


@pytest.mark.parametrize("kind", ("duplicate", "reversed", "invalid", "short"))
def test_bad_calendar_rejected(days, kind):
    mutated = list(days)
    if kind == "duplicate":
        mutated.insert(20, mutated[20])
    elif kind == "reversed":
        mutated.reverse()
    elif kind == "invalid":
        mutated[0] = "not-a-date"
    else:
        mutated = [d for d in days if d >= "2026-01-01"]
    with pytest.raises(ValueError):
        s.build_plan(mutated)


@pytest.mark.parametrize("boundary", ("2026-01-02", "2026-01-03"))
def test_targets_must_strictly_follow_checkpoint(days, monkeypatch, boundary):
    monkeypatch.setattr(s, "PUBLIC_BEFORE", boundary)
    with pytest.raises(ValueError, match="target_predates_checkpoint"):
        s.build_plan(days)


def test_contract_is_zero_shot_non_promoting_with_source_binding(contract):
    assert contract["source"] == s.base.source_identity()
    config = contract["config"]
    assert config["context"] == 128 and config["horizon"] == 1 and config["cells"] == 90
    assert config["costs"] == [5, 10, 20]
    assert all(config[k] is False for k in ("training", "selection", "holdout", "paper_input"))
    assert config["budget"] == dict(seconds=600, gpu=True, passes=1, training=False)
    pin = s.digest(s.encode(contract))
    assert s.header(contract, pin)["evidence_grade"] == "POST_CHECKPOINT_SEEN_DATA_DEVELOPMENT"


@pytest.mark.parametrize("field", ("source", "config", "runtime", "name", "pin"))
def test_header_rejects_changed_binding(contract, field):
    changed = copy.deepcopy(contract)
    if field == "source":
        changed["source"]["dataset_sha256"] = OTHER
    elif field == "config":
        changed["config"]["context"] = 64
    elif field == "runtime":
        changed["runtime"]["timesfm"] = "unsupported"
    elif field == "name":
        changed["name"] = "other-study"
    pin = OTHER if field == "pin" else s.digest(s.encode(changed))
    with pytest.raises(ValueError):
        s.header(changed, pin)


def test_past_only_prepare_and_fake_predictor_never_receive_targets(rows, contract):
    prepared = s.prepare(rows, contract["plan"])
    calls = []

    def fake(model, pins, contexts, *, horizon, device):
        calls.append((contexts.shape, contexts.dtype))
        assert set(pins) == {"config.json", "model.safetensors"}
        assert model == "synthetic-model" and horizon == 1 and device == "cuda"
        assert np.all(contexts == np.float32(30))
        return np.full((len(contexts), 1), -7, dtype=np.float32), None

    frozen_forecasts = s.forecast_all(prepared, "synthetic-model", predictor=fake)
    assert calls == [((435, 128), np.dtype("float32"))]
    for forecasts, actions in frozen_forecasts:
        assert np.all(forecasts["timesfm"] == -7)
        assert np.all(forecasts["rolling_mean"] == 30)
        assert np.all(forecasts["previous_return"] == 30)
        assert np.all(forecasts["zero"] == 0)
        assert not actions["timesfm"].any()
        assert all(not v.flags.writeable for v in (*forecasts.values(), *actions.values()))


@pytest.mark.parametrize("missing", (False, True))
def test_current_target_and_future_mutation_cannot_change_earlier_input_or_forecast(
    rows,
    contract,
    missing,
):
    target = date(2026, 7, 31) if missing else date.fromisoformat(contract["plan"][0]["target"])
    modified = {
        symbol: tuple(
            replace(r, close=Decimal("98")) if r.session_date >= target else r
            for r in stream
            if not (missing and r.session_date == target)
        )
        for symbol, stream in rows.items()
    }
    before, after = (s.prepare(data, contract["plan"]) for data in (rows, modified))
    left = s.forecast_all(before, "model", predictor=predictor)
    right = s.forecast_all(after, "model", predictor=predictor)
    for i in (1, 3, 5) if missing else (0, 2, 4):
        idx = before[i]["dates"].index(target.isoformat())
        assert after[i]["dates"][idx] == before[i]["dates"][idx] == target.isoformat()
        np.testing.assert_array_equal(before[i]["x"][idx], after[i]["x"][idx])
        for name in s.FORECASTS:
            assert left[i][0][name][idx] == right[i][0][name][idx]
        for name in s.POLICIES:
            assert left[i][1][name][idx] == right[i][1][name][idx]
    if missing:
        result = s.score(after, right, contract, s.digest(s.encode(contract)), runtime(after))
        for group in result["groups"][1::2]:
            assert group["censored"] == 1
            assert group["planned"] == 84


def test_missing_history_is_excluded_without_bridging_or_renumbering(rows, contract):
    missing = contract["plan"][0]["history"][0]
    changed = dict(rows)
    changed["SPY"] = tuple(r for r in rows["SPY"] if r.session_date.isoformat() != missing)
    prepared = s.prepare(changed, contract["plan"])
    first = prepared[0]
    expected = [
        p["target"]
        for p in contract["plan"]
        if p["period"] == "2026-Q1" and missing not in p["history"]
    ]
    assert first["dates"] == expected and first["planned"] == 61
    assert first["dates"][0] == "2026-01-05" and len(first["x"]) == 60
    assert len(prepared[2]["x"]) == 61


def test_per_day_ohlc_positive_scaling_preserves_context_and_scores(rows, contract):
    changed = {}
    for symbol, stream in rows.items():
        changed[symbol] = tuple(
            replace(
                r,
                **{k: getattr(r, k) * Decimal(i % 7 + 1) for k in ("open", "high", "low", "close")},
            )
            for i, r in enumerate(stream)
        )
    before, after = (s.prepare(data, contract["plan"]) for data in (rows, changed))
    for a, b in zip(before, after, strict=True):
        np.testing.assert_array_equal(a["x"], b["x"])
    assert scored(rows, contract) == scored(changed, contract)


@pytest.mark.parametrize("bad", ("symbol", "duplicate", "reverse", "date"))
def test_invalid_row_identity_and_order_fail(rows, contract, bad):
    changed = dict(rows)
    stream = list(rows["SPY"])
    if bad == "symbol":
        stream[0] = replace(stream[0], symbol="QQQ")
    elif bad == "date":
        stream[0] = replace(stream[0], session_date="2025-01-02")
    elif bad == "reverse":
        stream.reverse()
    else:
        stream.insert(0, stream[0])
    changed["SPY"] = tuple(stream)
    with pytest.raises(ValueError):
        s.prepare(changed, contract["plan"])


@pytest.mark.parametrize("bad", ("shape", "nan", "inf"))
def test_predictor_bad_geometry_or_nonfinite_output_rejected(rows, contract, bad):
    def fake(model, pins, x, **kwargs):
        if bad == "shape":
            return np.zeros(len(x)), None
        return np.full((len(x), 1), np.nan if bad == "nan" else np.inf), None

    with pytest.raises(ValueError, match="forecast_shape"):
        s.forecast_all(s.prepare(rows, contract["plan"]), "model", predictor=fake)


def test_empty_group_does_not_call_predictor(rows, contract):
    prepared = s.prepare(rows, contract["plan"])
    prepared[0]["x"] = np.empty((0, 128), dtype=np.float32)
    with pytest.raises(ValueError, match="input_unavailable"):
        s.forecast_all(prepared, "model", predictor=forbidden)


def test_fixed_strict_threshold_and_all_in_cost_not_roundtrip_doubled(rows, contract):
    def edges(model, pins, x, **kwargs):
        return np.resize(np.array([-10, 0, 20, 20.01, 30], dtype=np.float32), len(x))[:, None], None

    result = scored(rows, contract, predict=edges)
    assert len(result["cells"]) == 90 and len(result["groups"]) == 6
    for group in result["groups"]:
        assert Decimal(group["metrics"]["rolling_mean"]["mse_bps2"]) == 0
        assert Decimal(group["metrics"]["previous_return"]["mse_bps2"]) == 0
        assert Decimal(group["metrics"]["zero"]["mse_bps2"]) == 900
        assert Decimal(group["metrics"]["zero"]["mae_bps"]) == 30
    for cell in result["cells"]:
        trades = cell["trades"]
        assert Decimal(cell["gross_sum_bps"]) == trades * 30
        assert Decimal(cell["net_sum_bps"]) == trades * (30 - cell["cost"])
        if cell["policy"] == "cash":
            assert trades == cell["selected"] == 0 and Decimal(cell["mean_net_bps"]) == 0
        peers = [
            c
            for c in result["cells"]
            if all(c[k] == cell[k] for k in ("symbol", "period", "policy"))
        ]
        assert len({c["action_sha256"] for c in peers}) == 1
        assert len({c["trades"] for c in peers}) == 1
    prepared = s.prepare(rows, contract["plan"])
    forecasts, actions = s.forecast_all(prepared, "model", predictor=edges)[0]
    assert forecasts["timesfm"][2] == 20
    assert list(actions["timesfm"][:5]) == [False, False, False, True, True]


def test_scores_have_controls_and_only_aggregates_no_raw_values(rows, contract):
    result = scored(rows, contract)
    for group in result["groups"]:
        assert Decimal(group["metrics"]["timesfm"]["mse_bps2"]) == 1369
        assert Decimal(group["metrics"]["timesfm"]["mae_bps"]) == 37
    encoded = s.encode(result).decode()
    for forbidden_field in (
        '"open"',
        '"close"',
        '"dates"',
        '"targets"',
        '"predictions"',
        '"x"',
        '"index"',
    ):
        assert forbidden_field not in encoded
    assert result["runtime"]["training"] is result["runtime"]["predictions_retained"] is False


@pytest.mark.parametrize(
    "mutation",
    (
        "extra",
        "group_order",
        "count_bool",
        "metric_nan",
        "cell_order",
        "cost",
        "cash",
        "runtime",
        "training",
    ),
)
def test_result_validator_rejects_corruption(rows, contract, mutation):
    result = scored(rows, contract)
    if mutation == "extra":
        result["raw"] = "must not escape"
    elif mutation == "group_order":
        result["groups"].reverse()
    elif mutation == "count_bool":
        result["groups"][0]["censored"] = False
    elif mutation == "metric_nan":
        result["groups"][0]["metrics"]["zero"]["mse_bps2"] = "NaN"
    elif mutation == "cell_order":
        result["cells"].reverse()
    elif mutation == "cost":
        result["cells"][1]["net_sum_bps"] = "12345"
    elif mutation == "cash":
        result["cells"][4]["selected"] = 1
    elif mutation == "runtime":
        result["runtime"]["point_count"] += 1
    else:
        result["runtime"]["training"] = True
    with pytest.raises(ValueError):
        s.validate_result(result, contract, s.digest(s.encode(contract)))


def test_cost_path_cannot_change_action_hash(rows, contract):
    result = scored(rows, contract)
    result["cells"][5]["action_sha256"] = OTHER
    with pytest.raises(ValueError, match="cost_changes_action"):
        s.validate_result(result, contract, s.digest(s.encode(contract)))


@pytest.mark.parametrize(
    "mutation", ("cohort_hash", "action_hash", "cuda", "device", "point_count_type")
)
def test_result_rejects_malformed_identity_or_gpu_runtime(rows, contract, mutation):
    result = scored(rows, contract)
    if mutation == "cohort_hash":
        result["groups"][0]["cohort_sha256"] = "not-a-hash"
    elif mutation == "action_hash":
        for cell in result["cells"]:
            if (cell["symbol"], cell["period"], cell["policy"]) == ("SPY", "2026-Q1", "timesfm"):
                cell["action_sha256"] = "not-a-hash"
    elif mutation == "cuda":
        result["runtime"]["cuda"] = None
    elif mutation == "device":
        result["runtime"]["device"] = ""
    else:
        result["runtime"]["point_count"] = float(result["runtime"]["point_count"])
    with pytest.raises(ValueError):
        s.validate_result(result, contract, s.digest(s.encode(contract)))


def test_freeze_verify_and_single_immutable_source_contract(frozen):
    assert len(frozen.registrations) == 1 and len(frozen.checks) == 2
    assert frozen.registrations[0]["holdout_access"] == "none"
    assert frozen.registrations[0]["dataset_hash"] == s.base.DATASET_HASH
    with pytest.raises(FileExistsError):
        s.freeze(frozen.root, frozen.market)
    raw = (frozen.output / "precommit.json").read_bytes()
    assert s.digest(raw) == frozen.pin
    (frozen.output / "precommit.json").write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="precommit_changed"):
        s.verify(frozen.root, frozen.market, frozen.pin)


@pytest.mark.parametrize("kind", ("absent", "wrong_pin", "extra"))
def test_worker_requires_exact_attempt_before_any_data_load(frozen, kind):
    if kind != "absent":
        attempt = {"contract_sha256": OTHER if kind == "wrong_pin" else frozen.pin}
        if kind == "extra":
            attempt["extra"] = True
        s.atomic_new(frozen.output / "started.json", attempt)
    with pytest.raises((ValueError, FileNotFoundError)):
        s.run_worker(
            frozen.root,
            frozen.market,
            frozen.pin,
            frozen.output / "worker-result.json",
            time.monotonic() + 1,
        )
    assert not (frozen.output / "worker-result.json").exists()


def test_worker_rejects_output_outside_owned_directory(frozen):
    with pytest.raises(ValueError, match="worker_path"):
        s.run_worker(
            frozen.root, frozen.market, frozen.pin, frozen.root / "other.json", time.monotonic() + 1
        )


def test_worker_data_failure_is_categorical_and_has_no_partial_rows(frozen, monkeypatch):
    s.atomic_new(frozen.output / "started.json", {"contract_sha256": frozen.pin})

    def fail(*args, **kwargs):
        raise ValueError("synthetic sensitive detail")

    monkeypatch.setattr(s.base, "load_verified_tiingo_etf_d1_snapshot", fail)
    path = frozen.output / "worker-result.json"
    s.run_worker(frozen.root, frozen.market, frozen.pin, path, time.monotonic() + 1)
    result = json.loads(path.read_bytes())
    assert result == s.failure(frozen.contract, frozen.pin, "runtime_or_invariant_failure")
    assert "sensitive" not in path.read_text()
    s.validate_result(result, frozen.contract, frozen.pin)
    result["cells"] = [{"partial": True}]
    with pytest.raises(ValueError, match="failure_shape"):
        s.validate_result(result, frozen.contract, frozen.pin)


@pytest.mark.parametrize("mode", ("timeout", "raise"))
def test_parent_gpu_lock_spans_dispatch_and_releases_on_failure(frozen, monkeypatch, mode):
    parent = runpy.run_path(str(s.REPO / "scripts/run_tiingo_month_start_development.py"))
    launcher = runpy.run_path(str(s.REPO / "scripts/run_timesfm_return_development.py"))
    namespace = parent["dispatch"].__globals__
    events = []

    @contextmanager
    def fake_lock(path):
        assert path == frozen.root / "agent" / "locks/gpu.lock"
        events.append("acquire")
        try:
            yield
        finally:
            events.append("release")

    def supervise(*args, **kwargs):
        assert events == ["acquire"] and 0 < kwargs["seconds"] <= 600
        events.append("timeout")
        return dict(timed_out=True, exit_code=None)

    def dispatch_error(*args):
        assert events == ["acquire"]
        events.append("raise")
        raise RuntimeError("synthetic dispatch failure")

    class ParentMain:
        __globals__ = namespace

        def __call__(self, argv):
            return namespace["dispatch"](frozen.root, frozen.market, frozen.pin)

    if mode == "raise":
        monkeypatch.setitem(namespace, "dispatch", dispatch_error)
    monkeypatch.setitem(namespace, "supervise", supervise)
    monkeypatch.setitem(namespace, "register_campaign_outcome", lambda **kwargs: None)
    entry = launcher["main"]
    monkeypatch.setitem(entry.__globals__, "os", SimpleNamespace(environ={}))
    monkeypatch.setitem(
        entry.__globals__, "runpy", SimpleNamespace(run_path=lambda path: {"main": ParentMain()})
    )
    monkeypatch.setitem(entry.__globals__, "GpuFileLock", fake_lock)
    monkeypatch.setitem(entry.__globals__, "resolve_agent_root", lambda _: frozen.root / "agent")
    if mode == "raise":
        with pytest.raises(RuntimeError, match="synthetic dispatch failure"):
            entry([])
    else:
        assert entry([])["criterion"] == "hard_timeout"
        assert events == ["acquire", "timeout", "release"]
        with pytest.raises(ValueError, match="attempt_already_exists"):
            namespace["dispatch"](frozen.root, frozen.market, frozen.pin)
        assert events == ["acquire", "timeout", "release", "acquire", "release"]
    if mode == "raise":
        assert events == ["acquire", mode, "release"]


def test_worker_entry_suppresses_exception_body(monkeypatch):
    def fail(*args):
        raise RuntimeError("synthetic private body")

    monkeypatch.setattr(s, "run_worker", fail)
    with pytest.raises(SystemExit) as caught:
        s.worker_entry()
    assert caught.value.code == 1 and caught.value.__suppress_context__
