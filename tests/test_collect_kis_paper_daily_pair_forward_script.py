from __future__ import annotations

import importlib.util
import io
import json
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
        "collect_kis_paper_daily_pair_forward_observation",
        lambda *_args, **kwargs: SimpleNamespace(
            rows_by_target={},
            failure_reasons_by_target={},
            observed_at=kwargs["observed_at"],
        ),
    )
    monkeypatch.setattr(
        script,
        "commit_kis_paper_daily_pair_forward_observation",
        lambda **_kwargs: collected.setdefault(
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
    assert receipt["payload"] == {
        "status": "ready",
        "runtime_contract_sha256": _runtime_contract_sha256(script),
    }


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
        "failure_stage": "control_gate",
        "runtime_contract_sha256": _runtime_contract_sha256(script),
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
    assert receipt["payload"] == {
        "status": "deferred",
        "reason": "token_request_not_due",
        "runtime_contract_sha256": _runtime_contract_sha256(script),
    }


def test_deferred_commit_failure_emits_fixed_storage_kind_without_loading_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script = _script_module()
    emitted: dict[str, object] = {}
    private_detail = "private-defer-detail-canary"

    monkeypatch.setattr(
        script,
        "KisPaperMarketDataTokenStartGate",
        lambda **_kwargs: _TokenGate(False),
    )
    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", lambda **_kwargs: _RateGate())
    monkeypatch.setattr(
        script,
        "_defer_pair_cache",
        lambda **_kwargs: (_ for _ in ()).throw(OSError(private_detail)),
    )
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_environment_config",
        lambda: pytest.fail("deferred commit failure must not load configuration"),
    )
    _capture_receipt(monkeypatch, script, tmp_path, emitted, "d")

    exit_code = _run_credentialed_collection(script, tmp_path)

    assert exit_code == 20
    _assert_collector_stage(
        emitted,
        script,
        "commit",
        expected_commit_failure_kind="storage",
    )
    receipt = emitted["receipt"]
    assert isinstance(receipt, dict)
    assert private_detail not in json.dumps(receipt, sort_keys=True)


def test_environment_failure_emits_fixed_safe_stage_without_constructing_a_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script = _script_module()
    emitted: dict[str, object] = {}

    _install_ready_gates(monkeypatch, script)
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_environment_config",
        lambda: (_ for _ in ()).throw(script.KisPaperMarketDataError("invalid")),
    )
    monkeypatch.setattr(
        script,
        "KisPaperMarketDataClient",
        lambda **_kwargs: pytest.fail("environment failure must not construct a client"),
    )
    monkeypatch.setattr(
        script,
        "UrllibKisPaperDailyPairForwardTransport",
        lambda **_kwargs: pytest.fail("environment failure must not construct a transport"),
    )
    _capture_receipt(monkeypatch, script, tmp_path, emitted, "e")

    exit_code = _run_credentialed_collection(script, tmp_path)

    assert exit_code == 20
    _assert_collector_stage(emitted, script, "environment")


def test_collection_failure_emits_fixed_safe_stage_without_committing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script = _script_module()
    emitted: dict[str, object] = {}

    _install_ready_gates(monkeypatch, script)
    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", lambda: object())
    monkeypatch.setattr(
        script,
        "UrllibKisPaperDailyPairForwardTransport",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(script, "KisPaperMarketDataClient", lambda **_kwargs: object())
    monkeypatch.setattr(
        script,
        "collect_kis_paper_daily_pair_forward_observation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            script.KisPaperMarketDataError("invalid")
        ),
    )
    monkeypatch.setattr(
        script,
        "commit_kis_paper_daily_pair_forward_observation",
        lambda **_kwargs: pytest.fail("collection failure must not commit a cache observation"),
    )
    _capture_receipt(monkeypatch, script, tmp_path, emitted, "f")

    exit_code = _run_credentialed_collection(script, tmp_path)

    assert exit_code == 20
    _assert_collector_stage(emitted, script, "collection")


