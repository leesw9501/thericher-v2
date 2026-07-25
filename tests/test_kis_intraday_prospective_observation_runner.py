from __future__ import annotations

import hashlib
import json
import os
import socket
import urllib.request
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

import thericher_v2.data.kis_intraday_prospective_observation as prospective_input
import thericher_v2.research.kis_intraday_prospective_observation_runner as observation_runner
from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_intraday import prepare_kis_paper_intraday_feature_input
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution import LOCAL_PAPER_SOURCE
from thericher_v2.research.kis_intraday_prospective_head_observation import (
    KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES,
)
from thericher_v2.research.kis_intraday_prospective_observation_runner import (
    _run_directory,
    run_kis_intraday_prospective_observation,
)
from thericher_v2.state import EventStore

_HISTORICAL_DATES = KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES
_PROSPECTIVE_DATES = (
    date(2026, 7, 8),
    date(2026, 7, 9),
    date(2026, 7, 10),
    date(2026, 7, 13),
    date(2026, 7, 14),
)
_CANDIDATES = ("flat", "always_long", "previous_bar_direction", "regularized_linear")


def test_runner_persists_sanitized_replayable_jsonl_and_reuses_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    artifact_root = tmp_path / "model-artifacts"
    first = run_kis_intraday_prospective_observation(
        _observation_input(),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
    )

    assert first.reused is False
    assert first.frozen_model_receipt_path.is_relative_to(artifact_root)
    assert first.summary_path.is_relative_to(artifact_root)
    summary = json.loads(first.summary_path.read_text(encoding="utf-8"))
    assert summary["mode"] == "offline_local_paper"
    assert summary["selection_allowed"] is False
    assert summary["profitability_conclusion"] is False
    assert summary["broker_order_submitted"] is False
    assert summary["receipt_sha256"].startswith("sha256:")
    assert [item["candidate_id"] for item in summary["candidate_replays"]] == list(_CANDIDATES)

    run_directory = _run_directory(
        artifact_root,
        first.consumer.frozen_model_receipt.receipt_hash,
    )
    assert not list(run_directory.rglob("*.sqlite"))
    for evidence in summary["candidate_replays"]:
        event_path = run_directory / "events" / f"{evidence['candidate_id']}.jsonl"
        events = tuple(EventStore(event_path.with_suffix(".sqlite"), event_path).iter_events())
        assert evidence["event_jsonl_sha256"] == _sha256_file(event_path)
        assert evidence["event_count"] == len(events)
        assert evidence["decision_count"] == sum(
            event.event_type == "ensemble_decision" for event in events
        )
        assert evidence["fill_count"] == sum(event.event_type == "fill" for event in events)
        assert all(
            set(event.payload) == {"source", "candidate_id", "action"}
            for event in events
            if event.event_type == "ensemble_decision"
        )
        fills = [event for event in events if event.event_type == "fill"]
        assert all(
            set(event.payload)
            == {"source", "candidate_id", "market", "symbol", "side", "quantity"}
            for event in fills
        )
        assert all(event.payload["source"] == LOCAL_PAPER_SOURCE for event in fills)
        assert EventStore(event_path.with_suffix(".sqlite"), event_path).replay() is not None
        rendered = event_path.read_text(encoding="utf-8")
        assert "client_order_id" not in rendered
        assert '"price"' not in rendered
        assert '"fee"' not in rendered
        assert "source_path" not in rendered

    assert [item["session_date"] for item in summary["session_observations"]] == [
        item.isoformat() for item in _PROSPECTIVE_DATES
    ]
    for session in summary["session_observations"]:
        assert session["fill_source"] == LOCAL_PAPER_SOURCE
        assert [item["candidate_id"] for item in session["candidate_replays"]] == list(
            _CANDIDATES
        )
        for evidence in session["candidate_replays"]:
            event_path = run_directory / "events" / f"{evidence['candidate_id']}.jsonl"
            events = tuple(EventStore(event_path.with_suffix(".sqlite"), event_path).iter_events())
            session_events = [
                event
                for event in events
                if evidence["first_event_seq"] <= event.seq <= evidence["last_event_seq"]
            ]
            assert len(session_events) == evidence["event_count"]
            assert evidence["session_event_sha256"] == _sha256_payload(
                {"events": [event.to_record() for event in session_events]}
            )

    for path in (first.frozen_model_receipt_path, first.summary_path):
        rendered = path.read_text(encoding="utf-8")
        assert "client_order_id" not in rendered
        assert '"price"' not in rendered
        assert "source_path" not in rendered
        assert "after_cost_pnl" not in rendered

    original_summary = first.summary_path.read_bytes()
    replay = run_kis_intraday_prospective_observation(
        _observation_input(),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
    )
    assert replay.reused is True
    assert replay.summary_path.read_bytes() == original_summary

    first.summary_path.unlink()

    def fail_replay(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("complete candidate streams must be reused")

    monkeypatch.setattr(observation_runner, "run_local_paper_validation", fail_replay)
    recovered = run_kis_intraday_prospective_observation(
        _observation_input(),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
    )
    assert recovered.reused is False
    assert recovered.summary_path.read_bytes() == original_summary


def test_runner_rejects_tampered_completed_summary_or_event(tmp_path: Path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    first = run_kis_intraday_prospective_observation(
        _observation_input(),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
    )
    original_summary = first.summary_path.read_bytes()
    summary = json.loads(original_summary)
    summary["receipt_sha256"] = "sha256:" + "0" * 64
    first.summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ValueError, match="summary does not match"):
        run_kis_intraday_prospective_observation(
            _observation_input(),
            artifact_root=artifact_root,
            repo_root=Path.cwd(),
        )

    first.summary_path.write_bytes(original_summary)
    event_path = (
        _run_directory(artifact_root, first.consumer.frozen_model_receipt.receipt_hash)
        / "events"
        / "always_long.jsonl"
    )
    original_events = event_path.read_bytes()
    records = [json.loads(line) for line in original_events.decode("utf-8").splitlines()]
    records[0]["payload"]["price"] = "1"
    event_path.write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="event evidence"):
        run_kis_intraday_prospective_observation(
            _observation_input(),
            artifact_root=artifact_root,
            repo_root=Path.cwd(),
        )

    assert event_path.read_bytes() != original_events


