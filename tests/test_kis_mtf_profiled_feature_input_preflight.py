from __future__ import annotations

import json
import os
import socket
import urllib.request
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_intraday_mtf_availability import (
    freeze_kis_intraday_mtf_availability_contract,
    materialize_kis_intraday_mtf_availability,
)
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.models.sequence_window import SequenceWindowInputError
from thericher_v2.research import kis_mtf_profiled_feature_input_preflight as preflight
from thericher_v2.research.causal_mtf_window_profile_feasibility import (
    CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
)

_SESSION_DATE = date(2026, 7, 6)
_CODE_REVISION = "sha256:" + "c" * 64


def test_all_frozen_profiles_form_aligned_target_free_pairs() -> None:
    materialization = _materialize(_catalogs())

    assert materialization.receipt.status == "feature_inputs_ready"
    assert materialization.receipt.eligible_session_count == 1
    assert tuple(
        aggregate.profile_id for aggregate in materialization.receipt.profile_aggregates
    ) == (
        "short",
        "kis_baseline",
        "one_hour",
        "medium",
        "long",
        "extended",
    )
    assert len(materialization.pairs) == 6
    for aggregate in materialization.receipt.profile_aggregates:
        assert aggregate.feature_ready_pair_count == 1
        assert aggregate.input_unavailable_pair_count == 0
        assert aggregate.aggregate_input_sha256 is not None
    for pair in materialization.pairs:
        expected = CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.profile(pair.profile_id)
        assert pair.catalog_sha256 == preflight.KIS_MTF_PROFILED_FEATURE_INPUT_CATALOG_SHA256
        assert pair.feature_timestamp == pair.cutoff
        assert all(leg.source_contract_sha256 == pair.source_contract_sha256 for leg in pair.legs)
        assert all(leg.cutoff == pair.cutoff for leg in pair.legs)
        assert all(leg.feature_timestamp == pair.feature_timestamp for leg in pair.legs)
        for leg in pair.legs:
            assert tuple(leg.window_ends) == tuple(
                (timeframe, sequence.end_ts) for timeframe, sequence in leg.window.windows.items()
            )
            assert {
                timeframe: len(rows) for timeframe, rows in leg.feature_values.items()
            } == dict(expected.lookbacks)


def test_post_cutoff_and_next_target_minutes_do_not_change_projection() -> None:
    baseline = _materialize(_catalogs(include_post_cutoff=True))
    changed = _materialize(_catalogs(include_post_cutoff=True, mutate_post_cutoff=True))

    assert _pair_digests(changed) == _pair_digests(baseline)
    assert _feature_values(changed) == _feature_values(baseline)
    assert changed.receipt.receipt_sha256 == baseline.receipt.receipt_sha256


def test_pre_cutoff_slow_constituent_change_requires_reconstruction_and_changes_digest() -> None:
    catalogs = _catalogs()
    baseline = _materialize(catalogs)
    first_pair = baseline.pairs[0]
    slow_bar = first_pair.legs[0].window.windows[Timeframe.H1].bars[-1]
    qqq_bars = catalogs["QQQ/NAS/1m"].bars
    changed_bar = next(
        bar for bar in qqq_bars if bar.start_ts == slow_bar.end_ts - timedelta(minutes=1)
    )
    changed_q = replace(
        changed_bar,
        high=changed_bar.high + Decimal("0.25"),
        close=changed_bar.close + Decimal("0.25"),
    )
    changed_prefix = tuple(
        changed_q if bar.start_ts == changed_bar.start_ts else bar for bar in qqq_bars
    )

    with pytest.raises(ValueError, match="reconstruction"):
        preflight.verify_slow_bar_constituent_containment(
            slow_bar=slow_bar,
            minute_bars=changed_prefix,
            cutoff=first_pair.cutoff,
        )

    changed_catalogs = {
        **catalogs,
        "QQQ/NAS/1m": _catalog("QQQ", "NAS", bars=changed_prefix),
    }
    recomputed = _materialize(changed_catalogs)
    assert _pair_digests(recomputed) != _pair_digests(baseline)


