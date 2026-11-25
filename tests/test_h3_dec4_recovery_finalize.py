"""Finalize only the exact physical receipt, joined recovery and native readback."""

from dataclasses import asdict
from pathlib import Path

import pytest

import test_h3_dec4_crash_recovery as fixture
from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.execution.net25_pending_reconciliation import Net25TerminalProof
from thericher_v2.ops.h3_dec4_recovery_finalize import _finalize, _sha


@pytest.fixture
def recovered(tmp_path):
    active = fixture.active.__wrapped__(tmp_path)
    path, identity, _ = active
    fixture._run(active)
    run = identity["run"]
    physical = path.parent / ("PHYSICAL-CLOSED-" + run + ".json")
    native = path.parent / ("NATIVE-RECONCILED-" + run + ".json")
    proof = Net25TerminalProof(
        *("sha256:" + n * 64 for n in "123456"), evidence_kind="broker_terminal_retained"
    )
    receipt = dict(
        schema="h3-dec4-native-reconciled-v1",
        source=identity["source"],
        original_claim_sha256=_sha(path.read_bytes()),
        physical_sha256=_sha(physical.read_bytes()),
        joined_recovery_visit_sha256="a" * 64,
        order_posts=0,
        terminal=asdict(proof),
    )
    native.write_bytes(pv.encode(receipt))
    return path, identity, native, receipt, proof


def finish(case, *, verify=lambda proof: proof, pending=None):
    path, identity, native, receipt, proof = case
    return _finalize(
        path.parent.parent,
        fixture._BANK,
        identity,
        receipt["physical_sha256"],
        _sha(native.read_bytes()),
        pending or proof.pending_ref,
        lambda _: None,
        verify,
    )


def test_exact_reconciled_close_writes_terminal_before_releasing_active(recovered, monkeypatch):
    path, identity, _, _, _ = recovered
    original = Path.unlink
    closed = path.parent / ("CLOSED-" + identity["run"] + ".json")

    def fail_once(member, **kwargs):
        if member == path:
            assert closed.exists()
            raise OSError("invented interruption after terminal save")
        return original(member, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_once)
        with pytest.raises(OSError, match="after terminal"):
            finish(recovered)
    assert path.exists()
    before = closed.read_bytes()
    assert finish(recovered)["status"] == "CLOSED_OPERATIONAL_ONLY"
    assert not path.exists() and closed.read_bytes() == before
    assert pv._decode(before)["reservation_or_budget_release"] is False


@pytest.mark.parametrize("case", ["unconfirmed_native", "wrong_order", "tampered_original"])
def test_bad_recovery_stays_held(recovered, case):
    path, _, _, _, _ = recovered
    if case == "tampered_original":
        before = pv._decode(path.read_bytes())
        path.write_bytes(pv.encode(before | {"sequence": before["sequence"] + 1}))
    with pytest.raises(pv.Denied):
        finish(
            recovered,
            verify=lambda proof: None if case == "unconfirmed_native" else proof,
            pending="sha256:" + "b" * 64 if case == "wrong_order" else None,
        )
    assert path.exists() and not list(path.parent.glob("CLOSED-*.json"))
