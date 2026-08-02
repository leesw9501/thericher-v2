from __future__ import annotations

import importlib
import json
import os
import socket
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib import request

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session

_MODULE_NAME = "thericher_v2.research.spy_intraday_mtf_logistic_10m"

try:
    research = importlib.import_module(_MODULE_NAME)
except ModuleNotFoundError as error:
    if error.name == _MODULE_NAME:
        pytest.skip(
            "awaiting the frozen SPY intraday MTF logistic implementation",
            allow_module_level=True,
        )
    raise


_SESSION_DATES = (
    date(2026, 6, 22),
    date(2026, 6, 23),
    date(2026, 6, 24),
    date(2026, 6, 25),
    date(2026, 6, 26),
    date(2026, 6, 29),
    date(2026, 6, 30),
    date(2026, 7, 1),
    date(2026, 7, 2),
    date(2026, 7, 6),
    date(2026, 7, 7),
    date(2026, 7, 8),
    date(2026, 7, 9),
    date(2026, 7, 10),
    date(2026, 7, 13),
    date(2026, 7, 14),
    date(2026, 7, 15),
    date(2026, 7, 16),
    date(2026, 7, 17),
    date(2026, 7, 20),
    date(2026, 7, 21),
)
_SLOTS_PER_SESSION = 19
_SOURCE_ID = "kis.paper.private.intraday.spy.ams.m1.v1"
_SOURCE_HASH = "sha256:64f149f5ff1c9002107f001a44f78c54c8944e9c030d6153898b1229d9c742e6"


def test_prepare_freezes_the_21_session_10_1_10_causal_multitimeframe_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)
    prepared = research.prepare_spy_intraday_mtf_logistic_10m(_catalog())
    payload = _safe_payload(prepared)

    assert prepared.status == "ready"
    assert _lookup(payload, "complete_regular_session_count") == 21
    contract = _mapping(payload, "contract")
    split = _mapping(contract, "split")
    assert _lookup(split, "development_sessions") == 10
    assert _lookup(split, "purge_sessions") == 1
    assert _lookup(split, "validation_sessions") == 10
    schedule = _mapping(contract, "decision_schedule")
    assert _lookup(schedule, "first_offset_minutes") == 180
    assert _lookup(schedule, "last_offset_minutes") == 360
    assert _lookup(schedule, "step_minutes") == 10
    assert _lookup(schedule, "timezone") == "America/New_York"

    features = _mapping(contract, "features")
    assert _lookup(features, "names") == [
        "m1_return_30m",
        "m1_realized_range_30m",
        "m5_return_6bar",
        "m10_return_3bar",
        "h1_latest_candle_return",
        "h3_latest_candle_return",
    ]
    assert _lookup(features, "m1_return_minutes") == 30
    assert _lookup(features, "m1_realized_range_minutes") == 30
    assert _lookup(features, "m5_return_completed_bars") == 6
    assert _lookup(features, "m10_return_completed_bars") == 3
    assert _lookup(features, "h1_latest_completed_candle_return") is True
    assert _lookup(features, "h3_latest_completed_candle_return") is True
    assert _lookup(contract, "target") == "next_10m_m1_open_to_open_sign"
    model = _mapping(contract, "model")
    assert _lookup(model, "long_only_probability_threshold") == "0.55000000000000004"
    preflight = _mapping(contract, "preflight")
    assert _lookup(preflight, "minimum_rows_each_phase") == 150
    assert _lookup(preflight, "minimum_validation_long_decisions") == 30

    phases = _phases(payload)
    for phase_name in ("development", "validation"):
        facts = phases[phase_name]
        assert _lookup(facts, "session_count") == 10
        assert _lookup(facts, "scheduled_row_count") == 10 * _SLOTS_PER_SESSION
        assert _lookup(facts, "feature_row_count") == 10 * _SLOTS_PER_SESSION
        assert _lookup(facts, "structural_unavailable_count") == 0


