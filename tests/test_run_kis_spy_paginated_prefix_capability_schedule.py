from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parents[1]
_RUNNER = _ROOT / "scripts" / "run_kis_spy_paginated_prefix_capability_schedule.ps1"
_INSTALLER = _ROOT / "scripts" / "install_kis_paper_schedules.ps1"
_COMPOSE = _ROOT / "docker-compose.yml"
_COLLECTOR = _ROOT / "scripts" / "collect_kis_paper_spy_paginated_prefix_capability.py"


def test_runner_uses_two_nonwaiting_et_gated_stages_without_head_route_reuse() -> None:
    source = _RUNNER.read_text(encoding="ascii")
    lowered = source.lower()

    assert '[ValidateSet("negative-control", "feasibility")]' in source
    assert 'FindSystemTimeZoneById("Eastern Standard Time")' in source
    assert "Test-PrefixStageWindow" in source
    assert "no_network_noop" in source
    assert "positive-preflight" in source
    assert "kis-spy-paginated-prefix-collector" in source
    assert "kis-spy-paginated-prefix-observer" in source
    assert "Start-Sleep" not in source
    assert "intraday-head" not in lowered
    assert "prospective-spy-cycle" not in lowered
    assert "KIS_PAPER_APP_KEY" not in source
    assert "KIS_LIVE" not in source
    assert ".env" not in source
    assert "--observed-at" not in source
    assert "$collectionStartedAt" not in source


def test_kst_trigger_pairs_map_to_exactly_one_eligible_eastern_season() -> None:
    cases = (
        (date(2026, 1, 6), "15:29:30", "05:29:30", "05:30:00"),
        (date(2026, 8, 4), "15:29:30", "04:29:30", "04:30:00"),
    )
    triggers = ("04:29:30", "05:29:30", "04:30:00", "05:30:00")

    for kst_date, expected_negative, expected_negative_kst, expected_positive_kst in cases:
        converted = {
            trigger: datetime.combine(kst_date, time.fromisoformat(trigger))
            .replace(tzinfo=ZoneInfo("Asia/Seoul"))
            .astimezone(ZoneInfo("America/New_York"))
            for trigger in triggers
        }
        negative_eligible = [
            trigger
            for trigger, eastern in converted.items()
            if eastern.strftime("%H:%M:%S") == expected_negative
        ]
        positive_eligible = [
            trigger
            for trigger, eastern in converted.items()
            if eastern.strftime("%H:%M:%S") == "15:30:00"
        ]

        assert negative_eligible == [expected_negative_kst]
        assert positive_eligible == [expected_positive_kst]
        assert all(
            eastern.date() == kst_date - timedelta(days=1) and eastern.weekday() < 5
            for eastern in converted.values()
        )


def test_compose_keeps_collector_credentials_and_observer_isolation_separate() -> None:
    compose = _COMPOSE.read_text(encoding="ascii")
    collector = compose.split("\n  kis-spy-paginated-prefix-collector:\n", maxsplit=1)[1].split(
        "\n  kis-spy-paginated-prefix-observer:\n", maxsplit=1
    )[0]
    observer = compose.split("\n  kis-spy-paginated-prefix-observer:\n", maxsplit=1)[1].split(
        "\n  kis-paper-intraday-head:\n", maxsplit=1
    )[0]

    assert 'profiles: ["kis-spy-paginated-prefix-capability"]' in collector
    assert "KIS_PAPER_APP_KEY" in collector
    assert "KIS_PAPER_APP_SECRET" in collector
    assert "KIS_PAPER_ACCOUNT" not in collector
    assert "KIS_LIVE" not in collector
    assert "/app/market_data" in collector
    assert "/app/collection_control" in collector
    assert 'profiles: ["kis-spy-paginated-prefix-capability"]' in observer
    assert "network_mode: none" in observer
    assert "read_only: true" in observer
    assert "- /tmp" in observer
    assert "/app/market_data:ro" in observer
    assert "/app/model_artifacts" in observer
    assert "KIS_PAPER_APP_" not in observer
    assert "KIS_PAPER_ACCOUNT" not in observer
    assert "KIS_LIVE" not in observer
    assert "/app/private" not in observer
    assert "/app/runtime" not in observer
    assert "local-paper" not in observer


def test_collector_has_one_bounded_market_data_client_and_no_account_or_live_surface() -> None:
    source = _COLLECTOR.read_text(encoding="ascii")

    assert source.count("KisPaperMarketDataClient(") == 1
    assert "max_minute_page_attempts=KIS_SPY_PAGINATED_PREFIX_MAX_PAGES" in source
    assert "KisPaperMinuteQuery(" in source
    assert "run_id_for_session" in source
    assert "KIS_PAPER_ACCOUNT" not in source
    assert "KIS_LIVE" not in source


def test_installer_adds_two_new_kst_tasks_without_changing_head_schedule() -> None:
    source = _INSTALLER.read_text(encoding="ascii")
    head = source.split('Name = "thericher-kis-paper-intraday-head"', maxsplit=1)[1].split(
        "    },", maxsplit=1
    )[0]
    negative = source.split('Name = "thericher-kis-paper-spy-prefix-negative-control"', maxsplit=1)[
        1
    ].split("    },", maxsplit=1)[0]
    feasibility = source.split('Name = "thericher-kis-paper-spy-prefix-feasibility"', maxsplit=1)[
        1
    ].split("    },", maxsplit=1)[0]

    assert 'At = @("00:31", "02:31", "04:31", "06:20")' in head
    assert 'Runner = "run_kis_paper_intraday_head_schedule.ps1"' in head
    assert 'Profile = "kis-spy-paginated-prefix-capability"' in negative
    assert 'Service = "kis-spy-paginated-prefix-observer"' in negative
    assert 'Runner = "run_kis_spy_paginated_prefix_capability_schedule.ps1"' in negative
    assert 'RunnerArguments = "-Stage `"negative-control`""' in negative
    assert 'At = @("04:29:30", "05:29:30")' in negative
    assert "RecoverMissedRun = $false" in negative
    assert "ExecutionLimitMinutes = 10" in negative
    assert 'Service = "kis-spy-paginated-prefix-collector"' in feasibility
    assert 'RunnerArguments = "-Stage `"feasibility`""' in feasibility
    assert 'At = @("04:30:00", "05:30:00")' in feasibility
    assert "RecoverMissedRun = $false" in feasibility
    assert '$schedule.ContainsKey("RunnerArguments")' in source
    assert "Assert-KoreaStandardTime" in source
