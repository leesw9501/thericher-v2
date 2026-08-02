from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import thericher_v2.execution.kis_paper_prospective_spy_session as session_module
import thericher_v2.models.prospective_spy_intraday_observation as observation_module
from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_prospective_spy_capture import (
    KIS_PAPER_PROSPECTIVE_SPY_CAPTURE_ARTIFACT_DIR,
)
from thericher_v2.execution.kis_paper_prospective_spy_session import (
    run_kis_paper_prospective_spy_session,
)
from thericher_v2.execution.kis_paper_quote import KisPaperSpyLimitInput
from thericher_v2.execution.kis_readonly import (
    KisPaperAccountIdentity,
    KisPaperCashSnapshot,
    KisPaperOpenOrdersSnapshot,
    KisPaperOrderableFundsSnapshot,
    KisPaperReadOnlySnapshot,
)
from thericher_v2.market.resample import SessionWindow
from thericher_v2.models.prospective_spy_intraday_observation import (
    ProspectiveSpyIntradayObservationReceipt,
    observe_prospective_spy_intraday_baseline,
)
from thericher_v2.models.prospective_spy_intraday_session import (
    build_prospective_spy_intraday_session_record,
)

_SESSION_DATE = date(2026, 8, 3)
_SESSION = SessionWindow(
    open_ts=datetime(2026, 8, 3, 13, 30, tzinfo=UTC),
    close_ts=datetime(2026, 8, 3, 20, 0, tzinfo=UTC),
)
_CUTOFF = datetime(2026, 8, 3, 19, 30, tzinfo=UTC)
_SOURCE_CONTRACT_HASH = "sha256:" + "c" * 64


def test_current_enter_receipt_reaches_only_the_existing_kis_paper_canary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact_root, repository_root = _roots(tmp_path)
    observation = _write_receipt(artifact_root, _receipt())
    client = _FlatSpyClient(captured_at=observation.decided_at)
    calls: dict[str, object] = {}

    def run_canary(prepared, **kwargs):
        calls["submit_permitted"] = (
            kwargs["submit_permitted"](observation.decided_at),
            kwargs["submit_permitted"](observation.valid_until + timedelta(microseconds=1)),
        )
        return SimpleNamespace(
            run_id="receipt-" + prepared.receipt_ref.removeprefix("sha256:"),
            reason_code="cancelled",
            safe_payload=lambda: {
                "kind": "kis_paper_canary_outcome",
                "phase": "cancelled",
                "paper_only": True,
            },
        )

    monkeypatch.setattr(session_module, "run_kis_paper_receipt_canary", run_canary)
    outcome = run_kis_paper_prospective_spy_session(
        environment=_NoCredentialEnvironment(),
        artifact_root=artifact_root,
        repository_root=repository_root,
        execute=True,
        cancel_after_submit=True,
        client=client,  # type: ignore[arg-type]
        now=observation.decided_at,
        **_paths(tmp_path),
    )

    assert outcome.status == "canary_completed"
    assert outcome.reason_code == "cancelled"
    assert client.calls == ["snapshot", "limit_input"]
    assert calls["submit_permitted"] == (True, False)
    payload = json.loads(outcome.evidence_path.read_text(encoding="ascii"))
    assert payload["route"] == "kis_paper"
    assert payload["paper_only"] is True
    assert payload["canary"]["phase"] == "cancelled"
    rendered = outcome.evidence_path.read_text(encoding="ascii")
    for forbidden in ("500.25", "111.111", "7777", "local_paper", str(artifact_root)):
        assert forbidden not in rendered


def test_missing_receipt_never_constructs_a_kis_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact_root, repository_root = _roots(tmp_path)
    _deny_kis_config(monkeypatch)

    outcome = run_kis_paper_prospective_spy_session(
        environment=_NoCredentialEnvironment(),
        artifact_root=artifact_root,
        repository_root=repository_root,
        execute=True,
        cancel_after_submit=True,
        now=_CUTOFF,
        **_paths(tmp_path),
    )

    assert outcome.status == "no_intent"
    assert outcome.reason_code == "receipt_unavailable"
    assert outcome.research_receipt is None
    assert outcome.canary is None


