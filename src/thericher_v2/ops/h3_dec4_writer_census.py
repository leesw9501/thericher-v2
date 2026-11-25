"""Dec4 fresh writer census using the pinned read-only R8 collector and classifier."""

import ast
import hashlib
import json
import math
import os
import re
import subprocess
import time
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.ops.h3_dec4_scheduler_provider import (
    _file_stamp,
    _open_locked,
    _path_stamp,
    _unique_object,
    _windows_root,
)

_ROOT = Path("D:/thericher-v2/model-artifacts/execution")
_R8 = _ROOT / "n9h3-control-r8/c1/controller"
_NATIVE = _ROOT / "current-net25-native-descriptor-prewrite-repair-20261105-v1/guard"
_CENSUS = _NATIVE / "census.ps1"
_PROJECT = _NATIVE / "projector.py"
_CLASSIFIER = _R8 / "scoped_native.py"
_SCOPE = _R8 / "scoped_admission.py"
_DOCKER = Path("C:/Program Files/Docker/Docker/resources/bin/docker.exe")
_ENGINE = "npipe:////./pipe/dockerDesktopLinuxEngine"
_PWSH = Path("C:/Program Files/PowerShell/7/pwsh.exe")
_SOURCES = {
    _CENSUS: "bb28405d3765d8014127bf158300f61528d6928f49db139df5db3197b629f215",
    _PROJECT: "fd09aa60580fde7bbe44ba067cca4110fbae637191a3b298a8498bbf67b3a4e4",
    _CLASSIFIER: "4448d2dd3e6cc35c0f318dc216eb651677bc17a1529fce76a260120deb917313",
    _SCOPE: "7ff4e948c751490e217ae4eb985eb74861c4ecf473d1c15e0a1da0fc2898794b",
}
_MAX_REPLY = 4 * 1024 * 1024
_MAX_CONTAINERS = 64
_DOCKER_DRIVES = ("/run/desktop/mnt/host/", "/host_mnt/", "/mnt/")


def _need(ok, code):
    if not ok:
        raise ValueError("h3_writer_census_" + code)


@dataclass(frozen=True, slots=True)
class Dec4CensusProfile:
    claims_path: Path
    claims_sha256: str
    pwsh_sha256: str
    docker_sha256: str
    empty_docker_config: Path
    sensitive: tuple[str, ...]
    protected: tuple[str, ...]
    financial_entries: tuple[str, ...]

    def __post_init__(self):
        _need(
            all(
                isinstance(p, Path) and p.is_absolute()
                for p in (self.claims_path, self.empty_docker_config)
            )
            and all(
                pv._hash(pin) for pin in (self.claims_sha256, self.pwsh_sha256, self.docker_sha256)
            )
            and type(self.financial_entries) is tuple
            and self.financial_entries
            and all(pv._hash(item) for item in self.financial_entries)
            and all(
                type(roots) is tuple and roots and all(type(p) is str and bool(p) for p in roots)
                for roots in (self.sensitive, self.protected)
            ),
            "profile",
        )

    @property
    def sha256(self):
        return pv.digest(
            dict(
                schema="h3-dec4-writer-census-v1",
                claimant=str(self.claims_path),
                claims=self.claims_sha256,
                pwsh=self.pwsh_sha256,
                docker=self.docker_sha256,
                config=str(self.empty_docker_config),
                sensitive=self.sensitive,
                protected=self.protected,
                financial_entries=self.financial_entries,
                sources={str(path): pin for path, pin in _SOURCES.items()},
            )
        )


class _Denied(RuntimeError):
    pass


def _pin(path, digest):
    p = Path(path)
    pv.ordinary(p)
    if not p.is_absolute():
        raise _Denied("source_scope")
    raw = p.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest.removeprefix("sha256:"):
        raise _Denied("source_pin")
    return raw


def _original_need(ok, code):
    if not ok:
        raise _Denied(code)


