"""Synthetic preparation tests: no retained data, credentials, network or models."""

from __future__ import annotations

import builtins
import importlib.util
import json
import socket
import subprocess
import sys
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research.forward_variance_smoke import (
    MINUTE,
    build_variance_smoke_case,
    decision_at,
)

OPEN = datetime(2023, 3, 13, 13, 30, tzinfo=UTC)
SESSION = SessionWindow(OPEN, OPEN + 390 * MINUTE)


@pytest.fixture(autouse=True)
def blocked_external_surfaces(monkeypatch):
    original_open, original_import = Path.open, builtins.__import__

    def checked_open(path, *args, **kwargs):
        normalized = str(path).replace("\\", "/").lower()
        if normalized.startswith(("d:/market_data", "d:/thericher-v2/model-artifacts")):
            pytest.fail("real artifact or data access")
        if ".env" in path.name.lower():
            pytest.fail("credential access")
        return original_open(path, *args, **kwargs)

    def checked_import(name, *args, **kwargs):
        if (
            name == "torch"
            or name.startswith("torch.")
            or any(part in name.lower() for part in ("broker", "credential", "dotenv", "kis_"))
        ):
            pytest.fail("forbidden runtime import")
        return original_import(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("network or subprocess attempted")

    monkeypatch.setattr(Path, "open", checked_open)
    monkeypatch.setattr(builtins, "__import__", checked_import)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)


