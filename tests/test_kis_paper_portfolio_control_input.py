from __future__ import annotations

import hashlib
import inspect
import json
import socket
import stat
import subprocess
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.data import kis_daily_price_endpoints as endpoints
from thericher_v2.execution import kis_paper_portfolio_control_input as adapter
from thericher_v2.execution.kis_market_data import KisMarketDataResponse, KisPaperDailyQuery
from thericher_v2.research.cross_asset_etf_input import CrossAssetSession

SYMBOLS = ("SPY", "TLT", "GLD")
VENUES = ("AMS", "NAS", "AMS")
INVOCATION = "a" * 32
KIND = "kis-current-control-refresh-v1"


def _sha(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _encode(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _utc(value):
    return value.isoformat().replace("+00:00", "Z")


def engineering_control(columns):
    assert tuple(map(len, columns)) == (253, 253, 253)
    assert all(type(value) is Decimal for column in columns for value in column)
    return (
        {symbol: columns[i][0] / Decimal(1000) for i, symbol in enumerate(SYMBOLS)},
        {
            symbol: {
                peer: columns[i][-1] / Decimal(1000000) if symbol == peer else Decimal("0.00005")
                for peer in SYMBOLS
            }
            for i, symbol in enumerate(SYMBOLS)
        },
    )


def _sessions():
    result, day = [], date(2025, 1, 2)
    while len(result) < 253:
        if day.weekday() < 5:
            result.append(
                CrossAssetSession(
                    day,
                    datetime.combine(day, time(14, 30), UTC),
                    datetime.combine(day, time(21), UTC),
                )
            )
        day += timedelta(days=1)
    return tuple(result)


def _calendar_sha(sessions):
    return _sha(
        _encode(
            [
                dict(
                    date=s.session_date.isoformat(),
                    open_at=_utc(s.open_at),
                    close_at=_utc(s.close_at),
                )
                for s in sessions
            ]
        )
    )


@pytest.fixture
def bundle(tmp_path):
    artifact, market = tmp_path / "a", tmp_path / "m"
    artifact.mkdir()
    market.mkdir()
    sessions = _sessions()
    target = sessions[-1].close_at
    observed, decision = target + timedelta(minutes=1), target + timedelta(hours=1)
    last = sessions[-1]
    future_day = last.session_date + timedelta(days=1)
    while future_day.weekday() >= 5:
        future_day += timedelta(days=1)
    future = CrossAssetSession(
        future_day,
        datetime.combine(future_day, time(14, 30), UTC),
        datetime.combine(future_day, time(21), UTC),
    )
    scheduled = (*sessions, future)
    relative = Path("data/kis-current-control-refresh-v1") / INVOCATION
    market_relative = Path("us_equities/kis_paper_private/current-control-history") / INVOCATION
    retained, pages, provenance = [], [], {}
    helper_path = Path(inspect.getsourcefile(engineering_control))
    helper_sha = _sha(helper_path.read_bytes())
    source_pins = {"helper": helper_sha, "worker": _sha(b"synthetic worker")}

    def retain(root, path, value):
        raw = value if isinstance(value, bytes) else _encode(value)
        full = (artifact if root == "ARTIFACT" else market) / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(raw)
        item = dict(root=root, path=path.as_posix(), sha256=_sha(raw))
        retained.append(item)
        return item

    dates = tuple(session.session_date.isoformat() for session in sessions)
    columns = tuple(
        tuple(Decimal(100 * (i + 1)) + Decimal(j + 1) / Decimal(100) for j in range(253))
        for i in range(3)
    )
    for index, (symbol, venue) in enumerate(zip(SYMBOLS, VENUES, strict=True)):
        selected = {}
        for ordinal, (start, end) in enumerate(((153, 253), (54, 154), (0, 55)), 1):
            by_date = dates[end - 1].replace("-", "")
            continuation = None if ordinal == 1 else "F"
            question = dict(
                symbol=symbol,
                exchange=venue,
                BYMD=by_date,
                GUBN="0",
                MODP="0",
                continuation=continuation,
                page_ordinal=ordinal,
            )
            raw_rows = [
                dict(
                    xymd=dates[j].replace("-", ""),
                    open=str(columns[index][j]),
                    clos=str(columns[index][j]),
                    high="1000",
                    low="1",
                    tvol="0",
                )
                for j in reversed(range(start, end))
            ]
            raw = _encode(dict(rt_cd="0", output1={}, output2=raw_rows))
            query = KisPaperDailyQuery(
                symbol=symbol,
                exchange=venue,
                by_date=by_date,
                continuation=continuation,
                approved_symbol_exchanges={
                    s: frozenset({v}) for s, v in zip(SYMBOLS, VENUES, strict=True)
                },
            )
            page = endpoints.parse_kis_daily_price_endpoints(
                KisMarketDataResponse(200, {"tr_cont": "F"}, raw), query=query
            )
            entered = target + timedelta(seconds=len(pages) * 2 + 1)
            facts = dict(
                query=question,
                call_entered_at=_utc(entered),
                observed_at=_utc(entered + timedelta(seconds=1)),
                facts=page.safe_facts(),
            )
            intent = retain("MARKET", market_relative / f"{symbol}-{ordinal}.query.json", question)
            raw_binding = retain("MARKET", market_relative / f"{symbol}-{ordinal}.raw.json", raw)
            typed = retain(
                "MARKET",
                market_relative / f"{symbol}-{ordinal}.oc.json",
                facts
                | dict(
                    rows=[row.as_document() for row in page.rows],
                    source_row_fingerprints=page.source_row_fingerprints,
                ),
            )
            pages.append(facts | dict(intent=intent, raw=raw_binding, typed=typed))
            for row in page.rows:
                selected[row.session_date] = dict(
                    open=row.open,
                    close=row.close,
                    fingerprints=[row.provider_row_sha256],
                    unused_ohlcv_faults=list(row.unused_ohlcv_faults),
                )
        provenance[symbol] = selected
    weights, covariance = engineering_control(columns)
    geometry = _calendar_sha(scheduled)
    control = dict(
        kind=KIND,
        target_as_of=_utc(target),
        observed_at=_utc(observed),
        session_dates=dates,
        closes=[[str(value) for value in column] for column in columns],
        selected_provenance=provenance,
        control=dict(
            weights={s: str(weights[s]) for s in SYMBOLS},
            covariance={s: {t: str(covariance[s][t]) for t in SYMBOLS} for s in SYMBOLS},
        ),
        pages=pages,
        source_pins=source_pins,
        calendar_geometry_sha256=geometry,
        price_only=True,
        MODP="0_opaque",
        PIT="not_claimed",
        total_return="not_claimed",
        finality="not_observed",
        provider_publication_at="not_observed",
    )
    control_binding = retain("ARTIFACT", relative / "control.json", control)
    receipt = dict(
        kind=KIND,
        invocation_id=INVOCATION,
        status="ready",
        reason=None,
        started_at=_utc(target + timedelta(seconds=1)),
        completed_at=_utc(observed + timedelta(seconds=1)),
        elapsed_seconds=60.0,
        target_as_of=_utc(target),
        token_POST_attempts=1,
        daily_GET_attempts=9,
        accepted_pages=9,
        count_semantics="inherited dispatch attempts; not independently measured wire starts",
        required_close_count=253,
        return_count=252,
        pages=pages,
        source_pins=source_pins,
        source_reattestation="matched",
        retained_reattestation="matched",
        calendar_geometry_sha256=geometry,
        calendar_attestation="caller_NYSE_schedule",
        next_due=None,
        input_binding=control_binding,
        required_first_date=dates[0],
        required_last_date=dates[-1],
        retained_files=retained,
        **{
            k: control[k]
            for k in (
                "price_only",
                "MODP",
                "PIT",
                "total_return",
                "finality",
                "provider_publication_at",
            )
        },
    )
    receipt_relative = relative / "receipt.json"
    receipt_path = artifact / receipt_relative
    receipt_path.write_bytes(_encode(receipt))
    parent_relative = relative.parent / f"parent-{INVOCATION}.json"
    parent = dict(
        status="ready",
        child_reaped=True,
        invocation_absent=True,
        source_package_unchanged=True,
        all_retained_unchanged=True,
        worker_receipt_path=receipt_path.as_posix(),
        worker_receipt_sha256=_sha(receipt_path.read_bytes()),
        worker=dict(
            status="ready",
            source_unchanged=True,
            input_binding=control_binding,
            receipt_path="/artifacts/" + receipt_relative.as_posix(),
            receipt_sha256=_sha(receipt_path.read_bytes()),
        ),
    )
    parent_path = artifact / parent_relative
    parent_path.write_bytes(_encode(parent))
    value = SimpleNamespace(
        artifact=artifact,
        market=market,
        sessions=sessions,
        scheduled=scheduled,
        target=target,
        observed=observed,
        decision=decision,
        helper_sha=helper_sha,
        control=control,
        receipt=receipt,
        parent=parent,
        control_relative=relative / "control.json",
        receipt_relative=receipt_relative,
        parent_relative=parent_relative,
        columns=columns,
    )

    def repin():
        (artifact / value.control_relative).write_bytes(_encode(value.control))
        value.receipt["input_binding"]["sha256"] = _sha(
            (artifact / value.control_relative).read_bytes()
        )
        (artifact / value.receipt_relative).write_bytes(_encode(value.receipt))
        value.parent["worker_receipt_sha256"] = _sha(
            (artifact / value.receipt_relative).read_bytes()
        )
        value.parent["worker"]["receipt_sha256"] = value.parent["worker_receipt_sha256"]
        (artifact / value.parent_relative).write_bytes(_encode(value.parent))
        return adapter.KisPaperPortfolioControlInputBinding(
            control_relative_path=value.control_relative.as_posix(),
            control_sha256=_sha((artifact / value.control_relative).read_bytes()),
            receipt_relative_path=value.receipt_relative.as_posix(),
            receipt_sha256=_sha((artifact / value.receipt_relative).read_bytes()),
            parent_relative_path=value.parent_relative.as_posix(),
            parent_sha256=_sha((artifact / value.parent_relative).read_bytes()),
        )

    value.repin = repin
    value.binding = repin()

    def load(**overrides):
        return adapter.load_kis_paper_portfolio_control_input(
            **(
                dict(
                    binding=value.binding,
                    artifact_root=artifact,
                    market_root=market,
                    expected_sessions=sessions,
                    expected_calendar_sha256=_calendar_sha(scheduled),
                    decision_at=decision,
                    engineering_control=engineering_control,
                    engineering_helper_sha256=helper_sha,
                )
                | overrides
            )
        )

    value.load = load
    return value


def _reject(bundle, **overrides):
    with pytest.raises(adapter.KisPaperPortfolioControlInputError) as caught:
        bundle.load(**overrides)
    assert isinstance(caught.value.reason_code, str) and caught.value.reason_code
    assert str(bundle.artifact) not in str(caught.value)
    return caught.value.reason_code


def test_exact_synthetic_input_reconstructs_and_reattests(bundle):
    result = bundle.load()
    weights, covariance = engineering_control(bundle.columns)
    assert result.input_ref == bundle.binding.control_sha256
    assert result.control_ref.startswith("sha256:")
    assert result.target_as_of == bundle.target and result.observed_at == bundle.observed
    assert dict(result.weights_by_symbol) == weights
    assert {s: dict(row) for s, row in result.covariance_by_symbol.items()} == covariance
    assert result.reattest() is True
    assert bundle.load().control_ref == result.control_ref


def test_canonical_host_receipt_pointer_maps_to_the_native_artifact_root(bundle):
    bundle.parent["worker_receipt_path"] = (
        "D:/thericher-v2/model-artifacts/" + bundle.receipt_relative.as_posix()
    )
    bundle.binding = bundle.repin()
    assert bundle.load().reattest() is True


def test_full_producer_calendar_commitment_is_independently_computed(bundle):
    assert len(bundle.scheduled) == 254
    assert bundle.scheduled[-1].close_at > bundle.decision
    assert _calendar_sha(bundle.scheduled) != _calendar_sha(bundle.sessions)
    result = bundle.load(expected_calendar_sha256=_calendar_sha(bundle.scheduled))
    assert result.target_as_of == bundle.sessions[-1].close_at
    assert result.reattest() is True


@pytest.mark.parametrize("expected", [None, "", "not-a-digest", _sha(b"other calendar")])
def test_full_calendar_hash_is_not_copied_or_implicitly_waived(bundle, expected):
    _reject(bundle, expected_calendar_sha256=expected)


def test_default_calendar_commitment_is_253_selected_sessions_for_synthetic_input(bundle):
    geometry = _calendar_sha(bundle.sessions)
    bundle.control["calendar_geometry_sha256"] = geometry
    bundle.receipt["calendar_geometry_sha256"] = geometry
    bundle.binding = bundle.repin()
    assert bundle.load(expected_calendar_sha256=None).reattest() is True


def test_result_is_frozen_and_projection_hides_financial_fields(bundle):
    result = bundle.load()
    with pytest.raises((FrozenInstanceError, AttributeError)):
        result.input_ref = "replacement"
    with pytest.raises(TypeError):
        result.weights_by_symbol["SPY"] = Decimal(0)
    with pytest.raises(TypeError):
        result.covariance_by_symbol["SPY"]["TLT"] = Decimal(0)
    public = json.dumps(result.safe_payload()) + repr(result)
    for forbidden in ("closes", "selected_provenance", "weights", "covariance"):
        assert forbidden not in public
    for value in result.weights_by_symbol.values():
        assert str(value) not in public


@pytest.mark.parametrize("field", ["control", "receipt", "parent"])
def test_top_level_hash_mutation_and_missing_files_fail(bundle, field):
    result = bundle.load()
    path = bundle.artifact / getattr(bundle, field + "_relative")
    original = path.read_bytes()
    path.write_bytes(original + b" ")
    assert result.reattest() is False
    _reject(bundle)
    path.unlink()
    _reject(bundle)


@pytest.mark.parametrize("field", ["control", "receipt", "parent"])
def test_binding_digest_is_independent_of_current_file_contents(bundle, field):
    binding = replace(bundle.binding, **{field + "_sha256": _sha(b"unrelated witness")})
    _reject(bundle, binding=binding)


@pytest.mark.parametrize("relative", ["../outside.json", "/outside.json", "C:/outside.json"])
def test_relative_path_cannot_escape_its_bound_root(bundle, relative):
    with pytest.raises(adapter.KisPaperPortfolioControlInputError):
        binding = replace(bundle.binding, control_relative_path=relative)
        bundle.load(binding=binding)


@pytest.mark.parametrize("index", [0, 4, 13, 26])
def test_retained_mutation_invalidates_load_and_live_reattest(bundle, index):
    result = bundle.load()
    item = bundle.receipt["retained_files"][index]
    root = bundle.market if item["root"] == "MARKET" else bundle.artifact
    path = root / item["path"]
    path.write_bytes(path.read_bytes() + b" ")
    assert result.reattest() is False
    _reject(bundle)


@pytest.mark.parametrize("count", [0, 63, 252, 254])
def test_requires_exact_253_caller_sessions(bundle, count):
    sessions = bundle.sessions[:count]
    if count == 254:
        last = sessions[-1]
        sessions += (
            CrossAssetSession(
                last.session_date + timedelta(days=1),
                last.open_at + timedelta(days=1),
                last.close_at + timedelta(days=1),
            ),
        )
    _reject(bundle, expected_sessions=sessions)


@pytest.mark.parametrize("variant", ["duplicate", "reverse", "list", "shift"])
def test_calendar_identity_is_not_count_alone(bundle, variant):
    sessions = bundle.sessions
    if variant == "duplicate":
        sessions = (*sessions[:-1], sessions[-2])
    elif variant == "reverse":
        sessions = tuple(reversed(sessions))
    elif variant == "list":
        sessions = list(sessions)
    else:
        sessions = tuple(
            CrossAssetSession(
                s.session_date + timedelta(days=1),
                s.open_at + timedelta(days=1),
                s.close_at + timedelta(days=1),
            )
            for s in sessions
        )
    _reject(bundle, expected_sessions=sessions)


@pytest.mark.parametrize("variant", ["naive", "before_close", "before_observation"])
def test_decision_clock_rejects_unavailable_input(bundle, variant):
    decision = {
        "naive": bundle.decision.replace(tzinfo=None),
        "before_close": bundle.target - timedelta(seconds=1),
        "before_observation": bundle.observed - timedelta(seconds=1),
    }[variant]
    _reject(bundle, decision_at=decision)


@pytest.mark.parametrize("field", ["observed_at", "target_as_of"])
def test_rebound_future_control_clock_is_rejected(bundle, field):
    bundle.control[field] = _utc(bundle.decision + timedelta(seconds=1))
    bundle.binding = bundle.repin()
    _reject(bundle)


@pytest.mark.parametrize("variant", ["63", "permuted", "provenance", "double_shrink", "ulp"])
def test_rebound_control_cannot_change_geometry_symbol_binding_or_formula(bundle, variant):
    if variant == "63":
        bundle.control["session_dates"] = bundle.control["session_dates"][-63:]
        bundle.control["closes"] = [c[-63:] for c in bundle.control["closes"]]
    elif variant == "permuted":
        bundle.control["closes"][0], bundle.control["closes"][1] = (
            bundle.control["closes"][1],
            bundle.control["closes"][0],
        )
    elif variant == "provenance":
        bundle.control["selected_provenance"]["SPY"][bundle.sessions[-1].session_date.isoformat()][
            "close"
        ] = "123456.789"
    else:
        row = bundle.control["control"]["covariance"]["SPY"]
        row["TLT"] = "0.000045" if variant == "double_shrink" else "0.000050000000000000000001"
        bundle.control["control"]["covariance"]["TLT"]["SPY"] = row["TLT"]
    bundle.binding = bundle.repin()
    _reject(bundle)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "input_unavailable"),
        ("child_reaped", False),
        ("invocation_absent", False),
        ("source_package_unchanged", False),
        ("all_retained_unchanged", False),
        ("worker_receipt_sha256", _sha(b"different receipt")),
    ],
)
def test_parent_custody_facts_are_required_even_with_a_new_parent_pin(bundle, field, value):
    bundle.parent[field] = value
    bundle.binding = bundle.repin()
    if field == "worker_receipt_sha256":
        bundle.parent[field] = value
        path = bundle.artifact / bundle.parent_relative
        path.write_bytes(_encode(bundle.parent))
        bundle.binding = replace(bundle.binding, parent_sha256=_sha(path.read_bytes()))
    _reject(bundle)


