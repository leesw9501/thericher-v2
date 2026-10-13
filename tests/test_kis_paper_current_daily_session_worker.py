import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.execution import kis_paper_canary as canary
from thericher_v2.execution.kis_readonly import KisHttpRequest

PATH = Path(__file__).resolve().parents[1] / "scripts/run_kis_paper_current_daily_session_worker.py"
SPEC = importlib.util.spec_from_file_location("current_daily_worker", PATH)
w = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(w)


def packet():
    return dict(
        KIS_PAPER_APP_KEY="synthetic-key",
        KIS_PAPER_APP_SECRET="synthetic-secret",
        KIS_PAPER_ACCOUNT_NO="12345678",
        KIS_PAPER_ACCOUNT_PRODUCT_CODE="01",
        THERICHER_MODE="kis_paper",
    )


def test_inert_default_never_reads_packet_or_runs(monkeypatch, capsys):
    monkeypatch.setattr(w.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"not-read")))
    monkeypatch.setattr(w, "run", lambda _: (_ for _ in ()).throw(AssertionError()))
    assert w.main([]) == 0
    assert json.loads(capsys.readouterr().out)["credential_reads"] == 0
    assert w.sys.stdin.buffer.tell() == 0


def test_only_fixed_virtual_config_from_exact_paper_fields():
    config = w.parse_packet(json.dumps(packet()).encode())
    assert config.base_url == "https://openapivts.koreainvestment.com:29443"


@pytest.mark.parametrize("fault", ["mode", "live", "duplicate", "size", "host", "missing"])
def test_unsafe_config_never_reaches_worker(monkeypatch, capsys, fault):
    body = packet()
    if fault == "mode":
        body["THERICHER_MODE"] = "kis_live"
    elif fault == "live":
        body["KIS_LIVE_APP_KEY"] = "must-not-read-or-route"
    elif fault == "host":
        body["base_url"] = "untrusted-host"
    elif fault == "missing":
        body.pop("KIS_PAPER_ACCOUNT_NO")
    encoded = json.dumps(body).encode()
    if fault == "duplicate":
        encoded = b'{"KIS_PAPER_APP_KEY":"one","KIS_PAPER_APP_KEY":"two"}'
    elif fault == "size":
        encoded = b" " * 8193
    monkeypatch.setattr(w.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(encoded)))
    monkeypatch.setattr(w, "run", lambda _: (_ for _ in ()).throw(AssertionError()))
    assert w.main(["--execute"]) == 20
    text = capsys.readouterr().out
    assert json.loads(text)["status"] == "unavailable"
    assert "synthetic-secret" not in text and "must-not-read" not in text


def test_native_live_request_denied_before_gate_or_network(tmp_path):
    transport = w.OwnedTransport(control_root=tmp_path / "control")
    with pytest.raises(canary.KisPaperCanaryError):
        transport._request(
            KisHttpRequest("POST", "https://openapi.koreainvestment.com:9443/oauth2/tokenP", {})
        )
    assert sum(transport.calls.values()) == 0
    assert not (tmp_path / "control").exists()


def test_restart_recovery_loader_is_not_implicitly_called(monkeypatch):
    from thericher_v2.execution import kis_paper_current_daily_session as session

    transport = SimpleNamespace(
        calls=dict(token_posts=0, get_requests=0, buy_posts=0, sell_posts=0, cancel_posts=0)
    )
    monkeypatch.setattr(w, "OwnedTransport", lambda **kwargs: transport)
    monkeypatch.setattr(
        w,
        "collect_daily_contexts",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("current Data must not block recovery")
        ),
    )

    def native(**kwargs):
        assert kwargs["execute"] is True and callable(kwargs["data_loader"])
        return session.CurrentDailySessionOutcome("complete", "exact_cycle_complete")

    monkeypatch.setattr(session, "run_kis_paper_current_daily_session", native)
    value = w.run(w.parse_packet(json.dumps(packet()).encode()))
    assert value["status"] == "complete" and value["market_daily_gets"] == 0
    assert sum(value["calls"].values()) == 0


def test_owned_same_token_is_borrowed_for_market_and_portfolio(monkeypatch):
    from thericher_v2.execution import kis_paper_current_daily_session as session

    transport = SimpleNamespace(
        calls=dict(token_posts=1, get_requests=0, buy_posts=0, sell_posts=0, cancel_posts=0)
    )
    monkeypatch.setattr(w, "OwnedTransport", lambda **kwargs: transport)
    monkeypatch.setattr(
        canary.KisPaperCanaryClient, "_issue_access_token", lambda _: "synthetic-bearer"
    )

    def collect(cfg, **kwargs):
        assert kwargs["access_token"] == "synthetic-bearer"
        assert kwargs["token_interval_seconds"] == 60
        return SimpleNamespace(
            status="complete", receipts=(), daily_gets=12, reason=None, next_due_utc=None
        )

    monkeypatch.setattr(w, "collect_daily_contexts", collect)

    def reader(**kwargs):
        assert kwargs["access_token"] == "synthetic-bearer"
        return SimpleNamespace(portfolio_preview_snapshot=lambda **k: "private-read")

    monkeypatch.setattr(w.readonly, "KisPaperReadOnlyClient", reader)

    def native(**kwargs):
        assert kwargs["data_loader"]() == {}
        assert kwargs["reads_factory"]() == "private-read"
        return session.CurrentDailySessionOutcome("no_intent", "current_input_unavailable")

    monkeypatch.setattr(session, "run_kis_paper_current_daily_session", native)
    value = w.run(w.parse_packet(json.dumps(packet()).encode()))
    assert value["calls"]["token_posts"] == 1 and value["market_daily_gets"] == 12
    assert "synthetic-bearer" not in json.dumps(value)
