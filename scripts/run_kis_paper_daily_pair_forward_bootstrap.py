"""Quiet, pair-only schedule bootstrap with explicit Paper credential routing."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import stat
import subprocess
import sys
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_WINDOWS_ROOT = Path("C:/Windows")
_POWERSHELL = _WINDOWS_ROOT / "System32/WindowsPowerShell/v1.0/powershell.exe"
_DOCKER_BIN = Path("C:/Program Files/Docker/Docker/resources/bin")
_DOCKER = _DOCKER_BIN / "docker.exe"
_COMPOSE_PLUGIN = Path("C:/Program Files/Docker/cli-plugins/docker-compose.exe")
_DOCKER_CONFIG = Path(
    "D:/thericher-v2/model-artifacts/data/kis-paper-daily-pair-forward-bootstrap-v1/docker-config"
)
_LOCAL_ENGINE = "npipe:////./pipe/dockerDesktopLinuxEngine"
_SCHEDULE = "scripts/run_kis_paper_daily_pair_forward_schedule.ps1"
_COLLECTION = "kis-paper-daily-pair-forward-v2"
_PREFLIGHT = _COLLECTION + "-preflight"
_SAFE_HOST_KEYS = ("USERPROFILE", "LOCALAPPDATA", "APPDATA", "TEMP", "TMP")
_GUARD_REASONS = ("host_timezone_not_kst", "shared_dispatcher_busy")
_RECOVERY_EXIT = 20


class _QuietParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError("bootstrap_arguments_invalid")


def _no_reparse(path: Path) -> None:
    for node in (path, *path.parents):
        try:
            value = node.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(value.st_mode) or getattr(value, "st_file_attributes", 0) & 0x400:
            raise ValueError("bootstrap_reparse_denied")


def _ordinary_file(path: Path) -> None:
    _no_reparse(path)
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("bootstrap_file_required")


def _project_root(value: Path | None) -> Path:
    if value is None or not value.is_absolute() or ".." in value.parts:
        raise ValueError("bootstrap_project_required")
    _no_reparse(value)
    if value.resolve(strict=True) != _REPOSITORY_ROOT.resolve(strict=True):
        raise ValueError("bootstrap_project_unbound")
    _ordinary_file(value / "docker-compose.yml")
    _ordinary_file(value / ".env.example")
    return value


def _safe_environment(environment: Mapping[str, str]) -> dict[str, str]:
    # Select named nonsecret values only; never enumerate or copy the caller environment.
    result = {}
    for key in _SAFE_HOST_KEYS:
        value = environment.get(key)
        if isinstance(value, str) and value and "\x00" not in value:
            result[key] = value
    result.update(
        SYSTEMROOT=str(_WINDOWS_ROOT),
        WINDIR=str(_WINDOWS_ROOT),
        SYSTEMDRIVE=_WINDOWS_ROOT.drive,
        PATH=os.pathsep.join(
            str(p)
            for p in (
                _WINDOWS_ROOT / "System32",
                _WINDOWS_ROOT,
                _POWERSHELL.parent,
                _DOCKER_BIN,
            )
        ),
        PSModulePath=str(_POWERSHELL.parent / "Modules"),
        THERICHER_MODE="off",
        THERICHER_HOST_MARKET_DATA_ROOT="D:/market_data",
        THERICHER_HOST_MODEL_ARTIFACT_ROOT="D:/thericher-v2/model-artifacts",
        THERICHER_MODEL_ARTIFACT_ROOT="/app/model_artifacts",
        DOCKER_HOST=_LOCAL_ENGINE,
        DOCKER_CONFIG=str(_DOCKER_CONFIG),
    )
    return result


def _compose_service(root: Path, arguments: Sequence[str]) -> str:
    prefix = [
        "compose",
        "--env-file",
        str(root / ".env.example"),
        "--project-directory",
        str(root),
        "--profile",
        _COLLECTION,
        "run",
        "--rm",
        "--no-deps",
        "--pull",
        "never",
    ]
    args = list(arguments)
    if args[: len(prefix)] != prefix:
        raise ValueError("bootstrap_compose_prefix")
    tail = args[len(prefix) :]
    if tail in ([_PREFLIGHT], [_COLLECTION]):
        return tail[0]
    override = [
        "--entrypoint",
        "python",
        _PREFLIGHT,
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
    ]
    if tail[:-1] == override and tail[-1:] and tail[-1] in _GUARD_REASONS:
        return _PREFLIGHT
    raise ValueError("bootstrap_compose_service")


def _load_paper_config(root: Path):
    # This isolated CLI imports only the named existing loader, only for collection.
    sys.path.insert(0, str(root / "src"))
    sys.implementation.cache_tag = None
    market = importlib.import_module("thericher_v2.execution.kis_market_data")
    expected = root / "src/thericher_v2/execution/kis_market_data.py"
    if Path(market.__file__).resolve(strict=True) != expected.resolve(strict=True):
        raise ValueError("bootstrap_loader_source")
    return market.load_kis_paper_market_data_config(
        root / ".env", environment={"THERICHER_MODE": "off"}
    )


def _docker_config_payload() -> bytes:
    return (
        json.dumps(
            {"cliPluginsExtraDirs": [_COMPOSE_PLUGIN.parent.as_posix()]},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _validate_docker_config(expected: bytes) -> None:
    _no_reparse(_DOCKER_CONFIG)
    if [entry.name for entry in _DOCKER_CONFIG.iterdir()] != ["config.json"]:
        raise ValueError("bootstrap_docker_config_foreign_member")
    path = _DOCKER_CONFIG / "config.json"
    _ordinary_file(path)
    before = path.stat()
    if before.st_size != len(expected):
        raise ValueError("bootstrap_docker_config_unbound")
    with path.open("rb") as stream:
        raw = stream.read(len(expected) + 1)
    after = path.stat()

    def identity(value):
        return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)

    if raw != expected or identity(before) != identity(after):
        raise ValueError("bootstrap_docker_config_unbound")
    _no_reparse(path)
    if [entry.name for entry in _DOCKER_CONFIG.iterdir()] != ["config.json"]:
        raise ValueError("bootstrap_docker_config_foreign_member")


def _empty_docker_config() -> None:
    """Keep credentials empty; admit only exact public plugin-discovery config."""
    _ordinary_file(_COMPOSE_PLUGIN)
    _no_reparse(_DOCKER_CONFIG)
    _DOCKER_CONFIG.mkdir(parents=True, exist_ok=True)
    _no_reparse(_DOCKER_CONFIG)
    expected = _docker_config_payload()
    if any(_DOCKER_CONFIG.iterdir()):
        _validate_docker_config(expected)
        return
    temporary = _DOCKER_CONFIG.parent / (".pair-config-" + uuid.uuid4().hex + ".tmp")
    created = None
    try:
        with temporary.open("xb") as stream:
            value = os.fstat(stream.fileno())
            created = (value.st_dev, value.st_ino)
            stream.write(expected)
            stream.flush()
            os.fsync(stream.fileno())
        _no_reparse(temporary)
        _no_reparse(_DOCKER_CONFIG)
        try:
            # Create-if-absent: never replace a concurrent foreign config.
            os.link(temporary, _DOCKER_CONFIG / "config.json")
        except FileExistsError:
            pass
        _validate_docker_config(expected)
    finally:
        if created is not None:
            value = temporary.lstat()
            if (
                not stat.S_ISREG(value.st_mode)
                or getattr(value, "st_file_attributes", 0) & 0x400
                or (value.st_dev, value.st_ino) != created
            ):
                raise ValueError("bootstrap_config_temp_changed")
            temporary.unlink()


def _launch(command: Sequence[str], root: Path, environment: Mapping[str, str]) -> int:
    if os.name != "nt":
        raise ValueError("bootstrap_windows_required")
    _ordinary_file(Path(command[0]))
    child = subprocess.Popen(
        list(command),
        cwd=root,
        env=dict(environment),
        shell=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return int(child.wait())


def main(argv: Sequence[str] | None = None) -> int:
    parser = _QuietParser(add_help=False, exit_on_error=False)
    parser.add_argument("--execute", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--schedule", action="store_true")
    mode.add_argument("--compose", action="store_true")
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("compose_arguments", nargs=argparse.REMAINDER)
    try:
        args = parser.parse_args(argv)
    except (argparse.ArgumentError, ValueError):
        return 2
    if not args.execute:
        return 0
    try:
        root = _project_root(args.project_root)
        environment = _safe_environment(os.environ)
        if args.schedule and not args.compose_arguments:
            _ordinary_file(root / _SCHEDULE)
            return _launch(
                [
                    str(_POWERSHELL),
                    "-WindowStyle",
                    "Hidden",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(root / _SCHEDULE),
                    "-ProjectRoot",
                    str(root),
                ],
                root,
                environment,
            )
        if not args.compose or args.compose_arguments[:1] != ["--"]:
            raise ValueError("bootstrap_mode_required")
        arguments = args.compose_arguments[1:]
        service = _compose_service(root, arguments)
        _empty_docker_config()
        if service == _COLLECTION:
            try:
                config = _load_paper_config(root)
            except Exception:
                # Let the unchanged collector emit its existing environment-stage receipt.
                config = None
            if config is not None:
                environment["KIS_PAPER_APP_KEY"] = config.app_key
                environment["KIS_PAPER_APP_SECRET"] = config.app_secret
        return _launch([str(_DOCKER), "--host", _LOCAL_ENGINE, *arguments], root, environment)
    except Exception:
        return _RECOVERY_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
