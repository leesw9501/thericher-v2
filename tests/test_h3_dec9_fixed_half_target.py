import json
import os
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from fractions import Fraction
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from test_h3_fixed_half_dec4_contract_readiness import _invented_forecast
from thericher_v2.execution import kis_market_data as market
from thericher_v2.execution import kis_paper_data_capture as capture
from thericher_v2.ops import h3_dec9_fixed_half_capture as sealer
from thericher_v2.ops import h3_dec9_fixed_half_target as target
from thericher_v2.ops.h3_dec9_target_owner import run_dec9_target_owner
from thericher_v2.ops.h3_fixed_half_block_readout import (
    H3BlockReadoutError,
    H3SlotReaderBinding,
    H3SlotReadiness,
    read_h3_fixed_half_block,
)
from thericher_v2.research.prospective_h3_block import reduce_prospective_h3_block

_TICK = timedelta(microseconds=1)
_OPENS = datetime(2026, 12, 9, 21, 30, tzinfo=UTC)


def _write(path, doc):
    raw = target._json(doc)
    path.write_bytes(raw)
    return target._sha(raw)


@pytest.fixture
def edition(tmp_path, monkeypatch):
    data = tmp_path / "artifacts/dec9"
    source = data / "source/SOURCE.json"
    source.parent.mkdir(parents=True)
    source_sha = _write(source, {"invented_source": True})
    pins = target.Dec9TargetPins(
        owner="invented-dec9-owner",
        source_sha256=source_sha,
        attempt_sha256="b" * 64,
        data_root=data,
        market_root=tmp_path / "market/dec9",
        prebound_at=target.ENTRY_OPEN - _TICK,
        capture_opens=_OPENS,
        capture_closes=_OPENS + timedelta(minutes=10),
        seal_before=_OPENS + timedelta(minutes=15),
    )
    initial_digest = pins.prebind_sha256
    run = data / "run"
    artifact, owner, custody = (run / name for name in ("capture", "owner", "target"))
    tape = target.H3DailyPanelPlan(target.NET25_H3_AXIS, target.INTERVAL.expiry)
    now = _OPENS
    calls = []
    config_loads = []

    class Response:
        status = 200
        headers = {}

        def __init__(self, doc):
            self.body = json.dumps(doc).encode("ascii")

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
            col = len(calls) - 2
            symbol, venue = tape.axis[col]
            assert parse_qs(url.query) == dict(
                SYMB=[symbol], EXCD=[venue], GUBN=["0"], BYMD=["20261209"], MODP=["1"]
            )
            return Response(
                dict(
                    rt_cd="0",
                    output1=dict(rsym=f"D{venue}{symbol}"),
                    output2=[
                        dict(
                            xymd=day.strftime("%Y%m%d"),
                            open=str(100 + i + col),
                            high="1000",
                            low="1",
                            clos=str(101 + i + col),
                            tvol="1",
                        )
                        for i, day in reversed(tuple(enumerate(tape.sessions)))
                    ],
                )
            )

    def no_network(*_args, **_kwargs):
        pytest.fail("real network forbidden")

    def advance(seconds):
        nonlocal now
        now += timedelta(seconds=seconds)

    def config_loader():
        assert (owner / "ATTEMPT.json").is_file() and not calls
        config_loads.append(True)
        return market.KisPaperMarketDataConfig(app_key="invented-key", app_secret="invented-secret")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(urllib.request, "build_opener", lambda *_: Opener())
    monkeypatch.setattr(capture, "_MARKET_BASE", tmp_path / "market")
    monkeypatch.setattr(capture, "_ARTIFACT_BASE", tmp_path / "artifacts")
    birth = f"win-filetime:{target._ticks(_OPENS)}"
    monkeypatch.setattr(sealer, "process_start", lambda pid: birth if pid == os.getpid() else None)
    owner_digest = run_dec9_target_owner(
        pins,
        prebind_sha256=initial_digest,
        clock=lambda: now,
        owner_ready=lambda: capture.CaptureReadiness(True),
        config_loader=config_loader,
        monotonic=lambda: (now - _OPENS).total_seconds(),
        sleeper=advance,
    )
    assert config_loads == [True] and calls == ["POST"] + ["GET"] * 19
    closure = run / "OWNER-CLOSED.json"
    assert target._sha(closure.read_bytes()) == owner_digest
    a = json.loads((owner / "ATTEMPT.json").read_bytes())
    s = json.loads((custody / "TARGET-CUSTODY.json").read_bytes())
    c = json.loads(closure.read_bytes())
    box = SimpleNamespace(
        pins=pins,
        prebind=initial_digest,
        owner_digest=owner_digest,
        attempt=a,
        seal=s,
        closure=c,
        now=pins.release_at,
        owner=owner,
        source=source,
        capture_state=artifact / "capture-state.json",
        pages=tuple(sorted(pins.market_root.glob("*.native.json"))),
        calls=calls,
    )

    def flush():
        c["attempt_sha256"] = _write(owner / "ATTEMPT.json", a)
        c["target_custody_sha256"] = _write(custody / "TARGET-CUSTODY.json", s)
        _write(
            owner / "TARGET-PIN.json",
            dict(
                schema="H3_DEC9_TARGET_PIN_V1",
                attempt_record_sha256=c["attempt_sha256"],
                prebind_sha256=initial_digest,
                capture_state_sha256=s["capture_state_sha256"],
                capture_closed_at=s["capture_closed_at"],
                target_custody_sha256=c["target_custody_sha256"],
            ),
        )
        box.owner_digest = _write(run / "OWNER-CLOSED.json", c)

    def closed(pid, native_start, digest):
        return (pid, native_start, digest) == (os.getpid(), birth, box.owner_digest)

    def options(**changes):
        return (
            dict(
                pins=box.pins,
                prebind_sha256=box.prebind,
                data_owner_sha256=box.owner_digest,
                data_owner_closed=closed,
                reader_ready=lambda: True,
                clock=lambda: box.now,
            )
            | changes
        )

    box.flush, box.options = flush, options
    return box


