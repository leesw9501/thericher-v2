from __future__ import annotations

import importlib.util
import json
from datetime import timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from thericher_v2.data.norgate_trial_raw_d1 import NorgateTrialRawD1Error

_SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "materialize_norgate_local_d1_etf.py"
_EXPECTED_SYMBOLS = ("SPY", "QQQ", "IWM")


def test_materialized_receipt_is_source_safe_and_uses_fixed_etf_builder_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()
    captured = _install_successful_materialization(script, monkeypatch)
    repository = tmp_path / "repository"
    destination = tmp_path / "market-data" / "snapshot"
    receipt_root = tmp_path / "model-artifacts" / "receipts"
    monkeypatch.setattr(script, "_repository_root", lambda: repository)

    script.main(
        [
            "--run-label",
            "fixture",
            "--destination",
            str(destination),
            "--receipt-root",
            str(receipt_root),
        ]
    )

    receipt_path = receipt_root / "fixture.json"
    receipt_text = receipt_path.read_text(encoding="utf-8")
    payload = json.loads(receipt_text)
    printed = json.loads(capsys.readouterr().out)
    builder_kwargs = captured["builder_calls"][0]
    requested_start = builder_kwargs["requested_start"]
    requested_end = builder_kwargs["requested_end"]

    assert printed["receipt_hash"] == script._sha256(receipt_path.read_bytes())
    assert printed["result"] == payload
    assert payload["status"] == "qualified_for_offline_research"
    assert payload["reason"] == "valid_bounded_response"
    assert payload["source"]["symbol_set"] == list(_EXPECTED_SYMBOLS)
    assert payload["source"]["interval"] == "1d"
    assert payload["source"]["requested_adjustment_setting"] == "NONE"
    assert payload["source"]["paper_input_eligible"] is False
    assert payload["source"]["promotion_eligible"] is False
    assert payload["research_readiness"] == "source_local_daily_campaign_contract_required"
    assert builder_kwargs["destination"] == destination
    assert builder_kwargs["repo_root"] == repository
    assert builder_kwargs["norgate_package_version"] == "test-client-version"
    assert [query.symbol for query in captured["bar_queries"]] == list(_EXPECTED_SYMBOLS)
    assert all(query.market == "US" for query in captured["bar_queries"])
    assert all(query.timeframe is script.Timeframe.D1 for query in captured["bar_queries"])
    assert all(query.start_ts.date() == requested_start for query in captured["bar_queries"])
    assert all(
        query.end_ts.date() == requested_end + timedelta(days=1)
        for query in captured["bar_queries"]
    )
    assert captured["event_queries"] == [
        (symbol, requested_start, requested_end) for symbol in _EXPECTED_SYMBOLS
    ]
    assert {
        "raw_price",
        "raw_date",
        "raw_path",
        "actual_start",
        "actual_end",
        "snapshot_dir",
    }.isdisjoint(payload)
    for forbidden in (
        "private-price-value",
        "private-date-value",
        "private-path-value",
        str(destination),
        str(requested_start),
        str(requested_end),
    ):
        assert forbidden not in receipt_text


def test_same_materialization_receipt_is_idempotently_verified(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()
    captured = _install_successful_materialization(script, monkeypatch)
    repository = tmp_path / "repository"
    destination = tmp_path / "market-data" / "snapshot"
    receipt_root = tmp_path / "model-artifacts" / "receipts"
    monkeypatch.setattr(script, "_repository_root", lambda: repository)
    arguments = [
        "--run-label",
        "idempotent",
        "--destination",
        str(destination),
        "--receipt-root",
        str(receipt_root),
    ]

    script.main(arguments)
    first_output = json.loads(capsys.readouterr().out)
    receipt_path = receipt_root / "idempotent.json"
    first_bytes = receipt_path.read_bytes()

    script.main(arguments)
    second_output = json.loads(capsys.readouterr().out)

    assert receipt_path.read_bytes() == first_bytes
    assert second_output == first_output
    assert len(captured["builder_calls"]) == 2
    assert [call["destination"] for call in captured["builder_calls"]] == [destination, destination]


def test_git_receipt_root_is_rejected_before_materialization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script = _load_script()
    repository = tmp_path / "repository"
    receipt_root = repository / "receipts"
    materialization_calls = 0

    def materialize(**_kwargs: object) -> dict[str, object]:
        nonlocal materialization_calls
        materialization_calls += 1
        return {"status": "materialized"}

    monkeypatch.setattr(script, "_repository_root", lambda: repository)
    monkeypatch.setattr(script, "_materialize_payload", materialize)

    with pytest.raises(ValueError, match="receipts must stay outside Git"):
        script.main(
            [
                "--run-label",
                "git-root",
                "--destination",
                str(tmp_path / "market-data" / "snapshot"),
                "--receipt-root",
                str(receipt_root),
            ]
        )

    assert materialization_calls == 0
    assert not receipt_root.exists()


@pytest.mark.parametrize(
    ("error_name", "expected_status", "expected_reason", "run_label"),
    (
        ("NorgateClientUnavailableError", "input_unavailable", "source_client_missing", "client"),
        (
            "NorgateLocalUpdaterUnavailableError",
            "input_unavailable",
            "local_updater_unavailable",
            "updater",
        ),
        (
            "NorgateCapitalEventUnavailableError",
            "input_unavailable",
            "capital_event_evidence_unavailable",
            "events",
        ),
        ("NorgateMalformedResponseError", "unqualified", "malformed_daily_response", "malformed"),
    ),
)
def test_norgate_errors_write_categorical_receipts_without_error_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    error_name: str,
    expected_status: str,
    expected_reason: str,
    run_label: str,
) -> None:
    script = _load_script()
    repository = tmp_path / "repository"
    destination = tmp_path / "market-data" / "snapshot"
    receipt_root = tmp_path / "model-artifacts" / "receipts"
    error_type = getattr(script, error_name)
    private_error_text = f"private-error-detail:{destination}"

    def raise_unavailable(**_kwargs: object) -> object:
        raise error_type(private_error_text)

    monkeypatch.setattr(script, "_repository_root", lambda: repository)
    monkeypatch.setattr(script, "NorgateRawDailyBarProvider", _NoDataProvider)
    monkeypatch.setattr(script, "_client_version", lambda: "test-client-version")
    monkeypatch.setattr(script, "build_norgate_trial_raw_d1_snapshot", raise_unavailable)

    script.main(
        [
            "--run-label",
            run_label,
            "--destination",
            str(destination),
            "--receipt-root",
            str(receipt_root),
        ]
    )

    receipt_text = (receipt_root / f"{run_label}.json").read_text(encoding="utf-8")
    payload = json.loads(receipt_text)

    assert payload["status"] == expected_status
    assert payload["reason"] == expected_reason
    assert payload["raw_market_data_written"] is False
    assert private_error_text not in receipt_text
    assert private_error_text not in capsys.readouterr().out


