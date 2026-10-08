"""Read-only binding of an exact retained engineering control to Paper planning.

Hashes establish retained-byte consistency on the assumed-honest host, not
provider publication/finality. The caller supplies the latest completed NYSE
sessions and a trusted helper; this module never imports downloaded code.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from thericher_v2.contracts import require_utc
from thericher_v2.data.kis_daily_price_endpoints import parse_kis_daily_price_endpoints
from thericher_v2.execution.kis_market_data import KisMarketDataResponse, KisPaperDailyQuery
from thericher_v2.research.cross_asset_etf_input import CrossAssetSession

from .kis_paper_portfolio_budget import _digest

_KIND = "kis-current-control-refresh-v1"
_SYMBOLS = ("SPY", "TLT", "GLD")
_VENUES = ("AMS", "NAS", "AMS")
_HASH = re.compile(r"sha256:[0-9a-f]{64}")
_HELPER = "sha256:1a27351623a311c8f6e263ca235a28f49c7386c42a49db3033d16d875049e576"
_LIMITS = dict(
    price_only=True,
    MODP="0_opaque",
    PIT="not_claimed",
    total_return="not_claimed",
    finality="not_observed",
    provider_publication_at="not_observed",
)


class KisPaperPortfolioControlInputError(ValueError):
    """A categorical failure scoped only to this input."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _check(condition: bool, reason: str) -> None:
    if not condition:
        raise KisPaperPortfolioControlInputError(reason)


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _plain(path: Path) -> Path:
    path = path.absolute()
    for part in (path, *path.parents):
        info = part.lstat()
        _check(
            not part.is_symlink()
            and not stat.S_ISLNK(info.st_mode)
            and not getattr(info, "st_file_attributes", 0) & 0x400,
            "path_link_invalid",
        )
    return path


def _path(root: Path, relative: str) -> Path:
    _check(
        type(relative) is str and bool(relative) and "\\" not in relative and ":" not in relative,
        "path_invalid",
    )
    parts = PurePosixPath(relative)
    _check(
        not parts.is_absolute()
        and all(p not in {".", ".."} for p in parts.parts)
        and str(parts) == relative,
        "path_invalid",
    )
    return _plain(root / relative)


