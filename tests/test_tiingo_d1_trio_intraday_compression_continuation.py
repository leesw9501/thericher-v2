from __future__ import annotations

import ast
import importlib.util
import json
import socket
import subprocess
import sys
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import thericher_v2.research.tiingo_d1_trio_intraday_compression_continuation as subject
from thericher_v2.data.tiingo_etf_daily import (
    TIINGO_ETF_D1_SYMBOLS,
    LoadedTiingoEtfDailySnapshot,
    TiingoEtfDailyRow,
    TiingoEtfDailySnapshot,
)


def test_target_free_input_does_not_open_a_validation_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def target_forbidden(*_args: object, **_kwargs: object) -> tuple[Decimal, ...]:
        raise AssertionError("input construction must not read a validation target")

    monkeypatch.setattr(subject, "_target_vector", target_forbidden)
    campaign_input = subject.build_tiingo_d1_trio_intraday_compression_input(_snapshot())

    assert campaign_input.status == "ready"
    assert (
        campaign_input.development_signal_count
        >= subject.TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_MIN_DEVELOPMENT_SIGNALS
    )
    assert campaign_input.development_signal_symbol_count == len(TIINGO_ETF_D1_SYMBOLS)
    assert (
        campaign_input.validation_active_day_count
        >= subject.TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_MIN_VALIDATION_ACTIVE_DAYS
    )


def test_first_validation_decision_uses_no_future_bar() -> None:
    baseline = subject.build_tiingo_d1_trio_intraday_compression_input(_snapshot())
    first = baseline._validation_decisions[0]
    changed = _snapshot()
    rows = {symbol: list(values) for symbol, values in changed.rows_by_symbol.items()}
    target_index = first.index + 1
    for symbol in TIINGO_ETF_D1_SYMBOLS:
        row = rows[symbol][target_index]
        rows[symbol][target_index] = replace(
            row,
            open=row.open * Decimal("5"),
            high=row.high * Decimal("5"),
            low=row.low * Decimal("5"),
            close=row.close * Decimal("5"),
        )
    changed_snapshot = LoadedTiingoEtfDailySnapshot(
        snapshot=changed.snapshot,
        rows_by_symbol={symbol: tuple(values) for symbol, values in rows.items()},
    )
    rerun = subject.build_tiingo_d1_trio_intraday_compression_input(changed_snapshot)

    assert _decision_at(rerun, first.index).symbols == first.symbols


def test_split_uses_a_real_purge_between_development_and_validation() -> None:
    campaign_input = subject.build_tiingo_d1_trio_intraday_compression_input(_snapshot())
    development = campaign_input.development_session_count
    validation_start = development + campaign_input.purge_session_count

    assert campaign_input.purge_session_count == 61
    assert (
        validation_start
        - subject.TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_LOOKBACK
        > development
    )
    assert all(
        decision.index >= validation_start
        for decision in campaign_input._validation_decisions
    )
    assert all(
        decision.index + 1 < campaign_input.common_session_count
        for decision in campaign_input._validation_decisions
    )


@pytest.mark.parametrize("kind", ["zero_range", "event", "discontinuity", "invalid_volume"])
def test_signal_abstains_on_invalid_causal_chain(kind: str) -> None:
    snapshot = _snapshot()
    rows = list(snapshot.rows_by_symbol["SPY"])
    index = 1000
    assert subject._symbol_qualifies(rows, index)
    if kind == "zero_range":
        row = rows[index]
        rows[index] = replace(row, high=row.open, low=row.open)
    elif kind == "event":
        rows[index - 5] = replace(rows[index - 5], div_cash=Decimal("1"))
    elif kind == "discontinuity":
        row = rows[index - 1]
        rows[index - 1] = replace(row, close=row.close * Decimal("1.25"))
    else:
        rows[index - 4] = replace(rows[index - 4], volume=Decimal("0"))

    assert subject._symbol_qualifies(rows, index) is False


