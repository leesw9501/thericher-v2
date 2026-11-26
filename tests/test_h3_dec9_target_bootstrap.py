"""Credential-free Dec9 bootstrap source and native callable binding checks."""

import importlib.util
import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest

from thericher_v2.ops.h3_dec9_fixed_half_target import ENTRY_OPEN, Dec9TargetPins

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/run_h3_dec9_target_owner.py"
SPEC = importlib.util.spec_from_file_location("dec9_bootstrap_test", SCRIPT)
BOOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOOT)
OWNER = "src/thericher_v2/ops/h3_dec9_target_owner.py"


def _freeze(root, members, **override):
    for name, data in members.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    manifest = dict(
        schema=BOOT.SOURCE_SCHEMA,
        run=BOOT.RUN_NAME,
        tree="a" * 40,
        files={key: BOOT._sha(raw) for key, raw in members.items()},
    )
    manifest.update(override)
    raw = json.dumps(manifest).encode()
    (root / "SOURCE.json").write_bytes(raw)
    return BOOT._sha(raw)


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    root = tmp_path / "source"
    monkeypatch.setattr(BOOT, "SOURCE", root)
    members = dict.fromkeys(BOOT._REQUIRED, b"marker = 'frozen'\n")
    return root, members, _freeze(root, members)


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ("digest", "digest"),
        ("phase", "manifest"),
        ("missing", "member_missing"),
        ("changed", "member_changed"),
        ("extra_file", "member_unlisted"),
        ("cache_dir", "member_unlisted"),
    ],
)
def test_source_refuses_nonexact_freeze(frozen, change, error):
    root, members, pin = frozen
    assert BOOT.verify_source(pin) == members
    if change == "digest":
        pin = "0" * 64
    elif change == "phase":
        pin = _freeze(root, members, schema="H3_DEC3_DATA_SOURCE_V1")
    elif change == "missing":
        (root / OWNER).unlink()
    elif change == "changed":
        (root / OWNER).write_bytes(b"marker = 'changed'")
    elif change == "extra_file":
        (root / "src/thericher_v2/ops/unlisted.pyd").touch()
    else:
        (root / "src/thericher_v2/ops/__pycache__").mkdir()
    with pytest.raises(ValueError, match=f"^dec9_source_{error}$"):
        BOOT.verify_source(pin)


def test_loader_executes_only_the_verified_bytes(frozen):
    root, _, pin = frozen
    loader = BOOT._FrozenImports(BOOT.verify_source(pin))
    (root / OWNER).write_bytes(b"raise AssertionError('reopened source')")
    spec = loader.find_spec("thericher_v2.ops.h3_dec9_target_owner")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    assert module.marker == "frozen"
    with pytest.raises(ModuleNotFoundError, match="dec9_source_import"):
        loader.find_spec("thericher_v2.ops.h3_dec9_other_owner")


def test_isolated_binding_uses_real_target_owner(tmp_path):
    data_root, market_root = tmp_path / "data", tmp_path / "market"
    root = data_root / "source"
    members = {
        path.relative_to(REPO).as_posix(): path.read_bytes()
        for path in (REPO / "src/thericher_v2").rglob("*.py")
    }
    members[BOOT.ENTRY] = SCRIPT.read_bytes()
    pin = _freeze(root, members)
    prebound_at = ENTRY_OPEN - timedelta(seconds=1)
    pins = Dec9TargetPins(
        owner="thericher-" + BOOT.RUN_NAME,
        source_sha256=pin,
        attempt_sha256=BOOT._sha(f"{BOOT.RUN_NAME}:{pin}".encode("ascii")),
        data_root=data_root,
        market_root=market_root,
        prebound_at=prebound_at,
        capture_opens=BOOT.OPENS,
        capture_closes=BOOT.CLOSES,
        seal_before=BOOT.SEAL_BEFORE,
    )
    check = """
import importlib.util
import sys
from datetime import datetime
from pathlib import Path

entry, venv, pin, prebound_at, digest = sys.argv[1:]
spec = importlib.util.spec_from_file_location("dec9_test_child", entry)
boot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)
boot.SOURCE = Path(entry).parents[1]
boot.DATA_ROOT = boot.SOURCE.parent
boot.MARKET_ROOT = boot.DATA_ROOT.parent / "market"
boot.VENV = Path(venv)
boot._require_runtime = lambda: None
boot._capture_window = lambda: None
args = {"prebound_at": datetime.fromisoformat(prebound_at)}
try:
    boot.bind_target_owner(pin, target_prebind_sha256="0" * 64, **args)
except ValueError as error:
    assert str(error) == "dec9_owner_prebind"
else:
    raise AssertionError("wrong prebind admitted")
assert not any(boot._project_module(name) for name in sys.modules)
bound = boot.bind_target_owner(pin, target_prebind_sha256=digest, **args)
from thericher_v2.ops.h3_dec9_target_owner import run_dec9_target_owner
assert bound.run_owner is run_dec9_target_owner
assert bound.pins.prebind_sha256 == bound.prebind_sha256 == digest
"""
    subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-c",
            check,
            str(root / BOOT.ENTRY),
            sys.prefix,
            pin,
            prebound_at.isoformat(),
            pins.prebind_sha256,
        ],
        check=True,
        timeout=30,
    )
    assert not (data_root / "run").exists()
    assert not market_root.exists()


def test_bootstrap_is_not_an_executable_dispatch():
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(SCRIPT)], check=False, timeout=10
    )
    assert completed.returncode == 20
