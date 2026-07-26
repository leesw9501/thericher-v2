"""Focused tests for the non-executable QQQ/SPY D1 fold materializer."""

from __future__ import annotations

import ast
import hashlib
import os
import socket
import subprocess
import sys
import urllib.request
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_daily import KisPaperPrivateDailyCatalog
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.kis_daily_joint_event_d1_materializer import (
    KIS_DAILY_JOINT_EVENT_D1_ADJUSTMENT_MODE,
    KIS_DAILY_JOINT_EVENT_D1_CATALOG_ID,
    _assert_source_safe,
    build_kis_daily_joint_event_d1_materializer,
    write_kis_daily_joint_event_d1_materializer_receipt,
)
from thericher_v2.kis_daily_joint_event_window_contract import (
    DEFAULT_KIS_DAILY_JOINT_EVENT_WINDOW_SPEC,
    KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE,
    build_kis_daily_joint_event_window_contract,
    load_verified_kis_daily_joint_event_fold_input,
    load_verified_kis_daily_joint_event_window_contract,
    select_kis_daily_joint_event_fold_input,
    write_kis_daily_joint_event_fold_input,
    write_kis_daily_joint_event_window_contract,
)


def _sha256(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("ascii")).hexdigest()


def _session_dates_hash(sessions: tuple[date, ...]) -> str:
    return "sha256:" + hashlib.sha256(
        "\n".join(session.isoformat() for session in sessions).encode("utf-8")
    ).hexdigest()


