"""Host-side result boundary for the new H20 phase read-only transport."""

import ast
import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from thericher_v2.execution.paper_peer_visit import _read
from thericher_v2.ops.h20_exact_phase_outcomes import (
    _GROSS_SIGNS,
    _READER,
    _load,
    _result,
    _unknown_phase,
)

OPENS = datetime(2026, 12, 1, 14, 41, tzinfo=UTC)
LAST_START = datetime(2026, 12, 1, 14, 43, tzinfo=UTC)
HARD_STOP = datetime(2026, 12, 1, 14, 46, tzinfo=UTC)
_PUBLIC = Path(
    "D:/thericher-v2/model-artifacts/execution/"
    "current-h20-reader-parent-activation-20261101-v1/read_outcome.py"
)
_PUBLIC_PIN = "e4e4c96af7a4d013054a23e5063189c79a070f1abf8dca8b5f5d13ee1f51fa83"
_TARGETS = {
    "/contract.json": "bind",
    "/h20-sdk": "bind",
    "/h20-source": "bind",
    "/legacy": "bind",
    "/reader": "bind",
    "/app/private": "volume",
}
_CHOICES = {
    "plan": {"UNKNOWN", "LINKED", "NO_LINKED_PLAN"},
    "attempt": {"UNKNOWN", "RECORDED", "NOT_RECORDED"},
    "acceptance": {"UNKNOWN", "ACKNOWLEDGED"},
    "fill": {"UNKNOWN", "NOT_RECORDED", "ZERO", "PARTIAL", "FULL"},
    "terminal": {"UNKNOWN", "YES"},
}


def _need(ok):
    if not ok:
        raise ValueError("H20_PHASE_HOST_UNQUALIFIED")


def _check_result(value, *, reasons, stages):
    reference = _result("OK", "COMPLETE")
    _need(type(value) is dict and value.keys() == reference.keys())
    for key, allowed in (
        ("reason", reasons),
        ("stage", stages),
        ("current_owned_inventory", {"UNKNOWN", "POSITIVE", "FLAT"}),
        ("gross_PnL_sign", _GROSS_SIGNS),
    ):
        _need(type(value[key]) is str and value[key] in allowed)
    for key in reference.keys() - {
        "reason",
        "stage",
        "entry",
        "exit",
        "current_owned_inventory",
        "gross_PnL_sign",
    }:
        _need(type(value[key]) is type(reference[key]) and value[key] == reference[key])
    for phase in ("entry", "exit"):
        row = value[phase]
        _need(type(row) is dict and row.keys() == _CHOICES.keys())
        _need(all(type(row[k]) is str and row[k] in choices for k, choices in _CHOICES.items()))
        if row["plan"] != "LINKED":
            _need(row == _unknown_phase(row["plan"]))
        elif row["fill"] in {"ZERO", "PARTIAL", "FULL"} or row["acceptance"] == "ACKNOWLEDGED":
            _need(row["attempt"] == "RECORDED")
    if value["reason"] != "OK":
        _need(value["entry"] == value["exit"] == _unknown_phase())
        _need(value["stage"] != "COMPLETE" and value["current_owned_inventory"] == "UNKNOWN")
        _need(value["gross_PnL_sign"] == "UNKNOWN")
    else:
        _need(value["stage"] == "COMPLETE" and value["entry"]["plan"] == "LINKED")
        _need(value["exit"]["plan"] in {"LINKED", "NO_LINKED_PLAN"})
        if value["exit"]["plan"] == "LINKED":
            _need(value["entry"]["terminal"] == "YES")
        if value["current_owned_inventory"] == "FLAT":
            _need(
                value["exit"]["plan"] == "LINKED" and value["exit"]["fill"] in {"PARTIAL", "FULL"}
            )
        if value["current_owned_inventory"] != "UNKNOWN":
            _need(value["entry"]["fill"] in {"PARTIAL", "FULL"})
        if value["gross_PnL_sign"] != "UNKNOWN":
            _need(
                value["current_owned_inventory"] == "FLAT"
                and value["entry"]["terminal"] == value["exit"]["terminal"] == "YES"
            )
    return value


def _strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _need(key not in result)
            result[key] = value
        return result

    def nonfinite(_):
        _need(False)

    return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)


