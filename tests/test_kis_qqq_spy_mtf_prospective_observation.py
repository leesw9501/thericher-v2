from __future__ import annotations

import hashlib
import json
import socket
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import thericher_v2.data.kis_qqq_spy_mtf_prospective_observation as observation
from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session


def test_pair_attempt_binds_historical_exclusion_and_exact_causal_tails(tmp_path: Path) -> None:
    historical_date = date(2026, 7, 20)
    prospective_date = date(2026, 7, 21)
    contract, repository, artifact_root = _contract(tmp_path, historical_date)
    draft = observation.materialize_kis_qqq_spy_mtf_prospective_attempt(
        contract,
        prospective_catalogs=_catalogs(prospective_date),
        observed_at=_observed_after_cutoff(prospective_date),
    )

    assert contract.historical_exclusion_through == historical_date
    assert draft.status == "observed"
    assert draft.reason == "pair_available"
    assert [target.availability for target in draft.targets] == ["available", "available"]
    for target in draft.targets:
        sequence = target._sequence_window
        assert sequence is not None
        assert tuple(sequence.windows) == (
            Timeframe.M1,
            Timeframe.M5,
            Timeframe.M10,
            Timeframe.H1,
            Timeframe.H3,
        )
        assert [len(sequence.windows[timeframe].bars) for timeframe in sequence.windows] == [
            30,
            6,
            3,
            2,
            2,
        ]
        assert all(window.end_ts == draft.cutoff for window in sequence.windows.values())
        assert all(
            window.start_ts >= draft.session.open_ts
            for window in sequence.windows.values()
        )
        assert target.source.dataset_hash is None

    result = observation.append_kis_qqq_spy_mtf_prospective_attempt(
        artifact_root=artifact_root,
        repo_root=repository,
        draft=draft,
    )

    assert result.outcome == "appended"
    assert result.attempt is not None
    assert result.attempt.sealed_at >= draft.cutoff
    rendered = "\n".join(
        path.read_text(encoding="ascii")
        for path in artifact_root.rglob("*.json")
    )
    assert "101.234" not in rendered
    assert str(tmp_path) not in rendered
    assert '"open": "101.234' not in rendered
    assert '"close": "101.734' not in rendered
    assert '"volume": "99123' not in rendered
    assert '"account"' not in rendered
    assert '"credential"' not in rendered


def test_one_leg_failure_is_a_sealed_not_observed_attempt(tmp_path: Path) -> None:
    historical_date = date(2026, 7, 20)
    prospective_date = date(2026, 7, 21)
    contract, repository, artifact_root = _contract(tmp_path, historical_date)
    catalogs = _catalogs(prospective_date)
    draft = observation.materialize_kis_qqq_spy_mtf_prospective_attempt(
        contract,
        prospective_catalogs={
            "QQQ/NAS/1m": catalogs["QQQ/NAS/1m"],
            "SPY/AMS/1m": None,
        },
        observed_at=_observed_after_cutoff(prospective_date),
    )

    result = observation.append_kis_qqq_spy_mtf_prospective_attempt(
        artifact_root=artifact_root,
        repo_root=repository,
        draft=draft,
    )

    assert draft.status == "not_observed"
    assert draft.reason == "spy_unavailable"
    assert [target.availability for target in draft.targets] == ["available", "missing"]
    assert result.outcome == "appended"
    assert result.attempt is not None
    assert result.attempt.sealed_at >= draft.cutoff


def test_historical_session_is_explicitly_excluded(tmp_path: Path) -> None:
    historical_date = date(2026, 7, 20)
    contract, _, _ = _contract(tmp_path, historical_date)

    draft = observation.materialize_kis_qqq_spy_mtf_prospective_attempt(
        contract,
        prospective_catalogs=_catalogs(historical_date),
        observed_at=_observed_after_cutoff(historical_date),
    )

    assert draft.status == "not_observed"
    assert draft.reason == "historical_excluded"
    assert all(target.availability == "missing" for target in draft.targets)


