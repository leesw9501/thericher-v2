from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

import thericher_v2.research.chronos_t5_norgate_d1_probe as probe
from thericher_v2.research.norgate_broad_representation import (
    DEFAULT_REPRESENTATION_GEOMETRY,
    ObservedReturnDataset,
)


def test_prepare_and_reattest_safe_chronos_model_outside_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    calls: list[dict[str, object]] = []

    def downloader(**kwargs: object) -> str:
        calls.append(dict(kwargs))
        destination = Path(str(kwargs["local_dir"]))
        (destination / "config.json").write_text("{}", encoding="ascii")
        (destination / "model.safetensors").write_bytes(b"safe-tensor-bytes")
        (destination / "spiece.model").write_bytes(b"tokenizer-bytes")
        cache = destination / ".cache" / "huggingface"
        cache.mkdir(parents=True)
        (cache / "download-metadata.json").write_text("{}", encoding="ascii")
        return str(destination)

    first = probe.prepare_chronos_t5_tiny_local_model(
        artifact_root=artifact_root,
        repository_root=repository,
        downloader=downloader,
    )
    second = probe.load_verified_chronos_t5_tiny_local_model(
        artifact_root=artifact_root,
        repository_root=repository,
    )

    assert len(calls) == 1
    assert calls[0]["repo_id"] == probe.CHRONOS_T5_MODEL_ID
    assert calls[0]["revision"] == probe.CHRONOS_T5_MODEL_REVISION
    assert set(calls[0]["allow_patterns"]) == probe._ALLOWED_MODEL_FILES
    assert first.manifest_sha256 == second.manifest_sha256
    assert first.directory.is_relative_to(artifact_root)
    manifest = json.loads(first.manifest_path.read_text(encoding="ascii"))
    assert manifest["license"] == "Apache-2.0"
    assert manifest["safe_serialization"] is True
    assert {item["path"] for item in manifest["files"]} == {
        "config.json",
        "model.safetensors",
        "spiece.model",
    }
    assert not (first.directory / ".cache").exists()


