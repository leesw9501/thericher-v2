from __future__ import annotations

import hashlib
import inspect
import json
import os
import socket
import urllib.request
from pathlib import Path

import pytest

from thericher_v2.research import granite_ttm_runtime_smoke as granite


def test_prepare_allows_only_pinned_files_in_an_external_artifact_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    repo_root.mkdir()
    _pin_fixture_safetensors(monkeypatch)
    observed: dict[str, object] = {}

    def downloader(**kwargs: object) -> None:
        observed.update(kwargs)
        directory = Path(str(kwargs["local_dir"]))
        _write_model_files(directory)
        (directory / ".cache").mkdir()
        (directory / ".cache" / "download.json").write_text("{}", encoding="utf-8")

    model = granite.prepare_granite_ttm_r1_local_model(
        artifact_root=artifact_root,
        repository_root=repo_root,
        downloader=downloader,
    )

    assert set(observed["allow_patterns"]) == {
        "config.json",
        "generation_config.json",
        "model.safetensors",
    }
    assert observed["repo_id"] == granite.GRANITE_TTM_MODEL_ID
    assert observed["revision"] == granite.GRANITE_TTM_MODEL_REVISION
    assert model.directory.is_relative_to(artifact_root.resolve())
    assert not model.directory.is_relative_to(repo_root.resolve())
    assert not (model.directory / ".cache").exists()
    manifest = json.loads(model.manifest_path.read_text(encoding="utf-8"))
    assert {record["path"] for record in manifest["files"]} == {
        "config.json",
        "generation_config.json",
        "model.safetensors",
    }

    with pytest.raises(ValueError, match="outside the Git workspace"):
        granite.prepare_granite_ttm_r1_local_model(
            artifact_root=repo_root / "model-artifacts",
            repository_root=repo_root,
            downloader=downloader,
        )


def test_manifest_rejects_tampered_or_missing_safetensor_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    repo_root.mkdir()
    _pin_fixture_safetensors(monkeypatch)
    model = _prepared_model(artifact_root, repo_root)

    (model.directory / "model.safetensors").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="safetensors pin"):
        granite.load_verified_granite_ttm_r1_local_model(
            artifact_root=artifact_root,
            repository_root=repo_root,
        )

    _write_model_files(model.directory)
    _rewrite_manifest(model.directory)
    (model.directory / "generation_config.json").unlink()
    with pytest.raises(ValueError, match="incomplete"):
        granite.load_verified_granite_ttm_r1_local_model(
            artifact_root=artifact_root,
            repository_root=repo_root,
        )


