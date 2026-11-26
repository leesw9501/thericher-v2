"""Hold the source-bound retirement roster and recheck custody under the bank gate."""

import os
import sys
import time
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.ops.h3_dec4_scheduler_provider import _path_stamp, _windows_root
from thericher_v2.ops.h3_dec4_writer_census import (
    _PWSH,
    Dec4CensusProfile,
    Dec4WriterCensus,
    _full_member,
    _json,
    _run,
)
from thericher_v2.ops.h3_dec4_writer_identity import _EPOCH, read_windows_actor

_RETIRED = frozenset(
    (
        r"\thericher-net25-lstm-h3-nov9-entry-20261109-v1",
        r"\thericher-net25-lstm-h3-nov9-owned-exit-20261112-v1",
    )
)


def _norm(path):
    return str(path).replace("\\", "/").casefold().rstrip("/")


@dataclass(frozen=True, slots=True, repr=False)
class Dec4RestoreWriterGuard:
    census: Dec4WriterCensus
    helper: Path
    helper_sha256: str
    roster: Path
    roster_sha256: str
    gate_root: Path
    bank_key: str
    bank_volume: str

    def __post_init__(self):
        pv._need(
            type(self.census) is Dec4WriterCensus
            and type(self.census.profile) is Dec4CensusProfile
            and all(
                isinstance(path, Path) and path.is_absolute()
                for path in (self.helper, self.roster, self.gate_root)
            )
            and self.helper.name == "read_h3_restore_retired_writers.ps1"
            and all(
                pv._hash(pin) for pin in (self.helper_sha256, self.roster_sha256, self.bank_key)
            )
            and {_norm(self.gate_root), _norm(self.bank_volume)}
            <= {_norm(item) for item in self.census.profile.protected}
            and (
                self.census.profile.monitor is None
                or self.census.profile.monitor.bank_volume == self.bank_volume
            ),
            "h3_restore_writer_scope",
        )

    @property
    def sha256(self):
        return pv.digest(
            dict(
                schema="h3-restore-writer-guard-v1",
                census=self.census.profile.sha256,
                helper=str(self.helper),
                helper_sha256=self.helper_sha256,
                roster=str(self.roster),
                roster_sha256=self.roster_sha256,
                gate_root=str(self.gate_root),
                bank=self.bank_key,
                volume=self.bank_volume,
            )
        )

    @contextmanager
    def hold(self, record, *, deadline):
        """The caller must hold the original bank gate during each returned check.

        The qualified release owns the completeness of the gate/retirement roster.
        Neither this object nor a process sample fences an unregistered writer.
        """
        pv._record(record, self.bank_key)
        pv._need(deadline > datetime.now(UTC), "h3_restore_writer_deadline")
        pid = os.getpid()
        actor = read_windows_actor(pid)
        pv._need(
            actor.pid == pid
            and pid != record["owner"]["pid"]
            and _norm(actor.image) == _norm(sys.executable)
            and actor.parsed_argv_sha256 == pv.digest(list(sys.orig_argv)),
            "h3_restore_writer_self_unbound",
        )
        cap = time.monotonic() + (deadline - datetime.now(UTC)).total_seconds()

        def bind_self(facts):
            rows = [row for row in facts.get("actors", ()) if row.get("pid") == pid]
            pv._need(
                len(rows) == 1 and read_windows_actor(pid) == actor,
                "h3_restore_writer_self_unbound",
            )
            row = rows[0]
            ticks = str(row["start_ticks"])
            epoch = int(actor.filetime) + _EPOCH
            pv._need(
                row["argv_sha256"] == actor.raw_command_sha256
                and ticks in {str(epoch), str(epoch // 10 * 10)},
                "h3_restore_writer_self_unbound",
            )
            return frozenset(((pid, ticks, actor.raw_command_sha256),))

        with self._retirement(cap) as retired:

            def check():
                return (
                    retired()
                    and self.census.evaluate(
                        own=None, deadline=cap, bind_owned=bind_self, exact_scope=None
                    )
                    is True
                    and datetime.now(UTC) < deadline
                    and time.monotonic() < cap
                )

            yield check

    def retirement_ready(self):
        """Refuse to arm if a known retired writer could still start."""
        with self._retirement(time.monotonic() + 2.5) as check:
            return check()

    @contextmanager
    def _retirement(self, cap):
        root = _windows_root()
        env = dict(
            SystemRoot=str(root), WINDIR=str(root), TEMP=str(root / "Temp"), TMP=str(root / "Temp")
        )
        expected = dict(
            schema="h3-restore-retired-writers-proof-v1",
            profile_sha256=self.roster_sha256,
            retired=True,
        )
        with ExitStack() as stack:
            inputs = {
                _PWSH: self.census.profile.pwsh_sha256,
                self.helper: self.helper_sha256,
                self.roster: self.roster_sha256,
            }
            locked = {path: _full_member(path, pin, stack) for path, pin in inputs.items()}
            paths = [row["path"] for row in _json(locked[self.roster][1])["tasks"]]
            pv._need(_RETIRED <= set(paths), "h3_restore_retirement_roster_incomplete")

            def check():
                argv = (
                    str(_PWSH),
                    "-NoProfile",
                    "-NonInteractive",
                    "-File",
                    str(self.helper),
                    "-ProfilePath",
                    str(self.roster),
                    "-ProfileSha256",
                    self.roster_sha256,
                )
                proof = _json(_run(argv, cwd=root / "System32", env=env, deadline=cap))
                return (
                    pv._same(proof, expected)
                    and time.monotonic() < cap
                    and all(_path_stamp(path) == value[0] for path, value in locked.items())
                )

            yield check
