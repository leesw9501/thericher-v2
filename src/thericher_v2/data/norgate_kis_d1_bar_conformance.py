"""Fixed, offline D1 relationship conformance check for Norgate and KIS."""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_left
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, time
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_daily import (
    KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
    KisPaperPrivateDailyCatalog,
    load_kis_paper_private_daily_catalog,
)
from thericher_v2.data.norgate_d1_diagnostic_source import (
    VerifiedNorgateD1Panel,
    load_verified_norgate_d1_diagnostic_panel,
)
from thericher_v2.research.historical_kis_campaign import HISTORICAL_KIS_DAILY_TARGET_KEYS

NORGATE_KIS_D1_BAR_CONFORMANCE_ID = "norgate-kis-d1-bar-conformance-v1"

_VERSION = 1
_REQUIRED_SYMBOLS = ("SPY", "QQQ")
# These hashes pin the same private QQQ/SPY source vintage used by the prior
# sequence contract.  Keep this offline check independent of its model module.
_HISTORICAL_KIS_DAILY_EXPECTED_INDEX_HASH = (
    "sha256:e0bb847994a97b1df1181b0013fabcb784d979c7c366f686940e563cb01ac660"
)
_HISTORICAL_KIS_DAILY_EXPECTED_FULL_DATASET_HASH = (
    "sha256:78b00556ddbc8bcfb0c4d1bb67e004e4a4c4ff035a8c348b2516b842fa397718"
)
_PRICE_TOLERANCE = Decimal("0.0005")
_VOLUME_TOLERANCE = Decimal("0.05")
_MIN_AGREEMENT_RATE = Decimal("0.95")
_DISCONTINUITY_MOVE = Decimal("0.20")
_PRICE_FIELDS = ("close_to_close", "open_to_close", "high_to_open", "low_to_open")
_VOLUME_FIELD = "volume_ratio"
_FIELD_ORDER = (*_PRICE_FIELDS, _VOLUME_FIELD)
_STRATA = ("quiet", "discontinuity_adjacent")

ConformanceStatus = Literal["conforming_with_limits", "nonconforming", "input_unavailable"]
EvidenceStatus = Literal["pass", "nonconforming", "input_unavailable"]


@dataclass(frozen=True, slots=True)
class NorgateKisD1FieldEvidence:
    """Source-safe aggregate evidence for one symbol, relationship, and stratum."""

    symbol: str
    field_id: str
    stratum: str
    status: EvidenceStatus
    aligned_sample_count: int
    aligned_agreement_count: int
    backward_sample_count: int
    backward_agreement_count: int
    forward_sample_count: int
    forward_agreement_count: int

    def __post_init__(self) -> None:
        if (
            self.symbol not in _REQUIRED_SYMBOLS
            or self.field_id not in _FIELD_ORDER
            or self.stratum not in _STRATA
            or self.status not in {"pass", "nonconforming", "input_unavailable"}
            or any(
                not isinstance(value, int) or isinstance(value, bool) or value < 0
                for value in (
                    self.aligned_sample_count,
                    self.aligned_agreement_count,
                    self.backward_sample_count,
                    self.backward_agreement_count,
                    self.forward_sample_count,
                    self.forward_agreement_count,
                )
            )
            or self.aligned_agreement_count > self.aligned_sample_count
            or self.backward_agreement_count > self.backward_sample_count
            or self.forward_agreement_count > self.forward_sample_count
        ):
            raise ValueError("Norgate/KIS D1 field evidence is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "field_id": self.field_id,
            "stratum": self.stratum,
            "status": self.status,
            "aligned": _aggregate_payload(
                self.aligned_sample_count, self.aligned_agreement_count
            ),
            "backward_shift": _aggregate_payload(
                self.backward_sample_count, self.backward_agreement_count
            ),
            "forward_shift": _aggregate_payload(
                self.forward_sample_count, self.forward_agreement_count
            ),
        }


