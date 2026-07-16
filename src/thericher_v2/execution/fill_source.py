"""Fill-source evidence helpers for local-paper attribution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .local_paper import LOCAL_PAPER_SOURCE


@dataclass(frozen=True)
class FillEventArtifact:
    path: Path | None
    expected_fill_count: int
    label: str = ""

    def __post_init__(self) -> None:
        if self.expected_fill_count < 0:
            raise ValueError("expected_fill_count must be non-negative")


@dataclass(frozen=True)
class FillSourceEvidence:
    fill_source_counts: dict[str, int]
    local_paper_fills: tuple[dict[str, Any], ...]
    unreadable_event_artifacts: tuple[str, ...]
    missing_zero_fill_event_artifacts: tuple[str, ...]
    unknown_fill_count: int

    @property
    def non_local_fill_source_counts(self) -> dict[str, int]:
        return {
            source: count
            for source, count in self.fill_source_counts.items()
            if source != LOCAL_PAPER_SOURCE
        }

    @property
    def all_fills_local_paper(self) -> bool:
        return (
            not self.non_local_fill_source_counts
            and not self.unreadable_event_artifacts
            and self.unknown_fill_count == 0
        )

    def to_summary(self) -> dict[str, Any]:
        return {
            "fill_source_counts": self.fill_source_counts,
            "local_paper_fill_count": self.fill_source_counts.get(LOCAL_PAPER_SOURCE, 0),
            "non_local_fill_source_counts": self.non_local_fill_source_counts,
            "unknown_fill_count": self.unknown_fill_count,
            "unreadable_event_artifacts": list(self.unreadable_event_artifacts),
            "missing_zero_fill_event_artifacts": list(
                self.missing_zero_fill_event_artifacts
            ),
            "all_fills_local_paper": self.all_fills_local_paper,
        }


def collect_fill_source_evidence(
    event_artifacts: tuple[FillEventArtifact, ...],
) -> FillSourceEvidence:
    fill_source_counts: dict[str, int] = {}
    local_paper_fills: list[dict[str, Any]] = []
    unreadable_artifacts: list[str] = []
    missing_zero_fill_artifacts: list[str] = []
    unknown_fill_count = 0
    for event_artifact in event_artifacts:
        path = event_artifact.path
        if path is None or not path.exists():
            if event_artifact.expected_fill_count == 0:
                if path is not None:
                    missing_zero_fill_artifacts.append(str(path))
                continue
            unreadable_artifacts.append(_artifact_label(event_artifact))
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            if event_artifact.expected_fill_count == 0:
                missing_zero_fill_artifacts.append(str(path))
                continue
            unreadable_artifacts.append(_artifact_label(event_artifact))
            continue
        try:
            fill_payloads = tuple(_fill_payloads(lines))
        except (TypeError, json.JSONDecodeError):
            unreadable_artifacts.append(_artifact_label(event_artifact))
            continue
        for payload in fill_payloads:
            source = payload.get("source")
            if not isinstance(source, str) or not source:
                unknown_fill_count += 1
                source = ""
            fill_source_counts[source] = fill_source_counts.get(source, 0) + 1
            if source == LOCAL_PAPER_SOURCE:
                local_paper_fills.append(payload)
    return FillSourceEvidence(
        fill_source_counts=fill_source_counts,
        local_paper_fills=tuple(local_paper_fills),
        unreadable_event_artifacts=tuple(unreadable_artifacts),
        missing_zero_fill_event_artifacts=tuple(missing_zero_fill_artifacts),
        unknown_fill_count=unknown_fill_count,
    )


def _fill_payloads(lines: list[str]) -> tuple[dict[str, Any], ...]:
    payloads: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("event_type") != "fill":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            raise TypeError("fill event payload must be a JSON object")
        payloads.append(payload)
    return tuple(payloads)


def _artifact_label(event_artifact: FillEventArtifact) -> str:
    if event_artifact.label:
        return event_artifact.label
    if event_artifact.path is None:
        return "<missing>"
    return str(event_artifact.path)
