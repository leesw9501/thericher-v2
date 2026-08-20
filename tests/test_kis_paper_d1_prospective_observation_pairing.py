from __future__ import annotations

import importlib.util
import json
import socket
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from thericher_v2.data import kis_paper_d1_prospective_observation_pairing as pairing
from thericher_v2.data.kis_paper_daily_pair_forward_cache import (
    KIS_PAPER_DAILY_PAIR_FORWARD_RETAINED_REVISION_CONFLICT_REASON,
    KIS_PAPER_DAILY_PAIR_FORWARD_V2_IDENTITY,
    KisPaperDailyPairForwardRow,
)
from thericher_v2.execution.kis_paper_daily_pair_forward import (
    KisPaperDailyPairForwardObservation,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIRST_OBSERVED_AT = datetime(2026, 8, 20, 23, 15, tzinfo=UTC)
LATER_OBSERVED_AT = datetime(2026, 8, 21, 14, 20, tzinfo=UTC)
SESSION = date(2026, 8, 20)


def test_first_and_later_pair_replays_without_raw_data_or_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    first_fetcher, first_calls = _recording_fetcher(_observation(FIRST_OBSERVED_AT))
    first = _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=FIRST_OBSERVED_AT,
        observation_fetcher=first_fetcher,
    )

    assert first.status == "first_recorded"
    assert first.stage == "first"
    assert first.evidence_path is not None
    assert len(first_calls) == 1
    first_text = first.evidence_path.read_text(encoding="utf-8")
    assert "812.34" not in first_text
    assert "test-token" not in first_text
    state = _state(artifact_root)
    assert state["expected_stage"] == "later"
    assert state["next_due_at_utc"] == "2026-08-21T14:20:00Z"

    later_fetcher, later_calls = _recording_fetcher(_observation(LATER_OBSERVED_AT))
    later = _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=LATER_OBSERVED_AT,
        observation_fetcher=later_fetcher,
    )

    assert later.status == "measurement_only_match"
    assert later.reason is None
    assert later.stage == "later"
    assert later.evidence_path is not None
    assert len(later_calls) == 1
    assert later.first_row_hashes == later.later_row_hashes
    assert _state(artifact_root)["expected_stage"] == "first"

    def forbid_network(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("receipt validation must stay offline")

    monkeypatch.setattr(socket, "create_connection", forbid_network)
    replay = pairing.validate_kis_paper_d1_prospective_observation_pairing_receipt(
        later.evidence_path,
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    assert replay["status"] == "measurement_only_match"
    assert replay["measurement_only"] is True
    assert replay["route_isolation"]["daily_market_data_only"] is True
    assert replay["route_isolation"]["account_endpoints_used"] is False
    assert replay["route_isolation"]["order_endpoints_used"] is False
    assert replay["route_isolation"]["live_endpoints_used"] is False


def test_hash_mismatch_disqualifies_only_the_exact_session(tmp_path: Path) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    first_fetcher, _ = _recording_fetcher(_observation(FIRST_OBSERVED_AT))
    _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=FIRST_OBSERVED_AT,
        observation_fetcher=first_fetcher,
    )
    later_fetcher, calls = _recording_fetcher(
        _observation(LATER_OBSERVED_AT, qqq_close="813.34")
    )

    result = _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=LATER_OBSERVED_AT,
        observation_fetcher=later_fetcher,
    )

    assert result.status == "disqualified"
    assert result.reason == "identity_mismatch"
    assert result.first_row_hashes != result.later_row_hashes
    assert len(calls) == 1
    assert _state(artifact_root)["expected_stage"] == "first"


