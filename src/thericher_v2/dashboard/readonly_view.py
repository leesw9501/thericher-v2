"""Korean view of validated public categories; no state, controls or imports of workers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from html import escape
from typing import Any

_KST = timezone(timedelta(hours=9), name="KST")
_ACTUAL = {
    "unknown": "실행 미확인",
    "abstain": "실행 보류",
    "not_entered": "기술 단계 미진입",
    "technical_failure": "기술 실패",
    "completed": "기술 실행 완료",
}
_FINANCIAL = {
    "unknown": "미확인",
    "not_attempted": "시도 없음 관측",
    "attempted": "제출 시도 관측",
    "accepted": "제출 수락 관측",
    "not_observed": "미관측",
    "linked": "연결 체결 관측",
    "observed": "소유분 관측",
}
_INSTALLATION = {"unknown": "미확인", "installed": "설치 확인", "not_installed": "미설치 관측"}
_STAGES = {
    "producer": "입력 생성",
    "startup": "작업 시작",
    "capture": "입력 관측",
    "entry": "진입 계획",
    "exit": "소유분 청산 계획",
}
_REQUEST = {
    "unknown": "미확인",
    "none": "저장된 요청 없음",
    "pause_requested": "일시정지 요청",
    "resume_requested": "재개 요청",
}
_ACK = {"unknown": "미확인", "acknowledged": "확인 관측", "not_acknowledged": "미확인 응답 관측"}
_CSS = """
:root{color-scheme:light;--ink:#182329;--muted:#59656a;--line:#d4dcda;
--paper:#f8faf9;--green:#176a4d;--amber:#865500;--red:#a43038}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);
font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;letter-spacing:0}
.shell{max-width:1240px;margin:auto;padding:20px 24px}header{border-bottom:2px solid var(--ink);
padding:0 0 12px}h1{font-size:24px;line-height:1.3;margin:0}h2{font-size:18px;margin:18px 0 4px}
h3{font-size:15px;margin:0 0 3px}p{margin:5px 0}small,.muted,time{color:var(--muted)}
.source{padding:9px 12px;margin:0 0 14px;border-left:3px solid var(--amber);background:#fff5da;
font-size:12px;overflow-wrap:anywhere}.source.fresh{border-color:var(--green);background:#ebf5ef}
.scope{color:var(--muted);font-size:12px}.run{border-bottom:1px solid var(--line);padding:14px 0;
min-width:0}.run-heading{display:flex;justify-content:space-between;align-items:baseline;
gap:8px;flex-wrap:wrap}.status{font-size:12px;font-weight:600}.failure{color:var(--red);
border-left:3px solid var(--red);padding-left:9px;margin:8px 0}.failure code{font-size:12px}
.financial{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:10px 0}
dt{font-size:12px;color:var(--muted)}dd{margin:2px 0;font-size:13px;font-weight:600}
code{overflow-wrap:anywhere;white-space:normal;font-size:12px}.technical{font-size:12px;
color:var(--muted)}.clock small{display:inline-block;margin-left:5px}.details{font-size:12px;
margin-top:9px}.details summary{cursor:pointer;color:#245e69}.details ol{list-style:none;
padding:0;margin:7px 0}.details li{display:grid;grid-template-columns:110px minmax(0,1fr);
gap:8px;padding:5px 0;border-bottom:1px solid var(--line)}.reference{overflow-wrap:anywhere}
.control{display:flex;gap:20px;flex-wrap:wrap;padding:14px 0;align-items:center}
.control dl{display:flex;gap:20px;flex-wrap:wrap;margin:0}
.control fieldset{border:0;padding:0;margin:0}
.control button{width:34px;height:32px;border:1px solid var(--line);border-radius:4px;
background:#edf0ee;color:#88918d;font-size:17px}.unknown{padding:18px 0;color:var(--muted)}
footer{border-top:1px solid var(--line);padding:12px 0;font-size:12px;color:var(--muted)}
.run,.financial div,.control div{min-width:0}h1,h2,h3,p,dd,time{overflow-wrap:anywhere}
@media(max-width:600px){.shell{padding:14px 12px}h1{font-size:22px}h2{font-size:16px}
.financial{gap:8px}.financial dd{font-size:12px}.run{padding:12px 0}
.details li{grid-template-columns:88px minmax(0,1fr)}.clock small{display:block;margin-left:0}
.control{gap:10px}.control dl{gap:12px}.run-heading{display:block}.status{display:block}}
"""


def _clock(value: str | None) -> str:
    if value is None:
        return '<span class="muted">관측 시각 미확인 · UNKNOWN</span>'
    instant = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    return (
        '<time class="clock">'
        + instant.astimezone(_KST).strftime("%Y-%m-%d %H:%M:%S KST")
        + "<small>"
        + instant.strftime("%Y-%m-%d %H:%M:%S UTC")
        + "</small></time>"
    )


def _category(label: str, code: str) -> str:
    return escape(label) + ' <span class="technical">' + escape(code.upper()) + "</span>"


def _run(run: dict[str, Any]) -> str:
    actual = run["outcome"]
    parts = [
        '<article class="run"><div class="run-heading"><h3>',
        escape(run["label"]),
        '</h3><span class="status">',
        _category(_ACTUAL[actual["status"]], actual["status"]),
        "</span></div>",
        _clock(actual["observed_at"]),
    ]
    if actual["failure"] is not None:
        failure = actual["failure"]
        parts += [
            '<p class="failure">확인된 기술 실패 · <code>',
            escape(failure["reason"]),
            "</code><br><code>",
            escape(failure["exception"]),
            " · ",
            escape(failure["stage"]),
            "</code></p>",
        ]
    if actual["task_exit_codes"]:
        codes = " / ".join("UNKNOWN" if c is None else str(c) for c in actual["task_exit_codes"])
        parts += [
            '<p class="technical">Task metadata: ',
            escape(codes),
            " · 금융 결과 아님</p>",
        ]
    parts.append('<dl class="financial">')
    for key, label in (("submit", "실제 제출"), ("fill", "연결 체결"), ("owned", "공개 소유 관측")):
        code = run["financial"][key]
        parts += ["<div><dt>", label, "</dt><dd>", _category(_FINANCIAL[code], code), "</dd></div>"]
    parts.append("</dl>")
    evidence = run["evidence"]
    parts += [
        '<details class="details evidence"><summary>공개 근거 · ',
        escape(evidence["kind"]),
        '</summary><p class="reference"><code>',
        escape(evidence["reference"]),
        "</code><br>SHA256: <code>",
        escape(evidence["sha256"] or "UNKNOWN"),
        "</code></p></details>",
        '<details class="details installation"><summary>설치·원래 계획 · ',
        _category(_INSTALLATION[run["installation"]], run["installation"]),
        "</summary><p>설치 ≠ 실행·체결 · 계획 시각과 실제 관측은 별개</p><ol>",
    ]
    for event in run["plan"]:
        parts += ["<li><span>", _STAGES[event["stage"]], "</span>", _clock(event["at"]), "</li>"]
    if not run["plan"]:
        parts.append("<li>공개 계획 미수신 · UNKNOWN</li>")
    parts.append("</ol></details></article>")
    return "".join(parts)


def render_readonly_dashboard(snapshot: dict[str, Any]) -> str:
    """Render only the already validated DTO; every input label is HTML escaped."""
    state = snapshot["source_state"]
    source_label = {
        "fresh": "공개 스냅샷 관측 · FRESH",
        "stale": "이전 관측 · 현재 상태 미확인 · STALE",
        "unknown": "공개 근거 미수신 · UNKNOWN",
    }[state]
    parts = [
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<meta http-equiv="refresh" content="30;url=/">',
        "<title>TheRicher v2 · Paper 공개 관측</title><style>",
        _CSS,
        '</style></head><body><main class="shell"><p class="source ',
        state,
        '">',
        source_label,
        " · Read-only<br>",
        _clock(snapshot["as_of"]),
        "</p><header><h1>TheRicher v2</h1>",
        '<p class="scope">Paper 운영 · 공개 범주 관측</p></header>',
        '<section aria-label="Paper actual outcomes"><h2>Paper 실행 · 확인된 관측</h2>',
        '<p class="scope">공개 근거 스냅샷 · 현재 계좌 조회 아님</p>',
    ]
    if snapshot["runs"]:
        parts.extend(_run(run) for run in snapshot["runs"])
    else:
        count = snapshot["counts"]["runs"]
        parts.append(
            '<p class="unknown">'
            + (
                "실행 근거 미수신 · 실행 수 UNKNOWN"
                if count is None
                else "공개 실행 목록 비어 있음"
            )
            + "</p>"
        )
    control = snapshot["control"]
    parts += [
        '</section><section class="control" aria-label="Saved request and worker acknowledgement">',
        '<fieldset disabled><button type="button" disabled ',
        'title="일시정지 요청 비활성 · Pause request" ',
        'aria-label="일시정지 요청 비활성 · Pause request">&#9208;</button></fieldset><dl>',
        "<div><dt>저장된 요청</dt><dd>",
        _category(_REQUEST[control["saved_request"]], control["saved_request"]),
        "</dd></div><div><dt>실행기 확인</dt><dd>",
        _category(_ACK[control["worker_ack"]], control["worker_ack"]),
        "</dd></div></dl></section>",
        "<footer>Paper · 순손익 UNKNOWN · 저장된 요청 ≠ 실행기 확인</footer>",
        "</main></body></html>",
    ]
    return "".join(parts)
