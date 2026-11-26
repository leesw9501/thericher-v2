from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from thericher_v2.data.kis_paper_h3_capture import H3DailyCapture
from thericher_v2.data.kis_paper_h3_daily_panel import qualify_h3_daily_panel
from thericher_v2.execution.kis_paper_data_capture import CaptureReadiness, CaptureResult
from thericher_v2.ops import h3_dec9_fixed_half_capture as producer
from thericher_v2.ops import h3_dec9_fixed_half_target as target
from thericher_v2.ops import h3_dec9_target_owner as entry
from thericher_v2.research.prospective_h3_target_custody import _json, _sha

_TICK = timedelta(microseconds=1)
_OPENS = datetime(2026, 12, 9, 21, 30, tzinfo=UTC)


@pytest.fixture
def launch(tmp_path, monkeypatch):
    data = tmp_path / "data"
    source = data / "source/SOURCE.json"
    source.parent.mkdir(parents=True)
    raw_source = _json({"invented_source": True})
    source.write_bytes(raw_source)
    pins = target.Dec9TargetPins(
        owner="invented-dec9",
        source_sha256=_sha(raw_source),
        attempt_sha256="a" * 64,
        data_root=data,
        market_root=tmp_path / "market",
        prebound_at=target.ENTRY_OPEN - _TICK,
        capture_opens=_OPENS,
        capture_closes=_OPENS + timedelta(minutes=10),
        seal_before=_OPENS + timedelta(minutes=15),
    )
    run = data / "run"
    attempt = run / "owner/ATTEMPT.json"
    closure = run / "OWNER-CLOSED.json"
    birth = f"win-filetime:{target._ticks(_OPENS)}"
    box = SimpleNamespace(
        now=_OPENS,
        pins=pins,
        run=run,
        closure=closure,
        ready=True,
        calls=0,
        native_start=birth,
        change_state=lambda state: None,
        state_path=run / "capture/capture-state.json",
        first_page=pins.market_root / "GET-000001.native.json",
    )
    monkeypatch.setattr(producer, "process_start", lambda _pid: box.native_start)
    prebind = pins.prebind_sha256

    def native(plan):
        box.calls += 1
        assert attempt.is_file() and not closure.exists()
        assert not pins.market_root.exists() and not box.state_path.parent.exists()
        box.state_path.parent.mkdir()
        pins.market_root.mkdir()
        started = box.now
        completed, captures = {}, []
        for col, query in enumerate(plan.queries, 1):
            path = pins.market_root / f"GET-{col:06d}.native.json"
            raw = _json(
                [
                    dict(
                        xymd=day.strftime("%Y%m%d"),
                        open=str(100 + i + col),
                        high="1000",
                        low="1",
                        clos=str(101 + i + col),
                        tvol="1",
                    )
                    for i, day in reversed(tuple(enumerate(plan.sessions)))
                ]
            )
            path.write_bytes(raw)
            ref = dict(path=str(path), sha256=_sha(raw))
            n = len(plan.sessions)
            captures.append((CaptureResult(query.key, "ACCEPTED", row_count=n, native=ref), raw))
            completed[query.key] = dict(
                query_key=query.key,
                status="ACCEPTED",
                cache_hit=False,
                reason=None,
                row_count=n,
                native=ref,
            )
        state = dict(
            version="kis-paper-data-capture-v1",
            contract=dict(
                market_root=str(pins.market_root),
                artifact_root=str(box.state_path.parent),
                queries=[query.document() for query in plan.queries],
            ),
            GET=19,
            POST=1,
            retry=0,
            pending=None,
            failed_attempts=[],
            started_utc=started.isoformat(),
            completed=completed,
        )
        box.change_state(state)
        state_raw = _json(state)
        box.state_path.write_bytes(state_raw)
        box.now += _TICK
        return H3DailyCapture(qualify_h3_daily_panel(plan, captures), _sha(state_raw), box.now)

    def write(**changes):
        options = dict(
            prebind_sha256=prebind,
            capture_once=native,
            owner_ready=lambda: box.ready,
            clock=lambda: box.now,
        )
        return producer.write_dec9_fixed_half_capture(pins, **(options | changes))

    box.write, box.native, box.prebind, box.birth = write, native, prebind, birth
    return box


def test_metadata_surround_round_trips_without_opening_pages(launch, monkeypatch):
    bounded = target._bounded_read
    visited = []

    def track(path, *args):
        visited.append(path.name)
        return bounded(path, *args)

    monkeypatch.setattr(target, "_bounded_read", track)
    digest = launch.write()
    assert launch.calls == 1 and _sha(launch.closure.read_bytes()) == digest
    assert set(visited) == {
        "SOURCE.json",
        "ATTEMPT.json",
        "capture-state.json",
        "TARGET-CUSTODY.json",
        "TARGET-PIN.json",
        "OWNER-CLOSED.json",
    }

    def read(closure):
        return target.read_dec9_fixed_half_target(
            launch.pins,
            prebind_sha256=launch.prebind,
            data_owner_sha256=digest,
            data_owner_closed=closure,
            reader_ready=lambda: True,
            clock=lambda: launch.pins.release_at,
        )

    with pytest.raises(ValueError, match="dec9_target_owner_not_closed"):
        read(lambda *args: False)
    closed = target._document(launch.closure.read_bytes())
    attempt = target._document((launch.run / "owner/ATTEMPT.json").read_bytes())
    assert closed["native_start"] == launch.birth
    marks = read(lambda *args: args == (attempt["pid"], launch.birth, digest))
    assert len(marks.opens) == 4 and len(marks.closes) == 3
    assert marks.opens[0][0] == 157 and marks.closes[-1][0] == 160
    with pytest.raises(ValueError, match="dec9_capture_fresh_scope"):
        launch.write()
    assert launch.calls == 1


