from __future__ import annotations

import json
import os
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.contracts import Timeframe
from thericher_v2.models.sequence_window import SequenceWindowInputError
from thericher_v2.research.causal_mtf_window_profile_feasibility import (
    CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
    CausalMtfWindowProfile,
    CausalMtfWindowProfileCatalog,
    assess_profile_feasibility,
    assess_profile_with_deterministic_synthetic_bars,
    deterministic_synthetic_bars,
    write_catalog_registration_receipt,
)

_CUTOFF = datetime(2026, 8, 5, 15, 0, tzinfo=UTC)
_ISSUED_AT = datetime(2026, 8, 5, 15, 1, tzinfo=UTC)


def test_catalog_digest_is_stable_and_has_exact_canonical_profiles() -> None:
    catalog = CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG

    assert tuple(profile.profile_id for profile in catalog.profiles) == (
        "short",
        "kis_baseline",
        "one_hour",
        "medium",
        "long",
        "extended",
    )
    assert catalog.identity_sha256 == CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.identity_sha256
    assert catalog.profile("extended").lookback_vector == (180, 36, 18, 2, 2)


def test_rejects_altered_or_forged_catalog() -> None:
    profiles = list(CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.profiles)
    profiles[0] = CausalMtfWindowProfile("short", (16, 3, 3, 2, 2))
    with pytest.raises(ValueError, match="immutable canonical"):
        CausalMtfWindowProfileCatalog(profiles=tuple(profiles))

    profiles = list(CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.profiles)
    profiles.reverse()
    with pytest.raises(ValueError, match="immutable canonical"):
        CausalMtfWindowProfileCatalog(profiles=tuple(profiles))

    with pytest.raises(ValueError, match="schema_version"):
        replace(CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG, schema_version=999)


def test_kis_baseline_profile_is_compatible_with_existing_causal_window_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)
    result = assess_profile_with_deterministic_synthetic_bars(
        catalog=CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
        profile_id="kis_baseline",
        cutoff=_CUTOFF,
    )

    assert result.status == "feasible"
    assert {timeframe: len(window.bars) for timeframe, window in result.window.windows.items()} == {
        Timeframe.M1: 30,
        Timeframe.M5: 6,
        Timeframe.M10: 3,
        Timeframe.H1: 2,
        Timeframe.H3: 2,
    }
    assert "100" not in str(result.source_safe_summary())


@pytest.mark.parametrize(
    "profile_id",
    ("short", "kis_baseline", "one_hour", "medium", "long", "extended"),
)
def test_every_canonical_profile_has_a_pure_deterministic_feasibility_path(
    profile_id: str,
) -> None:
    result = assess_profile_with_deterministic_synthetic_bars(
        catalog=CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
        profile_id=profile_id,
        cutoff=_CUTOFF,
    )

    assert result.status == "feasible"
    assert result.profile_id == profile_id


@pytest.mark.parametrize(
    ("mutate", "status", "timeframe"),
    [
        (
            lambda supplied: _replace_last(supplied, Timeframe.M1, complete=False),
            "incomplete",
            Timeframe.M1,
        ),
        (
            lambda supplied: {
                **supplied,
                Timeframe.M5: (*supplied[Timeframe.M5], supplied[Timeframe.M5][-1]),
            },
            "duplicate",
            Timeframe.M5,
        ),
        (
            lambda supplied: _replace_last(supplied, Timeframe.M10, start_ts=_CUTOFF),
            "future",
            Timeframe.M10,
        ),
        (lambda supplied: _gap_m1(supplied), "non_contiguous", Timeframe.M1),
        (lambda supplied: _stale_h3(supplied), "misaligned", Timeframe.H3),
    ],
)
def test_rejects_future_incomplete_duplicate_non_contiguous_and_stale_slow_inputs(
    mutate,
    status: str,
    timeframe: Timeframe,
) -> None:
    profile = CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.profile("kis_baseline")
    supplied = mutate(deterministic_synthetic_bars(profile=profile, cutoff=_CUTOFF))

    with pytest.raises(SequenceWindowInputError) as raised:
        assess_profile_feasibility(
            catalog=CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
            profile_id="kis_baseline",
            bars_by_timeframe=supplied,
            cutoff=_CUTOFF,
        )

    assert raised.value.status == status
    assert raised.value.timeframe == timeframe


def test_catalog_receipt_requires_external_root_and_redacts_it(tmp_path: Path) -> None:
    catalog = CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG
    artifact_root = tmp_path / "model-artifacts"
    receipt = write_catalog_registration_receipt(
        catalog=catalog,
        artifact_root=artifact_root,
        issued_at=_ISSUED_AT,
    )

    payload = json.loads(receipt.receipt_path.read_text(encoding="utf-8"))
    assert receipt.receipt_path.resolve().is_relative_to(artifact_root.resolve())
    assert payload["receipt_sha256"] == receipt.receipt_sha256
    receipt_text = receipt.receipt_path.read_text(encoding="utf-8")
    assert str(artifact_root) not in receipt_text
    assert "WINDOW" not in receipt_text
    assert "SYNTHETIC" not in receipt_text
    assert "100.00" not in receipt_text
    assert "campaign_id" not in receipt_text
    assert "profile_id" not in receipt_text
    with pytest.raises(ValueError, match="immutable"):
        write_catalog_registration_receipt(
            catalog=catalog,
            artifact_root=artifact_root,
            issued_at=_ISSUED_AT,
        )


def test_catalog_receipt_rejects_git_local_artifact_root() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    with pytest.raises(ValueError, match="outside the Git workspace"):
        write_catalog_registration_receipt(
            catalog=CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
            artifact_root=repo_root / "model-artifacts",
            issued_at=_ISSUED_AT,
        )


def _replace_last(supplied, timeframe: Timeframe, **changes):
    return {
        **supplied,
        timeframe: (*supplied[timeframe][:-1], replace(supplied[timeframe][-1], **changes)),
    }


def _gap_m1(supplied):
    bars = supplied[Timeframe.M1]
    return {
        **supplied,
        Timeframe.M1: (
            *bars[:-2],
            replace(bars[-2], start_ts=bars[-2].start_ts + timedelta(seconds=30)),
            bars[-1],
        ),
    }


def _stale_h3(supplied):
    profile = CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.profile("kis_baseline")
    stale_cutoff = _CUTOFF - Timeframe.H3.duration
    stale_h3_bars = deterministic_synthetic_bars(
        profile=profile,
        cutoff=stale_cutoff,
    )[Timeframe.H3]
    return {
        **supplied,
        Timeframe.H3: stale_h3_bars,
    }


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("window profile feasibility must remain offline")

    monkeypatch.setattr(os, "getenv", fail_external)
    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
