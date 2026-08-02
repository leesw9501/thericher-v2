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
from thericher_v2.data import norgate_active_build_revision as revision
from thericher_v2.data.norgate_d1_diagnostic_source import VerifiedNorgateD1Panel
from thericher_v2.data.norgate_daily import (
    NorgateClientUnavailableError,
    NorgateMalformedResponseError,
)
from thericher_v2.data.norgate_trial_raw_d1 import NorgateTrialRawD1Result
from thericher_v2.data.provider import BarQuery

_SESSIONS = (date(2031, 2, 3), date(2031, 2, 4))
_RAW_DATE = "2031-02-03"
_RAW_PRICE = "913.777"
_RAW_PATH = r"D:\private-source\norgate"
_CREDENTIAL = "unit-secret-must-not-persist"


class _FixedPanelLoader:
    def __init__(self, panel: VerifiedNorgateD1Panel) -> None:
        self.panel = panel
        self.calls: list[tuple[Path, dict[str, object]]] = []

    def __call__(self, snapshot_dir: Path, **kwargs: object) -> VerifiedNorgateD1Panel:
        self.calls.append((snapshot_dir, kwargs))
        return self.panel


class _Provider:
    def __init__(self, bars_by_symbol: Mapping[str, tuple[Bar, ...]]) -> None:
        self.bars_by_symbol = bars_by_symbol
        self.calls: list[BarQuery] = []
        self.credential = _CREDENTIAL

    def get_bars(self, query: BarQuery) -> list[Bar]:
        self.calls.append(query)
        return list(self.bars_by_symbol[query.symbol])


class _FailingProvider:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def get_bars(self, _query: BarQuery) -> list[Bar]:
        self.calls += 1
        raise self.error


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


