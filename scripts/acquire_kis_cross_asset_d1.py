"""Finite, source-safe KIS Paper cross-asset D1 capability acquisition."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import time
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType

from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_DAILY_ADJUSTMENT_PROBE_MODES,
    KIS_PAPER_DAILY_DEFAULT_ADJUSTMENT_MODES,
    KIS_PAPER_DAILY_PATH,
    KIS_PAPER_MARKET_DATA_BASE_URL,
    KIS_PAPER_TOKEN_PATH,
    KisMarketDataRequest,
    KisMarketDataResponse,
    KisMarketDataTransport,
    KisPaperDailyAdjustmentProbeQuery,
    KisPaperDailyRawPage,
    KisPaperMarketDataClient,
    KisPaperMarketDataError,
    UrllibKisPaperMarketDataTransport,
    load_kis_paper_market_data_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)
from thericher_v2.execution.kis_private_daily_backfill import (
    _acquire_worker_lock,
    _release_worker_lock,
)
from thericher_v2.execution.kis_private_daily_collector import (
    private_daily_cache_would_cross_free_space_floor,
)

GOAL = "kis-cross-asset-d1-input-foundation-v1"
SCOPE = MappingProxyType(
    {"SPY": frozenset({"AMS"}), "TLT": frozenset({"NAS"}), "GLD": frozenset({"AMS"})}
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    "scripts/acquire_kis_cross_asset_d1.py",
    "src/thericher_v2/contracts.py",
    "src/thericher_v2/execution/kis_market_data.py",
    "src/thericher_v2/execution/kis_market_data_rate_gate.py",
    "src/thericher_v2/execution/kis_private_daily_backfill.py",
    "src/thericher_v2/execution/kis_private_daily_collector.py",
)
SAFE_REASONS = frozenset(
    {
        "auth_rejected",
        "auth_response_invalid",
        "config_missing",
        "daily_response_invalid",
        "daily_response_rejected",
        "daily_page_limit_exceeded",
        "rate_limited",
        "transport_failure",
        "redirect_rejected",
        "request_not_allowlisted",
        "paper_host_required",
        "token_request_not_due",
        "response_invalid",
    }
)


class ProbeStop(RuntimeError):
    """Internal fixed categorical stop; never constructed from provider text."""


class CrossAssetDailyTransport(UrllibKisPaperMarketDataTransport):
    """Fixed daily-only scope, supporting probes and ordinary MODP0 on one client."""

    def request(self, request: KisMarketDataRequest) -> KisMarketDataResponse:
        path = urllib.parse.urlsplit(request.url).path
        if request.method == "POST" and path == KIS_PAPER_TOKEN_PATH:
            return self._request_with_daily_symbol_exchanges(
                request,
                daily_symbol_exchanges=SCOPE,
            )
        if request.method != "GET" or path != KIS_PAPER_DAILY_PATH:
            raise KisPaperMarketDataError("request_not_allowlisted")
        marker = request.daily_adjustment_modes
        if marker is None:
            modes = KIS_PAPER_DAILY_DEFAULT_ADJUSTMENT_MODES
        elif marker == KIS_PAPER_DAILY_ADJUSTMENT_PROBE_MODES:
            modes = KIS_PAPER_DAILY_ADJUSTMENT_PROBE_MODES
        else:
            raise KisPaperMarketDataError("request_not_allowlisted")
        return self._request_with_daily_symbol_exchanges(
            request,
            daily_symbol_exchanges=SCOPE,
            daily_adjustment_modes=modes,
        )


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _source_pins(repository_root: Path) -> dict[str, str]:
    return {name: _sha((repository_root / name).read_bytes()) for name in SOURCE_FILES}


def _utc(value: datetime) -> str:
    if value.tzinfo != UTC:
        raise ValueError("UTC clock required")
    return value.isoformat().replace("+00:00", "Z")


def _external(path: Path, repository_root: Path) -> Path:
    absolute = path.absolute()
    for ancestor in (absolute, *absolute.parents):
        if ancestor.exists():
            info = ancestor.lstat()
            if ancestor.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("external root must not contain links")
    resolved = absolute.resolve()
    if resolved.is_relative_to(repository_root.resolve()):
        raise ValueError("external storage required")
    return resolved


def _write_new(path: Path, data: bytes) -> str:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    return _sha(data)


def _write_json(path: Path, payload: Mapping[str, object]) -> str:
    return _write_new(path, (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode())


def probe_queries() -> tuple[KisPaperDailyAdjustmentProbeQuery, ...]:
    return tuple(
        KisPaperDailyAdjustmentProbeQuery(
            symbol=symbol,
            exchange=exchange,
            by_date=anchor,
            adjustment_mode=mode,
            approved_symbol_exchanges=SCOPE,
        )
        for symbol, exchange, anchor, mode in (
            ("SPY", "AMS", "20261007", "0"),
            ("SPY", "AMS", "20261007", "1"),
            ("TLT", "NAS", "20261007", "0"),
            ("TLT", "NAS", "20261007", "1"),
            ("GLD", "AMS", "20261007", "0"),
            ("GLD", "AMS", "20261007", "1"),
            ("TLT", "NAS", "20071231", "0"),
            ("GLD", "AMS", "20071231", "0"),
        )
    )


def _query_fact(query: KisPaperDailyAdjustmentProbeQuery) -> dict[str, object]:
    return {
        "symbol": query.symbol,
        "exchange": query.exchange,
        "BYMD": query.by_date,
        "MODP": query.adjustment_mode,
        "GUBN": "0",
    }


class _ProbeTransport:
    """Keep response bodies private and enforce the frozen appointment boundary."""

    def __init__(
        self,
        delegate: KisMarketDataTransport,
        *,
        raw_root: Path,
        market_root: Path,
        deadline: float,
        monotonic: Callable[[], float],
        check_source: Callable[[], None],
        space_check: Callable[[int], bool],
    ) -> None:
        self.delegate = delegate
        self.raw_root = raw_root
        self.market_root = market_root
        self.deadline = deadline
        self.monotonic = monotonic
        self.check_source = check_source
        self.space_check = space_check
        self.token_dispatch_attempts = 0
        self.daily_dispatch_attempts = 0
        self.responses: list[dict[str, object]] = []
        self._pending: tuple[KisMarketDataRequest, KisMarketDataResponse, int] | None = None

    def request(self, request: KisMarketDataRequest) -> KisMarketDataResponse:
        self._pending = None
        self.check_source()
        if self.monotonic() >= self.deadline:
            raise ProbeStop("runtime_budget")
        if request.method == "POST":
            if self.token_dispatch_attempts >= 1:
                raise ProbeStop("token_budget")
            self.token_dispatch_attempts += 1
        else:
            if self.daily_dispatch_attempts >= 8:
                raise ProbeStop("page_budget")
            if self.space_check(1_048_576):
                raise ProbeStop("storage_floor")
            self.daily_dispatch_attempts += 1
        response = self.delegate.request(request)
        if request.method == "GET":
            self._pending = (request, response, self.daily_dispatch_attempts)
        self.check_source()
        return response

    def commit_market_response(self, query: KisPaperDailyAdjustmentProbeQuery) -> None:
        """Called only after the client parse and page-fact validation succeed."""
        if self._pending is None:
            raise ProbeStop("response_invalid")
        request, response, ordinal = self._pending
        expected = {
            "SYMB": query.symbol,
            "EXCD": query.exchange,
            "BYMD": query.by_date,
            "MODP": query.adjustment_mode,
        }
        if not 200 <= response.status_code < 300 or any(
            request.query.get(key) != value for key, value in expected.items()
        ):
            raise ProbeStop("response_invalid")
        headers = {key.lower(): value for key, value in request.headers.items()}
        private_values = tuple(
            value
            for value in (
                headers.get("appkey"),
                headers.get("appsecret"),
                headers.get("authorization", "").removeprefix("Bearer "),
            )
            if value
        )
        if any(secret.encode("utf-8") in response.body for secret in private_values):
            raise ProbeStop("credential_echo_rejected")
        pending_values = [response.payload()]
        while pending_values:
            value = pending_values.pop()
            if isinstance(value, str) and any(secret in value for secret in private_values):
                raise ProbeStop("credential_echo_rejected")
            if isinstance(value, Mapping):
                pending_values.extend(value.keys())
                pending_values.extend(value.values())
            elif isinstance(value, list):
                pending_values.extend(value)
        self.check_source()
        if self.space_check(len(response.body)):
            raise ProbeStop("storage_floor")
        destination = self.raw_root / f"daily-{ordinal:02d}.json"
        digest = _write_new(destination, response.body)
        self.responses.append(
            {
                "ordinal": ordinal,
                "market_relative_path": destination.relative_to(self.market_root).as_posix(),
                "sha256": digest,
                "http_status_class": "2xx",
                "query": expected,
            }
        )
        self.discard_pending_response()

    def discard_pending_response(self) -> None:
        self._pending = None


def _page_fact(
    page: KisPaperDailyRawPage,
    query: KisPaperDailyAdjustmentProbeQuery,
    ordinary_rows: dict[str, dict[str, str]],
) -> dict[str, object]:
    fingerprints: dict[str, str] = {}
    duplicates = 0
    for row in page.rows:
        datetime.strptime(row.xymd, "%Y%m%d")
        if row.xymd > query.by_date:
            raise ProbeStop("date_after_anchor")
        fingerprint = _sha(json.dumps(row.as_document(), sort_keys=True).encode())
        if row.xymd in fingerprints:
            if fingerprints[row.xymd] != fingerprint:
                raise ProbeStop("daily_duplicate_conflict")
            duplicates += 1
        fingerprints[row.xymd] = fingerprint
    if not fingerprints:
        raise ProbeStop("empty_response")
    overlap = 0
    older_progress: bool | None = None
    if query.adjustment_mode == "0":
        prior = ordinary_rows.setdefault(query.symbol, {})
        for session_date, fingerprint in fingerprints.items():
            if session_date in prior:
                if prior[session_date] != fingerprint:
                    raise ProbeStop("daily_duplicate_conflict")
                overlap += 1
        if query.by_date == "20071231":
            older_progress = bool(prior) and min(fingerprints) < min(prior)
            if not older_progress:
                raise ProbeStop("nonadvancing_cursor")
        prior.update(fingerprints)
    else:
        prior = ordinary_rows.get(query.symbol, {})
        overlap = len(set(prior) & set(fingerprints))
    return {
        **_query_fact(query),
        "status": "observed",
        "row_count": len(page.rows),
        "unique_date_count": len(fingerprints),
        "newest_date": max(fingerprints),
        "oldest_date": min(fingerprints),
        "exact_duplicate_date_count": duplicates,
        "ordinary_exact_overlap_count": overlap if query.adjustment_mode == "0" else None,
        "mode_pair_common_date_count": overlap if query.adjustment_mode == "1" else None,
        "mode_pair_changed_date_count": sum(
            prior[d] != fingerprints[d] for d in prior.keys() & fingerprints.keys()
        )
        if query.adjustment_mode == "1"
        else None,
        "older_unique_progress": older_progress,
        "candidate_next_BYMD": min(fingerprints),
        "continuation_category": "F" if page.page.continuation_available else "not_observed",
    }


def run_probe(
    *,
    market_root: Path,
    artifact_root: Path,
    repository_root: Path,
    run_label: str,
    dotenv_path: Path,
    clock: Callable[[], datetime] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    transport_factory: Callable[..., KisMarketDataTransport] | None = None,
    config_loader: Callable | None = None,
    space_check: Callable[[int], bool] | None = None,
) -> dict[str, object]:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", run_label):
        raise ValueError("run label invalid")
    clock = clock or (lambda: datetime.now(UTC))
    market = _external(market_root, repository_root)
    artifacts = _external(artifact_root, repository_root)
    if market == artifacts or market.is_relative_to(artifacts) or artifacts.is_relative_to(market):
        raise ValueError("market and artifact roots must be disjoint")
    started = clock()
    start_monotonic = monotonic()
    deadline = start_monotonic + 60
    pins = _source_pins(repository_root)
    base = market / "us_equities/kis_paper_private/cross-asset-d1" / GOAL / "probe"
    raw_root = base / run_label
    run_root = artifacts / "data" / GOAL / "capability" / run_label
    _external(raw_root, repository_root)
    _external(run_root, repository_root)
    if raw_root.exists() or run_root.exists():
        raise FileExistsError("immutable run already exists")
    run_root.mkdir(parents=True)
    queries = probe_queries()
    contract = {
        "kind": "kis_cross_asset_d1_capability_contract",
        "goal": GOAL,
        "started_at_utc": _utc(started),
        "run_label": run_label,
        "base_url": KIS_PAPER_MARKET_DATA_BASE_URL,
        "endpoint": KIS_PAPER_DAILY_PATH,
        "tr_id": "HHDFS76240000",
        "queries": [_query_fact(q) for q in queries],
        "maximum_daily_GETs": 8,
        "maximum_token_POSTs": 1,
        "initiation_deadline_seconds": 60,
        "transport_timeout_seconds": 15,
        "source_pins": pins,
        "modes": "opaque; no adjusted/dividend/TR/PIT claim",
    }
    contract_sha = _write_json(run_root / "contract.json", contract)
    check_space = space_check or (
        lambda count: private_daily_cache_would_cross_free_space_floor(
            cache_root=raw_root,
            repo_root=repository_root,
            projected_bytes=count,
        )
    )
    client = None
    recorder = None
    lock = None
    facts: list[dict[str, object]] = []
    reason = None
    next_due = None
    token_gate = None

    def check_source() -> None:
        if _source_pins(repository_root) != pins:
            raise ProbeStop("source_hash_changed")

    def paced_sleep(delay: float) -> None:
        nonlocal next_due
        if not math.isfinite(delay) or delay < 0:
            raise ProbeStop("invalid_pacing_delay")
        if delay > 1.0 + 1e-6:
            next_due = _utc(clock() + timedelta(seconds=delay))
            raise ProbeStop("cooldown_not_due")
        if monotonic() + delay >= deadline:
            raise ProbeStop("runtime_budget")
        sleeper(delay)

    try:
        if check_space(8 * 1_048_576):
            raise ProbeStop("storage_floor")
        base.mkdir(parents=True, exist_ok=True)
        lock = _acquire_worker_lock(root=base, observed_at=started)
        if lock is None:
            raise ProbeStop("worker_busy")
        raw_root.mkdir()
        control = market / "us_equities/kis_paper_private/collection-control-v1"
        _external(control, repository_root)
        request_gate = KisPaperMarketDataRateGate(
            control_root=control,
            clock=clock,
            sleeper=paced_sleep,
        )
        token_gate = KisPaperMarketDataTokenStartGate(control_root=control, clock=clock)
        check_source()
        config = (config_loader or load_kis_paper_market_data_config)(dotenv_path)
        transport = (transport_factory or CrossAssetDailyTransport)(
            timeout_seconds=15.0,
            request_gate=request_gate,
            token_start_gate=token_gate,
        )
        recorder = _ProbeTransport(
            transport,
            raw_root=raw_root,
            market_root=market,
            deadline=deadline,
            monotonic=monotonic,
            check_source=check_source,
            space_check=check_space,
        )
        client = KisPaperMarketDataClient(
            config=config,
            transport=recorder,
            max_minute_page_attempts=1,
            max_daily_page_attempts=8,
        )
        client.ensure_authenticated()
        ordinary_rows: dict[str, dict[str, str]] = {}
        for query in queries:
            page = client.fetch_daily_raw_page(query)
            fact = _page_fact(page, query, ordinary_rows)
            recorder.commit_market_response(query)
            facts.append(fact)
        check_source()
    except ProbeStop as error:
        reason = error.args[0]
    except KisPaperMarketDataError as error:
        reason = str(error) if str(error) in SAFE_REASONS else "provider_failure_unclassified"
        if reason == "token_request_not_due" and token_gate is not None:
            due = token_gate.snapshot().next_token_request_not_before_utc
            next_due = _utc(due) if due is not None else None
    except (OSError, ValueError, RuntimeError):
        reason = "local_io_or_contract_invalid"
    finally:
        if recorder is not None:
            recorder.discard_pending_response()
        _release_worker_lock(lock)
    try:
        source_reattestation = "matched" if _source_pins(repository_root) == pins else "mismatch"
        if source_reattestation == "mismatch":
            reason = "source_hash_changed"
    except OSError:
        source_reattestation = "unavailable"
        reason = "source_hash_unavailable"
    counts = client.call_counts if client is not None else None
    receipt = {
        "kind": "kis_cross_asset_d1_capability_receipt",
        "goal": GOAL,
        "run_label": run_label,
        "contract_sha256": contract_sha,
        "source_pins": pins,
        "source_reattestation": source_reattestation,
        "started_at_utc": _utc(started),
        "completed_at_utc": _utc(clock()),
        "status": "observed" if reason is None else ("partial" if facts else "unavailable"),
        "reason": reason,
        "owned_next_due_utc": next_due,
        "recovery_class": "closed" if reason is None else "preserve_exact_attempt",
        "call_counts": {
            "token_attempts": counts.token_attempts if counts else 0,
            "daily_page_attempts": counts.daily_page_attempts if counts else 0,
        },
        "dispatch_attempts_are_not_proof_of_HTTP_start": True,
        "accepted_page_count": len(facts),
        "categorical_failure_count": int(reason is not None),
        "queries_not_attempted": [
            _query_fact(q) for q in queries[counts.daily_page_attempts if counts else 0 :]
        ],
        "pages": facts,
        "private_daily_responses": recorder.responses if recorder else [],
        "token_body_retained": False,
        "raw_stdout": False,
        "remaining_page_estimate": "unknown",
        "eta": "unknown",
        "limitations": [
            "Modes opaque; no adjusted/dividend/total-return/PIT/finality claim.",
            "No MODP0 repeat control; mode differences may include revisions.",
            "Fixed anchors only; no global history-floor or unlimited-reach claim.",
            "Capability only; no collection, account, order or live route.",
        ],
    }
    receipt_path = run_root / "receipt.json"
    receipt_sha = _write_json(receipt_path, receipt)
    return {
        "status": receipt["status"],
        "reason": reason,
        "receipt_path": str(receipt_path),
        "receipt_sha256": receipt_sha,
        "accepted_page_count": len(facts),
        "call_counts": receipt["call_counts"],
        "owned_next_due_utc": next_due,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--market-root", type=Path, default=Path("D:/market_data"))
    parser.add_argument(
        "--artifact-root", type=Path, default=Path("D:/thericher-v2/model-artifacts")
    )
    parser.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--dotenv-path", type=Path, default=REPOSITORY_ROOT / ".env")
    args = parser.parse_args(argv)
    if not args.execute:
        print(
            json.dumps(
                {"status": "not_executed", "queries": [_query_fact(q) for q in probe_queries()]}
            )
        )
        return 0
    try:
        result = run_probe(
            market_root=args.market_root,
            artifact_root=args.artifact_root,
            repository_root=args.repository_root,
            run_label=args.run_label,
            dotenv_path=args.dotenv_path,
        )
    except (OSError, ValueError, RuntimeError):
        result = {"status": "unavailable", "reason": "local_io_or_contract_invalid"}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "observed" else 20


if __name__ == "__main__":
    raise SystemExit(main())