@pytest.mark.parametrize(
    ("session_date", "expected_cutoff"),
    [
        (date(2026, 3, 10), datetime(2026, 3, 10, 19, 30, tzinfo=UTC)),
        (date(2026, 11, 30), datetime(2026, 11, 30, 20, 30, tzinfo=UTC)),
    ],
)
def test_observation_window_uses_dst_safe_eastern_cutoff(
    session_date: date,
    expected_cutoff: datetime,
) -> None:
    window = observation.prospective_observation_window(expected_cutoff)

    assert window is not None
    observed_date, session, cutoff = window
    assert observed_date == session_date
    assert cutoff == expected_cutoff
    assert session.open_ts < cutoff < session.close_ts


def test_store_is_idempotent_records_divergence_and_keeps_monotonic_seals(tmp_path: Path) -> None:
    historical_date = date(2026, 7, 20)
    first_date = date(2026, 7, 21)
    second_date = date(2026, 7, 22)
    contract, repository, artifact_root = _contract(tmp_path, historical_date)
    first_draft = observation.materialize_kis_qqq_spy_mtf_prospective_attempt(
        contract,
        prospective_catalogs=_catalogs(first_date),
        observed_at=_observed_after_cutoff(first_date),
    )
    first = observation.append_kis_qqq_spy_mtf_prospective_attempt(
        artifact_root=artifact_root,
        repo_root=repository,
        draft=first_draft,
    )
    duplicate = observation.append_kis_qqq_spy_mtf_prospective_attempt(
        artifact_root=artifact_root,
        repo_root=repository,
        draft=first_draft,
    )

    changed_catalogs = _catalogs(first_date)
    changed_bars = changed_catalogs["QQQ/NAS/1m"].bars
    changed_catalogs["QQQ/NAS/1m"] = _catalog(
        "QQQ",
        "NAS",
        first_date,
        bars=changed_bars[:-1]
        + (replace(changed_bars[-1], close=changed_bars[-1].close + Decimal("0.1")),),
    )
    changed_draft = observation.materialize_kis_qqq_spy_mtf_prospective_attempt(
        contract,
        prospective_catalogs=changed_catalogs,
        observed_at=_observed_after_cutoff(first_date) + timedelta(minutes=1),
    )
    conflict = observation.append_kis_qqq_spy_mtf_prospective_attempt(
        artifact_root=artifact_root,
        repo_root=repository,
        draft=changed_draft,
    )
    second = observation.append_kis_qqq_spy_mtf_prospective_attempt(
        artifact_root=artifact_root,
        repo_root=repository,
        draft=observation.materialize_kis_qqq_spy_mtf_prospective_attempt(
            contract,
            prospective_catalogs=_catalogs(second_date),
            observed_at=_observed_after_cutoff(second_date),
        ),
    )

    assert first.outcome == "appended"
    assert duplicate.outcome == "duplicate"
    assert conflict.outcome == "conflict"
    assert conflict.attempt_count == 1
    assert len(list(artifact_root.rglob("conflicts/*.json"))) == 1
    assert second.outcome == "appended"
    assert first.attempt is not None
    assert conflict.attempt is not None
    assert second.attempt is not None
    assert second.attempt.sealed_at > first.attempt.sealed_at
    assert second.attempt.sealed_at > conflict.attempt.sealed_at


def test_store_stops_at_thirty_fresh_session_attempts(tmp_path: Path) -> None:
    historical_date = date(2026, 7, 20)
    session_dates = _regular_dates_after(historical_date, count=31)
    contract, repository, artifact_root = _contract(tmp_path, historical_date)
    head_catalogs = _catalogs(*session_dates)

    for session_date in session_dates[:30]:
        result = observation.append_kis_qqq_spy_mtf_prospective_attempt(
            artifact_root=artifact_root,
            repo_root=repository,
            draft=observation.materialize_kis_qqq_spy_mtf_prospective_attempt(
                contract,
                prospective_catalogs=head_catalogs,
                observed_at=_observed_after_cutoff(session_date),
            ),
        )
        assert result.outcome == "appended"

    terminal = observation.append_kis_qqq_spy_mtf_prospective_attempt(
        artifact_root=artifact_root,
        repo_root=repository,
        draft=observation.materialize_kis_qqq_spy_mtf_prospective_attempt(
            contract,
            prospective_catalogs=head_catalogs,
            observed_at=_observed_after_cutoff(session_dates[30]),
        ),
    )

    assert terminal.outcome == "cap_reached"
    assert terminal.attempt_count == 30
    assert len(list(artifact_root.rglob("attempts/*.json"))) == 30