@pytest.mark.parametrize(
    "variant", ["status", "source", "input", "receipt_pointer", "worker_pointer", "worker_hash"]
)
def test_parent_worker_and_receipt_link_cannot_be_rebound_to_other_evidence(bundle, variant):
    if variant == "status":
        bundle.parent["worker"]["status"] = "input_unavailable"
    elif variant == "source":
        bundle.parent["worker"]["source_unchanged"] = False
    elif variant == "input":
        bundle.parent["worker"]["input_binding"] = dict(
            bundle.receipt["input_binding"], sha256=_sha(b"other control")
        )
    elif variant == "receipt_pointer":
        bundle.parent["worker_receipt_path"] = "/artifacts/data/other/receipt.json"
    elif variant == "worker_pointer":
        bundle.parent["worker"]["receipt_path"] = "/artifacts/data/other/receipt.json"
    bundle.binding = bundle.repin()
    if variant == "worker_hash":
        bundle.parent["worker"]["receipt_sha256"] = _sha(b"other receipt")
        path = bundle.artifact / bundle.parent_relative
        path.write_bytes(_encode(bundle.parent))
        bundle.binding = replace(bundle.binding, parent_sha256=_sha(path.read_bytes()))
    _reject(bundle)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "input_unavailable"),
        ("reason", "required_session_missing"),
        ("source_reattestation", "unavailable"),
        ("retained_reattestation", "not_checked"),
        ("required_close_count", 63),
        ("return_count", 63),
        ("accepted_pages", True),
        ("daily_GET_attempts", 10),
    ],
)
def test_receipt_is_not_a_ready_claim_without_its_exact_contract(bundle, field, value):
    bundle.receipt[field] = value
    bundle.binding = bundle.repin()
    _reject(bundle)


