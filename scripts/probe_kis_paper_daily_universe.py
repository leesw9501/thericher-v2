"""Run the finite NAS-only KIS Paper daily-universe capability probe."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.data.official_symbol_directory_nas_probe import (
    build_official_symbol_directory_nas_probe_registry,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataClient,
    KisPaperMarketDataError,
    load_kis_paper_market_data_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY,
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)
from thericher_v2.execution.kis_paper_daily_universe_probe import (
    KIS_PAPER_DAILY_UNIVERSE_PROBE_CACHE_ROOT,
    KIS_PAPER_DAILY_UNIVERSE_PROBE_EVIDENCE_ROOT,
    KIS_PAPER_DAILY_UNIVERSE_PROBE_MAX_PAGES_PER_TARGET,
    UrllibKisPaperDailyUniverseProbeTransport,
    run_kis_paper_daily_universe_probe,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_OFFICIAL_DIRECTORY_ROOT = Path(
    "D:/market_data/us_equities/official_symbol_directory/raw/snapshot=2026-07-18"
)
_MARKET_DATA_ROOT = Path("D:/market_data")
_MODEL_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    dotenv_path: Path = _REPOSITORY_ROOT / ".env",
) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--anchor-date")
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=KIS_PAPER_DAILY_UNIVERSE_PROBE_CACHE_ROOT,
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=KIS_PAPER_DAILY_UNIVERSE_PROBE_EVIDENCE_ROOT,
    )
    parser.add_argument("--directory-root", type=Path, default=_OFFICIAL_DIRECTORY_ROOT)
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "not_executed", "reason": "execute_flag_required"}))
        return

    cache_root = Path(args.cache_root)
    artifact_root = Path(args.artifact_root)
    directory_root = Path(args.directory_root)
    if not _is_within(cache_root, _MARKET_DATA_ROOT) or not _is_within(
        artifact_root,
        _MODEL_ARTIFACT_ROOT,
    ):
        print(json.dumps({"status": "not_executed", "reason": "storage_root_required"}))
        return
    observed_at = clock()
    try:
        registry = build_official_symbol_directory_nas_probe_registry(
            manifest_path=directory_root / "manifest.json",
            nasdaq_listing_path=directory_root / "nasdaqlisted.txt",
        )
        request_gate = KisPaperMarketDataRateGate(
            control_root=_shared_control_root(cache_root)
        )
        token_start_gate = KisPaperMarketDataTokenStartGate(
            control_root=_shared_control_root(cache_root)
        )
        client = KisPaperMarketDataClient(
            config=load_kis_paper_market_data_config(dotenv_path),
            transport=UrllibKisPaperDailyUniverseProbeTransport(
                registry=registry,
                request_gate=request_gate,
                token_start_gate=token_start_gate,
            ),
            max_daily_page_attempts=(
                KIS_PAPER_DAILY_UNIVERSE_PROBE_MAX_PAGES_PER_TARGET * len(registry.targets)
            ),
        )
        result = run_kis_paper_daily_universe_probe(
            client,
            registry=registry,
            cache_root=cache_root,
            artifact_root=artifact_root,
            code_revision=_current_code_revision(_REPOSITORY_ROOT),
            observed_at=observed_at,
            anchor_date=args.anchor_date,
        )
    except (KisPaperMarketDataError, OSError, ValueError):
        print(json.dumps({"status": "unavailable", "reason": "daily_universe_probe_unavailable"}))
        return

    print(
        json.dumps(
            {
                "status": "completed",
                "anchor_date": result.anchor_date,
                "registry_sha256": result.registry_sha256,
                "target_states": [
                    {
                        "target_key": state.target_key,
                        "classification": state.classification,
                        "recovery": state.recovery,
                        "reason": state.reason,
                    }
                    for state in result.target_states
                ],
                "requests": {
                    "token_attempts": result.call_counts.token_attempts,
                    "minute_page_attempts": result.call_counts.minute_page_attempts,
                    "daily_page_attempts": result.call_counts.daily_page_attempts,
                },
                "recovery": result.recovery,
                "cache_manifest_sha256": result.manifest_sha256,
                "evidence_sha256": result.evidence_sha256,
            },
            sort_keys=True,
        )
    )


def _shared_control_root(cache_root: Path) -> Path:
    """Share the existing KIS ingress controls with the private cache lanes."""

    root = Path(cache_root)
    if root.name == "v1" and root.parent.name == "daily-universe-probe":
        return root.parent.parent / KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY
    return root.parent / KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _current_code_revision(repo_root: Path) -> str:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "diff", "--quiet"],
            cwd=repo_root,
            check=False,
            capture_output=True,
        ).returncode != 0
    except (OSError, subprocess.SubprocessError):
        return "git:unavailable"
    return f"git:{revision}" + ("+dirty" if dirty else "")


if __name__ == "__main__":
    main()