def test_fit_is_development_only_and_validation_target_changes_cannot_change_preflight_or_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)
    baseline_prepared = research.prepare_spy_intraday_mtf_logistic_10m(_catalog())
    shifted_prepared = research.prepare_spy_intraday_mtf_logistic_10m(
        _catalog(final_validation_target_shift=Decimal("77.777")),
    )

    assert _safe_payload(baseline_prepared) == _safe_payload(shifted_prepared)
    baseline_model = research.fit_spy_intraday_mtf_logistic_10m(baseline_prepared)
    shifted_model = research.fit_spy_intraday_mtf_logistic_10m(shifted_prepared)
    assert _safe_payload(baseline_model) == _safe_payload(shifted_model)

    contract_model = _mapping(_mapping(_safe_payload(baseline_prepared), "contract"), "model")
    fitted_model = _mapping(_safe_payload(baseline_model), "model")
    assert _lookup(fitted_model, "family") == "standardized_l2_logistic_regression"
    assert float(str(_lookup(fitted_model, "c"))) == pytest.approx(0.1)
    assert _lookup(fitted_model, "class_weight") is None
    assert _lookup(fitted_model, "fit_scope") == "development_only"
    assert _lookup(contract_model, "refit_allowed") is False

    # The poisoned value is a future target open for the final validation slot.
    # Preparation and fitting are not permitted to inspect it.
    poisoned_prepared = research.prepare_spy_intraday_mtf_logistic_10m(
        _catalog(poison_final_validation_target_open=True),
    )
    poisoned_model = research.fit_spy_intraday_mtf_logistic_10m(poisoned_prepared)
    assert _safe_payload(poisoned_prepared) == _safe_payload(baseline_prepared)
    assert _safe_payload(poisoned_model) == _safe_payload(baseline_model)


def test_target_free_long_floor_rejects_a_policy_before_validation_targets_are_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)
    prepared = research.prepare_spy_intraday_mtf_logistic_10m(
        _catalog(
            validation_profile="bearish",
            poison_final_validation_target_open=True,
        ),
    )
    model = research.fit_spy_intraday_mtf_logistic_10m(prepared)
    result = research.evaluate_spy_intraday_mtf_logistic_10m(prepared, model)

    assert result.status == "input_unavailable"
    payload = _safe_payload(result)
    assert _lookup(payload, "reason") == "insufficient_validation_long_decisions"
    input_payload = _mapping(payload, "input")
    validation_facts = _phases(input_payload)["validation"]
    assert _lookup(validation_facts, "feature_row_count") == 190
    assert _lookup(payload, "validation") is None


def test_validation_uses_executed_event_means_cost_band_and_the_dual_20bp_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)

    selective_prepared = research.prepare_spy_intraday_mtf_logistic_10m(
        _catalog(validation_profile="alternating"),
    )
    selective_model = research.fit_spy_intraday_mtf_logistic_10m(selective_prepared)
    selective = research.evaluate_spy_intraday_mtf_logistic_10m(
        selective_prepared,
        selective_model,
    )
    selective_validation = _mapping(_safe_payload(selective), "validation")
    candidate_count = _lookup(selective_validation, "policy_long_decision_count")
    reference_count = _lookup(selective_validation, "always_long_decision_count")
    assert 30 <= candidate_count < reference_count == 190
    _assert_mean_uses_own_executed_event_count(
        selective_validation,
        total_key="policy_net_total_bps_by_all_in_round_trip_cost",
        mean_key="policy_net_mean_bps_by_all_in_round_trip_cost",
        count=candidate_count,
    )
    _assert_mean_uses_own_executed_event_count(
        selective_validation,
        total_key="always_long_net_total_bps_by_all_in_round_trip_cost",
        mean_key="always_long_net_mean_bps_by_all_in_round_trip_cost",
        count=reference_count,
    )

    prepared = research.prepare_spy_intraday_mtf_logistic_10m(
        _catalog(validation_profile="bullish"),
    )
    model = research.fit_spy_intraday_mtf_logistic_10m(prepared)
    result = research.evaluate_spy_intraday_mtf_logistic_10m(prepared, model)

    assert result.status == "falsified"
    validation = _mapping(_safe_payload(result), "validation")
    assert _lookup(validation, "policy_long_decision_count") == 190
    assert _lookup(validation, "always_long_decision_count") == 190
    policy_totals = _decimal_mapping(
        validation,
        "policy_net_total_bps_by_all_in_round_trip_cost",
    )
    policy_means = _decimal_mapping(
        validation,
        "policy_net_mean_bps_by_all_in_round_trip_cost",
    )
    reference_means = _decimal_mapping(
        validation,
        "always_long_net_mean_bps_by_all_in_round_trip_cost",
    )
    assert tuple(policy_totals) == ("5", "10", "20")
    assert policy_totals["20"] <= 0
    assert policy_means == reference_means
    assert tuple(_lookup(validation, "kill_reasons")) == (
        "policy_net_total_flat_or_worse_at_20bp",
        "policy_mean_no_better_than_always_long_at_20bp",
    )