def test_insufficient_preflight_never_reads_a_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(signal_every=None)
    campaign_input = subject.build_tiingo_d1_trio_intraday_compression_input(snapshot)
    assert campaign_input.status == "input_unavailable"
    assert campaign_input.reason == "insufficient_target_free_development_signals"
    campaign = subject.freeze_tiingo_d1_trio_intraday_compression_campaign(
        campaign_input,
        artifact_root=tmp_path / "artifacts",
        repo_root=_repo(tmp_path),
        code_revision="sha256:" + "a" * 64,
        attempt_id="unit-unavailable",
    )
    assert campaign.registry_entry.holdout_access == "none"

    def target_forbidden(*_args: object, **_kwargs: object) -> tuple[Decimal, ...]:
        raise AssertionError("unavailable input must not open a target")

    monkeypatch.setattr(subject, "_target_vector", target_forbidden)
    result = subject.run_tiingo_d1_trio_intraday_compression_campaign(campaign)

    assert result.status == "input_unavailable"
    assert result.metrics is None


def test_joint_null_moves_only_full_blocks_and_preserves_joint_vectors() -> None:
    vectors = tuple(
        (Decimal(index), Decimal(index + 1000), Decimal(index + 2000))
        for index in range(467)
    )
    permuted = subject._block_permute_joint_target_vectors(vectors, seed=1234)

    assert permuted == subject._block_permute_joint_target_vectors(vectors, seed=1234)
    assert permuted[-7:] == vectors[-7:]
    assert {
        vectors[index : index + 10]
        for index in range(0, 460, 10)
    } == {
        permuted[index : index + 10]
        for index in range(0, 460, 10)
    }


@pytest.mark.parametrize(
    ("candidate", "equal_exposure", "null_p95"),
    [
        ((30, 25, 0), (20, 15, -10), -1),
        ((30, 25, 10), (20, 25, 0), -1),
        ((30, 25, 10), (20, 15, 0), 10),
    ],
)
def test_kill_tests_are_strict(
    candidate: tuple[int, int, int],
    equal_exposure: tuple[int, int, int],
    null_p95: int,
) -> None:
    metrics = _metrics(candidate, equal_exposure, null_p95)

    assert metrics.is_falsified is True


def test_external_contract_and_summary_are_idempotent_and_redacted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("offline campaign must not access the network")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    campaign_input = subject.build_tiingo_d1_trio_intraday_compression_input(
        _snapshot(start_price=Decimal("123.456789"))
    )
    repo_root = _repo(tmp_path)
    artifact_root = tmp_path / "artifacts"
    first = subject.freeze_tiingo_d1_trio_intraday_compression_campaign(
        campaign_input,
        artifact_root=artifact_root,
        repo_root=repo_root,
        code_revision="sha256:" + "a" * 64,
        attempt_id="unit-r1",
    )
    same = subject.freeze_tiingo_d1_trio_intraday_compression_campaign(
        campaign_input,
        artifact_root=artifact_root,
        repo_root=repo_root,
        code_revision="sha256:" + "a" * 64,
        attempt_id="unit-r1",
    )
    with pytest.raises(ValueError, match="immutable artifact conflicts"):
        subject.freeze_tiingo_d1_trio_intraday_compression_campaign(
            campaign_input,
            artifact_root=artifact_root,
            repo_root=repo_root,
            code_revision="sha256:" + "b" * 64,
            attempt_id="unit-r1",
        )
    result = subject.run_tiingo_d1_trio_intraday_compression_campaign(first)

    def evaluation_forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("an existing summary must reattach before target evaluation")

    monkeypatch.setattr(subject, "_evaluate", evaluation_forbidden)
    repeated = subject.run_tiingo_d1_trio_intraday_compression_campaign(same)
    written = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (first.contract_path, result.summary_path)
    )

    assert repeated.summary_sha256 == result.summary_sha256
    assert repeated.metrics is None
    assert repeated.safe_payload()["metrics"] == result.safe_payload()["metrics"]
    assert repeated.registry_outcome.record_sha256 == result.registry_outcome.record_sha256
    assert result.summary_path.is_relative_to(artifact_root)
    assert "123.456789" not in written
    assert "2020-" not in written
    assert '"numeric_metrics_persisted":false' in written
    assert '"profitability_or_pnl_claim":false' in written
    assert '"gpu_used":false' in written

    blocked = repo_root / "not-yet-created-artifacts"
    with pytest.raises(ValueError, match="outside the Git workspace"):
        subject.freeze_tiingo_d1_trio_intraday_compression_campaign(
            campaign_input,
            artifact_root=blocked,
            repo_root=repo_root,
            code_revision="sha256:" + "a" * 64,
            attempt_id="repo-root",
        )
    assert not blocked.exists()


