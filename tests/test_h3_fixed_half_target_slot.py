import os
from dataclasses import asdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_h3_nov30_run import owned_data  # noqa: F401
from thericher_v2.ops import h3_fixed_half_target_slot as slot
from thericher_v2.ops import h3_nov30_run
from thericher_v2.research.prospective_h3_target_custody import write_nov30_h3_target_custody

_TICK = timedelta(microseconds=1)
_OLD_FORECAST_SOURCE = "6cef92fda598c0f1f9aada60ca7a49b80ce50bb8f8b323129cc2db3144629c24"


@pytest.fixture
def edition(tmp_path, monkeypatch):
    data = tmp_path / "data"
    market = tmp_path / "native"
    forecast_root = tmp_path / "forecast"
    monkeypatch.setattr(slot, "_DATA", data)
    monkeypatch.setattr(slot, "_MARKET", market)
    monkeypatch.setattr(slot, "_FORECAST", forecast_root)
    source = data / "source/SOURCE.json"
    source.parent.mkdir(parents=True)
    source.write_bytes(b'{"invented_source":true}')
    monkeypatch.setattr(slot, "_SOURCE", slot._sha(source.read_bytes()))
    pins = slot._pins()
    monkeypatch.setattr(slot, "_PREBIND", pins.prebind_sha256)
    prebind = data / "TARGET-PREBIND.json"
    prebind.write_bytes(
        slot._json(
            dict(
                prebound_at=pins.prebound_at.isoformat(),
                source_sha256=pins.source_sha256,
                target_prebind_sha256=pins.prebind_sha256,
            )
        )
    )
    monkeypatch.setattr(slot, "_PREBIND_FILE", slot._sha(prebind.read_bytes()))
    root = data / "run"
    attempt_root = root / "owner"
    attempt_root.mkdir(parents=True)
    pins.artifact_root.mkdir()
    market.mkdir()
    forecast_root.mkdir()
    page_rows = {}
    plan = slot.H3DailyPanelPlan(slot.NET25_H3_AXIS, slot.INTERVAL.expiry)
    for n, query in enumerate(plan.queries, 1):
        path = market / f"GET-{n:06d}.native.json"
        page_rows[path] = (
            query,
            [
                dict(
                    xymd=day.strftime("%Y%m%d"),
                    open=str(100 + n + i),
                    high=str(102 + n + i),
                    low=str(99 + n + i),
                    clos=str(101 + n + i),
                    tvol="1234",
                )
                for i, day in enumerate(reversed(plan.sessions))
            ],
        )
    started = slot.CAPTURE_OPENS_UTC
    capture_closed = slot.CAPTURE_CLOSES_UTC - _TICK
    sealed = slot.CAPTURE_CLOSES_UTC
    attempt = dict(
        schema="H3_DEC3_DATA_ATTEMPT_V1",
        owner=pins.owner,
        launch_attempt_sha256=pins.attempt_sha256,
        source_sha256=pins.source_sha256,
        target_prebind_sha256=pins.prebind_sha256,
        synthetic=False,
        pid=12345,
        started_at=started.isoformat(),
        roots=[
            str(p)
            for p in (market, pins.artifact_root, root / "input", root / "point", attempt_root)
        ],
    )
    forecast = dict(
        schema="H3_NOV30_FORECAST_OWNER_CLOSED_V1",
        source=slot._FORECAST_SOURCE,
        data_owner_sha256="b" * 64,
        ready_sha256="c" * 64,
        seal_sha256="d" * 64,
        closed_at=slot._FORECAST_OPENS.isoformat(),
    )
    forecast_path = forecast_root / "OWNER-CLOSED.json"
    attempt_path = attempt_root / "ATTEMPT.json"
    pin_path = attempt_root / "TARGET-PIN.json"
    owner_path = root / "OWNER-CLOSED.json"
    state_path = pins.artifact_root / "capture-state.json"
    custody_path = pins.target_root / "TARGET-CUSTODY.json"
    owner = dict(
        schema="H3_DEC3_OWNER_CLOSED_V1",
        source_sha256=pins.source_sha256,
        native_start=f"win-filetime:{slot._ticks(started)}",
        closed_at=(sealed + _TICK).isoformat(),
        ready_sha256="a" * 64,
        target_status="pinned",
    )
    pin_changes = {}
    box = SimpleNamespace(
        root=root,
        forecast=forecast,
        forecast_path=forecast_path,
        attempt=attempt,
        attempt_path=attempt_path,
        owner=owner,
        owner_path=owner_path,
        pin=pin_path,
        pages=page_rows,
        now=slot.RELEASE_AT,
        source=source,
        prebind=prebind,
        pin_changes=pin_changes,
        custody=custody_path,
    )

    def flush():
        completed = {}
        for path, (query, rows) in page_rows.items():
            raw = slot._json(rows)
            path.write_bytes(raw)
            completed[query.key] = asdict(
                slot.CaptureResult(
                    query.key,
                    "ACCEPTED",
                    row_count=len(rows),
                    native=dict(path=str(path), sha256=slot._sha(raw)),
                    raw=dict(path="not-read", sha256="e" * 64),
                )
            )
        state_path.write_bytes(
            slot._json(
                dict(
                    version="kis-paper-data-capture-v1",
                    GET=19,
                    POST=1,
                    retry=0,
                    pending=None,
                    started_utc=started.isoformat(),
                    failed_attempts=[],
                    completed=completed,
                    contract=dict(
                        market_root=str(market),
                        artifact_root=str(pins.artifact_root),
                        queries=[q.document() for q in plan.queries],
                    ),
                )
            )
        )
        state_digest = slot._sha(state_path.read_bytes())
        attempt_path.write_bytes(slot._json(attempt))
        owner["attempt_sha256"] = slot._sha(attempt_path.read_bytes())
        if custody_path.exists():
            custody_path.unlink()
            pins.target_root.rmdir()
        owner["target_custody_sha256"] = write_nov30_h3_target_custody(
            pins,
            prebind_sha256=pins.prebind_sha256,
            capture_state_sha256=state_digest,
            capture_closed_at=capture_closed,
            clock=lambda: sealed,
        )
        pin_path.write_bytes(
            slot._json(
                dict(
                    schema="H3_DEC3_TARGET_PIN_V1",
                    attempt_record_sha256=owner["attempt_sha256"],
                    prebind_sha256=pins.prebind_sha256,
                    capture_state_sha256=state_digest,
                    capture_closed_at=capture_closed.isoformat(),
                    target_custody_sha256=owner["target_custody_sha256"],
                )
                | pin_changes
            )
        )
        owner_path.write_bytes(slot._json(owner))
        forecast_path.write_bytes(slot._json(forecast))
        box.owner_digest = slot._sha(owner_path.read_bytes())
        box.forecast_digest = slot._sha(forecast_path.read_bytes())

    def read(**options):
        return slot.read_nov30_fixed_half_target_slot(
            **(
                dict(
                    data_owner_sha256=box.owner_digest,
                    forecast_owner_sha256=box.forecast_digest,
                    reader_ready=lambda: True,
                    clock=lambda: box.now,
                )
                | options
            )
        )

    flush()
    box.read = read
    box.flush = flush
    return box


