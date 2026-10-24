"""Invented loader/Popen fixtures only; never invoke a Task, Docker or real dotenv."""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/run_kis_paper_daily_pair_forward_bootstrap.py"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("pair_bootstrap_test", SCRIPT)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    root = tmp_path / "project with spaces"
    (root / "scripts").mkdir(parents=True)
    (root / "docker-compose.yml").write_text("services: {}", encoding="ascii")
    (root / ".env.example").write_text("THERICHER_MODE=off", encoding="ascii")
    (root / script._SCHEDULE).write_text("# SYN never executed", encoding="ascii")
    exe = tmp_path / "fake.exe"
    exe.write_bytes(b"SYN not executable")
    monkeypatch.setattr(script, "_REPOSITORY_ROOT", root)
    monkeypatch.setattr(script, "_POWERSHELL", exe)
    monkeypatch.setattr(script, "_DOCKER", exe)
    monkeypatch.setattr(script, "_COMPOSE_PLUGIN", exe)
    monkeypatch.setattr(script, "_DOCKER_CONFIG", tmp_path / "owned empty docker")
    monkeypatch.setattr(
        script,
        "os",
        SimpleNamespace(
            name="nt",
            environ=script.os.environ,
            pathsep=";",
            fstat=script.os.fstat,
            fsync=script.os.fsync,
            link=script.os.link,
        ),
    )
    loader = Mock(return_value=SimpleNamespace(app_key="SYN_APP", app_secret="SYN_SECRET"))
    monkeypatch.setattr(script, "_load_paper_config", loader)
    popen = Mock(return_value=SimpleNamespace(wait=lambda: 7))
    monkeypatch.setattr(script.subprocess, "Popen", popen)
    monkeypatch.setattr(script.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    return script, root, loader, popen


def prefix(script, root):
    return [
        "compose",
        "--env-file",
        str(root / ".env.example"),
        "--project-directory",
        str(root),
        "--profile",
        script._COLLECTION,
        "run",
        "--rm",
        "--no-deps",
        "--pull",
        "never",
    ]


def cli(root, args):
    return ["--execute", "--compose", "--project-root", str(root), "--", *args]


def guard(script, reason):
    return [
        "--entrypoint",
        "python",
        script._PREFLIGHT,
        "scripts/collect_kis_paper_daily_pair_forward.py",
        "--preflight",
        "--cache-lineage",
        "v2",
        "--cache-root",
        "/app/market_data",
        "--artifact-root",
        "/app/model_artifacts",
        "--repository-root",
        "/app",
        "--schedule-guard-failed",
        reason,
    ]


def test_default_inert_and_quiet(setup, capsys):
    script, _, loader, popen = setup
    assert script.main([]) == 0
    loader.assert_not_called()
    popen.assert_not_called()
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize(
    "args",
    [
        ["--execute"],
        ["--execute", "--schedule", "--compose"],
        ["--unrecognized", "SYN_SECRET"],
        ["--execute", "--help"],
    ],
)
def test_invalid_cli_never_emits_values_or_launches(setup, args, capsys):
    script, _, loader, popen = setup
    assert script.main(args) in (2, 20)
    loader.assert_not_called()
    popen.assert_not_called()
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("service", ["preflight", "collection"])
@pytest.mark.parametrize("exit_code", [0, 2, 7, 10, 20])
def test_service_exact_argv_env_and_exit(setup, service, exit_code, capsys):
    script, root, loader, popen = setup
    popen.return_value.wait = lambda: exit_code
    selected = script._PREFLIGHT if service == "preflight" else script._COLLECTION
    args = prefix(script, root) + [selected]
    assert script.main(cli(root, args)) == exit_code
    command = popen.call_args.args[0]
    assert command == [str(script._DOCKER), "--host", script._LOCAL_ENGINE, *args]
    env = popen.call_args.kwargs["env"]
    assert env["THERICHER_MODE"] == "off"
    assert env["DOCKER_HOST"] == script._LOCAL_ENGINE
    assert env["DOCKER_CONFIG"] == str(script._DOCKER_CONFIG)
    assert "SYN_SECRET" not in json.dumps(command)
    if service == "collection":
        loader.assert_called_once_with(root)
        assert env["KIS_PAPER_APP_KEY"] == "SYN_APP"
        assert env["KIS_PAPER_APP_SECRET"] == "SYN_SECRET"
    else:
        loader.assert_not_called()
        assert "KIS_PAPER_APP_KEY" not in env and "KIS_PAPER_APP_SECRET" not in env
    assert popen.call_args.kwargs["shell"] is False
    assert popen.call_args.kwargs["creationflags"] == 0x08000000
    assert all(
        popen.call_args.kwargs[k] == script.subprocess.DEVNULL
        for k in ("stdin", "stdout", "stderr")
    )
    assert [p.name for p in script._DOCKER_CONFIG.iterdir()] == ["config.json"]
    assert (script._DOCKER_CONFIG / "config.json").read_bytes() == script._docker_config_payload()
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("reason", ["host_timezone_not_kst", "shared_dispatcher_busy"])
def test_guard_override_preserves_exact_existing_service_and_never_loads_keys(setup, reason):
    script, root, loader, popen = setup
    args = prefix(script, root) + guard(script, reason)
    assert script.main(cli(root, args)) == 7
    loader.assert_not_called()
    assert popen.call_args.args[0][3:] == args


@pytest.mark.parametrize(
    "fault",
    [
        ValueError("SYN_SECRET"),
        OSError("SYN_SECRET"),
        RuntimeError("SYN_SECRET"),
        ModuleNotFoundError("SYN_SECRET"),
    ],
)
def test_loader_failure_still_launches_same_collector_blank_keys(setup, fault, capsys):
    script, root, loader, popen = setup
    loader.side_effect = fault
    args = prefix(script, root) + [script._COLLECTION]
    assert script.main(cli(root, args)) == 7
    env = popen.call_args.kwargs["env"]
    assert "KIS_PAPER_APP_KEY" not in env and "KIS_PAPER_APP_SECRET" not in env
    assert popen.call_args.args[0][-1] == script._COLLECTION
    assert capsys.readouterr() == ("", "")


def test_schedule_launches_only_original_ps_without_keys(setup):
    script, root, loader, popen = setup
    assert script.main(["--execute", "--schedule", "--project-root", str(root)]) == 7
    assert popen.call_args.args[0] == [
        str(script._POWERSHELL),
        "-WindowStyle",
        "Hidden",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(root / script._SCHEDULE),
        "-ProjectRoot",
        str(root),
    ]
    assert not any(key.startswith("KIS_") for key in popen.call_args.kwargs["env"])
    loader.assert_not_called()
    assert not script._DOCKER_CONFIG.exists()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s, r, a: [*a, "--env-file", str(r / ".env")],
        lambda s, r, a: a[0:1] + a[3:],
        lambda s, r, a: [x if x != str(r / ".env.example") else str(r / ".env") for x in a],
        lambda s, r, a: [x if x != "never" else "always" for x in a],
        lambda s, r, a: a[:-1] + ["kis-live"],
        lambda s, r, a: a[:-1] + ["kis-paper-daily-pair-forward"],
        lambda s, r, a: a[:-1] + guard(s, "SYN_SECRET"),
        lambda s, r, a: a[:-1] + guard(s, "host_timezone_not_kst") + ["extra"],
        lambda s, r, a: a[:-1] + ["--entrypoint", "sh", s._PREFLIGHT],
    ],
)
def test_rejects_any_other_compose_route_before_loading_or_launch(setup, mutate):
    script, root, loader, popen = setup
    args = mutate(script, root, prefix(script, root) + [script._COLLECTION])
    assert script.main(cli(root, args)) == 20
    loader.assert_not_called()
    popen.assert_not_called()
    assert not script._DOCKER_CONFIG.exists()


