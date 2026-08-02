from __future__ import annotations

import json
import socket
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import norgate_broad_active_build_conformance as conformance
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.data.norgate_daily import NorgateClientUnavailableError
from thericher_v2.data.norgate_trial_development_panel import (
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_HASH,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_ID,
    NorgateTrialDevelopmentPanelCatalog,
    NorgateTrialDevelopmentPanelScope,
    NorgateTrialDevelopmentPanelSourceIdentity,
)
from thericher_v2.data.provider import BarQuery

_SYMBOLS = ("SPY", "QQQ", "IWM")
_SESSIONS = (date(2031, 2, 3), date(2031, 2, 5))
_RAW_DATE = "2031-02-03"
_RAW_PRICE = "913.777"
_RAW_PATH = r"D:\private-source\norgate"
_CREDENTIAL = "unit-secret-must-not-persist"


class _CatalogLoader:
    def __init__(self, catalog: NorgateTrialDevelopmentPanelCatalog) -> None:
        self.catalog = catalog
        self.calls: list[tuple[Path, dict[str, object]]] = []

    def __call__(self, snapshot: Path, **kwargs: object) -> NorgateTrialDevelopmentPanelCatalog:
        self.calls.append((snapshot, kwargs))
        return self.catalog


class _Provider:
    def __init__(self, bars_by_symbol: Mapping[str, tuple[Bar, ...]]) -> None:
        self.bars_by_symbol = bars_by_symbol
        self.calls: list[BarQuery] = []
        self.credential = _CREDENTIAL

    def get_bars(self, query: BarQuery) -> list[Bar]:
        self.calls.append(query)
        return list(self.bars_by_symbol[query.symbol])


class _DoubleReadProvider:
    def __init__(
        self,
        responses_by_symbol: Mapping[str, tuple[tuple[Bar, ...], tuple[Bar, ...]]],
    ) -> None:
        self.responses_by_symbol = responses_by_symbol
        self.calls: list[BarQuery] = []
        self._calls_by_symbol: dict[str, int] = {}

    def get_bars(self, query: BarQuery) -> list[Bar]:
        self.calls.append(query)
        index = self._calls_by_symbol.get(query.symbol, 0)
        self._calls_by_symbol[query.symbol] = index + 1
        return list(self.responses_by_symbol[query.symbol][index])


class _FailingProvider:
    def get_bars(self, _query: BarQuery) -> list[Bar]:
        raise NorgateClientUnavailableError(_CREDENTIAL)


class _MidRunFailingProvider:
    def __init__(self, bars_by_symbol: Mapping[str, tuple[Bar, ...]]) -> None:
        self.bars_by_symbol = bars_by_symbol
        self.calls: list[BarQuery] = []

    def get_bars(self, query: BarQuery) -> list[Bar]:
        self.calls.append(query)
        if query.symbol == "QQQ":
            raise NorgateClientUnavailableError(_CREDENTIAL)
        return list(self.bars_by_symbol[query.symbol])