@dataclass(frozen=True, slots=True)
class NorgateKisD1BarConformanceResult:
    """Immutable receipt handle for the fixed offline comparison."""

    status: ConformanceStatus
    receipt_path: Path
    receipt_sha256: str
    norgate_dataset_hash: str
    norgate_manifest_hash: str
    kis_dataset_hash: str
    kis_index_hash: str
    evidence: tuple[NorgateKisD1FieldEvidence, ...]

    def __post_init__(self) -> None:
        if (
            self.status not in {"conforming_with_limits", "nonconforming", "input_unavailable"}
            or not _is_sha256(self.receipt_sha256)
            or any(
                not _is_sha256(value)
                for value in (
                    self.norgate_dataset_hash,
                    self.norgate_manifest_hash,
                    self.kis_dataset_hash,
                    self.kis_index_hash,
                )
            )
            or not self.receipt_path.is_file()
            or self.receipt_path.is_symlink()
            or len(self.evidence) != len(_REQUIRED_SYMBOLS) * len(_FIELD_ORDER) * len(_STRATA)
        ):
            raise ValueError("Norgate/KIS D1 conformance result is invalid")

    def safe_payload(self) -> dict[str, object]:
        return _safe_payload(
            status=self.status,
            norgate_dataset_hash=self.norgate_dataset_hash,
            norgate_manifest_hash=self.norgate_manifest_hash,
            kis_dataset_hash=self.kis_dataset_hash,
            kis_index_hash=self.kis_index_hash,
            evidence=self.evidence,
        )


def build_norgate_kis_d1_bar_conformance_receipt(
    *,
    snapshot_dir: Path,
    cache_root: Path,
    artifact_root: Path,
    expected_norgate_dataset_hash: str,
    expected_norgate_manifest_hash: str,
    repo_root: Path | None = None,
) -> NorgateKisD1BarConformanceResult:
    """Reattest pinned offline sources and write one aggregate-only receipt."""

    root = _external_artifact_root(artifact_root, repo_root)
    _require_sha256(expected_norgate_dataset_hash, "expected Norgate dataset hash")
    _require_sha256(expected_norgate_manifest_hash, "expected Norgate manifest hash")

    # Both loaders hash-attest their input bytes before this function reads Bar values.
    norgate = load_verified_norgate_d1_diagnostic_panel(
        snapshot_dir,
        expected_dataset_hash=expected_norgate_dataset_hash,
        expected_manifest_hash=expected_norgate_manifest_hash,
        repo_root=repo_root,
    )
    kis = load_kis_paper_private_daily_catalog(
        cache_root,
        target_keys=HISTORICAL_KIS_DAILY_TARGET_KEYS,
        expected_index_hash=_HISTORICAL_KIS_DAILY_EXPECTED_INDEX_HASH,
        expected_full_dataset_hash=_HISTORICAL_KIS_DAILY_EXPECTED_FULL_DATASET_HASH,
        repo_root=repo_root,
    )
    source = _validated_sources(norgate=norgate, kis=kis)
    evidence = _evaluate_evidence(source)
    status = _aggregate_status(evidence)
    payload = _safe_payload(
        status=status,
        norgate_dataset_hash=norgate.source_result.dataset_hash,
        norgate_manifest_hash=norgate.source_result.manifest_hash,
        kis_dataset_hash=kis.dataset_hash,
        kis_index_hash=kis.index_hash,
        evidence=evidence,
    )
    receipt_hash = _sha256_json(payload)
    path = _receipt_path(root, receipt_hash)
    _write_or_verify_json(path, payload, artifact_root=root)
    return NorgateKisD1BarConformanceResult(
        status=status,
        receipt_path=path,
        receipt_sha256="sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        norgate_dataset_hash=norgate.source_result.dataset_hash,
        norgate_manifest_hash=norgate.source_result.manifest_hash,
        kis_dataset_hash=kis.dataset_hash,
        kis_index_hash=kis.index_hash,
        evidence=evidence,
    )