def test_real_custody_and_original_pages_to_typed_first_slot(edition, monkeypatch):
    accesses = []
    native = slot._read_native

    def spy(root, reference):
        accesses.append(Path(reference))
        return native(root, reference)

    monkeypatch.setattr(slot, "_read_native", spy)
    marks = edition.read()
    assert type(marks) is slot.ProspectiveH3Marks
    assert marks.sessions == tuple(
        date.fromisoformat(day) for day in ("2026-11-30", "2026-12-01", "2026-12-02", "2026-12-03")
    )
    assert marks.symbols == tuple(symbol for symbol, _ in slot.NET25_H3_AXIS[:17])
    assert tuple(row[0] for row in marks.opens) == tuple(map(Decimal, (104, 103, 102, 101)))
    assert tuple(row[-1] for row in marks.closes) == tuple(map(Decimal, (121, 120, 119)))
    assert [path for path in accesses if path.parent == next(iter(edition.pages)).parent] == list(
        edition.pages
    )
    assert all(path.name not in ("SEAL.json", "READY.json", "DATA-READY.json") for path in accesses)


def test_repaired_forecast_producer_closure_feeds_original_slot(
    edition, owned_data, monkeypatch  # noqa: F811
):
    calls = []

    def forward(name, pin, fit, arrays):
        calls.append(name)
        return {str(key): 0.0 for key in arrays["key"]}

    monkeypatch.setattr(h3_nov30_run, "make_nov30_h3_forward", lambda **_: forward)
    monkeypatch.setattr(h3_nov30_run, "_MEMBERS", {})
    edition.forecast_path.unlink()
    edition.forecast_path.parent.rmdir()
    seal = h3_nov30_run.run_nov30_forecast(
        owned_data.data,
        edition.forecast_path.parent,
        forecast_pin=slot._FORECAST_SOURCE,
        clock=lambda: h3_nov30_run.OPENS,
        validate_input=owned_data.validate,
    )
    assert calls == ["SELF", "OLD60"]
    raw = edition.forecast_path.read_bytes()
    assert slot._document(raw)["seal_sha256"] == seal
    assert edition.read(forecast_owner_sha256=slot._sha(raw)).sessions[0] == slot.INTERVAL.entry


