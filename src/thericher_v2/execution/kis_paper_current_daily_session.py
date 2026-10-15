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
    value = dict(version=2, context=context, cycle_ref=None,
                 completed=False, terminal_state="active")
    return value | {"ref": "sha256:" + budget._digest(value)}


def _validate(value, paths, account):
    keys = {"version", "context", "cycle_ref", "completed", "ref"}
    _check(type(value) is dict and type(value.get("version")) is int)
    _check((value["version"], set(value)) in ((1, keys), (2, keys | {"terminal_state"})))
    _check(type(value["completed"]) is bool)
    if value["version"] == 2:
        _check(value["terminal_state"] in {"active", "complete", "incomplete"}
               and value["completed"] == (value["terminal_state"] == "complete")
               and (value["terminal_state"] == "active" or value["cycle_ref"] is not None))
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


def _preintent_contract(context):
    native = _native(context)
    return dict(
        session_id=native["session_id"], account_ref=context["expected_account_ref"],
        basis_ref=context["expected_basis_ref"], owner_refs=context["expected_owner_refs"],
        binding_ref=context["expected_binding_ref"], input_ref=native["input_ref"],
        control_ref=native["control_ref"], target_as_of=native["target_as_of"].isoformat(),
        weights={s: str(native["weights_by_symbol"][s]) for s in cycle.SYMBOLS},
        covariance={
            s: {t: str(native["covariance_by_symbol"][s][t]) for t in cycle.SYMBOLS}
            for s in cycle.SYMBOLS
        },
    )


def _preintent_request_runs(context):
    contract_ref = budget._digest(_preintent_contract(context))
    account, basis = context["expected_account_ref"], context["expected_basis_ref"]
    requests, runs = set(), set()
    for side in ("buy", "sell"):
        request = "portfolio-" + side + "-" + contract_ref
        requests.add(request)
        for symbol in cycle.SYMBOLS:
            identity = [account, basis, request, symbol]
            if side == "sell":
                identity.extend([side, "portfolio-" + symbol.lower()])
            runs.add("bp-" + budget._digest(identity))
    return requests, runs


def _refresh_preintent_context(record, *, root, pointer, paths, account, clock):
    """Refresh only starting custody when no native request could have begun.

    Caller retains daily ownership. Any existing native checkpoint keeps its
    original context and exact recovery; shared-book writes remain native-only.
    """
    if record["completed"] or record["cycle_ref"] is not None:
        return record
    _validate(record, paths, account)
    context = record["context"]
    key = budget._digest([account, context["expected_basis_ref"], context["native"]["session_id"]])
    directory = root / ".portfolio_cycles" / key
    for path in (directory, directory / ".advance", directory / "..advance.lock"):
        execution._unlinked(path)
    with canary.exclusive_kis_paper_canary_state_lock(directory / ".advance"):
        with cycle._shared(root):
            _check(budget._read_json(pointer) == record)
            entries = tuple(directory.iterdir())
            for path in entries:
                execution._unlinked(path)
            # Checkpoint-before-reservation is the native ordering contract.
            if any(path.name != "..advance.lock" for path in entries):
                return record
            binding = budget._load_binding(root, account)
            _check(binding is not None and binding["version"] in {3, 4}
                   and binding["legacy_spy"] is None
                   and binding["basis_ref"] == context["expected_basis_ref"])
            owner_refs = {o.owner_ref: pin for o, pin in budget._owners(binding)}
            current_ref = "sha256:" + budget._digest(binding)
            if (context["expected_binding_ref"] == current_ref
                    and context["expected_owner_refs"] == owner_refs):
                return record
            at = require_utc(clock())
            _check(datetime.fromisoformat(context["available_at"]) < at
                   < datetime.fromisoformat(context["valid_until"]))
            proposal = _record(dict(context, expected_owner_refs=owner_refs,
                                    expected_binding_ref=current_ref))
            _validate(proposal, paths, account)
            old_requests, old_runs = _preintent_request_runs(context)
            new_requests, new_runs = _preintent_request_runs(proposal["context"])
            requests, runs = old_requests | new_requests, old_runs | new_runs
            plans = list(binding["portfolio"]["plans"])
            if binding["version"] == 4:
                plans.extend(p for stock in binding["stocks"].values() for p in stock["plans"])
            _check(not any(p["request_id"] in requests for p in plans))
            states, replayed, proofs, _ = cycle._project(root, binding, at)
            _check(not runs.intersection(states))
            for run in runs:
                path = root / (run + ".json")
                execution._unlinked(path)
                _check(not path.exists())
            _check(all(budget._terminal(state, proofs.get(run))
                       and run in binding["terminal_evidence"]
                       for run, state in replayed.items()))
            _check(budget._read_json(pointer) == record
                   and budget._load_binding(root, account) == binding)
            final_at = require_utc(clock())
            _check(datetime.fromisoformat(context["available_at"]) < final_at
                   < datetime.fromisoformat(context["valid_until"]))
            budget._atomic_json(pointer, proposal)
            _check(budget._read_json(pointer) == proposal)
            return proposal


