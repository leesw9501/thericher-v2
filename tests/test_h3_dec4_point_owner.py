import io
import json
import subprocess
from datetime import timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.models import h3_shadow_point
from thericher_v2.ops import h3_dec4_point_owner as owner
from thericher_v2.ops.h3_dec4_run import Dec4H3Run

_PARSER_BYTES = b"""def validate_input(arrays, header, *, expected_source, role, expected_keys,
                   synthetic):
    if (header['source'], header['role'], header['synthetic']) != (
        expected_source, role, synthetic
    ) or arrays['key'].tolist() != expected_keys:
        raise ValueError('invented parser binding')
"""
_MODEL_BYTES = b"""import torch

class HorizonModel(torch.nn.Module):
    def __init__(self, kind):
        super().__init__()
        assert kind == "LSTM"
        self.lstm = torch.nn.LSTM(12, 2, batch_first=True)
        self.projection = torch.nn.Linear(10, 3)

    def forward(self, x, z):
        return self.projection(torch.cat([self.lstm(x)[0][:, -1], z], dim=1))
"""


@pytest.fixture
def setup_owner(tmp_path, monkeypatch):
    research = tmp_path / "research"
    data = tmp_path / "data" / owner.DATA_NAME
    root = data / "run"
    market = tmp_path / "unused-market"
    parser = data / "source" / owner._PARSER
    parser.parent.mkdir(parents=True)
    parser.write_bytes(_PARSER_BYTES)
    parser_digest = owner._sha(_PARSER_BYTES)
    source = parser.parent.parent / "SOURCE.json"
    source.write_bytes(
        owner._json(
            dict(
                schema="H3_DEC3_DATA_SOURCE_V1",
                run=owner.DATA_NAME,
                tree="1" * 40,
                files={owner._WRITER: owner._WRITER_SHA, owner._PARSER: parser_digest},
            )
        )
    )
    source_digest = owner._sha(source.read_bytes())
    for name, value in (
        ("_RESEARCH", research),
        ("_DATA", data),
        ("_MARKET", market),
        ("_PARSER_SHA", parser_digest),
        ("DATA_SOURCE_SHA256", source_digest),
        ("process_start", lambda pid: None),
    ):
        monkeypatch.setattr(owner, name, value)
    run = Dec4H3Run(market, root / "capture", root / "input", root / "point", source_digest, False)
    run.artifact_root.mkdir(parents=True)
    run.input_root.mkdir()
    attempt_path = root / "owner" / "ATTEMPT.json"
    attempt_path.parent.mkdir()
    closed_path = root / "OWNER-CLOSED.json"
    ready_path = run.input_root / "READY.json"
    state = run.artifact_root / "capture-state.json"
    state.write_bytes(b'{"invented":true}')
    start = owner.CAPTURE_OPENS_UTC
    birth = f"win-filetime:{owner._ticks(start)}"
    decision = h3_shadow_point.DEC4_BINDING_CLOCK.isoformat()
    np.savez_compressed(
        run.input_root / "INPUT.npz",
        x=np.zeros((17, 60, 12), np.float32),
        z=np.zeros((17, 8), np.float64),
        known=np.ones(17, bool),
        entry_index=np.zeros(17, np.int64),
        key=np.array([f"20261204|{i:02}" for i in range(17)]),
        decision_at=np.full(17, decision),
        context_close=np.full(17, "2026-12-03T21:00:00+00:00"),
    )
    header = owner._json(
        dict(
            schema="SHORT_SWING_H123_INPUT_V1",
            producer="Data.ShortSwingEndpointProducer",
            consumer="EngineResearch.ShortSwingHorizonInput",
            source=source_digest,
            role="FUTURE_20261203_ASOF_20261204",
            synthetic=False,
            unit="ORIGINAL_LOG_OHLC_LAST_CLOSE_PLUS_IND8",
            shape=[60, 12, 8],
            role_start=0,
            role_stop=1,
            payload_sha256=owner._sha((run.input_root / "INPUT.npz").read_bytes()),
        )
    )
    (run.input_root / "INPUT.json").write_bytes(header)
    ready = dict(
        schema="H3_PUBLISHER_INPUT_READY_V1",
        source_sha256=source_digest,
        synthetic=False,
        decision_at=decision,
        closed_at=start.replace(minute=38).isoformat(),
        capture_state_sha256=owner._sha(state.read_bytes()),
        input_header_sha256=owner._sha(header),
        input_payload_sha256=json.loads(header)["payload_sha256"],
        ready_at=start.replace(minute=43).isoformat(),
    )
    attempt = dict(
        schema="H3_DEC3_DATA_ATTEMPT_V1",
        owner="thericher-" + owner.DATA_NAME,
        launch_attempt_sha256=owner._sha(f"{owner.DATA_NAME}:{source_digest}".encode("ascii")),
        source_sha256=source_digest,
        target_prebind_sha256=owner._PREBIND,
        started_at=start.isoformat(),
        pid=12345,
        synthetic=False,
        roots=[
            str(path)
            for path in (
                run.market_root,
                run.artifact_root,
                run.input_root,
                run.point_root,
                attempt_path.parent,
            )
        ],
    )
    closed = dict(
        schema="H3_DEC3_OWNER_CLOSED_V1",
        source_sha256=source_digest,
        native_start=birth,
        closed_at=start.replace(minute=44).isoformat(),
        target_status="pin_failed",
        target_custody_sha256=None,
    )

    def write_data():
        attempt_path.write_bytes(owner._json(attempt))
        ready_path.write_bytes(owner._json(ready))
        closed.update(
            attempt_sha256=owner._sha(attempt_path.read_bytes()),
            ready_sha256=owner._sha(ready_path.read_bytes()),
        )
        (run.input_root / "DATA-READY.json").write_bytes(run._receipt(closed["ready_sha256"]))
        closed_path.write_bytes(owner._json(closed))

    def checkpoint(blobs):
        members, pins, mounts, paths = [], [], {}, []
        for (name, _, _), blob, const in zip(
            owner._MEMBERS, blobs, ("MODEL_SHA", "STATS_SHA", "WEIGHTS_SHA"), strict=True
        ):
            path = research / "original" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
            digest = owner._sha(blob)
            members.append((name, digest, len(blob)))
            pins.append(dict(path=path.as_posix(), sha256=digest, bytes=len(blob)))
            mounts["/" + name] = dict(path=str(path), sha256=digest)
            paths.append(path)
            monkeypatch.setattr(h3_shadow_point, const, digest)
        manifest = research / owner._SOURCE72 / "SOURCE.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_bytes(
            owner._json(
                dict(
                    schema="NOV9_LSTM_H3_CLOCK_BOUND_SOURCE_V2",
                    pins=pins,
                    mount_files=mounts,
                )
            )
        )
        monkeypatch.setattr(owner, "_MEMBERS", tuple(members))
        monkeypatch.setattr(owner, "SOURCE72_SHA256", owner._sha(manifest.read_bytes()))
        return paths

    write_data()
    box = SimpleNamespace(
        run=run,
        root=root,
        source=source,
        attempt=attempt,
        attempt_path=attempt_path,
        closed=closed,
        closed_path=closed_path,
        ready=ready,
        ready_path=ready_path,
        now=owner.OPENS,
        checkpoint=checkpoint,
        write_data=write_data,
        calls=[],
    )

    def attest(pid, native_start, digest):
        assert (pid, native_start, digest) == (
            attempt["pid"],
            birth,
            owner._sha(closed_path.read_bytes()),
        )
        box.calls.append(digest)
        return True

    def launch(**kwargs):
        options = dict(
            point_source_sha256="f" * 64,
            owner_ready=lambda: True,
            data_owner_closed=attest,
            clock=lambda: box.now,
        )
        return owner.run_dec4_point_owner(**(options | kwargs))

    box.launch = launch
    return box


