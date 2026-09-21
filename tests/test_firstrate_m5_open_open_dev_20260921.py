"""Synthetic-only checks for the isolated same-payoff development package."""

from __future__ import annotations

import csv
import json
import runpy
import socket
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import CSV_FIELDS, bar_to_record
from thericher_v2.data.resample import resample_bars
from thericher_v2.execution import EmergencyStore
from thericher_v2.research import firstrate_m5_open_open_dev_20260921 as dev

START = datetime(2026, 1, 1, tzinfo=UTC)


def bars(count=8 * 288, *, timeframe=Timeframe.M5, symbol="SPY"):
    result = []
    for i in range(count):
        price = Decimal(100) + Decimal((i * 7) % 101) / 100
        close = price + (Decimal("0.01") if i % 2 else Decimal("-0.01"))
        result.append(
            Bar(
                symbol=symbol,
                market="US",
                timeframe=timeframe,
                start_ts=START + i * timeframe.duration,
                open=price,
                high=max(price, close) + Decimal("0.1"),
                low=min(price, close) - Decimal("0.1"),
                close=close,
                volume=Decimal(1000),
                complete=True,
            )
        )
    return result


def install_source(root: Path, *, days=8):
    """Write only generated synthetic bars beneath pytest's external root."""
    market, artifacts = root / "market", root / "artifacts"
    market.mkdir()
    records = []
    for symbol in dev.SYMBOLS:
        source = bars(days * 1440 + 3, timeframe=Timeframe.M1, symbol=symbol)
        path = market / f"{symbol}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(bar_to_record(bar) for bar in source)
        records.append(
            {
                "symbol": symbol,
                "market": "US",
                "timeframe": "1m",
                "canonical_market_data_relative_path": path.name,
                "canonical_sha256": dev.sha256(path.read_bytes()),
                "bar_count": len(source),
                "timestamp_set_equal": True,
                "emitted_timestamp_set_sha256": dev.sha256(
                    "".join(f"{bar.start_ts.isoformat()}\n" for bar in source).encode()
                ),
            }
        )
    receipt = artifacts / dev.RECEIPT
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps(
            {
                "schema_version": "firstrate-free-intraday-normalization-receipt-v1",
                "status": "completed",
                "permitted_interpretation": "source_isolated_retrospective_mechanics_only",
                "normalizations": records,
            }
        ),
        encoding="utf-8",
    )
    return market, artifacts


def test_complete_only_resampling_drops_final_partial_and_internal_missing_minute():
    source = bars(318, timeframe=Timeframe.M1)
    complete = resample_bars(source, Timeframe.M5)
    assert len(complete) == 63
    assert complete[-1].end_ts == START + timedelta(minutes=315)
    assert all(bar.complete for bar in complete)
    index = {bar.start_ts: bar for bar in complete}
    observation, reason = dev.past_observation(index, START + timedelta(minutes=310))
    assert reason == "eligible"
    outcome, reason = dev.attach_outcome(index, observation)
    assert outcome is None
    assert reason == "future_exit_missing_or_incomplete"
    missing = resample_bars(source[:101] + source[102:], Timeframe.M5)
    assert len(missing) == 62
    assert START + timedelta(minutes=100) not in {bar.start_ts for bar in missing}
    assert (
        dev.past_observation(
            {bar.start_ts: bar for bar in missing}, START + timedelta(minutes=310)
        )[1]
        == "past_missing"
    )


def test_future_changes_preserve_features_eligibility_and_every_decision():
    source = bars(500)
    index = {bar.start_ts: bar for bar in source}
    train_times = [START + i * dev.STEP for i in range(60, 200, 2)]
    observations, _ = dev._observations(index, train_times)
    outcomes, _ = dev._outcomes(index, observations)
    model = dev.fit_control(observations, outcomes)
    timestamp = START + 400 * dev.STEP
    observation = dev.past_observation(index, timestamp)[0]
    decisions = dev.decisions([observation], model)
    future_removed = {key: value for key, value in index.items() if key < timestamp}
    unchanged = dev.past_observation(future_removed, timestamp)[0]
    assert unchanged == observation
    assert dev.decisions([unchanged], model) == decisions
    assert dev.attach_outcome(future_removed, unchanged)[0] is None
    changed = dict(index)
    for key in tuple(changed):
        if key >= timestamp:
            bar = changed[key]
            changed[key] = replace(
                bar, open=bar.open * 10, high=bar.high * 10, low=bar.low * 10, close=bar.close * 10
            )
    assert dev.past_observation(changed, timestamp)[0] == observation
    assert dev.decisions([dev.past_observation(changed, timestamp)[0]], model) == decisions


