from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "probe_kis_paper_minute_capability.py"


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--explicit-older-key-once"],
        ["--fixed-historical-key-pair"],
    ],
)
def test_probe_script_requires_explicit_execution_without_loading_credentials(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
) -> None:
    script = _load_script()
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_config",
        lambda _: (_ for _ in ()).throw(AssertionError("credentials must stay unread")),
    )

    assert script.main(arguments) == 0

    assert json.loads(capsys.readouterr().out) == {
        "reason": "execute_flag_required",
        "status": "not_executed",
    }


def test_probe_script_rejects_a_faster_than_official_candidate_before_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = _load_script()
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_config",
        lambda _: (_ for _ in ()).throw(AssertionError("credentials must stay unread")),
    )

    with pytest.raises(SystemExit, match="2"):
        script.main(["--execute", "--minimum-request-interval-seconds", "0.5"])


def test_probe_script_rejects_observed_only_target_before_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = _load_script()
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_config",
        lambda _: (_ for _ in ()).throw(AssertionError("credentials must stay unread")),
    )

    with pytest.raises(SystemExit, match="2"):
        script.main(["--execute", "--target", "SPY/NAS"])


@pytest.mark.parametrize(
    "arguments",
    [
        ["--execute", "--target", "IWM/AMS", "--max-pages", "2"],
        ["--execute", "--target", "IWM/AMS", "--include-previous-day"],
    ],
)
def test_probe_script_rejects_candidate_scope_expansion_before_credentials(
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
) -> None:
    script = _load_script()
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_config",
        lambda _: (_ for _ in ()).throw(AssertionError("credentials must stay unread")),
    )

    with pytest.raises(SystemExit, match="2"):
        script.main(arguments)


@pytest.mark.parametrize("explicit_older_key", [False, True])
def test_probe_script_records_one_second_candidate_through_data_only_route(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    explicit_older_key: bool,
) -> None:
    script = _load_script()
    observed: dict[str, object] = {}

    class _RateGate:
        def __init__(self, **kwargs: object) -> None:
            observed["rate_gate"] = kwargs

    monkeypatch.setattr(script, "KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT", tmp_path / "market")
    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", _RateGate)
    monkeypatch.setattr(
        script,
        "KisPaperMarketDataTokenStartGate",
        lambda **kwargs: {"token_gate": kwargs},
    )
    monkeypatch.setattr(
        script,
        "UrllibKisPaperMarketDataTransport",
        lambda **kwargs: {"transport": kwargs},
    )
    monkeypatch.setattr(
        script,
        "KisPaperMarketDataClient",
        lambda **kwargs: {"client": kwargs},
    )
    monkeypatch.setattr(script, "load_kis_paper_market_data_config", lambda _: object())

    def probe_and_write(**kwargs: object) -> SimpleNamespace:
        observed["probe"] = kwargs
        return SimpleNamespace(
            outcome=SimpleNamespace(
                status="complete",
                safe_payload=lambda: {
                    "paper_only": True,
                    "raw_market_data_retained": False,
                    "route_class": "kis_paper_market_data",
                    "status": "complete",
                },
            ),
            evidence_path=tmp_path / "artifact.json",
        )

    monkeypatch.setattr(script, "probe_and_write_kis_paper_minute_capability", probe_and_write)

    scope_arguments = (
        ["--explicit-older-key-once", "--target", "QQQ/NAS", "--max-pages", "3"]
        if explicit_older_key
        else ["--include-previous-day", "--target", "SPY/AMS", "--max-pages", "1"]
    )
    assert (
        script.main(
            [
                "--execute",
                "--artifact-root",
                str(tmp_path / "artifacts"),
                *scope_arguments,
                "--minimum-request-interval-seconds",
                "1.0",
            ]
        )
        == 0
    )

    rate_gate = observed["rate_gate"]
    assert isinstance(rate_gate, dict)
    assert rate_gate["control_root"] == tmp_path / "collection-control-v1"
    assert rate_gate["minimum_request_interval_seconds"] == 1.0
    assert callable(rate_gate["on_request_started"])
    probe = observed["probe"]
    assert isinstance(probe, dict)
    assert probe["tested_request_interval_seconds"] == 1.0
    assert probe["max_pages"] == (2 if explicit_older_key else 1)
    assert probe["include_previous_day"] is (not explicit_older_key)
    assert probe["target"] == (("QQQ", "NAS") if explicit_older_key else ("SPY", "AMS"))
    assert probe["explicit_older_key_once"] is explicit_older_key
    client = probe["client"]
    assert isinstance(client, dict)
    assert client["client"]["max_minute_page_attempts"] == (2 if explicit_older_key else 1)
    assert json.loads(capsys.readouterr().out) == {
        "evidence_path": str(tmp_path / "artifact.json"),
        "paper_only": True,
        "raw_market_data_retained": False,
        "route_class": "kis_paper_market_data",
        "status": "complete",
    }
    source = SCRIPT.read_text(encoding="utf-8")
    assert "KIS_PAPER_ACCOUNT" not in source
    assert "KIS_LIVE_" not in source


@pytest.mark.parametrize(
    "arguments",
    [
        ["--target", "SPY/AMS"],
        ["--target", "IWM/AMS"],
        ["--include-previous-day"],
        ["--max-pages", "1"],
    ],
)
def test_explicit_older_key_scope_is_validated_before_credentials(monkeypatch, arguments):
    script = _load_script()

    def deny(*_args, **_kwargs):
        raise AssertionError("credentials, gates and transport must stay untouched")

    monkeypatch.setattr(script, "load_kis_paper_market_data_config", deny)
    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", deny)
    monkeypatch.setattr(script, "UrllibKisPaperMarketDataTransport", deny)
    with pytest.raises(SystemExit, match="2"):
        script.main(["--execute", "--explicit-older-key-once", *arguments])


