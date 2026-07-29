from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


def test_records_a_per_target_distribution_without_a_feasibility_verdict(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()
    repository_root = _repository_root(tmp_path)
    baseline = _panel("a", generation=604, target_counts=(8, 8), states=("ready", "complete"))
    candidate = _panel(
        "b",
        generation=4000,
        target_counts=(300, 600),
        states=("ready", "source_limited"),
    )
    candidate_manifest = tmp_path / "candidate.json"
    candidate_manifest.write_text("{}\n", encoding="ascii")
    postrun = _postrun_payload(baseline, candidate, candidate_manifest)
    postrun_path = tmp_path / "postrun.json"
    postrun_path.write_text(json.dumps(postrun, sort_keys=True), encoding="ascii")
    monkeypatch.setattr(
        script,
        "load_materialized_kis_paper_daily_broad_panel",
        lambda path, **_kwargs: baseline if Path(path).name == "baseline.json" else candidate,
    )
    monkeypatch.setattr(script, "compare_kis_paper_daily_broad_panels", lambda *_args: _equal())
    artifact_root = tmp_path / "artifacts"

    exit_code = script.main(
        [
            "--postrun-receipt",
            str(postrun_path),
            "--baseline-manifest",
            str(tmp_path / "baseline.json"),
            "--candidate-manifest",
            str(candidate_manifest),
            "--artifact-root",
            str(artifact_root),
            "--repository-root",
            str(repository_root),
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "recorded"
    assert "feasible" not in json.dumps(output, sort_keys=True).lower()
    assert output["distribution"]["bar_count_buckets"] == {
        "1_63": 0,
        "64_126": 0,
        "127_252": 0,
        "253_504": 1,
        "505_plus": 1,
    }
    assert output["distribution"]["state_counts"] == {"ready": 1, "source_limited": 1}
    receipt_paths = list(artifact_root.glob("chronology-*.json"))
    assert len(receipt_paths) == 1
    _assert_source_safe(json.loads(receipt_paths[0].read_text(encoding="utf-8")))


def test_preserves_a_noncomplete_postrun_without_new_observation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()
    repository_root = _repository_root(tmp_path)
    postrun_path = tmp_path / "postrun.json"
    postrun_path.write_text(
        json.dumps(
            {
                "kind": "kis_paper_daily_broad_panel_postrun",
                "status": "retry",
                "reason": "index_changed_during_reattest",
            }
        ),
        encoding="ascii",
    )
    artifact_root = tmp_path / "artifacts"

    exit_code = script.main(
        [
            "--postrun-receipt",
            str(postrun_path),
            "--baseline-manifest",
            str(tmp_path / "baseline.json"),
            "--candidate-manifest",
            str(tmp_path / "candidate.json"),
            "--artifact-root",
            str(artifact_root),
            "--repository-root",
            str(repository_root),
        ]
    )

    assert exit_code == 20
    assert json.loads(capsys.readouterr().out) == {
        "status": "not_recorded",
        "reason": "postrun_not_complete",
    }
    assert not artifact_root.exists()


def test_chronology_script_stays_offline_and_nonpromoting() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "observe_kis_paper_daily_broad_panel_chronology.py"
    ).read_text(encoding="ascii").lower()

    for forbidden in (
        ".env",
        "kis_paper_app_",
        "kis_paper_account",
        "kis_live_",
        "os.getenv",
        "socket",
        "urllib",
        "requests",
        "subprocess",
        "docker",
        "feasible",
        "model.fit",
    ):
        assert forbidden not in source


def _postrun_payload(
    baseline: SimpleNamespace,
    candidate: SimpleNamespace,
    candidate_manifest: Path,
) -> dict[str, object]:
    comparison = _equal()
    return {
        "kind": "kis_paper_daily_broad_panel_postrun",
        "status": "complete",
        "reason": "stable_full_breadth_panel",
        "baseline": {
            "dataset_hash": baseline.dataset_hash,
            "index_generation": baseline.index_generation,
        },
        "candidate": {
            "dataset_hash": candidate.dataset_hash,
            "index_generation": candidate.index_generation,
            "target_count": len(candidate.target_keys),
            "covered_target_count": candidate.covered_target_count,
            "zero_coverage_target_count": candidate.zero_coverage_target_count,
            "quarantined_target_count": candidate.quarantined_target_count,
            "manifest_sha256": _sha256(candidate_manifest.read_bytes()),
        },
        "continuity": {
            "status": comparison.status,
            "shared_target_count": comparison.shared_target_count,
            "shared_row_count": comparison.shared_row_count,
            "mismatched_target_count": comparison.mismatched_target_count,
            "mismatched_row_count": comparison.mismatched_row_count,
        },
    }


def _panel(
    hash_character: str,
    *,
    generation: int,
    target_counts: tuple[int, ...],
    states: tuple[str, ...],
) -> SimpleNamespace:
    target_keys = tuple(f"S{index}/NAS" for index in range(len(target_counts)))
    targets = {
        key: SimpleNamespace(
            bar_count=target_counts[index],
            state=states[index],
            coverage_start="2024-01-02",
            coverage_end="2026-07-28",
        )
        for index, key in enumerate(target_keys)
    }
    return SimpleNamespace(
        dataset_hash="sha256:" + hash_character * 64,
        index_generation=generation,
        target_keys=target_keys,
        covered_target_count=len(target_keys),
        zero_coverage_target_count=0,
        quarantined_target_count=0,
        targets_by_key=targets,
    )


def _equal() -> SimpleNamespace:
    return SimpleNamespace(
        status="equal",
        shared_target_count=2,
        shared_row_count=16,
        mismatched_target_count=0,
        mismatched_row_count=0,
    )


def _repository_root(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    return root


def _load_script() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "observe_kis_paper_daily_broad_panel_chronology.py"
    )
    specification = importlib.util.spec_from_file_location(
        "observe_kis_paper_daily_broad_panel_chronology_for_test",
        script_path,
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _assert_source_safe(value: object) -> None:
    forbidden = {"open", "high", "low", "close", "volume", "price", "prices", "raw"}
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = "".join(character for character in key.lower() if character.isalnum())
            assert normalized not in forbidden
            _assert_source_safe(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_source_safe(nested)
