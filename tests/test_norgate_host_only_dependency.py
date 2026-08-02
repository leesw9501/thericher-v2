from __future__ import annotations

import tomllib
from pathlib import Path


def test_norgate_client_is_isolated_from_base_and_docker_research_runtime() -> None:
    repository = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((repository / "pyproject.toml").read_text(encoding="utf-8"))
    extras = pyproject["project"]["optional-dependencies"]
    base_dependencies = pyproject["project"]["dependencies"]

    assert extras["norgate-host"] == ["norgatedata==1.0.77"]
    assert all("norgatedata" not in requirement for requirement in extras["research"])
    assert all("norgatedata" not in requirement for requirement in base_dependencies)

    dockerfile = (repository / "Dockerfile").read_text(encoding="ascii")
    assert '-e ".[research]"' in dockerfile
    assert "norgate-host" not in dockerfile
