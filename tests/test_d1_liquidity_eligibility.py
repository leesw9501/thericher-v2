from __future__ import annotations

import hashlib
import inspect
import json
import os
import socket
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe
from thericher_v2.data import d1_liquidity_eligibility as eligibility_module
from thericher_v2.data import source_scoped_liquid_universe as universe_module
from thericher_v2.data.d1_liquidity_eligibility import (
    D1_LIQUIDITY_ELIGIBILITY_ID,
    D1_LIQUIDITY_ELIGIBILITY_SPEC,
    D1LiquidityEligibilityPartition,
    SourcePartitionedD1LiquidityEligibility,
    _D1LiquidityEligibilityComputation,
    _load_source_partitioned_d1_liquidity_eligibility,
    _materialize_source_partitioned_d1_liquidity_eligibility,
    evaluate_d1_liquidity_eligibility,
    materialize_source_partitioned_d1_liquidity_eligibility,
    require_attested_source_partitioned_d1_liquidity_eligibility,
)
from thericher_v2.data.source_scoped_liquid_universe import (
    SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID,
    SOURCE_SCOPED_LIQUID_UNIVERSE_ID,
    SOURCE_SCOPED_LIQUID_UNIVERSE_NAS_SOURCE_ID,
    SourceScopedLiquidUniverse,
    SourceScopedLiquidUniverseInstrument,
)
from thericher_v2.research import d1_research_eligibility as research_module
from thericher_v2.research.d1_research_eligibility import (
    D1ResearchEligibilityInput,
    build_d1_research_eligibility_input,
    require_attested_d1_research_eligibility_input,
)

_HASH_A = "sha256:" + "a" * 64
_HASH_B = "sha256:" + "b" * 64
_HASH_C = "sha256:" + "c" * 64
_ETF_IDS = ("QQQ/NAS", "SPY/AMS", "IWM/AMS")
_NAS_IDS = ("AAPL/NAS", "AMZN/NAS", "GOOGL/NAS", "META/NAS", "MSFT/NAS", "NVDA/NAS")


def test_completed_d1_boundaries_and_turnover_thresholds_are_categorical() -> None:
    qqq = _instrument("QQQ", "NAS", SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID)
    insufficient = evaluate_d1_liquidity_eligibility(
        instrument=qqq,
        bars=_bars("QQQ", count=59, close=Decimal("10"), volume=Decimal("1000000")),
        dataset_hash=_HASH_A,
    )
    exact = evaluate_d1_liquidity_eligibility(
        instrument=qqq,
        bars=_bars("QQQ", count=60, close=Decimal("10"), volume=Decimal("1000000")),
        dataset_hash=_HASH_A,
    )
    below = evaluate_d1_liquidity_eligibility(
        instrument=qqq,
        bars=_bars(
            "QQQ",
            count=60,
            close=Decimal("9.999999"),
            volume=Decimal("1000000"),
        ),
        dataset_hash=_HASH_A,
    )

    assert insufficient.d1_research_eligible is False
    assert insufficient.ineligibility_reasons == ("insufficient_completed_d1_bars",)
    assert exact.d1_research_eligible is True
    assert exact.ineligibility_reasons == ()
    assert below.d1_research_eligible is False
    assert below.ineligibility_reasons == ("recent_completed_d1_median_turnover_below_threshold",)
    assert not hasattr(exact, "median_dollar_turnover")
    assert not hasattr(exact, "completed_bar_count")


def test_incomplete_or_zero_volume_bars_cannot_qualify_a_stream() -> None:
    qqq = _instrument("QQQ", "NAS", SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID)
    complete_below = _bars(
        "QQQ",
        count=60,
        close=Decimal("1"),
        volume=Decimal("1000000"),
    )
    incomplete_high_turnover = _bars(
        "QQQ",
        count=20,
        close=Decimal("1000"),
        volume=Decimal("1000000"),
        start_index=60,
        complete=False,
    )
    incomplete_ignored = evaluate_d1_liquidity_eligibility(
        instrument=qqq,
        bars=complete_below + incomplete_high_turnover,
        dataset_hash=_HASH_A,
    )
    zero_volume = list(
        _bars("QQQ", count=60, close=Decimal("10"), volume=Decimal("1000000"))
    )
    zero_volume[-1] = _bar(
        "QQQ",
        start_index=59,
        close=Decimal("10"),
        volume=Decimal("0"),
        complete=True,
    )
    zero_volume_result = evaluate_d1_liquidity_eligibility(
        instrument=qqq,
        bars=tuple(zero_volume),
        dataset_hash=_HASH_A,
    )

    assert incomplete_ignored.d1_research_eligible is False
    assert incomplete_ignored.ineligibility_reasons == (
        "recent_completed_d1_median_turnover_below_threshold",
    )
    assert zero_volume_result.d1_research_eligible is False
    assert zero_volume_result.ineligibility_reasons == (
        "recent_completed_d1_volume_not_all_positive",
    )


