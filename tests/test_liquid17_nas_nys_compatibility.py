"""Invented NAS/NYS native codec, custody and lifecycle; no actual broker effects."""

import ast
import copy
import hashlib
import json
from dataclasses import fields, replace
from datetime import timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

import test_kis_paper_current_stock_cycle as legacy
import test_kis_paper_stock_plan_reservation as reservations
import test_kis_paper_stock_session_recovery as recovery_fixture
import test_kis_paper_weight_cycle as weights
import test_model_paper_profile as model_fixture
import test_model_paper_weights_h5 as metadata_fixture
from test_kis_paper_current_stock_cycle_worker import w
from test_kis_paper_portfolio_execute import CONFIG
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_current_stock_cycle as core
from thericher_v2.execution import kis_paper_stock_plan as planner
from thericher_v2.execution import kis_paper_stock_session_recovery as recovery
from thericher_v2.execution.kis_paper_fill_accounting import fill_identity_ref
from thericher_v2.execution.kis_paper_quote import KisPaperQuoteError
from thericher_v2.execution.kis_paper_stock_quote import (
    KisPaperStockInstrument,
    KisPaperUsStockInstrument,
    build_kis_paper_stock_quote_request,
    validate_kis_paper_stock_quote_request,
)
from thericher_v2.execution.kis_paper_stock_readonly import (
    KisPaperStockReadOnlyClient,
    _instrument,
)
from thericher_v2.research.model_paper_weights import (
    MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
    MODEL_PAPER_WEIGHTS_US_5_SESSION_PROFILE,
    ModelPaperWeightRow,
    load_model_paper_weights_input,
    prepare_model_paper_weights_input,
    serialize_model_paper_weights_input,
)

D = Decimal
PROFILE = core.StockCycleProfile.MODEL_WEIGHTS_US_H5
ROOT = Path(__file__).resolve().parents[1]
PRESERVED_AST_SHA256 = {
    "KisPaperStockInstrument": "69302c288dc4b13a40b0010fe4bd9b0d3f0828f808104a7e202ba7a1fbea8ca9",
    "_pack": "f909497d3858d898d2298712005d18f14850e7892b07a2a40dfe9216e8fcbdc1",
    "_unpack": "ea60be192ee5bc3e99dec1f7c98f5ad8e3ec5fc385dc460b53a6710133202863",
    "_stock_identity": "c0152f8a970328eed7e136acd274140b67665dc39fa4ec21c719e96aef1da38a",
    "_stock_price_ref": "69d52ad4af285d7592ecac51422a842b510934b1c684eb19d464e05995d8675e",
    "_stock_owner_id": "18975b20b091ad08f39ac1926fd52a9f1858f4b92a360cc434a386ba0abedfb0",
    "_V1_KEYS": "a58cfab8512c158e13834e40487ee277360de56883f77a97a04a0fe9c07957de",
    "_V2_KEYS": "daa29a9318118f1ced4ca690e801b6bd9bd7de2de547128adb747c6243af1d36",
    "_V3_KEYS": "5f0aacefc64757215e3315b7fe3ace2b2041f19fbc19af23a49ce39046450054",
    "_V4_KEYS": "dbd272ab4a0810120648377682f4c4cc50a64fc779bc226a83d589ffb2615ef8",
}


@pytest.fixture(autouse=True)
def no_actual_calls(monkeypatch):
    legacy.no_actual_calls.__wrapped__(monkeypatch)


def point(profile=MODEL_PAPER_WEIGHTS_US_5_SESSION_PROFILE):
    old = metadata_fixture._prepared()
    rows = tuple(
        ModelPaperWeightRow(
            i, f"SYNA{chr(65 + i)}/" + ("AMS" if i == 16 else "NYS" if i % 2 == 0 else "NAS"),
            i != 15, D(".25") if i in (0, 16) else D(".5") if i == 1 else D(0),
        )
        for i in range(17)
    )
    return prepare_model_paper_weights_input(
        metadata_fixture._metadata(old.entry_session, old.exit_session, rows),
        entry_session=old.entry_session, exit_session=old.exit_session, profile=profile,
    )