def test_no_separator_or_schedule_tail_is_rejected(setup):
    script, root, loader, popen = setup
    assert (
        script.main(
            [
                "--execute",
                "--compose",
                "--project-root",
                str(root),
                *prefix(script, root),
                script._COLLECTION,
            ]
        )
        == 20
    )
    assert script.main(["--execute", "--schedule", "--project-root", str(root), "--", "bad"]) == 20
    loader.assert_not_called()
    popen.assert_not_called()


def test_environment_uses_only_direct_safe_getters_and_fixed_controls(setup):
    script, _, _, _ = setup

    class Poison(Mapping):
        def __iter__(self):
            raise AssertionError("environment_enumerated")

        def __len__(self):
            raise AssertionError("environment_enumerated")

        def __getitem__(self, key):
            assert key in script._SAFE_HOST_KEYS, "secret_or_control_environment_read"
            return "SYN_SAFE_" + key

    result = script._safe_environment(Poison())
    assert not any(key.startswith(("KIS_", "COMPOSE_", "PYTHON")) for key in result)
    assert "DOCKER_CONTEXT" not in result
    assert result["PSModulePath"] == str(script._POWERSHELL.parent / "Modules")
    assert result["PATH"] != "SYN_CALLER_PATH"
    assert result["THERICHER_HOST_MARKET_DATA_ROOT"] == "D:/market_data"


@pytest.mark.parametrize("node", ["file", "directory"])
def test_owned_config_rejects_existing_foreign_members_without_erasing(setup, node):
    script, root, loader, popen = setup
    script._DOCKER_CONFIG.mkdir()
    target = script._DOCKER_CONFIG / "foreign"
    target.write_text("SYN") if node == "file" else target.mkdir()
    assert script.main(cli(root, prefix(script, root) + [script._COLLECTION])) == 20
    assert target.exists()
    loader.assert_not_called()
    popen.assert_not_called()


