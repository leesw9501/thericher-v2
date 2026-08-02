from __future__ import annotations

import ast
import importlib.util
import socket
import subprocess
import sys
from collections import OrderedDict
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import thericher_v2.research.kis_nas_d1_volume_exhaustion_reversal as subject
from thericher_v2.contracts import Bar, Timeframe


def test_loader_passes_only_development_phase_and_census_never_opens_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    phase = _development_phase()

    class Source:
        input_id = "kis.paper.private.daily.nas.sequence.input-v1"
        development = phase

        @property
        def purge(self) -> object:
            raise AssertionError("volume campaign must not access purge")

        @property
        def validation(self) -> object:
            raise AssertionError("volume campaign must not access consumed validation")

    from thericher_v2.data import kis_paper_daily_history_sequence_input as sequence_input

    monkeypatch.setattr(
        sequence_input,
        "load_kis_paper_daily_history_sequence_input",
        lambda **_kwargs: Source(),
    )

    def fail_target(*_args: object, **_kwargs: object) -> float:
        raise AssertionError("target-free census must not open a next-session target")

    monkeypatch.setattr(subject, "_target_return_bps", fail_target)
    prepared = subject.load_kis_nas_d1_volume_exhaustion_reversal_input(
        manifest_path=tmp_path / "manifest.json",
        cache_root=tmp_path / "cache",
        panel_root=tmp_path / "panel",
        repo_root=tmp_path,
    )

    assert prepared.status == "ready"
    assert (
        prepared.structural_signal_count
        >= subject.KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_MIN_SIGNAL_COUNT
    )
    assert (
        prepared.structural_signal_symbol_count
        >= subject.KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_MIN_SYMBOL_COUNT
    )
    source = Path(subject.__file__).read_text(encoding="utf-8")
    assert "source.purge" not in source
    assert "source.validation" not in source


def test_evaluation_uses_exact_causal_and_target_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = subject.build_kis_nas_d1_volume_exhaustion_reversal_input(
        _development_phase(),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )
    assert prepared.status == "ready"
    bars = prepared._bars_by_symbol["AAPL"]
    baseline = subject._signal_flags(
        bars,
        decision_index=subject.KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_EVALUATION_DECISION_START,
    )
    changed = list(bars)
    changed[1021] = _normal_bar("AAPL", 1021, close_multiplier=Decimal("1.10"))
    changed[1043] = _normal_bar("AAPL", 1043, close_multiplier=Decimal("1.10"))
    assert subject._signal_flags(
        tuple(changed),
        decision_index=subject.KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_EVALUATION_DECISION_START,
    ) == baseline

    seen: list[int] = []
    original = subject._target_return_bps

    def capture(bar: Bar) -> float:
        seen.append((bar.start_ts - _START).days)
        return original(bar)

    monkeypatch.setattr(subject, "_target_return_bps", capture)
    subject._evaluate(prepared)

    assert min(seen) == subject.KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_EVALUATION_DECISION_START + 1
    assert max(seen) == subject.KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_EVALUATION_DECISION_STOP + 1
    assert len(seen) == prepared.evaluation_slot_count


def test_rule_abstains_for_invalid_causal_conditions() -> None:
    bars = list(_bars("AAPL"))
    index = 1060
    assert subject._signal_flags(tuple(bars), decision_index=index) == subject._SignalFlags(
        candidate=True,
        candle_only=True,
    )

    zero_range = list(bars)
    zero_range[index] = Bar(
        symbol="AAPL",
        market="US",
        timeframe=Timeframe.D1,
        start_ts=zero_range[index].start_ts,
        open=Decimal("100"),
        high=Decimal("100"),
        low=Decimal("100"),
        close=Decimal("100"),
        volume=Decimal("2000"),
        complete=True,
    )
    assert subject._signal_flags(tuple(zero_range), decision_index=index) == subject._SignalFlags(
        candidate=False,
        candle_only=False,
    )

    zero_median_volume = list(bars)
    for prior_index in range(index - 20, index):
        zero_median_volume[prior_index] = replace(
            zero_median_volume[prior_index],
            volume=Decimal("0"),
        )
    assert subject._signal_flags(
        tuple(zero_median_volume), decision_index=index
    ) == subject._SignalFlags(candidate=False, candle_only=False)

    discontinuous = list(bars)
    discontinuous[index - 1] = Bar(
        symbol="AAPL",
        market="US",
        timeframe=Timeframe.D1,
        start_ts=discontinuous[index - 1].start_ts,
        open=Decimal("100"),
        high=Decimal("100"),
        low=Decimal("50"),
        close=Decimal("50"),
        volume=Decimal("1000"),
        complete=True,
    )
    assert subject._signal_flags(
        tuple(discontinuous), decision_index=index
    ) == subject._SignalFlags(candidate=False, candle_only=False)
    incomplete = tuple(
        replace(bars[index], complete=False) if position == index else bar
        for position, bar in enumerate(bars)
    )
    assert subject._signal_flags(
        incomplete,
        decision_index=index,
    ) == subject._SignalFlags(candidate=False, candle_only=False)
    wrong_timeframe = tuple(
        replace(bars[index], timeframe=Timeframe.H1) if position == index else bar
        for position, bar in enumerate(bars)
    )
    assert subject._signal_flags(
        wrong_timeframe,
        decision_index=index,
    ) == subject._SignalFlags(candidate=False, candle_only=False)


