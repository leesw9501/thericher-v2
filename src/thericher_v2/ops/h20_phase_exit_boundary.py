"""Original Dec1 operational closure prerequisite for the offline H20 reader."""

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from thericher_v2.execution.paper_peer_visit import _decode, _read, _record, _run, bank_key
from thericher_v2.ops.h20_phase_host import HARD_STOP, OPENS, _need, _strict_json

_ROOT = Path(
    "D:/thericher-v2/model-artifacts/execution/"
    "current-h20-next-session-deployment-preparation-20261031-v1/point-root-binding-r2"
)
_HOST = _ROOT / "a/graph/host"
_EXIT = _HOST / "out/exit"
_OBSERVER = _HOST / "observer-exit/owned-output"
_SOURCE = "c42867faeaa16211913c708ef83e5a110e80ff11f878b18d5a43da0f6c3708ad"
_RELEASE = "a4a7ceb1b6f06254567d1cd3c46dc6e1f1f83f0ca365a3926eae4c1a9a60983f"
_PLAN = "60c6b0a3687f566b0e4d8d326a2428e37e543129023227fe7e1786a4e7c14dac"
_CONTROL = "98a210e12939da6c771a639df20b1fafe43a3dff7e72138ee23a0b9d5bea7798"
_ROUND = "single-etf-H20-operational-once-20261102-v1"
TASK = "thericher-etf-h20-spy-owned-exit-20261201-v1"
_TRIGGER = OPENS.replace(minute=25)
_NATIVE = OPENS.replace(minute=30)
_RESTORE = OPENS.replace(minute=37)
_FINISH = OPENS.replace(minute=39)
_FILES = ("STARTED.json", "OWN-NATIVE-CLOSURE.json", "RESULT.json")


def _utc_now():
    return datetime.now(UTC)


def _pin(raw):
    return sha256(raw).hexdigest()


def _verify_static(snapshot):
    plan = snapshot(_HOST / "TASK-PLAN.json")
    control = snapshot(_HOST / "CONTROL.json")
    source = snapshot(_HOST / "SOURCE.json")
    release = snapshot(_ROOT / "p2/PARENT-TRUE.json")
    _need(
        (_pin(plan), _pin(control), _pin(source), _pin(release))
        == (_PLAN, _CONTROL, _SOURCE, _RELEASE)
    )
    control_data = _strict_json(control)
    window = control_data["windows"]["exit"]
    task_plan = _strict_json(plan)
    _need(task_plan["round_id"] == _ROUND and task_plan["phases"]["exit"]["name"] == TASK)
    _need(Path(window["output_root"]) == _EXIT)
    _need(Path(window["observer"]["output_root"]) == _OBSERVER)
    for name, stamp in [
        ("trigger", _TRIGGER),
        ("native_start", _NATIVE),
        ("restore", _RESTORE),
        ("hard", _FINISH),
    ]:
        _need(datetime.fromisoformat(window[name]) == stamp)
    return control_data


def _verify_restore(snapshot, closure):
    started = _OBSERVER / "RESTORE-STARTED.json"
    result = _OBSERVER / "RESTORE-RESULT.json"
    start, done = (_strict_json(snapshot(path)) for path in (started, result))
    pin = _pin(snapshot(closure))
    _need(
        start["task"] == "thericher-kis-paper-snapshot-observer"
        and Path(start["closure_path"]) == closure
        and start["closure_sha256"] == done["closure_ref_sha256"] == pin
        and start["Parent_attests_exact_runtime_owner_closure"] is True
        and start["independently_proven_by_helper"] is False
        and done["status"] == "ORIGINAL_ENABLED_RESTORED_EXACT"
        and done["restore_obligation"] is False
        and done["history_not_reset"] is True
        and done["financial_outcome"] == "UNKNOWN"
        and done["TaskRun_Kill_newTask"] == 0
        and done["before"]["enabled"] is False
        and done["before"]["instances"] == 0
        and type(done["after"]["enabled"]) is bool
    )
    return started, result


