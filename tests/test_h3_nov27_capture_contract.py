import hashlib
import io
import json
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import numpy as np
import pytest

from thericher_v2.data.kis_paper_h3_capture import capture_h3_daily_panel_once
from thericher_v2.data.kis_paper_h3_daily_panel import (
    NET25_H3_AXIS,
    H3DailyPanelError,
    H3DailyPanelPlan,
)
from thericher_v2.data.kis_paper_h3_producer import produce_nov27_h3_publisher_input_once
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution import kis_market_data as market
from thericher_v2.execution import kis_paper_data_capture as capture
from thericher_v2.models.h3_publisher_input import (
    H3InputBinding,
    read_h3_publisher_input,
)

AS_OF = date(2026, 11, 27)
EARLY_CLOSE = datetime(2026, 11, 27, 18, tzinfo=UTC)
# Expected producer clocks, independent of its constants.
CAPTURE_OPENS = EARLY_CLOSE + timedelta(minutes=30)
CAPTURE_CLOSES = EARLY_CLOSE + timedelta(minutes=40)
INPUT_HARD_STOP = EARLY_CLOSE + timedelta(minutes=45)
DECISION = datetime(2026, 11, 30, 14, 25, tzinfo=UTC)
SOURCE = hashlib.sha256(b"invented nov27 MODP1 source").hexdigest()
ROLE = "FUTURE_20261127_ASOF_20261130"
KEYS = [f"20261130|{i:02d}" for i in range(17)]


@pytest.fixture(scope="module")
def plan():
    return H3DailyPanelPlan(NET25_H3_AXIS, as_of=AS_OF)


def test_plan_uses_early_close_and_exact_next_session(plan):
    session = us_equity_2026_session(AS_OF)
    assert session.kind == "early_close"
    assert session.window.close_ts == plan.as_of_close_utc == EARLY_CLOSE
    assert us_equity_2026_session(date(2026, 11, 26)) is None
    assert us_equity_2026_session(date(2026, 11, 28)) is None
    assert us_equity_2026_session(date(2026, 11, 29)) is None
    assert us_equity_2026_session(DECISION.date()).window.open_ts == DECISION + timedelta(minutes=5)
    assert len(plan.sessions) == 60 and plan.sessions[-2:] == (date(2026, 11, 25), AS_OF)
    assert len({query.key for query in plan.queries}) == 19
    assert plan.axis[-2:] == (("SPY", "AMS"), ("QQQ", "NAS"))


def _capture_options(plan, tmp_path):
    return dict(
        plan=plan,
        market_root=tmp_path / "market/nov27",
        artifact_root=tmp_path / "artifacts/nov27",
        window_opens_utc=CAPTURE_OPENS,
        window_closes_utc=CAPTURE_CLOSES,
    )


@pytest.mark.parametrize(
    ("opens", "now", "reason"),
    [
        (EARLY_CLOSE, EARLY_CLOSE, "window_invalid"),
        (CAPTURE_OPENS, CAPTURE_OPENS - timedelta(microseconds=1), "outside_window"),
        (CAPTURE_OPENS, CAPTURE_CLOSES, "outside_window"),
        (CAPTURE_OPENS, EARLY_CLOSE.replace(hour=21, minute=30), "outside_window"),
    ],
)
def test_capture_refuses_early_late_or_regular_close_clock(plan, tmp_path, opens, now, reason):
    def forbidden():
        pytest.fail("capture gate must refuse before owner or config access")

    options = _capture_options(plan, tmp_path) | {"window_opens_utc": opens}
    with pytest.raises(H3DailyPanelError, match=reason):
        capture_h3_daily_panel_once(
            **options, clock=lambda: now, owner_ready=forbidden, config_loader=forbidden
        )
    with pytest.raises(ValueError, match="h3_producer_outside_capture_window"):
        produce_nov27_h3_publisher_input_once(
            market_root=options["market_root"],
            artifact_root=options["artifact_root"],
            input_root=tmp_path / "input-nov30",
            data_source_sha256=SOURCE,
            synthetic=True,
            clock=lambda: now,
            owner_ready=forbidden,
            config_loader=forbidden,
            prefix_features=_features,
            parse_input=_parse,
        )
    assert not list(tmp_path.iterdir())


def _features(ohlc, known, conditional):
    assert ohlc.shape == (60, 19, 4)
    assert ohlc[-1, :, 3].tolist() == list(range(11, 30))
    assert known.all() and not conditional.any()
    return np.ones((17, 60, 12), np.float32), np.ones((17, 8), np.float64)


def _validate(arrays, header, *, expected_source, role, expected_keys, synthetic):
    assert header["schema"] == "SHORT_SWING_H123_INPUT_V1"
    assert header["producer"] == "Data.ShortSwingEndpointProducer"
    assert header["consumer"] == "EngineResearch.ShortSwingHorizonInput"
    assert header["source"] == expected_source == SOURCE
    assert header["role"] == role == ROLE
    assert header["synthetic"] is synthetic is True
    assert arrays["key"].tolist() == expected_keys == KEYS
    assert set(arrays["context_close"]) == {EARLY_CLOSE.isoformat()}
    assert set(arrays["decision_at"]) == {DECISION.isoformat()}
    assert arrays["known"].all() and not arrays["entry_index"].any()
    assert arrays["x"].shape == (17, 60, 12) and arrays["x"].dtype == np.float32
    assert arrays["z"].shape == (17, 8) and arrays["z"].dtype == np.float64


