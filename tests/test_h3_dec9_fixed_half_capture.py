from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from thericher_v2.data import kis_paper_h3_capture as native_capture
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
        registrations=[],
        native_start=birth,
        change_state=lambda state: None,
        state_path=run / "capture/capture-state.json",
        first_page=pins.market_root / "GET-000001.native.json",
    )
    monkeypatch.setattr(producer, "process_start", lambda _pid: box.native_start)
    prebind = pins.prebind_sha256

    def create(role, path):
        path.mkdir()
        box.registrations.append(role)
        return True

    def native(plan, create_child, verify_roots):
        box.calls += 1
        assert attempt.is_file() and not closure.exists()
        assert not pins.market_root.exists() and not box.state_path.parent.exists()
        for path in (pins.market_root, box.state_path.parent):
            assert create_child(path) is True
        verify_roots()
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
            create_root=create,
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
    assert launch.registrations == ["run", "market", "capture"]
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
    def native(*args):
        if fault == "pending":
            launch.change_state = lambda state: state.update(pending={"method": "GET"})
        result = launch.native(*args)
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
            create_root=lambda *_: pytest.fail("creation called on denied entry"),
            config_loader=lambda: pytest.fail("config loaded on denied entry"),
        )
    assert not launch.run.exists()
    assert not launch.pins.market_root.exists()


@pytest.mark.parametrize("fault", ["owner", "deadline"])
def test_owner_entry_rechecks_before_loading_config(launch, monkeypatch, fault):
    def native(**kwargs):
        assert (launch.run / "owner/ATTEMPT.json").is_file()
        assert kwargs["owner_ready"]().ready
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
            create_root=lambda _, path: path.mkdir() is None,
            config_loader=lambda: pytest.fail("config loaded after loss of authority"),
        )

    monkeypatch.setattr(entry, "capture_h3_daily_panel_once", native)
    with pytest.raises(ValueError, match="dec9_owner_config_denied"):
        run()
    assert not launch.closure.exists()
    launch.now, launch.ready = _OPENS, True
    with pytest.raises(ValueError, match="dec9_capture_fresh_scope"):
        run()


@pytest.mark.parametrize("fault", ["missing", "deny", "truthy", "exception"])
def test_run_registration_fails_before_attempt(launch, fault):
    def create(role, path):
        assert role == "run" and path == launch.run
        path.mkdir()
        if fault == "exception":
            raise RuntimeError("invented internal detail")
        return 1 if fault == "truthy" else False

    with pytest.raises(ValueError, match="^dec9_capture_root_(registration|changed)$"):
        launch.write(create_root=None if fault == "missing" else create)
    assert launch.calls == 0
    assert launch.run.exists() is (fault != "missing")
    assert not (launch.run / "owner").exists()


@pytest.mark.parametrize("fault", ["market", "capture", "replace_run"])
def test_child_denial_or_drift_blocks_native_session_entry(launch, monkeypatch, fault):
    def create(role, path):
        path.mkdir()
        if role == fault:
            return False
        if role == "capture" and fault == "replace_run":
            replaced = launch.run
            replaced.rename(replaced.with_name(f"moved-{replaced.name}"))
            replaced.mkdir()
        return True

    def forbidden(*args, **kwargs):
        pytest.fail("native session or config entered without all roots bound")

    monkeypatch.setattr(native_capture, "KisPaperDataCaptureSession", forbidden)
    with pytest.raises(ValueError, match="^dec9_capture_root_(registration|changed)$"):
        entry.run_dec9_target_owner(
            launch.pins,
            prebind_sha256=launch.prebind,
            clock=lambda: launch.now,
            owner_ready=lambda: CaptureReadiness(True),
            create_root=create,
            config_loader=forbidden,
        )
    assert not launch.closure.exists()


def test_unreported_children_cannot_seal(launch):
    def native(plan, _create_child, verify_roots):
        return launch.native(plan, lambda path: path.mkdir() is None, verify_roots)

    with pytest.raises(ValueError, match="^dec9_capture_root_registration$"):
        launch.write(capture_once=native)
    assert launch.registrations == ["run"]
    assert not launch.closure.exists()


def test_returned_capture_can_seal_at_capture_cutoff(launch):
    def native(*args):
        result = launch.native(*args)
        assert result.closed_at < launch.pins.capture_closes
        launch.now = launch.pins.capture_closes
        return result

    digest = launch.write(capture_once=native)
    assert _sha(launch.closure.read_bytes()) == digest
    assert launch.registrations == ["run", "market", "capture"]
