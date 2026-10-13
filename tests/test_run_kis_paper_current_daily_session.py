import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts/run_kis_paper_current_daily_session.py"
SPEC = importlib.util.spec_from_file_location("daily_portfolio_host", PATH)
w = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(w)


def payload():
    return dict(
        kind="kis_paper_current_daily_session_v1",
        status="no_intent",
        reason="current_input_unavailable",
        limitation="cycle_status_not_current_inventory_or_net_pnl",
        paper_only=True,
        visits=[],
        calls=dict(token_posts=0, get_requests=0, buy_posts=0, sell_posts=0, cancel_posts=0),
        market_daily_gets=0,
        collection_reason=None,
        next_due_utc=None,
        observed_at_utc="2026-10-13T20:00:00+00:00",
        fees="not_observed",
        settled_cash="not_observed",
        net_pnl="not_observed",
    )


def test_default_no_docker_no_source_no_credentials(monkeypatch):
    for name in ("source_map", "load_kis_paper_config"):
        monkeypatch.setattr(w, name, lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(
        w.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError())
    )
    assert w.run(image="", execute=False)["status"] == "inert"


def test_command_preserves_exact_existing_book_and_rw_read_locks():
    args = w.command("sha256:" + "a" * 64, "b" * 32)
    mounts = [args[i + 1] for i, v in enumerate(args) if v == "--mount"]
    for volume, target in zip(w.VOLUMES, ("private", "runtime", "emergency"), strict=True):
        assert f"type=volume,source={volume},target=/app/{target},volume-nocopy" in mounts
    assert not any(".env" in value or "KIS_" in value for value in args)
    assert "--read-only" in args and "--log-driver" in args
    with pytest.raises(ValueError):
        w.command("untrusted:latest", "b" * 32)


@pytest.mark.parametrize(
    "fault", ["secret", "kind", "limitation", "cash", "boolean", "visits", "counter"]
)
def test_closed_nested_output_schema(fault):
    value = payload()
    if fault == "secret":
        value["access_token"] = "never-print"
    elif fault == "kind":
        value["kind"] = "raw-secret"
    elif fault == "limitation":
        value["limitation"] = "raw-private-value"
    elif fault == "cash":
        value["settled_cash"] = "private-amount"
    elif fault == "boolean":
        value["calls"]["get_requests"] = True
    elif fault == "visits":
        value["visits"] = [dict(token="secret")]
    else:
        value["calls"]["buy_posts"] = 4
    with pytest.raises(ValueError):
        w.validate_result(value)


def test_source_mismatch_no_credential_read(monkeypatch):
    monkeypatch.setattr(w, "cleanup", lambda *a: True)
    monkeypatch.setattr(w, "source_map", lambda: dict(source="expected"))
    monkeypatch.setattr(
        w.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=b'{"source":"wrong"}'),
    )
    monkeypatch.setattr(
        w, "load_kis_paper_config", lambda *a, **k: (_ for _ in ()).throw(AssertionError())
    )
    with pytest.raises(ValueError, match="worker_image_source_mismatch"):
        w.run(image="sha256:" + "a" * 64, execute=True)


def test_only_stdin_private_packet_no_argv_env_output(monkeypatch):
    monkeypatch.setattr(w, "source_map", lambda: dict(source="expected"))
    monkeypatch.setattr(
        w,
        "load_kis_paper_config",
        lambda *a, **k: SimpleNamespace(
            app_key="synthetic-key",
            app_secret="synthetic-secret",
            account_number="12345678",
            account_product_code="01",
        ),
    )
    seen = []

    def call(args, **kwargs):
        seen.append(args)
        assert not any(k.startswith("KIS_") for k in kwargs["env"])
        assert "synthetic-secret" not in str(args) and "12345678" not in str(args)
        if args[1] == "run" and "--network" in args:
            return SimpleNamespace(returncode=0, stdout=b'{"source":"expected"}')
        if args[1] == "run":
            packet = json.loads(kwargs["input"])
            assert set(packet) == {
                "KIS_PAPER_APP_KEY",
                "KIS_PAPER_APP_SECRET",
                "KIS_PAPER_ACCOUNT_NO",
                "KIS_PAPER_ACCOUNT_PRODUCT_CODE",
                "THERICHER_MODE",
            }
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload()).encode())
        return SimpleNamespace(returncode=0, stdout=b"")

    monkeypatch.setattr(w.subprocess, "run", call)
    value = w.run(image="sha256:" + "a" * 64, execute=True)
    assert value["status"] == "no_intent" and value["exact_container_absent"]
    assert "synthetic-secret" not in json.dumps(value) and "12345678" not in json.dumps(value)
    assert len(seen) == 7


