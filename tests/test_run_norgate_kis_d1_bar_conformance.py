from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

_CAMPAIGN_ID = "norgate-kis-d1-bar-conformance-v1"
_DATA_MODULE = "thericher_v2.data.norgate_kis_d1_bar_conformance"


def test_runner_pins_sources_and_prints_only_aggregate_safe_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _load_runner(monkeypatch)
    snapshot = tmp_path / "private-snapshot"
    cache_root = tmp_path / "private-cache"
    artifact_root = tmp_path / "model-artifacts"
    observed: dict[str, object] = {}

    def build_receipt(**kwargs: object) -> _Receipt:
        observed.update(kwargs)
        return _write_receipt(
            artifact_root,
            status="conforming_with_limits",
            aggregate={"required_relationship_count": 8, "nonconforming_count": 0},
        )

    monkeypatch.setattr(runner, "build_norgate_kis_d1_bar_conformance_receipt", build_receipt)
    runner.main(
        [
            "--snapshot",
            str(snapshot),
            "--kis-daily-catalog-root",
            str(cache_root),
            "--artifact-root",
            str(artifact_root),
        ]
    )

    summary = json.loads(capsys.readouterr().out)
    assert observed == {
        "snapshot_dir": snapshot,
        "cache_root": cache_root,
        "artifact_root": artifact_root.resolve(),
        "expected_norgate_dataset_hash": runner._EXPECTED_NORGATE_DATASET_HASH,
        "expected_norgate_manifest_hash": runner._EXPECTED_NORGATE_MANIFEST_HASH,
        "repo_root": runner._REPOSITORY_ROOT,
    }
    assert summary == {
        "campaign_id": _CAMPAIGN_ID,
        "receipt_sha256": _receipt_hash("conforming_with_limits"),
        "status": "conforming_with_limits",
        "outcome": {
            "status": "conforming_with_limits",
            "aggregate": {"required_relationship_count": 8, "nonconforming_count": 0},
        },
    }
    rendered = json.dumps(summary, ensure_ascii=True, sort_keys=True)
    assert str(snapshot) not in rendered
    assert str(cache_root) not in rendered
    assert str(artifact_root) not in rendered
    assert "2026-08-02" not in rendered
    assert "901.23" not in rendered


def test_runner_reattests_an_identical_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _load_runner(monkeypatch)
    artifact_root = tmp_path / "model-artifacts"
    calls = 0

    def build_receipt(**_kwargs: object) -> _Receipt:
        nonlocal calls
        calls += 1
        return _write_receipt(
            artifact_root,
            status="nonconforming",
            aggregate={"required_relationship_count": 8, "nonconforming_count": 1},
        )

    monkeypatch.setattr(runner, "build_norgate_kis_d1_bar_conformance_receipt", build_receipt)
    arguments = [
        "--snapshot",
        str(tmp_path / "private-snapshot"),
            "--kis-daily-catalog-root",
        str(tmp_path / "private-cache"),
        "--artifact-root",
        str(artifact_root),
    ]

    runner.main(arguments)
    first_output = capsys.readouterr().out
    first_receipt = _receipt_path(artifact_root).read_bytes()
    runner.main(arguments)

    assert calls == 2
    assert capsys.readouterr().out == first_output
    assert _receipt_path(artifact_root).read_bytes() == first_receipt


def test_runner_rejects_git_artifact_root_before_data_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_runner(monkeypatch)
    called = False

    def must_not_run(**_kwargs: object) -> _Receipt:
        nonlocal called
        called = True
        raise AssertionError("Data builder must not run")

    monkeypatch.setattr(runner, "build_norgate_kis_d1_bar_conformance_receipt", must_not_run)
    with pytest.raises(ValueError, match="outside Git"):
        runner.main(
            [
                "--snapshot",
                "D:/market_data/private-snapshot",
                "--kis-daily-catalog-root",
                "D:/market_data/private-cache",
                "--artifact-root",
                str(runner._REPOSITORY_ROOT / "artifacts"),
            ]
        )
    assert called is False