def test_current_reader_revalidates_the_exact_later_binding_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    first_fetcher, _ = _recording_fetcher(_observation(FIRST_OBSERVED_AT))
    first = _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=FIRST_OBSERVED_AT,
        observation_fetcher=first_fetcher,
    )
    later_fetcher, _ = _recording_fetcher(_observation(LATER_OBSERVED_AT))
    later = _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=LATER_OBSERVED_AT,
        observation_fetcher=later_fetcher,
    )
    assert first.evidence_path is not None
    assert first.receipt_sha256 is not None
    assert later.evidence_path is not None

    def forbid_network(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("current outcome reader must stay offline")

    monkeypatch.setattr(socket, "create_connection", forbid_network)
    current = pairing.read_current_kis_paper_d1_prospective_observation_pairing_outcome(
        artifact_root=artifact_root,
        repository_root=repository_root,
    )

    assert current["receipt_id"] == later.evidence_path.stem
    assert current["status"] == "measurement_only_match"
    assert current["first_receipt_binding"] == {
        "receipt_id": first.evidence_path.stem,
        "receipt_sha256": first.receipt_sha256,
    }
    pointer_text = _current_pointer(artifact_root).read_text(encoding="utf-8")
    assert "812.34" not in pointer_text
    assert "test-token" not in pointer_text


def test_current_reader_rejects_a_tampered_current_pointer(tmp_path: Path) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    first_fetcher, _ = _recording_fetcher(_observation(FIRST_OBSERVED_AT))
    _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=FIRST_OBSERVED_AT,
        observation_fetcher=first_fetcher,
    )
    later_fetcher, _ = _recording_fetcher(_observation(LATER_OBSERVED_AT))
    _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=LATER_OBSERVED_AT,
        observation_fetcher=later_fetcher,
    )
    pointer_path = _current_pointer(artifact_root)
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["receipt_sha256"] = "sha256:" + "0" * 64
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    with pytest.raises(pairing.KisPaperD1ProspectiveObservationPairingError):
        pairing.read_current_kis_paper_d1_prospective_observation_pairing_outcome(
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def test_current_reader_rejects_a_pointer_with_a_mismatched_observed_timestamp(
    tmp_path: Path,
) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    first_fetcher, _ = _recording_fetcher(_observation(FIRST_OBSERVED_AT))
    _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=FIRST_OBSERVED_AT,
        observation_fetcher=first_fetcher,
    )
    later_fetcher, _ = _recording_fetcher(_observation(LATER_OBSERVED_AT))
    _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=LATER_OBSERVED_AT,
        observation_fetcher=later_fetcher,
    )
    pointer_path = _current_pointer(artifact_root)
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["updated_at_utc"] = "2026-08-22T00:00:00Z"
    pointer.pop("pointer_sha256")
    pointer["pointer_sha256"] = pairing._sha256(pointer)
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    with pytest.raises(
        pairing.KisPaperD1ProspectiveObservationPairingError,
        match="current_pointer_invalid",
    ):
        pairing.read_current_kis_paper_d1_prospective_observation_pairing_outcome(
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def test_current_reader_rejects_a_receipt_with_a_mismatched_file_identity(
    tmp_path: Path,
) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    first_fetcher, _ = _recording_fetcher(_observation(FIRST_OBSERVED_AT))
    _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=FIRST_OBSERVED_AT,
        observation_fetcher=first_fetcher,
    )
    later_fetcher, _ = _recording_fetcher(_observation(LATER_OBSERVED_AT))
    later = _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=LATER_OBSERVED_AT,
        observation_fetcher=later_fetcher,
    )
    assert later.evidence_path is not None
    receipt = json.loads(later.evidence_path.read_text(encoding="utf-8"))
    receipt["receipt_id"] = "later-rebound"
    receipt.pop("receipt_sha256")
    receipt["receipt_sha256"] = pairing._sha256(receipt)
    later.evidence_path.write_text(json.dumps(receipt), encoding="utf-8")
    pointer_path = _current_pointer(artifact_root)
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["receipt_sha256"] = receipt["receipt_sha256"]
    pointer.pop("pointer_sha256")
    pointer["pointer_sha256"] = pairing._sha256(pointer)
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    with pytest.raises(
        pairing.KisPaperD1ProspectiveObservationPairingError,
        match="current_receipt_unavailable",
    ):
        pairing.read_current_kis_paper_d1_prospective_observation_pairing_outcome(
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def test_current_reader_rejects_a_pointer_receipt_path_escape(tmp_path: Path) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    first_fetcher, _ = _recording_fetcher(_observation(FIRST_OBSERVED_AT))
    _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=FIRST_OBSERVED_AT,
        observation_fetcher=first_fetcher,
    )
    later_fetcher, _ = _recording_fetcher(_observation(LATER_OBSERVED_AT))
    later = _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=LATER_OBSERVED_AT,
        observation_fetcher=later_fetcher,
    )
    assert later.evidence_path is not None
    escaped_receipt = json.loads(later.evidence_path.read_text(encoding="utf-8"))
    escaped_receipt["receipt_id"] = "../escaped"
    escaped_receipt.pop("receipt_sha256")
    escaped_receipt["receipt_sha256"] = pairing._sha256(escaped_receipt)
    escaped_path = later.evidence_path.parent.parent / "escaped.json"
    escaped_path.write_text(json.dumps(escaped_receipt), encoding="utf-8")
    pointer_path = _current_pointer(artifact_root)
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["receipt_id"] = "../escaped"
    pointer["receipt_sha256"] = escaped_receipt["receipt_sha256"]
    pointer.pop("pointer_sha256")
    pointer["pointer_sha256"] = pairing._sha256(pointer)
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    with pytest.raises(
        pairing.KisPaperD1ProspectiveObservationPairingError,
        match="current_pointer_invalid",
    ):
        pairing.read_current_kis_paper_d1_prospective_observation_pairing_outcome(
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def test_current_reader_rejects_a_first_receipt_with_mismatched_file_identity(
    tmp_path: Path,
) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    first_fetcher, _ = _recording_fetcher(_observation(FIRST_OBSERVED_AT))
    first = _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=FIRST_OBSERVED_AT,
        observation_fetcher=first_fetcher,
    )
    later_fetcher, _ = _recording_fetcher(_observation(LATER_OBSERVED_AT))
    later = _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=LATER_OBSERVED_AT,
        observation_fetcher=later_fetcher,
    )
    assert first.evidence_path is not None
    assert later.evidence_path is not None
    forged_first = json.loads(first.evidence_path.read_text(encoding="utf-8"))
    forged_first["receipt_id"] = "first-rebound"
    forged_first.pop("receipt_sha256")
    forged_first["receipt_sha256"] = pairing._sha256(forged_first)
    first.evidence_path.write_text(json.dumps(forged_first), encoding="utf-8")
    forged_later = json.loads(later.evidence_path.read_text(encoding="utf-8"))
    forged_later["first_receipt_binding"]["receipt_sha256"] = forged_first[
        "receipt_sha256"
    ]
    forged_later.pop("receipt_sha256")
    forged_later["receipt_sha256"] = pairing._sha256(forged_later)
    later.evidence_path.write_text(json.dumps(forged_later), encoding="utf-8")
    pointer_path = _current_pointer(artifact_root)
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["receipt_sha256"] = forged_later["receipt_sha256"]
    pointer.pop("pointer_sha256")
    pointer["pointer_sha256"] = pairing._sha256(pointer)
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    with pytest.raises(
        pairing.KisPaperD1ProspectiveObservationPairingError,
        match="receipt_invalid",
    ):
        pairing.read_current_kis_paper_d1_prospective_observation_pairing_outcome(
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def test_current_reader_rejects_a_later_receipt_bound_to_the_wrong_first(
    tmp_path: Path,
) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    first_fetcher, _ = _recording_fetcher(_observation(FIRST_OBSERVED_AT))
    _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=FIRST_OBSERVED_AT,
        observation_fetcher=first_fetcher,
    )
    later_fetcher, _ = _recording_fetcher(_observation(LATER_OBSERVED_AT))
    later = _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=LATER_OBSERVED_AT,
        observation_fetcher=later_fetcher,
    )
    assert later.evidence_path is not None
    receipt = json.loads(later.evidence_path.read_text(encoding="utf-8"))
    receipt["first_receipt_binding"]["receipt_id"] = "first-unknown"
    receipt.pop("receipt_sha256")
    receipt["receipt_sha256"] = pairing._sha256(receipt)
    later.evidence_path.write_text(json.dumps(receipt), encoding="utf-8")
    pointer_path = _current_pointer(artifact_root)
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["receipt_sha256"] = receipt["receipt_sha256"]
    pointer.pop("pointer_sha256")
    pointer["pointer_sha256"] = pairing._sha256(pointer)
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    with pytest.raises(pairing.KisPaperD1ProspectiveObservationPairingError):
        pairing.read_current_kis_paper_d1_prospective_observation_pairing_outcome(
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def test_schedule_owned_wait_never_constructs_a_client(tmp_path: Path) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    calls: list[datetime] = []

    def fetcher(*_args: object, **kwargs: object) -> KisPaperDailyPairForwardObservation:
        calls.append(kwargs["observed_at"])
        raise AssertionError("not-due work must not collect")

    result = _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        observation_fetcher=fetcher,
    )

    assert result.status == "not_due"
    assert result.reason == "next_due_owned"
    assert result.evidence_path is None
    assert calls == []
    assert _state(artifact_root)["expected_stage"] == "first"
    with pytest.raises(
        pairing.KisPaperD1ProspectiveObservationPairingError,
        match="current_pointer_unavailable",
    ):
        pairing.read_current_kis_paper_d1_prospective_observation_pairing_outcome(
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def test_existing_first_receipt_reattaches_idempotently_without_collection(tmp_path: Path) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    first_fetcher, _ = _recording_fetcher(_observation(FIRST_OBSERVED_AT))
    first = _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=FIRST_OBSERVED_AT,
        observation_fetcher=first_fetcher,
    )
    assert first.evidence_path is not None
    state_path = artifact_root.joinpath(
        *pairing.KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_ARTIFACT_PARTS,
        "state.json",
    )
    state_path.unlink()
    calls: list[datetime] = []

    def forbidden_fetcher(*_args: object, **kwargs: object) -> KisPaperDailyPairForwardObservation:
        calls.append(kwargs["observed_at"])
        raise AssertionError("a retained first receipt must be reattached, not recollected")

    replay = _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=FIRST_OBSERVED_AT,
        observation_fetcher=forbidden_fetcher,
    )

    assert replay.status == "first_recorded"
    assert replay.evidence_path == first.evidence_path
    assert calls == []
    assert len(list(first.evidence_path.parent.glob("first-*.json"))) == 1