def test_source_probe_timeout_reaps_exact_owner_before_credentials(monkeypatch):
    monkeypatch.setattr(w, "source_map", lambda: dict(source="expected"))
    removed = []
    monkeypatch.setattr(w, "cleanup", lambda *args: removed.append(args) or True)
    monkeypatch.setattr(
        w, "load_kis_paper_config", lambda *a, **k: (_ for _ in ()).throw(AssertionError())
    )

    def timeout(args, **kwargs):
        assert "--network" in args and "--name" in args and "--label" in args
        raise w.subprocess.TimeoutExpired(args, 15)

    monkeypatch.setattr(w.subprocess, "run", timeout)
    with pytest.raises(w.subprocess.TimeoutExpired):
        w.run(image="sha256:" + "a" * 64, execute=True)
    assert len(removed) == 1 and removed[0][0] == "thericher-daily-source-" + removed[0][1]


@pytest.mark.parametrize("fault", ["exit", "cleanup"])
def test_post_dispatch_fault_retains_safe_report_and_unknown_effects(monkeypatch, fault):
    monkeypatch.setattr(w, "source_map", lambda: dict(source="expected"))
    monkeypatch.setattr(
        w,
        "load_kis_paper_config",
        lambda *a, **k: SimpleNamespace(
            app_key="synthetic",
            app_secret="synthetic",
            account_number="12345678",
            account_product_code="01",
        ),
    )
    cleanup_results = iter([True, fault != "cleanup"])
    monkeypatch.setattr(w, "cleanup", lambda *a: next(cleanup_results))

    def call(args, **kwargs):
        if args[1] == "run" and "--network" in args:
            return SimpleNamespace(returncode=0, stdout=b'{"source":"expected"}')
        if args[1] == "run":
            return SimpleNamespace(
                returncode=137 if fault == "exit" else 0, stdout=json.dumps(payload()).encode()
            )
        return SimpleNamespace(returncode=0, stdout=b"")

    monkeypatch.setattr(w.subprocess, "run", call)
    result = w.run(image="sha256:" + "a" * 64, execute=True)
    assert result["status"] == "unavailable" and result["unknown_effects_not_assumed_zero"]
    assert result["worker_report"]["status"] == "no_intent"
    assert result["reason"] != "launcher_preflight_failed"


def test_cleanup_removes_immutable_id_not_replacement_name(monkeypatch):
    actor, replacement, identity = "a" * 64, "b" * 64, "c" * 32
    results = iter([actor, replacement])
    seen = []

    def call(args, **kwargs):
        seen.append(args)
        if args[1] == "container":
            return SimpleNamespace(returncode=0, stdout=next(results).encode())
        if args[1] == "inspect":
            assert args[-1] == actor
            return SimpleNamespace(returncode=0, stdout=identity.encode())
        assert args == ["docker", "rm", "--force", actor]
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(w.subprocess, "run", call)
    assert w.cleanup("replacement-prone-name", identity, {}) is False
    assert len(seen) == 4


def test_cleanup_timeout_is_unknown_not_exception(monkeypatch):
    def timeout(args, **kwargs):
        raise w.subprocess.TimeoutExpired(args, 5)

    monkeypatch.setattr(w.subprocess, "run", timeout)
    assert w.cleanup("synthetic", "a" * 32, {}) is False


def test_partial_failure_never_means_no_submission():
    value = w.validate_result(
        dict(
            status="unavailable",
            reason="worker_recovery_required",
            paper_only=True,
            unknown_effects_not_assumed_zero=True,
        )
    )
    assert "calls" not in value