def test_runner_rejects_untyped_or_external_receipts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_runner(monkeypatch)
    artifact_root = tmp_path / "model-artifacts"
    receipt = _write_receipt(
        tmp_path / "outside-artifacts",
        status="input_unavailable",
        aggregate={"required_relationship_count": 0, "nonconforming_count": 0},
    )
    monkeypatch.setattr(
        runner,
        "build_norgate_kis_d1_bar_conformance_receipt",
        lambda **_kwargs: receipt,
    )

    with pytest.raises(ValueError, match="location is invalid"):
        runner.main(
            [
                "--snapshot",
                str(tmp_path / "private-snapshot"),
                "--kis-daily-catalog-root",
                str(tmp_path / "private-cache"),
                "--artifact-root",
                str(artifact_root),
            ]
        )


def test_runner_rejects_source_path_disclosure_from_safe_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_runner(monkeypatch)
    snapshot = tmp_path / "private-snapshot"
    artifact_root = tmp_path / "model-artifacts"
    receipt = _write_receipt(
        artifact_root,
        status="input_unavailable",
        aggregate={"required_relationship_count": 0, "nonconforming_count": 0},
    )
    unsafe = SimpleNamespace(
        status=receipt.status,
        receipt_path=receipt.receipt_path,
        receipt_sha256=receipt.receipt_sha256,
        safe_payload=lambda: {"status": receipt.status, "accidental_path": str(snapshot)},
    )
    monkeypatch.setattr(
        runner,
        "build_norgate_kis_d1_bar_conformance_receipt",
        lambda **_kwargs: unsafe,
    )

    with pytest.raises(ValueError, match="discloses a path"):
        runner.main(
            [
                "--snapshot",
                str(snapshot),
                "--kis-daily-catalog-root",
                str(tmp_path / "private-catalog"),
                "--artifact-root",
                str(artifact_root),
            ]
        )


def test_runner_has_no_external_or_execution_client_surface() -> None:
    source = _script_path().read_text(encoding="ascii").lower()
    for forbidden in (
        ".env",
        "environ",
        "requests",
        "urllib",
        "socket",
        "broker",
        "account",
        "local_paper",
        "gpu",
        "training",
        "live",
        "norgatedata",
    ):
        assert forbidden not in source
    assert source.count("from thericher_v2.data.norgate_kis_d1_bar_conformance import") == 1
    assert "kis_paper_daily_history_panel" not in source


@dataclass(frozen=True)
class _Receipt:
    status: str
    receipt_path: Path
    receipt_sha256: str
    aggregate: dict[str, int]

    def safe_payload(self) -> dict[str, object]:
        return {"status": self.status, "aggregate": self.aggregate}


def _write_receipt(artifact_root: Path, *, status: str, aggregate: dict[str, int]) -> _Receipt:
    path = _receipt_path(artifact_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(
        {"status": status, "aggregate": aggregate},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    if path.exists():
        assert path.read_bytes() == content
    else:
        path.write_bytes(content)
    return _Receipt(
        status=status,
        receipt_path=path,
        receipt_sha256=_receipt_hash(status),
        aggregate=aggregate,
    )


def _receipt_hash(status: str) -> str:
    return "sha256:" + hashlib.sha256(status.encode("ascii")).hexdigest()


def _receipt_path(artifact_root: Path) -> Path:
    return artifact_root / "receipt" / "conformance.json"


def _script_path() -> Path:
    return Path(__file__).resolve().parents[1] / "scripts" / "run_norgate_kis_d1_bar_conformance.py"


def _load_runner(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    data_module = ModuleType(_DATA_MODULE)
    data_module.NORGATE_KIS_D1_BAR_CONFORMANCE_ID = _CAMPAIGN_ID
    data_module.build_norgate_kis_d1_bar_conformance_receipt = lambda **_kwargs: None
    monkeypatch.setitem(sys.modules, _DATA_MODULE, data_module)
    specification = importlib.util.spec_from_file_location(
        "run_norgate_kis_d1_bar_conformance_for_test",
        _script_path(),
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module
