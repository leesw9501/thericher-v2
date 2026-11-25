import json
from dataclasses import replace

import numpy as np
import pytest

from test_kis_paper_h3_producer import dated_run as dated_run
from test_kis_paper_h3_producer import validate_input
from thericher_v2.data.kis_paper_h3_daily_panel import H3DailyPanelError
from thericher_v2.models import h3_shadow_point
from thericher_v2.ops import h3_dec4_run as ops


@pytest.fixture
def launchers(dated_run, monkeypatch):
    options, requests, set_clock = dated_run
    pins = {
        key: options.pop(key)
        for key in ("market_root", "artifact_root", "input_root", "data_source_sha256", "synthetic")
    }
    run = ops.Dec4H3Run(**pins, point_root=pins["input_root"].with_name("point-dec4"))
    forwards = []

    def forward(arrays, source, stats, weights, *, before_forward):
        assert arrays["x"].shape == (17, 60, 12)
        assert (source, stats, weights) == (b"model", b"stats", b"weights")
        before_forward()
        forwards.append(1)
        return np.ones(17, np.float64)

    monkeypatch.setattr(h3_shadow_point, "_frozen_lstm", forward)

    def data(plan=run):
        return ops.run_dec3_data(plan, **options)

    def point(plan=run, *, owner_ready=lambda: True, minute=48):
        set_clock(ops.INPUT_HARD_STOP_UTC.replace(minute=minute))
        return ops.run_dec4_point(
            replace(plan),
            clock=options["clock"],
            owner_ready=owner_ready,
            validate_input=validate_input,
            model_source=b"model",
            stats=b"stats",
            weights=b"weights",
        )

    return run, data, point, requests, forwards


def test_native_data_receipt_to_independent_shadow_point(launchers):
    run, data, point, requests, forwards = launchers
    ready_digest = data()
    assert requests == ["POST"] + ["GET"] * 19
    assert not run.point_root.exists()
    with pytest.raises(FileExistsError, match="consumed_root"):
        data()
    with pytest.raises(ValueError, match="point_clock_denied"):
        point(minute=52)
    point_digest = point()
    record = h3_shadow_point.read_dec4_h3_shadow_point(
        run.point_root,
        binding=ops.H3InputBinding(
            run.data_source_sha256, ops.DECISION_UTC, ops.INPUT_HARD_STOP_UTC, run.synthetic
        ),
        ready_sha256=ready_digest,
        point_sha256=point_digest,
    )
    assert record["ready_sha256"] == ready_digest
    assert record["synthetic"] and not record["financial_authority"]
    with pytest.raises(FileExistsError, match="consumed_root"):
        point()
    assert len(requests) == 20 and forwards == [1]


def test_native_ready_without_data_completion_receipt_is_not_admitted(launchers, monkeypatch):
    run, data, point, requests, forwards = launchers
    native = ops.produce_dec3_h3_publisher_input_once

    def interrupted(**kwargs):
        native(**kwargs)
        raise ValueError("invented_post_ready_failure")

    monkeypatch.setattr(ops, "produce_dec3_h3_publisher_input_once", interrupted)
    with pytest.raises(ValueError, match="invented_post_ready_failure"):
        data()
    assert (run.input_root / "READY.json").exists()
    with pytest.raises(H3DailyPanelError, match="unreadable"):
        point()
    with pytest.raises(FileExistsError, match="consumed_root"):
        data()
    assert len(requests) == 20 and not forwards and not run.point_root.exists()


def test_expired_data_receipt_stays_pending_and_cannot_feed_point(
    launchers, dated_run, monkeypatch
):
    run, data, point, requests, forwards = launchers
    _, _, set_clock = dated_run
    native = ops.produce_dec3_h3_publisher_input_once

    def finish_at_hard_stop(**kwargs):
        produced = native(**kwargs)
        set_clock(ops.INPUT_HARD_STOP_UTC)
        return produced

    monkeypatch.setattr(ops, "produce_dec3_h3_publisher_input_once", finish_at_hard_stop)
    with pytest.raises(ValueError, match="receipt_clock_denied"):
        data()
    assert (run.input_root / "DATA-READY.pending").exists()
    assert not (run.input_root / "DATA-READY.json").exists()
    with pytest.raises(ValueError, match="receipt_pending"):
        point()
    assert len(requests) == 20 and not forwards and not run.point_root.exists()


def test_point_refuses_wrong_plan_owner_or_native_ready_digest(launchers):
    run, data, point, requests, forwards = launchers
    data()
    for plan in (
        replace(run, market_root=run.market_root.with_name("other-market")),
        replace(run, artifact_root=run.artifact_root.with_name("other-state")),
        replace(run, point_root=run.point_root.with_name("other-point")),
        replace(run, data_source_sha256="4" * 64),
        replace(run, synthetic=False),
    ):
        with pytest.raises(ValueError, match="receipt_binding_mismatch"):
            point(plan)
        assert not plan.point_root.exists()
    with pytest.raises(ValueError, match="point_owner_denied"):
        point(owner_ready=lambda: False)
    receipt = run.input_root / "DATA-READY.json"
    payload = json.loads(receipt.read_bytes())
    payload["ready_sha256"] = "5" * 64
    receipt.write_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii"))
    with pytest.raises(ValueError, match="ready_digest_mismatch"):
        point()
    assert len(requests) == 20 and not forwards and not run.point_root.exists()


def test_data_refuses_invalid_output_plan_before_capture(launchers):
    run, data, _, requests, forwards = launchers
    with pytest.raises(ValueError, match="overlapping_roots"):
        data(replace(run, point_root=run.input_root / "nested"))
    run.point_root.mkdir()
    with pytest.raises(FileExistsError, match="consumed_root"):
        data()
    assert not requests and not forwards and not run.market_root.exists()
