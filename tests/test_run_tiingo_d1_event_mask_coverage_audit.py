from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def test_runner_uses_pinned_snapshot_and_safe_summary(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    runner = _load_runner()
    snapshot = object()
    summary_path = tmp_path / "summary.json"
    summary_path.write_text('{"raw_market_data_written": false}\n', encoding="ascii")
    observed: dict[str, object] = {}

    def load_snapshot(path: Path, **kwargs: object) -> object:
        observed["snapshot_path"] = path
        observed["load_kwargs"] = kwargs
        return snapshot

    def run_audit(
        received_snapshot: object,
        **kwargs: object,
    ) -> SimpleNamespace:
        observed["received_snapshot"] = received_snapshot
        observed["run_kwargs"] = kwargs
        return SimpleNamespace(summary_path=summary_path)

    monkeypatch.setattr(runner, "load_verified_tiingo_etf_d1_snapshot", load_snapshot)
    monkeypatch.setattr(runner, "run_tiingo_d1_event_mask_coverage_audit", run_audit)
    artifact_root = tmp_path / "model-artifacts"

    runner.main(["--run-label", "unit-run", "--artifact-root", str(artifact_root)])

    assert observed["received_snapshot"] is snapshot
    assert observed["load_kwargs"] == {
        "dataset_id": "us_equities.tiingo_etf_daily.snapshot=20260801T173121Z-tiingo-etf-d1-r1",
        "expected_dataset_hash": (
            "sha256:b47539a373bf2d625ad2380376808cf412219f6c5d932b66631bb3aa553683cf"
        ),
        "expected_manifest_hash": (
            "sha256:8b2e375a027e645ea2065ec61b252b7097da5e743155eb819129391125c072de"
        ),
        "market_data_root": runner.DEFAULT_MARKET_DATA_ROOT,
        "repo_root": runner._REPOSITORY_ROOT,
    }
    assert observed["run_kwargs"] == {
        "artifact_root": artifact_root,
        "rotation_artifact_root": artifact_root,
        "rotation_run_label": runner._ROTATION_RUN_LABEL,
        "run_label": "unit-run",
        "repo_root": runner._REPOSITORY_ROOT,
    }
    assert capsys.readouterr().out == '{"raw_market_data_written": false}\n'


def test_runner_verify_only_uses_safe_receipt(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    runner = _load_runner()
    snapshot = object()
    observed: dict[str, object] = {}

    def load_snapshot(path: Path, **kwargs: object) -> object:
        observed["snapshot_path"] = path
        observed["load_kwargs"] = kwargs
        return snapshot

    def validate_audit(
        received_snapshot: object,
        **kwargs: object,
    ) -> SimpleNamespace:
        observed["received_snapshot"] = received_snapshot
        observed["validation_kwargs"] = kwargs
        return SimpleNamespace(
            status="verified",
            precommit_hash="sha256:" + "a" * 64,
            rotation_precommit_hash="sha256:" + "b" * 64,
        )

    def unexpected_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("--verify-only must not run the audit")

    monkeypatch.setattr(runner, "load_verified_tiingo_etf_d1_snapshot", load_snapshot)
    monkeypatch.setattr(runner, "validate_tiingo_d1_event_mask_coverage_audit", validate_audit)
    monkeypatch.setattr(runner, "run_tiingo_d1_event_mask_coverage_audit", unexpected_run)
    artifact_root = tmp_path / "model-artifacts"

    runner.main(
        [
            "--run-label",
            "unit-verify",
            "--artifact-root",
            str(artifact_root),
            "--verify-only",
        ]
    )

    assert observed["received_snapshot"] is snapshot
    assert observed["validation_kwargs"] == {
        "artifact_root": artifact_root,
        "rotation_artifact_root": artifact_root,
        "rotation_run_label": runner._ROTATION_RUN_LABEL,
        "run_label": "unit-verify",
        "repo_root": runner._REPOSITORY_ROOT,
    }
    assert capsys.readouterr().out == (
        '{"precommit_hash": "sha256:'
        + "a" * 64
        + '", "rotation_precommit_hash": "sha256:'
        + "b" * 64
        + '", "status": "verified"}\n'
    )


def test_runner_has_no_credential_or_execution_surface() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_tiingo_d1_event_mask_coverage_audit.py"
    ).read_text(encoding="ascii").lower()

    assert ".env" not in source
    assert "kis" not in source
    assert "order" not in source
    assert "broker" not in source
    assert "http" not in source


def _load_runner():
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_tiingo_d1_event_mask_coverage_audit.py"
    )
    specification = importlib.util.spec_from_file_location(
        "run_tiingo_d1_event_mask_coverage_audit_for_test",
        script_path,
    )
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module