def test_stale_or_abstaining_receipt_never_constructs_a_kis_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact_root, repository_root = _roots(tmp_path)
    stale = _write_receipt(artifact_root, _receipt())
    _deny_kis_config(monkeypatch)

    stale_outcome = run_kis_paper_prospective_spy_session(
        environment=_NoCredentialEnvironment(),
        artifact_root=artifact_root,
        repository_root=repository_root,
        execute=True,
        cancel_after_submit=True,
        now=stale.valid_until + timedelta(microseconds=1),
        session_id="stale-receipt",
        **_paths(tmp_path),
    )
    assert stale_outcome.status == "no_intent"
    assert stale_outcome.reason_code == "receipt_not_current"

    abstaining = _write_receipt(artifact_root, _receipt(upward=False))
    abstain_outcome = run_kis_paper_prospective_spy_session(
        environment=_NoCredentialEnvironment(),
        artifact_root=artifact_root,
        repository_root=repository_root,
        execute=True,
        cancel_after_submit=True,
        now=abstaining.decided_at,
        session_id="abstaining-receipt",
        **_paths(tmp_path),
    )
    assert abstain_outcome.status == "no_intent"
    assert abstain_outcome.reason_code == "receipt_abstain"


def test_malformed_receipt_never_reads_credentials_or_creates_an_intent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact_root, repository_root = _roots(tmp_path)
    destination = (
        artifact_root
        / KIS_PAPER_PROSPECTIVE_SPY_CAPTURE_ARTIFACT_DIR
        / _SESSION_DATE.isoformat()
        / "receipt.json"
    )
    destination.parent.mkdir(parents=True)
    destination.write_text("{}\n", encoding="ascii")
    _deny_kis_config(monkeypatch)

    outcome = run_kis_paper_prospective_spy_session(
        environment=_NoCredentialEnvironment(),
        artifact_root=artifact_root,
        repository_root=repository_root,
        execute=True,
        cancel_after_submit=True,
        now=_CUTOFF,
        **_paths(tmp_path),
    )

    assert outcome.status == "no_intent"
    assert outcome.reason_code == "receipt_unavailable"
    assert outcome.research_receipt is None
    assert outcome.canary is None


