"""Invented exact identities only; no file, account, broker or model access."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from thericher_v2.execution.paper_cohort_attribution import (
    AccountedPaperOwner,
    PaperCohortBinding,
    PaperCohortSchedule,
    PaperOwnerCounts,
    PaperOwnerIdentity,
    attribute_paper_cohorts,
)

AT = datetime(2026, 10, 26, 10, tzinfo=UTC)
PIN = "sha256:" + "1" * 64
OTHER = "sha256:" + "2" * 64
IDENTITY = PaperOwnerIdentity("a" * 64, PIN, "invented-private-owner", OTHER)
COUNTS = PaperOwnerCounts(3, 2, 2, 2, 3, 0)


def owner(**changes):
    return replace(AccountedPaperOwner(IDENTITY, PIN, OTHER, COUNTS, "positive", PIN), **changes)


def binding(**changes):
    return replace(PaperCohortBinding(IDENTITY, PIN, OTHER, "SYN-H20", PIN), **changes)


def schedule(**changes):
    return replace(
        PaperCohortSchedule(
            IDENTITY.account_ref,
            IDENTITY.basis_ref,
            "SYN-H20",
            PIN,
            OTHER,
            "exit",
            AT + timedelta(days=20),
            AT + timedelta(days=20, minutes=20),
            True,
            PIN,
        ),
        **changes,
    )


def project(o=None, bs=None, ss=None):
    return attribute_paper_cohorts(
        (owner() if o is None else o,),
        (binding(),) if bs is None else bs,
        (schedule(),) if ss is None else ss,
        as_of=AT,
    )[0]


def test_exact_join_and_count_only_public_projection():
    row = project()
    assert row.status == "mapped" and row.cohort_label == "SYN-H20"
    assert row.positive_owner_scopes == 1 and row.exit_status == "paired"
    payload = row.safe_payload()
    text = json.dumps(payload)
    assert IDENTITY.account_ref not in text and IDENTITY.owner_ref not in text
    assert IDENTITY.owner_binding_ref not in text
    assert payload["broker_holdings"] == "not_established"
    assert payload["distinct_execution_count"] == "not_established"
    assert payload["counts"]["positive_cumulative_fill_states"] == 2
    assert all(payload[k] == "not_observed" for k in ("fees", "settlement", "net_pnl"))
    assert payload["reservation_release"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("account_ref", "b" * 64),
        ("basis_ref", OTHER),
        ("owner_ref", "other-owner"),
        ("owner_binding_ref", PIN),
    ],
)
def test_every_identity_dimension_is_exact(field, value):
    wrong = binding(identity=replace(IDENTITY, **{field: value}))
    row = project(bs=(wrong,))
    assert row.status == "unmapped" and row.cohort_label is None and not row.schedules


@pytest.mark.parametrize("field", ["input_ref", "policy_ref"])
def test_input_and_policy_are_not_interchangeable(field):
    row = project(o=owner(**{field: None}))
    assert row.status == "unmapped" and row.exit_status == "unknown"


def test_multiple_historical_input_owner_is_not_latest_model_credit():
    row = project(o=owner(input_ref=None, policy_ref=None))
    assert row.counts == COUNTS and row.status == "unmapped"


def test_competing_exact_bindings_remain_ambiguous():
    row = project(bs=(binding(), binding(cohort_label="SYN-COMPETING")))
    assert row.status == "ambiguous" and row.cohort_label is None
    assert row.exit_status == "unknown" and not row.schedules


@pytest.mark.parametrize(
    "change",
    [
        dict(account_ref="b" * 64),
        dict(basis_ref=OTHER),
        dict(input_ref=OTHER),
        dict(policy_ref=PIN),
        dict(cohort_label="SYN-OTHER"),
        dict(enabled=False),
        dict(starts_at=AT - timedelta(minutes=20), ends_at=AT),
    ],
)
def test_schedule_scoped_binding_and_inclusive_end(change):
    assert project(ss=(schedule(**change),)).exit_status == "missing"


def test_owned_recovery_schedule_is_labelled_as_recovery_not_success():
    row = project(ss=(schedule(phase="recovery"),))
    assert row.exit_status == "recovery_only"
    assert row.safe_payload()["schedules"][0]["phase"] == "recovery"
    assert row.safe_payload()["recovery_schedule_proves_exit"] is False


def test_exit_plus_recovery_has_exit_coverage_but_neither_proves_success():
    row = project(ss=(schedule(), schedule(phase="recovery")))
    assert row.exit_status == "paired" and len(row.schedules) == 2
    assert row.safe_payload()["broker_holdings"] == "not_established"


@pytest.mark.parametrize("field", ["account_ref", "owner_ref", "basis_ref", "owner_binding_ref"])
@pytest.mark.parametrize("value", [None, True, 1, [], b"not-text"])
def test_identity_types_fail_categorically_before_string_operations(field, value):
    with pytest.raises(ValueError, match="paper_attribution_(identity|reference)_invalid"):
        replace(IDENTITY, **{field: value})


def test_entry_phase_cannot_count_as_an_exit_schedule():
    with pytest.raises(ValueError, match="schedule_invalid"):
        schedule(phase="entry")


def test_unknown_inventory_or_pending_never_becomes_no_exit_needed():
    assert project(o=owner(inventory="unknown")).exit_status == "unknown"
    pending = PaperOwnerCounts(1, 1, 0, 0, 0, 1)
    assert project(o=owner(inventory="flat", counts=pending)).exit_status == "unknown"
    assert project(o=owner(inventory="flat")).exit_status == "not_required"


def test_partial_schedule_does_not_cover_another_positive_input():
    second_identity = replace(IDENTITY, owner_ref="second-owner")
    second_owner = owner(identity=second_identity, input_ref=OTHER)
    second_binding = binding(identity=second_identity, input_ref=OTHER)
    rows = attribute_paper_cohorts(
        (owner(), second_owner),
        (binding(), second_binding),
        (schedule(),),
        as_of=AT,
    )
    assert len(rows) == 1 and rows[0].positive_owner_scopes == 2
    assert rows[0].exit_status == "missing"


def test_one_canonical_owner_is_not_counted_twice_with_new_binding():
    with pytest.raises(ValueError, match="duplicate_owner"):
        attribute_paper_cohorts(
            (owner(), owner(identity=replace(IDENTITY, owner_binding_ref=PIN))),
            (),
            (),
            as_of=AT,
        )


@pytest.mark.parametrize(
    "counts",
    [
        (-1, 0, 0, 0, 0, 0),
        (1, 2, 0, 0, 0, 0),
        (1, 0, 1, 0, 0, 0),
        (1, 1, 0, 0, 1, 1),
        (True, 0, 0, 0, 0, 0),
    ],
)
def test_invalid_counts_are_categorical(counts):
    with pytest.raises(ValueError, match="paper_attribution_counts"):
        PaperOwnerCounts(*counts)


def test_empty_input_is_not_invented_zero_profit():
    assert attribute_paper_cohorts((), (), (), as_of=AT) == ()


def test_duplicate_same_mapping_does_not_double_counts():
    assert project(bs=(binding(), binding())).counts == COUNTS
