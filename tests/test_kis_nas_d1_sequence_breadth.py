from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import kis_paper_daily_history_sequence_input as data_input
from thericher_v2.data.kis_paper_daily_history_panel import (
    KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
    KIS_PAPER_DAILY_HISTORY_PANEL_ID,
    KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS,
    KisPaperDailyHistoryPanel,
    KisPaperDailyHistoryPanelTarget,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.research import kis_nas_d1_sequence_breadth as breadth
from thericher_v2.research import kis_nas_d1_sequence_campaign as campaign


def test_cpu_smoke_spec_is_frozen() -> None:
    assert breadth.KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_STEPS == 160
    assert tuple(spec.steps for spec in breadth.KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_SPECS) == (
        160,
    ) * len(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)


@pytest.fixture
def fast_cpu_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(breadth, "KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_STEPS", 2)
    monkeypatch.setattr(
        breadth,
        "KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_SPECS",
        tuple(
            breadth.KisNasD1L2LogisticSpec(
                symbol=symbol,
                seed=2026072810 + index,
                steps=2,
            )
            for index, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
        ),
    )


@pytest.fixture(scope="module")
def baseline_breadth_input(
    tmp_path_factory: pytest.TempPathFactory,
) -> breadth.KisNasD1SequenceBreadthInput:
    return _breadth_input(tmp_path_factory.mktemp("breadth-source") / "baseline")


def test_cpu_smoke_is_per_symbol_deterministic_and_target_free(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fast_cpu_smoke: None,
    baseline_breadth_input: breadth.KisNasD1SequenceBreadthInput,
) -> None:
    _deny_external_access(monkeypatch)
    prepared = baseline_breadth_input
    assert_prepared_unchanged = _memoize_prepared_input_attestation(monkeypatch, prepared)
    artifact_root = tmp_path / "model-artifacts"

    first = breadth.run_kis_nas_d1_l2_logistic_smoke(
        prepared,
        artifact_root=artifact_root,
        run_label="cpu-a",
        repo_root=Path.cwd(),
    )
    summary = json.loads(first.summary_path.read_text(encoding="utf-8"))
    repeat = breadth.fit_kis_nas_d1_l2_logistic_smoke(
        prepared,
        breadth.KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_SPECS[0],
    )

    assert first.candidates[0].model.parameter_hash == repeat.parameter_hash
    assert [candidate.validation_forward.output_shape for candidate in first.candidates] == [
        (313, 1)
    ] * len(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
    assert all(candidate.validation_forward.all_finite for candidate in first.candidates)
    assert all(candidate.validation_forward.output_bounds_valid for candidate in first.candidates)
    assert summary["validation"] == {
        "forward_only": True,
        "labels_materialized": False,
    }
    assert summary["artifact_policy"]["checkpoints_written"] is False
    assert summary["reporting"]["selection_allowed"] is False
    assert summary["reporting"]["pnl_materialized"] is False
    assert first.summary_path.is_relative_to(artifact_root)
    _assert_no_value_level_fields(summary)
    assert_prepared_unchanged()


def test_symbol_and_validation_changes_do_not_cross_the_fit_boundary(
    tmp_path: Path,
    fast_cpu_smoke: None,
    baseline_breadth_input: breadth.KisNasD1SequenceBreadthInput,
) -> None:
    baseline = baseline_breadth_input
    other_symbol_changed = _breadth_input(
        tmp_path / "other-symbol",
        altered_symbol="AMZN",
        altered_from_index=300,
        alteration=Decimal("30"),
    )
    validation_changed = _breadth_input(
        tmp_path / "validation-only",
        altered_symbol="AAPL",
        altered_from_index=1800,
        alteration=Decimal("30"),
    )
    aapl_spec = breadth.KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_SPECS[0]

    baseline_model = breadth.fit_kis_nas_d1_l2_logistic_smoke(baseline, aapl_spec)
    other_symbol_model = breadth.fit_kis_nas_d1_l2_logistic_smoke(
        other_symbol_changed,
        aapl_spec,
    )
    validation_model = breadth.fit_kis_nas_d1_l2_logistic_smoke(
        validation_changed,
        aapl_spec,
    )

    assert (
        baseline.standardizer("AAPL").standardizer_hash
        == other_symbol_changed.standardizer("AAPL").standardizer_hash
    )
    assert baseline_model.parameter_hash == other_symbol_model.parameter_hash
    assert (
        baseline.standardizer("AAPL").standardizer_hash
        == validation_changed.standardizer("AAPL").standardizer_hash
    )
    assert baseline_model.parameter_hash == validation_model.parameter_hash
    assert (
        baseline.campaign_input.validation_input_hash
        != validation_changed.campaign_input.validation_input_hash
    )


def test_cuda_breadth_writes_external_source_safe_fake_checkpoints(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    baseline_breadth_input: breadth.KisNasD1SequenceBreadthInput,
) -> None:
    _deny_external_access(monkeypatch)
    prepared = baseline_breadth_input
    assert_prepared_unchanged = _memoize_prepared_input_attestation(monkeypatch, prepared)
    artifact_root = tmp_path / "model-artifacts"
    cpu_summary = _write_cpu_smoke_summary(prepared, artifact_root / "cpu-summary.json")

    run = breadth.run_kis_nas_d1_cuda_sequence_breadth(
        prepared,
        cpu_smoke_summary_path=cpu_summary,
        artifact_root=artifact_root,
        run_label="cuda",
        repo_root=Path.cwd(),
        trainer=_fake_cuda_trainer,
    )
    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))

    assert run.status == "completed"
    assert len(run.candidates) == 18
    assert all(
        candidate.checkpoint_path.is_relative_to(artifact_root) for candidate in run.candidates
    )
    assert all(candidate.safe_weights_only_reload for candidate in run.candidates)
    assert summary["artifact_policy"]["checkpoints_written"] is True
    assert all(
        candidate["validation_forward"]["labels_materialized"] is False
        for candidate in summary["candidates"]
    )
    _assert_no_value_level_fields(summary)
    source = Path(breadth.__file__).read_text(encoding="utf-8")
    assert "weights_only=True" in source
    assert "weights_only=False" not in source
    assert_prepared_unchanged()