def _incomplete_path(root, record):
    context = record["context"]
    return root / ".portfolio_cycles" / budget._digest([
        context["expected_account_ref"], context["expected_basis_ref"],
        context["native"]["session_id"],
    ]) / "terminal-incomplete.json"


def _incomplete_custody(root, record, account, at):
    context = record["context"]
    binding = budget._load_binding(root, account)
    _check(binding is not None and binding["version"] in {3, 4}
           and binding["legacy_spy"] is None
           and binding["basis_ref"] == context["expected_basis_ref"])
    directory = _incomplete_path(root, record).parent
    for name in ("cycle.json", "buy.json"):
        execution._unlinked(directory / name)
    retained = budget._read_json(directory / "cycle.json")
    _check(type(retained) is dict
           and set(retained) == {"contract", "initial", "sell", "targets", "ref"}
           and retained["contract"] == _preintent_contract(context)
           and retained["ref"] == record["cycle_ref"]
           == "sha256:" + budget._digest({k: v for k, v in retained.items() if k != "ref"})
           and "sha256:" + budget._digest(retained["initial"])
           == context["expected_binding_ref"])
    stages = (retained["sell"], budget._read_json(directory / "buy.json"))
    states, replayed, proofs, projection = cycle._project(root, binding, at)
    _check(projection.reserved_buys == 0 and all(
        run in binding["terminal_evidence"] and budget._terminal(state, proofs.get(run))
        for run, state in replayed.items()
    ))
    current_seeds = budget._portfolio_seed_states(binding)
    runs = set()
    for side, stage in zip(("sell", "buy"), stages, strict=True):
        if stage is None:
            continue
        _check(type(stage) is dict and set(stage) == {"parent", "proposed", "ref"}
               and stage["ref"] == "sha256:" + budget._digest(
                   {k: v for k, v in stage.items() if k != "ref"}))
        plan = stage["proposed"]["portfolio"]["plans"][-1]
        _check(plan in binding["portfolio"]["plans"]
               and plan["request_id"] == "portfolio-" + side + "-"
               + budget._digest(retained["contract"])
               and plan["parent_binding_ref"] == "sha256:" + budget._digest(stage["parent"]))
        seeds = budget._portfolio_seed_states(stage["proposed"])
        for run in plan["states"]:
            _check(run not in runs and run in states
                   and seeds[run].intent == current_seeds[run].intent == states[run].intent
                   and states[run].intent.side == side)
            runs.add(run)
    _check(runs and any(replayed[run].cumulative_fill is None
                       or replayed[run].cumulative_fill.quantity != states[run].intent.quantity
                       for run in runs))
    return binding, projection


def _incomplete_archive(root, pointer, record, paths, account, clock, *, create=False):
    if record["cycle_ref"] is None or record["completed"]:
        return None
    path = _incomplete_path(root, record)
    for item in (path, path.parent / ".advance", path.parent / "..advance.lock"):
        execution._unlinked(item)
    archived = budget._read_json(path)
    if archived is None and not create:
        return None
    value = dict(version=1, classification="terminal_incomplete", record=record)
    value["ref"] = "sha256:" + budget._digest(value)
    _check(archived is None or archived == value)
    _validate(record, paths, account)
    with canary.exclusive_kis_paper_canary_state_lock(path.parent / ".advance"):
        with cycle._shared(root):
            _check(budget._read_json(pointer) == record)
            if archived is None:
                for name in ("cycle.json", "buy.json"):
                    execution._unlinked(path.parent / name)
                retained = budget._read_json(path.parent / "cycle.json")
                buy = budget._read_json(path.parent / "buy.json")
                _check(type(retained) is dict)
                cycle._prefix(root, retained["initial"], (retained["sell"], buy),
                              require_utc(clock()))
            _incomplete_custody(root, record, account, require_utc(clock()))
            cycle._record(path, value)
    return value