def _compile(raw, path):
    # Reuse the old collector algorithms without importing its unrelated release.
    tree = ast.parse(raw, filename=str(path))
    bindings = dict(
        Denied=_Denied,
        checked=_pin,
        need=_original_need,
        sha=lambda raw: hashlib.sha256(raw).hexdigest(),
    )
    for item in list(tree.body):
        if isinstance(item, ast.ImportFrom) and item.module == "common":
            _need(all(x.name in bindings and x.asname is None for x in item.names), "source_abi")
            tree.body.remove(item)
    ns = dict(__file__=str(path), __name__="_dec4_pinned_writer_component", **bindings)
    exec(compile(tree, str(path), "exec", dont_inherit=True), ns)
    return SimpleNamespace(**ns)


def _full_member(path, pin, stack):
    stamp = _path_stamp(path)
    handle = stack.enter_context(_open_locked(path))
    _need(stamp == _file_stamp(os.fstat(handle.fileno())), "source_changed")
    if path in (_PWSH, _DOCKER):
        _need(hashlib.file_digest(handle, "sha256").hexdigest() == pin, "source_changed")
        return stamp, None
    raw = handle.read(_MAX_REPLY + 1)
    _need(len(raw) <= _MAX_REPLY and hashlib.sha256(raw).hexdigest() == pin, "source_changed")
    return stamp, raw


def _run(argv, *, cwd, env, deadline):
    left = deadline - time.monotonic()
    _need(left > 0, "time")
    result = subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=cwd,
        env=env,
        timeout=left,
        check=False,
        creationflags=getattr(
            subprocess, "CREATE_NO_WINDOW" if argv[0] == str(_PWSH) else "DETACHED_PROCESS", 0
        ),
    )
    _need(
        result.returncode == 0 and len(result.stdout) <= _MAX_REPLY and time.monotonic() < deadline,
        "native_reply",
    )
    return result.stdout


def _ids(raw):
    ids = raw.decode("ascii").splitlines()
    _need(
        len(ids) <= _MAX_CONTAINERS and all(pv._hash(i) for i in ids) and len(set(ids)) == len(ids),
        "membership",
    )
    return tuple(sorted(ids))


def _json(raw):
    return json.loads(raw, object_pairs_hook=_unique_object)


def _collect(project, claims, invoke, *, host_args, docker_args, own):
    list_args = (*docker_args, "ps", "--quiet", "--no-trunc")
    members = _ids(invoke(list_args))
    host = _json(invoke(host_args))
    _need(
        type(host) is dict
        and host.get("complete") is True
        and type(host.get("actors")) is list
        and host.get("containers") == [],
        "host_unavailable",
    )
    ids = sorted(set(members) | ({own} if own is not None else set()))
    if ids:
        raw = invoke(
            (
                *docker_args,
                "container",
                "inspect",
                "--format",
                project.template(claims["container_rules"]),
                *ids,
            )
        )
        # The pinned projector sanitizes fields, but duplicate JSON keys must
        # be refused before it normalizes the rule matches.
        parsed = [_json(line) for line in raw.splitlines() if line.strip()]
        _need(len(parsed) == len(ids), "container_reply")
        containers = project.parse(raw)
    else:
        containers = []
    _need(
        sorted(row["Id"] for row in containers) == ids
        and all(
            type(row["Running"]) is bool and row["Running"] is (row["Id"] in members)
            for row in containers
        )
        and _ids(invoke(list_args)) == members,
        "membership_changed",
    )
    return host | {"containers": containers}


def _windows_mount(raw):
    _need(type(raw) is str and raw and "\0" not in raw, "mount_alias")
    value = raw.replace("\\", "/")
    for prefix in _DOCKER_DRIVES:
        if value.casefold().startswith(prefix):
            match = re.fullmatch(r"([A-Za-z])(?:/(.*))?", value[len(prefix) :])
            _need(match is not None, "mount_alias")
            value = match[1] + ":/" + (match[2] or "")
            break
    match = re.fullmatch(r"([A-Za-z]):/(.*)", value)
    if match is None:
        return None
    tail = match[2].rstrip("/")
    _need(
        not any(
            part in {"", ".", ".."} or part.endswith((" ", ".")) or ":" in part
            for part in tail.split("/")
            if tail
        ),
        "mount_alias",
    )
    return match[1].casefold() + ":/" + tail


def _aliases(roots):
    aliases = set(roots)
    for root in roots:
        mapped = _windows_mount(root)
        if mapped is not None:
            aliases.add(mapped)
            aliases.update(prefix + mapped[0] + "/" + mapped[3:] for prefix in _DOCKER_DRIVES)
    return tuple(sorted(aliases))


