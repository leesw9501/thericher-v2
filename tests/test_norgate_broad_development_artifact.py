from __future__ import annotations

import json
import socket
import subprocess
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.norgate_broad_development_artifact import (
    build_norgate_broad_development_feature_artifact,
    load_verified_norgate_broad_development_feature_artifact,
    verify_norgate_broad_development_feature_artifact,
)
from thericher_v2.data.norgate_membership import build_norgate_sp500_membership_snapshot
from thericher_v2.data.norgate_trial_development_panel import (
    build_norgate_trial_development_panel_snapshot,
)
from thericher_v2.data.norgate_trial_raw_d1 import (
    NorgateCapitalEventEvidence,
    build_norgate_trial_raw_d1_snapshot,
)

try:
    import numpy as np
except ImportError:
    pytestmark = pytest.mark.skip(reason="requires the research NumPy extra")

_START = date(2024, 1, 2)
_SESSIONS = tuple(_START + timedelta(days=index) for index in range(483))
_END = _SESSIONS[-1]
_CANDIDATES = ("AAA", "BBB")


class _Dtype:
    def __init__(self, names: tuple[str, ...]) -> None:
        self.names = names


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.dtype = _Dtype(("Date", "Index Constituent"))
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _MembershipClient:
    class PaddingType:
        NONE = "none"

    __version__ = "test-version"

    def watchlist_symbols(self, _watchlist: str) -> list[str]:
        return list(_CANDIDATES)

    def index_constituent_timeseries(
        self, _symbol: str, _index_name: str, **_kwargs: Any
    ) -> _Rows:
        return _Rows(
            [
                {"Date": session.isoformat(), "Index Constituent": 1}
                for session in _SESSIONS
            ]
        )


def test_builds_attested_external_features_without_network_or_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, repo, panel, artifact_root = _panel_fixture(tmp_path, non_positive_open_index=150)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("feature artifact crossed a forbidden boundary")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("feature artifact must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(Path, "read_text", guard_read_text)
    result = build_norgate_broad_development_feature_artifact(
        panel,
        artifact_root=artifact_root,
        market_data_root=root,
        repo_root=repo,
    )

    assert result.artifact_dir.is_relative_to(artifact_root)
    assert result.feature_array.shape == (922, 20)
    assert result.feature_array.dtype == np.float32
    assert result.contract["row_counts"] == {
        "development": 600,
        "purge": 4,
        "validation": 318,
    }
    assert result.contract["scope"] == {
        "engineering_cuda_exploration_eligible": True,
        "point_in_time_eligible": False,
        "ranking_eligible": False,
        "sealed_holdout_eligible": False,
        "campaign_eligible": False,
        "model_eligible": False,
        "model_promotion_eligible": False,
        "gpu_eligible": False,
        "paper_trading_eligible": False,
        "pnl_eligible": False,
        "profitability_eligible": False,
    }
    assert result.contract["transform"]["feature_source_index_range"] == "t-20..t"
    assert result.contract["temporal_groups"]["development"]["decision_date_count"] == 300
    assert result.contract["temporal_groups"]["validation"]["decision_date_count"] == 159
    assert result.decision_indices.min() == 20
    assert result.decision_indices.max() == 480
    assert np.array_equal(result.source_start_indices, result.decision_indices - 20)
    assert np.array_equal(result.source_end_indices, result.decision_indices)
    assert np.array_equal(result.entry_indices, result.decision_indices + 1)
    assert np.array_equal(result.exit_indices, result.decision_indices + 2)
    assert np.array_equal(result.source_end_timestamps_ns, result.decision_timestamps_ns)
    canonical_order = np.lexsort((result.symbol_ranks, result.decision_indices))
    assert np.array_equal(canonical_order, np.arange(result.feature_array.shape[0]))
    assert set(result.label_array.tolist()) == {0, 1}
    non_positive_label = (result.symbol_ranks == 1) & (result.decision_indices == 148)
    assert result.label_array[non_positive_label].tolist() == [0]

    parent_manifest = json.loads((panel / "manifest.json").read_text(encoding="utf-8"))
    assert parent_manifest["scope"]["model_eligible"] is False
    assert parent_manifest["scope"]["gpu_eligible"] is False
    loaded = load_verified_norgate_broad_development_feature_artifact(
        result.artifact_dir,
        artifact_root=artifact_root,
        market_data_root=root,
        repo_root=repo,
    )
    assert loaded.contract_hash == result.contract_hash
    assert loaded.artifact_hash == result.artifact_hash
    assert loaded.parent_dataset_hash == result.parent_dataset_hash
    assert loaded.parent_manifest_hash == result.parent_manifest_hash


def test_excludes_the_fixed_raw_discontinuity_window(tmp_path: Path) -> None:
    root, repo, panel, artifact_root = _panel_fixture(tmp_path, discontinuity_index=100)
    result = build_norgate_broad_development_feature_artifact(
        panel,
        artifact_root=artifact_root,
        market_data_root=root,
        repo_root=repo,
    )

    first_rank = result.symbol_ranks == 1
    excluded_decisions = set(range(98, 121))
    assert result.feature_array.shape == (899, 20)
    assert not (set(result.decision_indices[first_rank].tolist()) & excluded_decisions)
    assert set(result.decision_indices[~first_rank].tolist()) == set(range(20, 481))
    assert result.contract["discontinuity_conditioning"]["checked_index_range"] == "t-20..t+2"
    assert result.contract["inherited_boundary_limitations"] == {
        "raw_discontinuity_index_zero": "not_computable_without_prior_panel_close"
    }


def test_rejects_feature_and_parent_scope_tampering(tmp_path: Path) -> None:
    root, repo, panel, artifact_root = _panel_fixture(tmp_path)
    result = build_norgate_broad_development_feature_artifact(
        panel,
        artifact_root=artifact_root,
        market_data_root=root,
        repo_root=repo,
    )

    feature_path = result.artifact_dir / "features.npz"
    original_feature_bytes = feature_path.read_bytes()
    feature_path.write_bytes(original_feature_bytes + b"tampered")
    with pytest.raises(ValueError, match="feature artifact features hash mismatch"):
        verify_norgate_broad_development_feature_artifact(
            result.artifact_dir,
            artifact_root=artifact_root,
            market_data_root=root,
            repo_root=repo,
        )

    feature_path.write_bytes(original_feature_bytes)
    manifest_path = panel / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["scope"]["gpu_eligible"] = True
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="scope is invalid"):
        load_verified_norgate_broad_development_feature_artifact(
            result.artifact_dir,
            artifact_root=artifact_root,
            market_data_root=root,
            repo_root=repo,
        )