@pytest.mark.parametrize(
    "arguments",
    [
        ["--explicit-older-key-once"],
        ["--include-previous-day"],
        ["--target", "SPY/AMS"],
        ["--target", "IWM/AMS"],
        ["--max-pages", "1"],
        ["--max-pages", "4"],
        ["--historical-key", "20260901120000"],
    ],
)
def test_fixed_key_cli_invalid_scope_fails_before_all_setup(monkeypatch, arguments):
    script = _load_script()

    def deny(*_args, **_kwargs):
        raise AssertionError("credentials, gates and transport must remain untouched")

    for name in (
        "load_kis_paper_market_data_config",
        "KisPaperMarketDataRateGate",
        "KisPaperMarketDataTokenStartGate",
        "UrllibKisPaperMarketDataTransport",
        "KisPaperMarketDataClient",
        "probe_and_write_kis_paper_minute_capability",
        "probe_and_write_kis_paper_minute_fixed_key_capability",
    ):
        monkeypatch.setattr(script, name, deny)
    with pytest.raises(SystemExit, match="2"):
        script.main(["--execute", "--fixed-historical-key-pair", *arguments])


def test_fixed_key_cli_validates_frozen_keys_before_credentials(monkeypatch):
    script = _load_script()
    events = []

    def invalid_plan():
        events.append("plan")
        raise ValueError("synthetic invalid fixed keys")

    def deny(*_args, **_kwargs):
        raise AssertionError("credentials must remain unread")

    monkeypatch.setattr(script, "validate_kis_paper_minute_fixed_key_probe", invalid_plan)
    monkeypatch.setattr(script, "load_kis_paper_market_data_config", deny)
    with pytest.raises(ValueError, match="invalid fixed keys"):
        script.main(["--execute", "--fixed-historical-key-pair"])
    assert events == ["plan"]


@pytest.mark.parametrize("page_arguments", [[], ["--max-pages", "2"], ["--max-pages", "3"]])
def test_fixed_key_cli_single_capped_client_metadata_hash_and_no_head_path(
    monkeypatch, tmp_path, capsys, page_arguments
):
    import thericher_v2.execution.kis_market_data as market_data
    from thericher_v2.data.kis_paper_minute_capability_probe import (
        KIS_PAPER_MINUTE_FIXED_HISTORICAL_KEYS,
    )

    script = _load_script()
    clients, requests, configurations = [], [], []

    def config(_path):
        configurations.append(_path)
        return market_data.KisPaperMarketDataConfig(
            app_key="synthetic-private-app-key", app_secret="synthetic-private-secret"
        )

    class Transport:
        def __init__(self, **_kwargs):
            pass

        def request(self, request):
            market_data._validate_request(request)
            requests.append(request)
            if request.method == "POST":
                return market_data.KisMarketDataResponse.from_payload(
                    {"access_token": "synthetic-private-token"}
                )
            key = request.query["KEYB"]
            return market_data.KisMarketDataResponse.from_payload(
                {
                    "rt_cd": "0",
                    "msg1": "synthetic-private-body",
                    "output1": {"more": "0"},
                    "output2": [
                        {
                            "xymd": key[:8],
                            "xhms": key[8:],
                            "kymd": key[:8],
                            "khms": key[8:],
                            "open": "12345.67",
                            "high": "12346.67",
                            "low": "12344.67",
                            "last": "12345.67",
                            "evol": "100",
                        }
                    ],
                },
            )

    def client(**kwargs):
        assert kwargs["max_minute_page_attempts"] == 2
        instance = market_data.KisPaperMarketDataClient(**kwargs)
        clients.append(instance)
        return instance

    def deny(*_args, **_kwargs):
        raise AssertionError("old head probe must not run")

    monkeypatch.setattr(script, "load_kis_paper_market_data_config", config)
    monkeypatch.setattr(script, "UrllibKisPaperMarketDataTransport", Transport)
    monkeypatch.setattr(script, "KisPaperMarketDataClient", client)
    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", lambda **_kwargs: object())
    monkeypatch.setattr(script, "KisPaperMarketDataTokenStartGate", lambda **_kwargs: object())
    monkeypatch.setattr(script, "probe_and_write_kis_paper_minute_capability", deny)
    assert (
        script.main(
            [
                "--execute",
                "--fixed-historical-key-pair",
                "--artifact-root",
                str(tmp_path / "artifacts"),
                *page_arguments,
            ],
            clock=lambda: datetime(2026, 10, 3, tzinfo=UTC),
        )
        == 0
    )
    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert output.err == "" and len(clients) == len(configurations) == 1
    assert [request.query["KEYB"] for request in requests if request.method == "GET"] == list(
        KIS_PAPER_MINUTE_FIXED_HISTORICAL_KEYS
    )
    assert len(requests) == 3 and payload["minute_page_request_count"] == 2
    assert payload["token_request_count"] == 1 and payload["raw_market_data_retained"] is False
    encoded = Path(payload["evidence_path"]).read_bytes()
    assert payload["evidence_sha256"] == "sha256:" + hashlib.sha256(encoded).hexdigest()
    assert all(
        value not in output.out + encoded.decode("ascii")
        for value in (
            "12345.67",
            "synthetic-private-app-key",
            "synthetic-private-secret",
            "synthetic-private-token",
            "synthetic-private-body",
        )
    )
    assert [page["category"] for page in payload["pages"]] == ["requested_date_observed"] * 2


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "probe_kis_paper_minute_capability_for_test",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
