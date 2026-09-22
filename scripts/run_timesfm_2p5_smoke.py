"""Acquire pinned Apache-2.0 TimesFM 2.5 or run an offline synthetic smoke."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import shutil
import signal
import time
import urllib.request
import zipfile
from contextlib import nullcontext
from pathlib import Path

from thericher_v2.research.artifact_paths import ensure_external_artifact_directory
from thericher_v2.research.campaign_registry import (
    register_campaign_outcome,
    register_frozen_campaign,
)
from thericher_v2.research.engine_research_agent import GpuFileLock, resolve_agent_root

REPO = Path(__file__).resolve().parents[1]
MODEL_ID = "google/timesfm-2.5-200m-pytorch"
REVISION = "1d952420fba87f3c6dee4f240de0f1a0fbc790e3"
NAME = "timesfm-2p5-offline-runtime-20260922-v3"
WHEEL = "timesfm-2.0.2-py3-none-any.whl"
WHEEL_URL = (
    "https://files.pythonhosted.org/packages/ce/f2/"
    "3a7ed286070526a0e48487fdfd3b7ca25f90dd0205fd87f4bb27e15ad4fb/" + WHEEL
)
PINS = {
    "README.md": "4c3f16633a3d8b9324904bf004429aced2ee009b84e64effb59a902520cc7f2e",
    "config.json": "cd3315b760d5cc7e278d7afdf41b897031ced888fc6c115bd9b3ac0ea2c47408",
    "model.safetensors": "2f776efe6245e42b24bc4153ffdf61810140210e4bd3b01fb21f7aa779ab6ce8",
    WHEEL: "c7bde94beb1651e1251cdf1e9d09cf6f015e0218d038a4a836a170dc70b08071",
}
IMAGE = "sha256:d6b43213ee3877653e3c1e79c7238fb5caa71241abf238838fa0c3332cf4f039"
LENGTHS = (12, 36, 128, 256)


def encode(payload):
    return (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def file_hash(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("artifact_not_regular")
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def paths(root):
    model = ensure_external_artifact_directory(
        root, REPO, "foundation-models", "timesfm-2.5-200m", REVISION
    )
    output = ensure_external_artifact_directory(root, REPO, "research", NAME)
    return model, output


def verify_files(model):
    for filename, expected in PINS.items():
        if file_hash(model / filename) != expected:
            raise ValueError("public_asset_hash_mismatch")


def prepare(root):
    """Only this explicit phase can download; the inference phases are offline."""
    model, output = paths(root)
    usage = shutil.disk_usage(model)
    missing = sum(1_000_000_000 for f in PINS if not (model / f).exists())
    if (usage.free - missing) / usage.total < 0.15:
        raise ValueError("storage_floor")
    for filename, expected in PINS.items():
        target = model / filename
        if target.exists() or target.is_symlink():
            if file_hash(target) != expected:
                raise ValueError("existing_asset_hash_mismatch")
            continue
        url = WHEEL_URL if filename == WHEEL else (
            f"https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/{filename}"
        )
        # Interrupted bytes remain explicitly partial, never a loadable checkpoint.
        partial = model / (filename + ".partial")
        with partial.open("xb") as handle, urllib.request.urlopen(url, timeout=60) as response:
            total = 0
            started = time.monotonic()
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 1_000_000_000 or time.monotonic() - started > 900:
                    raise ValueError("acquisition_budget")
                handle.write(chunk)
        if file_hash(partial) != expected:
            raise ValueError("download_hash_mismatch")
        partial.rename(target)
    verify_files(model)
    with zipfile.ZipFile(model / WHEEL) as archive:
        license_bytes = archive.read("timesfm-2.0.2.dist-info/licenses/LICENSE")
    if b"Apache License" not in license_bytes or b"Version 2.0" not in license_bytes:
        raise ValueError("runtime_license_mismatch")
    contract = {
        "name": NAME,
        "model_id": MODEL_ID,
        "model_revision": REVISION,
        "files": PINS,
        "weights_license": "Apache-2.0: exact official model-card frontmatter",
        "runtime_license_sha256": digest(license_bytes),
        "runtime": {"timesfm": "2.0.2", "torch": "2.7.0+cu128"},
        "base_image": IMAGE,
        "code_sha256": {
            p: file_hash(REPO / p)
            for p in (
                "scripts/run_timesfm_2p5_smoke.py",
                "src/thericher_v2/research/timesfm_local.py",
            )
        },
        "input": "synthetic sin(arange(n)/7) + arange(n)/100; no market data",
        "context_lengths": LENGTHS,
        "horizon": 12,
        "phase_seconds": 240,
        "strongest_kill": "wrong hash, remote access, device fallback, nonfinite/wrong shape",
        "selection": False,
        "training": False,
        "holdout_access": "none",
        "paper_input": False,
        "accuracy_or_profitability_claim": False,
        "pretraining_market_overlap": "not_verified",
    }
    raw = encode(contract)
    path = output / "contract.json"
    if path.exists():
        if path.is_symlink() or path.read_bytes() != raw:
            raise ValueError("contract_conflict")
    else:
        with path.open("xb") as handle:
            handle.write(raw)
    register_frozen_campaign(
        contract_hash=digest(raw), dataset_hash=digest(encode(contract["input"])),
        split_hash=digest(b"synthetic_no_split"), cost_model_hash=digest(b"no_market_score"),
        trial_family=NAME, holdout_access="none", artifact_root=root, repo_root=REPO,
    )
    return {"status": "prepared", "contract_sha256": digest(raw)}


def run_phase(root, phase):
    import numpy as np
    import torch

    from thericher_v2.research.timesfm_local import forecast_timesfm_2p5

    model, output = paths(root)
    contract_path = output / "contract.json"
    if contract_path.is_symlink():
        raise ValueError("contract_link")
    raw = contract_path.read_bytes()
    contract = json.loads(raw)
    if (
        contract["files"] != PINS or contract["name"] != NAME
        or contract.get("model_id") != MODEL_ID or contract.get("model_revision") != REVISION
    ):
        raise ValueError("contract_identity")
    expected_sources = {
        "scripts/run_timesfm_2p5_smoke.py", "src/thericher_v2/research/timesfm_local.py"
    }
    source_hashes = contract.get("code_sha256")
    if not isinstance(source_hashes, dict) or set(source_hashes) != expected_sources:
        raise ValueError("code_changed")
    for path, expected in source_hashes.items():
        if file_hash(REPO / path) != expected:
            raise ValueError("code_changed")
    verify_files(model)
    if importlib.metadata.version("timesfm") != "2.0.2" or torch.__version__ != "2.7.0+cu128":
        raise ValueError("runtime_changed")
    if phase == "cuda":
        cpu = json.loads((output / "cpu.json").read_bytes())
        if cpu["status"] != "complete" or cpu["contract_sha256"] != digest(raw):
            raise ValueError("matching_cpu_missing")
    target = output / f"{phase}.json"
    if target.exists() or target.is_symlink():
        raise ValueError("phase_already_recorded")
    torch.set_num_threads(2)
    lock = GpuFileLock(resolve_agent_root(root) / "locks/gpu.lock") if phase == "cuda" else (
        nullcontext()
    )
    with lock:
        started = time.monotonic()
        contexts = [np.sin(np.arange(n) / 7) + np.arange(n) / 100 for n in LENGTHS]
        points, quantiles = forecast_timesfm_2p5(
            model_directory=model,
            expected_sha256={k: PINS[k] for k in ("config.json", "model.safetensors")},
            contexts=contexts, horizon=12, device=phase,
        )
        result = {
            "status": "complete", "phase": phase, "contract_sha256": digest(raw),
            "point_shape": list(points.shape),
            "quantile_shape": list(quantiles.shape),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "market_data_accessed": False, "predictions_retained": False,
            "training": False, "paper_input": False,
            "runtime": {k: importlib.metadata.version(k) for k in (
                "torch", "numpy", "timesfm", "safetensors", "huggingface-hub"
            )},
        }
        if phase == "cuda":
            result["gpu"] = torch.cuda.get_device_name(0)
            result["peak_allocated_bytes"] = torch.cuda.max_memory_allocated(0)
        with target.open("xb") as handle:
            handle.write(encode(result))
    if phase == "cuda":
        register_campaign_outcome(
            contract_hash=digest(raw), outcome_class="non_promoting_completed",
            outcome_reference_sha256=digest(encode(result)), artifact_root=root, repo_root=REPO,
        )
    return result


def interrupt(*_):
    raise KeyboardInterrupt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--phase", choices=("cpu", "cuda"))
    args = parser.parse_args(argv)
    signal.signal(signal.SIGTERM, interrupt)
    try:
        result = prepare(args.artifact_root) if args.prepare else run_phase(
            args.artifact_root, args.phase
        )
    except (Exception, KeyboardInterrupt):
        result = {"status": "unavailable", "raw_error_suppressed": True}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in ("prepared", "complete") else 1


if __name__ == "__main__":
    raise SystemExit(main())
