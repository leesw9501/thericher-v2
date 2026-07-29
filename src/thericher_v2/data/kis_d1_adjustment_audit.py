"""Offline split-signature audit for the retained KIS Paper D1 history panel.

The audit examines fixed public split-session pairs in memory and writes only
source hashes plus categorical outcomes outside Git. It does not repair data,
qualify all corporate actions, or create a research/execution input.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.data.kis_paper_daily_history_panel import (
    KIS_PAPER_DAILY_HISTORY_CACHE_ROOT,
    KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
    KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS,
    KisPaperDailyHistoryPanel,
    build_kis_paper_daily_history_panel,
)
from thericher_v2.research.validation import _reject_repo_artifact_path, resolve_model_artifact_root

KIS_D1_ADJUSTMENT_AUDIT_ID = "kis-d1-adjustment-split-signature-audit-v1"
KIS_D1_ADJUSTMENT_AUDIT_VERSION = 1
KIS_D1_ADJUSTMENT_AUDIT_DIRECTORY = "data/kis-d1-adjustment-audit"
KIS_D1_DISCONTINUITY_CENSUS_ID = "kis-d1-unexplained-discontinuity-census-v2"
KIS_D1_DISCONTINUITY_CENSUS_VERSION = 2
KIS_D1_DISCONTINUITY_CENSUS_DIRECTORY = "data/kis-d1-discontinuity-census"
SPLIT_SIGNATURE_THRESHOLD_MULTIPLIER = Decimal("3")
_AUDITED_SYMBOLS = ("AAPL", "AMZN", "GOOGL", "NVDA")
_SPLIT_SESSION_PAIRS = MappingProxyType(
    {
        "AAPL": ((date(2020, 8, 28), date(2020, 8, 31)),),
        "AMZN": ((date(2022, 6, 3), date(2022, 6, 6)),),
        "GOOGL": ((date(2022, 7, 15), date(2022, 7, 18)),),
        "NVDA": (
            (date(2021, 7, 19), date(2021, 7, 20)),
            (date(2024, 6, 7), date(2024, 6, 10)),
        ),
    }
)
AuditStatus = Literal[
    "consistent_with_declared_unadjusted",
    "declared_unadjusted_falsified",
    "inconclusive",
]
SymbolStatus = Literal["signature_observed", "signature_absent", "inconclusive_pair"]
CensusStatus = Literal[
    "no_unexplained_large_discontinuity",
    "unexplained_large_discontinuity_observed",
    "inconclusive",
]
CensusSymbolStatus = Literal[
    "no_unexplained_large_discontinuity",
    "unexplained_large_discontinuity_observed",
    "inconclusive_pair",
]
_FORBIDDEN_OUTPUT_KEYS = frozenset(
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
        "timestamp",
        "timestamps",
        "date",
        "dates",
        "eventdate",
        "eventdates",
        "sourcepath",
        "workdir",
        "statesqlite",
        "eventjsonl",
        "eventlog",
    }
)


@dataclass(frozen=True, slots=True)
class KisD1AdjustmentAuditSource:
    """Hash-attested source metadata with no source path or row values."""

    dataset_id: str
    dataset_sha256: str
    index_sha256: str
    adjustment_mode: str

    def __post_init__(self) -> None:
        if (
            not self.dataset_id
            or not _is_sha256(self.dataset_sha256)
            or not _is_sha256(self.index_sha256)
            or self.adjustment_mode != KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE
        ):
            raise ValueError("KIS D1 adjustment audit source is invalid")

    def to_payload(self) -> dict[str, str]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_sha256": self.dataset_sha256,
            "index_sha256": self.index_sha256,
            "adjustment_mode": self.adjustment_mode,
        }


@dataclass(frozen=True, slots=True)
class KisD1SplitSignatureResult:
    """Categorical outcome for one fixed set of public split-session pairs."""

    symbol: str
    required_event_count: int
    complete_event_count: int
    signature_event_count: int
    status: SymbolStatus

    def __post_init__(self) -> None:
        expected_status: SymbolStatus
        if self.complete_event_count != self.required_event_count:
            expected_status = "inconclusive_pair"
        elif self.signature_event_count == self.required_event_count:
            expected_status = "signature_observed"
        else:
            expected_status = "signature_absent"
        if (
            self.symbol not in _AUDITED_SYMBOLS
            or self.required_event_count <= 0
            or not 0 <= self.complete_event_count <= self.required_event_count
            or not 0 <= self.signature_event_count <= self.complete_event_count
            or self.status != expected_status
        ):
            raise ValueError("KIS D1 split-signature result is invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "required_event_count": self.required_event_count,
            "complete_event_count": self.complete_event_count,
            "signature_event_count": self.signature_event_count,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class KisD1AdjustmentAudit:
    """One narrow source-semantics outcome, never a model/execution input."""

    source: KisD1AdjustmentAuditSource
    contract_sha256: str
    status: AuditStatus
    results_by_symbol: Mapping[str, KisD1SplitSignatureResult]

    def __post_init__(self) -> None:
        results = MappingProxyType(dict(self.results_by_symbol))
        expected_status = _aggregate_status(tuple(results.values()))
        if (
            not _is_sha256(self.contract_sha256)
            or tuple(results) != _AUDITED_SYMBOLS
            or any(result.symbol != symbol for symbol, result in results.items())
            or self.status != expected_status
        ):
            raise ValueError("KIS D1 adjustment audit is invalid")
        object.__setattr__(self, "results_by_symbol", results)

    @property
    def model_eligible(self) -> bool:
        return False

    @property
    def paper_trading_eligible(self) -> bool:
        return False

    def to_payload(self) -> dict[str, object]:
        return {
            "source": self.source.to_payload(),
            "contract_sha256": self.contract_sha256,
            "status": self.status,
            "results": [
                self.results_by_symbol[symbol].to_payload() for symbol in _AUDITED_SYMBOLS
            ],
            "scope": {
                "retrospective_kis_label_input_integrity_only": True,
                "adjustment_semantics_fully_verified": False,
                "corporate_action_qualified": False,
                "norgate_conformance_changed": False,
                "source_transfer_eligible": False,
                "model_eligible": False,
                "ranking_eligible": False,
                "pnl_or_profitability_claim": False,
                "paper_trading_eligible": False,
            },
        }


@dataclass(frozen=True, slots=True)
class KisD1AdjustmentAuditReceipt:
    """Immutable external receipt for one source-local audit."""

    audit: KisD1AdjustmentAudit
    audit_sha256: str
    receipt_path: Path
    receipt_sha256: str

    def __post_init__(self) -> None:
        if (
            not _is_sha256(self.audit_sha256)
            or not _is_sha256(self.receipt_sha256)
            or self.receipt_path.is_symlink()
            or not self.receipt_path.is_file()
        ):
            raise ValueError("KIS D1 adjustment audit receipt is invalid")


KisPanelLoader = Callable[[Path, Path | None], KisPaperDailyHistoryPanel]


@dataclass(frozen=True, slots=True)
class KisD1DiscontinuityCensusResult:
    """Aggregate discontinuity categories for one retained source stream."""

    symbol: str
    adjacent_pair_count: int
    complete_pair_count: int
    known_fixed_split_signature_count: int
    unexplained_large_discontinuity_count: int
    status: CensusSymbolStatus

    def __post_init__(self) -> None:
        expected_status: CensusSymbolStatus
        if self.complete_pair_count != self.adjacent_pair_count:
            expected_status = "inconclusive_pair"
        elif self.unexplained_large_discontinuity_count > 0:
            expected_status = "unexplained_large_discontinuity_observed"
        else:
            expected_status = "no_unexplained_large_discontinuity"
        if (
            self.symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or self.adjacent_pair_count < 0
            or not 0 <= self.complete_pair_count <= self.adjacent_pair_count
            or not 0 <= self.known_fixed_split_signature_count <= self.complete_pair_count
            or not 0 <= self.unexplained_large_discontinuity_count <= self.complete_pair_count
            or self.known_fixed_split_signature_count
            + self.unexplained_large_discontinuity_count
            > self.complete_pair_count
            or self.status != expected_status
        ):
            raise ValueError("KIS D1 discontinuity census result is invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "adjacent_pair_count": self.adjacent_pair_count,
            "complete_pair_count": self.complete_pair_count,
            "known_fixed_split_signature_count": self.known_fixed_split_signature_count,
            "unexplained_large_discontinuity_count": self.unexplained_large_discontinuity_count,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class KisD1DiscontinuityCensus:
    """A value-free complement census for the frozen KIS D1 source."""

    source: KisD1AdjustmentAuditSource
    contract_sha256: str
    status: CensusStatus
    results_by_symbol: Mapping[str, KisD1DiscontinuityCensusResult]

    def __post_init__(self) -> None:
        results = MappingProxyType(dict(self.results_by_symbol))
        expected_status = _aggregate_census_status(tuple(results.values()))
        if (
            not _is_sha256(self.contract_sha256)
            or tuple(results) != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or any(result.symbol != symbol for symbol, result in results.items())
            or self.status != expected_status
        ):
            raise ValueError("KIS D1 discontinuity census is invalid")
        object.__setattr__(self, "results_by_symbol", results)

    @property
    def model_eligible(self) -> bool:
        return False

    @property
    def paper_trading_eligible(self) -> bool:
        return False

    def to_payload(self) -> dict[str, object]:
        return {
            "source": self.source.to_payload(),
            "contract_sha256": self.contract_sha256,
            "status": self.status,
            "results": [
                self.results_by_symbol[symbol].to_payload()
                for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            ],
            "scope": {
                "source_semantics_observation_only": True,
                "unexplained_discontinuity_cause_identified": False,
                "adjustment_semantics_fully_verified": False,
                "corporate_action_qualified": False,
                "norgate_conformance_changed": False,
                "label_eligible": False,
                "source_transfer_eligible": False,
                "model_eligible": False,
                "ranking_eligible": False,
                "pnl_or_profitability_claim": False,
                "paper_trading_eligible": False,
            },
        }


@dataclass(frozen=True, slots=True)
class KisD1DiscontinuityCensusReceipt:
    """Immutable external receipt for one value-free source census."""

    census: KisD1DiscontinuityCensus
    census_sha256: str
    receipt_path: Path
    receipt_sha256: str

    def __post_init__(self) -> None:
        if (
            not _is_sha256(self.census_sha256)
            or not _is_sha256(self.receipt_sha256)
            or self.receipt_path.is_symlink()
            or not self.receipt_path.is_file()
        ):
            raise ValueError("KIS D1 discontinuity census receipt is invalid")


def build_kis_d1_discontinuity_census_receipt(
    *,
    artifact_root: Path | None = None,
    market_data_root: Path,
    repo_root: Path | None = None,
    panel_loader: KisPanelLoader | None = None,
) -> KisD1DiscontinuityCensusReceipt:
    """Reattest a frozen KIS panel and write one categorical census receipt."""

    root = _external_artifact_root(artifact_root or resolve_model_artifact_root(), repo_root)
    load_panel = panel_loader or _load_kis_panel
    panel = load_panel(Path(market_data_root), repo_root)
    census = assess_kis_d1_discontinuity_census(panel)
    census_payload = census.to_payload()
    census_sha256 = _sha256_json(census_payload)
    receipt_payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_d1_discontinuity_census_receipt",
        "version": KIS_D1_DISCONTINUITY_CENSUS_VERSION,
        "census_id": KIS_D1_DISCONTINUITY_CENSUS_ID,
        "census_sha256": census_sha256,
        "census": census_payload,
        "artifact_policy": {
            "external_artifact_only": True,
            "network_accessed": False,
            "credentials_accessed": False,
            "kis_accessed": False,
            "broker_accessed": False,
            "source_rows_persisted": False,
            "market_values_persisted": False,
            "returns_persisted": False,
            "event_dates_persisted": False,
            "per_pair_records_persisted": False,
            "labels_persisted": False,
            "predictions_persisted": False,
            "model_artifacts_persisted": False,
            "pnl_persisted": False,
        },
    }
    _reject_forbidden_output_keys(receipt_payload)
    target = root / KIS_D1_DISCONTINUITY_CENSUS_DIRECTORY / census_sha256[7:] / "receipt.json"
    _write_or_verify_json(target, receipt_payload)
    return KisD1DiscontinuityCensusReceipt(
        census=census,
        census_sha256=census_sha256,
        receipt_path=target,
        receipt_sha256=_sha256(target.read_bytes()),
    )


def assess_kis_d1_discontinuity_census(
    panel: KisPaperDailyHistoryPanel,
) -> KisD1DiscontinuityCensus:
    """Census only aggregate large retained-pair signatures in memory."""

    if panel.adjustment_mode != KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE:
        raise ValueError("KIS D1 adjustment mode is invalid")
    results: dict[str, KisD1DiscontinuityCensusResult] = {}
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        stream = panel.bars_by_symbol[symbol]
        adjacent_pair_count = 0
        complete_pair_count = 0
        known_signature_count = 0
        unexplained_count = 0
        for before, after in zip(stream.bars[:-1], stream.bars[1:], strict=True):
            adjacent_pair_count += 1
            if (
                not before.complete
                or not after.complete
                or before.close <= 0
                or after.close <= 0
            ):
                continue
            complete_pair_count += 1
            if not _has_split_signature(before.close, after.close):
                continue
            if _is_known_fixed_split(symbol, before.start_ts.date(), after.start_ts.date()):
                known_signature_count += 1
            else:
                unexplained_count += 1
        status: CensusSymbolStatus
        if complete_pair_count != adjacent_pair_count:
            status = "inconclusive_pair"
        elif unexplained_count > 0:
            status = "unexplained_large_discontinuity_observed"
        else:
            status = "no_unexplained_large_discontinuity"
        results[symbol] = KisD1DiscontinuityCensusResult(
            symbol=symbol,
            adjacent_pair_count=adjacent_pair_count,
            complete_pair_count=complete_pair_count,
            known_fixed_split_signature_count=known_signature_count,
            unexplained_large_discontinuity_count=unexplained_count,
            status=status,
        )
    source = KisD1AdjustmentAuditSource(
        dataset_id=panel.dataset_id,
        dataset_sha256=panel.dataset_hash,
        index_sha256=panel.index_hash,
        adjustment_mode=panel.adjustment_mode,
    )
    return KisD1DiscontinuityCensus(
        source=source,
        contract_sha256=_census_contract_sha256(),
        status=_aggregate_census_status(tuple(results.values())),
        results_by_symbol=results,
    )


def _aggregate_census_status(results: tuple[KisD1DiscontinuityCensusResult, ...]) -> CensusStatus:
    if any(result.status == "inconclusive_pair" for result in results):
        return "inconclusive"
    if any(
        result.status == "unexplained_large_discontinuity_observed" for result in results
    ):
        return "unexplained_large_discontinuity_observed"
    return "no_unexplained_large_discontinuity"


def _known_fixed_split_pairs() -> frozenset[tuple[str, date, date]]:
    return frozenset(
        (symbol, before_session, after_session)
        for symbol, pairs in _SPLIT_SESSION_PAIRS.items()
        for before_session, after_session in pairs
    )


def _is_known_fixed_split(symbol: str, before_session: date, after_session: date) -> bool:
    return (symbol, before_session, after_session) in _known_fixed_split_pairs()


def _census_contract_sha256() -> str:
    return _sha256_json(
        {
            "census_id": KIS_D1_DISCONTINUITY_CENSUS_ID,
            "version": KIS_D1_DISCONTINUITY_CENSUS_VERSION,
            "signature": "abs(log(close_later / close_earlier)) >= log(3)",
            "known_fixed_split_pairs": [
                {
                    "symbol": symbol,
                    "before_session": before_session.isoformat(),
                    "after_session": after_session.isoformat(),
                }
                for symbol in _AUDITED_SYMBOLS
                for before_session, after_session in _SPLIT_SESSION_PAIRS[symbol]
            ],
            "scan_symbols": list(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS),
            "pair_scope": "ordered_adjacent_retained_completed_d1_pairs",
        }
    )


def build_kis_d1_adjustment_audit_receipt(
    *,
    artifact_root: Path | None = None,
    market_data_root: Path,
    repo_root: Path | None = None,
    panel_loader: KisPanelLoader | None = None,
) -> KisD1AdjustmentAuditReceipt:
    """Reattest a frozen KIS panel and write one categorical external receipt."""

    root = _external_artifact_root(artifact_root or resolve_model_artifact_root(), repo_root)
    load_panel = panel_loader or _load_kis_panel
    panel = load_panel(Path(market_data_root), repo_root)
    audit = assess_kis_d1_adjustment_audit(panel)
    audit_payload = audit.to_payload()
    audit_sha256 = _sha256_json(audit_payload)
    receipt_payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_d1_adjustment_audit_receipt",
        "version": KIS_D1_ADJUSTMENT_AUDIT_VERSION,
        "audit_id": KIS_D1_ADJUSTMENT_AUDIT_ID,
        "audit_sha256": audit_sha256,
        "audit": audit_payload,
        "artifact_policy": {
            "external_artifact_only": True,
            "network_accessed": False,
            "credentials_accessed": False,
            "kis_accessed": False,
            "broker_accessed": False,
            "source_rows_persisted": False,
            "market_values_persisted": False,
            "returns_persisted": False,
            "event_dates_persisted": False,
            "labels_persisted": False,
            "predictions_persisted": False,
            "model_artifacts_persisted": False,
            "pnl_persisted": False,
        },
    }
    _reject_forbidden_output_keys(receipt_payload)
    target = root / KIS_D1_ADJUSTMENT_AUDIT_DIRECTORY / audit_sha256[7:] / "receipt.json"
    _write_or_verify_json(target, receipt_payload)
    return KisD1AdjustmentAuditReceipt(
        audit=audit,
        audit_sha256=audit_sha256,
        receipt_path=target,
        receipt_sha256=_sha256(target.read_bytes()),
    )


def assess_kis_d1_adjustment_audit(panel: KisPaperDailyHistoryPanel) -> KisD1AdjustmentAudit:
    """Evaluate fixed pair signatures in memory without exposing values or dates."""

    if panel.adjustment_mode != KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE:
        raise ValueError("KIS D1 adjustment mode is invalid")
    results: dict[str, KisD1SplitSignatureResult] = {}
    for symbol in _AUDITED_SYMBOLS:
        by_session = {bar.start_ts.date(): bar for bar in panel.bars_by_symbol[symbol].bars}
        required_pairs = _SPLIT_SESSION_PAIRS[symbol]
        complete_count = 0
        signature_count = 0
        for before_session, after_session in required_pairs:
            before = by_session.get(before_session)
            after = by_session.get(after_session)
            if before is None or after is None or before.close <= 0 or after.close <= 0:
                continue
            complete_count += 1
            if _has_split_signature(before.close, after.close):
                signature_count += 1
        status: SymbolStatus
        if complete_count != len(required_pairs):
            status = "inconclusive_pair"
        elif signature_count == len(required_pairs):
            status = "signature_observed"
        else:
            status = "signature_absent"
        results[symbol] = KisD1SplitSignatureResult(
            symbol=symbol,
            required_event_count=len(required_pairs),
            complete_event_count=complete_count,
            signature_event_count=signature_count,
            status=status,
        )
    source = KisD1AdjustmentAuditSource(
        dataset_id=panel.dataset_id,
        dataset_sha256=panel.dataset_hash,
        index_sha256=panel.index_hash,
        adjustment_mode=panel.adjustment_mode,
    )
    return KisD1AdjustmentAudit(
        source=source,
        contract_sha256=_contract_sha256(),
        status=_aggregate_status(tuple(results.values())),
        results_by_symbol=results,
    )


def _load_kis_panel(market_data_root: Path, repo_root: Path | None) -> KisPaperDailyHistoryPanel:
    cache_root = _rebase_market_data_path(
        KIS_PAPER_DAILY_HISTORY_CACHE_ROOT,
        market_data_root=market_data_root,
    )
    return build_kis_paper_daily_history_panel(cache_root=cache_root, repo_root=repo_root)


def _has_split_signature(before: Decimal, after: Decimal) -> bool:
    """Equivalent to abs(log(after / before)) >= log(3), using Decimal only."""

    return after / before >= SPLIT_SIGNATURE_THRESHOLD_MULTIPLIER or before / after >= (
        SPLIT_SIGNATURE_THRESHOLD_MULTIPLIER
    )


def _aggregate_status(results: tuple[KisD1SplitSignatureResult, ...]) -> AuditStatus:
    if any(result.status == "inconclusive_pair" for result in results):
        return "inconclusive"
    if any(result.status == "signature_absent" for result in results):
        return "declared_unadjusted_falsified"
    return "consistent_with_declared_unadjusted"


def _contract_sha256() -> str:
    return _sha256_json(
        {
            "audit_id": KIS_D1_ADJUSTMENT_AUDIT_ID,
            "version": KIS_D1_ADJUSTMENT_AUDIT_VERSION,
            "signature": "abs(log(close_after / close_before)) >= log(3)",
            "events": [
                {
                    "symbol": symbol,
                    "before_session": before_session.isoformat(),
                    "after_session": after_session.isoformat(),
                }
                for symbol in _AUDITED_SYMBOLS
                for before_session, after_session in _SPLIT_SESSION_PAIRS[symbol]
            ],
        }
    )


def _rebase_market_data_path(path: Path, *, market_data_root: Path) -> Path:
    default_root = Path("D:/market_data")
    try:
        relative = Path(path).relative_to(default_root)
    except ValueError as error:
        raise ValueError(
            "KIS D1 adjustment-audit cache must be beneath market-data root"
        ) from error
    return Path(market_data_root) / relative


def _external_artifact_root(root: Path, repo_root: Path | None) -> Path:
    candidate = Path(root)
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError("KIS D1 adjustment-audit artifact root is invalid")
    _reject_repo_artifact_path(candidate, repo_root or Path.cwd())
    return candidate.resolve()


def _write_or_verify_json(path: Path, payload: Mapping[str, object]) -> None:
    encoded = _json_bytes(payload)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or path.read_bytes() != encoded:
            raise FileExistsError("KIS D1 adjustment audit receipt is immutable")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{uuid.uuid4().hex}.stage")
    try:
        staging.write_bytes(encoded)
        if path.exists() or path.is_symlink():
            raise FileExistsError("KIS D1 adjustment audit receipt is immutable")
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)


def _reject_forbidden_output_keys(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = "".join(character for character in str(key).lower() if character.isalnum())
            if normalized in _FORBIDDEN_OUTPUT_KEYS:
                raise ValueError("KIS D1 adjustment audit receipt contains a raw field")
            _reject_forbidden_output_keys(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _reject_forbidden_output_keys(nested)


def _json_bytes(payload: Mapping[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256_json(payload: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )
