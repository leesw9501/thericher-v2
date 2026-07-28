from __future__ import annotations

import hashlib
import json
import os
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import kis_paper_daily_history_sequence_input as data_input
from thericher_v2.data.kis_paper_daily_history_panel import (
    KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
    KIS_PAPER_DAILY_HISTORY_PANEL_ID,
    KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS,
    KisPaperDailyHistoryPanel,
    KisPaperDailyHistoryPanelTarget,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.research import kis_nas_d1_sealed_evaluation as sealed
from thericher_v2.research import kis_nas_d1_sequence_breadth as breadth
from thericher_v2.research import kis_nas_d1_sequence_campaign as campaign


@pytest.fixture(scope="module")
def evaluation_bundle(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(breadth, "KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_STEPS", 2)
    specs = tuple(
        breadth.KisNasD1L2LogisticSpec(
            symbol=symbol,
            seed=2026072810 + index,
            steps=2,
        )
        for index, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
    )
    monkeypatch.setattr(breadth, "KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_SPECS", specs)
    monkeypatch.setattr(sealed, "KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_SPECS", specs)
    try:
        root = tmp_path_factory.mktemp("sealed-evaluation")
        repository_root = root / "repository"
        repository_root.mkdir()
        source_input = data_input._prepare_kis_paper_daily_history_sequence_input(  # noqa: SLF001
            _panel(root / "market-data")
        )
        campaign_input = campaign.build_kis_nas_d1_sequence_campaign(source_input)
        campaign_precommit_hash = campaign.calculate_kis_nas_d1_sequence_campaign_precommit_hash(
            campaign_input
        )
        breadth_input = breadth.build_kis_nas_d1_sequence_breadth_input(
            campaign_input,
            campaign_precommit_hash=campaign_precommit_hash,
        )
        artifact_root = root / "external-model-artifacts"
        cpu_summary_path, cpu_summary_hash, cpu_models = _write_cpu_smoke_evidence(
            breadth_input,
            artifact_root=artifact_root,
        )
        cuda_summary_path, cuda_summary_hash, checkpoint_root = _write_cuda_breadth_evidence(
            breadth_input,
            artifact_root=artifact_root,
            cpu_summary_hash=cpu_summary_hash,
        )
        evidence = sealed.KisNasD1SealedEvaluationEvidence(
            panel_dataset_hash=source_input.panel_dataset_hash,
            campaign_contract_hash=campaign_input.contract.contract_hash,
            campaign_precommit_hash=campaign_precommit_hash,
            cpu_summary_hash=cpu_summary_hash,
            cuda_summary_hash=cuda_summary_hash,
        )
        monkeypatch.setattr(sealed, "KIS_NAS_D1_SEALED_EVALUATION_EVIDENCE", evidence)
        evaluation_input = sealed.build_kis_nas_d1_sealed_evaluation_input(
            source_input,
            evidence=evidence,
            cpu_summary_path=cpu_summary_path,
            cuda_summary_path=cuda_summary_path,
            checkpoint_root=checkpoint_root,
        )
        yield SimpleNamespace(
            artifact_root=artifact_root,
            breadth_input=breadth_input,
            checkpoint_root=checkpoint_root,
            cpu_models=cpu_models,
            cpu_summary_path=cpu_summary_path,
            cuda_summary_path=cuda_summary_path,
            evaluation_input=evaluation_input,
            repository_root=repository_root,
        )
    finally:
        monkeypatch.undo()


def test_sealed_evaluation_is_offline_local_paper_and_replayable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    evaluation_bundle: SimpleNamespace,
) -> None:
    _deny_external_access(monkeypatch)
    cpu_summary = json.loads(evaluation_bundle.cpu_summary_path.read_text(encoding="utf-8"))
    cuda_summary = json.loads(evaluation_bundle.cuda_summary_path.read_text(encoding="utf-8"))
    monkeypatch.setattr(
        sealed,
        "_execution_environment_payload",
        lambda: {"kind": "docker", "detection": "dockerenv_marker_present"},
    )
    monkeypatch.setattr(sealed, "_load_cpu_summary", lambda *_args, **_kwargs: cpu_summary)
    monkeypatch.setattr(sealed, "_load_cuda_summary", lambda *_args, **_kwargs: cuda_summary)
    monkeypatch.setattr(sealed, "_cpu_prediction_batches", _fake_cpu_prediction_batches)
    monkeypatch.setattr(sealed, "_cuda_prediction_batches", _fake_cuda_prediction_batches)

    run = sealed.run_kis_nas_d1_sealed_evaluation(
        evaluation_bundle.evaluation_input,
        artifact_root=tmp_path / "external-model-artifacts",
        run_label="sealed-run",
        review_status="review_unavailable",
        repo_root=evaluation_bundle.repository_root,
    )
    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    precommit = json.loads(run.precommit_path.read_text(encoding="utf-8"))
    results = run.candidate_results + run.comparator_results

    assert len(run.candidate_results) == 24
    assert len(run.comparator_results) == 18
    assert {result.sample_count for result in results} == {313}
    assert all(result.all_fills_local_paper for result in results)
    assert all(result.replay_reconstructed for result in results)
    assert all(result.terminal_position_zero for result in results)
    assert all(result.fill_count == result.long_slot_count * 2 for result in results)
    assert {
        item["replay"]["fill_source"]
        for item in summary["candidates"] + summary["comparators"]
    } == {"local_paper"}
    assert all(
        item["replay"]["event_rows_retained"] is False
        for item in summary["candidates"] + summary["comparators"]
    )
    assert summary["review_status"] == "review_unavailable"
    assert summary["execution_environment"] == {
        "kind": "docker",
        "detection": "dockerenv_marker_present",
    }
    assert precommit["execution_environment"] == {
        "kind": "docker",
        "detection": "dockerenv_marker_present",
    }
    assert summary["artifact_policy"] == {
        "repo_storage_allowed": False,
        "raw_rows_persisted": False,
        "target_values_persisted": False,
        "prediction_values_persisted": False,
        "event_rows_persisted": False,
    }
    assert run.summary_path.is_relative_to(tmp_path / "external-model-artifacts")
    assert not list(run.summary_path.parent.glob("*.jsonl"))
    assert not list(run.summary_path.parent.glob("*.sqlite"))
    assert not list(run.summary_path.parent.glob("*.pt"))
    _assert_no_value_level_fields(summary)


def test_execution_environment_receipt_is_marker_bound_and_source_safe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    marker = tmp_path / "dockerenv"
    monkeypatch.setattr(sealed, "_DOCKER_ENVIRONMENT_MARKER", marker)

    assert sealed._execution_environment_payload() == {  # noqa: SLF001
        "kind": "host",
        "detection": "dockerenv_marker_absent",
    }

    marker.write_text("", encoding="utf-8")

    assert sealed._execution_environment_payload() == {  # noqa: SLF001
        "kind": "docker",
        "detection": "dockerenv_marker_present",
    }


def test_sealed_evaluation_rejects_a_linked_output_parent_before_writing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    evaluation_bundle: SimpleNamespace,
) -> None:
    artifact_root = tmp_path / "external-model-artifacts"
    linked_parent = artifact_root / sealed.KIS_NAS_D1_SEALED_EVALUATION_ID
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == linked_parent or original_is_symlink(path),
    )

    with pytest.raises(ValueError, match="cannot contain a symlink or junction"):
        sealed._prepare_output_dir(  # noqa: SLF001
            artifact_root=artifact_root,
            repository=evaluation_bundle.repository_root,
            run_label="linked-output",
        )

    assert artifact_root.is_dir()
    assert not linked_parent.exists()


