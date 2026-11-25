"""Exact handoff from the owned Nov27 capture into the Nov30 forecast."""

from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.data.kis_paper_h3_capture import H3DailyCapture
from thericher_v2.data.kis_paper_h3_daily_panel import NET25_H3_AXIS, H3DailyPanel, H3DailyPanelPlan
from thericher_v2.execution.kis_market_data import KisPaperDailyRawRow
from thericher_v2.models.h3_publisher_input import H3InputBinding, write_h3_publisher_input
from thericher_v2.ops import h3_nov30_run as module


@pytest.fixture
def owned_data(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "SOURCE.json").write_bytes(b"invented source")
    pin = module._sha(b"invented source")
    monkeypatch.setattr(module, "DATA_SOURCE_SHA256", pin)
    run = tmp_path / "run"
    capture_root = run / "capture"
    capture_root.mkdir(parents=True)
    state = capture_root / "capture-state.json"
    state.write_bytes(b"invented captured state")
    attempt = module._json(
        dict(
            source=pin,
            run=module.DATA_NAME,
            started_at=module.NOV27_CAPTURE_OPENS_UTC.isoformat(),
        )
    )
    (run / "ATTEMPT.json").write_bytes(attempt)
    plan = H3DailyPanelPlan(NET25_H3_AXIS, date(2026, 11, 27))
    rows = tuple(
        tuple(
            KisPaperDailyRawRow(day.strftime("%Y%m%d"), "2", "3", "1", "2", "1")
            for _ in NET25_H3_AXIS
        )
        for day in plan.sessions
    )
    closed = module.NOV27_CAPTURE_OPENS_UTC + timedelta(seconds=60)
    data = H3DailyCapture(H3DailyPanel(plan, rows), module._sha(state.read_bytes()), closed)
    binding = H3InputBinding(
        pin, module.NOV27_DECISION_UTC, module.NOV27_INPUT_HARD_STOP_UTC, False
    )

    def validate(a, h, **pins):
        assert h["source"] == pin and h["synthetic"] is False
        assert a["key"].tolist() == pins["expected_keys"]

    def parse(root, **pins):
        import json

        with np.load(root / "INPUT.npz", allow_pickle=False) as archive:
            a = dict(archive)
        h = json.loads((root / "INPUT.json").read_bytes())
        validate(a, h, **pins)
        return a, h

    digest = write_h3_publisher_input(
        run / "input",
        data,
        binding=binding,
        clock=lambda: closed,
        parse_input=parse,
        prefix_features=lambda *_: (
            np.zeros((17, 60, 12), dtype=np.float32),
            np.zeros((17, 8), dtype=np.float64),
        ),
    )
    owner = dict(
        schema="H3_NOV27_OWNER_CLOSED_V1",
        source=pin,
        attempt_sha256=module._sha(attempt),
        ready_sha256=digest,
        closed_at=closed.isoformat(),
        read_only=True,
        paper_only=True,
    )
    (run / "OWNER-CLOSED.json").write_bytes(module._json(owner))
    return SimpleNamespace(data=tmp_path, run=run, pin=pin, validate=validate, owner=owner)


@pytest.mark.parametrize("corruption", ["missing", "attempt", "ready", "late", "failed"])
def test_data_closure_required_before_model_access(owned_data, tmp_path, monkeypatch, corruption):
    source = owned_data
    end = source.run / "OWNER-CLOSED.json"
    if corruption == "missing":
        end.unlink()
    elif corruption == "attempt":
        (source.run / "ATTEMPT.json").write_bytes(b"{}")
    elif corruption == "ready":
        (source.run / "input" / "READY.json").write_bytes(b"{}")
    elif corruption == "late":
        end.write_bytes(
            module._json(source.owner | {"closed_at": module.NOV27_INPUT_HARD_STOP_UTC.isoformat()})
        )
    else:
        (source.run / "FAILED.json").write_bytes(b"{}")

    def uncalled(**_):
        pytest.fail("unadmitted Data closure reached the model loader")

    monkeypatch.setattr(module, "make_nov30_h3_forward", uncalled)
    monkeypatch.setattr(module, "_MEMBERS", {})
    with pytest.raises((OSError, ValueError)):
        module.run_nov30_forecast(
            source.data,
            tmp_path / "forecast",
            forecast_pin="a" * 64,
            clock=lambda: module.OPENS,
            validate_input=source.validate,
        )
    assert not (tmp_path / "forecast").exists()


def test_once_only_run_uses_exact_ready_and_closes(owned_data, tmp_path, monkeypatch):
    source = owned_data
    calls = []

    def forward(model, pin, fit, arrays):
        calls.append(model)
        return {str(key): 0.0 for key in arrays["key"]}

    monkeypatch.setattr(module, "make_nov30_h3_forward", lambda **_: forward)
    monkeypatch.setattr(module, "_MEMBERS", {})
    out = tmp_path / "forecast"
    kwargs = dict(forecast_pin="a" * 64, clock=lambda: module.OPENS, validate_input=source.validate)
    digest = module.run_nov30_forecast(source.data, out, **kwargs)
    assert module._sha((out / "SEAL.json").read_bytes()) == digest
    assert b'"seal_sha256":"' + digest.encode() + b'"' in (out / "OWNER-CLOSED.json").read_bytes()
    with pytest.raises(ValueError, match="nov30_forecast_destination"):
        module.run_nov30_forecast(source.data, out, **kwargs)
    assert calls == ["SELF", "OLD60"]
