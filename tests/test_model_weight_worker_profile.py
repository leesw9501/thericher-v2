"""Inert worker injection ABI checks, not native or broker qualification."""

import io
import json
import socket
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_kis_paper_current_stock_cycle_worker import CONFIG, NOW, w
from thericher_v2.execution import kis_paper_current_stock_cycle as cycle

INPUT_REF = "sha256:" + "a" * 64
POLICY_REF = "sha256:" + "b" * 64


def _forbidden(*_args, **_kwargs):
    pytest.fail("unexpected real dependency or legacy target path")


@pytest.fixture(autouse=True)
def inert_dependencies(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", _forbidden)
    monkeypatch.setattr(socket.socket, "connect", _forbidden)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", _forbidden)
    monkeypatch.setattr(w.readonly, "load_kis_paper_config", _forbidden)
    monkeypatch.setattr(w, "RequestBudget", _forbidden)
    monkeypatch.setattr(w, "client_factory", _forbidden)
    monkeypatch.setattr(w, "native_paths", _forbidden)
    monkeypatch.setattr(w, "load_targets", _forbidden)
    monkeypatch.setattr(cycle, "run_kis_paper_current_stock_cycle", _forbidden)


def _injection(**changes):
    values = dict(
        profile=cycle.StockCycleProfile.MODEL_WEIGHTS_NAS,
        target_loader=lambda: object(),
        expected_input_ref=INPUT_REF,
        expected_policy_ref=POLICY_REF,
    )
    values.update(changes)
    return values


def _mock_construction(monkeypatch):
    limits = SimpleNamespace(
        calls=dict(token_posts=0, get_requests=0, buy_posts=0, sell_posts=0, cancel_posts=0),
        starts=[],
    )
    client = object()
    seen = []
    paths = dict(
        state_root=Path("invented-state"),
        repository_root=Path("invented-repository"),
        artifact_root=Path("invented-artifacts"),
    )

    def budget(**kwargs):
        assert kwargs["control_root"] == w.CONTROL
        assert kwargs["clock"]() == NOW
        seen.append("budget")
        return limits

    def factory(config, passed_limits):
        assert config is CONFIG and passed_limits is limits
        seen.append("client_factory")
        return client

    monkeypatch.setattr(w, "RequestBudget", budget)
    monkeypatch.setattr(w, "client_factory", factory)
    monkeypatch.setattr(w, "native_paths", lambda: paths)
    return limits, client, seen, paths


@pytest.mark.parametrize(
    "profile",
    [cycle.StockCycleProfile.MODEL_PROPOSAL_NAS, cycle.StockCycleProfile.MODEL_WEIGHTS_NAS],
)
def test_model_profiles_forward_exact_loader_refs_and_metadata(monkeypatch, profile):
    limits, client, seen, paths = _mock_construction(monkeypatch)
    loaded = object()
    loads = []
    failure_sink = object()

    def clock():
        return NOW

    def loader():
        loads.append(True)
        return loaded

    def native(**kwargs):
        assert kwargs == dict(
            **paths,
            expected_account_ref=w.budget._digest(
                [CONFIG.base_url, CONFIG.account_number, CONFIG.account_product_code]
            ),
            expected_input_ref=INPUT_REF,
            expected_policy_ref=POLICY_REF,
            target_loader=loader,
            client_factory=client,
            clock=clock,
            execute=True,
            profile=profile,
            first_failure_sink=failure_sink,
        )
        assert kwargs["target_loader"]() is loaded
        seen.append("core")
        return cycle.CurrentStockCycleOutcome("complete", "already_completed", 0)

    monkeypatch.setattr(cycle, "run_kis_paper_current_stock_cycle", native)
    result = w.run(
        CONFIG, execute=True, clock=clock, first_failure_sink=failure_sink,
        **_injection(profile=profile, target_loader=loader),
    )
    assert seen == ["budget", "client_factory", "core"] and loads == [True]
    assert (result["status"], result["reason"]) == ("complete", "already_completed")
    assert result["calls"] is limits.calls and sum(result["calls"].values()) == 0
    assert result["paper_only"] is True and result["unknown_effects_not_assumed_zero"] is True
    assert result["observed_at_utc"] == NOW.isoformat()
    assert (result["fees"], result["settled_cash"], result["net_pnl"]) == ("not_observed",) * 3


def test_default_run_and_cli_are_inert_with_zero_constructions(monkeypatch, capsys):
    unread = io.BytesIO(b"invented-never-read")
    monkeypatch.setattr(w.sys, "stdin", SimpleNamespace(buffer=unread))
    monkeypatch.setattr(w, "parse_packet", _forbidden)
    expected = dict(status="inert", credential_reads=0, broker_calls=0)
    assert w.run(None, **_injection()) == expected
    assert w.main([]) == 0
    assert json.loads(capsys.readouterr().out) == expected
    assert unread.tell() == 0


@pytest.mark.parametrize(
    "profile",
    ["invented-unknown-profile", cycle.StockCycleProfile.CURRENT20_EQUALRANK4,
     cycle.StockCycleProfile.MODEL_WEIGHTS_NAS.value],
    ids=["unknown", "current20", "nonenum-spelling"],
)
def test_other_profiles_reject_before_budget_client_or_core(profile):
    with pytest.raises(ValueError, match="^model_profile_injection_invalid$"):
        w.run(CONFIG, execute=True, **_injection(profile=profile))


def test_incomplete_or_noncallable_injection_rejects_before_construction():
    for field in ("profile", "target_loader", "expected_input_ref", "expected_policy_ref"):
        with pytest.raises(ValueError, match="^model_profile_injection_invalid$"):
            w.run(CONFIG, execute=True, **_injection(**{field: None}))
    with pytest.raises(ValueError, match="^model_profile_injection_invalid$"):
        w.run(CONFIG, execute=True, **_injection(target_loader=object()))


@pytest.mark.parametrize(
    "field,bad_ref",
    [("expected_input_ref", "sha256:" + "A" * 64),
     ("expected_policy_ref", "sha256:" + "b" * 64 + "\n")],
)
def test_noncanonical_refs_reject_before_budget_client_or_core(field, bad_ref):
    with pytest.raises(ValueError, match="^model_profile_injection_invalid$"):
        w.run(CONFIG, execute=True, **_injection(**{field: bad_ref}))


def test_injected_loader_failure_never_falls_back_to_legacy_targets(monkeypatch):
    limits, _, seen, _ = _mock_construction(monkeypatch)
    calls = []

    def broken_loader():
        calls.append(True)
        raise ValueError("invented-loader-failure")

    def native(**kwargs):
        assert kwargs["target_loader"] is broken_loader
        return kwargs["target_loader"]()

    monkeypatch.setattr(cycle, "run_kis_paper_current_stock_cycle", native)
    result = w.run(CONFIG, execute=True, clock=lambda: NOW,
                   **_injection(target_loader=broken_loader))
    assert calls == [True] and seen == ["budget", "client_factory"]
    assert (result["status"], result["reason"]) == ("unavailable", "worker_recovery_required")
    assert result["calls"] is limits.calls and sum(result["calls"].values()) == 0
    assert result["unknown_effects_not_assumed_zero"] is True
