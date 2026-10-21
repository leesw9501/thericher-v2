"""FUND20 native compatibility with invented data and temporary synthetic custody."""

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, fields, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest

import test_kis_paper_current_stock_cycle as legacy
import test_model_paper_profile as model_native
from test_model_paper_proposal import PIN, prepared
from thericher_v2.contracts import require_utc
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution import kis_paper_current_stock_cycle as cycle
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research import model_paper_proposal as model
from thericher_v2.research.model_paper_horizon import MODEL_PAPER_20_SESSION_PROFILE

V1 = "model-proposal-nas-v1"
V20 = MODEL_PAPER_20_SESSION_PROFILE
D = Decimal
CEILING = D(".025")


@pytest.fixture(autouse=True)
def no_actual_calls(monkeypatch):
    legacy.no_actual_calls.__wrapped__(monkeypatch)


def point20(*, ceiling=CEILING):
    base = prepared(entry=date(2026, 10, 21))
    first = base.entry_session
    last = us_equity_2026_session(date(2026, 11, 17)).window
    known = (0, 1, 2, 3, 8, 9, 10, 11)
    rows = tuple(replace(base.metadata.rows[i], score=-D(i + 1)) for i in known)
    sidecar = dict(
        rows=[asdict(r) for r in rows],
        mask25=[dict(slot=i + 3, known=i in known) for i in range(25)],
    )
    holding = dict(
        execution_profile=V1,
        input_holding_profile=V20,
        point_ref=PIN,
        arm="SYN_FUND",
        calendar_ref=PIN,
        entry_session=asdict(first),
        exit_session=asdict(last),
        exit_not_before=last.close_ts - timedelta(minutes=15),
        original_basis_gross_ceiling=ceiling,
        bank="EXISTING_SHARED_INITIAL_TENTH",
        venue="NAS_ONLY_NYS_UNSPENT_NO_RENORMALIZATION",
    )
    metadata = replace(
        base.metadata,
        rows=rows,
        original_basis_gross_ceiling=ceiling,
        full_output_ref=model._digest(sidecar),
        policy_ref=model._digest(holding),
        exit_not_before=holding["exit_not_before"],
    )
    return (
        model.prepare_model_paper_input(
            metadata, entry_session=first, exit_session=last, profile=V20
        ),
        sidecar,
        holding,
    )


# Frozen v1 point codec, namespaced to coexist with the new implementation.
# Its profile/14-day checks and native unpack algorithm intentionally do not call
# the new loader/validator. Common metadata and target codecs are unchanged.
@dataclass(frozen=True, slots=True)
class _V1Input:
    metadata: model.ModelPaperMetadata
    targets: tuple[model.ModelPaperTarget, ...]
    entry_session: SessionWindow
    exit_session: SessionWindow
    profile: str = V1
    execution_payoff: str = "operational_execution_proxy_not_replay_equivalent"

    def __post_init__(self):
        model._need(type(self) is _V1Input and self.profile == V1, "model_profile_invalid")
        model._need(
            self.execution_payoff == "operational_execution_proxy_not_replay_equivalent",
            "model_execution_payoff_invalid",
        )
        model._need(type(self.metadata) is model.ModelPaperMetadata, "model_metadata_invalid")
        self.metadata.__post_init__()
        model._need(
            type(self.entry_session) is SessionWindow and type(self.exit_session) is SessionWindow,
            "model_sessions_invalid",
        )
        first, last = self.entry_session, self.exit_session
        model._need(
            self.metadata.score_observed_at
            < first.open_ts
            < first.close_ts
            < last.open_ts
            < last.close_ts
            <= first.open_ts + timedelta(days=14),
            "model_session_clocks_invalid",
        )
        model._need(
            type(self.metadata.exit_not_before) is datetime
            and self.metadata.exit_not_before.utcoffset() == timedelta(0)
            and last.open_ts <= self.metadata.exit_not_before < last.close_ts,
            "model_exit_window_invalid",
        )
        model._need(
            type(self.targets) is tuple and self.targets == model._targets(self.metadata, first),
            "model_target_composition_changed",
        )


