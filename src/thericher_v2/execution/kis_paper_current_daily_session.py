"""One repeatable owned daily portfolio pointer; native cycles own all effects."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from thericher_v2.contracts import require_utc
from thericher_v2.research.kis_paper_current_daily_control import (
    CurrentDailyControl,
    build_current_daily_control,
)

from . import kis_paper_budget_strategy as budget
from . import kis_paper_canary as canary
from . import kis_paper_portfolio_cycle as cycle
from . import kis_paper_portfolio_execute as execution
from .kis_paper_session import is_us_equity_regular_session_window
from .kis_readonly import KIS_PAPER_BASE_URL, KisPaperConfig, KisPaperReadOnlyError

POINTER = ".current_daily_portfolio.json"
_NATIVE_KEYS = frozenset((
    "session_id", "input_ref", "control_ref", "weights_by_symbol",
    "covariance_by_symbol", "target_as_of",
))
_READONLY_REASONS = {
    "transport_failure": "readonly_transport_failure",
    "response_invalid": "readonly_response_invalid",
    "open_orders_rejected": "readonly_open_orders_rejected",
    "open_orders_response_incomplete": "readonly_open_orders_response_incomplete",
    "open_orders_response_duplicate": "readonly_open_orders_response_duplicate",
    "open_orders_pagination_incomplete": "readonly_open_orders_pagination_incomplete",
    "balance_response_incomplete": "readonly_balance_response_incomplete",
    "orderable_funds_response_incomplete": "readonly_orderable_funds_response_incomplete",
    "ccnl_response_incomplete": "readonly_ccnl_response_incomplete",
}
_CANARY_REASONS = {
    "transport_failure": "canary_transport_failure",
    "auth_rejected": "canary_auth_rejected",
    "auth_response_invalid": "canary_auth_response_invalid",
    "access_token_invalid": "canary_access_token_invalid",
    "token_request_not_due": "canary_token_request_not_due",
    "request_budget_exhausted": "canary_request_budget_exhausted",
}
_CYCLE_REASONS = {
    "cycle_custody_mismatch": "cycle_custody_mismatch",
    "portfolio_pending_identity": "portfolio_pending_identity",
    "cycle_checkpoint_conflict": "cycle_checkpoint_conflict",
    "cycle_checkpoint_invalid": "cycle_checkpoint_invalid",
    "cycle_book_missing": "cycle_book_missing",
    "cycle_book_changed": "cycle_book_changed",
    "cycle_terminal_unproven": "cycle_terminal_unproven",
    "cycle_target_unreached": "cycle_target_unreached",
}


def _failure_reason(error):
    # Only typed local codes or one exact cycle literal may cross this boundary.
    try:
        if isinstance(error, KisPaperReadOnlyError):
            code, reasons = error.code, _READONLY_REASONS
        elif isinstance(error, canary.KisPaperCanaryError):
            code, reasons = error.code, _CANARY_REASONS
        elif isinstance(error, cycle._RecoveryRequired):
            args = error.args
            if type(args) is not tuple or len(args) != 1:
                return None
            code, reasons = args[0], _CYCLE_REASONS
        else:
            return None
        return reasons.get(code) if type(code) is str else None
    except Exception:
        return None


@dataclass(frozen=True, repr=False)
class CurrentDailySessionOutcome:
    status: str
    reason: str

    def safe_payload(self):
        return dict(kind="kis_paper_current_daily_session_v1", status=self.status,
                    reason=self.reason, limitation="cycle_status_not_current_inventory_or_net_pnl")


def _check(ok):
    if not ok:
        raise ValueError("daily_session_context_invalid")


def _account(client):
    _check(isinstance(client, canary.KisPaperCanaryClient))
    config = client._config
    _check(type(config) is KisPaperConfig and config.base_url == KIS_PAPER_BASE_URL)
    replace(config)
    return budget._digest([config.base_url, config.account_number, config.account_product_code])


class _WindowClient(canary.KisPaperCanaryClient):
    """Same client/token/intent, with a submit-only native final-clock check."""

    def __init__(self, client, context, clock):
        self._delegate = client
        self._context = context
        self._clock = clock

    @property
    def _config(self):
        return self._delegate._config

    def snapshot(self):
        return self._delegate.snapshot()

    def reconcile(self, state, *, now):
        return self._delegate.reconcile(state, now=now)

    def cancel_order(self, intent, *, broker_order_id):
        return self._delegate.cancel_order(intent, broker_order_id=broker_order_id)

    def orderable_funds_at_limit(self, *, symbol, exchange, limit_price):
        return self._delegate.orderable_funds_at_limit(
            symbol=symbol, exchange=exchange, limit_price=limit_price,
        )

    def submit_limit(self, intent, *, now=None, clock=None):
        caller_clock = self._clock if clock is None else clock

        def checked_clock():
            # Preserve the native risk callback at its own final wire boundary.
            at = require_utc(caller_clock())
            context = self._context
            if (_account(self._delegate) != context["expected_account_ref"]
                    or not datetime.fromisoformat(context["available_at"]) < at
                    < datetime.fromisoformat(context["valid_until"])
                    or not is_us_equity_regular_session_window(at)):
                raise canary.KisPaperCanaryError("intent_expired")
            return at

        return self._delegate.submit_limit(intent, now=now, clock=checked_clock)


def _native(context):
    args = dict(context["native"])
    _check(set(args) == _NATIVE_KEYS)
    _check(type(args["session_id"]) is str
           and budget._QQQ_ENTRY_REQUEST_ID.fullmatch(args["session_id"]))
    _check(all(type(args[k]) is str and budget._SHA.fullmatch(args[k])
               for k in ("input_ref", "control_ref")))
    args["target_as_of"] = require_utc(datetime.fromisoformat(args["target_as_of"]))
    args["weights_by_symbol"] = {s: Decimal(v) for s, v in args["weights_by_symbol"].items()}
    args["covariance_by_symbol"] = {
        s: {t: Decimal(v) for t, v in row.items()}
        for s, row in args["covariance_by_symbol"].items()
    }
    _check(set(args["weights_by_symbol"]) == set(cycle.SYMBOLS))
    _check(all(v.is_finite() and 0 <= v <= 1 for v in args["weights_by_symbol"].values()))
    cycle._covariance(args["covariance_by_symbol"])
    available = require_utc(datetime.fromisoformat(context["available_at"]))
    until = require_utc(datetime.fromisoformat(context["valid_until"]))
    _check(args["target_as_of"] < available < until)
    return args


def _record(context):
    value = dict(version=1, context=context, cycle_ref=None, completed=False)
    return value | {"ref": "sha256:" + budget._digest(value)}


def _validate(value, paths, account):
    _check(type(value) is dict
           and set(value) == {"version", "context", "cycle_ref", "completed", "ref"})
    _check(value["version"] == 1 and type(value["completed"]) is bool)
    _check(value["ref"] == "sha256:"
           + budget._digest({k: v for k, v in value.items() if k != "ref"}))
    context = value["context"]
    _check(type(context) is dict and set(context) == {
        "paths", "expected_account_ref", "expected_basis_ref", "expected_owner_refs",
        "expected_binding_ref", "native", "available_at", "valid_until",
    })
    _check(context["paths"] == paths and context["expected_account_ref"] == account)
    _check(all(type(context[k]) is str and budget._SHA.fullmatch(context[k])
               for k in ("expected_basis_ref", "expected_binding_ref")))
    _check(type(context["expected_owner_refs"]) is dict
           and all(type(k) is str and type(v) is str and budget._SHA.fullmatch(v)
                   for k, v in context["expected_owner_refs"].items()))
    ref = value["cycle_ref"]
    _check(ref is None or type(ref) is str and budget._SHA.fullmatch(ref))
    _check(not value["completed"] or ref is not None)
    return _native(context)


def run_kis_paper_current_daily_session(
    *, state_root: Path, repository_root: Path, artifact_root: Path,
    runtime_projection_path: Path, paper_account_snapshot_path: Path,
    emergency_state_path: Path, execution_control_path: Path,
    client=None, data_loader: Callable | None = None, reads_factory: Callable | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC), execute: bool = False,
) -> CurrentDailySessionOutcome:
    """One native visit. Unfinished context wins before Data; no expiry rollover.

    An expired unfilled cycle remains retained for exact native recovery, not
    declared complete/released. Caller owns bounded transport, scheduling and
    actual request/fill claims. No credentials, client or baseline is selected.
    """
    if execute is False:
        return CurrentDailySessionOutcome("inert", "execution_not_requested")
    pointer = None
    try:
        _check(type(execute) is bool and callable(clock) and callable(reads_factory))
        account = _account(client)
        root = Path(state_root).resolve()
        paths = dict(state_root=str(root), repository_root=str(Path(repository_root).resolve()),
                     artifact_root=str(Path(artifact_root).resolve()),
                     runtime_projection_path=str(Path(runtime_projection_path).resolve()),
                     paper_account_snapshot_path=str(Path(paper_account_snapshot_path).resolve()),
                     emergency_state_path=str(Path(emergency_state_path).resolve()),
                     execution_control_path=str(Path(execution_control_path).resolve()))
        for path in (Path(state_root), *map(Path, paths.values())):
            execution._unlinked(path)
        budget._validate_paths(root, Path(repository_root), Path(artifact_root),
                               *map(Path, (paths[k] for k in (
                                   "runtime_projection_path", "paper_account_snapshot_path",
                                   "emergency_state_path", "execution_control_path",
                               ))))
        pointer = root / POINTER
        lock = root / ".current_daily_portfolio_worker"
        for path in (pointer, lock.with_name("." + lock.name + ".lock")):
            execution._unlinked(path)
        with canary.exclusive_kis_paper_canary_state_lock(lock):
            record = budget._read_json(pointer)
            if record is not None:
                _validate(record, paths, account)
            if record is None or record["completed"]:
                try:
                    _check(callable(data_loader))
                    control = build_current_daily_control(data_loader(), as_of=require_utc(clock()))
                    _check(type(control) is CurrentDailyControl)
                except Exception:
                    return CurrentDailySessionOutcome("no_intent", "current_input_unavailable")
                native = control.native_arguments()
                if record is not None:
                    old = record["context"]["native"]
                    if all(native[k] == old[k] for k in ("session_id", "input_ref", "control_ref")):
                        return CurrentDailySessionOutcome("complete", "already_completed")
                    _check(control.target_as_of >= datetime.fromisoformat(old["target_as_of"]))
                binding = budget._load_binding(root, account)
                _check(binding is not None and binding["version"] in {3, 4})
                if record is not None:
                    _check(binding["basis_ref"] == record["context"]["expected_basis_ref"])
                budget.project_budget(root, binding, as_of=require_utc(clock()))
                packed = dict(native)
                packed["target_as_of"] = native["target_as_of"].isoformat()
                packed["weights_by_symbol"] = {
                    s: str(v) for s, v in native["weights_by_symbol"].items()
                }
                packed["covariance_by_symbol"] = {
                    s: {t: str(v) for t, v in row.items()}
                    for s, row in native["covariance_by_symbol"].items()
                }
                record = _record(dict(
                    paths=paths, expected_account_ref=account,
                    expected_basis_ref=binding["basis_ref"],
                    expected_owner_refs={o.owner_ref: ref for o, ref in budget._owners(binding)},
                    expected_binding_ref="sha256:" + budget._digest(binding), native=packed,
                    available_at=control.available_at.isoformat(),
                    valid_until=control.valid_until.isoformat(),
                ))
                _validate(record, paths, account)
                budget._atomic_json(pointer, record)
                _check(budget._read_json(pointer) == record)
            native = _validate(record, paths, account)
            context = record["context"]
            result = cycle.advance_kis_paper_portfolio_cycle(
                **{k: Path(v) for k, v in paths.items()}, **native,
                **{k: context[k] for k in (
                    "expected_account_ref", "expected_basis_ref", "expected_owner_refs",
                    "expected_binding_ref",
                )}, reads_factory=reads_factory, clock=clock, execute=True,
                client=_WindowClient(client, context, clock),
                expected_cycle_ref=record["cycle_ref"],
            )
            _check(type(result) is cycle.KisPaperPortfolioCycleOutcome)
            _check(result.status in {"pending", "complete", "unavailable"})
            if result.cycle_ref is not None:
                _check(budget._SHA.fullmatch(result.cycle_ref))
                _check(record["cycle_ref"] is None or record["cycle_ref"] == result.cycle_ref)
                record["cycle_ref"] = result.cycle_ref
            record["completed"] = result.status == "complete"
            record["ref"] = "sha256:" + budget._digest({
                k: v for k, v in record.items() if k != "ref"
            })
            _validate(record, paths, account)
            budget._atomic_json(pointer, record)
            _check(budget._read_json(pointer) == record)
            return CurrentDailySessionOutcome(result.status, {
                "pending": "exact_cycle_advanced", "complete": "exact_cycle_complete",
                "unavailable": "native_recovery_required",
            }[result.status])
    except Exception as error:
        reason = _failure_reason(error)
        if reason is None:
            reason = ("retained_context_recovery_required" if pointer is not None
                      else "session_configuration_invalid")
        return CurrentDailySessionOutcome("unavailable", reason)
