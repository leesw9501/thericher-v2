from __future__ import annotations

import importlib.util
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_kis_paper_snapshot_bridge.py"
SPEC = importlib.util.spec_from_file_location("snapshot_bridge_launcher", SCRIPT)
assert SPEC and SPEC.loader
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)
INVOCATION = "6b991b8c-98ef-46de-ab4e-cbfa7fe1d00e"


def payload(status="complete"):
    observed = datetime(2026, 10, 13, 15, tzinfo=UTC)
    stamp = observed.strftime("%Y%m%dT%H%M%S%fZ")
    return {
        "status": status,
        "reason_code": "config_missing" if status == "unavailable" else None,
        "observed_at": observed.isoformat(),
        "scope": "read_only",
        "account_snapshot_complete": status == "complete",
        "observer_invocation_id": INVOCATION,
        "evidence_path": (
            f"/app/model_artifacts/execution/kis-paper-console-bridge/{stamp}-{status}.json"
        ),
        "observer_evidence_path": (
            f"/app/model_artifacts/execution/kis-paper-snapshot-observer/"
            f"{stamp}-{INVOCATION}-{status}.json"
        ),
    }


@pytest.fixture
def launch_fake(monkeypatch, tmp_path):
    config = SimpleNamespace(
        app_key="synthetic-key",
        app_secret="synthetic-secret",
        account_number="synthetic-account",
        account_product_code="synthetic-product",
    )
    calls = []
    loaded = []
    monkeypatch.setattr(
        launcher.ro,
        "load_kis_paper_config",
        lambda path: loaded.append(path) or config,
    )

    def launch(value=None, code=0, environment=None, runner=None):
        def run(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(
                command,
                code,
                stdout=json.dumps(
                    (value or payload())
                    | {"runtime_source_sha256": launcher.kis_paper_bridge_source_digest()}
                ).encode(),
                stderr=b"PRIVATE_RAW_ERROR",
            )

        monkeypatch.setattr(launcher.subprocess, "run", runner or run)
        result = launcher.launch(
            tmp_path,
            tmp_path / ".env",
            INVOCATION,
            environment={} if environment is None else environment,
        )
        return result, calls, loaded, config

    return launch


def test_only_four_paper_fields_explicit_compose_file_and_one_child(launch_fake):
    class RestrictedEnvironment(dict):
        def __iter__(self):
            raise AssertionError("Must not enumerate environment values")

        def __getitem__(self, key):
            assert key in launcher.OS_DOCKER_KEYS
            return super().__getitem__(key)

    env = RestrictedEnvironment(
        PATH="synthetic-path",
        PROGRAMFILES="synthetic-program-files",
        KIS_LIVE_APP_KEY="DO_NOT_READ",
    )
    (result, code), calls, loaded, config = launch_fake(environment=env)
    assert code == 0 and result == payload()
    assert len(calls) == len(loaded) == 1
    command, kwargs = calls[0]
    child = kwargs["env"]
    assert set(child) - set(launcher.OS_DOCKER_KEYS) == set(launcher.ro.KIS_PAPER_ENV_KEYS) | {
        "COMPOSE_DISABLE_ENV_FILE",
    }
    assert {key for key in child if key.startswith("KIS_")} == set(launcher.ro.KIS_PAPER_ENV_KEYS)
    assert child["COMPOSE_DISABLE_ENV_FILE"] == "1"
    assert child["PROGRAMFILES"] == "synthetic-program-files"
    assert command[command.index("--env-file") + 1].endswith(".env.example")
    assert command[-1] == "kis-readonly" and command.count("kis-readonly") == 2
    assert kwargs["stderr"] is subprocess.DEVNULL
    assert kwargs["stdout"] is subprocess.PIPE
    assert kwargs["timeout"] == launcher.BRIDGE_TIMEOUT_SECONDS
    assert command[command.index("--name") + 1] == (
        f"thericher-snapshot-bridge-{INVOCATION.replace('-', '')}"
    )
    assert command[command.index("--label") + 1] == f"{launcher.INVOCATION_LABEL}={INVOCATION}"
    for secret in vars(config).values():
        assert secret not in " ".join(command)
        assert secret not in json.dumps(result)


def test_default_inert_never_reads_credentials_or_invokes_child(monkeypatch, capsys):
    def deny(*args, **kwargs):
        raise AssertionError("inert path accessed a side effect")

    monkeypatch.setattr(launcher.ro, "load_kis_paper_config", deny)
    monkeypatch.setattr(launcher.subprocess, "run", deny)
    assert launcher.main([]) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "inert", "submit_capability": False}


