from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from thericher_v2.contracts import TargetExposureProposal


def test_receipt_script_writes_idempotent_sanitized_external_evidence(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    artifact_root = tmp_path / "model-artifacts"
    source_catalog = object()
    feature_catalog = SimpleNamespace(dataset_id="kis.paper.private.intraday.qqq.nas.m1.v1")
    feature_input = SimpleNamespace(
        catalog=feature_catalog,
        input_id="unit-input-id",
        input_hash="sha256:" + "a" * 64,
        session_dates=script._FROZEN_SESSION_DATES,
    )
    decided_at = datetime(2026, 7, 21, 20, 0, tzinfo=UTC)
    source = SimpleNamespace(bars=(SimpleNamespace(end_ts=decided_at),))
    capability = SimpleNamespace(
        symbol_scope=("QQQ", "SPY"),
        exchange_scope=("NAS", "AMS"),
        contract_sha256="sha256:" + "b" * 64,
    )
    proposal = TargetExposureProposal(
        proposal_id="unit-unqualified-proposal",
        symbol="QQQ",
        market="US",
        action="abstain",
        target_exposure=0,
        confidence=0,
        feature_schema_id="unit-feature-schema",
        input_status="unqualified",
        decided_at=decided_at,
        valid_until=decided_at + timedelta(minutes=1),
        feature_window_end=None,
        reason="unit_unqualified",
    )

    monkeypatch.setattr(
        script,
        "load_verified_kis_paper_private_intraday_catalog",
        lambda **_: source_catalog,
    )
    monkeypatch.setattr(
        script,
        "prepare_kis_paper_intraday_feature_input",
        lambda catalog, *, session_dates: _feature_input_for_test(
            catalog,
            session_dates,
            source_catalog=source_catalog,
            feature_input=feature_input,
        ),
    )
    monkeypatch.setattr(
        script,
        "require_complete_kis_paper_private_intraday_session",
        lambda *_args, **_kwargs: source,
    )
    monkeypatch.setattr(script, "observed_kis_paper_capabilities", lambda: (capability,))
    monkeypatch.setattr(
        script,
        "evaluate_kis_paper_baseline",
        lambda bars, **kwargs: _evaluation_for_test(
            bars,
            kwargs,
            source=source,
            capability=capability,
            proposal=proposal,
        ),
    )

    args = ["--artifact-root", str(artifact_root), "--run-id", "unit-r1"]
    script.main(args)
    first = json.loads(capsys.readouterr().out)
    script.main(args)
    second = json.loads(capsys.readouterr().out)

    destination = artifact_root / "kis-paper-baseline-receipt" / "unit-r1" / "receipt.json"
    assert first == second == json.loads(destination.read_text(encoding="utf-8"))
    assert first["mode"] == "offline_kis_native_receipt"
    assert first["receipt"]["decision_class"] == "abstain"
    assert first["receipt"]["input_status"] == "unqualified"
    assert first["local_paper_preparation"]["status"] == "no_intent"
    assert first["local_paper_preparation"]["reason"] == "receipt_not_eligible"
    rendered = json.dumps(first, sort_keys=True)
    for forbidden in ("QQQ", "NASD", "101.25", "KIS_LIVE", "credential"):
        assert forbidden not in rendered


def test_receipt_script_rejects_an_artifact_root_inside_git() -> None:
    script = _load_script()

    with pytest.raises(SystemExit):
        script.main(["--artifact-root", str(script._REPO_ROOT / "model_artifacts")])


def _feature_input_for_test(
    catalog: object,
    session_dates: tuple[object, ...],
    *,
    source_catalog: object,
    feature_input: object,
) -> object:
    assert catalog is source_catalog
    assert session_dates
    return feature_input


def _evaluation_for_test(
    bars: object,
    kwargs: dict[str, object],
    *,
    source: object,
    capability: object,
    proposal: TargetExposureProposal,
) -> SimpleNamespace:
    assert bars is source.bars
    assert kwargs["capability"] is capability
    assert kwargs["symbol"] == "QQQ"
    assert kwargs["market"] == "US"
    assert kwargs["as_of"] == source.bars[-1].end_ts
    return SimpleNamespace(proposal=proposal)


def _load_script() -> ModuleType:
    script_path = Path(__file__).parents[1] / "scripts" / "write_kis_paper_baseline_receipt.py"
    spec = importlib.util.spec_from_file_location(
        "write_kis_paper_baseline_receipt_for_test",
        script_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
