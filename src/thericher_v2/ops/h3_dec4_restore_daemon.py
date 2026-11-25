"""Read-only Dec4 observer restore probe for the original daemon and capsule."""

import hashlib
import re
import time
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.ops.h3_dec4_scheduler_provider import _path_stamp, _windows_root
from thericher_v2.ops.h3_dec4_writer_census import (
    _DOCKER,
    _ENGINE,
    _full_member,
    _ids,
    _run,
)

_DAEMON_ID = re.compile(rb"[a-zA-Z0-9:_-]{12,128}")
_LIMIT_SECONDS = 3.0


def _require(ok):
    if not ok:
        raise ValueError("h3_restore_daemon_closure_unknown")


def _daemon_pin(raw):
    value = raw.strip()
    _require(type(value) is bytes and _DAEMON_ID.fullmatch(value) is not None)
    return hashlib.sha256(value).hexdigest()


def _probe(invoke, pin, record):
    info = ("info", "--format", "{{.ID}}")
    _require(_daemon_pin(invoke(info)) == pin)
    for visit in record["visits"]:
        cid = visit["create"]["cid"]
        _require(visit["status"] == "CLOSED" and pv._hash(cid) and pv._run(visit["run"]))
        # Include stopped containers. Check both the ACKed CID and a recreated
        # container carrying the exact ownership labels, independent of its CID.
        list_all = ("ps", "--all", "--quiet", "--no-trunc")
        _require(not _ids(invoke((*list_all, "--filter", "id=" + cid))))
        _require(
            not _ids(
                invoke(
                    (
                        *list_all,
                        "--filter",
                        "label=thericher.single_owner.visit=" + visit["run"],
                        "--filter",
                        "label=thericher.single_owner.source=" + record["identity"]["source"],
                    )
                )
            )
        )
    _require(_daemon_pin(invoke(info)) == pin)
    return True


@dataclass(frozen=True, slots=True, repr=False)
class Dec4RestoreDaemon:
    """Source-pinned native observer verification, not writer exclusion."""

    docker_sha256: str
    daemon_id_sha256: str
    empty_docker_config: Path

    def __post_init__(self):
        _require(
            pv._hash(self.docker_sha256)
            and pv._hash(self.daemon_id_sha256)
            and isinstance(self.empty_docker_config, Path)
            and self.empty_docker_config.is_absolute()
        )

    @property
    def sha256(self):
        return pv.digest(
            {
                "schema": "h3-dec4-restore-daemon-v1",
                "engine": _ENGINE,
                "docker_sha256": self.docker_sha256,
                "daemon_id_sha256": self.daemon_id_sha256,
                "config": str(self.empty_docker_config),
            }
        )

    def check(self, *, bank, record):
        try:
            return self._check(bank, record)
        except Exception:
            raise ValueError("h3_restore_daemon_closure_unknown") from None

    def _check(self, bank, record):
        _require(pv.canonical_bank(_ENGINE, bank["volume"]) == bank)
        pv._record(record, pv.bank_key(bank))
        _require(len(record["visits"]) <= 1)
        deadline = time.monotonic() + _LIMIT_SECONDS
        config = self.empty_docker_config
        root = _windows_root()

        def config_stamp():
            pv.ordinary(config)
            _require(config.is_dir() and not any(config.iterdir()))
            info = config.stat()
            return info.st_dev, info.st_ino, info.st_mtime_ns

        before = config_stamp()
        env = {
            "SystemRoot": str(root),
            "WINDIR": str(root),
            "TEMP": str(root / "Temp"),
            "TMP": str(root / "Temp"),
            "DOCKER_CONFIG": str(config),
        }
        with ExitStack() as stack:
            stamp, _ = _full_member(_DOCKER, self.docker_sha256, stack)

            def invoke(args):
                return _run(
                    (str(_DOCKER), "--host", _ENGINE, *args),
                    cwd=root / "System32",
                    env=env,
                    deadline=deadline,
                )

            result = _probe(invoke, self.daemon_id_sha256, record)
            _require(
                _path_stamp(_DOCKER) == stamp
                and config_stamp() == before
                and time.monotonic() < deadline
            )
        return result
