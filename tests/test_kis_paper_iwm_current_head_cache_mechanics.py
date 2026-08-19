from __future__ import annotations

import hashlib
import json
import os
import socket
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import thericher_v2.data.kis_paper_intraday as private_intraday_module
import thericher_v2.data.kis_paper_iwm_current_head_cache_mechanics as mechanics_module
import thericher_v2.execution.kis_private_intraday_backfill as backfill_module
from thericher_v2.data.kis_paper_iwm_current_head_cache_mechanics import (
    KIS_PAPER_IWM_CURRENT_HEAD_CACHE_MECHANICS_ARTIFACT_DIRECTORY,
    KIS_PAPER_IWM_CURRENT_HEAD_CACHE_MECHANICS_TARGET_KEY,
    inspect_and_write_kis_paper_iwm_current_head_cache_mechanics,
    inspect_kis_paper_iwm_current_head_cache_mechanics,
    write_kis_paper_iwm_current_head_cache_mechanics_evidence,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMinutePage,
    KisPaperMinuteQuery,
    KisPaperMinuteRawBar,
)
from thericher_v2.execution.kis_private_intraday_backfill import (
    KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION,
    run_kis_paper_iwm_current_head_cycle,
)


class _MinuteClient:
    def __init__(self, page: KisPaperMinutePage) -> None:
        self._page = page
        self.queries: list[KisPaperMinuteQuery] = []

    def fetch_minute_page(
        self,
        query: KisPaperMinuteQuery,
        *,
        before_request: object = None,
    ) -> KisPaperMinutePage:
        self.queries.append(query)
        return self._page


def test_reattaches_iwm_cache_as_aggregate_external_mechanics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root, market_data_root, cache_root = _seed_iwm_cache(monkeypatch, tmp_path)
    artifact_root = tmp_path / "artifacts"

    receipt = inspect_and_write_kis_paper_iwm_current_head_cache_mechanics(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repo_root=repo_root,
        market_data_root=market_data_root,
    )

    mechanics = receipt.mechanics
    assert mechanics.indexed_retained_chunk_count == 1
    assert mechanics.bar_count == 3
    assert mechanics.complete_bar_count + mechanics.incomplete_bar_count == mechanics.bar_count
    assert mechanics.adjacent_m1_pair_count + mechanics.non_adjacent_pair_count == 2
    assert mechanics.maximum_interbar_seconds >= 60
    assert receipt.evidence_path.parent == (
        artifact_root / KIS_PAPER_IWM_CURRENT_HEAD_CACHE_MECHANICS_ARTIFACT_DIRECTORY
    )
    payload = receipt.mechanics.safe_payload()
    assert json.loads(receipt.evidence_path.read_text(encoding="utf-8")) == payload
    assert receipt.evidence_sha256 == "sha256:" + hashlib.sha256(
        receipt.evidence_path.read_bytes()
    ).hexdigest()
    assert payload["target_key"] == KIS_PAPER_IWM_CURRENT_HEAD_CACHE_MECHANICS_TARGET_KEY
    assert payload["integrity_status"] == "index_manifest_raw_verified"
    assert payload["session_finality"] == "not_observed"
    assert payload["decision_time_availability"] == "not_observed"
    assert payload["model_input_eligibility"] is False
    assert payload["network_access"] is False
    assert payload["credentials_read"] is False
    assert payload["paper_execution"] is False
    serialized = json.dumps(payload, sort_keys=True)
    for forbidden in (
        "12345.67",
        "20260819",
        "ohlcv_1m.csv.gz",
        "access_token",
        str(cache_root),
    ):
        assert forbidden not in serialized


def test_tampered_compressed_raw_file_fails_before_mechanics_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root, market_data_root, cache_root = _seed_iwm_cache(monkeypatch, tmp_path)
    raw_path = next(
        (cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION).glob(
            "snapshots/*/raw/ohlcv_1m.csv.gz"
        )
    )
    raw_path.write_bytes(raw_path.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="raw hash mismatch"):
        inspect_kis_paper_iwm_current_head_cache_mechanics(
            cache_root=cache_root,
            repo_root=repo_root,
            market_data_root=market_data_root,
        )


