"""Trusted enum handoff and complete SYN producer -> codec -> native worker flow."""

import hashlib
import importlib.util
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import test_kis_paper_current_stock_cycle as legacy
from test_model_paper_profile import h as h
from test_model_paper_profile import record
from test_prepare_window21_paper_proposal import bundle as bundle
from test_prepare_window21_paper_proposal import prepare
from thericher_v2.execution import kis_paper_current_stock_cycle as cycle
from thericher_v2.research.model_paper_proposal import (
    load_model_paper_input,
    serialize_model_paper_input,
)

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/run_kis_paper_current_stock_cycle_worker.py"
SPEC = importlib.util.spec_from_file_location("synthetic_model_paper_worker_test", SCRIPT)
w = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(w)
PIN = "sha256:" + "3" * 64
POLICY = "sha256:" + "4" * 64


@pytest.fixture(autouse=True)
def no_actual_calls(monkeypatch):
    legacy.no_actual_calls.__wrapped__(monkeypatch)

    def denied(*_args, **_kwargs):
        pytest.fail("actual_worker_effect_forbidden")

    monkeypatch.setattr(w, "client_factory", denied)
    monkeypatch.setattr(w, "native_paths", denied)
    monkeypatch.setattr(w, "RequestBudget", denied)
    monkeypatch.setattr(w.readonly, "load_kis_paper_config", denied)


def limits(**_kwargs):
    return SimpleNamespace(
        calls=dict(token_posts=0, get_requests=0, buy_posts=0, sell_posts=0, cancel_posts=0),
        starts=[],
    )


def test_default_remains_inert_before_injection_paths_or_config():
    assert w.run(None, profile="untrusted-value", target_loader="not-called") == dict(
        status="inert", credential_reads=0, broker_calls=0
    )


@pytest.mark.parametrize(
    "fault", ["text", "legacy", "current20", "missing_loader", "missing_pin", "bad_pin", "no_enum"]
)
def test_untrusted_profile_or_partial_injection_cannot_select_loader(fault):
    arguments = dict(
        profile=cycle.StockCycleProfile.MODEL_PROPOSAL_NAS,
        target_loader=lambda: None,
        expected_input_ref=PIN,
        expected_policy_ref=POLICY,
    )
    if fault == "text":
        arguments["profile"] = cycle.StockCycleProfile.MODEL_PROPOSAL_NAS.value
    elif fault == "legacy":
        arguments["profile"] = cycle.StockCycleProfile.LEGACY_NAS
    elif fault == "current20":
        arguments["profile"] = cycle.StockCycleProfile.CURRENT20_EQUALRANK4
    elif fault == "missing_loader":
        arguments["target_loader"] = None
    elif fault == "missing_pin":
        arguments["expected_input_ref"] = None
    elif fault == "bad_pin":
        arguments["expected_policy_ref"] = "untrusted-policy"
    else:
        arguments["profile"] = None
    with pytest.raises(ValueError, match="model_profile_injection_invalid"):
        w.run(legacy.CONFIG, execute=True, **arguments)


def test_only_trusted_enum_loader_and_pins_are_forwarded_legacy_defaults_stay_exact(monkeypatch):
    captured = []

    def clock():
        return legacy.AT

    factory, loader, sink = object(), lambda: None, lambda _: None
    monkeypatch.setattr(w, "RequestBudget", limits)
    monkeypatch.setattr(w, "native_paths", lambda: dict(state_root="invented-state-root"))
    monkeypatch.setattr(w, "client_factory", lambda *_: factory)

    def native(**arguments):
        captured.append(arguments)
        return cycle.CurrentStockCycleOutcome("no_intent", "native_risk_no_intent")

    monkeypatch.setattr(cycle, "run_kis_paper_current_stock_cycle", native)
    result = w.run(
        legacy.CONFIG,
        execute=True,
        clock=clock,
        profile=cycle.StockCycleProfile.MODEL_PROPOSAL_NAS,
        target_loader=loader,
        expected_input_ref=PIN,
        expected_policy_ref=POLICY,
        first_failure_sink=sink,
    )
    args = captured[-1]
    assert result["status"] == "no_intent" and args["target_loader"] is loader
    assert args["profile"] is cycle.StockCycleProfile.MODEL_PROPOSAL_NAS
    assert args["expected_input_ref"] == PIN and args["expected_policy_ref"] == POLICY
    assert args["client_factory"] is factory and args["first_failure_sink"] is sink
    assert "fees" in result and result["net_pnl"] == "not_observed"
    w.run(legacy.CONFIG, execute=True, clock=clock)
    assert "profile" not in captured[-1] and "first_failure_sink" not in captured[-1]
    assert captured[-1]["expected_input_ref"] == "sha256:" + w.PRIVATE_PINS["targets.private.json"]
    assert captured[-1]["expected_policy_ref"] == "sha256:" + w.POLICY_PIN


def test_complete_synthetic_producer_seal_restore_worker_native_entry(h, bundle, monkeypatch):
    source = prepare(bundle)
    payload = serialize_model_paper_input(source)
    expected_sha = hashlib.sha256(payload).hexdigest()
    h["data"], h["now"] = source, source.entry_session.open_ts + timedelta(minutes=30)
    loads = []

    def loader():
        loads.append(True)
        return load_model_paper_input(
            payload, expected_sha256=expected_sha, expected_policy_ref=source.policy_ref
        )

    monkeypatch.setattr(w, "RequestBudget", limits)
    monkeypatch.setattr(
        w,
        "native_paths",
        lambda: {
            k: v
            for k, v in h["call"].items()
            if k
            in {
                "state_root",
                "repository_root",
                "artifact_root",
                "runtime_projection_path",
                "paper_account_snapshot_path",
                "emergency_state_path",
                "execution_control_path",
            }
        },
    )
    monkeypatch.setattr(w, "client_factory", lambda *_: h["call"]["client_factory"])
    arguments = dict(
        execute=True,
        clock=lambda: h["now"],
        profile=cycle.StockCycleProfile.MODEL_PROPOSAL_NAS,
        target_loader=loader,
        expected_input_ref=source.input_ref,
        expected_policy_ref=source.policy_ref,
    )
    assert w.run(legacy.CONFIG, **arguments)["status"] == "advanced"
    assert len(loads) == len(h["submits"]) == 1 and h["submits"][0].symbol == "AAPL"
    saved = record(h)
    assert cycle._unpack(saved["active"]["model_input"]) == source
    assert len(cycle._unpack(saved["active"]["model_input"]).metadata.rows) == 25
    assert w.run(legacy.CONFIG, **arguments)["status"] == "advanced"
    assert len(loads) == 1 and len(h["submits"]) == 2


def test_stdin_and_cli_cannot_pick_profile_or_module(monkeypatch):
    for option in ("--profile", "--module", "--proposal"):
        with pytest.raises(SystemExit):
            w.main([option, "untrusted"])
    packet = dict(
        KIS_PAPER_APP_KEY="synthetic-key",
        KIS_PAPER_APP_SECRET="synthetic-secret",
        KIS_PAPER_ACCOUNT_NO="12345678",
        KIS_PAPER_ACCOUNT_PRODUCT_CODE="01",
        THERICHER_MODE="kis_paper",
        profile=cycle.StockCycleProfile.MODEL_PROPOSAL_NAS.value,
    )
    with pytest.raises(ValueError):
        w.parse_packet(json.dumps(packet).encode())
    source = SCRIPT.read_text()
    assert "import torch" not in source and "import numpy" not in source
    assert "prepare_window21" not in source
