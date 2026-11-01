from __future__ import annotations

import ast
from pathlib import Path

from thericher_v2.dashboard.server import build_parser

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_monitor_overlay_exposes_only_public_read_only_projection():
    source = (REPO_ROOT / "docker-compose.monitor.yml").read_text(encoding="utf-8")
    assert "THERICHER_OPERATIONS_ROOT: /app/operations" in source
    assert "model-artifacts/monitor/paper-operations" in source
    assert "read_only: true" in source
    assert "create_host_path: false" in source
    assert "restart: unless-stopped" in source
    for forbidden in ("KIS_", "TIINGO", "/app/private", "docker.sock", "ports:"):
        assert forbidden not in source


def test_operation_root_is_opt_in_without_implicit_env_file(monkeypatch):
    monkeypatch.delenv("THERICHER_OPERATIONS_ROOT", raising=False)
    assert build_parser().parse_args([]).operations_artifact_root is None
    monkeypatch.setenv("THERICHER_OPERATIONS_ROOT", "/app/public-test-outcomes")
    assert build_parser().parse_args([]).operations_artifact_root == Path(
        "/app/public-test-outcomes"
    )


def test_server_and_monitor_have_no_credential_or_broker_imports():
    for name in ("server.py", "operations.py"):
        source = (REPO_ROOT / "src/thericher_v2/dashboard" / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        ] + [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        assert not any("kis" in name.lower() for name in imports)
        assert not any("dotenv" in name.lower() for name in imports)


def test_docker_context_excludes_local_environment_and_unrelated_scratch():
    lines = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in lines
    assert ".venv" in lines
    assert "%SystemDrive%" in lines
