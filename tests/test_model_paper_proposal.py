"""Pure sealed proposal ABI; invented scores, no model/account/market reads."""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction

import pytest

from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.research.model_paper_proposal import (
    ModelPaperMetadata,
    ModelPaperRow,
    load_model_paper_input,
    prepare_model_paper_input,
    serialize_model_paper_input,
)

D = Decimal
PIN = "sha256:" + "1" * 64
POLICY = "sha256:" + "2" * 64
ROUTES = (
    "AAPL/NAS",
    "AMD/NAS",
    "AMZN/NAS",
    "GOOGL/NAS",
    "META/NAS",
    "MSFT/NAS",
    "NVDA/NAS",
    "TSLA/NAS",
    "JPM/NYS",
    "JNJ/NYS",
    "XOM/NYS",
    "PG/NYS",
    "KO/NYS",
    "HD/NYS",
    "V/NYS",
    "DIS/NYS",
    "UNH/NYS",
    "COST/NAS",
    "LLY/NYS",
    "CAT/NYS",
    "MS/NYS",
    "CVX/NYS",
    "NEE/NYS",
    "VZ/NYS",
    "ADBE/NAS",
)


def prepared(*, selected=(0, 1, 2, 8, 9), policy=POLICY, entry=date(2026, 10, 19), **changes):
    first = us_equity_2026_session(entry).window
    prior_day = entry - timedelta(days=1)
    while us_equity_2026_session(prior_day) is None:
        prior_day -= timedelta(days=1)
    previous = us_equity_2026_session(prior_day).window.close_ts
    last_day, count = entry, 1
    while count < 5:
        last_day += timedelta(days=1)
        count += int(us_equity_2026_session(last_day) is not None)
    last = us_equity_2026_session(last_day).window
    stamp = first.open_ts - timedelta(hours=1)
    metadata = ModelPaperMetadata(
        "synthetic-window21-not-winner",
        "synthetic-close-return-21",
        PIN,
        PIN,
        PIN,
        PIN,
        PIN,
        policy,
        PIN,
        previous,
        previous + timedelta(hours=1),
        stamp,
        stamp,
        stamp,
        stamp,
        last.close_ts - timedelta(minutes=20),
        D(".025"),
        tuple(
            ModelPaperRow(
                i + 3, route, D(1) - D(i) / 100, i + 1, D(".2") if i in selected else D(0)
            )
            for i, route in enumerate(ROUTES)
        ),
    )
    metadata = replace(metadata, **changes)
    return prepare_model_paper_input(metadata, entry_session=first, exit_session=last)


def reload(value):
    payload = serialize_model_paper_input(value)
    return load_model_paper_input(
        payload,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        expected_policy_ref=value.policy_ref,
    )


def test_full25_roundtrip_keeps_skips_and_original_mass_not_replacement():
    value = prepared()
    assert reload(value) == value
    assert json.loads(serialize_model_paper_input(value))["execution_payoff"] == (
        "operational_execution_proxy_not_replay_equivalent"
    )
    assert len(value.metadata.rows) == 25 and len(value.targets) == 3
    assert sum(r.route.endswith("/NAS") for r in value.metadata.rows) == 10
    assert [t.route for t in value.targets] == list(ROUTES[:3])
    assert value.metadata.eligible_weight == Fraction(3, 5)
    assert value.metadata.skipped_weight == Fraction(2, 5)
    assert all(
        t.research_weight == D(".2") and t.proposal.target_exposure == D(".005")
        for t in value.targets
    )
    assert sum(t.proposal.target_exposure for t in value.targets) == D(".015")
    assert all("quantity" not in t.proposal.__dataclass_fields__ for t in value.targets)
    assert (
        value.input_ref
        == "sha256:" + hashlib.sha256(serialize_model_paper_input(value)).hexdigest()
    )


def test_all_selected_nys_is_empty_proposal_not_renormalized_nas():
    value = prepared(selected=(8, 9, 10, 11, 12))
    assert not value.targets and value.metadata.eligible_weight == 0
    assert value.metadata.skipped_weight == 1 and len(reload(value).metadata.rows) == 25


