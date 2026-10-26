"""Opt-in execution timing only; invented inputs/book/client and mocked wire."""

import copy
import hashlib
import json
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

import test_kis_paper_weight_cycle as native
from test_kis_paper_current_stock_cycle_worker import CONFIG, Response, w
from test_kis_paper_stock_canary import INSTRUMENT, _generic_request, _quote_request
from test_model_paper_weights_h5 import _metadata
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution import kis_paper_current_stock_cycle as cycle
from thericher_v2.execution import kis_paper_portfolio_plan as portfolio
from thericher_v2.research import model_paper_weights as weights

PROFILE = cycle.StockCycleProfile.MODEL_WEIGHTS_NAS_H20_EARLY_EXIT
NEW_POLICY = "sha256:" + "8" * 64


def point(first=date(2026, 10, 26), last=date(2026, 11, 20)):
    first, last = [us_equity_2026_session(d).window for d in (first, last)]
    meta = replace(
        _metadata(first, last),
        policy_ref=NEW_POLICY,
        exit_not_before=last.close_ts - timedelta(minutes=45),
    )
    return weights.prepare_model_paper_weights_input(
        meta, entry_session=first, exit_session=last, profile=PROFILE.value
    )


@pytest.fixture(autouse=True)
def no_real_access(monkeypatch):
    def deny(*a, **k):
        pytest.fail("actual_network_or_credentials_forbidden")

    for owner, attr in (
        (socket, "create_connection"),
        (socket.socket, "connect"),
        (urllib.request, "urlopen"),
        (urllib.request.OpenerDirector, "open"),
        (w.readonly, "load_kis_paper_config"),
        (w.readonly, "load_kis_paper_config_from_environment"),
    ):
        monkeypatch.setattr(owner, attr, deny)


@pytest.fixture
def h(tmp_path):
    state = native.h.__wrapped__(tmp_path)
    native.bind(state, point(), PROFILE)
    state["configured"] = []

    def configure(value, side, session):
        state["configured"].append(
            (side, weights.model_paper_early_exit_window(value, operational_session=session))
        )

    state["call"]["configure_early_exit"] = configure
    return state


def forbidden(*a, **k):
    pytest.fail("retained_request_must_not_reload_or_replace")


def test_explicit_profile_roundtrip_dst_and_half_day():
    for first, last, hour in (
        (date(2026, 10, 26), date(2026, 11, 20), 21),
        (date(2026, 2, 20), date(2026, 3, 19), 20),
        (date(2026, 10, 30), date(2026, 11, 27), 18),
    ):
        value = point(first, last)
        raw = weights.serialize_model_paper_weights_input(value)
        assert (
            weights.load_model_paper_weights_input(
                raw, expected_sha256=hashlib.sha256(raw).hexdigest(), expected_policy_ref=NEW_POLICY
            )
            == value
        )
        window = weights.model_paper_early_exit_window(value)
        close = value.exit_session.close_ts
        assert close.hour == hour
        assert (window.exit_start, window.exit_end, window.cleanup_end, window.closure_before) == (
            close - timedelta(minutes=45),
            close - timedelta(minutes=25),
            close - timedelta(minutes=20),
            close - timedelta(minutes=15),
        )
        assert value.execution_basis == weights.EARLY_EXIT_EXECUTION_BASIS
        assert "NON_PARITY" in value.execution_basis


