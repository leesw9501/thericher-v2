from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest


@pytest.fixture
def runner(tmp_path, monkeypatch):
    script = Path(__file__).parents[1] / "scripts/run_timesfm_2p5_smoke.py"
    spec = importlib.util.spec_from_file_location("timesfm_smoke_runner_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    repo = tmp_path / "repo"
    for relative in (
        "scripts/run_timesfm_2p5_smoke.py",
        "src/thericher_v2/research/timesfm_local.py",
    ):
        source = repo / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# Synthetic source identity\n", encoding="ascii")
    monkeypatch.setattr(module, "REPO", repo)

    license_bytes = b"Apache License\nVersion 2.0\nSynthetic fixture only\n"
    wheel = io.BytesIO()
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("timesfm-2.0.2.dist-info/licenses/LICENSE", license_bytes)
    assets = {
        "README.md": b"---\nlicense: apache-2.0\n---\nSynthetic fixture only\n",
        "config.json": b'{"synthetic": true}\n',
        "model.safetensors": b"not-real-model-weights",
        module.WHEEL: wheel.getvalue(),
    }
    monkeypatch.setattr(
        module, "PINS", {name: hashlib.sha256(raw).hexdigest() for name, raw in assets.items()}
    )
    network = Mock(side_effect=AssertionError("network forbidden in synthetic tests"))
    monkeypatch.setattr(module.urllib.request, "urlopen", network)
    monkeypatch.setattr(
        module.shutil, "disk_usage", Mock(return_value=SimpleNamespace(total=100e9, free=90e9))
    )
    monkeypatch.setattr(module, "register_frozen_campaign", Mock())
    monkeypatch.setattr(module, "register_campaign_outcome", Mock())
    monkeypatch.setattr(module, "GpuFileLock", Mock(side_effect=AssertionError("GPU forbidden")))
    monkeypatch.setattr(module, "resolve_agent_root", Mock(side_effect=AssertionError("no agent")))
    monkeypatch.setattr(module.signal, "signal", Mock())

    torch = ModuleType("torch")
    torch.__version__ = "2.7.0+cu128"
    torch.set_num_threads = Mock()
    monkeypatch.setitem(sys.modules, "torch", torch)
    adapter = ModuleType("thericher_v2.research.timesfm_local")
    adapter.forecast_timesfm_2p5 = Mock(return_value=(np.zeros((4, 12)), np.zeros((4, 12, 10))))
    monkeypatch.setitem(sys.modules, adapter.__name__, adapter)
    versions = {
        "timesfm": "2.0.2", "torch": "2.7.0+cu128", "numpy": "synthetic",
        "safetensors": "synthetic", "huggingface-hub": "synthetic",
    }
    monkeypatch.setattr(
        module.importlib.metadata, "version", Mock(side_effect=versions.__getitem__)
    )

    root = tmp_path / "artifacts"
    model, output = module.paths(root)
    for name, raw in assets.items():
        (model / name).write_bytes(raw)
    return SimpleNamespace(
        module=module, root=root, model=model, output=output, assets=assets,
        network=network, forecast=adapter.forecast_timesfm_2p5, torch=torch,
        license_bytes=license_bytes,
    )


@pytest.fixture
def prepared(runner):
    runner.module.prepare(runner.root)
    runner.module.register_frozen_campaign.reset_mock()
    return runner


def test_prepare_rejects_workspace_artifact_root(runner):
    root = runner.module.REPO / "model-artifacts"
    with pytest.raises(ValueError, match="outside the Git workspace"):
        runner.module.prepare(root)
    assert not root.exists()
    runner.network.assert_not_called()
    runner.module.register_frozen_campaign.assert_not_called()


def test_prepare_reuses_verified_assets_and_identical_contract(runner):
    module = runner.module
    first = module.prepare(runner.root)
    raw = (runner.output / "contract.json").read_bytes()
    contract = json.loads(raw)
    assert first == {"status": "prepared", "contract_sha256": module.digest(raw)}
    assert contract["model_id"] == "google/timesfm-2.5-200m-pytorch"
    assert contract["model_revision"] == module.REVISION
    assert contract["files"] == module.PINS
    assert contract["runtime"] == {"timesfm": "2.0.2", "torch": "2.7.0+cu128"}
    assert contract["runtime_license_sha256"] == module.digest(runner.license_bytes)
    assert contract["holdout_access"] == "none"
    assert contract["paper_input"] is contract["training"] is False
    assert contract["accuracy_or_profitability_claim"] is False
    assert set(contract["code_sha256"]) == {
        "scripts/run_timesfm_2p5_smoke.py", "src/thericher_v2/research/timesfm_local.py"
    }
    module.register_frozen_campaign.assert_called_once_with(
        contract_hash=module.digest(raw),
        dataset_hash=module.digest(module.encode(contract["input"])),
        split_hash=module.digest(b"synthetic_no_split"),
        cost_model_hash=module.digest(b"no_market_score"), trial_family=module.NAME,
        holdout_access="none", artifact_root=runner.root, repo_root=module.REPO,
    )
    assert module.prepare(runner.root) == first
    assert (runner.output / "contract.json").read_bytes() == raw
    assert {path.name: path.read_bytes() for path in runner.model.iterdir()} == runner.assets
    runner.network.assert_not_called()
    runner.forecast.assert_not_called()


def test_prepare_rejects_preexisting_wrong_hash_without_replacing_asset(runner):
    target = runner.model / "model.safetensors"
    target.write_bytes(b"corrupted synthetic asset")
    with pytest.raises(ValueError, match="existing_asset_hash_mismatch"):
        runner.module.prepare(runner.root)
    assert target.read_bytes() == b"corrupted synthetic asset"
    assert not (runner.output / "contract.json").exists()
    runner.network.assert_not_called()
    runner.module.register_frozen_campaign.assert_not_called()


def test_prepare_downloads_only_missing_asset_from_pinned_revision(runner):
    target = runner.model / "config.json"
    target.unlink()
    runner.network.side_effect = lambda *_args, **_kwargs: io.BytesIO(runner.assets[target.name])
    assert runner.module.prepare(runner.root)["status"] == "prepared"
    runner.network.assert_called_once_with(
        f"https://huggingface.co/{runner.module.MODEL_ID}/resolve/"
        f"{runner.module.REVISION}/config.json", timeout=60,
    )
    assert target.read_bytes() == runner.assets[target.name]
    assert not target.with_name("config.json.partial").exists()


def test_prepare_rejects_download_hash_without_promoting_partial(runner):
    target = runner.model / "config.json"
    target.unlink()
    runner.network.side_effect = lambda *_args, **_kwargs: io.BytesIO(b"bad synthetic download")
    with pytest.raises(ValueError, match="download_hash_mismatch"):
        runner.module.prepare(runner.root)
    assert not target.exists()
    assert target.with_name("config.json.partial").read_bytes() == b"bad synthetic download"
    assert not (runner.output / "contract.json").exists()
    runner.module.register_frozen_campaign.assert_not_called()


def test_prepare_rejects_contract_conflict_after_source_change(prepared):
    runner = prepared
    contract = runner.output / "contract.json"
    before = contract.read_bytes()
    (runner.module.REPO / "scripts/run_timesfm_2p5_smoke.py").write_bytes(b"changed source")
    with pytest.raises(ValueError, match="contract_conflict"):
        runner.module.prepare(runner.root)
    assert contract.read_bytes() == before
    runner.network.assert_not_called()
    runner.module.register_frozen_campaign.assert_not_called()


def test_cpu_phase_is_offline_and_records_only_synthetic_summary(prepared):
    runner = prepared
    result = runner.module.run_phase(runner.root, "cpu")
    assert result["status"] == "complete"
    assert result["phase"] == "cpu"
    assert result["contract_sha256"] == runner.module.digest(
        (runner.output / "contract.json").read_bytes()
    )
    assert result["point_shape"] == [4, 12]
    assert result["quantile_shape"] == [4, 12, 10]
    assert result["market_data_accessed"] is result["predictions_retained"] is False
    assert result["training"] is result["paper_input"] is False
    assert json.loads((runner.output / "cpu.json").read_bytes()) == result
    runner.forecast.assert_called_once()
    args = runner.forecast.call_args.kwargs
    assert args["model_directory"] == runner.model
    assert args["expected_sha256"] == {
        name: runner.module.PINS[name] for name in ("config.json", "model.safetensors")
    }
    assert args["horizon"] == 12 and args["device"] == "cpu"
    assert [len(context) for context in args["contexts"]] == list(runner.module.LENGTHS)
    for n, context in zip(runner.module.LENGTHS, args["contexts"], strict=True):
        np.testing.assert_array_equal(context, np.sin(np.arange(n) / 7) + np.arange(n) / 100)
    runner.torch.set_num_threads.assert_called_once_with(2)
    runner.network.assert_not_called()
    runner.module.GpuFileLock.assert_not_called()
    runner.module.register_campaign_outcome.assert_not_called()


def test_run_phase_missing_asset_never_downloads(prepared):
    runner = prepared
    (runner.model / "model.safetensors").unlink()
    with pytest.raises(ValueError, match="artifact_not_regular"):
        runner.module.run_phase(runner.root, "cpu")
    assert not (runner.output / "cpu.json").exists()
    runner.network.assert_not_called()
    runner.forecast.assert_not_called()


def test_run_phase_rejects_contract_identity_change(prepared):
    runner = prepared
    path = runner.output / "contract.json"
    contract = json.loads(path.read_bytes())
    contract["name"] = "different-campaign"
    path.write_bytes(runner.module.encode(contract))
    with pytest.raises(ValueError, match="contract_identity"):
        runner.module.run_phase(runner.root, "cpu")
    runner.network.assert_not_called()
    runner.forecast.assert_not_called()
    assert not (runner.output / "cpu.json").exists()


def test_run_phase_rejects_changed_adapter_source(prepared):
    runner = prepared
    (runner.module.REPO / "src/thericher_v2/research/timesfm_local.py").write_bytes(b"changed")
    with pytest.raises(ValueError, match="code_changed"):
        runner.module.run_phase(runner.root, "cpu")
    runner.forecast.assert_not_called()
    runner.network.assert_not_called()
    assert not (runner.output / "cpu.json").exists()


@pytest.mark.parametrize("field", ["model_id", "model_revision"])
def test_run_phase_rejects_changed_model_identity(prepared, field):
    runner = prepared
    path = runner.output / "contract.json"
    contract = json.loads(path.read_bytes())
    contract[field] = "different-public-model"
    path.write_bytes(runner.module.encode(contract))
    with pytest.raises(ValueError, match="contract_identity"):
        runner.module.run_phase(runner.root, "cpu")
    runner.forecast.assert_not_called()
    runner.network.assert_not_called()


def test_run_phase_rejects_missing_source_hashes(prepared):
    runner = prepared
    path = runner.output / "contract.json"
    contract = json.loads(path.read_bytes())
    contract["code_sha256"] = {}
    path.write_bytes(runner.module.encode(contract))
    with pytest.raises(ValueError, match="code_changed|contract_identity"):
        runner.module.run_phase(runner.root, "cpu")
    runner.forecast.assert_not_called()
    assert not (runner.output / "cpu.json").exists()


@pytest.mark.parametrize("phase", ["prepare", "cpu", "cuda"])
def test_main_dispatches_exactly_one_phase(runner, monkeypatch, capsys, phase):
    prepare = Mock(return_value={"status": "prepared"})
    run = Mock(return_value={"status": "complete", "phase": phase})
    monkeypatch.setattr(runner.module, "prepare", prepare)
    monkeypatch.setattr(runner.module, "run_phase", run)
    args = ["--prepare"] if phase == "prepare" else ["--phase", phase]
    assert runner.module.main(["--artifact-root", str(runner.root), *args]) == 0
    if phase == "prepare":
        prepare.assert_called_once_with(runner.root)
        run.assert_not_called()
        assert json.loads(capsys.readouterr().out) == {"status": "prepared"}
    else:
        run.assert_called_once_with(runner.root, phase)
        prepare.assert_not_called()
        assert json.loads(capsys.readouterr().out) == {"status": "complete", "phase": phase}
    runner.network.assert_not_called()


@pytest.mark.parametrize(
    ("phase", "error"), [("prepare", RuntimeError), ("cpu", KeyboardInterrupt)]
)
def test_main_suppresses_raw_errors(runner, monkeypatch, capsys, phase, error):
    message = "synthetic-private-marker: never disclose this exception"
    target = "prepare" if phase == "prepare" else "run_phase"
    monkeypatch.setattr(runner.module, target, Mock(side_effect=error(message)))
    args = ["--prepare"] if phase == "prepare" else ["--phase", phase]
    assert runner.module.main(["--artifact-root", str(runner.root), *args]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"status": "unavailable", "raw_error_suppressed": True}
    assert captured.err == ""
    assert message not in captured.out
    runner.network.assert_not_called()
