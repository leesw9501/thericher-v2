"""Bounded offline QQQ/SPY D1 naive controls behind the frozen event audit.

The module deliberately performs only a retrospective local-paper plumbing
check.  It does not expose the untouched tail, train a model, or route a
decision toward KIS.  Temporary local-paper event logs are replay-checked and
deleted before the one sanitized aggregate artifact is written.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from thericher_v2.contracts import Bar, OrderIntent, Timeframe
from thericher_v2.data.kis_daily_event_boundary_audit import (
    KisDailyEventBoundaryAudit,
    KisDailyEventBoundaryPartition,
    load_kis_daily_event_boundary_audit,
)
from thericher_v2.data.kis_paper_daily import (
    KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT,
    KisPaperPrivateDailyCatalog,
    load_kis_paper_private_daily_catalog,
)
from thericher_v2.execution.emergency import EmergencyStore
from thericher_v2.execution.fill_source import (
    FillEventArtifact,
    collect_fill_source_evidence,
)
from thericher_v2.execution.local_paper import (
    LOCAL_PAPER_SOURCE,
    LocalPaperBroker,
    replay_local_paper_account,
)
from thericher_v2.state import Event

KIS_DAILY_MASKED_NAIVE_VALIDATION_ID = "kis-daily-masked-naive-validation-v1"
DEFAULT_KIS_DAILY_MASKED_NAIVE_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/kis-daily-masked-naive-validation"
)
DEFAULT_KIS_DAILY_EVENT_BOUNDARY_AUDIT_PATH = Path(
    "D:/thericher-v2/model-artifacts/research-contracts/"
    "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-event-boundary-audit.json"
)

_SYMBOL_TARGETS = {
    "QQQ": "QQQ/NAS/MODP=0",
    "SPY": "SPY/AMS/MODP=0",
}
_SYMBOLS = tuple(_SYMBOL_TARGETS)
_PHASES = ("development", "validation")
_PREFIX_PARTITIONS = ("development", "purge", "validation", "embargo")
_CONTROLS = ("flat", "always_long", "previous_session_direction")
_MAX_ENTRIES_PER_TEMPORARY_REPLAY = 64
_Control = Literal["flat", "always_long", "previous_session_direction"]
_Phase = Literal["development", "validation"]
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_FORBIDDEN_SUMMARY_KEYS = frozenset(
    {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "price",
        "prices",
        "return",
        "returns",
        "perbarreturn",
        "perbarreturns",
        "eventjsonlpath",
        "eventlogpath",
    }
)

_EXPECTED_AUDIT_ARTIFACT_SHA256 = (
    "sha256:3d97b26b5e8e422cb2b4bcf262fbd1be887e44d7e43afdd9e2b5d689f805a46c"
)
_EXPECTED_CATALOG_DATASET_HASH = (
    "sha256:78b00556ddbc8bcfb0c4d1bb67e004e4a4c4ff035a8c348b2516b842fa397718"
)
_EXPECTED_CATALOG_INDEX_HASH = (
    "sha256:e0bb847994a97b1df1181b0013fabcb784d979c7c366f686940e563cb01ac660"
)
_EXPECTED_SIDECAR_DATASET_HASH = (
    "sha256:9a3e3b22c4a6045c4f26e6e77439cb3322cb61f8f6c04b422bb31412631d0de3"
)
_EXPECTED_SIDECAR_MANIFEST_HASH = (
    "sha256:c6f4b7113507d27577fb7ee66328db53d274e08d2470d3854b6f4e9aa46d171d"
)
_EXPECTED_SESSION_DATES_SHA256 = (
    "sha256:a8743b8af3b9df84f9a68d51cd6b74a882809995d142b82602746af5329044cd"
)
_EXPECTED_MASK_IDENTITY = (
    "sha256:921c61b8abf822b0aee71b66b43c37875cb581e95bf7a1563b053880c087d429"
)
_EXPECTED_PARTITION_IDENTITY = (
    "sha256:b82ed4022237929febde187651cb31e74740b311faa85c850967c617ac8dcfdb"
)


@dataclass(frozen=True, slots=True)
class MaskedNaiveControlResult:
    """Aggregate result for one fixed control, phase, and symbol."""

    phase: _Phase
    symbol: str
    control: _Control
    eligible_decision_count: int
    entry_count: int
    replay_batch_count: int
    fill_count: int
    starting_cash: Decimal
    ending_cash: Decimal
    total_fees: Decimal
    all_fills_local_paper: bool
    replay_invariant_passed: bool

    @property
    def pnl(self) -> Decimal:
        return self.ending_cash - self.starting_cash


@dataclass(frozen=True, slots=True)
class MaskedNaiveValidationResult:
    """Re-executable aggregate evidence without source rows or fill values."""

    audit_artifact_sha256: str
    source_dataset_hash: str
    prefix_dataset_hash: str
    common_session_count: int
    control_results: tuple[MaskedNaiveControlResult, ...]
    artifact_path: Path
    artifact_sha256: str


@dataclass(frozen=True, slots=True)
class _Candidate:
    phase: _Phase
    symbol: str
    prior_bar: Bar
    signal_bar: Bar
    entry_bar: Bar
    exit_bar: Bar


@dataclass(frozen=True, slots=True)
class _TemporaryReplayResult:
    cash_delta: Decimal
    total_fees: Decimal
    fill_count: int
    all_fills_local_paper: bool
    replay_invariant_passed: bool


class _InMemoryReplayStore:
    """Small EventStore-compatible buffer for one disposable replay batch.

    ``LocalPaperBroker`` still owns fill semantics.  Keeping append/replay
    events in memory prevents each fixed-size batch from repeatedly parsing
    its own JSONL, then ``flush`` creates the exact temporary evidence consumed
    by the existing fill-source verifier.
    """

    def __init__(self, *, jsonl_path: Path) -> None:
        self.jsonl_path = jsonl_path
        self._events: list[Event] = []

    def append(self, event: Event) -> Event:
        recorded = event.with_seq(len(self._events) + 1)
        self._events.append(recorded)
        return recorded

    def iter_events(self) -> tuple[Event, ...]:
        return tuple(self._events)

    def flush(self) -> None:
        try:
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with self.jsonl_path.open("x", encoding="utf-8", newline="\n") as handle:
                for event in self._events:
                    record = json.dumps(
                        event.to_record(),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    handle.write(record)
                    handle.write("\n")
        except OSError as error:
            raise RuntimeError("masked daily validation event evidence is unwritable") from error


def run_pinned_kis_daily_masked_naive_validation(
    *,
    audit_path: Path | str = DEFAULT_KIS_DAILY_EVENT_BOUNDARY_AUDIT_PATH,
    cache_root: Path | str = KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT,
    artifact_root: Path | str = DEFAULT_KIS_DAILY_MASKED_NAIVE_ARTIFACT_ROOT,
    repo_root: Path | str | None = None,
) -> MaskedNaiveValidationResult:
    """Re-attest the frozen audit before exposing the permitted catalog prefix.

    The catalog loader checks the full raw-source identity first, then builds
    only bars through the audit embargo endpoint.  No sidecar rows are loaded
    here: the qualified audit is the sole event-boundary contract.
    """

    audit = load_kis_daily_event_boundary_audit(
        audit_path,
        expected_artifact_sha256=_EXPECTED_AUDIT_ARTIFACT_SHA256,
        expected_catalog_dataset_hash=_EXPECTED_CATALOG_DATASET_HASH,
        expected_catalog_index_hash=_EXPECTED_CATALOG_INDEX_HASH,
        expected_sidecar_dataset_hash=_EXPECTED_SIDECAR_DATASET_HASH,
        expected_sidecar_manifest_hash=_EXPECTED_SIDECAR_MANIFEST_HASH,
        expected_session_dates_sha256=_EXPECTED_SESSION_DATES_SHA256,
        expected_mask_identity=_EXPECTED_MASK_IDENTITY,
        expected_partition_identity=_EXPECTED_PARTITION_IDENTITY,
    )
    catalog = load_kis_paper_private_daily_catalog(
        cache_root,
        target_keys=tuple(_SYMBOL_TARGETS.values()),
        expected_index_hash=audit.lineage.catalog_index_hash,
        expected_full_dataset_hash=audit.lineage.catalog_dataset_hash,
        end_session=audit.partition("embargo").end_session,
        repo_root=repo_root,
    )
    return run_kis_daily_masked_naive_validation(
        catalog,
        audit=audit,
        source_dataset_hash=audit.lineage.catalog_dataset_hash,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )


def run_kis_daily_masked_naive_validation(
    catalog: KisPaperPrivateDailyCatalog,
    *,
    audit: KisDailyEventBoundaryAudit,
    source_dataset_hash: str,
    artifact_root: Path | str = DEFAULT_KIS_DAILY_MASKED_NAIVE_ARTIFACT_ROOT,
    repo_root: Path | str | None = None,
) -> MaskedNaiveValidationResult:
    """Run the three fixed local-paper controls on audit-eligible D1 pairs."""

    _require_sha256(source_dataset_hash, "source_dataset_hash")
    _validate_catalog_prefix(catalog, audit=audit, source_dataset_hash=source_dataset_hash)
    resolved_root = _prepare_artifact_root(artifact_root=artifact_root, repo_root=repo_root)
    candidates = _eligible_candidates(catalog, audit=audit)
    control_results: list[MaskedNaiveControlResult] = []
    for phase in _PHASES:
        for symbol in _SYMBOLS:
            shared_candidates = candidates[(phase, symbol)]
            for control in _CONTROLS:
                control_results.append(
                    _run_control(
                        phase=phase,
                        symbol=symbol,
                        control=control,
                        candidates=shared_candidates,
                        temporary_root=resolved_root,
                    )
                )
    _validate_shared_eligibility(tuple(control_results))
    summary = _summary_document(
        catalog=catalog,
        audit=audit,
        source_dataset_hash=source_dataset_hash,
        control_results=tuple(control_results),
    )
    artifact_path, artifact_sha256 = _write_aggregate_summary(
        artifact_root=resolved_root,
        summary=summary,
    )
    return MaskedNaiveValidationResult(
        audit_artifact_sha256=audit.artifact_sha256,
        source_dataset_hash=source_dataset_hash,
        prefix_dataset_hash=catalog.dataset_hash,
        common_session_count=len(catalog.common_sessions),
        control_results=tuple(control_results),
        artifact_path=artifact_path,
        artifact_sha256=artifact_sha256,
    )


def _validate_catalog_prefix(
    catalog: KisPaperPrivateDailyCatalog,
    *,
    audit: KisDailyEventBoundaryAudit,
    source_dataset_hash: str,
) -> None:
    if source_dataset_hash != audit.lineage.catalog_dataset_hash:
        raise ValueError("masked daily validation source dataset hash does not match audit")
    if catalog.index_hash != audit.lineage.catalog_index_hash:
        raise ValueError("masked daily validation catalog index hash does not match audit")
    if tuple(catalog.bars_by_symbol) != _SYMBOLS:
        raise ValueError("masked daily validation requires the fixed QQQ/SPY panel")

    permitted_partitions = tuple(audit.partition(name) for name in _PREFIX_PARTITIONS)
    expected_count = sum(partition.session_count for partition in permitted_partitions)
    if len(catalog.common_sessions) != expected_count:
        raise ValueError("masked daily validation catalog prefix session count is incompatible")
    cursor = 0
    for partition in permitted_partitions:
        selected = catalog.common_sessions[cursor : cursor + partition.session_count]
        if (
            len(selected) != partition.session_count
            or selected[0] != partition.start_session
            or selected[-1] != partition.end_session
        ):
            raise ValueError("masked daily validation catalog partition geometry is incompatible")
        cursor += partition.session_count
    if cursor != len(catalog.common_sessions):  # Defensive even after the count check.
        raise ValueError("masked daily validation catalog prefix is incompatible")
    if catalog.common_sessions[-1] >= audit.partition("untouched_tail").start_session:
        raise ValueError("masked daily validation attempted to consume the untouched tail")

    for symbol in _SYMBOLS:
        stream = catalog.bars_by_symbol[symbol].bars
        if (
            len(stream) != len(catalog.common_sessions)
            or any(
                bar.symbol != symbol
                or bar.market != "US"
                or bar.timeframe != Timeframe.D1
                or not bar.complete
                for bar in stream
            )
            or tuple(bar.start_ts.date() for bar in stream) != catalog.common_sessions
        ):
            raise ValueError("masked daily validation catalog stream is incompatible")


def _eligible_candidates(
    catalog: KisPaperPrivateDailyCatalog,
    *,
    audit: KisDailyEventBoundaryAudit,
) -> dict[tuple[_Phase, str], tuple[_Candidate, ...]]:
    session_index = {session: index for index, session in enumerate(catalog.common_sessions)}
    result: dict[tuple[_Phase, str], tuple[_Candidate, ...]] = {}
    for phase in _PHASES:
        partition = audit.partition(phase)
        start = _partition_start_index(partition, session_index=session_index)
        stop = start + partition.session_count
        if catalog.common_sessions[stop - 1] != partition.end_session:
            raise ValueError("masked daily validation phase geometry is incompatible")
        for symbol in _SYMBOLS:
            bars = catalog.bars_by_symbol[symbol].bars
            masked_boundaries = {
                (pair.start_session, pair.end_session)
                for pair in audit.masked_pairs_by_symbol[symbol]
            }
            candidates: list[_Candidate] = []
            for entry_index in range(start + 2, stop - 1):
                sessions = catalog.common_sessions[entry_index - 2 : entry_index + 2]
                if len(sessions) != 4:
                    raise ValueError("masked daily validation candidate geometry is incompatible")
                boundaries = tuple(zip(sessions[:-1], sessions[1:], strict=True))
                if any(boundary in masked_boundaries for boundary in boundaries):
                    continue
                candidates.append(
                    _Candidate(
                        phase=phase,
                        symbol=symbol,
                        prior_bar=bars[entry_index - 2],
                        signal_bar=bars[entry_index - 1],
                        entry_bar=bars[entry_index],
                        exit_bar=bars[entry_index + 1],
                    )
                )
            result[(phase, symbol)] = tuple(candidates)
    return result


def _partition_start_index(
    partition: KisDailyEventBoundaryPartition,
    *,
    session_index: dict[date, int],
) -> int:
    try:
        return session_index[partition.start_session]
    except KeyError as error:
        raise ValueError("masked daily validation partition start is unavailable") from error


def _run_control(
    *,
    phase: _Phase,
    symbol: str,
    control: _Control,
    candidates: tuple[_Candidate, ...],
    temporary_root: Path,
) -> MaskedNaiveControlResult:
    selected = tuple(
        (candidate_index, candidate)
        for candidate_index, candidate in enumerate(candidates, start=1)
        if _should_enter(control, candidate=candidate)
    )
    batches = tuple(_entry_batches(selected)) or ((),)
    replay_results = tuple(
        _run_temporary_replay_batch(
            phase=phase,
            symbol=symbol,
            control=control,
            entries=batch,
            temporary_root=temporary_root,
        )
        for batch in batches
    )
    if not all(item.replay_invariant_passed for item in replay_results):
        raise RuntimeError("masked daily validation must use replayable local-paper fills")
    starting_cash = Decimal("10000")
    total_cash_delta = sum((item.cash_delta for item in replay_results), Decimal("0"))
    return MaskedNaiveControlResult(
        phase=phase,
        symbol=symbol,
        control=control,
        eligible_decision_count=len(candidates),
        entry_count=len(selected),
        replay_batch_count=len(replay_results),
        fill_count=sum((item.fill_count for item in replay_results), 0),
        starting_cash=starting_cash,
        ending_cash=starting_cash + total_cash_delta,
        total_fees=sum((item.total_fees for item in replay_results), Decimal("0")),
        all_fills_local_paper=all(item.all_fills_local_paper for item in replay_results),
        replay_invariant_passed=True,
    )


def _entry_batches(
    entries: tuple[tuple[int, _Candidate], ...],
) -> tuple[tuple[tuple[int, _Candidate], ...], ...]:
    return tuple(
        entries[start : start + _MAX_ENTRIES_PER_TEMPORARY_REPLAY]
        for start in range(0, len(entries), _MAX_ENTRIES_PER_TEMPORARY_REPLAY)
    )


def _run_temporary_replay_batch(
    *,
    phase: _Phase,
    symbol: str,
    control: _Control,
    entries: tuple[tuple[int, _Candidate], ...],
    temporary_root: Path,
) -> _TemporaryReplayResult:
    with TemporaryDirectory(
        prefix=f".{KIS_DAILY_MASKED_NAIVE_VALIDATION_ID}-",
        dir=temporary_root,
    ) as name:
        work_dir = Path(name)
        event_store = _InMemoryReplayStore(jsonl_path=work_dir / "events.jsonl")
        starting_cash = Decimal("10000")
        broker = LocalPaperBroker(
            event_store=event_store,
            emergency_store=EmergencyStore(work_dir / "emergency.json"),
            starting_cash=starting_cash,
            fee_bps=Decimal("1"),
            slippage_bps=Decimal("0"),
        )
        total_fees = Decimal("0")
        expected_fill_count = 0
        for candidate_index, candidate in entries:
            decision_id = (
                f"{KIS_DAILY_MASKED_NAIVE_VALIDATION_ID}-{phase}-{symbol.lower()}-"
                f"{control}-{candidate_index:04d}"
            )
            entry = broker.submit_and_fill_next_bar(
                OrderIntent(
                    client_order_id=f"{decision_id}-entry",
                    symbol=symbol,
                    market="US",
                    side="buy",
                    quantity=Decimal("1"),
                    limit_price=None,
                    decision_id=decision_id,
                    created_at=candidate.signal_bar.end_ts,
                ),
                signal_bar=candidate.signal_bar,
                execution_bar=candidate.entry_bar,
            )
            if entry.fill is None:
                raise RuntimeError(
                    "masked daily validation entry did not produce a local-paper fill"
                )
            total_fees += entry.fill.fee
            expected_fill_count += 1
            exit_execution = broker.submit_and_fill_next_bar(
                OrderIntent(
                    client_order_id=f"{decision_id}-exit",
                    symbol=symbol,
                    market="US",
                    side="sell",
                    quantity=entry.fill.quantity,
                    limit_price=None,
                    decision_id=f"{decision_id}-flatten",
                    created_at=candidate.entry_bar.end_ts,
                ),
                signal_bar=candidate.entry_bar,
                execution_bar=candidate.exit_bar,
            )
            if exit_execution.fill is None:
                raise RuntimeError(
                    "masked daily validation exit did not produce a local-paper fill"
                )
            total_fees += exit_execution.fill.fee
            expected_fill_count += 1

        event_store.flush()
        fill_evidence = collect_fill_source_evidence(
            (
                FillEventArtifact(
                    path=event_store.jsonl_path,
                    expected_fill_count=expected_fill_count,
                    label=f"{phase}-{symbol}-{control}",
                ),
            )
        )
        if not fill_evidence.local_paper_replay_invariant_passed:
            raise RuntimeError("masked daily validation must use replayable local-paper fills")
        account = broker.account()
        replayed_account = replay_local_paper_account(event_store, starting_cash=starting_cash)
        if account != replayed_account or account.positions:
            raise RuntimeError("masked daily validation must finish flat and replayable")
        return _TemporaryReplayResult(
            cash_delta=account.cash - starting_cash,
            total_fees=total_fees,
            fill_count=len(fill_evidence.local_paper_fills),
            all_fills_local_paper=fill_evidence.all_fills_local_paper,
            replay_invariant_passed=fill_evidence.local_paper_replay_invariant_passed,
        )


def _should_enter(control: _Control, *, candidate: _Candidate) -> bool:
    if control == "flat":
        return False
    if control == "always_long":
        return True
    if control == "previous_session_direction":
        return candidate.signal_bar.close > candidate.prior_bar.close
    raise ValueError("masked daily validation control is invalid")  # pragma: no cover


def _validate_shared_eligibility(results: tuple[MaskedNaiveControlResult, ...]) -> None:
    expected_result_count = len(_PHASES) * len(_SYMBOLS) * len(_CONTROLS)
    if len(results) != expected_result_count:
        raise RuntimeError("masked daily validation controls are incomplete")
    grouped: dict[tuple[_Phase, str], set[int]] = {}
    controls_by_group: dict[tuple[_Phase, str], set[_Control]] = {}
    for result in results:
        key = (result.phase, result.symbol)
        grouped.setdefault(key, set()).add(result.eligible_decision_count)
        controls_by_group.setdefault(key, set()).add(result.control)
        if not result.all_fills_local_paper or not result.replay_invariant_passed:
            raise RuntimeError("masked daily validation lost local-paper replay evidence")
        if result.fill_count != result.entry_count * 2:
            raise RuntimeError("masked daily validation fill count is incompatible")
    for phase in _PHASES:
        for symbol in _SYMBOLS:
            key = (phase, symbol)
            if grouped.get(key) is None or len(grouped[key]) != 1:
                raise RuntimeError("masked daily validation control eligibility is not identical")
            if controls_by_group.get(key) != set(_CONTROLS):
                raise RuntimeError("masked daily validation controls are incomplete")


def _summary_document(
    *,
    catalog: KisPaperPrivateDailyCatalog,
    audit: KisDailyEventBoundaryAudit,
    source_dataset_hash: str,
    control_results: tuple[MaskedNaiveControlResult, ...],
) -> dict[str, object]:
    phase_eligibility = [
        {
            "phase": phase,
            "symbol": symbol,
            "eligible_decision_count": next(
                result.eligible_decision_count
                for result in control_results
                if result.phase == phase and result.symbol == symbol
            ),
        }
        for phase in _PHASES
        for symbol in _SYMBOLS
    ]
    summary: dict[str, object] = {
        "schema_version": 1,
        "kind": KIS_DAILY_MASKED_NAIVE_VALIDATION_ID,
        "inputs": {
            "audit_artifact_sha256": audit.artifact_sha256,
            "catalog_full_dataset_hash": source_dataset_hash,
            "catalog_prefix_dataset_hash": catalog.dataset_hash,
            "catalog_index_hash": catalog.index_hash,
            "sidecar_dataset_hash": audit.lineage.sidecar_dataset_hash,
            "sidecar_manifest_hash": audit.lineage.sidecar_manifest_hash,
            "mask_identity": audit.mask_identity,
            "partition_identity": audit.partition_identity,
            "symbols": list(_SYMBOLS),
            "prefix_session_count": len(catalog.common_sessions),
        },
        "eligibility": {
            "candidate_geometry": (
                "four consecutive observed D1 sessions inside one named phase; "
                "all three intervening audited boundaries unmasked"
            ),
            "control_eligibility_identical": True,
            "phase_totals": phase_eligibility,
            "purge_or_embargo_consumed": False,
            "untouched_tail_materialized": False,
        },
        "execution": {
            "surface": "local_simulation",
            "source": LOCAL_PAPER_SOURCE,
            "horizon": "signal_close_then_next_open_entry_then_following_open_exit",
            "quantity": "1",
            "starting_cash": "10000",
            "fee_bps": "1",
            "slippage_bps": "0",
            "maximum_entries_per_temporary_replay": _MAX_ENTRIES_PER_TEMPORARY_REPLAY,
            "fixed_quantity_cash_deltas_aggregated_across_replays": True,
            "temporary_event_logs_deleted": True,
            "replay_checked_before_deletion": True,
        },
        "controls": [
            {
                "phase": result.phase,
                "symbol": result.symbol,
                "control": result.control,
                "eligible_decision_count": result.eligible_decision_count,
                "entry_count": result.entry_count,
                "replay_batch_count": result.replay_batch_count,
                "fill_count": result.fill_count,
                "starting_cash": str(result.starting_cash),
                "ending_cash": str(result.ending_cash),
                "pnl": str(result.pnl),
                "total_fees": str(result.total_fees),
                "all_fills_local_paper": result.all_fills_local_paper,
                "replay_invariant_passed": result.replay_invariant_passed,
            }
            for result in control_results
        ],
        "scope": {
            "retrospective_unadjusted_daily_plumbing_only": True,
            "total_return_eligible": False,
            "point_in_time_feature_eligible": False,
            "model_training_eligible": False,
            "model_selection_eligible": False,
            "paper_or_live_evidence": False,
            "claude_verdict": "supported-with-limits",
            "limitations": [
                (
                    "event-calendar-conditioned exclusions do not prove small distributions "
                    "or special actions"
                ),
                "unadjusted source lineage and external close semantics remain unverified",
                "no point-in-time availability, alpha, profitability, broker, or live conclusion",
            ],
        },
    }
    _assert_sanitized_summary(summary)
    return summary


def _prepare_artifact_root(*, artifact_root: Path | str, repo_root: Path | str | None) -> Path:
    root = Path(artifact_root)
    if root.is_symlink():
        raise ValueError("masked daily validation artifact root must not be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    try:
        resolved_root = root.resolve(strict=True)
    except OSError as error:
        raise ValueError("masked daily validation artifact root is invalid") from error
    if repo_root is not None:
        repository = Path(repo_root).resolve()
        if resolved_root.is_relative_to(repository):
            raise ValueError("masked daily validation artifacts must stay outside Git")
    _cleanup_stale_temporary_replays(resolved_root)
    return resolved_root


def _cleanup_stale_temporary_replays(artifact_root: Path) -> None:
    """Remove only abandoned, tool-owned temporary event directories.

    The final artifact must never retain raw local-paper fills.  A hard stop
    can bypass ``TemporaryDirectory`` cleanup, so recover before a new run.
    """

    prefix = f".{KIS_DAILY_MASKED_NAIVE_VALIDATION_ID}-"
    try:
        entries = tuple(artifact_root.iterdir())
    except OSError as error:
        raise ValueError("masked daily validation artifact root is unreadable") from error
    for entry in entries:
        if not entry.name.startswith(prefix):
            continue
        if entry.is_symlink() or not entry.is_dir():
            raise ValueError("masked daily validation temporary replay path is invalid")
        try:
            resolved_entry = entry.resolve(strict=True)
        except OSError as error:
            raise ValueError("masked daily validation temporary replay path is invalid") from error
        if not resolved_entry.is_relative_to(artifact_root):
            raise ValueError("masked daily validation temporary replay path escaped artifact root")
        try:
            shutil.rmtree(resolved_entry)
        except OSError as error:
            raise ValueError("masked daily validation temporary replay cleanup failed") from error


def _write_aggregate_summary(
    *,
    artifact_root: Path,
    summary: dict[str, object],
) -> tuple[Path, str]:
    _assert_sanitized_summary(summary)
    destination = artifact_root / f"{KIS_DAILY_MASKED_NAIVE_VALIDATION_ID}.json"
    if destination.is_symlink():
        raise ValueError("masked daily validation artifact path must not be a symlink")
    payload = (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8")
    content_hash = _sha256(payload)
    if destination.exists():
        try:
            existing = destination.read_bytes()
        except OSError as error:
            raise ValueError("masked daily validation artifact is unreadable") from error
        if existing != payload:
            raise ValueError(
                "masked daily validation artifact already exists with different content"
            )
        return destination, content_hash
    try:
        with destination.open("xb") as handle:
            handle.write(payload)
    except FileExistsError:
        return _write_aggregate_summary(artifact_root=artifact_root, summary=summary)
    except OSError as error:
        raise ValueError("masked daily validation artifact is unwritable") from error
    return destination, content_hash


def _assert_sanitized_summary(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ValueError("masked daily validation artifact keys must be strings")
            normalized = re.sub(r"[^a-z0-9]", "", key.lower())
            if normalized in _FORBIDDEN_SUMMARY_KEYS:
                raise ValueError("masked daily validation artifact contains raw market fields")
            _assert_sanitized_summary(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_sanitized_summary(nested)


def _require_sha256(value: str, label: str) -> None:
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"masked daily validation {label} must be sha256:<64 lowercase hex>")


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()