def test_old_profile_still_exact15_and_no_retagging_or_clock_forgery():
    value = point()
    with pytest.raises(ValueError, match="weights_session_clocks_invalid"):
        weights.prepare_model_paper_weights_input(
            value.metadata, entry_session=value.entry_session, exit_session=value.exit_session
        )
    old = weights.prepare_model_paper_weights_input(
        replace(
            value.metadata, exit_not_before=value.exit_session.close_ts - timedelta(minutes=15)
        ),
        entry_session=value.entry_session,
        exit_session=value.exit_session,
    )
    document = json.loads(weights.serialize_model_paper_weights_input(value))
    for field, replacement in (
        ("profile", old.profile),
        ("execution_basis", weights.EXECUTION_BASIS),
    ):
        changed = document | {field: replacement}
        raw = json.dumps(changed, sort_keys=True, separators=(",", ":")).encode()
        with pytest.raises(ValueError):
            weights.load_model_paper_weights_input(
                raw, expected_sha256=hashlib.sha256(raw).hexdigest(), expected_policy_ref=NEW_POLICY
            )
    for minutes in (44, 46):
        with pytest.raises(ValueError, match="weights_session_clocks_invalid"):
            weights.prepare_model_paper_weights_input(
                replace(
                    value.metadata,
                    exit_not_before=value.exit_session.close_ts - timedelta(minutes=minutes),
                ),
                entry_session=value.entry_session,
                exit_session=value.exit_session,
                profile=PROFILE.value,
            )
    with pytest.raises(ValueError, match="weights_session_clocks_invalid"):
        weights.prepare_model_paper_weights_input(
            replace(value.metadata, weights_observed_at=value.entry_session.open_ts),
            entry_session=value.entry_session,
            exit_session=value.exit_session,
            profile=PROFILE.value,
        )


def test_native_input_admission_and_required_boundary_no_cross_profile(h):
    value = h["data"]
    assert cycle._validate_input(value, h["now"], PROFILE) is value
    with pytest.raises(cycle._CycleFault, match="cycle_input_invalid"):
        cycle._validate_input(value, h["now"], cycle.StockCycleProfile.MODEL_WEIGHTS_NAS)
    before = native.bank_bytes(h)
    result = native.run(h, configure_early_exit=None)
    assert result.reason == "cycle_configuration_invalid"
    assert native.bank_bytes(h) == before and not h["submits"]


def test_late_entry_shared_v4_book_has_no_profile_codec_or_extra_cap(h):
    h["now"] = h["data"].entry_session.open_ts + timedelta(hours=5)
    assert native.visit_all(h)[-1].status == "hold"
    binding = cycle.budget._load_binding(h["root"])
    assert binding["version"] == 4
    for key in ("allocated_usd", "basis_ref", "orders", "qqq", "portfolio"):
        assert binding[key] == h["initial"][key]
    assert PROFILE.value.encode() not in native.bank_bytes(h)
    assert b"NON_PARITY" not in native.bank_bytes(h)
    states = portfolio._states(h["root"], binding)
    replayed, proofs = portfolio._replay_scope(binding, states)
    projection = cycle.budget.project_shared_budget(
        binding=binding,
        states=replayed,
        expected_account_ref=binding["account_ref"],
        expected_basis_ref=binding["basis_ref"],
        expected_owner_refs=cycle._refs(binding),
        as_of=h["now"],
    )
    assert projection.remaining_cap >= 0
    assert set(proofs) <= set(states)
    assert h["submits"] and all(i.side == "buy" for i in h["submits"])
    assert native.record(h)["profile"] == PROFILE.value


def test_exit_half_open_boundaries_and_ttl_clipped_to_fresh_cutoff(h):
    assert native.visit_all(h)[-1].status == "hold"
    window = weights.model_paper_early_exit_window(h["data"])
    count = len(h["submits"])
    for at in (window.exit_start - timedelta(microseconds=1), window.exit_end):
        h["now"] = at
        assert native.run(h, target_loader=forbidden).status == "hold"
        assert len(h["submits"]) == count
    h["now"] = window.exit_end - timedelta(seconds=1)
    assert native.run(h, target_loader=forbidden).status == "advanced"
    sell = h["submits"][-1]
    assert sell.side == "sell" and sell.valid_until == window.exit_end
    assert sell.quantity <= h["submits"][0].quantity


