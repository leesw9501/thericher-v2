from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_credentialed_collection_uses_nonreserving_token_due_check(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script = _script_module()
    token_gate = _TokenGate()
    rate_gate = _RateGate()
    emitted: dict[str, object] = {}
    collected: dict[str, object] = {}

    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", lambda **_kwargs: rate_gate)
    monkeypatch.setattr(script, "KisPaperMarketDataTokenStartGate", lambda **_kwargs: token_gate)
    monkeypatch.setattr(
        script,
        "UrllibKisPaperDailyPairForwardTransport",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", lambda: object())
    monkeypatch.setattr(script, "KisPaperMarketDataClient", lambda **_kwargs: object())
    monkeypatch.setattr(
        script,
        "collect_kis_paper_daily_pair_forward_once",
        lambda *_args, **_kwargs: collected.setdefault(
            "result",
            SimpleNamespace(status="ready", safe_payload=lambda: {"status": "ready"}),
        ),
    )
    monkeypatch.setattr(
        script,
        "_write_source_safe_receipt",
        lambda **kwargs: emitted.update(kwargs)
        or (tmp_path / "receipt.json", "sha256:" + "a" * 64),
    )

    exit_code = script._run_credentialed_collection(  # noqa: SLF001
        cache_root=tmp_path / "cache",
        control_root=tmp_path / "control",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repository",
        frozen_boundary=datetime(2026, 7, 24, tzinfo=UTC).date(),
        observed_at=datetime(2026, 8, 3, 21, tzinfo=UTC),
    )

    assert exit_code == 0
    assert token_gate.checked
    assert "result" in collected
    receipt = emitted["receipt"]
    assert isinstance(receipt, dict)
    assert receipt["payload"] == {"status": "ready"}


class _TokenGate:
    def __init__(self) -> None:
        self.checked = False

    def token_request_is_due(self) -> bool:
        self.checked = True
        return True


class _RateGate:
    def snapshot(self) -> SimpleNamespace:
        return SimpleNamespace(retry_not_before_utc=None)


def _script_module() -> object:
    script_path = Path(__file__).parents[1] / "scripts" / "collect_kis_paper_daily_pair_forward.py"
    specification = importlib.util.spec_from_file_location(
        "collect_kis_paper_daily_pair_forward_for_test",
        script_path,
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module
