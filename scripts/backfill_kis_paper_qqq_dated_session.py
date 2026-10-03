"""One bounded native QQQ/SPY dated session or predeclared September panel invocation."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataClient,
    KisPaperMarketDataConfig,
    KisPaperMarketDataError,
    UrllibKisPaperMarketDataTransport,
    load_kis_paper_market_data_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY,
    KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
    KIS_PAPER_MARKET_DATA_TOKEN_REQUEST_NOT_DUE_REASON,
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)
from thericher_v2.execution.kis_private_intraday_backfill import (
    KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT,
    KIS_PAPER_QQQ_DATED_CACHE_ROOT,
    KIS_PAPER_QQQ_DATED_SESSION,
    kis_paper_qqq_dated_session_cache_root,
    kis_paper_qqq_dated_session_complete,
    kis_paper_qqq_dated_session_initial_key,
    run_kis_paper_qqq_dated_session_cycle,
    sanitize_kis_paper_private_intraday_failure_reason,
    validate_kis_paper_qqq_dated_session_request,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--target", choices=("QQQ/NAS", "SPY/AMS"), default="QQQ/NAS")
    parser.add_argument("--pages", type=int, default=4)
    parser.add_argument("--session-date", type=date.fromisoformat)
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--september-panel", action="store_true")
    parser.add_argument("--code-revision")
    args = parser.parse_args(argv)
    symbol, exchange = args.target.split("/")
    target = (symbol, exchange)
    if args.september_panel and (args.session_date is not None or args.cache_root is not None):
        parser.error("--september-panel cannot override its predeclared dates or roots")
    observed = clock()
    dates = (
        _september_panel_dates()
        if args.september_panel
        else (args.session_date or KIS_PAPER_QQQ_DATED_SESSION,)
    )
    try:
        roots = tuple(
            args.cache_root
            or (
                KIS_PAPER_QQQ_DATED_CACHE_ROOT
                if day == KIS_PAPER_QQQ_DATED_SESSION and target == ("QQQ", "NAS")
                else kis_paper_qqq_dated_session_cache_root(day, target=target)
            )
            for day in dates
        )
        if (
            not 1 <= len(dates) <= 20
            or len(dates) * args.pages > 80
            or len(set(dates)) != len(dates)
            or tuple(sorted(dates)) != dates
            or (
                args.september_panel
                and any(not date(2026, 9, 2) <= day <= date(2026, 9, 30) for day in dates)
            )
        ):
            raise ValueError("finite panel budget exceeded")
        for day, root in zip(dates, roots, strict=True):
            validate_kis_paper_qqq_dated_session_request(
                cache_root=root,
                repo_root=_REPO_ROOT,
                session_date=day,
                pages=args.pages,
                inspect_paths=False,
                observed_at=observed,
                target=target,
            )
    except ValueError:
        parser.error(
            "closed 2026 regular native sessions, bound target/date roots and 1..4 pages required"
        )
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "not_executed",
                    "keyb": kis_paper_qqq_dated_session_initial_key(dates[0], observed_at=observed),
                    "session_dates": [day.isoformat() for day in dates],
                    "max_gets": len(dates) * args.pages,
                    "reason": "execute_flag_required",
                    **({"target_key": f"{symbol}/{exchange}/1m"} if symbol == "SPY" else {}),
                }
            )
        )
        return 0
    if not args.code_revision or not args.code_revision.strip() or "\n" in args.code_revision:
        parser.error("--code-revision is required for execution")
    try:
        for day, root in zip(dates, roots, strict=True):
            validate_kis_paper_qqq_dated_session_request(
                cache_root=root,
                repo_root=_REPO_ROOT,
                session_date=day,
                pages=args.pages,
                observed_at=observed,
                target=target,
            )
        config = _load_paper_config()
        control_root = KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT.parent / (
            KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY
        )
        request_gate = KisPaperMarketDataRateGate(
            control_root=control_root,
            **({"sleeper": _yield_long_cooldown} if args.september_panel else {}),
        )
        token_gate = KisPaperMarketDataTokenStartGate(control_root=control_root)
        client = KisPaperMarketDataClient(
            config=config,
            max_minute_page_attempts=len(dates) * args.pages,
            transport=UrllibKisPaperMarketDataTransport(
                request_gate=request_gate,
                token_start_gate=token_gate,
            ),
        )
        if args.september_panel:
            payload = _collect_panel(
                client=client,
                dates=dates,
                roots=roots,
                pages=args.pages,
                code_revision=args.code_revision,
                observed=observed,
                request_gate=request_gate,
                token_gate=token_gate,
                target=target,
            )
            print(json.dumps(payload, sort_keys=True))
            return 0 if payload["status"] == "complete" else 1
        result = run_kis_paper_qqq_dated_session_cycle(
            client=client,
            cache_root=roots[0],
            repo_root=_REPO_ROOT,
            code_revision=args.code_revision,
            session_date=dates[0],
            pages=args.pages,
            observed_at=observed,
            target=target,
        )
        complete = result.status in {"collected", "partial", "recovered"} and (
            kis_paper_qqq_dated_session_complete(
                cache_root=roots[0],
                repo_root=_REPO_ROOT,
                session_date=dates[0],
                observed_at=observed,
                target=target,
            )
        )
        payload = {
            **({"target_key": result.target_key} if symbol == "SPY" else {}),
            "status": "complete" if complete else "incomplete",
            "collection_status": result.status,
            "reason": result.reason,
            "row_count": result.row_count,
            "exact_overlap_rows": result.exact_overlap_rows,
            "manifest_path": str(result.manifest_path) if result.manifest_path else None,
            "manifest_hash": result.manifest_hash,
            "regular_session_complete": complete,
        }
    except KisPaperMarketDataError as error:
        payload = {
            "status": "incomplete",
            "reason": sanitize_kis_paper_private_intraday_failure_reason(error),
        }
        complete = False
    except (OSError, ValueError):
        payload = {"status": "indeterminate", "reason": "dated_session_unavailable"}
        complete = False
    print(json.dumps(payload, sort_keys=True))
    return 0 if complete else 1


def _load_paper_config() -> KisPaperMarketDataConfig:
    # Native invocation uses the existing byte-wise approved dotenv whitelist,
    # never ambient Docker credentials or unapproved account/live fields.
    return load_kis_paper_market_data_config(_REPO_ROOT / ".env", environment={})


def _september_panel_dates() -> tuple[date, ...]:
    from thericher_v2.data.us_equity_session import us_equity_2026_session

    return tuple(
        day
        for number in range(2, 31)
        if (session := us_equity_2026_session(day := date(2026, 9, number))) is not None
        and session.kind == "regular"
    )


def _yield_long_cooldown(seconds: float) -> None:
    # Preserve the existing one-second start spacing; yield a shared backoff.
    if seconds > KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS:
        raise KisPaperMarketDataError("rate_limited")
    time.sleep(seconds)


def _shared_next_due(
    reason: str | None,
    request_gate: KisPaperMarketDataRateGate,
    token_gate: KisPaperMarketDataTokenStartGate,
) -> str | None:
    if reason == KIS_PAPER_MARKET_DATA_TOKEN_REQUEST_NOT_DUE_REASON:
        due = token_gate.snapshot().next_token_request_not_before_utc
    elif reason == "rate_limited":
        snapshot = request_gate.snapshot()
        # This invocation exits and releases its client; a later process needs
        # a fresh token. This is not a wait for a still-authenticated client.
        candidates = [
            snapshot.retry_not_before_utc,
            token_gate.snapshot().next_token_request_not_before_utc,
        ]
        if snapshot.last_request_started_at_utc is not None:
            candidates.append(
                snapshot.last_request_started_at_utc
                + timedelta(
                    seconds=KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
                )
            )
        due = max((item for item in candidates if item is not None), default=None)
    else:
        due = None
    return due.isoformat().replace("+00:00", "Z") if due is not None else None


def _collect_panel(
    *,
    client: KisPaperMarketDataClient,
    dates: tuple[date, ...],
    roots: tuple[Path, ...],
    pages: int,
    code_revision: str,
    observed: datetime,
    request_gate: KisPaperMarketDataRateGate,
    token_gate: KisPaperMarketDataTokenStartGate,
    target: tuple[str, str] = ("QQQ", "NAS"),
) -> dict[str, object]:
    sessions = []
    next_due = None
    for day, root in zip(dates, roots, strict=True):
        try:
            result = run_kis_paper_qqq_dated_session_cycle(
                client=client,
                cache_root=root,
                repo_root=_REPO_ROOT,
                code_revision=code_revision,
                session_date=day,
                pages=pages,
                observed_at=observed,
                target=target,
            )
            complete = result.status in {"collected", "partial", "recovered"} and (
                kis_paper_qqq_dated_session_complete(
                    cache_root=root,
                    repo_root=_REPO_ROOT,
                    session_date=day,
                    observed_at=observed,
                    target=target,
                )
            )
            record = {
                "session_date": day.isoformat(),
                "collection_status": result.status,
                "reason": result.reason,
                "row_count": result.row_count,
                "manifest_hash": result.manifest_hash,
                "regular_session_complete": complete,
            }
        except KisPaperMarketDataError as error:
            record = {
                "session_date": day.isoformat(),
                "collection_status": "rejected",
                "reason": sanitize_kis_paper_private_intraday_failure_reason(error),
                "row_count": 0,
                "manifest_hash": None,
                "regular_session_complete": False,
            }
        except (OSError, ValueError):
            record = {
                "session_date": day.isoformat(),
                "collection_status": "indeterminate",
                "reason": "dated_session_unavailable",
                "row_count": 0,
                "manifest_hash": None,
                "regular_session_complete": False,
            }
        sessions.append(record)
        reason = record["reason"]
        if reason in {KIS_PAPER_MARKET_DATA_TOKEN_REQUEST_NOT_DUE_REASON, "rate_limited"}:
            next_due = _shared_next_due(reason, request_gate, token_gate)
            break
        counts = client.call_counts
        if counts.token_attempts and not counts.minute_page_attempts:
            # A failed first authentication cannot become repeated fresh POSTs.
            break
    counts = client.call_counts
    complete_count = sum(item["regular_session_complete"] for item in sessions)
    return {
        **({"target_key": f"{target[0]}/{target[1]}/1m"} if target[0] == "SPY" else {}),
        "status": "complete" if complete_count == len(dates) else "incomplete",
        "planned_session_count": len(dates),
        "session_count": len(sessions),
        "complete_session_count": complete_count,
        "max_gets": len(dates) * pages,
        "minute_page_attempts": counts.minute_page_attempts,
        "token_attempts": counts.token_attempts,
        "next_due": next_due,
        "sessions": sessions,
    }


if __name__ == "__main__":
    raise SystemExit(main())