def test_missing_target_fails_closed_and_does_not_leave_a_pending_pair(tmp_path: Path) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    incomplete = KisPaperDailyPairForwardObservation(
        rows_by_target={"QQQ/NAS": (_row("QQQ", "NAS", "812.34"),)},
        failure_reasons_by_target={"SPY/AMS": "daily_response_unavailable"},
        observed_at=FIRST_OBSERVED_AT,
    )
    fetcher, calls = _recording_fetcher(incomplete)

    result = _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=FIRST_OBSERVED_AT,
        observation_fetcher=fetcher,
    )

    assert result.status == "input_unavailable"
    assert result.reason == "first_observation_unavailable"
    assert result.first_row_hashes is None
    assert len(calls) == 1
    assert _state(artifact_root)["expected_stage"] == "first"


def test_invalid_first_receipt_fails_closed_before_later_collection(tmp_path: Path) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    first_fetcher, _ = _recording_fetcher(_observation(FIRST_OBSERVED_AT))
    first = _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=FIRST_OBSERVED_AT,
        observation_fetcher=first_fetcher,
    )
    assert first.evidence_path is not None
    receipt = json.loads(first.evidence_path.read_text(encoding="utf-8"))
    receipt["source_contract_sha256"] = "sha256:" + "0" * 64
    first.evidence_path.write_text(json.dumps(receipt), encoding="utf-8")
    calls: list[datetime] = []

    def forbidden_fetcher(*_args: object, **kwargs: object) -> KisPaperDailyPairForwardObservation:
        calls.append(kwargs["observed_at"])
        raise AssertionError("invalid binding must not re-collect")

    result = _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=LATER_OBSERVED_AT,
        observation_fetcher=forbidden_fetcher,
    )

    assert result.status == "input_unavailable"
    assert result.reason == "first_receipt_unavailable"
    assert calls == []
    assert _state(artifact_root)["expected_stage"] == "first"


