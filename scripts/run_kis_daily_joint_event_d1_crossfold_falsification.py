"""Write one fixed, offline D1 cross-fold falsification artifact."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.kis_daily_joint_event_d1_crossfold_falsification import (
    run_kis_daily_joint_event_d1_crossfold_falsification,
)
from thericher_v2.kis_daily_joint_event_window_contract import DEFAULT_MODEL_ARTIFACT_ROOT

_REPO_ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_MODEL_ARTIFACT_ROOT)
    args = parser.parse_args(argv)

    run = run_kis_daily_joint_event_d1_crossfold_falsification(
        artifact_root=Path(args.artifact_root),
        run_label=str(args.run_label),
        repo_root=_REPO_ROOT,
    )
    print(run.summary_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