def _foreign_writable_binds(facts, own):
    identities = {}
    for row in facts["containers"]:
        if row["Id"] == own:
            continue
        for mount in row["Mounts"]:
            if mount["Type"] != "bind" or mount["RW"] is not True:
                continue
            mapped = _windows_mount(mount["Source"])
            _need(mapped is not None, "mount_alias")
            path = Path(mapped)
            pv.ordinary(path)
            _need(path.is_absolute() and path.resolve(strict=True) == path, "mount_alias")
            stat = path.lstat()
            identities[path] = (stat.st_dev, stat.st_ino)
    return identities


class Dec4WriterCensus:
    """Retain source locks and run the existing scope decision on one fresh sample."""

    def __init__(self, profile):
        _need(type(profile) is Dec4CensusProfile, "profile")
        self.profile = profile

    def evaluate(self, *, own, deadline, bind_owned, exact_scope):
        try:
            return self._evaluate(own, deadline, bind_owned, exact_scope)
        except Exception:
            # Never expose raw host arguments, mount paths or child output.
            raise ValueError("h3_writer_census_not_admitted") from None

    def _evaluate(self, own, deadline, bind_owned, exact_scope):
        p = self.profile
        _need(
            type(deadline) in (int, float)
            and math.isfinite(deadline)
            and (own is None or pv._hash(own)),
            "effect_scope",
        )
        deadline = min(deadline, time.monotonic() + 8.0)
        root = _windows_root()
        pv.ordinary(p.empty_docker_config)
        _need(p.empty_docker_config.is_dir() and not any(p.empty_docker_config.iterdir()), "config")
        config_stat = p.empty_docker_config.stat()
        env = dict(
            SystemRoot=str(root),
            WINDIR=str(root),
            TEMP=str(root / "Temp"),
            TMP=str(root / "Temp"),
            DOCKER_CONFIG=str(p.empty_docker_config),
        )
        files = _SOURCES | {
            _PWSH: p.pwsh_sha256,
            _DOCKER: p.docker_sha256,
            p.claims_path: p.claims_sha256,
        }
        with ExitStack() as stack:
            data = {path: _full_member(path, pin, stack) for path, pin in files.items()}
            claims = _json(data[p.claims_path][1])
            _need(
                type(claims) is dict
                and type(claims["host_rules"]) is list
                and type(claims["container_rules"]) is list,
                "claims",
            )
            project, native, scope = (
                _compile(data[path][1], path) for path in (_PROJECT, _CLASSIFIER, _SCOPE)
            )

            def invoke(args):
                return _run(args, cwd=root / "System32", env=env, deadline=deadline)

            facts = _collect(
                project,
                claims,
                invoke,
                own=own,
                docker_args=(str(_DOCKER), "--host", _ENGINE),
                host_args=(
                    str(_PWSH),
                    "-NoProfile",
                    "-NonInteractive",
                    "-File",
                    str(_CENSUS),
                    "-ClaimsPath",
                    str(p.claims_path),
                    "-ClaimsSha256",
                    p.claims_sha256,
                ),
            )
            owned = bind_owned(facts)
            binds = _foreign_writable_binds(facts, own)
            result = scope.decide(
                facts,
                claims,
                owned,
                native=native,
                sensitive=_aliases(p.sensitive),
                protected=_aliases(p.protected),
                financial_entries=p.financial_entries,
                own_container=own,
                own_scope=exact_scope,
            )
            pv.ordinary(p.empty_docker_config)
            config_after = p.empty_docker_config.stat()
            _need(
                result["status"] == "NO_CURRENT_PRIVATE_CUSTODY_WRITER_OBSERVED"
                and bind_owned(facts) == owned
                and _foreign_writable_binds(facts, own) == binds
                and all(_path_stamp(path) == pair[0] for path, pair in data.items())
                and (config_stat.st_dev, config_stat.st_ino, config_stat.st_mtime_ns)
                == (config_after.st_dev, config_after.st_ino, config_after.st_mtime_ns)
                and not any(p.empty_docker_config.iterdir())
                and time.monotonic() < deadline,
                "decision",
            )
            return True