def test_rejects_repository_output_and_wrong_external_root(tmp_path: Path) -> None:
    root, repo, panel, artifact_root = _panel_fixture(tmp_path)
    with pytest.raises(ValueError, match="outside Git workspace"):
        build_norgate_broad_development_feature_artifact(
            panel,
            artifact_root=repo,
            market_data_root=root,
            repo_root=repo,
        )

    result = build_norgate_broad_development_feature_artifact(
        panel,
        artifact_root=artifact_root,
        market_data_root=root,
        repo_root=repo,
    )
    wrong_root = tmp_path / "other-artifacts"
    wrong_root.mkdir()
    with pytest.raises(ValueError, match="under artifact root"):
        verify_norgate_broad_development_feature_artifact(
            result.artifact_dir,
            artifact_root=wrong_root,
            market_data_root=root,
            repo_root=repo,
        )


def _panel_fixture(
    tmp_path: Path,
    *,
    discontinuity_index: int | None = None,
    non_positive_open_index: int | None = None,
) -> tuple[Path, Path, Path, Path]:
    root = tmp_path / "market-data"
    root.mkdir(parents=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    artifact_root.mkdir()
    membership = root / "membership" / "snapshot=2026-07-19-norgate-sp500-membership-r1"
    build_norgate_sp500_membership_snapshot(
        destination=membership,
        requested_start=_START,
        requested_end=_END,
        retrieved_at_utc=datetime(2026, 7, 19, tzinfo=UTC),
        expected_candidate_count=len(_CANDIDATES),
        client_loader=_MembershipClient,
        market_data_root=root,
        repo_root=repo,
        platform_name="win32",
        disk_usage=lambda _path: SimpleNamespace(total=100, free=50),
    )
    calendar = root / "calendar" / "snapshot=2026-07-19-norgate-trial-raw-d1-r2"
    build_norgate_trial_raw_d1_snapshot(
        destination=calendar,
        requested_start=_START,
        requested_end=_END,
        retrieved_at_utc=datetime(2026, 7, 19, tzinfo=UTC),
        norgate_bars=lambda symbol, _start, _end: _bars(symbol),
        capital_event_evidence=lambda _symbol, _start, _end: _events(),
        norgate_package_version="test-version",
        market_data_root=root,
        repo_root=repo,
        platform_name="win32",
        disk_usage=lambda _path: SimpleNamespace(total=100, free=50),
    )
    panel = root / "panel" / "snapshot=2026-07-19-norgate-trial-broad-d1-panel-r1"
    build_norgate_trial_development_panel_snapshot(
        destination=panel,
        membership_snapshot=membership,
        calendar_snapshot=calendar,
        retrieved_at_utc=datetime(2026, 7, 19, tzinfo=UTC),
        load_bars=lambda symbol, _start, _end: _candidate_bars(
            symbol,
            discontinuity_index=discontinuity_index,
            non_positive_open_index=non_positive_open_index,
        ),
        norgate_package_version="test-version",
        minimum_selected_symbols=2,
        market_data_root=root,
        repo_root=repo,
        platform_name="win32",
        disk_usage=lambda _path: SimpleNamespace(total=100, free=50),
    )
    return root, repo, panel, artifact_root


def _candidate_bars(
    symbol: str,
    *,
    discontinuity_index: int | None,
    non_positive_open_index: int | None,
) -> Sequence[Bar]:
    return [
        _bar(
            symbol,
            session,
            index,
            discontinuity_index=discontinuity_index if symbol == "AAA" else None,
            non_positive_open_index=non_positive_open_index if symbol == "AAA" else None,
        )
        for index, session in enumerate(_SESSIONS)
    ]


def _bars(symbol: str) -> list[Bar]:
    return [
        _bar(
            symbol,
            session,
            index,
            discontinuity_index=None,
            non_positive_open_index=None,
        )
        for index, session in enumerate(_SESSIONS)
    ]


def _bar(
    symbol: str,
    session: date,
    index: int,
    *,
    discontinuity_index: int | None,
    non_positive_open_index: int | None,
) -> Bar:
    multiplier = (
        Decimal("1.30")
        if discontinuity_index is not None and index >= discontinuity_index
        else Decimal("1")
    )
    opening = (Decimal("100") + Decimal(index)) * multiplier
    if non_positive_open_index is not None and index == non_positive_open_index:
        opening -= Decimal("3")
    closing = opening + Decimal("0.5")
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=datetime.combine(session, datetime.min.time(), UTC),
        open=opening,
        high=closing + Decimal("1"),
        low=opening - Decimal("1"),
        close=closing,
        volume=Decimal("1000"),
    )


def _events() -> NorgateCapitalEventEvidence:
    return NorgateCapitalEventEvidence(
        returned_row_count=len(_SESSIONS),
        returned_start=_START,
        returned_end=_END,
        clipped_session_count=len(_SESSIONS),
        marker_dates=(),
    )