def test_run_writes_idempotent_source_safe_external_receipts_and_rejects_git_storage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    monkeypatch.setenv("KIS_PAPER_APP_KEY", "not-for-artifacts")
    monkeypatch.setenv("TIINGO_API_TOKEN", "not-for-artifacts")
    artifact_root = tmp_path / "model-artifacts"
    repo_root = tmp_path / "repository"
    repo_root.mkdir()
    catalog = _catalog(start_price=Decimal("987.654321"), validation_profile="bullish")

    first = research.run_spy_intraday_mtf_logistic_10m(
        catalog,
        artifact_root=artifact_root,
        run_label="unit-r1",
        repo_root=repo_root,
    )
    rerun = research.run_spy_intraday_mtf_logistic_10m(
        catalog,
        artifact_root=artifact_root,
        run_label="unit-r1",
        repo_root=repo_root,
    )

    assert first.precommit_path == rerun.precommit_path
    assert first.summary_path == rerun.summary_path
    assert first.precommit_hash == rerun.precommit_hash
    assert first.precommit_path.is_relative_to(artifact_root)
    assert first.summary_path.is_relative_to(artifact_root)
    serialized = json.dumps(
        {
            "precommit": json.loads(first.precommit_path.read_text(encoding="utf-8")),
            "summary": json.loads(first.summary_path.read_text(encoding="utf-8")),
        },
        sort_keys=True,
    )
    _assert_source_safe(json.loads(serialized))
    for forbidden in (
        "987.654321",
        "not-for-artifacts",
        "KIS_PAPER_APP_KEY",
        "TIINGO_API_TOKEN",
    ):
        assert forbidden not in serialized

    with pytest.raises(ValueError, match="outside Git"):
        research.run_spy_intraday_mtf_logistic_10m(
            catalog,
            artifact_root=repo_root / "model-artifacts",
            run_label="repo-r1",
            repo_root=repo_root,
        )


class _TargetOpenPoison(Decimal):
    """Raise if a target-only validation open enters preflight or fitting."""

    def __add__(self, _other: object) -> Decimal:
        _target_accessed()

    def __radd__(self, _other: object) -> Decimal:
        _target_accessed()

    def __sub__(self, _other: object) -> Decimal:
        _target_accessed()

    def __rsub__(self, _other: object) -> Decimal:
        _target_accessed()

    def __mul__(self, _other: object) -> Decimal:
        _target_accessed()

    def __rmul__(self, _other: object) -> Decimal:
        _target_accessed()

    def __truediv__(self, _other: object) -> Decimal:
        _target_accessed()

    def __rtruediv__(self, _other: object) -> Decimal:
        _target_accessed()


def _target_accessed() -> None:
    raise AssertionError("validation target must remain unread before evaluation")


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("SPY intraday MTF logistic must remain offline and credential-free")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_external)


def _safe_payload(value: object) -> dict[str, object]:
    method = getattr(value, "safe_payload", None)
    assert callable(method), "public campaign values must expose source-safe payloads"
    payload = method()
    assert isinstance(payload, dict)
    return payload


def _lookup(mapping: Mapping[str, object], *names: str) -> object:
    for name in names:
        if name in mapping:
            return mapping[name]
    raise AssertionError(
        f"missing required payload key; expected one of {names!r}, got {tuple(mapping)!r}"
    )


def _mapping(mapping: Mapping[str, object], *names: str) -> dict[str, object]:
    value = _lookup(mapping, *names)
    assert isinstance(value, dict), f"{names!r} must be a mapping"
    return value