@pytest.mark.parametrize("mutation", ("future", "incomplete", "duplicate", "gap", "mismatched"))
def test_invalid_minute_inputs_become_categorical_no_result(mutation: str) -> None:
    catalogs = _catalogs()
    qqq_bars = catalogs["QQQ/NAS/1m"].bars
    if mutation == "future":
        changed = (*qqq_bars[:-1], replace(qqq_bars[-1], start_ts=qqq_bars[-1].end_ts))
        bad_catalog = _catalog("QQQ", "NAS", bars=changed)
    elif mutation == "incomplete":
        changed = (*qqq_bars[:-1], replace(qqq_bars[-1], complete=False))
        bad_catalog = _catalog("QQQ", "NAS", bars=changed)
    elif mutation == "duplicate":
        changed = (*qqq_bars, qqq_bars[-1])
        bad_catalog = _catalog("QQQ", "NAS", bars=changed)
    elif mutation == "gap":
        changed = qqq_bars[:-1]
        bad_catalog = _catalog("QQQ", "NAS", bars=changed)
    else:
        changed = (*qqq_bars[:-1], replace(qqq_bars[-1], symbol="OTHER"))
        bad_catalog = _unsafe_catalog("QQQ", "NAS", changed)

    result = _materialize({**catalogs, "QQQ/NAS/1m": bad_catalog})

    assert result.receipt.status == "input_unavailable"
    assert result.receipt.reason == "causal_input_unavailable"
    assert all(
        aggregate.feature_ready_pair_count == 0
        for aggregate in result.receipt.profile_aggregates
    )


@pytest.mark.parametrize(
    ("mutate", "status", "timeframe"),
    (
        (
            lambda supplied, cutoff: {
                **supplied,
                Timeframe.H1: supplied[Timeframe.H1][:-1],
            },
            "misaligned",
            Timeframe.H1,
        ),
        (
            lambda supplied, cutoff: {
                **supplied,
                Timeframe.H3: (
                    *supplied[Timeframe.H3][:-1],
                    replace(supplied[Timeframe.H3][-1], complete=False),
                ),
            },
            "incomplete",
            Timeframe.H3,
        ),
        (
            lambda supplied, cutoff: {
                **supplied,
                Timeframe.H1: (*supplied[Timeframe.H1], supplied[Timeframe.H1][-1]),
            },
            "duplicate",
            Timeframe.H1,
        ),
        (
            lambda supplied, cutoff: {
                **supplied,
                Timeframe.H3: (
                    *supplied[Timeframe.H3][:-2],
                    replace(
                        supplied[Timeframe.H3][-2],
                        start_ts=supplied[Timeframe.H3][-2].start_ts + timedelta(minutes=1),
                    ),
                    supplied[Timeframe.H3][-1],
                ),
            },
            "non_contiguous",
            Timeframe.H3,
        ),
        (
            lambda supplied, cutoff: {
                **supplied,
                Timeframe.H1: (
                    *supplied[Timeframe.H1][:-1],
                    replace(supplied[Timeframe.H1][-1], start_ts=cutoff),
                ),
            },
            "future",
            Timeframe.H1,
        ),
        (
            lambda supplied, cutoff: {
                **supplied,
                Timeframe.H3: (
                    *supplied[Timeframe.H3][:-1],
                    replace(supplied[Timeframe.H3][-1], symbol="OTHER"),
                ),
            },
            "misaligned",
            Timeframe.H3,
        ),
    ),
)
def test_pure_projection_rejects_stale_and_malformed_slow_bars(
    mutate,
    status: str,
    timeframe: Timeframe,
) -> None:
    catalogs = _catalogs()
    source_contract, source_receipt, contract = _contracts(catalogs)
    qqq_source = source_contract.source_identities[0]
    session = us_equity_2026_session(_SESSION_DATE)
    assert session is not None
    cutoff = preflight._session_cutoff(session.window)
    prefix = preflight._complete_causal_prefix(
        catalogs["QQQ/NAS/1m"].bars,
        expected_symbol="QQQ",
        session=session.window,
        cutoff=cutoff,
    )
    supplied = preflight._resample_completed_prefix(prefix, session=session.window, cutoff=cutoff)
    invalid = mutate(supplied, cutoff)

    with pytest.raises(SequenceWindowInputError) as raised:
        preflight.build_target_free_mtf_feature_projection(
            source_contract_sha256=contract.source_contract_sha256,
            source_dataset_hash=qqq_source.dataset_hash,
            catalog=CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
            profile_id="kis_baseline",
            minute_bars=prefix,
            bars_by_timeframe=invalid,
            cutoff=cutoff,
        )

    assert raised.value.status == status
    assert raised.value.timeframe == timeframe
    assert source_receipt.status == "qualified_for_prospective_input"