def test_exact_match_writes_safe_receipt_and_reattaches_provider_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_root, repo_root = _roots(tmp_path)
    catalog = _catalog()
    loader = _CatalogLoader(catalog)
    provider = _Provider(_bars_by_symbol())

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("conformance probe must not use the network")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    result = conformance.build_norgate_broad_active_build_conformance_receipt(
        destination=artifact_root / "exact",
        artifact_root=artifact_root,
        repo_root=repo_root,
        active_provider=provider,
        catalog_loader=loader,
    )

    assert result.status == "matching"
    assert result.reason == "active_build_matches_broad_frozen_contract"
    assert result.selected_symbol_count == 3
    assert result.common_session_count == 2
    assert result.reference_bar_count == 6
    assert result.observed_active_bar_count == 6
    assert result.active_response_hash is not None
    assert [item.symbol for item in result.evidence] == list(_SYMBOLS)
    assert len(provider.calls) == 6
    assert all(query.timeframe is Timeframe.D1 for query in provider.calls)
    assert loader.calls == [
        (
            conformance.FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_SNAPSHOT_DIR,
            {
                "expected_dataset_id": FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_ID,
                "expected_dataset_hash": FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_HASH,
                "market_data_root": conformance.DEFAULT_MARKET_DATA_ROOT,
                "repo_root": repo_root,
            },
        )
    ]

    receipt_text = (result.receipt_dir / "receipt.json").read_text(encoding="utf-8")
    safe_text = json.dumps(result.safe_payload(), sort_keys=True)
    for forbidden in (_RAW_DATE, _RAW_PRICE, _RAW_PATH, _CREDENTIAL):
        assert forbidden not in receipt_text
        assert forbidden not in safe_text
    receipt = json.loads(receipt_text)
    assert receipt["active_reader"] == {
        "two_reads_per_symbol": True,
        "serial_single_provider": True,
        "active_response_sha256": result.active_response_hash,
    }
    assert receipt["target_free_integrity"]["raw_ohlcv_persisted"] is False

    calls_before_reattach = len(provider.calls)
    reattached = conformance.verify_norgate_broad_active_build_conformance_receipt(
        result.receipt_dir,
        artifact_root=artifact_root,
        repo_root=repo_root,
        expected_receipt_sha256=result.receipt_sha256,
    )
    assert reattached == result
    assert len(provider.calls) == calls_before_reattach

    idempotent = conformance.build_norgate_broad_active_build_conformance_receipt(
        destination=result.receipt_dir,
        artifact_root=artifact_root,
        repo_root=repo_root,
        active_provider=provider,
        catalog_loader=loader,
    )
    assert idempotent == result
    assert len(provider.calls) == calls_before_reattach


def test_value_mismatch_is_revision_detected_without_session_coverage_claim(tmp_path: Path) -> None:
    artifact_root, repo_root = _roots(tmp_path)
    active = _bars_by_symbol()
    active["QQQ"] = (
        active["QQQ"][0],
        replace(active["QQQ"][1], close=active["QQQ"][1].close + Decimal("0.125")),
    )

    result = _build(artifact_root, repo_root, _Provider(active))

    assert result.status == "revision_detected"
    assert result.reason == "shared_session_value_mismatch_detected"
    assert result.safe_payload()["value_mismatch_symbol_count"] == 1
    assert result.safe_payload()["symbol_absent_count"] == 0
    assert result.safe_payload()["session_coverage_mismatch_count"] == 0
    assert result.active_response_hash is not None


def test_absent_symbol_is_input_unavailable_not_a_value_revision(tmp_path: Path) -> None:
    artifact_root, repo_root = _roots(tmp_path)
    active = _bars_by_symbol()
    active["IWM"] = ()

    result = _build(artifact_root, repo_root, _Provider(active))

    assert result.status == "input_unavailable"
    assert result.reason == "active_symbol_or_session_coverage_unavailable"
    assert result.safe_payload()["symbol_absent_count"] == 1
    assert result.safe_payload()["value_mismatch_symbol_count"] == 0
    assert result.active_response_hash is not None


def test_missing_and_surplus_sessions_are_input_unavailable_not_a_value_revision(
    tmp_path: Path,
) -> None:
    artifact_root, repo_root = _roots(tmp_path)
    active = _bars_by_symbol()
    active["SPY"] = (
        active["SPY"][0],
        _bar("SPY", 1, date(2031, 2, 4)),
    )

    result = _build(artifact_root, repo_root, _Provider(active))

    evidence = next(item for item in result.evidence if item.symbol == "SPY")
    assert result.status == "input_unavailable"
    assert result.reason == "active_symbol_or_session_coverage_unavailable"
    assert evidence.series_category == "session_coverage_mismatch"
    assert evidence.missing_session_count == 1
    assert evidence.surplus_session_count == 1
    assert evidence.value_mismatch_count == 0


