from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import thericher_v2.data.kis_paper_iwm_m1_current_head_replay as replay_module
from thericher_v2.contracts import Timeframe
from thericher_v2.data.kis_paper_iwm_m1_current_head import (
    KisPaperIwmM1CurrentHeadOutcome,
    write_kis_paper_iwm_m1_current_head_evidence,
)
from thericher_v2.data.kis_paper_iwm_m1_current_head_replay import (
    list_verified_kis_paper_iwm_m1_current_head_observations,
    load_selected_verified_kis_paper_iwm_m1_current_head_replay,
    load_verified_kis_paper_iwm_m1_current_head_replay,
    resample_verified_kis_paper_iwm_m1_current_head_replay,
    write_kis_paper_iwm_m1_current_head_replay_evidence,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMinuteRawBar,
)


def test_single_snapshot_replays_deterministically_into_every_timeframe(
    tmp_path: Path,
) -> None:
    roots = _seed_snapshot(tmp_path, bar_count=190, observed_at=_observed_at())
    primary_state = roots["market_data"] / "primary-qqq-spy" / "state.json"
    primary_state.parent.mkdir()
    primary_state.write_text('{"primary":"unchanged"}\n', encoding="utf-8")

    first = _load(roots)
    second = _load(roots)
    resampled = resample_verified_kis_paper_iwm_m1_current_head_replay(first)

    assert first == second
    assert all(bar.complete for bar in first.bars)
    assert {timeframe: len(bars) for timeframe, bars in resampled.items()} == {
        Timeframe.M1: 190,
        Timeframe.M5: 38,
        Timeframe.M10: 19,
        Timeframe.H1: 3,
        Timeframe.H3: 1,
    }
    assert primary_state.read_text(encoding="utf-8") == '{"primary":"unchanged"}\n'

    evidence = write_kis_paper_iwm_m1_current_head_replay_evidence(
        replay=first,
        resampled=resampled,
        artifact_root=roots["artifact_root"],
        repository_root=roots["repository_root"],
    )
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    serialized = json.dumps(payload, sort_keys=True)
    assert payload["completed_bucket_counts"] == {
        "1m": 190,
        "5m": 38,
        "10m": 19,
        "1h": 3,
        "3h": 1,
    }
    assert payload["broker_or_network_used"] is False
    assert payload["provider_finality"] == "not_observed"
    assert payload["model_input_eligibility"] is False
    assert str(roots["cache_root"]) not in serialized
    assert "123.45" not in serialized


def test_replay_rejects_tampered_raw_before_emitting_bars(tmp_path: Path) -> None:
    roots = _seed_snapshot(tmp_path, bar_count=10, observed_at=_observed_at())
    raw_path = _snapshot_path(roots) / "rows.csv.gz"
    raw_path.write_bytes(raw_path.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="raw hash mismatch"):
        _load(roots)


def test_replay_rejects_cross_target_manifest_before_emitting_bars(tmp_path: Path) -> None:
    roots = _seed_snapshot(tmp_path, bar_count=10, observed_at=_observed_at())
    manifest_path = _snapshot_path(roots) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["target_key"] = "QQQ/NAS/1m"
    manifest_path.write_bytes(_canonical_json_bytes(manifest) + b"\n")

    with pytest.raises(ValueError, match="snapshot is invalid"):
        _load(roots)


def test_replay_rejects_multiple_receipts_as_an_ambiguous_association(tmp_path: Path) -> None:
    roots = _seed_snapshot(tmp_path, bar_count=10, observed_at=_observed_at())
    receipt_root = roots["artifact_root"] / "data" / "kis-paper-iwm-m1-current-head"
    original = next(receipt_root.glob("*.json"))
    (receipt_root / "second.json").write_bytes(original.read_bytes())

    with pytest.raises(ValueError, match="observation receipts are duplicated"):
        _observations(roots)


