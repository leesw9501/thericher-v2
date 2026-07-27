from __future__ import annotations

import ast
import hashlib
import json
import os
import socket
import urllib.request
from dataclasses import replace
from pathlib import Path

import pytest

import thericher_v2.kis_daily_joint_event_d1_crossfold_falsification as falsification


def test_crossfold_falsification_is_fold_local_source_safe_and_offline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    repo_root = tmp_path / "repo"
    artifact_root = tmp_path / "model-artifacts"
    pins = _write_pinned_screen_artifacts(artifact_root)

    run = falsification.run_kis_daily_joint_event_d1_crossfold_falsification(
        artifact_root=artifact_root,
        run_label="unit-a",
        repo_root=repo_root,
        pins=pins,
    )

    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    serialized = run.summary_path.read_text(encoding="utf-8").lower()
    assert run.summary_path.is_relative_to(artifact_root)
    assert run.precommit_path.is_relative_to(artifact_root)
    assert summary["status"] == "complete"
    assert summary["source_summary_count"] == 6
    assert summary["observation_count"] == 12
    assert summary["scope"] == {
        "candidate_only": True,
        "candidate_selection_eligible": False,
        "credentials_persisted": False,
        "ensemble_eligible": False,
        "feature_values_persisted": False,
        "model_execution_eligible": False,
        "offline_only": True,
        "paper_decision_eligible": False,
        "per_decision_outputs_persisted": False,
        "raw_market_data_persisted": False,
        "replay_materialized": False,
        "target_values_persisted": False,
    }
    assert {observation.conclusion for observation in run.observations} == {
        "falsified",
        "inconclusive",
    }
    for observation in run.observations:
        expected_majority = max(
            observation.observed_positive_count,
            observation.evaluated_count - observation.observed_positive_count,
        )
        assert observation.class_majority_correct_count == expected_majority
        assert observation.conclusion == (
            "inconclusive"
            if observation.candidate_correct_count > expected_majority
            else "falsified"
        )
    assert all(
        observation.candidate_correct_count <= observation.evaluated_count
        and observation.class_majority_correct_count <= observation.evaluated_count
        for observation in run.observations
    )
    assert all(
        term not in serialized
        for term in (
            '"open"',
            '"close"',
            '"return"',
            '"label"',
            '"prediction"',
            '"probability"',
            '"threshold"',
            '"pnl"',
            '"account"',
            '"order"',
            '"intent"',
            '"action"',
            '"winner"',
            '"rank"',
            '"mean"',
            '"average"',
        )
    )
    assert all(
        set(observation)
        == {
            "candidate_correct_count",
            "candidate_id",
            "class_majority_correct_count",
            "conclusion",
            "evaluated_count",
            "fold_id",
            "mode",
            "observed_positive_count",
            "run_label",
        }
        for observation in summary["observations"]
    )