def test_runtime_uses_explicit_safe_loader_and_cpu_before_cuda(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    repo_root.mkdir()
    _pin_fixture_safetensors(monkeypatch)
    model = _prepared_model(artifact_root, repo_root)
    contract = granite.freeze_granite_ttm_r1_runtime_smoke(
        model,
        artifact_root=artifact_root,
        repository_root=repo_root,
    )
    monkeypatch.setattr(
        granite,
        "_comparison_outcome",
        lambda _reference, _candidate: "within_tolerance",
    )
    calls: list[str] = []

    def inference(_directory: Path, phase: granite.Phase) -> granite.GraniteTtmInferenceOutput:
        calls.append(phase)
        return granite.GraniteTtmInferenceOutput(
            shape=(1, 96, 1),
            dtype="torch.float32",
            finite=True,
            comparison_value=object(),
            peak_memory_bytes=12 if phase == "cuda" else None,
        )

    with pytest.raises(ValueError, match="completed matching CPU receipt"):
        granite.run_granite_ttm_r1_cuda_smoke(
            contract,
            model,
            inference=inference,
            cuda_available=lambda: True,
        )

    cpu, cuda = granite.run_granite_ttm_r1_runtime_smoke(
        contract,
        model,
        include_cuda=True,
        inference=inference,
        cuda_available=lambda: True,
        clock=lambda: 1.0,
    )

    assert calls == ["cpu", "cuda"]
    assert cpu.status == "completed"
    assert cuda is not None and cuda.status == "completed"
    source = inspect.getsource(granite._local_ttm_inference)
    assert "TinyTimeMixerForPrediction" in source
    assert "local_files_only=True" in source
    assert "trust_remote_code=False" in source
    assert "AutoModel" not in source
    assert "GRANITE_TTM_CPU_FORWARD_COUNT" in source
    assert "GRANITE_TTM_CUDA_WARMUP_COUNT" in source
    assert "GRANITE_TTM_CUDA_FORWARD_COUNT" in source
    assert "_assert_cuda_peak_memory(torch)" in source
    assert "with _phase_timeout" in inspect.getsource(granite._run_phase)


def test_cuda_peak_memory_cap_is_a_terminal_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    repo_root.mkdir()
    _pin_fixture_safetensors(monkeypatch)
    model = _prepared_model(artifact_root, repo_root)
    contract = granite.freeze_granite_ttm_r1_runtime_smoke(
        model,
        artifact_root=artifact_root,
        repository_root=repo_root,
    )
    monkeypatch.setattr(
        granite,
        "_comparison_outcome",
        lambda _reference, _candidate: "within_tolerance",
    )

    def inference(_directory: Path, phase: granite.Phase) -> granite.GraniteTtmInferenceOutput:
        return granite.GraniteTtmInferenceOutput(
            shape=(1, 96, 1),
            dtype="torch.float32",
            finite=True,
            comparison_value=object(),
            peak_memory_bytes=(
                granite.GRANITE_TTM_CUDA_MAX_PEAK_MEMORY_BYTES + 1
                if phase == "cuda"
                else None
            ),
        )

    _, cuda = granite.run_granite_ttm_r1_runtime_smoke(
        contract,
        model,
        include_cuda=True,
        inference=inference,
        cuda_available=lambda: True,
        clock=lambda: 1.0,
    )

    assert cuda is not None
    assert cuda.status == "failed"
    assert cuda.terminal_category == "memory_cap_exceeded"


def test_cuda_requires_a_current_cpu_comparison_and_reattests_completed_cpu_receipts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    repo_root.mkdir()
    _pin_fixture_safetensors(monkeypatch)
    model = _prepared_model(artifact_root, repo_root)
    contract = granite.freeze_granite_ttm_r1_runtime_smoke(
        model,
        artifact_root=artifact_root,
        repository_root=repo_root,
    )
    monkeypatch.setattr(
        granite,
        "_comparison_outcome",
        lambda _reference, _candidate: "within_tolerance",
    )
    calls: list[str] = []

    def inference(_directory: Path, phase: granite.Phase) -> granite.GraniteTtmInferenceOutput:
        calls.append(phase)
        return granite.GraniteTtmInferenceOutput(
            shape=(1, 96, 1),
            dtype="torch.float32",
            finite=True,
            comparison_value=object(),
            peak_memory_bytes=0 if phase == "cuda" else None,
        )

    assert granite.run_granite_ttm_r1_cpu_smoke(
        contract,
        model,
        inference=inference,
        clock=lambda: 1.0,
    ).status == "completed"
    _, resumed_cuda = granite.run_granite_ttm_r1_runtime_smoke(
        contract,
        model,
        include_cuda=True,
        inference=inference,
        cuda_available=lambda: True,
        clock=lambda: 1.0,
    )

    assert resumed_cuda is not None
    assert resumed_cuda.status == "failed"
    assert resumed_cuda.terminal_category == "cpu_cuda_comparison_unavailable"
    assert calls == ["cpu"]

    cpu_receipt_path = contract.run_directory / "cpu-receipt.json"
    cpu_payload = json.loads(cpu_receipt_path.read_text(encoding="utf-8"))
    cpu_payload["output"] = {"shape": [1, 96, 1], "dtype": "", "finite": True}
    cpu_receipt_path.write_text(
        json.dumps(cpu_payload, ensure_ascii=True, sort_keys=True),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="completed matching CPU receipt"):
        granite.run_granite_ttm_r1_cuda_smoke(
            contract,
            model,
            inference=inference,
            cuda_available=lambda: True,
        )


def test_terminal_failure_is_not_retried_and_receipt_is_source_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    repo_root.mkdir()
    _pin_fixture_safetensors(monkeypatch)
    model = _prepared_model(artifact_root, repo_root)
    contract = granite.freeze_granite_ttm_r1_runtime_smoke(
        model,
        artifact_root=artifact_root,
        repository_root=repo_root,
    )
    calls = 0

    def failing_inference(
        _directory: Path,
        _phase: granite.Phase,
    ) -> granite.GraniteTtmInferenceOutput:
        nonlocal calls
        calls += 1
        raise RuntimeError("secret-token=do-not-persist, market-price=123.45")

    first = granite.run_granite_ttm_r1_cpu_smoke(
        contract,
        model,
        inference=failing_inference,
        clock=lambda: 1.0,
    )
    second = granite.run_granite_ttm_r1_cpu_smoke(
        contract,
        model,
        inference=failing_inference,
        clock=lambda: 1.0,
    )

    receipt = first.receipt_path.read_text(encoding="utf-8")
    assert first.status == "failed"
    assert first.terminal_category == "runtime_failure"
    assert second.receipt_sha256 == first.receipt_sha256
    assert calls == 1
    assert "secret-token" not in receipt
    assert "123.45" not in receipt
    assert "exception" not in receipt
    assert set(json.loads(receipt)) <= {
        "kind",
        "contract_sha256",
        "model_manifest_sha256",
        "phase",
        "status",
        "terminal_category",
        "elapsed_milliseconds",
        "scope",
        "output",
        "peak_memory_bytes",
        "cpu_cuda_comparison",
    }


def test_prepare_and_contract_have_no_network_or_credential_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    repo_root.mkdir()
    _pin_fixture_safetensors(monkeypatch)

    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Granite TTM local preparation must not access a network")

    class EnvironmentWithoutKisSecrets(dict[str, str]):
        def get(self, key: str, default: object = None) -> object:
            if key.startswith("KIS_"):
                raise AssertionError("Granite TTM must not read KIS credentials")
            return super().get(key, default)

    def downloader(**kwargs: object) -> None:
        _write_model_files(Path(str(kwargs["local_dir"])))

    monkeypatch.setattr(socket, "socket", fail_external)
    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "environ", EnvironmentWithoutKisSecrets(os.environ))
    model = granite.prepare_granite_ttm_r1_local_model(
        artifact_root=artifact_root,
        repository_root=repo_root,
        downloader=downloader,
    )
    contract = granite.freeze_granite_ttm_r1_runtime_smoke(
        model,
        artifact_root=artifact_root,
        repository_root=repo_root,
    )

    assert contract.path.is_relative_to(artifact_root.resolve())
    source = inspect.getsource(granite)
    assert "thericher_v2.execution" not in source
    assert "KIS_" not in source