def test_native_invented_cpu_forward_and_exact_closure(setup_owner, monkeypatch):
    torch = pytest.importorskip("torch")
    safetensors = pytest.importorskip("safetensors.torch")
    b = setup_owner
    model_module = {}
    exec(_MODEL_BYTES, model_module)
    model = model_module["HorizonModel"]("LSTM")
    state = {name: torch.zeros_like(value) for name, value in model.state_dict().items()}
    state["projection.bias"][:] = 1
    stats = io.BytesIO()
    np.savez(
        stats,
        mean=np.zeros(12),
        std=np.ones(12),
        zmean=np.zeros(8),
        zstd=np.ones(8),
        scale=np.array(1.0),
    )
    b.checkpoint((_MODEL_BYTES, stats.getvalue(), safetensors.save(state)))
    calls = []
    native = h3_shadow_point._frozen_lstm

    def forward(*args, **kwargs):
        calls.append(1)
        return native(*args, **kwargs)

    monkeypatch.setattr(h3_shadow_point, "_frozen_lstm", forward)
    digest = b.launch()
    point_root = b.run.point_root
    close = json.loads((point_root / "OWNER-CLOSED.json").read_bytes())
    point = (point_root / "POINT.json").read_bytes()
    assert close["point_sha256"] == digest == owner._sha(point)
    assert close["data_owner_sha256"] == owner._sha(b.closed_path.read_bytes())
    assert close["data_attempt_sha256"] == owner._sha(b.attempt_path.read_bytes())
    assert close["ready_sha256"] == owner._sha(b.ready_path.read_bytes())
    assert json.loads(point)["scores"] == [1.0] * 17
    assert close["financial_authority"] is False and len(b.calls) >= 3
    assert not b.run.market_root.exists() and not (b.root / "target").exists()
    with pytest.raises(FileExistsError):
        b.launch()
    assert calls == [1]