def test_linked_path_detection_includes_windows_junctions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    junction = tmp_path / "junction"
    original_is_junction = getattr(Path, "is_junction", None)
    monkeypatch.setattr(
        Path,
        "is_junction",
        lambda path: path == junction or (
            callable(original_is_junction) and original_is_junction(path)
        ),
        raising=False,
    )

    with pytest.raises(ValueError, match="cannot contain a symlink or junction"):
        sealed._reject_linked_path_components(junction / "child")  # noqa: SLF001


def test_failure_receipt_keeps_marker_observation_source_safe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    evaluation_bundle: SimpleNamespace,
) -> None:
    cpu_summary = json.loads(evaluation_bundle.cpu_summary_path.read_text(encoding="utf-8"))
    cuda_summary = json.loads(evaluation_bundle.cuda_summary_path.read_text(encoding="utf-8"))
    monkeypatch.setattr(sealed, "_load_cpu_summary", lambda *_args, **_kwargs: cpu_summary)
    monkeypatch.setattr(sealed, "_load_cuda_summary", lambda *_args, **_kwargs: cuda_summary)
    monkeypatch.setattr(
        sealed,
        "_execution_environment_payload",
        lambda: {"kind": "docker", "detection": "dockerenv_marker_present"},
    )

    def fail_after_precommit(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("injected prediction failure")

    monkeypatch.setattr(sealed, "_prediction_batches", fail_after_precommit)
    artifact_root = tmp_path / "external-model-artifacts"
    with pytest.raises(RuntimeError, match="injected prediction failure"):
        sealed.run_kis_nas_d1_sealed_evaluation(
            evaluation_bundle.evaluation_input,
            artifact_root=artifact_root,
            run_label="failure-marker",
            review_status="review_unavailable",
            repo_root=evaluation_bundle.repository_root,
        )

    failure = json.loads(
        (
            artifact_root
            / sealed.KIS_NAS_D1_SEALED_EVALUATION_ID
            / "failure-marker"
            / "failure.json"
        ).read_text(encoding="utf-8")
    )
    assert failure["execution_environment"] == {
        "kind": "docker",
        "detection": "dockerenv_marker_present",
    }
    _assert_no_value_level_fields(failure)


def test_cpu_prediction_batches_refit_and_require_recorded_lineage(
    monkeypatch: pytest.MonkeyPatch,
    evaluation_bundle: SimpleNamespace,
) -> None:
    summary = json.loads(evaluation_bundle.cpu_summary_path.read_text(encoding="utf-8"))
    calls: list[str] = []

    def fake_fit(
        _breadth_input: breadth.KisNasD1SequenceBreadthInput,
        spec: breadth.KisNasD1L2LogisticSpec,
    ) -> breadth.KisNasD1L2LogisticModel:
        calls.append(spec.symbol)
        return evaluation_bundle.cpu_models[spec.symbol]

    monkeypatch.setattr(sealed, "fit_kis_nas_d1_l2_logistic_smoke", fake_fit)

    batches = sealed._cpu_prediction_batches(  # noqa: SLF001
        evaluation_bundle.evaluation_input,
        cpu_summary=summary,
    )

    assert calls == list(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
    assert len(batches) == 6
    assert {len(batch.probabilities) for batch in batches} == {313}

    summary["candidates"][0]["model_parameter_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="CPU model lineage drifted"):
        sealed._cpu_prediction_batches(  # noqa: SLF001
            evaluation_bundle.evaluation_input,
            cpu_summary=summary,
        )


def test_sealed_input_rejects_caller_replacement_evidence(
    evaluation_bundle: SimpleNamespace,
) -> None:
    replacement = replace(
        evaluation_bundle.evaluation_input.evidence,
        cuda_summary_hash="sha256:" + "0" * 64,
    )

    with pytest.raises(ValueError, match="evidence is not frozen"):
        sealed.build_kis_nas_d1_sealed_evaluation_input(
            evaluation_bundle.evaluation_input.source_input,
            evidence=replacement,
            cpu_summary_path=evaluation_bundle.cpu_summary_path,
            cuda_summary_path=evaluation_bundle.cuda_summary_path,
            checkpoint_root=evaluation_bundle.checkpoint_root,
        )


@pytest.mark.parametrize(
    "review_status",
    ("unsupported", "uncertain", "supported-with-limits"),
)
def test_adverse_claude_verdict_cannot_open_sealed_target(
    tmp_path: Path,
    evaluation_bundle: SimpleNamespace,
    review_status: str,
) -> None:
    artifact_root = tmp_path / "external-model-artifacts"

    with pytest.raises(ValueError, match="does not permit target opening"):
        sealed.run_kis_nas_d1_sealed_evaluation(
            evaluation_bundle.evaluation_input,
            artifact_root=artifact_root,
            run_label=f"review-{review_status}",
            review_status=review_status,
            repo_root=evaluation_bundle.repository_root,
        )

    assert not artifact_root.exists()


def test_sealed_evaluation_rejects_git_artifact_root_before_target_opening(
    monkeypatch: pytest.MonkeyPatch,
    evaluation_bundle: SimpleNamespace,
) -> None:
    cpu_summary = json.loads(evaluation_bundle.cpu_summary_path.read_text(encoding="utf-8"))
    cuda_summary = json.loads(evaluation_bundle.cuda_summary_path.read_text(encoding="utf-8"))
    monkeypatch.setattr(sealed, "_load_cpu_summary", lambda *_args, **_kwargs: cpu_summary)
    monkeypatch.setattr(sealed, "_load_cuda_summary", lambda *_args, **_kwargs: cuda_summary)

    with pytest.raises(ValueError, match="outside the Git workspace"):
        sealed.run_kis_nas_d1_sealed_evaluation(
            evaluation_bundle.evaluation_input,
            artifact_root=evaluation_bundle.repository_root / "model-artifacts",
            run_label="git-root",
            review_status="review_unavailable",
            repo_root=evaluation_bundle.repository_root,
        )


def test_checkpoint_reload_is_weights_only_and_strict(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    evaluation_bundle: SimpleNamespace,
) -> None:
    spec = breadth.KIS_NAS_D1_SEQUENCE_CUDA_ARCHITECTURE_SPECS[0]
    checkpoint_path = tmp_path / "external-checkpoint.pt"
    checkpoint_path.write_bytes(b"placeholder")
    standardizer = evaluation_bundle.breadth_input.standardizer(spec.symbol)
    seen: dict[str, object] = {}

    class FakeModel:
        def load_state_dict(self, state_dict: object, *, strict: bool) -> None:
            seen["state_dict"] = state_dict
            seen["strict"] = strict

        def eval(self) -> None:
            seen["eval"] = True

    fake_model = FakeModel()

    class FakeTorch:
        def load(
            self,
            path: Path,
            *,
            map_location: str,
            weights_only: bool,
        ) -> dict[str, object]:
            seen["path"] = path
            seen["map_location"] = map_location
            seen["weights_only"] = weights_only
            return {
                "schema_version": 1,
                "kind": "kis_nas_d1_sequence_breadth_checkpoint",
                "campaign_contract_hash": (
                    evaluation_bundle.breadth_input.campaign_input.contract.contract_hash
                ),
                "development_input_hash": standardizer.development_input_hash,
                "standardizer_hash": standardizer.standardizer_hash,
                "architecture": spec.safe_payload(),
                "state_dict": {"unit": "weights"},
            }

    monkeypatch.setattr(sealed, "build_torch_sequence_model", lambda **_kwargs: fake_model)

    loaded = sealed._load_cuda_checkpoint(  # noqa: SLF001
        checkpoint_path,
        breadth_input=evaluation_bundle.breadth_input,
        spec=spec,
        torch=FakeTorch(),
    )

    assert loaded is fake_model
    assert seen == {
        "path": checkpoint_path,
        "map_location": "cpu",
        "weights_only": True,
        "state_dict": {"unit": "weights"},
        "strict": True,
        "eval": True,
    }


def test_real_torch_checkpoint_reloads_and_forwards_on_cpu(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    torch = pytest.importorskip("torch")
    evaluation_bundle = request.getfixturevalue("evaluation_bundle")
    assert isinstance(evaluation_bundle, SimpleNamespace)
    spec = breadth.KIS_NAS_D1_SEQUENCE_CUDA_ARCHITECTURE_SPECS[0]
    standardizer = evaluation_bundle.breadth_input.standardizer(spec.symbol)
    checkpoint_path = tmp_path / "external-checkpoint.pt"
    model = sealed.build_torch_sequence_model(
        torch=torch,
        architecture_id=spec.architecture_id,
        feature_count=1,
        hidden_size=spec.hidden_size,
        attention_heads=spec.attention_heads,
        tcn_kernel_size=spec.tcn_kernel_size,
    )
    torch.save(
        {
            "schema_version": 1,
            "kind": "kis_nas_d1_sequence_breadth_checkpoint",
            "campaign_contract_hash": (
                evaluation_bundle.breadth_input.campaign_input.contract.contract_hash
            ),
            "development_input_hash": standardizer.development_input_hash,
            "standardizer_hash": standardizer.standardizer_hash,
            "architecture": spec.safe_payload(),
            "state_dict": model.state_dict(),
        },
        checkpoint_path,
    )

    loaded = sealed._load_cuda_checkpoint(  # noqa: SLF001
        checkpoint_path,
        breadth_input=evaluation_bundle.breadth_input,
        spec=spec,
        torch=torch,
    )
    probabilities = sealed._cuda_probabilities(  # noqa: SLF001
        loaded,
        breadth_input=evaluation_bundle.breadth_input,
        spec=spec,
        torch=torch,
    )

    assert len(probabilities) == 313
    assert all(0.0 <= probability <= 1.0 for probability in probabilities)


def test_runner_is_offline_and_does_not_load_environment_files() -> None:
    source = Path("scripts/run_kis_nas_d1_sealed_evaluation.py").read_text(encoding="utf-8")

    assert "load_dotenv" not in source
    assert "os.environ" not in source
    assert "KIS_PAPER_APP_" not in source
    assert "KIS_LIVE_" not in source
    assert "requests" not in source


def _fake_cuda_prediction_batches(
    evaluation_input: sealed.KisNasD1SealedEvaluationInput,
    *,
    cuda_summary: object,
    repository: Path,
) -> tuple[sealed._PredictionBatch, ...]:  # noqa: SLF001
    del repository
    assert isinstance(cuda_summary, dict)
    receipts = cuda_summary["candidates"]
    assert isinstance(receipts, list)
    batches: list[sealed._PredictionBatch] = []  # noqa: SLF001
    for index, (receipt, spec) in enumerate(
        zip(receipts, breadth.KIS_NAS_D1_SEQUENCE_CUDA_ARCHITECTURE_SPECS, strict=True)
    ):
        assert isinstance(receipt, dict)
        sample_count = len(evaluation_input.campaign_input.validation_samples(spec.symbol))
        batches.append(
            sealed._PredictionBatch(  # noqa: SLF001
                result_id=f"cuda_{spec.architecture_id}:{spec.symbol}",
                model_family=f"cuda_{spec.architecture_id}",
                symbol=spec.symbol,
                lineage_hash=str(receipt["checkpoint_sha256"]),
                probabilities=tuple(
                    0.75 if (sample_index + index) % 3 else 0.25
                    for sample_index in range(sample_count)
                ),
            )
        )
    return tuple(batches)


def _fake_cpu_prediction_batches(
    evaluation_input: sealed.KisNasD1SealedEvaluationInput,
    *,
    cpu_summary: object,
) -> tuple[sealed._PredictionBatch, ...]:  # noqa: SLF001
    del cpu_summary
    batches: list[sealed._PredictionBatch] = []  # noqa: SLF001
    for index, spec in enumerate(sealed.KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_SPECS):
        sample_count = len(evaluation_input.campaign_input.validation_samples(spec.symbol))
        batches.append(
            sealed._PredictionBatch(  # noqa: SLF001
                result_id=f"cpu_l2_logistic:{spec.symbol}",
                model_family="cpu_l2_logistic",
                symbol=spec.symbol,
                lineage_hash="sha256:" + f"{index + 1:064x}",
                probabilities=tuple(
                    0.75 if (sample_index + index) % 4 else 0.25
                    for sample_index in range(sample_count)
                ),
            )
        )
    return tuple(batches)


def _write_cpu_smoke_evidence(
    breadth_input: breadth.KisNasD1SequenceBreadthInput,
    *,
    artifact_root: Path,
) -> tuple[Path, str, dict[str, breadth.KisNasD1L2LogisticModel]]:
    output_root = artifact_root / breadth.KIS_NAS_D1_SEQUENCE_BREADTH_ID / "cpu-smoke" / "cpu"
    output_root.mkdir(parents=True)
    precommit_path = output_root / "precommit.json"
    precommit_bytes = _json_bytes(
        breadth._cpu_precommit_payload(breadth_input),  # noqa: SLF001
    )
    precommit_path.write_bytes(precommit_bytes)
    models: dict[str, breadth.KisNasD1L2LogisticModel] = {}
    candidates: list[dict[str, object]] = []
    for spec in breadth.KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_SPECS:
        standardizer = breadth_input.standardizer(spec.symbol)
        model = breadth.KisNasD1L2LogisticModel(
            spec=spec,
            development_input_hash=standardizer.development_input_hash,
            standardizer_hash=standardizer.standardizer_hash,
            weights=(0.0,) * 20,
            intercept=0.0,
            initial_loss=0.5,
            final_loss=0.25,
        )
        models[spec.symbol] = model
        sample_count = len(breadth_input.campaign_input.validation_samples(spec.symbol))
        candidates.append(
            {
                "symbol": spec.symbol,
                "model_id": "l2_logistic",
                "model_parameter_hash": model.parameter_hash,
                "standardizer_hash": standardizer.standardizer_hash,
                "development_sample_count": len(
                    breadth_input.campaign_input.development_samples(spec.symbol)
                ),
                "steps": spec.steps,
                "seed": spec.seed,
                "initial_loss": "0.50000000",
                "final_loss": "0.25000000",
                "validation_forward": {
                    "symbol": spec.symbol,
                    "sample_count": sample_count,
                    "output_shape": [sample_count, 1],
                    "all_finite": True,
                    "output_bounds_valid": True,
                    "labels_materialized": False,
                },
            }
        )
    summary_path = output_root / "summary.json"
    summary_bytes = _json_bytes(
        {
            "schema_version": 1,
            "kind": "kis_nas_d1_sequence_cpu_smoke",
            "status": "completed",
            "precommit_hash": _sha256_bytes(precommit_bytes),
            "source": breadth._source_payload(breadth_input),  # noqa: SLF001
            "candidates": candidates,
            "validation": {
                "labels_materialized": False,
                "forward_only": True,
            },
            "artifact_policy": {
                "repo_storage_allowed": False,
                "checkpoints_written": False,
                "raw_rows_persisted": False,
                "predictions_persisted": False,
            },
            "reporting": breadth._reporting_payload(),  # noqa: SLF001
        }
    )
    summary_path.write_bytes(summary_bytes)
    return summary_path, _sha256_bytes(summary_bytes), models


def _write_cuda_breadth_evidence(
    breadth_input: breadth.KisNasD1SequenceBreadthInput,
    *,
    artifact_root: Path,
    cpu_summary_hash: str,
) -> tuple[Path, str, Path]:
    output_root = artifact_root / breadth.KIS_NAS_D1_SEQUENCE_BREADTH_ID / "cuda-breadth" / "cuda"
    checkpoint_root = output_root / "checkpoints"
    checkpoint_root.mkdir(parents=True)
    precommit_path = output_root / "precommit.json"
    precommit_bytes = _json_bytes(
        breadth._cuda_precommit_payload(breadth_input, cpu_summary_hash),  # noqa: SLF001
    )
    precommit_path.write_bytes(precommit_bytes)
    candidates: list[dict[str, object]] = []
    for spec in breadth.KIS_NAS_D1_SEQUENCE_CUDA_ARCHITECTURE_SPECS:
        checkpoint_path = checkpoint_root / f"{spec.architecture_id}-{spec.symbol}.pt"
        checkpoint_bytes = f"unit:{spec.architecture_id}:{spec.symbol}".encode("ascii")
        checkpoint_path.write_bytes(checkpoint_bytes)
        sample_count = len(breadth_input.campaign_input.validation_samples(spec.symbol))
        candidates.append(
            {
                "architecture": spec.safe_payload(),
                "development_sample_count": len(
                    breadth_input.campaign_input.development_samples(spec.symbol)
                ),
                "checkpoint_sha256": _sha256_bytes(checkpoint_bytes),
                "backend": "torch_cuda",
                "device": "unit-cuda",
                "torch_version": "unit",
                "cuda_version": None,
                "initial_loss": "0.50000000",
                "final_loss": "0.25000000",
                "cuda_peak_memory_bytes": 0,
                "safe_weights_only_reload": True,
                "validation_forward": {
                    "symbol": spec.symbol,
                    "sample_count": sample_count,
                    "output_shape": [sample_count, 1],
                    "all_finite": True,
                    "output_bounds_valid": True,
                    "labels_materialized": False,
                },
            }
        )
    summary_path = output_root / "summary.json"
    summary_bytes = _json_bytes(
        {
            "schema_version": 1,
            "kind": "kis_nas_d1_sequence_cuda_breadth",
            "status": "completed",
            "reason": "unit CUDA candidate receipts completed",
            "precommit_hash": _sha256_bytes(precommit_bytes),
            "cpu_smoke_summary_hash": cpu_summary_hash,
            "source": breadth._source_payload(breadth_input),  # noqa: SLF001
            "candidates": candidates,
            "validation": {
                "labels_materialized": False,
                "forward_only": True,
            },
            "artifact_policy": {
                "repo_storage_allowed": False,
                "checkpoints_written": True,
                "raw_rows_persisted": False,
                "predictions_persisted": False,
            },
            "reporting": breadth._reporting_payload(),  # noqa: SLF001
        }
    )
    summary_path.write_bytes(summary_bytes)
    return summary_path, _sha256_bytes(summary_bytes), checkpoint_root


def _panel(root: Path) -> KisPaperDailyHistoryPanel:
    root.mkdir(parents=True)
    index_path = root / "index.json"
    index_path.write_text("{}\n", encoding="utf-8")
    start = datetime(2017, 1, 3, tzinfo=UTC)
    sessions = tuple((start + timedelta(days=index)).date() for index in range(2179))
    bars_by_symbol: dict[str, object] = {}
    targets_by_key: dict[str, KisPaperDailyHistoryPanelTarget] = {}
    for offset, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS, start=1):
        bars = tuple(
            _bar(
                symbol=symbol,
                start_ts=start + timedelta(days=index),
                value=(
                    Decimal("100")
                    + Decimal(offset * 10)
                    + Decimal(index) / Decimal("100")
                    + Decimal(index % 5) / Decimal("10")
                ),
            )
            for index in range(2179)
        )
        bars_by_symbol[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id=KIS_PAPER_DAILY_HISTORY_PANEL_ID,
            dataset_hash=data_input.KIS_PAPER_DAILY_HISTORY_SEQUENCE_EXPECTED_DATASET_HASH,
            source_path=index_path,
            bars=bars,
        )
        state = "source_limited" if symbol == "MSFT" else "complete"
        targets_by_key[f"{symbol}/NAS"] = KisPaperDailyHistoryPanelTarget(
            target_key=f"{symbol}/NAS",
            state=state,
            last_reason="daily_response_invalid" if state == "source_limited" else None,
            chunk_count=1,
            bar_count=len(bars),
            coverage_start_bucket=_quarter(sessions[0]),
            coverage_end_bucket=_quarter(sessions[-1]),
        )
    return KisPaperDailyHistoryPanel(
        dataset_id=KIS_PAPER_DAILY_HISTORY_PANEL_ID,
        dataset_hash=data_input.KIS_PAPER_DAILY_HISTORY_SEQUENCE_EXPECTED_DATASET_HASH,
        index_hash="sha256:" + "a" * 64,
        index_path=index_path,
        source_root=root,
        adjustment_mode=KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
        bars_by_symbol=MappingProxyType(bars_by_symbol),
        targets_by_key=MappingProxyType(targets_by_key),
        common_sessions=sessions,
    )


def _bar(*, symbol: str, start_ts: datetime, value: Decimal) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=start_ts,
        open=value,
        high=value + Decimal("1"),
        low=value - Decimal("1"),
        close=value,
        volume=Decimal("1000"),
        complete=True,
    )


def _quarter(value: date) -> str:
    return f"{value.year}-Q{(value.month - 1) // 3 + 1}"


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("external access is forbidden")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
    monkeypatch.setattr(os, "getenv", denied)


def _assert_no_value_level_fields(payload: object) -> None:
    forbidden = {
        "account",
        "bar",
        "broker",
        "close_returns",
        "credential",
        "credentials",
        "event_rows",
        "feature_rows",
        "label",
        "labels",
        "order",
        "orders",
        "price",
        "prices",
        "prediction",
        "predictions",
        "probability",
        "probabilities",
        "raw_bars",
        "secret",
        "target",
        "targets",
    }
    if isinstance(payload, dict):
        for key, value in payload.items():
            assert key.lower() not in forbidden
            _assert_no_value_level_fields(value)
    elif isinstance(payload, list):
        for value in payload:
            _assert_no_value_level_fields(value)
