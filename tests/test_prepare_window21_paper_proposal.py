"""Actual producer CLI on SYN-only inputs and an injected invented score function."""

import ast
import hashlib
import importlib.util
import io
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import test_kis_paper_current_stock_cycle as legacy
from thericher_v2.research.model_paper_proposal import load_model_paper_input

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/prepare_window21_paper_proposal.py"
SPEC = importlib.util.spec_from_file_location("synthetic_window21_producer_test", SCRIPT)
producer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(producer)
NOW = datetime(2026, 10, 20, 1, tzinfo=UTC)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def invented_infer(closes, metadata):
    assert closes.shape == (25, 22) and closes.dtype == np.float64
    rows = [
        dict(
            stock_slot=i + 3,
            route=route,
            score=0.9 - i / 100 if i in (0, 1, 2, 8, 9) else -1.0,
            rank=1 + sum(j < i for j in (0, 1, 2, 8, 9)) if i in (0, 1, 2, 8, 9) else 6,
            normalized_weight=0.2 if i in (0, 1, 2, 8, 9) else 0.0,
        )
        for i, route in enumerate(producer.WINDOW21_ROUTES)
    ]
    return dict(
        schema="UNTRUSTED_WINDOW21_RANK_WEIGHTS_V1",
        rows=rows,
        checkpoint_manifest_sha256=producer.CHECKPOINT_PIN,
        affine_sha256=producer.AFFINE_PIN,
        execution_authority=False,
        capital_targets_included=False,
        positive_slots=5,
        unfilled_slots=0,
        input_binding={
            k: metadata[k]
            for k in (
                "as_of",
                "source_available_utc",
                "required_previous_close_utc",
                "entry_ordinal",
                "canonical_source_ref",
                "capture_commit_ref",
                "calendar_ref",
            )
        },
    )


@pytest.fixture(autouse=True)
def no_actual_calls(monkeypatch):
    legacy.no_actual_calls.__wrapped__(monkeypatch)
    monkeypatch.setattr(producer, "_native_infer", lambda *_: pytest.fail("market_model_forbidden"))


@pytest.fixture
def bundle(tmp_path):
    stream = io.BytesIO()
    np.savez_compressed(stream, close22=np.full((25, 22), 10.0, dtype=np.float64))
    raw = stream.getvalue()
    (tmp_path / "close22.npz").write_bytes(raw)
    past, future = producer.official_sessions("2026-10-20")
    metadata = dict(
        stock_routes=list(producer.WINDOW21_ROUTES),
        stock_slots=list(range(3, 28)),
        past_ordinals=list(range(978, 1000)),
        entry_ordinal=1000,
        past_close_utc=[s.close_ts.isoformat() for s in past],
        required_previous_close_utc=past[-1].close_ts.isoformat(),
        entry_open_utc=future[0].open_ts.isoformat(),
        known=[[True] * 22 for _ in range(25)],
        source_available_utc="2026-10-19T23:00:00+00:00",
        as_of="2026-10-20T00:00:00+00:00",
        **dict.fromkeys(
            ("canonical_source_ref", "capture_commit_ref", "calendar_ref"), "sha256:" + "3" * 64
        ),
    )
    document = dict(
        schema="WINDOW21_CANONICAL_CLOSE_INPUT_V1",
        entry_date="2026-10-20",
        metadata=metadata,
        close_ref=dict(path="close22.npz", sha256=sha(raw)),
    )
    policy = dict(
        schema="WINDOW21_MODEL_PAPER_POLICY_V1",
        adapter_ready_sha256=producer.READY_PIN,
        original_basis_gross_ceiling=".025",
        exit_minutes_before_close=20,
    )
    return dict(root=tmp_path, document=document, policy=policy, calls=[])


def prepare(bundle, *, infer=None):
    def tracked(closes, metadata):
        bundle["calls"].append(True)
        return (infer or invented_infer)(closes, metadata)

    moments = iter(NOW + timedelta(seconds=i) for i in range(3))
    body, policy = encoded(bundle["document"]), encoded(bundle["policy"])
    return producer.prepare(
        body,
        input_sha256=sha(body),
        policy_payload=policy,
        policy_sha256=sha(policy),
        input_directory=bundle["root"],
        clock=lambda: next(moments),
        infer=tracked,
    )


