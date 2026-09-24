from __future__ import annotations

import importlib.util
import json
import runpy
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest

from thericher_v2.execution import kis_market_data, kis_market_data_rate_gate
from thericher_v2.execution import kis_paper_daily_spy_head as head_module
from thericher_v2.execution.kis_paper_daily_spy_head import (
    KisPaperDailySpyHeadCollection,
)

NOW = datetime(2026, 9, 24, 13, 15, tzinfo=UTC)
_RUNTIME_NAMES = (
    "load_kis_paper_market_data_config",
    "KisPaperMarketDataRateGate",
    "KisPaperMarketDataTokenStartGate",
    "UrllibKisPaperMarketDataTransport",
    "KisPaperMarketDataClient",
    "collect_kis_paper_daily_spy_head_once",
)


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = _load_script()
    for name in _RUNTIME_NAMES:
        monkeypatch.setattr(module, name, Mock(name=name))
    return module


def test_without_execute_does_not_touch_runtime(
    script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert script.main([]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "execute_flag_required",
    }
    for name in _RUNTIME_NAMES:
        getattr(script, name).assert_not_called()


@pytest.mark.parametrize("status", ["collected", "unchanged"])
def test_success_preserves_payload_and_runtime_wiring(
    script: ModuleType, capsys: pytest.CaptureFixture[str], status: str
) -> None:
    payload = {
        "schema_version": 1,
        "kind": "kis_paper_daily_spy_head_collection",
        "status": status,
        "observed_at": "2026-09-24T13:15:00Z",
        "eligible_through_session": "2026-09-23",
        "row_count": 2,
        "reason": None,
        "snapshot": {
            "schema_version": 1,
            "kind": "kis_paper_daily_spy_head_snapshot",
            "dataset_id": "synthetic-head",
            "dataset_hash": "sha256:" + "a" * 64,
            "symbol": "SPY",
            "exchange": "AMS",
            "last_session": "2026-09-23",
            "row_count": 2,
            "collected_at": "2026-09-24T13:15:00Z",
            "current_exchange_session_excluded": True,
        },
        "paper_only": True,
    }
    result = Mock(status=status)
    result.safe_payload.return_value = payload
    script.collect_kis_paper_daily_spy_head_once.return_value = result
    root = Path("isolated") / "daily-head" / "v1"
    repository = Path("isolated") / "repository"
    dotenv = Path("isolated") / "unused-env"

    assert (
        script.main(
            ["--execute", "--cache-root", str(root), "--repository-root", str(repository)],
            clock=lambda: NOW,
            dotenv_path=dotenv,
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out) == payload
    assert "failure_stage" not in payload
    assert "failure_category" not in payload
    script.load_kis_paper_market_data_config.assert_called_once_with(dotenv)
    control = root.parent.parent / "collection-control-v1"
    script.KisPaperMarketDataRateGate.assert_called_once_with(control_root=control)
    script.KisPaperMarketDataTokenStartGate.assert_called_once_with(control_root=control)
    script.UrllibKisPaperMarketDataTransport.assert_called_once_with(
        request_gate=script.KisPaperMarketDataRateGate.return_value,
        token_start_gate=script.KisPaperMarketDataTokenStartGate.return_value,
    )
    script.KisPaperMarketDataClient.assert_called_once_with(
        config=script.load_kis_paper_market_data_config.return_value,
        transport=script.UrllibKisPaperMarketDataTransport.return_value,
    )
    script.collect_kis_paper_daily_spy_head_once.assert_called_once_with(
        script.KisPaperMarketDataClient.return_value,
        cache_root=root,
        repository_root=repository,
        observed_at=NOW,
    )


@pytest.mark.parametrize("eligible_through", [None, date(2026, 9, 23)])
def test_typed_unavailable_result_exits_nonzero_with_fixed_diagnostics(
    script: ModuleType,
    capsys: pytest.CaptureFixture[str],
    eligible_through: date | None,
) -> None:
    result = KisPaperDailySpyHeadCollection(
        status="unavailable",
        observed_at=NOW,
        eligible_through_session=eligible_through,
        row_count=0,
        snapshot=None,
        reason="insufficient_completed_rows",
    )
    script.collect_kis_paper_daily_spy_head_once.return_value = result

    assert script.main(["--execute"], clock=lambda: NOW) == 20
    assert json.loads(capsys.readouterr().out) == {
        **result.safe_payload(),
        "failure_stage": "collection",
        "failure_category": "insufficient_completed_rows",
    }


@pytest.mark.parametrize(
    ("name", "stage"),
    [
        ("load_kis_paper_market_data_config", "environment"),
        ("KisPaperMarketDataRateGate", "control_gate"),
        ("KisPaperMarketDataTokenStartGate", "control_gate"),
        ("UrllibKisPaperMarketDataTransport", "client_setup"),
        ("KisPaperMarketDataClient", "client_setup"),
        ("collect_kis_paper_daily_spy_head_once", "collection"),
    ],
)
def test_failure_stage_and_short_circuit_are_source_safe(
    script: ModuleType, capsys: pytest.CaptureFixture[str], name: str, stage: str
) -> None:
    getattr(script, name).side_effect = OSError("sensitive path and provider body")

    assert script.main(["--execute"], clock=lambda: NOW) == 20
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "status": "unavailable",
        "reason": "daily_head_unavailable",
        "failure_stage": stage,
        "failure_category": "io_error",
    }
    for later_name in _RUNTIME_NAMES[_RUNTIME_NAMES.index(name) + 1 :]:
        getattr(script, later_name).assert_not_called()


@pytest.mark.parametrize(
    "code",
    [
        "config_missing",
        "paper_host_required",
        "request_not_allowlisted",
        "redirect_rejected",
        "transport_failure",
        "response_invalid",
        "daily_response_invalid",
        "daily_page_limit_exceeded",
        "rate_limited",
        "auth_rejected",
        "auth_response_invalid",
        kis_market_data_rate_gate.KIS_PAPER_MARKET_DATA_TOKEN_REQUEST_NOT_DUE_REASON,
    ],
)
def test_market_data_failure_category_is_allowlisted(
    script: ModuleType, capsys: pytest.CaptureFixture[str], code: str
) -> None:
    script.collect_kis_paper_daily_spy_head_once.side_effect = (
        kis_market_data.KisPaperMarketDataError(code)
    )

    assert script.main(["--execute"], clock=lambda: NOW) == 20
    assert json.loads(capsys.readouterr().out) == {
        "status": "unavailable",
        "reason": "market_data_unavailable",
        "failure_stage": "collection",
        "failure_category": code,
    }


@pytest.mark.parametrize(
    ("error", "reason", "category"),
    [
        (
            kis_market_data.KisPaperMarketDataError("sensitive-body"),
            "market_data_unavailable",
            "market_data_error",
        ),
        (
            kis_market_data.KisPaperMarketDataError("auth_rejected sensitive-body"),
            "market_data_unavailable",
            "market_data_error",
        ),
        (
            kis_market_data.KisPaperMarketDataError("auth_rejected", "sensitive-body"),
            "market_data_unavailable",
            "market_data_error",
        ),
        (
            kis_market_data.KisPaperMarketDataError(["sensitive-body"]),
            "market_data_unavailable",
            "market_data_error",
        ),
        (kis_market_data.KisPaperMarketDataError(), "market_data_unavailable", "market_data_error"),
        (
            head_module.KisPaperDailySpyHeadError("sensitive-body"),
            "daily_head_unavailable",
            "head_contract",
        ),
        (ValueError("sensitive-body"), "daily_head_unavailable", "invalid_input"),
        (OSError("sensitive-body"), "daily_head_unavailable", "io_error"),
        (RuntimeError("sensitive-body"), "daily_head_unavailable", "unexpected_error"),
    ],
)
def test_exception_contents_are_never_emitted(
    script: ModuleType,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    reason: str,
    category: str,
) -> None:
    script.collect_kis_paper_daily_spy_head_once.side_effect = error

    assert script.main(["--execute"], clock=lambda: NOW) == 20
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "sensitive-body" not in captured.out
    assert json.loads(captured.out) == {
        "status": "unavailable",
        "reason": reason,
        "failure_stage": "collection",
        "failure_category": category,
    }


@pytest.mark.parametrize("exit_code", [0, 20])
def test_cli_propagates_exit_code_without_real_runtime(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], exit_code: int
) -> None:
    mocks = []
    for module, names in (
        (
            kis_market_data,
            (
                "load_kis_paper_market_data_config",
                "KisPaperMarketDataClient",
                "UrllibKisPaperMarketDataTransport",
            ),
        ),
        (
            kis_market_data_rate_gate,
            (
                "KisPaperMarketDataRateGate",
                "KisPaperMarketDataTokenStartGate",
            ),
        ),
        (head_module, ("collect_kis_paper_daily_spy_head_once",)),
    ):
        for name in names:
            mock = Mock(name=name)
            monkeypatch.setattr(module, name, mock)
            mocks.append(mock)
    if exit_code:
        kis_market_data.load_kis_paper_market_data_config.side_effect = (
            kis_market_data.KisPaperMarketDataError("config_missing")
        )
    script_path = Path(__file__).parents[1] / "scripts" / "collect_kis_paper_daily_spy_head.py"
    monkeypatch.setattr(sys, "argv", [str(script_path), *(["--execute"] if exit_code else [])])

    with pytest.raises(SystemExit) as caught:
        runpy.run_path(str(script_path), run_name="__main__")

    assert caught.value.code == exit_code
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out)["status"] == ("unavailable" if exit_code else "not_executed")
    for mock in mocks[1 if exit_code else 0 :]:
        mock.assert_not_called()


def test_daily_head_uses_the_same_control_root_as_daily_and_intraday_workers() -> None:
    script = _load_script()

    root = script._shared_control_root(
        Path("D:/market_data/us_equities/kis_paper_private/daily-head/v1")
    )

    assert root == Path("D:/market_data/us_equities/kis_paper_private/collection-control-v1")


def _load_script() -> ModuleType:
    script_path = Path(__file__).parents[1] / "scripts" / "collect_kis_paper_daily_spy_head.py"
    spec = importlib.util.spec_from_file_location(
        "collect_kis_paper_daily_spy_head_for_test",
        script_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
