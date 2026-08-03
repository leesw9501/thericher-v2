from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.ops.kis_paper_intraday_head_schedule_receipt import (
    KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_DIRECTORY,
    SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE,
    write_kis_paper_intraday_head_schedule_receipt,
)

_COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"


def test_schedule_receipt_writes_a_complete_source_safe_no_intent_outcome(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"

    result = write_kis_paper_intraday_head_schedule_receipt(
        **_complete_kwargs(),
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    assert result.terminal_status == "complete"
    assert result.recovery_class == "complete"
    assert result.scheduler_exit_code == 0
    assert result.evidence_path == (
        artifact_root
        / KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_DIRECTORY
        / "intraday-head-unit.json"
    )
    payload = json.loads(result.evidence_path.read_text(encoding="ascii"))
    assert payload["status"] == "complete"
    assert payload["terminal"] == {
        "recovery_class": "complete",
        "scheduler_exit_code": 0,
        "status": "complete",
    }
    assert payload["stages"]["prospective_spy_cycle"] == {
        "canary_run_id": None,
        "collector_process_separate": True,
        "cycle_id": "prospective-spy-cycle-unit",
        "exit_code": 0,
        "status": "no_intent",
    }
    assert payload["stages"]["prospective_loop"] == {
        "exit_code": 0,
        "status": "embedded",
    }
    assert payload["stages"]["prospective_session"] == {
        "exit_code": 0,
        "session_id": "prospective-qqq-unit",
        "status": "no_intent",
    }
    assert payload["stages"]["prospective_validation"] == {
        "exit_code": 0,
        "session_id": "prospective-qqq-unit",
        "status": "validated",
    }
    assert payload["stages"]["profiled_mtf_forward_capture"] == {
        "data_only": True,
        "exit_code": 0,
        "status": "outside_cycle_slot",
    }
    rendered = result.evidence_path.read_bytes().lower()
    assert b"paper-key" not in rendered
    assert b"kis_live" not in rendered


@pytest.mark.parametrize(
    ("overrides", "expected_recovery_class"),
    [
        ({"prospective_loop_exit_code": 7}, "prospective_loop_exit_nonzero"),
        ({"prospective_loop_status": "unavailable"}, "prospective_loop_payload_unavailable"),
        ({"prospective_session_exit_code": 9}, "prospective_session_exit_nonzero"),
        ({"prospective_session_status": "unavailable"}, "prospective_session_payload_unavailable"),
        ({"prospective_session_id": None}, "prospective_session_id_unavailable"),
        ({"prospective_validation_exit_code": 11}, "prospective_validation_exit_nonzero"),
        (
            {"prospective_validation_status": "unavailable"},
            "prospective_validation_payload_unavailable",
        ),
        (
            {"prospective_validation_session_id": "prospective-qqq-other"},
            "prospective_validation_session_mismatch",
        ),
    ],
)
def test_schedule_receipt_marks_required_downstream_faults_for_recovery(
    tmp_path: Path,
    overrides: dict[str, object],
    expected_recovery_class: str,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    kwargs = _complete_kwargs()
    kwargs.update(overrides)

    result = write_kis_paper_intraday_head_schedule_receipt(
        **kwargs,
        artifact_root=tmp_path / "model-artifacts",
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    assert result.terminal_status == "recovery"
    assert result.recovery_class == expected_recovery_class
    assert result.scheduler_exit_code == SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE
    assert result.safe_payload()["status"] == "recovery"


def test_schedule_receipt_preserves_the_collection_exit_code(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    kwargs = _complete_kwargs()
    kwargs["collection_exit_code"] = 13

    result = write_kis_paper_intraday_head_schedule_receipt(
        **kwargs,
        artifact_root=tmp_path / "model-artifacts",
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    assert result.terminal_status == "recovery"
    assert result.recovery_class == "collection_exit_nonzero"
    assert result.scheduler_exit_code == 13


@pytest.mark.parametrize(
    ("overrides", "expected_recovery_class"),
    [
        ({"prospective_spy_cycle_exit_code": 7}, "prospective_spy_cycle_exit_nonzero"),
        (
            {"prospective_spy_cycle_status": "unavailable"},
            "prospective_spy_cycle_payload_unavailable",
        ),
        ({"prospective_spy_cycle_id": None}, "prospective_spy_cycle_id_unavailable"),
        (
            {
                "prospective_spy_cycle_status": "canary_completed",
                "prospective_spy_canary_run_id": None,
            },
            "prospective_spy_canary_run_id_unavailable",
        ),
    ],
)
def test_schedule_receipt_marks_prospective_spy_cycle_faults_for_recovery(
    tmp_path: Path,
    overrides: dict[str, object],
    expected_recovery_class: str,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    kwargs = _complete_kwargs()
    kwargs.update(overrides)

    result = write_kis_paper_intraday_head_schedule_receipt(
        **kwargs,
        artifact_root=tmp_path / "model-artifacts",
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    assert result.terminal_status == "recovery"
    assert result.recovery_class == expected_recovery_class
    assert result.scheduler_exit_code == SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE


def test_schedule_receipt_is_idempotent_for_one_run_id_and_timestamp(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    observed_at = datetime(2026, 7, 28, 15, 31, tzinfo=UTC)

    first = write_kis_paper_intraday_head_schedule_receipt(
        **_complete_kwargs(),
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=observed_at,
    )
    first_bytes = first.evidence_path.read_bytes()
    second = write_kis_paper_intraday_head_schedule_receipt(
        **_complete_kwargs(),
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=observed_at,
    )

    assert second.evidence_path == first.evidence_path
    assert second.evidence_path.read_bytes() == first_bytes


def test_schedule_receipt_keeps_the_legacy_observer_optional(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    kwargs = _complete_kwargs()
    kwargs.update(observation_exit_code=17, observation_status="unavailable")

    result = write_kis_paper_intraday_head_schedule_receipt(
        **kwargs,
        artifact_root=tmp_path / "model-artifacts",
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    assert result.terminal_status == "complete"
    assert result.scheduler_exit_code == 0


def test_schedule_receipt_accepts_the_explicit_data_only_execution_branch(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    kwargs = _complete_kwargs()
    kwargs.update(
        prospective_loop_status="not_applicable",
        prospective_session_status="not_applicable",
        prospective_session_id=None,
        prospective_validation_status="not_applicable",
        prospective_validation_session_id=None,
        observation_status="not_observed",
    )

    result = write_kis_paper_intraday_head_schedule_receipt(
        **kwargs,
        artifact_root=tmp_path / "model-artifacts",
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    assert result.terminal_status == "complete"
    assert result.scheduler_exit_code == 0
    assert result.safe_payload()["stages"]["observation"] == {
        "exit_code": 0,
        "status": "not_observed",
        "required_for_qqq_cycle": False,
        "data_only_pair_observation": True,
    }


@pytest.mark.parametrize(
    ("overrides", "expected_recovery_class"),
    [
        (
            {"observation_exit_code": 20, "observation_status": "unavailable"},
            "observation_exit_nonzero",
        ),
        ({"observation_status": "unavailable"}, "observation_payload_unavailable"),
        ({"observation_status": "busy"}, "observation_payload_unavailable"),
    ],
)
def test_data_only_schedule_receipt_requires_a_terminal_observation_fact(
    tmp_path: Path,
    overrides: dict[str, object],
    expected_recovery_class: str,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    kwargs = _complete_kwargs()
    kwargs.update(
        prospective_loop_status="not_applicable",
        prospective_session_status="not_applicable",
        prospective_session_id=None,
        prospective_validation_status="not_applicable",
        prospective_validation_session_id=None,
    )
    kwargs.update(overrides)

    result = write_kis_paper_intraday_head_schedule_receipt(
        **kwargs,
        artifact_root=tmp_path / "model-artifacts",
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    assert result.terminal_status == "recovery"
    assert result.recovery_class == expected_recovery_class
    assert result.scheduler_exit_code == SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE


@pytest.mark.parametrize(
    ("overrides", "expected_recovery_class"),
    [
        (
            {"capture_cycle_exit_code": 20, "capture_cycle_status": "input_unavailable"},
            "capture_cycle_exit_nonzero",
        ),
        ({"capture_cycle_status": "unavailable"}, "capture_cycle_payload_unavailable"),
        ({"capture_cycle_status": "busy"}, "capture_cycle_payload_unavailable"),
    ],
)
def test_data_only_schedule_receipt_requires_a_terminal_capture_cycle_fact(
    tmp_path: Path,
    overrides: dict[str, object],
    expected_recovery_class: str,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    kwargs = _complete_kwargs()
    kwargs.update(
        prospective_loop_status="not_applicable",
        prospective_session_status="not_applicable",
        prospective_session_id=None,
        prospective_validation_status="not_applicable",
        prospective_validation_session_id=None,
    )
    kwargs.update(overrides)

    result = write_kis_paper_intraday_head_schedule_receipt(
        **kwargs,
        artifact_root=tmp_path / "model-artifacts",
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    assert result.terminal_status == "recovery"
    assert result.recovery_class == expected_recovery_class
    assert result.scheduler_exit_code == SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE


def test_schedule_receipt_rejects_a_git_workspace_artifact_root(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()

    with pytest.raises(ValueError, match="outside Git"):
        write_kis_paper_intraday_head_schedule_receipt(
            **_complete_kwargs(),
            artifact_root=repository_root / "model-artifacts",
            repository_root=repository_root,
            observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
        )


def test_compose_schedule_receipt_service_is_offline_and_has_no_kis_surface() -> None:
    compose = _COMPOSE.read_text(encoding="ascii")
    section = compose.split("\n  kis-paper-intraday-head-receipt:\n", maxsplit=1)[1].split(
        "\n  kis-paper-receipt-observer:\n", maxsplit=1
    )[0]
    lowered = section.lower()

    assert 'profiles: ["kis-paper-intraday-head"]' in section
    assert "network_mode: none" in section
    assert "read_only: true" in section
    assert "thericher_v2.ops.kis_paper_intraday_head_schedule_receipt" in section
    assert "KIS_PAPER_" not in section
    assert "kis_live" not in lowered
    assert "/app/market_data" not in section
    assert "/app/model_artifacts" in section


def test_compose_capture_cycle_service_is_offline_and_has_no_kis_surface() -> None:
    compose = _COMPOSE.read_text(encoding="ascii")
    section = compose.split("\n  profiled-mtf-forward-capture-cycle:\n", maxsplit=1)[1].split(
        "\n  kis-readonly:\n", maxsplit=1
    )[0]
    lowered = section.lower()

    assert 'profiles: ["kis-paper-intraday-head"]' in section
    assert "network_mode: none" in section
    assert "read_only: true" in section
    assert "run_profiled_mtf_forward_capture_cycle.py" in section
    assert "KIS_PAPER_" not in section
    assert "kis_live" not in lowered
    assert "/app/market_data" in section
    assert "/app/model_artifacts" in section


def test_compose_prospective_spy_cycle_has_only_the_virtual_paper_route() -> None:
    compose = _COMPOSE.read_text(encoding="ascii")
    section = compose.split("\n  kis-paper-prospective-spy-cycle:\n", maxsplit=1)[1].split(
        "\n  kis-paper-prospective-spy-timing-probe:\n", maxsplit=1
    )[0]
    lowered = section.lower()

    assert 'profiles: ["kis-paper-intraday-head"]' in section
    assert "thericher_v2.ops.kis_paper_prospective_spy_cycle" in section
    assert "--execute" in section
    assert "--cancel-after-submit" in section
    assert "THERICHER_MODE: kis_paper" in section
    assert "KIS_PAPER_APP_KEY" in section
    assert "KIS_PAPER_ACCOUNT_NO" in section
    assert "KIS_LIVE" not in section
    assert "gpus:" not in section
    assert ":/app/market_data:ro" in section
    assert ":/app/model_artifacts" in section
    assert "network_mode: none" not in lowered


def test_compose_prospective_spy_timing_probe_is_network_disabled_and_credential_free() -> None:
    compose = _COMPOSE.read_text(encoding="ascii")
    section = compose.split("\n  kis-paper-prospective-spy-timing-probe:\n", maxsplit=1)[1].split(
        "\n  kis-paper-prospective-qqq-session:\n", maxsplit=1
    )[0]

    assert 'profiles: ["kis-paper-intraday-head"]' in section
    assert "thericher_v2.ops.kis_paper_prospective_spy_timing_probe" in section
    assert "network_mode: none" in section
    assert "KIS_" not in section
    assert "THERICHER_MODE" not in section
    assert ":/app/market_data:ro" in section
    assert ":/app/model_artifacts" in section


def _complete_kwargs() -> dict[str, object]:
    return {
        "run_id": "intraday-head-unit",
        "collection_exit_code": 0,
        "prospective_spy_cycle_exit_code": 0,
        "prospective_spy_cycle_status": "no_intent",
        "prospective_spy_cycle_id": "prospective-spy-cycle-unit",
        "prospective_spy_canary_run_id": None,
        "prospective_loop_exit_code": 0,
        "prospective_loop_status": "embedded",
        "prospective_session_exit_code": 0,
        "prospective_session_status": "no_intent",
        "prospective_session_id": "prospective-qqq-unit",
        "prospective_validation_exit_code": 0,
        "prospective_validation_status": "validated",
        "prospective_validation_session_id": "prospective-qqq-unit",
        "observation_exit_code": 0,
        "observation_status": "pending",
        "capture_cycle_exit_code": 0,
        "capture_cycle_status": "outside_cycle_slot",
    }
