"""Pure count-only attribution of already accounted Paper owner scopes.

The caller establishes native journal/plan/intent/fill lineage and stable,
source-admitted custody. This join cannot establish broker holdings, execution
permission, scheduler origin, distinct fill events, settlement or net PnL.
Private identities stay in memory and never enter the safe projection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from thericher_v2.contracts import require_utc

_PIN = re.compile(r"sha256:[0-9a-f]{64}")
_ACCOUNT = re.compile(r"[0-9a-f]{64}")
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}")


def _pin(value: str) -> None:
    if type(value) is not str or _PIN.fullmatch(value) is None:
        raise ValueError("paper_attribution_reference_invalid")


@dataclass(frozen=True, slots=True, repr=False)
class PaperOwnerIdentity:
    account_ref: str
    basis_ref: str
    owner_ref: str
    owner_binding_ref: str

    def __post_init__(self) -> None:
        if (
            type(self.account_ref) is not str
            or _ACCOUNT.fullmatch(self.account_ref) is None
            or type(self.owner_ref) is not str
            or not self.owner_ref
        ):
            raise ValueError("paper_attribution_identity_invalid")
        _pin(self.basis_ref)
        _pin(self.owner_binding_ref)


@dataclass(frozen=True, slots=True)
class PaperOwnerCounts:
    intents: int
    submit_attempts: int
    acknowledged_references: int
    positive_cumulative_fill_states: int
    terminal_order_states: int
    unresolved_attempts: int

    def __post_init__(self) -> None:
        values = tuple(getattr(self, key) for key in self.__dataclass_fields__)
        if any(type(v) is not int or v < 0 for v in values):
            raise ValueError("paper_attribution_counts_invalid")
        if (
            any(v > self.intents for v in values[1:])
            or self.acknowledged_references > self.submit_attempts
            or self.unresolved_attempts > self.submit_attempts
            or self.terminal_order_states + self.unresolved_attempts > self.intents
        ):
            raise ValueError("paper_attribution_counts_inconsistent")


@dataclass(frozen=True, slots=True, repr=False)
class AccountedPaperOwner:
    identity: PaperOwnerIdentity
    input_ref: str | None
    policy_ref: str | None
    counts: PaperOwnerCounts
    inventory: Literal["positive", "flat", "unknown"]
    evidence_ref: str

    def __post_init__(self) -> None:
        if (
            type(self.identity) is not PaperOwnerIdentity
            or type(self.counts) is not PaperOwnerCounts
        ):
            raise TypeError("paper_attribution_owner_type")
        if self.inventory not in {"positive", "flat", "unknown"}:
            raise ValueError("paper_attribution_inventory_invalid")
        for value in (self.input_ref, self.policy_ref):
            if value is not None:
                _pin(value)
        _pin(self.evidence_ref)


@dataclass(frozen=True, slots=True, repr=False)
class PaperCohortBinding:
    identity: PaperOwnerIdentity
    input_ref: str
    policy_ref: str
    cohort_label: str
    evidence_ref: str

    def __post_init__(self) -> None:
        if type(self.identity) is not PaperOwnerIdentity:
            raise TypeError("paper_attribution_binding_type")
        if type(self.cohort_label) is not str or _LABEL.fullmatch(self.cohort_label) is None:
            raise ValueError("paper_attribution_label_invalid")
        for value in (self.input_ref, self.policy_ref, self.evidence_ref):
            _pin(value)


@dataclass(frozen=True, slots=True, repr=False)
class PaperCohortSchedule:
    account_ref: str
    basis_ref: str
    cohort_label: str
    input_ref: str
    policy_ref: str
    phase: Literal["exit", "recovery"]
    starts_at: datetime
    ends_at: datetime
    enabled: bool
    evidence_ref: str

    def __post_init__(self) -> None:
        if type(self.account_ref) is not str or _ACCOUNT.fullmatch(self.account_ref) is None:
            raise ValueError("paper_attribution_identity_invalid")
        _pin(self.basis_ref)
        if type(self.cohort_label) is not str or _LABEL.fullmatch(self.cohort_label) is None:
            raise ValueError("paper_attribution_label_invalid")
        for value in (self.input_ref, self.policy_ref, self.evidence_ref):
            _pin(value)
        if self.phase not in {"exit", "recovery"} or type(self.enabled) is not bool:
            raise ValueError("paper_attribution_schedule_invalid")
        if require_utc(self.starts_at) >= require_utc(self.ends_at):
            raise ValueError("paper_attribution_schedule_window_invalid")


@dataclass(frozen=True, slots=True)
class PaperCohortAttribution:
    cohort_label: str | None
    status: Literal["mapped", "unmapped", "ambiguous"]
    owner_scopes: int
    positive_owner_scopes: int
    unknown_inventory_owner_scopes: int
    counts: PaperOwnerCounts
    exit_status: Literal["paired", "recovery_only", "missing", "not_required", "unknown"]
    schedules: tuple[PaperCohortSchedule, ...]
    evidence_refs: tuple[str, ...]

    def safe_payload(self) -> dict[str, object]:
        return {
            "cohort_label": self.cohort_label,
            "status": self.status,
            "owner_scopes": self.owner_scopes,
            "positive_owner_scopes": self.positive_owner_scopes,
            "unknown_inventory_owner_scopes": self.unknown_inventory_owner_scopes,
            "counts": {key: getattr(self.counts, key) for key in self.counts.__dataclass_fields__},
            "exit_status": self.exit_status,
            "recovery_schedule_proves_exit": False,
            "schedules": [
                {
                    "phase": s.phase,
                    "starts_at": s.starts_at.isoformat(),
                    "ends_at": s.ends_at.isoformat(),
                    "evidence_ref": s.evidence_ref,
                }
                for s in self.schedules
            ],
            "evidence_refs": list(self.evidence_refs),
            "broker_holdings": "not_established",
            "distinct_execution_count": "not_established",
            "fees": "not_observed",
            "settlement": "not_observed",
            "net_pnl": "not_observed",
            "reservation_release": False,
        }


def attribute_paper_cohorts(
    owners: tuple[AccountedPaperOwner, ...],
    bindings: tuple[PaperCohortBinding, ...],
    schedules: tuple[PaperCohortSchedule, ...],
    *,
    as_of: datetime,
) -> tuple[PaperCohortAttribution, ...]:
    """Exact identity+input+policy join; no inference from names or inventory.

    One native owner may contain multiple historical inputs. The caller must
    withhold its input/policy rather than assign all cumulative counts to its
    latest model. Supplied schedules are dated, independently attested facts,
    not proof of a running or future successful exit/recovery.
    """
    require_utc(as_of)
    for sequence, cls in (
        (owners, AccountedPaperOwner),
        (bindings, PaperCohortBinding),
        (schedules, PaperCohortSchedule),
    ):
        if type(sequence) is not tuple or any(type(v) is not cls for v in sequence):
            raise TypeError("paper_attribution_sequence_type")
    if len(
        {(o.identity.account_ref, o.identity.basis_ref, o.identity.owner_ref) for o in owners}
    ) != len(owners):
        raise ValueError("paper_attribution_duplicate_owner")
    groups: dict[tuple[str | None, str], list[AccountedPaperOwner]] = {}
    selected: dict[PaperOwnerIdentity, PaperCohortBinding] = {}
    for owner in owners:
        matches = [
            b
            for b in bindings
            if b.identity == owner.identity
            and b.input_ref == owner.input_ref
            and b.policy_ref == owner.policy_ref
        ]
        keys = {(b.cohort_label, b.input_ref, b.policy_ref) for b in matches}
        if len(keys) == 1:
            label = matches[0].cohort_label
            selected[owner.identity] = matches[0]
            key = (label, "mapped")
        else:
            key = (None, "ambiguous" if keys else "unmapped")
        groups.setdefault(key, []).append(owner)
    result = []
    for (label, status), group in sorted(groups.items(), key=lambda x: str(x[0])):
        positive = sum(o.inventory == "positive" for o in group)
        unknown = sum(o.inventory == "unknown" for o in group)
        unresolved = sum(o.counts.unresolved_attempts for o in group)
        exact = {
            (o.identity.account_ref, o.identity.basis_ref, b.input_ref, b.policy_ref)
            for o in group
            if (b := selected.get(o.identity)) is not None
        }
        paired = tuple(
            s
            for s in schedules
            if label is not None
            and s.cohort_label == label
            and (s.account_ref, s.basis_ref, s.input_ref, s.policy_ref) in exact
            and s.enabled
            and s.ends_at > as_of
        )
        covered = (
            all(
                any(
                    (s.account_ref, s.basis_ref, s.input_ref, s.policy_ref)
                    == (
                        o.identity.account_ref,
                        o.identity.basis_ref,
                        selected[o.identity].input_ref,
                        selected[o.identity].policy_ref,
                    )
                    for s in paired
                    if s.phase == "exit"
                )
                for o in group
                if o.inventory == "positive"
            )
            if status == "mapped"
            else False
        )
        exit_status = (
            "unknown"
            if status != "mapped" or unknown or unresolved
            else "not_required"
            if not positive
            else "paired"
            if covered
            else "recovery_only"
            if any(s.phase == "recovery" for s in paired)
            else "missing"
        )
        result.append(
            PaperCohortAttribution(
                label,
                status,
                len(group),
                positive,
                unknown,
                PaperOwnerCounts(
                    *(
                        sum(getattr(o.counts, key) for o in group)
                        for key in PaperOwnerCounts.__dataclass_fields__
                    )
                ),
                exit_status,
                paired,
                tuple(
                    sorted(
                        {o.evidence_ref for o in group}
                        | {
                            selected[o.identity].evidence_ref
                            for o in group
                            if o.identity in selected
                        }
                    )
                ),
            )
        )
    return tuple(result)
