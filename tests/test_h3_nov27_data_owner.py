"""Credential-free checks of the dated Windows Data launcher's intake."""

import hashlib
import importlib.util
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.data import kis_paper_h3_producer
from thericher_v2.execution import kis_market_data

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_h3_nov27_data_owner.py"
SPEC = importlib.util.spec_from_file_location("nov27_data_owner_test", SCRIPT)
OWNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OWNER)


def _digest(data):
    return hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize("offset", [-1, 600, 900])
def test_outside_clock_never_verifies_or_claims(tmp_path, monkeypatch, offset):
    def forbidden(*args):
        pytest.fail("outside clock must not reach a launcher input")

    monkeypatch.setattr(OWNER, "verify_source", forbidden)
    stamp = OWNER.OPENS + timedelta(seconds=offset)
    with pytest.raises(ValueError, match="^nov27_owner_clock$"):
        OWNER.run_owner(tmp_path / "source", "1" * 64, clock=lambda: stamp)
    assert not list(tmp_path.iterdir())


def _bundle(root, monkeypatch):
    contents = {
        "src/thericher_v2/__init__.py": b"",
        "scripts/run_h3_nov27_data_owner.py": b"# fixture launcher",
        **{name: name.encode() for name in OWNER.PINNED_CODE},
    }
    hashes = {name: _digest(data) for name, data in contents.items()}
    monkeypatch.setattr(OWNER, "PINNED_CODE", {name: hashes[name] for name in OWNER.PINNED_CODE})
    for name, data in contents.items():
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
    raw = json.dumps(
        dict(schema="H3_NOV27_DATA_SOURCE_V1", run=OWNER.RUN_NAME, tree="a" * 40, files=hashes)
    ).encode()
    (root / "SOURCE.json").write_bytes(raw)
    return contents, _digest(raw)


def test_enforces_exact_import_tree(tmp_path, monkeypatch):
    root = tmp_path / "source"
    data, pin = _bundle(root, monkeypatch)
    assert OWNER.verify_source(root, pin) == {name: data[name] for name in OWNER.PINNED_CODE}
    with pytest.raises(ValueError, match="^nov27_source_digest$"):
        OWNER.verify_source(root, "0" * 64)
    injected = root / "src/thericher_v2/unlisted.py"
    injected.write_bytes(b"# unlisted import candidate")
    with pytest.raises(ValueError, match="^nov27_source_member_unlisted$"):
        OWNER.verify_source(root, pin)
    injected.unlink()
    (root / "src/thericher_v2/__init__.py").write_bytes(b"# tampered")
    with pytest.raises(ValueError, match="^nov27_source_member_changed$"):
        OWNER.verify_source(root, pin)


def test_dec3_is_a_distinct_once_only_window_and_prebind(tmp_path, monkeypatch):
    src = tmp_path / "source"
    pin = "1" * 64
    prebound = OWNER.DEC3_OPENS - timedelta(days=1)
    base, run, target = OWNER.dec3_plan(src, pin, prebound)
    assert base == tmp_path / "run"
    assert run.input_root == base / "input"
    assert target.target_root == base / "target" and target.source_sha256 == pin
    assert len(target.prebind_sha256) == 64

    def forbidden(*_args, **_kwargs):
        pytest.fail("out-of-window Dec3 must not reach source or credentials")

    monkeypatch.setattr(OWNER, "verify_source", forbidden)
    with pytest.raises(ValueError, match="^dec3_owner_clock$"):
        OWNER.run_dec3(
            src,
            pin,
            prebound_at=prebound,
            target_digest=target.prebind_sha256,
            clock=lambda: OWNER.DEC3_LAST_START,
        )
    assert not base.exists()


def test_owner_claim_precedes_scoped_loader_and_prevents_repeat(tmp_path, monkeypatch):
    root = tmp_path / "source"
    root.mkdir()
    manifest = b"invented source"
    (root / "SOURCE.json").write_bytes(manifest)
    pin = _digest(manifest)
    claim = tmp_path / "run" / "ATTEMPT.json"
    calls = []
    monkeypatch.setattr(OWNER, "MARKET", tmp_path / "invented-market")
    monkeypatch.setattr(OWNER.sys, "path", OWNER.sys.path.copy())
    monkeypatch.setattr(
        OWNER, "verify_source", lambda root, pin: dict.fromkeys(OWNER.PINNED_CODE, b"")
    )
    monkeypatch.setattr(
        OWNER, "_load", lambda *_: SimpleNamespace(prefix_features=None, parse_input=None)
    )
    monkeypatch.setattr(OWNER.shutil, "disk_usage", lambda _: SimpleNamespace(total=100, free=50))

    def config(path, *, environment):
        assert environment == {}
        assert json.loads(claim.read_bytes())["source"] == pin
        calls.append("scoped")
        return object()

    def capture(**kwargs):
        assert kwargs["owner_ready"]().ready is True
        kwargs["config_loader"]()
        return SimpleNamespace(ready_sha256="1" * 64)

    monkeypatch.setattr(kis_market_data, "load_kis_paper_market_data_config", config)
    monkeypatch.setattr(kis_paper_h3_producer, "produce_nov27_h3_publisher_input_once", capture)
    OWNER.run_owner(root, pin, clock=lambda: OWNER.OPENS)
    assert json.loads((claim.parent / "OWNER-CLOSED.json").read_bytes())["ready_sha256"] == "1" * 64
    with pytest.raises(FileExistsError):
        OWNER.run_owner(root, pin, clock=lambda: OWNER.OPENS)
    assert calls == ["scoped"]
