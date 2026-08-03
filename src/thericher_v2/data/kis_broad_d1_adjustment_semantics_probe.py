"""One small, opaque KIS Paper daily-representation capability probe.

The probe consumes the already-attested broad-D1 panel only in memory.  It
compares two provider request values for a fixed anonymous witness sample, then
writes aggregate-only evidence outside Git.  It cannot alter the retained
``MODP=0`` cache, establish provider semantics, or supply a research or
execution input.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Protocol

from thericher_v2.contracts import SCHEMA_VERSION, Bar
from thericher_v2.data.kis_broad_d1_geometry_audit import (
    KisBroadD1GeometryAudit,
    KisBroadD1GeometryAuditSpec,
    build_kis_broad_d1_geometry_audit_from_selection,
)
from thericher_v2.data.kis_paper_daily_broad_panel import (
    KisPaperDailyBroadPanelSelection,
    load_materialized_kis_paper_daily_broad_panel_selection,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperDailyAdjustmentProbeQuery,
    KisPaperDailyRawPage,
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataError,
)
from thericher_v2.research.artifact_paths import ensure_external_artifact_directory

KIS_BROAD_D1_ADJUSTMENT_SEMANTICS_PROBE_ID = "kis-broad-d1-adjustment-semantics-probe-v1"
KIS_BROAD_D1_ADJUSTMENT_SEMANTICS_PROBE_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts"
)
KIS_BROAD_D1_ADJUSTMENT_SEMANTICS_PROBE_DIRECTORY = (
    "data/kis-broad-d1-adjustment-semantics-probe-v1"
)
KIS_BROAD_D1_ADJUSTMENT_SEMANTICS_PROBE_MAX_WITNESS_COUNT = 2
KIS_BROAD_D1_ADJUSTMENT_SEMANTICS_PROBE_MODE_SEQUENCE = ("0", "1", "0")
_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)

ProbeStatus = Literal["unchanged", "changed", "unsupported", "unavailable", "inconsistent"]
ProbeReason = Literal[
    "all_pairs_equal",
    "all_pairs_different",
    "alternate_representation_rejected",
    "authentication_unavailable",
    "comparison_row_absent",
    "daily_response_unavailable",
    "mixed_comparison_result",
    "mode_zero_nonrepeatable",
    "no_fixed_witness",
]


class KisBroadD1AdjustmentSemanticsProbeClient(Protocol):
    """The entire KIS surface needed by the bounded Data-owned probe."""

    @property
    def call_counts(self) -> KisPaperMarketDataCallCounts: ...

    def ensure_authenticated(self) -> None: ...

    def fetch_daily_raw_page(
        self, query: KisPaperDailyAdjustmentProbeQuery
    ) -> KisPaperDailyRawPage: ...


@dataclass(frozen=True, slots=True)
class KisBroadD1AdjustmentSemanticsProbeSource:
    """Aggregate identity of the attested panel and frozen event selector."""

    dataset_hash: str
    manifest_sha256: str
    materialization_receipt_sha256: str
    source_index_hash: str
    selected_target_key_set_hash: str
    common_grid_sha256: str
    geometry_contract_sha256: str
    geometry_event_mask_sha256: str
    selected_target_count: int
    grid_count: int
    fixed_event_count: int

    def __post_init__(self) -> None:
        if (
            any(
                not _is_sha256(value)
                for value in (
                    self.dataset_hash,
                    self.manifest_sha256,
                    self.materialization_receipt_sha256,
                    self.source_index_hash,
                    self.selected_target_key_set_hash,
                    self.common_grid_sha256,
                    self.geometry_contract_sha256,
                    self.geometry_event_mask_sha256,
                )
            )
            or self.selected_target_count != 128
            or self.grid_count != 800
            or self.fixed_event_count < 0
        ):
            raise ValueError("KIS broad D1 adjustment probe source is invalid")

    def payload(self) -> dict[str, object]:
        return {
            "dataset_hash": self.dataset_hash,
            "manifest_sha256": self.manifest_sha256,
            "materialization_receipt_sha256": self.materialization_receipt_sha256,
            "source_index_hash": self.source_index_hash,
            "selected_target_key_set_hash": self.selected_target_key_set_hash,
            "common_grid_sha256": self.common_grid_sha256,
            "geometry_contract_sha256": self.geometry_contract_sha256,
            "geometry_event_mask_sha256": self.geometry_event_mask_sha256,
            "selected_target_count": self.selected_target_count,
            "grid_count": self.grid_count,
            "fixed_event_count": self.fixed_event_count,
        }


@dataclass(frozen=True, slots=True, repr=False)
class _AdjustmentWitness:
    """One in-memory-only panel event identity; never serialized directly."""

    target_key: str
    by_date: str

    def __post_init__(self) -> None:
        symbol, separator, exchange = self.target_key.partition("/")
        if (
            separator != "/"
            or not symbol.isascii()
            or not symbol.isalnum()
            or len(exchange) != 3
            or not exchange.isascii()
            or not exchange.isalpha()
            or len(self.by_date) != 8
            or not self.by_date.isdigit()
        ):
            raise ValueError("KIS broad D1 adjustment probe witness is invalid")

    @property
    def symbol(self) -> str:
        return self.target_key.partition("/")[0]

    @property
    def exchange(self) -> str:
        return self.target_key.partition("/")[2]

    def query(
        self,
        mode: Literal["0", "1"],
        scope: Mapping[str, frozenset[str]],
    ) -> KisPaperDailyAdjustmentProbeQuery:
        return KisPaperDailyAdjustmentProbeQuery(
            symbol=self.symbol,
            exchange=self.exchange,
            by_date=self.by_date,
            adjustment_mode=mode,
            approved_symbol_exchanges=scope,
        )

    def private_key(self) -> str:
        return f"{self.target_key}:{self.by_date}"


@dataclass(frozen=True, slots=True)
class KisBroadD1AdjustmentSemanticsProbePlan:
    """Frozen, non-persistent input to a single serial KIS comparison."""

    source: KisBroadD1AdjustmentSemanticsProbeSource
    witness_identity_sha256: str
    witnesses: tuple[_AdjustmentWitness, ...]

    def __post_init__(self) -> None:
        witnesses = tuple(self.witnesses)
        if (
            not isinstance(self.source, KisBroadD1AdjustmentSemanticsProbeSource)
            or not _is_sha256(self.witness_identity_sha256)
            or len(witnesses) > KIS_BROAD_D1_ADJUSTMENT_SEMANTICS_PROBE_MAX_WITNESS_COUNT
            or tuple(sorted((item.target_key, item.by_date) for item in witnesses))
            != tuple((item.target_key, item.by_date) for item in witnesses)
            or len({item.private_key() for item in witnesses}) != len(witnesses)
        ):
            raise ValueError("KIS broad D1 adjustment probe plan is invalid")
        object.__setattr__(self, "witnesses", witnesses)

    @property
    def daily_symbol_exchanges(self) -> Mapping[str, frozenset[str]]:
        scope: dict[str, set[str]] = {}
        for witness in self.witnesses:
            scope.setdefault(witness.symbol, set()).add(witness.exchange)
        return MappingProxyType(
            {
                symbol: frozenset(exchanges)
                for symbol, exchanges in sorted(scope.items())
            }
        )


@dataclass(frozen=True, slots=True)
class KisBroadD1AdjustmentSemanticsProbeOutcome:
    """Aggregate-only result; no witness identity or market value is retained."""

    source: KisBroadD1AdjustmentSemanticsProbeSource
    status: ProbeStatus
    reason: ProbeReason
    witness_identity_sha256: str
    witness_count: int
    accepted_daily_response_count: int
    categorical_error_count: int
    call_counts: KisPaperMarketDataCallCounts

    def __post_init__(self) -> None:
        expected = {
            "unchanged": "all_pairs_equal",
            "changed": "all_pairs_different",
            "unsupported": "alternate_representation_rejected",
        }
        if (
            not isinstance(self.source, KisBroadD1AdjustmentSemanticsProbeSource)
            or self.status
            not in {"unchanged", "changed", "unsupported", "unavailable", "inconsistent"}
            or self.reason not in {
                "all_pairs_equal",
                "all_pairs_different",
                "alternate_representation_rejected",
                "authentication_unavailable",
                "comparison_row_absent",
                "daily_response_unavailable",
                "mixed_comparison_result",
                "mode_zero_nonrepeatable",
                "no_fixed_witness",
            }
            or (self.status in expected and self.reason != expected[self.status])
            or (
                self.status == "inconsistent"
                and self.reason not in {"mixed_comparison_result", "mode_zero_nonrepeatable"}
            )
            or (
                self.status == "unavailable"
                and self.reason
                not in {
                    "authentication_unavailable",
                    "comparison_row_absent",
                    "daily_response_unavailable",
                    "no_fixed_witness",
                }
            )
            or not _is_sha256(self.witness_identity_sha256)
            or not (
                0
                <= self.witness_count
                <= KIS_BROAD_D1_ADJUSTMENT_SEMANTICS_PROBE_MAX_WITNESS_COUNT
            )
            or self.accepted_daily_response_count < 0
            or self.categorical_error_count < 0
            or self.call_counts.token_attempts < 0
            or self.call_counts.daily_page_attempts < self.accepted_daily_response_count
            or self.call_counts.minute_page_attempts != 0
        ):
            raise ValueError("KIS broad D1 adjustment probe outcome is invalid")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": KIS_BROAD_D1_ADJUSTMENT_SEMANTICS_PROBE_ID,
            "status": self.status,
            "reason": self.reason,
            "source": self.source.payload(),
            "comparison": {
                "mode_sequence": list(KIS_BROAD_D1_ADJUSTMENT_SEMANTICS_PROBE_MODE_SEQUENCE),
                "witness_count": self.witness_count,
                "witness_identity_sha256": self.witness_identity_sha256,
                "fixed_selector": "within_bar_high_low_ratio_gt_2",
                "provider_mode_semantics_proven": False,
            },
            "request_counts": {
                "token_attempts": self.call_counts.token_attempts,
                "daily_page_attempts": self.call_counts.daily_page_attempts,
                "minute_page_attempts": self.call_counts.minute_page_attempts,
                "accepted_daily_response_count": self.accepted_daily_response_count,
                "categorical_error_count": self.categorical_error_count,
            },
            "scope": {
                "current_cache_rewritten": False,
                "raw_cache_representation_reinterpreted": False,
                "point_in_time_qualified": False,
                "corporate_action_qualified": False,
                "model_eligible": False,
                "ranking_eligible": False,
                "paper_trading_eligible": False,
                "live_trading_eligible": False,
            },
            "artifact_policy": {
                "external_artifact_only": True,
                "raw_market_data_persisted": False,
                "raw_rows_persisted": False,
                "witness_identity_persisted": False,
                "credentials_persisted": False,
                "account_or_broker_payload_persisted": False,
                "model_artifact_persisted": False,
                "gpu_used": False,
            },
        }


@dataclass(frozen=True, slots=True)
class KisBroadD1AdjustmentSemanticsProbeRun:
    outcome: KisBroadD1AdjustmentSemanticsProbeOutcome
    run_directory: Path
    receipt_path: Path
    receipt_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.outcome, KisBroadD1AdjustmentSemanticsProbeOutcome)
            or not self.run_directory.is_dir()
            or self.run_directory.is_symlink()
            or not self.receipt_path.is_file()
            or self.receipt_path.is_symlink()
            or not _is_sha256(self.receipt_sha256)
            or _sha256_bytes(self.receipt_path.read_bytes()) != self.receipt_sha256
        ):
            raise ValueError("KIS broad D1 adjustment probe run is invalid")


def prepare_kis_broad_d1_adjustment_semantics_probe(
    selection: KisPaperDailyBroadPanelSelection,
) -> KisBroadD1AdjustmentSemanticsProbePlan:
    """Freeze a lexicographic in-memory witness sample from the audited panel."""

    if not isinstance(selection, KisPaperDailyBroadPanelSelection):
        raise TypeError("KIS broad D1 adjustment probe requires a selected panel")
    audit = build_kis_broad_d1_geometry_audit_from_selection(
        selection,
        spec=KisBroadD1GeometryAuditSpec(),
    )
    source = _source_from_selection(selection, audit)
    witnesses = _select_fixed_witnesses(selection)
    return KisBroadD1AdjustmentSemanticsProbePlan(
        source=source,
        witness_identity_sha256=_sha256_payload(
            {"witnesses": [item.private_key() for item in witnesses]}
        ),
        witnesses=witnesses,
    )


def load_kis_broad_d1_adjustment_semantics_probe_plan(
    *,
    manifest_path: Path | str,
    materialization_receipt_path: Path | str,
    cache_root: Path | str,
    panel_root: Path | str,
    repo_root: Path | str | None = None,
) -> KisBroadD1AdjustmentSemanticsProbePlan:
    """Reattach the exact fixed panel before selecting anonymous witnesses."""

    selection = load_materialized_kis_paper_daily_broad_panel_selection(
        manifest_path,
        materialization_receipt_path=materialization_receipt_path,
        cohort_target_count=128,
        minimum_bar_count=801,
        common_session_count=800,
        terminal_buffer_sessions=1,
        raw_byte_attestation_limit=512,
        cache_root=cache_root,
        panel_root=panel_root,
        repo_root=repo_root,
    )
    return prepare_kis_broad_d1_adjustment_semantics_probe(selection)


def assess_kis_broad_d1_adjustment_semantics_probe(
    plan: KisBroadD1AdjustmentSemanticsProbePlan,
    client: KisBroadD1AdjustmentSemanticsProbeClient | None,
) -> KisBroadD1AdjustmentSemanticsProbeOutcome:
    """Run exactly one bounded comparison sequence or close it categorically."""

    if not isinstance(plan, KisBroadD1AdjustmentSemanticsProbePlan):
        raise TypeError("KIS broad D1 adjustment probe requires a frozen plan")
    if not plan.witnesses:
        return _outcome(
            plan,
            status="unavailable",
            reason="no_fixed_witness",
            accepted_daily_response_count=0,
            categorical_error_count=0,
            call_counts=_zero_call_counts(),
        )
    if client is None:
        raise TypeError("KIS broad D1 adjustment probe client is required for witnesses")
    try:
        client.ensure_authenticated()
    except KisPaperMarketDataError:
        return _outcome(
            plan,
            status="unavailable",
            reason="authentication_unavailable",
            accepted_daily_response_count=0,
            categorical_error_count=1,
            call_counts=client.call_counts,
        )

    accepted = 0
    pair_differences: list[bool] = []
    scope = plan.daily_symbol_exchanges
    for witness in plan.witnesses:
        fingerprints: list[str] = []
        for mode in KIS_BROAD_D1_ADJUSTMENT_SEMANTICS_PROBE_MODE_SEQUENCE:
            try:
                page = client.fetch_daily_raw_page(witness.query(mode, scope))
            except KisPaperMarketDataError as error:
                return _outcome(
                    plan,
                    status=(
                        "unsupported"
                        if mode == "1" and str(error) == "daily_response_rejected"
                        else "unavailable"
                    ),
                    reason=(
                        "alternate_representation_rejected"
                        if mode == "1" and str(error) == "daily_response_rejected"
                        else "daily_response_unavailable"
                    ),
                    accepted_daily_response_count=accepted,
                    categorical_error_count=1,
                    call_counts=client.call_counts,
                )
            row = next((item for item in page.rows if item.xymd == witness.by_date), None)
            if row is None:
                return _outcome(
                    plan,
                    status="unavailable",
                    reason="comparison_row_absent",
                    accepted_daily_response_count=accepted + 1,
                    categorical_error_count=1,
                    call_counts=client.call_counts,
                )
            fingerprints.append(_row_fingerprint(row.as_document()))
            accepted += 1
        if fingerprints[0] != fingerprints[2]:
            return _outcome(
                plan,
                status="inconsistent",
                reason="mode_zero_nonrepeatable",
                accepted_daily_response_count=accepted,
                categorical_error_count=0,
                call_counts=client.call_counts,
            )
        pair_differences.append(fingerprints[0] != fingerprints[1])

    if all(not item for item in pair_differences):
        return _outcome(
            plan,
            status="unchanged",
            reason="all_pairs_equal",
            accepted_daily_response_count=accepted,
            categorical_error_count=0,
            call_counts=client.call_counts,
        )
    if all(pair_differences):
        return _outcome(
            plan,
            status="changed",
            reason="all_pairs_different",
            accepted_daily_response_count=accepted,
            categorical_error_count=0,
            call_counts=client.call_counts,
        )
    return _outcome(
        plan,
        status="inconsistent",
        reason="mixed_comparison_result",
        accepted_daily_response_count=accepted,
        categorical_error_count=0,
        call_counts=client.call_counts,
    )


def run_kis_broad_d1_adjustment_semantics_probe(
    *,
    plan: KisBroadD1AdjustmentSemanticsProbePlan,
    client: KisBroadD1AdjustmentSemanticsProbeClient | None,
    artifact_root: Path | str = KIS_BROAD_D1_ADJUSTMENT_SEMANTICS_PROBE_ARTIFACT_ROOT,
    run_label: str,
    repo_root: Path | str | None = None,
) -> KisBroadD1AdjustmentSemanticsProbeRun:
    """Persist exactly one aggregate receipt below the external artifact root."""

    if not _RUN_LABEL.fullmatch(run_label):
        raise ValueError("KIS broad D1 adjustment probe run label is invalid")
    repository = Path(repo_root or Path.cwd()).resolve()
    root = ensure_external_artifact_directory(
        Path(artifact_root),
        repository,
        *KIS_BROAD_D1_ADJUSTMENT_SEMANTICS_PROBE_DIRECTORY.split("/"),
    )
    run_directory = root / run_label
    if run_directory.exists() or run_directory.is_symlink():
        raise FileExistsError("KIS broad D1 adjustment probe artifact is immutable")
    run_directory.mkdir()
    if run_directory.is_symlink() or run_directory.resolve(strict=True) != run_directory:
        raise ValueError("KIS broad D1 adjustment probe artifact path is invalid")
    outcome = assess_kis_broad_d1_adjustment_semantics_probe(plan, client)
    receipt_path = run_directory / "summary.json"
    receipt_sha256 = _write_json_new(receipt_path, outcome.payload())
    return KisBroadD1AdjustmentSemanticsProbeRun(
        outcome=outcome,
        run_directory=run_directory,
        receipt_path=receipt_path,
        receipt_sha256=receipt_sha256,
    )


def _source_from_selection(
    selection: KisPaperDailyBroadPanelSelection,
    audit: KisBroadD1GeometryAudit,
) -> KisBroadD1AdjustmentSemanticsProbeSource:
    return KisBroadD1AdjustmentSemanticsProbeSource(
        dataset_hash=selection.dataset_hash,
        manifest_sha256=selection.manifest_sha256,
        materialization_receipt_sha256=selection.materialization_receipt_sha256,
        source_index_hash=selection.index_sha256,
        selected_target_key_set_hash=selection.selected_target_key_set_hash,
        common_grid_sha256=audit.source.common_session_grid_sha256,
        geometry_contract_sha256=audit.contract_sha256,
        geometry_event_mask_sha256=audit.feature_event_mask_sha256,
        selected_target_count=len(selection.selected_target_keys),
        grid_count=selection.common_session_count,
        fixed_event_count=audit.feature_event_count,
    )


def _select_fixed_witnesses(
    selection: KisPaperDailyBroadPanelSelection,
) -> tuple[_AdjustmentWitness, ...]:
    reference = selection.bars_by_target[selection.selected_target_keys[0]].bars
    grid_start = -(selection.common_session_count + selection.terminal_buffer_sessions)
    grid_end = -selection.terminal_buffer_sessions
    grid = tuple(item.start_ts for item in reference[grid_start:grid_end])
    candidates: list[_AdjustmentWitness] = []
    for target_key in selection.selected_target_keys:
        by_start = {item.start_ts: item for item in selection.bars_by_target[target_key].bars}
        for start in grid:
            record = by_start[start]
            if _is_fixed_range_event(record):
                candidates.append(
                    _AdjustmentWitness(
                        target_key=target_key,
                        by_date=start.strftime("%Y%m%d"),
                    )
                )
    return tuple(sorted(candidates, key=lambda item: (item.target_key, item.by_date))[:2])


def _is_fixed_range_event(record: Bar) -> bool:
    return float(record.high) / float(record.low) > 2.0


def _outcome(
    plan: KisBroadD1AdjustmentSemanticsProbePlan,
    *,
    status: ProbeStatus,
    reason: ProbeReason,
    accepted_daily_response_count: int,
    categorical_error_count: int,
    call_counts: KisPaperMarketDataCallCounts,
) -> KisBroadD1AdjustmentSemanticsProbeOutcome:
    return KisBroadD1AdjustmentSemanticsProbeOutcome(
        source=plan.source,
        status=status,
        reason=reason,
        witness_identity_sha256=plan.witness_identity_sha256,
        witness_count=len(plan.witnesses),
        accepted_daily_response_count=accepted_daily_response_count,
        categorical_error_count=categorical_error_count,
        call_counts=call_counts,
    )


def _row_fingerprint(row: Mapping[str, str]) -> str:
    return _sha256_payload({"provider_row": dict(sorted(row.items()))})


def _zero_call_counts() -> KisPaperMarketDataCallCounts:
    return KisPaperMarketDataCallCounts(
        token_attempts=0,
        minute_page_attempts=0,
        daily_page_attempts=0,
    )


def _write_json_new(path: Path, payload: Mapping[str, object]) -> str:
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    try:
        descriptor = os.open(
            str(path),
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
            0o600,
        )
    except FileExistsError as error:
        raise FileExistsError("KIS broad D1 adjustment probe receipt is immutable") from error
    try:
        remaining = memoryview(encoded)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("KIS broad D1 adjustment probe receipt write failed")
            remaining = remaining[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return _sha256_bytes(encoded)


def _sha256_payload(payload: Mapping[str, object]) -> str:
    return _sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None
