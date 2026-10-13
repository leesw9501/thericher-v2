from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from thericher_v2.data import kis_paper_etf_daily_context as data
from thericher_v2.execution import kis_market_data as native


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch):
    path = Path(__file__).resolve().parents[1] / "scripts/collect_kis_paper_etf_daily_context.py"
    spec = importlib.util.spec_from_file_location("etf_daily_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in (
        "load_kis_paper_market_data_config",
        "load_kis_paper_market_data_environment_config",
        "collect_daily_contexts",
        "read_daily_context",
    ):
        monkeypatch.setattr(module, name, Mock(name=name))
    return module


def test_default_inert_no_config_client_cache_read(script, capsys) -> None:
    assert script.main([]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "not_executed"
    for name in (
        "load_kis_paper_market_data_config",
        "load_kis_paper_market_data_environment_config",
        "collect_daily_contexts",
        "read_daily_context",
    ):
        getattr(script, name).assert_not_called()


def test_execute_requires_explicit_configuration(script, capsys) -> None:
    assert script.main(["--execute"]) == 20
    assert json.loads(capsys.readouterr().out)["reason"] == "config_missing"
    script.collect_daily_contexts.assert_not_called()
    script.load_kis_paper_market_data_environment_config.assert_not_called()


@pytest.mark.parametrize("floor", [60, 300])
@pytest.mark.parametrize("config", ["env", "dotenv"])
def test_selective_config_and_runtime_wiring(script, capsys, floor, config) -> None:
    result = data.DailyCollectionResult("complete", None, (), 1, 12, None, (1.25,))
    script.collect_daily_contexts.return_value = result
    options = ["--paper-from-env"] if config == "env" else ["--paper-dotenv", "explicit-paper"]
    assert script.main(["--execute", *options, "--token-interval-seconds", str(floor)]) == 0
    assert json.loads(capsys.readouterr().out)["daily_gets"] == 12
    if config == "env":
        script.load_kis_paper_market_data_environment_config.assert_called_once_with()
        script.load_kis_paper_market_data_config.assert_not_called()
        configured = script.load_kis_paper_market_data_environment_config.return_value
    else:
        script.load_kis_paper_market_data_config.assert_called_once_with(
            Path("explicit-paper"), environment={"THERICHER_MODE": "off"}
        )
        script.load_kis_paper_market_data_environment_config.assert_not_called()
        configured = script.load_kis_paper_market_data_config.return_value
    script.collect_daily_contexts.assert_called_once_with(
        configured,
        cache_root=data.CACHE_ROOT,
        artifact_root=data.ARTIFACT_ROOT,
        control_root=data.CONTROL_ROOT,
        token_interval_seconds=floor,
    )


def test_replay_is_read_only_no_authentication(script, capsys) -> None:
    script.read_daily_context.return_value.safe_payload.return_value = dict(row_count=253)
    pin = "sha256:" + "a" * 64
    assert script.main(["--receipt", "exact-receipt", "--receipt-sha256", pin]) == 0
    assert json.loads(capsys.readouterr().out) == dict(row_count=253)
    script.read_daily_context.assert_called_once_with(
        Path("exact-receipt"), pin, cache_root=data.CACHE_ROOT, required_count=253
    )
    script.collect_daily_contexts.assert_not_called()
    script.load_kis_paper_market_data_environment_config.assert_not_called()


def test_replay_cannot_enable_acquisition(script, capsys) -> None:
    assert script.main(["--receipt", "exact", "--execute", "--paper-from-env"]) == 20
    assert json.loads(capsys.readouterr().out)["reason"] == "invalid_contract"
    script.collect_daily_contexts.assert_not_called()
    script.read_daily_context.assert_not_called()


def test_unknown_error_redacted(script, capsys) -> None:
    script.collect_daily_contexts.side_effect = RuntimeError("secret/raw body/order/private amount")
    assert script.main(["--execute", "--paper-from-env"]) == 20
    text = capsys.readouterr().out
    assert json.loads(text) == dict(status="unavailable", reason="input_unavailable")
    assert "secret" not in text and "raw body" not in text


def test_partial_yields_only_worker_not_global_hold(script, capsys) -> None:
    script.collect_daily_contexts.return_value = data.DailyCollectionResult(
        "incomplete", "token_request_not_due", (), 0, 0, None, ()
    )
    assert script.main(["--execute", "--paper-from-env"]) == 20
    assert json.loads(capsys.readouterr().out)["reason"] == "token_request_not_due"


def test_stdin_selective_config_uses_native_loader_without_environment_blend(
    script, monkeypatch, capsys
) -> None:
    loader = Mock(wraps=native.load_kis_paper_market_data_environment_config)
    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", loader)
    supplied = dict(KIS_PAPER_APP_KEY="synthetic-stdin-key", KIS_PAPER_APP_SECRET="stdin-secret")
    stream = io.BytesIO(json.dumps(supplied).encode())
    script.collect_daily_contexts.return_value = data.DailyCollectionResult(
        "complete", None, (), 1, 12, None, ()
    )
    assert script.main(["--execute", "--paper-config-stdin"], stdin=stream) == 0
    configured = script.collect_daily_contexts.call_args.args[0]
    assert type(configured) is native.KisPaperMarketDataConfig
    assert configured.app_key == supplied["KIS_PAPER_APP_KEY"]
    assert configured.app_secret == supplied["KIS_PAPER_APP_SECRET"]
    loader.assert_called_once_with(environment=supplied)
    script.load_kis_paper_market_data_config.assert_not_called()
    output = capsys.readouterr()
    assert supplied["KIS_PAPER_APP_KEY"] not in output.out + output.err
    assert supplied["KIS_PAPER_APP_SECRET"] not in output.out + output.err


@pytest.mark.parametrize(
    "argv",
    [
        ["--paper-config-stdin"],
        ["--receipt", "exact", "--paper-config-stdin"],
    ],
)
def test_inert_or_replay_denied_never_reads_stdin(script, argv, capsys) -> None:
    stream = Mock()
    expected = 20 if "--receipt" in argv else 0
    assert script.main(argv, stdin=stream) == expected
    stream.read.assert_not_called()
    script.collect_daily_contexts.assert_not_called()
    script.read_daily_context.assert_not_called()
    script.load_kis_paper_market_data_environment_config.assert_not_called()
    capsys.readouterr()


@pytest.mark.parametrize(
    "payload",
    [
        b'{"KIS_PAPER_APP_KEY":"first","KIS_PAPER_APP_KEY":"duplicate","KIS_PAPER_APP_SECRET":"s"}',
        b'{"KIS_PAPER_APP_KEY":"k","KIS_PAPER_APP_SECRET":"s","extra":"forbidden"}',
        b'{"KIS_PAPER_APP_KEY":"k"}',
        b"[]",
        b"{} {}",
        b"null",
        b"\xff",
        b'{"KIS_PAPER_APP_KEY":NaN,"KIS_PAPER_APP_SECRET":"s"}',
        b'{"KIS_PAPER_APP_KEY":true,"KIS_PAPER_APP_SECRET":"s"}',
        b'{"KIS_PAPER_APP_KEY":" ","KIS_PAPER_APP_SECRET":"s"}',
        b'{"KIS_PAPER_APP_KEY":{"KIS_PAPER_APP_SECRET":"nested"},"KIS_PAPER_APP_SECRET":"s"}',
        b'{"KIS_PAPER_APP_KEY":"k","KIS_PAPER_APP_SECRET":null}',
    ],
)
def test_invalid_stdin_fail_closed_redacted(script, monkeypatch, capsys, payload) -> None:
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_environment_config",
        native.load_kis_paper_market_data_environment_config,
    )
    assert script.main(["--execute", "--paper-config-stdin"], stdin=io.BytesIO(payload)) == 20
    assert json.loads(capsys.readouterr().out) == dict(
        status="unavailable", reason="config_missing"
    )
    script.collect_daily_contexts.assert_not_called()


def test_stdin_bytes_are_bounded_single_read(script, capsys) -> None:
    stream = Mock()
    stream.read.return_value = b"x" * (script._STDIN_CONFIG_MAX_BYTES + 1)
    assert script.main(["--execute", "--paper-config-stdin"], stdin=stream) == 20
    stream.read.assert_called_once_with(script._STDIN_CONFIG_MAX_BYTES + 1)
    assert json.loads(capsys.readouterr().out)["reason"] == "config_missing"
    script.load_kis_paper_market_data_environment_config.assert_not_called()
    script.collect_daily_contexts.assert_not_called()


def test_stdin_and_environment_selection_mutually_exclusive(script, capsys) -> None:
    stream = Mock()
    with pytest.raises(SystemExit) as error:
        script.main(["--execute", "--paper-config-stdin", "--paper-from-env"], stdin=stream)
    assert error.value.code == 2
    stream.read.assert_not_called()
    script.collect_daily_contexts.assert_not_called()
    capsys.readouterr()
