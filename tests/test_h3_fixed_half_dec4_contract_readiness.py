"""Dec4/Dec9 data-plane smoke, not production custody or runtime admission.

Invented normalized native pages stand in for an already acquired edition.
Forecast byte validation is native, but its filesystem and owner-tree checks
are not exercised. Block attestations are fixture inputs, not terminal evidence.
No capture, model, market runner, or real artifact path is used.
"""

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from fractions import Fraction

import pytest

from thericher_v2.data.kis_paper_h3_daily_panel import (
    NET25_H3_AXIS,
    H3DailyPanelError,
    H3DailyPanelPlan,
    qualify_h3_daily_panel,
)
from thericher_v2.execution.kis_paper_data_capture import CaptureResult
from thericher_v2.ops import h3_dec4_fixed_half_plan as plan
from thericher_v2.ops import h3_dec4_fixed_half_reader as forecast_reader
from thericher_v2.ops import h3_dec4_point_owner as dec3
from thericher_v2.ops.h3_fixed_half_block_readout import (
    H3BlockReadoutError,
    H3SlotReaderBinding,
    H3SlotReadiness,
    read_h3_fixed_half_block,
)
from thericher_v2.ops.h3_fixed_half_slot_evaluate import evaluate_dec4_fixed_half_slot
from thericher_v2.research.prospective_h3_block import reduce_prospective_h3_block
from thericher_v2.research.prospective_h3_calendar import H3Interval
from thericher_v2.research.prospective_h3_marks import project_prospective_h3_marks

_SESSIONS = tuple(date(2026, 12, day) for day in (4, 7, 8, 9))
_INTERVAL = H3Interval(_SESSIONS[0], _SESSIONS[-1])
_RELEASE = datetime(2026, 12, 28, 21, tzinfo=UTC)
_SOURCE = "a" * 64


@pytest.fixture(scope="module")
def invented_target():
    target_plan = H3DailyPanelPlan(NET25_H3_AXIS, _INTERVAL.expiry)
    captures = []
    for col, query in enumerate(target_plan.queries):
        page = json.dumps(
            [
                dict(
                    xymd=day.strftime("%Y%m%d"),
                    open=str(100 + row + col),
                    high="1000",
                    low="1",
                    clos=str(101 + row + col),
                    tvol="1",
                )
                for row, day in reversed(tuple(enumerate(target_plan.sessions)))
            ]
        ).encode("ascii")
        result = CaptureResult(
            query.key, "ACCEPTED", 60, native={"sha256": hashlib.sha256(page).hexdigest()}
        )
        captures.append((result, page))
    return target_plan, tuple(reversed(captures))


def _invented_forecast():
    refs = tuple(char * 64 for char in "bcde")
    identity = dict(
        study=plan.STUDY,
        financial_authority=False,
        synthetic=False,  # This is the native record's required ABI value, not an attestation.
        forecast_source_sha256=_SOURCE,
        data_source_sha256=dec3.DATA_SOURCE_SHA256,
        data_attempt_sha256=refs[0],
        data_owner_sha256=refs[1],
        ready_sha256=refs[2],
        data_ready_sha256=refs[3],
        parser_sha256=dec3._PARSER_SHA,
        self_model=asdict(plan.loader.SELF_PIN),
        old60_model=asdict(plan.loader.OLD60_PIN),
        fit_sha256=plan.loader.FIT_SHA256,
        input_adapter_sha256=plan.loader._ADAPTER_SHA256,
        entry_io_sha256=plan.loader._ENTRY_IO_SHA256,
        policy_sha256=plan.POLICY_SHA256,
        role="FUTURE_20261203_ASOF_20261204",
        keys=[f"20261204|{i:02d}" for i in range(17)],
        context_close="2026-12-03T21:00:00+00:00",
        decision_at="2026-12-04T14:25:00+00:00",
        entry_open="2026-12-04T14:30:00+00:00",
        expiry_open="2026-12-09T14:30:00+00:00",
        input_verified_at="2026-12-04T14:12:00+00:00",
        attempt_started_at="2026-12-04T14:12:30+00:00",
    )
    attempt = dec3._json(dict(identity, schema="DEC4_FIXED_HALF_H3_ATTEMPT_V1"))
    sealed = datetime(2026, 12, 4, 14, 14, tzinfo=UTC)
    seal = dec3._json(
        dict(
            identity,
            schema="DEC4_FIXED_HALF_H3_FORECAST_V1",
            attempt_sha256=dec3._sha(attempt),
            sealed_at=sealed.isoformat(),
            SELF=[3.0, 2.0] + [0.0] * 15,
            OLD60=[-1.0, -2.0] + [0.0] * 15,
            BLEND=[1.0] + [0.0] * 16,
        )
    )
    completion = forecast_reader.Dec4ForecastCompletion(
        _SOURCE, dec3._sha(seal), 0, sealed + timedelta(seconds=1)
    )
    return forecast_reader._admit(attempt, seal, source=_SOURCE, completion=completion, refs=refs)