def test_two_folds_strictly_purge_training_labels_before_first_feature_history():
    source = bars()
    index = {bar.start_ts: bar for bar in source}
    folds = dev.fold_schedules(source)
    assert len(folds) == 2
    for train_times, eval_times, cutoff in folds:
        train_x, _ = dev._observations(index, train_times)
        train_y, _ = dev._outcomes(index, train_x)
        eval_x, _ = dev._observations(index, eval_times)
        first_history = min(item.history_start for item in eval_x)
        latest_label = max(y.exit_bar.start_ts for y in train_y if y is not None)
        assert cutoff == eval_times[0] - 60 * dev.STEP
        assert latest_label < cutoff <= first_history
        assert all(t + dev.STEP < cutoff for t in train_times)
        assert len(train_times) <= 1024
        assert len(eval_times) <= 256
    assert folds[0][1][-1] < folds[1][1][0]


def test_no_backfill_when_prelabel_sample_has_input_shortfall(tmp_path, monkeypatch):
    source = bars()
    scheduled = dev.fold_schedules(source)
    removed = {t - dev.STEP for train, evaluation, _ in scheduled for t in (*train, *evaluation)}
    gapped = [bar for bar in source if bar.start_ts not in removed]
    assert dev.fold_schedules(gapped) == scheduled

    def forbidden_fit(*args):
        raise AssertionError("shortfall must not fit or backfill")

    monkeypatch.setattr(dev, "fit_control", forbidden_fit)
    results = dev.compare_stream(
        gapped, EmergencyStore(tmp_path / "emergency.json"), deadline=time.monotonic() + 30
    )
    for result, (training, evaluation, _) in zip(results, scheduled, strict=True):
        assert result["status"] == "input_unavailable_training_support"
        assert result["training_inputs"]["scheduled"] == len(training)
        assert result["evaluation_inputs"]["scheduled"] == len(evaluation)
        assert result["training_inputs"]["eligible"] == 0
        assert result["cells"] == []


@pytest.mark.parametrize("cost", [1, 3, 5])
def test_independent_target_and_fee_parity_all_costs(tmp_path, cost):
    source = bars(62)
    index = {bar.start_ts: bar for bar in source}
    observation = dev.past_observation(index, START + 60 * dev.STEP)[0]
    entry = replace(
        source[60],
        open=Decimal("101.123456"),
        high=Decimal(200),
        low=Decimal(1),
        close=Decimal(100),
    )
    exit_bar = replace(
        source[61], open=Decimal("102.765432"), high=Decimal(200), low=Decimal(1), close=Decimal(1)
    )
    outcome = dev.Outcome(entry, exit_bar)
    # Literal independently rounded opens also catch a mistaken target.close label.
    gross = Decimal("102.7654") - Decimal("101.1235")
    fee = (Decimal("101.1235") * Decimal(cost) / Decimal(10000)).quantize(Decimal("0.0001")) + (
        Decimal("102.7654") * Decimal(cost) / Decimal(10000)
    ).quantize(Decimal("0.0001"))
    assert outcome.target == float(Decimal("102.7654") / Decimal("101.1235") - 1)
    assert outcome.target > 0
    actual = dev.replay_roundtrip(
        observation, outcome, cost, EmergencyStore(tmp_path / "emergency.json")
    )
    assert actual == (gross, fee, (gross - fee) / Decimal("101.1235") * 10000)
    assert not list(tmp_path.rglob("*.sqlite"))
    assert not list(tmp_path.rglob("*.jsonl"))


def test_replay_kill_test_rejects_mismatched_target(tmp_path, monkeypatch):
    source = bars(62)
    index = {bar.start_ts: bar for bar in source}
    observation = dev.past_observation(index, START + 60 * dev.STEP)[0]
    outcome = dev.attach_outcome(index, observation)[0]
    monkeypatch.setattr(dev.Outcome, "entry_open", property(lambda self: Decimal("99")))
    with pytest.raises(ValueError, match="target_replay_parity_failed"):
        dev.replay_roundtrip(observation, outcome, 3, EmergencyStore(tmp_path / "emergency"))


def test_freeze_reads_only_receipt_not_raw_bars_and_never_overwrites(tmp_path, monkeypatch):
    market, artifacts = install_source(tmp_path, days=1)
    original = Path.read_bytes

    def metadata_only(path):
        assert path.suffix != ".csv"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", metadata_only)
    digest = dev.freeze(artifact_root=artifacts, run_label="fixture")
    contract = (dev._run_dir(artifacts, "fixture") / "contract.json").read_bytes()
    assert dev.sha256(contract) == digest
    frozen = json.loads(contract)
    assert frozen["observation_windows_m5"] == [60]
    assert len(frozen["prior_rejected_results"]) == 3
    assert frozen["budget"]["fits"] == 4
    assert frozen["generalization_claim"] is False
    assert frozen["promotion"] is False
    assert len(list(market.glob("*.csv"))) == 2
    with pytest.raises(FileExistsError):
        dev.freeze(artifact_root=artifacts, run_label="fixture")