def test_replay_rejects_a_receipt_bound_to_a_missing_snapshot(tmp_path: Path) -> None:
    roots = _seed_snapshot(tmp_path, bar_count=10, observed_at=_observed_at())
    receipt_path = next(
        (roots["artifact_root"] / "data" / "kis-paper-iwm-m1-current-head").glob("*.json")
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["snapshot_content_sha256"] = "f" * 64
    receipt_path.write_bytes(_canonical_json_bytes(receipt) + b"\n")

    with pytest.raises(ValueError, match="snapshot is invalid"):
        _load(roots)


def test_replay_rejects_a_receipt_that_is_not_source_safe(tmp_path: Path) -> None:
    roots = _seed_snapshot(tmp_path, bar_count=10, observed_at=_observed_at())
    receipt_path = next(
        (roots["artifact_root"] / "data" / "kis-paper-iwm-m1-current-head").glob("*.json")
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["raw_price"] = "123.45"
    receipt_path.write_bytes(_canonical_json_bytes(receipt) + b"\n")

    with pytest.raises(ValueError, match="collection receipt is invalid"):
        _load(roots)


def test_replay_drops_an_incomplete_target_bucket(tmp_path: Path) -> None:
    start = datetime(2026, 7, 24, 0, 0, tzinfo=UTC)
    roots = _seed_snapshot(
        tmp_path,
        bar_count=5,
        observed_at=start + timedelta(minutes=4),
        start=start,
    )

    replay = _load(roots)
    resampled = resample_verified_kis_paper_iwm_m1_current_head_replay(replay)

    assert len(resampled[Timeframe.M1]) == 4
    assert resampled[Timeframe.M5] == ()
    assert resampled[Timeframe.M10] == ()
    assert resampled[Timeframe.H1] == ()
    assert resampled[Timeframe.H3] == ()


def test_legacy_unbound_snapshot_stays_incomplete(tmp_path: Path) -> None:
    roots = _seed_snapshot(
        tmp_path,
        bar_count=10,
        observed_at=_observed_at(),
        bound_receipt=False,
    )

    replay = _load(roots)
    resampled = resample_verified_kis_paper_iwm_m1_current_head_replay(replay)

    assert replay.completion_basis == "completion_evidence_unavailable"
    assert replay.observed_at is None
    assert not any(bar.complete for bar in replay.bars)
    assert all(not bars for bars in resampled.values())
    assert replay.safe_payload(resampled=resampled)["status"] == "completion_evidence_unavailable"


def test_bound_receipt_selects_its_snapshot_alongside_legacy_evidence(tmp_path: Path) -> None:
    roots = _seed_snapshot(tmp_path, bar_count=10, observed_at=_observed_at())
    receipt_root = roots["artifact_root"] / "data" / "kis-paper-iwm-m1-current-head"
    bound_path = next(receipt_root.glob("*.json"))
    legacy_receipt = json.loads(bound_path.read_text(encoding="utf-8"))
    legacy_receipt.pop("receipt_version")
    legacy_receipt.pop("snapshot_content_sha256")
    (receipt_root / "legacy.json").write_bytes(_canonical_json_bytes(legacy_receipt) + b"\n")
    extra_snapshot = roots["cache_root"] / "v1" / "snapshots" / ("e" * 64)
    extra_snapshot.mkdir()

    replay = _load(roots)

    assert replay.completion_basis == "receipt_snapshot_content_binding"
    assert len(resample_verified_kis_paper_iwm_m1_current_head_replay(replay)[Timeframe.M1]) == 10


def test_selector_requires_an_explicit_id_for_multiple_bound_observations(tmp_path: Path) -> None:
    roots = _seed_snapshot(tmp_path, bar_count=10, observed_at=_observed_at())
    _write_bound_receipt(roots, observed_at=_observed_at() + timedelta(minutes=1))

    observations = _observations(roots)

    assert len(observations) == 2
    assert observations[0].observation_id != observations[1].observation_id
    with pytest.raises(ValueError, match="explicit observation ID"):
        _load(roots)
    selected = load_selected_verified_kis_paper_iwm_m1_current_head_replay(
        observation_id=observations[1].observation_id,
        cache_root=roots["cache_root"],
        artifact_root=roots["artifact_root"],
        repository_root=roots["repository_root"],
        market_data_root=roots["market_data"],
    )

    assert selected.observation_id == observations[1].observation_id
    assert selected.receipt_sha256 == observations[1].receipt_sha256
    assert selected.snapshot_content_sha256 == observations[1].snapshot_content_sha256
    assert all(bar.complete for bar in selected.bars)


def test_selector_keeps_distinct_time_ordered_observations_with_reverse_ids(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    roots = _seed_snapshot(tmp_path, bar_count=10, observed_at=_observed_at())
    _write_bound_receipt(roots, observed_at=_observed_at() + timedelta(minutes=1))
    assigned_ids: dict[str, str] = {}
    available_ids = iter(("f" * 64, "0" * 64))

    def observation_id(*, receipt_sha256: str, snapshot_content_sha256: str | None) -> str:
        del snapshot_content_sha256
        if receipt_sha256 not in assigned_ids:
            assigned_ids[receipt_sha256] = next(available_ids)
        return "iwm-observation:" + assigned_ids[receipt_sha256]

    monkeypatch.setattr(replay_module, "_observation_id", observation_id)

    observations = _observations(roots)

    assert [observation.observation_id[-1] for observation in observations] == ["f", "0"]
    selected = load_selected_verified_kis_paper_iwm_m1_current_head_replay(
        observation_id=observations[1].observation_id,
        cache_root=roots["cache_root"],
        artifact_root=roots["artifact_root"],
        repository_root=roots["repository_root"],
        market_data_root=roots["market_data"],
    )
    assert selected.observation_id == observations[1].observation_id


def test_selector_lists_legacy_as_incomplete_without_exposing_raw_values(tmp_path: Path) -> None:
    roots = _seed_snapshot(
        tmp_path,
        bar_count=10,
        observed_at=_observed_at(),
        bound_receipt=False,
    )

    observations = _observations(roots)
    payload = observations[0].safe_payload()
    selected = load_selected_verified_kis_paper_iwm_m1_current_head_replay(
        observation_id=observations[0].observation_id,
        cache_root=roots["cache_root"],
        artifact_root=roots["artifact_root"],
        repository_root=roots["repository_root"],
        market_data_root=roots["market_data"],
    )

    assert len(observations) == 1
    assert payload["completion_basis"] == "completion_evidence_unavailable"
    assert payload["snapshot_content_sha256"] is None
    assert "123.45" not in json.dumps(payload, sort_keys=True)
    assert not any(bar.complete for bar in selected.bars)


def test_selector_ignores_an_owned_stale_receipt_staging_file(tmp_path: Path) -> None:
    roots = _seed_snapshot(tmp_path, bar_count=10, observed_at=_observed_at())
    receipt_root = roots["artifact_root"] / "data" / "kis-paper-iwm-m1-current-head"
    receipt = next(receipt_root.glob("*.json"))
    (receipt_root / ".aaaaaaaaaaaaaaaa.bbbbbbbb.stage").write_bytes(receipt.read_bytes())

    observations = _observations(roots)

    assert len(observations) == 1
    assert observations[0].completion_basis == "receipt_snapshot_content_binding"


def test_selector_ignores_a_legacy_source_safe_failure_receipt(tmp_path: Path) -> None:
    roots = _seed_snapshot(tmp_path, bar_count=10, observed_at=_observed_at())
    receipt_root = roots["artifact_root"] / "data" / "kis-paper-iwm-m1-current-head"
    failure = KisPaperIwmM1CurrentHeadOutcome(
        status="unavailable",
        observed_at=_observed_at() + timedelta(minutes=1),
        row_count=0,
        exact_duplicate_rows=0,
        continuation_category="not_observed",
        cache_disposition="not_written",
        response_class="rate_limited",
        raw_market_data_retained=False,
    )
    (receipt_root / "legacy-failure.json").write_bytes(
        _canonical_json_bytes(failure.safe_payload()) + b"\n"
    )

    observations = _observations(roots)

    assert len(observations) == 1
    assert observations[0].completion_basis == "receipt_snapshot_content_binding"


def test_replay_evidence_rejects_a_linked_intermediate_directory(tmp_path: Path) -> None:
    roots = _seed_snapshot(tmp_path, bar_count=10, observed_at=_observed_at())
    replay = _load(roots)
    output_root = tmp_path / "output-artifacts"
    outside = tmp_path / "outside"
    output_root.mkdir()
    outside.mkdir()
    try:
        (output_root / "data").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory links are unavailable on this host")

    with pytest.raises(ValueError, match="replay evidence directory is invalid"):
        write_kis_paper_iwm_m1_current_head_replay_evidence(
            replay=replay,
            resampled=resample_verified_kis_paper_iwm_m1_current_head_replay(replay),
            artifact_root=output_root,
            repository_root=roots["repository_root"],
        )

    assert not any(outside.iterdir())


def _seed_snapshot(
    tmp_path: Path,
    *,
    bar_count: int,
    observed_at: datetime,
    start: datetime | None = None,
    bound_receipt: bool = True,
) -> dict[str, Path]:
    repository_root = tmp_path / "repo"
    market_data = tmp_path / "market-data"
    cache_root = market_data / "iwm-current-head"
    artifact_root = tmp_path / "artifacts"
    repository_root.mkdir()
    first_start = start or datetime(2026, 7, 24, 0, 0, tzinfo=UTC)
    raw_bars = tuple(_raw_bar(first_start + timedelta(minutes=index)) for index in range(bar_count))
    raw_bytes = _compressed_raw_csv(raw_bars)
    content_digest = hashlib.sha256(
        _canonical_json_bytes([raw_bar.as_document() for raw_bar in raw_bars])
    ).hexdigest()
    snapshot = cache_root / "v1" / "snapshots" / content_digest
    snapshot.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "kind": "kis_paper_iwm_m1_current_head_snapshot",
        "collection_version": "v1",
        "target_key": "IWM/AMS/1m",
        "collection_scope": "one_current_day_head_page_no_continuation",
        "content_sha256": content_digest,
        "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "raw_filename": "rows.csv.gz",
        "row_count": len(raw_bars),
        "exact_duplicate_rows": 0,
        "continuation_observed": False,
    }
    (snapshot / "rows.csv.gz").write_bytes(raw_bytes)
    (snapshot / "manifest.json").write_bytes(_canonical_json_bytes(manifest) + b"\n")
    outcome = KisPaperIwmM1CurrentHeadOutcome(
        status="collected",
        observed_at=observed_at,
        row_count=len(raw_bars),
        exact_duplicate_rows=0,
        continuation_category="not_observed",
        cache_disposition="retained",
        response_class="accepted",
        raw_market_data_retained=True,
        snapshot_content_sha256=content_digest,
    )
    if bound_receipt:
        write_kis_paper_iwm_m1_current_head_evidence(
            outcome=outcome,
            artifact_root=artifact_root,
            repository_root=repository_root,
        )
    else:
        legacy_receipt = outcome.safe_payload()
        legacy_receipt.pop("receipt_version")
        legacy_receipt.pop("snapshot_content_sha256")
        legacy_path = artifact_root / "data" / "kis-paper-iwm-m1-current-head" / "legacy.json"
        legacy_path.parent.mkdir(parents=True)
        legacy_path.write_bytes(_canonical_json_bytes(legacy_receipt) + b"\n")
    return {
        "repository_root": repository_root,
        "market_data": market_data,
        "cache_root": cache_root,
        "artifact_root": artifact_root,
    }


def _load(roots: dict[str, Path]):
    return load_verified_kis_paper_iwm_m1_current_head_replay(
        cache_root=roots["cache_root"],
        artifact_root=roots["artifact_root"],
        repository_root=roots["repository_root"],
        market_data_root=roots["market_data"],
    )


def _observations(roots: dict[str, Path]):
    return list_verified_kis_paper_iwm_m1_current_head_observations(
        artifact_root=roots["artifact_root"],
        repository_root=roots["repository_root"],
    )


def _write_bound_receipt(roots: dict[str, Path], *, observed_at: datetime) -> None:
    snapshot_content_sha256 = _snapshot_path(roots).name
    write_kis_paper_iwm_m1_current_head_evidence(
        outcome=KisPaperIwmM1CurrentHeadOutcome(
            status="collected",
            observed_at=observed_at,
            row_count=10,
            exact_duplicate_rows=0,
            continuation_category="not_observed",
            cache_disposition="already_retained",
            response_class="accepted",
            raw_market_data_retained=True,
            snapshot_content_sha256=snapshot_content_sha256,
        ),
        artifact_root=roots["artifact_root"],
        repository_root=roots["repository_root"],
    )


def _snapshot_path(roots: dict[str, Path]) -> Path:
    snapshots = roots["cache_root"] / "v1" / "snapshots"
    return next(snapshots.iterdir())


def _raw_bar(timestamp: datetime) -> KisPaperMinuteRawBar:
    korea_timestamp = timestamp.astimezone(_KOREA)
    return KisPaperMinuteRawBar(
        exchange_date=timestamp.strftime("%Y%m%d"),
        exchange_time=timestamp.strftime("%H%M%S"),
        korea_date=korea_timestamp.strftime("%Y%m%d"),
        korea_time=korea_timestamp.strftime("%H%M%S"),
        open=Decimal("123.45"),
        high=Decimal("123.50"),
        low=Decimal("123.40"),
        last=Decimal("123.46"),
        volume=Decimal("100"),
    )


def _observed_at() -> datetime:
    return datetime(2026, 7, 24, 3, 30, tzinfo=UTC)


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _compressed_raw_csv(raw_bars: tuple[KisPaperMinuteRawBar, ...]) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as gzip_handle:
        with io.TextIOWrapper(gzip_handle, encoding="utf-8", newline="") as text_handle:
            writer = csv.DictWriter(
                text_handle,
                fieldnames=(
                    "xymd",
                    "xhms",
                    "kymd",
                    "khms",
                    "open",
                    "high",
                    "low",
                    "last",
                    "evol",
                ),
                lineterminator="\n",
            )
            writer.writeheader()
            for raw_bar in raw_bars:
                writer.writerow(raw_bar.as_document())
    return buffer.getvalue()


_KOREA = ZoneInfo("Asia/Seoul")