def _parse(raw, native):
    _need(type(raw) is bytes and 0 < len(raw) <= 8192)
    return _check_result(_strict_json(raw), reasons=native["REASONS"], stages=native["STAGES"])


def invoke_h20_phase_window(
    *,
    at,
    source_sha256,
    image,
    mounts,
    transport,
    admission_ready,
):
    """Run the exact phase guest through the independently bound native transport.

    The caller owns protected source pins, append-only attempt acquisition and
    the scoped native configure/closure. This adapter never starts a Scheduler
    task, selects data mounts, or treats guest success as native closure.
    """
    _need(type(at) is datetime and at.utcoffset() is not None and OPENS <= at < LAST_START)
    _need(
        type(source_sha256) is str
        and len(source_sha256) == 64
        and all(c in "0123456789abcdef" for c in source_sha256)
        and type(image) is str
        and image.startswith("sha256:")
        and len(image) == 71
        and all(c in "0123456789abcdef" for c in image[7:])
        and type(mounts) is list
        and len(mounts) == len(_TARGETS)
        and callable(transport)
        and callable(admission_ready)
    )
    _need(
        all(
            type(row) is dict
            and set(row) == {"target", "source", "type", "readonly"}
            and row["readonly"] is True
            and row["type"] == _TARGETS.get(row["target"])
            and type(row["source"]) is str
            and row["source"]
            and not any(c in row["source"] for c in ",\r\n\0")
            for row in mounts
        )
        and {row["target"] for row in mounts} == _TARGETS.keys()
    )
    native = _load(_read(_READER)[0])
    _need(admission_ready() is True)
    return transport(
        image,
        mounts,
        ["-I", "-S", "-B", "/reader/guest.py", "--source-sha256", source_sha256, "--read"],
        lambda raw: _parse(raw, native),
    )


def _validated_phase_projection(value, before, observed):
    when = datetime.fromisoformat(observed)
    _need(when.utcoffset() is not None and OPENS <= when < HARD_STOP)
    native = _load(_read(_READER)[0])
    checked = _check_result(value, reasons=native["REASONS"], stages=native["STAGES"])
    return dict(
        status="VALIDATED_CURRENT_RETAINED_PHASE_STATE",
        evidence=before,
        observed_utc=observed,
        OS_scheduler_origin="NOT_CRYPTOGRAPHICALLY_PROVEN",
        **checked,
    )


def read_h20_phase_envelope(run, source_pin, binding, coordinator_pin, *, published_result_pin):
    """Verify the independent publication pin and original native links.

    The caller must retain the exact result digest outside the result directory
    under the protected native publication profile. Never derive it from the
    result at read time.
    """
    original = _read(_PUBLIC)
    _need(sha256(original[0]).hexdigest() == _PUBLIC_PIN)
    tree = ast.parse(original[0], filename="h20_pinned_public_reader.py")
    helpers = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in {"need", "same", "validate"}
    ]
    (validate,) = (node for node in helpers if node.name == "validate")
    first = next(
        i
        for i, node in enumerate(validate.body)
        if isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) == "value"
    )
    validate.body[first:] = ast.parse(
        """
need(pointer(run / "RESULT.json") == before)
return phase_projection(result["result"], before, result["observed_utc"])
"""
    ).body
    snapshots = {}

    def snapshot(path):
        current = _read(path)
        _need(snapshots.setdefault(path, current) == current)
        return current[0]

    def pointer(path):
        raw = snapshot(path)
        return {"path": str(path), "bytes": len(raw), "sha256": sha256(raw).hexdigest()}

    supplied = {
        "Path": Path,
        "pointer": pointer,
        "read": lambda path: _strict_json(snapshot(path)),
        "PHASES": ["before_create", "before_start", "before_read", "after_read", "after_remove"],
        "phase_projection": _validated_phase_projection,
    }
    exec(
        compile(ast.fix_missing_locations(ast.Module(helpers, [])), "h20_public_reader.py", "exec"),
        supplied,
    )
    result = supplied["validate"](run, source_pin, binding, coordinator_pin)
    _need(
        supplied["pointer"](run / "RESULT.json") == result["evidence"]
        and result["evidence"]["sha256"] == published_result_pin
        and _read(_PUBLIC) == original
        and all(_read(path) == snapshot for path, snapshot in snapshots.items())
    )
    return result