def test_exact_agreement_writes_redacted_receipt_and_reattaches_without_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_root, repo_root = _roots(tmp_path)
    panel = _panel()
    loader = _FixedPanelLoader(panel)
    provider = _Provider(panel.bars_by_symbol)

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("revision probe must not use the network")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    result = revision.build_norgate_active_build_revision_receipt(
        destination=artifact_root / "revision-equal",
        artifact_root=artifact_root,
        repo_root=repo_root,
        active_provider=provider,
        fixed_panel_loader=loader,
    )

    assert result.status == "matching"
    assert result.reason == "active_build_matches_frozen_contract"
    assert result.reference_bar_count == 6
    assert result.active_bar_count == 6
    assert result.divergent_bar_count == 0
    assert [item.symbol for item in result.evidence] == ["SPY", "QQQ", "IWM"]
    assert len(provider.calls) == 6
    assert all(query.timeframe is Timeframe.D1 for query in provider.calls)
    assert loader.calls == [
        (
            revision.FROZEN_NORGATE_FIXED_TRIO_D1_SNAPSHOT_DIR,
            {
                "expected_dataset_hash": revision.FROZEN_NORGATE_FIXED_TRIO_D1_DATASET_HASH,
                "expected_manifest_hash": revision.FROZEN_NORGATE_FIXED_TRIO_D1_MANIFEST_HASH,
                "market_data_root": revision.DEFAULT_MARKET_DATA_ROOT,
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
    assert result.active_response_hash is not None
    assert receipt["active_reader"]["active_response_sha256"] == result.active_response_hash
    assert result.safe_payload()["active_response_sha256"] == result.active_response_hash
    assert receipt["target_free_integrity"] == {
        "bar_level_divergence_is_categorical": True,
        "normalization_performed": False,
        "target_or_label_computed": False,
        "raw_ohlcv_persisted": False,
        "session_dates_persisted": False,
        "source_paths_persisted": False,
        "receipt_written_under_artifact_root": True,
    }

    calls_before_reattach = len(provider.calls)
    reattached = revision.verify_norgate_active_build_revision_receipt(
        result.receipt_dir,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    assert reattached == result
    assert len(provider.calls) == calls_before_reattach


def test_one_bar_divergence_is_categorical_revision_not_normalization(tmp_path: Path) -> None:
    artifact_root, repo_root = _roots(tmp_path)
    panel = _panel()
    altered = dict(panel.bars_by_symbol)
    altered["QQQ"] = (
        altered["QQQ"][0],
        replace(altered["QQQ"][1], close=altered["QQQ"][1].close + Decimal("0.125")),
    )

    result = revision.build_norgate_active_build_revision_receipt(
        destination=artifact_root / "revision-divergent",
        artifact_root=artifact_root,
        repo_root=repo_root,
        active_provider=_Provider(altered),
        fixed_panel_loader=_FixedPanelLoader(panel),
    )

    assert result.status == "revision_detected"
    assert result.reason == "bar_level_divergence_detected"
    assert result.divergent_bar_count == 1
    assert [item.divergent_bar_count for item in result.evidence] == [0, 1, 0]
    receipt = json.loads((result.receipt_dir / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["target_free_integrity"]["bar_level_divergence_is_categorical"] is True
    assert receipt["target_free_integrity"]["normalization_performed"] is False


def test_missing_active_sessions_are_structural_revision_with_stable_response(
    tmp_path: Path,
) -> None:
    artifact_root, repo_root = _roots(tmp_path)
    panel = _panel()
    missing = dict(panel.bars_by_symbol)
    missing["IWM"] = ()
    provider = _Provider(missing)

    result = revision.build_norgate_active_build_revision_receipt(
        destination=artifact_root / "revision-missing-session",
        artifact_root=artifact_root,
        repo_root=repo_root,
        active_provider=provider,
        fixed_panel_loader=_FixedPanelLoader(panel),
    )

    assert result.status == "revision_detected"
    assert result.reason == "bar_level_divergence_detected"
    assert result.active_bar_count == 4
    assert result.divergent_bar_count == 2
    assert [item.divergent_bar_count for item in result.evidence] == [0, 0, 2]
    assert result.active_response_hash is not None
    assert len(provider.calls) == 6


def test_structural_divergence_count_is_keyed_by_session_not_row_position() -> None:
    reference = tuple(
        _bar("SPY", index, session)
        for index, session in enumerate(
            (date(2031, 2, 3), date(2031, 2, 4), date(2031, 2, 5))
        )
    )

    assert revision._divergent_bar_count(reference, reference[1:]) == 1


def test_active_response_hash_is_stable_for_equal_decimal_representations() -> None:
    panel = _panel()
    scaled = dict(panel.bars_by_symbol)
    scaled["SPY"] = tuple(
        replace(bar, close=bar.close.quantize(Decimal("0.0000")))
        for bar in panel.bars_by_symbol["SPY"]
    )

    assert revision._active_response_hash(panel.bars_by_symbol) == revision._active_response_hash(
        scaled
    )


def test_result_rejects_matching_status_with_divergence(tmp_path: Path) -> None:
    artifact_root, repo_root = _roots(tmp_path)
    result = revision.build_norgate_active_build_revision_receipt(
        destination=artifact_root / "revision-valid-result",
        artifact_root=artifact_root,
        repo_root=repo_root,
        active_provider=_Provider(_panel().bars_by_symbol),
        fixed_panel_loader=_FixedPanelLoader(_panel()),
    )

    with pytest.raises(ValueError, match="revision result is invalid"):
        replace(result, divergent_bar_count=1)


def test_nonrepeatable_active_reader_is_input_unavailable_before_reference_comparison(
    tmp_path: Path,
) -> None:
    artifact_root, repo_root = _roots(tmp_path)
    panel = _panel()
    second_qqq = (
        panel.bars_by_symbol["QQQ"][0],
        replace(panel.bars_by_symbol["QQQ"][1], close=Decimal("914.500")),
    )
    provider = _DoubleReadProvider(
        {
            "SPY": (panel.bars_by_symbol["SPY"], panel.bars_by_symbol["SPY"]),
            "QQQ": (panel.bars_by_symbol["QQQ"], second_qqq),
            "IWM": (panel.bars_by_symbol["IWM"], panel.bars_by_symbol["IWM"]),
        }
    )

    result = revision.build_norgate_active_build_revision_receipt(
        destination=artifact_root / "revision-nonrepeatable",
        artifact_root=artifact_root,
        repo_root=repo_root,
        active_provider=provider,
        fixed_panel_loader=_FixedPanelLoader(panel),
    )

    assert result.status == "input_unavailable"
    assert result.reason == "active_reader_nonrepeatable"
    assert result.evidence == ()
    assert result.active_response_hash is None
    assert len(provider.calls) == 4
    receipt = json.loads((result.receipt_dir / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["active_reader"]["active_response_sha256"] is None
    assert _RAW_DATE not in json.dumps(receipt, sort_keys=True)
    assert _RAW_PRICE not in json.dumps(receipt, sort_keys=True)


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (NorgateClientUnavailableError(_CREDENTIAL), "active_client_unavailable"),
        (NorgateMalformedResponseError(_CREDENTIAL), "active_response_malformed"),
    ],
)
def test_provider_unavailable_or_malformed_is_categorized_without_error_leakage(
    tmp_path: Path,
    error: Exception,
    reason: str,
) -> None:
    artifact_root, repo_root = _roots(tmp_path)
    provider = _FailingProvider(error)

    result = revision.build_norgate_active_build_revision_receipt(
        destination=artifact_root / f"revision-{reason.replace('_', '-')}",
        artifact_root=artifact_root,
        repo_root=repo_root,
        active_provider=provider,
        fixed_panel_loader=_FixedPanelLoader(_panel()),
    )

    assert result.status == "input_unavailable"
    assert result.reason == reason
    assert result.evidence == ()
    assert result.active_response_hash is None
    assert result.active_bar_count == 0
    assert result.divergent_bar_count == 0
    assert provider.calls == 1
    receipt_text = (result.receipt_dir / "receipt.json").read_text(encoding="utf-8")
    assert _CREDENTIAL not in receipt_text


def test_rejects_repository_and_noncontained_artifact_destinations(tmp_path: Path) -> None:
    artifact_root, repo_root = _roots(tmp_path)

    with pytest.raises(revision.NorgateActiveBuildRevisionError, match="outside the Git workspace"):
        revision.build_norgate_active_build_revision_receipt(
            destination=repo_root / "revision-inside-repo",
            artifact_root=repo_root,
            repo_root=repo_root,
            active_provider=_Provider(_panel().bars_by_symbol),
            fixed_panel_loader=_FixedPanelLoader(_panel()),
        )
    with pytest.raises(revision.NorgateActiveBuildRevisionError, match="stay under artifact root"):
        revision.build_norgate_active_build_revision_receipt(
            destination=tmp_path / "elsewhere" / "revision-outside-root",
            artifact_root=artifact_root,
            repo_root=repo_root,
            active_provider=_Provider(_panel().bars_by_symbol),
            fixed_panel_loader=_FixedPanelLoader(_panel()),
        )


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    artifact_root = tmp_path / "external-artifacts"
    repo_root = tmp_path / "repo"
    artifact_root.mkdir()
    repo_root.mkdir()
    return artifact_root, repo_root


def _panel() -> VerifiedNorgateD1Panel:
    bars_by_symbol = {
        symbol: tuple(_bar(symbol, index, session) for index, session in enumerate(_SESSIONS))
        for symbol in ("SPY", "QQQ", "IWM")
    }
    return VerifiedNorgateD1Panel(
        source_result=NorgateTrialRawD1Result(
            snapshot_dir=Path(_RAW_PATH) / "snapshot=immutable",
            dataset_id="unit.fixed-trio",
            dataset_hash=revision.FROZEN_NORGATE_FIXED_TRIO_D1_DATASET_HASH,
            manifest_hash=revision.FROZEN_NORGATE_FIXED_TRIO_D1_MANIFEST_HASH,
            row_count=sum(len(bars) for bars in bars_by_symbol.values()),
            common_session_count=len(_SESSIONS),
            event_marker_count=0,
            excluded_session_count=0,
            actual_start=_SESSIONS[0],
            actual_end=_SESSIONS[-1],
            norgate_package_version="fixture",
            free_percent=40.0,
        ),
        common_sessions=_SESSIONS,
        bars_by_symbol=MappingProxyType(bars_by_symbol),
    )


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
