"""Synthetic geometry campaign checks. Never read retained rows or call a provider."""

from __future__ import annotations

import json
import runpy
import socket
import time
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.data import tiingo_etf_daily as daily
from thericher_v2.data.tiingo_etf_daily import TiingoEtfDailyRow
from thericher_v2.research import tiingo_geometry_ridge_development as s


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("real data, network and credentials forbidden")

    monkeypatch.setattr(s, "load_verified_tiingo_etf_d1_snapshot", forbidden)
    monkeypatch.setattr(s.base, "load_verified_tiingo_etf_d1_snapshot", forbidden)
    monkeypatch.setattr(daily, "read_tiingo_api_token", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def weekdays(start, count):
    days = []
    while len(days) < count:
        if start.weekday() < 5:
            days.append(start.isoformat())
        start += timedelta(days=1)
    return days


@pytest.fixture(scope="module")
def days():
    return (
        weekdays(date(2000, 12, 1), 21)
        + weekdays(date(2001, 1, 1), 600)
        + weekdays(date(2013, 1, 1), 125)
        + weekdays(date(2020, 1, 1), 125)
    )


@pytest.fixture
def contract(days, monkeypatch):
    monkeypatch.setattr(s, "calendar_days", lambda: days)
    return s.proposed_contract()


@pytest.fixture(scope="module")
def rows(days):
    return {
        symbol: tuple(
            TiingoEtfDailyRow(
                symbol,
                date.fromisoformat(d),
                Decimal(100),
                Decimal(102),
                Decimal(98),
                Decimal("100.3"),
                Decimal(1000),
                Decimal(0),
                Decimal(1),
            )
            for d in days
        )
        for symbol in s.SYMBOLS
    }


def evaluate(contract, rows):
    return s.evaluate(rows, contract, s.digest(s.encode(contract)), deadline=time.monotonic() + 45)


def prepared(contract, rows, symbol="SPY", fold=0):
    return s.prepare(
        {r.session_date.isoformat(): r for r in rows[symbol]},
        contract["plan"],
        contract["plan"]["folds"][fold],
        time.monotonic() + 45,
    )


def change_row(rows, symbol, index, **values):
    result = dict(rows)
    result[symbol] = tuple(
        replace(r, **values) if i == index else r for i, r in enumerate(rows[symbol])
    )
    return result


def test_exact_12_fits_108_cells_six_twofold_tables_and_costs(contract, rows):
    result = evaluate(contract, rows)
    assert result["status"] == "complete"
    assert sum(g["fits"] for g in result["groups"]) == 12
    assert len(result["cells"]) == 108 and len(result["comparisons"]) == 6
    for group in result["groups"]:
        assert group["counts"]["eval_observed"] == 125
        assert group["counts"]["eval_censored"] == 0
        assert group["counts"]["train_observed"] in {580, 705}
    for cell in result["cells"]:
        active = cell["policy"] != "cash"
        assert cell["trade_count"] == (125 if active else 0)
        assert cell["selected_censored_count"] == 0
        assert Decimal(cell["mean_net_bps"]) == (30 - cell["cost_bps"] if active else 0)
        if cell["paired_mse_bps2"] is not None:
            assert Decimal(cell["paired_mse_bps2"]) == 0
        matched = [
            c for c in result["cells"] if all(c[k] == cell[k] for k in ("symbol", "fold", "policy"))
        ]
        assert len({c["action_sha256"] for c in matched}) == 1
    for table in result["comparisons"]:
        assert len(table["folds"]) == 2
        assert all(f["paired_count"] == 125 for f in table["folds"])
    assert result["criterion"] == "descriptive_only_no_selection"


def test_exact_frozen_contract_and_imported_code_pins(contract):
    config = contract["config"]
    assert config["windows"] == [5, 20] and config["action_domain"] == [0, 1]
    assert config["budget"] == dict(
        cpu_threads=1, memory_bytes=1024**3, wall_seconds=600, gpu=False, passes=1, retries=False
    )
    assert config["expected_main_owned_image"] == s.IMAGE
    assert config["scope"]["holdout_access"] == "none"
    assert config["scope"]["paper_input"] is False
    assert "tiingo-d1-sequence-breadth-v1" in config["prior_families"]
    assert s.base.NAME in config["prior_families"]
    assert set(contract["code_sha256"]) == set(s.CODE)
    for path, pin in contract["code_sha256"].items():
        assert pin == s.digest((s.REPO / path).read_bytes())
    assert all(
        key not in s.encode(contract).decode()
        for key in ('"open":', '"close":', '"forecasts":', '"weights":')
    )


def test_calendar_real_sessions_and_full_20_day_purge():
    plan = s.build_plan(s.calendar_days())
    days = plan["days"]
    assert days[-1] == "2026-07-31" and "2025-08-01" in days
    for fold in plan["folds"]:
        first = fold["evaluation"][0]
        assert fold["train"][1] == first - 20
        assert days[fold["train"][1] - 1] < fold["train_exit_before"]
    january = days.index("2024-01-02")
    assert days[january - 1] == "2023-12-29"


def test_geometry_zero_range_and_positive_independent_scale(rows):
    row = rows["SPY"][0]
    assert s.geometry(row) == pytest.approx((0.003, 0.04, 0.15))
    assert s.geometry(
        replace(row, open=Decimal(7), high=Decimal(7), low=Decimal(7), close=Decimal(7))
    ) == (0, 0, 0)
    for scale in (Decimal("0.001"), Decimal(37)):
        changed = replace(
            row, **{k: getattr(row, k) * scale for k in ("open", "high", "low", "close")}
        )
        assert s.geometry(changed) == s.geometry(row)
        assert s.outcome(changed) == s.outcome(row)


def test_full_daily_rescaling_and_event_flags_do_not_change_results(contract, rows):
    scaled = {
        symbol: tuple(
            replace(
                row,
                **{
                    k: getattr(row, k) * Decimal(2 + i % 9)
                    for k in ("open", "high", "low", "close")
                },
                div_cash=Decimal(8),
                split_factor=Decimal(4),
                volume=Decimal(0),
            )
            for i, row in enumerate(stream)
        )
        for symbol, stream in rows.items()
    }
    assert evaluate(contract, scaled) == evaluate(contract, rows)


def test_known_next_scheduled_target_not_decision_or_following_day(contract, rows):
    j = contract["plan"]["folds"][0]["evaluation"][0]
    changed = change_row(rows, "SPY", j - 1, close=Decimal("100.7"))
    changed = change_row(changed, "SPY", j, close=Decimal("101.1"))
    changed = change_row(changed, "SPY", j + 1, close=Decimal("98.7"))
    p = prepared(contract, changed)
    assert p.eval_indices[0] == j
    assert p.eval_x[0, -1, 0] == pytest.approx(0.007)
    assert s.outcome(changed["SPY"][j]) == 110
    assert s.outcome(changed["SPY"][j - 1]) == 70
    assert s.outcome(changed["SPY"][j + 1]) == -130
    forecasts = {policy: np.array([21.0]) for policy in s.POLICIES[:4]}
    day = [contract["plan"]["days"][j]]
    correct = s._score(forecasts, [s.outcome(changed["SPY"][j])], day)
    shifted = s._score(forecasts, [s.outcome(changed["SPY"][j + 1])], day)
    assert Decimal(correct[0]["gross_sum_bps"]) == 110
    assert Decimal(shifted[0]["gross_sum_bps"]) == -130
    result = evaluate(contract, changed)
    mean = next(
        c
        for c in result["cells"]
        if c["symbol"] == "SPY"
        and c["fold"] == s.FOLDS[0][0]
        and c["policy"] == "train_mean"
        and c["cost_bps"] == 20
    )
    assert Decimal(mean["mean_net_bps"]) == Decimal("9.36")


def test_future_target_changes_payoff_not_prior_features_scaler_or_forecast(contract, rows):
    j = contract["plan"]["folds"][0]["evaluation"][0]
    altered = change_row(rows, "SPY", j, close=Decimal("101.9"))
    first, second = prepared(contract, rows), prepared(contract, altered)
    assert np.array_equal(first.train_x, second.train_x)
    assert np.array_equal(first.train_y, second.train_y)
    assert np.array_equal(first.eval_x[0], second.eval_x[0])
    a, ah, _ = s.forecasts(first, time.monotonic() + 30)
    b, bh, _ = s.forecasts(second, time.monotonic() + 30)
    assert ah == bh
    assert all(a[k][0] == b[k][0] for k in a)
    assert s.outcome(rows["SPY"][j]) != s.outcome(altered["SPY"][j])


def test_missing_target_is_censored_without_shifting_or_cross_symbol_cohort(contract, rows):
    j = contract["plan"]["folds"][0]["evaluation"][0]
    changed = dict(rows)
    changed["SPY"] = rows["SPY"][:j] + rows["SPY"][j + 1 :]
    original, missing = prepared(contract, rows), prepared(contract, changed)
    assert missing.eval_indices[0] == j and missing.eval_indices[1] == j + 21
    assert np.array_equal(original.eval_x[0], missing.eval_x[0])
    result = evaluate(contract, changed)
    assert result["status"] == "complete"
    group = result["groups"][0]
    assert group["counts"]["eval_input_excluded"] == 20
    assert group["counts"]["eval_censored"] == 1
    assert group["counts"]["eval_observed"] == 104
    assert all(g["counts"]["eval_observed"] == 125 for g in result["groups"][2:])
    assert group["scores"][0]["selected_censored_count"] == 1


@pytest.mark.parametrize("bad", ["0", "-1", "NaN", "Infinity"])
def test_invalid_ohlc_never_becomes_feature_or_target(rows, bad):
    row = replace(rows["SPY"][0], open=Decimal(bad))
    assert s.geometry(row) is None and s.outcome(row) is None


def test_threshold_is_strict_binary_and_fixed_across_all_costs():
    values = np.array([-5, 0, 20, 20.000001])
    scores = s._score({p: values for p in s.POLICIES[:4]}, [Decimal(30)] * 4, ["a", "b", "c", "d"])
    assert scores[0]["selected_count"] == scores[0]["trade_count"] == 1
    assert scores[0]["action_sha256"] == s.digest(
        s.encode([("a", 0), ("b", 0), ("c", 0), ("d", 1)])
    )
    assert scores[-2]["trade_count"] == 4 and scores[-1]["trade_count"] == 0


def test_scaler_and_ridge_share_train_only_20_context(contract, rows, monkeypatch):
    from thericher_v2.research import firstrate_m5_h30_lstm_dev_20260921 as old

    p = prepared(contract, rows)
    original = p.train_x.copy()
    p.eval_x[:] = 99
    calls = []

    def predict(fold, context):
        calls.append((fold, context))
        return np.zeros(len(fold.eval_x))

    monkeypatch.setattr(old, "ridge_predict", predict)
    forecasts, sha, fits = s.forecasts(p, time.monotonic() + 30)
    assert [c for _, c in calls] == [5, 20] and calls[0][0] is calls[1][0]
    mean, scale = original.mean(axis=(0, 1)), original.std(axis=(0, 1))
    scale = np.where(scale == 0, 1, scale)
    assert sha == s.digest(s.encode([mean.tolist(), scale.tolist()]))
    assert np.array_equal(calls[0][0].train_x, (original - mean) / scale)
    assert np.array_equal(calls[0][0].train_y, p.train_y)
    assert fits == 2 and np.all(forecasts["previous_intraday"] == 990000)


@pytest.mark.parametrize("limit,expected", [(99, "input_unavailable"), (100, "complete")])
def test_observed_eval_minimum_is_not_zero_censor_requirement(contract, rows, limit, expected):
    first, stop = contract["plan"]["folds"][0]["evaluation"]
    cutoff = first + limit
    changed = dict(rows)
    changed["SPY"] = rows["SPY"][:cutoff] + rows["SPY"][stop:]
    result = evaluate(contract, changed)
    assert result["status"] == expected
    if expected == "input_unavailable":
        assert all(
            score["gross_sum_bps"] is None and score["mse_bps2"] is None
            for g in result["groups"]
            for score in g["scores"]
        )
        assert result["groups"][0]["scores"][0]["trade_count"] == 99
        assert result["groups"][0]["scores"][0]["selected_censored_count"] == 1
        assert result["cells"][0]["action_sha256"] is not None
        assert all(
            c["mean_net_bps"] is None and c["paired_mse_bps2"] is None for c in result["cells"]
        )


def test_training_insufficiency_skips_its_fit_and_suppresses_all_scores(contract, rows):
    altered = dict(rows, SPY=())
    result = evaluate(contract, altered)
    assert result["status"] == "input_unavailable"
    assert result["groups"][0]["fits"] == 0
    assert all(c["mean_net_bps"] is None for c in result["cells"])


@pytest.mark.parametrize("count", [499, 500])
def test_train_floor_and_real_ridge_match_centered_closed_form(count):
    rng = np.random.default_rng(811)
    train_x = rng.normal(size=(count, 20, 3))
    train_y = 7 + 5 * train_x[:, -1, 0] - 3 * train_x[:, -10, 1]
    eval_x = rng.normal(size=(8, 20, 3))
    p = SimpleNamespace(train_x=train_x, train_y=train_y, eval_x=eval_x)
    if count < 500:
        with pytest.raises(ValueError, match="insufficient_train"):
            s.forecasts(p, time.monotonic() + 30)
        return
    predictions, _, fits = s.forecasts(p, time.monotonic() + 30)
    mean, scale = train_x.mean(axis=(0, 1)), train_x.std(axis=(0, 1))
    for window in s.WINDOWS:
        x = ((train_x - mean) / scale)[:, -window:].reshape(count, -1)
        e = ((eval_x - mean) / scale)[:, -window:].reshape(8, -1)
        x_mean = x.mean(axis=0)
        centered = x - x_mean
        coefficients = np.linalg.solve(
            centered.T @ centered + np.eye(3 * window), centered.T @ (train_y - train_y.mean())
        )
        expected = (e - x_mean) @ coefficients + train_y.mean()
        np.testing.assert_allclose(predictions[f"ridge{window}"], expected, rtol=1e-11, atol=1e-11)
    assert fits == 2


def test_purged_labels_never_enter_training_but_may_be_development_history(contract, rows):
    j = contract["plan"]["folds"][0]["evaluation"][0] - 20
    altered = change_row(rows, "SPY", j, close=Decimal("101.4"))
    first, second = prepared(contract, rows), prepared(contract, altered)
    assert np.array_equal(first.train_x, second.train_x)
    assert np.array_equal(first.train_y, second.train_y)
    assert not np.array_equal(first.eval_x[0], second.eval_x[0])


def test_insufficient_result_cannot_smuggle_metrics(contract, rows):
    result = evaluate(contract, dict(rows, SPY=()))
    result["groups"][2]["scores"][0]["mse_bps2"] = "0.000000000000"
    with pytest.raises(ValueError, match="unavailable_metrics"):
        s.validate_result(result, contract, s.digest(s.encode(contract)))


@pytest.mark.parametrize("kind", ["duplicate", "reverse", "symbol"])
def test_row_identity_order_is_fail_closed(contract, rows, kind):
    altered = dict(rows)
    stream = rows["SPY"]
    altered["SPY"] = (
        (stream[0],) + stream
        if kind == "duplicate"
        else tuple(reversed(stream))
        if kind == "reverse"
        else (replace(stream[0], symbol="WRONG"),) + stream[1:]
    )
    with pytest.raises(ValueError):
        evaluate(contract, altered)


def test_deadline_and_disjoint_21_session_blocks(contract, rows):
    with pytest.raises(ValueError, match="hard_timeout"):
        s.evaluate(rows, contract, s.digest(s.encode(contract)), deadline=0)
    assert s.nonoverlap_blocks(range(20, 62)) == 2


@pytest.mark.parametrize(
    "kind",
    [
        "extra",
        "count_bool",
        "partial",
        "cost",
        "net",
        "mse",
        "action_hash",
        "source",
        "config",
        "raw_score",
        "nan",
        "table",
    ],
)
def test_safe_result_rejects_shape_binding_and_derived_metric_tampering(contract, rows, kind):
    result = evaluate(contract, rows)
    if kind == "extra":
        result["forecasts"] = [1]
    elif kind == "count_bool":
        result["groups"][0]["counts"]["eval_censored"] = False
    elif kind == "partial":
        result["cells"].pop()
    elif kind == "cost":
        result["cells"][0]["cost_bps"] = 6
    elif kind in {"net", "mse"}:
        result["cells"][0]["mean_net_bps" if kind == "net" else "paired_mse_bps2"] = (
            "123.000000000000"
        )
    elif kind == "action_hash":
        result["cells"][0]["action_sha256"] = "sha256:" + "0" * 64
    elif kind in {"source", "config"}:
        result[f"{kind}_sha256"] = "sha256:" + "0" * 64
    elif kind == "raw_score":
        result["groups"][0]["scores"][0]["prices"] = [100]
    elif kind == "nan":
        result["groups"][0]["scores"][0]["mse_bps2"] = "NaN"
    elif kind == "table":
        result["comparisons"][0]["folds"][0]["paired_count"] = 1
    with pytest.raises((ValueError, TypeError, KeyError)):
        s.validate_result(result, contract, s.digest(s.encode(contract)))


@pytest.fixture
def frozen(contract, tmp_path, monkeypatch):
    artifact, market = tmp_path / "artifacts", tmp_path / "market"
    receipt = artifact / s.base.RECEIPT
    manifest = market / s.base.SNAPSHOT / "manifest.json"
    for path in (receipt, manifest):
        path.parent.mkdir(parents=True)
        path.write_bytes(b'{"synthetic":true}\n')
    monkeypatch.setattr(s.base, "RECEIPT_HASH", s.digest(receipt.read_bytes()))
    monkeypatch.setattr(s.base, "MANIFEST_HASH", s.digest(manifest.read_bytes()))
    pin = s.freeze(artifact, market)
    output, bound = s.verify(artifact, market, pin)
    return SimpleNamespace(
        artifact=artifact,
        market=market,
        pin=pin,
        output=output,
        contract=bound,
        receipt=receipt,
        manifest=manifest,
    )


def test_freeze_is_metadata_only_atomic_and_cannot_overwrite(frozen):
    original = (frozen.output / "precommit.json").read_bytes()
    assert {p.name for p in frozen.output.iterdir()} == {"precommit.json"}
    with pytest.raises(FileExistsError):
        s.freeze(frozen.artifact, frozen.market)
    with pytest.raises(FileExistsError):
        s.atomic_new(frozen.output / "precommit.json", {})
    assert original == (frozen.output / "precommit.json").read_bytes()


@pytest.mark.parametrize("field", ["code_sha256", "config_sha256", "plan", "runtime"])
def test_changed_code_config_dates_or_runtime_fail_before_loader(frozen, monkeypatch, field):
    original = s.proposed_contract

    def changed():
        payload = original()
        payload[field] = {}
        return payload

    monkeypatch.setattr(s, "proposed_contract", changed)
    with pytest.raises(ValueError, match="precommit_changed"):
        s.verify(frozen.artifact, frozen.market, frozen.pin)


@pytest.mark.parametrize("field", ["receipt", "manifest"])
def test_source_metadata_tampering_fails(frozen, field):
    getattr(frozen, field).write_bytes(b"changed")
    with pytest.raises(ValueError):
        s.verify(frozen.artifact, frozen.market, frozen.pin)


def fake_loader(frozen, rows, monkeypatch):
    def load(path, **kwargs):
        assert path == frozen.market / s.base.SNAPSHOT
        assert kwargs["expected_dataset_hash"] == s.base.DATASET_HASH
        assert kwargs["expected_manifest_hash"] == s.base.MANIFEST_HASH
        assert (frozen.output / "precommit.json").exists()
        assert json.loads((frozen.output / "started.json").read_bytes()) == {
            "contract_sha256": frozen.pin
        }
        return SimpleNamespace(
            rows_by_symbol=rows,
            snapshot=SimpleNamespace(
                dataset_id=s.base.DATASET_ID,
                dataset_hash=s.base.DATASET_HASH,
                manifest_hash=s.base.MANIFEST_HASH,
            ),
        )

    monkeypatch.setattr(s, "load_verified_tiingo_etf_d1_snapshot", load)


def test_worker_precommit_before_outcomes_and_no_overwrite(frozen, rows, monkeypatch):
    path = frozen.output / "worker-result.json"
    with pytest.raises(ValueError):
        s.run_worker(frozen.artifact, frozen.market, frozen.pin, path, time.monotonic() + 30)
    s.atomic_new(frozen.output / "started.json", {"contract_sha256": frozen.pin})
    fake_loader(frozen, rows, monkeypatch)
    s.run_worker(frozen.artifact, frozen.market, frozen.pin, path, time.monotonic() + 30)
    result = json.loads(path.read_bytes())
    assert result["status"] == "complete"
    assert not any(k in s.encode(result).decode() for k in ('"open":', '"close":', '"forecasts":'))
    with pytest.raises(ValueError, match="worker_path"):
        s.run_worker(frozen.artifact, frozen.market, frozen.pin, path, time.monotonic() + 30)


def test_cli_reuses_runner_and_importable_worker(monkeypatch):
    ns = runpy.run_path(str(s.REPO / "scripts/run_tiingo_geometry_ridge_development.py"))
    namespace = {}
    exec("def main(argv):\n return (study, worker, argv)", namespace)

    def load(path):
        assert path == str(s.REPO / "scripts/run_tiingo_month_start_development.py")
        return namespace

    monkeypatch.setattr(ns["runpy"], "run_path", load)
    assert ns["main"](["--freeze"]) == (s, s.worker_entry, ["--freeze"])


@pytest.mark.parametrize("mode", ["success", "timeout", "invalid", "failed", "interrupt"])
def test_reused_runner_single_pass_and_categorical_failure(frozen, rows, monkeypatch, capsys, mode):
    ns = runpy.run_path(str(s.REPO / "scripts/run_tiingo_month_start_development.py"))
    globals_ = ns["main"].__globals__
    globals_["study"], globals_["worker"] = s, s.worker_entry
    fake_loader(frozen, rows, monkeypatch)

    def supervise(target, args, *, seconds):
        assert target is s.worker_entry and 0 < seconds <= 600
        if mode == "interrupt":
            raise KeyboardInterrupt
        if mode in {"success", "invalid"}:
            target(*args)
            if mode == "invalid":
                result = json.loads(args[-2].read_bytes())
                result["raw_rows"] = "PRIVATE"
                args[-2].write_bytes(s.encode(result))
        return dict(timed_out=mode == "timeout", exit_code=1 if mode == "failed" else 0)

    globals_["supervise"] = supervise
    argv = [
        "--run",
        "--artifact-root",
        str(frozen.artifact),
        "--market-data-root",
        str(frozen.market),
        "--contract-sha256",
        frozen.pin,
    ]
    assert ns["main"](argv) == (0 if mode == "success" else 1)
    result = json.loads((frozen.output / "summary.json").read_bytes())
    assert result["status"] == ("complete" if mode == "success" else "failed")
    assert "PRIVATE" not in (frozen.output / "summary.json").read_text()
    original = (frozen.output / "summary.json").read_bytes()
    assert ns["main"](argv) == 1
    assert original == (frozen.output / "summary.json").read_bytes()
    capsys.readouterr()


def test_importable_worker_runs_under_existing_spawn_supervisor(tmp_path):
    ns = runpy.run_path(str(s.REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py"))
    report = ns["supervise"](
        s.worker_entry,
        (
            tmp_path / "empty-artifacts",
            tmp_path / "empty-market",
            "invalid",
            tmp_path / "unused.json",
            time.monotonic() + 10,
        ),
        seconds=10,
        name="geometry-synthetic",
    )
    assert report["exit_code"] == 1 and report["timed_out"] is False
    assert not (tmp_path / "unused.json").exists()


def test_synthetic_snapshot_through_real_verified_loader(contract, rows, tmp_path, monkeypatch):
    artifact, market = tmp_path / "artifacts", tmp_path / "market"
    snapshot = market / s.base.SNAPSHOT
    raw_dir = snapshot / "raw"
    raw_dir.mkdir(parents=True)
    hashes = {}
    for symbol, stream in rows.items():
        raw = s.encode(
            [
                dict(
                    date=r.session_date.isoformat(),
                    **{k: str(getattr(r, k)) for k in ("open", "high", "low", "close", "volume")},
                    divCash=str(r.div_cash),
                    splitFactor=str(r.split_factor),
                )
                for r in stream
            ]
        )
        (raw_dir / f"{symbol}.json").write_bytes(raw)
        hashes[symbol] = s.digest(raw)
    canonical = daily._gzip_bytes(daily._canonical_csv_bytes(rows))
    (snapshot / "ohlcv_1d.csv.gz").write_bytes(canonical)
    manifest = daily._manifest(
        target=snapshot,
        requested_start=date(2000, 12, 1),
        requested_end=date(2026, 7, 31),
        retrieved_at=datetime(2026, 8, 9, tzinfo=UTC),
        canonical_hash=s.digest(canonical),
        canonical_size=len(canonical),
        raw_hashes=hashes,
        rows_by_symbol=rows,
        raw_dir=raw_dir,
        free_percent=50,
    )
    raw = s.encode(manifest)
    (snapshot / "manifest.json").write_bytes(raw)
    receipt = artifact / s.base.RECEIPT
    receipt.parent.mkdir(parents=True)
    receipt.write_bytes(s.encode({"synthetic": True, "manifest_hash": s.digest(raw)}))
    monkeypatch.setattr(s.base, "DATASET_HASH", s.digest(canonical))
    monkeypatch.setattr(s.base, "MANIFEST_HASH", s.digest(raw))
    monkeypatch.setattr(s.base, "RECEIPT_HASH", s.digest(receipt.read_bytes()))
    monkeypatch.setattr(
        s, "load_verified_tiingo_etf_d1_snapshot", daily.load_verified_tiingo_etf_d1_snapshot
    )
    pin = s.freeze(artifact, market)
    output, bound = s.verify(artifact, market, pin)
    s.atomic_new(output / "started.json", {"contract_sha256": pin})
    path = output / "worker-result.json"
    s.run_worker(artifact, market, pin, path, time.monotonic() + 45)
    result = json.loads(path.read_bytes())
    assert result["status"] == "complete" and len(result["cells"]) == 108
    s.validate_result(result, bound, pin)