def test_cuda_breadth_rejects_an_unattested_cpu_smoke_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    baseline_breadth_input: breadth.KisNasD1SequenceBreadthInput,
) -> None:
    _deny_external_access(monkeypatch)
    artifact_root = tmp_path / "model-artifacts"
    cpu_summary = artifact_root / "cpu-summary.json"
    cpu_summary.parent.mkdir(parents=True)
    cpu_summary.write_text(
        json.dumps(
            {
                "kind": "kis_nas_d1_sequence_cpu_smoke",
                "status": "completed",
                "source": breadth._source_payload(baseline_breadth_input),  # noqa: SLF001
                "candidates": [{"symbol": "AAPL"}],
                "validation": {"labels_materialized": False},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="CPU smoke summary"):
        breadth.run_kis_nas_d1_cuda_sequence_breadth(
            baseline_breadth_input,
            cpu_smoke_summary_path=cpu_summary,
            artifact_root=artifact_root,
            run_label="cuda-unattested",
            repo_root=Path.cwd(),
            trainer=_fake_cuda_trainer,
        )

    assert not (artifact_root / breadth.KIS_NAS_D1_SEQUENCE_BREADTH_ID / "cuda-breadth").exists()


def test_cuda_breadth_rejects_a_repository_cpu_smoke_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    baseline_breadth_input: breadth.KisNasD1SequenceBreadthInput,
) -> None:
    _deny_external_access(monkeypatch)
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    cpu_summary = _write_cpu_smoke_summary(
        baseline_breadth_input,
        repository_root / "artifacts" / "cpu-summary.json",
    )

    with pytest.raises(ValueError, match="outside the Git workspace"):
        breadth.run_kis_nas_d1_cuda_sequence_breadth(
            baseline_breadth_input,
            cpu_smoke_summary_path=cpu_summary,
            artifact_root=tmp_path / "external-model-artifacts",
            run_label="cuda-git-input",
            repo_root=repository_root,
            trainer=_fake_cuda_trainer,
        )

    assert not (tmp_path / "external-model-artifacts").exists()


def test_cuda_unavailable_is_a_scoped_source_safe_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    baseline_breadth_input: breadth.KisNasD1SequenceBreadthInput,
) -> None:
    prepared = baseline_breadth_input
    assert_prepared_unchanged = _memoize_prepared_input_attestation(monkeypatch, prepared)
    artifact_root = tmp_path / "model-artifacts"
    cpu_summary = _write_cpu_smoke_summary(prepared, artifact_root / "cpu-summary.json")
    fake_cuda = SimpleNamespace(is_available=lambda: False)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=fake_cuda))

    run = breadth.run_kis_nas_d1_cuda_sequence_breadth(
        prepared,
        cpu_smoke_summary_path=cpu_summary,
        artifact_root=artifact_root,
        run_label="cuda-unavailable",
        repo_root=Path.cwd(),
    )
    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))

    assert run.status == "cuda_unavailable"
    assert run.candidates == ()
    assert summary["reason"] == "PyTorch CUDA is unavailable in the research runtime"
    assert summary["artifact_policy"]["checkpoints_written"] is False
    assert_prepared_unchanged()


