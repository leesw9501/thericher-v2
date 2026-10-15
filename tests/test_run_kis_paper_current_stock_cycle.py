"""Synthetic immutable-image launch and cleanup boundaries; Docker is mocked."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts/run_kis_paper_current_stock_cycle.py"
SPEC = importlib.util.spec_from_file_location("current_stock_host", PATH)
w = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(w)
IMAGE = "sha256:" + "a" * 64
IDENTITY = "b" * 32


@pytest.fixture(autouse=True)
def no_real_dispatch(monkeypatch):
    monkeypatch.setattr(w.subprocess, "run", lambda *a, **k: pytest.fail("actual Docker forbidden"))
    monkeypatch.setattr(w, "load_paper_config", lambda: pytest.fail("actual credentials forbidden"))


def payload():
    return dict(
        kind="kis_paper_current_stock_cycle_v1",
        status="pending",
        reason="exact_request_retained",
        leg_count=1,
        limitation="cycle_status_not_current_inventory_or_net_pnl",
        paper_only=True,
        unknown_effects_not_assumed_zero=True,
        visits=1,
        calls=dict(token_posts=0, get_requests=0, buy_posts=0, sell_posts=0, cancel_posts=0),
        http_start_gaps_seconds=[],
        pacing_basis="final_opener_delegate_boundary_not_socket_wire_measurement",
        observed_at_utc="2026-10-15T14:00:00+00:00",
        fees="not_observed",
        settled_cash="not_observed",
        net_pnl="not_observed",
    )


def test_inert_does_not_read_source_credentials_or_docker(monkeypatch, capsys):
    monkeypatch.setattr(w, "source_map", lambda: pytest.fail("inert source read"))
    assert w.run()["status"] == "inert"
    assert w.main([]) == 0
    assert json.loads(capsys.readouterr().out) == dict(
        status="inert", credential_reads=0, broker_calls=0
    )


@pytest.mark.parametrize(
    "status,reason,exit_code",
    [
        ("advanced", "native_leg_closed", 0),
        ("unavailable", "native_recovery_required", 20),
    ],
)
def test_main_stdout_exact_evidence_path_binds_immutable_written_result(
    tmp_path, monkeypatch, capsys, status, reason, exit_code
):
    result = payload()
    result.update(status=status, reason=reason)
    expected = json.dumps(result, sort_keys=True).encode("ascii")
    calls = []

    def fake_run(**kwargs):
        calls.append(kwargs)
        return dict(result)

    monkeypatch.setattr(w, "run", fake_run)
    monkeypatch.setattr(w, "ARTIFACT", tmp_path)
    manifest = tmp_path / "source-manifest.json"
    manifest_ref = "sha256:" + "c" * 64
    assert (
        w.main(
            [
                "--execute",
                "--image",
                IMAGE,
                "--source-manifest",
                str(manifest),
                "--source-manifest-ref",
                manifest_ref,
            ]
        )
        == exit_code
    )
    stdout = json.loads(capsys.readouterr().out)
    evidence = Path(stdout.pop("evidence_path"))
    assert (
        evidence.parent == tmp_path / "execution/current-nas-owned-model-paper-runtime-20261015-v1"
    )
    assert evidence.name.endswith("Z.json")
    written = evidence.read_bytes()
    assert written == expected and stdout == result == json.loads(written)
    assert "evidence_path" not in json.loads(written)
    assert hashlib.sha256(written).digest() == hashlib.sha256(expected).digest()
    assert calls == [
        dict(
            image=IMAGE,
            execute=True,
            source_manifest=manifest,
            source_manifest_ref=manifest_ref,
        )
    ]


def test_command_network_none_default_and_exact_same_bank():
    args = w.command(IMAGE, IDENTITY)
    assert args[args.index("--network") + 1] == "none" and "--execute" not in args
    actual = w.command(IMAGE, IDENTITY, execute=True)
    assert "--execute" in actual and "--network" not in actual
    for volume, target in zip(w.VOLUMES, ("private", "runtime", "emergency"), strict=True):
        assert f"type=volume,source={volume},target=/app/{target},volume-nocopy" in actual
    assert "/app/" + w.WORKER in actual
    assert not any("KIS_" in a or ".env" in a for a in actual)
    assert "--read-only" in actual and actual[actual.index("--log-driver") + 1] == "none"
    with pytest.raises(ValueError):
        w.command("mutable:latest", IDENTITY)
    with pytest.raises(ValueError):
        w.command(IMAGE, "unsafe")


def test_source_inventory_includes_all_src_and_imported_helpers():
    inventory = w.source_map()
    assert {w.HOST, w.WORKER, *w.HELPERS} <= set(inventory)
    assert len([name for name in inventory if name.startswith("src/")]) == len(
        list((w.ROOT / "src").rglob("*.py"))
    )
    assert not any(".env" in name for name in inventory)
    assert w.CREDENTIAL_PATH == Path("C:/Users/Public/Documents/thericher-v2/.env")


def test_exact_manifest_required_before_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(w, "source_map", lambda: dict(source="b" * 64))
    raw = b'{"files":{"source":"' + b"b" * 64 + b'"}}'
    path = tmp_path / "sources.json"
    path.write_bytes(raw)
    ref = "sha256:" + hashlib.sha256(raw).hexdigest()
    assert w.read_manifest(path, ref) == dict(source="b" * 64)
    with pytest.raises(ValueError, match="source_manifest_mismatch"):
        w.read_manifest(path, "sha256:" + "a" * 64)
    path.write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="source_manifest_mismatch"):
        w.run(image=IMAGE, execute=True, source_manifest=path, source_manifest_ref=ref)


def test_frozen_source_inventory_is_independent_of_mutable_checkout(tmp_path, monkeypatch):
    snapshot = tmp_path / "frozen-repository"
    for name in (w.HOST, w.WORKER, *w.HELPERS):
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((w.ROOT / name).read_bytes())
    (snapshot / "src").mkdir()
    (snapshot / "src/pinned.py").write_text("FROZEN = True\n", encoding="ascii")
    monkeypatch.setattr(w, "ROOT", snapshot)
    expected = w.source_map()
    original = tmp_path / "mutable-checkout/src"
    original.mkdir(parents=True)
    (original / "new_module.py").write_text("MUTABLE = True\n", encoding="ascii")
    assert w.source_map() == expected
    assert w.CREDENTIAL_PATH == Path("C:/Users/Public/Documents/thericher-v2/.env")
    assert not (snapshot / ".env").exists()


@pytest.mark.parametrize(
    "fault",
    [
        "private",
        "reason",
        "kind",
        "cash",
        "bool",
        "calls",
        "order",
        "cancel",
        "visits",
        "gaps",
        "time",
    ],
)
def test_closed_categorical_output(fault):
    value = payload()
    if fault == "private":
        value["symbol"] = "SYNTH"
    elif fault == "reason":
        value["reason"] = "synthetic-secret"
    elif fault == "kind":
        value["kind"] = "raw-private"
    elif fault == "cash":
        value["settled_cash"] = "123"
    elif fault == "bool":
        value["calls"]["get_requests"] = True
    elif fault == "calls":
        value["calls"]["get_requests"] = 129
    elif fault == "order":
        value["calls"]["buy_posts"] = value["calls"]["sell_posts"] = 1
    elif fault == "cancel":
        value["calls"]["cancel_posts"] = 2
    elif fault == "visits":
        value["visits"] = True
    elif fault == "gaps":
        value["http_start_gaps_seconds"] = [float("nan")]
    else:
        value["observed_at_utc"] = "2026-10-15T14:00:00"
    with pytest.raises(ValueError, match="stock_worker_output_invalid"):
        w.validate_result(value)


def test_native_status_reason_pairs_are_not_interchangeable():
    value = payload()
    value["status"] = "complete"
    with pytest.raises(ValueError, match="stock_worker_output_invalid"):
        w.validate_result(value)


def test_host_contract_agrees_with_worker_pairs_plus_fixed_failure_code():
    from test_kis_paper_current_stock_cycle_worker import w as worker

    expected = {status: set(reasons) for status, reasons in worker.NATIVE_REASONS.items()}
    expected["unavailable"].add("worker_recovery_required")
    assert w.STATUS_REASONS == expected
    assert w.SAFE_REASONS == set().union(*expected.values())


@pytest.mark.parametrize(
    "allowed,reason",
    [
        ("no_intent", "cycle_never_reserved_retired"),
        ("unavailable", "cycle_retirement_unproven"),
        ("unavailable", "cycle_retired_request_restored"),
        ("unavailable", "cycle_owned_not_flat"),
    ],
)
@pytest.mark.parametrize(
    "status", ["advanced", "complete", "hold", "no_intent", "pending", "unavailable"]
)
def test_four_native_reasons_reject_every_wrong_status(allowed, reason, status):
    from test_kis_paper_current_stock_cycle_worker import w as worker

    value = payload()
    value.update(status=status, reason=reason)
    if status == allowed:
        assert w.validate_result(value) == value
        assert (
            worker._categorical(dict(status=status, reason=reason, leg_count=1))["reason"] == reason
        )
        return
    with pytest.raises(ValueError, match="stock_worker_output_invalid"):
        w.validate_result(value)
    with pytest.raises(ValueError, match="native_cycle_output_invalid"):
        worker._categorical(dict(status=status, reason=reason, leg_count=1))


def test_missing_success_counters_not_assumed_zero():
    value = payload()
    del value["calls"]
    with pytest.raises(ValueError, match="stock_worker_output_invalid"):
        w.validate_result(value)


@pytest.fixture
def launch(monkeypatch):
    expected = dict(source="c" * 64)
    monkeypatch.setattr(w, "read_manifest", lambda *a: expected)
    monkeypatch.setattr(w, "source_map", lambda: expected)
    monkeypatch.setattr(w, "os_environment", lambda: dict(PATH="synthetic"))
    monkeypatch.setattr(
        w,
        "load_paper_config",
        lambda: SimpleNamespace(
            app_key="synthetic-key",
            app_secret="synthetic-secret",
            account_number="12345678",
            account_product_code="01",
        ),
    )
    seen = []

    def call(args, **kwargs):
        seen.append((args, kwargs))
        assert kwargs["creationflags"] == getattr(w.subprocess, "CREATE_NO_WINDOW", 0)
        assert not any(key.startswith("KIS_") for key in kwargs["env"])
        assert "synthetic-secret" not in str(args) and "12345678" not in str(args)
        if args[1] == "run" and "--network" in args:
            return SimpleNamespace(returncode=0, stdout=json.dumps(expected).encode())
        if args[1] == "run":
            packet = json.loads(kwargs["input"])
            assert packet["THERICHER_MODE"] == "kis_paper"
            assert packet["KIS_PAPER_APP_SECRET"] == "synthetic-secret"
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload()).encode())
        return SimpleNamespace(returncode=0, stdout=b"")

    monkeypatch.setattr(w.subprocess, "run", call)
    return seen


def test_private_packet_stdin_only_quiet_cleanup_and_output(launch):
    result = w.run(
        image=IMAGE, execute=True, source_manifest="synthetic", source_manifest_ref="synthetic"
    )
    assert result["status"] == "pending" and result["exact_container_absent"] is True
    assert "synthetic-secret" not in json.dumps(result) and "12345678" not in json.dumps(result)
    assert sum("input" in kwargs for _, kwargs in launch) == 1
    filters = [args[args.index("--filter") + 1] for args, _ in launch if "--filter" in args]
    assert any(f.startswith("name=^/") for f in filters)
    assert any(f.startswith("label=" + w.LABEL + "=") for f in filters)


def test_image_mismatch_precedes_credentials(launch, monkeypatch):
    monkeypatch.setattr(w, "load_paper_config", lambda: pytest.fail("mismatch read credentials"))

    def call(args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=b"{}" if args[1] == "run" else b"")

    monkeypatch.setattr(w.subprocess, "run", call)
    with pytest.raises(ValueError, match="worker_image_source_mismatch"):
        w.run(image=IMAGE, execute=True)


@pytest.mark.parametrize("fault", ["exit", "timeout", "cleanup", "raw_output"])
def test_post_dispatch_unknown_effects_preserved(launch, monkeypatch, fault):
    original = w.subprocess.run

    def call(args, **kwargs):
        if args[1] == "run" and "--execute" in args:
            if fault == "timeout":
                raise w.subprocess.TimeoutExpired(args, 320)
            return SimpleNamespace(
                returncode=137 if fault == "exit" else 0,
                stdout=b'{"secret":"never-print"}'
                if fault == "raw_output"
                else json.dumps(payload()).encode(),
            )
        return original(args, **kwargs)

    monkeypatch.setattr(w.subprocess, "run", call)
    if fault == "cleanup":
        absent = iter((True, False))
        monkeypatch.setattr(w, "cleanup", lambda *a: next(absent))
    result = w.run(image=IMAGE, execute=True)
    assert result["status"] == "unavailable" and result["unknown_effects_not_assumed_zero"] is True
    assert "never-print" not in json.dumps(result)
    if fault in {"exit", "cleanup"}:
        assert result["worker_report"]["status"] == "pending"


def test_cleanup_wrong_owner_never_removed(monkeypatch):
    seen = []

    def call(args, **kwargs):
        seen.append(args)
        assert args[1] != "rm"
        return SimpleNamespace(
            returncode=0, stdout=("a" * 64 if args[1] == "container" else "foreign-owner").encode()
        )

    monkeypatch.setattr(w.subprocess, "run", call)
    assert w.cleanup("owned-name", IDENTITY, {}) is False
    assert len(seen) == 2


def test_cleanup_typed_absence_not_english_stderr(monkeypatch):
    seen = []

    def call(args, **kwargs):
        seen.append(args)
        assert args[1] == "container"
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"no such object")

    monkeypatch.setattr(w.subprocess, "run", call)
    assert w.cleanup("owned-name", IDENTITY, {}) is True
    assert len(seen) == 2


def test_cleanup_named_actor_absent_but_owned_label_remaining_is_unknown(monkeypatch):
    def call(args, **kwargs):
        query = args[args.index("--filter") + 1]
        assert args[1] == "container"
        return SimpleNamespace(returncode=0, stdout=b"" if query.startswith("name=") else b"a" * 64)

    monkeypatch.setattr(w.subprocess, "run", call)
    assert w.cleanup("owned-name", IDENTITY, {}) is False


def test_probe_timeout_cleanup_precedes_any_paper_keys(launch, monkeypatch):
    cleaned = []
    monkeypatch.setattr(w, "cleanup", lambda *a: cleaned.append(a) or True)
    monkeypatch.setattr(
        w, "load_paper_config", lambda: pytest.fail("credentials before probe closure")
    )

    def timeout(args, **kwargs):
        assert "--network" in args and kwargs["creationflags"] == getattr(
            w.subprocess, "CREATE_NO_WINDOW", 0
        )
        raise w.subprocess.TimeoutExpired(args, 15)

    monkeypatch.setattr(w.subprocess, "run", timeout)
    with pytest.raises(w.subprocess.TimeoutExpired):
        w.run(image=IMAGE, execute=True)
    assert len(cleaned) == 1 and cleaned[0][0].startswith("thericher-current-stock-source-")