@pytest.mark.parametrize("already_empty", [False, True])
def test_owned_config_first_use_creates_only_fixed_public_plugin_config(setup, already_empty):
    script, _, loader, popen = setup
    if already_empty:
        script._DOCKER_CONFIG.mkdir()
    script._empty_docker_config()
    path = script._DOCKER_CONFIG / "config.json"
    assert path.read_bytes() == script._docker_config_payload()
    assert json.loads(path.read_bytes()) == {
        "cliPluginsExtraDirs": [script._COMPOSE_PLUGIN.parent.as_posix()]
    }
    assert [p.name for p in script._DOCKER_CONFIG.iterdir()] == ["config.json"]
    assert list(script._DOCKER_CONFIG.parent.glob(".pair-config-*.tmp")) == []
    loader.assert_not_called()
    popen.assert_not_called()


def test_owned_config_second_call_preserves_identity_bytes_and_mtime(setup, monkeypatch):
    script, _, loader, popen = setup
    script._empty_docker_config()
    path = script._DOCKER_CONFIG / "config.json"
    before = path.stat()
    link = Mock(side_effect=AssertionError("second_publish_attempt"))
    monkeypatch.setattr(script.os, "link", link)
    script._empty_docker_config()
    after = path.stat()
    assert (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) == (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    assert path.read_bytes() == script._docker_config_payload()
    link.assert_not_called()
    loader.assert_not_called()
    popen.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        b"{}",
        b'{"auths":{"SYN":{"auth":"SYN"}}}',
        b'{"credsStore":"SYN"}',
        b'{"cliPluginsExtraDirs":["SYN_FOREIGN"]}',
        b'{"cliPluginsExtraDirs":[],"currentContext":"SYN"}',
        b"SYN not JSON",
    ],
)
def test_owned_config_foreign_contents_are_preserved_and_never_launched(setup, payload):
    script, root, loader, popen = setup
    script._DOCKER_CONFIG.mkdir()
    path = script._DOCKER_CONFIG / "config.json"
    path.write_bytes(payload)
    before = path.stat()
    assert script.main(cli(root, prefix(script, root) + [script._COLLECTION])) == 20
    assert path.read_bytes() == payload
    assert path.stat().st_mtime_ns == before.st_mtime_ns
    loader.assert_not_called()
    popen.assert_not_called()


def test_owned_config_rejects_equal_size_altered_bytes(setup):
    script, root, loader, popen = setup
    script._DOCKER_CONFIG.mkdir()
    path = script._DOCKER_CONFIG / "config.json"
    payload = script._docker_config_payload().replace(
        b"cliPluginsExtraDirs", b"cliPluginsExtraDirX"
    )
    assert len(payload) == len(script._docker_config_payload())
    path.write_bytes(payload)
    assert script.main(cli(root, prefix(script, root) + [script._COLLECTION])) == 20
    assert path.read_bytes() == payload
    loader.assert_not_called()
    popen.assert_not_called()


def test_owned_config_rejects_directory_at_config_file_path(setup):
    script, root, loader, popen = setup
    path = script._DOCKER_CONFIG / "config.json"
    path.mkdir(parents=True)
    assert script.main(cli(root, prefix(script, root) + [script._COLLECTION])) == 20
    assert path.is_dir()
    loader.assert_not_called()
    popen.assert_not_called()