@pytest.mark.parametrize("status", ["not_bound", "seal_failed", "pin_failed", "pinned"])
def test_target_categories_do_not_read_or_gate_target_files(setup_owner, monkeypatch, status):
    b = setup_owner
    b.closed["target_status"] = status
    if status == "not_bound":
        b.attempt["target_prebind_sha256"] = None
    if status == "pinned":
        b.closed["target_custody_sha256"] = "e" * 64
    b.write_data()
    b.checkpoint((b"model", b"stats", b"weights"))

    def forward(*args, before_forward):
        before_forward()
        return np.zeros(17)

    monkeypatch.setattr(h3_shadow_point, "_frozen_lstm", forward)
    b.launch()
    assert (b.run.point_root / "OWNER-CLOSED.json").is_file()
    assert not (b.root / "target").exists()


@pytest.mark.parametrize(
    ("record", "field", "value", "error"),
    [
        ("attempt", "pid", True, "owner_binding"),
        ("attempt", "launch_attempt_sha256", "0" * 64, "owner_binding"),
        ("attempt", "roots", [], "owner_binding"),
        ("attempt", "started_at", "2026-12-03T21:29:59+00:00", "data_clock"),
        ("closed", "native_start", "linux-startticks:123", "native_start"),
        ("closed", "native_start", "win-filetime:1", "data_clock"),
        ("closed", "closed_at", "2026-12-03T21:45:00+00:00", "data_clock"),
        ("closed", "target_status", "unknown_other", "categorical"),
        ("ready", "closed_at", "2026-12-03T21:40:00+00:00", "data_clock"),
        ("ready", "ready_at", "2026-12-03T21:44:59+00:00", "data_clock"),
        ("ready", "ready_at", "2026-12-03T21:43:00-05:00", "data_clock"),
        ("ready", "synthetic", True, "ready_binding"),
    ],
)
def test_refuses_resealed_but_wrong_installed_record(setup_owner, record, field, value, error):
    b = setup_owner
    getattr(b, record)[field] = value
    b.write_data()
    with pytest.raises(ValueError, match=error):
        b.launch()
    assert not b.run.point_root.exists()


@pytest.mark.parametrize("which", ["source", "attempt_path", "ready_path", "data_ready"])
def test_refuses_broken_digest_chain(setup_owner, which):
    b = setup_owner
    path = (b.run.input_root / "DATA-READY.json") if which == "data_ready" else getattr(b, which)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="digest|record"):
        b.launch()
    assert not b.run.point_root.exists()