def test_conflicted_cache_fails_closed_before_first_collection(tmp_path: Path) -> None:
    repository_root, artifact_root = _roots(tmp_path)
    calls: list[datetime] = []

    def forbidden_fetcher(*_args: object, **kwargs: object) -> KisPaperDailyPairForwardObservation:
        calls.append(kwargs["observed_at"])
        raise AssertionError("conflicted cache must stop before collection")

    result = _run(
        repository_root=repository_root,
        artifact_root=artifact_root,
        observed_at=FIRST_OBSERVED_AT,
        observation_fetcher=forbidden_fetcher,
        conflict=True,
    )

    assert result.status == "input_unavailable"
    assert result.reason == "cache_conflict_or_unavailable"
    assert calls == []


def test_worker_uses_only_the_existing_daily_data_client(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_worker_script()
    gates: list[object] = []
    transport_kwargs: dict[str, object] = {}
    client_kwargs: dict[str, object] = {}

    class FakeGate:
        def __init__(self, *, control_root: Path) -> None:
            self.control_root = control_root
            gates.append(self)

    class FakeTransport:
        def __init__(self, **kwargs: object) -> None:
            transport_kwargs.update(kwargs)

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            client_kwargs.update(kwargs)

    class FakeResult:
        def safe_payload(self) -> dict[str, str]:
            return {"status": "not_due"}

    def fake_run(**kwargs: object) -> FakeResult:
        factory = kwargs["client_factory"]
        assert callable(factory)
        factory()
        return FakeResult()

    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", FakeGate)
    monkeypatch.setattr(script, "KisPaperMarketDataTokenStartGate", FakeGate)
    monkeypatch.setattr(script, "UrllibKisPaperDailyPairForwardTransport", FakeTransport)
    monkeypatch.setattr(script, "KisPaperMarketDataClient", FakeClient)
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_environment_config",
        lambda *, environment: object(),
    )
    monkeypatch.setattr(script, "run_kis_paper_d1_prospective_observation_pairing", fake_run)

    script.main(["--execute"], environment={"THERICHER_MODE": "off"})

    assert [gate.control_root for gate in gates] == [
        script._CANONICAL_CONTROL_ROOT,
        script._CANONICAL_CONTROL_ROOT,
    ]
    assert transport_kwargs == {
        "request_gate": gates[0],
        "token_start_gate": gates[1],
    }
    assert client_kwargs["config"] is not None
    assert client_kwargs["transport"] is not None
    assert client_kwargs["max_daily_page_attempts"] == 1
    assert json.loads(capsys.readouterr().out) == {"status": "not_due"}

    worker_source = (
        REPOSITORY_ROOT / "scripts" / "observe_kis_paper_d1_prospective_observation_pairing.py"
    ).read_text(encoding="utf-8")
    for forbidden in (".env", "KIS_LIVE", "KIS_PAPER_ACCOUNT", "order"):
        assert forbidden not in worker_source