def minutes(symbol, session=SESSION):
    return tuple(
        Bar(
            symbol,
            "US",
            Timeframe.M1,
            session.open_ts + index * MINUTE,
            Decimal(100 + index),
            Decimal(100 + index),
            Decimal(100 + index),
            Decimal(100 + index),
            Decimal(index),
        )
        for index in range(session.duration // MINUTE)
    )


@pytest.fixture
def pair():
    return minutes("QQQ"), minutes("SPY")


def test_exact_decision_input_target_geometry(pair):
    case = build_variance_smoke_case(*pair, session=SESSION)
    assert case.decision_at == OPEN + 150 * MINUTE
    assert case.input_status == "available"
    assert case.context.history_start == OPEN + 30 * MINUTE
    assert case.context.completed_through == case.decision_at
    assert len(case.context.own_bars) == len(case.context.peer_bars) == 120
    for target in (support.target for support in case.targets):
        assert target.target_start == OPEN + 151 * MINUTE
        assert target.target_end == OPEN + 211 * MINUTE
        assert target.available_at == OPEN + 212 * MINUTE
        assert target.horizon_minutes == 60


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("fault", ["missing", "incomplete", "price"])
def test_forward_edits_never_remove_or_change_past_input(pair, index, fault):
    original = build_variance_smoke_case(*pair, session=SESSION)
    edited = list(pair)
    at = OPEN + 180 * MINUTE
    edited[index] = tuple(
        replace(bar, complete=False)
        if fault == "incomplete" and bar.start_ts == at
        else replace(
            bar, open=Decimal(500), high=Decimal(500), low=Decimal(500), close=Decimal(500)
        )
        if fault == "price" and bar.start_ts == at
        else bar
        for bar in edited[index]
        if fault != "missing" or bar.start_ts != at
    )
    changed = build_variance_smoke_case(*edited, session=SESSION)
    assert changed.context == original.context
    assert changed.input_status == original.input_status == "available"
    assert changed.targets[1 - index] == original.targets[1 - index]
    if fault == "price":
        assert changed.targets[index].target != original.targets[index].target
    else:
        assert changed.targets[index].status == "required_forward_m1_shortfall"


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("fault", ["missing", "incomplete"])
def test_past_shortfall_does_not_filter_available_targets(pair, index, fault):
    original = build_variance_smoke_case(*pair, session=SESSION)
    edited = list(pair)
    at = OPEN + 60 * MINUTE
    edited[index] = tuple(
        replace(bar, complete=False) if bar.start_ts == at else bar
        for bar in edited[index]
        if fault != "missing" or bar.start_ts != at
    )
    changed = build_variance_smoke_case(*edited, session=SESSION)
    assert changed.context is None
    assert changed.input_status == "required_past_m1_shortfall"
    assert changed.targets == original.targets


@pytest.mark.parametrize("duration", [210, 211, 212])
def test_early_close_keeps_inputs_and_censors_only_target(duration):
    session = SessionWindow(OPEN, OPEN + duration * MINUTE)
    case = build_variance_smoke_case(
        minutes("QQQ", session), minutes("SPY", session), session=session
    )
    assert case.input_status == "available"
    assert case.decision_at == OPEN + 150 * MINUTE
    assert all(
        support.status == ("available" if duration == 212 else "session_horizon_shortfall")
        for support in case.targets
    )


def test_short_session_has_separate_context_and_horizon_shortfall():
    session = SessionWindow(OPEN, OPEN + 120 * MINUTE)
    case = build_variance_smoke_case((), (), session=session)
    assert decision_at(session) == OPEN + 110 * MINUTE
    assert case.input_status == "session_context_shortfall"
    assert all(support.status == "session_horizon_shortfall" for support in case.targets)


@pytest.mark.parametrize("region", ["past", "forward"])
@pytest.mark.parametrize("fault", ["symbol", "market", "timeframe", "order", "duplicate"])
def test_wrong_required_identity_is_not_accepted(pair, region, fault):
    edited = list(pair)
    bars = list(pair[0])
    index = 60 if region == "past" else 180
    if fault == "order":
        bars[index], bars[index + 1] = bars[index + 1], bars[index]
    elif fault == "duplicate":
        bars.insert(index, bars[index])
    else:
        bars[index] = replace(
            bars[index],
            **{fault: {"symbol": "SPY", "market": "KR", "timeframe": Timeframe.M5}[fault]},
        )
    edited[0] = tuple(bars)
    if fault in ("order", "duplicate"):
        case = build_variance_smoke_case(*edited, session=SESSION)
        assert (case.input_status if region == "past" else case.targets[0].status) != "available"
    else:
        with pytest.raises(ValueError, match="identity|declared"):
            build_variance_smoke_case(*edited, session=SESSION)


def test_values_outside_both_required_intervals_are_irrelevant(pair):
    original = build_variance_smoke_case(*pair, session=SESSION)
    selected = tuple(
        tuple(bar for bar in stream if OPEN + 30 * MINUTE <= bar.start_ts < OPEN + 212 * MINUTE)
        for stream in pair
    )
    assert build_variance_smoke_case(*selected, session=SESSION) == original
    assert "realized_variance" not in repr(original)


@pytest.fixture
def runner():
    path = Path(__file__).resolve().parents[1] / "scripts/run_firstrate_forward_variance_smoke.py"
    spec = importlib.util.spec_from_file_location("variance_smoke_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_contract_is_finite_non_predictive(runner):
    plan = runner.contract({path: "sha256:" + "a" * 64 for path in runner.CODE})
    assert plan["scheduled_dates"] == 251
    assert plan["source_sha256"] == runner.SOURCES
    assert "past120" in plan["input"] and "one60min" in plan["target"]
    assert plan["compute"]["seconds"] == 120 and plan["compute"]["network"] == "none"
    assert not any(plan["prohibited"].values())
    assert "seen" in plan["grade"] and plan["splits"].startswith("none")


def test_freeze_is_durable_and_precedes_any_source_value_parse(runner, tmp_path, monkeypatch):
    events = []
    monkeypatch.setattr(runner, "file_hash", lambda path: "sha256:" + "a" * 64)
    monkeypatch.setattr(runner, "check_pins", lambda *args: events.append("checked"))
    monkeypatch.setattr(
        runner.LocalCsvBarProvider,
        "get_bars",
        lambda *args: pytest.fail("freeze parsed source values"),
    )
    monkeypatch.setattr(
        runner,
        "build_variance_smoke_case",
        lambda *args, **kwargs: pytest.fail("freeze accessed targets"),
    )
    original_fsync = runner.os.fsync

    def fsync(fd):
        events.append("durable")
        original_fsync(fd)

    monkeypatch.setattr(runner.os, "fsync", fsync)
    root = tmp_path / "smoke"
    result = runner.freeze(root, tmp_path, tmp_path, tmp_path)
    assert events == ["checked", "durable"]
    assert result["targets"] == 0
    assert json.loads((root / "contract.json").read_bytes())["study"] == runner.STUDY
    with pytest.raises(FileExistsError):
        runner.freeze(root, tmp_path, tmp_path, tmp_path)


@pytest.mark.parametrize("fault", ["contract", "code_keys", "code_hash", "source_hash"])
def test_pin_failure_precedes_loader_and_targets(runner, tmp_path, monkeypatch, fault):
    plan = runner.contract({path: "sha256:" + "a" * 64 for path in runner.CODE})
    source = tmp_path / "canonical.csv"
    source.write_bytes(b"synthetic bytes, never parsed")
    spec = SimpleNamespace(symbol="QQQ", canonical_market_data_relative_path=Path(source.name))
    monkeypatch.setattr(runner, "check_metadata", lambda *args: (spec,))
    monkeypatch.setattr(runner, "file_hash", lambda path: "sha256:" + "a" * 64)
    if fault == "contract":
        plan["target"] = "changed"
    elif fault == "code_keys":
        plan["code_sha256"].pop(runner.CODE[0])
    elif fault == "code_hash":
        plan["code_sha256"][runner.CODE[0]] = "sha256:" + "b" * 64
    with pytest.raises(runner.SmokeFault):
        runner.check_pins(plan, tmp_path, tmp_path, tmp_path)


def test_changed_lineage_never_parses_normalization(runner, tmp_path, monkeypatch):
    path = tmp_path / "lineage.json"
    path.write_bytes(b"{}")
    monkeypatch.setattr(
        runner,
        "parse_firstrate_normalization_receipt",
        lambda *args: pytest.fail("parsed despite failed lineage"),
    )
    with pytest.raises(runner.SmokeFault, match="lineage_hash_mismatch"):
        runner.check_metadata(path, tmp_path / "missing.json")


@pytest.fixture
def compute_harness(runner, tmp_path, monkeypatch):
    sessions = tuple(
        (OPEN + index * timedelta(days=1), OPEN + index * timedelta(days=1) + 390 * MINUTE)
        for index in range(251)
    )
    date_bytes = ("\n".join(pair[0].date().isoformat() for pair in sessions) + "\n").encode()
    monkeypatch.setattr(runner, "DATE_HASH", runner.digest(date_bytes))
    specs = tuple(
        SimpleNamespace(symbol=symbol, canonical_market_data_relative_path=Path(symbol))
        for symbol in runner.SYMBOLS
    )
    pins = []
    monkeypatch.setattr(runner, "check_pins", lambda *args: pins.append("check") or specs)
    monkeypatch.setattr(runner, "validate_firstrate_canonical_bars", lambda *args: None)
    monkeypatch.setattr(runner, "regular_sessions", lambda values: sessions)
    monkeypatch.setattr(runner.importlib.metadata, "version", lambda name: "5.4.0")
    sources = {symbol: list(minutes(symbol)) for symbol in runner.SYMBOLS}
    monkeypatch.setattr(
        runner.LocalCsvBarProvider, "get_bars", lambda self, query: sources[query.symbol]
    )
    return runner, sources, pins, tmp_path


def test_real_runner_counts_every_scheduled_key_without_future_mask(compute_harness):
    runner, sources, pins, root = compute_harness
    sources["SPY"] = [bar for bar in sources["SPY"] if bar.start_ts != OPEN + 180 * MINUTE]
    result = runner.compute(runner.contract({}), root, root, root, time.monotonic() + 120)
    assert pins == ["check", "check"]
    assert len(result["outcomes"]) == result["scheduled_shared_days"] == 251
    assert result["paired_inputs"] == {"available": 1, "required_past_m1_shortfall": 250}
    assert result["targets"]["QQQ"]["available"] == 1
    assert result["targets"]["SPY"]["required_forward_m1_shortfall"] == 251
    assert result["outcomes"][0]["input_status"] == "available"
    assert not result["raw_values_retained"]
    encoded = runner.encode(result)
    assert all(word not in encoded for word in (b"realized_variance", b"open", b"volume"))


def test_independent_input_commit_survives_changed_target(compute_harness):
    runner, sources, _, root = compute_harness
    first = runner.compute(runner.contract({}), root, root, root, time.monotonic() + 120)
    sources["QQQ"] = [
        replace(bar, open=Decimal(700), high=Decimal(700), low=Decimal(700), close=Decimal(700))
        if bar.start_ts == OPEN + 180 * MINUTE
        else bar
        for bar in sources["QQQ"]
    ]
    second = runner.compute(runner.contract({}), root, root, root, time.monotonic() + 120)
    assert first["input_commit_sha256"] == second["input_commit_sha256"]
    assert first["target_commit_sha256"] != second["target_commit_sha256"]


def test_expired_budget_never_loads_source(compute_harness, monkeypatch):
    runner, _, _, root = compute_harness
    monkeypatch.setattr(
        runner.LocalCsvBarProvider, "get_bars", lambda *args: pytest.fail("loaded after stop")
    )
    with pytest.raises(runner.SmokeFault, match="compute_stop"):
        runner.compute(runner.contract({}), root, root, root, time.monotonic() - 1)


@pytest.mark.parametrize("fault", ["contract", "raw_error", "readback"])
def test_cli_failure_suppresses_values_and_never_reports_target_pass(
    runner, tmp_path, monkeypatch, capsys, fault
):
    root = tmp_path / "smoke"
    root.mkdir()
    (root / "contract.json").write_bytes(b"{}")
    (root / "result.json").write_bytes(b"{}")
    args = SimpleNamespace(
        mode="verify",
        artifact_root=root,
        market_root=tmp_path,
        lineage=tmp_path,
        normalization=tmp_path,
    )
    monkeypatch.setattr(runner.argparse.ArgumentParser, "parse_args", lambda self: args)
    monkeypatch.setattr(Path, "resolve", lambda self: root)

    def compute(*args):
        if fault == "contract":
            raise runner.SmokeFault("contract_changed")
        if fault == "raw_error":
            raise ValueError("raw-price-must-not-escape")
        return {"status": "target_input_smoke_verified"}

    monkeypatch.setattr(runner, "compute", compute)
    assert runner.main() == 1
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "input_unavailable" and not output["target_pass"]
    assert "raw-price" not in json.dumps(output)


def test_script_import_has_no_environment_or_broker_side_effects(runner):
    assert runner.__name__ not in sys.modules
    assert runner.STUDY.startswith("firstrate-forward-variance")