@pytest.mark.parametrize("variant", ["missing", "duplicate", "foreign_root", "outside"])
def test_retained_hash_scope_is_exact_not_a_partial_success(bundle, variant):
    items = bundle.receipt["retained_files"]
    if variant == "missing":
        items.pop(0)
    elif variant == "duplicate":
        items.append(dict(items[0]))
    elif variant == "foreign_root":
        items[0]["root"] = "PRIVATE"
    else:
        items[0]["path"] = "../outside.json"
    bundle.binding = bundle.repin()
    _reject(bundle)


@pytest.mark.parametrize("field,value", [("exchange", "NAS"), ("MODP", "1"), ("symbol", "QQQ")])
def test_query_provenance_cannot_widen_symbol_venue_or_price_basis(bundle, field, value):
    page = bundle.control["pages"][0]
    page["query"][field] = value
    query = page["intent"]
    path = bundle.market / query["path"]
    path.write_bytes(_encode(page["query"]))
    query["sha256"] = _sha(path.read_bytes())
    bundle.binding = bundle.repin()
    _reject(bundle)


@pytest.mark.parametrize("variant", ["before_close", "after_decision", "entered_after_observed"])
def test_accepted_page_clocks_remain_causal_even_after_repinning(bundle, variant):
    fact = bundle.control["pages"][0]
    path = bundle.market / fact["typed"]["path"]
    typed = json.loads(path.read_bytes())
    if variant == "before_close":
        fact["call_entered_at"] = fact["observed_at"] = _utc(bundle.target - timedelta(seconds=1))
    elif variant == "after_decision":
        fact["observed_at"] = _utc(bundle.decision + timedelta(seconds=1))
    else:
        fact["call_entered_at"] = _utc(bundle.observed + timedelta(seconds=1))
    for field in ("call_entered_at", "observed_at"):
        typed[field] = fact[field]
    path.write_bytes(_encode(typed))
    fact["typed"]["sha256"] = _sha(path.read_bytes())
    bundle.binding = bundle.repin()
    _reject(bundle)