def test_runner_uses_no_environment_network_account_or_order_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    historical_date = date(2026, 7, 20)
    prospective_date = date(2026, 7, 21)
    historical = _catalogs(historical_date)
    head = _catalogs(prospective_date)
    repository = tmp_path / "repo"
    repository.mkdir()
    artifact_root = tmp_path / "artifacts"
    summary_path = _write_availability_summary(
        artifact_root,
        historical,
        common_count=1,
    )
    historical_root = tmp_path / "historical"
    head_root = tmp_path / "head"

    def load_catalog(**kwargs: object) -> CatalogedBars:
        catalogs = historical if Path(kwargs["cache_root"]) == historical_root else head
        return catalogs[f"{kwargs['symbol']}/{kwargs['exchange']}/1m"]

    monkeypatch.setattr(
        observation,
        "load_verified_kis_paper_private_intraday_catalog",
        load_catalog,
    )
    monkeypatch.setattr(socket, "create_connection", _forbid)
    monkeypatch.setattr(observation.os, "environ", _DenyEnvironment())

    result = observation.run_kis_qqq_spy_mtf_prospective_attempt(
        availability_summary_path=summary_path,
        historical_cache_root=historical_root,
        head_cache_root=head_root,
        artifact_root=artifact_root,
        repo_root=repository,
        code_revision=_sha256("code-r1"),
        observed_at=_observed_after_cutoff(prospective_date),
    )

    assert result is not None
    assert result.outcome == "appended"
    source = Path(observation.__file__).read_text(encoding="utf-8")
    assert "os.environ" not in source
    assert "execution." not in source
    assert "local_paper" not in source


def test_runner_reuses_the_sealed_contract_without_reopening_historical_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    historical_date = date(2026, 7, 20)
    prospective_date = date(2026, 7, 21)
    historical = _catalogs(historical_date)
    head = _catalogs(prospective_date)
    repository = tmp_path / "repo"
    repository.mkdir()
    artifact_root = tmp_path / "artifacts"
    summary_path = _write_availability_summary(artifact_root, historical, common_count=1)
    historical_root = tmp_path / "historical"
    head_root = tmp_path / "head"

    def first_loader(**kwargs: object) -> CatalogedBars:
        catalogs = historical if Path(kwargs["cache_root"]) == historical_root else head
        return catalogs[f"{kwargs['symbol']}/{kwargs['exchange']}/1m"]

    monkeypatch.setattr(
        observation,
        "load_verified_kis_paper_private_intraday_catalog",
        first_loader,
    )
    first = observation.run_kis_qqq_spy_mtf_prospective_attempt(
        availability_summary_path=summary_path,
        historical_cache_root=historical_root,
        head_cache_root=head_root,
        artifact_root=artifact_root,
        repo_root=repository,
        code_revision=_sha256("code-r1"),
        observed_at=_observed_after_cutoff(prospective_date),
    )

    def second_loader(**kwargs: object) -> CatalogedBars:
        assert Path(kwargs["cache_root"]) == head_root
        return head[f"{kwargs['symbol']}/{kwargs['exchange']}/1m"]

    monkeypatch.setattr(
        observation,
        "load_verified_kis_paper_private_intraday_catalog",
        second_loader,
    )
    second = observation.run_kis_qqq_spy_mtf_prospective_attempt(
        availability_summary_path=summary_path,
        historical_cache_root=historical_root,
        head_cache_root=head_root,
        artifact_root=artifact_root,
        repo_root=repository,
        code_revision=_sha256("code-r1"),
        observed_at=_observed_after_cutoff(prospective_date),
    )

    assert first is not None and first.outcome == "appended"
    assert second is not None and second.outcome == "duplicate"