def test_source_limited_iwm_limitation_survives_a_narrow_rule_pass() -> None:
    iwm = _instrument(
        "IWM",
        "AMS",
        SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID,
        limitations=("source_limited_history_scope", "d1_only"),
    )

    result = evaluate_d1_liquidity_eligibility(
        instrument=iwm,
        bars=_bars("IWM", count=60, close=Decimal("10"), volume=Decimal("1000000")),
        dataset_hash=_HASH_A,
    )

    assert result.d1_research_eligible is True
    assert "source_limited_history_scope" in result.limitations


def test_receipt_is_immutable_redacted_and_reattestable(tmp_path: Path) -> None:
    computation = _computation(tmp_path)
    repository = tmp_path / "repo"
    repository.mkdir()
    output_root = tmp_path / "external-output"

    first = _materialize_source_partitioned_d1_liquidity_eligibility(
        computation=computation,
        output_root=output_root,
        repository_root=repository,
        require_approved_output_root=False,
    )
    second = _materialize_source_partitioned_d1_liquidity_eligibility(
        computation=computation,
        output_root=output_root,
        repository_root=repository,
        require_approved_output_root=False,
    )
    loaded = _load_source_partitioned_d1_liquidity_eligibility(
        receipt_path=first.receipt_path,
        computation=computation,
        repository_root=repository,
        require_approved_receipt_root=False,
    )

    text = first.receipt_path.read_text(encoding="ascii")
    payload = json.loads(text)
    assert first == second
    assert first.receipt_sha256 == _sha256(first.receipt_path.read_bytes())
    assert loaded.receipt_id == D1_LIQUIDITY_ELIGIBILITY_ID
    assert loaded.receipt_sha256 == first.receipt_sha256
    assert tuple(partition.source_partition_id for partition in loaded.partitions) == (
        SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID,
        SOURCE_SCOPED_LIQUID_UNIVERSE_NAS_SOURCE_ID,
    )
    assert payload["contract"] == {
        "minimum_completed_bars": 60,
        "minimum_median_dollar_turnover": "10000000",
        "recent_completed_window_bars": 20,
        "timeframe": "1d",
    }
    assert payload["redaction"] == {
        "account_facts_persisted": False,
        "credentials_persisted": False,
        "observed_prices_persisted": False,
        "observed_turnover_values_persisted": False,
        "observed_volumes_persisted": False,
        "order_facts_persisted": False,
        "raw_rows_persisted": False,
    }
    assert "123.456789" not in text
    assert "98765.4321" not in text
    assert "12193262" not in text
    for forbidden_field in (
        '"open":',
        '"high":',
        '"low":',
        '"close":',
        '"volume":',
        '"turnover":',
        '"median_dollar_turnover":',
    ):
        assert forbidden_field not in text
    assert payload["scope"]["historical_membership_eligible"] is False
    assert payload["scope"]["ranking_eligible"] is False
    assert payload["scope"]["paper_trading_eligible"] is False
    assert payload["scope"]["executable_liquidity_eligible"] is False


def test_receipt_rejects_tampering_and_git_output(tmp_path: Path) -> None:
    computation = _computation(tmp_path)
    repository = tmp_path / "repo"
    repository.mkdir()
    materialization = _materialize_source_partitioned_d1_liquidity_eligibility(
        computation=computation,
        output_root=tmp_path / "external-output",
        repository_root=repository,
        require_approved_output_root=False,
    )
    payload = json.loads(materialization.receipt_path.read_text(encoding="ascii"))
    payload["scope"]["ranking_eligible"] = True
    materialization.receipt_path.write_text(json.dumps(payload) + "\n", encoding="ascii")

    with pytest.raises(ValueError, match="source provenance"):
        _load_source_partitioned_d1_liquidity_eligibility(
            receipt_path=materialization.receipt_path,
            computation=computation,
            repository_root=repository,
            require_approved_receipt_root=False,
        )
    with pytest.raises(ValueError, match="outside Git"):
        _materialize_source_partitioned_d1_liquidity_eligibility(
            computation=computation,
            output_root=repository / "forbidden-output",
            repository_root=repository,
            require_approved_output_root=False,
        )
    assert not (repository / "forbidden-output").exists()