def test_quote_delay_crosses_cutoff_before_new_intent(h, monkeypatch):
    native.visit_all(h)
    end = weights.model_paper_early_exit_window(h["data"]).exit_end
    h["now"] = end - timedelta(seconds=1)
    old = native.model_native.SyntheticClient.stock_exit_snapshot

    def delayed(client, **kw):
        reads = old(client, **kw)
        h["now"] = end
        return reads

    monkeypatch.setattr(native.model_native.SyntheticClient, "stock_exit_snapshot", delayed)
    before = native.bank_bytes(h)
    result = native.run(h)
    assert result.status == "hold" and native.record(h)["pending"] is None
    assert native.bank_bytes(h) == before
    assert all(i.side == "buy" for i in h["submits"])


def test_sell_unknown_cutoff_preserves_identity_then_nov23_is_recoverable(h):
    native.visit_all(h)
    window = weights.model_paper_early_exit_window(h["data"])
    h["now"], h["unknown"] = window.exit_start, True
    assert native.run(h).status == "pending"
    pending = copy.deepcopy(native.record(h)["pending"])
    bank = native.bank_bytes(h)
    submits, factories = len(h["submits"]), h["factories"]
    h["now"] = window.cleanup_end
    assert native.run(h, target_loader=forbidden).status == "pending"
    assert h["factories"] == factories and native.bank_bytes(h) == bank
    assert native.record(h)["pending"] == pending
    h["now"] = datetime(2026, 11, 23, 15, tzinfo=UTC)
    assert native.run(h, target_loader=forbidden).status == "pending"
    assert h["factories"] > factories and len(h["submits"]) == submits
    assert native.record(h)["pending"]["arguments"] == pending["arguments"]
    assert native.bank_bytes(h) == bank
    side, current = h["configured"][-1]
    assert side == "sell" and current.cleanup_end == datetime(2026, 11, 23, 20, 40, tzinfo=UTC)


def test_residual_later_day_uses_official_session_without_new_buy(h):
    native.visit_all(h)
    h["now"] = datetime(2026, 11, 23, 20, 14, 59, tzinfo=UTC)
    count = len(h["submits"])
    assert native.run(h).status == "hold" and len(h["submits"]) == count
    h["now"] = datetime(2026, 11, 23, 20, 15, tzinfo=UTC)
    assert native.run(h).status == "advanced"
    assert h["submits"][-1].side == "sell"
    assert h["submits"][-1].valid_until <= datetime(2026, 11, 23, 20, 35, tzinfo=UTC)


def test_buy_unknown_recovery_is_not_blocked_by_exit_cleanup(h):
    h["unknown"] = True
    assert native.run(h).status == "pending"
    pending = copy.deepcopy(native.record(h)["pending"])
    h["now"] = weights.model_paper_early_exit_window(h["data"]).cleanup_end
    factories, before = h["factories"], native.bank_bytes(h)
    assert native.run(h, target_loader=forbidden).status == "pending"
    assert h["factories"] > factories and len(h["submits"]) == 1
    assert native.record(h)["pending"]["arguments"] == pending["arguments"]
    assert native.bank_bytes(h) == before


def test_registered_foreign_stock_default_and_new_profile_never_adopt_then_emergency(h):
    value = h["data"]
    old_meta = replace(
        value.metadata,
        policy_ref="sha256:" + "7" * 64,
        exit_not_before=value.exit_session.close_ts - timedelta(minutes=15),
    )
    old = weights.prepare_model_paper_weights_input(
        old_meta, entry_session=value.entry_session, exit_session=value.exit_session
    )
    native.bind(h, old)
    assert native.run(h).status == "advanced"
    existing = copy.deepcopy(cycle.budget._load_binding(h["root"])["stocks"])
    symbol = h["submits"][0].symbol
    assert symbol == value.targets[0].proposal.symbol
    other_default = weights.prepare_model_paper_weights_input(
        replace(old_meta, policy_ref="sha256:" + "9" * 64),
        entry_session=value.entry_session,
        exit_session=value.exit_session,
    )
    for proposed, profile in ((other_default, native.PROFILE), (value, PROFILE)):
        native.bind(h, proposed, profile)
        assert native.run(h).status == "no_intent"
        assert native.record(h)["owners"] == {}
        assert cycle.budget._load_binding(h["root"])["stocks"][symbol] == existing[symbol]
        assert len(h["submits"]) == 1
        assert cycle._unpack(native.record(h)["active"]["targets"]) == proposed.targets
    cycle.canary.EmergencyStore(h["call"]["emergency_state_path"]).stop_new_orders("synthetic")
    assert native.run(h).status == "pending" and len(h["submits"]) == 1
    assert cycle.budget._load_binding(h["root"])["basis_ref"] == h["initial"]["basis_ref"]