def test_docker_service_and_schedule_are_virtual_data_only() -> None:
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    service = compose.split(
        "  kis-paper-d1-prospective-observation-pairing:\n", maxsplit=1
    )[1].split("\nvolumes:\n", maxsplit=1)[0]

    assert 'profiles: ["kis-paper-d1-prospective-observation-pairing"]' in service
    assert "read_only: true" in service
    assert "- /tmp" in service
    assert "scripts/observe_kis_paper_d1_prospective_observation_pairing.py" in service
    assert "KIS_PAPER_APP_KEY" in service
    assert "KIS_PAPER_APP_SECRET" in service
    assert "KIS_PAPER_ACCOUNT" not in service
    assert "KIS_LIVE" not in service
    assert "order" not in service
    assert (
        "daily-qqq-spy-forward/v2:/app/market_data:ro" in service
    )
    assert "collection-control-v1:/app/collection_control" in service
    artifact_mount = (
        "${THERICHER_HOST_MODEL_ARTIFACT_ROOT:-D:/thericher-v2/model-artifacts}"
        ":/app/model_artifacts"
    )
    assert artifact_mount in service

    schedule = (REPOSITORY_ROOT / "scripts" / "install_kis_paper_schedules.ps1").read_text(
        encoding="ascii"
    )
    task_name = "thericher-kis-paper-d1-prospective-observation-pairing"
    assert schedule.count(f'Name = "{task_name}"') == 1
    entry = schedule.split(f'Name = "{task_name}"', maxsplit=1)[1].split("    },", maxsplit=1)[0]
    assert 'Profile = "kis-paper-d1-prospective-observation-pairing"' in entry
    assert 'Service = "kis-paper-d1-prospective-observation-pairing"' in entry
    assert 'ImageServices = @("kis-paper-d1-prospective-observation-pairing")' in entry
    assert 'At = @("08:15", "23:20")' in entry
    assert "DaysOfWeek" not in entry
    assert "RecoverMissedRun = $false" in entry
    assert "ExecutionLimitMinutes = 5" in entry