def test_research_consumer_preserves_partitions_without_selection(tmp_path: Path) -> None:
    computation = _computation(tmp_path)
    repository = tmp_path / "repo"
    repository.mkdir()
    materialization = _materialize_source_partitioned_d1_liquidity_eligibility(
        computation=computation,
        output_root=tmp_path / "external-output",
        repository_root=repository,
        require_approved_output_root=False,
    )
    eligibility = _load_source_partitioned_d1_liquidity_eligibility(
        receipt_path=materialization.receipt_path,
        computation=computation,
        repository_root=repository,
        require_approved_receipt_root=False,
    )
    input = build_d1_research_eligibility_input(eligibility)

    assert input.receipt_sha256 == eligibility.receipt_sha256
    assert [partition.source_partition_id for partition in input.partitions] == [
        SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID,
        SOURCE_SCOPED_LIQUID_UNIVERSE_NAS_SOURCE_ID,
    ]
    assert [
        instrument.instrument_id for instrument in input.partitions[0].instruments
    ] == list(_ETF_IDS)
    assert [
        instrument.instrument_id for instrument in input.partitions[1].instruments
    ] == list(_NAS_IDS)
    assert input.historical_membership_eligible is False
    assert input.ranking_eligible is False
    assert input.model_selection_eligible is False
    assert input.paper_trading_eligible is False
    assert input.executable_liquidity_eligible is False
    assert input.cross_partition_alignment_eligible is False
    assert not hasattr(input, "instruments")
    assert not hasattr(input.partitions[0].instruments[0], "score")
    assert not hasattr(input.partitions[0].instruments[0], "action")
    forged_eligibility = object.__new__(SourcePartitionedD1LiquidityEligibility)
    forged_input = object.__new__(D1ResearchEligibilityInput)
    with pytest.raises(ValueError, match="receipt attestation"):
        build_d1_research_eligibility_input(forged_eligibility)
    with pytest.raises(ValueError, match="receipt attestation"):
        require_attested_source_partitioned_d1_liquidity_eligibility(forged_eligibility)
    with pytest.raises(ValueError, match="builder attestation"):
        require_attested_d1_research_eligibility_input(forged_input)
    object.__setattr__(eligibility, "ranking_eligible", True)
    with pytest.raises(ValueError, match="receipt attestation"):
        require_attested_source_partitioned_d1_liquidity_eligibility(eligibility)
    object.__setattr__(input, "executable_liquidity_eligible", True)
    with pytest.raises(ValueError, match="builder attestation"):
        require_attested_d1_research_eligibility_input(input)
    assert tuple(inspect.signature(build_d1_research_eligibility_input).parameters) == (
        "eligibility",
    )


def test_current_computation_reattests_the_source_universe_before_bar_computation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[str] = []
    universe = _attested_universe(tmp_path)
    computation = _computation(tmp_path)

    def materialize(*_args: object, **_kwargs: object) -> SimpleNamespace:
        events.append("materialize-universe")
        return SimpleNamespace(
            manifest_path=tmp_path / "external-source-universe" / "manifest.json"
        )

    def load(*_args: object, **_kwargs: object) -> SourceScopedLiquidUniverse:
        events.append("load-universe")
        return universe

    def compute(*_args: object, **_kwargs: object) -> _D1LiquidityEligibilityComputation:
        events.append("read-bars")
        return computation

    monkeypatch.setattr(
        eligibility_module,
        "materialize_source_scoped_liquid_universe_manifest",
        materialize,
    )
    monkeypatch.setattr(
        eligibility_module,
        "load_source_scoped_liquid_universe_manifest",
        load,
    )
    monkeypatch.setattr(
        eligibility_module,
        "_compute_d1_liquidity_eligibility_from_universe",
        compute,
    )

    result = eligibility_module._compute_current_d1_liquidity_eligibility(
        repository_root=tmp_path
    )

    assert result is computation
    assert events == ["materialize-universe", "load-universe", "read-bars"]


