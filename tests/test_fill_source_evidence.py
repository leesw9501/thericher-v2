from __future__ import annotations

import json
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.execution import (
    LOCAL_PAPER_SOURCE,
    FillEventArtifact,
    collect_fill_source_evidence,
)


def test_fill_source_evidence_accepts_local_paper_only(tmp_path) -> None:
    events = tmp_path / "events.jsonl"
    _write_events(
        events,
        (
            _fill_event(source=LOCAL_PAPER_SOURCE, client_order_id="a"),
            _fill_event(source=LOCAL_PAPER_SOURCE, client_order_id="b"),
            {"event_type": "order_accepted", "payload": {"source": "ignored"}},
        ),
    )

    evidence = collect_fill_source_evidence(
        (FillEventArtifact(path=events, expected_fill_count=2),)
    )

    assert evidence.all_fills_local_paper is True
    assert evidence.to_summary()["all_fills_local_paper"] is True
    assert evidence.to_summary()["local_paper_fill_count"] == 2
    assert evidence.local_paper_fills[0]["client_order_id"] == "a"
    assert evidence.non_local_fill_source_counts == {}


def test_fill_source_evidence_detects_mixed_and_unknown_sources(tmp_path) -> None:
    events = tmp_path / "events.jsonl"
    _write_events(
        events,
        (
            _fill_event(source=LOCAL_PAPER_SOURCE, client_order_id="a"),
            _fill_event(source="broker_paper", client_order_id="b"),
            {"event_type": "fill", "payload": {"client_order_id": "c"}},
        ),
    )

    evidence = collect_fill_source_evidence(
        (FillEventArtifact(path=events, expected_fill_count=3),)
    )
    summary = evidence.to_summary()

    assert evidence.all_fills_local_paper is False
    assert summary["non_local_fill_source_counts"] == {"broker_paper": 1, "": 1}
    assert summary["unknown_fill_count"] == 1


def test_fill_source_evidence_tolerates_missing_zero_fill_artifact(tmp_path) -> None:
    missing = tmp_path / "missing-events.jsonl"

    evidence = collect_fill_source_evidence(
        (FillEventArtifact(path=missing, expected_fill_count=0),)
    )
    summary = evidence.to_summary()

    assert summary["all_fills_local_paper"] is True
    assert summary["local_paper_fill_count"] == 0
    assert summary["unreadable_event_artifacts"] == []
    assert summary["missing_zero_fill_event_artifacts"] == [str(missing)]


def test_fill_source_evidence_flags_unreadable_nonzero_artifact(tmp_path) -> None:
    unreadable = tmp_path / "events-as-directory.jsonl"
    unreadable.mkdir()

    evidence = collect_fill_source_evidence(
        (
            FillEventArtifact(
                path=unreadable,
                expected_fill_count=1,
                label="slice_a:variant_1",
            ),
        )
    )
    summary = evidence.to_summary()

    assert summary["all_fills_local_paper"] is False
    assert summary["unreadable_event_artifacts"] == ["slice_a:variant_1"]


def test_fill_source_evidence_rejects_negative_expected_count() -> None:
    with pytest.raises(ValueError, match="expected_fill_count"):
        FillEventArtifact(path=None, expected_fill_count=-1)


def test_fill_source_evidence_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("fill source evidence must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("fill source evidence must not read credential files")
        return original_read_text(path, *args, **kwargs)

    events = tmp_path / "events.jsonl"
    _write_events(events, (_fill_event(source=LOCAL_PAPER_SOURCE, client_order_id="a"),))
    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    evidence = collect_fill_source_evidence(
        (FillEventArtifact(path=events, expected_fill_count=1),)
    )

    assert evidence.all_fills_local_paper is True


def _fill_event(*, source: str, client_order_id: str) -> dict[str, object]:
    return {
        "event_type": "fill",
        "created_at": datetime(2026, 1, 2, tzinfo=UTC).isoformat(),
        "payload": {
            "source": source,
            "client_order_id": client_order_id,
            "symbol": "AAA",
            "market": "US",
        },
    }


def _write_events(path: Path, events: tuple[dict[str, object], ...]) -> None:
    path.write_text(
        "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n",
        encoding="utf-8",
    )
