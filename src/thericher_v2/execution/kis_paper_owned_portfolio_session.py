"""One bounded current-input visit to the existing native Paper cycle.

The caller owns transport, calendar and process lifetime. No credentials,
replacement intent, cash envelope, scheduler or model selection lives here.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from thericher_v2.contracts import require_utc
from thericher_v2.research.cross_asset_etf_input import CrossAssetSession

from . import kis_paper_budget_strategy as budget
from .kis_paper_portfolio_control_input import (
    KisPaperPortfolioControlInputBinding,
    load_kis_paper_portfolio_control_input,
)
from .kis_paper_portfolio_cycle import advance_kis_paper_portfolio_cycle
from .kis_paper_portfolio_preview import project_kis_paper_portfolio_preview
from .kis_paper_portfolio_session_input import (
    KisPaperPortfolioSessionInputError,
    freeze_or_load_kis_paper_portfolio_session_input,
)


def visit_kis_paper_owned_portfolio_session(
    *,
    state_root: Path,
    repository_root: Path,
    artifact_root: Path,
    market_root: Path,
    runtime_projection_path: Path,
    paper_account_snapshot_path: Path,
    emergency_state_path: Path,
    execution_control_path: Path,
    client,
    proposed_input: KisPaperPortfolioControlInputBinding,
    calendar_sessions: tuple[CrossAssetSession, ...],
    expected_calendar_sha256: str,
    session: CrossAssetSession,
    session_id: str,
    engineering_control: Callable,
    engineering_helper_sha256: str,
    reads_factory: Callable,
    states_factory: Callable,
    clock: Callable[[], datetime],
    execute: bool = False,
) -> dict:
    """Preview is read-only; execution freezes input and custody before intents.

    A retained checkpoint wins over every proposed refresh. Outside the exact
    regular session an execution visit invokes neither cycle nor broker reads.
    An explicitly requested read-only preview may observe closed-market inputs;
    stale quotes are evidence, never an order. Unknown requests remain owned by
    their exact native recovery path.
    """
    if type(execute) is not bool:
        raise ValueError("session_execute_invalid")
    now = require_utc(clock())
    if execute and not session.open_at <= now < session.close_at:
        return dict(status="not_due", reason="outside_owned_regular_session", new_submits=0)
    config = client._config
    account = budget._digest([config.base_url, config.account_number, config.account_product_code])
    binding = budget._load_binding(state_root, account)
    if binding is None or binding["version"] not in {3, 4} or binding["legacy_spy"] is not None:
        raise ValueError("session_custody_unavailable")
    owners = {owner.owner_ref: ref for owner, ref in budget._owners(binding)}
    basis = binding["basis_ref"]
    custody = dict(
        expected_account_ref=account,
        expected_basis_ref=basis,
        expected_owner_refs=owners,
        expected_binding_ref="sha256:" + budget._digest(binding),
    )
    completed = tuple(s for s in calendar_sessions if s.close_at <= now)[-253:]
    choice = None
    if execute:
        try:
            choice = freeze_or_load_kis_paper_portfolio_session_input(
                state_root=state_root,
                session_id=session_id,
                **custody,
                input_binding=None,
                expected_sessions=None,
                engineering_helper_sha256=None,
                frozen_at=now,
            )
        except KisPaperPortfolioSessionInputError as error:
            if error.reason_code != "session_input_missing":
                raise
    requested = choice.binding if choice is not None else proposed_input
    selected = choice.sessions if choice is not None else completed
    helper_pin = choice.helper_sha256 if choice is not None else engineering_helper_sha256
    calendar_pin = (
        choice.expected_calendar_sha256 if choice is not None else expected_calendar_sha256
    )
    loaded = load_kis_paper_portfolio_control_input(
        binding=requested,
        artifact_root=artifact_root,
        market_root=market_root,
        expected_sessions=selected,
        decision_at=now,
        engineering_control=engineering_control,
        engineering_helper_sha256=helper_pin,
        expected_calendar_sha256=calendar_pin,
    )
    if execute and choice is None:
        if not loaded.reattest():
            raise ValueError("session_input_changed")
        choice = freeze_or_load_kis_paper_portfolio_session_input(
            state_root=state_root,
            session_id=session_id,
            **custody,
            input_binding=proposed_input,
            expected_sessions=completed,
            engineering_helper_sha256=engineering_helper_sha256,
            frozen_at=now,
            expected_calendar_sha256=expected_calendar_sha256,
        )
        # A racing first writer can win; never use the discarded proposed input.
        loaded = load_kis_paper_portfolio_control_input(
            binding=choice.binding,
            artifact_root=artifact_root,
            market_root=market_root,
            expected_sessions=choice.sessions,
            decision_at=now,
            engineering_control=engineering_control,
            engineering_helper_sha256=choice.helper_sha256,
            expected_calendar_sha256=choice.expected_calendar_sha256,
        )

    def reads():
        if not loaded.reattest():
            raise ValueError("session_input_changed")
        return reads_factory()

    if not execute:
        fresh = reads()
        result = project_kis_paper_portfolio_preview(
            binding=binding,
            states=states_factory(binding),
            expected_account_ref=account,
            expected_basis_ref=basis,
            expected_owner_refs=owners,
            reads=fresh,
            weights_by_symbol=loaded.weights_by_symbol,
            covariance_by_symbol=loaded.covariance_by_symbol,
            target_as_of=loaded.target_as_of,
            as_of=require_utc(clock()),
        )
        if not loaded.reattest():
            raise ValueError("session_input_changed")
        return result.safe_payload() | dict(input=loaded.safe_payload(), read_only=True)
    if not loaded.reattest():
        raise ValueError("session_input_changed")
    result = advance_kis_paper_portfolio_cycle(
        state_root=state_root,
        repository_root=repository_root,
        artifact_root=artifact_root,
        runtime_projection_path=runtime_projection_path,
        paper_account_snapshot_path=paper_account_snapshot_path,
        emergency_state_path=emergency_state_path,
        execution_control_path=execution_control_path,
        expected_account_ref=choice.account_ref,
        expected_basis_ref=choice.basis_ref,
        expected_owner_refs=choice.owner_refs,
        expected_binding_ref=choice.binding_ref,
        session_id=choice.session_id,
        input_ref=loaded.input_ref,
        control_ref=loaded.control_ref,
        weights_by_symbol=loaded.weights_by_symbol,
        covariance_by_symbol=loaded.covariance_by_symbol,
        target_as_of=loaded.target_as_of,
        reads_factory=reads,
        client=client,
        clock=clock,
        execute=True,
    )
    return result.safe_payload() | dict(
        input=loaded.safe_payload(), checkpoint=choice.safe_payload(), read_only=False
    )