def _run(
    *,
    repository_root: Path,
    artifact_root: Path,
    observed_at: datetime,
    observation_fetcher: Callable[..., KisPaperDailyPairForwardObservation],
    conflict: bool = False,
):
    def cache_loader(**kwargs: object) -> SimpleNamespace:
        assert kwargs["cache_identity"] == KIS_PAPER_DAILY_PAIR_FORWARD_V2_IDENTITY
        reason = (
            KIS_PAPER_DAILY_PAIR_FORWARD_RETAINED_REVISION_CONFLICT_REASON
            if conflict
            else None
        )
        return SimpleNamespace(
            targets_by_key={
                "QQQ/NAS": SimpleNamespace(last_reason=reason),
                "SPY/AMS": SimpleNamespace(last_reason=None),
            }
        )

    return pairing.run_kis_paper_d1_prospective_observation_pairing(
        cache_root=artifact_root / "cache",
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=observed_at,
        client_factory=object,
        cache_loader=cache_loader,
        observation_fetcher=observation_fetcher,
    )


def _recording_fetcher(
    *observations: KisPaperDailyPairForwardObservation,
) -> tuple[Callable[..., KisPaperDailyPairForwardObservation], list[datetime]]:
    remaining = list(observations)
    calls: list[datetime] = []

    def fetcher(_client: object, *, observed_at: datetime) -> KisPaperDailyPairForwardObservation:
        calls.append(observed_at)
        return remaining.pop(0)

    return fetcher, calls


def _observation(
    observed_at: datetime,
    *,
    qqq_close: str = "812.34",
    spy_close: str = "501.23",
) -> KisPaperDailyPairForwardObservation:
    return KisPaperDailyPairForwardObservation(
        rows_by_target={
            "QQQ/NAS": (_row("QQQ", "NAS", qqq_close),),
            "SPY/AMS": (_row("SPY", "AMS", spy_close),),
        },
        failure_reasons_by_target={},
        observed_at=observed_at,
    )


def _row(symbol: str, exchange: str, close: str) -> KisPaperDailyPairForwardRow:
    value = Decimal(close)
    return KisPaperDailyPairForwardRow(
        symbol=symbol,
        exchange=exchange,
        session_date=SESSION,
        open=value,
        high=value + Decimal("1"),
        low=value - Decimal("1"),
        close=value,
        volume=Decimal("100"),
    )


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    repository_root = tmp_path / "repository"
    artifact_root = tmp_path / "artifacts"
    repository_root.mkdir()
    artifact_root.mkdir()
    return repository_root, artifact_root


def _state(artifact_root: Path) -> dict[str, object]:
    path = artifact_root.joinpath(
        *pairing.KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_ARTIFACT_PARTS,
        "state.json",
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _current_pointer(artifact_root: Path) -> Path:
    return artifact_root.joinpath(
        *pairing.KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_ARTIFACT_PARTS,
        "current.json",
    )


def _load_worker_script() -> ModuleType:
    script_path = (
        REPOSITORY_ROOT
        / "scripts"
        / "observe_kis_paper_d1_prospective_observation_pairing.py"
    )
    spec = importlib.util.spec_from_file_location(
        "observe_kis_paper_d1_prospective_observation_pairing_for_test",
        script_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
