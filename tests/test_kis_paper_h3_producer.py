import hashlib
import json
import socket
import urllib.request
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import numpy as np
import pytest

from thericher_v2.data.kis_paper_h3_daily_panel import NET25_H3_AXIS, H3DailyPanelPlan
from thericher_v2.data.kis_paper_h3_producer import produce_dec3_h3_publisher_input_once
from thericher_v2.execution import kis_market_data as market
from thericher_v2.execution import kis_paper_data_capture as capture
from thericher_v2.models.h3_publisher_input import read_h3_publisher_input

OPEN = datetime(2026, 12, 3, 21, 30, tzinfo=UTC)
CLOSE = OPEN + timedelta(minutes=10)
LIMIT = OPEN + timedelta(minutes=15)
DECISION = datetime(2026, 12, 4, 14, 25, tzinfo=UTC)
SOURCE = "3" * 64


@pytest.fixture
def dated_run(tmp_path, monkeypatch):
    now = OPEN
    calls = []
    sessions = H3DailyPanelPlan(NET25_H3_AXIS).sessions

    def set_clock(stamp):
        nonlocal now
        now = stamp

    class Response:
        status = 200
        headers = {}

        def __init__(self, body):
            self.body = json.dumps(body).encode("ascii")

        def read(self, size):
            return self.body[:size]

        def close(self):
            pass

    class Opener:
        def open(self, request, timeout):
            url = urlsplit(request.full_url)
            method = request.get_method()
            calls.append(method)
            if method == "POST":
                assert url.path == market.KIS_PAPER_TOKEN_PATH
                return Response({"access_token": "invented-token"})
            assert method == "GET" and url.path == market.KIS_PAPER_DAILY_PATH
            i = len(calls) - 2
            symbol, venue = NET25_H3_AXIS[i]
            assert parse_qs(url.query) == dict(
                SYMB=[symbol], EXCD=[venue], GUBN=["0"], BYMD=["20261203"], MODP=["1"]
            )
            return Response(
                dict(
                    rt_cd="0",
                    output1=dict(rsym=f"D{venue}{symbol}"),
                    output2=[
                        dict(
                            xymd=day.strftime("%Y%m%d"),
                            open=str(10 + i),
                            high=str(13 + i),
                            low=str(9 + i),
                            clos=str(11 + i),
                            tvol="100",
                        )
                        for day in reversed(sessions)
                    ],
                )
            )

    def no_network(*args, **kwargs):
        pytest.fail("real network forbidden")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(urllib.request, "build_opener", lambda *_args: Opener())
    monkeypatch.setattr(capture, "_MARKET_BASE", tmp_path / "market")
    monkeypatch.setattr(capture, "_ARTIFACT_BASE", tmp_path / "artifacts")

    def features(ohlc, known, conditional):
        assert ohlc.shape == (60, 19, 4)
        assert ohlc[-1, :, 3].tolist() == list(range(11, 30))
        assert known.all() and not conditional.any()
        return np.ones((17, 60, 12), np.float32), np.ones((17, 8), np.float64)

    def parse_input(root, **pins):
        header = json.loads((root / "INPUT.json").read_bytes())
        with np.load(root / "INPUT.npz", allow_pickle=False) as archive:
            arrays = dict(archive)
        validate_input(arrays, header, **pins)
        return arrays, header

    options = dict(
        market_root=tmp_path / "market/dec3",
        artifact_root=tmp_path / "artifacts/dec3",
        input_root=tmp_path / "input-dec4",
        data_source_sha256=SOURCE,
        synthetic=True,
        clock=lambda: now,
        owner_ready=lambda: capture.CaptureReadiness(True),
        config_loader=lambda: market.KisPaperMarketDataConfig(
            app_key="invented-key", app_secret="invented-secret"
        ),
        prefix_features=features,
        parse_input=parse_input,
        monotonic=lambda: (now - OPEN).total_seconds(),
        sleeper=lambda seconds: set_clock(now + timedelta(seconds=seconds)),
    )
    return options, calls, set_clock


def validate_input(arrays, header, *, expected_source, role, expected_keys, synthetic):
    assert expected_source == header["source"] == SOURCE
    assert role == header["role"] == "FUTURE_20261203_ASOF_20261204"
    assert synthetic is header["synthetic"] is True
    assert expected_keys == arrays["key"].tolist() == [f"20261204|{i:02d}" for i in range(17)]
    assert set(arrays["decision_at"]) == {DECISION.isoformat()}
    assert set(arrays["context_close"]) == {"2026-12-03T21:00:00+00:00"}