def _v1_serialize(value):
    model._need(type(value) is _V1Input, "model_input_type_invalid")
    return model._canonical(dict(schema="model-paper-proposal-input-v1", **asdict(value)))


def _v1_load(payload, *, expected_sha256, expected_policy_ref):
    model._need(
        type(payload) is bytes
        and len(payload) <= 1024 * 1024
        and hashlib.sha256(payload).hexdigest() == expected_sha256,
        "model_input_pin_mismatch",
    )
    document = json.loads(
        payload,
        object_pairs_hook=model._unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("model_nonfinite")),
    )
    model._need(
        set(document)
        == {
            "schema",
            "profile",
            "metadata",
            "targets",
            "entry_session",
            "exit_session",
            "execution_payoff",
        }
        and document.pop("schema") == "model-paper-proposal-input-v1"
        and document["profile"] == V1,
        "model_input_schema_invalid",
    )
    raw = document["metadata"]
    model._need(
        set(raw) == {f.name for f in fields(model.ModelPaperMetadata)},
        "model_metadata_fields_invalid",
    )
    values = dict(raw)
    for name in (
        "feature_window_end",
        "source_available_at",
        "input_asof",
        "inference_started_at",
        "inference_completed_at",
        "score_observed_at",
        "exit_not_before",
    ):
        values[name] = require_utc(datetime.fromisoformat(raw[name]))
    values["original_basis_gross_ceiling"] = D(raw["original_basis_gross_ceiling"])
    values["rows"] = tuple(
        model.ModelPaperRow(r["slot"], r["route"], D(r["score"]), r["rank"], D(r["weight"]))
        for r in raw["rows"]
    )
    metadata = model.ModelPaperMetadata(**values)
    model._need(metadata.policy_ref == expected_policy_ref, "model_policy_pin_mismatch")

    def session(value):
        model._need(set(value) == {"open_ts", "close_ts"}, "model_session_fields_invalid")
        return SessionWindow(
            **{k: require_utc(datetime.fromisoformat(v)) for k, v in value.items()}
        )

    first, last = session(document["entry_session"]), session(document["exit_session"])
    result = _V1Input(metadata, model._targets(metadata, first), first, last)
    model._need(_v1_serialize(result) == payload, "model_payload_not_canonical_or_derived")
    return result


def _v1_unpack(value):
    if type(value) is not dict:
        return value
    if set(value) == {"type", "value"}:
        tag, item = value["type"], value["value"]
        if tag == "datetime":
            return require_utc(datetime.fromisoformat(item))
        if tag in {"Decimal", "Fraction"}:
            return (D if tag == "Decimal" else Fraction)(item)
        if tag == "tuple":
            return tuple(_v1_unpack(v) for v in item)
        types = cycle._TYPES | {"ModelPaperInput": _V1Input}
        cycle._check(tag in types, "cycle_value_invalid")
        return types[tag](**{key: _v1_unpack(v) for key, v in item.items()})
    return {key: _v1_unpack(item) for key, item in value.items()}


def _v1_projection(root, binding, at):
    states = cycle._states(root, binding)
    replayed, proofs = cycle._replay_scope(binding, states)
    projection = cycle.budget.project_shared_budget(
        binding=binding,
        states=states,
        expected_account_ref=binding["account_ref"],
        expected_basis_ref=binding["basis_ref"],
        expected_owner_refs=cycle._refs(binding),
        as_of=at,
    )
    return states, replayed, proofs, projection


def load_point(value, **changes):
    payload = model.serialize_model_paper_input(value)
    kwargs = dict(
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        expected_policy_ref=value.policy_ref,
        expected_profile=V20,
    )
    return model.load_model_paper_input(payload, **(kwargs | changes))


