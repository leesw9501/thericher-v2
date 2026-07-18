"""Strict, external-only access to the date-less Norgate candidate union."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MARKET_DATA_ROOT = Path("D:/market_data")
_CANDIDATE_COLUMNS = ("candidate_rank", "symbol")
_INELIGIBLE_SCOPE_KEYS = (
    "direct_historical_universe_list",
    "publication_time_proven",
    "pit_eligible",
    "campaign_eligible",
    "model_eligible",
)


@dataclass(frozen=True, slots=True)
class NorgateCandidateUnion:
    """Validated union bytes that remain a candidate list, never a universe claim."""

    candidate_count: int
    candidate_union_hash: str
    candidates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NorgateCandidateSelection:
    """In-memory selection; callers control whether symbols may be persisted."""

    candidate_count: int
    candidate_union_hash: str
    selected_ranks: tuple[int, ...]
    selected_symbols: tuple[str, ...]


def load_norgate_candidate_union(
    *,
    candidate_union_path: Path,
    candidate_union_manifest_path: Path,
    expected_candidate_union_hash: str,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> NorgateCandidateUnion:
    """Load one hash-bound external union without calling the Norgate client."""

    root = _validated_external_root(market_data_root, repo_root=repo_root)
    candidate_path = _validated_external_file(
        candidate_union_path, root=root, repo_root=repo_root, label="candidate union"
    )
    manifest_path = _validated_external_file(
        candidate_union_manifest_path, root=root, repo_root=repo_root, label="candidate manifest"
    )
    expected_hash = _required_sha256(expected_candidate_union_hash, "candidate union hash")
    candidate_bytes = candidate_path.read_bytes()
    candidate_hash = _sha256(candidate_bytes)
    if candidate_hash != expected_hash:
        raise ValueError("Norgate candidate union hash mismatch")
    manifest = _load_manifest(manifest_path)
    _validate_manifest(manifest, candidate_path=candidate_path, candidate_hash=candidate_hash)
    candidates = _parse_ranked_candidates(candidate_bytes)
    candidate_count = _positive_int(manifest.get("candidate_count"), "candidate count")
    if len(candidates) != candidate_count:
        raise ValueError("Norgate candidate count is inconsistent")
    return NorgateCandidateUnion(
        candidate_count=candidate_count,
        candidate_union_hash=candidate_hash,
        candidates=candidates,
    )


def select_rank_quantile_candidates(
    union: NorgateCandidateUnion, *, sample_size: int
) -> NorgateCandidateSelection:
    """Select inclusive integer quantiles without creating a membership interpretation."""

    ranks = rank_quantile_ranks(union.candidate_count, sample_size=sample_size)
    return NorgateCandidateSelection(
        candidate_count=union.candidate_count,
        candidate_union_hash=union.candidate_union_hash,
        selected_ranks=ranks,
        selected_symbols=tuple(union.candidates[rank - 1] for rank in ranks),
    )


def rank_quantile_ranks(candidate_count: int, *, sample_size: int) -> tuple[int, ...]:
    """Return the shared inclusive rank schedule for a fixed candidate count."""

    if (
        not isinstance(candidate_count, int)
        or isinstance(candidate_count, bool)
        or candidate_count <= 0
    ):
        raise ValueError("Norgate candidate count is invalid")
    if not isinstance(sample_size, int) or isinstance(sample_size, bool) or sample_size <= 0:
        raise ValueError("Norgate candidate sample size is invalid")
    if sample_size > candidate_count:
        raise ValueError("Norgate candidate union is smaller than the sample")
    if sample_size == 1:
        ranks = (1,)
    else:
        ranks = tuple(
            1 + index * (candidate_count - 1) // (sample_size - 1)
            for index in range(sample_size)
        )
    if len(set(ranks)) != sample_size:
        raise ValueError("Norgate candidate sample ranks are invalid")
    return ranks


def _load_manifest(path: Path) -> dict[str, object]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Norgate candidate manifest is invalid") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Norgate candidate manifest must be an object")
    return parsed


def _validate_manifest(
    manifest: dict[str, object],
    *,
    candidate_path: Path,
    candidate_hash: str,
) -> None:
    if (manifest.get("schema_version"), manifest.get("kind")) != (
        1,
        "norgate_sp500_current_past_membership_matrix",
    ):
        raise ValueError("Norgate candidate manifest schema is invalid")
    scope = manifest.get("scope")
    if not isinstance(scope, dict) or any(
        scope.get(key) is not False for key in _INELIGIBLE_SCOPE_KEYS
    ):
        raise ValueError("Norgate candidate manifest scope is invalid")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("Norgate candidate manifest files are invalid")
    candidate_file = files.get("candidate_union")
    if not isinstance(candidate_file, dict):
        raise ValueError("Norgate candidate manifest lineage is invalid")
    if candidate_file.get("path") != candidate_path.name:
        raise ValueError("Norgate candidate manifest path is invalid")
    if _required_sha256(candidate_file.get("sha256"), "manifest candidate hash") != candidate_hash:
        raise ValueError("Norgate candidate manifest hash mismatch")
    if candidate_file.get("size_bytes") != candidate_path.stat().st_size:
        raise ValueError("Norgate candidate manifest size is inconsistent")
    if tuple(candidate_file.get("columns", ())) != _CANDIDATE_COLUMNS:
        raise ValueError("Norgate candidate manifest columns are invalid")


def _parse_ranked_candidates(candidate_bytes: bytes) -> tuple[str, ...]:
    try:
        reader = csv.DictReader(io.StringIO(candidate_bytes.decode("utf-8"), newline=""))
    except UnicodeDecodeError as exc:
        raise ValueError("Norgate candidate union is not UTF-8") from exc
    if tuple(reader.fieldnames or ()) != _CANDIDATE_COLUMNS:
        raise ValueError("Norgate candidate union columns are invalid")
    candidates: list[str] = []
    for expected_rank, row in enumerate(reader, start=1):
        if set(row) != set(_CANDIDATE_COLUMNS):
            raise ValueError("Norgate candidate union row is invalid")
        rank = row.get("candidate_rank")
        symbol = row.get("symbol")
        if rank != str(expected_rank) or not isinstance(symbol, str) or not _valid_symbol(symbol):
            raise ValueError("Norgate candidate union row is invalid")
        candidates.append(symbol)
    if not candidates or len(set(candidates)) != len(candidates):
        raise ValueError("Norgate candidate union is invalid")
    return tuple(candidates)


def _validated_external_root(market_data_root: Path, *, repo_root: Path | None) -> Path:
    root = Path(market_data_root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Norgate candidate market-data root must exist")
    resolved = root.resolve()
    if repo_root is not None and resolved.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("Norgate candidate market-data root must stay outside Git")
    return resolved


def _validated_external_file(
    path: Path,
    *,
    root: Path,
    repo_root: Path | None,
    label: str,
) -> Path:
    candidate = Path(path)
    if not candidate.is_file() or candidate.is_symlink():
        raise ValueError(f"Norgate candidate {label} must be a regular file")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"Norgate candidate {label} must stay under market data")
    if repo_root is not None and resolved.is_relative_to(Path(repo_root).resolve()):
        raise ValueError(f"Norgate candidate {label} must stay outside Git")
    return resolved


def _valid_symbol(value: str) -> bool:
    return bool(value) and value == value.strip() and value == value.upper() and "\n" not in value


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"Norgate candidate {label} is invalid")
    return value


def _required_sha256(value: object, label: str) -> str:
    text = str(value or "")
    if len(text) != 71 or not text.startswith("sha256:") or any(
        character not in "0123456789abcdef" for character in text[7:]
    ):
        raise ValueError(f"Norgate candidate {label} is invalid")
    return text


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()