def _parse(root, **pins):
    header = json.loads((root / "INPUT.json").read_bytes())
    payload = (root / "INPUT.npz").read_bytes()
    assert hashlib.sha256(payload).hexdigest() == header["payload_sha256"]
    with np.load(io.BytesIO(payload), allow_pickle=False) as archive:
        arrays = dict(archive)
    _validate(arrays, header, **pins)
    return arrays, header


@pytest.mark.parametrize("case", ["success", "wrong_identity", "hard_stop"])
def test_native_nov27_capture_to_nov30_input(plan, tmp_path, monkeypatch, case):
    calls = []
    owner_checks = []
    now = CAPTURE_OPENS

    def sleep(seconds):
        nonlocal now
        now += timedelta(seconds=seconds)

    def forbidden(*_args, **_kwargs):
        pytest.fail("real network forbidden")

    def owner_ready():
        owner_checks.append(now)
        return capture.CaptureReadiness(True)

    def parse_input(root, **pins):
        nonlocal now
        parsed = _parse(root, **pins)
        now = INPUT_HARD_STOP if case == "hard_stop" else CAPTURE_CLOSES
        return parsed

    class Response(io.BytesIO):
        status = 200
        headers = {}

        def __init__(self, body):
            super().__init__(json.dumps(body).encode("ascii"))

    class Opener:
        def open(self, request, timeout):
            assert CAPTURE_OPENS <= now < CAPTURE_CLOSES
            assert owner_checks
            url = urlsplit(request.full_url)
            method = request.get_method()
            calls.append(method)
            if method == "POST":
                assert url.path == market.KIS_PAPER_TOKEN_PATH
                return Response({"access_token": "invented-token"})
            assert method == "GET" and url.path == market.KIS_PAPER_DAILY_PATH
            index = len(calls) - 2
            symbol, venue = NET25_H3_AXIS[index]
            assert parse_qs(url.query) == dict(
                SYMB=[symbol], EXCD=[venue], GUBN=["0"], BYMD=["20261127"], MODP=["1"]
            )
            return Response(
                dict(
                    rt_cd="0",
                    output1=dict(
                        rsym="DNASWRONG" if case == "wrong_identity" else f"D{venue}{symbol}"
                    ),
                    output2=[
                        dict(
                            xymd=day.strftime("%Y%m%d"),
                            open=str(10 + index),
                            high=str(13 + index),
                            low=str(9 + index),
                            clos=str(11 + index),
                            tvol="100",
                        )
                        for day in reversed(plan.sessions)
                    ],
                )
            )

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(urllib.request, "build_opener", lambda *_args: Opener())
    monkeypatch.setattr(capture, "_MARKET_BASE", tmp_path / "market")
    monkeypatch.setattr(capture, "_ARTIFACT_BASE", tmp_path / "artifacts")
    root = tmp_path / "input-nov30"
    options = dict(
        market_root=tmp_path / "market/nov27",
        artifact_root=tmp_path / "artifacts/nov27",
        input_root=root,
        data_source_sha256=SOURCE,
        synthetic=True,
        clock=lambda: now,
        owner_ready=owner_ready,
        config_loader=lambda: market.KisPaperMarketDataConfig(
            app_key="invented-key", app_secret="invented-secret"
        ),
        monotonic=lambda: (now - CAPTURE_OPENS).total_seconds(),
        sleeper=sleep,
        prefix_features=_features,
        parse_input=parse_input,
    )
    if case == "wrong_identity":
        with pytest.raises(H3DailyPanelError, match="page_unavailable"):
            produce_nov27_h3_publisher_input_once(**options)
        assert calls == ["POST", "GET"]
        assert not root.exists()
        return
    if case == "hard_stop":
        with pytest.raises(ValueError, match="h3_publisher_outside_window"):
            produce_nov27_h3_publisher_input_once(**options)
        assert calls == ["POST"] + ["GET"] * 19
        assert not (root / "READY.json").exists()
        return

    produced = produce_nov27_h3_publisher_input_once(**options)
    assert calls == ["POST"] + ["GET"] * 19
    assert produced.input_root == root
    state = produced.capture_state_path
    assert state == options["artifact_root"] / "capture-state.json"
    binding = produced.binding
    assert binding == H3InputBinding(SOURCE, DECISION, INPUT_HARD_STOP, synthetic=True)
    ready_raw = (root / "READY.json").read_bytes()
    assert hashlib.sha256(ready_raw).hexdigest() == produced.ready_sha256
    ready = json.loads(ready_raw)
    assert CAPTURE_OPENS <= datetime.fromisoformat(ready["closed_at"]) < CAPTURE_CLOSES
    assert datetime.fromisoformat(ready["ready_at"]) == CAPTURE_CLOSES
    assert hashlib.sha256(state.read_bytes()).hexdigest() == ready["capture_state_sha256"]

    read = dict(ready_sha256=produced.ready_sha256, validate_input=_validate)
    read_at = DECISION - timedelta(seconds=1)
    read_h3_publisher_input(root, state, binding=binding, clock=lambda: read_at, **read)
    with pytest.raises(ValueError, match="ready_binding_mismatch"):
        read_h3_publisher_input(
            root,
            state,
            binding=replace(binding, source_sha256="0" * 64),
            clock=lambda: read_at,
            **read,
        )
    with pytest.raises(ValueError, match="read_clock_mismatch"):
        read_h3_publisher_input(root, state, binding=binding, clock=lambda: DECISION, **read)
    state.write_bytes(b"substituted invented capture state")
    with pytest.raises(ValueError, match="member_digest_mismatch"):
        read_h3_publisher_input(root, state, binding=binding, clock=lambda: read_at, **read)