def _contract(
    tmp_path: Path,
    historical_date: date,
) -> tuple[observation.KisQqqSpyMtfProspectiveContract, Path, Path]:
    repository = tmp_path / "repo"
    repository.mkdir()
    artifact_root = tmp_path / "artifacts"
    historical = _catalogs(historical_date)
    summary_path = _write_availability_summary(artifact_root, historical, common_count=1)
    return (
        observation.freeze_kis_qqq_spy_mtf_prospective_contract(
            availability_summary_path=summary_path,
            historical_catalogs=historical,
            code_revision=_sha256("code-r1"),
            repo_root=repository,
        ),
        repository,
        artifact_root,
    )


def _write_availability_summary(
    artifact_root: Path,
    catalogs: dict[str, CatalogedBars],
    *,
    common_count: int,
) -> Path:
    path = artifact_root / "availability-summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    targets = []
    for target_key in ("QQQ/NAS/1m", "SPY/AMS/1m"):
        catalog = catalogs[target_key]
        targets.append(
            {
                "source": {
                    "target_key": target_key,
                    "dataset_id": catalog.dataset_id,
                    "dataset_hash": catalog.dataset_hash,
                }
            }
        )
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "receipt_id": "kis-intraday-mtf-availability-receipt-v1",
                "precommit_sha256": _sha256("precommit-r1"),
                "receipt": {
                    "receipt_id": "kis-intraday-mtf-availability-receipt-v1",
                    "contract_sha256": _sha256("contract-r1"),
                    "receipt_sha256": _sha256("receipt-r1"),
                    "status": "qualified_for_prospective_input",
                    "reason": None,
                    "common_aligned_session_count": common_count,
                    "targets": targets,
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _catalogs(*session_dates: date) -> dict[str, CatalogedBars]:
    return {
        "QQQ/NAS/1m": _catalog("QQQ", "NAS", *session_dates),
        "SPY/AMS/1m": _catalog("SPY", "AMS", *session_dates),
    }


def _catalog(
    symbol: str,
    exchange: str,
    *session_dates: date,
    bars: tuple[Bar, ...] | None = None,
) -> CatalogedBars:
    return _cataloged_bars_from_verified_loader(
        dataset_id=f"kis.paper.private.intraday.{symbol.lower()}.{exchange.lower()}.m1.v1",
        dataset_hash=_sha256(f"{symbol}-{exchange}-dataset"),
        source_path=Path(f"D:/market_data/{symbol.lower()}-{exchange.lower()}.json"),
        bars=bars
        if bars is not None
        else tuple(bar for session_date in session_dates for bar in _bars(symbol, session_date)),
    )


def _bars(symbol: str, session_date: date) -> tuple[Bar, ...]:
    source_session = us_equity_2026_session(session_date)
    assert source_session is not None and source_session.kind == "regular"
    return tuple(
        Bar(
            symbol=symbol,
            market="US",
            timeframe=Timeframe.M1,
            start_ts=source_session.window.open_ts + timedelta(minutes=offset),
            open=Decimal("101.234") + Decimal(offset) / Decimal("10000"),
            high=Decimal("102.234") + Decimal(offset) / Decimal("10000"),
            low=Decimal("100.234") + Decimal(offset) / Decimal("10000"),
            close=Decimal("101.734") + Decimal(offset) / Decimal("10000"),
            volume=Decimal("99123"),
            complete=True,
        )
        for offset in range(observation.KIS_QQQ_SPY_MTF_PROSPECTIVE_PREFIX_MINUTES)
    )


def _observed_after_cutoff(session_date: date) -> datetime:
    source_session = us_equity_2026_session(session_date)
    assert source_session is not None and source_session.kind == "regular"
    return source_session.window.open_ts + timedelta(hours=6, minutes=31)


def _regular_dates_after(start: date, *, count: int) -> tuple[date, ...]:
    result: list[date] = []
    candidate = start + timedelta(days=1)
    while len(result) < count:
        source_session = us_equity_2026_session(candidate)
        if source_session is not None and source_session.kind == "regular":
            result.append(candidate)
        candidate += timedelta(days=1)
    return tuple(result)


def _sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _forbid(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("network access is forbidden")


class _DenyEnvironment(dict[str, str]):
    def get(self, *_args: object, **_kwargs: object) -> str:
        raise AssertionError("environment access is forbidden")