def test_generic_profile_has_no_five_expert_fixed_target_count_or_uniform_weight_gate():
    value = prepared()
    rows = tuple(replace(r, weight=D(".04")) for r in value.metadata.rows)
    tied = prepared(rows=rows)
    assert len(tied.targets) == 10
    assert all(t.proposal.target_exposure == D(".001") for t in tied.targets)
    one = prepared(
        selected=(),
        rows=tuple(
            replace(r, weight=D(".123456789123456789123456789") if i == 0 else D(0))
            for i, r in enumerate(rows)
        ),
    )
    assert len(one.targets) == 1 and reload(one) == one


def test_independent_decimal_floor_is_context_free_and_never_increases_any_weight():
    base = prepared()
    rows = tuple(
        replace(r, weight=D(".3333333333333333") if i in (0, 8, 9) else D(0))
        for i, r in enumerate(base.metadata.rows)
    )
    normal = prepared(rows=rows)
    with localcontext() as context:
        context.prec = 6
        low = prepared(rows=rows)
        assert serialize_model_paper_input(low) == serialize_model_paper_input(normal)
    for t in low.targets:
        assert Fraction(t.proposal.target_exposure) <= Fraction(D(".025")) * Fraction(
            t.research_weight
        )


@pytest.mark.parametrize("fault", ["hash", "policy", "duplicate", "profile", "target", "row_extra"])
def test_pin_canonical_shape_profile_and_derived_target_tampering_rejected(fault):
    value = prepared()
    payload = serialize_model_paper_input(value)
    expected_policy = value.policy_ref
    if fault == "duplicate":
        payload = b'{"schema":"duplicate",' + payload[1:]
    elif fault in {"profile", "target", "row_extra"}:
        document = json.loads(payload)
        if fault == "profile":
            document["profile"] = "legacy-nas"
        elif fault == "target":
            document["targets"][0]["proposal"]["target_exposure"] = ".01"
        else:
            document["metadata"]["rows"][0]["quantity"] = 100
        payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    elif fault == "policy":
        expected_policy = PIN
    pin = "0" * 64 if fault == "hash" else hashlib.sha256(payload).hexdigest()
    with pytest.raises(ValueError):
        load_model_paper_input(payload, expected_sha256=pin, expected_policy_ref=expected_policy)


@pytest.mark.parametrize(
    "fault", ["negative", "nan", "venue", "slot", "duplicate", "future", "sum"]
)
def test_invalid_metadata_and_weight_caps_rejected(fault):
    value = prepared()
    with pytest.raises(ValueError):
        if fault == "negative":
            replace(value.metadata.rows[0], weight=D("-.1"))
        elif fault == "nan":
            replace(value.metadata.rows[0], score=D("NaN"))
        elif fault == "venue":
            replace(value.metadata.rows[0], route="AAPL/AMS")
        elif fault == "slot":
            replace(value.metadata.rows[0], slot=True)
        elif fault == "duplicate":
            replace(value.metadata, rows=(value.metadata.rows[0],) * 2)
        elif fault == "future":
            prepared(score_observed_at=datetime(2026, 10, 19, 15, tzinfo=UTC))
        else:
            replace(
                value.metadata, rows=tuple(replace(r, weight=D(".2")) for r in value.metadata.rows)
            )


def test_model_input_targets_cannot_be_mutated_even_with_valid_receipts():
    value = prepared()
    with pytest.raises(ValueError, match="model_target_composition_changed"):
        replace(value, targets=value.targets[:1])


def test_new_profile_timing_must_be_aware_and_within_declared_fifth_session():
    value = prepared()
    for stamp in (
        value.exit_session.open_ts - timedelta(seconds=1),
        value.exit_session.close_ts,
        value.metadata.exit_not_before.replace(tzinfo=None),
    ):
        with pytest.raises(ValueError, match="model_exit_window_invalid"):
            prepared(exit_not_before=stamp)