def test_slow_constituents_cannot_cross_cutoff_or_forge_values() -> None:
    catalogs = _catalogs()
    materialization = _materialize(catalogs)
    pair = next(pair for pair in materialization.pairs if pair.profile_id == "kis_baseline")
    slow_bar = pair.legs[0].window.windows[Timeframe.H3].bars[-1]
    session = us_equity_2026_session(_SESSION_DATE)
    assert session is not None
    cutoff = preflight._session_cutoff(session.window)
    prefix = preflight._complete_causal_prefix(
        catalogs["QQQ/NAS/1m"].bars,
        expected_symbol="QQQ",
        session=session.window,
        cutoff=cutoff,
    )

    future_constituent = replace(prefix[-1], start_ts=cutoff)
    with pytest.raises(ValueError, match="constituents"):
        preflight.verify_slow_bar_constituent_containment(
            slow_bar=slow_bar,
            minute_bars=(*prefix[:-1], future_constituent),
            cutoff=cutoff,
        )
    with pytest.raises(ValueError, match="reconstruction"):
        preflight.verify_slow_bar_constituent_containment(
            slow_bar=replace(slow_bar, volume=slow_bar.volume + Decimal("1")),
            minute_bars=prefix,
            cutoff=cutoff,
        )


def test_runner_is_offline_and_receipt_is_external_immutable_and_source_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalogs = _catalogs()
    _deny_external_access(monkeypatch)
    monkeypatch.setattr(
        preflight,
        "load_kis_intraday_mtf_availability_catalogs",
        lambda **_kwargs: catalogs,
    )
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"

    result = preflight.run_kis_mtf_profiled_feature_input_preflight(
        cache_root=tmp_path / "market-data",
        artifact_root=artifact_root,
        repo_root=repo_root,
        run_label="offline-r1",
        code_revision=_CODE_REVISION,
        expected_dataset_hashes={
            target_key: catalog.dataset_hash for target_key, catalog in catalogs.items()
        },
    )
    again = preflight.run_kis_mtf_profiled_feature_input_preflight(
        cache_root=tmp_path / "market-data",
        artifact_root=artifact_root,
        repo_root=repo_root,
        run_label="offline-r1",
        code_revision=_CODE_REVISION,
        expected_dataset_hashes={
            target_key: catalog.dataset_hash for target_key, catalog in catalogs.items()
        },
    )

    assert result.receipt.status == "feature_inputs_ready"
    assert again.summary_sha256 == result.summary_sha256
    payload = json.loads(result.summary_path.read_text(encoding="utf-8"))
    receipt_text = result.summary_path.read_text(encoding="utf-8")
    assert payload["receipt"]["status"] == "feature_inputs_ready"
    assert result.summary_path.resolve().is_relative_to(artifact_root.resolve())
    for forbidden in ("QQQ", "SPY", "2026-", "D:/", "100.00", "feature_values"):
        assert forbidden not in receipt_text

    with pytest.raises(ValueError, match="outside the Git workspace"):
        preflight.run_kis_mtf_profiled_feature_input_preflight(
            cache_root=tmp_path / "market-data",
            artifact_root=repo_root / "artifact",
            repo_root=repo_root,
            run_label="repo-root-r1",
            code_revision=_CODE_REVISION,
            expected_dataset_hashes={
                target_key: catalog.dataset_hash for target_key, catalog in catalogs.items()
            },
        )


