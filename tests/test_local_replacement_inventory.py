from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from thericher_v2.data.local_replacement_inventory import build_local_replacement_inventory


def test_writes_external_manifest_only_inventory_without_network_or_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(socket, "create_connection", _unexpected_network)
    original_read_bytes = Path.read_bytes

    def guard_read_bytes(path: Path, *args: object, **kwargs: object) -> bytes:
        if path.name.startswith(".env"):
            raise AssertionError("inventory must not read credentials")
        return original_read_bytes(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", guard_read_bytes)
    market_root = _fixtures(tmp_path)
    repo, artifacts = tmp_path / "repo", tmp_path / "artifacts"
    repo.mkdir()
    artifacts.mkdir()

    result = build_local_replacement_inventory(
        market_data_root=market_root,
        artifact_root=artifacts,
        repo_root=repo,
    )

    payload = json.loads(result.summary_path.read_bytes())
    assert result.summary_path.is_relative_to(artifacts)
    assert result.conclusion == "no_local_fresh_training_candidate"
    assert payload["scope"]["credential_access"] is False
    assert payload["conclusion"]["status"] == "no_local_fresh_training_candidate"
    assert {row["id"]: row["disposition"] for row in payload["candidates"]} == {
        "norgate_broad_r1": "not_fresh",
        "tiingo_standard_eod_pilot_r2": "not_ready",
        "fixed_etf_raw_yahoo_r2": "not_ready",
        "tiingo_full_history_r1": "not_ready",
        "yahoo_broad_daily_2026_06_23": "data_preflight_only",
        "tiingo_iex_intraday_r1": "not_ready",
    }
    with pytest.raises(FileExistsError):
        build_local_replacement_inventory(
            market_data_root=market_root,
            artifact_root=artifacts,
            repo_root=repo,
        )


def test_rejects_git_artifacts_and_changed_manifest(tmp_path: Path) -> None:
    market_root = _fixtures(tmp_path)
    repo, external = tmp_path / "repo", tmp_path / "external"
    repo.mkdir()
    external.mkdir()
    with pytest.raises(ValueError, match="outside the Git workspace"):
        build_local_replacement_inventory(
            market_data_root=market_root,
            artifact_root=repo,
            repo_root=repo,
        )

    path = market_root.joinpath(*_PILOT_MANIFEST)
    payload = json.loads(path.read_bytes())
    payload["aggregate"]["available"] = 28
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="tiingo_standard_eod_pilot_r2 manifest fact changed"):
        build_local_replacement_inventory(
            market_data_root=market_root,
            artifact_root=external,
            repo_root=repo,
        )


def test_source_has_no_network_or_credential_client() -> None:
    source = Path("src/thericher_v2/data/local_replacement_inventory.py").read_text().lower()
    forbidden = ("requests", "socket", "urllib", "dotenv", "torch", "kis")
    assert all(word not in source for word in forbidden)


_PILOT_MANIFEST = (
    "us_equities",
    "tiingo_standard_eod_pilot",
    "canonical",
    "snapshot=2026-07-18-tiingo-standard-eod-pilot-r2",
    "manifest.json",
)


def _unexpected_network(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("inventory must remain offline")


def _fixtures(tmp_path: Path) -> Path:
    root = tmp_path / "market-data"
    _write(
        root,
        (
            "us_equities",
            "norgate_trial_broad_development_panel",
            "canonical",
            "ohlcv_1d",
            "snapshot=2026-07-18-norgate-trial-broad-d1-panel-r1",
            "manifest.json",
        ),
        {
            "dataset_id": "norgate",
            "calendar_parent": {
                "actual_common_window": {"start": "2024-07-18", "end": "2026-06-22"}
            },
            "static_panel_contract": {"selected_symbol_count": 523},
            "scope": {"model_eligible": False, "gpu_eligible": False},
        },
    )
    _write(
        root,
        _PILOT_MANIFEST,
        {
            "dataset_id": "pilot",
            "requested_window": {"start": "2024-07-18", "end": "2026-07-17"},
            "aggregate": {"available": 29},
            "scope": {"model_eligible": False, "gpu_eligible": False},
        },
    )
    _write(
        root,
        (
            "us_equities",
            "fixed_etf_daily",
            "canonical",
            "ohlcv_1d",
            "snapshot=2026-07-18-r2",
            "manifest.json",
        ),
        {
            "dataset_id": "fixed",
            "symbols": ["SPY", "QQQ", "IWM"],
            "date_ranges": {"IWM": {"min": "2000-05-26", "max": "2026-06-22", "sessions": 6555}},
            "eligibility": {
                "development_training": {"eligible": True},
                "ranking": {"eligible": False},
            },
        },
    )
    _write(
        root,
        (
            "us_equities",
            "fixed_etf_full_history",
            "canonical",
            "tiingo_standard_eod",
            "snapshot=2026-07-18-tiingo-eod-full-history-r1",
            "manifest.json",
        ),
        {
            "dataset_id": "full",
            "symbols": ["SPY", "QQQ", "IWM"],
            "coverage_by_symbol": {"IWM": {"last_session": "2026-07-10"}},
            "scope": {"campaign_eligible": False, "point_in_time_eligible": False},
        },
    )
    _write(
        root,
        (
            "us_equities",
            "yahoo_daily_universe",
            "manifests",
            "yahoo_daily_universe_snapshot=2026-06-23.json",
        ),
        {
            "dataset": "yahoo_daily_universe",
            "results": {
                "symbols_succeeded": 1300,
                "rows": 7390436,
                "first_date": "1980-01-02",
                "last_date": "2026-06-22",
            },
        },
    )
    _write(
        root,
        (
            "us_equities",
            "fixed_etf_intraday",
            "canonical",
            "tiingo_iex_5m",
            "snapshot=2026-07-19-tiingo-iex-5m-r1",
            "manifest.json",
        ),
        {
            "dataset_id": "intraday",
            "common_session_coverage": {
                "first_session": "2026-01-13",
                "last_session": "2026-07-10",
                "session_count": 129,
            },
            "scope": {"training_eligible": False},
        },
    )
    return root


def _write(root: Path, parts: tuple[str, ...], payload: dict[str, object]) -> None:
    path = root.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