@pytest.mark.parametrize("stale", [None, "0" * 64])
def test_compatible_stale_runtime_output_is_rejected(stale):
    value = payload()
    if stale is not None:
        value["runtime_source_sha256"] = stale
    with pytest.raises(ValueError):
        launcher.sanitize(json.dumps(value).encode(), INVOCATION)


def test_runtime_source_pin_is_required_but_not_relayed_to_host_schema():
    value = payload() | {"runtime_source_sha256": launcher.kis_paper_bridge_source_digest()}
    assert launcher.sanitize(json.dumps(value).encode(), INVOCATION) == payload()


@pytest.mark.parametrize(
    "change",
    [
        {"raw_account": "PRIVATE"},
        {"observer_invocation_id": "PRIVATE"},
        {"evidence_path": "/app/model_artifacts/execution/kis-paper-console-bridge/PRIVATE.json"},
        {"reason_code": "12345678"},
        {"account_snapshot_complete": 1},
        {"diagnostic": {"raw_response": "PRIVATE"}},
        {"scope": "live"},
    ],
)
def test_malicious_or_unknown_fields_never_relay(launch_fake, change):
    value = payload() | change
    (result, code), *_ = launch_fake(value)
    assert code == 3
    assert result == launcher.failure("bridge_output_invalid")
    assert "PRIVATE" not in json.dumps(result)


def test_nonzero_preserved_and_safe_unavailable_projected(launch_fake):
    (result, code), *_ = launch_fake(payload("unavailable"), 27)
    assert code == 27 and result == payload("unavailable")


@pytest.mark.parametrize(
    "reason",
    ["auth_rejected", "balance_rejected", "open_orders_rejected", "orderable_funds_rejected"],
)
def test_actual_core_rejection_with_nonzero_is_preserved(launch_fake, reason):
    value = payload("unavailable") | {"reason_code": launcher.ro.KisPaperReadOnlyError(reason).code}
    (result, code), *_ = launch_fake(value, 2)
    assert code == 2 and result == value