@dataclass(frozen=True, slots=True)
class _ValidatedSources:
    norgate: Mapping[str, Mapping[date, Bar]]
    kis: Mapping[str, Mapping[date, Bar]]
    common_sessions: Mapping[str, tuple[date, ...]]


def _validated_sources(
    *, norgate: VerifiedNorgateD1Panel, kis: KisPaperPrivateDailyCatalog
) -> _ValidatedSources:
    if (
        norgate.source_result.dataset_hash is None
        or norgate.source_result.manifest_hash is None
        or kis.dataset_id != KIS_PAPER_PRIVATE_DAILY_CATALOG_ID
        or kis.adjustment_mode != "MODP=0_unadjusted"
    ):
        raise ValueError("Norgate/KIS D1 source identity is invalid")
    norgate_streams: dict[str, Mapping[date, Bar]] = {}
    kis_streams: dict[str, Mapping[date, Bar]] = {}
    common: dict[str, tuple[date, ...]] = {}
    for symbol in _REQUIRED_SYMBOLS:
        norgate_streams[symbol] = _stream_by_session(
            norgate.bars_by_symbol.get(symbol), symbol=symbol
        )
        kis_cataloged = kis.bars_by_symbol.get(symbol)
        kis_streams[symbol] = _stream_by_session(
            None if kis_cataloged is None else kis_cataloged.bars,
            symbol=symbol,
        )
        sessions = tuple(sorted(set(norgate_streams[symbol]) & set(kis_streams[symbol])))
        if not sessions:
            raise ValueError("Norgate/KIS D1 sources have no common sessions")
        common[symbol] = sessions
    return _ValidatedSources(norgate=norgate_streams, kis=kis_streams, common_sessions=common)


def _stream_by_session(bars: Sequence[Bar] | None, *, symbol: str) -> Mapping[date, Bar]:
    if not bars:
        raise ValueError("Norgate/KIS D1 source stream is unavailable")
    result: dict[date, Bar] = {}
    prior: date | None = None
    for bar in bars:
        if (
            not isinstance(bar, Bar)
            or bar.symbol != symbol
            or bar.market != "US"
            or bar.timeframe is not Timeframe.D1
            or not bar.complete
            or bar.start_ts.tzinfo is not UTC
            or bar.start_ts.time() != time()
        ):
            raise ValueError("Norgate/KIS D1 bar contract is invalid")
        session = bar.start_ts.date()
        if prior is not None and session <= prior:
            raise ValueError("Norgate/KIS D1 sessions are not strictly increasing")
        result[session] = bar
        prior = session
    return result


def _evaluate_evidence(source: _ValidatedSources) -> tuple[NorgateKisD1FieldEvidence, ...]:
    result: list[NorgateKisD1FieldEvidence] = []
    for symbol in _REQUIRED_SYMBOLS:
        sessions = source.common_sessions[symbol]
        strata = _strata_for_symbol(
            sessions=sessions,
            norgate=source.norgate[symbol],
            kis=source.kis[symbol],
        )
        norgate_values = _relationship_values(source.norgate[symbol], sessions=sessions)
        kis_values = _relationship_values(source.kis[symbol], sessions=sessions)
        positions = {session: index for index, session in enumerate(sessions)}
        for field_id in _FIELD_ORDER:
            for stratum in _STRATA:
                result.append(
                    _field_evidence(
                        symbol=symbol,
                        field_id=field_id,
                        stratum=stratum,
                        sessions=strata[stratum],
                        positions=positions,
                        all_sessions=sessions,
                        norgate_values=norgate_values,
                        kis_values=kis_values,
                    )
                )
    return tuple(result)