def _contract(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    external_root = tmp_path / "external"
    sessions = tuple(date(2000, 1, 1) + timedelta(days=index) for index in range(4756))
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
            for symbol, index in (("QQQ", 3805), ("SPY", 3860), ("QQQ", 3891), ("SPY", 3922))
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
    return build_kis_daily_joint_event_window_contract(
        catalog=catalog,
        sidecar=sidecar,
        event_boundary_audit=audit,
        created_at_utc=datetime(2026, 7, 27, tzinfo=UTC),
        repo_root=repo_root,
        spec=DEFAULT_KIS_DAILY_JOINT_EVENT_WINDOW_SPEC,
        model_execution_review=KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE,
    )


def _verified_fold_artifact(tmp_path: Path):
    contract = _contract(tmp_path)
    artifact_root = tmp_path / "artifacts"
    parent = write_kis_daily_joint_event_window_contract(
        destination=artifact_root / "contracts" / "parent.json",
        contract=contract,
        artifact_root=artifact_root,
        repo_root=tmp_path / "repo",
    )
    verified_parent = load_verified_kis_daily_joint_event_window_contract(
        path=parent.path,
        expected_artifact_sha256=parent.content_hash,
        expected_contract_identity=contract.contract_identity,
        rebuilt_contract=contract,
        artifact_root=artifact_root,
        repo_root=tmp_path / "repo",
    )
    fold_input = select_kis_daily_joint_event_fold_input(
        verified_parent,
        fold_id="expanding-1",
    )
    written = write_kis_daily_joint_event_fold_input(
        destination=artifact_root / "contracts" / "fold.json",
        fold_input=fold_input,
        artifact_root=artifact_root,
        repo_root=tmp_path / "repo",
    )
    verified_fold = load_verified_kis_daily_joint_event_fold_input(
        path=written.path,
        expected_artifact_sha256=written.content_hash,
        expected_fold_input_identity=fold_input.fold_input_identity,
        expected_fold_input=fold_input,
        artifact_root=artifact_root,
        repo_root=tmp_path / "repo",
    )
    return contract, artifact_root, verified_fold


def _catalog(
    contract: object,
    tmp_path: Path,
    *,
    qqq_close_overrides: dict[int, Decimal] | None = None,
    qqq_open_overrides: dict[int, Decimal] | None = None,
) -> KisPaperPrivateDailyCatalog:
    close_overrides = qqq_close_overrides or {}
    open_overrides = qqq_open_overrides or {}
    bars_by_symbol: dict[str, object] = {}
    for symbol, base in (("QQQ", Decimal("100")), ("SPY", Decimal("200"))):
        bars: list[Bar] = []
        for index, session in enumerate(contract.sessions):
            baseline_open = base + Decimal(index) / Decimal("10")
            opening = (
                open_overrides.get(index, baseline_open)
                if symbol == "QQQ"
                else baseline_open
            )
            closing = (
                close_overrides.get(index, opening + Decimal("0.5"))
                if symbol == "QQQ"
                else opening + Decimal("0.5")
            )
            bars.append(
                Bar(
                    symbol=symbol,
                    market="US",
                    timeframe=Timeframe.D1,
                    start_ts=datetime(session.year, session.month, session.day, tzinfo=UTC),
                    open=opening,
                    high=max(opening, closing) + Decimal("1"),
                    low=min(opening, closing) - Decimal("1"),
                    close=closing,
                    volume=Decimal("1000"),
                    complete=True,
                )
            )
        bars_by_symbol[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id=KIS_DAILY_JOINT_EVENT_D1_CATALOG_ID,
            dataset_hash=contract.catalog_dataset_hash,
            source_path=tmp_path / "external" / "catalog" / "index.json",
            bars=tuple(bars),
        )
    return KisPaperPrivateDailyCatalog(
        dataset_id=KIS_DAILY_JOINT_EVENT_D1_CATALOG_ID,
        dataset_hash=contract.catalog_dataset_hash,
        index_hash=contract.catalog_index_hash,
        index_path=tmp_path / "external" / "catalog" / "index.json",
        source_root=tmp_path / "external",
        adjustment_mode=KIS_DAILY_JOINT_EVENT_D1_ADJUSTMENT_MODE,
        bars_by_symbol=MappingProxyType(bars_by_symbol),
        common_sessions=contract.sessions,
        raw_price_limitations=("unit-only",),
    )


def test_materializer_preserves_the_exact_t_minus_20_to_t_plus_2_window(
    tmp_path: Path,
) -> None:
    contract, _artifact_root, verified_fold = _verified_fold_artifact(tmp_path)
    source = _catalog(contract, tmp_path)
    materializer = build_kis_daily_joint_event_d1_materializer(
        fold_input_artifact=verified_fold,
        catalog=source,
    )
    decision_index = verified_fold.fold_input.validation_eligible_decision_indices[0]

    window = materializer.materialize(phase="validation", decision_index=decision_index)

    assert materializer.eligible_decision_indices("validation") == (
        verified_fold.fold_input.validation_eligible_decision_indices
    )
    assert window.predecessor_index == decision_index - 20
    assert window.feature_start_index == decision_index - 19
    assert window.feature_end_index == decision_index
    assert len(window.feature_rows) == 20
    assert window.feature_rows[0].session == source.common_sessions[decision_index - 19]
    assert window.target_references.entry_index == decision_index + 1
    assert window.target_references.exit_index == decision_index + 2
    assert window.target_references.entry_start.date() == source.common_sessions[decision_index + 1]
    assert window.target_references.exit_start.date() == source.common_sessions[decision_index + 2]


def test_materializer_keeps_future_target_references_out_of_features(tmp_path: Path) -> None:
    contract, _artifact_root, verified_fold = _verified_fold_artifact(tmp_path)
    decision_index = verified_fold.fold_input.validation_eligible_decision_indices[0]
    baseline = build_kis_daily_joint_event_d1_materializer(
        fold_input_artifact=verified_fold,
        catalog=_catalog(contract, tmp_path),
    )
    shifted_target = build_kis_daily_joint_event_d1_materializer(
        fold_input_artifact=verified_fold,
        catalog=_catalog(
            contract,
            tmp_path,
            qqq_open_overrides={decision_index + 2: Decimal("9999")},
        ),
    )
    shifted_predecessor = build_kis_daily_joint_event_d1_materializer(
        fold_input_artifact=verified_fold,
        catalog=_catalog(
            contract,
            tmp_path,
            qqq_close_overrides={decision_index - 20: Decimal("9999")},
        ),
    )

    baseline_window = baseline.materialize(phase="validation", decision_index=decision_index)
    target_window = shifted_target.materialize(phase="validation", decision_index=decision_index)
    predecessor_window = shifted_predecessor.materialize(
        phase="validation",
        decision_index=decision_index,
    )

    assert baseline_window.feature_rows == target_window.feature_rows
    assert (
        baseline_window.target_references.exit_open_by_symbol["QQQ"]
        != target_window.target_references.exit_open_by_symbol["QQQ"]
    )
    assert (
        baseline_window.feature_rows[0].qqq_completed_close_return
        != predecessor_window.feature_rows[0].qqq_completed_close_return
    )
    assert baseline_window.feature_rows[1:] == predecessor_window.feature_rows[1:]


def test_materializer_rejects_sparse_holes_and_unverified_or_mismatched_inputs(
    tmp_path: Path,
) -> None:
    contract, _artifact_root, verified_fold = _verified_fold_artifact(tmp_path)
    source = _catalog(contract, tmp_path)
    materializer = build_kis_daily_joint_event_d1_materializer(
        fold_input_artifact=verified_fold,
        catalog=source,
    )
    fold = verified_fold.fold_input
    sparse_hole = next(
        index
        for index in range(fold.validation_start_index + 20, fold.validation_end_index - 2)
        if index not in fold.validation_eligible_decision_indices
    )

    with pytest.raises(ValueError, match="not sparse-eligible"):
        materializer.materialize(phase="validation", decision_index=sparse_hole)
    with pytest.raises(ValueError, match="must be reattested"):
        build_kis_daily_joint_event_d1_materializer(
            fold_input_artifact=replace(verified_fold, reattested_against_parent=False),
            catalog=source,
        )
    with pytest.raises(ValueError, match="catalog"):
        build_kis_daily_joint_event_d1_materializer(
            fold_input_artifact=verified_fold,
            catalog=replace(source, dataset_hash=_sha256("wrong-dataset")),
        )


def test_materializer_receipt_is_external_source_safe_and_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract, artifact_root, verified_fold = _verified_fold_artifact(tmp_path)
    source = _catalog(contract, tmp_path)
    decision_index = verified_fold.fold_input.validation_eligible_decision_indices[0]

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network or credential access is not allowed")

    with monkeypatch.context() as blocked:
        blocked.setattr(socket, "socket", fail)
        blocked.setattr(socket, "create_connection", fail)
        blocked.setattr(urllib.request, "urlopen", fail)
        blocked.setattr(os, "getenv", fail)
        materializer = build_kis_daily_joint_event_d1_materializer(
            fold_input_artifact=verified_fold,
            catalog=source,
        )
        receipt = write_kis_daily_joint_event_d1_materializer_receipt(
            destination=artifact_root / "receipts" / "window.json",
            materializer=materializer,
            phase="validation",
            decision_index=decision_index,
            artifact_root=artifact_root,
            repo_root=tmp_path / "repo",
        )

    serialized = receipt.path.read_text(encoding="utf-8").lower()
    assert receipt.content_hash == "sha256:" + hashlib.sha256(receipt.path.read_bytes()).hexdigest()
    assert '"close"' not in serialized
    assert '"return"' not in serialized
    assert '"label"' not in serialized
    assert '"open"' not in serialized
    assert '"credential"' not in serialized
    with pytest.raises(ValueError, match="not source-safe"):
        _assert_source_safe({"entry_open": "not-allowed"})
    with pytest.raises(FileExistsError):
        write_kis_daily_joint_event_d1_materializer_receipt(
            destination=receipt.path,
            materializer=receipt.materializer,
            phase="validation",
            decision_index=decision_index,
            artifact_root=artifact_root,
            repo_root=tmp_path / "repo",
        )


def test_materializer_import_is_pure_and_has_no_execution_or_network_imports() -> None:
    code = """\
import importlib
import sys
importlib.import_module('thericher_v2.kis_daily_joint_event_d1_materializer')
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

    module_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "thericher_v2"
        / "kis_daily_joint_event_d1_materializer.py"
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
        for term in (
            "execution",
            "broker",
            "socket",
            "urllib",
            "http",
            "requests",
            "dotenv",
            "tiingo",
            "campaign",
            "replay",
            "order",
        )
    )


def test_materializer_script_help_stays_on_the_pure_import_path() -> None:
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "prepare_kis_daily_joint_event_d1_materializer.py"
    )
    code = f"""\
import runpy
import sys
namespace = runpy.run_path({str(script_path)!r}, run_name='joint_d1_materializer_help_test')
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