@pytest.mark.parametrize("fault", ["prebind", "early", "late", "owner", "birth", "source"])
def test_preflight_denial_leaves_no_attempt(launch, fault):
    options = {}
    if fault == "prebind":
        options["prebind_sha256"] = "f" * 64
    elif fault == "early":
        launch.now -= _TICK
    elif fault == "late":
        launch.now = launch.pins.capture_closes
    elif fault == "owner":
        launch.ready = 1
    elif fault == "birth":
        launch.native_start = f"win-filetime:{target._ticks(_OPENS - _TICK)}"
    else:
        (launch.pins.data_root / "source/SOURCE.json").write_bytes(b"changed")
    with pytest.raises(ValueError, match="dec9_capture_"):
        launch.write(**options)
    assert launch.calls == 0 and not launch.run.exists()


@pytest.mark.parametrize(
    ("fault", "error"),
    [
        ("pending", "dec9_target_capture_contract"),
        ("stale_digest", "dec9_capture_digest"),
        ("closed_late", "dec9_capture_result"),
        ("clock_backwards", "dec9_capture_clock"),
        ("owner_lost", "dec9_capture_owner"),
        ("lock", "dec9_capture_membership"),
        ("missing_page", "dec9_capture_membership"),
    ],
)
def test_incomplete_capture_consumes_attempt_without_closure(launch, fault, error):
    def native(plan):
        if fault == "pending":
            launch.change_state = lambda state: state.update(pending={"method": "GET"})
        result = launch.native(plan)
        if fault == "stale_digest":
            launch.state_path.write_bytes(b"changed")
        elif fault == "closed_late":
            launch.now = launch.pins.capture_closes
            result = replace(result, closed_at=launch.now)
        elif fault == "clock_backwards":
            launch.now = _OPENS - _TICK
        elif fault == "owner_lost":
            launch.native_start = None
        elif fault == "lock":
            (launch.pins.market_root / "owner.lock.d").mkdir()
        elif fault == "missing_page":
            launch.first_page.unlink()
        return result

    with pytest.raises(ValueError, match=error):
        launch.write(capture_once=native)
    assert launch.calls == 1
    assert (launch.run / "owner/ATTEMPT.json").is_file() and not launch.closure.exists()
    assert not (launch.run / "target").exists()


def test_state_mutation_during_pin_readback_withholds_closure(launch, monkeypatch):
    bounded = target._bounded_read

    def mutate(path, *args):
        raw = bounded(path, *args)
        if path.name == "TARGET-PIN.json":
            launch.state_path.write_bytes(b"changed")
        return raw

    monkeypatch.setattr(target, "_bounded_read", mutate)
    with pytest.raises(ValueError, match="dec9_capture_digest"):
        launch.write()
    assert not launch.closure.exists()


def test_late_completion_readback_never_returns_authority(launch, monkeypatch):
    bounded = target._bounded_read

    def late(path, *args):
        raw = bounded(path, *args)
        if path == launch.closure:
            launch.now = launch.pins.seal_before
        return raw

    monkeypatch.setattr(target, "_bounded_read", late)
    with pytest.raises(ValueError, match="dec9_capture_clock"):
        launch.write()
    assert launch.closure.is_file()
    launch.now = _OPENS
    with pytest.raises(ValueError, match="dec9_capture_fresh_scope"):
        launch.write()
    assert launch.calls == 1


@pytest.mark.parametrize("fault", ["early", "prebind", "owner", "truthy"])
def test_owner_entry_denies_before_native_capture(launch, monkeypatch, fault):
    def forbidden(**_kwargs):
        pytest.fail("native capture called on denied entry")

    monkeypatch.setattr(entry, "capture_h3_daily_panel_once", forbidden)
    if fault == "early":
        launch.now -= _TICK
    readiness = True if fault == "truthy" else CaptureReadiness(fault != "owner")
    with pytest.raises(ValueError, match="dec9_capture_(clock|prebind|owner)"):
        entry.run_dec9_target_owner(
            launch.pins,
            prebind_sha256="f" * 64 if fault == "prebind" else launch.prebind,
            clock=lambda: launch.now,
            owner_ready=lambda: readiness,
            config_loader=lambda: pytest.fail("config loaded on denied entry"),
        )
    assert not launch.run.exists()
    assert not launch.pins.market_root.exists()


@pytest.mark.parametrize("fault", ["owner", "deadline"])
def test_owner_entry_rechecks_before_loading_config(launch, monkeypatch, fault):
    def native(**kwargs):
        assert (launch.run / "owner/ATTEMPT.json").is_file()
        assert kwargs["owner_ready"] is ready
        assert kwargs["private_roots"] is True
        if fault == "owner":
            launch.ready = False
        else:
            launch.now = launch.pins.capture_closes
        kwargs["config_loader"]()
        pytest.fail("denied config load returned")

    def ready():
        return CaptureReadiness(launch.ready)

    def run():
        return entry.run_dec9_target_owner(
            launch.pins,
            prebind_sha256=launch.prebind,
            clock=lambda: launch.now,
            owner_ready=ready,
            config_loader=lambda: pytest.fail("config loaded after loss of authority"),
        )

    monkeypatch.setattr(entry, "capture_h3_daily_panel_once", native)
    with pytest.raises(ValueError, match="dec9_owner_config_denied"):
        run()
    assert not launch.closure.exists()
    launch.now, launch.ready = _OPENS, True
    with pytest.raises(ValueError, match="dec9_capture_fresh_scope"):
        run()