def test_reused_summary_rejects_unallowlisted_content(tmp_path: Path) -> None:
    campaign_input = subject.build_tiingo_d1_trio_intraday_compression_input(_snapshot())
    repo_root = _repo(tmp_path)
    artifact_root = tmp_path / "artifacts"
    campaign = subject.freeze_tiingo_d1_trio_intraday_compression_campaign(
        campaign_input,
        artifact_root=artifact_root,
        repo_root=repo_root,
        code_revision="sha256:" + "a" * 64,
        attempt_id="tampered-r1",
    )
    subject.run_tiingo_d1_trio_intraday_compression_campaign(campaign)
    payload = json.loads(campaign.run_directory.joinpath("cpu-summary.json").read_text())
    payload["raw_rows"] = ["must-not-reattach"]
    campaign.run_directory.joinpath("cpu-summary.json").write_bytes(
        subject._canonical_json(payload)
    )

    with pytest.raises(ValueError, match="summary artifact is invalid"):
        subject.run_tiingo_d1_trio_intraday_compression_campaign(campaign)


def test_leaf_and_runner_have_no_execution_network_or_environment_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = Path(subject.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    assert not imported.intersection({"os", "socket", "subprocess", "requests", "torch"})
    assert "os.environ" not in source
    assert "thericher_v2.execution" not in source
    imported_leaf = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; "
            "import thericher_v2.research.tiingo_d1_trio_intraday_compression_continuation; "
            "raise SystemExit('thericher_v2.execution' in sys.modules)",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert imported_leaf.returncode == 0, imported_leaf.stderr
    legacy_data_api = subprocess.run(
        [
            sys.executable,
            "-c",
            "from thericher_v2.data import load_verified_tiingo_etf_d1_snapshot; "
            "raise SystemExit(not callable(load_verified_tiingo_etf_d1_snapshot))",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert legacy_data_api.returncode == 0, legacy_data_api.stderr

    path = (
        Path(__file__).parents[1]
        / "scripts"
        / "run_tiingo_d1_trio_intraday_compression_continuation.py"
    )
    spec = importlib.util.spec_from_file_location("compression_runner_test", path)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    captured: dict[str, object] = {}
    prepared = SimpleNamespace()
    campaign = SimpleNamespace(contract_sha256="sha256:" + "a" * 64)
    result = SimpleNamespace(
        status="falsified",
        reason="frozen_kill_test_failed",
        summary_sha256="sha256:" + "b" * 64,
        registry_outcome=SimpleNamespace(record_sha256="sha256:" + "c" * 64),
    )

    loaded = SimpleNamespace()

    def load(*_args: object, **kwargs: object) -> SimpleNamespace:
        captured["load"] = kwargs
        return loaded

    def build(value: object) -> SimpleNamespace:
        captured["build"] = value
        return prepared

    def freeze(value: object, **kwargs: object) -> SimpleNamespace:
        captured["freeze"] = {"value": value, **kwargs}
        return campaign

    def run(value: object) -> SimpleNamespace:
        captured["run"] = value
        return result

    monkeypatch.setattr(runner, "load_verified_tiingo_etf_d1_snapshot", load)
    monkeypatch.setattr(runner, "build_tiingo_d1_trio_intraday_compression_input", build)
    monkeypatch.setattr(runner, "freeze_tiingo_d1_trio_intraday_compression_campaign", freeze)
    monkeypatch.setattr(runner, "run_tiingo_d1_trio_intraday_compression_campaign", run)
    runner.main(
        [
            "--snapshot",
            str(tmp_path / "snapshot"),
            "--market-data-root",
            str(tmp_path / "market-data"),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--repo-root",
            str(tmp_path),
            "--attempt-id",
            "unit-r1",
        ]
    )

    assert captured["build"] is loaded
    assert captured["freeze"]["value"] is prepared
    assert captured["run"] is campaign
    assert captured["load"]["dataset_id"] == runner._EXPECTED_DATASET_ID
    assert captured["load"]["expected_dataset_hash"] == runner._EXPECTED_DATASET_HASH
    assert "data/__init__.py" in runner._CAMPAIGN_CODE_PATHS[1].as_posix()
    source = path.read_text(encoding="utf-8")
    for forbidden in (".env", "os.environ", "requests", "socket", "urllib", "torch"):
        assert forbidden not in source


def _decision_at(
    campaign_input: subject.TiingoD1TrioIntradayCompressionInput,
    index: int,
) -> subject._CompressionDecision:
    return next(
        decision
        for decision in campaign_input._validation_decisions
        if decision.index == index
    )


def _metrics(
    candidate: tuple[int, int, int],
    equal_exposure: tuple[int, int, int],
    null_p95: int,
) -> subject.TiingoD1TrioIntradayCompressionMetrics:
    return subject.TiingoD1TrioIntradayCompressionMetrics(
        active_day_count=60,
        active_position_count=70,
        active_symbol_count=3,
        candidate_net_mean_bps_by_cost=tuple(
            zip(("10", "15", "20"), (Decimal(value) for value in candidate), strict=True)
        ),
        equal_exposure_net_mean_bps_by_cost=tuple(
            zip(
                ("10", "15", "20"),
                (Decimal(value) for value in equal_exposure),
                strict=True,
            )
        ),
        null_p95_net_mean_bps_primary_cost=Decimal(null_p95),
        null_count=subject.TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_NULL_COUNT,
    )


def _repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repository"
    repo_root.mkdir(exist_ok=True)
    return repo_root


def _snapshot(
    *,
    count: int = 1500,
    signal_every: int | None = 5,
    start_price: Decimal = Decimal("100"),
) -> LoadedTiingoEtfDailySnapshot:
    rows_by_symbol = {
        symbol: tuple(
            _row(symbol, index, signal_every=signal_every, start_price=start_price)
            for index in range(count)
        )
        for symbol in TIINGO_ETF_D1_SYMBOLS
    }
    snapshot = TiingoEtfDailySnapshot(
        snapshot_dir=Path("D:/market_data/us_equities/fixture-tiingo-etf-d1-r1"),
        dataset_id="us_equities.tiingo_etf_daily.snapshot=fixture-tiingo-etf-d1-r1",
        dataset_hash="sha256:" + "a" * 64,
        manifest_hash="sha256:" + "b" * 64,
        raw_hashes={
            symbol: "sha256:" + character * 64
            for symbol, character in zip(TIINGO_ETF_D1_SYMBOLS, "cde", strict=True)
        },
        session_counts={symbol: count for symbol in TIINGO_ETF_D1_SYMBOLS},
        date_ranges={
            symbol: (rows[0].session_date, rows[-1].session_date)
            for symbol, rows in rows_by_symbol.items()
        },
        event_session_counts={symbol: 0 for symbol in TIINGO_ETF_D1_SYMBOLS},
        row_count=count * len(TIINGO_ETF_D1_SYMBOLS),
        free_percent=50.0,
    )
    return LoadedTiingoEtfDailySnapshot(snapshot=snapshot, rows_by_symbol=rows_by_symbol)


def _row(
    symbol: str,
    index: int,
    *,
    signal_every: int | None,
    start_price: Decimal,
) -> TiingoEtfDailyRow:
    opening = start_price + Decimal(index) / Decimal("100")
    close = opening * Decimal("1.002")
    is_signal = signal_every is not None and index % signal_every == 0
    if is_signal:
        high = opening * Decimal("1.003")
        low = opening * Decimal("0.995")
    else:
        high = opening * Decimal("1.012")
        low = opening * Decimal("0.988")
    return TiingoEtfDailyRow(
        symbol=symbol,
        session_date=date(2020, 1, 1) + timedelta(days=index),
        open=opening,
        high=high,
        low=low,
        close=close,
        volume=Decimal("1000"),
        div_cash=Decimal("0"),
        split_factor=Decimal("1"),
    )