def test_prepared_seal_uses_actual_clocks_22_sessions_full25_and_unspent_mass(bundle):
    value = prepare(bundle)
    assert len(bundle["calls"]) == 1 and len(value.metadata.rows) == 25
    assert [t.proposal.symbol for t in value.targets] == ["AAPL", "AMD", "AMZN"]
    assert value.metadata.inference_started_at == NOW
    assert value.metadata.inference_completed_at == NOW + timedelta(seconds=1)
    assert value.metadata.score_observed_at == NOW + timedelta(seconds=2)
    assert value.exit_session.close_ts == datetime(2026, 10, 26, 20, tzinfo=UTC)
    assert value.metadata.model_ref == "sha256:" + producer.CHECKPOINT_PIN
    assert value.metadata.affine_ref == "sha256:" + producer.AFFINE_PIN
    assert value.metadata.exit_not_before == datetime(2026, 10, 26, 19, 40, tzinfo=UTC)


def test_real_cli_creates_canonical_pinned_json_and_refuses_overwrite(bundle, monkeypatch, capsys):
    root = bundle["root"]
    source, policy = encoded(bundle["document"]), encoded(bundle["policy"])
    (root / "input.json").write_bytes(source)
    (root / "policy.json").write_bytes(policy)
    monkeypatch.setattr(producer, "_native_infer", invented_infer)
    monkeypatch.setattr(
        producer,
        "datetime",
        SimpleNamespace(now=lambda _: NOW, fromisoformat=datetime.fromisoformat),
    )
    arguments = [
        "--input-manifest",
        str(root / "input.json"),
        "--input-sha256",
        sha(source),
        "--policy",
        str(root / "policy.json"),
        "--policy-sha256",
        sha(policy),
        "--output",
        str(root / "proposal.json"),
    ]
    assert producer.main(arguments) == 0
    receipt = json.loads(capsys.readouterr().out)
    payload = (root / "proposal.json").read_bytes()
    value = load_model_paper_input(
        payload, expected_sha256=sha(payload), expected_policy_ref="sha256:" + sha(policy)
    )
    assert value.input_ref == receipt["input_ref"] and receipt["model_rows"] == 25
    assert receipt["unsupported_venue_rows"] == 15 and receipt["targets"] == 3
    assert receipt["full_universe_performance_claim"] is False
    assert receipt["replay_payoff_equivalent"] is False
    assert receipt["fixed5_inactive_cash_preserved"] is True
    with pytest.raises(ValueError, match="producer_output_create_once"):
        producer.main(arguments)


def score_fixture(scores, weights):
    def infer(closes, metadata):
        result = invented_infer(closes, metadata)
        result["positive_slots"] = min(5, sum(score > 0 for score in scores))
        result["unfilled_slots"] = 5 - result["positive_slots"]
        for index, row in enumerate(result["rows"]):
            row.update(
                score=scores[index],
                rank=1 + sum(score > scores[index] for score in scores),
                normalized_weight=weights[index],
            )
        return result

    return infer


@pytest.mark.parametrize(
    "selected", [(0,), (8,), (0, 1, 2), (0, 1, 8), (8, 9, 10), (0, 1, 2, 3, 4), (0, 1, 2, 8, 9)]
)
def test_fixed5_one_three_five_positives_preserve_inactive_and_nys_cash(bundle, selected):
    bundle["policy"]["original_basis_gross_ceiling"] = ".10"
    scores = [1.0 if i in selected else -1.0 for i in range(25)]
    weights = [1 / len(selected) if i in selected else 0.0 for i in range(25)]
    value = prepare(bundle, infer=score_fixture(scores, weights))
    expected_gross = Decimal(".10") * len(selected) / 5
    assert value.metadata.original_basis_gross_ceiling == expected_gross
    assert [r.weight for r in value.metadata.rows] == [Decimal(str(w)) for w in weights]
    assert [t.slot - 3 for t in value.targets] == [
        i for i in selected if producer.WINDOW21_ROUTES[i].endswith("/NAS")
    ]
    # Each active original slot is .10 / 5, never .10 / active-or-eligible count.
    for target in value.targets:
        assert Decimal(0) <= Decimal(".02") - target.proposal.target_exposure < Decimal("1e-17")
    actual = sum((Fraction(t.proposal.target_exposure) for t in value.targets), Fraction())
    expected_nas = Fraction(Decimal(".02")) * len(value.targets)
    assert actual <= expected_nas <= Fraction(expected_gross)
    payload = producer.serialize_model_paper_input(value)
    assert (
        load_model_paper_input(
            payload, expected_sha256=sha(payload), expected_policy_ref=value.policy_ref
        )
        == value
    )


