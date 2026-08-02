from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_runner_uses_only_pinned_offline_spy_catalog_and_safe_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _load_runner()
    catalog = SimpleNamespace(
        dataset_id="kis.paper.private.intraday.spy.ams.m1.v1",
        dataset_hash="sha256:64f149f5ff1c9002107f001a44f78c54c8944e9c030d6153898b1229d9c742e6",
    )
    summary_path = tmp_path / "summary.json"
    summary_path.write_text('{"raw_market_data_written": false}\n', encoding="ascii")
    observed: dict[str, object] = {}

    def load_catalog(**kwargs: object) -> object:
        observed["load_kwargs"] = kwargs
        return catalog

    def run_campaign(
        received_catalog: object,
        *,
        artifact_root: Path,
        run_label: str,
        repo_root: Path,
    ) -> SimpleNamespace:
        observed["received_catalog"] = received_catalog
        observed["artifact_root"] = artifact_root
        observed["run_label"] = run_label
        observed["repo_root"] = repo_root
        return SimpleNamespace(summary_path=summary_path)

    monkeypatch.setattr(runner, "load_verified_kis_paper_private_intraday_catalog", load_catalog)
    monkeypatch.setattr(runner, "run_spy_intraday_mtf_logistic_10m", run_campaign)
    cache_root = tmp_path / "market-data"
    artifact_root = tmp_path / "model-artifacts"

    runner.main(
        [
            "--run-label",
            "unit-run",
            "--cache-root",
            str(cache_root),
            "--artifact-root",
            str(artifact_root),
        ]
    )

    assert observed["received_catalog"] is catalog
    assert observed["run_label"] == "unit-run"
    assert observed["artifact_root"] == artifact_root
    assert observed["load_kwargs"] == {
        "cache_root": cache_root,
        "repo_root": runner._REPOSITORY_ROOT,
        "symbol": "SPY",
        "exchange": "AMS",
    }
    assert capsys.readouterr().out == '{"raw_market_data_written": false}\n'


def test_runner_rejects_unpinned_catalog_before_campaign_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_runner()
    catalog = SimpleNamespace(dataset_id="different.dataset", dataset_hash="sha256:" + "0" * 64)
    monkeypatch.setattr(
        runner,
        "load_verified_kis_paper_private_intraday_catalog",
        lambda **_kwargs: catalog,
    )
    campaign_called = False

    def run_campaign(*_args: object, **_kwargs: object) -> None:
        nonlocal campaign_called
        campaign_called = True

    monkeypatch.setattr(runner, "run_spy_intraday_mtf_logistic_10m", run_campaign)

    with pytest.raises(ValueError, match="source identity"):
        runner.main(["--run-label", "unit-run", "--artifact-root", str(tmp_path)])
    assert campaign_called is False


def test_runner_has_no_credential_or_broker_surface() -> None:
    source = (
        (Path(__file__).resolve().parents[1] / "scripts" / "run_spy_intraday_mtf_logistic_10m.py")
        .read_text(encoding="ascii")
        .lower()
    )

    assert ".env" not in source
    assert "os.environ" not in source
    assert "order" not in source
    assert "broker" not in source
    assert "http" not in source


def _load_runner():
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "run_spy_intraday_mtf_logistic_10m.py"
    )
    specification = importlib.util.spec_from_file_location(
        "run_spy_intraday_mtf_logistic_10m_for_test",
        script_path,
    )
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module
