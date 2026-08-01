from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.market.resample import SessionWindow
from thericher_v2.models.prospective_spy_intraday_session import (
    ProspectiveSpyIntradaySessionRecord,
    build_prospective_spy_intraday_session_record,
)
from thericher_v2.models.sequence_window import (
    CausalMultiTimeframeSequenceWindow,
    CausalSequenceWindow,
)

_SESSION = SessionWindow(
    open_ts=datetime(2026, 8, 3, 13, 30, tzinfo=UTC),
    close_ts=datetime(2026, 8, 3, 20, 0, tzinfo=UTC),
)
_CUTOFF = datetime(2026, 8, 3, 19, 30, tzinfo=UTC)
_SOURCE_CONTRACT_HASH = "sha256:" + "f" * 64


def test_baseline_rejects_a_record_with_a_duplicate_selected_source_bar() -> None:
    record = _record()
    original_m1 = record.sequence_window.windows[Timeframe.M1]
    duplicate_m1 = CausalSequenceWindow(
        timeframe=Timeframe.M1,
        bars=(*original_m1.bars[:-2], original_m1.bars[-1], original_m1.bars[-1]),
        cutoff=_CUTOFF,
    )
    windows = dict(record.sequence_window.windows)
    windows[Timeframe.M1] = duplicate_m1
    duplicate_window = CausalMultiTimeframeSequenceWindow(
        symbol="SPY",
        market="US",
        cutoff=_CUTOFF,
        windows=windows,
    )

    # The public record constructor must not treat structural metadata as a
    # substitute for revalidating the selected completed-bar windows.
    with pytest.raises(
        ValueError,
        match="prospective session sequence window is invalid",
    ):
        replace(record, sequence_window=duplicate_window)


def test_leaf_import_does_not_load_execution_or_kis_provider_modules() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json, sys; "
                "import thericher_v2.models.prospective_spy_intraday_baseline; "
                "print(json.dumps(sorted(name for name in sys.modules "
                "if name.startswith('thericher_v2.'))))"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    imported = set(json.loads(completed.stdout))

    assert not any(
        name == "thericher_v2.execution"
        or name.startswith("thericher_v2.execution.")
        or name == "thericher_v2.data.provider"
        or name.startswith("thericher_v2.data.kis_")
        or name.startswith("thericher_v2.research.kis_")
        for name in imported
    )


def _record() -> ProspectiveSpyIntradaySessionRecord:
    bars = tuple(
        Bar(
            symbol="SPY",
            market="US",
            timeframe=Timeframe.M1,
            start_ts=_SESSION.open_ts + Timeframe.M1.duration * index,
            open=Decimal("100") + Decimal(index) / Decimal("100"),
            high=Decimal("101") + Decimal(index) / Decimal("100"),
            low=Decimal("99") + Decimal(index) / Decimal("100"),
            close=Decimal("100") + Decimal(index) / Decimal("100"),
            volume=Decimal("1"),
            complete=True,
        )
        for index in range(360)
    )
    return build_prospective_spy_intraday_session_record(
        bars,
        session=_SESSION,
        cutoff=_CUTOFF,
        source_contract_hash=_SOURCE_CONTRACT_HASH,
    )
