"""Additive H5 native lifecycle and cross-profile recovery on invented custody."""

import copy
from dataclasses import replace
from datetime import date, timedelta

import pytest

import test_kis_paper_current_stock_cycle as legacy
import test_kis_paper_weight_cycle as weights
import test_model_paper_profile as model_native
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution import kis_paper_current_stock_cycle as cycle
from thericher_v2.research.model_paper_weights import (
    MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
    prepare_model_paper_weights_input,
)

H5 = cycle.StockCycleProfile.MODEL_WEIGHTS_NAS_H5
H20 = cycle.StockCycleProfile.MODEL_WEIGHTS_NAS


@pytest.fixture(autouse=True)
def no_actual_calls(monkeypatch):
    legacy.no_actual_calls.__wrapped__(monkeypatch)


def point(profile=H5):
    if profile is H20:
        return weights.prepared()
    first = us_equity_2026_session(date(2026, 10, 26)).window
    last = us_equity_2026_session(date(2026, 10, 30)).window
    meta = replace(weights.metadata(), exit_not_before=last.close_ts - timedelta(minutes=15))
    return prepare_model_paper_weights_input(
        meta, entry_session=first, exit_session=last, profile=MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE
    )


@pytest.fixture
def h(tmp_path):
    result = model_native.h.__wrapped__(tmp_path)
    weights.bind(result, point(), H5)
    return result


def forbidden(*args, **kwargs):
    pytest.fail("cross_profile_must_fail_before_loader_or_client")


def test_h5_roundtrip_native_entries_and_exact_retained_exit(h):
    assert h["data"].profile == H5.value
    assert cycle._unpack(cycle._pack(h["data"])) == h["data"]
    assert weights.visit_all(h)[-1].status == "hold"
    retained = weights.record(h)
    assert retained["profile"] == H5.value
    assert cycle._unpack(retained["active"]["model_input"]) == h["data"]
    buys = len(h["submits"])
    assert buys > 0 and all(intent.side == "buy" for intent in h["submits"])
    basis = cycle.budget._load_binding(h["root"])["basis_ref"]
    h["now"] = h["data"].metadata.exit_not_before - timedelta(seconds=1)
    assert weights.run(h, target_loader=forbidden).status == "hold"
    h["now"] += timedelta(seconds=1)
    assert weights.visit_all(h, target_loader=forbidden)[-1].status == "complete"
    assert len(h["submits"]) == 2 * buys
    assert all(intent.side == "sell" for intent in h["submits"][buys:])
    assert cycle.budget._load_binding(h["root"])["basis_ref"] == basis


@pytest.mark.parametrize("profile", [H5, H20])
def test_cross_profile_fresh_input_denied_before_any_side_effect(h, profile):
    other = H20 if profile is H5 else H5
    weights.bind(h, point(profile), other)
    before = weights.bank_bytes(h)
    assert weights.run(h).reason == "cycle_input_invalid"
    assert weights.bank_bytes(h) == before and weights.record(h) is None
    assert h["factories"] == 0 and h["submits"] == []


@pytest.mark.parametrize("profile", [H5, H20])
@pytest.mark.parametrize("forge_header", [False, True])
def test_pending_cross_profile_cannot_release_or_replace_request(h, profile, forge_header):
    weights.bind(h, point(profile), profile)
    h["unknown"] = True
    assert weights.run(h).status == "pending"
    other = H20 if profile is H5 else H5
    original = weights.record(h)
    pending = copy.deepcopy(original["pending"])
    if forge_header:
        original["profile"] = other.value
        cycle._save(weights.pointer(h), original)
    before = weights.bank_bytes(h)
    result = weights.run(h, profile=other, target_loader=forbidden, client_factory=forbidden)
    assert result.status == "unavailable"
    assert weights.bank_bytes(h) == before
    assert weights.record(h)["pending"] == pending
    assert len(h["submits"]) == 1


@pytest.mark.parametrize("missing_or_unknown", [None, "model-weights-nas-arbitrary-session"])
def test_missing_or_unknown_persisted_profile_denied_before_recovery(h, missing_or_unknown):
    h["unknown"] = True
    assert weights.run(h).status == "pending"
    saved = weights.record(h)
    if missing_or_unknown is None:
        del saved["profile"]
    else:
        saved["profile"] = missing_or_unknown
    cycle._save(weights.pointer(h), saved)
    before = weights.bank_bytes(h)
    pending = copy.deepcopy(saved["pending"])
    assert weights.run(h, target_loader=forbidden, client_factory=forbidden).status == "unavailable"
    assert weights.bank_bytes(h) == before and weights.record(h)["pending"] == pending


def test_h5_unknown_request_keeps_its_identity_on_normal_restart(h):
    h["unknown"] = True
    assert weights.run(h).status == "pending"
    pending = copy.deepcopy(weights.record(h)["pending"])
    before = weights.bank_bytes(h)
    h["now"] = h["data"].exit_session.close_ts + timedelta(days=2)
    assert weights.run(h, target_loader=forbidden).status == "pending"
    assert weights.record(h)["pending"] == pending
    assert weights.bank_bytes(h) == before and len(h["submits"]) == 1