def test_v1_wire_bytes_and_native_codec_match_frozen_old_default():
    value = prepared()
    payload = model.serialize_model_paper_input(value)
    old = _v1_load(
        payload,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        expected_policy_ref=value.policy_ref,
    )
    assert _v1_serialize(old) == payload
    assert _v1_serialize(_v1_unpack(cycle._pack(value))) == payload
    assert cycle._unpack(cycle._pack(value)) == value
    assert (
        model.load_model_paper_input(
            payload,
            expected_sha256=hashlib.sha256(payload).hexdigest(),
            expected_policy_ref=value.policy_ref,
        )
        == value
    )
    assert value.profile == V1


def test_explicit_v20_wire_native_codec_and_old_readers_fail_closed():
    value, _, _ = point20()
    payload = model.serialize_model_paper_input(value)
    assert load_point(value) == value
    assert cycle._unpack(cycle._pack(value)) == value
    assert _v1_unpack(cycle._pack(value.targets)) == value.targets
    kwargs = dict(
        expected_sha256=hashlib.sha256(payload).hexdigest(), expected_policy_ref=value.policy_ref
    )
    for reader in (_v1_load, model.load_model_paper_input):
        with pytest.raises(ValueError, match="model_input_schema_invalid"):
            reader(payload, **kwargs)
    packed = cycle._pack(value)
    before = copy.deepcopy(packed)
    with pytest.raises(ValueError, match="model_profile_invalid"):
        _v1_unpack(packed)
    assert packed == before
    with pytest.raises(ValueError, match="model_session_clocks_invalid"):
        model.prepare_model_paper_input(
            value.metadata, entry_session=value.entry_session, exit_session=value.exit_session
        )


@pytest.mark.parametrize("expected", ["unknown", "model-proposal-nas-20session-v0", None])
def test_unsupported_expected_profile_fails_closed(expected):
    value, _, _ = point20()
    with pytest.raises(ValueError, match="model_profile_invalid"):
        load_point(value, expected_profile=expected)
    with pytest.raises(ValueError, match="model_profile_invalid"):
        replace(value, profile=expected)


@pytest.mark.parametrize("minutes", [0, 14, 16, 30, 400])
def test_new_holding_profile_enforces_exact_fifteen_minute_proxy(minutes):
    value, _, _ = point20()
    metadata = replace(
        value.metadata, exit_not_before=value.exit_session.close_ts - timedelta(minutes=minutes)
    )
    with pytest.raises(ValueError, match="model_20session_exit_proxy_invalid"):
        replace(value, metadata=metadata)
    forged = copy.copy(value)
    object.__setattr__(forged, "metadata", metadata)
    with pytest.raises(cycle._CycleFault, match="cycle_session_invalid"):
        cycle._validate_input(
            forged, value.entry_session.open_ts, cycle.StockCycleProfile.MODEL_PROPOSAL_NAS
        )


def test_full_eight_and_twentyfive_mask_survive_without_imputation_or_renormalization():
    value, sidecar, _ = point20()
    assert len(value.metadata.rows) == 8
    assert len(sidecar["mask25"]) == 25
    assert sum(not row["known"] for row in sidecar["mask25"]) == 17
    assert len(value.targets) == 3
    assert value.metadata.full_output_ref == model._digest(sidecar)
    assert all(row.score < 0 for row in value.metadata.rows)
    assert sum(t.proposal.target_exposure for t in value.targets) == D(".015")
    assert value.metadata.skipped_weight == Fraction(2, 5)
    assert load_point(value).metadata.rows == value.metadata.rows


def test_holding_contract_policy_and_input_fingerprints_bind_request_identity():
    value, _, holding = point20()
    changed, _, _ = point20(ceiling=D(".020"))
    assert value.policy_ref == model._digest(holding)
    assert value.policy_ref != prepared().policy_ref
    assert changed.policy_ref != value.policy_ref and changed.input_ref != value.input_ref
    assert cycle.model_paper_pointer(changed.policy_ref) != cycle.model_paper_pointer(
        value.policy_ref
    )
    payload = model.serialize_model_paper_input(value)
    assert value.input_ref == "sha256:" + hashlib.sha256(payload).hexdigest()
    document = json.loads(payload)
    document["profile"] = V1
    altered = model._canonical(document)
    assert "sha256:" + hashlib.sha256(altered).hexdigest() != value.input_ref
    with pytest.raises(ValueError, match="model_input_schema_invalid"):
        model.load_model_paper_input(
            altered,
            expected_sha256=hashlib.sha256(altered).hexdigest(),
            expected_policy_ref=value.policy_ref,
            expected_profile=V20,
        )
    with pytest.raises(ValueError, match="model_policy_pin_mismatch"):
        load_point(value, expected_policy_ref=changed.policy_ref)