@pytest.mark.parametrize("invocation", [INVOCATION.replace("46de", "16de"), "not-a-uuid"])
def test_invalid_or_non_v4_invocation_rejected_before_config_read(
    monkeypatch, tmp_path, invocation
):
    calls = []

    def deny(*args, **kwargs):
        calls.append(True)
        raise AssertionError("must reject before side effects")

    monkeypatch.setattr(launcher.ro, "load_kis_paper_config", deny)
    monkeypatch.setattr(launcher.subprocess, "run", deny)
    assert launcher.launch(tmp_path, tmp_path / ".env", invocation) == (
        launcher.failure("invocation_invalid"),
        3,
    )
    assert calls == []


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "owner_invocation",
        "owner_service",
        "owner_read_only",
        "owner_id",
        "owner_name",
        "inspect_nonzero",
        "inspect_raw",
        "inspect_timeout",
        "remove_nonzero",
        "remove_timeout",
        "remaining_present",
        "remaining_nonzero",
    ],
)
def test_timeout_cleanup_only_exact_verified_readonly_container(launch_fake, fault, capsys):
    calls = []
    container_id = "a" * 64
    name = f"thericher-snapshot-bridge-{INVOCATION.replace('-', '')}"

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"], b"PRIVATE", b"PRIVATE")
        assert kwargs["env"] == {"PATH": "synthetic-path"}
        assert kwargs["timeout"] == launcher.CLEANUP_TIMEOUT_SECONDS
        assert kwargs["stderr"] is subprocess.DEVNULL
        if command[2] == "inspect":
            assert command[-1] == name
            assert command[4] == launcher.OWNERSHIP_FORMAT
            assert ".Env" not in command[4]
            owner = {
                "id": container_id,
                "name": f"/{name}",
                "invocation": INVOCATION,
                "service": "kis-readonly",
                "read_only": True,
            }
            if fault and fault.startswith("owner_"):
                owner[fault.removeprefix("owner_")] = "PRIVATE"
            if fault == "inspect_timeout":
                raise subprocess.TimeoutExpired(command, kwargs["timeout"], b"PRIVATE", b"PRIVATE")
            return subprocess.CompletedProcess(
                command,
                int(fault == "inspect_nonzero"),
                stdout=b"PRIVATE" if fault == "inspect_raw" else json.dumps(owner).encode(),
            )
        if command[2] == "rm":
            assert command == ["docker.exe", "container", "rm", "--force", container_id]
            assert kwargs["stdout"] is subprocess.DEVNULL
            if fault == "remove_timeout":
                raise subprocess.TimeoutExpired(command, kwargs["timeout"], b"PRIVATE", b"PRIVATE")
            return subprocess.CompletedProcess(command, int(fault == "remove_nonzero"))
        assert command == [
            "docker.exe",
            "container",
            "ls",
            "--all",
            "--quiet",
            "--no-trunc",
            "--filter",
            f"id={container_id}",
        ]
        return subprocess.CompletedProcess(
            command,
            int(fault == "remaining_nonzero"),
            stdout=container_id.encode() if fault == "remaining_present" else b"",
        )

    (result, code), _, _, config = launch_fake(
        environment={"PATH": "synthetic-path"},
        runner=run,
    )
    expected = "docker_timeout" if fault is None else "docker_timeout_cleanup_unknown"
    assert result == launcher.failure(expected) and code == 3
    if fault and (fault.startswith("owner_") or fault.startswith("inspect_")):
        assert len(calls) == 2
    assert sum(kwargs["timeout"] for _, kwargs in calls) <= 195
    assert 240 - (launcher.BRIDGE_TIMEOUT_SECONDS + 3 * launcher.CLEANUP_TIMEOUT_SECONDS) >= 45
    assert "PRIVATE" not in json.dumps(result)
    for command, _ in calls:
        assert all(secret not in " ".join(command) for secret in vars(config).values())
    assert capsys.readouterr().out == ""


def test_complete_nonzero_is_classified_not_claimed_complete(launch_fake):
    (result, code), *_ = launch_fake(payload(), 27)
    assert code == 27 and result == launcher.failure("docker_nonzero_exit")


def test_core_diagnostic_is_validated_then_not_forwarded(launch_fake):
    endpoint = launcher.ro.KIS_PAPER_READ_ONLY_ENDPOINTS[0]
    value = payload("unavailable")
    value["diagnostic"] = {"endpoint": endpoint.name, "tr_id": endpoint.tr_id, "http_status": "503"}
    (result, code), *_ = launch_fake(value, 2)
    assert code == 2 and result == payload("unavailable")


@pytest.mark.parametrize(
    "raw",
    [
        b"PRIVATE RAW OUTPUT",
        b'{}\n{"raw":"PRIVATE"}',
        b'{"status":"complete","status":"PRIVATE"}',
        b"\xff",
    ],
)
def test_raw_duplicate_or_multiple_output_rejected(raw):
    with pytest.raises((ValueError, UnicodeDecodeError)):
        launcher.sanitize(raw, INVOCATION)


def test_cli_exception_and_bad_arguments_are_sanitized(monkeypatch, capsys):
    assert launcher.main(["--unknown", "PRIVATE"]) == 3
    output = capsys.readouterr()
    assert "PRIVATE" not in output.out and output.err == ""
    monkeypatch.setattr(
        launcher, "launch", lambda *args: (_ for _ in ()).throw(RuntimeError("PRIVATE"))
    )
    assert (
        launcher.main(
            [
                "--execute",
                "--project-root",
                "synthetic",
                "--paper-credential-path",
                "synthetic/.env",
                "--observer-invocation-id",
                INVOCATION,
            ]
        )
        == 3
    )
    output = capsys.readouterr()
    assert "PRIVATE" not in output.out and output.err == ""