@pytest.mark.parametrize("score", [-1.0, 0.0])
def test_no_positive_signal_preserves_full25_with_empty_targets_not_zero_dto_ceiling(bundle, score):
    bundle["policy"]["original_basis_gross_ceiling"] = ".10"
    value = prepare(bundle, infer=score_fixture([score] * 25, [0.0] * 25))
    assert len(value.metadata.rows) == 25 and value.targets == ()
    assert all(r.weight == 0 for r in value.metadata.rows)
    assert value.metadata.original_basis_gross_ceiling == Decimal(".10")
    payload = producer.serialize_model_paper_input(value)
    assert (
        load_model_paper_input(
            payload, expected_sha256=sha(payload), expected_policy_ref=value.policy_ref
        ).targets
        == ()
    )


def test_fixed5_fair_fifth_place_ties_share_remaining_slots_before_nys_skip(bundle):
    bundle["policy"]["original_basis_gross_ceiling"] = ".10"
    scores, weights = [-1.0] * 25, [0.0] * 25
    for index in (0, 1):
        scores[index], weights[index] = 2.0, 0.2
    for index in (2, 3, 8, 9):
        scores[index], weights[index] = 1.0, 0.15
    value = prepare(bundle, infer=score_fixture(scores, weights))
    assert value.metadata.original_basis_gross_ceiling == Decimal(".10")
    amounts = {t.slot - 3: t.proposal.target_exposure for t in value.targets}
    assert amounts == {0: Decimal(".02"), 1: Decimal(".02"), 2: Decimal(".015"), 3: Decimal(".015")}
    assert sum(amounts.values()) == Decimal(".07")
    assert [value.metadata.rows[i].weight for i in (2, 3, 8, 9)] == [Decimal(".15")] * 4
    assert value.metadata.skipped_weight == Fraction(3, 10)


def test_positive_support_permutation_never_renormalizes_by_route_or_index(bundle):
    bundle["policy"]["original_basis_gross_ceiling"] = ".10"
    scores = np.array([2.0, 2.0, 1.0, 1.0, 1.0, 1.0] + [-1.0] * 19)
    weights = np.array([0.2, 0.2, 0.15, 0.15, 0.15, 0.15] + [0.0] * 19)
    order = np.random.default_rng(2801).permutation(25)
    for indices in (np.arange(25), order):
        given_scores, given_weights = scores[indices].tolist(), weights[indices].tolist()
        value = prepare(bundle, infer=score_fixture(given_scores, given_weights))
        assert value.metadata.original_basis_gross_ceiling == Decimal(".10")
        assert [r.weight for r in value.metadata.rows] == [Decimal(str(w)) for w in given_weights]
        amounts = {t.slot - 3: t.proposal.target_exposure for t in value.targets}
        expected = {
            i: Decimal(".10") * Decimal(str(weight))
            for i, weight in enumerate(given_weights)
            if weight > 0 and producer.WINDOW21_ROUTES[i].endswith("/NAS")
        }
        assert amounts == expected
        assert sum(amounts.values()) <= Decimal(".10")


def test_fixed5_scaling_is_independent_of_ambient_decimal_precision(bundle):
    bundle["policy"]["original_basis_gross_ceiling"] = ".123456789123456789123456789"
    scores, weights = [1.0, 1.0, 1.0] + [-1.0] * 22, [1 / 3] * 3 + [0.0] * 22
    normal = prepare(bundle, infer=score_fixture(scores, weights))
    with localcontext() as context:
        context.prec = 6
        low = prepare(bundle, infer=score_fixture(scores, weights))
    assert producer.serialize_model_paper_input(low) == producer.serialize_model_paper_input(normal)