def test_snapshot_contract_failure_is_not_reclassified_as_source_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script = _load_script()
    repository = tmp_path / "repository"
    receipt_root = tmp_path / "model-artifacts" / "receipts"

    def raise_snapshot_failure(**_kwargs: object) -> object:
        raise NorgateTrialRawD1Error("snapshot integrity failure")

    monkeypatch.setattr(script, "_repository_root", lambda: repository)
    monkeypatch.setattr(script, "NorgateRawDailyBarProvider", _NoDataProvider)
    monkeypatch.setattr(script, "_client_version", lambda: "test-client-version")
    monkeypatch.setattr(script, "build_norgate_trial_raw_d1_snapshot", raise_snapshot_failure)

    with pytest.raises(NorgateTrialRawD1Error, match="snapshot integrity"):
        script.main(
            [
                "--run-label",
                "integrity",
                "--destination",
                str(tmp_path / "market-data" / "snapshot"),
                "--receipt-root",
                str(receipt_root),
            ]
        )

    assert not (receipt_root / "integrity.json").exists()


def test_script_source_has_no_credential_or_execution_surface() -> None:
    source = _SCRIPT_PATH.read_text(encoding="utf-8").casefold()

    for forbidden in (".env", "os.environ", "kis", "broker", "order", "gpu"):
        assert forbidden not in source


class _NoDataProvider:
    def get_bars(self, _query: object) -> list[object]:
        pytest.fail("test must not query Norgate data")


def _install_successful_materialization(
    script: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    captured: dict[str, object] = {"bar_queries": [], "event_queries": [], "builder_calls": []}

    class FakeProvider:
        def get_bars(self, query: object) -> list[object]:
            captured["bar_queries"].append(query)
            return []

    def load_capital_events(symbol: str, start: object, end: object) -> object:
        captured["event_queries"].append((symbol, start, end))
        return object()

    def build_snapshot(**kwargs: object) -> SimpleNamespace:
        captured["builder_calls"].append(kwargs)
        requested_start = kwargs["requested_start"]
        requested_end = kwargs["requested_end"]
        for symbol in _EXPECTED_SYMBOLS:
            kwargs["norgate_bars"](symbol, requested_start, requested_end)
            kwargs["capital_event_evidence"](symbol, requested_start, requested_end)
        return SimpleNamespace(
            common_session_count=504,
            row_count=1512,
            dataset_hash="sha256:" + "a" * 64,
            manifest_hash="sha256:" + "b" * 64,
            event_marker_count=3,
            excluded_session_count=6,
            norgate_package_version="test-client-version",
            raw_price="private-price-value",
            raw_date="private-date-value",
            raw_path="private-path-value",
        )

    monkeypatch.setattr(script, "NorgateRawDailyBarProvider", FakeProvider)
    monkeypatch.setattr(script, "load_norgate_capital_event_evidence", load_capital_events)
    monkeypatch.setattr(script, "_client_version", lambda: "test-client-version")
    monkeypatch.setattr(script, "build_norgate_trial_raw_d1_snapshot", build_snapshot)
    return captured


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "materialize_norgate_local_d1_etf_for_test",
        _SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
