"""Native CPU continuation and refusal checks for next fixed50 training."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from thericher_v2.research import training_checkpoint as cp

np = pytest.importorskip("numpy")
torch = pytest.importorskip("torch")
IDENTITY = {
    "contract_sha256": "1" * 64,
    "source_sha256": "2" * 64,
    "batch_order_sha256": "3" * 64,
    "active_cap": "7200",
    "attempt": "one",
}


@pytest.fixture(autouse=True)
def cpu_state():
    state, threads = torch.get_rng_state(), torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_rng_state(state)
    torch.set_num_threads(threads)


def objects():
    model = torch.nn.Sequential(
        torch.nn.Linear(3, 5), torch.nn.Tanh(), torch.nn.Dropout(0.3), torch.nn.Linear(5, 1)
    ).double()
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.03, amsgrad=True)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=0, factor=0.5)
    return dict(
        model=model,
        optimizer=optimizer,
        scheduler=scheduler,
        numpy_rng=np.random.default_rng(109),
        identity=IDENTITY,
    )


def epochs(items, count):
    model, optimizer, scheduler = (items[k] for k in ("model", "optimizer", "scheduler"))
    x = torch.arange(24, dtype=torch.float64).reshape(8, 3) / 24
    result = []
    for _ in range(count):
        for start in (0, 4):
            noise = items["numpy_rng"].normal(scale=0.001)
            optimizer.zero_grad(set_to_none=True)
            loss = (model(x[start : start + 4]) - noise).square().mean()
            result.append(loss.item())
            loss.backward()
            optimizer.step()
        scheduler.step(1.0)
    return result


def saved(tmp_path):
    torch.manual_seed(2026)
    items = objects()
    epochs(items, 2)
    path = tmp_path / "epoch-2"
    cp.save_epoch_checkpoint(path, **items, epoch=2, best=1.0, counters={"optimizer_steps": 4})
    return path, items


def manifest_edit(path, change):
    manifest = json.loads((path / "manifest.json").read_bytes())
    change(manifest)
    value = json.dumps(manifest, sort_keys=True).encode()
    (path / "manifest.json").write_bytes(value)
    (path / "COMMITTED").write_text(hashlib.sha256(value).hexdigest(), encoding="ascii")


def test_native_bit_exact_uninterrupted_vs_resume(tmp_path):
    torch.manual_seed(2026)
    full = objects()
    losses = epochs(full, 5)
    final = {k: v.detach().clone() for k, v in full["model"].state_dict().items()}
    expected_torch = torch.rand(8)
    expected_numpy = full["numpy_rng"].random(8)
    expected_scheduler = full["scheduler"].state_dict()
    path, branch = saved(tmp_path)
    restarted = objects()
    info = cp.restore_epoch_checkpoint(path, **restarted)
    assert (info.epoch, info.best, info.counters) == (2, 1.0, {"optimizer_steps": 4})
    assert epochs(restarted, 3) == losses[4:]
    for key, value in restarted["model"].state_dict().items():
        assert torch.equal(value, final[key])
    assert torch.equal(torch.rand(8), expected_torch)
    assert np.array_equal(restarted["numpy_rng"].random(8), expected_numpy)
    assert restarted["scheduler"].state_dict() == expected_scheduler
    assert branch["scheduler"].get_last_lr() != full["scheduler"].get_last_lr()


def test_restore_twice_rewinds_only_named_state(tmp_path):
    path, _ = saved(tmp_path)
    fresh = objects()
    cp.restore_epoch_checkpoint(path, **fresh)
    first = epochs(fresh, 1)
    first_rng = torch.rand(3)
    cp.restore_epoch_checkpoint(path, **fresh)
    assert epochs(fresh, 1) == first
    assert torch.equal(torch.rand(3), first_rng)


@pytest.mark.parametrize(
    "field", ["contract_sha256", "source_sha256", "batch_order_sha256", "active_cap", "attempt"]
)
def test_identity_and_cap_changes_denied(tmp_path, field):
    path, _ = saved(tmp_path)
    fresh = objects()
    fresh["identity"] = dict(IDENTITY, **{field: "9" * 64})
    before = torch.get_rng_state()
    with pytest.raises(ValueError, match="identity"):
        cp.restore_epoch_checkpoint(path, **fresh)
    assert torch.equal(before, torch.get_rng_state())


@pytest.mark.parametrize(
    "damage",
    ["missing_commit", "truncated_npz", "manifest_hash", "runtime", "shape", "epoch", "oversized"],
)
def test_torn_and_mismatched_state_denied(tmp_path, damage):
    path, _ = saved(tmp_path)
    if damage == "missing_commit":
        (path / "COMMITTED").unlink()
    elif damage == "truncated_npz":
        (path / "arrays.npz").write_bytes(b"PK")
    elif damage == "manifest_hash":
        (path / "manifest.json").write_bytes(b"{}")
    elif damage == "runtime":
        manifest_edit(path, lambda m: m["runtime"].update(torch="different"))
    elif damage == "shape":
        manifest_edit(path, lambda m: next(iter(m["arrays"].values())).update(shape=[999]))
    elif damage == "epoch":

        def change(m):
            for key, value in m["tree"]["dict"]:
                if key == "epoch":
                    m["tree"]["dict"].remove([key, value])
                    m["tree"]["dict"].append([key, 9])
                    break

        manifest_edit(path, change)
    else:
        manifest_edit(path, lambda m: next(iter(m["arrays"].values())).update(shape=[2**60]))
    with pytest.raises((ValueError, FileNotFoundError)):
        cp.restore_epoch_checkpoint(path, **objects())


def test_optimizer_parameter_order_denied(tmp_path):
    path, _ = saved(tmp_path)
    fresh = objects()
    fresh["optimizer"] = torch.optim.AdamW(
        reversed(list(fresh["model"].parameters())), lr=0.03, amsgrad=True
    )
    fresh["scheduler"] = torch.optim.lr_scheduler.ReduceLROnPlateau(
        fresh["optimizer"], patience=0, factor=0.5
    )
    with pytest.raises(ValueError, match="runtime"):
        cp.restore_epoch_checkpoint(path, **fresh)


def test_no_overwrite_or_repo_artifact(tmp_path):
    path, items = saved(tmp_path)
    before = (path / "COMMITTED").read_bytes()
    with pytest.raises(FileExistsError):
        cp.save_epoch_checkpoint(path, **items, epoch=2, best=1.0, counters={"optimizer_steps": 4})
    assert (path / "COMMITTED").read_bytes() == before
    with pytest.raises(ValueError, match="outside"):
        cp.save_epoch_checkpoint(
            tmp_path / "denied",
            **items,
            epoch=2,
            best=1.0,
            counters={"optimizer_steps": 4},
            repo_root=tmp_path,
        )
    assert not (tmp_path / "denied").exists()


def test_counter_mismatch_rejected_before_publication(tmp_path):
    items = objects()
    epochs(items, 1)
    with pytest.raises(ValueError, match="step_counter"):
        cp.save_epoch_checkpoint(
            tmp_path / "bad", **items, epoch=1, best=1.0, counters={"optimizer_steps": 99}
        )
    assert not (tmp_path / "bad").exists()


@pytest.mark.parametrize("device", ["cuda:0", "cuda:999", "meta", "mps"])
def test_malformed_device_refused_before_unpack_or_allocation(tmp_path, monkeypatch, device):
    path, _ = saved(tmp_path)
    manifest_edit(path, lambda m: next(iter(m["arrays"].values())).update(device=device))
    fresh = objects()

    def forbidden(*args, **kwargs):
        raise AssertionError("must reject device before unpack/transfer")

    monkeypatch.setattr(cp._Codec, "unpack", forbidden)
    monkeypatch.setattr(torch.Tensor, "to", forbidden)
    with pytest.raises(ValueError, match="device_denied"):
        cp.restore_epoch_checkpoint(path, **fresh)


def test_cuda_visible_index_validation_without_cuda_calls():
    cp._check_devices({"a": {"device": "cpu"}, "b": {"device": "cuda:1"}}, 2)
    for device in ("cuda:2", "cuda:-1", "cuda", "meta", "mps"):
        with pytest.raises(ValueError, match="device_denied"):
            cp._check_devices({"a": {"device": device}}, 2)


def test_failed_commit_stays_unusable(tmp_path, monkeypatch):
    items = objects()
    epochs(items, 1)

    def interrupted(*args):
        raise OSError("simulated commit interruption")

    monkeypatch.setattr(cp.os, "link", interrupted)
    path = tmp_path / "incomplete"
    with pytest.raises(OSError, match="interruption"):
        cp.save_epoch_checkpoint(path, **items, epoch=1, best=1.0, counters={"optimizer_steps": 2})
    assert (path / "arrays.npz").exists()
    assert not (path / "COMMITTED").exists()
    with pytest.raises(FileNotFoundError):
        cp.restore_epoch_checkpoint(path, **objects())


def test_missing_optimizer_moments_denied(tmp_path):
    path, _ = saved(tmp_path)

    def change(manifest):
        for key, value in manifest["tree"]["dict"]:
            if key == "optimizer":
                for field, state in value["dict"]:
                    if field == "state":
                        state["dict"].clear()

    manifest_edit(path, change)
    with pytest.raises(ValueError, match="state_completeness"):
        cp.restore_epoch_checkpoint(path, **objects())


def test_lazy_torch_import():
    src = str(Path(cp.__file__).resolve().parents[2])
    env = {
        k: os.environ[k] for k in ("SystemRoot", "WINDIR", "PATH", "TEMP", "TMP") if k in os.environ
    }
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-I",
            "-c",
            f"import sys;sys.path.insert(0,{src!r});"
            "import thericher_v2.research.training_checkpoint;assert 'torch' not in sys.modules;"
            "assert 'numpy' not in sys.modules",
        ],
        env=env,
        capture_output=True,
        timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert result.returncode == 0
