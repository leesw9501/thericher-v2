from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_kis_paper_daily_history_candle_state_input import (  # type: ignore[import-not-found]
    _assert_no_value_fields,
    _deny_external_access,
    _source,
)
from thericher_v2.data.kis_paper_daily_history_panel import KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
from thericher_v2.research import kis_nas_d1_candle_state_breadth as breadth
from thericher_v2.research import kis_nas_d1_candle_state_campaign as campaign


def test_campaign_freezes_phase_local_target_and_candidate_only_precommit(tmp_path: Path) -> None:
    campaign_input = campaign.build_kis_nas_d1_candle_state_campaign(_source(tmp_path / "source"))
    repository = tmp_path / "repo"
    repository.mkdir()
    precommit = campaign.write_kis_nas_d1_candle_state_campaign_precommit(
        campaign_input,
        review_status="review_unavailable",
        artifact_root=tmp_path / "external-model-artifacts" / "campaign",
        repo_root=repository,
    )
    payload = json.loads(precommit.precommit_path.read_text(encoding="utf-8"))

    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        development = campaign_input.development_samples(symbol)
        validation = campaign_input.validation_samples(symbol)
        assert len(development) == 1469
        assert len(validation) == 303
        assert all(sample.label in {0, 1} for sample in development)
        assert not hasattr(validation[0], "label")
        assert campaign.is_kis_nas_d1_candle_state_reference_long(
            validation[0],
            comparator_id="always_long",
        )
    assert payload["reporting"]["selection_allowed"] is False
    assert payload["campaign_contract"]["features"]["future_bars_read"] is False
    _assert_no_value_fields(payload)


def test_cpu_and_fake_cuda_breadth_stay_offline_source_safe_and_external(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _fast_cpu(monkeypatch)
    _deny_external_access(monkeypatch)
    prepared = _breadth_input(tmp_path / "source")
    artifact_root = tmp_path / "external-model-artifacts"
    repository = tmp_path / "repo"
    repository.mkdir()
    cpu = breadth.run_kis_nas_d1_candle_state_l2_logistic_smoke(
        prepared,
        artifact_root=artifact_root,
        run_label="cpu",
        repo_root=repository,
    )
    cpu_payload = json.loads(cpu.summary_path.read_text(encoding="utf-8"))

    assert len(cpu.candidates) == len(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
    assert all(
        candidate.validation_forward.output_shape == (303, 1) for candidate in cpu.candidates
    )
    assert cpu_payload["validation"] == {"forward_only": True, "labels_materialized": False}
    assert cpu.summary_path.is_relative_to(artifact_root)
    assert cpu.summary_attestation_path.is_relative_to(artifact_root)
    _assert_no_value_fields(cpu_payload)

    monkeypatch.setattr(
        breadth,
        "_torch_or_none",
        lambda: SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True)),
    )
    cuda = breadth.run_kis_nas_d1_candle_state_cuda_breadth(
        prepared,
        cpu_smoke_summary_path=cpu.summary_path,
        artifact_root=artifact_root,
        run_label="cuda",
        repo_root=repository,
        trainer=_fake_cuda_trainer,
    )
    cuda_payload = json.loads(cuda.summary_path.read_text(encoding="utf-8"))

    assert cuda.status == "completed"
    assert len(cuda.candidates) == 18
    assert all(candidate.safe_weights_only_reload for candidate in cuda.candidates)
    assert all(
        candidate.checkpoint_path.is_relative_to(artifact_root) for candidate in cuda.candidates
    )
    assert cuda_payload["reporting"]["selection_allowed"] is False
    _assert_no_value_fields(cuda_payload)


def test_breadth_rejects_git_workspace_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _fast_cpu(monkeypatch)
    prepared = _breadth_input(tmp_path / "source")
    repository = tmp_path / "repo"
    repository.mkdir()

    with pytest.raises(ValueError, match="outside the Git workspace"):
        breadth.run_kis_nas_d1_candle_state_l2_logistic_smoke(
            prepared,
            artifact_root=repository / "artifacts",
            run_label="inside-repo",
            repo_root=repository,
        )