def _native_node(path, name):
    return next(n for n in ast.parse(path.read_text()).body
                if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name == name)


def _ast_pin(node):
    # Empty optional fields differ between supported Python AST versions.
    def canonical(value):
        if isinstance(value, ast.AST):
            return [type(value).__name__, [
                [key, canonical(item)] for key, item in ast.iter_fields(value)
                if item is not None and item != []
            ]]
        if isinstance(value, list):
            return [canonical(item) for item in value]
        return value

    payload = json.dumps(canonical(node), separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def test_ast_pins_ignore_empty_version_fields_but_keep_semantic_changes():
    node = ast.parse("def original(): pass").body[0]
    pin = _ast_pin(node)
    without_empty = copy.deepcopy(node)
    without_empty._fields = tuple(
        key for key, value in ast.iter_fields(node) if value is not None and value != []
    )
    assert _ast_pin(without_empty) == pin
    without_empty.name = "changed"
    assert _ast_pin(without_empty) != pin


def test_old_instrument_and_pack_functions_are_source_identical_to_frozen_baseline():
    for relative, names in (
        ("src/thericher_v2/execution/kis_paper_stock_quote.py", ("KisPaperStockInstrument",)),
        ("src/thericher_v2/execution/kis_paper_current_stock_cycle.py", ("_pack", "_unpack")),
        ("src/thericher_v2/execution/kis_paper_budget_strategy.py",
         ("_stock_identity", "_stock_price_ref", "_stock_owner_id")),
    ):
        for name in names:
            assert _ast_pin(_native_node(ROOT / relative, name)) == PRESERVED_AST_SHA256[name]
    old = KisPaperStockInstrument("SYN", "ref:" + "a" * 64)
    assert [f.name for f in fields(old)] == ["symbol", "binding_ref"]
    assert core._pack(old) == {"type": "KisPaperStockInstrument", "value": {
        "symbol": "SYN", "binding_ref": old.binding_ref,
    }}
    relative = "src/thericher_v2/execution/kis_paper_budget_strategy.py"
    assignments = {
        n.targets[0].id: _ast_pin(n.value)
        for n in ast.parse((ROOT / relative).read_text()).body
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id in {"_V1_KEYS", "_V2_KEYS", "_V3_KEYS", "_V4_KEYS"}
    }
    assert assignments == {name: PRESERVED_AST_SHA256[name] for name in (
        "_V1_KEYS", "_V2_KEYS", "_V3_KEYS", "_V4_KEYS",
    )}


@pytest.mark.parametrize("venue,order", [("NAS", "NASD"), ("NYS", "NYSE")])
@pytest.mark.parametrize("kind", ["asking_price", "price_detail"])
def test_native_instrument_quote_codec_and_client_bind_exact_namespaces(venue, order, kind):
    instrument = KisPaperUsStockInstrument("SYN", "ref:" + "a" * 64, venue)
    assert instrument.order_exchange == order and instrument.market == "US"
    assert core._unpack(core._pack(instrument)) == instrument
    request = build_kis_paper_stock_quote_request(
        config=CONFIG, access_token="invented-only", instrument=instrument, kind=kind,
    )
    assert request.query == {"AUTH": "", "EXCD": venue, "SYMB": "SYN"}
    validate_kis_paper_stock_quote_request(request, instrument=instrument)
    with pytest.raises(KisPaperQuoteError):
        validate_kis_paper_stock_quote_request(
            replace(request, query=dict(request.query, EXCD=order)), instrument=instrument,
        )
    client = core.KisPaperStockCanaryClient(config=CONFIG, transport=None, instrument=instrument)
    client._require_target("SYN", order)
    with pytest.raises(core.canary.KisPaperCanaryError):
        client._require_target("SYN", "NYSE" if order == "NASD" else "NASD")


@pytest.mark.parametrize("venue", ["AMS", "AMEX", "NASD", "NYSE", "nys", "", None, True])
def test_unknown_missing_and_context_only_venues_are_not_instruments(venue):
    with pytest.raises(KisPaperQuoteError, match="stock_venue_invalid"):
        KisPaperUsStockInstrument("SYN", "ref:" + "a" * 64, venue)


def test_forged_or_subclassed_instrument_does_not_gain_exact_type_admission():
    class Foreign(KisPaperUsStockInstrument):
        pass

    with pytest.raises(core.KisPaperReadOnlyError):
        _instrument(Foreign("SYN", "ref:" + "a" * 64, "NYS"))
    forged = KisPaperUsStockInstrument("SYN", "ref:" + "a" * 64, "NYS")
    object.__setattr__(forged, "venue", "AMS")
    with pytest.raises(core.KisPaperReadOnlyError):
        _instrument(forged)


def test_seventeen_axis_profile_codec_masks_and_mass_remain_exact():
    value = point()
    old = point(MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE)
    assert len(value.metadata.rows) == 17 and value.metadata.rows == old.metadata.rows
    assert value.metadata.weight_bytes_ref == old.metadata.weight_bytes_ref
    assert value.metadata.feature_mask_ref == old.metadata.feature_mask_ref
    assert [t.slot for t in value.targets] == [1, 0]
    assert [t.slot for t in old.targets] == [1]
    assert value.metadata.eligible_weight == Fraction(1, 2)
    assert value.metadata.eligible_weight_for_profile(value.profile) == Fraction(3, 4)
    assert value.metadata.skipped_weight_for_profile(value.profile) == Fraction(1, 4)
    assert sum((t.proposal.target_exposure for t in value.targets), D(0)) == D(".00375")
    raw = serialize_model_paper_weights_input(value)
    loaded = load_model_paper_weights_input(
        raw, expected_sha256=hashlib.sha256(raw).hexdigest(), expected_policy_ref=value.policy_ref,
    )
    assert loaded == value == core._unpack(core._pack(value))
    assert core._validate_model_input(value, value.entry_session.open_ts, PROFILE) is value
    with pytest.raises(core._CycleFault):
        core._validate_model_input(value, value.entry_session.open_ts,
                                   core.StockCycleProfile.MODEL_WEIGHTS_NAS_H5)
    body = json.loads(raw)
    body["profile"] = MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE
    crossed = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(ValueError):
        load_model_paper_weights_input(
            crossed, expected_sha256=hashlib.sha256(crossed).hexdigest(),
            expected_policy_ref=value.policy_ref,
        )


def test_native_producer_input_file_and_exact_overlay_consumer_roundtrip(tmp_path):
    value = point()
    target = tmp_path / "INPUT.json"
    payload = serialize_model_paper_weights_input(value)
    target.write_bytes(payload)
    loaded = load_model_paper_weights_input(
        target.read_bytes(), expected_sha256=hashlib.sha256(payload).hexdigest(),
        expected_policy_ref=value.policy_ref,
    )
    assert loaded == value
    assert Path(core.__file__).resolve().is_relative_to(ROOT / "src")
    assert [type(core._target_instrument(t, PROFILE)) for t in loaded.targets] == [
        KisPaperUsStockInstrument, KisPaperUsStockInstrument,
    ]
    assert {core._target_instrument(t, PROFILE).order_exchange for t in loaded.targets} == {
        "NASD", "NYSE",
    }


def test_actual_worker_factory_exact_new_types_reuse_only_synthetic_token(monkeypatch):
    calls = []

    class SyntheticTokenTransport:
        def __init__(self, *, instrument, limits):
            self.instrument = instrument

        def request(self, request):
            assert request.url.endswith(w.readonly.KIS_PAPER_TOKEN_PATH)
            calls.append("synthetic_token")
            return w.readonly.KisHttpResponse.from_payload({"access_token": "invented-only"})

    monkeypatch.setattr(w, "OwnedTransport", SyntheticTokenTransport)
    factory = w.client_factory(CONFIG, object())
    nas = KisPaperUsStockInstrument("SYN", "ref:" + "a" * 64, "NAS")
    nys = replace(nas, venue="NYS")
    assert factory(nas).instrument == nas
    assert factory(nys).instrument == nys
    assert factory(nas) is factory(nas)
    assert calls == ["synthetic_token"]
    with pytest.raises(ValueError, match="stock_instrument_invalid"):
        factory(object())


def test_native_readonly_exact_funds_method_passes_new_order_venue_without_new_token(monkeypatch):
    captured = {}

    def invented_funds(self, token, at, **kwargs):
        captured.update(kwargs, token_reused=token == "invented-only")
        return "synthetic-cash", "synthetic-orderability"

    monkeypatch.setattr(KisPaperStockReadOnlyClient, "_cash_and_orderable_funds", invented_funds)
    client = KisPaperStockReadOnlyClient(
        config=CONFIG, transport=None, access_token="invented-only",
    )
    instrument = KisPaperUsStockInstrument("SYN", "ref:" + "a" * 64, "NYS")
    assert client.stock_orderable_funds_at_limit(instrument=instrument, limit_price=D(10)) == (
        "synthetic-cash", "synthetic-orderability",
    )
    assert captured == dict(symbol="SYN", exchange="NYSE", limit_price=D(10),
                            exact=True, token_reused=True)


def _venue_args(args, venue):
    old = args["instrument"]
    instrument = KisPaperUsStockInstrument(old.symbol, old.binding_ref, venue)
    reads = args["reads"]
    return args | dict(
        instrument=instrument,
        reads=replace(
            reads, instrument=instrument,
            orderable=replace(reads.orderable, reference_exchange=instrument.order_exchange),
        ),
    )


def test_native_mixed_bank_retains_original_nas_unknown_and_all_fingerprints(tmp_path):
    args = reservations._arguments()
    io = reservations._persist(tmp_path, args)
    first = planner.reserve_kis_paper_stock_plan(**io)
    (nas,) = first.intents
    unknown = reservations._observed(nas, phase="outcome_unknown", unavailable=True)
    budget._atomic_json(io["state_root"] / (nas.run_id + ".json"), unknown.to_dict())
    nas_bytes = (io["state_root"] / (nas.run_id + ".json")).read_bytes()
    original = copy.deepcopy(first.binding["stocks"][nas.symbol])
    fresh = reservations._fresh_target(
        args, first, symbol="NEWSYN", states={nas.run_id: unknown},
        at=args["as_of"] + timedelta(seconds=10),
    )
    fresh = _venue_args(fresh, "NYS")
    pure = planner.build_kis_paper_stock_plan(**fresh)
    assert pure.status == "prepared"
    call = {k: v for k, v in fresh.items() if k not in {"binding", "states"}}
    second = planner.reserve_kis_paper_stock_plan(
        **{k: io[k] for k in ("state_root", "repository_root", "artifact_root")}, **call,
    )
    assert second.status == "reserved" and second.intents[0].exchange == "NYSE"
    book = budget._load_binding(io["state_root"], io["expected_account_ref"])
    assert book["stocks"][nas.symbol] == original
    assert (io["state_root"] / (nas.run_id + ".json")).read_bytes() == nas_bytes
    assert set(book) == budget._V4_KEYS
    assert book["basis_ref"] == first.binding["basis_ref"]
    assert book["allocated_usd"] == first.binding["allocated_usd"]
    projection = budget.project_budget(io["state_root"], book,
                                       as_of=fresh["as_of"], stock_symbol=nas.symbol)
    assert projection.reserved_buys >= nas.quantity * nas.limit_price
    assert budget._stock_seed_states(book)[nas.run_id].intent == nas
    with pytest.raises(core._RecoveryRequired):
        planner.build_kis_paper_stock_plan(**(fresh | dict(
            binding=book, states=budget._stock_seed_states(book) | {nas.run_id: unknown},
            instrument=replace(fresh["instrument"], venue="NAS"),
            expected_owner_refs=reservations._refs(book),
        )))


@pytest.mark.parametrize("wrong", ["funds", "instrument", "account"])
def test_native_nys_planner_rejects_crossed_observation_identity(wrong):
    args = _venue_args(reservations._arguments(), "NYS")
    assert planner.build_kis_paper_stock_plan(**args).status == "prepared"
    reads = args["reads"]
    if wrong == "funds":
        reads = replace(reads, orderable=replace(reads.orderable, reference_exchange="NASD"))
    elif wrong == "instrument":
        reads = replace(reads, instrument=replace(args["instrument"], venue="NAS"))
    else:
        reads = replace(reads, account_ref="b" * 64)
    result = planner.build_kis_paper_stock_plan(**(args | dict(reads=reads)))
    assert result.status == "no_intent" and result.intents == ()


@pytest.mark.parametrize("venue", ["NAS", "NYS"])
def test_native_unknown_recovery_never_renews_or_submits_original_seed(tmp_path, venue):
    call = recovery_fixture.request()
    instrument = KisPaperUsStockInstrument("AAPL", call["proof"].instrument.binding_ref, venue)
    intent = replace(call["seed"].intent, exchange=instrument.order_exchange)
    seed = replace(call["seed"], intent=intent)
    proof = replace(call["proof"], state_root=tmp_path.resolve(), instrument=instrument,
                    intent_ref=intent.fingerprint)
    state = replace(seed, phase="outcome_unknown", submission_started_at=intent.created_at,
                    reason_code="submit_transport_unknown")
    call.update(seed=seed, state=state, proof=proof,
                as_of=intent.valid_until + timedelta(seconds=1))
    result = recovery.plan_stock_session_recovery(**call)
    assert result.action == "reconcile_unknown"
    assert result.intent == intent and result.original_valid_until == intent.valid_until


class VenueSyntheticClient(model_fixture.SyntheticClient):
    def snapshot(self, *, exit_only=False):
        original = super().snapshot(exit_only=exit_only)
        exchanges = {o["intent"].symbol: o["intent"].exchange for o in self.h["orders"].values()}
        return replace(
            original,
            positions=tuple(replace(p, exchange=exchanges.get(p.symbol, p.exchange))
                            for p in original.positions),
            open_orders=replace(original.open_orders, orders=tuple(
                replace(o, exchange=exchanges.get(o.symbol, o.exchange))
                for o in original.open_orders.orders)),
        )

    def stock_preview_snapshot(self, **kwargs):
        original = super().stock_preview_snapshot(**kwargs)
        return replace(original, orderable=replace(
            original.orderable, reference_exchange=self.instrument.order_exchange))

    def reconcile(self, state, **kwargs):
        original = super().reconcile(state, **kwargs)
        observation = original.execution
        if observation is None:
            return original
        fill = observation.fill
        if fill is None:
            return original
        fill = replace(fill, identity_ref=fill_identity_ref(
            raw_order_id=state.broker_order_id, order_at=state.submission_started_at,
            symbol=state.intent.symbol, exchange=state.intent.exchange,
            side=state.intent.side, quantity=state.intent.quantity,
        ))
        return replace(original, execution=replace(observation, fill=fill))


@pytest.fixture
def us_h(tmp_path):
    h = model_fixture.h.__wrapped__(tmp_path)
    weights.bind(h, point(), PROFILE)

    def factory(instrument):
        h["factories"] += 1
        assert type(instrument) is KisPaperUsStockInstrument
        return VenueSyntheticClient(h, instrument)

    h["call"]["client_factory"] = factory
    return h


def test_native_us_codec_planner_buy_sell_closure_retains_old_f9_and_shared_bank(us_h):
    before = budget._load_binding(us_h["root"])
    old_qqq = copy.deepcopy(before["qqq"])
    old_states = {
        row["run_id"]: (us_h["root"] / (row["run_id"] + ".json")).read_bytes()
        for row in before["qqq"]["orders"]
    }
    assert weights.visit_all(us_h)[-1].status == "hold"
    buys = tuple(us_h["submits"])
    assert {i.exchange for i in buys} == {"NASD", "NYSE"}
    assert len(buys) == 2
    us_h["now"] = us_h["data"].metadata.exit_not_before
    outcomes = weights.visit_all(us_h, target_loader=lambda: pytest.fail("retained_input_only"))
    assert outcomes[-1].status == "complete"
    assert [i.side for i in us_h["submits"]] == ["buy", "buy", "sell", "sell"]
    book = budget._load_binding(us_h["root"])
    assert book["qqq"] == old_qqq
    assert all((us_h["root"] / (run + ".json")).read_bytes() == raw
               for run, raw in old_states.items())
    assert book["basis_ref"] == before["basis_ref"]
    assert book["allocated_usd"] == before["allocated_usd"]
    for key in ("orders", "portfolio", "legacy_spy"):
        assert book[key] == before[key]
    assert {row.exchange for row, _ in budget._owners(book) if row.stock_binding_ref} == {
        "NASD", "NYSE",
    }


def test_sealed_route_prevents_pending_venue_swap_even_with_same_v1_receipt(us_h):
    us_h["unknown"] = True
    assert weights.run(us_h).status == "pending"
    record = weights.record(us_h)
    original = copy.deepcopy(record["pending"])
    args = core._unpack(original["arguments"])
    wrong = "NYS" if args["instrument"].venue == "NAS" else "NAS"
    args["instrument"] = replace(args["instrument"], venue=wrong)
    record["pending"]["arguments"] = core._pack(args)
    with pytest.raises(core._CycleFault, match="cycle_input_binding_mismatch"):
        core._model_record_input(record, us_h["data"].input_ref, us_h["data"].policy_ref, PROFILE)
    assert weights.record(us_h)["pending"] == original


def _nys_only(h):
    value = h["data"]
    rows = tuple(replace(row, weight=D(1) if row.slot == 0 else D(0))
                 for row in value.metadata.rows)
    metadata = metadata_fixture._metadata(value.entry_session, value.exit_session, rows)
    weights.bind(h, prepare_model_paper_weights_input(
        metadata, entry_session=value.entry_session, exit_session=value.exit_session,
        profile=PROFILE.value,
    ), PROFILE)


def test_native_nys_unknown_request_never_resubmits_reloads_or_releases(us_h):
    _nys_only(us_h)
    us_h["unknown"] = True
    assert weights.run(us_h).status == "pending"
    saved = weights.record(us_h)
    pending = copy.deepcopy(saved["pending"])
    assert len(us_h["submits"]) == 1 and us_h["submits"][0].exchange == "NYSE"
    intent = us_h["submits"][0]
    us_h["now"] = intent.valid_until + timedelta(seconds=1)
    def denied():
        pytest.fail("unknown_request_must_not_load_new_input")
    assert weights.run(us_h, target_loader=denied).status == "pending"
    assert weights.record(us_h)["pending"] == pending
    assert len(us_h["submits"]) == 1 and us_h["cancels"] == []
    book = budget._load_binding(us_h["root"])
    assert budget.project_budget(us_h["root"], book, as_of=us_h["now"],
                                 stock_symbol=intent.symbol).reserved_buys >= (
        intent.quantity * intent.limit_price
    )


def test_native_nys_partial_unknown_cancel_then_linked_owned_sell(us_h):
    _nys_only(us_h)
    us_h["partial"] = True
    assert weights.run(us_h).status == "pending"
    entry = us_h["submits"][0]
    assert entry.exchange == "NYSE" and entry.quantity > 1
    us_h["now"] += timedelta(minutes=6)
    us_h["cancel_unknown"] = True
    assert weights.run(us_h).status == "pending"
    assert us_h["cancels"] == [entry]
    us_h["cancel_unknown"] = False
    us_h["orders"][entry.run_id].update(remaining=D(0), cancelled=True)
    assert weights.run(us_h).status == "advanced"
    us_h["partial"] = False
    us_h["now"] = us_h["data"].metadata.exit_not_before
    assert weights.run(us_h).status == "complete"
    sell = us_h["submits"][-1]
    assert sell.side == "sell" and sell.exchange == "NYSE" and sell.quantity == 1


def test_native_us_all_sizing_no_orders_complete_without_false_fill(us_h):
    value = us_h["data"]
    value = prepare_model_paper_weights_input(
        replace(value.metadata, original_basis_gross_ceiling=D(".000001")),
        entry_session=value.entry_session, exit_session=value.exit_session, profile=PROFILE.value,
    )
    weights.bind(us_h, value, PROFILE)
    results = weights.visit_all(us_h)
    assert results[-1].status == "complete" and results[-1].reason == "policy_no_order_complete"
    assert us_h["submits"] == [] and us_h["cancels"] == []
    assert weights.record(us_h)["active"] is None