def test_runner_recovery_rejects_duplicate_decision_event(tmp_path: Path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    first = run_kis_intraday_prospective_observation(
        _observation_input(),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
    )
    event_path = (
        _run_directory(artifact_root, first.consumer.frozen_model_receipt.receipt_hash)
        / "events"
        / "always_long.jsonl"
    )
    records = [json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines()]
    duplicate = dict(
        next(record for record in records if record["event_type"] == "ensemble_decision")
    )
    duplicate["seq"] = len(records) + 1
    records.append(duplicate)
    event_path.write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n",
        encoding="utf-8",
    )
    first.summary_path.unlink()

    with pytest.raises(ValueError, match="event evidence"):
        run_kis_intraday_prospective_observation(
            _observation_input(),
            artifact_root=artifact_root,
            repo_root=Path.cwd(),
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda records: records[0].update({"unexpected": "field"}),
        lambda records: records[0].update({"schema_version": 0}),
        lambda records: next(
            record for record in records if record["event_type"] == "fill"
        )["payload"].update({"quantity": "not-a-decimal"}),
        lambda records: records.append(
            {
                **next(record for record in records if record["event_type"] == "fill"),
                "seq": len(records) + 1,
            }
        ),
        lambda records: next(
            record for record in records if record["event_type"] == "fill"
        )["payload"].update({"symbol": "unexpected"}),
    ],
    ids=["extra-envelope-field", "wrong-schema", "invalid-quantity", "extra-fill", "wrong-symbol"],
)
def test_runner_recovery_rejects_noncanonical_or_unplanned_event_evidence(
    tmp_path: Path,
    mutate,
) -> None:
    artifact_root = tmp_path / "model-artifacts"
    first = run_kis_intraday_prospective_observation(
        _observation_input(),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
    )
    event_path = (
        _run_directory(artifact_root, first.consumer.frozen_model_receipt.receipt_hash)
        / "events"
        / "always_long.jsonl"
    )
    records = [json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines()]
    mutate(records)
    event_path.write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n",
        encoding="utf-8",
    )
    first.summary_path.unlink()

    with pytest.raises(ValueError, match="event evidence"):
        run_kis_intraday_prospective_observation(
            _observation_input(),
            artifact_root=artifact_root,
            repo_root=Path.cwd(),
        )