@pytest.mark.parametrize("fault", ["hash", "profile", "target", "exit", "duplicate"])
def test_pinned_v20_loader_rejects_tampering_even_with_recomputed_hash(fault):
    value, _, _ = point20()
    payload = model.serialize_model_paper_input(value)
    document = json.loads(payload)
    if fault == "profile":
        document["profile"] = "unsupported"
    elif fault == "target":
        document["targets"][0]["proposal"]["target_exposure"] = ".1"
    elif fault == "exit":
        document["metadata"]["exit_not_before"] = value.exit_session.close_ts.isoformat()
    payload = model._canonical(document)
    if fault == "duplicate":
        payload = b'{"profile":"duplicate",' + payload[1:]
    with pytest.raises(ValueError):
        model.load_model_paper_input(
            payload,
            expected_sha256="0" * 64 if fault == "hash" else hashlib.sha256(payload).hexdigest(),
            expected_policy_ref=value.policy_ref,
            expected_profile=V20,
        )


@pytest.fixture
def h(tmp_path):
    value = model_native.h.__wrapped__(tmp_path)
    value["data"], _, _ = point20()
    value["now"] = value["data"].entry_session.open_ts + timedelta(minutes=30)
    value["call"].update(
        expected_input_ref=value["data"].input_ref, expected_policy_ref=value["data"].policy_ref
    )
    return value


def test_native_v20_own_registry_and_legacy_global_book_keep_original_bank_and_canaries(
    h, monkeypatch
):
    binding = cycle._book(h["root"], h["call"]["expected_account_ref"])
    old_states = {k: v.to_dict() for k, v in cycle._states(h["root"], binding).items()}
    assert model_native.visit_all(h)[-1].status == "hold"
    saved = model_native.record(h)
    assert saved["profile"] == V1 and cycle.StockCycleProfile.MODEL_PROPOSAL_NAS.value == V1
    assert saved["owner_key"] == h["data"].policy_ref
    assert cycle._unpack(saved["active"]["model_input"]) == h["data"]
    cycle._model_record_input(saved, h["data"].input_ref, h["data"].policy_ref)
    binding = cycle._book(h["root"], h["call"]["expected_account_ref"])
    for key in ("basis_ref", "allocated_usd", "orders", "qqq", "portfolio"):
        assert binding[key] == h["initial"][key]
    # Global projection uses referenced native canary states, not foreign model DTOs.
    with monkeypatch.context() as guard:
        guard.setattr(cycle, "_unpack", lambda _: pytest.fail("global_book_not_model_unpack"))
        projected = cycle._projection(h["root"], binding, h["now"])
        assert _v1_projection(h["root"], binding, h["now"]) == projected
    assert all(projected[0][k].to_dict() == v for k, v in old_states.items())
    assert len(h["submits"]) == 3


def test_unknown_v20_request_recovers_before_loader_and_never_refreshes_identity_or_reservation(h):
    h["unknown"] = True
    assert model_native.run(h).status == "pending"
    pending = copy.deepcopy(model_native.record(h)["pending"])
    args = cycle._unpack(pending["arguments"])
    expected = "model-" + cycle.budget._digest(
        [
            h["data"].policy_ref,
            h["data"].input_ref,
            args["instrument"].binding_ref,
            "buy",
            0,
            h["data"].entry_session.open_ts.isoformat(),
        ]
    )
    assert args["request_id"] == expected
    bank = (h["root"] / cycle.budget.BUDGET_FILE).read_bytes()
    h["now"] = h["data"].exit_session.close_ts + timedelta(days=1)
    for _ in range(2):
        assert (
            model_native.run(h, target_loader=lambda: pytest.fail("pending_before_loader")).status
            == "pending"
        )
    assert model_native.record(h)["pending"]["arguments"] == pending["arguments"]
    assert (h["root"] / cycle.budget.BUDGET_FILE).read_bytes() == bank
    assert len(h["submits"]) == 1


