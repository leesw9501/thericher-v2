from __future__ import annotations

import importlib.util
import json
import os
import socket
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_kis_multitimeframe_momentum_policy_smoke.py"
)
_SPEC = importlib.util.spec_from_file_location("multitimeframe_momentum_smoke_script", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
script = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(script)


def test_script_writes_only_a_safe_external_structural_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _deny_external_access(monkeypatch)
    source = _source()
    monkeypatch.setattr(
        script,
        "load_verified_kis_paper_private_intraday_catalog",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(
        script,
        "require_complete_kis_paper_private_intraday_session",
        lambda _catalog, **_kwargs: source,
    )
    artifact_root = tmp_path / "external-artifacts"

    script.main(
        [
            "--session-date",
            "2026-07-21",
            "--symbol",
            "QQQ",
            "--artifact-root",
            str(artifact_root),
            "--run-label",
            "unit-r1",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    summary_path = (
        artifact_root
        / "research"
        / "multitimeframe-momentum-policy-smoke-v1"
        / "unit-r1"
        / "summary.json"
    )
    assert payload == json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "offline_local_cache_no_broker"
    assert payload["evidence"]["timeframes"] == ["1m", "5m", "10m", "1h", "3h"]
    assert payload["artifact_policy"] == {
        "artifact_root": str(artifact_root.resolve()),
        "broker_called": False,
        "checkpoint_written": False,
        "credential_read": False,
        "network_called": False,
        "raw_market_data_written": False,
    }
    serialized = summary_path.read_text(encoding="utf-8")
    assert "KIS_PAPER_" not in serialized
    assert "open\"" not in serialized
    assert "close\"" not in serialized


def test_script_rejects_an_artifact_root_inside_the_workspace(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="outside the Git workspace"):
        script._reject_repo_artifact_root(_SCRIPT_PATH.parents[1])
    assert not (tmp_path / "unexpected").exists()


def _source() -> CatalogedBars:
    session = us_equity_2026_session(datetime(2026, 7, 21, tzinfo=UTC).date())
    assert session is not None
    bars: list[Bar] = []
    for index in range(390):
        opened = Decimal("100") + Decimal(index) / Decimal("100")
        closed = opened + Decimal("0.02")
        bars.append(
            Bar(
                symbol="QQQ",
                market="US",
                timeframe=Timeframe.M1,
                start_ts=session.window.open_ts + timedelta(minutes=index),
                open=opened,
                high=closed + Decimal("0.01"),
                low=opened - Decimal("0.01"),
                close=closed,
                volume=Decimal("1000") + Decimal(index),
                complete=True,
            )
        )
    return _cataloged_bars_from_verified_loader(
        dataset_id="kis.paper.private.intraday.qqq.nas.m1.smoke-unit-v1",
        dataset_hash="sha256:" + "a" * 64,
        source_path=Path("D:/market_data/unit-multitimeframe-momentum-index.json"),
        bars=tuple(bars),
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("smoke script must not access external state")

    monkeypatch.setattr(os, "getenv", fail_external)
    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
