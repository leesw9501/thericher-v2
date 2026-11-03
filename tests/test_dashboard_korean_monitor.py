"""Synthetic operator-monitor coverage for the KIS Paper execution-learning loop."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

import pytest

from thericher_v2.dashboard import operations as dashboard_operations
from thericher_v2.dashboard.operations import build_operations_snapshot
from thericher_v2.dashboard.view import (
    DashboardSnapshot,
    build_snapshot,
    render_dashboard,
)
from thericher_v2.execution.emergency import EmergencyStore
from thericher_v2.execution.paper_account_snapshot import (
    PaperAccountOrderableForeignFunds,
    PaperAccountReferenceOrderability,
    PaperAccountSnapshot,
)
from thericher_v2.state import EventStore

NOW = datetime(2026, 11, 1, 14, 0, tzinfo=UTC)
POINTERS = {
    "h20": (
        "artifact:execution/current-h20-reader-parent-completion-20261101-v1/"
        "actual-once/RESULT.json"
    ),
    "googl": (
        "artifact:execution/current-us19-unit-reader-binding-repair-20261101-v1/"
        "actual-once/RESULT.json"
    ),
}


@pytest.fixture
def snapshot(tmp_path: Path) -> DashboardSnapshot:
    events = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    events.bootstrap()
    return build_snapshot(events, EmergencyStore(tmp_path / "emergency.json"), now=NOW)


def _operations(**changes: object) -> dict[str, object]:
    run = {
        "key": "h20",
        "label": "H20",
        "symbol": "SPY",
        "entry_due_at": "2026-11-02T15:15:00Z",
        "read_due_at": "2026-11-02T15:35:00Z",
        "exit_due_at": "2026-12-01T14:30:00Z",
        "status": "unknown",
        "submit": "unknown",
        "fill": "unknown",
        "inventory": "unknown",
        "reason_code": "public_evidence_missing",
        "evidence_at": None,
        "evidence_pointer": None,
    }
    run.update(changes)
    return {"observed_at": NOW.isoformat(), "runs": [run]}


def _validated(**changes: object) -> dict[str, object]:
    return _operations(
        **{
            "status": "validated",
            "reason_code": "host_published_public_outcome",
            "evidence_at": NOW.isoformat(),
            "evidence_pointer": POINTERS["h20"],
            **changes,
        }
    )


class _Markup(HTMLParser):
    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[tuple[str, dict[str, str | None]]] = []
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append((tag, dict(attrs)))

    def tags(self, tag: str) -> list[dict[str, str | None]]:
        return [attrs for actual, attrs in self.elements if actual == tag]


def test_optional_operations_contract_does_not_invent_financial_activity(snapshot) -> None:
    assert snapshot.operations_snapshot is None
    assert snapshot.to_dict()["operations_snapshot"] is None
    html = render_dashboard(snapshot)
    assert "TheRicher v2" in html
    assert '<html lang="ko">' in html
    assert "KIS Paper 실행 현황" in html and "source: kis_paper" in html
    assert "로컬 시뮬레이터" in html and "source: local_paper" in html
    assert html.index('id="operations-heading"') < html.index('id="local-heading"')
    assert 'data-run="h20"' in html and 'data-run="googl"' in html
    assert "H20 · SPY" in html and "US19 · GOOGL" in html
    assert "GOOGL · GOOGL" not in html
    assert "미확인 · unknown" in html
    assert "예약 시각 ≠ 제출·체결" in html
    assert "KIS 순손익: 미관측" in html
    assert "Ready" not in html and "realtime" not in html


def test_native_build_snapshot_handoff_is_optional_and_allowlisted(tmp_path) -> None:
    events = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    events.bootstrap()
    supplied = _operations(account_number="DO_NOT_EXPOSE")
    supplied["raw_body"] = "DO_NOT_EXPOSE"
    before = deepcopy(supplied)
    result = build_snapshot(
        events,
        EmergencyStore(tmp_path / "emergency.json"),
        operations_snapshot=supplied,
        now=NOW,
    )
    assert supplied == before
    assert result.operations_snapshot is not supplied
    assert set(result.to_dict()["operations_snapshot"]) == {"observed_at", "runs"}
    assert "DO_NOT_EXPOSE" not in json.dumps(result.to_dict())
    assert "DO_NOT_EXPOSE" not in render_dashboard(result)


def test_empty_runs_keep_a_safe_envelope_with_explicit_unknown_rows(snapshot) -> None:
    result = replace(snapshot, operations_snapshot={"observed_at": NOW.isoformat(), "runs": []})
    operations = result.to_dict()["operations_snapshot"]
    assert operations["observed_at"] == NOW.isoformat()
    assert [run["key"] for run in operations["runs"]] == ["h20", "googl", "h3"]
    assert all(
        run["submit"] == run["fill"] == run["inventory"] == "unknown" for run in operations["runs"]
    )


def test_native_operations_producer_to_snapshot_to_html_without_io(tmp_path, monkeypatch) -> None:
    events = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    events.bootstrap()
    operations = build_operations_snapshot(None, now=NOW)
    result = build_snapshot(
        events,
        EmergencyStore(tmp_path / "emergency.json"),
        operations_snapshot=operations,
        now=NOW,
    )
    monkeypatch.setattr(Path, "open", lambda *a, **k: pytest.fail("unexpected file I/O"))
    html = render_dashboard(result, form_nonce="synthetic-handoff-nonce")
    assert "2026-11-03 00:15 KST" in html and "2026-11-03 00:35 KST" in html
    assert "2026-11-03 05:55 KST" in html and "2026-11-03 06:05 KST" in html
    assert "2026-11-10 05:55 KST" in html
    runs = result.to_dict()["operations_snapshot"]["runs"]
    assert [(row["key"], row["symbol"]) for row in runs] == [
        ("h20", "SPY"), ("googl", "GOOGL"), ("h3", "AMD")
    ]
    assert all(row["submit"] == row["fill"] == row["inventory"] == "unknown" for row in runs)
    assert "synthetic-handoff-nonce" in html


@pytest.mark.parametrize("age_seconds", [0, 301, 86400])
def test_native_public_projection_to_backend_to_view_retains_history(tmp_path, age_seconds) -> None:
    evidence_at = datetime(2026, 11, 2, 21, 6, tzinfo=UTC)
    current = evidence_at + timedelta(seconds=age_seconds)
    public = tmp_path / "public"
    public.mkdir()
    for run in dashboard_operations._RUNS:
        projection = dashboard_operations._projection(run, evidence_at)
        projection.update(
            status="validated",
            submit="accepted",
            fill="confirmed",
            inventory="owned",
            reason_code="host_published_public_outcome",
            evidence_at=evidence_at.isoformat(),
            evidence_pointer=run.evidence_pointer,
            result_sha256="f" * 64,
        )
        (public / f"{run.key}.json").write_text(json.dumps(projection), encoding="utf-8")
    operations = build_operations_snapshot(public, now=current)
    events = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    events.bootstrap()
    result = build_snapshot(
        events,
        EmergencyStore(tmp_path / "emergency.json"),
        operations_snapshot=operations,
        now=current,
    )
    rows = result.to_dict()["operations_snapshot"]["runs"]
    assert len(rows) == 3
    assert rows[-1]["key"] == "h3" and rows[-1]["status"] == "unknown"
    for row in rows[:2]:
        assert row["status"] == "validated"
        assert row["submit"] == "accepted" and row["fill"] == "confirmed"
        assert row["evidence_pointer"] == POINTERS[row["key"]]
        assert row["evidence_at"] == evidence_at.isoformat()
        assert row["inventory"] == ("owned" if age_seconds == 0 else "unknown")
        assert row["reason_code"] == (
            "host_published_public_outcome" if age_seconds == 0 else "historical_public_outcome"
        )
    html = render_dashboard(result)
    assert "기록된 주문 제출" in html and "기록된 연결 체결" in html
    assert "접수 확인" in html and "연결 체결 확인" in html
    assert "2026-11-03 00:15 KST" in html and "2026-12-01 23:30 KST" in html
    if age_seconds:
        assert "과거 공개 판독 결과" in html and "현재 보유 미확인" in html
    assert result.local_paper_fill_count == 0


def test_scheduled_times_are_kst_and_utc_without_implied_submits(snapshot) -> None:
    result = replace(snapshot, operations_snapshot=_operations(status="scheduled"))
    html = render_dashboard(result)
    assert "2026-11-03 00:15 KST" in html and "2026-11-02 15:15 UTC" in html
    assert "2026-11-03 00:35 KST" in html and "2026-12-01 23:30 KST" in html
    assert "진입 시작 · Entry" in html
    assert "결과 판독 · Read trigger" in html and "청산 시작 · Exit" in html
    run = result.to_dict()["operations_snapshot"]["runs"][0]
    assert run["status"] == "scheduled"
    assert run["submit"] == run["fill"] == run["inventory"] == "unknown"
    assert "접수 확인" not in html and "연결 체결 확인" not in html


@pytest.mark.parametrize(
    "field,value,label",
    [
        ("submit", "not_observed", "관측되지 않음"),
        ("submit", "attempted", "제출 시도"),
        ("submit", "accepted", "접수 확인"),
        ("submit", "rejected", "거절 확인"),
        ("fill", "not_observed", "관측되지 않음"),
        ("fill", "confirmed", "연결 체결 확인"),
        ("inventory", "owned", "소유 보유 관측"),
        ("inventory", "flat", "소유 잔고 없음 관측"),
    ],
)
def test_financial_categories_are_distinct_and_evidence_bound(
    snapshot, field, value, label
) -> None:
    result = replace(snapshot, operations_snapshot=_validated(**{field: value}))
    run = result.to_dict()["operations_snapshot"]["runs"][0]
    assert run[field] == value
    assert all(run[other] == "unknown" for other in {"submit", "fill", "inventory"} - {field})
    html = render_dashboard(result)
    assert label in html and POINTERS["h20"] in html
    assert "공개 판독 결과 · 호스트 게시" in html
    assert "현재 재확인 아님" in html


@pytest.mark.parametrize("status", ["scheduled", "unknown", "invalid", "unavailable", "working"])
def test_unvalidated_results_never_promote_financial_claims(snapshot, status) -> None:
    result = replace(
        snapshot,
        operations_snapshot=_validated(
            status=status, submit="accepted", fill="confirmed", inventory="flat"
        ),
    )
    run = result.to_dict()["operations_snapshot"]["runs"][0]
    assert run["submit"] == run["fill"] == run["inventory"] == "unknown"
    assert "접수 확인" not in render_dashboard(result)
    assert "연결 체결 확인" not in render_dashboard(result)


@pytest.mark.parametrize(
    "change",
    [
        {"evidence_at": None},
        {"evidence_at": "2026-11-01T14:01:00Z"},
        {"evidence_pointer": "https://untrusted.example/private"},
        {"evidence_pointer": "artifact:arbitrary/private.json"},
        {"reason_code": "raw-private-account-number"},
        {"reason_code": "public_evidence_withheld"},
    ],
)
def test_missing_or_invalid_evidence_cannot_back_a_fill(snapshot, change) -> None:
    result = replace(snapshot, operations_snapshot=_validated(fill="confirmed", **change))
    run = result.to_dict()["operations_snapshot"]["runs"][0]
    assert run["status"] == "invalid" and run["fill"] == "unknown"
    assert run["reason_code"] == "public_evidence_invalid"
    html = render_dashboard(result)
    assert "실행 담당 점검" in html and "연결 체결 확인" not in html
    assert "untrusted.example" not in html and "raw-private-account-number" not in html


@pytest.mark.parametrize("stale_field", ["observed_at", "evidence_at"])
def test_stale_public_evidence_keeps_pointer_but_not_current_inventory(
    snapshot, stale_field
) -> None:
    operations = _validated(submit="accepted", fill="confirmed", inventory="owned")
    expired = (NOW - timedelta(seconds=301)).isoformat()
    if stale_field == "observed_at":
        operations["observed_at"] = expired
        operations["runs"][0]["evidence_at"] = expired
    else:
        operations["runs"][0]["evidence_at"] = expired
    result = replace(snapshot, operations_snapshot=operations)
    run = result.to_dict()["operations_snapshot"]["runs"][0]
    assert run["status"] == "validated" and run["inventory"] == "unknown"
    assert run["submit"] == "accepted" and run["fill"] == "confirmed"
    assert run["reason_code"] == "historical_public_outcome"
    assert run["evidence_pointer"] == POINTERS["h20"]
    assert "현재 보유 미확인" in render_dashboard(result)


def test_historical_qualifier_cannot_repromote_current_inventory(snapshot) -> None:
    result = replace(
        snapshot,
        operations_snapshot=_validated(
            submit="accepted",
            fill="confirmed",
            inventory="owned",
            reason_code="historical_public_outcome",
        ),
    )
    run = result.to_dict()["operations_snapshot"]["runs"][0]
    assert run["status"] == "validated" and run["inventory"] == "unknown"
    assert run["submit"] == "accepted" and run["fill"] == "confirmed"


def test_expired_unvalidated_values_never_become_immutable_history(snapshot) -> None:
    result = replace(
        snapshot,
        operations_snapshot=_validated(
            status="unknown",
            reason_code="historical_public_outcome",
            submit="accepted",
            fill="confirmed",
            inventory="owned",
        ),
    )
    run = result.to_dict()["operations_snapshot"]["runs"][0]
    assert run["status"] == "unknown"
    assert run["submit"] == run["fill"] == run["inventory"] == "unknown"
    assert run["reason_code"] == "public_evidence_missing"


@pytest.mark.parametrize(
    "operations",
    [
        None,
        [],
        {},
        {"observed_at": NOW.isoformat(), "runs": {}},
        {"observed_at": "2099-01-01T00:00:00Z", "runs": []},
    ],
)
def test_invalid_envelopes_fail_closed(snapshot, operations) -> None:
    result = replace(snapshot, operations_snapshot=operations)
    assert result.to_dict()["operations_snapshot"] is None
    assert "운영 결과 연결 설정 확인" in render_dashboard(result)


@pytest.mark.parametrize(
    "stamp",
    [
        "<script>alert(1)</script>",
        "2026-11-02T15:10:00",
        123,
        [],
        "9999-12-31T23:59:59Z",
        "0001-01-01T00:00:00Z",
    ],
)
def test_malformed_or_naive_dates_are_unknown_not_raw_html(snapshot, stamp) -> None:
    result = replace(snapshot, operations_snapshot=_operations(entry_due_at=stamp))
    run = result.to_dict()["operations_snapshot"]["runs"][0]
    assert run["entry_due_at"] is None
    assert "<script>" not in render_dashboard(result)


def test_duplicate_wrong_symbol_and_extra_runs_do_not_borrow_evidence(snapshot) -> None:
    operations = _validated(fill="confirmed")
    operations["runs"] += [deepcopy(operations["runs"][0]), {"key": "other", "label": "RAW"}]
    result = replace(snapshot, operations_snapshot=operations)
    runs = result.to_dict()["operations_snapshot"]["runs"]
    assert len(runs) == 3 and runs[0]["fill"] == "unknown"
    operations = _validated(symbol="GOOGL", fill="confirmed")
    result = replace(snapshot, operations_snapshot=operations)
    assert result.to_dict()["operations_snapshot"]["runs"][0]["fill"] == "unknown"
    assert "RAW" not in render_dashboard(result)


def test_untrusted_strings_are_removed_and_form_nonce_is_escaped(snapshot) -> None:
    marker = '<img src=x onerror="alert(1)">'
    operations = _operations(
        label=marker,
        status=marker,
        submit=marker,
        fill=marker,
        inventory=marker,
        reason_code=marker,
        evidence_pointer=marker,
    )
    result = replace(snapshot, operations_snapshot=operations, execution_control_reason=marker)
    html = render_dashboard(result, form_nonce='nonce"<&')
    assert marker not in html and marker not in json.dumps(result.to_dict()["operations_snapshot"])
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in html
    assert 'value="nonce&quot;&lt;&amp;"' in html


def test_pause_and_emergency_forms_are_nonce_bound_requests_not_runtime_acks(snapshot) -> None:
    for paused in (False, True):
        result = replace(snapshot, pause_buys=paused, pause_sells=paused, stop_new_orders=paused)
        html = render_dashboard(result, form_nonce="test-nonce")
        markup = _Markup(html)
        expected = "resume" if paused else "pause"
        assert {form["action"] for form in markup.tags("form")} == {
            f"/controls/{expected}-buys",
            f"/controls/{expected}-sells",
            "/emergency/stop-new-orders",
        }
        assert all(form["method"] == "post" for form in markup.tags("form"))
        assert (
            len(
                [
                    i
                    for i in markup.tags("input")
                    if i.get("name") == "csrf" and i.get("value") == "test-nonce"
                ]
            )
            == 3
        )
        assert "실행기 반영: 미확인" in html and "consumer ack unknown" in html
        assert "제어 요청 저장 ≠ 모든 실행기 반영" in html
        assert "정지 완료" not in html
        assert "일시정지 요청 · Paused" in html if paused else "정지 요청 없음" in html
        assert "미확인 주문·예약금은 유지" in html


def test_snapshot_age_and_expiry_do_not_invent_prices_or_pnl(snapshot) -> None:
    account = PaperAccountSnapshot(
        status="complete",
        observed_at=NOW - timedelta(seconds=90),
        expires_at=NOW + timedelta(seconds=210),
        orderable_foreign_funds=PaperAccountOrderableForeignFunds("USD", Decimal("100")),
        reference_orderability=PaperAccountReferenceOrderability(
            "USD", Decimal("100"), "NASD", "SPY"
        ),
    )
    result = replace(
        snapshot,
        paper_account=account,
        paper_account_status="available",
        paper_account_observed_at=account.observed_at.isoformat(),
    )
    html = render_dashboard(result)
    assert "1분 30초 경과" in html
    assert "2026-11-01 22:58 KST" in html and "2026-11-01 13:58 UTC" in html
    assert "유효 기한" in html and "계좌 전체 관측" in html
    assert "not settled cash, account equity" in html
    assert "가격·평가손익·순손익: 미관측" in html


def test_keyboard_tables_and_manual_refresh_need_no_scripts_or_external_assets(snapshot) -> None:
    html = render_dashboard(snapshot)
    markup = _Markup(html)
    ids = [element["id"] for _, element in markup.elements if "id" in element]
    assert len(ids) == len(set(ids))
    for link in markup.tags("a"):
        href = link.get("href", "")
        assert href == "/" or (href.startswith("#") and href[1:] in ids)
    for _, element in markup.elements:
        if "table-wrap" in element.get("class", ""):
            assert element["tabindex"] == "0"
            assert element["role"] == "region" and element["aria-label"]
    assert all(header.get("scope") == "col" for header in markup.tags("th"))
    assert markup.tags("caption") and markup.tags("summary")
    assert not markup.tags("script") and not markup.tags("link")
    assert not any(meta.get("http-equiv") == "refresh" for meta in markup.tags("meta"))
    assert ":focus-visible" in html and "skip-link" in html
    assert "@media (max-width: 760px)" in html and "overflow-x: auto" in html
    assert "@media (max-width: 480px)" in html


def test_render_follows_no_artifact_pointers_or_environment(snapshot, monkeypatch) -> None:
    result = replace(snapshot, operations_snapshot=_validated(fill="confirmed"))
    monkeypatch.setattr(Path, "open", lambda *a, **k: pytest.fail("unexpected file I/O"))
    assert POINTERS["h20"] in render_dashboard(result)
    assert result.to_dict()["operations_snapshot"]["runs"][0]["fill"] == "confirmed"