def test_null_moves_only_full_blocks_and_leaves_trailing_partial_block_fixed() -> None:
    values = tuple(float(index) for index in range(467))
    permuted = subject._block_permute_target_returns(values, seed=1234)

    assert permuted == subject._block_permute_target_returns(values, seed=1234)
    assert permuted[-7:] == values[-7:]
    original_blocks = {values[index : index + 10] for index in range(0, 460, 10)}
    assert {
        permuted[index : index + 10]
        for index in range(0, 460, 10)
    } == original_blocks


@pytest.mark.parametrize(
    ("candidate", "candle", "null_p95"),
    [
        ((30.0, 25.0, 0.0), (20.0, 15.0, -10.0), -1.0),
        ((30.0, 25.0, 10.0), (20.0, 25.0, 0.0), -1.0),
        ((30.0, 25.0, 10.0), (20.0, 15.0, 0.0), 10.0),
    ],
)
def test_falsification_kill_tests_are_strict(
    candidate: tuple[float, float, float],
    candle: tuple[float, float, float],
    null_p95: float,
) -> None:
    metrics = _metrics(candidate=candidate, candle=candle, null_p95=null_p95)

    assert metrics.is_falsified is True


def test_positive_result_is_still_non_promoting_and_external_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prepared = subject.build_kis_nas_d1_volume_exhaustion_reversal_input(
        _development_phase(),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )
    repo_root = tmp_path / "repository"
    repo_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("offline volume falsification must not access the network")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(
        subject,
        "_evaluate",
        lambda _input: _metrics(
            candidate=(30.0, 25.0, 21.0),
            candle=(10.0, 5.0, 1.0),
            null_p95=20.0,
        ),
    )
    contract = subject.freeze_kis_nas_d1_volume_exhaustion_reversal_campaign(
        prepared,
        artifact_root=artifact_root,
        repo_root=repo_root,
        code_revision="unit-code-revision",
    )
    same_contract = subject.freeze_kis_nas_d1_volume_exhaustion_reversal_campaign(
        prepared,
        artifact_root=artifact_root,
        repo_root=repo_root,
        code_revision="unit-code-revision",
    )
    with pytest.raises(ValueError, match="contract conflicts"):
        subject.freeze_kis_nas_d1_volume_exhaustion_reversal_campaign(
            prepared,
            artifact_root=artifact_root,
            repo_root=repo_root,
            code_revision="changed-unit-code-revision",
        )
    result = subject.run_kis_nas_d1_volume_exhaustion_reversal(contract)
    repeated = subject.run_kis_nas_d1_volume_exhaustion_reversal(contract)
    serialized = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (contract.contract_path, result.summary_path)
    )

    assert same_contract.contract_sha256 == contract.contract_sha256
    assert result.status == "inconclusive_non_promoting"
    assert repeated.summary_sha256 == result.summary_sha256
    assert repeated.registry_outcome.record_sha256 == result.registry_outcome.record_sha256
    assert contract.run_directory.is_relative_to(artifact_root)
    assert "2020-" not in serialized
    assert "100.000" not in serialized
    assert '"numeric_metrics_persisted":false' in serialized
    assert '"profitability_or_pnl_claim":false' in serialized
    assert '"gpu_used":false' in serialized
    assert not list(contract.run_directory.glob("*.pt"))

    with pytest.raises(ValueError, match="outside the Git workspace"):
        subject.freeze_kis_nas_d1_volume_exhaustion_reversal_campaign(
            prepared,
            artifact_root=repo_root / "artifacts",
            repo_root=repo_root,
            code_revision="unit-code-revision",
        )