def _strata_for_symbol(
    *, sessions: tuple[date, ...], norgate: Mapping[date, Bar], kis: Mapping[date, Bar]
) -> Mapping[str, tuple[date, ...]]:
    discontinuities = _discontinuity_sessions(norgate) | _discontinuity_sessions(kis)
    adjacent: set[date] = set()
    for discontinuity in discontinuities:
        index = bisect_left(sessions, discontinuity)
        if index < len(sessions) and sessions[index] == discontinuity:
            adjacent.update(sessions[max(0, index - 1) : min(len(sessions), index + 2)])
        else:
            adjacent.update(sessions[max(0, index - 1) : min(len(sessions), index + 1)])
    return {
        "quiet": tuple(session for session in sessions if session not in adjacent),
        "discontinuity_adjacent": tuple(session for session in sessions if session in adjacent),
    }


def _discontinuity_sessions(stream: Mapping[date, Bar]) -> set[date]:
    result: set[date] = set()
    prior: Bar | None = None
    for session, bar in stream.items():
        if prior is not None and (
            _raw_move(bar.open, prior.close) >= _DISCONTINUITY_MOVE
            or _raw_move(bar.close, prior.close) >= _DISCONTINUITY_MOVE
        ):
            result.add(session)
        prior = bar
    return result


def _raw_move(current: Decimal, prior: Decimal) -> Decimal:
    return abs(current / prior - Decimal("1"))


def _relationship_values(
    stream: Mapping[date, Bar], *, sessions: tuple[date, ...]
) -> Mapping[date, Mapping[str, Decimal | None]]:
    result: dict[date, Mapping[str, Decimal | None]] = {}
    for index, session in enumerate(sessions):
        bar = stream[session]
        relationships: dict[str, Decimal | None] = {
            "open_to_close": _ratio(bar.close, bar.open),
            "high_to_open": _ratio(bar.high, bar.open),
            "low_to_open": _ratio(bar.low, bar.open),
        }
        if index > 0:
            prior = stream[sessions[index - 1]]
            relationships["close_to_close"] = _ratio(bar.close, prior.close)
            relationships["volume_ratio"] = _ratio(bar.volume, prior.volume)
        result[session] = relationships
    return result


def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if numerator <= 0 or denominator <= 0:
        return None
    return numerator / denominator


def _field_evidence(
    *,
    symbol: str,
    field_id: str,
    stratum: str,
    sessions: tuple[date, ...],
    positions: Mapping[date, int],
    all_sessions: tuple[date, ...],
    norgate_values: Mapping[date, Mapping[str, Decimal | None]],
    kis_values: Mapping[date, Mapping[str, Decimal | None]],
) -> NorgateKisD1FieldEvidence:
    anchors = _shared_eligible_anchors(
        sessions=sessions,
        positions=positions,
        all_sessions=all_sessions,
        field_id=field_id,
        norgate_values=norgate_values,
        kis_values=kis_values,
    )
    if not anchors:
        status: EvidenceStatus = "input_unavailable"
        aligned = backward = forward = (0, 0)
    else:
        aligned = _agreement_counts(anchors, anchors, field_id, norgate_values, kis_values)
        backward = _agreement_counts(
            anchors,
            tuple(all_sessions[positions[session] - 1] for session in anchors),
            field_id,
            norgate_values,
            kis_values,
        )
        forward = _agreement_counts(
            anchors,
            tuple(all_sessions[positions[session] + 1] for session in anchors),
            field_id,
            norgate_values,
            kis_values,
        )
        if (
            _rate(*aligned) >= _MIN_AGREEMENT_RATE
            and _rate(*aligned) > _rate(*backward)
            and _rate(*aligned) > _rate(*forward)
        ):
            status = "pass"
        else:
            status = "nonconforming"
    return NorgateKisD1FieldEvidence(
        symbol=symbol,
        field_id=field_id,
        stratum=stratum,
        status=status,
        aligned_sample_count=aligned[0],
        aligned_agreement_count=aligned[1],
        backward_sample_count=backward[0],
        backward_agreement_count=backward[1],
        forward_sample_count=forward[0],
        forward_agreement_count=forward[1],
    )


