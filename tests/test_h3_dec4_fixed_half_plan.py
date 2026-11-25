import json
from pathlib import Path

import numpy as np
import pytest

from test_h3_dec4_point_owner import setup_owner  # noqa: F401
from test_nov30_h3_checkpoint_loader import SCALE, synthetic  # noqa: F401
from thericher_v2.ops import h3_dec4_fixed_half_plan as plan
from thericher_v2.ops import h3_dec4_point_owner as dec3
from thericher_v2.ops import h3_nov30_run as nov30


@pytest.fixture
def case(setup_owner, monkeypatch):  # noqa: F811
    box = setup_owner
    box.now = plan.OPENS
    box.destination = dec3._RESEARCH / plan.STUDY / "run"
    box.destination.parent.mkdir(parents=True)

    def launch(**kwargs):
        return plan.run_dec4_fixed_half_forecast(
            **(
                dict(
                    forecast_source_sha256="f" * 64,
                    clock=lambda: box.now,
                    owner_ready=lambda: True,
                    data_owner_closed=lambda *args: True,
                )
                | kwargs
            )
        )

    def rewrite(**updates):
        root = box.run.input_root
        with np.load(root / "INPUT.npz", allow_pickle=False) as archive:
            arrays = dict(archive)
        np.savez_compressed(root / "INPUT.npz", **(arrays | updates))
        header_path = root / "INPUT.json"
        header = json.loads(header_path.read_bytes())
        header["payload_sha256"] = dec3._sha((root / "INPUT.npz").read_bytes())
        header_path.write_bytes(dec3._json(header))
        box.ready.update(
            input_header_sha256=dec3._sha(header_path.read_bytes()),
            input_payload_sha256=header["payload_sha256"],
        )
        box.write_data()

    box.launch, box.rewrite = launch, rewrite
    return box


def test_native_join_and_two_cpu_forwards(case, synthetic, monkeypatch):  # noqa: F811
    import torch
    from safetensors.torch import load, save

    own = plan.loader.SELF_PIN
    bundled = save(
        {
            **{f"model.{key}": value for key, value in load(synthetic["self_checkpoint"]).items()},
            "optimizer.11": torch.tensor([float("nan")]),
            "rng.cpu": torch.zeros(4, dtype=torch.uint8),
        }
    )
    monkeypatch.setattr(
        plan.loader, "SELF_PIN", plan.loader.H3ModelPin(own.source_sha256, dec3._sha(bundled))
    )
    member_paths = {}
    for name, raw in (synthetic | {"self_checkpoint": bundled}).items():
        path = case.destination.parent / name
        path.write_bytes(raw)
        member_paths[name] = path
    monkeypatch.setattr(plan, "_MEMBERS", member_paths)
    real_loader = plan._make_forward
    calls = []

    def factory(members):
        native = real_loader(members)

        def forward(name, arrays):
            calls.append(name)
            assert not arrays["key"].flags.writeable
            assert tuple(arrays["key"]) == plan.KEYS
            assert arrays["decision_at"].tolist() == [plan.HARD_STOP.isoformat()] * 17
            return native(name, arrays)

        return forward

    monkeypatch.setattr(plan, "_make_forward", factory)
    lstat = Path.lstat

    def no_point_or_target(path):
        assert not path.is_relative_to(case.run.point_root)
        assert not path.is_relative_to(case.run.market_root)
        return lstat(path)

    case.run.point_root.mkdir()
    monkeypatch.setattr(Path, "lstat", no_point_or_target)
    row = np.arange(17, dtype=np.float64)
    x = np.broadcast_to((2 * row + 2).astype(np.float32)[:, None, None], (17, 60, 12))
    z = np.broadcast_to((4 * row + 3)[:, None], (17, 8))
    case.rewrite(x=x, z=z)

    def attest(pid, birth, digest):
        return (pid, birth, digest) == (
            case.attempt["pid"],
            case.closed["native_start"],
            dec3._sha(case.closed_path.read_bytes()),
        )

    digest = case.launch(data_owner_closed=attest)
    raw = (case.destination / "SEAL.json").read_bytes()
    obj = json.loads(raw)
    attempt = (case.destination / "ATTEMPT.json").read_bytes()
    assert digest == dec3._sha(raw)
    assert calls == ["SELF", "OLD60"]
    assert obj["attempt_sha256"] == dec3._sha(attempt)
    assert obj["data_owner_sha256"] == dec3._sha(case.closed_path.read_bytes())
    assert obj["ready_sha256"] == case.closed["ready_sha256"]
    assert obj["data_ready_sha256"] == dec3._sha(
        (case.run.input_root / "DATA-READY.json").read_bytes()
    )
    assert obj["financial_authority"] is False
    assert obj["policy_sha256"] == nov30.POLICY_SHA256
    assert obj["keys"] == list(plan.KEYS)
    assert obj["entry_open"] == "2026-12-04T14:30:00+00:00"
    assert obj["expiry_open"] == "2026-12-09T14:30:00+00:00"
    assert obj["SELF"] == pytest.approx(2 * row * SCALE)
    assert obj["OLD60"] == pytest.approx(-2 * row * SCALE)
    assert obj["BLEND"] == pytest.approx(np.zeros(17))
    with pytest.raises(FileExistsError, match="pending_or_consumed"):
        case.launch()
    assert calls == ["SELF", "OLD60"]


@pytest.mark.parametrize("failure", ["opening", "closure", "receipt", "key", "close", "decision"])
def test_denies_inexact_dec3_join_before_model_read(case, monkeypatch, failure):
    def deny(*args, **kwargs):
        pytest.fail("unexpected checkpoint read")

    monkeypatch.setattr(plan, "_MEMBERS", {"unexpected": None})
    real_read = dec3._read
    monkeypatch.setattr(
        dec3, "_read", lambda path, *args: deny() if path is None else real_read(path, *args)
    )
    kwargs = {}
    if failure == "opening":
        case.now = plan.LAST_START
    elif failure == "closure":
        kwargs["data_owner_closed"] = lambda *args: False
    elif failure == "receipt":
        (case.run.input_root / "DATA-READY.json").write_bytes(b"{}")
    elif failure == "key":
        case.rewrite(key=np.array(plan.KEYS[::-1]))
    elif failure == "close":
        case.rewrite(context_close=np.full(17, "2026-12-03T20:59:00+00:00"))
    else:
        case.rewrite(decision_at=np.full(17, plan.ENTRY_OPEN.isoformat()))
    with pytest.raises(ValueError):
        case.launch(**kwargs)
    assert not case.destination.exists()


@pytest.mark.parametrize("failure", ["drift", "late", "order"])
def test_incomplete_forward_consumes_attempt_without_seal(case, monkeypatch, failure):
    calls = []

    def forward(name, arrays):
        calls.append(name)
        keys = plan.KEYS
        if name == "OLD60":
            if failure == "drift":
                case.closed["closed_at"] = dec3.CAPTURE_OPENS_UTC.replace(minute=43).isoformat()
                case.write_data()
            elif failure == "late":
                case.now = plan.HARD_STOP
            else:
                keys = keys[::-1]
        return dict.fromkeys(keys, 1.0)

    monkeypatch.setattr(plan, "_MEMBERS", {})
    monkeypatch.setattr(plan, "_make_forward", lambda members: forward)
    with pytest.raises(ValueError, match="dec4_fixed_half_"):
        case.launch()
    assert calls == ["SELF", "OLD60"]
    assert (case.destination / "ATTEMPT.json").is_file()
    assert not (case.destination / "SEAL.json").exists()
