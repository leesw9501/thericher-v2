"""Run one offline KIS-cache momentum-to-policy structural smoke."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from thericher_v2.contracts import Timeframe
from thericher_v2.data import (
    load_verified_kis_paper_private_intraday_catalog,
    require_complete_kis_paper_private_intraday_session,
    us_equity_2026_session,
)
from thericher_v2.models import (
    CurrentSourceMetadata,
    MultiTimeframeMomentumConfig,
    MultiTimeframeMomentumSpec,
    OpportunityEligibility,
    TargetPositionPolicyConfig,
    adapt_current_source_opportunity_eligibility,
    build_causal_bar_source_contract,
    build_multitimeframe_momentum_evidence,
    propose_target_exposure,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\intraday")
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_SYMBOL_EXCHANGES = {"QQQ": "NAS", "SPY": "AMS"}
_TIMEFRAMES = (Timeframe.M1, Timeframe.M5, Timeframe.M10, Timeframe.H1, Timeframe.H3)


def main(
    argv: Sequence[str] | None = None,
    *,
    upstream_candidate_factory: Callable[..., OpportunityEligibility] | None = None,
) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--symbol", choices=tuple(_SYMBOL_EXCHANGES), default="QQQ")
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--run-label")
    args = parser.parse_args(argv)

    try:
        session_date = date.fromisoformat(args.session_date)
    except ValueError:
        parser.error("--session-date must use YYYY-MM-DD")
    session = us_equity_2026_session(session_date)
    if session is None:
        parser.error("--session-date is not a 2026 US equity trading session")
    artifact_root = Path(args.artifact_root).resolve()
    _reject_repo_artifact_root(artifact_root)

    symbol = str(args.symbol).upper()
    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=args.cache_root,
        repo_root=_REPO_ROOT,
        symbol=symbol,
        exchange=_SYMBOL_EXCHANGES[symbol],
    )
    source = require_complete_kis_paper_private_intraday_session(
        catalog,
        session=session.window,
    )
    evidence = build_multitimeframe_momentum_evidence(
        source.bars,
        session=session.window,
        config=_momentum_config(),
        as_of=session.window.close_ts,
    )
    expected_contract = build_causal_bar_source_contract(
        source.bars,
        contract_id="kis-private-intraday-momentum-smoke-v1",
        as_of=session.window.close_ts,
    )
    source_complete = all(bar.complete for bar in source.bars)
    candidate = (upstream_candidate_factory or _predeclared_smoke_candidate)(
        symbol=symbol,
        market="US",
        session_date=session.session_date,
        as_of=session.window.close_ts,
    )
    opportunity = adapt_current_source_opportunity_eligibility(
        candidate,
        CurrentSourceMetadata(
            contract=expected_contract,
            symbol=symbol,
            market="US",
            input_status="ready" if source_complete else "incomplete",
            complete=source_complete,
            observed_at=session.window.close_ts,
            valid_until=session.window.close_ts + timedelta(minutes=2),
        ),
        expected_contract=expected_contract,
        as_of=session.window.close_ts,
    )
    proposal = propose_target_exposure(
        opportunity.eligibility,
        evidence.predictions,
        current_exposure=Decimal("0"),
        config=_policy_config(),
        as_of=session.window.close_ts,
    )
    run_label = args.run_label or f"{symbol.lower()}-{session.session_date.isoformat()}-r1"
    _validate_run_label(run_label)
    output_dir = artifact_root / "research" / "multitimeframe-momentum-policy-smoke-v1" / run_label
    if output_dir.exists():
        raise FileExistsError(f"smoke artifact already exists: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)
    summary = {
        "schema_version": 1,
        "kind": "multitimeframe_momentum_policy_smoke",
        "status": "complete",
        "mode": "offline_local_cache_no_broker",
        "source": {
            "dataset_id": source.dataset_id,
            "dataset_hash": source.dataset_hash,
            "session_date": session.session_date.isoformat(),
            "symbol": symbol,
        },
        "evidence": {
            "input_status": evidence.input_status,
            "reason": evidence.reason,
            "timeframes": [
                prediction.signal.timeframe.value for prediction in evidence.predictions
            ],
            "actions": [prediction.signal.action for prediction in evidence.predictions],
        },
        "opportunity": {
            "input_status": opportunity.input_status,
            "reason": opportunity.reason,
        },
        "proposal": {
            "action": proposal.action,
            "input_status": proposal.input_status,
            "reason": proposal.reason,
        },
        "artifact_policy": {
            "raw_market_data_written": False,
            "checkpoint_written": False,
            "credential_read": False,
            "network_called": False,
            "broker_called": False,
            "artifact_root": str(artifact_root),
        },
        "claim": (
            "structural completed-bar model-to-policy smoke only; not a profitability, "
            "selection, or order claim"
        ),
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))


def _predeclared_smoke_candidate(
    *,
    symbol: str,
    market: str,
    session_date: date,
    as_of: datetime,
) -> OpportunityEligibility:
    """Return the explicit fixed-scope candidate for this structural smoke."""

    return OpportunityEligibility(
        opportunity_ref=_opaque_reference(
            "predeclared-momentum-smoke-candidate-v1",
            symbol,
            market,
            session_date.isoformat(),
            as_of.isoformat(),
        ),
        symbol=symbol,
        market=market,
        eligible=True,
        input_status="ready",
        observed_at=as_of,
        valid_until=as_of + timedelta(minutes=2),
    )


def _momentum_config() -> MultiTimeframeMomentumConfig:
    return MultiTimeframeMomentumConfig(
        feature_schema_id="multitimeframe-momentum-ohlcv-v1",
        experts=(
            MultiTimeframeMomentumSpec(Timeframe.M1, 5, Decimal("1"), Decimal("-1")),
            MultiTimeframeMomentumSpec(Timeframe.M5, 4, Decimal("1"), Decimal("-1")),
            MultiTimeframeMomentumSpec(Timeframe.M10, 3, Decimal("1"), Decimal("-1")),
            MultiTimeframeMomentumSpec(Timeframe.H1, 3, Decimal("1"), Decimal("-1")),
            MultiTimeframeMomentumSpec(Timeframe.H3, 1, Decimal("1"), Decimal("-1")),
        ),
    )


def _policy_config() -> TargetPositionPolicyConfig:
    return TargetPositionPolicyConfig(
        policy_id="multitimeframe-momentum-policy-smoke-v1",
        feature_schema_id="multitimeframe-momentum-ohlcv-v1",
        required_timeframes=_TIMEFRAMES,
        maximum_evidence_age={
            Timeframe.M1: timedelta(minutes=2),
            Timeframe.M5: timedelta(minutes=10),
            Timeframe.M10: timedelta(minutes=20),
            Timeframe.H1: timedelta(hours=1),
            Timeframe.H3: timedelta(hours=3),
        },
        minimum_confidence=Decimal("0.01"),
        minimum_absolute_edge_bps=Decimal("0.01"),
        entry_target_exposure=Decimal("0.10"),
        decision_ttl=timedelta(minutes=2),
    )


def _opaque_reference(*parts: str) -> str:
    payload = "|".join(parts).encode("utf-8")
    return f"ref:{hashlib.sha256(payload).hexdigest()}"


def _reject_repo_artifact_root(artifact_root: Path) -> None:
    if artifact_root == _REPO_ROOT or artifact_root.is_relative_to(_REPO_ROOT):
        raise ValueError("artifact root must stay outside the Git workspace")


def _validate_run_label(value: str) -> None:
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789-_"
    if not value or any(character not in allowed for character in value):
        raise ValueError("run label must use lowercase letters, digits, hyphens, or underscores")


if __name__ == "__main__":
    main()