@pytest.mark.parametrize(
    ("error_factory", "expected_kind"),
    [
        (
            lambda script, message: script.KisPaperDailyPairForwardCacheError(message),
            "cache_contract",
        ),
        (lambda _script, message: OSError(message), "storage"),
        (lambda _script, message: ValueError(message), "validation"),
    ],
)
def test_commit_failure_emits_fixed_safe_stage_after_collection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    error_factory: object,
    expected_kind: str,
) -> None:
    script = _script_module()
    emitted: dict[str, object] = {}
    private_detail = "private-detail-canary"

    _install_ready_gates(monkeypatch, script)
    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", lambda: object())
    monkeypatch.setattr(
        script,
        "UrllibKisPaperDailyPairForwardTransport",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(script, "KisPaperMarketDataClient", lambda **_kwargs: object())
    monkeypatch.setattr(
        script,
        "collect_kis_paper_daily_pair_forward_observation",
        lambda *_args, **kwargs: SimpleNamespace(
            rows_by_target={},
            failure_reasons_by_target={},
            observed_at=kwargs["observed_at"],
        ),
    )
    monkeypatch.setattr(
        script,
        "commit_kis_paper_daily_pair_forward_observation",
        lambda **_kwargs: (_ for _ in ()).throw(
            error_factory(script, private_detail)  # type: ignore[operator]
        ),
    )
    _capture_receipt(monkeypatch, script, tmp_path, emitted, "g")

    exit_code = _run_credentialed_collection(script, tmp_path)

    assert exit_code == 20
    _assert_collector_stage(
        emitted,
        script,
        "commit",
        expected_commit_failure_kind=expected_kind,
    )
    receipt = emitted["receipt"]
    assert isinstance(receipt, dict)
    assert set(receipt) == {"artifact_policy", "kind", "observed_at_bucket", "payload"}
    assert private_detail not in json.dumps(receipt, sort_keys=True)


def test_commit_failure_kind_uses_fixed_exception_order_and_omits_unmatched() -> None:
    script = _script_module()

    assert script._commit_failure_kind(io.UnsupportedOperation("canary")) == "storage"  # type: ignore[attr-defined]  # noqa: SLF001
    assert script._commit_failure_kind(RuntimeError("canary")) is None  # type: ignore[attr-defined]  # noqa: SLF001


def test_commit_failure_kind_is_limited_to_known_commit_payloads() -> None:
    script = _script_module()
    observed_at = datetime(2026, 8, 3, 21, tzinfo=UTC)

    payload = script._collector_unavailable_payload(  # type: ignore[attr-defined]  # noqa: SLF001
        observed_at,
        "commit",
        commit_failure_kind="storage",
    )

    assert payload["commit_failure_kind"] == "storage"
    payload = script._collector_unavailable_payload(  # type: ignore[attr-defined]  # noqa: SLF001
        observed_at,
        "commit",
        commit_failure_kind="cache_contract",
        commit_failure_phase="cache_prepare",
    )
    assert payload["commit_failure_phase"] == "cache_prepare"
    with pytest.raises(ValueError):
        script._collector_unavailable_payload(  # type: ignore[attr-defined]  # noqa: SLF001
            observed_at,
            "collection",
            commit_failure_kind="storage",
        )
    with pytest.raises(ValueError):
        script._collector_unavailable_payload(  # type: ignore[attr-defined]  # noqa: SLF001
            observed_at,
            "commit",
            commit_failure_kind="unexpected",
        )
    with pytest.raises(ValueError):
        script._collector_unavailable_payload(  # type: ignore[attr-defined]  # noqa: SLF001
            observed_at,
            "commit",
            commit_failure_kind="storage",
            commit_failure_phase="cache_prepare",
        )
    with pytest.raises(ValueError):
        script._collector_unavailable_payload(  # type: ignore[attr-defined]  # noqa: SLF001
            observed_at,
            "commit",
            commit_failure_kind="cache_contract",
            commit_failure_phase="not_allowlisted",
        )


def test_commit_failure_kind_does_not_bleed_into_a_later_success_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script = _script_module()
    receipts: list[dict[str, object]] = []

    monkeypatch.setattr(
        script,
        "_write_source_safe_receipt",
        lambda **kwargs: receipts.append(kwargs["receipt"])
        or (tmp_path / f"receipt-{len(receipts)}.json", "sha256:" + "h" * 64),
    )
    observed_at = datetime(2026, 8, 3, 21, tzinfo=UTC)

    script._emit_collector_stage_unavailable(  # type: ignore[attr-defined]  # noqa: SLF001
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repository",
        observed_at=observed_at,
        failure_stage="commit",
        commit_failure_kind="storage",
    )
    script._emit_source_safe_receipt(  # type: ignore[attr-defined]  # noqa: SLF001
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repository",
        observed_at=observed_at,
        payload={"status": "ready"},
        exit_code=0,
    )

    assert receipts[0]["payload"]["commit_failure_kind"] == "storage"
    assert "commit_failure_phase" not in receipts[0]["payload"]
    assert "commit_failure_kind" not in receipts[1]["payload"]
    assert "commit_failure_phase" not in receipts[1]["payload"]


def test_commit_failure_phase_emits_only_fixed_safe_cache_contract_detail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script = _script_module()
    emitted: dict[str, object] = {}
    private_detail = "private-phase-detail-canary"
    error = script.KisPaperDailyPairForwardCacheError(private_detail)
    error._commit_failure_phase = "cache_prepare"  # type: ignore[attr-defined]  # noqa: SLF001

    _install_ready_gates(monkeypatch, script)
    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", lambda: object())
    monkeypatch.setattr(
        script,
        "UrllibKisPaperDailyPairForwardTransport",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(script, "KisPaperMarketDataClient", lambda **_kwargs: object())
    monkeypatch.setattr(
        script,
        "collect_kis_paper_daily_pair_forward_observation",
        lambda *_args, **kwargs: SimpleNamespace(
            rows_by_target={},
            failure_reasons_by_target={},
            observed_at=kwargs["observed_at"],
        ),
    )
    monkeypatch.setattr(
        script,
        "commit_kis_paper_daily_pair_forward_observation",
        lambda **_kwargs: (_ for _ in ()).throw(error),
    )
    _capture_receipt(monkeypatch, script, tmp_path, emitted, "p")

    exit_code = _run_credentialed_collection(script, tmp_path)

    assert exit_code == 20
    _assert_collector_stage(
        emitted,
        script,
        "commit",
        expected_commit_failure_kind="cache_contract",
        expected_commit_failure_phase="cache_prepare",
    )
    receipt = emitted["receipt"]
    assert isinstance(receipt, dict)
    assert private_detail not in json.dumps(receipt, sort_keys=True)


def test_networkless_readiness_checks_only_control_and_aggregate_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script = _script_module()
    emitted: dict[str, object] = {}

    _install_ready_gates(monkeypatch, script)
    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", lambda: object())
    monkeypatch.setattr(
        script,
        "KisPaperMarketDataClient",
        lambda **_kwargs: pytest.fail("readiness must not construct a client"),
    )
    monkeypatch.setattr(
        script,
        "UrllibKisPaperDailyPairForwardTransport",
        lambda **_kwargs: pytest.fail("readiness must not construct a transport"),
    )
    monkeypatch.setattr(
        script,
        "collect_kis_paper_daily_pair_forward_observation",
        lambda *_args, **_kwargs: pytest.fail("readiness must not collect market data"),
    )
    monkeypatch.setattr(
        script,
        "commit_kis_paper_daily_pair_forward_observation",
        lambda **_kwargs: pytest.fail("readiness must not write a cache observation"),
    )
    _capture_receipt(monkeypatch, script, tmp_path, emitted, "h")

    exit_code = script._run_readiness(  # noqa: SLF001
        control_root=tmp_path / "control",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repository",
        observed_at=datetime(2026, 8, 3, 21, tzinfo=UTC),
    )

    assert exit_code == 0
    receipt = emitted["receipt"]
    assert isinstance(receipt, dict)
    assert receipt["payload"] == {
        "status": "ready",
        "readiness": "aggregate_ready",
        "token_request_due": True,
        "rate_gate_deferred": False,
        "runtime_contract_sha256": _runtime_contract_sha256(script),
        "route_isolation": {
            "daily_market_data_only": True,
            "account_endpoints_used": False,
            "position_endpoints_used": False,
            "open_order_endpoints_used": False,
            "quote_endpoints_used": False,
            "order_endpoints_used": False,
            "live_endpoints_used": False,
            "network_requests_used": False,
            "cache_writes": False,
        },
    }


def test_readiness_environment_failure_stays_networkless_and_source_safe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script = _script_module()
    emitted: dict[str, object] = {}

    _install_ready_gates(monkeypatch, script)
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_environment_config",
        lambda: (_ for _ in ()).throw(script.KisPaperMarketDataError("invalid")),
    )
    monkeypatch.setattr(
        script,
        "KisPaperMarketDataClient",
        lambda **_kwargs: pytest.fail("readiness must not construct a client"),
    )
    _capture_receipt(monkeypatch, script, tmp_path, emitted, "i")

    exit_code = script._run_readiness(  # noqa: SLF001
        control_root=tmp_path / "control",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repository",
        observed_at=datetime(2026, 8, 3, 21, tzinfo=UTC),
    )

    assert exit_code == 20
    receipt = emitted["receipt"]
    assert isinstance(receipt, dict)
    assert receipt["payload"]["reason"] == "readiness_unavailable"
    assert receipt["payload"]["failure_stage"] == "environment"
    assert receipt["payload"]["runtime_contract_sha256"] == _runtime_contract_sha256(script)


def test_runtime_contract_fingerprint_is_static_and_environment_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = _script_module()
    baseline = _runtime_contract_sha256(script)

    monkeypatch.setenv("KIS_PAPER_APP_KEY", "private-key")
    monkeypatch.setenv("KIS_PAPER_APP_SECRET", "private-secret")

    assert _runtime_contract_sha256(script) == baseline
    monkeypatch.setattr(
        script,
        "_RUNTIME_CONTRACT",
        {**script._RUNTIME_CONTRACT, "collector_failure_stages": ("control_gate",)},
    )
    assert _runtime_contract_sha256(script) != baseline
    assert script._RUNTIME_CONTRACT["commit_failure_kinds"] == (  # type: ignore[attr-defined]  # noqa: SLF001
        "cache_contract",
        "storage",
        "validation",
    )
    assert script._RUNTIME_CONTRACT["commit_failure_phases"] == (  # type: ignore[attr-defined]  # noqa: SLF001
        "cache_prepare",
        "snapshot_persist",
        "index_persist",
        "cache_reverify",
    )


def test_source_safe_receipt_writer_uses_an_external_create_only_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script = _script_module()
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "external" / "artifacts"

    class _FixedReceiptClock:
        @staticmethod
        def now(_timezone: object) -> datetime:
            return datetime(2026, 8, 3, 21, tzinfo=UTC)

    monkeypatch.setattr(script, "datetime", _FixedReceiptClock)
    monkeypatch.setattr(script.uuid, "uuid4", lambda: SimpleNamespace(hex="j" * 32))
    receipt = {
        "kind": "kis_paper_daily_pair_forward_receipt",
        "payload": {"status": "ready"},
    }

    path, digest = script._write_source_safe_receipt(  # noqa: SLF001
        artifact_root=artifact_root,
        repository_root=repository_root,
        receipt=receipt,
    )

    assert path.is_relative_to(artifact_root)
    assert not path.is_relative_to(repository_root)
    assert digest.startswith("sha256:")
    with pytest.raises(FileExistsError):
        script._write_source_safe_receipt(  # noqa: SLF001
            artifact_root=artifact_root,
            repository_root=repository_root,
            receipt=receipt,
        )


def test_cache_current_preflight_never_reads_kis_configuration_or_constructs_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script = _script_module()
    emitted: dict[str, object] = {}
    current_session = datetime(2026, 8, 18, tzinfo=UTC).date()
    cache = SimpleNamespace(
        frozen_boundary=datetime(2026, 7, 24, tzinfo=UTC).date(),
        targets_by_key={
            target_key: SimpleNamespace(latest_session=current_session)
            for target_key in script._TARGET_KEYS
        },
        common_sessions=(current_session,),
        safe_payload=lambda: {"kind": "kis_paper_daily_pair_forward_cache"},
    )

    monkeypatch.setattr(
        script,
        "latest_completed_us_equity_d1_session",
        lambda _value: current_session,
    )
    monkeypatch.setattr(
        script,
        "load_verified_kis_paper_daily_pair_forward_cache",
        lambda **_kwargs: cache,
    )
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_environment_config",
        lambda: pytest.fail("cache-current preflight must not read KIS configuration"),
    )
    monkeypatch.setattr(
        script,
        "KisPaperMarketDataClient",
        lambda **_kwargs: pytest.fail("cache-current preflight must not construct a client"),
    )
    monkeypatch.setattr(
        script,
        "UrllibKisPaperDailyPairForwardTransport",
        lambda **_kwargs: pytest.fail("cache-current preflight must not construct a transport"),
    )
    monkeypatch.setattr(
        script,
        "_write_source_safe_receipt",
        lambda **kwargs: emitted.update(kwargs)
        or (tmp_path / "receipt.json", "sha256:" + "d" * 64),
    )

    exit_code = script._run_preflight(  # noqa: SLF001
        cache_root=tmp_path / "cache",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repository",
        frozen_boundary=cache.frozen_boundary,
        observed_at=datetime(2026, 8, 19, 14, tzinfo=UTC),
        schedule_guard_failed=None,
    )

    assert exit_code == 0
    receipt = emitted["receipt"]
    assert isinstance(receipt, dict)
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    assert payload["status"] == "cache_current"
    assert payload["eligible_through"] == "2026-08-18"
    assert payload["route_isolation"] == {
        "daily_market_data_only": True,
        "account_endpoints_used": False,
        "position_endpoints_used": False,
        "open_order_endpoints_used": False,
        "quote_endpoints_used": False,
        "order_endpoints_used": False,
        "live_endpoints_used": False,
    }


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