def test_cuda_rejects_a_tampered_cpu_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _fast_cpu(monkeypatch)
    prepared = _breadth_input(tmp_path / "source")
    artifact_root = tmp_path / "external-model-artifacts"
    repository = tmp_path / "repo"
    repository.mkdir()
    cpu = breadth.run_kis_nas_d1_candle_state_l2_logistic_smoke(
        prepared,
        artifact_root=artifact_root,
        run_label="cpu",
        repo_root=repository,
    )
    payload = json.loads(cpu.summary_path.read_text(encoding="utf-8"))
    payload["source"] = {"campaign_contract_hash": "sha256:" + "0" * 64}
    cpu.summary_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="CPU smoke summary"):
        breadth.run_kis_nas_d1_candle_state_cuda_breadth(
            prepared,
            cpu_smoke_summary_path=cpu.summary_path,
            artifact_root=artifact_root,
            run_label="cuda",
            repo_root=repository,
            trainer=_fake_cuda_trainer,
        )


def test_cuda_rejects_cpu_candidate_payload_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _fast_cpu(monkeypatch)
    prepared = _breadth_input(tmp_path / "source")
    artifact_root = tmp_path / "external-model-artifacts"
    repository = tmp_path / "repo"
    repository.mkdir()
    cpu = breadth.run_kis_nas_d1_candle_state_l2_logistic_smoke(
        prepared,
        artifact_root=artifact_root,
        run_label="cpu",
        repo_root=repository,
    )
    payload = json.loads(cpu.summary_path.read_text(encoding="utf-8"))
    payload["candidates"][0]["final_loss"] = "0.00000000"
    cpu.summary_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="CPU smoke summary"):
        breadth.run_kis_nas_d1_candle_state_cuda_breadth(
            prepared,
            cpu_smoke_summary_path=cpu.summary_path,
            artifact_root=artifact_root,
            run_label="cuda",
            repo_root=repository,
            trainer=_fake_cuda_trainer,
        )


def test_standardizer_hash_canonicalizes_sub_quantum_drift() -> None:
    development_input_hash = "sha256:" + "a" * 64
    first = breadth.KisNasD1CandleStateStandardizer(
        symbol="AAPL",
        development_input_hash=development_input_hash,
        means=(0.1234567890121,) * 5,
        scales=(1.1234567890121,) * 5,
    )
    second = breadth.KisNasD1CandleStateStandardizer(
        symbol="AAPL",
        development_input_hash=development_input_hash,
        means=(0.1234567890122,) * 5,
        scales=(1.1234567890122,) * 5,
    )

    assert first.means == second.means
    assert first.scales == second.scales
    assert first.standardizer_hash == second.standardizer_hash


def test_cuda_rejects_a_checkpoint_outside_its_candidate_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _fast_cpu(monkeypatch)
    prepared = _breadth_input(tmp_path / "source")
    artifact_root = tmp_path / "external-model-artifacts"
    repository = tmp_path / "repo"
    repository.mkdir()
    cpu = breadth.run_kis_nas_d1_candle_state_l2_logistic_smoke(
        prepared,
        artifact_root=artifact_root,
        run_label="cpu",
        repo_root=repository,
    )
    monkeypatch.setattr(
        breadth,
        "_torch_or_none",
        lambda: SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True)),
    )
    cuda = breadth.run_kis_nas_d1_candle_state_cuda_breadth(
        prepared,
        cpu_smoke_summary_path=cpu.summary_path,
        artifact_root=artifact_root,
        run_label="cuda",
        repo_root=repository,
        trainer=_outside_checkpoint_trainer,
    )

    assert cuda.status == "candidate_failed"
    assert cuda.failure is not None
    assert cuda.failure.category == "invalid"
    assert cuda.candidates == ()


def test_docker_artifacts_must_stay_under_the_mounted_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = tmp_path / "app"
    repository.mkdir()
    mounted_root = repository / "model_artifacts"
    mounted_root.mkdir()
    outside_root = tmp_path / "temporary-artifacts"
    original_is_mount = Path.is_mount

    def is_mount(path: Path) -> bool:
        return path.resolve() == mounted_root.resolve() or original_is_mount(path)

    monkeypatch.setattr(Path, "is_mount", is_mount)
    monkeypatch.setattr(breadth, "_DOCKER_REPOSITORY_ROOT", repository)
    monkeypatch.setattr(breadth, "_DOCKER_ARTIFACT_ROOT", mounted_root)
    monkeypatch.setattr(campaign, "_DOCKER_REPOSITORY_ROOT", repository)
    monkeypatch.setattr(campaign, "_DOCKER_ARTIFACT_ROOT", mounted_root)

    allowed = breadth._prepare_output_dir(  # noqa: SLF001
        artifact_root=mounted_root,
        repo_root=repository,
        mode="cpu-smoke",
        run_label="mounted-root",
    )
    assert allowed.is_relative_to(mounted_root)
    with pytest.raises(ValueError, match="Docker artifacts"):
        breadth._prepare_output_dir(  # noqa: SLF001
            artifact_root=outside_root,
            repo_root=repository,
            mode="cpu-smoke",
            run_label="outside-root",
        )
    with pytest.raises(ValueError, match="Docker artifacts"):
        campaign._external_output_root(outside_root, repository)  # noqa: SLF001