def test_rehashed_extended_ttl_receipt_never_constructs_a_kis_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact_root, repository_root = _roots(tmp_path)
    receipt = _write_receipt(artifact_root, _receipt())
    destination = (
        artifact_root
        / KIS_PAPER_PROSPECTIVE_SPY_CAPTURE_ARTIFACT_DIR
        / _SESSION_DATE.isoformat()
        / "receipt.json"
    )
    payload = receipt.to_payload()
    payload["valid_until"] = (receipt.valid_until + timedelta(minutes=1)).isoformat().replace(
        "+00:00", "Z"
    )
    payload["receipt_id"] = observation_module._receipt_id(
        {key: value for key, value in payload.items() if key != "receipt_id"}
    )
    destination.write_text(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _deny_kis_config(monkeypatch)

    outcome = run_kis_paper_prospective_spy_session(
        environment=_NoCredentialEnvironment(),
        artifact_root=artifact_root,
        repository_root=repository_root,
        execute=True,
        cancel_after_submit=True,
        now=_CUTOFF,
        **_paths(tmp_path),
    )

    assert outcome.status == "no_intent"
    assert outcome.reason_code == "receipt_unavailable"
    assert outcome.research_receipt is None
    assert outcome.canary is None


@pytest.mark.parametrize("upward", [True, False])
def test_ineligible_receipts_never_touch_an_injected_paper_client(
    tmp_path: Path,
    upward: bool,
) -> None:
    artifact_root, repository_root = _roots(tmp_path)
    receipt = _write_receipt(artifact_root, _receipt(upward=upward))
    client = _NoAccessClient()
    now = receipt.valid_until + timedelta(microseconds=1) if upward else receipt.decided_at

    outcome = run_kis_paper_prospective_spy_session(
        environment=_NoCredentialEnvironment(),
        artifact_root=artifact_root,
        repository_root=repository_root,
        execute=True,
        cancel_after_submit=True,
        client=client,  # type: ignore[arg-type]
        now=now,
        session_id=f"ineligible-{'stale' if upward else 'abstain'}",
        **_paths(tmp_path),
    )

    assert outcome.status == "no_intent"
    assert outcome.reason_code == ("receipt_not_current" if upward else "receipt_abstain")
    assert client.calls == []


def test_changed_receipt_content_cannot_reuse_a_preview_input_or_decision_binding(
    tmp_path: Path,
) -> None:
    artifact_root, repository_root = _roots(tmp_path)
    first = _write_receipt(artifact_root, _receipt())
    first_outcome = run_kis_paper_prospective_spy_session(
        environment=_NoCredentialEnvironment(),
        artifact_root=artifact_root,
        repository_root=repository_root,
        execute=False,
        cancel_after_submit=True,
        now=first.decided_at,
        session_id="first-preview",
        **_paths(tmp_path),
    )
    changed = _write_receipt(artifact_root, _receipt(changed_last_bar=True))
    changed_outcome = run_kis_paper_prospective_spy_session(
        environment=_NoCredentialEnvironment(),
        artifact_root=artifact_root,
        repository_root=repository_root,
        execute=False,
        cancel_after_submit=True,
        now=changed.decided_at,
        session_id="changed-preview",
        **_paths(tmp_path),
    )

    assert first_outcome.status == changed_outcome.status == "preview"
    assert first_outcome.research_receipt is not None
    assert changed_outcome.research_receipt is not None
    assert (
        first_outcome.research_receipt.input_manifest_ref
        != changed_outcome.research_receipt.input_manifest_ref
    )
    assert (
        first_outcome.research_receipt.decision_id
        != changed_outcome.research_receipt.decision_id
    )


def test_preview_rejects_a_nested_artifact_symlink_before_writing_evidence(
    tmp_path: Path,
) -> None:
    artifact_root, repository_root = _roots(tmp_path)
    observation = _write_receipt(artifact_root, _receipt())
    execution_directory = artifact_root / "execution"
    try:
        execution_directory.symlink_to(repository_root, target_is_directory=True)
    except OSError:
        pytest.skip("creating a directory symlink is unavailable on this Windows host")

    with pytest.raises(ValueError, match="evidence path"):
        run_kis_paper_prospective_spy_session(
            environment=_NoCredentialEnvironment(),
            artifact_root=artifact_root,
            repository_root=repository_root,
            execute=False,
            cancel_after_submit=True,
            now=observation.decided_at,
            session_id="symlink-preview",
            **_paths(tmp_path),
        )

    assert not tuple(repository_root.rglob("evidence.json"))


def test_session_id_cannot_be_a_path_component(tmp_path: Path) -> None:
    artifact_root, repository_root = _roots(tmp_path)

    with pytest.raises(ValueError, match="session id"):
        run_kis_paper_prospective_spy_session(
            environment=_NoCredentialEnvironment(),
            artifact_root=artifact_root,
            repository_root=repository_root,
            execute=False,
            cancel_after_submit=True,
            now=_CUTOFF,
            session_id=".",
            **_paths(tmp_path),
        )


class _NoCredentialEnvironment(dict[str, str]):
    def __getitem__(self, key: str) -> str:
        raise AssertionError(f"receipt rejection must not read {key}")

    def get(self, key: str, default=None):
        raise AssertionError(f"receipt rejection must not read {key}")


class _FlatSpyClient:
    def __init__(self, *, captured_at: datetime) -> None:
        self.calls: list[str] = []
        self.limit_input = KisPaperSpyLimitInput(
            last=Decimal("500.25"),
            decimal_places=2,
            tick_size=Decimal("0.01"),
            quoted_at=captured_at,
        )
        self.snapshot_value = KisPaperReadOnlySnapshot(
            identity=KisPaperAccountIdentity("****5678-**", captured_at),
            cash=KisPaperCashSnapshot("USD", Decimal("1000"), captured_at),
            orderable_funds=KisPaperOrderableFundsSnapshot(
                "USD",
                Decimal("1000"),
                "AMEX",
                "SPY",
                Decimal("1"),
                captured_at,
            ),
            positions=(),
            open_orders=KisPaperOpenOrdersSnapshot((), captured_at),
            captured_at=captured_at,
        )

    def snapshot(self) -> KisPaperReadOnlySnapshot:
        self.calls.append("snapshot")
        return self.snapshot_value

    def fetch_spy_limit_input(self, *, observed_at: datetime) -> KisPaperSpyLimitInput:
        self.calls.append("limit_input")
        assert observed_at == self.limit_input.quoted_at
        return self.limit_input


class _NoAccessClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def snapshot(self) -> KisPaperReadOnlySnapshot:
        self.calls.append("snapshot")
        raise AssertionError("ineligible receipt must not read the Paper account")

    def fetch_spy_limit_input(self, *, observed_at: datetime) -> KisPaperSpyLimitInput:
        self.calls.append("limit_input")
        raise AssertionError("ineligible receipt must not read a Paper quote")


def _deny_kis_config(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("ineligible receipt must not load Paper configuration")

    monkeypatch.setattr(session_module, "load_kis_paper_config_from_environment", fail)


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    artifact_root.mkdir()
    repository_root.mkdir()
    return artifact_root, repository_root


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "state_root": tmp_path / "private",
        "runtime_projection_path": tmp_path / "runtime" / "projection.json",
        "paper_account_snapshot_path": tmp_path / "runtime" / "account.json",
        "emergency_state_path": tmp_path / "emergency" / "state.json",
        "execution_control_path": tmp_path / "emergency" / "control.json",
    }


def _write_receipt(
    artifact_root: Path,
    receipt: ProspectiveSpyIntradayObservationReceipt,
) -> ProspectiveSpyIntradayObservationReceipt:
    destination = (
        artifact_root
        / KIS_PAPER_PROSPECTIVE_SPY_CAPTURE_ARTIFACT_DIR
        / _SESSION_DATE.isoformat()
        / "receipt.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(receipt.canonical_json() + "\n", encoding="utf-8")
    return receipt


def _receipt(
    *,
    upward: bool = True,
    changed_last_bar: bool = False,
) -> ProspectiveSpyIntradayObservationReceipt:
    bars = list(_source_bars(upward=upward))
    if changed_last_bar:
        bars[-1] = replace(
            bars[-1],
            open=bars[-1].open + Decimal("0.001"),
            high=bars[-1].high + Decimal("0.001"),
            low=bars[-1].low + Decimal("0.001"),
            close=bars[-1].close + Decimal("0.001"),
        )
    record = build_prospective_spy_intraday_session_record(
        tuple(bars),
        session=_SESSION,
        cutoff=_CUTOFF,
        source_contract_hash=_SOURCE_CONTRACT_HASH,
    )
    return observe_prospective_spy_intraday_baseline(record).receipt


def _source_bars(*, upward: bool) -> tuple[Bar, ...]:
    count = (_CUTOFF - _SESSION.open_ts) // Timeframe.M1.duration
    return tuple(_bar_at(index, upward=upward) for index in range(count))


def _bar_at(index: int, *, upward: bool) -> Bar:
    movement = Decimal(index) / Decimal("1000")
    open_value = Decimal("111.111") + movement if upward else Decimal("222.222") - movement
    return Bar(
        symbol="SPY",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=_SESSION.open_ts + Timeframe.M1.duration * index,
        open=open_value,
        high=open_value + Decimal("1"),
        low=open_value - Decimal("0.5"),
        close=open_value + Decimal("0.2"),
        volume=Decimal("7777"),
        complete=True,
    )
