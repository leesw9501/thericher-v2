from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


def test_freeze_mode_dispatches_the_fixed_offline_campaign(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script_module()
    observed: dict[str, object] = {}
    feature_artifact = tmp_path / "feature-artifact"
    artifact_root = tmp_path / "external-artifacts"
    market_data_root = tmp_path / "market-data"
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    monkeypatch.setattr(
        script,
        "freeze_norgate_broad_development_campaign_from_artifact",
        lambda path, **kwargs: observed.update({"path": path, **kwargs})
        or SimpleNamespace(
            campaign_id=script.NORGATE_BROAD_OPPORTUNITY_DEVELOPMENT_CAMPAIGN.campaign_id,
            contract_path=artifact_root / "campaign-contract.json",
            contract_sha256="sha256:" + "a" * 64,
            artifact_hash="sha256:" + "b" * 64,
            derived_contract_hash="sha256:" + "c" * 64,
        ),
    )

    script.main(
        [
            "--mode",
            "freeze",
            "--feature-artifact",
            str(feature_artifact),
            "--artifact-root",
            str(artifact_root),
            "--market-data-root",
            str(market_data_root),
            "--repo-root",
            str(repository_root),
            "--code-revision",
            "unit-test",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert observed["path"] == feature_artifact
    expected_campaign = script.NORGATE_BROAD_OPPORTUNITY_DEVELOPMENT_CAMPAIGN.campaign_id
    assert observed["campaign_id"] == expected_campaign
    assert payload["mode"] == "freeze"
    assert payload["campaign_id"] == observed["campaign_id"]


def test_cuda_mode_requires_the_single_allowlisted_job() -> None:
    script = _load_script_module()

    with pytest.raises(SystemExit, match="2"):
        script.main(["--mode", "cuda"])


def _load_script_module() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_norgate_broad_opportunity_development.py"
    )
    spec = importlib.util.spec_from_file_location("norgate_opportunity_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Norgate opportunity campaign script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
