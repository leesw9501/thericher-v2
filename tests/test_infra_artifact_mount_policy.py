from __future__ import annotations

import tomllib
from pathlib import Path


def test_research_profile_mounts_external_artifact_and_market_data_roots() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    research = _compose_service_block(compose, "research")
    base_services = "\n".join(
        (_compose_service_block(compose, "engine"), _compose_service_block(compose, "web"))
    )

    assert "target: research" in research
    assert 'profiles: ["research"]' in research
    assert "network_mode: none" in research
    assert "read_only: true" in research
    assert "- /tmp" in research
    assert "gpus: all" in research
    assert "./src:/app/src:ro" in research
    assert "./scripts:/app/scripts:ro" in research
    assert (
        "THERICHER_MODEL_ARTIFACT_ROOT: "
        "${THERICHER_MODEL_ARTIFACT_ROOT:-/app/model_artifacts}"
    ) in research
    assert (
        "${THERICHER_HOST_MARKET_DATA_ROOT:-D:/market_data}:/app/market_data:ro"
    ) in research
    assert (
        "${THERICHER_HOST_MODEL_ARTIFACT_ROOT:-D:/thericher-v2/model-artifacts}:"
        "/app/model_artifacts"
    ) in research
    assert "/app/model_artifacts" not in base_services
    assert "NVIDIA_VISIBLE_DEVICES" not in base_services
    assert "gpus:" not in base_services


def test_torch_dependency_stays_research_docker_stage_only() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"].get("dependencies", [])
    optional_dependencies = pyproject["project"].get("optional-dependencies", {})
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    stages = _dockerfile_stages(dockerfile)

    declared_dependencies = [
        *dependencies,
        *(dependency for group in optional_dependencies.values() for dependency in group),
    ]
    assert all("torch" not in dependency.lower() for dependency in declared_dependencies)
    assert "torch==" not in stages["base"].lower()
    assert "torch==" in stages["research"].lower()
    assert "download.pytorch.org/whl/cu128" in stages["research"]
    assert "torch==" not in stages["runtime"].lower()


def _compose_service_block(compose: str, service: str) -> str:
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