@pytest.mark.parametrize("fault", ["early", "naive", "not_ready"])
def test_denies_before_path_access(edition, monkeypatch, fault):
    if fault == "early":
        edition.now -= _TICK
    if fault == "naive":
        edition.now = edition.now.replace(tzinfo=None)

    def forbidden(*_):
        pytest.fail("visited a path before release and reader admission")

    monkeypatch.setattr(slot, "_fingerprint", forbidden)
    with pytest.raises(ValueError, match="read_denied"):
        edition.read(reader_ready=lambda: fault != "not_ready")


@pytest.mark.parametrize(
    ("part", "key", "value", "error"),
    [
        ("forecast", "closed_at", slot._FORECAST_CUTOFF.isoformat(), "forecast"),
        ("forecast", "source", "0" * 64, "forecast"),
        ("forecast", "source", _OLD_FORECAST_SOURCE, "forecast"),
        ("owner", "target_status", "pin_failed", "data_owner"),
        ("owner", "closed_at", slot.INPUT_HARD_STOP_UTC.isoformat(), "attempt"),
        ("owner", "closed_at", (slot.CAPTURE_CLOSES_UTC - _TICK).isoformat(), "capture_clock"),
        ("attempt", "target_prebind_sha256", "0" * 64, "attempt"),
        ("pin_changes", "attempt_record_sha256", "0" * 64, "target_pin"),
    ],
)
def test_resealed_wrong_metadata_withholds_page_reads(
    edition, monkeypatch, part, key, value, error
):
    getattr(edition, part)[key] = value
    edition.flush()
    native = slot._read_native

    def spy(root, reference):
        assert Path(reference) not in edition.pages
        return native(root, reference)

    monkeypatch.setattr(slot, "_read_native", spy)
    with pytest.raises(ValueError, match=error):
        edition.read()


@pytest.mark.parametrize(
    "which", ["owner_path", "forecast_path", "attempt_path", "prebind", "source"]
)
def test_exact_metadata_digests_cannot_be_self_pinned(edition, which):
    path = getattr(edition, which)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="member_digest"):
        edition.read()


def test_custody_hash_must_match_the_owner_attestation(edition):
    edition.custody.write_bytes(edition.custody.read_bytes() + b" ")
    with pytest.raises(ValueError, match="h3_target_seal_digest_mismatch"):
        edition.read()


def test_page_digest_and_native_row_contract_are_distinct(edition):
    path = next(iter(edition.pages))
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="member_digest"):
        edition.read()
    edition.pages[path][1][0]["xymd"] = edition.pages[path][1][1]["xymd"]
    edition.flush()
    with pytest.raises(ValueError, match="duplicate_session"):
        edition.read()


def test_one_page_changing_after_its_read_withholds_result(edition, monkeypatch):
    first, *_, last = edition.pages
    native = slot._read_native

    def move_clock(root, reference):
        raw = native(root, reference)
        if Path(reference) == last:
            stat = first.stat()
            os.utime(first, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        return raw

    monkeypatch.setattr(slot, "_read_native", move_clock)
    with pytest.raises(ValueError, match="member_changed"):
        edition.read()


def test_native_hardlink_alias_refused_even_with_matching_bytes(edition):
    path = next(iter(edition.pages))
    twin = path.with_suffix(".twin")
    os.link(path, twin)
    try:
        with pytest.raises(ValueError, match="hardlink"):
            edition.read()
    finally:
        twin.unlink()
