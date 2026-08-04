from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from thericher_v2.data.norgate_trial_raw_d1 import NorgateTrialRawD1Result

_DATASET_HASH = "sha256:" + "c" * 64
_MANIFEST_HASH = "sha256:" + "d" * 64
_PRIVATE_SOURCE = r"D:\private-source\norgate\snapshot=operator-supplied"


def test_runner_requires_snapshot_and_binds_the_verified_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _load_runner()
    source = _verified_source()
    supplied_snapshot = tmp_path / "market-data" / "snapshot=explicit"
    artifact_root = tmp_path / "external-artifacts"
    market_data_root = tmp_path / "market-data"
    observed: dict[str, object] = {}

    def verify(snapshot_dir: Path, **kwargs: object) -> NorgateTrialRawD1Result:
        observed["verification"] = (snapshot_dir, kwargs)
        return source

    def build(**kwargs: object) -> SimpleNamespace:
        observed["build"] = kwargs
        return SimpleNamespace(
            receipt_sha256="sha256:" + "e" * 64,
            safe_payload=lambda: {
                "status": "matching",
                "reason": "active_build_matches_frozen_contract",
                "reference_dataset_hash": _DATASET_HASH,
                "reference_manifest_hash": _MANIFEST_HASH,
                "reference_bar_count": 1536,
                "active_bar_count": 1536,
                "divergent_bar_count": 0,
                "active_response_sha256": "sha256:" + "f" * 64,
                "per_symbol": [{"not": "printed"}],
            },
        )

    monkeypatch.setattr(runner, "verify_norgate_trial_raw_d1_snapshot", verify)
    monkeypatch.setattr(runner, "build_norgate_active_build_revision_receipt", build)
    assert runner.main(
        [
            "--snapshot-dir",
            str(supplied_snapshot),
            "--run-label",
            "unit-explicit",
            "--artifact-root",
            str(artifact_root),
            "--market-data-root",
            str(market_data_root),
        ]
    ) == 0

    assert observed["verification"] == (
        supplied_snapshot,
        {
            "market_data_root": market_data_root,
            "repo_root": runner.REPOSITORY_ROOT,
        },
    )
    build_kwargs = observed["build"]
    assert isinstance(build_kwargs, dict)
    assert build_kwargs["destination"] == artifact_root / "revision-unit-explicit"
    reference = build_kwargs["reference"]
    assert reference.snapshot_dir == source.snapshot_dir
    assert reference.expected_dataset_hash == _DATASET_HASH
    assert reference.expected_manifest_hash == _MANIFEST_HASH

    output = capsys.readouterr().out
    printed = json.loads(output)
    assert printed == {
        "active_bar_count": 1536,
        "active_response_sha256": "sha256:" + "f" * 64,
        "divergent_bar_count": 0,
        "probe_id": runner.NORGATE_ACTIVE_BUILD_REVISION_PROBE_ID,
        "reason": "active_build_matches_frozen_contract",
        "receipt_sha256": "sha256:" + "e" * 64,
        "reference_bar_count": 1536,
        "reference_dataset_hash": _DATASET_HASH,
        "reference_manifest_hash": _MANIFEST_HASH,
        "status": "matching",
    }
    assert "per_symbol" not in output
    assert _PRIVATE_SOURCE not in output


def test_runner_rejects_missing_explicit_snapshot_directory() -> None:
    runner = _load_runner()

    with pytest.raises(SystemExit) as excinfo:
        runner.main(["--run-label", "unit-missing"])

    assert excinfo.value.code == 2


def test_runner_static_surface_excludes_secret_broker_and_model_paths() -> None:
    source = _script_path().read_text(encoding="ascii").casefold()

    for forbidden in (
        ".env",
        "broker",
        "dotenv",
        "kis_",
        "model",
        "orderintent",
        "os.environ",
        "sklearn",
        "torch",
    ):
        assert forbidden not in source
    assert "norgaterawdailybarprovider" not in source
    assert "verify_norgate_trial_raw_d1_snapshot" in source


def _verified_source() -> NorgateTrialRawD1Result:
    return NorgateTrialRawD1Result(
        snapshot_dir=Path(_PRIVATE_SOURCE),
        dataset_id="unit.fixed-trio",
        dataset_hash=_DATASET_HASH,
        manifest_hash=_MANIFEST_HASH,
        row_count=1536,
        common_session_count=512,
        event_marker_count=0,
        excluded_session_count=0,
        actual_start=date(2030, 1, 2),
        actual_end=date(2032, 1, 2),
        norgate_package_version="fixture",
        free_percent=40.0,
    )


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "norgate_fixed_trio_active_build_revision_runner",
        _script_path(),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_norgate_fixed_trio_active_build_revision.py"
    )