def test_runner_rejects_symlinked_artifact_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalogs = _catalogs()
    monkeypatch.setattr(
        preflight,
        "load_kis_intraday_mtf_availability_catalogs",
        lambda **_kwargs: catalogs,
    )
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    external_target = tmp_path / "external-target"
    external_target.mkdir()
    linked_root = tmp_path / "linked-artifacts"
    try:
        linked_root.symlink_to(external_target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows host")

    with pytest.raises(ValueError, match="symlink"):
        preflight.run_kis_mtf_profiled_feature_input_preflight(
            cache_root=tmp_path / "market-data",
            artifact_root=linked_root,
            repo_root=repo_root,
            run_label="linked-root-r1",
            code_revision=_CODE_REVISION,
            expected_dataset_hashes={
                target_key: catalog.dataset_hash for target_key, catalog in catalogs.items()
            },
        )


def _materialize(
    catalogs: dict[str, CatalogedBars],
) -> preflight.KisMtfProfiledFeatureInputMaterialization:
    source_contract, source_receipt, contract = _contracts(catalogs)
    return preflight.materialize_kis_mtf_profiled_feature_inputs(
        contract=contract,
        source_contract=source_contract,
        source_receipt=source_receipt,
        catalogs=catalogs,
    )


def _contracts(
    catalogs: dict[str, CatalogedBars],
):
    source_contract = freeze_kis_intraday_mtf_availability_contract(
        catalogs,
        code_revision=_CODE_REVISION,
    )
    source_receipt = materialize_kis_intraday_mtf_availability(source_contract, catalogs)
    contract = preflight.freeze_kis_mtf_profiled_feature_input_contract(
        source_contract=source_contract,
        source_receipt=source_receipt,
        catalog=CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
        code_revision=_CODE_REVISION,
    )
    return source_contract, source_receipt, contract


def _catalogs(
    *,
    include_post_cutoff: bool = False,
    mutate_post_cutoff: bool = False,
) -> dict[str, CatalogedBars]:
    return {
        "QQQ/NAS/1m": _catalog(
            "QQQ",
            "NAS",
            bars=_bars(
                "QQQ",
                include_post_cutoff=include_post_cutoff,
                mutate_post_cutoff=mutate_post_cutoff,
            ),
        ),
        "SPY/AMS/1m": _catalog(
            "SPY",
            "AMS",
            bars=_bars("SPY", include_post_cutoff=include_post_cutoff),
        ),
    }


def _catalog(symbol: str, exchange: str, *, bars: tuple[Bar, ...]) -> CatalogedBars:
    return _cataloged_bars_from_verified_loader(
        dataset_id=f"kis.paper.private.intraday.{symbol.lower()}.{exchange.lower()}.m1.v1",
        dataset_hash=_sha256(f"{symbol}-{exchange}"),
        source_path=Path(f"D:/market-data/{symbol.lower()}.index.json"),
        bars=bars,
    )


def _unsafe_catalog(symbol: str, exchange: str, bars: tuple[Bar, ...]) -> CatalogedBars:
    result = object.__new__(CatalogedBars)
    object.__setattr__(
        result,
        "dataset_id",
        f"kis.paper.private.intraday.{symbol.lower()}.{exchange.lower()}.m1.v1",
    )
    object.__setattr__(result, "dataset_hash", _sha256(f"{symbol}-{exchange}"))
    object.__setattr__(result, "source_path", Path(f"D:/market-data/{symbol.lower()}.index.json"))
    object.__setattr__(result, "bars", bars)
    return result


def _bars(
    symbol: str,
    *,
    include_post_cutoff: bool = False,
    mutate_post_cutoff: bool = False,
) -> tuple[Bar, ...]:
    session = us_equity_2026_session(_SESSION_DATE)
    assert session is not None and session.kind == "regular"
    count = 362 if include_post_cutoff else 360
    output: list[Bar] = []
    for offset in range(count):
        base = Decimal("100") + Decimal(offset) / Decimal("1000")
        close = base + Decimal("0.02")
        if mutate_post_cutoff and offset >= 360:
            close += Decimal("3")
        output.append(
            Bar(
                symbol=symbol,
                market="US",
                timeframe=Timeframe.M1,
                start_ts=session.window.open_ts + timedelta(minutes=offset),
                open=base,
                high=close + Decimal("0.03"),
                low=base - Decimal("0.03"),
                close=close,
                volume=Decimal("1000") + Decimal(offset),
                complete=True,
            )
        )
    return tuple(output)


def _pair_digests(
    materialization: preflight.KisMtfProfiledFeatureInputMaterialization,
) -> tuple[str, ...]:
    return tuple(pair.pair_input_sha256 for pair in materialization.pairs)


def _feature_values(
    materialization: preflight.KisMtfProfiledFeatureInputMaterialization,
) -> tuple[object, ...]:
    return tuple(
        tuple(tuple(leg.feature_values.items()) for leg in pair.legs)
        for pair in materialization.pairs
    )


def _sha256(value: str) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def deny(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("preflight must remain local and credential-free")

    monkeypatch.setattr(os, "getenv", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
