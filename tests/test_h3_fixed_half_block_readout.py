from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from test_prospective_h3_block import replays as native_replays
from thericher_v2.ops.h3_dec4_fixed_half_reader import RELEASE_AT as DEC4_RELEASE_AT
from thericher_v2.ops.h3_fixed_half_block_evaluate import evaluate_h3_fixed_half_block
from thericher_v2.ops.h3_fixed_half_block_readout import (
    BLOCK_RELEASE_AT,
    H3BlockReadoutError,
    H3SlotReaderBinding,
    H3SlotReadiness,
    read_h3_fixed_half_block,
)
from thericher_v2.ops.h3_fixed_half_target_slot import RELEASE_AT as NOV30_RELEASE_AT
from thericher_v2.research.prospective_h3_block import H3BlockSlot

replays = native_replays


@pytest.fixture
def readers(replays):
    reads = []

    def bind(replay, index):
        def read(reader_ready):
            assert reader_ready() is True
            reads.append(index)
            return replay

        return H3SlotReaderBinding(replay.interval, f"{index + 1:064x}", read)

    return tuple(bind(replay, index) for index, replay in enumerate(replays)), reads


def _at_release():
    return BLOCK_RELEASE_AT


def _ready(_binding):
    return H3SlotReadiness.READY


def test_native_expiry_close_matches_existing_reader_releases():
    assert BLOCK_RELEASE_AT == datetime(2026, 12, 28, 21, tzinfo=UTC)
    assert BLOCK_RELEASE_AT == NOV30_RELEASE_AT == DEC4_RELEASE_AT


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 12, 3, 21, tzinfo=UTC),
        datetime(2026, 12, 28, 14, 30, tzinfo=UTC),
        BLOCK_RELEASE_AT - timedelta(microseconds=1),
        BLOCK_RELEASE_AT.replace(tzinfo=None),
        BLOCK_RELEASE_AT.astimezone(timezone(timedelta(hours=9))),
        "2026-12-28T21:00:00Z",
    ],
)
def test_no_attestation_or_target_read_before_valid_release(readers, now):
    bindings, reads = readers

    def attest(_binding):
        pytest.fail("attestation ran before a valid release")

    with pytest.raises(H3BlockReadoutError, match="h3_block_readout_clock"):
        read_h3_fixed_half_block(bindings, attest=attest, clock=lambda: now)
    assert reads == []


@pytest.mark.parametrize("missing", [(), (2,), (2, 4), (0, 1, 2, 3, 4)])
def test_reads_bound_slots_in_order_and_preserves_native_result(readers, replays, missing):
    bindings, reads = readers
    pins = {binding.interval: binding for binding in bindings}

    def attest(binding):
        assert binding is pins[binding.interval]
        index = bindings.index(binding)
        assert binding.source_sha256 == f"{index + 1:064x}"
        return H3SlotReadiness.UNMEASURED if index in missing else H3SlotReadiness.READY

    result = read_h3_fixed_half_block(bindings, attest=attest, clock=_at_release)
    expected = tuple(
        H3BlockSlot(replay.interval, None if index in missing else replay)
        for index, replay in enumerate(replays)
    )
    assert reads == [index for index in range(5) if index not in missing]
    assert result == evaluate_h3_fixed_half_block(expected)
    assert result.unmeasured_intervals == tuple(bindings[index].interval for index in missing)
    assert (result.block.comparison is not None) == (len(missing) <= 1)
    assert result.block.slots[1].status == ("absent" if 1 in missing else "no_signal")


@pytest.mark.parametrize(
    ("change", "error"),
    [
        (lambda bindings: bindings[:-1], "schedule"),
        (lambda bindings: bindings[::-1], "schedule"),
        (lambda bindings: (bindings[0], *bindings[:-1]), "schedule"),
        (list, "schedule"),
        (lambda bs: (replace(bs[0], interval=tuple(bs[0].interval)), *bs[1:]), "schedule"),
        (lambda bs: (*bs[:-1], replace(bs[-1], source_sha256="unbound")), "source"),
        (lambda bs: (*bs[:-1], replace(bs[-1], read=None)), "source"),
    ],
)
def test_validates_full_ordered_binding_before_attestation(readers, change, error):
    bindings, reads = readers

    def attest(_binding):
        pytest.fail("invalid binding reached attestation")

    with pytest.raises(H3BlockReadoutError, match=f"h3_block_readout_{error}"):
        read_h3_fixed_half_block(change(bindings), attest=attest, clock=_at_release)
    assert reads == []