def test_native_capture_to_frozen_block(edition, monkeypatch):
    visited = []
    read_file = target._bounded_read

    def spy(path, *args):
        visited.append(path)
        return read_file(path, *args)

    monkeypatch.setattr(target, "_bounded_read", spy)
    marks = target.read_dec9_fixed_half_target(**edition.options())
    assert marks.sessions == tuple(date(2026, 12, day) for day in (4, 7, 8, 9))
    assert marks.symbols == _invented_forecast().forecast_symbols
    assert len(marks.opens) == 4 and len(marks.closes) == 3
    assert [p for p in visited if p.parent == edition.pins.market_root] == list(edition.pages) * 2
    assert not any(p.name in {"SEAL.json", "READY.json", "DATA-READY.json"} for p in visited)

    def read(ready):
        return target.evaluate_dec4_with_dec9_target(
            _invented_forecast(), **edition.options(reader_ready=ready)
        )

    def forbidden(_ready):
        pytest.fail("unmeasured slot opened")

    bindings = tuple(
        H3SlotReaderBinding(
            slot.interval, "d" * 64, read if slot.interval == target.INTERVAL else forbidden
        )
        for slot in reduce_prospective_h3_block(()).slots
    )

    def attest(binding):
        if binding.interval == target.INTERVAL:
            return H3SlotReadiness.READY
        return H3SlotReadiness.UNMEASURED

    result = read_h3_fixed_half_block(bindings, attest=attest, clock=lambda: edition.now)
    slot = result.block.slots[1]
    assert slot.status == "scored" and result.block.admitted_count == 1
    assert result.block.comparison is None
    replay = slot.replay
    buy = Fraction(400, 13601)
    sell = buy * Fraction(159, 156)
    assert replay.model.entry_notional == replay.matched_gross_ew.entry_notional == buy
    assert replay.model.exit_notional == sell
    assert replay.model.growth == sell - buy - (buy + sell) / 400
    assert edition.calls == ["POST"] + ["GET"] * 19

    edition.pages[-1].write_bytes(edition.pages[-1].read_bytes() + b" ")
    with pytest.raises(H3BlockReadoutError, match="^h3_block_readout_reader_error$"):
        read_h3_fixed_half_block(bindings, attest=attest, clock=lambda: edition.now)