def _prepared_model(artifact_root: Path, repo_root: Path) -> granite.GraniteTtmLocalModel:
    return granite.prepare_granite_ttm_r1_local_model(
        artifact_root=artifact_root,
        repository_root=repo_root,
        downloader=lambda **kwargs: _write_model_files(Path(str(kwargs["local_dir"]))),
    )


def _pin_fixture_safetensors(monkeypatch: pytest.MonkeyPatch) -> None:
    value = b"fixture-safetensors"
    monkeypatch.setattr(granite, "GRANITE_TTM_SAFETENSORS_SHA256", _sha256(value))
    monkeypatch.setattr(granite, "GRANITE_TTM_SAFETENSORS_SIZE", len(value))


def _write_model_files(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "config.json").write_text("{}", encoding="utf-8")
    (directory / "generation_config.json").write_text("{}", encoding="utf-8")
    (directory / "model.safetensors").write_bytes(b"fixture-safetensors")


def _rewrite_manifest(directory: Path) -> None:
    records = granite._verified_model_file_records(directory)
    payload = {
        "kind": "granite_ttm_r1_local_model_manifest",
        "model_id": granite.GRANITE_TTM_MODEL_ID,
        "model_revision": granite.GRANITE_TTM_MODEL_REVISION,
        "license": granite.GRANITE_TTM_MODEL_LICENSE,
        "source_url": granite.GRANITE_TTM_SOURCE_URL,
        "runtime_package": {
            "name": granite.GRANITE_TTM_PACKAGE,
            "version": granite.GRANITE_TTM_PACKAGE_VERSION,
        },
        "safe_serialization": True,
        "files": records,
        "scope": granite._non_promoting_scope(),
    }
    (directory / "model-manifest.json").write_text(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
