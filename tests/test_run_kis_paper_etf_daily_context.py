import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts/run_kis_paper_etf_daily_context.py"
SPEC = importlib.util.spec_from_file_location("etf_context_host", PATH)
w = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(w)


def valid():
    return dict(
        status="complete",
        reason=None,
        token_posts=1,
        daily_gets=12,
        next_due_utc=None,
        receipts=[
            dict(
                path="/app/model_artifacts/data/etf-daily-context-v1/"
                + "a" * 32
                + "/SPY/receipt.json",
                sha256="sha256:" + "b" * 64,
            )
        ],
        http_start_gaps_seconds=[1.25],
        pacing_basis="final_opener_delegate_boundary_not_socket_wire_measurement",
    )


def test_default_inert_no_source_config_or_docker(monkeypatch):
    monkeypatch.setattr(w, "source_map", lambda: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(
        w.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError())
    )
    monkeypatch.setattr(
        w,
        "load_kis_paper_market_data_config",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError()),
    )
    assert w.run(image="", execute=False) == dict(
        status="inert", credential_reads=0, broker_calls=0
    )


def test_exact_image_and_required_external_binds_without_credential_env():
    args = w.docker_command("sha256:" + "a" * 64, "b" * 32)
    assert "--paper-config-stdin" in args and "--env-file" not in args
    assert not any("KIS_" in item or ".env" in item for item in args)
    assert "--read-only" in args and args[args.index("--log-driver") + 1] == "none"
    assert any("/app/market_data" in item for item in args)
    assert any("/app/model_artifacts" in item for item in args)
    with pytest.raises(ValueError, match="exact_local_image"):
        w.docker_command("untrusted:latest", "b" * 32)


def test_no_kis_names_routed_in_docker_environment(monkeypatch):
    monkeypatch.setenv("KIS_LIVE_APP_SECRET", "must-not-read-or-route")
    monkeypatch.setenv("KIS_PAPER_APP_SECRET", "must-not-route")
    result = w.os_environment()
    assert not any(name.startswith("KIS_") for name in result)


def test_closed_projection_and_exact_pointer_mapping():
    result = w.validate_result(valid())
    assert Path(result["receipts"][0]["path"]).is_relative_to(w.ARTIFACT)
    assert set(result) == set(valid())


def test_categorical_cli_failure_preserved_without_inventing_counts():
    result = w.validate_result(dict(status="unavailable", reason="config_missing"))
    assert result == dict(status="unavailable", reason="config_missing")
    assert "daily_gets" not in result and "token_posts" not in result
    with pytest.raises(ValueError):
        w.validate_result(dict(status="unavailable", reason="raw-secret-unknown-message"))


@pytest.mark.parametrize(
    "fault", ["secret", "boolean_counter", "escape", "invalid_hash", "nonfinite"]
)
def test_unsafe_or_mismatched_worker_output_rejected(fault):
    value = valid()
    if fault == "secret":
        value["access_token"] = "not-printed"
    elif fault == "boolean_counter":
        value["token_posts"] = True
    elif fault == "escape":
        value["receipts"][0]["path"] = (
            "/app/model_artifacts/data/etf-daily-context-v1/../../private"
        )
    elif fault == "invalid_hash":
        value["receipts"][0]["sha256"] = "wrong"
    else:
        value["http_start_gaps_seconds"] = [float("nan")]
    with pytest.raises(ValueError):
        w.validate_result(value)


def test_source_mismatch_precedes_any_credential_read(monkeypatch):
    monkeypatch.setattr(w, "cleanup", lambda *a: True)
    monkeypatch.setattr(w, "source_map", lambda: {"synthetic": "expected"})
    monkeypatch.setattr(
        w.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=b'{"synthetic":"wrong"}'),
    )
    monkeypatch.setattr(
        w,
        "load_kis_paper_market_data_config",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("credentials must not be read")),
    )
    with pytest.raises(ValueError, match="image_source_mismatch"):
        w.run(image="sha256:" + "a" * 64, execute=True)