def test_leaf_and_runner_stay_offline_and_wire_explicit_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = Path(subject.__file__).read_text(encoding="utf-8")
    module = ast.parse(source)
    imported = {
        alias.name
        for node in module.body
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    for forbidden in ("torch", "requests", "socket", "os", "urllib"):
        assert forbidden not in imported
    for forbidden in (".env", "os.environ", "thericher_v2.execution"):
        assert forbidden not in source
    registry_source = (
        Path(subject.__file__).with_name("campaign_registry.py").read_text(encoding="utf-8")
    )
    artifact_paths_source = (
        Path(subject.__file__).with_name("artifact_paths.py").read_text(encoding="utf-8")
    )
    assert "from .validation import" not in registry_source
    assert "thericher_v2.execution" not in artifact_paths_source
    imported = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import thericher_v2.research.kis_nas_d1_volume_exhaustion_reversal; "
            "raise SystemExit('thericher_v2.execution' in sys.modules)",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert imported.returncode == 0, imported.stderr
    legacy_public_api = subprocess.run(
        [
            sys.executable,
            "-c",
            "from thericher_v2.research import CampaignContract; "
            "raise SystemExit(CampaignContract.__name__ != 'CampaignContract')",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert legacy_public_api.returncode == 0, legacy_public_api.stderr

    path = Path(__file__).parents[1] / "scripts" / "run_kis_nas_d1_volume_exhaustion_reversal.py"
    spec = importlib.util.spec_from_file_location("volume_exhaustion_runner_test", path)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    captured: dict[str, object] = {}
    prepared = SimpleNamespace()
    contract = SimpleNamespace(contract_sha256="sha256:" + "a" * 64)
    result = SimpleNamespace(
        status="falsified",
        reason="frozen_kill_test_failed",
        summary_sha256="sha256:" + "b" * 64,
        registry_outcome=SimpleNamespace(record_sha256="sha256:" + "c" * 64),
    )

    def load(**kwargs: object) -> SimpleNamespace:
        captured["load"] = kwargs
        return prepared

    def freeze(value: object, **kwargs: object) -> SimpleNamespace:
        captured["freeze"] = {"value": value, **kwargs}
        return contract

    def run(value: object) -> SimpleNamespace:
        captured["run"] = value
        return result

    monkeypatch.setattr(runner, "load_kis_nas_d1_volume_exhaustion_reversal_input", load)
    monkeypatch.setattr(runner, "freeze_kis_nas_d1_volume_exhaustion_reversal_campaign", freeze)
    monkeypatch.setattr(runner, "run_kis_nas_d1_volume_exhaustion_reversal", run)
    market_data_root = tmp_path / "market-data"
    artifact_root = tmp_path / "artifacts"
    runner.main(
        [
            "--market-data-root",
            str(market_data_root),
            "--artifact-root",
            str(artifact_root),
            "--repo-root",
            str(tmp_path),
            "--attempt-id",
            "unit-r1",
        ]
    )

    assert captured["freeze"]["value"] is prepared
    assert captured["freeze"]["artifact_root"] == artifact_root
    assert captured["run"] is contract
    runner_source = path.read_text(encoding="utf-8")
    assert 'Path("/.dockerenv").is_file()' in runner_source
    assert "_CAMPAIGN_CODE_PATHS" in runner_source
    assert "artifact_paths.py" in runner_source
    assert "campaign_registry.py" in runner_source
    for forbidden in (".env", "os.environ", "requests", "socket", "urllib", "torch"):
        assert forbidden not in runner_source


def test_external_artifact_components_cannot_follow_symlinks(tmp_path: Path) -> None:
    prepared = subject.build_kis_nas_d1_volume_exhaustion_reversal_input(
        _development_phase(),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )
    repo_root = tmp_path / "repository"
    repo_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    artifact_root.mkdir()
    research_link = artifact_root / "research"
    try:
        research_link.symlink_to(repo_root, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows host")

    with pytest.raises(ValueError, match="artifact directory must not be a symlink"):
        subject.freeze_kis_nas_d1_volume_exhaustion_reversal_campaign(
            prepared,
            artifact_root=artifact_root,
            repo_root=repo_root,
            code_revision="unit-code-revision",
        )
    assert not list(repo_root.iterdir())


def test_artifact_root_cannot_be_or_traverse_a_symlink(tmp_path: Path) -> None:
    prepared = subject.build_kis_nas_d1_volume_exhaustion_reversal_input(
        _development_phase(),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )
    repo_root = tmp_path / "repository"
    repo_root.mkdir()
    external_root = tmp_path / "model-artifacts"
    external_root.mkdir()
    root_link = tmp_path / "artifact-root-link"
    try:
        root_link.symlink_to(external_root, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows host")

    with pytest.raises(ValueError, match="must not traverse a symlink"):
        subject.freeze_kis_nas_d1_volume_exhaustion_reversal_campaign(
            prepared,
            artifact_root=root_link,
            repo_root=repo_root,
            code_revision="unit-code-revision",
        )
    assert not list(external_root.iterdir())


def test_uncreated_artifact_root_inside_git_is_rejected_before_creation(tmp_path: Path) -> None:
    prepared = subject.build_kis_nas_d1_volume_exhaustion_reversal_input(
        _development_phase(),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )
    repo_root = tmp_path / "repository"
    repo_root.mkdir()
    artifact_root = repo_root / "not-yet-created-artifacts"

    with pytest.raises(ValueError, match="outside the Git workspace"):
        subject.freeze_kis_nas_d1_volume_exhaustion_reversal_campaign(
            prepared,
            artifact_root=artifact_root,
            repo_root=repo_root,
            code_revision="unit-code-revision",
        )
    assert not artifact_root.exists()


_START = datetime(2020, 1, 1, tzinfo=UTC)


def _metrics(
    *,
    candidate: tuple[float, float, float],
    candle: tuple[float, float, float],
    null_p95: float,
) -> subject.KisNasD1VolumeExhaustionReversalMetrics:
    return subject.KisNasD1VolumeExhaustionReversalMetrics(
        candidate_trade_count=12,
        candidate_symbol_count=4,
        candle_only_trade_count=20,
        evaluation_slot_count=subject._evaluation_slot_count(),
        candidate_net_mean_bps_by_cost=tuple(
            zip(("10", "15", "20"), candidate, strict=True)
        ),
        candle_only_net_mean_bps_by_cost=tuple(
            zip(("10", "15", "20"), candle, strict=True)
        ),
        null_p95_net_mean_bps_primary_cost=null_p95,
        null_count=subject.KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_NULL_COUNT,
    )


def _development_phase() -> SimpleNamespace:
    sessions = tuple((_START + timedelta(days=index)).date() for index in range(1510))
    bars_by_symbol: OrderedDict[str, SimpleNamespace] = OrderedDict()
    for symbol in subject.KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_SYMBOLS:
        bars_by_symbol[symbol] = SimpleNamespace(bars=_bars(symbol))
    return SimpleNamespace(
        phase="development",
        parent_dataset_id=subject.KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_DATASET_ID,
        parent_dataset_hash=subject.KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_DATASET_HASH,
        index_hash="sha256:" + "a" * 64,
        bars_by_symbol=bars_by_symbol,
        common_sessions=sessions,
    )


def _bars(symbol: str) -> tuple[Bar, ...]:
    candidate_indices = set(range(40, 1510, 20))
    candle_only_indices = set(range(50, 1510, 20))
    return tuple(
        _candidate_bar(symbol, index, elevated_volume=index in candidate_indices)
        if index in candidate_indices | candle_only_indices
        else _normal_bar(symbol, index)
        for index in range(1510)
    )


def _normal_bar(
    symbol: str,
    index: int,
    *,
    close_multiplier: Decimal = Decimal("1.001"),
) -> Bar:
    opening = Decimal("100") + Decimal(index) / Decimal("100")
    close = opening * close_multiplier
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=_START + timedelta(days=index),
        open=opening,
        high=max(opening, close) * Decimal("1.005"),
        low=min(opening, close) * Decimal("0.995"),
        close=close,
        volume=Decimal("1000"),
        complete=True,
    )


def _candidate_bar(symbol: str, index: int, *, elevated_volume: bool) -> Bar:
    opening = Decimal("100") + Decimal(index) / Decimal("100")
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=_START + timedelta(days=index),
        open=opening,
        high=opening * Decimal("1.04"),
        low=opening * Decimal("0.94"),
        close=opening * Decimal("0.95"),
        volume=Decimal("2000") if elevated_volume else Decimal("1000"),
        complete=True,
    )