def test_refuses_reparse_parent(setup_owner):
    b = setup_owner
    original = b.attempt_path.parent
    moved = original.rename(b.root / "moved")
    if owner.os.name == "nt":
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(original), str(moved)],
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0
    else:
        original.symlink_to(moved, target_is_directory=True)
    try:
        with pytest.raises(ValueError, match="reparse"):
            b.launch()
    finally:
        if owner.os.name == "nt":
            original.rmdir()
        else:
            original.unlink()


@pytest.mark.parametrize("which", ["owner", "tree", "native"])
def test_refuses_unproven_owners(setup_owner, monkeypatch, which):
    b = setup_owner
    options = {}
    if which == "owner":
        options["owner_ready"] = lambda: False
    elif which == "tree":
        options["data_owner_closed"] = lambda *_: False
    else:
        monkeypatch.setattr(owner, "process_start", lambda pid: b.closed["native_start"])
    with pytest.raises(ValueError, match="not_ready|not_closed"):
        b.launch(**options)
    assert not b.run.point_root.exists()


@pytest.mark.parametrize("which", ["model", "stats", "weights"])
def test_refuses_changed_source72_member_before_forward(setup_owner, which):
    b = setup_owner
    paths = dict(
        zip(
            ("model", "stats", "weights"),
            b.checkpoint((b"model", b"stats", b"weights")),
            strict=True,
        )
    )
    path = paths[which]
    path.write_bytes(b"0" * path.stat().st_size)
    with pytest.raises(ValueError, match="source_member_digest"):
        b.launch()
    assert not b.run.point_root.exists()
    with pytest.raises(FileExistsError):
        b.launch()


@pytest.mark.parametrize("which", ["early", "late", "regression", "hard"])
def test_windows_and_no_late_closure(setup_owner, monkeypatch, which):
    b = setup_owner
    b.checkpoint((b"unused model", b"stats", b"weights"))
    forwards = []

    def forward(*args, before_forward):
        if which == "regression":
            b.now -= timedelta(seconds=1)
        before_forward()
        forwards.append(1)
        b.now = owner.HARD_STOP
        return np.ones(17)

    monkeypatch.setattr(h3_shadow_point, "_frozen_lstm", forward)
    if which == "early":
        b.now = owner.OPENS - timedelta(microseconds=1)
    elif which == "late":
        b.now = owner.LAST_START
    elif which == "regression":
        b.now = owner.OPENS + timedelta(seconds=2)
    with pytest.raises(ValueError, match="owner_clock|owner_start"):
        b.launch()
    assert forwards == ([1] if which == "hard" else [])
    assert not (b.run.point_root / "OWNER-CLOSED.json").exists()


def test_handoff_change_after_input_check_withholds_point(setup_owner, monkeypatch):
    b = setup_owner
    b.checkpoint((b"unused model", b"stats", b"weights"))

    def forward(*args, before_forward):
        before_forward()
        b.closed["target_status"] = "seal_failed"
        b.write_data()
        return np.ones(17)

    monkeypatch.setattr(h3_shadow_point, "_frozen_lstm", forward)
    with pytest.raises(ValueError, match="handoff_changed"):
        b.launch()
    assert not (b.run.point_root / "OWNER-CLOSED.json").exists()


def test_hard_stop_at_closure_rename_withholds_completion(setup_owner, monkeypatch):
    b = setup_owner
    b.checkpoint((b"unused model", b"stats", b"weights"))

    def forward(*args, before_forward):
        before_forward()
        return np.ones(17)

    path_type = type(b.run.point_root)
    native_rename = path_type.rename

    def rename(path, target):
        moved = native_rename(path, target)
        if path.name == "OWNER-CLOSED.pending":
            b.now = owner.HARD_STOP
        return moved

    monkeypatch.setattr(h3_shadow_point, "_frozen_lstm", forward)
    monkeypatch.setattr(path_type, "rename", rename)
    with pytest.raises(ValueError, match="owner_clock"):
        b.launch()
    assert (b.run.point_root / "POINT.json").is_file()
    assert not (b.run.point_root / "OWNER-CLOSED.json").exists()
