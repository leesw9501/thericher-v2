from __future__ import annotations

import builtins
import io
import json
import os
import socket
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.market.resample import SessionWindow
from thericher_v2.models.prospective_spy_intraday_observation import (
    observe_prospective_spy_intraday_baseline,
)
from thericher_v2.models.prospective_spy_intraday_session import (
    ProspectiveSpyIntradaySessionRecord,
    build_prospective_spy_intraday_session_record,
)

_SESSION = SessionWindow(
    open_ts=datetime(2026, 8, 3, 13, 30, tzinfo=UTC),
    close_ts=datetime(2026, 8, 3, 20, 0, tzinfo=UTC),
)
_CUTOFF = datetime(2026, 8, 3, 19, 30, tzinfo=UTC)
_SOURCE_CONTRACT_HASH = "sha256:" + "c" * 64
_FORBIDDEN_SAFE_KEYS = frozenset(
    {
        "account",
        "close",
        "credential",
        "file",
        "high",
        "low",
        "ohlcv",
        "open",
        "order",
        "password",
        "path",
        "price",
        "quantity",
        "secret",
        "token",
        "volume",
    }
)


def test_same_input_produces_a_byte_stable_source_safe_receipt() -> None:
    first = observe_prospective_spy_intraday_baseline(_record())
    second = observe_prospective_spy_intraday_baseline(_record())

    assert first.receipt.canonical_json() == second.receipt.canonical_json()
    assert first.receipt.receipt_id == second.receipt.receipt_id
    assert first.safe_payload() == first.receipt.to_payload()


def test_selected_bar_value_change_commits_to_a_new_receipt_without_changing_action() -> None:
    original = observe_prospective_spy_intraday_baseline(_record())
    changed_bars = list(_source_bars())
    selected = changed_bars[-1]
    changed_bars[-1] = replace(
        selected,
        open=selected.open + Decimal("0.001"),
        high=selected.high + Decimal("0.001"),
        low=selected.low + Decimal("0.001"),
        close=selected.close + Decimal("0.001"),
        volume=selected.volume + Decimal("1"),
    )
    changed_record = _record(tuple(changed_bars))
    changed = observe_prospective_spy_intraday_baseline(changed_record)

    assert original.evaluation.proposal.action == changed.evaluation.proposal.action == "enter"
    assert original.record.contract_hash == changed_record.contract_hash
    assert (
        original.receipt.bar_content_commitment_sha256
        != changed.receipt.bar_content_commitment_sha256
    )
    assert original.receipt.receipt_id != changed.receipt.receipt_id


def test_safe_payload_excludes_raw_source_values_and_sensitive_or_execution_fields() -> None:
    observation = observe_prospective_spy_intraday_baseline(_record())
    payload = observation.safe_payload()
    encoded = observation.receipt.canonical_json()

    _assert_safe_payload(payload)
    assert json.loads(encoded) == payload
    for raw_source_value in ("111.111", "112.111", "110.111", "111.611", "7777"):
        assert raw_source_value not in encoded


def test_direct_leaf_import_does_not_load_data_research_execution_or_kis_modules() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json, sys; "
                "import thericher_v2.models.prospective_spy_intraday_observation; "
                "print(json.dumps(sorted(name for name in sys.modules "
                "if name.startswith('thericher_v2.'))))"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    imported = set(json.loads(completed.stdout))

    for package in (
        "thericher_v2.data",
        "thericher_v2.research",
        "thericher_v2.execution",
    ):
        assert not any(name == package or name.startswith(f"{package}.") for name in imported)
    assert not any(
        name.startswith("thericher_v2.data.kis_")
        or name.startswith("thericher_v2.research.kis_")
        or name.startswith("thericher_v2.execution.kis_")
        for name in imported
    )


def test_observation_performs_no_socket_or_dotenv_read(monkeypatch) -> None:
    record = _record()
    dotenv_reads: list[object] = []
    original_builtin_open = builtins.open
    original_io_open = io.open
    original_path_open = Path.open

    def guarded_open(file: object, *args: object, **kwargs: object) -> Any:
        _reject_dotenv_read(file, dotenv_reads)
        return original_builtin_open(file, *args, **kwargs)

    def guarded_io_open(file: object, *args: object, **kwargs: object) -> Any:
        _reject_dotenv_read(file, dotenv_reads)
        return original_io_open(file, *args, **kwargs)

    def guarded_path_open(path: Path, *args: object, **kwargs: object) -> Any:
        _reject_dotenv_read(path, dotenv_reads)
        return original_path_open(path, *args, **kwargs)

    def reject_socket(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("pure observation path must not open a socket")

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(io, "open", guarded_io_open)
    monkeypatch.setattr(Path, "open", guarded_path_open)
    monkeypatch.setattr(socket, "socket", reject_socket)
    monkeypatch.setattr(socket, "create_connection", reject_socket)

    observation = observe_prospective_spy_intraday_baseline(record)

    assert observation.receipt.decision_class == "enter"
    assert dotenv_reads == []


def _record(
    bars: tuple[Bar, ...] | None = None,
) -> ProspectiveSpyIntradaySessionRecord:
    return build_prospective_spy_intraday_session_record(
        _source_bars() if bars is None else bars,
        session=_SESSION,
        cutoff=_CUTOFF,
        source_contract_hash=_SOURCE_CONTRACT_HASH,
    )


def _source_bars() -> tuple[Bar, ...]:
    count = (_CUTOFF - _SESSION.open_ts) // Timeframe.M1.duration
    return tuple(_bar_at(index) for index in range(count))


def _bar_at(index: int) -> Bar:
    open_value = Decimal("111.111") + Decimal(index) / Decimal("1000")
    return Bar(
        symbol="SPY",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=_SESSION.open_ts + Timeframe.M1.duration * index,
        open=open_value,
        high=open_value + Decimal("1"),
        low=open_value - Decimal("1"),
        close=open_value + Decimal("0.5"),
        volume=Decimal("7777"),
        complete=True,
    )


def _assert_safe_payload(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            assert isinstance(key, str)
            normalized_key = key.casefold()
            assert normalized_key not in _FORBIDDEN_SAFE_KEYS
            _assert_safe_payload(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_safe_payload(nested)
    else:
        assert value is None or isinstance(value, (str, int, bool))


def _reject_dotenv_read(file: object, reads: list[object]) -> None:
    if os.fspath(file).casefold().endswith(".env"):
        reads.append(file)
        raise AssertionError("pure observation path must not read .env")