@pytest.mark.parametrize("fault", ["early", "not_ready", "rewind", "prebind", "entry_open", "late"])
def test_denies_before_any_filesystem_access(edition, monkeypatch, fault):
    def forbidden(*_args, **_kwargs):
        pytest.fail("filesystem accessed before valid admission")

    monkeypatch.setattr(target, "_fingerprint", forbidden)
    if fault == "early":
        options = edition.options(clock=lambda: edition.now - _TICK, reader_ready=forbidden)
    elif fault == "not_ready":
        options = edition.options(reader_ready=lambda: 1)
    elif fault == "rewind":
        times = iter((edition.now, edition.now - _TICK))
        options = edition.options(clock=lambda: next(times))
    elif fault == "prebind":
        options = edition.options(prebind_sha256="0" * 64)
    else:
        when = target.ENTRY_OPEN if fault == "entry_open" else target.ENTRY_OPEN + _TICK
        options = edition.options(pins=replace(edition.pins, prebound_at=when))
    with pytest.raises(ValueError, match="read_denied|prebind|pin_clock"):
        target.read_dec9_fixed_half_target(**options)


@pytest.mark.parametrize(
    "fault", ["closure", "attempt", "seal", "query", "ordinal", "pending", "state_pending"]
)
def test_bad_metadata_denies_before_native_page_reads(edition, monkeypatch, fault):
    options = {}
    if fault == "closure":
        options["data_owner_closed"] = lambda *_: False
    elif fault == "attempt":
        edition.attempt["launch_attempt_sha256"] = "0" * 64
    elif fault == "seal":
        edition.seal["sealed_at"] = edition.pins.seal_before.isoformat()
    elif fault == "pending":
        (edition.owner / "TARGET-PIN.pending").touch()
    elif fault == "state_pending":
        edition.capture_state.with_suffix(".json.pending").touch()
    else:
        state = json.loads(edition.capture_state.read_bytes())
        if fault == "query":
            state["contract"]["queries"].reverse()
        else:
            list(state["completed"].values())[0]["native"]["path"] = str(edition.pages[-1])
        edition.seal["capture_state_sha256"] = _write(edition.capture_state, state)
    edition.flush()
    read_file = target._bounded_read

    def spy(path, *args):
        assert path.parent != edition.pins.market_root
        return read_file(path, *args)

    monkeypatch.setattr(target, "_bounded_read", spy)
    with pytest.raises(ValueError, match="owner_not_closed|attempt|custody|capture_|membership"):
        target.read_dec9_fixed_half_target(**edition.options(**options))


def test_hardlink_alias_refused_even_with_original_page_bytes(edition):
    page = edition.pages[0]
    alias = page.with_suffix(".alias")
    os.link(page, alias)
    try:
        with pytest.raises(ValueError, match="hardlink|dec9_target_path"):
            target.read_dec9_fixed_half_target(**edition.options())
    finally:
        alias.unlink()


@pytest.mark.parametrize("fault", ["bytes", "mtime", "membership"])
def test_late_mutation_withholds_marks(edition, monkeypatch, fault):
    first, *_, last = edition.pages
    read_file = target._bounded_read
    touched = False

    def mutate(path, *args):
        nonlocal touched
        raw = read_file(path, *args)
        if path == last and not touched:
            touched = True
            info = first.stat()
            if fault == "bytes":
                first.write_bytes(first.read_bytes().replace(b'"tvol":"1"', b'"tvol":"2"', 1))
                os.utime(first, ns=(info.st_atime_ns, info.st_mtime_ns))
            elif fault == "mtime":
                os.utime(first, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))
            else:
                (edition.pins.market_root / "late").touch()
        return raw

    monkeypatch.setattr(target, "_bounded_read", mutate)
    with pytest.raises(ValueError, match="member_digest|member_changed|membership"):
        target.read_dec9_fixed_half_target(**edition.options())
