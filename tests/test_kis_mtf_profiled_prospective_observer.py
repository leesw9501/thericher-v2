from __future__ import annotations

import hashlib
import json
import socket
import subprocess
import sys
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import thericher_v2.data.kis_mtf_profiled_prospective_observer as observer
import thericher_v2.data.profiled_mtf_forward_capture_cycle as capture_cycle
from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import kis_intraday_mtf_availability as availability
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.research.causal_mtf_window_profile_feasibility import (
    CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
)
from thericher_v2.research.kis_mtf_profiled_feature_input_preflight import (
    build_target_free_mtf_feature_projection,
    completed_causal_minute_prefix,
    resample_completed_causal_prefix,
)


def test_all_profiles_are_forward_only_source_safe_and_idempotent(
    preflight_binding,
    tmp_path: Path,
) -> None:
    historical_dates = _regular_dates_after(date(2026, 6, 1), count=21)
    forward_date = _regular_dates_after(historical_dates[-1] + timedelta(days=1), count=1)[0]
    historical = _catalogs(historical_dates, marker="historical")
    head = _catalogs((forward_date,), marker="head")
    contract = _contract(historical, preflight_binding)

    observation = _observation(contract, historical, head, forward_date)

    assert observation is not None
    assert observation.status == "observed"
    assert tuple(profile.profile_id for profile in observation.profiles) == (
        observer.KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PROFILE_IDS
    )
    assert {profile.status for profile in observation.profiles} == {"observed"}

    repository = tmp_path / "repo"
    repository.mkdir()
    artifact_root = tmp_path / "artifacts"
    first = observer.append_kis_mtf_profiled_prospective_observation(
        artifact_root=artifact_root,
        repo_root=repository,
        contract=contract,
        observation=observation,
    )
    second = observer.append_kis_mtf_profiled_prospective_observation(
        artifact_root=artifact_root,
        repo_root=repository,
        contract=contract,
        observation=observation,
    )

    assert first.outcome == "appended"
    assert second.outcome == "duplicate"
    payloads = [
        json.loads(path.read_text(encoding="utf-8")) for path in artifact_root.rglob("*.json")
    ]
    assert len(payloads) == 2
    rendered = json.dumps(payloads, sort_keys=True)
    for forbidden in ("QQQ", "SPY", "2026-", "D:/market_data", "101."):
        assert forbidden not in rendered


def test_historical_sessions_do_not_create_forward_observations(preflight_binding) -> None:
    historical_dates = _regular_dates_after(date(2026, 6, 1), count=21)
    historical = _catalogs(historical_dates, marker="historical")
    contract = _contract(historical, preflight_binding)

    observation = _observation(contract, historical, historical, historical_dates[-1])

    assert observation is None


def test_cutoff_boundary_seals_profiles_and_rejects_forged_slow_bars(preflight_binding) -> None:
    historical_dates = _regular_dates_after(date(2026, 6, 1), count=21)
    forward_date = _regular_dates_after(historical_dates[-1] + timedelta(days=1), count=1)[0]
    historical = _catalogs(historical_dates, marker="historical")
    baseline_head = _catalogs((forward_date,), marker="head-a")
    contract = _contract(historical, preflight_binding)
    baseline = _observation(contract, historical, baseline_head, forward_date)

    post_cutoff_head = _catalogs(
        (forward_date,),
        marker="head-after-cutoff",
        after_cutoff_minutes=2,
    )
    after_cutoff = _observation(contract, historical, post_cutoff_head, forward_date)

    assert baseline is not None and after_cutoff is not None
    assert after_cutoff.content_commitment_sha256 == baseline.content_commitment_sha256
    assert after_cutoff.head_source_contract_sha256 == baseline.head_source_contract_sha256

    changed_bars = list(baseline_head["QQQ/NAS/1m"].bars)
    changed_bars[180] = replace(
        changed_bars[180],
        volume=changed_bars[180].volume + Decimal("1"),
    )
    forged_prefix = completed_causal_minute_prefix(
        tuple(changed_bars),
        expected_symbol="QQQ",
        session=us_equity_2026_session(forward_date).window,
        cutoff=_cutoff(forward_date),
    )
    old_resample = resample_completed_causal_prefix(
        completed_causal_minute_prefix(
            baseline_head["QQQ/NAS/1m"].bars,
            expected_symbol="QQQ",
            session=us_equity_2026_session(forward_date).window,
            cutoff=_cutoff(forward_date),
        ),
        session=us_equity_2026_session(forward_date).window,
        cutoff=_cutoff(forward_date),
    )
    with pytest.raises(ValueError, match="slow bar does not match"):
        build_target_free_mtf_feature_projection(
            source_contract_sha256=_sha256("source"),
            source_dataset_hash=_sha256("dataset"),
            catalog=CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
            profile_id="extended",
            minute_bars=forged_prefix,
            bars_by_timeframe=old_resample,
            cutoff=_cutoff(forward_date),
        )

    legitimate_head = dict(baseline_head)
    legitimate_head["QQQ/NAS/1m"] = _catalog(
        "QQQ",
        "NAS",
        (forward_date,),
        marker="head-before-cutoff",
        bars=tuple(changed_bars),
    )
    legitimate = _observation(contract, historical, legitimate_head, forward_date)

    assert legitimate is not None
    assert legitimate.status == "observed"
    assert legitimate.content_commitment_sha256 != baseline.content_commitment_sha256