def _install_ready_gates(monkeypatch: pytest.MonkeyPatch, script: object) -> None:
    monkeypatch.setattr(script, "KisPaperMarketDataTokenStartGate", lambda **_kwargs: _TokenGate())
    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", lambda **_kwargs: _RateGate())


def _capture_receipt(
    monkeypatch: pytest.MonkeyPatch,
    script: object,
    tmp_path: Path,
    emitted: dict[str, object],
    digest_character: str,
) -> None:
    monkeypatch.setattr(
        script,
        "_write_source_safe_receipt",
        lambda **kwargs: emitted.update(kwargs)
        or (tmp_path / "receipt.json", "sha256:" + digest_character * 64),
    )


def _run_credentialed_collection(script: object, tmp_path: Path) -> int:
    return script._run_credentialed_collection(  # type: ignore[attr-defined]  # noqa: SLF001
        cache_root=tmp_path / "cache",
        control_root=tmp_path / "control",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repository",
        frozen_boundary=datetime(2026, 7, 24, tzinfo=UTC).date(),
        observed_at=datetime(2026, 8, 3, 21, tzinfo=UTC),
    )


def _assert_collector_stage(
    emitted: dict[str, object],
    script: object,
    expected_stage: str,
    *,
    expected_commit_failure_kind: str | None = None,
    expected_commit_failure_phase: str | None = None,
) -> None:
    receipt = emitted["receipt"]
    assert isinstance(receipt, dict)
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    assert payload["status"] == "unavailable"
    assert payload["reason"] == "collector_unavailable"
    assert payload["failure_stage"] == expected_stage
    assert payload["runtime_contract_sha256"] == _runtime_contract_sha256(script)
    if expected_commit_failure_kind is None:
        assert "commit_failure_kind" not in payload
    else:
        assert payload["commit_failure_kind"] == expected_commit_failure_kind
    if expected_commit_failure_phase is None:
        assert "commit_failure_phase" not in payload
    else:
        assert payload["commit_failure_phase"] == expected_commit_failure_phase


def _runtime_contract_sha256(script: object) -> str:
    return script._runtime_contract_sha256()  # type: ignore[attr-defined]  # noqa: SLF001


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