def test_runner_rebuilds_only_missing_safe_candidate_stream(tmp_path: Path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    first = run_kis_intraday_prospective_observation(
        _observation_input(),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
    )
    events_directory = (
        _run_directory(artifact_root, first.consumer.frozen_model_receipt.receipt_hash) / "events"
    )
    (events_directory / "flat.jsonl").unlink()

    recovered = run_kis_intraday_prospective_observation(
        _observation_input(),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
    )

    assert recovered.reused is False
    assert (events_directory / "flat.jsonl").is_file()
    assert json.loads(recovered.summary_path.read_text(encoding="utf-8"))["status"] == "complete"

    (events_directory / "unexpected.bin").write_bytes(b"not-a-safe-partial")
    with pytest.raises(ValueError, match="requires reconciliation"):
        run_kis_intraday_prospective_observation(
            _observation_input(),
            artifact_root=artifact_root,
            repo_root=Path.cwd(),
        )


def _observation_input() -> prospective_input.KisIntradayProspectiveObservationInput:
    historical = prepare_kis_paper_intraday_feature_input(
        _catalog(_HISTORICAL_DATES, dataset_marker="historical", hash_marker="a"),
        session_dates=_HISTORICAL_DATES,
    )
    prospective = prepare_kis_paper_intraday_feature_input(
        _catalog(_PROSPECTIVE_DATES, dataset_marker="prospective", hash_marker="b"),
        session_dates=_PROSPECTIVE_DATES,
    )
    contract_hash = "sha256:" + "c" * 64
    precommit_hash = "sha256:" + "d" * 64
    artifact_slot_id = prospective_input._artifact_slot_id(
        contract_hash=contract_hash,
        selected_session_dates=_PROSPECTIVE_DATES,
    )
    selected_rows_fingerprint_sha256 = "sha256:" + "f" * 64
    head_index_metadata_sha256 = "sha256:" + "9" * 64
    input_hash = prospective_input._input_hash(
        historical_input_hash=historical.input_hash,
        prospective_input_hash=prospective.input_hash,
        contract_hash=contract_hash,
        precommit_hash=precommit_hash,
        artifact_slot_id=artifact_slot_id,
        selected_rows_fingerprint_sha256=selected_rows_fingerprint_sha256,
        head_index_metadata_sha256=head_index_metadata_sha256,
        historical_session_dates=historical.session_dates,
        prospective_session_dates=prospective.session_dates,
    )
    return prospective_input._verified_observation_input(
        historical_catalog=historical.catalog,
        prospective_catalog=prospective.catalog,
        historical_session_dates=historical.session_dates,
        prospective_session_dates=prospective.session_dates,
        historical_input_hash=historical.input_hash,
        prospective_input_hash=prospective.input_hash,
        contract_hash=contract_hash,
        precommit_hash=precommit_hash,
        artifact_slot_id=artifact_slot_id,
        selected_rows_fingerprint_sha256=selected_rows_fingerprint_sha256,
        head_index_metadata_sha256=head_index_metadata_sha256,
        input_hash=input_hash,
    )


def _catalog(
    session_dates: tuple[date, ...],
    *,
    dataset_marker: str,
    hash_marker: str,
) -> CatalogedBars:
    bars: list[Bar] = []
    for session_index, session_date in enumerate(session_dates):
        session = us_equity_2026_session(session_date)
        assert session is not None
        for minute in range(390):
            opened = Decimal("100") + Decimal(session_index) + Decimal(minute) / Decimal("100")
            closed = opened + (Decimal("0.02") if minute % 3 else Decimal("-0.01"))
            bars.append(
                Bar(
                    symbol="QQQ",
                    market="US",
                    timeframe=Timeframe.M1,
                    start_ts=session.window.open_ts + Timeframe.M1.duration * minute,
                    open=opened,
                    high=max(opened, closed) + Decimal("0.01"),
                    low=min(opened, closed) - Decimal("0.01"),
                    close=closed,
                    volume=Decimal("1000") + Decimal(minute),
                    complete=True,
                )
            )
    return _cataloged_bars_from_verified_loader(
        dataset_id=f"kis.paper.private.intraday.qqq.nas.m1.{dataset_marker}-runner-v1",
        dataset_hash="sha256:" + hash_marker * 64,
        source_path=Path(f"D:/market_data/{dataset_marker}-runner.json"),
        bars=tuple(bars),
    )


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_payload(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("prospective observation runner must stay offline")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_external)