def test_full_offline_fixture_has_48_matched_cells_and_no_promotion(tmp_path, monkeypatch):
    market, artifacts = install_source(tmp_path)

    def no_network(*args, **kwargs):
        raise AssertionError("offline fixture must never connect")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    digest = dev.freeze(artifact_root=artifacts, run_label="fixture")
    summary = dev.run_frozen(
        market_data_root=market,
        artifact_root=artifacts,
        run_label="fixture",
        contract_sha256=digest,
    )
    assert summary["status"] == "development_complete"
    assert summary["evidence_grade"] == "DEVELOPMENT_ONLY_ALREADY_SEEN"
    for name in (
        "promotion",
        "generalization_claim",
        "independent_performance_claim",
        "holdout_access",
        "retained_weights",
    ):
        assert summary[name] is False
    all_cells = []
    for stream in summary["streams"]:
        # 3 extra M1 rows at the end must not produce another M5 bar.
        assert stream["m5_count"] == 8 * 288
        for fold in stream["folds"]:
            assert fold["strict_label_history_separation"] is True
            assert fold["training_nonoverlap_blocks"] >= 2
            assert fold["evaluation_nonoverlap_blocks"] >= 2
            inputs = fold["evaluation_inputs"]
            outcomes = fold["evaluation_outcomes"]
            assert inputs["scheduled"] == sum(
                inputs[k] for k in ("eligible", "past_missing", "past_incomplete")
            )
            assert (
                inputs["eligible"]
                == outcomes["eligible"]
                == sum(
                    outcomes[k]
                    for k in (
                        "observed",
                        "future_entry_missing_or_incomplete",
                        "future_exit_missing_or_incomplete",
                    )
                )
            )
            assert len({c["scored_decisions"] for c in fold["cells"]}) == 1
            all_cells.extend(fold["cells"])
    assert len(all_cells) == 48
    flat = [c for c in all_cells if c["candidate"] == "always_flat"]
    assert all(Decimal(c["net_pnl"]) == 0 and c["trades"] == 0 for c in flat)
    assert all(c["terminal_flat"] and c["parity_verified"] for c in all_cells)
    output = dev._run_dir(artifacts, "fixture")
    assert sorted(path.name for path in output.iterdir()) == [
        "contract.json",
        "run-started.json",
        "summary.json",
    ]
    text = (output / "summary.json").read_text()
    for forbidden in ('"open":', '"close":', '"features":', '"predictions":', '"weights":'):
        assert forbidden not in text
    with pytest.raises(FileExistsError):
        dev.run_frozen(
            market_data_root=market,
            artifact_root=artifacts,
            run_label="fixture",
            contract_sha256=digest,
        )


def test_outcome_censoring_does_not_backfill_or_change_long_intents():
    source = bars(150)
    index = {bar.start_ts: bar for bar in source}
    times = [START + i * dev.STEP for i in (60, 80, 100)]
    observations, inputs = dev._observations(index, times)
    original, _ = dev._outcomes(index, observations)
    changed = {key: value for key, value in index.items() if key != times[1] + dev.STEP}
    censored, counts = dev._outcomes(changed, observations)
    assert inputs["eligible"] == len(observations) == 3
    assert len(censored) == 3
    assert original[1] is not None and censored[1] is None
    assert counts["future_exit_missing_or_incomplete"] == 1
    assert counts["observed"] == 2


def test_changed_contract_refuses_raw_loader(tmp_path, monkeypatch):
    market, artifacts = install_source(tmp_path, days=1)
    digest = dev.freeze(artifact_root=artifacts, run_label="fixture")
    path = dev._run_dir(artifacts, "fixture") / "contract.json"
    payload = json.loads(path.read_bytes())
    payload["ridge"]["alpha"] = 2
    path.write_text(json.dumps(payload), encoding="utf-8")

    def no_loader(*args, **kwargs):
        raise AssertionError("must reject changed freeze before data read")

    monkeypatch.setattr(dev.LocalCsvBarProvider, "get_bars", no_loader)
    with pytest.raises(ValueError, match="frozen_contract_changed"):
        dev.run_frozen(
            market_data_root=market,
            artifact_root=artifacts,
            run_label="fixture",
            contract_sha256=digest,
        )


def test_external_roots_run_labels_and_budget_fail_closed(tmp_path):
    with pytest.raises(ValueError, match="external_root_required"):
        dev.freeze(artifact_root=dev.REPO, run_label="fixture")
    with pytest.raises(ValueError, match="invalid_run_label"):
        dev._run_dir(tmp_path, "../escape")
    with pytest.raises(TimeoutError):
        dev.compare_stream(
            bars(), EmergencyStore(tmp_path / "emergency"), deadline=time.monotonic() - 1
        )


def test_cli_requires_explicit_mode_and_contract_and_sanitizes_errors(tmp_path, capsys):
    main = runpy.run_path(str(dev.REPO / "scripts/run_firstrate_m5_open_open_dev_20260921.py"))[
        "main"
    ]
    with pytest.raises(SystemExit):
        main(["--run-label", "fixture"])
    with pytest.raises(SystemExit):
        main(["--run", "--run-label", "fixture"])
    assert main(["--freeze", "--run-label", "fixture", "--artifact-root", str(tmp_path)]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "offline_contract_or_namespace_unavailable"
    assert str(tmp_path) not in json.dumps(output)
