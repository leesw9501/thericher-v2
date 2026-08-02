from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from thericher_v2.research.norgate_d1_trio_momentum_falsification import (
    NorgateD1TrioMomentumResult,
)


def test_runner_uses_pinned_source_and_emits_aggregate_only_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _load_runner()
    snapshot = tmp_path / "market-data" / "snapshot=private-source"
    artifact_root = tmp_path / "model-artifacts"
    panel = SimpleNamespace(bars_by_symbol={"SPY": (), "QQQ": (), "IWM": ()})
    observed: dict[str, object] = {}

    def load_panel(path: Path, **kwargs: object) -> object:
        observed["snapshot"] = path
        observed["load_kwargs"] = kwargs
        return panel

    def run_diagnostic(received_bars: object) -> NorgateD1TrioMomentumResult:
        observed["received_bars"] = received_bars
        return _result(
            status="inconclusive_non_promoting",
            reason="rule_hit_rate_strictly_above_always_long",
            rule_longs=31,
            rule_hits=18,
            always_long_hits=70,
        )

    monkeypatch.setattr(runner, "load_verified_norgate_d1_diagnostic_panel", load_panel)
    monkeypatch.setattr(runner, "run_norgate_d1_trio_momentum_falsification", run_diagnostic)
    runner.main(
        [
            "--snapshot",
            str(snapshot),
            "--run-label",
            "unit-run",
            "--artifact-root",
            str(artifact_root),
        ]
    )

    summary = json.loads(capsys.readouterr().out)
    receipt = _receipt(artifact_root)
    assert observed == {
        "snapshot": snapshot,
        "load_kwargs": {
            "expected_dataset_hash": runner._EXPECTED_DATASET_HASH,
            "expected_manifest_hash": runner._EXPECTED_MANIFEST_HASH,
            "repo_root": runner._REPOSITORY_ROOT,
        },
        "received_bars": panel.bars_by_symbol,
    }
    assert summary["campaign_id"] == runner._CAMPAIGN_ID
    assert summary["receipt_sha256"] == runner._sha256(
        json.dumps(
            receipt,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    assert receipt["outcome"] == _result(
        status="inconclusive_non_promoting",
        reason="rule_hit_rate_strictly_above_always_long",
        rule_longs=31,
        rule_hits=18,
        always_long_hits=70,
    ).safe_payload()
    text = _receipt_path(artifact_root).read_text(encoding="ascii")
    assert str(snapshot) not in text
    assert "901.23" not in text
    assert "2026-08-02" not in text


def test_runner_reattests_an_identical_redacted_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _load_runner()
    artifact_root = tmp_path / "model-artifacts"
    monkeypatch.setattr(
        runner,
        "load_verified_norgate_d1_diagnostic_panel",
        lambda *_args, **_kwargs: SimpleNamespace(bars_by_symbol={"SPY": (), "QQQ": (), "IWM": ()}),
    )
    monkeypatch.setattr(
        runner,
        "run_norgate_d1_trio_momentum_falsification",
        lambda *_args, **_kwargs: _result(
            status="rejected",
            reason="rule_hit_rate_not_above_always_long",
            rule_longs=30,
            rule_hits=12,
            always_long_hits=70,
        ),
    )
    arguments = [
        "--snapshot",
        str(tmp_path / "market-data" / "snapshot=private-source"),
        "--run-label",
        "unit-run",
        "--artifact-root",
        str(artifact_root),
    ]

    runner.main(arguments)
    first = _receipt_path(artifact_root).read_bytes()
    first_summary = capsys.readouterr().out
    runner.main(arguments)

    assert _receipt_path(artifact_root).read_bytes() == first
    assert capsys.readouterr().out == first_summary


def test_runner_rejects_git_artifact_root_before_source_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_runner()
    source_read = False

    def fail_source_read(*_args: object, **_kwargs: object) -> object:
        nonlocal source_read
        source_read = True
        raise AssertionError("source must not be read")

    monkeypatch.setattr(runner, "load_verified_norgate_d1_diagnostic_panel", fail_source_read)
    with pytest.raises(ValueError, match="outside Git"):
        runner.main(
            [
                "--snapshot",
                "C:/private/snapshot",
                "--run-label",
                "unit-run",
                "--artifact-root",
                str(runner._REPOSITORY_ROOT / "artifacts"),
            ]
        )
    assert source_read is False


def test_runner_rejects_an_untyped_result_before_writing_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_runner()
    artifact_root = tmp_path / "model-artifacts"
    monkeypatch.setattr(
        runner,
        "load_verified_norgate_d1_diagnostic_panel",
        lambda *_args, **_kwargs: SimpleNamespace(bars_by_symbol={"SPY": (), "QQQ": (), "IWM": ()}),
    )
    monkeypatch.setattr(
        runner,
        "run_norgate_d1_trio_momentum_falsification",
        lambda *_args, **_kwargs: SimpleNamespace(safe_payload=lambda: {}),
    )

    with pytest.raises(TypeError, match="typed result"):
        runner.main(
            [
                "--snapshot",
                str(tmp_path / "market-data" / "snapshot=private-source"),
                "--run-label",
                "invalid",
                "--artifact-root",
                str(artifact_root),
            ]
        )
    assert not any(artifact_root.rglob("validation-receipt.json"))


def test_receipt_boundary_rejects_a_subclass_safe_payload_override() -> None:
    runner = _load_runner()

    class ForgedResult(NorgateD1TrioMomentumResult):
        def safe_payload(self) -> dict[str, object]:
            return {
                "campaign_id": runner._CAMPAIGN_ID,
                "status": "inconclusive_non_promoting",
                "raw_bar": "must-not-be-serialized",
            }

    result = ForgedResult(
        status="rejected",
        reason="rule_hit_rate_not_above_always_long",
        target_evaluation_performed=True,
        validation_long_decision_count=30,
        validation_target_evaluable_slot_count=138,
        rule_hit_count=12,
        always_long_hit_count=70,
    )

    with pytest.raises(TypeError, match="exact typed result"):
        runner._receipt_payload(result)


def test_runner_rejects_mutated_result_semantics_before_receipt_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_runner()
    artifact_root = tmp_path / "model-artifacts"
    result = _result(
        status="rejected",
        reason="rule_hit_rate_not_above_always_long",
        rule_longs=30,
        rule_hits=12,
        always_long_hits=70,
    )
    object.__setattr__(result, "status", "inconclusive_non_promoting")
    monkeypatch.setattr(
        runner,
        "load_verified_norgate_d1_diagnostic_panel",
        lambda *_args, **_kwargs: SimpleNamespace(bars_by_symbol={"SPY": (), "QQQ": (), "IWM": ()}),
    )
    monkeypatch.setattr(
        runner,
        "run_norgate_d1_trio_momentum_falsification",
        lambda *_args, **_kwargs: result,
    )

    with pytest.raises(ValueError, match="result semantics"):
        runner.main(
            [
                "--snapshot",
                str(tmp_path / "market-data" / "snapshot=private-source"),
                "--run-label",
                "invalid",
                "--artifact-root",
                str(artifact_root),
            ]
        )

    assert not any(artifact_root.rglob("validation-receipt.json"))


def test_runner_has_no_external_or_execution_surface() -> None:
    source = _script_path().read_text(encoding="ascii").lower()
    for forbidden in (
        ".env",
        "os.environ",
        "http",
        "urllib",
        "requests",
        "socket",
        "kis",
        "order",
        "broker",
        "account",
        "local_paper",
        "gpu",
        "training",
        "live",
    ):
        assert forbidden not in source


def _result(
    *,
    status: str,
    reason: str,
    rule_longs: int,
    rule_hits: int,
    always_long_hits: int,
) -> NorgateD1TrioMomentumResult:
    return NorgateD1TrioMomentumResult(
        status=status,  # type: ignore[arg-type]
        reason=reason,  # type: ignore[arg-type]
        target_evaluation_performed=True,
        validation_long_decision_count=rule_longs,
        validation_target_evaluable_slot_count=138,
        rule_hit_count=rule_hits,
        always_long_hit_count=always_long_hits,
    )


def _receipt(artifact_root: Path) -> dict[str, object]:
    return json.loads(_receipt_path(artifact_root).read_text(encoding="ascii"))


def _receipt_path(artifact_root: Path) -> Path:
    return (
        artifact_root
        / "research"
        / "norgate-d1-trio-momentum-falsification-v1"
        / "unit-run"
        / "validation-receipt.json"
    )


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_norgate_d1_trio_momentum_falsification.py"
    )


def _load_runner() -> ModuleType:
    specification = importlib.util.spec_from_file_location(
        "run_norgate_d1_trio_momentum_falsification_for_test",
        _script_path(),
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module