def test_nonrepeatable_reader_is_categorized_per_symbol_and_remaining_symbols_continue(
    tmp_path: Path,
) -> None:
    artifact_root, repo_root = _roots(tmp_path)
    active = _bars_by_symbol()
    changed = (
        active["QQQ"][0],
        replace(active["QQQ"][1], close=Decimal("914.5")),
    )
    provider = _DoubleReadProvider(
        {
            "SPY": (active["SPY"], active["SPY"]),
            "QQQ": (active["QQQ"], changed),
            "IWM": (active["IWM"], active["IWM"]),
        }
    )

    result = _build(artifact_root, repo_root, provider)

    assert result.status == "input_unavailable"
    assert result.reason == "active_reader_nonrepeatable"
    assert result.safe_payload()["nonrepeatable_symbol_count"] == 1
    assert result.active_response_hash is None
    assert [item.series_category for item in result.evidence] == [
        "exact_match",
        "reader_nonrepeatable",
        "exact_match",
    ]
    assert len(provider.calls) == 6


def test_response_hash_is_stable_for_equal_decimal_representations() -> None:
    original = _bars_by_symbol()
    scaled = dict(original)
    scaled["SPY"] = tuple(
        replace(bar, close=bar.close.quantize(Decimal("0.0000"))) for bar in original["SPY"]
    )
    assert conformance._active_response_hash(
        _SYMBOLS, original
    ) == conformance._active_response_hash(
        _SYMBOLS,
        scaled,
    )


def test_schema_version_difference_is_not_an_ohlcv_revision(tmp_path: Path) -> None:
    artifact_root, repo_root = _roots(tmp_path)
    active = _bars_by_symbol()
    active["QQQ"] = tuple(
        replace(bar, schema_version=bar.schema_version + 1) for bar in active["QQQ"]
    )

    result = _build(artifact_root, repo_root, _Provider(active))

    assert result.status == "matching"
    assert result.safe_payload()["value_mismatch_symbol_count"] == 0


def test_client_error_is_input_unavailable_without_secret_leakage(tmp_path: Path) -> None:
    artifact_root, repo_root = _roots(tmp_path)

    result = _build(artifact_root, repo_root, _FailingProvider())

    assert result.status == "input_unavailable"
    assert result.reason == "active_client_unavailable"
    assert len(result.evidence) == 1
    assert result.evidence[0].series_category == "source_unavailable"
    assert result.safe_payload()["source_unavailable_symbol_count"] == 1
    assert result.active_response_hash is None
    receipt_text = (result.receipt_dir / "receipt.json").read_text(encoding="utf-8")
    assert _CREDENTIAL not in receipt_text


def test_mid_run_provider_failure_preserves_prior_symbol_evidence(tmp_path: Path) -> None:
    artifact_root, repo_root = _roots(tmp_path)
    provider = _MidRunFailingProvider(_bars_by_symbol())

    result = _build(artifact_root, repo_root, provider)

    assert result.status == "input_unavailable"
    assert result.reason == "active_client_unavailable"
    assert [item.series_category for item in result.evidence] == [
        "exact_match",
        "source_unavailable",
    ]
    assert result.observed_active_bar_count == 2
    assert result.safe_payload()["source_unavailable_symbol_count"] == 1
    assert len(provider.calls) == 3


