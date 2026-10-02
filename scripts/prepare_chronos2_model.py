"""Acquire immutable official Chronos-2 bytes/source evidence; never run inference."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
import urllib.request
import warnings
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.research.chronos2_local import (
    CHRONOS2_CHECKPOINT_DATE,
    CHRONOS2_IMAGE,
    CHRONOS2_MODEL_ID,
    CHRONOS2_REPO_COMMIT,
    CHRONOS2_REVISION,
    CHRONOS2_SHA256,
    CHRONOS2_SIZES,
    PINNED_RUNTIME,
    _unlinked_stat,
    _verified_directory,
)

_CARD_REVISION = "29ec3766d36d6f73f0696f85560a422f50e8498c"
_WHEEL_NAME = "chronos_forecasting-2.2.2-py3-none-any.whl"
_WHEEL_SHA256 = "1ff681451361f8c0a5fd6920cc1a0d8139f46c85f77a7d6d34fd554390bc76d9"
_WHEEL_URL = (
    "https://files.pythonhosted.org/packages/18/d9/"
    "ca38acd7a34c9ee6ed8bd05c2824d3fcc789a93ebdb185e56f81b89fa783/" + _WHEEL_NAME
)
_SOURCE_FILES = (
    "LICENSE",
    "NOTICE",
    "README.md",
    "pyproject.toml",
    "src/chronos/chronos2/config.py",
    "src/chronos/chronos2/model.py",
    "src/chronos/chronos2/dataset.py",
    "src/chronos/chronos2/pipeline.py",
)


def _hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _directory(path: Path) -> None:
    for parent in (*reversed(path.parents), path):
        if parent.exists() or parent.is_symlink():
            _unlinked_stat(parent)
    path.mkdir(parents=True, exist_ok=True)
    for parent in (*reversed(path.parents), path):
        if not parent.is_dir():
            raise ValueError("Asset parent is not a directory")
        _unlinked_stat(parent)


def _storage_floor(path: Path, projected: int) -> None:
    usage = shutil.disk_usage(path)
    ratio = (usage.free - projected) / usage.total
    if ratio < 0.15:
        raise ValueError("Acquisition would cross the 15 percent free-space floor")
    if ratio < 0.20:
        warnings.warn("Projected asset storage is below 20 percent free", stacklevel=2)


def _download(url: str, path: Path, limit: int, digest: str | None = None) -> dict:
    _directory(path.parent)
    if path.exists():
        _unlinked_stat(path)
        if not path.is_file() or path.stat().st_size > limit:
            raise ValueError("Existing source asset is invalid")
        if digest is not None and _hash(path) != digest:
            raise ValueError("Existing immutable asset SHA256 mismatch")
    else:
        _storage_floor(path.parent, limit)
        partial = path.with_name(path.name + ".partial")
        started = time.monotonic()
        created = False
        # No HF client, implicit token, login, proxy authentication, or retries.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with partial.open("xb") as out:
                created = True
                request = urllib.request.Request(url, headers={"User-Agent": "thericher-research"})
                with opener.open(request, timeout=30) as response:
                    size = 0
                    while block := response.read(1024 * 1024):
                        size += len(block)
                        if size > limit or time.monotonic() - started > 600:
                            raise ValueError("Source acquisition exceeded its finite bound")
                        out.write(block)
            if digest is not None and _hash(partial) != digest:
                raise ValueError("Downloaded asset SHA256 mismatch")
            if path.exists():
                raise ValueError("Concurrent source acquisition conflicts")
            partial.rename(path)
        except Exception:
            # Delete only the exact regular partial created by this invocation.
            # A pre-existing partial is retained for explicit recovery.
            if created and partial.exists():
                _unlinked_stat(partial)
                partial.unlink()
            raise
    return {"url": url, "path": str(path), "sha256": _hash(path), "bytes": path.stat().st_size}


def prepare(artifact_root: Path) -> dict:
    """One serialized acquisition, source snapshots and a hash-bound JSON receipt."""
    root = artifact_root.absolute()
    repo = Path(__file__).resolve().parents[1]
    if ".." in root.parts or root.anchor.startswith(("\\\\", "//")) or root.is_relative_to(repo):
        raise ValueError("Chronos-2 assets must be external, local and unlinked")
    _directory(root)
    _storage_floor(root, CHRONOS2_SIZES["model.safetensors"] + 16 * 1024 * 1024)
    model = root / "foundation-models" / "chronos-2" / CHRONOS2_REVISION
    source = root / "research" / "engine-source-retrieval" / "chronos2-runtime-20261002-v1"
    wheels = root / "wheel-cache" / "chronos2-2.2.2"
    _directory(source)
    receipt_path = source / "source-retrieval.json"
    if receipt_path.exists():
        _unlinked_stat(receipt_path)
        previous = json.loads(receipt_path.read_text(encoding="utf-8"))
        _verified_directory(model)
        for item in previous["assets"]:
            path = Path(item["path"])
            _unlinked_stat(path)
            if _hash(path) != item["sha256"]:
                raise ValueError("Immutable source receipt readback mismatch")
        return previous
    assets = []

    def acquire(url: str, path: Path, limit: int = 1024 * 1024, digest: str | None = None):
        record = _download(url, path, limit, digest)
        assets.append(record)
        return path

    base = "https://huggingface.co/amazon/chronos-2"
    metadata_path = acquire(
        f"https://huggingface.co/api/models/amazon/chronos-2/revision/{CHRONOS2_REVISION}?blobs=true",
        source / "checkpoint-api.json",
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if (
        metadata["sha"] != CHRONOS2_REVISION
        or datetime.fromisoformat(metadata["lastModified"])
        != datetime.fromisoformat(CHRONOS2_CHECKPOINT_DATE)
        or metadata["cardData"]["license"] != "apache-2.0"
        or metadata.get("gated") is not False
    ):
        raise ValueError("Official checkpoint identity/date/license is not the frozen source")
    weights = next(
        item for item in metadata["siblings"] if item["rfilename"] == "model.safetensors"
    )
    if weights["lfs"]["sha256"] != CHRONOS2_SHA256["model.safetensors"]:
        raise ValueError("Official LFS identity mismatch")
    acquire(
        "https://huggingface.co/api/models/amazon/chronos-2/commits/main",
        source / "checkpoint-history.json",
    )
    acquire(f"{base}/resolve/{_CARD_REVISION}/README.md", source / "model-card.md")
    github = f"https://raw.githubusercontent.com/amazon-science/chronos-forecasting/{CHRONOS2_REPO_COMMIT}"
    for name in _SOURCE_FILES:
        acquire(f"{github}/{name}", source / name)
    acquire(
        f"https://api.github.com/repos/amazon-science/chronos-forecasting/commits/{CHRONOS2_REPO_COMMIT}",
        source / "repo-commit.json",
    )
    license_text = (source / "LICENSE").read_text(encoding="utf-8")
    if "Apache License" not in license_text or "Version 2.0, January 2004" not in license_text:
        raise ValueError("Official repository license is not Apache-2.0")
    for name, digest in CHRONOS2_SHA256.items():
        acquire(
            f"{base}/resolve/{CHRONOS2_REVISION}/{name}", model / name, CHRONOS2_SIZES[name], digest
        )
    acquire(f"{github}/LICENSE", model / "LICENSE", digest=_hash(source / "LICENSE"))
    _verified_directory(model)
    wheel = acquire(_WHEEL_URL, wheels / _WHEEL_NAME, 72663, _WHEEL_SHA256)
    acquire("https://pypi.org/pypi/chronos-forecasting/2.2.2/json", source / "wheel-pypi.json")
    with zipfile.ZipFile(wheel) as archive:
        for name in _SOURCE_FILES:
            if name.startswith("src/") and archive.read(name[4:]) != (source / name).read_bytes():
                raise ValueError("Published wheel differs from the pinned official runtime source")
    receipt = {
        "kind": "chronos2_offline_runtime_source_receipt",
        "retrieved_at": datetime.now(UTC).isoformat(),
        "engine_loop": "feature/model research",
        "model_id": CHRONOS2_MODEL_ID,
        "model_revision": CHRONOS2_REVISION,
        "checkpoint_date": CHRONOS2_CHECKPOINT_DATE,
        "repo_commit": CHRONOS2_REPO_COMMIT,
        "repo_commit_date": "2025-12-17T18:12:57Z",
        "model_card_revision": _CARD_REVISION,
        "model_license": "apache-2.0 (official checkpoint card metadata)",
        "code_license": "Apache-2.0",
        "license_verbatim_path": str(source / "LICENSE"),
        "model_directory": str(model),
        "model_sha256": CHRONOS2_SHA256,
        "existing_image": CHRONOS2_IMAGE,
        "runtime_versions": PINNED_RUNTIME,
        "dependency_decision": (
            "Use existing image; wheel cached inertly for source/hash attestation"
        ),
        "checkpoint_before_2026_targets": True,
        "temporal_interpretation": "Trusted official dated hash predates January-July 2026 targets",
        "pretraining_corpus_period": "not_disclosed",
        "pretraining_instrument_scope": "not_disclosed",
        "stated_training_sources": [
            "Chronos Datasets subset",
            "GIFT-Eval Pretrain subset",
            "synthetic",
        ],
        "limits": [
            "Earlier-context/instrument overlap not independently verified",
            "Revised seen-data remains development, not independent holdout or Paper qualification",
            "Cross-series attention is restricted to exactly one aligned origin trio",
            "No market evaluation, GPU campaign, training, KIS, credentials, or public service",
        ],
        "claude_review": (
            "review_unavailable: actual Claude CLI weekly limit until 2026-10-04; "
            "no substantive verdict received"
        ),
        "claude_review_evidence": (
            "Main orchestrator's actual CLI observation in 2026-10-02 handoff"
        ),
        "recovery_class": "complete",
        "assets": assets,
    }
    with receipt_path.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact-root", type=Path, default=Path("D:/thericher-v2/model-artifacts")
    )
    args = parser.parse_args()
    receipt = prepare(args.artifact_root)
    print(
        json.dumps(
            {
                "model_directory": receipt["model_directory"],
                "model_sha256": receipt["model_sha256"],
                "recovery_class": "complete",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
