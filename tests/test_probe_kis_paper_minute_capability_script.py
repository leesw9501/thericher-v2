from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "probe_kis_paper_minute_capability.py"


@pytest.mark.parametrize("arguments", [[], ["--explicit-older-key-once"]])
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


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "probe_kis_paper_minute_capability_for_test",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
