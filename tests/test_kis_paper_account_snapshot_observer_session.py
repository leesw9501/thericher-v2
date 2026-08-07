"""Focused tests for the pure account-snapshot observer session inspector."""

from __future__ import annotations

import ast
import importlib.util
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "inspect_kis_paper_account_snapshot_observer_session.py"
)


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("snapshot_observer_session", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_regular_session_open_is_eligible() -> None:
    script = _load_script()

    result = script.inspect_session(datetime(2026, 7, 21, 14, 30, tzinfo=UTC))

    assert result == {
        "kind": "kis_paper_snapshot_observer_session",
        "observed_at": "2026-07-21T14:30:00Z",
        "status": "eligible",
    }


def test_holiday_is_session_unavailable() -> None:
    script = _load_script()

    result = script.inspect_session(datetime(2026, 7, 3, 14, 30, tzinfo=UTC))

    assert result["status"] == "session_unavailable"


def test_early_close_is_eligible_before_its_close() -> None:
    script = _load_script()

    result = script.inspect_session(datetime(2026, 11, 27, 17, 0, tzinfo=UTC))

    assert result["status"] == "eligible"


def test_time_at_early_close_is_outside_regular_session() -> None:
    script = _load_script()

    result = script.inspect_session(datetime(2026, 11, 27, 18, 0, tzinfo=UTC))

    assert result["status"] == "outside_regular_session"


def test_out_of_calendar_scope_is_session_unavailable() -> None:
    script = _load_script()

    result = script.inspect_session(datetime(2027, 1, 4, 14, 30, tzinfo=UTC))

    assert result["status"] == "session_unavailable"


def test_non_utc_datetime_is_rejected() -> None:
    script = _load_script()
    non_utc = datetime(2026, 7, 21, 23, 30, tzinfo=timezone(timedelta(hours=9)))

    with pytest.raises(ValueError, match="explicit UTC"):
        script.inspect_session(non_utc)


@pytest.mark.parametrize(
    "observed_at",
    ["not-a-time", "2026-07-21T23:30:00+09:00", "2026-07-21T14:30:00"],
)
def test_cli_rejects_invalid_or_non_utc_observed_at(
    observed_at: str, capsys: pytest.CaptureFixture[str]
) -> None:
    script = _load_script()

    with pytest.raises(SystemExit) as error:
        script.main(["--observed-at", observed_at])

    assert error.value.code == 2
    assert capsys.readouterr().out == ""


def test_cli_outputs_only_the_frozen_session_envelope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()

    script.main(["--observed-at", "2026-07-21T14:30:00Z"])

    assert json.loads(capsys.readouterr().out) == {
        "kind": "kis_paper_snapshot_observer_session",
        "observed_at": "2026-07-21T14:30:00Z",
        "status": "eligible",
    }


def test_script_imports_only_pure_local_dependencies() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        name.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for name in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert imported_modules == {
        "__future__",
        "argparse",
        "collections.abc",
        "datetime",
        "json",
        "thericher_v2.data.us_equity_session",
        "typing",
    }
    for forbidden_token in (
        "os.environ",
        "getenv(",
        "KIS_PAPER_",
        "KIS_LIVE_",
        "requests.",
        "subprocess.",
        "docker",
        "socket",
        "urllib",
    ):
        assert forbidden_token not in source
