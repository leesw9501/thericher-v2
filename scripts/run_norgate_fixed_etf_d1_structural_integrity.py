"""Write target-free integrity evidence for the newest fixed-ETF Norgate D1 snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from thericher_v2.data.norgate_trial_raw_d1 import (  # noqa: E402
    DEFAULT_MARKET_DATA_ROOT,
    FIXED_NORGATE_TRIAL_SYMBOLS,
    NorgateTrialRawD1Result,
    verify_norgate_trial_raw_d1_snapshot,
)

DEFAULT_NORGATE_FIXED_ETF_D1_SNAPSHOT_ROOT = Path(
    "D:/market_data/us_equities/norgate_trial/local_d1_etf"
)
DEFAULT_NORGATE_FIXED_ETF_D1_STRUCTURAL_INTEGRITY_ROOT = Path(
    "D:/thericher-v2/model-artifacts/data/norgate-fixed-etf-d1-structural-integrity-v1"
)
_ASSESSMENT_ID = "norgate-fixed-etf-d1-structural-integrity-v1"
_RECEIPT_FILE = "assessment.json"
_SNAPSHOT_NAME = re.compile(
    r"snapshot=[A-Za-z0-9][A-Za-z0-9._-]{0,127}-norgate-trial-raw-d1-r2",
    re.ASCII,
)
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot-root",
        type=Path,
        default=DEFAULT_NORGATE_FIXED_ETF_D1_SNAPSHOT_ROOT,
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_NORGATE_FIXED_ETF_D1_STRUCTURAL_INTEGRITY_ROOT,
    )
    parser.add_argument("--market-data-root", type=Path, default=DEFAULT_MARKET_DATA_ROOT)
    arguments = parser.parse_args(argv)
    source = verify_norgate_trial_raw_d1_snapshot(
        _newest_snapshot(arguments.snapshot_root),
        market_data_root=arguments.market_data_root,
        repo_root=REPOSITORY_ROOT,
    )
    artifact_root = _artifact_root(arguments.artifact_root)
    receipt_path = _receipt_path(source, artifact_root)
    if receipt_path.exists():
        document, receipt_bytes = _verified_receipt(receipt_path, source, artifact_root)
    else:
        document = _receipt_document(source, assessed_at=datetime.now(UTC).replace(microsecond=0))
        _write_new_receipt(receipt_path, _json_bytes(document), artifact_root)
        document, receipt_bytes = _verified_receipt(receipt_path, source, artifact_root)
    print(json.dumps(_safe_payload(document, receipt_bytes), sort_keys=True))
    return 0


def _newest_snapshot(snapshot_root: Path) -> Path:
    root = _existing_directory(snapshot_root, "Norgate fixed-ETF snapshot root")
    candidates: list[tuple[int, str, Path]] = []
    try:
        children = tuple(root.iterdir())
    except OSError as exc:
        raise ValueError("Norgate fixed-ETF snapshot root is unreadable") from exc
    for child in children:
        if (
            _is_link_like(child)
            or not child.is_dir()
            or _SNAPSHOT_NAME.fullmatch(child.name) is None
        ):
            continue
        try:
            resolved = child.resolve(strict=True)
            stat = child.stat(follow_symlinks=False)
        except OSError:
            continue
        if resolved.is_relative_to(root):
            candidates.append((stat.st_mtime_ns, child.name, resolved))
    if not candidates:
        raise ValueError("Norgate fixed-ETF raw-D1 snapshot is unavailable")
    return max(candidates)[2]


def _artifact_root(value: Path) -> Path:
    root = Path(value)
    repository = _existing_directory(REPOSITORY_ROOT, "repository root")
    resolved_candidate = root.resolve(strict=False)
    if resolved_candidate == repository or resolved_candidate.is_relative_to(repository):
        raise ValueError(
            "Norgate structural-integrity artifacts must stay outside the Git workspace"
        )
    if root.exists() and (_is_link_like(root) or not root.is_dir()):
        raise ValueError("Norgate structural-integrity artifact root is invalid")
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve(strict=True)
    if root == repository or root.is_relative_to(repository):
        raise ValueError(
            "Norgate structural-integrity artifacts must stay outside the Git workspace"
        )
    return root


def _receipt_path(source: NorgateTrialRawD1Result, artifact_root: Path) -> Path:
    if _SHA256.fullmatch(source.dataset_hash) is None:
        raise ValueError("Norgate dataset hash is invalid")
    return artifact_root / f"assessment={source.dataset_hash[7:]}" / _RECEIPT_FILE


def _receipt_document(
    source: NorgateTrialRawD1Result,
    *,
    assessed_at: datetime,
) -> dict[str, object]:
    timestamp = _format_utc(assessed_at)
    return {
        "schema_version": 1,
        "kind": "norgate_fixed_etf_d1_structural_integrity",
        "assessment_id": _ASSESSMENT_ID,
        "assessed_at_utc": timestamp,
        "status": "integrity_attested",
        "reason": "verified_fixed_etf_raw_d1_contract",
        "source": {
            "provider": "norgate_local_trial",
            "instrument_scope": "fixed_us_etf_trio",
            "interval": "1d",
            "dataset_sha256": source.dataset_hash,
            "manifest_sha256": source.manifest_hash,
        },
        "geometry": {
            "symbol_count": len(FIXED_NORGATE_TRIAL_SYMBOLS),
            "row_count": source.row_count,
            "common_session_count": source.common_session_count,
            "per_symbol_rows_equal_common_session_count": True,
        },
        "integrity": {
            "raw_dataset_hash_verified": True,
            "manifest_contract_verified": True,
            "fixed_symbol_order_verified": True,
            "common_session_alignment_verified": True,
            "strict_session_order_verified": True,
            "ohlcv_geometry_verified": True,
            "capital_event_exclusion_contract_verified": True,
            "capital_event_marker_count": source.event_marker_count,
            "capital_event_exclusion_count": source.excluded_session_count,
        },
        "scope": {
            "target_free_integrity_only": True,
            "offline_data_quality_only": True,
            "point_in_time_eligible": False,
            "model_eligible": False,
            "gpu_eligible": False,
            "paper_trading_eligible": False,
            "pnl_eligible": False,
            "promotion_eligible": False,
        },
        "receipt_constraints": {
            "raw_ohlcv_persisted": False,
            "session_dates_persisted": False,
            "source_paths_persisted": False,
            "target_or_label_computed": False,
            "provider_or_network_used": False,
            "credential_access_used": False,
        },
    }


def _verified_receipt(
    receipt_path: Path,
    source: NorgateTrialRawD1Result,
    artifact_root: Path,
) -> tuple[dict[str, object], bytes]:
    parent = receipt_path.parent
    if (
        parent.parent != artifact_root
        or _is_link_like(parent)
        or not parent.is_dir()
        or not parent.resolve(strict=True).is_relative_to(artifact_root)
        or _is_link_like(receipt_path)
        or not receipt_path.is_file()
    ):
        raise ValueError("Norgate structural-integrity receipt is unavailable")
    receipt_bytes = receipt_path.read_bytes()
    try:
        document = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Norgate structural-integrity receipt is invalid") from exc
    if not isinstance(document, dict):
        raise ValueError("Norgate structural-integrity receipt is invalid")
    assessed_at = _parse_utc(document.get("assessed_at_utc"))
    if document != _receipt_document(source, assessed_at=assessed_at):
        raise ValueError("Norgate structural-integrity receipt is invalid")
    return document, receipt_bytes


def _safe_payload(document: dict[str, object], receipt_bytes: bytes) -> dict[str, object]:
    source = _mapping(document.get("source"))
    geometry = _mapping(document.get("geometry"))
    integrity = _mapping(document.get("integrity"))
    return {
        "assessment_id": document["assessment_id"],
        "receipt_sha256": _sha256(receipt_bytes),
        "assessed_at_utc": document["assessed_at_utc"],
        "status": document["status"],
        "reason": document["reason"],
        "source_dataset_sha256": source["dataset_sha256"],
        "source_manifest_sha256": source["manifest_sha256"],
        "row_count": geometry["row_count"],
        "common_session_count": geometry["common_session_count"],
        "capital_event_marker_count": integrity["capital_event_marker_count"],
        "capital_event_exclusion_count": integrity["capital_event_exclusion_count"],
    }


def _write_new_receipt(target: Path, data: bytes, artifact_root: Path) -> None:
    parent = target.parent
    if parent.parent != artifact_root or _is_link_like(parent):
        raise ValueError("Norgate structural-integrity receipt destination is invalid")
    try:
        parent.mkdir()
    except FileExistsError:
        pass
    if _is_link_like(parent) or not parent.is_dir() or not parent.resolve().is_relative_to(
        artifact_root
    ):
        raise ValueError("Norgate structural-integrity receipt destination is invalid")
    try:
        with target.open("xb") as handle:
            handle.write(data)
    except FileExistsError:
        return


def _existing_directory(path: Path, label: str) -> Path:
    candidate = Path(path)
    if _is_link_like(candidate) or not candidate.is_dir():
        raise ValueError(f"{label} is invalid")
    return candidate.resolve(strict=True)


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Norgate structural-integrity receipt is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Norgate structural-integrity receipt is invalid") from exc
    return _utc_datetime(parsed)


def _format_utc(value: datetime) -> str:
    return _utc_datetime(value).isoformat().replace("+00:00", "Z")


def _utc_datetime(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("Norgate structural-integrity timestamp is invalid")
    result = value.astimezone(UTC)
    if result.microsecond:
        raise ValueError("Norgate structural-integrity timestamp is invalid")
    return result


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Norgate structural-integrity receipt is invalid")
    return value


def _is_link_like(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())


def _json_bytes(value: dict[str, object]) -> bytes:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return (encoded + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
