"""Retrospective-only event masks for KIS QQQ/SPY daily return labels."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import MappingProxyType

from thericher_v2.data.kis_daily_corporate_actions import (
    KIS_DAILY_CORPORATE_ACTION_SYMBOLS,
    KisDailyCorporateActionSnapshot,
    kis_daily_session_dates_hash,
)
from thericher_v2.data.kis_paper_daily import KisPaperPrivateDailyCatalog

DEFAULT_MODEL_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
KIS_DAILY_EVENT_MASK_CONTRACT_SCHEMA_VERSION = 1
KIS_DAILY_EVENT_MASK_CONTRACT_KIND = "kis_daily_event_mask_contract"
_SCOPE = {
    "retrospective_price_return_label_integrity_only": True,
    "point_in_time_feature_eligible": False,
    "model_training_eligible": False,
    "paper_decision_eligible": False,
    "price_data_consumed": False,
}


@dataclass(frozen=True, slots=True)
class KisDailyEventMaskedPair:
    """One chronological t-to-t+1 pair excluded from price-return labels."""

    symbol: str
    start_session: date
    end_session: date
    event_dates: tuple[date, ...]


@dataclass(frozen=True, slots=True)
class KisDailyEventMaskContract:
    """A frozen source contract; it cannot score, train, or route an order."""

    catalog_dataset_hash: str
    catalog_index_hash: str
    sidecar_dataset_hash: str
    sidecar_manifest_hash: str
    sessions: tuple[date, ...]
    excluded_pairs: Mapping[str, tuple[KisDailyEventMaskedPair, ...]]

    def document(self) -> dict[str, object]:
        return {
            "schema_version": KIS_DAILY_EVENT_MASK_CONTRACT_SCHEMA_VERSION,
            "kind": KIS_DAILY_EVENT_MASK_CONTRACT_KIND,
            "catalog_dataset_hash": self.catalog_dataset_hash,
            "catalog_index_hash": self.catalog_index_hash,
            "sidecar_dataset_hash": self.sidecar_dataset_hash,
            "sidecar_manifest_hash": self.sidecar_manifest_hash,
            "session_dates_sha256": kis_daily_session_dates_hash(self.sessions),
            "session_count": len(self.sessions),
            "scope": dict(_SCOPE),
            "exclusion_rule": "exclude_t_to_t_plus_1_when_either_endpoint_is_an_event_date",
            "excluded_pairs": [
                {
                    "symbol": pair.symbol,
                    "start_session": pair.start_session.isoformat(),
                    "end_session": pair.end_session.isoformat(),
                    "event_dates": [event_date.isoformat() for event_date in pair.event_dates],
                }
                for symbol in KIS_DAILY_CORPORATE_ACTION_SYMBOLS
                for pair in self.excluded_pairs[symbol]
            ],
        }


@dataclass(frozen=True, slots=True)
class KisDailyEventMaskContractArtifact:
    path: Path
    content_hash: str
    contract: KisDailyEventMaskContract


def build_kis_daily_event_mask_contract(
    *,
    catalog: KisPaperPrivateDailyCatalog,
    sidecar: KisDailyCorporateActionSnapshot,
) -> KisDailyEventMaskContract:
    """Build only the conservative label-exclusion geometry from event dates."""

    if not isinstance(catalog, KisPaperPrivateDailyCatalog):
        raise ValueError("KIS daily event-mask catalog is invalid")
    if not isinstance(sidecar, KisDailyCorporateActionSnapshot):
        raise ValueError("KIS daily event-mask sidecar is invalid")
    if (
        sidecar.catalog_dataset_hash != catalog.dataset_hash
        or sidecar.catalog_index_hash != catalog.index_hash
    ):
        raise ValueError("KIS daily event-mask sidecar lineage is incompatible")
    sessions = tuple(catalog.common_sessions)
    if (
        len(sessions) < 2
        or tuple(sorted(sessions)) != sessions
        or len(set(sessions)) != len(sessions)
    ):
        raise ValueError("KIS daily event-mask sessions are invalid")
    event_dates = {
        symbol: frozenset(
            event.mapped_kis_session_date for event in sidecar.events if event.symbol == symbol
        )
        for symbol in KIS_DAILY_CORPORATE_ACTION_SYMBOLS
    }
    excluded: dict[str, tuple[KisDailyEventMaskedPair, ...]] = {}
    for symbol in KIS_DAILY_CORPORATE_ACTION_SYMBOLS:
        pairs: list[KisDailyEventMaskedPair] = []
        for start_session, end_session in zip(sessions[:-1], sessions[1:], strict=True):
            matched = tuple(sorted({start_session, end_session}.intersection(event_dates[symbol])))
            if matched:
                pairs.append(
                    KisDailyEventMaskedPair(
                        symbol=symbol,
                        start_session=start_session,
                        end_session=end_session,
                        event_dates=matched,
                    )
                )
        if not pairs:
            raise ValueError(f"KIS daily event-mask has no excluded pairs for {symbol}")
        excluded[symbol] = tuple(pairs)
    return KisDailyEventMaskContract(
        catalog_dataset_hash=catalog.dataset_hash,
        catalog_index_hash=catalog.index_hash,
        sidecar_dataset_hash=sidecar.dataset_hash,
        sidecar_manifest_hash=sidecar.manifest_hash,
        sessions=sessions,
        excluded_pairs=MappingProxyType(excluded),
    )


def write_kis_daily_event_mask_contract(
    *,
    destination: Path,
    contract: KisDailyEventMaskContract,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    repo_root: Path | None = None,
) -> KisDailyEventMaskContractArtifact:
    """Write one immutable, price-free receipt outside the repository."""

    if not isinstance(contract, KisDailyEventMaskContract):
        raise ValueError("KIS daily event-mask contract is invalid")
    root = Path(artifact_root).resolve(strict=False)
    requested = Path(destination)
    resolved = requested.resolve(strict=False)
    if requested.exists() or requested.is_symlink():
        raise FileExistsError("KIS daily event-mask destination already exists")
    if resolved.suffix != ".json" or not resolved.is_relative_to(root):
        raise ValueError("KIS daily event-mask destination must be a JSON artifact")
    _assert_external_artifact(resolved, repo_root=repo_root)
    payload = (json.dumps(contract.document(), indent=2, sort_keys=True) + "\n").encode("utf-8")
    requested.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=requested.parent, delete=False) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    try:
        os.replace(temporary, requested)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return KisDailyEventMaskContractArtifact(
        path=requested.resolve(),
        content_hash="sha256:" + hashlib.sha256(payload).hexdigest(),
        contract=contract,
    )


def _assert_external_artifact(path: Path, *, repo_root: Path | None) -> None:
    if repo_root is not None:
        repository = Path(repo_root).resolve(strict=False)
        docker_artifacts = Path("/app/model_artifacts").resolve()
        if path == repository or path.is_relative_to(repository):
            if repository != Path("/app").resolve() or not path.is_relative_to(docker_artifacts):
                raise ValueError("KIS daily event-mask artifact must stay outside Git")
    if any((parent / ".git").exists() for parent in (path, *path.parents)):
        raise ValueError("KIS daily event-mask artifact must stay outside Git")