def test_cuda_candidate_failure_cleans_its_incomplete_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    baseline_breadth_input: breadth.KisNasD1SequenceBreadthInput,
) -> None:
    _deny_external_access(monkeypatch)
    prepared = baseline_breadth_input
    assert_prepared_unchanged = _memoize_prepared_input_attestation(monkeypatch, prepared)
    artifact_root = tmp_path / "model-artifacts"
    cpu_summary = _write_cpu_smoke_summary(prepared, artifact_root / "cpu-summary.json")

    run = breadth.run_kis_nas_d1_cuda_sequence_breadth(
        prepared,
        cpu_smoke_summary_path=cpu_summary,
        artifact_root=artifact_root,
        run_label="cuda-failed",
        repo_root=Path.cwd(),
        trainer=_failing_cuda_trainer,
    )
    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))

    assert run.status == "candidate_failed"
    assert run.candidates == ()
    assert run.failure is not None
    assert run.failure.spec == breadth.KIS_NAS_D1_SEQUENCE_CUDA_ARCHITECTURE_SPECS[0]
    assert run.failure.category == "runtime"
    assert not list((run.summary_path.parent / "checkpoints").glob("*.pt"))
    assert summary["artifact_policy"]["checkpoints_written"] is False
    assert summary["failure"]["category"] == "runtime"
    _assert_no_value_level_fields(summary)
    assert_prepared_unchanged()


def test_breadth_rejects_repository_and_symlink_artifacts_and_exposes_offline_docker_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    baseline_breadth_input: breadth.KisNasD1SequenceBreadthInput,
) -> None:
    prepared = baseline_breadth_input
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(ValueError, match="outside the Git workspace"):
        breadth.run_kis_nas_d1_l2_logistic_smoke(
            prepared,
            artifact_root=repo_root / "model-artifacts",
            run_label="bad-root",
            repo_root=repo_root,
        )

    external_root = tmp_path / "external-model-artifacts"
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda value: value == external_root or original_is_symlink(value),
    )
    with pytest.raises(ValueError, match="artifact root cannot be a symlink"):
        breadth.run_kis_nas_d1_l2_logistic_smoke(
            prepared,
            artifact_root=external_root,
            run_label="symlink-root",
            repo_root=repo_root,
        )

    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    runner = Path("scripts/run_kis_nas_d1_sequence_breadth.py").read_text(encoding="utf-8")
    assert "network_mode: none" in compose
    assert "gpus: all" in compose
    assert "/app/market_data:ro" in compose
    assert "/app/model_artifacts" in compose
    assert "--market-data-root" in runner
    assert "--artifact-root" in runner


