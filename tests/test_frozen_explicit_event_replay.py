from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture()
def runner_module() -> ModuleType:
    script_path = Path(__file__).parents[1] / "scripts" / "run_frozen_explicit_event_replay.py"
    module_name = "frozen_explicit_event_replay_test_module"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop(module_name, None)


def test_runner_hard_blocks_before_preparation_without_eligible_loader_attestation(
    runner_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    args = _arguments(runner_module, tmp_path)
    campaign = SimpleNamespace(common_sessions=(datetime(2024, 1, 2, tzinfo=UTC),))
    loader_kwargs: dict[str, object] = {}

    monkeypatch.setattr(
        runner_module,
        "load_cataloged_yahoo_daily_1d_bars",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        runner_module,
        "build_daily_campaign_plan",
        lambda *_args, **_kwargs: campaign,
    )

    def reject_unattested(*_args: object, **kwargs: object) -> object:
        loader_kwargs.update(kwargs)
        raise ValueError("corporate-action snapshot is not replay eligible")

    def fail_if_prepared(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("preparation must not run without eligible loader attestation")

    monkeypatch.setattr(runner_module, "load_cataloged_corporate_actions", reject_unattested)
    monkeypatch.setattr(runner_module, "prepare_daily_explicit_event_replay", fail_if_prepared)

    with pytest.raises(ValueError, match="not replay eligible"):
        runner_module.prepare_frozen_explicit_event_replay(args)

    assert loader_kwargs["require_replay_eligible"] is True
    assert loader_kwargs["expected_r2_dataset_id"] == args.r2_dataset_id
    assert loader_kwargs["expected_r2_dataset_hash"] == args.r2_dataset_hash
    assert loader_kwargs["expected_r2_manifest_hash"] == args.r2_manifest_hash


def test_runner_forwards_attested_inputs_and_only_prepares_frozen_cells(
    runner_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    args = _arguments(runner_module, tmp_path)
    campaign = SimpleNamespace(common_sessions=(datetime(2024, 1, 2, tzinfo=UTC),))
    actions = object()
    calls: dict[str, object] = {}

    def load_bars(*_args: object, **kwargs: object) -> object:
        calls.setdefault("bar_symbols", []).append(kwargs["symbol"])
        return object()

    def build_plan(cataloged_bars: tuple[object, ...], **kwargs: object) -> object:
        calls["cataloged_bars"] = cataloged_bars
        calls["catalog_facts"] = kwargs["catalog_facts"]
        calls["campaign_id"] = kwargs["campaign_id"]
        return campaign

    def load_actions(*received: object, **kwargs: object) -> object:
        calls["action_snapshot"] = received[0]
        calls["action_kwargs"] = kwargs
        return actions

    prepared = _prepared_fixture(args)

    def prepare(received_campaign: object, **kwargs: object) -> object:
        calls["prepared_campaign"] = received_campaign
        calls["preparation_kwargs"] = kwargs
        return prepared

    monkeypatch.setattr(runner_module, "load_cataloged_yahoo_daily_1d_bars", load_bars)
    monkeypatch.setattr(runner_module, "build_daily_campaign_plan", build_plan)
    monkeypatch.setattr(runner_module, "load_cataloged_corporate_actions", load_actions)
    monkeypatch.setattr(runner_module, "prepare_daily_explicit_event_replay", prepare)

    payload = runner_module.prepare_frozen_explicit_event_replay(args)

    action_kwargs = calls["action_kwargs"]
    preparation_kwargs = calls["preparation_kwargs"]
    catalog_facts = calls["catalog_facts"]
    assert calls["bar_symbols"] == ["SPY", "QQQ", "IWM"]
    assert calls["campaign_id"] == args.source_campaign_id
    assert catalog_facts.catalog_id == args.catalog_id
    assert catalog_facts.constructed_as_of_utc == datetime(2026, 7, 18, tzinfo=UTC)
    assert action_kwargs["require_replay_eligible"] is True
    assert action_kwargs["expected_dataset_hash"] == args.corporate_action_dataset_hash
    assert action_kwargs["expected_manifest_hash"] == args.corporate_action_manifest_hash
    assert action_kwargs["expected_r2_dataset_id"] == args.r2_dataset_id
    assert action_kwargs["expected_r2_dataset_hash"] == args.r2_dataset_hash
    assert action_kwargs["expected_r2_manifest_hash"] == args.r2_manifest_hash
    assert action_kwargs["observed_session_dates"] == {
        symbol: frozenset({datetime(2024, 1, 2, tzinfo=UTC).date()})
        for symbol in ("SPY", "QQQ", "IWM")
    }
    assert calls["prepared_campaign"] is campaign
    assert preparation_kwargs["corporate_actions"] is actions
    assert preparation_kwargs["source_summary_path"] == (
        args.artifact_root / "daily-campaign" / args.source_campaign_id / "summary.json"
    )
    assert preparation_kwargs["expected_source_summary_sha256"] == args.source_summary_sha256
    assert preparation_kwargs["replay_id"] == args.replay_id
    assert preparation_kwargs["artifact_root"] == args.artifact_root
    assert payload["status"] == "prepared_not_executed"
    assert payload["training_runs"] == 0
    assert payload["verified_checkpoint_count"] == 6
    assert payload["fold_local_prefit_standardization"] == "preserved"
    assert payload["replay_cells"] == {
        "frozen": 36,
        "baseline": 18,
        "candidate": 18,
        "executed": 0,
    }


def test_attribution_requires_pinned_source_hash_and_new_output_id(
    runner_module: ModuleType,
    tmp_path: Path,
) -> None:
    args = _arguments(runner_module, tmp_path)
    args.attribute = True

    with pytest.raises(ValueError, match="requires --replay-summary-sha256 and --attribution-id"):
        runner_module.attribute_frozen_explicit_event_replay(args)


def test_runner_requires_all_tiingo_raw_d1_pins(
    runner_module: ModuleType,
    tmp_path: Path,
) -> None:
    args = _arguments(runner_module, tmp_path)
    args.tiingo_raw_d1_snapshot = tmp_path / "raw-d1"

    with pytest.raises(ValueError, match="requires snapshot, dataset id, dataset hash"):
        runner_module.prepare_frozen_explicit_event_replay(args)


def test_runner_forwards_attested_tiingo_raw_d1_as_a_frozen_target(
    runner_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    args = _arguments(runner_module, tmp_path)
    raw_snapshot = tmp_path / "raw-d1"
    raw_snapshot.mkdir()
    args.tiingo_raw_d1_snapshot = raw_snapshot
    args.tiingo_raw_d1_dataset_id = (
        "us_equities.fixed_etf_tiingo_raw_d1.snapshot=unit-raw-d1"
    )
    args.tiingo_raw_d1_dataset_hash = "sha256:" + "e" * 64
    args.tiingo_raw_d1_manifest_hash = "sha256:" + "f" * 64

    campaign = SimpleNamespace(common_sessions=(datetime(2024, 1, 2, tzinfo=UTC),))
    target = object()
    actions = object()
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        runner_module,
        "load_cataloged_yahoo_daily_1d_bars",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        runner_module,
        "build_daily_campaign_plan",
        lambda *_args, **_kwargs: campaign,
    )
    monkeypatch.setattr(
        runner_module,
        "load_cataloged_corporate_actions",
        lambda *_args, **_kwargs: actions,
    )
    r2_lineage = SimpleNamespace(
        dataset_id=args.r2_dataset_id,
        dataset_hash=args.r2_dataset_hash,
        manifest_hash=args.r2_manifest_hash,
    )

    def load_r2_lineage(path: Path) -> object:
        calls["r2_lineage_path"] = path
        return r2_lineage

    monkeypatch.setattr(
        runner_module,
        "load_fixed_r2_corporate_action_lineage",
        load_r2_lineage,
    )

    def load_raw(snapshot: Path, **kwargs: object) -> object:
        calls.setdefault("raw_symbols", []).append(kwargs["symbol"])
        calls["raw_snapshot"] = snapshot
        calls["raw_kwargs"] = kwargs
        return object()

    def build_target(
        source_campaign: object,
        bars: tuple[object, ...],
        **kwargs: object,
    ) -> object:
        calls["target_source_campaign"] = source_campaign
        calls["target_bars"] = bars
        calls["target_kwargs"] = kwargs
        return target

    prepared = _prepared_fixture(args)

    def prepare(source_campaign: object, **kwargs: object) -> object:
        calls["prepared_source_campaign"] = source_campaign
        calls["preparation_kwargs"] = kwargs
        return prepared

    monkeypatch.setattr(runner_module, "load_cataloged_tiingo_raw_d1_bars", load_raw)
    monkeypatch.setattr(
        runner_module,
        "build_daily_source_sensitivity_replay_plan",
        build_target,
    )
    monkeypatch.setattr(runner_module, "prepare_daily_explicit_event_replay", prepare)

    runner_module.prepare_frozen_explicit_event_replay(args)

    assert calls["r2_lineage_path"] == args.r2_subset.parent
    assert calls["raw_symbols"] == ["SPY", "QQQ", "IWM"]
    assert calls["raw_snapshot"] == raw_snapshot.resolve()
    raw_kwargs = calls["raw_kwargs"]
    assert raw_kwargs["dataset_id"] == args.tiingo_raw_d1_dataset_id
    assert raw_kwargs["expected_dataset_hash"] == args.tiingo_raw_d1_dataset_hash
    assert raw_kwargs["expected_manifest_hash"] == args.tiingo_raw_d1_manifest_hash
    assert raw_kwargs["source_snapshot_dir"] == args.corporate_action_snapshot.resolve()
    assert raw_kwargs["r2_lineage"] is r2_lineage
    assert calls["target_source_campaign"] is campaign
    assert len(calls["target_bars"]) == 3
    assert calls["target_kwargs"] == {
        "replay_campaign_id": f"{args.replay_id}-input"
    }
    assert calls["prepared_source_campaign"] is campaign
    assert calls["preparation_kwargs"]["replay_target_plan"] is target
    assert (
        calls["preparation_kwargs"]["replay_target_manifest_hash"]
        == args.tiingo_raw_d1_manifest_hash
    )


def test_attribution_rejects_tiingo_raw_d1_source_sensitivity_input(
    runner_module: ModuleType,
    tmp_path: Path,
) -> None:
    args = _arguments(runner_module, tmp_path)
    args.attribute = True
    args.tiingo_raw_d1_snapshot = tmp_path / "raw-d1"
    args.tiingo_raw_d1_dataset_id = (
        "us_equities.fixed_etf_tiingo_raw_d1.snapshot=unit-raw-d1"
    )
    args.tiingo_raw_d1_dataset_hash = "sha256:" + "e" * 64
    args.tiingo_raw_d1_manifest_hash = "sha256:" + "f" * 64

    with pytest.raises(ValueError, match="does not support a source-sensitivity replay input"):
        runner_module.attribute_frozen_explicit_event_replay(args)


def _arguments(runner_module: ModuleType, tmp_path: Path):
    r2_dir = tmp_path / "r2"
    r2_dir.mkdir()
    r2_subset = r2_dir / "ohlcv_1d.csv.gz"
    r2_subset.write_bytes(b"r2-bytes")
    r2_manifest = r2_dir / "manifest.json"
    r2_manifest.write_bytes(b"r2-manifest")
    action_snapshot = tmp_path / "actions"
    action_snapshot.mkdir()
    _write_tiingo_manifest(action_snapshot)
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    return runner_module.build_parser().parse_args(
        [
            "--r2-subset",
            str(r2_subset),
            "--r2-dataset-id",
            "us_equities.fixed_etf_daily.1d.snapshot=test-r2",
            "--r2-dataset-hash",
            _sha256(b"r2-bytes"),
            "--r2-manifest-hash",
            _sha256(b"r2-manifest"),
            "--catalog-id",
            "sha256:" + "a" * 64,
            "--catalog-constructed-as-utc",
            "2026-07-18T00:00:00Z",
            "--corporate-action-snapshot",
            str(action_snapshot),
            "--corporate-action-dataset-id",
            "us_equities.fixed_etf_corporate_actions.snapshot=test-events",
            "--corporate-action-dataset-hash",
            "sha256:" + "b" * 64,
            "--corporate-action-manifest-hash",
            "sha256:" + "c" * 64,
            "--source-campaign-id",
            "raw-d1-source-r1",
            "--source-summary-sha256",
            "sha256:" + "d" * 64,
            "--replay-id",
            "raw-d1-explicit-events-r1",
            "--artifact-root",
            str(artifact_root),
            "--repo-root",
            str(Path(__file__).parents[1]),
        ]
    )


def _prepared_fixture(args) -> SimpleNamespace:
    baseline_cells = [
        SimpleNamespace(kind="baseline")
        for _fold in ("fold-1", "fold-2")
        for _symbol in ("SPY", "QQQ", "IWM")
        for _baseline in ("always_long", "flat", "previous_bar_direction")
    ]
    candidate_cells = []
    for fold_id in ("fold-1", "fold-2"):
        for candidate_index in range(3):
            checkpoint = Path(f"/{fold_id}-{candidate_index}.pt")
            for _symbol in ("SPY", "QQQ", "IWM"):
                candidate_cells.append(
                    SimpleNamespace(
                        kind="candidate",
                        fold_id=fold_id,
                        checkpoint_path=checkpoint,
                        standardization=SimpleNamespace(fold_id=fold_id),
                    )
                )
    return SimpleNamespace(
        replay_id=args.replay_id,
        source_campaign_id=args.source_campaign_id,
        corporate_action_dataset_id=args.corporate_action_dataset_id,
        corporate_action_dataset_hash=args.corporate_action_dataset_hash,
        corporate_action_manifest_hash=args.corporate_action_manifest_hash,
        r2_dataset_id=args.r2_dataset_id,
        r2_dataset_hash=args.r2_dataset_hash,
        r2_manifest_hash=args.r2_manifest_hash,
        source_summary_sha256=args.source_summary_sha256,
        parent_sensitivity_verdict="unsupported",
        training_runs=0,
        cells=tuple((*baseline_cells, *candidate_cells)),
    )


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _write_tiingo_manifest(snapshot: Path) -> None:
    payload = {
        "campaign_coverage": {"start": "2022-11-22", "end": "2026-06-22"},
        "scope": {
            "retrospective_development_replay_only": True,
            "point_in_time_eligible": False,
            "ranking_eligible": False,
            "sealed_holdout_eligible": False,
        },
        "tiingo_source_contract": {
            "source": "Tiingo standard EOD API",
            "endpoint_template": "https://api.tiingo.com/tiingo/daily/{symbol}/prices",
            "normalization_fields": ["date", "divCash", "splitFactor"],
            "raw_response_policy": "exact_per_symbol_bytes",
        },
        "raw_sources": [
            {
                "source_id": f"tiingo-standard-eod-{symbol.lower()}",
                "provider": "Tiingo standard EOD API",
                "source_kind": "licensed_api",
                "acquisition_mode": "authorized_api",
                "source_url": f"https://api.tiingo.com/tiingo/daily/{symbol}/prices",
                "symbols": [symbol],
                "event_types": ["cash_distribution", "split"],
            }
            for symbol in ("SPY", "QQQ", "IWM")
        ],
    }
    (snapshot / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
