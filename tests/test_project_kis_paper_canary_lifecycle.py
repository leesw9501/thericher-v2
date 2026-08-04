"""Host-only behavior tests for the sanitized lifecycle projection script."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from types import SimpleNamespace

from thericher_v2.contracts import SCHEMA_VERSION

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "project_kis_paper_canary_lifecycle.py"
VALIDATOR_SCRIPT_PATH = (
    Path(__file__).parents[1] / "scripts" / "validate_kis_paper_canary_lifecycle_evidence.py"
)


def _write_valid_evidence(
    artifact_root: Path,
    run_id: str,
    *,
    recorded_run_id: str | None = None,
) -> None:
    evidence_path = artifact_root / "execution" / "kis-paper-canary" / run_id / "evidence.json"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": "kis_paper_canary_evidence",
                "paper_only": True,
                "run_id": recorded_run_id or run_id,
                "intent_fingerprint": "sha256:" + "a" * 64,
                "decision_ref": "decision-" + "b" * 16,
                "observed_at": "2026-08-04T00:00:00+00:00",
                "phase": "submitted",
                "order_side": "buy",
                "submit_response_category": "acknowledged_order_reference",
                "reconciliation": {
                    "status": "clean",
                    "account_status": "available",
                    "matching_open_order": True,
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_lifecycle_projection_defaults_to_host_artifact_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("THERICHER_HOST_MODEL_ARTIFACT_ROOT", str(tmp_path / "host-artifacts"))
    monkeypatch.setenv("THERICHER_MODEL_ARTIFACT_ROOT", "/app/model_artifacts")

    script = runpy.run_path(str(SCRIPT_PATH))
    arguments = script["build_parser"]().parse_args(["--run-id", "canary-test-1"])

    assert arguments.artifact_root == tmp_path / "host-artifacts"


def test_lifecycle_projection_prints_sanitized_fact_for_valid_evidence(
    tmp_path: Path,
    capsys,
) -> None:
    run_id = "canary-cli-valid-1"
    _write_valid_evidence(tmp_path, run_id)
    script = runpy.run_path(str(SCRIPT_PATH))

    assert script["main"](["--run-id", run_id, "--artifact-root", str(tmp_path)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["paper_only"] is True
    assert payload["lifecycle_state"] == "acknowledged"
    assert payload["attribution_eligibility"] == "open"
    assert payload["sizing_status"] == "fixed_canary"
    assert "order_reference" not in payload
    assert "account" not in payload


def test_lifecycle_projection_reports_missing_evidence_as_unavailable(
    tmp_path: Path,
    capsys,
) -> None:
    script = runpy.run_path(str(SCRIPT_PATH))

    assert (
        script["main"](
            ["--run-id", "canary-cli-missing-1", "--artifact-root", str(tmp_path)]
        )
        == 2
    )

    assert json.loads(capsys.readouterr().out) == {
        "paper_only": True,
        "status": "unavailable",
    }


def test_lifecycle_projection_rejects_unsafe_or_mismatched_run_id(
    tmp_path: Path,
    capsys,
) -> None:
    script = runpy.run_path(str(SCRIPT_PATH))

    _write_valid_evidence(tmp_path, "")

    assert script["main"](["--run-id", "", "--artifact-root", str(tmp_path)]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "paper_only": True,
        "status": "unavailable",
    }

    assert script["main"](["--run-id", "../outside", "--artifact-root", str(tmp_path)]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "paper_only": True,
        "status": "unavailable",
    }


def test_lifecycle_projection_rejects_reparse_run_root(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    run_id = "canary-cli-reparse-1"
    _write_valid_evidence(tmp_path, run_id)
    run_root = tmp_path / "execution" / "kis-paper-canary" / run_id
    original_lstat = Path.lstat

    def marked_lstat(path: Path):
        metadata = original_lstat(path)
        if path == run_root:
            return SimpleNamespace(
                st_mode=metadata.st_mode,
                st_file_attributes=0x400,
            )
        return metadata

    monkeypatch.setattr(Path, "lstat", marked_lstat)
    script = runpy.run_path(str(SCRIPT_PATH))

    assert script["main"](["--run-id", run_id, "--artifact-root", str(tmp_path)]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "paper_only": True,
        "status": "unavailable",
    }

    _write_valid_evidence(tmp_path, "canary-cli-requested-1", recorded_run_id="canary-cli-other-1")

    assert (
        script["main"](
            ["--run-id", "canary-cli-requested-1", "--artifact-root", str(tmp_path)]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out) == {
        "paper_only": True,
        "status": "unavailable",
    }


def test_lifecycle_validator_independently_revalidates_safe_projection(
    tmp_path: Path,
    capsys,
) -> None:
    run_id = "canary-cli-validator-1"
    _write_valid_evidence(tmp_path, run_id)
    script = runpy.run_path(str(VALIDATOR_SCRIPT_PATH))

    assert script["main"](["--run-id", run_id, "--artifact-root", str(tmp_path)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["run_id"] == run_id
    assert payload["paper_only"] is True
    assert "order_reference" not in payload