def test_conflict_and_external_artifact_root_enforcement(
    preflight_binding,
    tmp_path: Path,
) -> None:
    historical_dates = _regular_dates_after(date(2026, 6, 1), count=21)
    forward_date = _regular_dates_after(historical_dates[-1] + timedelta(days=1), count=1)[0]
    historical = _catalogs(historical_dates, marker="historical")
    contract = _contract(historical, preflight_binding)
    baseline_head = _catalogs((forward_date,), marker="head-a")
    baseline = _observation(contract, historical, baseline_head, forward_date)
    assert baseline is not None

    changed_bars = list(baseline_head["SPY/AMS/1m"].bars)
    changed_bars[180] = replace(
        changed_bars[180],
        volume=changed_bars[180].volume + Decimal("1"),
    )
    changed_head = dict(baseline_head)
    changed_head["SPY/AMS/1m"] = _catalog(
        "SPY",
        "AMS",
        (forward_date,),
        marker="head-conflict",
        bars=tuple(changed_bars),
    )
    changed = _observation(contract, historical, changed_head, forward_date)
    assert changed is not None

    repository = tmp_path / "repo"
    repository.mkdir()
    artifact_root = tmp_path / "artifacts"
    first = observer.append_kis_mtf_profiled_prospective_observation(
        artifact_root=artifact_root,
        repo_root=repository,
        contract=contract,
        observation=baseline,
    )
    stored = next(artifact_root.rglob("observations/*.json")).read_bytes()
    conflict = observer.append_kis_mtf_profiled_prospective_observation(
        artifact_root=artifact_root,
        repo_root=repository,
        contract=contract,
        observation=changed,
    )

    assert first.outcome == "appended"
    assert conflict.outcome == "conflict"
    assert next(artifact_root.rglob("observations/*.json")).read_bytes() == stored
    assert len(list(artifact_root.rglob("conflicts/*.json"))) == 1
    tampered_path = next(artifact_root.rglob("observations/*.json"))
    tampered_payload = json.loads(tampered_path.read_text(encoding="utf-8"))
    tampered_payload["symbol"] = "QQQ"
    tampered_path.write_text(json.dumps(tampered_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="stored observation"):
        observer.append_kis_mtf_profiled_prospective_observation(
            artifact_root=artifact_root,
            repo_root=repository,
            contract=contract,
            observation=baseline,
        )
    with pytest.raises(ValueError, match="outside the Git workspace"):
        observer.append_kis_mtf_profiled_prospective_observation(
            artifact_root=repository,
            repo_root=repository,
            contract=contract,
            observation=baseline,
        )
    with pytest.raises(ValueError, match="market-data root"):
        observer.append_kis_mtf_profiled_prospective_observation(
            artifact_root=Path("D:/market_data"),
            repo_root=repository,
            contract=contract,
            observation=baseline,
        )

    linked_root = tmp_path / "linked-artifacts"
    try:
        linked_root.symlink_to(artifact_root, target_is_directory=True)
    except OSError:
        pytest.skip("the current Windows environment does not permit test symlinks")
    with pytest.raises(ValueError, match="symlink"):
        observer.append_kis_mtf_profiled_prospective_observation(
            artifact_root=linked_root,
            repo_root=repository,
            contract=contract,
            observation=baseline,
        )


def test_runner_is_local_only_and_never_reads_environment(
    preflight_binding,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    historical_dates = _regular_dates_after(date(2026, 6, 1), count=21)
    forward_date = _regular_dates_after(historical_dates[-1] + timedelta(days=1), count=1)[0]
    historical = _catalogs(historical_dates, marker="historical")
    head = _catalogs((forward_date,), marker="head")
    repository = tmp_path / "repo"
    repository.mkdir()
    historical_root = tmp_path / "historical"
    head_root = tmp_path / "head"

    def local_loader(*, cache_root: Path, **_kwargs: object) -> dict[str, CatalogedBars]:
        assert cache_root in {historical_root, head_root}
        return historical if cache_root == historical_root else head

    preflight_binding(historical)
    monkeypatch.setattr(socket, "create_connection", _forbid)
    monkeypatch.setattr(observer.os, "environ", _DenyEnvironment())

    result = observer.run_kis_mtf_profiled_prospective_observer(
        historical_cache_root=historical_root,
        head_cache_root=head_root,
        artifact_root=tmp_path / "artifacts",
        repo_root=repository,
        code_revision=_sha256("code-r1"),
        observed_at=_observed_after_cutoff(forward_date),
        catalog_loader=local_loader,
    )

    assert result is not None
    assert result.outcome == "appended"
    forward_result = observer.run_kis_mtf_profiled_forward_outcome_witness(
        historical_cache_root=historical_root,
        head_cache_root=head_root,
        artifact_root=tmp_path / "artifacts",
        market_data_root=tmp_path / "market-data",
        repo_root=repository,
        code_revision=_sha256("code-r1"),
        observed_at=_outcome_due(forward_date),
        catalog_loader=local_loader,
    )
    assert forward_result is not None
    assert forward_result.outcome == "outcome_unavailable"
    source = Path(observer.__file__).read_text(encoding="utf-8").lower()
    for forbidden in (
        "os.environ",
        "socket",
        "urllib",
        "requests",
        "local_paper",
        "kis_live",
        "torch",
    ):
        assert forbidden not in source


def test_forward_outcome_seals_exact_completed_window_and_retains_raw_only_under_market_data(
    preflight_binding,
    tmp_path: Path,
) -> None:
    historical_dates = _regular_dates_after(date(2026, 6, 1), count=21)
    forward_date = _regular_dates_after(historical_dates[-1] + timedelta(days=1), count=1)[0]
    historical = _catalogs(historical_dates, marker="historical")
    head = _catalogs((forward_date,), marker="forward", after_cutoff_minutes=15)
    observer_contract = _contract(historical, preflight_binding)
    repository = tmp_path / "repo"
    repository.mkdir()
    artifact_root = tmp_path / "artifacts"
    market_data_root = tmp_path / "market-data"
    _store_input_observation(
        observer_contract,
        historical,
        head,
        forward_date,
        artifact_root,
        repository,
    )
    contract = observer.freeze_kis_mtf_profiled_forward_outcome_contract(observer_contract)

    materialization = observer.materialize_kis_mtf_profiled_forward_outcome_witness(
        contract,
        observer_contract=observer_contract,
        historical_catalogs=historical,
        head_catalogs=head,
        artifact_root=artifact_root,
        repo_root=repository,
        observed_at=_outcome_due(forward_date),
    )

    assert materialization is not None
    assert materialization.witness.status == "target_ready"
    first = observer.append_kis_mtf_profiled_forward_outcome_witness(
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        repo_root=repository,
        contract=contract,
        materialization=materialization,
    )
    duplicate = observer.append_kis_mtf_profiled_forward_outcome_witness(
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        repo_root=repository,
        contract=contract,
        materialization=materialization,
    )
    inventory = observer.inspect_kis_mtf_profiled_forward_outcome_inventory(
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        repo_root=repository,
        contract=contract,
    )
    catalog = observer.load_kis_mtf_profiled_forward_outcome_snapshot_catalog(
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        repo_root=repository,
        contract=contract,
    )

    assert first.outcome == "appended"
    assert duplicate.outcome == "duplicate"
    assert inventory.target_ready_pair_count == 1
    assert inventory.status == "target_ready"
    assert catalog.inventory == inventory
    assert len(catalog.snapshots) == 1
    assert catalog.snapshots[0].input_prefixes[0][-1].end_ts == _cutoff(forward_date)
    assert catalog.snapshots[0].outcome_end == _outcome_due(forward_date)
    outcome_payloads = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in artifact_root.rglob("mtf-forward-outcomes-v1/**/*.json")
    ]
    rendered = json.dumps(outcome_payloads, sort_keys=True)
    for forbidden in ("QQQ", "SPY", "2026-", "100.5", "D:/market_data"):
        assert forbidden not in rendered
    raw_snapshots = list(market_data_root.rglob("*.json"))
    assert len(raw_snapshots) == 1
    assert all(path.is_relative_to(market_data_root) for path in raw_snapshots)
    raw_bytes = raw_snapshots[0].read_bytes()
    assert _sha256_bytes(raw_bytes) == materialization.witness.raw_snapshot_sha256
    assert "QQQ" in raw_bytes.decode("utf-8")
    raw_snapshots[0].write_bytes(raw_bytes + b" ")
    with pytest.raises(ValueError, match="raw snapshot"):
        observer.load_kis_mtf_profiled_forward_outcome_snapshot_catalog(
            artifact_root=artifact_root,
            market_data_root=market_data_root,
            repo_root=repository,
            contract=contract,
        )
    raw_snapshots[0].write_bytes(raw_bytes)
    raw_snapshots[0].unlink()
    with pytest.raises(ValueError, match="raw snapshot"):
        observer.inspect_kis_mtf_profiled_forward_outcome_inventory(
            artifact_root=artifact_root,
            market_data_root=market_data_root,
            repo_root=repository,
            contract=contract,
        )
    with pytest.raises(ValueError, match="raw snapshot"):
        observer.load_kis_mtf_profiled_forward_outcome_snapshot_catalog(
            artifact_root=artifact_root,
            market_data_root=market_data_root,
            repo_root=repository,
            contract=contract,
        )


def test_empty_forward_outcome_inventory_is_read_only(preflight_binding, tmp_path: Path) -> None:
    historical_dates = _regular_dates_after(date(2026, 6, 1), count=21)
    historical = _catalogs(historical_dates, marker="historical")
    observer_contract = _contract(historical, preflight_binding)
    contract = observer.freeze_kis_mtf_profiled_forward_outcome_contract(observer_contract)
    repository = tmp_path / "repo"
    repository.mkdir()
    artifact_root = tmp_path / "artifacts"
    market_data_root = tmp_path / "market-data"

    inventory = observer.inspect_kis_mtf_profiled_forward_outcome_inventory(
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        repo_root=repository,
        contract=contract,
    )
    catalog = observer.load_kis_mtf_profiled_forward_outcome_snapshot_catalog(
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        repo_root=repository,
        contract=contract,
    )

    assert inventory.target_ready_pair_count == 0
    assert inventory.status == "zero_target_ready"
    assert catalog.inventory == inventory
    assert catalog.snapshots == ()
    assert not artifact_root.exists()
    assert not market_data_root.exists()


def test_forward_outcome_waits_for_the_final_1544_bar_and_recovers_without_sealing_gap(
    preflight_binding,
    tmp_path: Path,
) -> None:
    historical_dates = _regular_dates_after(date(2026, 6, 1), count=21)
    forward_date = _regular_dates_after(historical_dates[-1] + timedelta(days=1), count=1)[0]
    historical = _catalogs(historical_dates, marker="historical")
    complete_head = _catalogs((forward_date,), marker="complete", after_cutoff_minutes=15)
    incomplete_head = _catalogs((forward_date,), marker="incomplete", after_cutoff_minutes=14)
    observer_contract = _contract(historical, preflight_binding)
    repository = tmp_path / "repo"
    repository.mkdir()
    artifact_root = tmp_path / "artifacts"
    market_data_root = tmp_path / "market-data"
    _store_input_observation(
        observer_contract,
        historical,
        complete_head,
        forward_date,
        artifact_root,
        repository,
    )
    contract = observer.freeze_kis_mtf_profiled_forward_outcome_contract(observer_contract)

    before_due = observer.materialize_kis_mtf_profiled_forward_outcome_witness(
        contract,
        observer_contract=observer_contract,
        historical_catalogs=historical,
        head_catalogs=complete_head,
        artifact_root=artifact_root,
        repo_root=repository,
        observed_at=_outcome_due(forward_date) - timedelta(minutes=1),
    )
    unavailable = observer.materialize_kis_mtf_profiled_forward_outcome_witness(
        contract,
        observer_contract=observer_contract,
        historical_catalogs=historical,
        head_catalogs=incomplete_head,
        artifact_root=artifact_root,
        repo_root=repository,
        observed_at=_outcome_due(forward_date),
    )

    assert before_due is None
    assert unavailable is not None
    assert unavailable.witness.status == "outcome_unavailable"
    unavailable_result = observer.append_kis_mtf_profiled_forward_outcome_witness(
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        repo_root=repository,
        contract=contract,
        materialization=unavailable,
    )
    assert unavailable_result.outcome == "outcome_unavailable"
    assert not list(market_data_root.rglob("*.json"))

    recovered = observer.materialize_kis_mtf_profiled_forward_outcome_witness(
        contract,
        observer_contract=observer_contract,
        historical_catalogs=historical,
        head_catalogs=complete_head,
        artifact_root=artifact_root,
        repo_root=repository,
        observed_at=_outcome_due(forward_date),
    )
    assert recovered is not None
    assert recovered.witness.status == "target_ready"
    assert (
        observer.append_kis_mtf_profiled_forward_outcome_witness(
            artifact_root=artifact_root,
            market_data_root=market_data_root,
            repo_root=repository,
            contract=contract,
            materialization=recovered,
        ).outcome
        == "appended"
    )


def test_forward_outcome_detects_input_and_outcome_mutation_without_rewriting(
    preflight_binding,
    tmp_path: Path,
) -> None:
    historical_dates = _regular_dates_after(date(2026, 6, 1), count=21)
    forward_date = _regular_dates_after(historical_dates[-1] + timedelta(days=1), count=1)[0]
    historical = _catalogs(historical_dates, marker="historical")
    head = _catalogs((forward_date,), marker="forward", after_cutoff_minutes=15)
    observer_contract = _contract(historical, preflight_binding)
    repository = tmp_path / "repo"
    repository.mkdir()
    artifact_root = tmp_path / "artifacts"
    market_data_root = tmp_path / "market-data"
    _store_input_observation(
        observer_contract,
        historical,
        head,
        forward_date,
        artifact_root,
        repository,
    )
    contract = observer.freeze_kis_mtf_profiled_forward_outcome_contract(observer_contract)

    input_bars = list(head["QQQ/NAS/1m"].bars)
    input_bars[180] = replace(
        input_bars[180],
        volume=input_bars[180].volume + Decimal("1"),
    )
    input_mutated_head = dict(head)
    input_mutated_head["QQQ/NAS/1m"] = _catalog(
        "QQQ",
        "NAS",
        (forward_date,),
        marker="input-mutated",
        bars=tuple(input_bars),
    )
    input_mutated = observer.materialize_kis_mtf_profiled_forward_outcome_witness(
        contract,
        observer_contract=observer_contract,
        historical_catalogs=historical,
        head_catalogs=input_mutated_head,
        artifact_root=artifact_root,
        repo_root=repository,
        observed_at=_outcome_due(forward_date),
    )
    assert input_mutated is not None
    assert input_mutated.witness.status == "input_mutated"
    assert (
        observer.append_kis_mtf_profiled_forward_outcome_witness(
            artifact_root=artifact_root,
            market_data_root=market_data_root,
            repo_root=repository,
            contract=contract,
            materialization=input_mutated,
        ).outcome
        == "input_mutated"
    )
    assert not list(market_data_root.rglob("*.json"))

    baseline = observer.materialize_kis_mtf_profiled_forward_outcome_witness(
        contract,
        observer_contract=observer_contract,
        historical_catalogs=historical,
        head_catalogs=head,
        artifact_root=artifact_root,
        repo_root=repository,
        observed_at=_outcome_due(forward_date),
    )
    assert baseline is not None and baseline.witness.status == "target_ready"
    assert (
        observer.append_kis_mtf_profiled_forward_outcome_witness(
            artifact_root=artifact_root,
            market_data_root=market_data_root,
            repo_root=repository,
            contract=contract,
            materialization=baseline,
        ).outcome
        == "appended"
    )
    stored_outcome = next(artifact_root.rglob("outcomes/*.json")).read_bytes()

    outcome_bars = list(head["SPY/AMS/1m"].bars)
    outcome_bars[360] = replace(
        outcome_bars[360],
        volume=outcome_bars[360].volume + Decimal("1"),
    )
    outcome_mutated_head = dict(head)
    outcome_mutated_head["SPY/AMS/1m"] = _catalog(
        "SPY",
        "AMS",
        (forward_date,),
        marker="outcome-mutated",
        bars=tuple(outcome_bars),
    )
    outcome_mutated = observer.materialize_kis_mtf_profiled_forward_outcome_witness(
        contract,
        observer_contract=observer_contract,
        historical_catalogs=historical,
        head_catalogs=outcome_mutated_head,
        artifact_root=artifact_root,
        repo_root=repository,
        observed_at=_outcome_due(forward_date),
    )
    assert outcome_mutated is not None and outcome_mutated.witness.status == "target_ready"
    conflict = observer.append_kis_mtf_profiled_forward_outcome_witness(
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        repo_root=repository,
        contract=contract,
        materialization=outcome_mutated,
    )
    assert conflict.outcome == "conflict"
    assert next(artifact_root.rglob("outcomes/*.json")).read_bytes() == stored_outcome
    assert len(list(artifact_root.rglob("conflicts/*.json"))) == 1


def test_forward_outcome_ignores_post_window_mutation_and_rejects_repo_raw_root(
    preflight_binding,
    tmp_path: Path,
) -> None:
    historical_dates = _regular_dates_after(date(2026, 6, 1), count=21)
    forward_date = _regular_dates_after(historical_dates[-1] + timedelta(days=1), count=1)[0]
    historical = _catalogs(historical_dates, marker="historical")
    head = _catalogs((forward_date,), marker="forward", after_cutoff_minutes=15)
    observer_contract = _contract(historical, preflight_binding)
    repository = tmp_path / "repo"
    repository.mkdir()
    artifact_root = tmp_path / "artifacts"
    _store_input_observation(
        observer_contract,
        historical,
        head,
        forward_date,
        artifact_root,
        repository,
    )
    contract = observer.freeze_kis_mtf_profiled_forward_outcome_contract(observer_contract)
    baseline = observer.materialize_kis_mtf_profiled_forward_outcome_witness(
        contract,
        observer_contract=observer_contract,
        historical_catalogs=historical,
        head_catalogs=head,
        artifact_root=artifact_root,
        repo_root=repository,
        observed_at=_outcome_due(forward_date),
    )
    assert baseline is not None and baseline.witness.status == "target_ready"
    with pytest.raises(ValueError, match="outside the Git workspace"):
        observer.append_kis_mtf_profiled_forward_outcome_witness(
            artifact_root=artifact_root,
            market_data_root=repository,
            repo_root=repository,
            contract=contract,
            materialization=baseline,
        )

    post_window = _catalogs((forward_date,), marker="post-window", after_cutoff_minutes=16)
    post_window_bars = list(post_window["QQQ/NAS/1m"].bars)
    post_window_bars[375] = replace(
        post_window_bars[375],
        volume=post_window_bars[375].volume + Decimal("1"),
    )
    post_window["QQQ/NAS/1m"] = _catalog(
        "QQQ",
        "NAS",
        (forward_date,),
        marker="post-window-mutated",
        bars=tuple(post_window_bars),
    )
    unchanged = observer.materialize_kis_mtf_profiled_forward_outcome_witness(
        contract,
        observer_contract=observer_contract,
        historical_catalogs=historical,
        head_catalogs=post_window,
        artifact_root=artifact_root,
        repo_root=repository,
        observed_at=_outcome_due(forward_date) + timedelta(minutes=1),
    )
    assert unchanged is not None and unchanged.witness.status == "target_ready"
    assert unchanged.witness.witness_sha256 == baseline.witness.witness_sha256


def test_forward_outcome_excludes_historical_sessions_and_recovers_busy_store(
    preflight_binding,
    tmp_path: Path,
) -> None:
    historical_dates = _regular_dates_after(date(2026, 6, 1), count=21)
    forward_date = _regular_dates_after(historical_dates[-1] + timedelta(days=1), count=1)[0]
    historical = _catalogs(historical_dates, marker="historical")
    head = _catalogs((forward_date,), marker="forward", after_cutoff_minutes=15)
    observer_contract = _contract(historical, preflight_binding)
    contract = observer.freeze_kis_mtf_profiled_forward_outcome_contract(observer_contract)
    repository = tmp_path / "repo"
    repository.mkdir()
    artifact_root = tmp_path / "artifacts"
    market_data_root = tmp_path / "market-data"

    assert (
        observer.materialize_kis_mtf_profiled_forward_outcome_witness(
            contract,
            observer_contract=observer_contract,
            historical_catalogs=historical,
            head_catalogs=historical,
            artifact_root=artifact_root,
            repo_root=repository,
            observed_at=_outcome_due(historical_dates[-1]),
        )
        is None
    )
    _store_input_observation(
        observer_contract,
        historical,
        head,
        forward_date,
        artifact_root,
        repository,
    )
    materialization = observer.materialize_kis_mtf_profiled_forward_outcome_witness(
        contract,
        observer_contract=observer_contract,
        historical_catalogs=historical,
        head_catalogs=head,
        artifact_root=artifact_root,
        repo_root=repository,
        observed_at=_outcome_due(forward_date),
    )
    assert materialization is not None and materialization.witness.status == "target_ready"
    with pytest.raises(ValueError, match="outside the Git workspace"):
        observer.append_kis_mtf_profiled_forward_outcome_witness(
            artifact_root=repository,
            market_data_root=market_data_root,
            repo_root=repository,
            contract=contract,
            materialization=materialization,
        )

    root = observer._forward_outcome_store_root(
        artifact_root=artifact_root,
        repo_root=repository,
        contract_sha256=contract.contract_sha256,
    )
    lock_path = root / ".append.lock"
    lock_path.write_text("busy", encoding="ascii")
    busy = observer.append_kis_mtf_profiled_forward_outcome_witness(
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        repo_root=repository,
        contract=contract,
        materialization=materialization,
    )
    assert busy.outcome == "busy"
    assert not list(market_data_root.rglob("*.json"))
    lock_path.unlink()
    assert (
        observer.append_kis_mtf_profiled_forward_outcome_witness(
            artifact_root=artifact_root,
            market_data_root=market_data_root,
            repo_root=repository,
            contract=contract,
            materialization=materialization,
        ).outcome
        == "appended"
    )


def test_default_preflight_binding_rejects_arbitrary_21_session_history() -> None:
    historical_dates = _regular_dates_after(date(2026, 6, 1), count=21)
    historical = _catalogs(historical_dates, marker="arbitrary")

    with pytest.raises(ValueError, match="frozen completed cache"):
        observer.freeze_kis_mtf_profiled_prospective_observer_contract(
            historical_catalogs=historical,
            code_revision=_sha256("code-r1"),
        )


def test_frozen_preflight_constants_match_the_external_source_safe_artifact() -> None:
    artifact_directory = Path(
        "D:/thericher-v2/model-artifacts/research/"
        "kis-mtf-profiled-feature-input-preflight-v1/local-cache-20260803-r2"
    )
    precommit_path = artifact_directory / "precommit.json"
    summary_path = artifact_directory / "summary.json"
    if not precommit_path.is_file() or not summary_path.is_file():
        pytest.skip("the local frozen profiled-input artifact is unavailable")

    precommit_bytes = precommit_path.read_bytes()
    summary_bytes = summary_path.read_bytes()
    precommit = json.loads(precommit_bytes)
    summary = json.loads(summary_bytes)

    assert _sha256_bytes(precommit_bytes) == (
        observer.KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_PRECOMMIT_SHA256
    )
    assert _sha256_bytes(summary_bytes) == (
        observer.KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_SUMMARY_SHA256
    )
    assert precommit["contract_sha256"] == (
        observer.KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_CONTRACT_SHA256
    )
    assert precommit["source_contract_sha256"] == (
        observer.KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_SOURCE_CONTRACT_SHA256
    )
    assert precommit["source_receipt_sha256"] == (
        observer.KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_SOURCE_RECEIPT_SHA256
    )
    assert precommit["code_revision"] == (
        observer.KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_SOURCE_CODE_REVISION
    )
    assert summary["precommit_sha256"] == (
        observer.KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_PRECOMMIT_SHA256
    )
    assert summary["receipt"]["contract_sha256"] == (
        observer.KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_CONTRACT_SHA256
    )
    assert summary["receipt"]["eligible_session_count"] == 21


def test_conflict_directory_symlink_is_rejected(
    preflight_binding,
    tmp_path: Path,
) -> None:
    historical_dates = _regular_dates_after(date(2026, 6, 1), count=21)
    forward_date = _regular_dates_after(historical_dates[-1] + timedelta(days=1), count=1)[0]
    historical = _catalogs(historical_dates, marker="historical")
    contract = _contract(historical, preflight_binding)
    baseline_head = _catalogs((forward_date,), marker="head-a")
    baseline = _observation(contract, historical, baseline_head, forward_date)
    assert baseline is not None

    changed_bars = list(baseline_head["SPY/AMS/1m"].bars)
    changed_bars[180] = replace(
        changed_bars[180],
        volume=changed_bars[180].volume + Decimal("1"),
    )
    changed_head = dict(baseline_head)
    changed_head["SPY/AMS/1m"] = _catalog(
        "SPY",
        "AMS",
        (forward_date,),
        marker="head-conflict",
        bars=tuple(changed_bars),
    )
    changed = _observation(contract, historical, changed_head, forward_date)
    assert changed is not None

    repository = tmp_path / "repo"
    repository.mkdir()
    artifact_root = tmp_path / "artifacts"
    observer.append_kis_mtf_profiled_prospective_observation(
        artifact_root=artifact_root,
        repo_root=repository,
        contract=contract,
        observation=baseline,
    )
    conflict_directory = next(path for path in artifact_root.rglob("conflicts") if path.is_dir())
    conflict_directory.rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        conflict_directory.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("the current Windows environment does not permit test symlinks")

    with pytest.raises(ValueError, match="symlink"):
        observer.append_kis_mtf_profiled_prospective_observation(
            artifact_root=artifact_root,
            repo_root=repository,
            contract=contract,
            observation=changed,
        )


def test_core_import_does_not_load_execution_or_transport_modules() -> None:
    script = """
import sys
import typing
import thericher_v2.data.kis_mtf_profiled_prospective_observer
import thericher_v2.data.kis_intraday_mtf_availability
typing.get_type_hints(thericher_v2.data.kis_mtf_profiled_prospective_observer.run_kis_mtf_profiled_prospective_observer)
typing.get_type_hints(thericher_v2.data.kis_mtf_profiled_prospective_observer.run_kis_mtf_profiled_forward_outcome_witness)
typing.get_type_hints(thericher_v2.data.kis_intraday_mtf_availability.load_kis_intraday_mtf_availability_catalogs)
for name in sys.modules:
    if name.startswith("thericher_v2.execution"):
        raise SystemExit(name)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_capture_cycle_selects_exactly_one_regular_session_slot() -> None:
    session_date = _regular_dates_after(date(2026, 8, 3), count=1)[0]
    cutoff = _cutoff(session_date)

    assert (
        capture_cycle.select_profiled_mtf_forward_capture_cycle_action(
            cutoff - timedelta(microseconds=1)
        )
        == "outside_cycle_slot"
    )
    assert (
        capture_cycle.select_profiled_mtf_forward_capture_cycle_action(cutoff)
        == "input_observer"
    )
    assert (
        capture_cycle.select_profiled_mtf_forward_capture_cycle_action(
            _outcome_due(session_date) - timedelta(microseconds=1)
        )
        == "input_observer"
    )
    assert (
        capture_cycle.select_profiled_mtf_forward_capture_cycle_action(
            _outcome_due(session_date)
        )
        == "outcome_witness"
    )


def test_capture_cycle_runs_input_then_outcome_with_d_only_raw_snapshot(
    preflight_binding,
    tmp_path: Path,
) -> None:
    historical_dates = _regular_dates_after(date(2026, 6, 1), count=21)
    forward_date = _regular_dates_after(historical_dates[-1] + timedelta(days=1), count=1)[0]
    historical = _catalogs(historical_dates, marker="historical")
    head = _catalogs((forward_date,), marker="head", after_cutoff_minutes=15)
    preflight_binding(historical)
    repository = tmp_path / "repo"
    repository.mkdir()
    historical_root = tmp_path / "historical"
    head_root = tmp_path / "head"
    artifact_root = tmp_path / "artifacts"
    market_data_root = tmp_path / "market-data"

    def local_loader(*, cache_root: Path, **_kwargs: object) -> dict[str, CatalogedBars]:
        assert cache_root in {historical_root, head_root}
        return historical if cache_root == historical_root else head

    input_result = capture_cycle.run_profiled_mtf_forward_capture_cycle(
        historical_cache_root=historical_root,
        head_cache_root=head_root,
        market_data_root=market_data_root,
        artifact_root=artifact_root,
        repo_root=repository,
        code_revision=_sha256("code-r1"),
        observed_at=_cutoff(forward_date),
        catalog_loader=local_loader,
    )
    outcome_result = capture_cycle.run_profiled_mtf_forward_capture_cycle(
        historical_cache_root=historical_root,
        head_cache_root=head_root,
        market_data_root=market_data_root,
        artifact_root=artifact_root,
        repo_root=repository,
        code_revision=_sha256("code-r1"),
        observed_at=_outcome_due(forward_date),
        catalog_loader=local_loader,
    )

    assert input_result.action == "input_observer"
    assert input_result.status == "observed"
    assert outcome_result.action == "outcome_witness"
    assert outcome_result.status == "appended"
    assert len(list(market_data_root.rglob("*.json"))) == 1
    rendered = json.dumps(outcome_result.safe_payload(), sort_keys=True)
    for forbidden in ("QQQ", "SPY", "2026-", "100.5", "D:/market_data"):
        assert forbidden not in rendered


def test_capture_cycle_preserves_retry_conflict_and_input_mutation_recovery(
    preflight_binding,
    tmp_path: Path,
) -> None:
    historical_dates = _regular_dates_after(date(2026, 6, 1), count=21)
    forward_date = _regular_dates_after(historical_dates[-1] + timedelta(days=1), count=1)[0]
    historical = _catalogs(historical_dates, marker="historical")
    baseline_head = _catalogs((forward_date,), marker="head", after_cutoff_minutes=15)
    changed_bars = list(baseline_head["SPY/AMS/1m"].bars)
    changed_bars[180] = replace(
        changed_bars[180],
        volume=changed_bars[180].volume + Decimal("1"),
    )
    changed_head = dict(baseline_head)
    changed_head["SPY/AMS/1m"] = _catalog(
        "SPY",
        "AMS",
        (forward_date,),
        marker="changed-head",
        bars=tuple(changed_bars),
    )
    preflight_binding(historical)
    repository = tmp_path / "repo"
    repository.mkdir()
    historical_root = tmp_path / "historical"
    head_root = tmp_path / "head"
    artifact_root = tmp_path / "artifacts"
    market_data_root = tmp_path / "market-data"
    active_head = baseline_head

    def local_loader(*, cache_root: Path, **_kwargs: object) -> dict[str, CatalogedBars]:
        assert cache_root in {historical_root, head_root}
        return historical if cache_root == historical_root else active_head

    first = capture_cycle.run_profiled_mtf_forward_capture_cycle(
        historical_cache_root=historical_root,
        head_cache_root=head_root,
        market_data_root=market_data_root,
        artifact_root=artifact_root,
        repo_root=repository,
        code_revision=_sha256("code-r1"),
        observed_at=_cutoff(forward_date),
        catalog_loader=local_loader,
    )
    duplicate = capture_cycle.run_profiled_mtf_forward_capture_cycle(
        historical_cache_root=historical_root,
        head_cache_root=head_root,
        market_data_root=market_data_root,
        artifact_root=artifact_root,
        repo_root=repository,
        code_revision=_sha256("code-r1"),
        observed_at=_cutoff(forward_date),
        catalog_loader=local_loader,
    )
    active_head = changed_head
    conflict = capture_cycle.run_profiled_mtf_forward_capture_cycle(
        historical_cache_root=historical_root,
        head_cache_root=head_root,
        market_data_root=market_data_root,
        artifact_root=artifact_root,
        repo_root=repository,
        code_revision=_sha256("code-r1"),
        observed_at=_cutoff(forward_date),
        catalog_loader=local_loader,
    )
    mutated = capture_cycle.run_profiled_mtf_forward_capture_cycle(
        historical_cache_root=historical_root,
        head_cache_root=head_root,
        market_data_root=market_data_root,
        artifact_root=artifact_root,
        repo_root=repository,
        code_revision=_sha256("code-r1"),
        observed_at=_outcome_due(forward_date),
        catalog_loader=local_loader,
    )

    assert first.status == "observed"
    assert duplicate.status == "duplicate"
    assert conflict.status == "conflict"
    assert mutated.status == "input_mutated"
    assert not list(market_data_root.rglob("*.json"))


def test_capture_cycle_outside_slot_never_opens_a_cache_loader(tmp_path: Path) -> None:
    session_date = _regular_dates_after(date(2026, 8, 3), count=1)[0]
    repository = tmp_path / "repo"
    repository.mkdir()

    def forbidden_loader(**_kwargs: object) -> dict[str, CatalogedBars]:
        raise AssertionError("outside capture-cycle slot must not load cache data")

    result = capture_cycle.run_profiled_mtf_forward_capture_cycle(
        historical_cache_root=tmp_path / "historical",
        head_cache_root=tmp_path / "head",
        market_data_root=tmp_path / "market-data",
        artifact_root=tmp_path / "artifacts",
        repo_root=repository,
        code_revision=_sha256("code-r1"),
        observed_at=_cutoff(session_date) - timedelta(minutes=1),
        catalog_loader=forbidden_loader,
    )

    assert result.action == "outside_cycle_slot"
    assert result.status == "outside_cycle_slot"
    assert result.safe_payload() == {
        "kind": "profiled-mtf-forward-capture-cycle-v1",
        "action": "outside_cycle_slot",
        "status": "outside_cycle_slot",
    }
    assert not (tmp_path / "artifacts").exists()
    assert not (tmp_path / "market-data").exists()


def test_capture_cycle_import_stays_local_only() -> None:
    source = Path(capture_cycle.__file__).read_text(encoding="utf-8").lower()
    for forbidden in (
        "os.environ",
        "socket",
        "urllib",
        "requests",
        "local_paper",
        "kis_live",
        "torch",
    ):
        assert forbidden not in source
    script = """
import sys
import thericher_v2.data.profiled_mtf_forward_capture_cycle
for name in sys.modules:
    if name.startswith('thericher_v2.execution') or name == 'torch' or name.startswith('torch.'):
        raise SystemExit(name)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def _contract(
    historical: dict[str, CatalogedBars],
    preflight_binding,
) -> observer.KisMtfProfiledProspectiveObserverContract:
    preflight_binding(historical)
    return observer.freeze_kis_mtf_profiled_prospective_observer_contract(
        historical_catalogs=historical,
        code_revision=_sha256("code-r1"),
    )


def _store_input_observation(
    contract: observer.KisMtfProfiledProspectiveObserverContract,
    historical: dict[str, CatalogedBars],
    head: dict[str, CatalogedBars],
    session_date: date,
    artifact_root: Path,
    repository: Path,
) -> observer.KisMtfProfiledProspectiveObservation:
    input_observation = _observation(contract, historical, head, session_date)
    assert input_observation is not None and input_observation.status == "observed"
    assert (
        observer.append_kis_mtf_profiled_prospective_observation(
            artifact_root=artifact_root,
            repo_root=repository,
            contract=contract,
            observation=input_observation,
        ).outcome
        == "appended"
    )
    return input_observation


def _observation(
    contract: observer.KisMtfProfiledProspectiveObserverContract,
    historical: dict[str, CatalogedBars],
    head: dict[str, CatalogedBars],
    session_date: date,
) -> observer.KisMtfProfiledProspectiveObservation | None:
    return observer.materialize_kis_mtf_profiled_prospective_observation(
        contract,
        historical_catalogs=historical,
        head_catalogs=head,
        observed_at=_observed_after_cutoff(session_date),
    )


def _catalogs(
    session_dates: tuple[date, ...],
    *,
    marker: str,
    after_cutoff_minutes: int = 0,
) -> dict[str, CatalogedBars]:
    return {
        "QQQ/NAS/1m": _catalog(
            "QQQ",
            "NAS",
            session_dates,
            marker=f"{marker}-qqq",
            after_cutoff_minutes=after_cutoff_minutes,
        ),
        "SPY/AMS/1m": _catalog(
            "SPY",
            "AMS",
            session_dates,
            marker=f"{marker}-spy",
            after_cutoff_minutes=after_cutoff_minutes,
        ),
    }


def _catalog(
    symbol: str,
    exchange: str,
    session_dates: tuple[date, ...],
    *,
    marker: str,
    bars: tuple[Bar, ...] | None = None,
    after_cutoff_minutes: int = 0,
) -> CatalogedBars:
    return _cataloged_bars_from_verified_loader(
        dataset_id=f"kis.paper.private.intraday.{symbol.lower()}.{exchange.lower()}.m1.v1",
        dataset_hash=_sha256(marker),
        source_path=Path(f"D:/market_data/{symbol.lower()}-{exchange.lower()}.json"),
        bars=bars
        if bars is not None
        else _bars(symbol, session_dates, after_cutoff_minutes=after_cutoff_minutes),
    )


def _bars(
    symbol: str,
    session_dates: tuple[date, ...],
    *,
    after_cutoff_minutes: int,
) -> tuple[Bar, ...]:
    base = Decimal("100") if symbol == "QQQ" else Decimal("200")
    rows: list[Bar] = []
    for session_date in session_dates:
        session = us_equity_2026_session(session_date)
        assert session is not None and session.kind == "regular"
        for offset in range(360 + after_cutoff_minutes):
            price = base + Decimal(offset) / Decimal("1000")
            rows.append(
                Bar(
                    symbol=symbol,
                    market="US",
                    timeframe=Timeframe.M1,
                    start_ts=session.window.open_ts + timedelta(minutes=offset),
                    open=price,
                    high=price + Decimal("1"),
                    low=price - Decimal("1"),
                    close=price + Decimal("0.5"),
                    volume=Decimal("100") + Decimal(offset),
                    complete=True,
                )
            )
    return tuple(rows)


def _regular_dates_after(start: date, *, count: int) -> tuple[date, ...]:
    dates: list[date] = []
    candidate = start
    while len(dates) < count:
        session = us_equity_2026_session(candidate)
        if session is not None and session.kind == "regular":
            dates.append(candidate)
        candidate += timedelta(days=1)
    return tuple(dates)


def _observed_after_cutoff(session_date: date):
    return _cutoff(session_date) + timedelta(minutes=1)


def _outcome_due(session_date: date):
    return _cutoff(session_date) + timedelta(minutes=15)


def _cutoff(session_date: date):
    session = us_equity_2026_session(session_date)
    assert session is not None and session.kind == "regular"
    return session.window.open_ts + timedelta(hours=6)


def _sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _forbid(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("network access is forbidden")


class _DenyEnvironment(dict[str, str]):
    def get(self, *_args: object, **_kwargs: object) -> str:
        raise AssertionError("environment access is forbidden")


@pytest.fixture
def preflight_binding(monkeypatch: pytest.MonkeyPatch):
    def bind(historical: dict[str, CatalogedBars]) -> None:
        source_code_revision = _sha256("preflight-code-r1")
        source_contract = availability.freeze_kis_intraday_mtf_availability_contract(
            historical,
            code_revision=source_code_revision,
        )
        source_receipt = availability.materialize_kis_intraday_mtf_availability(
            source_contract,
            historical,
        )
        monkeypatch.setattr(
            observer,
            "KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_SUMMARY_SHA256",
            _sha256("preflight-summary-r1"),
        )
        monkeypatch.setattr(
            observer,
            "KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_SOURCE_CODE_REVISION",
            source_code_revision,
        )
        monkeypatch.setattr(
            observer,
            "KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_SOURCE_CONTRACT_SHA256",
            source_contract.contract_sha256,
        )
        monkeypatch.setattr(
            observer,
            "KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_SOURCE_RECEIPT_SHA256",
            source_receipt.receipt_sha256,
        )

    return bind