def _pairs(items):
    result = {}
    for key, value in items:
        _check(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def _json(raw: bytes):
    return json.loads(
        raw,
        object_pairs_hook=_pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(
            KisPaperPortfolioControlInputError("json_invalid")
        ),
    )


def _utc(value) -> datetime:
    if type(value) is str:
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _check(type(value) is datetime, "clock_invalid")
    return require_utc(value)


def _encode(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


@dataclass(frozen=True, repr=False)
class KisPaperPortfolioControlInputBinding:
    control_relative_path: str
    control_sha256: str
    receipt_relative_path: str
    receipt_sha256: str
    parent_relative_path: str
    parent_sha256: str


@dataclass(frozen=True, repr=False)
class KisPaperPortfolioControlInput:
    input_ref: str
    control_ref: str
    target_as_of: datetime
    observed_at: datetime
    weights_by_symbol: Mapping[str, Decimal] = field(repr=False)
    covariance_by_symbol: Mapping[str, Mapping[str, Decimal]] = field(repr=False)
    _files: tuple[tuple[Path, str], ...] = field(repr=False)
    _binding: KisPaperPortfolioControlInputBinding = field(repr=False)

    def reattest(self) -> bool:
        try:
            return all(_sha(_plain(path).read_bytes()) == digest for path, digest in self._files)
        except (OSError, ValueError):
            return False

    def safe_payload(self) -> dict:
        return dict(
            kind="kis-paper-portfolio-control-input-v1",
            status="bound",
            input_ref=self.input_ref,
            control_ref=self.control_ref,
            target_as_of=self.target_as_of.isoformat(),
            observed_at=self.observed_at.isoformat(),
            close_count=253,
            return_count=252,
            retained_file_count=28,
            evidence_pointer=self._binding.receipt_relative_path,
            **_LIMITS,
        )


def load_kis_paper_portfolio_control_input(
    *,
    binding: KisPaperPortfolioControlInputBinding,
    artifact_root: Path,
    market_root: Path,
    expected_sessions: tuple[CrossAssetSession, ...],
    decision_at: datetime,
    engineering_control: Callable,
    engineering_helper_sha256: str = _HELPER,
    expected_calendar_sha256: str | None = None,
) -> KisPaperPortfolioControlInput:
    """Validate one frozen producer run without network, writes or credential reads."""
    try:
        return _load(
            binding,
            artifact_root,
            market_root,
            expected_sessions,
            decision_at,
            engineering_control,
            engineering_helper_sha256,
            expected_calendar_sha256,
        )
    except KisPaperPortfolioControlInputError:
        raise
    except Exception:
        raise KisPaperPortfolioControlInputError("input_contract_invalid") from None


def _load(
    binding, artifact_root, market_root, sessions, decision_at, helper, helper_sha, calendar_sha
):
    _check(type(binding) is KisPaperPortfolioControlInputBinding, "binding_invalid")
    a, m = _plain(artifact_root), _plain(market_root)
    source = Path(__file__).absolute().parents[2]
    repo = source.parent if source.name == "src" else source
    _check(
        not a.is_relative_to(m)
        and not m.is_relative_to(a)
        and not any(p.is_relative_to(repo) for p in (a, m)),
        "root_invalid",
    )
    decision = _utc(decision_at)
    _check(
        type(sessions) is tuple
        and len(sessions) == 253
        and all(type(s) is CrossAssetSession for s in sessions),
        "calendar_invalid",
    )
    dates = [s.session_date.isoformat() for s in sessions]
    _check(
        dates == sorted(set(dates))
        and all(_utc(s.open_at) < _utc(s.close_at) <= decision for s in sessions),
        "calendar_invalid",
    )
    target = sessions[-1].close_at
    geometry = _sha(
        _encode(
            [
                dict(
                    date=d,
                    open_at=s.open_at.isoformat().replace("+00:00", "Z"),
                    close_at=s.close_at.isoformat().replace("+00:00", "Z"),
                )
                for d, s in zip(dates, sessions, strict=True)
            ]
        )
    )
    # The producer hashes its full schedule, including future sessions. A
    # runtime caller must bind that schedule hash, not relabel the 253-window.
    if calendar_sha is not None:
        _check(
            type(calendar_sha) is str and _HASH.fullmatch(calendar_sha) is not None,
            "calendar_digest_invalid",
        )
        geometry = calendar_sha
    files = {}

    def read(root, relative, digest):
        _check(type(digest) is str and _HASH.fullmatch(digest) is not None, "digest_invalid")
        path = _path(root, relative)
        raw = path.read_bytes()
        _check(_sha(raw) == digest, "bytes_changed")
        _check(path not in files or files[path] == digest, "binding_conflict")
        files[path] = digest
        return raw

    c = _json(read(a, binding.control_relative_path, binding.control_sha256))
    r = _json(read(a, binding.receipt_relative_path, binding.receipt_sha256))
    p = _json(read(a, binding.parent_relative_path, binding.parent_sha256))
    scope = PurePosixPath(binding.control_relative_path).parent
    inv = scope.name
    _check(
        re.fullmatch(r"[0-9a-f]{32}", inv) is not None
        and scope.parent == PurePosixPath("data") / _KIND
        and binding.control_relative_path == str(scope / "control.json")
        and binding.receipt_relative_path == str(scope / "receipt.json")
        and binding.parent_relative_path == str(scope.parent / f"parent-{inv}.json"),
        "scope_invalid",
    )
    input_binding = dict(
        root="ARTIFACT", path=binding.control_relative_path, sha256=binding.control_sha256
    )
    _check(
        p.get("status") == "ready"
        and all(
            p.get(k) is True
            for k in (
                "child_reaped",
                "invocation_absent",
                "source_package_unchanged",
                "all_retained_unchanged",
            )
        ),
        "parent_incomplete",
    )
    _check(
        p.get("worker_receipt_path")
        in {
            str(a / binding.receipt_relative_path).replace("\\", "/"),
            "D:/thericher-v2/model-artifacts/" + binding.receipt_relative_path,
        }
        and p.get("worker_receipt_sha256") == binding.receipt_sha256
        and p.get("worker", {}).get("status") == "ready"
        and p["worker"].get("source_unchanged") is True
        and p["worker"].get("input_binding") == input_binding
        and p["worker"].get("receipt_path") == "/artifacts/" + binding.receipt_relative_path
        and p["worker"].get("receipt_sha256") == binding.receipt_sha256,
        "parent_binding_invalid",
    )
    _check(
        c.get("kind") == r.get("kind") == _KIND
        and r.get("invocation_id") == inv
        and r.get("status") == "ready"
        and r.get("reason") is None
        and r.get("source_reattestation") == r.get("retained_reattestation") == "matched"
        and r.get("input_binding") == input_binding,
        "receipt_invalid",
    )
    observed = _utc(c["observed_at"])
    _check(
        target == _utc(c["target_as_of"]) == _utc(r["target_as_of"])
        and target <= _utc(r["started_at"]) <= observed <= _utc(r["completed_at"]) <= decision,
        "clock_invalid",
    )
    _check(
        c.get("session_dates") == dates
        and r.get("required_first_date") == dates[0]
        and r.get("required_last_date") == dates[-1]
        and c.get("calendar_geometry_sha256") == r.get("calendar_geometry_sha256") == geometry
        and r.get("required_close_count") == 253
        and r.get("return_count") == 252,
        "geometry_invalid",
    )
    _check(
        all(c.get(k) == v and r.get(k) == v for k, v in _LIMITS.items()), "source_limits_invalid"
    )
    _check(
        c.get("source_pins") == r.get("source_pins")
        and c["source_pins"].get("helper") == helper_sha
        and getattr(helper, "__name__", None) == "engineering_control",
        "helper_invalid",
    )
    helper_file = _plain(Path(inspect.getsourcefile(helper)))
    _check(
        _HASH.fullmatch(helper_sha) is not None and _sha(helper_file.read_bytes()) == helper_sha,
        "helper_changed",
    )
    files[helper_file] = helper_sha
    retained = r["retained_files"]
    _check(type(retained) is list and len(retained) == 28, "retained_invalid")
    content = {}
    for item in retained:
        root = a if item["root"] == "ARTIFACT" else m if item["root"] == "MARKET" else None
        _check(root is not None, "retained_scope_invalid")
        prefix = (
            scope
            if root == a
            else PurePosixPath(f"us_equities/kis_paper_private/current-control-history/{inv}")
        )
        _check(PurePosixPath(item["path"]).parent == prefix, "retained_scope_invalid")
        key = (item["root"], item["path"])
        _check(key not in content, "retained_duplicate")
        content[key] = read(root, item["path"], item["sha256"])
    _check(
        content.get(("ARTIFACT", binding.control_relative_path)) is not None,
        "retained_control_missing",
    )
    pages = c["pages"]
    _check(
        pages == r["pages"]
        and len(pages) == 9
        and r.get("accepted_pages") == r.get("daily_GET_attempts") == 9
        and r.get("token_POST_attempts") == 1,
        "page_count_invalid",
    )
    selected = {s: {} for s in _SYMBOLS}
    used = set()
    cursor, continuation = dates[-1].replace("-", ""), None
    for index, fact in enumerate(pages):
        symbol, venue = _SYMBOLS[index // 3], _VENUES[index // 3]
        if index % 3 == 0:
            cursor, continuation = dates[-1].replace("-", ""), None
        query = fact["query"]
        _check(
            query["symbol"] == symbol
            and query["exchange"] == venue
            and query["page_ordinal"] == index % 3 + 1
            and query["GUBN"] == query["MODP"] == "0",
            "query_invalid",
        )
        _check(
            target
            <= _utc(r["started_at"])
            <= _utc(fact["call_entered_at"])
            <= _utc(fact["observed_at"])
            <= observed,
            "page_clock_invalid",
        )
        _check(
            query["BYMD"] == cursor and query["continuation"] == continuation,
            "cursor_binding_invalid",
        )
        q = KisPaperDailyQuery(
            symbol=symbol,
            exchange=venue,
            by_date=query["BYMD"],
            continuation=query["continuation"],
            approved_symbol_exchanges={
                s: frozenset({v}) for s, v in zip(_SYMBOLS, _VENUES, strict=True)
            },
        )
        raw_values = {}
        for label, suffix in (("intent", "query"), ("raw", "raw"), ("typed", "oc")):
            item = fact[label]
            key = (item["root"], item["path"])
            _check(
                key in content
                and key not in used
                and item["root"] == "MARKET"
                and PurePosixPath(item["path"]).name == f"{symbol}-{index % 3 + 1}.{suffix}.json"
                and _sha(content[key]) == item["sha256"],
                "page_binding_invalid",
            )
            used.add(key)
            raw_values[label] = content[key]
        _check(_json(raw_values["intent"]) == query, "query_binding_invalid")
        _json(raw_values["raw"])
        page = parse_kis_daily_price_endpoints(
            KisMarketDataResponse(
                200, {"tr_cont": fact["facts"]["continuation"] or ""}, raw_values["raw"]
            ),
            query=q,
        )
        _check(
            bool(page.rows) and page.rows[0].session_date.replace("-", "") < cursor,
            "cursor_nonadvancing",
        )
        cursor, continuation = page.rows[0].session_date.replace("-", ""), page.continuation
        typed = _json(raw_values["typed"])
        _check(
            page.safe_facts() == fact["facts"] == typed["facts"]
            and typed["query"] == query
            and typed["call_entered_at"] == fact["call_entered_at"]
            and typed["observed_at"] == fact["observed_at"]
            and typed["rows"] == [row.as_document() for row in page.rows]
            and typed["source_row_fingerprints"] == [list(x) for x in page.source_row_fingerprints],
            "typed_binding_invalid",
        )
        for row in page.rows:
            old = selected[symbol].get(row.session_date)
            _check(
                old is None or (old["open"], old["close"]) == (row.open, row.close),
                "overlap_conflict",
            )
            fingerprints = {
                digest for day, digest in page.source_row_fingerprints if day == row.session_date
            }
            selected[symbol][row.session_date] = dict(
                open=row.open,
                close=row.close,
                fingerprints=sorted(fingerprints | (set(old["fingerprints"]) if old else set())),
                unused_ohlcv_faults=sorted(
                    set(row.unused_ohlcv_faults)
                    | (set(old["unused_ohlcv_faults"]) if old else set())
                ),
            )
    _check(len(used) == 27, "retained_unbound")
    provenance = {s: {d: selected[s][d] for d in dates} for s in _SYMBOLS}
    _check(c["selected_provenance"] == provenance, "provenance_invalid")
    columns = tuple(tuple(Decimal(provenance[s][d]["close"]) for d in dates) for s in _SYMBOLS)
    _check(
        c["closes"] == [[str(v) for v in column] for column in columns], "column_binding_invalid"
    )
    weights, covariance = helper(columns)
    _check(
        set(weights) == set(covariance) == set(_SYMBOLS)
        and all(type(v) is Decimal and v.is_finite() and v >= 0 for v in weights.values())
        and sum(map(Fraction, weights.values()), Fraction()) <= 1,
        "control_invalid",
    )
    _check(
        all(
            set(covariance[s]) == set(_SYMBOLS)
            and all(
                type(covariance[s][t]) is Decimal
                and covariance[s][t].is_finite()
                and covariance[s][t] == covariance[t][s]
                for t in _SYMBOLS
            )
            and covariance[s][s] >= 0
            for s in _SYMBOLS
        ),
        "control_invalid",
    )
    proposal = dict(
        weights={s: str(weights[s]) for s in _SYMBOLS},
        covariance={s: {t: str(covariance[s][t]) for t in _SYMBOLS} for s in _SYMBOLS},
    )
    _check(c["control"] == proposal, "control_recompute_mismatch")
    control_ref = _digest(proposal | dict(target_at=target.isoformat()))
    result = KisPaperPortfolioControlInput(
        binding.control_sha256,
        control_ref,
        target,
        observed,
        MappingProxyType(dict(weights)),
        MappingProxyType({s: MappingProxyType(dict(covariance[s])) for s in _SYMBOLS}),
        tuple(files.items()),
        binding,
    )
    _check(result.reattest(), "bytes_changed")
    return result