def _rollover_incomplete(root, pointer, record, proposal, paths, account, client, clock):
    path = _incomplete_path(root, record)
    for item in (path, path.parent / "..advance.lock"):
        execution._unlinked(item)
    with canary.exclusive_kis_paper_canary_state_lock(path.parent / ".advance"):
        with cycle._shared(root):
            _validate(record, paths, account)
            _validate(proposal, paths, account)
            _check(budget._read_json(pointer) == record)
            archived = budget._read_json(path)
            _check(type(archived) is dict
                   and set(archived) == {"version", "classification", "record", "ref"}
                   and type(archived["version"]) is int and archived["version"] == 1
                   and archived["record"] == record
                   and archived["classification"] == "terminal_incomplete"
                   and archived["ref"] == "sha256:" + budget._digest(
                       {k: v for k, v in archived.items() if k != "ref"}))
            binding, projection = _incomplete_custody(root, record, account, require_utc(clock()))
            context = proposal["context"]
            old = record["context"]
            _check(record.get("terminal_state") == "incomplete"
                   and context["native"]["session_id"] != old["native"]["session_id"]
                   and context["native"]["input_ref"] != old["native"]["input_ref"]
                   and datetime.fromisoformat(context["native"]["target_as_of"]).date()
                   > datetime.fromisoformat(old["native"]["target_as_of"]).date()
                   and datetime.fromisoformat(context["valid_until"]).date()
                   > datetime.fromisoformat(old["valid_until"]).date())
            _check(context["expected_basis_ref"] == binding["basis_ref"]
                   and context["expected_binding_ref"] == "sha256:" + budget._digest(binding)
                   and context["expected_owner_refs"]
                   == {o.owner_ref: ref for o, ref in budget._owners(binding)})
            requests, runs = _preintent_request_runs(context)
            _check(not any(p["request_id"] in requests for p in binding["portfolio"]["plans"]))
            _check(not runs.intersection(budget._seed_states(binding)))
            for run in runs:
                journal = root / (run + ".json")
                for item in (journal, journal.with_name("." + journal.name + ".lock")):
                    execution._unlinked(item)
                    _check(not item.exists())
            directory = _incomplete_path(root, proposal).parent
            execution._unlinked(directory)
            if directory.exists():
                for item in directory.iterdir():
                    execution._unlinked(item)
                    _check(item.name == "..advance.lock")
            snapshot = client.snapshot()
            execution._book(snapshot, projection, client._config, require_utc(clock()))
            at = require_utc(clock())
            _check(datetime.fromisoformat(context["available_at"]) < at
                   < datetime.fromisoformat(context["valid_until"])
                   and budget._read_json(pointer) == record
                   and budget._load_binding(root, account) == binding)
            budget._atomic_json(pointer, proposal)
            _check(budget._read_json(pointer) == proposal)


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
            archived = None
            if record is not None:
                _validate(record, paths, account)
                if record.get("terminal_state") == "incomplete":
                    archived = _incomplete_archive(
                        root, pointer, record, paths, account, clock, create=True,
                    )
                    if (require_utc(clock()).date()
                            <= datetime.fromisoformat(record["context"]["valid_until"]).date()):
                        return CurrentDailySessionOutcome("no_intent", "terminal_cycle_incomplete")
                record = _refresh_preintent_context(
                    record, root=root, pointer=pointer, paths=paths, account=account, clock=clock,
                )
            if record is None or record["completed"] or archived is not None:
                try:
                    _check(callable(data_loader))
                    control = build_current_daily_control(data_loader(), as_of=require_utc(clock()))
                    _check(type(control) is CurrentDailyControl)
                except Exception:
                    return CurrentDailySessionOutcome("no_intent", "current_input_unavailable")
                native = control.native_arguments()
                if record is not None:
                    old = record["context"]["native"]
                    if archived is not None and (
                        native["session_id"] == old["session_id"]
                        or native["input_ref"] == old["input_ref"]
                        or control.target_as_of.date()
                        <= datetime.fromisoformat(old["target_as_of"]).date()
                    ):
                        return CurrentDailySessionOutcome("no_intent", "terminal_cycle_incomplete")
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
                proposal = _record(dict(
                    paths=paths, expected_account_ref=account,
                    expected_basis_ref=binding["basis_ref"],
                    expected_owner_refs={o.owner_ref: ref for o, ref in budget._owners(binding)},
                    expected_binding_ref="sha256:" + budget._digest(binding), native=packed,
                    available_at=control.available_at.isoformat(),
                    valid_until=control.valid_until.isoformat(),
                ))
                _validate(proposal, paths, account)
                if archived is not None:
                    _rollover_incomplete(
                        root, pointer, record, proposal, paths, account, client, clock,
                    )
                else:
                    budget._atomic_json(pointer, proposal)
                record = proposal
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
            _check(result.status in {"pending", "complete", "unavailable", "terminal_incomplete"})
            if result.cycle_ref is not None:
                _check(budget._SHA.fullmatch(result.cycle_ref))
                _check(record["cycle_ref"] is None or record["cycle_ref"] == result.cycle_ref)
                record["cycle_ref"] = result.cycle_ref
            record["completed"] = result.status == "complete"
            if record["version"] == 2 or result.status == "terminal_incomplete":
                record["version"] = 2
                record["terminal_state"] = {
                    "complete": "complete", "terminal_incomplete": "incomplete",
                }.get(result.status, "active")
            record["ref"] = "sha256:" + budget._digest({
                k: v for k, v in record.items() if k != "ref"
            })
            _validate(record, paths, account)
            budget._atomic_json(pointer, record)
            _check(budget._read_json(pointer) == record)
            if result.status == "terminal_incomplete":
                _incomplete_archive(root, pointer, record, paths, account, clock, create=True)
                return CurrentDailySessionOutcome("no_intent", "terminal_cycle_incomplete")
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
