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


@pytest.mark.parametrize("broken_gate", ["token", "rate"])
def test_control_gate_failure_emits_recovery_without_constructing_a_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    broken_gate: str,
) -> None:
    script = _script_module()
    emitted: dict[str, object] = {}

    monkeypatch.setattr(
        script,
        "KisPaperMarketDataTokenStartGate",
        lambda **_kwargs: _BrokenTokenGate() if broken_gate == "token" else _TokenGate(),
    )
    monkeypatch.setattr(
        script,
        "KisPaperMarketDataRateGate",
        lambda **_kwargs: _BrokenRateGate() if broken_gate == "rate" else _RateGate(),
    )
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_environment_config",
        lambda: pytest.fail("control-gate failure must not read KIS configuration"),
    )
    monkeypatch.setattr(
        script,
        "KisPaperMarketDataClient",
        lambda **_kwargs: pytest.fail("control-gate failure must not construct a client"),
    )
    monkeypatch.setattr(
        script,
        "UrllibKisPaperDailyPairForwardTransport",
        lambda **_kwargs: pytest.fail("control-gate failure must not construct a transport"),
    )
    monkeypatch.setattr(
        script,
        "_write_source_safe_receipt",
        lambda **kwargs: emitted.update(kwargs)
        or (tmp_path / "receipt.json", "sha256:" + "b" * 64),
    )

    exit_code = script._run_credentialed_collection(  # noqa: SLF001
        cache_root=tmp_path / "cache",
        control_root=tmp_path / "control",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repository",
        frozen_boundary=datetime(2026, 7, 24, tzinfo=UTC).date(),
        observed_at=datetime(2026, 8, 3, 21, tzinfo=UTC),
    )

    assert exit_code == 20
    receipt = emitted["receipt"]
    assert isinstance(receipt, dict)
    assert receipt["payload"] == {
        "status": "unavailable",
        "reason": "collector_unavailable",
        "observed_at_bucket": "2026-08-03T21:00Z",
        "recovery": "resume",
        "route_isolation": {
            "daily_market_data_only": True,
            "account_endpoints_used": False,
            "position_endpoints_used": False,
            "open_order_endpoints_used": False,
            "quote_endpoints_used": False,
            "order_endpoints_used": False,
            "live_endpoints_used": False,
        },
    }


def test_token_deferral_keeps_its_existing_reason_outside_control_failure_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script = _script_module()
    emitted: dict[str, object] = {}

    monkeypatch.setattr(
        script,
        "KisPaperMarketDataTokenStartGate",
        lambda **_kwargs: _TokenGate(False),
    )
    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", lambda **_kwargs: _RateGate())
    monkeypatch.setattr(
        script,
        "_defer_pair_cache",
        lambda **_kwargs: SimpleNamespace(
            safe_payload=lambda: {"status": "deferred", "reason": "token_request_not_due"}
        ),
    )
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_environment_config",
        lambda: pytest.fail("deferral must not read KIS configuration"),
    )
    monkeypatch.setattr(
        script,
        "_write_source_safe_receipt",
        lambda **kwargs: emitted.update(kwargs)
        or (tmp_path / "receipt.json", "sha256:" + "c" * 64),
    )

    exit_code = script._run_credentialed_collection(  # noqa: SLF001
        cache_root=tmp_path / "cache",
        control_root=tmp_path / "control",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repository",
        frozen_boundary=datetime(2026, 7, 24, tzinfo=UTC).date(),
        observed_at=datetime(2026, 8, 3, 21, tzinfo=UTC),
    )

    assert exit_code == 20
    receipt = emitted["receipt"]
    assert isinstance(receipt, dict)
    assert receipt["payload"] == {"status": "deferred", "reason": "token_request_not_due"}


class _TokenGate:
    def __init__(self, due: bool = True) -> None:
        self.checked = False
        self._due = due

    def token_request_is_due(self) -> bool:
        self.checked = True
        return self._due


class _RateGate:
    def snapshot(self) -> SimpleNamespace:
        return SimpleNamespace(retry_not_before_utc=None)


class _BrokenTokenGate:
    def token_request_is_due(self) -> bool:
        raise ValueError("invalid control state")


class _BrokenRateGate:
    def snapshot(self) -> SimpleNamespace:
        raise OSError("control state unavailable")


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