def test_rejects_non_iwm_index_scope_before_opening_raw_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root, market_data_root, cache_root = _seed_iwm_cache(monkeypatch, tmp_path)
    index_path = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["targets"][0]["symbol"] = "QQQ"
    index["targets"][0]["exchange"] = "NAS"
    index["targets"][0]["target_key"] = "QQQ/NAS/1m"
    index["targets"][0]["chunks"] = []
    index_path.write_text(json.dumps(index, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="cache index is invalid"):
        inspect_kis_paper_iwm_current_head_cache_mechanics(
            cache_root=cache_root,
            repo_root=repo_root,
            market_data_root=market_data_root,
        )


def test_rejects_git_resident_cache_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(ValueError, match="cache root"):
        inspect_kis_paper_iwm_current_head_cache_mechanics(
            cache_root=repo_root / "cache",
            repo_root=repo_root,
            market_data_root=tmp_path / "market-data",
        )


def test_rejects_rebased_legacy_replay_cache_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    market_data_root = tmp_path / "market-data"
    replay_cache_root = (
        market_data_root / "us_equities" / "kis_paper_private" / "iwm_m1_current_head"
    )

    with pytest.raises(ValueError, match="cache root is invalid"):
        inspect_kis_paper_iwm_current_head_cache_mechanics(
            cache_root=replay_cache_root,
            repo_root=repo_root,
            market_data_root=market_data_root,
        )


def test_index_replacement_fails_before_raw_rows_are_decoded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root, market_data_root, cache_root = _seed_iwm_cache(monkeypatch, tmp_path)
    index_path = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION / "index.json"
    original_loader = mechanics_module.load_verified_kis_paper_private_intraday_catalog

    def replace_index_then_load(**kwargs: object):
        index_path.write_bytes(b"\n" + index_path.read_bytes())
        return original_loader(**kwargs)

    def fail_raw_decode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("raw rows must not be decoded after index replacement")

    monkeypatch.setattr(
        mechanics_module,
        "load_verified_kis_paper_private_intraday_catalog",
        replace_index_then_load,
    )
    monkeypatch.setattr(private_intraday_module, "_decode_raw_rows", fail_raw_decode)

    with pytest.raises(ValueError, match="index identity mismatch"):
        inspect_kis_paper_iwm_current_head_cache_mechanics(
            cache_root=cache_root,
            repo_root=repo_root,
            market_data_root=market_data_root,
        )


def test_rejects_artifact_intermediate_symlink_before_writing_outside_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root, market_data_root, cache_root = _seed_iwm_cache(monkeypatch, tmp_path)
    mechanics = inspect_kis_paper_iwm_current_head_cache_mechanics(
        cache_root=cache_root,
        repo_root=repo_root,
        market_data_root=market_data_root,
    )
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    outside_root = tmp_path / "outside"
    outside_root.mkdir()
    linked_data_root = artifact_root / "data"
    try:
        linked_data_root.symlink_to(outside_root, target_is_directory=True)
    except OSError:
        pytest.skip("directory links are unavailable on this host")

    with pytest.raises(ValueError, match="artifact destination is invalid"):
        write_kis_paper_iwm_current_head_cache_mechanics_evidence(
            mechanics=mechanics,
            artifact_root=artifact_root,
            repo_root=repo_root,
        )

    assert not (outside_root / "kis-paper-iwm-m1-current-head-cache-mechanics").exists()


def test_reattachment_is_offline_and_credential_free(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root, market_data_root, cache_root = _seed_iwm_cache(monkeypatch, tmp_path)

    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("IWM cache mechanics must stay offline")

    def fail_environment(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("IWM cache mechanics must not read credentials")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_environment)

    result = inspect_kis_paper_iwm_current_head_cache_mechanics(
        cache_root=cache_root,
        repo_root=repo_root,
        market_data_root=market_data_root,
    )

    assert result.bar_count == 3


def _seed_iwm_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[Path, Path, Path]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    market_data_root = tmp_path / "market-data"
    cache_root = market_data_root / "us_equities" / "kis_paper_private" / "iwm_current_head"
    monkeypatch.setattr(backfill_module, "KIS_PAPER_MARKET_DATA_ROOT", market_data_root)
    run = run_kis_paper_iwm_current_head_cycle(
        client=_MinuteClient(_page()),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        observed_at=datetime(2026, 8, 19, 14, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    assert run.status == "collected"
    return repo_root, market_data_root, cache_root


def _page() -> KisPaperMinutePage:
    start = datetime(2026, 8, 19, 22, 30)
    return KisPaperMinutePage(
        query=KisPaperMinuteQuery(exchange="AMS", symbol="IWM"),
        bars=tuple(_bar(start + timedelta(minutes=index)) for index in range(3)),
        next_cursor=None,
        more="",
    )


def _bar(timestamp: datetime) -> KisPaperMinuteRawBar:
    return KisPaperMinuteRawBar(
        exchange_date=timestamp.strftime("%Y%m%d"),
        exchange_time=timestamp.strftime("%H%M%S"),
        korea_date=timestamp.strftime("%Y%m%d"),
        korea_time=timestamp.strftime("%H%M%S"),
        open=Decimal("12345.67"),
        high=Decimal("12345.68"),
        low=Decimal("12345.66"),
        last=Decimal("12345.67"),
        volume=Decimal("123"),
    )
