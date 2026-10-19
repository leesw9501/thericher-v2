"""Pure allowlisted environment tests; no native shell, API or Docker effects."""

import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts/run_kis_paper_etf_daily_context.py"
SPEC = importlib.util.spec_from_file_location("etf_pathext_test_host", PATH)
host = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(host)


@pytest.mark.parametrize("key", ["PATHEXT", "PathExt", "pathext"])
@pytest.mark.parametrize("value", [None, "", " \t\r\n", ".EXE;.COM;.CUSTOM", " .EXE;.COM "])
def test_only_absent_empty_or_whitespace_pathext_gets_safe_fallback(monkeypatch, key, value):
    source = {
        "PATH": "synthetic-path",
        "WINDIR": "synthetic-windows",
        "DOCKER_CONTEXT": "synthetic-context",
    }
    if value is not None:
        source[key] = value
    monkeypatch.setattr(host.os, "environ", source)
    result = host.os_environment()
    target = "PATHEXT" if value is None else key
    expected = ".COM;.EXE;.BAT;.CMD" if value is None or not value.strip() else value
    assert result == {**source, target: expected}
    assert source.get(key) == value


def test_secret_values_never_read_or_forwarded_and_no_extra_os_keys(monkeypatch):
    reads = []

    class Environment(dict):
        def __getitem__(self, key):
            reads.append(key)
            if key not in {"PATH", "PATHEXT"}:
                raise AssertionError("secret_value_must_not_be_read")
            return super().__getitem__(key)

    source = Environment(
        PATH="synthetic-path",
        PATHEXT=".EXE;.COM",
        KIS_PAPER_APP_SECRET="synthetic-secret",
        KIS_LIVE_APP_SECRET="synthetic-secret",
        AWS_SECRET_ACCESS_KEY="synthetic-secret",
        PRIVATE_TOKEN="synthetic-secret",
    )
    monkeypatch.setattr(host.os, "environ", source)
    assert host.os_environment() == {"PATH": "synthetic-path", "PATHEXT": ".EXE;.COM"}
    assert set(reads) == {"PATH", "PATHEXT"}
