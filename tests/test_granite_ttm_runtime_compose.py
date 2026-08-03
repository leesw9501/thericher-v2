from __future__ import annotations

from pathlib import Path


def test_granite_runtime_docker_target_keeps_torch_cuda_inherited_and_verified() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    stages = _dockerfile_stages(dockerfile)
    granite = stages["granite-ttm-runtime"]

    assert "FROM research AS granite-ttm-runtime" in granite
    assert "--system-site-packages /opt/granite-venv" in granite
    assert "--no-deps" in granite
    assert "python -m pip check" in granite
    assert "requirements/granite-ttm-runtime.lock" in granite
    assert "sys.version_info[:2] == (3, 12)" in granite
    assert "torch.__version__ == '2.7.0+cu128'" in granite
    assert "torch.version.cuda == '12.8'" in granite
    assert "TinyTimeMixerForPrediction" in granite
    assert "torch==" not in granite.lower()


def test_granite_runtime_lock_is_exact_and_limits_additions_to_runtime_dependencies() -> None:
    lock = Path("requirements/granite-ttm-runtime.lock").read_text(encoding="utf-8")
    requirements = [line for line in lock.splitlines() if line and not line.startswith("#")]

    assert requirements
    assert all("==" in requirement for requirement in requirements)
    assert "granite-tsfm==0.3.1" in requirements
    assert "datasets==5.0.1" in requirements
    assert "Deprecated==1.3.1" in requirements
    assert all("torch" not in requirement.lower() for requirement in requirements)
    assert all("transformers" not in requirement.lower() for requirement in requirements)


def test_granite_acquisition_service_is_profiled_credential_free_and_artifact_scoped() -> None:
    service = _compose_service_block("granite-ttm-r1-acquisition")

    assert 'profiles: ["granite-ttm-acquisition"]' in service
    assert "target: granite-ttm-runtime" in service
    assert "thericher-v2-granite-ttm-runtime:0.3.1-torch2.7.0-cu128" in service
    assert "network_mode: none" not in service
    assert "read_only: true" in service
    assert "- /tmp" in service
    assert "scripts/prepare_granite_ttm_r1_model.py" in service
    assert "THERICHER_MODE: off" in service
    _assert_isolated_from_sensitive_surfaces(service)
    assert _volume_lines(service) == [
        "- ${THERICHER_HOST_MODEL_ARTIFACT_ROOT:-D:/thericher-v2/model-artifacts}:"
        "/app/model_artifacts"
    ]


def test_granite_runtime_smoke_service_is_offline_gpu_and_artifact_scoped() -> None:
    service = _compose_service_block("granite-ttm-r1-runtime-smoke")

    assert 'profiles: ["granite-ttm-runtime-smoke"]' in service
    assert "target: granite-ttm-runtime" in service
    assert "network_mode: none" in service
    assert "read_only: true" in service
    assert "gpus: all" in service
    assert "cpus: 2.0" in service
    assert "mem_limit: 2g" in service
    assert "- /tmp" in service
    assert "scripts/run_granite_ttm_r1_runtime_smoke.py" in service
    assert "THERICHER_MODE: off" in service
    assert 'HF_HUB_OFFLINE: "1"' in service
    assert 'TRANSFORMERS_OFFLINE: "1"' in service
    _assert_isolated_from_sensitive_surfaces(service)
    assert _volume_lines(service) == [
        "- ${THERICHER_HOST_MODEL_ARTIFACT_ROOT:-D:/thericher-v2/model-artifacts}:"
        "/app/model_artifacts"
    ]


def _assert_isolated_from_sensitive_surfaces(service: str) -> None:
    lowered = service.lower()
    for forbidden in (
        "kis_",
        "dashboard",
        "market_data",
        "/app/runtime",
        "/app/events",
        "/app/orders",
        "live",
        "thericher-v2-runtime",
    ):
        assert forbidden not in lowered


def _volume_lines(service: str) -> list[str]:
    lines = service.splitlines()
    start = lines.index("    volumes:")
    return [line.strip() for line in lines[start + 1 :] if line.startswith("      - ")]


def _compose_service_block(service: str) -> str:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    lines = compose.splitlines()
    marker = f"  {service}:"
    start = lines.index(marker)
    block: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("  ") and not line.startswith("    "):
            break
        block.append(line)
    return "\n".join(block)


def _dockerfile_stages(dockerfile: str) -> dict[str, str]:
    stages: dict[str, str] = {}
    current_name: str | None = None
    current_lines: list[str] = []
    for line in dockerfile.splitlines():
        lower = line.lower()
        if lower.startswith("from "):
            if current_name is not None:
                stages[current_name] = "\n".join(current_lines)
            current_lines = [line]
            current_name = lower.rsplit(" as ", maxsplit=1)[-1].strip()
        elif current_name is not None:
            current_lines.append(line)
    if current_name is not None:
        stages[current_name] = "\n".join(current_lines)
    return stages
