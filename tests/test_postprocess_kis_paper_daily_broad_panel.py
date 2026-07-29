from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


def test_postprocess_writes_a_full_breadth_continuity_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()
    repository_root = _repository_root(tmp_path)
    baseline = _panel(
        "a", generation=604, target_count=3, covered=2, zero=1, quarantined=0, rows=8
    )
    candidate = _panel(
        "b", generation=4000, target_count=3, covered=3, zero=0, quarantined=0, rows=18
    )
    materialized = SimpleNamespace(
        panel=candidate,
        manifest_path=tmp_path / "panels" / "candidate.json",
        manifest_hash="sha256:" + "c" * 64,
    )
    comparison = SimpleNamespace(
        status="equal",
        shared_target_count=2,
        shared_row_count=8,
        mismatched_target_count=0,
        mismatched_row_count=0,
    )
    continuity = SimpleNamespace(
        comparison=comparison,
        receipt_hash="sha256:" + "d" * 64,
    )
    monkeypatch.setattr(
        script,
        "materialize_kis_paper_daily_broad_panel",
        lambda **_kwargs: materialized,
    )
    monkeypatch.setattr(
        script,
        "load_materialized_kis_paper_daily_broad_panel",
        lambda *_args, **_kwargs: baseline,
    )
    monkeypatch.setattr(
        script,
        "materialize_kis_paper_daily_broad_panel_continuity",
        lambda **_kwargs: continuity,
    )
    artifact_root = tmp_path / "artifacts"

    exit_code = script.main(
        [
            "--baseline-manifest",
            str(tmp_path / "baseline.json"),
            "--postrun-artifact-root",
            str(artifact_root),
            "--repository-root",
            str(repository_root),
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "complete"
    assert output["reason"] == "stable_full_breadth_panel"
    assert output["candidate"]["covered_target_count"] == 3
    assert output["continuity"]["shared_row_count"] == 8
    receipt_paths = list(artifact_root.glob("postrun-*.json"))
    assert len(receipt_paths) == 1
    receipt = json.loads(receipt_paths[0].read_text(encoding="utf-8"))
    assert receipt == {key: value for key, value in output.items() if key != "receipt_sha256"}
    _assert_source_safe(receipt)


def test_postprocess_retains_a_scoped_retry_for_an_unstable_index(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()
    repository_root = _repository_root(tmp_path)
    monkeypatch.setattr(
        script,
        "materialize_kis_paper_daily_broad_panel",
        lambda **_kwargs: (_ for _ in ()).throw(
            ValueError("broad daily panel index changed during reattestation")
        ),
    )
    artifact_root = tmp_path / "artifacts"

    exit_code = script.main(
        [
            "--postrun-artifact-root",
            str(artifact_root),
            "--repository-root",
            str(repository_root),
        ]
    )

    assert exit_code == 20
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "retry"
    assert output["reason"] == "index_changed_during_reattest"
    assert "error" not in output
    assert len(list(artifact_root.glob("postrun-*.json"))) == 1


def test_postprocess_rejects_a_stable_panel_with_incomplete_breadth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()
    repository_root = _repository_root(tmp_path)
    baseline = _panel(
        "a", generation=604, target_count=3, covered=2, zero=1, quarantined=0, rows=8
    )
    candidate = _panel(
        "b", generation=4000, target_count=3, covered=2, zero=1, quarantined=0, rows=12
    )
    materialized = SimpleNamespace(
        panel=candidate,
        manifest_path=tmp_path / "panels" / "candidate.json",
        manifest_hash="sha256:" + "c" * 64,
    )
    continuity = SimpleNamespace(
        comparison=SimpleNamespace(
            status="equal",
            shared_target_count=2,
            shared_row_count=8,
            mismatched_target_count=0,
            mismatched_row_count=0,
        ),
        receipt_hash="sha256:" + "d" * 64,
    )
    monkeypatch.setattr(
        script,
        "materialize_kis_paper_daily_broad_panel",
        lambda **_kwargs: materialized,
    )
    monkeypatch.setattr(
        script,
        "load_materialized_kis_paper_daily_broad_panel",
        lambda *_args, **_kwargs: baseline,
    )
    monkeypatch.setattr(
        script,
        "materialize_kis_paper_daily_broad_panel_continuity",
        lambda **_kwargs: continuity,
    )

    exit_code = script.main(
        [
            "--postrun-artifact-root",
            str(tmp_path / "artifacts"),
            "--repository-root",
            str(repository_root),
        ]
    )

    assert exit_code == 20
    output = json.loads(capsys.readouterr().out)
    assert output["reason"] == "full_breadth_coverage_incomplete"


def test_postprocess_script_stays_offline_and_credential_free() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "postprocess_kis_paper_daily_broad_panel.py"
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
    ):
        assert forbidden not in source


def _panel(
    hash_character: str,
    *,
    generation: int,
    target_count: int,
    covered: int,
    zero: int,
    quarantined: int,
    rows: int,
) -> SimpleNamespace:
    target_keys = tuple(f"S{index}/NAS" for index in range(target_count))
    targets = {
        key: SimpleNamespace(bar_count=(rows // covered if index < covered else 0))
        for index, key in enumerate(target_keys)
    }
    return SimpleNamespace(
        dataset_hash="sha256:" + hash_character * 64,
        index_generation=generation,
        target_keys=target_keys,
        covered_target_count=covered,
        zero_coverage_target_count=zero,
        quarantined_target_count=quarantined,
        targets_by_key=targets,
    )


def _repository_root(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    return root


def _load_script() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "postprocess_kis_paper_daily_broad_panel.py"
    )
    specification = importlib.util.spec_from_file_location(
        "postprocess_kis_paper_daily_broad_panel_for_test",
        script_path,
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _assert_source_safe(value: object) -> None:
    forbidden = {"open", "high", "low", "close", "volume", "price", "prices", "raw", "row"}
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = "".join(character for character in key.lower() if character.isalnum())
            assert normalized not in forbidden
            _assert_source_safe(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_source_safe(nested)