@pytest.mark.parametrize("node", ["root", "config", "plugin"])
@pytest.mark.parametrize("kind", ["reparse", "dangling_symlink"])
def test_owned_config_reparse_metadata_is_rejected_before_open(setup, monkeypatch, node, kind):
    script, _, loader, popen = setup
    script._DOCKER_CONFIG.mkdir()
    path = script._DOCKER_CONFIG / "config.json"
    target = {"root": script._DOCKER_CONFIG, "config": path, "plugin": script._COMPOSE_PLUGIN}[node]
    real_lstat = Path.lstat

    def lstat(value, *args, **kwargs):
        if value == target:
            return SimpleNamespace(
                st_mode=0o120777 if kind == "dangling_symlink" else 0o100666,
                st_file_attributes=0x400 if kind == "reparse" else 0,
            )
        return real_lstat(value, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(ValueError, match="bootstrap_reparse_denied"):
        if node == "config":
            script._no_reparse(path)
        else:
            script._empty_docker_config()
    loader.assert_not_called()
    popen.assert_not_called()


@pytest.mark.parametrize("matching", [False, True])
def test_owned_config_atomic_race_never_overwrites_concurrent_contents(
    setup, monkeypatch, matching
):
    script, root, loader, popen = setup
    real_link = script.os.link
    payload = script._docker_config_payload() if matching else b'{"auths":{"SYN":{}}}'

    def race(source, target):
        target.write_bytes(payload)
        real_link(source, target)

    monkeypatch.setattr(script.os, "link", race)
    selected = script._PREFLIGHT if matching else script._COLLECTION
    assert script.main(cli(root, prefix(script, root) + [selected])) == (7 if matching else 20)
    assert (script._DOCKER_CONFIG / "config.json").read_bytes() == payload
    assert list(script._DOCKER_CONFIG.parent.glob(".pair-config-*.tmp")) == []
    loader.assert_not_called()
    assert popen.call_count == (1 if matching else 0)


def test_owned_config_member_appearing_during_publish_withholds_launch(setup, monkeypatch):
    script, root, loader, popen = setup
    real_link = script.os.link

    def race(source, target):
        real_link(source, target)
        (script._DOCKER_CONFIG / "foreign").mkdir()

    monkeypatch.setattr(script.os, "link", race)
    assert script.main(cli(root, prefix(script, root) + [script._COLLECTION])) == 20
    assert (script._DOCKER_CONFIG / "foreign").is_dir()
    assert list(script._DOCKER_CONFIG.parent.glob(".pair-config-*.tmp")) == []
    loader.assert_not_called()
    popen.assert_not_called()


def test_owned_config_failed_atomic_publish_is_not_retried(setup, monkeypatch):
    script, root, loader, popen = setup
    link = Mock(side_effect=OSError("SYN denied"))
    monkeypatch.setattr(script.os, "link", link)
    assert script.main(cli(root, prefix(script, root) + [script._COLLECTION])) == 20
    assert list(script._DOCKER_CONFIG.iterdir()) == []
    assert list(script._DOCKER_CONFIG.parent.glob(".pair-config-*.tmp")) == []
    link.assert_called_once()
    loader.assert_not_called()
    popen.assert_not_called()


def test_wrong_project_or_missing_public_file_is_rejected(setup):
    script, root, loader, popen = setup
    assert script.main(["--execute", "--schedule", "--project-root", str(root.parent)]) == 20
    assert script.main(["--execute", "--schedule", "--project-root", "relative"]) == 20
    (root / ".env.example").unlink()
    assert script.main(["--execute", "--schedule", "--project-root", str(root)]) == 20
    loader.assert_not_called()
    popen.assert_not_called()


def test_no_implicit_dotenv_open_in_schedule_or_preflight(setup, monkeypatch):
    script, root, loader, _ = setup
    real_open = Path.open

    def guarded_open(path, *args, **kwargs):
        assert path.name != ".env", "dotenv_read"
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    assert script.main(["--execute", "--schedule", "--project-root", str(root)]) == 7
    assert script.main(cli(root, prefix(script, root) + [script._PREFLIGHT])) == 7
    loader.assert_not_called()


def test_no_raw_child_failure_output_or_retry(setup, capsys):
    script, root, _, popen = setup
    popen.side_effect = OSError("SYN_SECRET")
    assert script.main(["--execute", "--schedule", "--project-root", str(root)]) == 20
    assert popen.call_count == 1
    assert capsys.readouterr() == ("", "")


def test_unexpected_launch_failure_is_quiet_without_retry(setup, capsys):
    script, root, loader, popen = setup
    popen.side_effect = TypeError("SYN_SECRET")
    assert script.main(["--execute", "--schedule", "--project-root", str(root)]) == 20
    assert popen.call_count == 1
    loader.assert_not_called()
    assert capsys.readouterr() == ("", "")


def test_scoped_loader_lazily_imports_only_named_module_and_off_mapping(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("pair_loader_test", SCRIPT)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    target = tmp_path / "src/thericher_v2/execution/kis_market_data.py"
    target.parent.mkdir(parents=True)
    target.write_text("# SYN never imported", encoding="ascii")
    config = SimpleNamespace(app_key="SYN_APP", app_secret="SYN_SECRET")
    loader = Mock(return_value=config)
    importer = Mock(
        return_value=SimpleNamespace(__file__=str(target), load_kis_paper_market_data_config=loader)
    )
    monkeypatch.setattr(script.importlib, "import_module", importer)
    monkeypatch.setattr(script.sys, "path", list(script.sys.path))
    monkeypatch.setattr(script.sys.implementation, "cache_tag", script.sys.implementation.cache_tag)
    assert script._load_paper_config(tmp_path) is config
    importer.assert_called_once_with("thericher_v2.execution.kis_market_data")
    loader.assert_called_once_with(tmp_path / ".env", environment={"THERICHER_MODE": "off"})
    assert script.sys.path[0] == str(tmp_path / "src")
