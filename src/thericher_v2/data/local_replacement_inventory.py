"""Write one bounded manifest-only decision about local replacement data."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .norgate_broad_development_artifact import DEFAULT_MODEL_ARTIFACT_ROOT
from .norgate_trial_development_panel import DEFAULT_MARKET_DATA_ROOT

INVENTORY_VERSION = "local-replacement-inventory-r2"
_R4_WINDOW = {"start": "2024-07-18", "end": "2026-06-22", "validation_rows": 3_420}
_R4_CONTRACT_HASH = "sha256:ddba0d578bf5ddaefe10c0c72b63ad8873a27c2243787e504d3c4e8fac0bf76e"

# This is intentionally a fixed inventory, not a discovery scan or data catalog.
_CANDIDATES: tuple[dict[str, Any], ...] = (
    {
        "id": "norgate_broad_r1",
        "path": (
            "us_equities",
            "norgate_trial_broad_development_panel",
            "canonical",
            "ohlcv_1d",
            "snapshot=2026-07-18-norgate-trial-broad-d1-panel-r1",
            "manifest.json",
        ),
        "source": "Norgate trial broad panel",
        "timeframe": "1d",
        "facts": {
            "date_range": (
                ("calendar_parent", "actual_common_window"),
                {"start": "2024-07-18", "end": "2026-06-22"},
            ),
            "selected_symbol_count": (("static_panel_contract", "selected_symbol_count"), 523),
            "model_eligible": (("scope", "model_eligible"), False),
            "gpu_eligible": (("scope", "gpu_eligible"), False),
        },
        "rights": "Norgate-origin trial data with a lapse-deletion marker.",
        "r4_overlap": "complete closed r4 parent window",
        "disposition": "not_fresh",
        "limitations": ["static survivor selection", "unverified adjustment semantics", "not PIT"],
    },
    {
        "id": "tiingo_standard_eod_pilot_r2",
        "path": (
            "us_equities",
            "tiingo_standard_eod_pilot",
            "canonical",
            "snapshot=2026-07-18-tiingo-standard-eod-pilot-r2",
            "manifest.json",
        ),
        "source": "Tiingo standard EOD pilot",
        "timeframe": "1d",
        "facts": {
            "date_range": (("requested_window",), {"start": "2024-07-18", "end": "2026-07-17"}),
            "available_symbols": (("aggregate", "available"), 29),
            "model_eligible": (("scope", "model_eligible"), False),
            "gpu_eligible": (("scope", "gpu_eligible"), False),
        },
        "rights": "Approved token; private internal use only; redistribution prohibited.",
        "r4_overlap": "18 sessions extend beyond the r4 Norgate end",
        "disposition": "not_ready",
        "limitations": ["static non-PIT union", "manifest forbids model/GPU use"],
    },
    {
        "id": "fixed_etf_raw_yahoo_r2",
        "path": (
            "us_equities",
            "fixed_etf_daily",
            "canonical",
            "ohlcv_1d",
            "snapshot=2026-07-18-r2",
            "manifest.json",
        ),
        "source": "fixed ETF raw Yahoo-derived subset",
        "timeframe": "1d",
        "facts": {
            "symbols": (("symbols",), ["SPY", "QQQ", "IWM"]),
            "iwm_date_range": (
                ("date_ranges", "IWM"),
                {"min": "2000-05-26", "max": "2026-06-22", "sessions": 6555},
            ),
            "development_training": (("eligibility", "development_training", "eligible"), True),
            "ranking_eligible": (("eligibility", "ranking", "eligible"), False),
        },
        "rights": "Inherits the unofficial Yahoo-derived source limitation.",
        "r4_overlap": "historical source reused by an exhausted, unsupported fixed-ETF campaign",
        "disposition": "not_ready",
        "limitations": ["static universe", "no PIT/delisting lineage", "campaign exhausted"],
    },
    {
        "id": "tiingo_full_history_r1",
        "path": (
            "us_equities",
            "fixed_etf_full_history",
            "canonical",
            "tiingo_standard_eod",
            "snapshot=2026-07-18-tiingo-eod-full-history-r1",
            "manifest.json",
        ),
        "source": "Tiingo fixed-ETF full history",
        "timeframe": "1d",
        "facts": {
            "symbols": (("symbols",), ["SPY", "QQQ", "IWM"]),
            "iwm_last_session": (("coverage_by_symbol", "IWM", "last_session"), "2026-07-10"),
            "campaign_eligible": (("scope", "campaign_eligible"), False),
            "point_in_time_eligible": (("scope", "point_in_time_eligible"), False),
        },
        "rights": "Operator-authorized private internal Tiingo use.",
        "r4_overlap": "contains r4 dates; prior exact raw-source alignment is unsupported",
        "disposition": "not_ready",
        "limitations": ["three static ETFs", "not campaign/PIT eligible"],
    },
    {
        "id": "yahoo_broad_daily_2026_06_23",
        "path": (
            "us_equities",
            "yahoo_daily_universe",
            "manifests",
            "yahoo_daily_universe_snapshot=2026-06-23.json",
        ),
        "source": "Yahoo broad daily bootstrap",
        "timeframe": "1d",
        "facts": {
            "date_range": (
                ("results", "first_date"),
                "1980-01-02",
            ),
            "last_date": (
                ("results", "last_date"),
                "2026-06-22",
            ),
            "symbols_succeeded": (
                ("results", "symbols_succeeded"),
                1300,
            ),
            "row_count": (
                ("results", "rows"),
                7_390_436,
            ),
        },
        "rights": "Unofficial endpoint; this inventory does not establish reusable source rights.",
        "r4_overlap": "earlier dates avoid r4 reuse but do not repair survivorship",
        "disposition": "data_preflight_only",
        "limitations": [
            "static survivor universe",
            "unofficial endpoint",
            "unproven adjustment lineage",
        ],
    },
    {
        "id": "tiingo_iex_intraday_r1",
        "path": (
            "us_equities",
            "fixed_etf_intraday",
            "canonical",
            "tiingo_iex_5m",
            "snapshot=2026-07-19-tiingo-iex-5m-r1",
            "manifest.json",
        ),
        "source": "Tiingo IEX intraday",
        "timeframe": "5m",
        "facts": {
            "coverage": (
                ("common_session_coverage", "first_session"),
                "2026-01-13",
            ),
            "last_session": (
                ("common_session_coverage", "last_session"),
                "2026-07-10",
            ),
            "session_count": (
                ("common_session_coverage", "session_count"),
                129,
            ),
            "training_eligible": (("scope", "training_eligible"), False),
        },
        "rights": "Operator-authorized private internal Tiingo IEX use.",
        "r4_overlap": "different short intraday source; no daily replacement coverage",
        "disposition": "not_ready",
        "limitations": ["IEX-only", "short window", "no corporate-action lineage"],
    },
)


@dataclass(frozen=True, slots=True)
class LocalReplacementInventory:
    artifact_dir: Path
    summary_path: Path
    summary_sha256: str
    conclusion: str


def build_local_replacement_inventory(
    *,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    repo_root: Path | None = None,
) -> LocalReplacementInventory:
    """Validate the fixed manifest set and write one immutable external summary."""

    repo = _external_root(
        Path(repo_root) if repo_root else Path(__file__).resolve().parents[3], "repo"
    )
    market_root = _external_root(Path(market_data_root), "market data", repo=repo)
    artifact_root = _external_root(Path(artifact_root), "artifact", repo=repo)
    target = artifact_root / "data-agent" / "local-replacement-inventory" / INVENTORY_VERSION
    _validate_target(target, artifact_root)
    candidates = [_inspect(spec, market_root) for spec in _CANDIDATES]
    payload = {
        "schema_version": 1,
        "kind": "local_replacement_inventory",
        "inventory_version": INVENTORY_VERSION,
        "scope": {
            "local_manifest_only": True,
            "network_access": False,
            "credential_access": False,
            "model_training": False,
            "paper_trading": False,
            "profitability_claim": False,
        },
        "r4_closed_window": {**_R4_WINDOW, "contract_hash": _R4_CONTRACT_HASH, "reusable": False},
        "candidates": candidates,
        "conclusion": {
            "status": "no_local_fresh_training_candidate",
            "model_contract_preflight_authorized": False,
            "data_only_preflight_candidate": "yahoo_broad_daily_2026_06_23",
            "operator_data_request": (
                "US daily PIT listings/delistings, as-of universe, and verified adjustment "
                "lineage; paid approval required."
            ),
        },
        "claude_review": {
            "verdict": "supported-with-limits",
            "reversal_fact": "PIT universe with delistings and verifiable adjustment provenance.",
        },
    }
    target.mkdir(parents=True, exist_ok=False)
    summary = target / "summary.json"
    with summary.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return LocalReplacementInventory(
        artifact_dir=target,
        summary_path=summary,
        summary_sha256=_sha256(summary),
        conclusion=str(payload["conclusion"]["status"]),
    )


def _inspect(spec: Mapping[str, Any], root: Path) -> dict[str, Any]:
    path = root.joinpath(*spec["path"])
    manifest = _manifest(path, str(spec["id"]))
    facts: dict[str, Any] = {}
    for name, (keys, expected) in spec["facts"].items():
        actual = _value(manifest, keys)
        if actual != expected:
            raise ValueError(f"{spec['id']} manifest fact changed: {name}")
        facts[name] = actual
    return {
        "id": spec["id"],
        "source": spec["source"],
        "timeframe": spec["timeframe"],
        "manifest_path": str(path.resolve()),
        "manifest_sha256": _sha256(path),
        "dataset_id": manifest.get("dataset_id", manifest.get("dataset")),
        "dataset_hash": manifest.get("dataset_hash"),
        "facts": facts,
        "rights": spec["rights"],
        "r4_overlap": spec["r4_overlap"],
        "disposition": spec["disposition"],
        "limitations": spec["limitations"],
    }


def _manifest(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} manifest is missing or unsafe")
    try:
        data = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} manifest is invalid") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label} manifest is invalid")
    return data


def _value(data: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    value: Any = data
    for key in keys:
        if not isinstance(value, Mapping) or key not in value:
            raise ValueError("manifest fact is missing")
        value = value[key]
    return value


def _external_root(root: Path, label: str, *, repo: Path | None = None) -> Path:
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"{label} root is invalid")
    resolved = root.resolve()
    if repo is not None and resolved.is_relative_to(repo):
        raise ValueError(f"{label} root must stay outside the Git workspace")
    return resolved


def _validate_target(target: Path, artifact_root: Path) -> None:
    if target.exists():
        raise FileExistsError(f"local replacement inventory already exists: {target}")
    parent = target.parent
    while not parent.exists():
        parent = parent.parent
    if parent.is_symlink() or not parent.resolve().is_relative_to(artifact_root):
        raise ValueError("local replacement inventory artifact path escapes its root")


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
