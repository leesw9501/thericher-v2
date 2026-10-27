from __future__ import annotations

import importlib.util
import io
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.execution import kis_market_data_rate_gate as gates


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
        "current_run_failure_reasons_by_target": {},
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


@pytest.mark.parametrize(
    ("token_due", "rate_deferred", "reason"),
    [
        (False, False, "token_request_not_due"),
        (True, True, "rate_limited"),
        (False, True, "token_request_not_due"),
    ],
)
def test_token_deferral_keeps_its_existing_reason_outside_control_failure_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    token_due: bool,
    rate_deferred: bool,
    reason: str,
) -> None:
    script = _script_module()
    emitted: dict[str, object] = {}

    monkeypatch.setattr(
        script,
        "KisPaperMarketDataTokenStartGate",
        lambda **_kwargs: _TokenGate(token_due),
    )
    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", lambda **_kwargs: _RateGate())
    monkeypatch.setattr(script, "_rate_gate_is_deferred", lambda *_args: rate_deferred)
    monkeypatch.setattr(
        script,
        "_defer_pair_cache",
        lambda **_kwargs: SimpleNamespace(
            safe_payload=lambda: {"status": "deferred", "reason": reason}
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
        "reason": reason,
        "current_run_failure_reasons_by_target": {"QQQ/NAS": reason, "SPY/AMS": reason},
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
        commit_failure_prepare_subphase="cache_access",
    )
    assert payload["commit_failure_phase"] == "cache_prepare"
    assert payload["commit_failure_prepare_subphase"] == "cache_access"
    payload = script._collector_unavailable_payload(  # type: ignore[attr-defined]  # noqa: SLF001
        observed_at,
        "commit",
        commit_failure_kind="cache_contract",
        commit_failure_phase="cache_prepare",
    )
    assert "commit_failure_prepare_subphase" not in payload
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
    with pytest.raises(ValueError):
        script._collector_unavailable_payload(  # type: ignore[attr-defined]  # noqa: SLF001
            observed_at,
            "commit",
            commit_failure_kind="cache_contract",
            commit_failure_phase="snapshot_persist",
            commit_failure_prepare_subphase="cache_access",
        )
    with pytest.raises(ValueError):
        script._collector_unavailable_payload(  # type: ignore[attr-defined]  # noqa: SLF001
            observed_at,
            "commit",
            commit_failure_kind="cache_contract",
            commit_failure_phase="cache_prepare",
            commit_failure_prepare_subphase="not_allowlisted",
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
    error._commit_failure_prepare_subphase = "cache_access"  # type: ignore[attr-defined]  # noqa: SLF001

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
        expected_commit_failure_prepare_subphase="cache_access",
    )
    receipt = emitted["receipt"]
    assert isinstance(receipt, dict)
    assert private_detail not in json.dumps(receipt, sort_keys=True)


def test_commit_failure_prepare_subphase_is_omitted_without_matching_triple() -> None:
    script = _script_module()
    error = script.KisPaperDailyPairForwardCacheError("private-phase-detail-canary")
    error._commit_failure_phase = "snapshot_persist"  # type: ignore[attr-defined]  # noqa: SLF001
    error._commit_failure_prepare_subphase = "cache_access"  # type: ignore[attr-defined]  # noqa: SLF001

    assert (
        script._commit_failure_prepare_subphase(  # type: ignore[attr-defined]  # noqa: SLF001
            error,
            "cache_contract",
            "snapshot_persist",
        )
        is None
    )
    assert (
        script._commit_failure_prepare_subphase(  # type: ignore[attr-defined]  # noqa: SLF001
            error,
            "storage",
            "cache_prepare",
        )
        is None
    )


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
    assert script._RUNTIME_CONTRACT["commit_failure_prepare_subphases"] == (  # type: ignore[attr-defined]  # noqa: SLF001
        "cache_access",
        "cache_state_load",
        "incoming_merge",
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


def test_v2_preflight_selects_the_frozen_identity_without_kis_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = _script_module()
    received: dict[str, object] = {}

    monkeypatch.setattr(
        script,
        "_run_preflight",
        lambda **kwargs: received.update(kwargs) or 17,
    )
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_environment_config",
        lambda: pytest.fail("v2 preflight must not read KIS configuration"),
    )

    exit_code = script.main(  # type: ignore[attr-defined]  # noqa: SLF001
        ["--preflight", "--cache-lineage", "v2"],
        clock=lambda: datetime(2026, 8, 20, 12, tzinfo=UTC),
    )

    assert exit_code == 17
    assert received["cache_identity"] == script.KIS_PAPER_DAILY_PAIR_FORWARD_V2_IDENTITY


def test_v2_missing_cache_preflight_receipt_stays_source_safe_and_network_free(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script = _script_module()
    emitted: dict[str, object] = {}
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    cache_root = tmp_path / "external" / "cache"

    monkeypatch.setattr(
        script,
        "latest_completed_us_equity_d1_session",
        lambda _value: datetime(2026, 8, 19, tzinfo=UTC).date(),
    )
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_environment_config",
        lambda: pytest.fail("v2 preflight must not read KIS configuration"),
    )
    monkeypatch.setattr(
        script,
        "KisPaperMarketDataClient",
        lambda **_kwargs: pytest.fail("v2 preflight must not construct a client"),
    )
    monkeypatch.setattr(
        script,
        "_write_source_safe_receipt",
        lambda **kwargs: emitted.update(kwargs)
        or (tmp_path / "receipt.json", "sha256:" + "v" * 64),
    )

    exit_code = script._run_preflight(  # noqa: SLF001
        cache_root=cache_root,
        artifact_root=tmp_path / "artifacts",
        repository_root=repository_root,
        frozen_boundary=datetime(2026, 7, 24, tzinfo=UTC).date(),
        observed_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
        schedule_guard_failed=None,
        cache_identity=script.KIS_PAPER_DAILY_PAIR_FORWARD_V2_IDENTITY,
    )

    assert exit_code == 10
    receipt = emitted["receipt"]
    assert isinstance(receipt, dict)
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    assert payload["status"] == "collection_required"
    assert payload["cache_identity"] == {
        "kind": "kis.paper.private.daily.qqq-spy.forward-v2",
        "version": "kis-paper-daily-qqq-spy-forward-v2",
    }
    assert payload["route_isolation"] == {
        "daily_market_data_only": True,
        "account_endpoints_used": False,
        "position_endpoints_used": False,
        "open_order_endpoints_used": False,
        "quote_endpoints_used": False,
        "order_endpoints_used": False,
        "live_endpoints_used": False,
    }


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


@pytest.mark.parametrize("current_failures", [{"QQQ/NAS": "transport_failure"}, {}])
def test_current_run_cause_does_not_replace_persisted_quarantine(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    current_failures: dict[str, str],
) -> None:
    script = _script_module()
    emitted: dict[str, object] = {}
    committed: dict[str, object] = {}
    rows = {target: () for target in ("QQQ/NAS", "SPY/AMS") if target not in current_failures}
    observation = SimpleNamespace(
        rows_by_target=rows,
        failure_reasons_by_target=current_failures,
        observed_at=datetime(2026, 8, 3, 21, tzinfo=UTC),
    )
    old_payload = {"status": "partial", "reason": "daily_retained_revision_conflict"}
    _install_ready_gates(monkeypatch, script)
    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", lambda: object())
    monkeypatch.setattr(script, "UrllibKisPaperDailyPairForwardTransport", lambda **_: object())
    monkeypatch.setattr(script, "KisPaperMarketDataClient", lambda **_: object())
    monkeypatch.setattr(
        script, "collect_kis_paper_daily_pair_forward_observation", lambda *_, **__: observation
    )

    def commit(**kwargs: object) -> SimpleNamespace:
        committed.update(kwargs)
        return SimpleNamespace(status="partial", safe_payload=lambda: old_payload)

    monkeypatch.setattr(script, "commit_kis_paper_daily_pair_forward_observation", commit)
    _capture_receipt(monkeypatch, script, tmp_path, emitted, "c")

    assert _run_credentialed_collection(script, tmp_path) == 20
    assert committed["failure_reasons_by_target"] is current_failures
    assert committed["rows_by_target"] is rows
    receipt = emitted["receipt"]
    assert isinstance(receipt, dict)
    assert receipt["payload"] == {
        **old_payload,
        "current_run_failure_reasons_by_target": current_failures,
        "runtime_contract_sha256": _runtime_contract_sha256(script),
    }
    assert "current_run_failure_reasons_by_target" not in old_payload


def test_current_run_failure_projection_is_target_scoped_and_never_coerces_objects() -> None:
    script = _script_module()

    class PrivateObject:
        def __str__(self) -> str:
            pytest.fail("must not stringify private object")

        def __repr__(self) -> str:
            pytest.fail("must not represent private object")

    failures = {
        "QQQ/NAS": PrivateObject(),
        "SPY/AMS": "rate_limited private-cause-canary",
        "unknown/private-target-canary": "private-cause-canary",
    }
    projected = script._current_run_failure_reasons(failures)  # noqa: SLF001
    assert projected == {
        "QQQ/NAS": "unexpected_private_daily_collector_error",
        "SPY/AMS": "unexpected_private_daily_collector_error",
    }
    assert "canary" not in json.dumps(projected)
    assert failures["SPY/AMS"] == "rate_limited private-cause-canary"
    assert script._current_run_failure_reasons({}) == {}  # noqa: SLF001


def test_current_failure_value_is_read_once_before_sanitizing() -> None:
    script = _script_module()

    class OneRead(dict[str, object]):
        def __getitem__(self, key: str) -> object:
            value = super().__getitem__(key)
            self.clear()
            return value

    assert script._current_run_failure_reasons(OneRead({"QQQ/NAS": "rate_limited"})) == {  # noqa: SLF001
        "QQQ/NAS": "rate_limited"
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
    expected_commit_failure_prepare_subphase: str | None = None,
) -> None:
    receipt = emitted["receipt"]
    assert isinstance(receipt, dict)
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    assert payload["status"] == "unavailable"
    assert payload["reason"] == "collector_unavailable"
    assert payload["failure_stage"] == expected_stage
    assert "current_run_failure_reasons_by_target" not in payload
    assert payload["runtime_contract_sha256"] == _runtime_contract_sha256(script)
    if expected_commit_failure_kind is None:
        assert "commit_failure_kind" not in payload
    else:
        assert payload["commit_failure_kind"] == expected_commit_failure_kind
    if expected_commit_failure_phase is None:
        assert "commit_failure_phase" not in payload
    else:
        assert payload["commit_failure_phase"] == expected_commit_failure_phase
    if expected_commit_failure_prepare_subphase is None:
        assert "commit_failure_prepare_subphase" not in payload
    else:
        assert (
            payload["commit_failure_prepare_subphase"]
            == expected_commit_failure_prepare_subphase
        )


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


def test_native_shared_mark_atomic_legacy_and_named_cli(monkeypatch, tmp_path):
    script = _script_module()
    control = tmp_path / "SYN-control"
    at = [datetime(2026, 10, 27, 12, tzinfo=UTC)]
    observer = gates.KisPaperMarketDataTokenStartGate(
        control_root=control, minimum_request_interval_seconds=60, clock=lambda: at[0]
    )
    legacy = gates.KisPaperMarketDataTokenStartGate(control_root=control, clock=lambda: at[0])
    assert observer.claim_token_request_start()
    at[0] += timedelta(seconds=240)
    assert observer.claim_token_request_start()
    at[0] += timedelta(seconds=61)
    assert not legacy.token_request_is_due()
    before = (control / "token-request.json").read_bytes()
    observed = []
    lock_checks = []
    real_lock = gates._exclusive_lock

    @contextmanager
    def real_atomic_then_legacy(path):
        assert (control / "token-request.lock.d").is_dir()
        lock_checks.append(True)
        with real_lock(path):
            yield

    def actual_gate(**kwargs):
        assert kwargs["control_root"] == Path("/app/collection_control")
        gate = gates.KisPaperMarketDataTokenStartGate(
            control_root=control,
            minimum_request_interval_seconds=kwargs["minimum_request_interval_seconds"],
            clock=lambda: at[0],
        )
        observed.append(gate)
        return gate

    class EnvironmentBoundary(RuntimeError):
        pass

    def no_credentials():
        raise EnvironmentBoundary("SYN boundary before any credential read or client")

    monkeypatch.setattr(gates, "_exclusive_lock", real_atomic_then_legacy)
    monkeypatch.setattr(script, "KisPaperMarketDataTokenStartGate", actual_gate)
    monkeypatch.setattr(
        script,
        "KisPaperMarketDataRateGate",
        lambda **_: SimpleNamespace(snapshot=lambda: SimpleNamespace(retry_not_before_utc=None)),
    )
    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", no_credentials)
    monkeypatch.setattr(
        script, "KisPaperMarketDataClient", lambda **_: pytest.fail("client forbidden")
    )
    args = ["--execute", "--cache-lineage", "v2", "--token-minimum-interval-seconds", "60"]
    with pytest.raises(EnvironmentBoundary):
        script.main(args, clock=lambda: at[0])
    gate = observed[-1]
    assert gate.token_request_is_due()
    assert gate.snapshot().next_token_request_not_before_utc == at[0] - timedelta(seconds=1)
    assert (control / "token-request.json").read_bytes() == before
    assert gate.claim_token_request_start()
    assert gates.KIS_PAPER_MARKET_DATA_TOKEN_MIN_REQUEST_INTERVAL_SECONDS == 300
    assert lock_checks
    held = control / "token-request.lock.d"
    held.mkdir()
    identity = held.stat()
    mark = (control / "token-request.json").read_bytes()
    try:
        assert not gate.claim_token_request_start()
        assert not gate.token_request_is_due()
        assert (control / "token-request.json").read_bytes() == mark
        assert not list(held.iterdir())
    finally:
        current = held.stat()
        assert (identity.st_dev, identity.st_ino) == (current.st_dev, current.st_ino)
        held.rmdir()


@pytest.mark.parametrize("seconds", ["0", "59", "61", "301", "nan", "inf"])
def test_cli_rejects_other_floor_before_any_gate(monkeypatch, seconds):
    script = _script_module()
    monkeypatch.setattr(
        script, "KisPaperMarketDataTokenStartGate", lambda **_: pytest.fail("gate forbidden")
    )
    with pytest.raises(SystemExit) as exc:
        script.main(
            ["--execute", "--cache-lineage", "v2", "--token-minimum-interval-seconds", seconds]
        )
    assert exc.value.code == 2


@pytest.mark.parametrize("mode,lineage", [("--execute", "v1"), ("--preflight", "v2")])
def test_floor60_scoped_to_named_v2_token_callers(monkeypatch, mode, lineage):
    script = _script_module()
    monkeypatch.setattr(
        script, "KisPaperMarketDataTokenStartGate", lambda **_: pytest.fail("gate forbidden")
    )
    assert (
        script.main([mode, "--cache-lineage", lineage, "--token-minimum-interval-seconds", "60"])
        == 2
    )


def test_default_300_unchanged_no_new_keyword(monkeypatch):
    script = _script_module()
    received = []
    monkeypatch.setattr(
        script, "_run_credentialed_collection", lambda **kwargs: received.append(kwargs) or 20
    )
    assert script.main(["--execute", "--cache-lineage", "v2"]) == 20
    assert "token_minimum_interval_seconds" not in received[0]


@pytest.mark.parametrize("floor", [0, 59, 61, 301, True, float("nan"), float("inf")])
def test_direct_caller_rejects_invalid_policy_before_gate(monkeypatch, floor):
    script = _script_module()
    monkeypatch.setattr(
        script, "KisPaperMarketDataTokenStartGate", lambda **_: pytest.fail("gate forbidden")
    )
    with pytest.raises(ValueError, match="token floor"):
        script._run_readiness(
            control_root=Path("/app/collection_control"),
            artifact_root=Path("/app/model_artifacts"),
            repository_root=Path("/app"),
            observed_at=datetime.now(UTC),
            token_minimum_interval_seconds=floor,
        )
