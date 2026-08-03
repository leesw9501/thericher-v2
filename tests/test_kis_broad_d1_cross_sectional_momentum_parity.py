from __future__ import annotations

import importlib
import inspect
import socket
import urllib.request
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.execution import kis_broad_d1_cross_sectional_momentum_parity as parity
from thericher_v2.execution.local_paper import LocalPaperBroker


def _bar(
    start_ts: datetime,
    *,
    timeframe: Timeframe = Timeframe.D1,
    complete: bool = True,
    symbol: str = "AAA",
) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=timeframe,
        start_ts=start_ts,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.50"),
        volume=Decimal("1000"),
        complete=complete,
    )


def _attest(**overrides: object) -> parity.D1CrossSectionalMomentumParityAttestation:
    arguments: dict[str, object] = {
        "signal_bar": _bar(datetime(2026, 1, 2, tzinfo=UTC)),
        "execution_bar": _bar(datetime(2026, 1, 5, tzinfo=UTC)),
        "next_observed_execution_bar": True,
        "source_limitations": parity.BROAD_D1_SOURCE_LIMITATIONS,
        "input_contract_ref": "sha256:" + "a" * 64,
    }
    arguments.update(overrides)
    return parity.attest_broad_d1_cross_sectional_momentum_parity(**arguments)  # type: ignore[arg-type]


def test_attestation_represents_only_completed_d1_to_next_observed_open() -> None:
    result = _attest()

    assert result.input_contract_ref == "sha256:" + "a" * 64
    assert result.source_limitations == parity.BROAD_D1_SOURCE_LIMITATIONS
    assert result.timing_rule == "completed_d1_t_to_next_observed_d1_open"
    assert result.next_observed_execution_bar_attested is True
    assert result.semantic_representability == "represented"
    assert result.executable_or_paper_eligibility == "not_evaluated_by_semantic_attestation"
    assert result.round_trip_stress_bps == (Decimal("5"), Decimal("10"), Decimal("20"))
    assert result.cost_assumption_status == (
        "research_accounting_assumption_not_verified_fill_cost_or_liquidity_model"
    )
    assert result.safe_payload() == {
        "input_contract_ref": "sha256:" + "a" * 64,
        "source_limitations": list(parity.BROAD_D1_SOURCE_LIMITATIONS),
        "timing": {
            "rule": "completed_d1_t_to_next_observed_d1_open",
            "next_observed_execution_bar_attested": True,
            "semantic_representability": "represented",
            "executable_or_paper_eligibility": "not_evaluated_by_semantic_attestation",
        },
        "round_trip_stress": {
            "bps": ["5", "10", "20"],
            "status": "research_accounting_assumption_not_verified_fill_cost_or_liquidity_model",
        },
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    (
        ({"signal_bar": _bar(datetime(2026, 1, 2, tzinfo=UTC), complete=False)}, "complete"),
        (
            {
                "signal_bar": _bar(datetime(2026, 1, 2, tzinfo=UTC), timeframe=Timeframe.M1),
                "execution_bar": _bar(
                    datetime(2026, 1, 2, 0, 1, tzinfo=UTC),
                    timeframe=Timeframe.M1,
                ),
            },
            "D1",
        ),
        ({"next_observed_execution_bar": False}, "next_observed_execution_bar"),
        (
            {"execution_bar": _bar(datetime(2026, 1, 2, 20, tzinfo=UTC))},
            "later observed UTC date",
        ),
        ({"source_limitations": ()}, "source_limitations"),
        (
            {"source_limitations": parity.BROAD_D1_SOURCE_LIMITATIONS[:-1]},
            "missing required values",
        ),
        ({"input_contract_ref": "   "}, "input_contract_ref"),
    ),
)
def test_attestation_rejects_invalid_assumptions(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        _attest(**overrides)


def test_attestation_has_no_network_or_credential_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("pure parity attestation must remain side-effect free")

    original_open = Path.open
    original_read_text = Path.read_text

    def guard_open(path: Path, *args: object, **kwargs: object):
        if path.name.lower().startswith(".env"):
            raise AssertionError("pure parity attestation must not read credential files")
        return original_open(path, *args, **kwargs)

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.lower().startswith(".env"):
            raise AssertionError("pure parity attestation must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(Path, "open", guard_open)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    reloaded = importlib.reload(parity)
    result = reloaded.attest_broad_d1_cross_sectional_momentum_parity(
        signal_bar=_bar(datetime(2026, 1, 2, tzinfo=UTC)),
        execution_bar=_bar(datetime(2026, 1, 5, tzinfo=UTC)),
        next_observed_execution_bar=True,
        source_limitations=reloaded.BROAD_D1_SOURCE_LIMITATIONS,
        input_contract_ref=None,
    )

    assert result.input_contract_ref is None
    assert result.executable_or_paper_eligibility == "not_evaluated_by_semantic_attestation"


def test_attestation_module_has_no_forbidden_route_or_io_surface() -> None:
    source = inspect.getsource(parity)

    for forbidden in (
        "socket",
        "urllib",
        "requests",
        "dotenv",
        "os.environ",
        "OrderIntent",
        "EventStore",
        "LocalPaperBroker",
        "KIS_PAPER",
        "KIS_LIVE",
        ".env",
        "http://",
        "https://",
    ):
        assert forbidden not in source


def test_attestation_timing_matches_existing_daily_replay_shape_without_invoking_route() -> None:
    signal = _bar(datetime(2026, 1, 2, tzinfo=UTC))
    execution = _bar(datetime(2026, 1, 5, tzinfo=UTC))
    result = _attest(signal_bar=signal, execution_bar=execution)
    route_validator = object.__new__(LocalPaperBroker)
    route_identity = SimpleNamespace(symbol="AAA", market="US")

    assert route_validator._validate_next_bar(route_identity, signal, execution) is None
    assert result.timing_rule == "completed_d1_t_to_next_observed_d1_open"
    assert result.executable_or_paper_eligibility == "not_evaluated_by_semantic_attestation"

    with pytest.raises(ValueError, match="later observed UTC date"):
        route_validator._validate_next_bar(
            route_identity,
            signal,
            _bar(datetime(2026, 1, 2, 20, tzinfo=UTC)),
        )
