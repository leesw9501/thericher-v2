"""Use the existing exact dashboard scope inside each bounded H20 census."""

import ast
import json
import stat
from hashlib import sha256
from pathlib import Path

from thericher_v2.execution.paper_peer_visit import _read
from thericher_v2.ops.h20_phase_host import _need, _strict_json

_BASE = Path("D:/thericher-v2/model-artifacts/execution")
_MONITOR = _BASE / "current-paper-monitor-admission-repair-20261102-v1"
_LINEAGE = _BASE / "current-paper-operational-lineage-repair-20261103-v1"
_ADOPTION = _LINEAGE / "adoption_unchanged.py"
_SOURCE_PIN = "38ee7a96b1dedf6e54bd1e0033f2cdc1dabff9c2aee2fc5d10d769e3d04d7749"
_WEB_PIN = "e07a569fa2c181718b224ab8d83edc57e61b3027badb6f95749eb165a7514716"
_BASE_PIN = "54b4d61409261590df257b9c17f77c21232dff9abfb2d9b6fcbf0ac79b9651c9"
_CLAIMS_PIN = "65cb0225c53295e857e7c8e16be8487ed7ff15ebe0e2135a424a182fb3c2b97f"
_HEADROOM_PIN = "e4ea9123c9238e0d4b59f8ff0c0728572bf56904f035ba196278d0ac52a17b4f"
_WRITER = _LINEAGE / "h20/entry/launch.py"
_WRITER_PATH_PIN = "dd4abfdbaed5476827b8089c5c7a54e0b55c68f120cc44a7694b04ae565bb57c"
_WEB_ENV = {"PATH", "PYTHONPATH", "THERICHER_MODE", "THERICHER_OPERATIONS_ROOT"}


def bind_h20_web_census(configured, binding):
    """Install source-only wrappers; all actual subprocesses use ns['call']."""
    snapshots = {}

    def pinned(path, expected):
        snapshot = _read(path)
        _need(snapshots.setdefault(path, snapshot) == snapshot)
        _need(sha256(snapshot[0]).hexdigest() == expected)
        return snapshot[0]

    base = _strict_json(pinned(_MONITOR / "h20/reader/BINDING.json", _BASE_PIN))
    claims_path = _MONITOR / "H20-READER-CLAIMS.json"
    claims = _strict_json(pinned(claims_path, _CLAIMS_PIN))
    headroom_path = _MONITOR / "h20/reader/HEADROOM-SOURCE.json"
    pinned(headroom_path, _HEADROOM_PIN)
    desc_path = _MONITOR / "WEB-DESCRIPTOR.json"
    descriptor = _strict_json(pinned(desc_path, _WEB_PIN))
    raw = pinned(_ADOPTION, _SOURCE_PIN)
    ns = configured.namespace
    _need(
        binding["claims"] == base["claims"]
        and binding["headroom_source"] == base["headroom_source"]
        and Path(binding["headroom_source"]["path"]) == headroom_path
        and Path(ns["SOURCE"]["claims_path"]) == claims_path
        and ns["SOURCE"]["claims_sha256"] == _CLAIMS_PIN
        and ns["CLAIMS"] == claims
        and set(descriptor["critical_environment"]) == _WEB_ENV
    )
    required_writers = {ns["SCOPED"].financial_entry_hash(p) for p in base["financial_entry_paths"]}
    _need(
        ns["SCOPED"].financial_entry_hash(_WRITER) == _WRITER_PATH_PIN
        and required_writers | {_WRITER_PATH_PIN} <= ns["SOURCE"]["financial_entry_hashes"]
    )

    def descriptor_bytes(path):
        _need(path == desc_path)
        return pinned(path, _WEB_PIN)

    def volumes():
        raw = ns["call"](scope["volume_argv"](), 8)
        _need(type(raw) is bytes and 0 < len(raw) <= 4096)
        return [_strict_json(line) for line in raw.splitlines() if line.strip()]

    # Load just the already qualified metadata helpers, never launch/adoption code.
    functions = {
        "need",
        "ordinary",
        "volume_argv",
        "physical_web",
        "ExactWebProjection",
        "ExactWebAdmission",
    }
    constants = {"IMAGE", "PUBLIC", "VOLUMES", "DOCKER", "ENGINE"}
    tree = ast.parse(raw)
    body = [
        node
        for node in tree.body
        if (isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in functions)
        or (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in constants
        )
    ]
    _need(len(body) == len(functions) + len(constants))
    scope = dict(
        Path=Path,
        stat=stat,
        json=json,
        BASE=_MONITOR,
        STATE={},
        checked=descriptor_bytes,
        volumes=volumes,
    )
    exec(compile(ast.Module(body, []), "<pinned H20 web census>", "exec"), scope)
    _need(scope["IMAGE"] == descriptor["image"])
    ns["PROJECTOR"] = scope["ExactWebProjection"](ns["PROJECTOR"])
    ns["ADMISSION"] = scope["ExactWebAdmission"](ns["ADMISSION"])
    previous = configured.fresh

    def fresh(**kwargs):
        _need(all(_read(path) == expected for path, expected in snapshots.items()))
        _need(previous(**kwargs) is True)
        _need(all(_read(path) == expected for path, expected in snapshots.items()))
        return True

    configured.fresh = fresh