@pytest.mark.parametrize("unsafe", [False, True])
def test_private_packet_not_in_argv_env_or_result_and_actor_absent(monkeypatch, unsafe):
    monkeypatch.setattr(w, "source_map", lambda: {"synthetic": "expected"})
    monkeypatch.setattr(
        w,
        "load_kis_paper_market_data_config",
        lambda *a, **k: SimpleNamespace(
            app_key="synthetic-private-key", app_secret="synthetic-private-secret"
        ),
    )
    calls = []

    def execute(args, **kwargs):
        calls.append((args, kwargs))
        assert "synthetic-private-key" not in str(args)
        assert "synthetic-private-secret" not in str(args)
        assert not any(name.startswith("KIS_") for name in kwargs["env"])
        if args[1] == "run" and "--network" in args:
            return SimpleNamespace(returncode=0, stdout=b'{"synthetic":"expected"}')
        if args[1] == "run":
            assert json.loads(kwargs["input"]) == dict(
                KIS_PAPER_APP_KEY="synthetic-private-key",
                KIS_PAPER_APP_SECRET="synthetic-private-secret",
            )
            body = {**valid(), "access_token": "synthetic-private-secret"} if unsafe else valid()
            return SimpleNamespace(returncode=0, stdout=json.dumps(body).encode())
        return SimpleNamespace(returncode=0, stdout=b"")

    monkeypatch.setattr(w.subprocess, "run", execute)
    value = w.run(image="sha256:" + "a" * 64, execute=True)
    assert value["status"] == ("unknown" if unsafe else "complete")
    assert value["exact_container_absent"] is True
    assert "synthetic-private" not in json.dumps(value)
    assert len(calls) == 4


def test_source_probe_timeout_reaps_exact_owner_before_credentials(monkeypatch):
    monkeypatch.setattr(w, "source_map", lambda: {"synthetic": "expected"})
    removed = []
    monkeypatch.setattr(w, "cleanup", lambda *args: removed.append(args) or True)
    monkeypatch.setattr(
        w,
        "load_kis_paper_market_data_config",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError()),
    )

    def timeout(args, **kwargs):
        assert "--network" in args and "--name" in args and "--label" in args
        raise w.subprocess.TimeoutExpired(args, 10)

    monkeypatch.setattr(w.subprocess, "run", timeout)
    with pytest.raises(w.subprocess.TimeoutExpired):
        w.run(image="sha256:" + "a" * 64, execute=True)
    assert len(removed) == 1 and removed[0][0] == "thericher-etf-source-" + removed[0][1]


@pytest.mark.parametrize("fault", ["exit", "cleanup"])
def test_dispatch_fault_retains_safe_report_without_success(monkeypatch, fault):
    monkeypatch.setattr(w, "source_map", lambda: {"synthetic": "expected"})
    monkeypatch.setattr(
        w,
        "load_kis_paper_market_data_config",
        lambda *a, **k: SimpleNamespace(app_key="synthetic", app_secret="synthetic"),
    )
    cleanup_results = iter([True, fault != "cleanup"])
    monkeypatch.setattr(w, "cleanup", lambda *a: next(cleanup_results))

    def call(args, **kwargs):
        if "--network" in args:
            return SimpleNamespace(returncode=0, stdout=b'{"synthetic":"expected"}')
        return SimpleNamespace(
            returncode=137 if fault == "exit" else 0, stdout=json.dumps(valid()).encode()
        )

    monkeypatch.setattr(w.subprocess, "run", call)
    result = w.run(image="sha256:" + "a" * 64, execute=True)
    assert result["status"] == "unknown" and result["worker_report"]["status"] == "complete"


def test_cleanup_removes_immutable_id_not_replacement_name(monkeypatch):
    actor, replacement, identity = "a" * 64, "b" * 64, "c" * 32
    results = iter([actor, replacement])

    def call(args, **kwargs):
        if args[1] == "container":
            return SimpleNamespace(returncode=0, stdout=next(results).encode())
        if args[1] == "inspect":
            assert args[-1] == actor
            return SimpleNamespace(returncode=0, stdout=identity.encode())
        assert args == ["docker", "rm", "--force", actor]
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(w.subprocess, "run", call)
    assert w.cleanup("replacement-prone-name", identity, {}) is False


def test_cleanup_timeout_is_unknown_not_exception(monkeypatch):
    def timeout(args, **kwargs):
        raise w.subprocess.TimeoutExpired(args, 5)

    monkeypatch.setattr(w.subprocess, "run", timeout)
    assert w.cleanup("synthetic", "a" * 32, {}) is False
