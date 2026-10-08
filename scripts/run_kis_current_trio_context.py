"""Inert-by-default, one-client current trio OC acquisition for the owned Paper cycle."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
import urllib.parse
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from thericher_v2 import contracts
from thericher_v2.data import kis_current_trio_context as current
from thericher_v2.data import kis_daily_price_endpoints as endpoint
from thericher_v2.data import resample
from thericher_v2.data import us_equity_session as calendar
from thericher_v2.execution import kis_market_data as market
from thericher_v2.execution import kis_market_data_rate_gate as pace
from thericher_v2.execution import kis_private_daily_backfill as backfill
from thericher_v2.execution import kis_private_daily_collector as storage

GOAL = "kis-owned-portfolio-repeatable-cycle-v1"
VERSION = "kis-current-trio-acquisition-v1"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path("C:/Users/Public/Documents/thericher-v2")
MARKET_ROOT = Path("D:/market_data")
ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")
MARKET_SCOPE = Path("us_equities/kis_paper_private/current-trio")
ARTIFACT_SCOPE = Path("data/kis-current-trio-context-v1")
CONTROL_SCOPE = Path("us_equities/kis_paper_private/collection-control-v1")
TARGETS = (("SPY", "AMS"), ("TLT", "NAS"), ("GLD", "AMS"))
SCOPE = {symbol: frozenset({venue}) for symbol, venue in TARGETS}
CONTEXT_PIN = "sha256:a1273093de79744a3c10646566de9c8187357fbe625c867c18732aa06841e657"
SOURCE_ORIGINS = {
    "scripts/run_kis_current_trio_context.py": Path(__file__),
    **{
        f"src/{m.__name__.replace('.', '/')}.py": Path(m.__file__)
        for m in (contracts, current, endpoint, resample, calendar, market, pace, backfill, storage)
    },
}
SAFE_REASONS = frozenset(
    {
        "calendar_invalid",
        "decision_not_in_entry_session",
        "collection_binding_invalid",
        "collection_time_invalid",
        "source_symbols_invalid",
        "page_invalid",
        "page_identity_mismatch",
        "page_hash_mismatch",
        "required_session_missing",
        "required_close_invalid",
        "auth_rejected",
        "auth_response_invalid",
        "config_missing",
        "rate_limited",
        "token_request_not_due",
        "cooldown_not_due",
        "transport_failure",
        "response_invalid",
        "daily_response_rejected",
        "endpoint_date_invalid",
        "endpoint_numeric_invalid",
        "endpoint_schema_invalid",
        "endpoint_query_invalid",
        "endpoint_date_after_anchor",
        "endpoint_duplicate_conflict",
        "credential_echo_rejected",
        "request_not_allowlisted",
        "runtime_budget",
        "page_budget",
        "worker_busy",
        "storage_floor",
        "source_hash_changed",
        "source_hash_unavailable",
        "source_import_origin_mismatch",
        "local_io_unavailable",
        "local_contract_invalid",
        "local_unexpected_failure",
        "provider_failure_unclassified",
        "invocation_exists",
        "retained_bytes_changed",
    }
)


class Stop(RuntimeError):
    pass


def _require(condition, reason):
    if not condition:
        raise Stop(reason)


def _sha(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _json(document):
    return (
        json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def _utc(value):
    _require(
        type(value) is datetime and value.utcoffset() == timedelta(0), "collection_time_invalid"
    )
    return value.isoformat().replace("+00:00", "Z")


def _source_pins(root):
    result = {}
    for name, origin in SOURCE_ORIGINS.items():
        path = root / name
        _require(path.resolve() == origin.resolve(), "source_import_origin_mismatch")
        result[name] = _sha(path.read_bytes())
    _require(
        result["src/thericher_v2/data/kis_current_trio_context.py"] == CONTEXT_PIN,
        "source_hash_changed",
    )
    return result


def _root(path, intended, repository_root):
    _require(path.absolute() == intended.absolute(), "local_contract_invalid")
    _require(
        not any(p.is_symlink() or (p.exists() and p.is_junction()) for p in (path, *path.parents)),
        "local_contract_invalid",
    )
    root = storage._external_cache_root(cache_root=path, repo_root=repository_root)
    _require(not root.is_relative_to(WORKSPACE_ROOT.resolve()), "local_contract_invalid")
    return root


def _child(root, relative):
    path = root / relative
    _require(
        not any(
            p.is_symlink() or (p.exists() and p.is_junction())
            for p in (path, *path.parents)
            if p.is_relative_to(root)
        ),
        "local_contract_invalid",
    )
    return backfill._resolve_external_child(path=path, root=root)


def _schedule(now):
    _utc(now)
    entry = calendar.us_equity_2026_session(now.astimezone(calendar.US_EQUITY_EASTERN).date())
    _require(
        entry is not None and entry.window.open_ts <= now < entry.window.close_ts,
        "decision_not_in_entry_session",
    )
    history, day = [], entry.session_date
    while len(history) < 64:
        day -= timedelta(days=1)
        session = calendar.us_equity_2026_session(day)
        if session is not None:
            history.append(session)
    return tuple(reversed(history)), entry


def _reason(error):
    if isinstance(error, current.KisCurrentTrioInputUnavailable):
        code = error.reason_code
    elif isinstance(error, (Stop, market.KisPaperMarketDataError)):
        code = str(error)
    elif isinstance(error, OSError):
        return "local_io_unavailable"
    elif isinstance(error, (ValueError, TypeError, AttributeError, KeyError)):
        return "local_contract_invalid"
    else:
        return "local_unexpected_failure"
    return code if code in SAFE_REASONS else "provider_failure_unclassified"


class _CaptureTransport:
    """Keep only the last GET in memory; retention follows full typed validation."""

    def __init__(self, delegate, *, check, check_deadline, clock, anchor):
        self.delegate, self.check, self.clock = delegate, check, clock
        self.check_deadline = check_deadline
        self.anchor = anchor
        self.last = None
        self.request_started_at = None
        self.token_attempts = self.get_attempts = 0

    def mark_start(self, now):
        self.check()
        self.request_started_at = now

    def request(self, request):
        self.last = None
        self.request_started_at = None
        self.check()
        parsed = urllib.parse.urlsplit(request.url)
        _require(
            request.url == market.KIS_PAPER_MARKET_DATA_BASE_URL + parsed.path,
            "request_not_allowlisted",
        )
        if request.method == "POST" and parsed.path == market.KIS_PAPER_TOKEN_PATH:
            _require(self.token_attempts == 0, "page_budget")
            self.token_attempts += 1
        else:
            _require(
                request.method == "GET"
                and parsed.path == market.KIS_PAPER_DAILY_PATH
                and self.get_attempts < 3,
                "request_not_allowlisted",
            )
            symbol, venue = TARGETS[self.get_attempts]
            params = request.query
            _require(
                params["SYMB"] == symbol
                and params["EXCD"] == venue
                and params["GUBN"] == "0"
                and params["MODP"] == "0"
                and params["BYMD"] == self.anchor
                and params["AUTH"] == ""
                and set(params) == {"AUTH", "SYMB", "EXCD", "GUBN", "MODP", "BYMD"}
                and request.headers.get("tr_id") == market.KIS_PAPER_DAILY_TR_ID
                and not request.headers.get("tr_cont"),
                "request_not_allowlisted",
            )
            self.get_attempts += 1
        response = self.delegate.request(request)
        self.check_deadline()
        if request.method == "GET":
            _require(self.request_started_at is not None, "collection_time_invalid")
            self.last = (request, response, self.request_started_at)
        return response

    def validated_body(self, page):
        _require(self.last is not None, "page_hash_mismatch")
        request, response, started = self.last
        _require(_sha(response.body) == page.source_body_sha256, "page_hash_mismatch")
        values = (
            request.headers["appkey"],
            request.headers["appsecret"],
            request.headers["authorization"].removeprefix("Bearer "),
        )
        reparsed = endpoint.parse_kis_daily_price_endpoints(
            response, query=page.query, credential_values=values
        )
        digest = current.current_trio_page_sha256(page)
        _require(digest == current.current_trio_page_sha256(reparsed), "page_hash_mismatch")
        self.check_deadline()
        observed = self.clock()
        self.last = None
        return response.body, started, observed, digest


def run_current_trio_context(
    *,
    invocation_id: str,
    dotenv_path: Path,
    market_root: Path = MARKET_ROOT,
    artifact_root: Path = ARTIFACT_ROOT,
    repository_root: Path = REPOSITORY_ROOT,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    """One owned attempt; no retries, continuation, token clearing or old input access."""
    _require(
        len(invocation_id) == 32 and all(c in "0123456789abcdef" for c in invocation_id),
        "local_contract_invalid",
    )
    m = _root(Path(market_root), MARKET_ROOT, repository_root)
    a = _root(Path(artifact_root), ARTIFACT_ROOT, repository_root)
    outcome_root = _child(a, ARTIFACT_SCOPE / invocation_id)
    _require(not outcome_root.exists(), "invocation_exists")
    outcome_root.mkdir(parents=True)
    started, begin = clock(), monotonic()
    deadline = begin + 120
    result = dict(
        kind=VERSION,
        goal=GOAL,
        invocation_id=invocation_id,
        status="input_unavailable",
        reason=None,
        started_at=_utc(started),
        completed_at=None,
        token_POST_attempts=0,
        daily_GET_attempts=0,
        accepted_pages=0,
        count_semantics="inherited dispatch attempts; not independently measured wire starts",
        pages=[],
        source_pins={},
        source_reattestation="unavailable",
        next_due=None,
        price_only=True,
        MODP="0_opaque",
        PIT="not_claimed",
        finality="not_observed",
        provider_publication_at="not_observed",
        input_binding=None,
    )
    lock = client = token_gate = request_gate = None
    pins, retained = {}, {}
    target = _child(m, MARKET_SCOPE / invocation_id)

    def check_deadline():
        _require(monotonic() < deadline, "runtime_budget")

    def expire_terminal():
        if monotonic() >= deadline:
            result.update(status="input_unavailable", reason="runtime_budget", input_binding=None)
            result["completed_at"] = _utc(clock())
            result["elapsed_seconds"] = round(monotonic() - begin, 3)

    try:
        try:
            pins = _source_pins(repository_root)
        except OSError:
            raise Stop("source_hash_unavailable") from None
        result["source_pins"] = pins
        history, entry = _schedule(started)
        base = _child(m, MARKET_SCOPE)
        base.mkdir(parents=True, exist_ok=True)
        lock = backfill._acquire_worker_lock(root=base, observed_at=started)
        _require(lock is not None, "worker_busy")
        _require(not target.exists(), "invocation_exists")
        target.mkdir()
        _require(
            not storage.private_daily_cache_would_cross_free_space_floor(
                cache_root=target, repo_root=repository_root, projected_bytes=4 * 1024 * 1024
            ),
            "storage_floor",
        )

        def check():
            _require(monotonic() + 15 <= deadline, "runtime_budget")
            now = clock()
            _require(
                entry.window.open_ts <= now < entry.window.close_ts, "decision_not_in_entry_session"
            )
            _require(_source_pins(repository_root) == pins, "source_hash_changed")

        def bounded_sleep(delay):
            _require(
                math.isfinite(delay)
                and 0 <= delay <= pace.KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
                "cooldown_not_due",
            )
            _require(monotonic() + delay + 15 <= deadline, "runtime_budget")
            sleeper(delay)

        control = _child(m, CONTROL_SCOPE)
        capture = _CaptureTransport(
            None,
            check=check,
            check_deadline=check_deadline,
            clock=clock,
            anchor=history[-1].session_date.strftime("%Y%m%d"),
        )
        request_gate = pace.KisPaperMarketDataRateGate(
            control_root=control,
            clock=clock,
            sleeper=bounded_sleep,
            on_request_started=capture.mark_start,
        )
        token_gate = pace.KisPaperMarketDataTokenStartGate(control_root=control, clock=clock)
        native = endpoint.KisPaperDailyEndpointTransport(
            timeout_seconds=15, request_gate=request_gate, token_start_gate=token_gate
        )
        capture.delegate = native
        config = market.load_kis_paper_market_data_config(dotenv_path)
        client = endpoint.KisPaperDailyEndpointClient(
            config=config, transport=capture, max_daily_page_attempts=3
        )
        client.ensure_authenticated()

        def retain(name, data):
            check_deadline()
            _require(
                not storage.private_daily_cache_would_cross_free_space_floor(
                    cache_root=target, repo_root=repository_root, projected_bytes=len(data)
                ),
                "storage_floor",
            )
            path = backfill._resolve_external_child(path=Path(name), root=target)
            storage._write_bytes_and_sync(path, data)
            digest = _sha(data)
            _require(_sha(path.read_bytes()) == digest, "retained_bytes_changed")
            retained[name] = digest
            check_deadline()
            return dict(path=path.relative_to(m).as_posix(), sha256=digest)

        pages, observations = {}, []
        for symbol, venue in TARGETS:
            query = market.KisPaperDailyQuery(
                symbol=symbol,
                exchange=venue,
                by_date=history[-1].session_date.strftime("%Y%m%d"),
                approved_symbol_exchanges=SCOPE,
            )
            page = client.fetch_daily_endpoint_page(query)
            body, requested, observed, typed_hash = capture.validated_body(page)
            facts = dict(
                page.safe_facts(),
                request_started_at=_utc(requested),
                observed_at=_utc(observed),
                typed_page_sha256=typed_hash,
                GUBN="0",
                query_continuation=None,
            )
            result["pages"].append(facts)
            result["accepted_pages"] += 1
            raw = retain(f"{symbol}.raw.json", body)
            typed = retain(
                f"{symbol}.oc.json",
                _json(
                    dict(
                        facts=facts,
                        rows=[r.as_document() for r in page.rows],
                        source_row_fingerprints=page.source_row_fingerprints,
                    )
                ),
            )
            observations.append(dict(**facts, raw=raw, typed=typed))
            pages[symbol] = page
            _require(
                all(
                    s.session_date.isoformat() in {r.session_date for r in page.rows}
                    for s in history
                ),
                "required_session_missing",
            )
        completed = clock()
        collection = retain(
            "collection.json",
            _json(
                dict(
                    kind=VERSION,
                    invocation_id=invocation_id,
                    source_pins=pins,
                    started_at=_utc(started),
                    completed_at=_utc(completed),
                    pages=observations,
                )
            ),
        )
        bindings = current.KisCurrentTrioCollectionBinding(
            collection_ref=collection["sha256"],
            started_at=started,
            completed_at=completed,
            pages=tuple(
                current.KisCurrentTrioPageBinding(
                    collection_ref=collection["sha256"],
                    query=pages[symbol].query,
                    source_body_sha256=facts["source_body_sha256"],
                    typed_page_sha256=facts["typed_page_sha256"],
                    request_started_at=datetime.fromisoformat(facts["request_started_at"]),
                    observed_at=datetime.fromisoformat(facts["observed_at"]),
                )
                for (symbol, _), facts in zip(TARGETS, observations, strict=True)
            ),
        )
        context = current.prepare_current_trio_context(
            pages,
            scheduled_history=history,
            entry_session=entry,
            decision_at=clock(),
            collection_binding=bindings,
        )
        private = retain(
            "context.json",
            _json(
                dict(
                    facts=context.safe_facts(),
                    session_dates=[d.isoformat() for d in context.session_dates],
                    closes=[[str(c) for c in channel] for channel in context.closes],
                    feature_cutoff=_utc(context.feature_cutoff),
                    entry_at=_utc(context.entry_at),
                    decision_at=_utc(context.decision_at),
                    observed_at_by_symbol=[_utc(t) for t in context.observed_at_by_symbol],
                    collection_completed_at=_utc(context.collection_completed_at),
                    collection=collection,
                )
            ),
        )
        check_deadline()
        result.update(
            status="ready",
            input_binding=dict(
                collection=collection, context=private, context_sha256=context.context_sha256
            ),
        )
    except Exception as error:
        result.update(status="input_unavailable", reason=_reason(error))
    finally:
        if client is not None:
            counts = client.call_counts
            result.update(
                token_POST_attempts=counts.token_attempts,
                daily_GET_attempts=counts.daily_page_attempts,
            )
        try:
            if pins:
                _require(_source_pins(repository_root) == pins, "source_hash_changed")
                for name, digest in retained.items():
                    _require(_sha((target / name).read_bytes()) == digest, "retained_bytes_changed")
                result["source_reattestation"] = "matched"
        except Exception as error:
            reason = _reason(error) if isinstance(error, Stop) else "source_hash_unavailable"
            result.update(
                status="input_unavailable",
                reason=reason,
                source_reattestation=(
                    "changed" if reason == "source_hash_changed" else "unavailable"
                ),
                input_binding=None,
            )
        try:
            if result["reason"] == "token_request_not_due" and token_gate is not None:
                due = token_gate.snapshot().next_token_request_not_before_utc
                result["next_due"] = _utc(due) if due is not None else None
            elif (
                result["reason"] in {"cooldown_not_due", "rate_limited"}
                and request_gate is not None
            ):
                due = request_gate.snapshot().retry_not_before_utc
                result["next_due"] = _utc(due) if due is not None else None
        except Exception:
            pass
        try:
            backfill._release_worker_lock(lock)
        except Exception:
            result.update(
                status="input_unavailable", reason="local_io_unavailable", input_binding=None
            )
        try:
            result["completed_at"] = _utc(clock())
            result["elapsed_seconds"] = round(monotonic() - begin, 3)
        except Exception:
            result.update(
                status="input_unavailable",
                reason="collection_time_invalid",
                input_binding=None,
                elapsed_seconds=None,
            )
        result["retained_files"] = {
            str(MARKET_SCOPE / invocation_id / n).replace("\\", "/"): h for n, h in retained.items()
        }
        receipt = outcome_root / "receipt.json"
        published_ready = False
        # Only owned immutable files remain; no shared catalog is projected after unlock.
        try:
            expire_terminal()
            pending = outcome_root / "receipt.pending.json"
            storage._write_bytes_and_sync(pending, _json(result))
            expire_terminal()
            if result["reason"] == "runtime_budget":
                pending = outcome_root / "receipt-budget.pending.json"
                storage._write_bytes_and_sync(pending, _json(result))
            pending.rename(receipt)
            published_ready = result["status"] == "ready"
            result = dict(
                result, receipt_path=str(receipt), receipt_sha256=_sha(receipt.read_bytes())
            )
        except OSError:
            result.update(
                status="input_unavailable", reason="local_io_unavailable", input_binding=None
            )
        finally:
            expire_terminal()
            if published_ready and result["reason"] == "runtime_budget":
                # Preserve provisional bytes if the final rename/read itself runs late.
                try:
                    receipt.rename(outcome_root / "receipt.overdeadline.json")
                    result.pop("receipt_path", None)
                    result.pop("receipt_sha256", None)
                    storage._write_bytes_and_sync(receipt, _json(result))
                    result = dict(
                        result, receipt_path=str(receipt), receipt_sha256=_sha(receipt.read_bytes())
                    )
                except OSError:
                    result.pop("receipt_sha256", None)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--invocation-id")
    parser.add_argument("--dotenv-path", type=Path, default=REPOSITORY_ROOT / ".env")
    parser.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--market-root", type=Path, default=MARKET_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=ARTIFACT_ROOT)
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(dict(status="not_executed", goal=GOAL, daily_GET_budget=3)))
        return 0
    try:
        result = run_current_trio_context(
            invocation_id=args.invocation_id or uuid.uuid4().hex,
            dotenv_path=args.dotenv_path,
            repository_root=args.repository_root,
            market_root=args.market_root,
            artifact_root=args.artifact_root,
        )
    except Exception:
        result = dict(status="input_unavailable", reason="local_io_or_contract_invalid")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "ready" else 20


if __name__ == "__main__":
    raise SystemExit(main())