def test_prepare_rejects_unsafe_or_in_repo_model_artifacts(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()

    with pytest.raises(ValueError, match="outside Git"):
        probe.prepare_chronos_t5_tiny_local_model(
            artifact_root=repository / "model-artifacts",
            repository_root=repository,
            downloader=lambda **_kwargs: "unused",
        )

    artifact_root = tmp_path / "model-artifacts"

    def unsafe_downloader(**kwargs: object) -> str:
        destination = Path(str(kwargs["local_dir"]))
        (destination / "config.json").write_text("{}", encoding="ascii")
        (destination / "model.safetensors").write_bytes(b"safe-tensor-bytes")
        (destination / "pytorch_model.bin").write_bytes(b"unsafe-pickle-route")
        return str(destination)

    with pytest.raises(ValueError, match="unsupported file"):
        probe.prepare_chronos_t5_tiny_local_model(
            artifact_root=artifact_root,
            repository_root=repository,
            downloader=unsafe_downloader,
        )
    assert not probe.default_chronos_t5_tiny_directory(artifact_root).exists()


def test_load_verified_accepts_legacy_file_record_order(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    model = _model(artifact_root=artifact_root, repository=repository)
    payload = json.loads(model.manifest_path.read_text(encoding="ascii"))
    payload["files"] = list(reversed(payload["files"]))
    model.manifest_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )

    reloaded = probe.load_verified_chronos_t5_tiny_local_model(
        artifact_root=artifact_root,
        repository_root=repository,
    )

    assert reloaded.file_sha256 == model.file_sha256


@pytest.mark.parametrize("mutation", ("duplicate", "extra_key", "bad_digest"))
def test_load_verified_rejects_malformed_manifest_file_records(
    tmp_path: Path,
    mutation: str,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    model = _model(artifact_root=artifact_root, repository=repository)
    payload = json.loads(model.manifest_path.read_text(encoding="ascii"))
    if mutation == "duplicate":
        payload["files"].append(dict(payload["files"][0]))
    elif mutation == "extra_key":
        payload["files"][0]["unexpected"] = "value"
    else:
        payload["files"][0]["sha256"] = "sha256:" + "A" * 64
    model.manifest_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )

    with pytest.raises(ValueError, match="file records are invalid"):
        probe.load_verified_chronos_t5_tiny_local_model(
            artifact_root=artifact_root,
            repository_root=repository,
        )


def test_load_verified_rejects_disk_only_model_file(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    model = _model(artifact_root=artifact_root, repository=repository)
    (model.directory / "pytorch_model.bin").write_bytes(b"unsafe-pickle-route")

    with pytest.raises(ValueError, match="unsupported file"):
        probe.load_verified_chronos_t5_tiny_local_model(
            artifact_root=artifact_root,
            repository_root=repository,
        )


def test_probe_freezes_and_runs_cpu_then_cuda_without_retaining_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    model = _model(artifact_root=artifact_root, repository=repository)
    dataset = _dataset()
    contract = probe.freeze_chronos_t5_norgate_d1_probe(
        dataset,
        model,
        artifact_root=artifact_root,
        repository_root=repository,
        run_id="unit-run",
        code_revision=_sha256("code-r1"),
    )

    def forecast(contexts: np.ndarray, _phase: probe.Phase) -> np.ndarray:
        return contexts[:, -1]

    cpu = probe.run_chronos_t5_norgate_d1_probe(
        contract,
        dataset,
        model,
        phase="cpu",
        forecast=forecast,
    )
    monkeypatch.setattr(probe, "_cuda_available", lambda: True)
    cuda = probe.run_chronos_t5_norgate_d1_probe(
        contract,
        dataset,
        model,
        phase="cuda",
        forecast=forecast,
    )

    assert cpu.status == "completed"
    assert cuda.status == "completed"
    assert cpu.summary_path.parent == contract.run_directory
    cpu_payload = json.loads(cpu.summary_path.read_text(encoding="ascii"))
    cuda_payload = json.loads(cuda.summary_path.read_text(encoding="ascii"))
    assert cpu_payload["case_count"] == probe.CHRONOS_T5_CPU_CASE_COUNT
    assert cuda_payload["case_count"] == min(
        probe.CHRONOS_T5_CUDA_CASE_COUNT,
        dataset.diagnostic_windows.shape[0],
    )
    assert cpu_payload["scope"]["paper_input_eligible"] is False
    assert cuda_payload["kill_test"]["kind"] == "reversed_target_order_directional_null"
    rendered = json.dumps({"contract": json.loads(contract.path.read_text()), "cpu": cpu_payload})
    assert "SPY" not in rendered


def test_cuda_probe_requires_matching_cpu_summary(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    model = _model(artifact_root=artifact_root, repository=repository)
    dataset = _dataset()
    contract = probe.freeze_chronos_t5_norgate_d1_probe(
        dataset,
        model,
        artifact_root=artifact_root,
        repository_root=repository,
        run_id="missing-cpu",
        code_revision=_sha256("code-r1"),
    )

    with pytest.raises(ValueError, match="CPU summary"):
        probe.run_chronos_t5_norgate_d1_probe(
            contract,
            dataset,
            model,
            phase="cuda",
            forecast=lambda contexts, _phase: contexts[:, -1],
        )


def test_cuda_unavailable_is_categorical_after_cpu_evidence(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    model = _model(artifact_root=artifact_root, repository=repository)
    dataset = _dataset()
    contract = probe.freeze_chronos_t5_norgate_d1_probe(
        dataset,
        model,
        artifact_root=artifact_root,
        repository_root=repository,
        run_id="cuda-unavailable",
        code_revision=_sha256("code-r1"),
    )
    probe.run_chronos_t5_norgate_d1_probe(
        contract,
        dataset,
        model,
        phase="cpu",
        forecast=lambda contexts, _phase: contexts[:, -1],
    )

    result = probe.run_chronos_t5_norgate_d1_probe(
        contract,
        dataset,
        model,
        phase="cuda",
        forecast=lambda contexts, _phase: contexts[:, -1],
    )

    assert result.status == "cuda_unavailable"
    payload = json.loads(result.summary_path.read_text(encoding="ascii"))
    assert payload["status"] == "cuda_unavailable"


def test_probe_core_has_no_provider_credential_execution_or_model_download_import() -> None:
    source = Path(probe.__file__).read_text(encoding="utf-8").lower()
    for forbidden in (
        "os.environ",
        "requests",
        "urllib",
        "socket",
        "kis_paper",
        "kis_live",
        "local_paper",
    ):
        assert forbidden not in source
    assert "local_files_only=true" in source
    assert "inputs=context_tensor" in source
    assert "dtype=torch.bfloat16" in source
    assert "batch_size = chronos_t5_cuda_batch_size" in source
    assert "device=device" not in source
    assert "huggingface_hub" not in __import__("sys").modules


def test_compose_acquisition_is_ephemeral_and_has_no_market_or_kis_surface() -> None:
    compose = Path(__file__).parents[1] / "docker-compose.yml"
    section = compose.read_text(encoding="ascii").split(
        "\n  chronos-t5-tiny-acquisition:\n",
        maxsplit=1,
    )[1].split("\n  kis-daily-overnight-intraday-state:\n", maxsplit=1)[0]
    lowered = section.lower()

    assert 'profiles: ["research-acquisition"]' in section
    assert "read_only: true" in section
    assert "- /tmp" in section
    assert "hf_home: /tmp/huggingface" in lowered
    assert "hf_hub_disable_xet: \"1\"" in lowered
    assert "kis_paper" not in lowered
    assert "kis_live" not in lowered
    assert "/app/market_data" not in lowered


def _model(*, artifact_root: Path, repository: Path) -> probe.ChronosT5LocalModel:
    def downloader(**kwargs: object) -> str:
        destination = Path(str(kwargs["local_dir"]))
        (destination / "config.json").write_text("{}", encoding="ascii")
        (destination / "model.safetensors").write_bytes(b"safe-tensor-bytes")
        return str(destination)

    return probe.prepare_chronos_t5_tiny_local_model(
        artifact_root=artifact_root,
        repository_root=repository,
        downloader=downloader,
    )


def _dataset() -> ObservedReturnDataset:
    development = _windows(row_count=32, offset=0)
    diagnostic = _windows(row_count=64, offset=1)
    sessions = tuple(date(2025, 1, 1) + timedelta(days=index) for index in range(120))
    return ObservedReturnDataset(
        dataset_id="norgate-test-d1",
        dataset_hash=_sha256("dataset"),
        manifest_hash=_sha256("manifest"),
        common_sessions=sessions,
        development_windows=development,
        diagnostic_windows=diagnostic,
        geometry=DEFAULT_REPRESENTATION_GEOMETRY,
        selected_symbol_count=3,
        development_window_sha256=_sha256(development.tobytes()),
        diagnostic_window_sha256=_sha256(diagnostic.tobytes()),
    )


def _windows(*, row_count: int, offset: int) -> np.ndarray:
    rows = []
    for row_index in range(row_count):
        values = [((row_index + column + offset) % 7 - 3) / 1000 for column in range(40)]
        rows.append(values)
    return np.asarray(rows, dtype=np.float32)


def _sha256(value: bytes | str) -> str:
    encoded = value.encode("ascii") if isinstance(value, str) else value
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
