"""Independent source-safe reattestation for the bounded D1 state smoke."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from pathlib import Path

from thericher_v2.contracts import SCHEMA_VERSION

from .kis_daily_overnight_intraday_state import (
    KIS_DAILY_OVERNIGHT_INTRADAY_STATE_ID,
    KIS_DAILY_OVERNIGHT_INTRADAY_STATE_LOOKBACK_SESSIONS,
    KIS_DAILY_OVERNIGHT_INTRADAY_STATE_SMOKE_SLOT_COUNT,
    KIS_DAILY_OVERNIGHT_INTRADAY_STATE_SYMBOLS,
)
from .kis_daily_relative_regime_control import load_current_kis_daily_relative_regime_input

KIS_DAILY_OVERNIGHT_INTRADAY_STATE_VALIDATION_ID = (
    "kis-daily-overnight-intraday-state-validation-v1"
)
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_RAW_FIELDS = frozenset(
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
        "eventjsonl",
        "eventlog",
        "sourcepath",
        "statesqlite",
        "workdir",
    }
)


def validate_current_kis_daily_overnight_intraday_state_cpu_smoke(
    *,
    cache_root: Path | str,
    artifact_root: Path | str,
    precommit_path: Path | str,
    summary_path: Path | str,
    run_label: str,
    repository_root: Path | str | None = None,
) -> tuple[str, str, Path]:
    """Reload source identity and reattest one prior smoke without replaying it."""

    if _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        raise ValueError("run label is invalid")
    repository = (Path.cwd() if repository_root is None else Path(repository_root)).resolve()
    root = _artifact_root(Path(artifact_root), repository)
    precommit_file = _artifact_file(Path(precommit_path), root)
    summary_file = _artifact_file(Path(summary_path), root)
    if precommit_file.parent != summary_file.parent:
        raise ValueError("smoke artifacts must share one directory")
    if any(
        path
        for pattern in ("*.jsonl", "*.sqlite", "*.pt", "*.pkl", "*.joblib")
        for path in precommit_file.parent.glob(pattern)
    ):
        raise ValueError("smoke persisted a prohibited artifact")
    precommit = _mapping(_read_json(precommit_file))
    summary = _mapping(_read_json(summary_file))
    _reject_raw_fields(precommit)
    _reject_raw_fields(summary)
    precommit_hash = precommit.get("precommit_hash")
    unsigned = {key: value for key, value in precommit.items() if key != "precommit_hash"}
    if not _is_sha256(precommit_hash) or _sha256_json(unsigned) != precommit_hash:
        raise ValueError("smoke precommit identity is invalid")
    source_input = load_current_kis_daily_relative_regime_input(
        cache_root=cache_root,
        repository_root=repository,
    )
    catalog = source_input.catalog
    expected_source = {
        "dataset_id": catalog.dataset_id,
        "dataset_hash": catalog.dataset_hash,
        "index_hash": catalog.index_hash,
        "symbols": list(KIS_DAILY_OVERNIGHT_INTRADAY_STATE_SYMBOLS),
        "completed_d1_session_count": len(catalog.common_sessions),
        "adjustment_mode": catalog.adjustment_mode,
        "limitations": list(catalog.raw_price_limitations),
        "source_mixing_allowed": False,
    }
    if (
        precommit.get("kind") != KIS_DAILY_OVERNIGHT_INTRADAY_STATE_ID
        or precommit.get("status") != "precommitted"
        or precommit.get("mode") != "cpu-smoke"
        or precommit.get("source") != expected_source
        or _mapping(precommit.get("rule")).get("feature_window_completed_d1_count")
        != KIS_DAILY_OVERNIGHT_INTRADAY_STATE_LOOKBACK_SESSIONS + 1
        or precommit.get("comparators")
        != ["flat", "always_long", "previous_bar_direction"]
        or _mapping(precommit.get("review")).get("claude_verdict") != "unsupported"
        or _mapping(precommit.get("scope")).get("full_validation_eligible") is not False
    ):
        raise ValueError("smoke contract is invalid")
    _validate_summary(summary, precommit_hash, expected_source)
    summary_hash = "sha256:" + hashlib.sha256(_json_bytes(summary)).hexdigest()
    receipt_path = precommit_file.parent / f"validation-{run_label}-{uuid.uuid4().hex[:8]}.json"
    _write_json(
        receipt_path,
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIS_DAILY_OVERNIGHT_INTRADAY_STATE_VALIDATION_ID,
            "status": "attested",
            "precommit_hash": precommit_hash,
            "summary_hash": summary_hash,
            "source": expected_source,
            "checks": {
                "source_reattested": True,
                "causal_contract": True,
                "local_paper_only": True,
                "unsupported_scope_preserved": True,
                "raw_artifact_fields_absent": True,
            },
            "scope": {
                "network_used": False,
                "credential_used": False,
                "broker_used": False,
                "paper_order_used": False,
                "gpu_used": False,
                "performance_claim": False,
            },
        },
    )
    return precommit_hash, summary_hash, receipt_path


def _validate_summary(
    summary: Mapping[str, object], precommit_hash: str, expected_source: Mapping[str, object]
) -> None:
    if (
        summary.get("kind") != KIS_DAILY_OVERNIGHT_INTRADAY_STATE_ID
        or summary.get("status") != "complete"
        or summary.get("mode") != "cpu-smoke"
        or summary.get("precommit_hash") != precommit_hash
        or summary.get("outcome") != "operational_smoke"
        or summary.get("source") != expected_source
        or _mapping(summary.get("review")).get("claude_verdict") != "unsupported"
    ):
        raise ValueError("smoke summary identity is invalid")
    scope = _mapping(summary.get("scope"))
    protected_scope_keys = (
        "gpu_used",
        "network_used",
        "credential_used",
        "broker_used",
        "paper_order_used",
        "full_validation_eligible",
        "promotion_eligible",
    )
    if any(scope.get(key) is not False for key in protected_scope_keys):
        raise ValueError("smoke summary scope widened unexpectedly")
    metrics = _mapping(_mapping(summary.get("validation")).get("metrics_by_symbol"))
    if set(metrics) != set(KIS_DAILY_OVERNIGHT_INTRADAY_STATE_SYMBOLS):
        raise ValueError("smoke metric symbols are invalid")
    for symbol in KIS_DAILY_OVERNIGHT_INTRADAY_STATE_SYMBOLS:
        roles = _mapping(metrics[symbol])
        if set(roles) != {"candidate", "always_long", "previous_bar_direction", "flat"}:
            raise ValueError("smoke metric roles are invalid")
        for role, metric in roles.items():
            _validate_metric(symbol, role, _mapping(metric))


def _validate_metric(symbol: str, role: str, metric: Mapping[str, object]) -> None:
    if (
        metric.get("symbol") != symbol
        or metric.get("role") != role
        or metric.get("decision_slot_count") != KIS_DAILY_OVERNIGHT_INTRADAY_STATE_SMOKE_SLOT_COUNT
        or not isinstance(metric.get("trade_count"), int)
        or metric.get("local_paper_fill_count") != metric["trade_count"] * 2
        or metric.get("fill_source") != "local_paper"
        or metric.get("all_fills_local_paper") is not True
        or metric.get("replayable") is not True
        or metric.get("final_position") != "0"
        or not _is_sha256(metric.get("replay_identity_hash"))
    ):
        raise ValueError("smoke replay metric is invalid")
    if role == "flat" and metric["trade_count"] != 0:
        raise ValueError("flat smoke metric is invalid")
    if (
        role == "always_long"
        and metric["trade_count"] != KIS_DAILY_OVERNIGHT_INTRADAY_STATE_SMOKE_SLOT_COUNT
    ):
        raise ValueError("always-long smoke metric is invalid")


def _artifact_root(candidate: Path, repository: Path) -> Path:
    root = candidate.resolve()
    mounted = root == repository / "model_artifacts" and root.is_mount()
    if candidate.is_symlink() or (_contains(repository, root) and not mounted):
        raise ValueError("artifact root must stay outside Git")
    return root


def _artifact_file(candidate: Path, root: Path) -> Path:
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError("artifact file is invalid")
    path = candidate.resolve()
    if not _contains(root, path):
        raise ValueError("artifact file is outside the artifact root")
    return path


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("artifact JSON is invalid") from error


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError("artifact mapping is invalid")
    return value


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    _reject_raw_fields(payload)
    with path.open("xb") as handle:
        handle.write(_json_bytes(payload))


def _reject_raw_fields(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = "".join(character for character in str(key).lower() if character.isalnum())
            if normalized in _RAW_FIELDS:
                raise ValueError("artifact contains a raw market field")
            _reject_raw_fields(nested)
    elif isinstance(value, list | tuple):
        for nested in value:
            _reject_raw_fields(nested)


def _contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def _sha256_json(payload: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(_json_bytes(payload)).hexdigest()


def _json_bytes(payload: Mapping[str, object]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
