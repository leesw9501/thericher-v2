"""Focused tests for the pure QQQ/SPY daily joint event-window contract."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import socket
import subprocess
import sys
import urllib.request
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.kis_daily_joint_event_window_contract import (
    DEFAULT_KIS_DAILY_JOINT_EVENT_WINDOW_SPEC,
    KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE,
    KisDailyJointEventWindowSpec,
    build_kis_daily_joint_event_window_contract,
    write_kis_daily_joint_event_window_contract,
)


def _sha256(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("ascii")).hexdigest()


def _spec(*, minimum_eligible_decision_count: int = 1) -> KisDailyJointEventWindowSpec:
    return KisDailyJointEventWindowSpec(
        feature_session_count=3,
        feature_return_prior_session_count=1,
        label_horizon_session_count=2,
        pre_validation_gap_session_count=5,
        validation_session_count=10,
        fold_count=3,
        initial_development_session_count=20,
        minimum_eligible_decision_count=minimum_eligible_decision_count,
    )


def _inputs(
    tmp_path: Path,
    *,
    event_specs: tuple[tuple[str, int], ...] = (("QQQ", 5),),
    session_count: int = 70,
) -> tuple[SimpleNamespace, SimpleNamespace, SimpleNamespace]:
    external_root = tmp_path / "external"
    sessions = tuple(date(2020, 1, 1) + timedelta(days=index) for index in range(session_count))
    catalog_dataset_hash = _sha256("catalog-dataset")
    catalog_index_hash = _sha256("catalog-index")
    sidecar_dataset_hash = _sha256("sidecar-dataset")
    sidecar_manifest_hash = _sha256("sidecar-manifest")
    catalog = SimpleNamespace(
        dataset_hash=catalog_dataset_hash,
        index_hash=catalog_index_hash,
        index_path=external_root / "catalog" / "index.json",
        bars_by_symbol={"QQQ": object(), "SPY": object()},
        common_sessions=sessions,
    )
    sidecar = SimpleNamespace(
        snapshot_dir=external_root / "sidecar",
        dataset_hash=sidecar_dataset_hash,
        manifest_hash=sidecar_manifest_hash,
        catalog_dataset_hash=catalog_dataset_hash,
        catalog_index_hash=catalog_index_hash,
        events=tuple(
            SimpleNamespace(
                symbol=symbol,
                mapped_kis_session_date=sessions[index],
                event_kind="cash_distribution",
            )
            for symbol, index in event_specs
        ),
    )
    audit = SimpleNamespace(
        path=external_root / "audit.json",
        artifact_sha256=_sha256("audit"),
        mask_identity=_sha256("audit-mask"),
        partition_identity=_sha256("audit-partition"),
        lineage=SimpleNamespace(
            catalog_dataset_hash=catalog_dataset_hash,
            catalog_index_hash=catalog_index_hash,
            sidecar_dataset_hash=sidecar_dataset_hash,
            sidecar_manifest_hash=sidecar_manifest_hash,
            session_dates_sha256=_session_dates_hash(sessions),
        ),
    )
    return catalog, sidecar, audit


def _session_dates_hash(sessions: tuple[date, ...]) -> str:
    payload = "\n".join(session.isoformat() for session in sessions).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _contract(
    tmp_path: Path,
    *,
    event_specs: tuple[tuple[str, int], ...] = (("QQQ", 5),),
    spec: KisDailyJointEventWindowSpec | None = None,
    session_count: int = 70,
    model_execution_review: str | None = None,
):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    catalog, sidecar, audit = _inputs(
        tmp_path,
        event_specs=event_specs,
        session_count=session_count,
    )
    kwargs = {}
    if model_execution_review is not None:
        kwargs["model_execution_review"] = model_execution_review
    return build_kis_daily_joint_event_window_contract(
        catalog=catalog,
        sidecar=sidecar,
        event_boundary_audit=audit,
        created_at_utc=datetime(2026, 7, 27, tzinfo=UTC),
        repo_root=repo_root,
        spec=spec or _spec(),
        **kwargs,
    )


def test_joint_events_exclude_both_symbols_across_full_feature_label_span(tmp_path: Path) -> None:
    contract = _contract(
        tmp_path,
        event_specs=(("QQQ", 29), ("SPY", 30)),
        spec=replace(_spec(), validation_session_count=20),
        session_count=100,
    )
    validation = contract.folds[0].validation_eligible_decision_indices

    # With the compact test geometry, t-3 is the real predecessor dependency.
    for decision_index in (28, 29, 30, 31, 32, 33):
        assert decision_index not in validation

    event_indices = {29, 30}
    for decision_index in validation:
        assert not event_indices.intersection(range(decision_index - 3, decision_index + 3))


def test_expanding_fold_geometry_preserves_the_final_unused_tail(tmp_path: Path) -> None:
    contract = _contract(tmp_path)

    assert [
        (
            fold.development_start_index,
            fold.development_end_index,
            fold.pre_validation_gap_start_index,
            fold.pre_validation_gap_end_index,
            fold.validation_start_index,
            fold.validation_end_index,
        )
        for fold in contract.folds
    ] == [
        (0, 20, 20, 25, 25, 35),
        (0, 35, 35, 40, 40, 50),
        (0, 50, 50, 55, 55, 65),
    ]
    assert contract.final_unused_tail_start_index == 65
    assert len(contract.sessions) - contract.final_unused_tail_start_index == 5


def test_default_contract_masks_the_real_twenty_session_predecessor_boundary(
    tmp_path: Path,
) -> None:
    contract = _contract(
        tmp_path,
        event_specs=(
            ("QQQ", 3805),
            ("SPY", 3860),
            ("QQQ", 3891),
            ("SPY", 3922),
        ),
        spec=DEFAULT_KIS_DAILY_JOINT_EVENT_WINDOW_SPEC,
        session_count=4756,
    )

    assert [fold.validation_start_index for fold in contract.folds] == [3805, 4079, 4353]
    assert [fold.validation_end_index for fold in contract.folds] == [4057, 4331, 4605]
    assert contract.final_unused_tail_start_index == 4605
    assert len(contract.sessions) - contract.final_unused_tail_start_index == 151
    first_validation = contract.folds[0].validation_eligible_decision_indices
    assert 3825 not in first_validation  # Its first return reads the event at t-20.
    assert 3860 not in first_validation  # Event at the decision session t.
    assert 3890 not in first_validation  # Event at the entry session t+1.
    assert 3920 not in first_validation  # Event at the exit/label session t+2.
    assert 3826 in first_validation


def test_contract_rejects_insufficient_post_mask_eligibility(tmp_path: Path) -> None:
    spec = _spec(minimum_eligible_decision_count=5)
    contract_inputs = _inputs(
        tmp_path,
        event_specs=tuple(("QQQ", index) for index in range(20, 70)),
    )
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(ValueError, match="too few eligible"):
        build_kis_daily_joint_event_window_contract(
            catalog=contract_inputs[0],
            sidecar=contract_inputs[1],
            event_boundary_audit=contract_inputs[2],
            created_at_utc=datetime(2026, 7, 27, tzinfo=UTC),
            repo_root=repo_root,
            spec=spec,
        )


def test_contract_rejects_deterministic_eligibility_tampering(tmp_path: Path) -> None:
    contract = _contract(tmp_path)
    first_fold = contract.folds[0]
    tampered_fold = replace(
        first_fold,
        validation_eligible_decision_indices=first_fold.validation_eligible_decision_indices[1:],
    )

    with pytest.raises(ValueError, match="eligibility is not deterministic"):
        replace(contract, folds=(tampered_fold, *contract.folds[1:]))


def test_contract_rejects_lineage_drift_and_repository_inputs(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    catalog, sidecar, audit = _inputs(tmp_path)
    drifted_sidecar = SimpleNamespace(**vars(sidecar))
    drifted_sidecar.catalog_dataset_hash = _sha256("different-catalog")

    with pytest.raises(ValueError, match="sidecar lineage"):
        build_kis_daily_joint_event_window_contract(
            catalog=catalog,
            sidecar=drifted_sidecar,
            event_boundary_audit=audit,
            created_at_utc=datetime(2026, 7, 27, tzinfo=UTC),
            repo_root=repo_root,
            spec=_spec(),
        )

    catalog.index_path = repo_root / "index.json"
    with pytest.raises(ValueError, match="input must stay outside"):
        build_kis_daily_joint_event_window_contract(
            catalog=catalog,
            sidecar=sidecar,
            event_boundary_audit=audit,
            created_at_utc=datetime(2026, 7, 27, tzinfo=UTC),
            repo_root=repo_root,
            spec=_spec(),
        )


def test_contract_rejects_a_sidecar_event_kind_outside_the_pinned_schema(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    catalog, sidecar, audit = _inputs(tmp_path)
    sidecar.events = (
        SimpleNamespace(
            symbol="QQQ",
            mapped_kis_session_date=catalog.common_sessions[5],
            event_kind="unqualified_event",
        ),
    )

    with pytest.raises(ValueError, match="sidecar event is incompatible"):
        build_kis_daily_joint_event_window_contract(
            catalog=catalog,
            sidecar=sidecar,
            event_boundary_audit=audit,
            created_at_utc=datetime(2026, 7, 27, tzinfo=UTC),
            repo_root=repo_root,
            spec=_spec(),
        )


def test_writer_is_external_immutable_source_safe_and_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _contract(
        tmp_path,
        model_execution_review=KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE,
    )
    artifact_root = tmp_path / "artifacts"
    destination = artifact_root / "contracts" / "joint.json"

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network or credential access is not allowed")

    with monkeypatch.context() as blocked:
        blocked.setattr(socket, "create_connection", fail)
        blocked.setattr(urllib.request, "urlopen", fail)
        blocked.setattr(os, "getenv", fail)
        artifact = write_kis_daily_joint_event_window_contract(
            destination=destination,
            contract=contract,
            artifact_root=artifact_root,
            repo_root=tmp_path / "repo",
        )

    assert artifact.path == destination.resolve()
    assert artifact.content_hash == "sha256:" + hashlib.sha256(destination.read_bytes()).hexdigest()
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["scope"]["offline_only"] is True
    assert payload["scope"]["model_execution_eligible"] is False
    assert payload["scope"]["model_execution_review"] == "review_unavailable"
    assert payload["spec"]["target_policy_id"].endswith("t_plus_2_v1")
    assert payload["event_boundary_audit"]["legacy_pair_mask_provenance_only"] is True
    assert payload["scope"]["generic_multi_fold_campaign_contract_eligible"] is False
    assert payload["scope"]["raw_market_data_persisted"] is False
    assert payload["scope"]["provider_response_persisted"] is False
    assert payload["scope"]["credentials_persisted"] is False
    serialized = json.dumps(payload).lower()
    assert '"close"' not in serialized
    assert '"order"' not in serialized
    assert '"credential"' not in serialized

    with pytest.raises(FileExistsError):
        write_kis_daily_joint_event_window_contract(
            destination=destination,
            contract=contract,
            artifact_root=artifact_root,
            repo_root=tmp_path / "repo",
        )
    with pytest.raises(ValueError, match="outside the Git workspace"):
        write_kis_daily_joint_event_window_contract(
            destination=tmp_path / "repo" / "joint.json",
            contract=contract,
            artifact_root=tmp_path / "repo" / "artifacts",
            repo_root=tmp_path / "repo",
        )
    with pytest.raises(ValueError, match="under the artifact root"):
        write_kis_daily_joint_event_window_contract(
            destination=tmp_path / "outside" / "joint.json",
            contract=contract,
            artifact_root=artifact_root,
            repo_root=tmp_path / "repo",
        )

    linked_parent = artifact_root / "linked-repository"
    try:
        linked_parent.symlink_to(tmp_path / "repo", target_is_directory=True)
    except OSError:
        pytest.skip("creating a test directory symlink is unavailable")
    with pytest.raises(ValueError, match="under the artifact root"):
        write_kis_daily_joint_event_window_contract(
            destination=linked_parent / "joint.json",
            contract=contract,
            artifact_root=artifact_root,
            repo_root=tmp_path / "repo",
        )


def test_fresh_import_has_no_execution_route_and_no_runtime_data_import() -> None:
    code = """\
import importlib
import sys
importlib.import_module('thericher_v2.kis_daily_joint_event_window_contract')
assert not [name for name in sys.modules if name.startswith('thericher_v2.execution')]
assert not [name for name in sys.modules if name.startswith('thericher_v2.data')]
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0, result.stderr

    module_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "thericher_v2"
        / "kis_daily_joint_event_window_contract.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imports = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ] + [
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    ]
    assert not any(
        term in imported
        for imported in imports
        for term in ("execution", "broker", "kis_market_data", "tiingo", "order")
    )


def test_script_help_stays_on_the_pure_import_path() -> None:
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "prepare_kis_daily_joint_event_window_contract.py"
    )
    code = f"""\
import runpy
import sys
namespace = runpy.run_path({str(script_path)!r}, run_name='joint_event_contract_help_test')
try:
    namespace['main'](['--help'])
except SystemExit as error:
    assert error.code == 0
else:
    raise AssertionError('expected --help to exit')
assert not [name for name in sys.modules if name.startswith('thericher_v2.data')]
assert not [name for name in sys.modules if name.startswith('thericher_v2.execution')]
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0, result.stderr
