from __future__ import annotations

import json
import os
import socket
import urllib.request
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import norgate_kis_d1_bar_conformance as conformance

_NORGATE_HASH = "sha256:" + "a" * 64
_NORGATE_MANIFEST_HASH = "sha256:" + "b" * 64
_KIS_HASH = "sha256:" + "c" * 64
_KIS_INDEX_HASH = "sha256:" + "d" * 64


def test_writes_idempotent_aggregate_only_external_receipt_after_attested_loaders(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    repo_root.mkdir()
    artifact_root.mkdir()
    observed: dict[str, object] = {}
    _install_synthetic_loaders(monkeypatch, observed=observed)
    _deny_external_access(monkeypatch)

    result = conformance.build_norgate_kis_d1_bar_conformance_receipt(
        snapshot_dir=tmp_path / "snapshot",
        cache_root=tmp_path / "cache",
        artifact_root=artifact_root,
        expected_norgate_dataset_hash=_NORGATE_HASH,
        expected_norgate_manifest_hash=_NORGATE_MANIFEST_HASH,
        repo_root=repo_root,
    )
    repeated = conformance.build_norgate_kis_d1_bar_conformance_receipt(
        snapshot_dir=tmp_path / "snapshot",
        cache_root=tmp_path / "cache",
        artifact_root=artifact_root,
        expected_norgate_dataset_hash=_NORGATE_HASH,
        expected_norgate_manifest_hash=_NORGATE_MANIFEST_HASH,
        repo_root=repo_root,
    )

    assert result.status == "conforming_with_limits"
    assert result.receipt_path.is_relative_to(artifact_root)
    assert repeated.receipt_path == result.receipt_path
    assert repeated.receipt_sha256 == result.receipt_sha256
    assert observed["norgate"] == (_NORGATE_HASH, _NORGATE_MANIFEST_HASH)
    assert observed["kis"] == {
        "target_keys": ("QQQ/NAS/MODP=0", "SPY/AMS/MODP=0"),
        "expected_index_hash": conformance._HISTORICAL_KIS_DAILY_EXPECTED_INDEX_HASH,
        "expected_full_dataset_hash": conformance._HISTORICAL_KIS_DAILY_EXPECTED_FULL_DATASET_HASH,
    }

    payload = json.loads(result.receipt_path.read_text(encoding="utf-8"))
    assert payload["status"] == "conforming_with_limits"
    assert payload["artifact_policy"]["network_accessed"] is False
    assert payload["scope"]["point_in_time_proven"] is False
    assert len(payload["evidence"]) == 20
    _assert_aggregate_only(payload)
    assert str(tmp_path) not in result.receipt_path.read_text(encoding="utf-8")


def test_rejects_a_non_discriminating_shift_probe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    _install_synthetic_loaders(monkeypatch, constant_relationships=True)

    result = conformance.build_norgate_kis_d1_bar_conformance_receipt(
        snapshot_dir=tmp_path / "snapshot",
        cache_root=tmp_path / "cache",
        artifact_root=artifact_root,
        expected_norgate_dataset_hash=_NORGATE_HASH,
        expected_norgate_manifest_hash=_NORGATE_MANIFEST_HASH,
    )

    assert result.status == "nonconforming"
    assert any(item.status == "nonconforming" for item in result.evidence)


def test_shift_probes_use_global_common_sessions_not_stratum_local_neighbors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    _install_synthetic_loaders(monkeypatch)

    result = conformance.build_norgate_kis_d1_bar_conformance_receipt(
        snapshot_dir=tmp_path / "snapshot",
        cache_root=tmp_path / "cache",
        artifact_root=artifact_root,
        expected_norgate_dataset_hash=_NORGATE_HASH,
        expected_norgate_manifest_hash=_NORGATE_MANIFEST_HASH,
    )

    discontinuity = next(
        item
        for item in result.evidence
        if item.symbol == "SPY"
        and item.field_id == "open_to_close"
        and item.stratum == "discontinuity_adjacent"
    )
    # The three adjacent sessions use their actual t-1/t+1 common-date neighbors,
    # including neighbors outside their stratum.
    assert discontinuity.aligned_sample_count == 3
    assert discontinuity.backward_sample_count == 3
    assert discontinuity.forward_sample_count == 3
    quiet = next(
        item
        for item in result.evidence
        if item.symbol == "SPY" and item.field_id == "open_to_close" and item.stratum == "quiet"
    )
    # The first/last common dates have no shared t-1/t+1 probe, so all three
    # comparisons are evaluated on the remaining seven anchors only.
    assert (
        quiet.aligned_sample_count
        == quiet.backward_sample_count
        == quiet.forward_sample_count
        == 7
    )
    assert all(
        item.aligned_sample_count
        == item.backward_sample_count
        == item.forward_sample_count
        for item in result.evidence
    )


def test_common_session_relationships_never_use_a_source_private_predecessor() -> None:
    norgate_bars = _bars("SPY", constant_relationships=False, include_discontinuity=True)
    kis_bars = tuple(bar for index, bar in enumerate(norgate_bars) if index != 5)
    norgate_stream = {bar.start_ts.date(): bar for bar in norgate_bars}
    kis_stream = {bar.start_ts.date(): bar for bar in kis_bars}
    sessions = tuple(sorted(set(norgate_stream) & set(kis_stream)))
    target = norgate_bars[6].start_ts.date()
    common_prior = norgate_bars[4]
    source_private_prior = norgate_bars[5]

    norgate_values = conformance._relationship_values(norgate_stream, sessions=sessions)
    kis_values = conformance._relationship_values(kis_stream, sessions=sessions)

    assert norgate_values[target]["close_to_close"] == kis_values[target]["close_to_close"]
    assert norgate_values[target]["close_to_close"] == norgate_bars[6].close / common_prior.close
    assert (
        norgate_values[target]["close_to_close"]
        != norgate_bars[6].close / source_private_prior.close
    )
    assert norgate_values[target]["volume_ratio"] == kis_values[target]["volume_ratio"]


def test_noncommon_discontinuity_marks_its_adjacent_common_sessions() -> None:
    norgate_bars = _bars("SPY", constant_relationships=False, include_discontinuity=True)
    kis_bars = tuple(bar for index, bar in enumerate(norgate_bars) if index != 5)
    norgate_stream = {bar.start_ts.date(): bar for bar in norgate_bars}
    kis_stream = {bar.start_ts.date(): bar for bar in kis_bars}
    sessions = tuple(sorted(set(norgate_stream) & set(kis_stream)))

    strata = conformance._strata_for_symbol(
        sessions=sessions,
        norgate=norgate_stream,
        kis=kis_stream,
    )

    assert norgate_bars[5].start_ts.date() not in sessions
    assert norgate_bars[4].start_ts.date() in strata["discontinuity_adjacent"]
    assert norgate_bars[6].start_ts.date() in strata["discontinuity_adjacent"]


def test_price_relationship_outside_five_bp_tolerance_is_nonconforming(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    _install_synthetic_loaders(monkeypatch, kis_close_multiplier=Decimal("1.02"))

    result = conformance.build_norgate_kis_d1_bar_conformance_receipt(
        snapshot_dir=tmp_path / "snapshot",
        cache_root=tmp_path / "cache",
        artifact_root=artifact_root,
        expected_norgate_dataset_hash=_NORGATE_HASH,
        expected_norgate_manifest_hash=_NORGATE_MANIFEST_HASH,
    )

    assert result.status == "nonconforming"


def test_zero_volume_ratio_is_nonconforming_not_a_missing_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    _install_synthetic_loaders(monkeypatch, kis_zero_volume_index=7)

    result = conformance.build_norgate_kis_d1_bar_conformance_receipt(
        snapshot_dir=tmp_path / "snapshot",
        cache_root=tmp_path / "cache",
        artifact_root=artifact_root,
        expected_norgate_dataset_hash=_NORGATE_HASH,
        expected_norgate_manifest_hash=_NORGATE_MANIFEST_HASH,
    )

    assert result.status == "nonconforming"
    assert any(
        item.field_id == "volume_ratio" and item.status == "nonconforming"
        for item in result.evidence
    )


def test_empty_discontinuity_stratum_fails_closed_as_input_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    _install_synthetic_loaders(monkeypatch, include_discontinuity=False)

    result = conformance.build_norgate_kis_d1_bar_conformance_receipt(
        snapshot_dir=tmp_path / "snapshot",
        cache_root=tmp_path / "cache",
        artifact_root=artifact_root,
        expected_norgate_dataset_hash=_NORGATE_HASH,
        expected_norgate_manifest_hash=_NORGATE_MANIFEST_HASH,
    )

    assert result.status == "input_unavailable"
    assert any(item.status == "input_unavailable" for item in result.evidence)


def test_rejects_repo_artifact_root_before_attested_loader_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    calls = 0

    def forbidden_loader(*_args: object, **_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("loader must not run")

    monkeypatch.setattr(conformance, "load_verified_norgate_d1_diagnostic_panel", forbidden_loader)

    with pytest.raises(ValueError, match="outside the Git workspace"):
        conformance.build_norgate_kis_d1_bar_conformance_receipt(
            snapshot_dir=tmp_path / "snapshot",
            cache_root=tmp_path / "cache",
            artifact_root=repo_root,
            expected_norgate_dataset_hash=_NORGATE_HASH,
            expected_norgate_manifest_hash=_NORGATE_MANIFEST_HASH,
            repo_root=repo_root,
        )
    assert calls == 0


def test_rejects_nested_symlink_artifact_component_before_any_receipt_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    campaign_path = artifact_root / conformance.NORGATE_KIS_D1_BAR_CONFORMANCE_ID
    campaign_path.mkdir()
    _mark_as_symlink(monkeypatch, campaign_path)
    _install_synthetic_loaders(monkeypatch)

    with pytest.raises(ValueError, match="contains a symlink"):
        conformance.build_norgate_kis_d1_bar_conformance_receipt(
            snapshot_dir=tmp_path / "snapshot",
            cache_root=tmp_path / "cache",
            artifact_root=artifact_root,
            expected_norgate_dataset_hash=_NORGATE_HASH,
            expected_norgate_manifest_hash=_NORGATE_MANIFEST_HASH,
        )
    assert not any(campaign_path.iterdir())


@pytest.mark.parametrize("component", ("campaign", "hash", "receipt"))
def test_receipt_path_rejects_each_symlink_component(
    component: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    receipt_hash = "sha256:" + "e" * 64
    campaign = artifact_root / conformance.NORGATE_KIS_D1_BAR_CONFORMANCE_ID
    campaign.mkdir()
    digest = campaign / receipt_hash[7:]
    digest.mkdir()
    receipt = digest / "receipt.json"
    if component == "campaign":
        marked = campaign
    elif component == "hash":
        marked = digest
    else:
        receipt.write_bytes(b"receipt")
        marked = receipt
    _mark_as_symlink(monkeypatch, marked)

    with pytest.raises(ValueError, match="contains a symlink"):
        conformance._receipt_path(artifact_root, receipt_hash)


def _mark_as_symlink(monkeypatch: pytest.MonkeyPatch, marked: Path) -> None:
    original = Path.is_symlink

    def is_symlink(path: Path) -> bool:
        return path == marked or original(path)

    monkeypatch.setattr(Path, "is_symlink", is_symlink)


def test_conflicting_existing_receipt_is_never_overwritten(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    _install_synthetic_loaders(monkeypatch)
    arguments = {
        "snapshot_dir": tmp_path / "snapshot",
        "cache_root": tmp_path / "cache",
        "artifact_root": artifact_root,
        "expected_norgate_dataset_hash": _NORGATE_HASH,
        "expected_norgate_manifest_hash": _NORGATE_MANIFEST_HASH,
    }
    first = conformance.build_norgate_kis_d1_bar_conformance_receipt(**arguments)
    first.receipt_path.write_bytes(b"conflicting-content")

    with pytest.raises(FileExistsError, match="immutable"):
        conformance.build_norgate_kis_d1_bar_conformance_receipt(**arguments)
    assert first.receipt_path.read_bytes() == b"conflicting-content"


def test_module_has_no_client_credential_broker_or_training_surface() -> None:
    source = Path(conformance.__file__).read_text(encoding="utf-8").lower()
    for forbidden in (
        "dotenv",
        "getenv",
        "requests.",
        "urllib.request",
        "socket.",
        "orderintent",
        "torch",
    ):
        assert forbidden not in source
    assert "from thericher_v2.execution" not in source
    assert "os.replace" not in source
    assert 'open("xb")' in source


def _install_synthetic_loaders(
    monkeypatch: pytest.MonkeyPatch,
    *,
    observed: dict[str, object] | None = None,
    constant_relationships: bool = False,
    kis_close_multiplier: Decimal = Decimal("1"),
    kis_zero_volume_index: int | None = None,
    include_discontinuity: bool = True,
) -> None:
    norgate_bars = _bars(
        "SPY",
        constant_relationships=constant_relationships,
        include_discontinuity=include_discontinuity,
    )
    qqq_norgate = _bars(
        "QQQ",
        constant_relationships=constant_relationships,
        include_discontinuity=include_discontinuity,
    )
    kis_spy = _mutate_close(norgate_bars, kis_close_multiplier, kis_zero_volume_index)
    kis_qqq = _mutate_close(qqq_norgate, kis_close_multiplier)

    def norgate_loader(_snapshot: Path, **kwargs: object) -> object:
        if observed is not None:
            observed["norgate"] = (
                kwargs["expected_dataset_hash"],
                kwargs["expected_manifest_hash"],
            )
        return SimpleNamespace(
            source_result=SimpleNamespace(
                dataset_hash=_NORGATE_HASH, manifest_hash=_NORGATE_MANIFEST_HASH
            ),
            bars_by_symbol={"SPY": norgate_bars, "QQQ": qqq_norgate},
        )

    def kis_loader(_cache: Path, **kwargs: object) -> object:
        if observed is not None:
            observed["kis"] = {
                "target_keys": kwargs["target_keys"],
                "expected_index_hash": kwargs["expected_index_hash"],
                "expected_full_dataset_hash": kwargs["expected_full_dataset_hash"],
            }
        return SimpleNamespace(
            dataset_id=conformance.KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
            dataset_hash=_KIS_HASH,
            index_hash=_KIS_INDEX_HASH,
            adjustment_mode="MODP=0_unadjusted",
            bars_by_symbol={
                "SPY": SimpleNamespace(bars=kis_spy),
                "QQQ": SimpleNamespace(bars=kis_qqq),
            },
        )

    monkeypatch.setattr(conformance, "load_verified_norgate_d1_diagnostic_panel", norgate_loader)
    monkeypatch.setattr(conformance, "load_kis_paper_private_daily_catalog", kis_loader)


def _bars(
    symbol: str, *, constant_relationships: bool, include_discontinuity: bool
) -> tuple[Bar, ...]:
    start = date(2024, 1, 2)
    bars: list[Bar] = []
    prior_close = Decimal("100")
    for index in range(12):
        session = start + timedelta(days=index)
        if constant_relationships:
            open_value = prior_close * (
                Decimal("1.25") if include_discontinuity and index == 5 else Decimal("1")
            )
            close_value = open_value
            high_value = open_value * Decimal("1.1")
            low_value = open_value * Decimal("0.9")
            volume = Decimal("1000")
        else:
            open_factor = Decimal("1") + Decimal(index + 1) / Decimal("1000")
            if include_discontinuity and index == 5:
                open_factor = Decimal("1.25")
            open_value = prior_close * open_factor
            close_value = open_value * (Decimal("1") + Decimal(index + 1) / Decimal("1000"))
            high_value = open_value * (Decimal("1.02") + Decimal(index) / Decimal("500"))
            low_value = open_value * (Decimal("0.98") - Decimal(index) / Decimal("1000"))
            volume = Decimal("1000") * Decimal((index + 2) ** 2)
        bars.append(
            Bar(
                symbol=symbol,
                market="US",
                timeframe=Timeframe.D1,
                start_ts=datetime.combine(session, datetime.min.time(), UTC),
                open=open_value,
                high=high_value,
                low=low_value,
                close=close_value,
                volume=volume,
                complete=True,
            )
        )
        prior_close = close_value
    return tuple(bars)


def _mutate_close(
    bars: tuple[Bar, ...], multiplier: Decimal, zero_volume_index: int | None = None
) -> tuple[Bar, ...]:
    if multiplier == 1 and zero_volume_index is None:
        return bars
    result: list[Bar] = []
    for index, bar in enumerate(bars):
        close_value = bar.close * multiplier
        result.append(
            Bar(
                symbol=bar.symbol,
                market=bar.market,
                timeframe=bar.timeframe,
                start_ts=bar.start_ts,
                open=bar.open,
                high=max(bar.high, close_value),
                low=min(bar.low, close_value),
                close=close_value,
                volume=Decimal("0") if index == zero_volume_index else bar.volume,
                complete=bar.complete,
            )
        )
    return tuple(result)


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("conformance must remain offline and credential-free")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)


def _assert_aggregate_only(value: object) -> None:
    forbidden = {
        "date",
        "dates",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "price",
        "prices",
        "return",
        "returns",
        "path",
        "paths",
        "credential",
        "token",
    }
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = "".join(character for character in key.lower() if character.isalnum())
            assert normalized not in forbidden
            _assert_aggregate_only(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_aggregate_only(nested)