def test_even_numerically_equal_changed_helper_strings_are_not_exact_reconstruction(bundle):
    weights = bundle.control["control"]["weights"]
    weights["SPY"] += "0"
    bundle.binding = bundle.repin()
    _reject(bundle)


@pytest.mark.parametrize("field", ["control", "receipt", "parent"])
def test_recursive_duplicate_json_keys_are_rejected_before_typed_projection(bundle, field):
    path = bundle.artifact / getattr(bundle, field + "_relative")
    raw = path.read_bytes().rstrip()
    raw = raw[:-1] + b',"nested_synthetic":{"duplicate":1,"duplicate":2}}\n'
    path.write_bytes(raw)
    if field == "control":
        bundle.receipt["input_binding"]["sha256"] = _sha(raw)
        (bundle.artifact / bundle.receipt_relative).write_bytes(_encode(bundle.receipt))
    if field != "parent":
        bundle.parent["worker_receipt_sha256"] = _sha(
            (bundle.artifact / bundle.receipt_relative).read_bytes()
        )
        bundle.parent["worker"]["receipt_sha256"] = bundle.parent["worker_receipt_sha256"]
        (bundle.artifact / bundle.parent_relative).write_bytes(_encode(bundle.parent))
    binding = replace(
        bundle.binding,
        control_sha256=_sha((bundle.artifact / bundle.control_relative).read_bytes()),
        receipt_sha256=_sha((bundle.artifact / bundle.receipt_relative).read_bytes()),
        parent_sha256=_sha((bundle.artifact / bundle.parent_relative).read_bytes()),
    )
    _reject(bundle, binding=binding)


