"""Private first-choice input custody, persisted before native intent preparation.

The digest checks canonical consistency on the assumed-honest host, not
authentication. Closed-session ownership and input loading remain caller-owned.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from thericher_v2.contracts import require_utc
from thericher_v2.research.cross_asset_etf_input import CrossAssetSession

from . import kis_paper_budget_strategy as budget
from . import kis_paper_portfolio_budget as proofs
from . import kis_paper_portfolio_control_input as control
from .kis_paper_canary import exclusive_kis_paper_canary_state_lock
from .kis_paper_portfolio_execute import _unlinked

_BINDING_KEYS = {f.name for f in fields(control.KisPaperPortfolioControlInputBinding)}
_KEYS = {
    "version",
    "session_id",
    "account_ref",
    "basis_ref",
    "owner_refs",
    "binding_ref",
    "binding",
    "sessions",
    "helper_sha256",
    "expected_calendar_sha256",
    "frozen_at",
    "digest",
}


class KisPaperPortfolioSessionInputError(ValueError):
    """Categorical failure scoped to this checkpoint, with no private values."""

    def __init__(self, reason_code: str):
        self.reason_code = reason_code
        super().__init__(reason_code)


def _check(value, reason="session_input_invalid"):
    if not value:
        raise KisPaperPortfolioSessionInputError(reason)


@dataclass(frozen=True, repr=False)
class KisPaperPortfolioSessionInput:
    binding: control.KisPaperPortfolioControlInputBinding
    sessions: tuple[CrossAssetSession, ...]
    helper_sha256: str
    expected_calendar_sha256: str
    frozen_at: datetime
    session_id: str
    account_ref: str
    basis_ref: str
    owner_refs: Mapping[str, str]
    binding_ref: str
    checkpoint_ref: str
    resumed: bool

    def safe_payload(self) -> dict[str, object]:
        return dict(
            kind="kis_paper_portfolio_session_input_v1",
            status="retained",
            resumed=self.resumed,
            session_count=len(self.sessions),
            owner_count=len(self.owner_refs),
            retained_binding_file_count=3,
            new_submits=0,
            integrity="canonical_digest_not_authentication",
        )


def _identity(session, account, basis):
    _check(
        type(session) is str and budget._QQQ_ENTRY_REQUEST_ID.fullmatch(session),
        "session_input_identity_invalid",
    )
    _check(
        type(account) is str and proofs._ACCOUNT.fullmatch(account),
        "session_input_identity_invalid",
    )
    _check(type(basis) is str and proofs._HASH.fullmatch(basis), "session_input_identity_invalid")
    return budget._digest([account, basis, session])


def _decode(value, identity, resumed):
    _check(
        type(value) is dict
        and set(value) == _KEYS
        and type(value["version"]) is int
        and value["version"] == 1
    )
    _check(
        _identity(value["session_id"], value["account_ref"], value["basis_ref"]) == identity,
        "session_input_identity_conflict",
    )
    _check(
        value["digest"]
        == "sha256:" + budget._digest({k: v for k, v in value.items() if k != "digest"}),
        "session_input_digest_invalid",
    )
    owners = value["owner_refs"]
    _check(
        type(owners) is dict
        and bool(owners)
        and all(
            type(k) is str
            and proofs._IDENTIFIER.fullmatch(k)
            and type(v) is str
            and proofs._HASH.fullmatch(v)
            for k, v in owners.items()
        )
    )
    _check(
        all(
            type(value[k]) is str and proofs._HASH.fullmatch(value[k])
            for k in ("binding_ref", "helper_sha256", "expected_calendar_sha256")
        )
    )
    b = value["binding"]
    _check(type(b) is dict and set(b) == _BINDING_KEYS)
    for key, v in b.items():
        _check(type(v) is str and bool(v))
        if key.endswith("_sha256"):
            _check(proofs._HASH.fullmatch(v))
        else:
            path = PurePosixPath(v)
            _check(
                "\\" not in v
                and ":" not in v
                and not path.is_absolute()
                and str(path) == v
                and all(p not in {".", ".."} for p in path.parts)
            )
    _check(type(value["sessions"]) is list and len(value["sessions"]) == 253)
    _check(
        all(
            type(s) is dict and set(s) == {"date", "open_at", "close_at"} for s in value["sessions"]
        )
    )
    sessions = tuple(
        CrossAssetSession(
            date.fromisoformat(s["date"]),
            datetime.fromisoformat(s["open_at"]),
            datetime.fromisoformat(s["close_at"]),
        )
        for s in value["sessions"]
    )
    _check([s.session_date for s in sessions] == sorted({s.session_date for s in sessions}))
    at = require_utc(datetime.fromisoformat(value["frozen_at"]))
    _check(all(s.close_at <= at for s in sessions))
    _check(_sessions(sessions) == value["sessions"] and at.isoformat() == value["frozen_at"])
    return KisPaperPortfolioSessionInput(
        control.KisPaperPortfolioControlInputBinding(**b),
        sessions,
        value["helper_sha256"],
        value["expected_calendar_sha256"],
        at,
        value["session_id"],
        value["account_ref"],
        value["basis_ref"],
        MappingProxyType(dict(owners)),
        value["binding_ref"],
        value["digest"],
        resumed,
    )


def _sessions(sessions):
    _check(
        type(sessions) is tuple
        and len(sessions) == 253
        and all(type(s) is CrossAssetSession for s in sessions)
    )
    for s in sessions:
        s.__post_init__()
    return [
        dict(
            date=s.session_date.isoformat(),
            open_at=s.open_at.isoformat(),
            close_at=s.close_at.isoformat(),
        )
        for s in sessions
    ]


def _read(path):
    value = budget._read_json(path)
    if value is not None:
        raw = path.read_bytes()
        _check(control._json(raw) == value, "session_input_mutated")
        _check(
            raw == json.dumps(value, sort_keys=True, separators=(",", ":")).encode(),
            "session_input_encoding_invalid",
        )
    return value


def freeze_or_load_kis_paper_portfolio_session_input(
    *,
    state_root: Path,
    session_id: str,
    expected_account_ref: str,
    expected_basis_ref: str,
    expected_owner_refs: Mapping[str, str],
    expected_binding_ref: str,
    input_binding: control.KisPaperPortfolioControlInputBinding | None,
    expected_sessions: tuple[CrossAssetSession, ...] | None,
    engineering_helper_sha256: str | None,
    frozen_at: datetime,
    expected_calendar_sha256: str | None = None,
) -> KisPaperPortfolioSessionInput:
    """First call freezes; retries ignore ALL proposed non-identity replacement terms."""
    try:
        key = _identity(session_id, expected_account_ref, expected_basis_ref)
        _check(isinstance(state_root, Path), "session_input_path_invalid")
        path = state_root.absolute() / ".portfolio_session_inputs" / (key + ".json")
        lock_path = path.with_name("." + path.name + ".lock")
        for p in (path, lock_path):
            _unlinked(p)
        with exclusive_kis_paper_canary_state_lock(path):
            _unlinked(path)
            saved = _read(path)
            if saved is not None:
                return _decode(saved, key, True)
            _check(
                type(input_binding) is control.KisPaperPortfolioControlInputBinding
                and isinstance(expected_owner_refs, Mapping)
                and type(frozen_at) is datetime,
                "session_input_missing",
            )
            rows = _sessions(expected_sessions)
            calendar_pin = (
                expected_calendar_sha256
                if expected_calendar_sha256 is not None
                else (
                    control._sha(
                        control._encode(
                            [{k: v.replace("+00:00", "Z") for k, v in row.items()} for row in rows]
                        )
                    )
                )
            )
            value = dict(
                version=1,
                session_id=session_id,
                account_ref=expected_account_ref,
                basis_ref=expected_basis_ref,
                owner_refs=dict(expected_owner_refs),
                binding_ref=expected_binding_ref,
                binding=asdict(input_binding),
                sessions=rows,
                helper_sha256=engineering_helper_sha256,
                expected_calendar_sha256=calendar_pin,
                frozen_at=require_utc(frozen_at).isoformat(),
            )
            value["digest"] = "sha256:" + budget._digest(value)
            result = _decode(value, key, False)
            budget._atomic_json(path, value)
            _check(_read(path) == value, "session_input_mutated")
            return result
    except KisPaperPortfolioSessionInputError:
        raise
    except Exception:
        raise KisPaperPortfolioSessionInputError("session_input_invalid") from None