def test_d1_contract_is_offline_without_credentials_network_or_broker_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qqq = _instrument("QQQ", "NAS", SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("D1 eligibility must not use this capability")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    result = evaluate_d1_liquidity_eligibility(
        instrument=qqq,
        bars=_bars("QQQ", count=60, close=Decimal("10"), volume=Decimal("1000000")),
        dataset_hash=_HASH_A,
    )

    assert result.d1_research_eligible is True
    for module in (eligibility_module, research_module):
        source = inspect.getsource(module).lower()
        for forbidden_name in (
            "urllib",
            "requests",
            "socket",
            "getenv",
            ".env",
            "orderintent",
            "torch",
            "cuda",
        ):
            assert forbidden_name not in source
    assert "source_paths" not in inspect.signature(
        materialize_source_partitioned_d1_liquidity_eligibility
    ).parameters
    assert "bars" not in inspect.signature(
        materialize_source_partitioned_d1_liquidity_eligibility
    ).parameters


def _computation(root: Path) -> _D1LiquidityEligibilityComputation:
    universe = _attested_universe(root)
    facts = []
    for instrument in universe.instruments:
        facts.append(
            evaluate_d1_liquidity_eligibility(
                instrument=instrument,
                bars=_bars(
                    instrument.symbol,
                    count=60,
                    close=Decimal("123.456789"),
                    volume=Decimal("98765.4321"),
                ),
                dataset_hash=(
                    _HASH_C
                    if instrument.source_id == SOURCE_SCOPED_LIQUID_UNIVERSE_NAS_SOURCE_ID
                    else _HASH_A
                ),
            )
        )
    return _D1LiquidityEligibilityComputation(
        source_universe_manifest_id=universe.manifest_id,
        source_universe_manifest_sha256=universe.manifest_sha256,
        spec=D1_LIQUIDITY_ELIGIBILITY_SPEC,
        partitions=(
            D1LiquidityEligibilityPartition(
                source_partition_id=SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID,
                instruments=tuple(facts[: len(_ETF_IDS)]),
            ),
            D1LiquidityEligibilityPartition(
                source_partition_id=SOURCE_SCOPED_LIQUID_UNIVERSE_NAS_SOURCE_ID,
                instruments=tuple(facts[len(_ETF_IDS) :]),
            ),
        ),
    )


def _attested_universe(root: Path) -> SourceScopedLiquidUniverse:
    manifest_path = root / "external-source-universe" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{}\n", encoding="ascii")
    instruments = tuple(
        _instrument(
            symbol,
            venue,
            SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID,
            limitations=("d1_only",)
            if symbol != "IWM"
            else ("d1_only", "source_limited_history_scope"),
        )
        for symbol, venue in (item.split("/") for item in _ETF_IDS)
    ) + tuple(
        _instrument(
            symbol,
            venue,
            SOURCE_SCOPED_LIQUID_UNIVERSE_NAS_SOURCE_ID,
            limitations=("d1_only", "current_source_scoped_only"),
        )
        for symbol, venue in (item.split("/") for item in _NAS_IDS)
    )
    result = object.__new__(SourceScopedLiquidUniverse)
    object.__setattr__(result, "manifest_id", SOURCE_SCOPED_LIQUID_UNIVERSE_ID)
    object.__setattr__(result, "manifest_sha256", _HASH_B)
    object.__setattr__(result, "manifest_path", manifest_path)
    object.__setattr__(result, "instruments", instruments)
    object.__setattr__(result, "membership_scope", "current_source_scoped_only")
    object.__setattr__(result, "historical_membership_eligible", False)
    object.__setattr__(result, "ranking_eligible", False)
    object.__setattr__(result, "paper_trading_eligible", False)
    object.__setattr__(result, "model_selection_eligible", False)
    object.__setattr__(result, "liquidity_qualified", False)
    object.__setattr__(result, "cross_partition_alignment_eligible", False)
    object.__setattr__(result, "limitations", universe_module._BASE_LIMITATIONS)
    object.__setattr__(result, "schema_version", SCHEMA_VERSION)
    object.__setattr__(result, "_attestation", universe_module._UNIVERSE_ATTESTATION)
    return result


def _instrument(
    symbol: str,
    venue: str,
    source_id: str,
    *,
    limitations: tuple[str, ...] = ("d1_only",),
) -> SourceScopedLiquidUniverseInstrument:
    return SourceScopedLiquidUniverseInstrument(
        instrument_id=f"{symbol}/{venue}",
        symbol=symbol,
        venue=venue,
        source_id=source_id,
        dataset_id=(
            "fixture.etf.daily"
            if source_id == SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID
            else "fixture.nas.daily"
        ),
        source_snapshot_sha256=(
            _HASH_A
            if source_id == SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID
            else _HASH_B
        ),
        supported_timeframes=(Timeframe.D1,),
        availability_scope="fixture-current-source-scope",
        limitations=limitations,
    )


def _bars(
    symbol: str,
    *,
    count: int,
    close: Decimal,
    volume: Decimal,
    start_index: int = 0,
    complete: bool = True,
) -> tuple[Bar, ...]:
    return tuple(
        _bar(
            symbol,
            start_index=start_index + index,
            close=close,
            volume=volume,
            complete=complete,
        )
        for index in range(count)
    )


def _bar(
    symbol: str,
    *,
    start_index: int,
    close: Decimal,
    volume: Decimal,
    complete: bool,
) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=start_index),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=volume,
        complete=complete,
    )


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()