def _shared_eligible_anchors(
    *,
    sessions: tuple[date, ...],
    positions: Mapping[date, int],
    all_sessions: tuple[date, ...],
    field_id: str,
    norgate_values: Mapping[date, Mapping[str, Decimal | None]],
    kis_values: Mapping[date, Mapping[str, Decimal | None]],
) -> tuple[date, ...]:
    result: list[date] = []
    for session in sessions:
        index = positions[session]
        if index == 0 or index + 1 >= len(all_sessions):
            continue
        prior = all_sessions[index - 1]
        following = all_sessions[index + 1]
        if all(
            field_id in relationships
            for relationships in (
                norgate_values[prior],
                norgate_values[session],
                norgate_values[following],
                kis_values[prior],
                kis_values[session],
                kis_values[following],
            )
        ):
            result.append(session)
    return tuple(result)


def _agreement_counts(
    norgate_sessions: tuple[date, ...],
    kis_sessions: tuple[date, ...],
    field_id: str,
    norgate_values: Mapping[date, Mapping[str, Decimal | None]],
    kis_values: Mapping[date, Mapping[str, Decimal | None]],
) -> tuple[int, int]:
    if len(norgate_sessions) != len(kis_sessions):
        raise ValueError("Norgate/KIS D1 comparison anchors are invalid")
    count = len(norgate_sessions)
    agreements = 0
    tolerance = _VOLUME_TOLERANCE if field_id == _VOLUME_FIELD else _PRICE_TOLERANCE
    for norgate_session, kis_session in zip(norgate_sessions, kis_sessions, strict=True):
        left = norgate_values[norgate_session][field_id]
        right = kis_values[kis_session][field_id]
        if (
            left is not None
            and right is not None
            and _log_ratio_difference(left, right) <= tolerance
        ):
            agreements += 1
    return count, agreements


def _log_ratio_difference(left: Decimal, right: Decimal) -> Decimal:
    if left <= 0 or right <= 0:
        return Decimal("Infinity")
    with localcontext() as context:
        context.prec = 50
        try:
            return abs((left / right).ln())
        except (InvalidOperation, ValueError):
            return Decimal("Infinity")


def _aggregate_status(evidence: tuple[NorgateKisD1FieldEvidence, ...]) -> ConformanceStatus:
    if any(item.status == "input_unavailable" for item in evidence):
        return "input_unavailable"
    if all(item.status == "pass" for item in evidence):
        return "conforming_with_limits"
    return "nonconforming"


def _safe_payload(
    *,
    status: ConformanceStatus,
    norgate_dataset_hash: str,
    norgate_manifest_hash: str,
    kis_dataset_hash: str,
    kis_index_hash: str,
    evidence: tuple[NorgateKisD1FieldEvidence, ...],
) -> dict[str, object]:
    return {
        "schema_version": _VERSION,
        "kind": "norgate_kis_d1_bar_conformance_receipt",
        "conformance_id": NORGATE_KIS_D1_BAR_CONFORMANCE_ID,
        "status": status,
        "source_identity": {
            "norgate_dataset_hash": norgate_dataset_hash,
            "norgate_manifest_hash": norgate_manifest_hash,
            "kis_dataset_hash": kis_dataset_hash,
            "kis_index_hash": kis_index_hash,
        },
        "comparison_contract": {
            "symbols": list(_REQUIRED_SYMBOLS),
            "fields": list(_FIELD_ORDER),
            "price_relationship_log_ratio_tolerance": str(_PRICE_TOLERANCE),
            "volume_relationship_log_ratio_tolerance": str(_VOLUME_TOLERANCE),
            "minimum_aligned_agreement_rate": str(_MIN_AGREEMENT_RATE),
            "discontinuity_raw_move_threshold": str(_DISCONTINUITY_MOVE),
            "shift_probes": ["one_session_backward", "one_session_forward"],
        },
        "evidence": [item.safe_payload() for item in evidence],
        "scope": {
            "non_promoting": True,
            "point_in_time_proven": False,
            "tradability_proven": False,
            "corporate_action_correctness_proven": False,
            "source_interchangeability_proven": False,
        },
        "artifact_policy": {
            "external_artifact_only": True,
            "network_accessed": False,
            "credentials_accessed": False,
            "kis_client_accessed": False,
            "broker_accessed": False,
            "account_accessed": False,
            "local_paper_accessed": False,
            "gpu_accessed": False,
            "model_or_training_accessed": False,
            "live_accessed": False,
            "source_rows_persisted": False,
            "per_row_comparisons_persisted": False,
            "market_values_persisted": False,
        },
    }