def test_breadth_allows_only_a_mounted_docker_artifact_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "app"
    repository_root.mkdir()
    mount_root = repository_root / "model_artifacts"
    mount_root.mkdir()
    original_is_mount = Path.is_mount

    def is_mount(path: Path) -> bool:
        return path.resolve() == mount_root.resolve() or original_is_mount(path)

    monkeypatch.setattr(Path, "is_mount", is_mount)
    monkeypatch.setattr(breadth, "_DOCKER_REPOSITORY_ROOT", repository_root)
    monkeypatch.setattr(breadth, "_DOCKER_ARTIFACT_ROOT", mount_root)

    output_dir = breadth._prepare_output_dir(  # noqa: SLF001
        artifact_root=mount_root,
        repo_root=repository_root,
        mode="cpu-smoke",
        run_label="mounted-root",
    )

    assert output_dir.is_relative_to(mount_root)


def test_breadth_frozen_campaign_requires_exact_contract_and_precommit(
    monkeypatch: pytest.MonkeyPatch,
    baseline_breadth_input: breadth.KisNasD1SequenceBreadthInput,
) -> None:
    campaign_input = baseline_breadth_input.campaign_input
    calculated_precommit_hash = campaign.calculate_kis_nas_d1_sequence_campaign_precommit_hash(
        campaign_input
    )
    monkeypatch.setattr(
        breadth,
        "KIS_NAS_D1_SEQUENCE_BREADTH_EXPECTED_CAMPAIGN_CONTRACT_HASH",
        campaign_input.contract.contract_hash,
    )
    monkeypatch.setattr(
        breadth,
        "KIS_NAS_D1_SEQUENCE_BREADTH_EXPECTED_CAMPAIGN_PRECOMMIT_HASH",
        calculated_precommit_hash,
    )

    breadth.require_frozen_kis_nas_d1_sequence_breadth_campaign(campaign_input)

    monkeypatch.setattr(
        breadth,
        "KIS_NAS_D1_SEQUENCE_BREADTH_EXPECTED_CAMPAIGN_PRECOMMIT_HASH",
        "sha256:" + "0" * 64,
    )
    with pytest.raises(ValueError, match="frozen precommit"):
        breadth.require_frozen_kis_nas_d1_sequence_breadth_campaign(campaign_input)


def _breadth_input(
    root: Path,
    *,
    altered_symbol: str | None = None,
    altered_from_index: int = 0,
    alteration: Decimal = Decimal("0"),
) -> breadth.KisNasD1SequenceBreadthInput:
    source = data_input._prepare_kis_paper_daily_history_sequence_input(  # noqa: SLF001
        _panel(
            root,
            altered_symbol=altered_symbol,
            altered_from_index=altered_from_index,
            alteration=alteration,
        )
    )
    campaign_input = campaign.build_kis_nas_d1_sequence_campaign(source)
    return breadth.build_kis_nas_d1_sequence_breadth_input(
        campaign_input,
        campaign_precommit_hash="sha256:" + "b" * 64,
    )


def _fake_cuda_trainer(
    prepared: breadth.KisNasD1SequenceBreadthInput,
    spec: breadth.KisNasD1SequenceArchitectureSpec,
    checkpoint_dir: Path,
) -> breadth.KisNasD1GpuCandidateReceipt:
    checkpoint_path = checkpoint_dir / f"{spec.architecture_id}-{spec.symbol}.pt"
    checkpoint_path.write_bytes(f"{spec.architecture_id}:{spec.symbol}".encode("ascii"))
    checkpoint_sha256 = "sha256:" + hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
    return breadth.KisNasD1GpuCandidateReceipt(
        spec=spec,
        development_sample_count=len(prepared.campaign_input.development_samples(spec.symbol)),
        validation_forward=breadth.KisNasD1TargetFreeForward(
            symbol=spec.symbol,
            sample_count=len(prepared.campaign_input.validation_samples(spec.symbol)),
            output_shape=(len(prepared.campaign_input.validation_samples(spec.symbol)), 1),
            all_finite=True,
            output_bounds_valid=True,
        ),
        checkpoint_path=checkpoint_path,
        checkpoint_sha256=checkpoint_sha256,
        backend="unit",
        device="unit-cuda",
        torch_version="unit",
        cuda_version=None,
        initial_loss=0.5,
        final_loss=0.25,
        cuda_peak_memory_bytes=0,
        safe_weights_only_reload=True,
    )