@pytest.mark.parametrize(
    "fault", ["positive_slots", "unfilled_slots", "false_zero", "negative_weighted"]
)
def test_fixed5_adapter_mass_receipt_cannot_silently_expand_gross(bundle, fault):
    def infer(closes, metadata):
        result = invented_infer(closes, metadata)
        if fault == "positive_slots":
            result["positive_slots"] = 3
        elif fault == "unfilled_slots":
            result["unfilled_slots"] = 3
        elif fault == "false_zero":
            result["positive_slots"], result["unfilled_slots"] = 0, 5
        else:
            result["rows"][0]["score"] = -1.0
            result["positive_slots"], result["unfilled_slots"] = 4, 1
        return result

    with pytest.raises(ValueError, match="producer_fixed5"):
        prepare(bundle, infer=infer)


@pytest.mark.parametrize(
    "fault",
    [
        "unknown",
        "route",
        "session",
        "ordinal",
        "ref",
        "future",
        "before_close",
        "ceiling",
        "adapter",
        "member",
        "object",
        "nonpositive",
        "path",
        "dtype",
        "exit_lead",
    ],
)
def test_input_faults_fail_before_any_forward(bundle, fault):
    metadata, policy = bundle["document"]["metadata"], bundle["policy"]
    if fault == "unknown":
        metadata["known"][0][0] = False
    elif fault == "route":
        metadata["stock_routes"][8] = "JPM/NAS"
    elif fault == "session":
        metadata["past_close_utc"][0] = metadata["past_close_utc"][1]
    elif fault == "ordinal":
        metadata["past_ordinals"][0] += 1
    elif fault == "ref":
        metadata["capture_commit_ref"] = "not-attested"
    elif fault == "future":
        metadata["as_of"] = "2026-10-20T14:00:00+00:00"
    elif fault == "before_close":
        metadata["source_available_utc"] = "2026-10-19T19:00:00+00:00"
    elif fault == "ceiling":
        policy["original_basis_gross_ceiling"] = "2"
    elif fault == "adapter":
        policy["adapter_ready_sha256"] = "4" * 64
    elif fault == "path":
        bundle["document"]["close_ref"]["path"] = "../close22.npz"
    elif fault == "exit_lead":
        policy["exit_minutes_before_close"] = 0
    else:
        stream = io.BytesIO()
        array = np.full(
            (25, 22),
            10.0,
            dtype=object if fault == "object" else np.float32 if fault == "dtype" else np.float64,
        )
        if fault == "nonpositive":
            array[0, 0] = 0
        members = dict(close22=array)
        if fault == "member":
            members["targets"] = np.zeros(25)
        np.savez_compressed(stream, **members)
        raw = stream.getvalue()
        (bundle["root"] / "close22.npz").write_bytes(raw)
        bundle["document"]["close_ref"]["sha256"] = sha(raw)
    with pytest.raises((ValueError, TypeError)):
        prepare(bundle)
    assert bundle["calls"] == []


@pytest.mark.parametrize("fault", ["rows", "input", "authority", "checkpoint", "weights"])
def test_adapter_output_is_bound_not_executable_or_silently_rerouted(bundle, fault):
    def infer(closes, metadata):
        output = invented_infer(closes, metadata)
        if fault == "rows":
            output["rows"][8]["route"] = "JPM/NAS"
        elif fault == "input":
            output["input_binding"]["as_of"] = "2026-10-19T00:00:00+00:00"
        elif fault == "authority":
            output["execution_authority"] = True
        elif fault == "checkpoint":
            output["checkpoint_manifest_sha256"] = "4" * 64
        else:
            output["rows"][0]["normalized_weight"] = 2.0
        return output

    with pytest.raises(ValueError):
        prepare(bundle, infer=infer)
    assert len(bundle["calls"]) == 1


def test_calendar_scope_and_fixed_trusted_module_boundary():
    with pytest.raises(ValueError):
        producer.official_sessions("2027-01-05")
    source = SCRIPT.read_text()
    imports = [
        node.module or ""
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    ]
    assert all("execution" not in name and "kis_" not in name for name in imports)
    assert "--module" not in source and "--python" not in source
    assert "allow_pickle=False" in source
    assert (
        len(
            {
                producer.READY_PIN,
                producer.SOURCE_PIN,
                producer.ADAPTER_PIN,
                producer.BINDING_PIN,
                producer.CHECKPOINT_PIN,
                producer.AFFINE_PIN,
            }
        )
        == 6
    )