def test_crossfold_falsification_rejects_a_mismatched_or_unsafe_summary(tmp_path: Path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    pins = _write_pinned_screen_artifacts(artifact_root)
    summary_path = (
        artifact_root
        / falsification.KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_ID
        / pins[0].run_label
        / "summary.json"
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["scope"]["offline_only"] = False
    _write_canonical(summary_path, summary)

    with pytest.raises(ValueError, match="hash does not match"):
        falsification.run_kis_daily_joint_event_d1_crossfold_falsification(
            artifact_root=artifact_root,
            run_label="mismatched",
            repo_root=tmp_path / "repo",
            pins=pins,
        )

    unsafe_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    unsafe_summary["raw_price"] = 1
    unsafe_summary["result_identity"] = _result_identity(unsafe_summary)
    _write_canonical(summary_path, unsafe_summary)
    unsafe_pin = replace(
        pins[0],
        result_identity=str(unsafe_summary["result_identity"]),
        summary_sha256=_file_sha256(summary_path),
    )
    with pytest.raises(ValueError, match="summary shape is invalid"):
        falsification.run_kis_daily_joint_event_d1_crossfold_falsification(
            artifact_root=artifact_root,
            run_label="unsafe",
            repo_root=tmp_path / "repo",
            pins=(unsafe_pin, *pins[1:]),
        )


def test_crossfold_falsification_rejects_a_matching_hash_noncanonical_summary(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "model-artifacts"
    pins = _write_pinned_screen_artifacts(artifact_root)
    summary_path = (
        artifact_root
        / falsification.KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_ID
        / pins[0].run_label
        / "summary.json"
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary_path.write_bytes(
        json.dumps(summary, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    noncanonical_pin = replace(pins[0], summary_sha256=_file_sha256(summary_path))

    with pytest.raises(ValueError, match="artifact is not canonical"):
        falsification.run_kis_daily_joint_event_d1_crossfold_falsification(
            artifact_root=artifact_root,
            run_label="noncanonical",
            repo_root=tmp_path / "repo",
            pins=(noncanonical_pin, *pins[1:]),
        )


def test_crossfold_falsification_rejects_artifacts_inside_git(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    artifact_root = repo_root / "model-artifacts"

    with pytest.raises(ValueError, match="outside the Git workspace"):
        falsification.run_kis_daily_joint_event_d1_crossfold_falsification(
            artifact_root=artifact_root,
            run_label="inside-repo",
            repo_root=repo_root,
            pins=(),
        )


def test_crossfold_falsification_refuses_to_overwrite_an_immutable_label(tmp_path: Path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    pins = _write_pinned_screen_artifacts(artifact_root)
    arguments = {
        "artifact_root": artifact_root,
        "run_label": "immutable",
        "repo_root": tmp_path / "repo",
        "pins": pins,
    }

    falsification.run_kis_daily_joint_event_d1_crossfold_falsification(**arguments)

    with pytest.raises(FileExistsError, match="run label already exists"):
        falsification.run_kis_daily_joint_event_d1_crossfold_falsification(**arguments)


def test_crossfold_falsification_rejects_a_reparse_output_root_before_create(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "model-artifacts"
    artifact_root.mkdir()
    output_root = artifact_root / falsification.KIS_DAILY_JOINT_EVENT_D1_CROSSFOLD_FALSIFICATION_ID
    output_root.mkdir()
    original = falsification._is_link_or_reparse_point  # noqa: SLF001

    def is_reparse(path: Path) -> bool:
        return path == output_root or original(path)

    monkeypatch.setattr(falsification, "_is_link_or_reparse_point", is_reparse)

    with pytest.raises(ValueError, match="artifact destination is invalid"):
        falsification._create_external_output_dir(  # noqa: SLF001
            artifact_root=artifact_root,
            repo_root=tmp_path / "repo",
            run_label="junction-like",
        )

    assert not (output_root / "junction-like").exists()


def test_only_the_fixed_e1_pin_accepts_the_legacy_missing_fold_id_shape() -> None:
    pins = falsification.KIS_DAILY_JOINT_EVENT_D1_CROSSFOLD_ARTIFACT_PINS

    assert pins[0].fold.legacy_source_without_fold_id is True
    assert pins[1].fold.legacy_source_without_fold_id is True
    assert all(not pin.fold.legacy_source_without_fold_id for pin in pins[2:])
    assert "fold_id" not in pins[0].fold.source_document()
    assert "fold_id" in pins[2].fold.source_document()


def test_crossfold_module_stays_import_and_route_free() -> None:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "thericher_v2"
        / "kis_daily_joint_event_d1_crossfold_falsification.py"
    )
    imports = _imports(module_path)

    assert not any(
        term in imported
        for imported in imports
        for term in (
            "execution",
            "broker",
            "socket",
            "urllib",
            "http",
            "requests",
            "subprocess",
            "dotenv",
            "os",
            "tiingo",
            "kis_paper",
            "replay",
            "order",
        )
    )


def _write_pinned_screen_artifacts(
    artifact_root: Path,
) -> tuple[falsification.KisDailyJointEventD1CrossfoldArtifactPin, ...]:
    source_root = artifact_root / falsification.KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_ID
    source_root.mkdir(parents=True)
    pins: list[falsification.KisDailyJointEventD1CrossfoldArtifactPin] = []
    for base_pin in falsification.KIS_DAILY_JOINT_EVENT_D1_CROSSFOLD_ARTIFACT_PINS:
        run_dir = source_root / base_pin.run_label
        run_dir.mkdir()
        precommit = _precommit_document(base_pin)
        precommit["precommit_identity"] = falsification._sha256_json(precommit)  # noqa: SLF001
        precommit_path = run_dir / "precommit.json"
        _write_canonical(precommit_path, precommit)
        summary = _summary_document(
            base_pin, precommit_identity=str(precommit["precommit_identity"])
        )
        summary["result_identity"] = falsification._sha256_json(summary)  # noqa: SLF001
        summary_path = run_dir / "summary.json"
        _write_canonical(summary_path, summary)
        pins.append(
            replace(
                base_pin,
                precommit_sha256=_file_sha256(precommit_path),
                screen_precommit_identity=str(precommit["precommit_identity"]),
                summary_sha256=_file_sha256(summary_path),
                result_identity=str(summary["result_identity"]),
            )
        )
    return tuple(pins)


def _precommit_document(
    pin: falsification.KisDailyJointEventD1CrossfoldArtifactPin,
) -> dict[str, object]:
    return {
        "artifact_policy": dict(falsification._EXPECTED_ARTIFACT_POLICY),  # noqa: SLF001
        "candidates": falsification._candidate_spec_documents(pin.mode),  # noqa: SLF001
        "classification": dict(falsification._EXPECTED_CLASSIFICATION),  # noqa: SLF001
        "kind": "kis_daily_joint_event_d1_sequence_screen",
        "mode": pin.mode,
        "normalization": {
            "fit_scope": "development_only",
            "normalization_identity": pin.fold.normalization_identity,
        },
        "schema_version": 1,
        "scope": dict(falsification._EXPECTED_SCOPE),  # noqa: SLF001
        "screen_id": falsification.KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_ID,
        "shape": dict(falsification._EXPECTED_SHAPE),  # noqa: SLF001
        "source": pin.fold.source_document(),
        "split": {
            "development_decision_count": pin.fold.development_decision_count,
            "pre_validation_gap_consumed": False,
            "untouched_tail_session_count": 151,
            "validation_decision_count": pin.fold.validation_decision_count,
        },
        "status": "precommitted",
    }


def _summary_document(
    pin: falsification.KisDailyJointEventD1CrossfoldArtifactPin,
    *,
    precommit_identity: str,
) -> dict[str, object]:
    document = _precommit_document(pin)
    document["status"] = "complete"
    document["precommit_identity"] = precommit_identity
    document["candidates"] = _summary_candidates(pin)
    return document


def _summary_candidates(
    pin: falsification.KisDailyJointEventD1CrossfoldArtifactPin,
) -> list[dict[str, object]]:
    evaluated_count = pin.fold.validation_decision_count
    observed_positive_count = evaluated_count // 2
    observed_negative_count = evaluated_count - observed_positive_count
    candidates: list[dict[str, object]] = []
    for spec in falsification._candidate_spec_documents(pin.mode):  # noqa: SLF001
        candidate_correct_count = (
            observed_negative_count + 1
            if spec["candidate_id"] == "linear"
            else observed_negative_count
        )
        true_positive_count = observed_positive_count
        true_negative_count = candidate_correct_count - true_positive_count
        false_positive_count = observed_negative_count - true_negative_count
        metrics = {
            "accuracy": round(candidate_correct_count / evaluated_count, 12),
            "evaluated_count": evaluated_count,
            "f1": 0.5,
            "false_negative_count": 0,
            "false_positive_count": false_positive_count,
            "observed_positive_count": observed_positive_count,
            "precision": 0.5,
            "recall": 1.0,
            "true_negative_count": true_negative_count,
            "true_positive_count": true_positive_count,
        }
        candidates.append(
            {
                **spec,
                "backend": "torch_cpu" if pin.mode == "cpu-smoke" else "torch_cuda",
                "device": "cpu" if pin.mode == "cpu-smoke" else "cuda",
                "metrics": metrics,
            }
        )
    return candidates


def _result_identity(summary: dict[str, object]) -> str:
    payload = dict(summary)
    payload.pop("result_identity", None)
    return falsification._sha256_json(payload)  # noqa: SLF001


def _write_canonical(path: Path, document: dict[str, object]) -> None:
    path.write_bytes(
        (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    )


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("cross-fold falsification must stay offline")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_external)


def _imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)
    return tuple(imports)