@pytest.mark.parametrize(
    ("state", "error"),
    [
        (H3SlotReadiness.UNOPENED, "unopened"),
        (H3SlotReadiness.LIVE, "live"),
        (H3SlotReadiness.ERROR, "error"),
        (None, "attestation"),
        (True, "attestation"),
    ],
)
def test_unresolved_last_slot_does_not_open_any_slot(readers, state, error):
    bindings, reads = readers

    def attest(binding):
        return state if binding is bindings[-1] else H3SlotReadiness.READY

    with pytest.raises(H3BlockReadoutError, match=f"^h3_block_readout_{error}$"):
        read_h3_fixed_half_block(bindings, attest=attest, clock=_at_release)
    assert reads == []


def test_attestation_failure_is_not_unmeasured(readers):
    bindings, reads = readers

    def attest(_binding):
        raise OSError("invented custody path")

    with pytest.raises(H3BlockReadoutError, match="^h3_block_readout_attest_error$"):
        read_h3_fixed_half_block(bindings, attest=attest, clock=_at_release)
    assert reads == []


def test_terminal_absence_must_stay_bound_through_block_readout(readers):
    bindings, reads = readers

    def attest(binding):
        if binding is bindings[0] and not reads:
            return H3SlotReadiness.UNMEASURED
        return H3SlotReadiness.READY

    with pytest.raises(H3BlockReadoutError, match="h3_block_readout_readiness_changed"):
        read_h3_fixed_half_block(bindings, attest=attest, clock=_at_release)
    assert reads == [1, 2, 3, 4]


def test_native_reader_gate_rechecks_clock_before_access(readers):
    bindings, reads = readers
    now = BLOCK_RELEASE_AT + timedelta(seconds=1)

    def read(reader_ready):
        nonlocal now
        now = BLOCK_RELEASE_AT
        reader_ready()
        pytest.fail("clock rollback admitted a target read")

    with pytest.raises(H3BlockReadoutError, match="h3_block_readout_clock"):
        read_h3_fixed_half_block(
            (replace(bindings[0], read=read), *bindings[1:]),
            attest=_ready,
            clock=lambda: now,
        )
    assert reads == []


def test_writer_appearing_during_read_withholds_result_and_later_reads(readers, replays):
    bindings, reads = readers
    live = False

    def attest(binding):
        if binding.interval == bindings[0].interval and live:
            return H3SlotReadiness.LIVE
        return H3SlotReadiness.READY

    def read(reader_ready):
        nonlocal live
        assert reader_ready() is True
        live = True
        return replays[0]

    with pytest.raises(H3BlockReadoutError, match="h3_block_readout_live"):
        read_h3_fixed_half_block(
            (replace(bindings[0], read=read), *bindings[1:]), attest=attest, clock=_at_release
        )
    assert reads == []


@pytest.mark.parametrize("throws", [False, True])
def test_reader_failure_is_not_unmeasured(readers, throws):
    bindings, reads = readers

    def read(reader_ready):
        assert reader_ready() is True
        if throws:
            raise FileNotFoundError("invented private path")
        return None

    error = "reader_error" if throws else "reader_result"
    with pytest.raises(H3BlockReadoutError, match=f"^h3_block_readout_{error}$"):
        read_h3_fixed_half_block(
            (replace(bindings[0], read=read), *bindings[1:]), attest=_ready, clock=_at_release
        )
    assert reads == []


def test_replay_interval_binding_is_enforced_by_native_adapter(readers, replays):
    bindings, _ = readers
    wrong = replace(bindings[0], read=lambda _ready: replays[1])
    with pytest.raises(ValueError, match="h3_fixed_half_block_binding"):
        read_h3_fixed_half_block((wrong, *bindings[1:]), attest=_ready, clock=_at_release)
