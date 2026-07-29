from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import numpy
import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.research.norgate_broad_representation import (
    RepresentationGeometry,
    _write_or_verify_safe_weights,
    build_observed_return_dataset,
    freeze_representation_campaign,
    frozen_norgate_panel_snapshot_dir,
    mask_observed_windows,
)


def test_observed_dataset_never_uses_a_future_bar_for_development_windows() -> None:
    geometry = RepresentationGeometry(
        window_length=4,
        mask_span=2,
        development_end_return_index=7,
        diagnostic_start_return_index=10,
    )
    catalog = _catalog(last_close=Decimal("112"))
    initial = build_observed_return_dataset(catalog, geometry=geometry)
    changed_future = build_observed_return_dataset(
        _catalog(last_close=Decimal("224")),
        geometry=geometry,
    )

    assert initial.development_windows.shape == (10, 4)
    assert initial.diagnostic_windows.shape == (2, 4)
    assert initial.development_window_sha256 == changed_future.development_window_sha256
    assert initial.diagnostic_window_sha256 != changed_future.diagnostic_window_sha256
    assert numpy.array_equal(initial.development_windows, changed_future.development_windows)
    assert not numpy.array_equal(initial.diagnostic_windows, changed_future.diagnostic_windows)


def test_frozen_panel_path_is_relative_to_the_injected_market_data_root() -> None:
    assert frozen_norgate_panel_snapshot_dir(Path("/app/market_data")) == Path(
        "/app/market_data/us_equities/norgate_trial_broad_development_panel/canonical/"
        "ohlcv_1d/snapshot=2026-07-18-norgate-trial-broad-d1-panel-r1"
    )


def test_masking_is_deterministic_and_exposes_only_observed_targets() -> None:
    windows = numpy.asarray(
        [[0.01, -0.02, 0.03, 0.04], [0.05, 0.06, -0.07, 0.08]],
        dtype=numpy.float32,
    )

    first = mask_observed_windows(windows, mask_span=2, seed=73)
    second = mask_observed_windows(windows, mask_span=2, seed=73)
    features, targets, mask = first

    assert all(numpy.array_equal(left, right) for left, right in zip(first, second, strict=True))
    assert features.shape == (2, 4, 2)
    assert targets.shape == (2, 4, 1)
    assert mask.shape == (2, 4, 1)
    assert numpy.array_equal(targets[..., 0], windows)
    assert numpy.array_equal(features[..., 1], mask[..., 0])
    assert numpy.all(mask.sum(axis=(1, 2)) == 2)
    assert numpy.all(features[..., 0][mask[..., 0].astype(bool)] == 0.0)


def test_contract_is_external_target_free_and_registry_backed(tmp_path: Path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    artifact_root.mkdir()
    dataset = build_observed_return_dataset(
        _catalog(last_close=Decimal("112")),
        geometry=RepresentationGeometry(
            window_length=4,
            mask_span=2,
            development_end_return_index=7,
            diagnostic_start_return_index=10,
        ),
    )

    contract = freeze_representation_campaign(
        dataset,
        artifact_root=artifact_root,
        repo_root=tmp_path / "repo",
        run_id="unit-target-free",
        code_revision="unit",
    )
    payload = json.loads(contract.contract_path.read_text(encoding="utf-8"))

    assert contract.contract_path.is_relative_to(artifact_root)
    assert contract.registry_entry.record_path.is_relative_to(artifact_root)
    assert payload["objective"] == "masked_span_reconstruction_of_observed_returns"
    assert payload["observed_windows"]["forward_labels"] is False
    assert payload["observed_windows"]["future_aware_quality_filter"] is False
    assert payload["training_policy"] == {
        "architecture_selection": False,
        "early_stopping": False,
        "fixed_steps": True,
        "score_leaderboard": False,
        "weight_format": "npz_numpy_arrays_no_pickle",
    }
    assert payload["scope"]["paper_trading_eligible"] is False
    assert "price" not in contract.contract_path.read_text(encoding="utf-8").lower()
    assert "credential" not in contract.contract_path.read_text(encoding="utf-8").lower()
    assert freeze_representation_campaign(
        dataset,
        artifact_root=artifact_root,
        repo_root=tmp_path / "repo",
        run_id="unit-target-free",
        code_revision="unit",
    ).registry_entry == contract.registry_entry


def test_contract_rejects_git_local_artifacts(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    artifact_root = repo_root / "model-artifacts"
    artifact_root.mkdir(parents=True)
    dataset = build_observed_return_dataset(
        _catalog(last_close=Decimal("112")),
        geometry=RepresentationGeometry(
            window_length=4,
            mask_span=2,
            development_end_return_index=7,
            diagnostic_start_return_index=10,
        ),
    )

    with pytest.raises(ValueError, match="outside the Git workspace"):
        freeze_representation_campaign(
            dataset,
            artifact_root=artifact_root,
            repo_root=repo_root,
            run_id="unit-target-free",
            code_revision="unit",
        )


def test_safe_weight_writer_uses_non_pickle_npz_arrays(tmp_path: Path) -> None:
    class FakeTensor:
        def __init__(self, values: object) -> None:
            self.values = values

        def detach(self) -> FakeTensor:
            return self

        def cpu(self) -> FakeTensor:
            return self

        def contiguous(self) -> FakeTensor:
            return self

        def numpy(self) -> object:
            return self.values

    class FakeModel:
        def state_dict(self) -> dict[str, FakeTensor]:
            return {"encoder.weight": FakeTensor(numpy.asarray([[1.0, 2.0]], dtype=numpy.float32))}

    path = tmp_path / "weights.npz"
    first_hash = _write_or_verify_safe_weights(path=path, model=FakeModel(), numpy=numpy)

    with numpy.load(path, allow_pickle=False) as payload:
        assert payload.files == ["encoder.weight"]
        assert numpy.array_equal(payload["encoder.weight"], numpy.asarray([[1.0, 2.0]]))
    assert _write_or_verify_safe_weights(path=path, model=FakeModel(), numpy=numpy) == first_hash


def _catalog(*, last_close: Decimal) -> SimpleNamespace:
    sessions = tuple(date(2025, 1, 1) + timedelta(days=index) for index in range(12))
    closes = tuple(Decimal("100") + Decimal(index) for index in range(11)) + (last_close,)
    bars_by_symbol = {
        symbol: SimpleNamespace(bars=_bars(symbol, sessions, closes))
        for symbol in ("AAA", "BBB")
    }
    return SimpleNamespace(
        source=SimpleNamespace(
            dataset_id="unit.norgate.target-free",
            dataset_hash=_digest("dataset"),
            manifest_hash=_digest("manifest"),
        ),
        common_sessions=sessions,
        bars_by_symbol=bars_by_symbol,
    )


def _bars(symbol: str, sessions: tuple[date, ...], closes: tuple[Decimal, ...]) -> tuple[Bar, ...]:
    return tuple(
        Bar(
            symbol=symbol,
            market="US",
            timeframe=Timeframe.D1,
            start_ts=datetime(session.year, session.month, session.day, tzinfo=UTC),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=Decimal("1000"),
        )
        for session, close in zip(sessions, closes, strict=True)
    )


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