def test_native_capture_through_publisher_and_reader(dated_run):
    options, calls, set_clock = dated_run
    parse = options["parse_input"]

    def parse_after_capture(root, **pins):
        result = parse(root, **pins)
        set_clock(CLOSE)  # The input stage may finish after the capture window.
        return result

    produced = produce_dec3_h3_publisher_input_once(
        **(options | {"parse_input": parse_after_capture})
    )
    assert calls == ["POST"] + ["GET"] * 19
    assert produced.capture_state_path == options["artifact_root"] / "capture-state.json"
    assert produced.input_root == options["input_root"]
    assert produced.binding.decision_at == DECISION
    assert produced.binding.hard_stop == LIMIT
    ready_raw = (produced.input_root / "READY.json").read_bytes()
    assert hashlib.sha256(ready_raw).hexdigest() == produced.ready_sha256
    ready = json.loads(ready_raw)
    assert OPEN <= datetime.fromisoformat(ready["closed_at"]) < CLOSE
    assert ready["ready_at"] == CLOSE.isoformat()
    arrays, _ = read_h3_publisher_input(
        produced.input_root,
        produced.capture_state_path,
        binding=produced.binding,
        ready_sha256=produced.ready_sha256,
        clock=lambda: LIMIT,
        validate_input=validate_input,
    )
    assert arrays["x"].shape == (17, 60, 12)
    set_clock(OPEN)
    with pytest.raises(ValueError, match="fresh_roots_required"):
        produce_dec3_h3_publisher_input_once(**options)
    assert calls == ["POST"] + ["GET"] * 19


@pytest.mark.parametrize(
    "stamp", [OPEN - timedelta(microseconds=1), CLOSE, OPEN.replace(tzinfo=None)]
)
def test_capture_window_refuses_before_touching_storage(stamp, dated_run, tmp_path):
    options, calls, set_clock = dated_run
    set_clock(stamp)
    with pytest.raises(ValueError, match="outside_capture_window"):
        produce_dec3_h3_publisher_input_once(**options)
    assert not calls and not list(tmp_path.iterdir())


@pytest.mark.parametrize("pin", ["owner_ready", "config_loader", "parse_input", "prefix_features"])
def test_requires_separate_pinned_callables(pin, dated_run, tmp_path):
    options, calls, _ = dated_run
    with pytest.raises(ValueError, match="pinned_callables_required"):
        produce_dec3_h3_publisher_input_once(**(options | {pin: None}))
    assert not calls and not list(tmp_path.iterdir())


def test_existing_input_is_not_reused_or_a_reason_to_spend_capture(dated_run):
    options, calls, _ = dated_run
    options["input_root"].mkdir()
    old = options["input_root"] / "DATAREADY.json"
    old.write_bytes(b"invented prior readiness")
    with pytest.raises(ValueError, match="fresh_roots_required"):
        produce_dec3_h3_publisher_input_once(**options)
    assert old.read_bytes() == b"invented prior readiness"
    assert not calls and not options["market_root"].exists()


def test_overlapping_custody_is_refused(dated_run):
    options, calls, _ = dated_run
    with pytest.raises(ValueError, match="roots_overlap"):
        produce_dec3_h3_publisher_input_once(
            **(options | {"input_root": options["artifact_root"] / "input"})
        )
    assert not calls


def test_owner_denial_prevents_wire_and_publication(dated_run):
    options, calls, _ = dated_run
    options["owner_ready"] = lambda: capture.CaptureReadiness(False)
    with pytest.raises(ValueError, match="page_unavailable"):
        produce_dec3_h3_publisher_input_once(**options)
    assert not calls and not options["input_root"].exists()


@pytest.mark.parametrize("failure", ["deadline", "capture_state"])
def test_withholds_handoff_on_deadline_or_state_drift(failure, dated_run):
    options, calls, set_clock = dated_run
    parse = options["parse_input"]

    def change_during_parse(root, **pins):
        result = parse(root, **pins)
        if failure == "deadline":
            set_clock(LIMIT)
        else:
            (options["artifact_root"] / "capture-state.json").write_bytes(b"changed")
        return result

    error = "outside_window" if failure == "deadline" else "capture_state_changed"
    with pytest.raises(ValueError, match=error):
        produce_dec3_h3_publisher_input_once(**(options | {"parse_input": change_during_parse}))
    assert calls == ["POST"] + ["GET"] * 19
    assert not (options["input_root"] / "READY.json").exists()