def _breadth_input(root: Path) -> breadth.KisNasD1CandleStateBreadthInput:
    campaign_input = campaign.build_kis_nas_d1_candle_state_campaign(_source(root))
    return breadth.build_kis_nas_d1_candle_state_breadth_input(
        campaign_input,
        campaign_precommit_hash=(
            campaign.calculate_kis_nas_d1_candle_state_campaign_precommit_hash(
                campaign_input,
                review_status="review_unavailable",
            )
        ),
        review_status="review_unavailable",
    )


def _fast_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(breadth, "KIS_NAS_D1_CANDLE_STATE_CPU_LOGISTIC_STEPS", 2)
    monkeypatch.setattr(
        breadth,
        "KIS_NAS_D1_CANDLE_STATE_CPU_LOGISTIC_SPECS",
        tuple(
            breadth.KisNasD1CandleStateL2LogisticSpec(
                symbol=symbol,
                seed=2026072815 + index,
                steps=2,
            )
            for index, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
        ),
    )


def _fake_cuda_trainer(
    prepared: breadth.KisNasD1CandleStateBreadthInput,
    spec: breadth.KisNasD1CandleStateArchitectureSpec,
    checkpoint_dir: Path,
) -> breadth.KisNasD1CandleStateGpuCandidateReceipt:
    checkpoint_path = checkpoint_dir / f"{spec.architecture_id}-{spec.symbol.lower()}.pt"
    checkpoint_path.write_bytes(b"unit-checkpoint")
    return breadth.KisNasD1CandleStateGpuCandidateReceipt(
        spec=spec,
        development_sample_count=len(prepared.campaign_input.development_samples(spec.symbol)),
        validation_forward=breadth.KisNasD1CandleStateTargetFreeForward(
            symbol=spec.symbol,
            sample_count=len(prepared.campaign_input.validation_samples(spec.symbol)),
            output_shape=(len(prepared.campaign_input.validation_samples(spec.symbol)), 1),
            all_finite=True,
            output_bounds_valid=True,
        ),
        checkpoint_path=checkpoint_path,
        checkpoint_sha256="sha256:" + hashlib.sha256(checkpoint_path.read_bytes()).hexdigest(),
        backend="unit",
        device="unit",
        torch_version="unit",
        cuda_version=None,
        initial_loss=0.5,
        final_loss=0.4,
        cuda_peak_memory_bytes=0,
        safe_weights_only_reload=True,
    )


def _outside_checkpoint_trainer(
    prepared: breadth.KisNasD1CandleStateBreadthInput,
    spec: breadth.KisNasD1CandleStateArchitectureSpec,
    checkpoint_dir: Path,
) -> breadth.KisNasD1CandleStateGpuCandidateReceipt:
    checkpoint_path = checkpoint_dir.parent / "unbound.pt"
    checkpoint_path.write_bytes(b"unbound-unit-checkpoint")
    return breadth.KisNasD1CandleStateGpuCandidateReceipt(
        spec=spec,
        development_sample_count=len(prepared.campaign_input.development_samples(spec.symbol)),
        validation_forward=breadth.KisNasD1CandleStateTargetFreeForward(
            symbol=spec.symbol,
            sample_count=len(prepared.campaign_input.validation_samples(spec.symbol)),
            output_shape=(len(prepared.campaign_input.validation_samples(spec.symbol)), 1),
            all_finite=True,
            output_bounds_valid=True,
        ),
        checkpoint_path=checkpoint_path,
        checkpoint_sha256="sha256:" + hashlib.sha256(checkpoint_path.read_bytes()).hexdigest(),
        backend="unit",
        device="unit",
        torch_version="unit",
        cuda_version=None,
        initial_loss=0.5,
        final_loss=0.4,
        cuda_peak_memory_bytes=0,
        safe_weights_only_reload=True,
    )
