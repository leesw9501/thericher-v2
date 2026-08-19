"""Source-safe, two-page temporal-reach evidence for the isolated IWM route."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Literal, Protocol

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.data.kis_paper_iwm_current_head import (
    validate_kis_paper_iwm_current_head_ingestion_artifact_root,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataError,
    KisPaperMinutePage,
    KisPaperMinuteQuery,
    derive_kis_paper_minute_continuation_key,
)

KIS_PAPER_IWM_TEMPORAL_REACH_PROBE_KIND = "kis_paper_iwm_m1_temporal_reach_probe"
KIS_PAPER_IWM_TEMPORAL_REACH_PROBE_ARTIFACT_DIRECTORY = (
    "data/kis-paper-iwm-m1-temporal-reach-continuation-probe"
)
KIS_PAPER_IWM_TEMPORAL_REACH_PROBE_TARGET = ("IWM", "AMS")
KIS_PAPER_IWM_TEMPORAL_REACH_PROBE_TARGET_KEY = "IWM/AMS/1m"


class KisPaperIwmTemporalReachProbeClient(Protocol):
    @property
    def call_counts(self) -> KisPaperMarketDataCallCounts: ...

    def fetch_minute_page(self, query: KisPaperMinuteQuery) -> KisPaperMinutePage: ...


@dataclass(frozen=True, slots=True)
class KisPaperIwmTemporalReachProbeOutcome:
    """Only aggregate facts from one head-plus-optional-continuation attempt."""

    status: Literal[
        "reachable",
        "continuation_not_observed",
        "input_unavailable",
        "non_older_or_conflicting",
    ]
    token_request_count: int
    minute_page_request_count: int
    accepted_page_count: int
    continuation_disposition: Literal[
        "head_unavailable",
        "header_not_recognized",
        "continuation_unavailable",
        "accepted_older_nonconflicting",
        "accepted_non_older_or_conflicting",
    ]
    page_yield_category: Literal["no_accepted_page", "head_only", "head_and_continuation"]
    overlap_direction: Literal[
        "not_observed",
        "strictly_older_nonconflicting",
        "overlap_or_not_older",
    ]
    elapsed_time_bucket: Literal["under_one_second", "under_one_minute", "one_minute_or_more"]
    target_key: str = KIS_PAPER_IWM_TEMPORAL_REACH_PROBE_TARGET_KEY
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        counts = (
            self.token_request_count,
            self.minute_page_request_count,
            self.accepted_page_count,
        )
        if (
            self.target_key != KIS_PAPER_IWM_TEMPORAL_REACH_PROBE_TARGET_KEY
            or self.schema_version != SCHEMA_VERSION
            or any(type(value) is not int or value < 0 for value in counts)
            or self.minute_page_request_count > 2
            or self.accepted_page_count > self.minute_page_request_count
            or self.accepted_page_count > 2
            or self.page_yield_category != _page_yield_category(self.accepted_page_count)
        ):
            raise ValueError("IWM temporal-reach probe outcome is invalid")
        expected = {
            "reachable": (
                2,
                "accepted_older_nonconflicting",
                "strictly_older_nonconflicting",
            ),
            "continuation_not_observed": (1, "header_not_recognized", "not_observed"),
            "non_older_or_conflicting": (
                2,
                "accepted_non_older_or_conflicting",
                "overlap_or_not_older",
            ),
        }.get(self.status)
        if expected is not None:
            if (
                self.accepted_page_count,
                self.continuation_disposition,
                self.overlap_direction,
            ) != expected:
                raise ValueError("IWM temporal-reach probe outcome is invalid")
        elif self.status == "input_unavailable":
            if self.continuation_disposition not in {
                "head_unavailable",
                "continuation_unavailable",
            } or self.overlap_direction != "not_observed":
                raise ValueError("IWM temporal-reach probe outcome is invalid")
        else:
            raise ValueError("IWM temporal-reach probe outcome is invalid")

    def safe_payload(self) -> dict[str, object]:
        """Return no timestamps, cursors, rows, values, paths, or secrets."""

        return {
            "schema_version": self.schema_version,
            "kind": KIS_PAPER_IWM_TEMPORAL_REACH_PROBE_KIND,
            "status": self.status,
            "paper_only": True,
            "route_class": "kis_paper_market_data",
            "target_key": self.target_key,
            "request_counts": {
                "token": self.token_request_count,
                "minute_page": self.minute_page_request_count,
            },
            "accepted_page_count": self.accepted_page_count,
            "continuation_disposition": self.continuation_disposition,
            "page_yield_category": self.page_yield_category,
            "overlap_direction": self.overlap_direction,
            "elapsed_time_bucket": self.elapsed_time_bucket,
            "model_input_eligibility": False,
        }


@dataclass(frozen=True, slots=True)
class KisPaperIwmTemporalReachProbeReceipt:
    """External location for a deterministic source-safe probe receipt."""

    outcome: KisPaperIwmTemporalReachProbeOutcome
    evidence_path: Path = field(repr=False)
    evidence_sha256: str

    def __post_init__(self) -> None:
        if not _is_sha256(self.evidence_sha256):
            raise ValueError("IWM temporal-reach probe receipt is invalid")


def run_kis_paper_iwm_temporal_reach_probe(
    *,
    client: KisPaperIwmTemporalReachProbeClient,
    monotonic_clock: Callable[[], float] = monotonic,
) -> KisPaperIwmTemporalReachProbeOutcome:
    """Attempt one IWM head and only a header-gated caller-derived continuation."""

    started = monotonic_clock()
    head: KisPaperMinutePage | None = None
    continuation: KisPaperMinutePage | None = None
    try:
        head = client.fetch_minute_page(
            KisPaperMinuteQuery(
                symbol="IWM",
                exchange="AMS",
                request_intent="iwm_temporal_reach_probe_head",
            )
        )
        if head.next_cursor is None:
            return _outcome(
                client=client,
                status="continuation_not_observed",
                accepted_page_count=1,
                continuation_disposition="header_not_recognized",
                overlap_direction="not_observed",
                started=started,
                monotonic_clock=monotonic_clock,
            )
        continuation = client.fetch_minute_page(
            KisPaperMinuteQuery(
                symbol="IWM",
                exchange="AMS",
                include_previous_day=True,
                continuation_next="1",
                continuation_key=derive_kis_paper_minute_continuation_key(head),
                request_intent="iwm_temporal_reach_probe_continuation",
            )
        )
    except KisPaperMarketDataError:
        return _outcome(
            client=client,
            status="input_unavailable",
            accepted_page_count=1 if head is not None else 0,
            continuation_disposition=(
                "continuation_unavailable" if head is not None else "head_unavailable"
            ),
            overlap_direction="not_observed",
            started=started,
            monotonic_clock=monotonic_clock,
        )

    if continuation is None:
        raise AssertionError("IWM temporal-reach probe continuation is unavailable")
    overlap_direction = _overlap_direction(head=head, continuation=continuation)
    return _outcome(
        client=client,
        status=(
            "reachable"
            if overlap_direction == "strictly_older_nonconflicting"
            else "non_older_or_conflicting"
        ),
        accepted_page_count=2,
        continuation_disposition=(
            "accepted_older_nonconflicting"
            if overlap_direction == "strictly_older_nonconflicting"
            else "accepted_non_older_or_conflicting"
        ),
        overlap_direction=overlap_direction,
        started=started,
        monotonic_clock=monotonic_clock,
    )


def run_and_write_kis_paper_iwm_temporal_reach_probe(
    *,
    client: KisPaperIwmTemporalReachProbeClient,
    artifact_root: Path,
    repo_root: Path,
    monotonic_clock: Callable[[], float] = monotonic,
) -> KisPaperIwmTemporalReachProbeReceipt:
    """Run the two-attempt probe and retain only its categorical receipt."""

    outcome = run_kis_paper_iwm_temporal_reach_probe(
        client=client,
        monotonic_clock=monotonic_clock,
    )
    return write_kis_paper_iwm_temporal_reach_probe_evidence(
        outcome=outcome,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )


def write_kis_paper_iwm_temporal_reach_probe_evidence(
    *,
    outcome: KisPaperIwmTemporalReachProbeOutcome,
    artifact_root: Path,
    repo_root: Path,
) -> KisPaperIwmTemporalReachProbeReceipt:
    """Atomically write a deterministic receipt outside the Git workspace."""

    root = validate_kis_paper_iwm_temporal_reach_probe_artifact_root(
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    _ensure_real_directory(root)
    payload = _canonical_json_bytes(outcome.safe_payload()) + b"\n"
    digest = hashlib.sha256(payload).hexdigest()
    directory = root / KIS_PAPER_IWM_TEMPORAL_REACH_PROBE_ARTIFACT_DIRECTORY
    _ensure_external_descendant_directory(root=root, path=directory)
    destination = directory / f"{digest[:16]}.json"
    _validate_destination(root=root, destination=destination)
    if destination.exists():
        if destination.read_bytes() != payload:
            raise ValueError("IWM temporal-reach probe evidence conflicts")
    else:
        staging = destination.with_name(f".{digest[:16]}.{uuid.uuid4().hex[:8]}.stage")
        _validate_destination(root=root, destination=staging)
        try:
            staging.write_bytes(payload)
            os.replace(staging, destination)
        finally:
            staging.unlink(missing_ok=True)
    return KisPaperIwmTemporalReachProbeReceipt(
        outcome=outcome,
        evidence_path=destination,
        evidence_sha256=f"sha256:{digest}",
    )


def validate_kis_paper_iwm_temporal_reach_probe_artifact_root(
    *,
    artifact_root: Path,
    repo_root: Path,
) -> Path:
    """Validate the source-safe external receipt root without creating it."""

    return validate_kis_paper_iwm_current_head_ingestion_artifact_root(
        artifact_root=artifact_root,
        repository_root=repo_root,
    )


def _outcome(
    *,
    client: KisPaperIwmTemporalReachProbeClient,
    status: Literal[
        "reachable",
        "continuation_not_observed",
        "input_unavailable",
        "non_older_or_conflicting",
    ],
    accepted_page_count: int,
    continuation_disposition: Literal[
        "head_unavailable",
        "header_not_recognized",
        "continuation_unavailable",
        "accepted_older_nonconflicting",
        "accepted_non_older_or_conflicting",
    ],
    overlap_direction: Literal[
        "not_observed",
        "strictly_older_nonconflicting",
        "overlap_or_not_older",
    ],
    started: float,
    monotonic_clock: Callable[[], float],
) -> KisPaperIwmTemporalReachProbeOutcome:
    counts = client.call_counts
    return KisPaperIwmTemporalReachProbeOutcome(
        status=status,
        token_request_count=counts.token_attempts,
        minute_page_request_count=counts.minute_page_attempts,
        accepted_page_count=accepted_page_count,
        continuation_disposition=continuation_disposition,
        page_yield_category=_page_yield_category(accepted_page_count),
        overlap_direction=overlap_direction,
        elapsed_time_bucket=_elapsed_time_bucket(max(0.0, monotonic_clock() - started)),
    )


def _overlap_direction(
    *,
    head: KisPaperMinutePage,
    continuation: KisPaperMinutePage,
) -> Literal["strictly_older_nonconflicting", "overlap_or_not_older"]:
    head_stamps = tuple(
        f"{row.exchange_date}{row.exchange_time}" for row in head.bars
    )
    continuation_stamps = tuple(
        f"{row.exchange_date}{row.exchange_time}" for row in continuation.bars
    )
    if (
        len(head_stamps) != len(set(head_stamps))
        or len(continuation_stamps) != len(set(continuation_stamps))
        or max(continuation_stamps) >= min(head_stamps)
    ):
        return "overlap_or_not_older"
    return "strictly_older_nonconflicting"


def _page_yield_category(
    accepted_page_count: int,
) -> Literal["no_accepted_page", "head_only", "head_and_continuation"]:
    if accepted_page_count == 0:
        return "no_accepted_page"
    if accepted_page_count == 1:
        return "head_only"
    if accepted_page_count == 2:
        return "head_and_continuation"
    raise ValueError("IWM temporal-reach probe accepted-page count is invalid")


def _elapsed_time_bucket(
    elapsed_seconds: float,
) -> Literal["under_one_second", "under_one_minute", "one_minute_or_more"]:
    if elapsed_seconds < 1:
        return "under_one_second"
    if elapsed_seconds < 60:
        return "under_one_minute"
    return "one_minute_or_more"


def _ensure_real_directory(path: Path) -> None:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError("IWM temporal-reach probe artifact destination is invalid")
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("IWM temporal-reach probe artifact destination is invalid")


def _ensure_external_descendant_directory(*, root: Path, path: Path) -> None:
    if not path.is_relative_to(root):
        raise ValueError("IWM temporal-reach probe artifact destination is invalid")
    current = root
    for component in path.relative_to(root).parts:
        current = current / component
        _ensure_real_directory(current)


def _validate_destination(*, root: Path, destination: Path) -> None:
    if destination.is_symlink() or (destination.exists() and not destination.is_file()):
        raise ValueError("IWM temporal-reach probe evidence destination is invalid")
    if not destination.resolve(strict=False).is_relative_to(root.resolve()):
        raise ValueError("IWM temporal-reach probe evidence destination is invalid")


def _canonical_json_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _is_sha256(value: str) -> bool:
    prefix, separator, digest = value.partition(":")
    return (
        prefix == "sha256"
        and separator == ":"
        and len(digest) == 64
        and all(character in "0123456789abcdef" for character in digest)
    )