def test_worker_wire_rechecks_pacing_and_owner_delay_and_cleanup(tmp_path):
    value = point()
    win = weights.model_paper_early_exit_window(value)
    sell = _generic_request("submit")
    sell = replace(
        sell,
        headers=dict(sell.headers) | {"tr_id": w.canary.KIS_PAPER_US_SELL_LIMIT_ORDER_TR_ID},
        json_body=dict(sell.json_body) | {"SLL_TYPE": "00"},
    )
    for index, delay in enumerate(("rate", "owner", "token", "cleanup")):
        now = [win.exit_end - timedelta(seconds=1)]
        limits = w.RequestBudget(
            control_root=tmp_path / str(index),
            clock=lambda now=now: now[0],
            monotonic=lambda: 0.0,
            sleeper=lambda _: None,
        )
        limits.configure_early_exit(value, "sell", value.exit_session)
        seen = []

        class Opener:
            def open(self, *a, seen=seen, **k):
                seen.append(True)
                return Response()

        transport = w.OwnedTransport(instrument=INSTRUMENT, limits=limits)
        transport._opener = Opener()
        limits.rate.wait_for_request_slot = lambda: None
        owner = None
        if delay == "rate":
            limits.rate.wait_for_request_slot = lambda now=now: now.__setitem__(0, win.exit_end)
        elif delay == "owner":

            def owner(now=now):
                now[0] = win.exit_end
        elif delay == "token":
            now[0] = win.cleanup_end - timedelta(seconds=1)

            def claim(now=now):
                now[0] = win.cleanup_end
                return True

            limits.token.claim_token_request_start = claim
        else:
            now[0] = win.cleanup_end
        with pytest.raises(w.canary.KisPaperCanaryError, match="early_exit_"):
            request = (
                _generic_request("token")
                if delay == "token"
                else (_quote_request() if delay == "cleanup" else sell)
            )
            transport._request(request, before_wire=owner)
        assert seen == [] and sum(limits.calls.values()) == 0


def test_worker_injection_opt_in_and_cleanup_allows_no_fresh_sell(tmp_path, monkeypatch):
    value = point()
    win = weights.model_paper_early_exit_window(value)
    now = [win.exit_end]
    limits = w.RequestBudget(
        control_root=tmp_path / "control",
        clock=lambda: now[0],
        monotonic=lambda: 0.0,
        sleeper=lambda _: None,
    )
    limits.configure_early_exit(value, "sell", value.exit_session)
    limits._execution_window_check(_generic_request("cancel"))
    limits._execution_window_check(_quote_request())
    now[0] = win.cleanup_end
    with pytest.raises(w.canary.KisPaperCanaryError):
        limits._execution_window_check(_generic_request("cancel"))
    monkeypatch.setattr(w, "RequestBudget", lambda **_: limits)
    monkeypatch.setattr(w, "native_paths", lambda: {})
    monkeypatch.setattr(w, "client_factory", lambda *a: forbidden)

    def run(**kwargs):
        assert kwargs["profile"] is PROFILE
        assert kwargs["configure_early_exit"] == limits.configure_early_exit
        return cycle.CurrentStockCycleOutcome("hold", "outside_declared_session")

    monkeypatch.setattr(cycle, "run_kis_paper_current_stock_cycle", run)
    assert (
        w.run(
            CONFIG,
            execute=True,
            profile=PROFILE,
            target_loader=lambda: value,
            expected_input_ref=value.input_ref,
            expected_policy_ref=value.policy_ref,
        )["status"]
        == "hold"
    )