def _block_inputs(target_plan, captures, events):
    def read(ready):
        assert ready() is True
        events.append("read_dec4")
        panel = qualify_h3_daily_panel(target_plan, captures)
        marks = project_prospective_h3_marks(panel, _INTERVAL)
        assert marks.sessions == _SESSIONS
        assert len(marks.opens) == 4 and len(marks.closes) == 3
        assert ready() is True
        return evaluate_dec4_fixed_half_slot(_invented_forecast(), marks)

    def unexpected_read(_ready):
        pytest.fail("synthetic terminally unmeasured slot must not read")

    bindings = tuple(
        H3SlotReaderBinding(
            slot.interval, _SOURCE, read if slot.interval == _INTERVAL else unexpected_read
        )
        for slot in reduce_prospective_h3_block(()).slots
    )

    def attest(binding):
        events.append("attest")
        if binding.interval == _INTERVAL:
            return H3SlotReadiness.READY
        return H3SlotReadiness.UNMEASURED

    return bindings, attest


def test_invented_dec9_pages_and_dec4_seal_reach_the_block(invented_target):
    events = []
    bindings, attest = _block_inputs(*invented_target, events)
    result = read_h3_fixed_half_block(bindings, attest=attest, clock=lambda: _RELEASE)

    assert events.count("read_dec4") == 1
    assert result.unmeasured_intervals == tuple(
        binding.interval for binding in bindings if binding.interval != _INTERVAL
    )
    assert result.block.admitted_count == 1 and result.block.comparison is None
    slot = result.block.slots[1]
    assert slot.interval == _INTERVAL and slot.status == "scored"
    replay = slot.replay
    assert replay is not None
    buy = Fraction(400, 13601)
    sell = buy * Fraction(159, 156)
    assert replay.model.entry_notional == replay.matched_gross_ew.entry_notional == buy
    assert replay.model.exit_notional == sell
    assert replay.model.growth == sell - buy - (buy + sell) / 400
    assert replay.cash.growth == 0


def test_block_refuses_before_attestation_or_read(invented_target):
    events = []
    bindings, attest = _block_inputs(*invented_target, events)
    with pytest.raises(H3BlockReadoutError, match="^h3_block_readout_clock$"):
        read_h3_fixed_half_block(
            bindings, attest=attest, clock=lambda: _RELEASE - timedelta(microseconds=1)
        )
    assert not events


def test_changed_page_cannot_be_scored_or_reported_unmeasured(invented_target):
    target_plan, captures = invented_target
    last_decision_key = target_plan.queries[16].key
    index = next(
        i for i, (result, _) in enumerate(captures) if result.query_key == last_decision_key
    )
    retained, page = captures[index]
    # Keep the original digest; a harmless JSON whitespace change still invalidates the bytes.
    altered = (*captures[:index], (retained, page + b" "), *captures[index + 1 :])
    with pytest.raises(H3DailyPanelError, match="^h3_panel_native_digest_mismatch$"):
        qualify_h3_daily_panel(target_plan, altered)

    events = []
    bindings, attest = _block_inputs(target_plan, altered, events)
    with pytest.raises(H3BlockReadoutError, match="^h3_block_readout_reader_error$"):
        read_h3_fixed_half_block(bindings, attest=attest, clock=lambda: _RELEASE)
    assert events.count("read_dec4") == 1
