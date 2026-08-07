from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from zoneinfo import ZoneInfo

from thericher_v2.data.kis_paper_iwm_m1_current_head import (
    collect_and_write_kis_paper_iwm_m1_current_head,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMinutePage,
    KisPaperMinuteQuery,
    KisPaperMinuteRawBar,
)

SCRIPT = Path(__file__).parents[1] / "scripts" / "replay_kis_paper_iwm_m1_current_head.py"


def test_script_replays_local_snapshot_without_credentials_or_paths(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    roots = _seed_snapshot(tmp_path)
    script = _load_script()
    monkeypatch.setattr(script, "_REPOSITORY_ROOT", roots["repository_root"])

    assert (
        script.main(
            [
                "--cache-root",
                str(roots["cache_root"]),
                "--market-data-root",
                str(roots["market_data_root"]),
                "--artifact-root",
                str(roots["artifact_root"]),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    serialized = json.dumps(payload, sort_keys=True)
    assert payload["status"] == "replayed"
    assert payload["broker_or_network_used"] is False
    assert payload["completed_bucket_counts"]["1m"] == 10
    assert str(roots["cache_root"]) not in serialized
    assert "123.45" not in serialized
    assert not (roots["repository_root"] / ".env").exists()


def test_script_rejects_an_in_repository_artifact_root(tmp_path: Path, capsys) -> None:
    roots = _seed_snapshot(tmp_path)
    script = _load_script()
    script._REPOSITORY_ROOT = roots["repository_root"]

    assert (
        script.main(
            [
                "--cache-root",
                str(roots["cache_root"]),
                "--market-data-root",
                str(roots["market_data_root"]),
                "--artifact-root",
                str(roots["repository_root"] / "artifacts"),
            ]
        )
        == 2
    )

    assert json.loads(capsys.readouterr().out) == {
        "broker_or_network_used": False,
        "paper_only": True,
        "route_class": "offline_local_cache",
        "status": "unavailable",
    }


def _seed_snapshot(tmp_path: Path) -> dict[str, Path]:
    repository_root = tmp_path / "repo"
    market_data_root = tmp_path / "market-data"
    cache_root = market_data_root / "iwm-current-head"
    artifact_root = tmp_path / "artifacts"
    repository_root.mkdir()
    start = datetime(2026, 7, 24, 0, 0, tzinfo=UTC)
    page = KisPaperMinutePage(
        query=KisPaperMinuteQuery(exchange="AMS", symbol="IWM"),
        bars=tuple(_raw_bar(start + timedelta(minutes=index)) for index in range(10)),
        next_cursor=None,
        more="",
    )
    collect_and_write_kis_paper_iwm_m1_current_head(
        client=_MinuteClient(page),
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository_root,
        market_data_root=market_data_root,
        observed_at=start + timedelta(hours=1),
    )
    return {
        "repository_root": repository_root,
        "market_data_root": market_data_root,
        "cache_root": cache_root,
        "artifact_root": artifact_root,
    }


def _raw_bar(timestamp: datetime) -> KisPaperMinuteRawBar:
    korea_timestamp = timestamp.astimezone(ZoneInfo("Asia/Seoul"))
    return KisPaperMinuteRawBar(
        exchange_date=timestamp.strftime("%Y%m%d"),
        exchange_time=timestamp.strftime("%H%M%S"),
        korea_date=korea_timestamp.strftime("%Y%m%d"),
        korea_time=korea_timestamp.strftime("%H%M%S"),
        open=Decimal("123.45"),
        high=Decimal("123.50"),
        low=Decimal("123.40"),
        last=Decimal("123.46"),
        volume=Decimal("100"),
    )


class _MinuteClient:
    def __init__(self, page: KisPaperMinutePage) -> None:
        self._page = page

    def fetch_minute_page(
        self,
        query: KisPaperMinuteQuery,
        **_kwargs: object,
    ) -> KisPaperMinutePage:
        assert query == KisPaperMinuteQuery(exchange="AMS", symbol="IWM")
        return self._page


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "replay_kis_paper_iwm_m1_current_head_for_test",
        SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("script module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