def _aggregate_payload(sample_count: int, agreement_count: int) -> dict[str, object]:
    return {
        "sample_count": sample_count,
        "agreement_count": agreement_count,
        "agreement_rate": str(_rate(sample_count, agreement_count)),
    }


def _rate(sample_count: int, agreement_count: int) -> Decimal:
    return Decimal(agreement_count) / Decimal(sample_count) if sample_count else Decimal("0")


def _external_artifact_root(root: Path, repo_root: Path | None) -> Path:
    candidate = Path(root)
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError("Norgate/KIS D1 artifact root is invalid")
    resolved = candidate.resolve()
    if repo_root is not None and resolved.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("Norgate/KIS D1 artifact root must stay outside the Git workspace")
    return resolved


def _receipt_path(artifact_root: Path, receipt_hash: str) -> Path:
    path = artifact_root / NORGATE_KIS_D1_BAR_CONFORMANCE_ID / receipt_hash[7:] / "receipt.json"
    _assert_no_symlink_components(path, artifact_root=artifact_root)
    return path


def _write_or_verify_json(
    path: Path, payload: Mapping[str, object], *, artifact_root: Path
) -> None:
    encoded = _json_bytes(payload)
    _create_receipt_parent(path, artifact_root=artifact_root)
    _assert_no_symlink_components(path, artifact_root=artifact_root)
    try:
        with path.open("xb") as receipt:
            receipt.write(encoded)
    except FileExistsError:
        _assert_no_symlink_components(path, artifact_root=artifact_root)
        if path.is_symlink() or not path.is_file() or path.read_bytes() != encoded:
            raise FileExistsError("Norgate/KIS D1 receipt is immutable") from None


def _create_receipt_parent(path: Path, *, artifact_root: Path) -> None:
    relative = path.parent.relative_to(artifact_root)
    current = artifact_root
    resolved_root = artifact_root.resolve()
    for component in relative.parts:
        current /= component
        if current.exists() or current.is_symlink():
            if (
                current.is_symlink()
                or not current.is_dir()
                or not current.resolve(strict=False).is_relative_to(resolved_root)
            ):
                raise ValueError("Norgate/KIS D1 receipt path contains a symlink")
            continue
        current.mkdir()
        if (
            current.is_symlink()
            or not current.is_dir()
            or not current.resolve(strict=False).is_relative_to(resolved_root)
        ):
            raise ValueError("Norgate/KIS D1 receipt path contains a symlink")


def _assert_no_symlink_components(path: Path, *, artifact_root: Path) -> None:
    try:
        relative = path.relative_to(artifact_root)
    except ValueError as error:
        raise ValueError("Norgate/KIS D1 receipt path is outside artifact root") from error
    resolved_root = artifact_root.resolve()
    current = resolved_root
    if current.is_symlink():
        raise ValueError("Norgate/KIS D1 receipt path contains a symlink")
    for component in relative.parts:
        current /= component
        if current.is_symlink() or not current.resolve(strict=False).is_relative_to(resolved_root):
            raise ValueError("Norgate/KIS D1 receipt path contains a symlink")


def _json_bytes(payload: Mapping[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256_json(payload: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _require_sha256(value: object, label: str) -> None:
    if not _is_sha256(value):
        raise ValueError(f"{label} is invalid")
