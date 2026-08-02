"""Run the fixed offline Norgate/KIS D1 bar-conformance falsification."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from thericher_v2.data.norgate_kis_d1_bar_conformance import (
    NORGATE_KIS_D1_BAR_CONFORMANCE_ID,
    build_norgate_kis_d1_bar_conformance_receipt,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_EXPECTED_NORGATE_DATASET_HASH = (
    "sha256:efa1b14ff60c6a107688179617d428546de68ca1d1756c62292e1206e15c58e7"
)
_EXPECTED_NORGATE_MANIFEST_HASH = (
    "sha256:7f30253d035f248889849b7a9a5933cdc41b2f2525b405690ef653ca69a33d45"
)


def main(argv: Sequence[str] | None = None) -> None:
    """Build one redacted, immutable receipt from the fixed offline inputs."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--kis-daily-catalog-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    arguments = parser.parse_args(argv)
    artifact_root = _validated_external_artifact_root(
        arguments.artifact_root,
        repository=_REPOSITORY_ROOT,
    )
    result = build_norgate_kis_d1_bar_conformance_receipt(
        snapshot_dir=arguments.snapshot,
        cache_root=arguments.kis_daily_catalog_root,
        artifact_root=artifact_root,
        expected_norgate_dataset_hash=_EXPECTED_NORGATE_DATASET_HASH,
        expected_norgate_manifest_hash=_EXPECTED_NORGATE_MANIFEST_HASH,
        repo_root=_REPOSITORY_ROOT,
    )
    summary = _safe_summary(
        result,
        artifact_root=artifact_root,
        source_roots=(arguments.snapshot, arguments.kis_daily_catalog_root),
    )
    print(json.dumps(summary, ensure_ascii=True, sort_keys=True))


def _validated_external_artifact_root(root: Path, *, repository: Path) -> Path:
    resolved_root = root.resolve(strict=False)
    resolved_repository = repository.resolve(strict=False)
    if resolved_root.is_relative_to(resolved_repository):
        raise ValueError("D1 conformance receipts must stay outside Git")
    if resolved_root.exists() and (resolved_root.is_symlink() or not resolved_root.is_dir()):
        raise ValueError("D1 conformance receipt root is invalid")
    resolved_root.mkdir(parents=True, exist_ok=True)
    return resolved_root.resolve(strict=False)


def _safe_summary(
    result: object,
    *,
    artifact_root: Path,
    source_roots: tuple[Path, Path],
) -> dict[str, object]:
    status = getattr(result, "status", None)
    receipt_path = getattr(result, "receipt_path", None)
    receipt_sha256 = getattr(result, "receipt_sha256", None)
    safe_payload = getattr(result, "safe_payload", None)
    if (
        not isinstance(status, str)
        or not isinstance(receipt_sha256, str)
        or not callable(safe_payload)
    ):
        raise TypeError("D1 conformance runner requires a typed receipt result")
    if not receipt_sha256.startswith("sha256:"):
        raise ValueError("D1 conformance receipt hash is invalid")

    resolved_receipt = Path(receipt_path).resolve(strict=False)
    if (
        not resolved_receipt.is_relative_to(artifact_root)
        or resolved_receipt.is_symlink()
        or not resolved_receipt.is_file()
    ):
        raise ValueError("D1 conformance receipt location is invalid")

    payload = safe_payload()
    if not isinstance(payload, Mapping) or payload.get("status") != status:
        raise ValueError("D1 conformance receipt payload is invalid")
    _reject_path_disclosure(payload, (*source_roots, artifact_root))
    summary = {
        "campaign_id": NORGATE_KIS_D1_BAR_CONFORMANCE_ID,
        "receipt_sha256": receipt_sha256,
        "status": status,
        "outcome": dict(payload),
    }
    return summary


def _reject_path_disclosure(value: object, roots: tuple[Path, ...]) -> None:
    root_strings = tuple(str(root) for root in roots)
    if isinstance(value, str):
        if any(root and root in value for root in root_strings):
            raise ValueError("D1 conformance receipt payload discloses a path")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_path_disclosure(key, roots)
            _reject_path_disclosure(item, roots)
        return
    if isinstance(value, (tuple, list)):
        for item in value:
            _reject_path_disclosure(item, roots)


if __name__ == "__main__":
    main()
