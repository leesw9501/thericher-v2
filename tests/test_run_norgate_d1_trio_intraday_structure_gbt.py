from __future__ import annotations

import importlib.util
import json
import socket
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from thericher_v2.research.norgate_d1_trio_intraday_structure_gbt import (
    run_norgate_d1_trio_intraday_structure_gbt_preflight,
)


def test_runner_writes_only_source_safe_external_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _load_runner()
    result = run_norgate_d1_trio_intraday_structure_gbt_preflight(_panel())
    artifact_root = tmp_path / "external-artifacts"
    revision_receipt = tmp_path / "active-revision" / "receipt-run"
    market_data_root = tmp_path / "market-data"
    received: dict[str, Path] = {}

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("runner must not use the network")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("runner must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)
    monkeypatch.setattr(
        runner,
        "verify_norgate_active_build_revision_receipt",
        lambda _receipt, *, artifact_root, **_kwargs: (
            received.update({"revision_root": artifact_root}) or _matching_revision()
        ),
    )
    monkeypatch.setattr(
        runner,
        "load_verified_norgate_d1_diagnostic_panel",
        lambda *_args, market_data_root, **_kwargs: (
            received.update({"market_data_root": market_data_root})
            or SimpleNamespace(bars_by_symbol=_panel())
        ),
    )
    monkeypatch.setattr(
        runner,
        "run_norgate_d1_trio_intraday_structure_gbt_preflight",
        lambda *_args, **_kwargs: result,
    )

    arguments = [
        "--run-label",
        "unit-safe",
        "--artifact-root",
        str(artifact_root),
        "--revision-receipt",
        str(revision_receipt),
        "--market-data-root",
        str(market_data_root),
    ]
    runner.main(arguments)
    first = json.loads(capsys.readouterr().out)
    runner.main(arguments)
    second = json.loads(capsys.readouterr().out)
    assert first == second
    assert first["status"] == result.status
    assert first["validation_date_group_count"] == 139
    assert received == {
        "revision_root": revision_receipt.parent,
        "market_data_root": market_data_root,
    }
    assert first["metrics"]["actual_balanced_accuracy"] in {
        "at_or_above_effect_floor",
        "at_or_above_chance_below_effect_floor",
        "below_chance",
    }

    receipts = list(artifact_root.rglob("preflight-receipt.json"))
    assert len(receipts) == 1
    content = receipts[0].read_text(encoding="utf-8")
    assert "101.234" not in content
    assert "2024-01-01" not in content
    assert "D:\\market_data" not in content
    assert "C:\\Users" not in content
    assert "unit-secret-must-not-persist" not in content
    assert '"network_access":false' in content
    assert '"broker_access":false' in content
    assert '"pnl_evaluated":false' in content


def test_runner_rejects_repository_artifacts_and_nonmatching_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_runner()
    repository = tmp_path / "repo"
    repository.mkdir()
    artifact_root = repository / "model-artifacts"
    monkeypatch.setattr(runner, "_REPOSITORY_ROOT", repository)

    with pytest.raises(ValueError, match="outside Git"):
        runner.main(["--run-label", "inside", "--artifact-root", str(artifact_root)])

    external = tmp_path / "external"
    revision = _matching_revision()
    monkeypatch.setattr(
        runner,
        "verify_norgate_active_build_revision_receipt",
        lambda *_args, **_kwargs: SimpleNamespace(
            **{**revision.__dict__, "status": "revision_detected"}
        ),
    )
    with pytest.raises(ValueError, match="not eligible"):
        runner.main(["--run-label", "revision", "--artifact-root", str(external)])


def test_runner_rejects_mutated_result_before_receipt_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_runner()
    result = run_norgate_d1_trio_intraday_structure_gbt_preflight(_panel())
    object.__setattr__(result, "reason", "development_target_single_class")
    artifact_root = tmp_path / "external"
    monkeypatch.setattr(
        runner,
        "verify_norgate_active_build_revision_receipt",
        lambda *_args, **_kwargs: _matching_revision(),
    )
    monkeypatch.setattr(
        runner,
        "load_verified_norgate_d1_diagnostic_panel",
        lambda *_args, **_kwargs: SimpleNamespace(bars_by_symbol=_panel()),
    )
    monkeypatch.setattr(
        runner,
        "run_norgate_d1_trio_intraday_structure_gbt_preflight",
        lambda *_args, **_kwargs: result,
    )

    with pytest.raises(ValueError, match="result semantics"):
        runner.main(["--run-label", "mutated", "--artifact-root", str(artifact_root)])
    assert not list(artifact_root.rglob("preflight-receipt.json"))


def test_runner_static_surface_excludes_provider_and_execution_paths() -> None:
    source = _script_path().read_text(encoding="ascii").lower()
    for forbidden in (
        "kis_",
        "orderintent",
        "source: local_paper",
        "norgaterawdailybarprovider",
        "norgatedata",
        "torch",
        "dotenv",
        "os.environ",
    ):
        assert forbidden not in source
    assert "verify_norgate_active_build_revision_receipt" in source
    assert "load_verified_norgate_d1_diagnostic_panel" in source


def test_runner_selects_the_canonical_container_market_data_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_runner()
    monkeypatch.setattr(runner, "_REPOSITORY_ROOT", Path("/app"))
    assert runner._default_market_data_root() == Path("/app/market_data")


def _matching_revision() -> SimpleNamespace:
    return SimpleNamespace(
        status="matching",
        receipt_sha256="sha256:" + "a" * 64,
        reference_dataset_hash="sha256:efa1b14ff60c6a107688179617d428546de68ca1d1756c62292e1206e15c58e7",
        reference_manifest_hash="sha256:7f30253d035f248889849b7a9a5933cdc41b2f2525b405690ef653ca69a33d45",
    )


def _panel() -> dict[str, tuple]:
    from test_norgate_d1_trio_intraday_structure_gbt import _panel as make_panel

    return make_panel()


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("norgate_gbt_runner", _script_path())
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_norgate_d1_trio_intraday_structure_gbt.py"
    )
