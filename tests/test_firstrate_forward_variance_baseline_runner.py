from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research.forward_variance_baseline import (
    ForwardVarianceBaselineConfig,
    ForwardVarianceRecord,
    fit_forward_variance_baseline,
    predict_forward_variance_baseline,
)
from thericher_v2.research.intraday_variance_targets import IntradayVarianceTarget

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "risk_baseline_test_runner", SCRIPTS / "run_firstrate_forward_variance_baseline.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pair(day=date(2023, 1, 3), *, minutes=390):
    opening = datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=14, minutes=30)
    session = SessionWindow(opening, opening + timedelta(minutes=minutes))
    streams = []
    for symbol in ("QQQ", "SPY"):
        rows = []
        for index in range(minutes):
            value = Decimal(100) + Decimal(index % 11) / Decimal(10)
            rows.append(
                Bar(
                    symbol=symbol,
                    market="US",
                    timeframe=Timeframe.M1,
                    start_ts=opening + timedelta(minutes=index),
                    open=value,
                    high=value,
                    low=value,
                    close=value,
                    volume=Decimal(1),
                    complete=True,
                )
            )
        streams.append(tuple(rows))
    return tuple(streams), session


def test_default_plan_has_no_file_source_credentials_or_fits(runner, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("default plan must not perform I/O or a fit")

    monkeypatch.setattr(runner, "freeze", forbidden)
    monkeypatch.setattr(runner, "compute", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(sys, "argv", ["runner"])
    assert runner.main() == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "plan",
        "study": runner.STUDY,
        "actual_fits": 0,
        "broker_calls": 0,
    }


def test_records_keep_exact_past_and_forward_geometry(runner):
    streams, session = pair()
    records = runner.records_from_pair(streams, session)
    for row in records:
        assert row.features_available_at == row.decision_at
        assert row.decision_at == session.open_ts + 150 * runner.MINUTE
        assert row.target.target_start == row.decision_at + runner.MINUTE
        assert row.target.available_at == row.decision_at + 62 * runner.MINUTE
        assert row.features[0] == row.past_realized_variance
        assert row.features[0] > 0
    assert records[0].features == records[1].features[::-1]


@pytest.mark.parametrize("mutation", ["remove", "incomplete", "value"])
def test_future_mutations_cannot_change_causal_input(runner, mutation):
    streams, session = pair()
    original = runner.records_from_pair(streams, session)
    at = original[0].decision_at
    changed = []
    for stream in streams:
        if mutation == "remove":
            values = tuple(bar for bar in stream if bar.start_ts < at)
        else:
            values = tuple(
                replace(bar, complete=False)
                if mutation == "incomplete" and bar.start_ts >= at
                else replace(
                    bar, open=bar.open * 3, high=bar.high * 3, low=bar.low * 3, close=bar.close * 3
                )
                if mutation == "value" and bar.start_ts == at + runner.MINUTE
                else bar
                for bar in stream
            )
        changed.append(values)
    records = runner.records_from_pair(tuple(changed), session)
    assert all(
        replace(a, target=None, target_status="not_inspected")
        == replace(b, target=None, target_status="not_inspected")
        for a, b in zip(original, records, strict=True)
    )
    if mutation == "value":
        assert records[0].target != original[0].target


def test_early_close_keeps_inputs_and_scoped_target_shortfall(runner):
    streams, session = pair(minutes=210)
    rows = runner.records_from_pair(streams, session)
    assert all(row.input_status == "available" for row in rows)
    assert all(row.target_status == "session_horizon_shortfall" for row in rows)
    assert all(row.target is None for row in rows)


def training_model(runner):
    records = []
    for offset in range(3):
        streams, session = pair(date(2023, 1, 3) + timedelta(days=offset))
        records.append(runner.records_from_pair(streams, session)[0])
    config = ForwardVarianceBaselineConfig(
        "QQQ", runner.FEATURES, date(2023, 1, 5), date(2023, 1, 7), 60, 119
    )
    return tuple(records), fit_forward_variance_baseline(records, config=config)


def test_numeric_model_roundtrip_and_train_attestation_do_not_refit(runner, monkeypatch):
    rows, model = training_model(runner)
    payload = runner.jsonable(asdict(model))
    monkeypatch.setattr(
        runner, "fit_forward_variance_baseline", lambda *a, **k: pytest.fail("refit")
    )
    restored = runner.read_model(payload, model.config)
    assert restored == model
    assert runner.attest_train(restored, rows, 1e-10) == {
        "scheduled": 3,
        "eligible": 3,
        "excluded": 0,
        "exclusions": {},
    }
    streams, session = pair(date(2023, 1, 7))
    later = runner.records_from_pair(streams, session)[:1]
    assert predict_forward_variance_baseline(restored, later) == predict_forward_variance_baseline(
        model, later
    )


@pytest.mark.parametrize(
    "field", ["feature_mean", "feature_scale", "intercept", "train_mean_variance"]
)
def test_train_transform_corruption_is_rejected(runner, field):
    rows, model = training_model(runner)
    value = getattr(model, field)
    changed = tuple(item + 1 for item in value) if isinstance(value, tuple) else value + 1
    with pytest.raises(runner.smoke.SmokeFault, match="TRAIN_transform_mismatch"):
        runner.attest_train(replace(model, **{field: changed}), rows, 1e-10)


def test_freeze_precedes_registration_and_never_parses_values(runner, monkeypatch, tmp_path):
    root = tmp_path / "study"
    order = []
    monkeypatch.setattr(runner.smoke, "file_hash", lambda path: "sha256:" + "a" * 64)
    monkeypatch.setattr(runner, "check_pins", lambda *args: order.append("pins"))

    def register(plan, actual_root, artifact_base):
        assert actual_root == root and (root / "contract.json").is_file()
        order.append("registered_after_contract")
        return type("Entry", (), {"record_sha256": "sha256:" + "b" * 64})()

    monkeypatch.setattr(runner, "register", register)
    monkeypatch.setattr(runner, "load_source_cases", lambda *args: pytest.fail("source values"))
    runner.freeze(
        root,
        tmp_path / "market",
        tmp_path / "lineage",
        tmp_path / "normalization",
        tmp_path / "preparation",
        tmp_path / "artifacts",
    )
    assert order == ["pins", "registered_after_contract"]
    original = (root / "contract.json").read_bytes()
    runner.freeze(
        root,
        tmp_path / "market",
        tmp_path / "lineage",
        tmp_path / "normalization",
        tmp_path / "preparation",
        tmp_path / "artifacts",
    )
    assert (root / "contract.json").read_bytes() == original
    assert order == ["pins", "registered_after_contract"] * 2


def synthetic_compute(runner, monkeypatch):
    sessions, grouped = [], {symbol: {} for symbol in ("QQQ", "SPY")}
    for index in range(251):
        streams, session = pair(date(2022, 1, 1) + timedelta(days=index), minutes=212)
        sessions.append(session)
        for symbol, stream in zip(("QQQ", "SPY"), streams, strict=True):
            grouped[symbol][session.open_ts.date()] = (stream[149], stream[151])

    def records(streams, session):
        index = (session.open_ts.date() - date(2022, 1, 1)).days
        at = session.open_ts + 150 * runner.MINUTE
        result = []
        for symbol, stream in zip(("QQQ", "SPY"), streams, strict=True):
            forward = [bar for bar in stream if bar.start_ts > at]
            target = None
            status = "missing_required_bars"
            if index in (25, 220):
                status = "session_horizon_shortfall"
            elif forward and forward[0].complete:
                value = float(forward[0].open) * 1e-8 * (1 + index % 7)
                target = IntradayVarianceTarget(
                    symbol,
                    at,
                    60,
                    at + runner.MINUTE,
                    at + 61 * runner.MINUTE,
                    at + 62 * runner.MINUTE,
                    value,
                )
                status = "available"
            own, peer = 1e-5 * (1 + index % 9), 1e-5 * (1 + index % 13)
            features = (own, peer) if symbol == "QQQ" else (peer, own)
            result.append(
                ForwardVarianceRecord(
                    session.open_ts.date(),
                    symbol,
                    at,
                    at,
                    features,
                    features[0],
                    target,
                    "available",
                    status,
                )
            )
        return tuple(result)

    monkeypatch.setattr(runner.platform, "python_version", lambda: "3.12.15")
    monkeypatch.setattr(
        runner.importlib.metadata,
        "version",
        lambda name: {
            "numpy": "2.5.1",
            "pandas-market-calendars": "5.4.0",
        }[name],
    )
    monkeypatch.setattr(runner, "check_pins", lambda *args: ())
    monkeypatch.setattr(runner, "load_source_cases", lambda *args: (tuple(sessions), grouped))
    monkeypatch.setattr(runner, "records_from_pair", records)
    return grouped


def test_source_adapter_two_train_only_fits_and_exact_json_replay(runner, monkeypatch):
    synthetic_compute(runner, monkeypatch)
    original_fit, fitted_dates = runner.fit_forward_variance_baseline, []

    def fit(rows, *, config):
        fitted_dates.append(tuple(row.session_date for row in rows))
        return original_fit(rows, config=config)

    monkeypatch.setattr(runner, "fit_forward_variance_baseline", fit)
    args = (runner.contract({}), None, None, None, None, float("inf"))
    result, models = runner.compute(*args)
    assert len(fitted_dates) == 2
    assert all(len(days) == 160 and max(days) == date(2022, 6, 9) for days in fitted_dates)
    assert all(item["eligible"] == 159 for item in result["training"].values())
    for symbol in ("QQQ", "SPY"):
        assert result["comparison"]["etfs"][symbol]["all90"]["eligible_count"] == 89
    assert result["mutation_checks"] == {
        "prefix_future_removal": 251,
        "comparison_future_support": 90,
        "comparison_future_value": 90,
        "target_blind_forecast": 180,
    }
    monkeypatch.setattr(
        runner, "fit_forward_variance_baseline", lambda *a, **k: pytest.fail("refit")
    )
    replay, restored = runner.compute(*args, models=json.loads(json.dumps(models)))
    assert replay == json.loads(json.dumps(result))
    assert restored == models


def test_comparison_future_mutation_preserves_train_state_and_prior_forecasts(runner, monkeypatch):
    grouped = synthetic_compute(runner, monkeypatch)
    args = (runner.contract({}), None, None, None, None, float("inf"))
    original, models = runner.compute(*args)
    for streams in grouped.values():
        for day, bars in streams.items():
            if day >= date(2022, 6, 11):
                streams[day] = tuple(
                    replace(
                        bar,
                        open=bar.open * 2,
                        high=bar.high * 2,
                        low=bar.low * 2,
                        close=bar.close * 2,
                    )
                    if bar.start_ts.minute == 1
                    else bar
                    for bar in bars
                )
    changed, changed_models = runner.compute(*args)
    assert changed_models == models
    assert changed["training"] == original["training"]
    for symbol in ("QQQ", "SPY"):
        assert changed["commitments"][symbol]["TRAIN"] == original["commitments"][symbol]["TRAIN"]
        assert (
            changed["commitments"][symbol]["comparison"]
            != original["commitments"][symbol]["comparison"]
        )


def test_replay_rejects_modified_numeric_model_before_use(runner, tmp_path):
    models = {"QQQ": {"coefficients": [1.0, 2.0]}}
    expected = {"model_sha256": runner.smoke.digest(runner.smoke.encode(models))}
    runner.smoke.write_once(tmp_path / "result.json", expected)
    runner.smoke.write_once(tmp_path / "models.json", {"QQQ": {"coefficients": [2.0, 2.0]}})
    with pytest.raises(runner.smoke.SmokeFault, match="model_changed"):
        runner.read_replay(tmp_path, runner.smoke.file_hash(tmp_path / "result.json"))


def test_freeze_registry_failure_can_reattach_exact_contract(runner, monkeypatch, tmp_path):
    root = tmp_path / "study"
    monkeypatch.setattr(runner.smoke, "file_hash", lambda path: "sha256:" + "a" * 64)
    monkeypatch.setattr(runner, "check_pins", lambda *args: ())
    attempts = []

    def register(*args):
        attempts.append((root / "contract.json").read_bytes())
        if len(attempts) == 1:
            raise RuntimeError("synthetic ledger contention")
        return type("Entry", (), {"record_sha256": "sha256:" + "b" * 64})()

    monkeypatch.setattr(runner, "register", register)
    args = (root, tmp_path, tmp_path, tmp_path, tmp_path, tmp_path)
    with pytest.raises(RuntimeError, match="synthetic ledger contention"):
        runner.freeze(*args)
    assert runner.freeze(*args)["actual_fits"] == 0
    assert attempts[0] == attempts[1]
    (root / "contract.json").write_bytes(b"{}")
    with pytest.raises(runner.smoke.SmokeFault, match="existing_contract_mismatch"):
        runner.freeze(*args)