def _failing_cuda_trainer(
    _prepared: breadth.KisNasD1SequenceBreadthInput,
    spec: breadth.KisNasD1SequenceArchitectureSpec,
    checkpoint_dir: Path,
) -> breadth.KisNasD1GpuCandidateReceipt:
    (checkpoint_dir / f"{spec.architecture_id}-{spec.symbol}.pt").write_bytes(b"incomplete")
    raise RuntimeError("simulated CUDA failure")


def _write_cpu_smoke_summary(
    prepared: breadth.KisNasD1SequenceBreadthInput,
    path: Path,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    precommit_path = path.with_name("precommit.json")
    precommit_payload = breadth._cpu_precommit_payload(prepared)  # noqa: SLF001
    precommit_path.write_text(
        json.dumps(precommit_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    precommit_hash = breadth._sha256_file(precommit_path)  # noqa: SLF001
    candidates = [
        {
            "symbol": spec.symbol,
            "model_id": "l2_logistic",
            "model_parameter_hash": "sha256:" + f"{index + 1:064x}",
            "standardizer_hash": prepared.standardizer(spec.symbol).standardizer_hash,
            "development_sample_count": len(
                prepared.campaign_input.development_samples(spec.symbol)
            ),
            "steps": spec.steps,
            "seed": spec.seed,
            "initial_loss": "0.50000000",
            "final_loss": "0.25000000",
            "validation_forward": {
                "symbol": spec.symbol,
                "sample_count": len(prepared.campaign_input.validation_samples(spec.symbol)),
                "output_shape": [
                    len(prepared.campaign_input.validation_samples(spec.symbol)),
                    1,
                ],
                "all_finite": True,
                "output_bounds_valid": True,
                "labels_materialized": False,
            },
        }
        for index, spec in enumerate(breadth.KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_SPECS)
    ]
    payload = {
        "schema_version": breadth.SCHEMA_VERSION,
        "kind": "kis_nas_d1_sequence_cpu_smoke",
        "status": "completed",
        "precommit_hash": precommit_hash,
        "source": breadth._source_payload(prepared),  # noqa: SLF001
        "candidates": candidates,
        "validation": {"labels_materialized": False, "forward_only": True},
        "artifact_policy": {
            "repo_storage_allowed": False,
            "checkpoints_written": False,
            "raw_rows_persisted": False,
            "predictions_persisted": False,
        },
        "reporting": breadth._reporting_payload(),  # noqa: SLF001
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _panel(
    root: Path,
    *,
    altered_symbol: str | None,
    altered_from_index: int,
    alteration: Decimal,
) -> KisPaperDailyHistoryPanel:
    root.mkdir(parents=True)
    index_path = root / "index.json"
    index_path.write_text("{}\n", encoding="utf-8")
    start = datetime(2017, 1, 3, tzinfo=UTC)
    sessions = tuple((start + timedelta(days=index)).date() for index in range(2179))
    dataset_hash = data_input.KIS_PAPER_DAILY_HISTORY_SEQUENCE_EXPECTED_DATASET_HASH
    bars_by_symbol: dict[str, object] = {}
    targets_by_key: dict[str, KisPaperDailyHistoryPanelTarget] = {}
    for offset, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS, start=1):
        bars = tuple(
            _bar(
                symbol=symbol,
                start_ts=start + timedelta(days=index),
                value=(
                    Decimal("100")
                    + Decimal(offset * 10)
                    + Decimal(index) / Decimal("10")
                    + (
                        alteration
                        if symbol == altered_symbol and index >= altered_from_index
                        else Decimal("0")
                    )
                ),
            )
            for index in range(2179)
        )
        bars_by_symbol[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id=KIS_PAPER_DAILY_HISTORY_PANEL_ID,
            dataset_hash=dataset_hash,
            source_path=index_path,
            bars=bars,
        )
        state = "source_limited" if symbol == "MSFT" else "complete"
        targets_by_key[f"{symbol}/NAS"] = KisPaperDailyHistoryPanelTarget(
            target_key=f"{symbol}/NAS",
            state=state,
            last_reason="daily_response_invalid" if state == "source_limited" else None,
            chunk_count=1,
            bar_count=len(bars),
            coverage_start_bucket=_quarter(sessions[0]),
            coverage_end_bucket=_quarter(sessions[-1]),
        )
    return KisPaperDailyHistoryPanel(
        dataset_id=KIS_PAPER_DAILY_HISTORY_PANEL_ID,
        dataset_hash=dataset_hash,
        index_hash="sha256:" + "a" * 64,
        index_path=index_path,
        source_root=root,
        adjustment_mode=KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
        bars_by_symbol=MappingProxyType(bars_by_symbol),
        targets_by_key=MappingProxyType(targets_by_key),
        common_sessions=sessions,
    )


def _bar(*, symbol: str, start_ts: datetime, value: Decimal) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=start_ts,
        open=value,
        high=value + Decimal("1"),
        low=value - Decimal("1"),
        close=value,
        volume=Decimal("1000"),
        complete=True,
    )


def _quarter(value: date) -> str:
    return f"{value.year}-Q{(value.month - 1) // 3 + 1}"


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("external access is forbidden")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
    monkeypatch.setattr(os, "getenv", denied)


def _memoize_prepared_input_attestation(
    monkeypatch: pytest.MonkeyPatch,
    prepared: breadth.KisNasD1SequenceBreadthInput,
) -> Callable[[], None]:
    """Keep one real attestation while avoiding repeat hashes of this immutable fixture."""

    original_breadth = breadth._require_attested_breadth_input  # noqa: SLF001
    original_campaign = campaign.require_attested_kis_nas_d1_sequence_campaign_input
    prepared_campaign = prepared.campaign_input
    breadth_was_attested = False
    campaign_was_attested = False

    def require_campaign_attested(value: object) -> None:
        nonlocal campaign_was_attested
        if value is not prepared_campaign or not campaign_was_attested:
            original_campaign(value)
            if value is prepared_campaign:
                campaign_was_attested = True

    def require_attested(value: object) -> None:
        nonlocal breadth_was_attested
        if value is not prepared or not breadth_was_attested:
            original_breadth(value)
            if value is prepared:
                breadth_was_attested = True

    monkeypatch.setattr(
        campaign,
        "require_attested_kis_nas_d1_sequence_campaign_input",
        require_campaign_attested,
    )
    monkeypatch.setattr(
        breadth,
        "require_attested_kis_nas_d1_sequence_campaign_input",
        require_campaign_attested,
    )
    monkeypatch.setattr(breadth, "_require_attested_breadth_input", require_attested)

    def assert_prepared_unchanged() -> None:
        original_campaign(prepared_campaign)
        original_breadth(prepared)

    return assert_prepared_unchanged


def _assert_no_value_level_fields(payload: object) -> None:
    forbidden = {
        "account",
        "broker",
        "close_returns",
        "credentials",
        "feature_rows",
        "labels",
        "pnl",
        "predictions",
        "probabilities",
        "raw_bars",
        "secret",
    }
    if isinstance(payload, dict):
        for key, value in payload.items():
            assert key.lower() not in forbidden
            _assert_no_value_level_fields(value)
    elif isinstance(payload, list):
        for value in payload:
            _assert_no_value_level_fields(value)