def test_rejects_repository_artifacts_and_tampered_receipt(tmp_path: Path) -> None:
    artifact_root, repo_root = _roots(tmp_path)

    with pytest.raises(
        conformance.NorgateBroadActiveBuildConformanceError, match="outside the Git"
    ):
        conformance.build_norgate_broad_active_build_conformance_receipt(
            destination=repo_root / "inside-repo",
            artifact_root=repo_root,
            repo_root=repo_root,
            active_provider=_Provider(_bars_by_symbol()),
            catalog_loader=_CatalogLoader(_catalog()),
        )

    result = _build(artifact_root, repo_root, _Provider(_bars_by_symbol()))
    receipt_path = result.receipt_dir / "receipt.json"
    document = json.loads(receipt_path.read_text(encoding="utf-8"))
    forged_hash = "sha256:" + "f" * 64
    document["active_reader"]["active_response_sha256"] = forged_hash
    document["outcome"]["active_response_sha256"] = forged_hash
    receipt_path.write_text(json.dumps(document), encoding="utf-8")
    forged = conformance.verify_norgate_broad_active_build_conformance_receipt(
        result.receipt_dir,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    assert forged.active_response_hash == forged_hash
    with pytest.raises(conformance.NorgateBroadActiveBuildConformanceError, match="expected value"):
        conformance.verify_norgate_broad_active_build_conformance_receipt(
            result.receipt_dir,
            artifact_root=artifact_root,
            repo_root=repo_root,
            expected_receipt_sha256=result.receipt_sha256,
        )


def test_reference_manifest_hash_is_pinned_before_provider_reads(tmp_path: Path) -> None:
    artifact_root, repo_root = _roots(tmp_path)
    provider = _Provider(_bars_by_symbol())

    with pytest.raises(conformance.NorgateBroadActiveBuildConformanceError, match="identity"):
        conformance.build_norgate_broad_active_build_conformance_receipt(
            destination=artifact_root / "wrong-manifest",
            artifact_root=artifact_root,
            repo_root=repo_root,
            active_provider=provider,
            catalog_loader=_CatalogLoader(_catalog(manifest_hash="sha256:" + "d" * 64)),
        )
    assert provider.calls == []


def _build(
    artifact_root: Path,
    repo_root: Path,
    provider: _Provider | _DoubleReadProvider | _FailingProvider | _MidRunFailingProvider,
) -> conformance.NorgateBroadActiveBuildConformanceResult:
    return conformance.build_norgate_broad_active_build_conformance_receipt(
        destination=artifact_root / "run",
        artifact_root=artifact_root,
        repo_root=repo_root,
        active_provider=provider,
        catalog_loader=_CatalogLoader(_catalog()),
    )


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    artifact_root = tmp_path / "external-artifacts"
    repo_root = tmp_path / "repo"
    artifact_root.mkdir()
    repo_root.mkdir()
    return artifact_root, repo_root


def _catalog(
    *,
    manifest_hash: str = conformance.FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_MANIFEST_HASH,
) -> NorgateTrialDevelopmentPanelCatalog:
    bars = _bars_by_symbol()
    source = NorgateTrialDevelopmentPanelSourceIdentity(
        snapshot_dir=Path(_RAW_PATH) / "snapshot=immutable",
        dataset_id=FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_ID,
        dataset_hash=FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_HASH,
        manifest_hash=manifest_hash,
        membership_dataset_id="unit.membership",
        membership_dataset_hash="sha256:" + "b" * 64,
        calendar_dataset_id="unit.calendar",
        calendar_dataset_hash="sha256:" + "c" * 64,
        provider="Norgate Data",
        interval="D",
        requested_stock_price_adjustment_setting="NONE",
        adjustment_semantics_verified=False,
    )
    scope = NorgateTrialDevelopmentPanelScope(
        development_panel_attested=True,
        development_training_eligible=True,
        point_in_time_eligible=False,
        ranking_eligible=False,
        sealed_holdout_eligible=False,
        campaign_eligible=False,
        model_eligible=False,
        gpu_eligible=False,
        paper_trading_eligible=False,
    )
    ranks = MappingProxyType({symbol: index for index, symbol in enumerate(_SYMBOLS, start=1)})
    cataloged = MappingProxyType(
        {
            symbol: _cataloged_bars_from_verified_loader(
                dataset_id=FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_ID,
                dataset_hash=FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_HASH,
                source_path=Path(_RAW_PATH) / f"{symbol}.csv.gz",
                bars=bars[symbol],
            )
            for symbol in _SYMBOLS
        }
    )
    return NorgateTrialDevelopmentPanelCatalog(
        source=source,
        scope=scope,
        candidate_count=3,
        selected_symbol_count=3,
        candidate_ranks_by_symbol=ranks,
        bars_by_symbol=cataloged,
        common_sessions=_SESSIONS,
        source_limitations=("unit limitation",),
    )


def _bars_by_symbol() -> dict[str, tuple[Bar, ...]]:
    return {
        symbol: tuple(_bar(symbol, index, session) for index, session in enumerate(_SESSIONS))
        for symbol in _SYMBOLS
    }


def _bar(symbol: str, index: int, session: date) -> Bar:
    base = Decimal(_RAW_PRICE) + Decimal(index)
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=datetime.combine(session, datetime.min.time(), UTC),
        open=base,
        high=base + Decimal("1"),
        low=base - Decimal("1"),
        close=base + Decimal("0.25"),
        volume=Decimal("1000") + Decimal(index),
    )
