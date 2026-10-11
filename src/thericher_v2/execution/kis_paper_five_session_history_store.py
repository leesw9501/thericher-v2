"""Private append-only application custody, not a broker or fill ledger.

Only fixed metadata/read DTOs can be restored. Historical bootstrap is caller-
attested retrospective custody; newly prepared seeds are retained before reserve.
The caller holds this store's canonical writer lock across dispatch. No I/O occurs
at import or construction, and no credential/configuration object is serializable.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass, fields
from datetime import datetime
from decimal import ROUND_FLOOR, Context, Decimal, localcontext
from pathlib import Path

from thericher_v2.contracts import TargetExposureProposal, require_utc
from thericher_v2.research.decision_receipt import ResearchDecisionReceipt
from thericher_v2.research.five_session_paper_decision import FiveSessionPaperDecision

from . import kis_paper_budget_strategy as budget
from .kis_paper_canary import exclusive_kis_paper_canary_state_lock
from .kis_paper_five_session import (
    KisPaperFiveSessionCohort,
    KisPaperFiveSessionCustody,
    cohort_from_paper_decision,
)
from .kis_paper_five_session_successor import KisPaperFiveSessionHistory
from .kis_paper_portfolio_budget import KisPaperPortfolioStateRef
from .kis_paper_quote import KisPaperSpyLimitInput
from .kis_paper_stock_quote import KisPaperStockInstrument
from .kis_paper_stock_readonly import (
    KisPaperStockExitAccountSnapshot,
    KisPaperStockExitReads,
    KisPaperStockPreviewReads,
)
from .kis_readonly import (
    KisPaperAccountIdentity,
    KisPaperCashSnapshot,
    KisPaperOpenOrder,
    KisPaperOpenOrdersSnapshot,
    KisPaperOrderableFundsSnapshot,
    KisPaperPosition,
    KisPaperReadOnlySnapshot,
)

_TYPES = {
    t.__name__: t
    for t in (
        TargetExposureProposal,
        ResearchDecisionReceipt,
        KisPaperFiveSessionCohort,
        KisPaperFiveSessionCustody,
        KisPaperFiveSessionHistory,
        KisPaperPortfolioStateRef,
        KisPaperSpyLimitInput,
        KisPaperStockInstrument,
        KisPaperStockPreviewReads,
        KisPaperStockExitReads,
        KisPaperStockExitAccountSnapshot,
        KisPaperAccountIdentity,
        KisPaperCashSnapshot,
        KisPaperOpenOrder,
        KisPaperOpenOrdersSnapshot,
        FiveSessionPaperDecision,
        KisPaperOrderableFundsSnapshot,
        KisPaperPosition,
        KisPaperReadOnlySnapshot,
    )
}
_NAME = re.compile(r"[0-9]{8}\.json", re.ASCII)
_PIN = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)


class FiveSessionHistoryError(ValueError):
    """Always static; arbitrary decoder or filesystem exception text is not exposed."""


def _check(ok: bool) -> None:
    if not ok:
        raise FiveSessionHistoryError("history_store_invalid")


def _encode(value):
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        _check(math.isfinite(value))
        return value
    if type(value) is Decimal:
        _check(value.is_finite())
        return {"decimal": str(value)}
    if type(value) is datetime:
        return {"utc": require_utc(value).isoformat()}
    if type(value) in _TYPES.values():
        return {
            "dto": type(value).__name__,
            "fields": {f.name: _encode(getattr(value, f.name)) for f in fields(value)},
        }
    if type(value) in (tuple, list):
        return {"tuple" if type(value) is tuple else "list": [_encode(v) for v in value]}
    if isinstance(value, Mapping):
        _check(all(type(k) is str for k in value))
        return {"map": {k: _encode(v) for k, v in value.items()}}
    raise FiveSessionHistoryError("history_store_invalid")


def _decode(value, depth=0):
    _check(depth < 40)
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        _check(math.isfinite(value))
        return value
    _check(type(value) is dict)
    if set(value) == {"decimal"}:
        out = Decimal(value["decimal"])
        _check(out.is_finite())
        return out
    if set(value) == {"utc"}:
        return require_utc(datetime.fromisoformat(value["utc"]))
    if set(value) == {"dto", "fields"}:
        cls = _TYPES.get(value["dto"])
        _check(cls is not None and type(value["fields"]) is dict)
        _check(set(value["fields"]) == {f.name for f in fields(cls)})
        return cls(**{k: _decode(v, depth + 1) for k, v in value["fields"].items()})
    if set(value) == {"map"}:
        _check(type(value["map"]) is dict)
        return {k: _decode(v, depth + 1) for k, v in value["map"].items()}
    for tag, cls in (("tuple", tuple), ("list", list)):
        if set(value) == {tag}:
            _check(type(value[tag]) is list)
            return cls(_decode(v, depth + 1) for v in value[tag])
    raise FiveSessionHistoryError("history_store_invalid")


def _unique(pairs):
    out = {}
    for key, value in pairs:
        _check(key not in out)
        out[key] = value
    return out


def _digest(payload) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _plain(path: Path) -> None:
    for part in (path, *path.parents):
        _check(not part.is_symlink() and not part.is_junction())


@dataclass(frozen=True, slots=True, repr=False)
class FiveSessionHistoryJournal:
    anchor: Mapping
    history: tuple[KisPaperFiveSessionHistory, ...]
    pending: Mapping | None
    head_ref: str | None
    record_count: int
    decisions: Mapping[str, FiveSessionPaperDecision]
    bootstrap_history: tuple[KisPaperFiveSessionHistory, ...]


class KisPaperFiveSessionHistoryStore:
    """A new private root outside repository/evidence; no canonical bank writes.

    ``locked`` serializes this runtime's callers only. It does not claim to lock
    legacy/native writers; canonical reserve/execute still use their own locks.
    """

    def __init__(self, root: Path, *, repository_root: Path, artifact_root: Path):
        self.root = Path(root)
        self.repository_root = Path(repository_root)
        self.artifact_root = Path(artifact_root)
        self._held = False

    def __repr__(self) -> str:
        return "KisPaperFiveSessionHistoryStore()"

    @contextmanager
    def locked(self):
        _check(not self._held and self.root.is_absolute())
        _plain(self.root)
        _check(not self.root.resolve().is_relative_to(self.repository_root.resolve()))
        _check(not self.root.resolve().is_relative_to(self.artifact_root.resolve()))
        try:
            budget._validate_paths(self.root.resolve(), self.repository_root, self.artifact_root)
        except Exception:
            raise FiveSessionHistoryError("history_store_invalid") from None
        self.root.mkdir(parents=True, exist_ok=True)
        _plain(self.root / ".history.lock")
        with exclusive_kis_paper_canary_state_lock(self.root / "history"):
            self._held = True
            try:
                yield self
            finally:
                self._held = False

    def read(self) -> FiveSessionHistoryJournal:
        _check(self._held)
        _plain(self.root)
        names = sorted(p.name for p in self.root.iterdir() if p.name != ".history.lock")
        _check(len(names) <= 10000)
        _check(names == [f"{i:08d}.json" for i in range(len(names))])
        anchor, history, pending, previous, decisions, bootstrap_history = (
            {},
            (),
            None,
            None,
            {},
            (),
        )
        try:
            with localcontext(Context(prec=64, rounding=ROUND_FLOOR)):
                for index, name in enumerate(names):
                    path = self.root / name
                    _check(_NAME.fullmatch(name) is not None)
                    _plain(path)
                    _check(path.is_file() and path.stat().st_size <= 4_000_000)
                    raw = json.loads(path.read_bytes(), object_pairs_hook=_unique)
                    _check(set(raw) == {"kind", "index", "previous", "payload", "ref"})
                    body = {k: v for k, v in raw.items() if k != "ref"}
                    _check(raw["index"] == index and type(raw["index"]) is int)
                    _check(raw["previous"] == previous and raw["ref"] == _digest(body))
                    data = _decode(raw["payload"])
                    if index == 0:
                        _check(raw["kind"] == "bootstrap" and set(data) == {"anchor", "history"})
                        anchor, history = data["anchor"], data["history"]
                        bootstrap_history = history
                        _validate_history(history)
                    elif raw["kind"] == "prepared":
                        _check(pending is None and data["before"] == history)
                        _validate_transition(data)
                        pending = data
                        if data["decision"] is not None:
                            decisions[data["after"][-1].cohort.fingerprint] = data["decision"]
                    elif raw["kind"] == "aborted_unreserved":
                        _check(
                            pending is not None
                            and set(data) == {"prepared_ref", "binding_ref", "as_of"}
                        )
                        _check(
                            data["prepared_ref"] == previous
                            and _PIN.fullmatch(data["binding_ref"]) is not None
                        )
                        require_utc(data["as_of"])
                        pending = None
                    else:
                        _check(raw["kind"] == "committed" and pending is not None)
                        _check(data == {"prepared_ref": previous})
                        history, pending = pending["after"], None
                    previous = raw["ref"]
        except FiveSessionHistoryError:
            raise
        except Exception:
            raise FiveSessionHistoryError("history_store_invalid") from None
        return FiveSessionHistoryJournal(
            anchor, history, pending, previous, len(names), decisions, bootstrap_history
        )

    def bootstrap(self, anchor: Mapping, history: tuple) -> FiveSessionHistoryJournal:
        journal = self.read()
        _validate_history(history)
        if journal.record_count:
            _check(journal.anchor == anchor)
            _check(journal.bootstrap_history == history)
            return journal
        return self._append("bootstrap", {"anchor": anchor, "history": history}, journal)

    def prepare(self, transition: Mapping) -> FiveSessionHistoryJournal:
        journal = self.read()
        _validate_transition(transition)
        _check(journal.record_count > 0 and transition["before"] == journal.history)
        if journal.pending is not None:
            _check(journal.pending == transition)
            return journal
        return self._append("prepared", transition, journal)

    def commit(self, prepared_ref: str) -> FiveSessionHistoryJournal:
        journal = self.read()
        _check(journal.pending is not None and journal.head_ref == prepared_ref)
        return self._append("committed", {"prepared_ref": prepared_ref}, journal)

    def abort_unreserved(
        self, prepared_ref: str, *, binding_ref: str, as_of: datetime
    ) -> FiveSessionHistoryJournal:
        """Retain unused staged bytes; caller verifies exact canonical absence.

        Scoped unreserved application custody, never an independent broker
        no-wire observation. Registered or ambiguous requests cannot use it.
        """
        journal = self.read()
        _check(journal.pending is not None and journal.head_ref == prepared_ref)
        _check(_PIN.fullmatch(binding_ref) is not None)
        return self._append(
            "aborted_unreserved",
            {
                "prepared_ref": prepared_ref,
                "binding_ref": binding_ref,
                "as_of": require_utc(as_of),
            },
            journal,
        )

    def _append(self, kind, payload, journal):
        _check(self._held)
        body = {
            "kind": kind,
            "index": journal.record_count,
            "previous": journal.head_ref,
            "payload": _encode(payload),
        }
        record = body | {"ref": _digest(body)}
        path = self.root / f"{journal.record_count:08d}.json"
        _plain(path)
        _check(not path.exists())
        budget._atomic_json(path, record)
        result = self.read()
        _check(result.head_ref == record["ref"])
        return result


def _validate_history(history):
    _check(type(history) is tuple and all(type(h) is KisPaperFiveSessionHistory for h in history))


def _validate_transition(value):
    _check(
        isinstance(value, Mapping)
        and set(value) == {"before", "after", "side", "arguments", "row", "plan_ref", "decision"}
    )
    _validate_history(value["before"])
    _validate_history(value["after"])
    _check(value["side"] in {"buy", "sell"})
    _check(value["decision"] is None or type(value["decision"]) is FiveSessionPaperDecision)
    _check(isinstance(value["arguments"], Mapping) and isinstance(value["row"], Mapping))
    _check(type(value["plan_ref"]) is str and _PIN.fullmatch(value["plan_ref"]) is not None)
    _check(value["plan_ref"] == "sha256:" + budget._digest(value["row"]))
    before, after = value["before"], value["after"]
    if value["side"] == "buy":
        _check(len(after) == len(before) + 1 and after[:-1] == before)
        if value["decision"] is not None:
            cohort = after[-1].cohort
            _check(
                cohort_from_paper_decision(value["decision"], calendar_ref=cohort.calendar_ref)
                == cohort
            )
            _check(
                value["arguments"].get("proposal") == value["decision"].proposal
                and value["arguments"].get("receipt") == value["decision"].receipt
            )
    else:
        _check(len(after) == len(before) and len(after) > 0)
        changed = [i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b]
        _check(len(changed) == 1)
        old, new = before[changed[0]], after[changed[0]]
        _check(old.cohort == new.cohort and old.input_ref == new.input_ref)
        _check(old.custody.entry == new.custody.entry)
        _check(new.custody.exits[:-1] == old.custody.exits)
        _check(len(new.custody.exits) == len(old.custody.exits) + 1)
        _check(new.plan_refs[:-1] == old.plan_refs)