@pytest.mark.parametrize("variant", ["pin", "name", "exception"])
def test_helper_custody_and_failure_are_scoped(bundle, variant):
    def wrong_name(columns):
        return engineering_control(columns)

    def failing(columns):
        raise RuntimeError("synthetic-private-error-99171")

    failing.__name__ = "engineering_control"
    if variant == "pin":
        _reject(bundle, engineering_helper_sha256=_sha(b"different source"))
    else:
        reason = _reject(bundle, engineering_control=wrong_name if variant == "name" else failing)
        assert "99171" not in reason


@pytest.mark.parametrize("root", ["artifact", "market"])
@pytest.mark.parametrize("kind", ["symlink", "reparse"])
def test_reparse_root_is_rejected_without_reading_through_it(bundle, monkeypatch, root, kind):
    flagged = getattr(bundle, root)
    original = Path.lstat
    monkeypatch.setattr(
        Path,
        "lstat",
        lambda path: (
            SimpleNamespace(
                st_mode=stat.S_IFLNK if kind == "symlink" else original(path).st_mode,
                st_file_attributes=0x400 if kind == "reparse" else 0,
            )
            if path == flagged
            else original(path)
        ),
    )
    _reject(bundle)


def test_load_and_reattest_have_no_write_network_or_process_effects(bundle, monkeypatch):
    before = {
        p: p.read_bytes()
        for root in (bundle.artifact, bundle.market)
        for p in root.rglob("*")
        if p.is_file()
    }

    def forbidden(*args, **kwargs):
        pytest.fail("control loader attempted an external or mutable effect")

    for method in ("write_bytes", "write_text", "mkdir", "unlink", "rename", "replace"):
        monkeypatch.setattr(Path, method, forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    result = bundle.load()
    assert result.reattest() is True
    assert before == {p: p.read_bytes() for p in before}
