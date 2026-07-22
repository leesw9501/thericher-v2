"""Write one reproducible, safe receipt for the frozen KIS-native QQQ input."""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.data import (
    load_verified_kis_paper_private_intraday_catalog,
    prepare_kis_paper_intraday_feature_input,
    require_complete_kis_paper_private_intraday_session,
    us_equity_2026_session,
)
from thericher_v2.data.kis_capability import observed_kis_paper_capabilities
from thericher_v2.execution.paper_decision_bridge import (
    PaperDecisionExecutionBinding,
    prepare_local_paper_intent,
)
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    receipt_from_target_exposure_proposal,
)
from thericher_v2.research.kis_paper_baseline import evaluate_kis_paper_baseline

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\intraday")
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_DEFAULT_RUN_ID = "qqq-20260623-20260721-receipt-r1"
_FROZEN_SESSION_DATES = (
    date(2026, 6, 23),
    date(2026, 6, 24),
    date(2026, 6, 25),
    date(2026, 6, 26),
    date(2026, 6, 29),
    date(2026, 6, 30),
    date(2026, 7, 1),
    date(2026, 7, 2),
    date(2026, 7, 6),
    date(2026, 7, 7),
    date(2026, 7, 8),
    date(2026, 7, 9),
    date(2026, 7, 10),
    date(2026, 7, 13),
    date(2026, 7, 14),
    date(2026, 7, 15),
    date(2026, 7, 16),
    date(2026, 7, 17),
    date(2026, 7, 20),
    date(2026, 7, 21),
)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--run-id", default=_DEFAULT_RUN_ID)
    args = parser.parse_args(argv)

    artifact_root = Path(args.artifact_root).resolve()
    if artifact_root.is_relative_to(_REPO_ROOT.resolve()):
        parser.error("--artifact-root must stay outside Git")
    run_id = str(args.run_id).strip()
    allowed_run_id_characters = "abcdefghijklmnopqrstuvwxyz0123456789-._"
    if not run_id or any(character not in allowed_run_id_characters for character in run_id):
        parser.error(
            "--run-id must contain only lowercase letters, digits, dot, dash, or underscore"
        )

    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=Path(args.cache_root),
        repo_root=_REPO_ROOT,
        symbol="QQQ",
        exchange="NAS",
    )
    feature_input = prepare_kis_paper_intraday_feature_input(
        catalog,
        session_dates=_FROZEN_SESSION_DATES,
    )
    latest_session = us_equity_2026_session(_FROZEN_SESSION_DATES[-1])
    if latest_session is None:
        raise RuntimeError("frozen receipt session is unavailable")
    latest_bars = require_complete_kis_paper_private_intraday_session(
        feature_input.catalog,
        session=latest_session.window,
    ).bars
    capability = next(
        item
        for item in observed_kis_paper_capabilities()
        if item.symbol_scope == ("QQQ", "SPY") and "NAS" in item.exchange_scope
    )
    evaluation = evaluate_kis_paper_baseline(
        latest_bars,
        capability=capability,
        symbol="QQQ",
        market="US",
        as_of=latest_bars[-1].end_ts,
    )
    input_manifest_ref = _sha256_reference(
        {
            "capability_contract_sha256": capability.contract_sha256,
            "dataset_id": feature_input.catalog.dataset_id,
            "feature_input_hash": feature_input.input_hash,
            "feature_input_id": feature_input.input_id,
            "schema_version": SCHEMA_VERSION,
            "session_dates": [value.isoformat() for value in feature_input.session_dates],
        }
    )
    references = DecisionReceiptReferences(
        campaign_ref=_opaque_reference("campaign", input_manifest_ref),
        model_ref=_opaque_reference("model", input_manifest_ref),
        input_manifest_ref=input_manifest_ref,
        proposal_ref=_opaque_reference(
            "proposal",
            input_manifest_ref,
            evaluation.proposal.proposal_id,
        ),
    )
    receipt = receipt_from_target_exposure_proposal(evaluation.proposal, references=references)
    local_preparation = prepare_local_paper_intent(
        receipt,
        binding=PaperDecisionExecutionBinding(
            proposal_ref=receipt.proposal_ref,
            symbol="QQQ",
            exchange="NASD",
            quantity=1,
        ),
        as_of=receipt.decided_at,
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_baseline_receipt",
        "mode": "offline_kis_native_receipt",
        "input_manifest_ref": input_manifest_ref,
        "receipt": receipt.to_payload(),
        "local_paper_preparation": local_preparation.safe_payload(),
        "claim": "identified KIS-native input receipt only; no KIS order or live behavior",
    }
    destination = artifact_root / "kis-paper-baseline-receipt" / run_id / "receipt.json"
    _write_or_verify(destination, payload)
    print(json.dumps(payload, sort_keys=True))


def _opaque_reference(*parts: str) -> str:
    return "ref:" + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _sha256_reference(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _write_or_verify(destination: Path, payload: dict[str, object]) -> None:
    encoded = (
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if destination.exists():
        if destination.read_bytes() != encoded:
            raise ValueError("receipt artifact identity conflicts with existing evidence")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.stage")
    try:
        staging.write_bytes(encoded)
        staging.replace(destination)
    finally:
        staging.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
