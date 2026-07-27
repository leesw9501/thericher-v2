"""Focused tests for the non-executable QQQ/SPY D1 fold materializer."""

from __future__ import annotations

import ast
import hashlib
import os
import runpy
import socket
import subprocess
import sys
import urllib.request
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_UP, Decimal, localcontext
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_daily import KisPaperPrivateDailyCatalog
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.kis_daily_joint_event_d1_materializer import (
    KIS_DAILY_JOINT_EVENT_D1_ADJUSTMENT_MODE,
    KIS_DAILY_JOINT_EVENT_D1_CATALOG_ID,
    KIS_DAILY_JOINT_EVENT_D1_SUPPORTED_FOLD_IDS,
    _assert_source_safe,
    build_kis_daily_joint_event_d1_materializer,
    write_kis_daily_joint_event_d1_materializer_receipt,
)
from thericher_v2.kis_daily_joint_event_d1_target_cost import (
    KIS_DAILY_JOINT_EVENT_D1_TARGET_COST_KIND,
    KIS_DAILY_JOINT_EVENT_D1_TARGET_DECIMAL_PRECISION,
    KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL,
    KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL,
    build_kis_daily_joint_event_d1_target_cost_adapter,
    calculate_kis_daily_joint_event_d1_target_label,
    write_kis_daily_joint_event_d1_target_cost_receipt,
)
from thericher_v2.kis_daily_joint_event_d1_target_cost import (
    _assert_source_safe as _assert_target_receipt_source_safe,
)
from thericher_v2.kis_daily_joint_event_window_contract import (
    DEFAULT_KIS_DAILY_JOINT_EVENT_WINDOW_SPEC,
    KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE,
    build_kis_daily_joint_event_window_contract,
    is_container_external_mount,
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
    repo_root.mkdir(parents=True)
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


def _verified_fold_artifact(tmp_path: Path, *, fold_id: str = "expanding-1"):
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
        fold_id=fold_id,
    )
    written = write_kis_daily_joint_event_fold_input(
        destination=artifact_root / "contracts" / f"fold-{fold_id}.json",
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


def _target_adapter(
    tmp_path: Path,
    *,
    qqq_close_overrides: dict[int, Decimal] | None = None,
    qqq_open_overrides: dict[int, Decimal] | None = None,
    fold_id: str = "expanding-1",
):
    contract, artifact_root, verified_fold = _verified_fold_artifact(tmp_path, fold_id=fold_id)
    source = _catalog(
        contract,
        tmp_path,
        qqq_close_overrides=qqq_close_overrides,
        qqq_open_overrides=qqq_open_overrides,
    )
    materializer = build_kis_daily_joint_event_d1_materializer(
        fold_input_artifact=verified_fold,
        catalog=source,
    )
    return (
        artifact_root,
        materializer,
        build_kis_daily_joint_event_d1_target_cost_adapter(materializer=materializer),
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


def test_expanding_three_stays_a_distinct_single_fold_materializer_and_target(
    tmp_path: Path,
) -> None:
    first_contract, _first_root, first_fold = _verified_fold_artifact(
        tmp_path / "expanding-one",
        fold_id="expanding-1",
    )
    second_contract, _second_root, second_fold = _verified_fold_artifact(
        tmp_path / "expanding-two",
        fold_id="expanding-2",
    )
    third_contract, _third_root, third_fold = _verified_fold_artifact(
        tmp_path / "expanding-three",
        fold_id="expanding-3",
    )
    assert first_contract.contract_identity == second_contract.contract_identity
    assert second_contract.contract_identity == third_contract.contract_identity
    assert third_fold.fold_input.fold_id == "expanding-3"
    assert (
        third_fold.fold_input.validation_start_index
        > first_fold.fold_input.validation_end_index
    )
    assert (
        third_fold.fold_input.validation_start_index
        > second_fold.fold_input.validation_end_index
    )
    assert third_fold.fold_input.development_eligible_decision_indices == (
        third_contract.folds[2].development_eligible_decision_indices
    )
    assert third_fold.fold_input.validation_eligible_decision_indices == (
        third_contract.folds[2].validation_eligible_decision_indices
    )
    assert max(third_fold.fold_input.validation_eligible_decision_indices) + 2 < (
        third_contract.final_unused_tail_start_index
    )
    assert len(third_contract.sessions) - third_contract.final_unused_tail_start_index == 151

    materializer = build_kis_daily_joint_event_d1_materializer(
        fold_input_artifact=third_fold,
        catalog=_catalog(third_contract, tmp_path / "expanding-three"),
    )
    adapter = build_kis_daily_joint_event_d1_target_cost_adapter(materializer=materializer)
    decision_index = materializer.eligible_decision_indices("validation")[0]
    target = adapter.derive(phase="validation", decision_index=decision_index)

    assert materializer.fold_input.fold_id == "expanding-3"
    assert target.decision_index == decision_index
    assert target.entry_index == decision_index + 1
    assert target.exit_index == decision_index + 2
    with pytest.raises(ValueError, match="not sparse-eligible"):
        materializer.materialize(
            phase="validation",
            decision_index=first_fold.fold_input.validation_eligible_decision_indices[0],
        )


def test_expanding_three_pin_binds_exact_counts_and_container_paths() -> None:
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "prepare_kis_daily_joint_event_d1_materializer.py"
    )
    namespace = runpy.run_path(str(script_path), run_name="joint_d1_third_fold_pin_test")
    pin = namespace["_fold_pin"]("expanding-3")

    assert KIS_DAILY_JOINT_EVENT_D1_SUPPORTED_FOLD_IDS == (
        "expanding-1",
        "expanding-2",
        "expanding-3",
    )
    assert pin.development_eligible_decision_count == 2671
    assert pin.validation_eligible_decision_count == 145
    assert pin.artifact_sha256 == (
        "sha256:40d6c9920a0edec12249f4b429c503b085b2e908466093496da8e0b6717128fc"
    )
    assert pin.fold_input_identity == (
        "sha256:1cf334306f1e2cc0e907d688d697c850aaf6ca0ef7ed2c42ee807f2c9633d11e"
    )
    assert namespace["_default_fold_artifact"](
        Path("/app/model_artifacts"),
        "expanding-3",
    ) == (
        Path("/app/model_artifacts")
        / "research-contracts"
        / pin.artifact_name
    )
    with pytest.raises(ValueError, match="fold id"):
        namespace["_fold_pin"]("expanding-4")

    container_repo = Path("/app").resolve()
    assert is_container_external_mount(Path("/app/market_data/source").resolve(), container_repo)
    assert is_container_external_mount(
        Path("/app/model_artifacts/receipt.json").resolve(),
        container_repo,
    )
    assert not is_container_external_mount(Path("/app/src").resolve(), container_repo)
    assert not is_container_external_mount(Path("/elsewhere").resolve(), container_repo)


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
    with pytest.raises(ValueError, match="not source-safe"):
        _assert_source_safe({"lineage": {"open": "not-allowed"}})
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


def test_target_cost_adapter_reconstructs_one_sparse_causal_target(tmp_path: Path) -> None:
    _artifact_root, materializer, adapter = _target_adapter(tmp_path)
    decision_index = materializer.eligible_decision_indices("validation")[0]

    target = adapter.derive(phase="validation", decision_index=decision_index)

    assert target.decision_index == decision_index
    assert target.predecessor_index == decision_index - 20
    assert target.feature_start_index == decision_index - 19
    assert target.feature_end_index == decision_index
    assert target.entry_index == decision_index + 1
    assert target.exit_index == decision_index + 2
    assert target.label in {0, 1}
    assert target.target_cost_identity == adapter.target_cost_identity
    assert adapter.target_cost_identity.startswith("sha256:")


def test_target_cost_adapter_uses_only_future_qqq_opens(tmp_path: Path) -> None:
    _artifact_root, baseline_materializer, baseline_adapter = _target_adapter(
        tmp_path,
        fold_id="expanding-3",
    )
    decision_index = baseline_materializer.eligible_decision_indices("validation")[0]
    _artifact_root, future_materializer, future_adapter = _target_adapter(
        tmp_path / "future",
        qqq_open_overrides={decision_index + 2: Decimal("9999")},
        fold_id="expanding-3",
    )
    _artifact_root, feature_materializer, feature_adapter = _target_adapter(
        tmp_path / "feature",
        qqq_close_overrides={decision_index: Decimal("9999")},
        fold_id="expanding-3",
    )

    baseline_window = baseline_materializer.materialize(
        phase="validation",
        decision_index=decision_index,
    )
    future_window = future_materializer.materialize(
        phase="validation",
        decision_index=decision_index,
    )
    feature_window = feature_materializer.materialize(
        phase="validation",
        decision_index=decision_index,
    )
    baseline_target = baseline_adapter.derive(phase="validation", decision_index=decision_index)
    future_target = future_adapter.derive(phase="validation", decision_index=decision_index)
    feature_target = feature_adapter.derive(phase="validation", decision_index=decision_index)

    assert baseline_window.feature_rows == future_window.feature_rows
    assert baseline_target.label == 0
    assert future_target.label == 1
    assert baseline_target.label != future_target.label
    assert baseline_window.feature_rows != feature_window.feature_rows
    assert baseline_target.label == feature_target.label


def test_target_cost_formula_is_fixed_and_context_independent() -> None:
    assert KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL == Decimal("1")
    assert KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL == Decimal("2")
    assert KIS_DAILY_JOINT_EVENT_D1_TARGET_DECIMAL_PRECISION == 34
    assert calculate_kis_daily_joint_event_d1_target_label(
        entry_open=Decimal("100"),
        exit_open=Decimal("100.0600"),
    ) == 0
    assert calculate_kis_daily_joint_event_d1_target_label(
        entry_open=Decimal("100"),
        exit_open=Decimal("100.0610"),
    ) == 1
    baseline = calculate_kis_daily_joint_event_d1_target_label(
        entry_open=Decimal("100.00065"),
        exit_open=Decimal("100.06067"),
    )
    with localcontext() as context:
        context.rounding = ROUND_UP
        context.prec = 8
        assert (
            calculate_kis_daily_joint_event_d1_target_label(
                entry_open=Decimal("100.00065"),
                exit_open=Decimal("100.06067"),
            )
            == baseline
        )
    with pytest.raises(ValueError, match="entry open"):
        calculate_kis_daily_joint_event_d1_target_label(
            entry_open=Decimal("0"),
            exit_open=Decimal("100"),
        )


def test_target_cost_adapter_rejects_sparse_holes_and_bad_materializers(tmp_path: Path) -> None:
    _artifact_root, materializer, adapter = _target_adapter(tmp_path)
    fold = materializer.fold_input
    sparse_hole = next(
        index
        for index in range(fold.validation_start_index + 20, fold.validation_end_index - 2)
        if index not in fold.validation_eligible_decision_indices
    )

    with pytest.raises(ValueError, match="not sparse-eligible"):
        adapter.derive(phase="validation", decision_index=sparse_hole)
    with pytest.raises(ValueError, match="materializer"):
        build_kis_daily_joint_event_d1_target_cost_adapter(materializer="not-a-materializer")  # type: ignore[arg-type]


def test_target_cost_receipt_is_external_source_safe_and_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_root, materializer, adapter = _target_adapter(tmp_path)
    decision_index = materializer.eligible_decision_indices("validation")[0]

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network or credential access is not allowed")

    with monkeypatch.context() as blocked:
        blocked.setattr(socket, "socket", fail)
        blocked.setattr(socket, "create_connection", fail)
        blocked.setattr(urllib.request, "urlopen", fail)
        blocked.setattr(os, "getenv", fail)
        receipt = write_kis_daily_joint_event_d1_target_cost_receipt(
            destination=artifact_root / "receipts" / "target-cost.json",
            adapter=adapter,
            phase="validation",
            decision_index=decision_index,
            artifact_root=artifact_root,
            repo_root=tmp_path / "repo",
        )

    serialized = receipt.path.read_text(encoding="utf-8").lower()
    assert receipt.content_hash == "sha256:" + hashlib.sha256(receipt.path.read_bytes()).hexdigest()
    assert KIS_DAILY_JOINT_EVENT_D1_TARGET_COST_KIND in serialized
    assert '"open"' not in serialized
    assert '"return"' not in serialized
    assert '"label"' not in serialized
    assert '"prediction"' not in serialized
    assert '"pnl"' not in serialized
    assert '"credential"' not in serialized
    assert '"order"' not in serialized
    with pytest.raises(ValueError, match="not source-safe"):
        _assert_target_receipt_source_safe({"entry_open": "not-allowed"})
    with pytest.raises(ValueError, match="not source-safe"):
        _assert_target_receipt_source_safe({"source_materializer": {"label": 1}})
    with pytest.raises(FileExistsError):
        write_kis_daily_joint_event_d1_target_cost_receipt(
            destination=receipt.path,
            adapter=adapter,
            phase="validation",
            decision_index=decision_index,
            artifact_root=artifact_root,
            repo_root=tmp_path / "repo",
        )


def test_target_cost_module_and_script_help_stay_on_the_pure_import_path() -> None:
    module_code = """\
import importlib
import sys
importlib.import_module('thericher_v2.kis_daily_joint_event_d1_target_cost')
assert not [name for name in sys.modules if name.startswith('thericher_v2.data')]
assert not [name for name in sys.modules if name.startswith('thericher_v2.execution')]
"""
    module_result = subprocess.run(
        [sys.executable, "-c", module_code],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert module_result.returncode == 0, module_result.stderr

    module_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "thericher_v2"
        / "kis_daily_joint_event_d1_target_cost.py"
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
            "backtest",
            "order",
        )
    )

    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "prepare_kis_daily_joint_event_d1_target_cost.py"
    )
    script_result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert script_result.returncode == 0, script_result.stderr