@pytest.mark.parametrize("fault", ["profile", "input", "policy", "request", "exit"])
def test_retained_tamper_is_rejected_before_loader_or_client_without_reset(h, fault):
    h["unknown"] = True
    assert model_native.run(h).status == "pending"
    saved = model_native.record(h)
    if fault == "profile":
        saved["active"]["model_input"]["value"]["profile"] = "unsupported"
    elif fault == "input":
        saved["active"]["input_ref"] = PIN
    elif fault == "policy":
        saved["owner_key"] = PIN
    elif fault == "request":
        saved["pending"]["arguments"]["request_id"] = "model-synthetic-tampered"
    else:
        saved["active"]["exit_session"] = cycle._pack(h["data"].entry_session)
    path = h["root"] / cycle.model_paper_pointer(h["data"].policy_ref)
    cycle._save(path, saved)
    before = path.read_bytes()
    bank = (h["root"] / cycle.budget.BUDGET_FILE).read_bytes()
    outcome = model_native.run(
        h,
        target_loader=lambda: pytest.fail("tamper_before_loader"),
        client_factory=lambda _: pytest.fail("tamper_before_client"),
    )
    assert outcome.status == "unavailable"
    assert path.read_bytes() == before
    assert (h["root"] / cycle.budget.BUDGET_FILE).read_bytes() == bank
    assert len(h["submits"]) == 1


def test_old_v1_unknown_cannot_be_rebound_to_twenty_session_input_or_reset(h):
    h["data"] = prepared(entry=date(2026, 10, 21))
    h["call"].update(
        expected_input_ref=h["data"].input_ref, expected_policy_ref=h["data"].policy_ref
    )
    h["unknown"] = True
    assert model_native.run(h).status == "pending"
    old = h["data"]
    path = h["root"] / cycle.model_paper_pointer(old.policy_ref)
    before = path.read_bytes()
    bank = (h["root"] / cycle.budget.BUDGET_FILE).read_bytes()
    new, _, _ = point20()
    # Deliberate invalid policy reuse: a new input cannot adopt a pending v1 owner.
    reused = model.prepare_model_paper_input(
        replace(new.metadata, policy_ref=old.policy_ref),
        entry_session=new.entry_session,
        exit_session=new.exit_session,
        profile=V20,
    )
    outcome = model_native.run(
        h,
        expected_input_ref=reused.input_ref,
        target_loader=lambda: pytest.fail("old_unknown_before_loader"),
        client_factory=lambda _: pytest.fail("old_unknown_before_client"),
    )
    assert outcome.status == "unavailable"
    assert path.read_bytes() == before
    assert (h["root"] / cycle.budget.BUDGET_FILE).read_bytes() == bank
    assert len(h["submits"]) == 1


def test_native_exit_waits_for_proxy_and_closes_owned_model_only(h):
    assert model_native.visit_all(h)[-1].status == "hold"
    h["now"] = h["data"].metadata.exit_not_before - timedelta(seconds=1)
    assert model_native.run(h, target_loader=lambda: pytest.fail("hold_no_reload")).status == "hold"
    assert len(h["submits"]) == 3
    h["now"] += timedelta(seconds=1)
    assert (
        model_native.visit_all(h, target_loader=lambda: pytest.fail("owned_exit_no_reload"))[
            -1
        ].status
        == "complete"
    )
    assert len(h["submits"]) == 6
    assert all(intent.side == "sell" for intent in h["submits"][3:])
    assert cycle.budget._load_binding(h["root"])["qqq"] == h["initial"]["qqq"]
