from __future__ import annotations

from pathlib import Path

import pytest

from thericher_v2.data import (
    norgate_membership,
    norgate_trial_development_panel,
    norgate_trial_raw_d1,
)


def test_external_market_data_mount_under_container_repo_is_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "app"
    market_data_root = repo_root / "market_data"
    snapshot = market_data_root / "snapshot=2026-07-18-norgate-trial-broad-d1-panel-r1"
    snapshot.mkdir(parents=True)

    original_is_mount = Path.is_mount

    def is_market_data_mount(path: Path) -> bool:
        return path.resolve() == market_data_root.resolve() or original_is_mount(path)

    monkeypatch.setattr(Path, "is_mount", is_market_data_mount)

    assert (
        norgate_trial_development_panel._validate_existing_snapshot(
            snapshot,
            market_data_root=market_data_root,
            repo_root=repo_root,
        )
        == snapshot.resolve()
    )
    assert norgate_membership._validate_existing_snapshot(
        snapshot,
        market_data_root=market_data_root,
        repo_root=repo_root,
        require_snapshot_name=False,
    ) == (snapshot.resolve(), market_data_root.resolve())
    assert (
        norgate_trial_raw_d1._validate_existing_snapshot(
            snapshot,
            market_data_root=market_data_root,
            repo_root=repo_root,
            require_snapshot_name=False,
        )
        == snapshot.resolve()
    )


def test_nested_non_mount_market_data_is_still_rejected(tmp_path: Path) -> None:
    repo_root = tmp_path / "app"
    market_data_root = repo_root / "market_data"
    snapshot = market_data_root / "snapshot=2026-07-18-norgate-trial-broad-d1-panel-r1"
    snapshot.mkdir(parents=True)

    with pytest.raises(ValueError, match="outside Git"):
        norgate_trial_development_panel._validate_existing_snapshot(
            snapshot,
            market_data_root=market_data_root,
            repo_root=repo_root,
        )
    with pytest.raises(ValueError, match="outside Git"):
        norgate_membership._validate_existing_snapshot(
            snapshot,
            market_data_root=market_data_root,
            repo_root=repo_root,
            require_snapshot_name=False,
        )
    with pytest.raises(ValueError, match="outside Git"):
        norgate_trial_raw_d1._validate_existing_snapshot(
            snapshot,
            market_data_root=market_data_root,
            repo_root=repo_root,
            require_snapshot_name=False,
        )