def _phases(payload: Mapping[str, object]) -> dict[str, dict[str, object]]:
    entries = _lookup(payload, "phases")
    assert isinstance(entries, list)
    phases = {
        str(entry["phase"]): entry
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("phase"), str)
    }
    assert tuple(sorted(phases)) == ("development", "validation")
    return phases


def _decimal_mapping(mapping: Mapping[str, object], key: str) -> dict[str, Decimal]:
    raw = _mapping(mapping, key)
    return {name: Decimal(str(value)) for name, value in raw.items()}


def _assert_mean_uses_own_executed_event_count(
    validation: Mapping[str, object],
    *,
    total_key: str,
    mean_key: str,
    count: object,
) -> None:
    assert isinstance(count, int) and count > 0
    totals = _decimal_mapping(validation, total_key)
    means = _decimal_mapping(validation, mean_key)
    assert tuple(totals) == tuple(means) == ("5", "10", "20")
    for cost in totals:
        assert means[cost] == totals[cost] / Decimal(count)


def _assert_source_safe(value: object) -> None:
    forbidden_keys = {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "start_ts",
        "end_ts",
        "timestamp",
        "session_date",
        "source_path",
        "raw_bars",
        "labels",
        "predictions",
        "coefficients",
        "weights",
        "intercept",
    }
    if isinstance(value, dict):
        assert not forbidden_keys.intersection(value)
        for nested in value.values():
            _assert_source_safe(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_source_safe(nested)


def _catalog(
    *,
    start_price: Decimal = Decimal("1000"),
    validation_profile: str = "alternating",
    final_validation_target_shift: Decimal = Decimal("0"),
    poison_final_validation_target_open: bool = False,
) -> CatalogedBars:
    bars: list[Bar] = []
    for session_index, session_date in enumerate(_SESSION_DATES):
        session = us_equity_2026_session(session_date)
        assert session is not None
        profile = _profile_for_session(
            session_index=session_index,
            validation_profile=validation_profile,
        )
        for minute in range(390):
            opened, closed = _minute_prices(
                profile=profile,
                session_index=session_index,
                minute=minute,
                start_price=start_price,
            )
            if session_index == len(_SESSION_DATES) - 1 and minute == 370:
                opened += final_validation_target_shift
                closed += final_validation_target_shift
            high = max(opened, closed) + Decimal("0.001")
            low = min(opened, closed) - Decimal("0.001")
            if (
                session_index == len(_SESSION_DATES) - 1
                and minute == 370
                and poison_final_validation_target_open
            ):
                opened = _TargetOpenPoison(str(opened))
            bars.append(
                Bar(
                    symbol="SPY",
                    market="US",
                    timeframe=Timeframe.M1,
                    start_ts=session.window.open_ts + Timeframe.M1.duration * minute,
                    open=opened,
                    high=high,
                    low=low,
                    close=closed,
                    volume=Decimal("1000") + Decimal(session_index) + Decimal(minute),
                    complete=True,
                )
            )
    return _cataloged_bars_from_verified_loader(
        dataset_id=_SOURCE_ID,
        dataset_hash=_SOURCE_HASH,
        source_path=Path("D:/market_data/unit-spy-intraday-mtf-logistic-index.json"),
        bars=tuple(bars),
    )


def _profile_for_session(*, session_index: int, validation_profile: str) -> str:
    if session_index < 10:
        return "bullish" if session_index % 2 == 0 else "bearish"
    if session_index == 10:
        return "bullish"
    if validation_profile == "bullish":
        return "bullish"
    if validation_profile == "bearish":
        return "bearish"
    if validation_profile == "alternating":
        return "bullish" if session_index % 2 == 1 else "bearish"
    raise AssertionError(f"unknown validation profile: {validation_profile}")


def _minute_prices(
    *,
    profile: str,
    session_index: int,
    minute: int,
    start_price: Decimal,
) -> tuple[Decimal, Decimal]:
    base = start_price + Decimal(session_index) * Decimal("10")
    slope = Decimal("0.1") if profile == "bullish" else Decimal("-0.1")
    opened = base + slope * Decimal(minute)
    return opened, opened + slope / Decimal("10")
