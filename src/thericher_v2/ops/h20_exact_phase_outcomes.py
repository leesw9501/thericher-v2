"""Phase-specific readout over the pinned H20 offline reader's exact native replay."""

import ast
import os
from hashlib import sha256
from pathlib import Path

from thericher_v2.execution.paper_peer_visit import _read

_READER = (
    Path(
        "D:/thericher-v2/model-artifacts/execution/"
        "current-h20-exact-outcome-reader-readiness-20261031-v1/runtime-r4/reader.py"
    )
    if os.name == "nt"
    else Path("/reader/reader.py")
)
_PIN = "4250965ffab28ecf0aebaa9f548201058bec02f50cec3718ef8862ab5c55b46f"
_SCHEMA = "H20_EXACT_OFFLINE_PHASE_OUTCOMES_V1"


def _unknown_phase(plan="UNKNOWN"):
    return dict(
        plan=plan, attempt="UNKNOWN", acceptance="UNKNOWN", fill="UNKNOWN", terminal="UNKNOWN"
    )


def _result(reason, stage):
    return dict(
        schema=_SCHEMA,
        reason=reason,
        stage=stage,
        entry=_unknown_phase(),
        exit=_unknown_phase(),
        current_owned_inventory="UNKNOWN",
        inventory_scope="EXACT_NATIVE_H20_LOT_LEDGER_NOT_BROKER_HOLDINGS",
        broker_holdings="NOT_READ",
        fees_settlement_netPnL="NOT_OBSERVED",
        net_PnL="UNKNOWN",
        reservation_released=False,
        raw_exception_retained=False,
    )


def _outcome(state, proof, terminal):
    fill = state.cumulative_fill
    if fill is None:
        category = "NOT_RECORDED"
    elif fill.quantity == 0:
        category = "ZERO"
    elif fill.quantity == state.intent.quantity:
        category = "FULL"
    else:
        if not 0 < fill.quantity < state.intent.quantity:
            raise ValueError("FILL_LINK_INVALID")
        category = "PARTIAL"
    return dict(
        plan="LINKED",
        attempt="RECORDED" if state.submission_started_at is not None else "NOT_RECORDED",
        acceptance="ACKNOWLEDGED"
        if state.submit_response_category == "acknowledged_order_reference"
        and state.broker_order_id is not None
        else "UNKNOWN",
        fill=category,
        terminal="YES" if terminal(state, proof) else "UNKNOWN",
    )


def _phases(chosen, terminal):
    if [phase for _, _, phase in chosen] not in (["entry"], ["entry", "exit"]):
        raise ValueError("STATE_BINDING_INVALID")
    entry, proof, _ = chosen[0]
    if entry.intent.side != "buy":
        raise ValueError("STATE_BINDING_INVALID")
    result = _result("OK", "COMPLETE")
    result["entry"] = _outcome(entry, proof, terminal)
    result["exit"] = _unknown_phase("NO_LINKED_PLAN")
    entry_fill = entry.cumulative_fill
    sold = 0
    if len(chosen) == 2:
        exit_state, exit_proof, _ = chosen[1]
        if exit_state.intent.side != "sell":
            raise ValueError("STATE_BINDING_INVALID")
        if not terminal(entry, proof) or entry.current_fill is None:
            raise ValueError("entry_outcome_unknown")
        if exit_state.intent.quantity > entry.current_fill.quantity:
            raise ValueError("owned_entry_quantity_changed")
        result["exit"] = _outcome(exit_state, exit_proof, terminal)
        if exit_state.cumulative_fill is not None:
            sold = exit_state.cumulative_fill.quantity
    if entry_fill is not None and entry_fill.quantity > 0 and entry.current_fill is not None:
        remaining = entry_fill.quantity - sold
        if remaining < 0:
            raise ValueError("FILL_LINK_INVALID")
        result["current_owned_inventory"] = "POSITIVE" if remaining > 0 else "FLAT"
    return result


def _load(raw):
    if sha256(raw).hexdigest() != _PIN:
        raise ValueError("SOURCE_BINDING_INVALID")
    tree = ast.parse(raw, filename="h20_pinned_reader.py")
    (project,) = (
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "project"
    )
    block = project.body[-1]
    # Keep original control/bank/seed/replay/fill links and error handling.
    # Replace only the entry-only projection and refuse an orphan exit control.
    first = next(
        i
        for i, node in enumerate(block.body)
        if isinstance(node, ast.Assign)
        and ast.unparse(node.targets[0]) == "(state, proof, _)"
        and ast.unparse(node.value) == "chosen[0]"
    )
    block.body[first:] = ast.parse(
        """
stage = "OWNED"
leg._lot_interference(binding, contract)
if len(chosen) == 1:
    path = leg._control_path(root, contract, "exit")
    leg._ordinary(path)
    need(not path.exists(), "CONTROL_BINDING_INVALID")
return _phase_projection(chosen, budget._terminal)
"""
    ).body
    namespace = {"__name__": "_h20_pinned_phase_projection", "_phase_projection": _phases}
    exec(compile(ast.fix_missing_locations(tree), "h20_pinned_reader.py", "exec"), namespace)
    return namespace


def read_h20_phase_outcomes(root, contract, as_of, *, source_check, inventory, unchanged, admit):
    """Requires the qualified read-only host; never run a broker or recovery client."""
    try:
        original = _read(_READER)
        native = _load(original[0])

        def retained_source():
            if _read(_READER) != original:
                raise ValueError("SOURCE_UNSTABLE")
            return source_check()

        value = native["read_exact"](
            root,
            contract,
            as_of,
            source_check=retained_source,
            inventory=inventory,
            unchanged=unchanged,
            admit=admit,
        )
        if value["schema"] == _SCHEMA:
            return value
        return _result(value["reason"], value["stage"])
    except Exception:
        return _result("SOURCE_BINDING_INVALID", "SOURCE")
