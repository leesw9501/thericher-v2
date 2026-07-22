from __future__ import annotations

import importlib.util
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace


def test_campaign_script_writes_a_sanitized_external_manifest(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    session_dates = tuple(date(2026, 1, day) for day in range(1, 21))
    artifact_root = tmp_path / "model-artifacts"
    source = object()
    catalog = SimpleNamespace(
        dataset_id="kis.paper.private.intraday.qqq.nas.m1.unit-v1",
        dataset_hash="sha256:" + "a" * 64,
    )
    campaign = SimpleNamespace(
        campaign_id="kis-intraday-cpu-naive-20-session-v1-unit-attempt",
        contract_hash="sha256:" + "b" * 64,
        naive_baselines=("flat", "always_long", "previous_bar_direction"),
    )
    plan = SimpleNamespace(
        campaign=campaign,
        cataloged_bars=catalog,
        session_dates=session_dates,
        development_session_dates=session_dates[:10],
        purge_session_date=session_dates[10],
        validation_session_dates=session_dates[11:],
    )
    validation = SimpleNamespace(
        bars_seen=3900,
        decisions_seen=2990,
        trades=(),
        event_count=2990,
        gross_pnl=Decimal("0"),
        after_cost_pnl=Decimal("0"),
        total_fees=Decimal("0"),
        total_slippage=Decimal("0"),
    )
    baseline = SimpleNamespace(
        baseline_id="flat",
        result=validation,
        fill_source="local_paper",
        artifact_path=artifact_root / "validation" / "unit.json",
        replay_evidence=SimpleNamespace(
            fill_source="local_paper",
            event_jsonl_sha256="sha256:" + "c" * 64,
            state_sqlite_sha256="sha256:" + "d" * 64,
        ),
    )
    campaign_result = SimpleNamespace(
        plan=plan,
        baseline_runs=(SimpleNamespace(phase="development", baseline=baseline),),
    )

    def load_catalog(**kwargs: object) -> object:
        assert kwargs == {
            "cache_root": tmp_path / "market-data",
            "repo_root": script._REPO_ROOT,
            "symbol": "QQQ",
            "exchange": "NAS",
        }
        return source

    def build_plan(
        loaded: object,
        *,
        session_dates: tuple[date, ...],
        campaign_id: str,
    ) -> object:
        assert loaded is source
        assert session_dates == plan.session_dates
        assert campaign_id == campaign.campaign_id
        return plan

    def run_campaign(
        received_plan: object,
        *,
        artifact_root: Path,
        work_root: Path,
        repo_root: Path,
        run_label: str,
    ) -> object:
        assert received_plan is plan
        assert artifact_root == tmp_path / "model-artifacts"
        assert work_root == artifact_root / "kis-intraday-cpu-campaign" / "unit-attempt" / "work"
        assert repo_root == script._REPO_ROOT
        assert run_label == "unit-attempt"
        return campaign_result

    monkeypatch.setattr(script, "load_verified_kis_paper_private_intraday_catalog", load_catalog)
    monkeypatch.setattr(script, "build_kis_intraday_cpu_campaign_plan", build_plan)
    monkeypatch.setattr(script, "run_kis_intraday_cpu_naive_baselines", run_campaign)

    args = ["--symbol", "QQQ", "--run-label", "unit-attempt"]
    for session_date in session_dates:
        args.extend(("--session-date", session_date.isoformat()))
    args.extend(("--cache-root", str(tmp_path / "market-data")))
    args.extend(("--artifact-root", str(artifact_root)))
    script.main(args)

    output = json.loads(capsys.readouterr().out)
    summary_path = artifact_root / "kis-intraday-cpu-campaign" / "unit-attempt" / "summary.json"
    assert output == json.loads(summary_path.read_text(encoding="utf-8"))
    assert output["mode"] == "offline_local_paper"
    assert output["all_fills_local_paper"] is True
    assert output["catalog"] == {
        "dataset_id": catalog.dataset_id,
        "dataset_hash": catalog.dataset_hash,
    }
    assert output["split"]["purge_session_date"] == "2026-01-11"
    assert output["baselines"] == [
        {
            "after_cost_pnl": "0",
            "all_fills_local_paper": True,
            "baseline_id": "flat",
            "bars_seen": 3900,
            "decisions_seen": 2990,
            "event_count": 2990,
            "event_jsonl_sha256": "sha256:" + "c" * 64,
            "fill_source": "local_paper",
            "gross_pnl": "0",
            "phase": "development",
            "state_sqlite_sha256": "sha256:" + "d" * 64,
            "total_fees": "0",
            "total_slippage": "0",
            "trade_count": 0,
            "validation_artifact_path": str(baseline.artifact_path),
        }
    ]
    rendered = json.dumps(output)
    assert "price" not in rendered
    assert "credential" not in rendered
    assert "source_path" not in rendered


def _load_script() -> ModuleType:
    script_path = Path(__file__).parents[1] / "scripts" / "run_kis_intraday_cpu_campaign.py"
    spec = importlib.util.spec_from_file_location(
        "run_kis_intraday_cpu_campaign_for_test",
        script_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
