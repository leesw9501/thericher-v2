import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.execution import kis_market_data as m
from thericher_v2.execution.kis_stock_intraday_foundation import (
    COHORT,
    FoundationLedger,
    file_ref,
    observed_coverage,
    prior_regular_key,
    run_foundation,
)

SESSIONS = [
    dict(open_utc=f"2026-10-{day}T13:30:00+00:00", close_utc=f"2026-10-{day}T20:00:00+00:00")
    for day in (15, 16)
]
TARGETS = [(s, "NAS") for s in COHORT]


def ledger(tmp_path, normal=40, retry=2):
    return FoundationLedger(
        artifact_root=tmp_path / "a",
        market_root=tmp_path / "m",
        targets=TARGETS,
        sessions=SESSIONS,
        normal_cap=normal,
        retry_cap=retry,
    )


def page(query, empty=False):
    start = datetime.strptime(query.continuation_key or "20261016155900", "%Y%m%d%H%M%S")
    rows = []
    for i in range(0 if empty else 120):
        x = start - timedelta(minutes=i)
        k = x.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(ZoneInfo("Asia/Seoul"))
        rows.append(
            m._parse_minute_bar(
                dict(
                    xymd=x.strftime("%Y%m%d"),
                    xhms=x.strftime("%H%M%S"),
                    kymd=k.strftime("%Y%m%d"),
                    khms=k.strftime("%H%M%S"),
                    open="10",
                    high="12",
                    low="9",
                    last="11",
                    evol="100",
                )
            )
        )
    return m.KisPaperMinutePage(
        query=query,
        bars=tuple(rows),
        next_cursor=None,
        more="",
        continuation_signal="blank_or_absent",
    )


def test_native_ledger_rounds_heads_before_backfill_and_no_repeat(tmp_path):
    job = ledger(tmp_path)
    called = []

    def fetch(q, retry):
        called.append((q.symbol, q.continuation_key))
        job.begin_wire("GET", query=q, retry=retry)
        body = json.dumps({"output2": [b.as_document() for b in page(q).bars]}).encode()
        ref = job.retain_raw(body)
        job.wire_finished()
        return page(q), ref, datetime.now(UTC).isoformat()

    run_foundation(job, fetch, lambda: None, lambda: None, prior_close_key="20261015155900")
    assert called[0] == ("AAPL", "20261015155900")
    assert called[1:21] == [(s, None) for s in COHORT]
    assert len(called) == len(set(called)) == job.state["GET"] == 40
    assert job.state["retry"] == 0
    coverage = observed_coverage(job)
    assert coverage["AAPL"]["regular_labels"] >= 120
    assert not any(v["transfer_ready"] for v in coverage.values())


def test_rth_calendar_jump_and_scope_bound():
    assert prior_regular_key("20261016092900", SESSIONS) == "20261015155900"
    assert prior_regular_key("20261016190000", SESSIONS) == "20261016155900"
    with pytest.raises(ValueError, match="calendar_bound"):
        prior_regular_key("20261015092900", SESSIONS)


def test_caps_pending_resume_and_new_scope_fail_closed(tmp_path):
    job = ledger(tmp_path, normal=1, retry=1)
    q = job.query("AAPL")
    job.begin_wire("GET", query=q)
    with pytest.raises(ValueError, match="pending"):
        ledger(tmp_path, normal=1, retry=1)
    job.wire_finished()
    job.begin_wire("GET", query=q, retry=True)
    job.wire_finished()
    with pytest.raises(ValueError, match="cap"):
        job.begin_wire("GET", query=q, retry=True)
    job.begin_wire("POST", query=None)
    job.wire_finished()
    with pytest.raises(ValueError, match="auth_cap"):
        job.begin_wire("POST", query=None)
    with pytest.raises(ValueError, match="cohort"):
        FoundationLedger(
            artifact_root=tmp_path / "a",
            market_root=tmp_path / "m",
            targets=list(reversed(TARGETS)),
            sessions=SESSIONS,
        )


def test_empty_is_scoped_and_whole_pages_are_immutable(tmp_path):
    job = ledger(tmp_path)
    q = job.query("AAPL", "20261015155900")
    job.begin_wire("GET", query=q)
    raw = job.retain_raw(b'{"output2":[]}')
    job.wire_finished()
    job.accept(q, page(q, empty=True), raw, datetime.now(UTC).isoformat())
    assert job.state["cursors"]["AAPL"]["status"] == "exact_cursor_empty"
    assert job.state["cursors"]["MSFT"]["status"] == "pending_head"
    with pytest.raises(FileExistsError):
        job.retain_raw(b"replacement")
    assert file_ref(__import__("pathlib").Path(raw["path"])) == raw


def test_observed_300_label_coverage_requires_real_contiguous_rows(tmp_path):
    job = ledger(tmp_path)
    q = job.query("AAPL")
    for _ in range(3):
        job.begin_wire("GET", query=q)
        raw = job.retain_raw(b"synthetic-raw")
        job.wire_finished()
        job.accept(q, page(q), raw, datetime.now(UTC).isoformat())
        q = job.query("AAPL", job.state["cursors"]["AAPL"]["key"])
    v = observed_coverage(job)["AAPL"]
    assert v["regular_labels"] == v["longest_contiguous_regular_labels"] == 360
    assert v["label_context300"] and not v["transfer_ready"]