def _verify_native(snapshot, control, receipt, pid):
    key = bank_key(control["bank"])
    run = receipt["run"]
    _need(_run(run))
    expected = Path(control["gate_root"]) / ("bank-" + key) / ("CLOSED-" + run + ".json")
    ref = receipt["control_ref"]
    _need(type(ref) is dict and ref.keys() == {"path", "sha256"} and Path(ref["path"]) == expected)
    raw = snapshot(expected)
    _need(_pin(raw) == ref["sha256"])
    value = _decode(raw)
    _need(
        value["status"] == "CLOSED_OPERATIONAL_ONLY"
        and value["reservation_or_budget_release"] is False
        and value["same_native_intent_reconciliation_required"] is True
    )
    record = value["record"]
    _record(record, key)
    identity = record["identity"]
    visits = record["visits"]
    _need(
        (identity["source"], identity["release"], identity["run"]) == (_SOURCE, _RELEASE, run)
        and record["owner"]["pid"] == pid
        and receipt["native_visits"] == len(visits)
        and receipt["native_children"] == sum(len(row["children"]) for row in visits)
        and all(row["status"] == "CLOSED" for row in visits)
    )


def prove_h20_exit_read_boundary(*, owner_closed):
    """Join retained original operation evidence, never a broker effect.

    The protected caller independently attests exact installed source/task
    identity, current hidden instances and positive outer PID absence in
    owner_closed(task, pid). Original BankLeg closure is read only under
    its exact gate path; current writer absence remains transport admission.
    Missing or unstable evidence raises. No task exit code is used here.
    """
    observed = _utc_now()
    _need(OPENS <= observed < HARD_STOP)
    snapshots = {}

    def snapshot(path):
        value = _read(path)
        _need(snapshots.setdefault(path, value) == value)
        return value[0]

    control = _verify_static(snapshot)
    paths = tuple(_EXIT / name for name in _FILES)
    start, closed, result = (_strict_json(snapshot(path)) for path in paths)
    restore_paths = _verify_restore(snapshot, paths[1])

    def mtime(path):
        return datetime.fromtimestamp(snapshots[path][1][-1] / 1_000_000_000, UTC)

    _need(_TRIGGER <= mtime(paths[0]) < _NATIVE <= mtime(paths[1]) <= mtime(restore_paths[0]))
    _need(
        _RESTORE <= mtime(restore_paths[0]) <= mtime(restore_paths[1]) <= mtime(paths[2]) < _FINISH
    )
    for row in (start, closed, result):
        _need(type(row) is dict and (row["source"], row["release"]) == (_SOURCE, _RELEASE))
    pid = start["pid"]
    _need(
        start["phase"] == result["phase"] == "exit"
        and start["round_id"] == closed["round_id"] == _ROUND
        and start["no_financial_claim"] is True
        and type(pid) is int
        and 0 < pid < 2**32
        and closed["schema"] == "paired-owner-native-visits-closed-v1"
        and closed["native_visits_only"] is True
        and closed["root_controller_exited"] is False
        and closed["reservations_released"] is result["reservations_released"] is False
        and closed["financial_outcome"] == "UNKNOWN"
        and result["restore_obligation"] is False
        and result["status"] == "H20_FINITE_OPERATIONAL_RETURN_NOT_FILL_PROOF"
    )
    (receipt,) = closed["receipts"]
    _need(
        receipt["schema"] == "paired-native-closure-v1"
        and (receipt["source"], receipt["release"], receipt["round_id"], receipt["phase"])
        == (_SOURCE, _RELEASE, _ROUND, "exit")
        and receipt["financial_outcome"] == "UNKNOWN"
        and receipt["root_controller_exited"] is False
        and receipt["reservation_or_budget_release"] is False
    )
    _need(owner_closed(TASK, pid) is True)
    if receipt["status"] == "SOURCE_PROVEN_NO_NATIVE_STARTED":
        _need(
            receipt["run"] is receipt["control_ref"] is None
            and receipt["native_visits"] == receipt["native_children"] == 0
        )
    else:
        _need(
            receipt["status"] == "EXACT_NATIVE_VISITS_CLOSED"
            and type(receipt["native_visits"]) is int
            and receipt["native_visits"] >= 0
            and type(receipt["native_children"]) is int
            and receipt["native_children"] >= 0
        )
        _verify_native(snapshot, control, receipt, pid)
    _need(all(_read(path) == value for path, value in snapshots.items()))
    _need(observed <= _utc_now() < HARD_STOP and owner_closed(TASK, pid) is True)
    return True
