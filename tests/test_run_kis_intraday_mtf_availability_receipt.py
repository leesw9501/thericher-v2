import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "run_kis_intraday_mtf_availability_receipt.py"
)


def test_task_owned_flag_omits_only_the_legacy_fixed_source_pin(
    monkeypatch,
    capsys,
) -> None:
    module = _load_module()
    expected_hashes: list[object] = []

    def fake_run(**kwargs: object) -> SimpleNamespace:
        expected_hashes.append(kwargs["expected_dataset_hashes"])
        return _result()

    monkeypatch.setattr(module, "run_kis_intraday_mtf_availability_receipt", fake_run)

    assert module.main(["--allow-current-source-identities", "--run-label", "task-owned-unit"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert expected_hashes == [None]
    assert payload["status"] == "qualified_for_prospective_input"
    assert payload["receipt_id"] == "kis-intraday-mtf-availability-receipt-v1"
    assert payload["receipt_sha256"] == "sha256:" + "d" * 64


def test_default_retains_the_legacy_fixed_source_pin(monkeypatch, capsys) -> None:
    module = _load_module()
    expected_hashes: list[object] = []

    def fake_run(**kwargs: object) -> SimpleNamespace:
        expected_hashes.append(kwargs["expected_dataset_hashes"])
        return _result()

    monkeypatch.setattr(module, "run_kis_intraday_mtf_availability_receipt", fake_run)

    assert module.main(["--run-label", "legacy-unit"]) == 0

    capsys.readouterr()
    assert expected_hashes == [module._EXPECTED_DATASET_HASHES]


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("availability_receipt_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _result() -> SimpleNamespace:
    return SimpleNamespace(
        contract=SimpleNamespace(contract_sha256="sha256:" + "a" * 64),
        receipt=SimpleNamespace(
            receipt_sha256="sha256:" + "d" * 64,
            status="qualified_for_prospective_input",
            reason=None,
        ),
        precommit_sha256="sha256:" + "b" * 64,
        summary_sha256="sha256:" + "c" * 64,
    )
