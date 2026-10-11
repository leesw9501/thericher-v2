"""Pure Goal93R2 metadata custody, not acquisition, inference or Paper authority.

``verify_shadow_link(claim_bytes, *, controls, read_metadata, observed_at)``
returns immutable hashes/clocks. ``expected_engine_links()`` supplies Engine's
15-field restore map; pass separately obtained, hash-checked result bytes to
Engine. The callback accepts an exact native metadata path and byte ceiling.
Packed/model bytes are never requested. Hash-linked declarations and reported
cleanup/source audits do not prove raw rows, OS isolation, PIT or finality.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath, PureWindowsPath

_PIN = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
_ID = re.compile(r"[0-9a-f]{32}", re.ASCII)
_KIND = "kis_shadow512_prior21_v1"
_GOAL = "kis-stock-five-session-prospective512-shadow-delivery-v1"
_A = "D:/thericher-v2/model-artifacts"
_DATA = f"{_A}/data/{_GOAL}"
_ROOT = f"{_A}/research/{_GOAL}/delivery-r2"
_CACHE = (
    "D:/market_data/us_equities/kis_paper_private/stock-five-session-shadow512/v1/shadow-20261019"
)
_START = "2026-10-16T21:15:00+00:00"
_DATA_END = "2026-10-16T21:35:00+00:00"
_END = "2026-10-16T21:45:00+00:00"
_RESULT_FIELDS = frozenset(
    "added_eligible availability broker_calls calendar26_sha256 calendar_validation "
    "complete_prior21_count completed_at data_source_count decision elapsed_seconds eligible_count "
    "exposure_units fit_calls frame_sha256 identity_count inference_calls inference_completed_at "
    "input_captured_at input_manifest_sha256 input_metadata_sha256 input_plan_sha256 "
    "model_dump_retained order_consumer original_eligible phase physical_capture_sha256 "
    "plan_sha256 raw_rows_retained reason scores_retained shadow_only source_count "
    "source_pins_sha256 source_chunks_sha256 sources_reattested status supported "
    "worker_sha256 worker_started_at".split()
)
_WORKER_FIELDS = frozenset(
    "status plan_sha256 runtime_contract_sha256 raw_stdout_retained "
    "materialization_completed_at_utc manifest_sha256 packed_sha256 target_count calendar_count "
    "grid_count record_count full_targets sparse_targets empty_targets supported eligible_count "
    "frame_sha256 availability qualification elapsed_seconds cursor_sha256 position daily_attempts "
    "accepted_pages categories next_due delegate_starts minimum_delegate_gap_seconds "
    "first_page_needed_rows first_page_floor_targets second_incremental_needed_rows "
    "orphan_recoveries lost_pending_attempts final_source_audit_passed".split()
)
_ENGINE_LINKS = tuple(
    "plan_sha256 worker_sha256 source_pins_sha256 input_plan_sha256 input_manifest_sha256 "
    "input_metadata_sha256 physical_capture_sha256 source_chunks_sha256 calendar26_sha256 "
    "source_count data_source_count input_captured_at".split()
)


class ShadowLinkError(ValueError):
    """Static scoped category; never includes callback errors or metadata values."""


def _require(ok: bool, category: str) -> None:
    if not ok:
        raise ShadowLinkError(category)


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _pin(value: object) -> str:
    _require(type(value) is str and bool(_PIN.fullmatch(value)), "pin_invalid")
    return value


def _pairs(items: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in items:
        _require(key not in value, "duplicate_json_key")
        value[key] = item
    return value


def _document(raw: bytes, wanted: str | None = None, cap: int = 4 * 1024**2) -> dict:
    _require(type(raw) is bytes and 0 < len(raw) <= cap, "metadata_size")
    if wanted is not None:
        _require(_sha(raw) == _pin(wanted), "metadata_hash")
    value = json.loads(
        raw,
        object_pairs_hook=_pairs,
        parse_constant=lambda _: _require(False, "nonfinite_json"),
    )
    _require(type(value) is dict, "metadata_object")
    _canonical(value)
    return value


def _fields(value: object, names: str | frozenset[str]) -> dict:
    names = frozenset(names.split()) if type(names) is str else names
    _require(type(value) is dict and set(value) == names, "metadata_fields")
    return value


def _clock(value: object) -> datetime:
    _require(type(value) is str, "clock_invalid")
    at = datetime.fromisoformat(value)
    _require(at.utcoffset() == timedelta(0), "clock_invalid")
    return at


def _path(value: object) -> str:
    _require(type(value) is str and 0 < len(value) <= 1024, "path_invalid")
    path = PureWindowsPath(value)
    _require(
        path.is_absolute()
        and path.drive.lower() in {"c:", "d:"}
        and ".." not in path.parts
        and not any(":" in part for part in path.parts[1:]),
        "path_invalid",
    )
    return str(path)


def _join(root: str, *parts: str) -> str:
    return _path(str(PureWindowsPath(root).joinpath(*parts)))


def _same(a: object, b: object) -> bool:
    return PureWindowsPath(_path(a)) == PureWindowsPath(_path(b))


def _pins(value: object) -> dict:
    _require(type(value) is dict and bool(value), "source_pins_invalid")
    result = {}
    for path, wanted in value.items():
        key = _path(path).casefold()
        _require(key not in result, "duplicate_source_identity")
        result[key] = _pin(wanted)
    return result


def _count(value: object, maximum: int = 10752) -> int:
    _require(type(value) is int and 0 <= value <= maximum, "count_invalid")
    return value


def _seconds(value: object, maximum: int) -> float:
    _require(
        type(value) in (int, float) and math.isfinite(value) and 0 <= value <= maximum,
        "elapsed_invalid",
    )
    return float(value)


@dataclass(frozen=True, slots=True, repr=False)
class ShadowControls:
    job_bytes: bytes
    data_plan_bytes: bytes
    engine_template_bytes: bytes
    job_sha: str = "sha256:e8550670d5b18a9bbf81600cb9d399e591e73300e95d9bbf996de5f73837be0a"
    data_plan_sha: str = "sha256:37b8ba01b35b6f165d680b0c629adaceef604e4f68a5529c8b676bbf57fc4085"
    engine_template_sha: str = (
        "sha256:b1d314ac8d6c817a392825b49a153a73ded99b57533ed5adb10f49961bf23715"
    )
    expected_delivery_root: str = _ROOT


@dataclass(frozen=True, slots=True)
class MetadataLink:
    path: str
    sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class VerifiedShadowLink:
    invocation_id: str
    engine_result_sha: str
    engine_plan_sha: str
    input_manifest_ref: MetadataLink
    packed_sha: str
    job_sha: str
    data_plan_sha: str
    source_pins_sha: str
    calendar_sha: str
    actual_clocks: tuple[tuple[str, str], ...]
    metadata_links: tuple[MetadataLink, ...]
    engine_links: tuple[tuple[str, object], ...]

    def expected_engine_links(self) -> dict[str, object]:
        """A fresh exact 15-field map; Engine receives raw result separately."""
        return dict(self.engine_links)


def _validate_controls(controls):
    _require(type(controls) is ShadowControls, "controls_invalid")
    root = _path(controls.expected_delivery_root)
    _require(
        any(_same(root, f"{_A}/research/{_GOAL}/delivery-{version}") for version in ("r2", "r3")),
        "delivery_root_invalid",
    )
    job = _document(controls.job_bytes, controls.job_sha)
    data = _document(controls.data_plan_bytes, controls.data_plan_sha)
    template = _document(controls.engine_template_bytes, controls.engine_template_sha)
    _require(
        job["kind"] == "prospective512_shadow_delivery_job_v1"
        and job["company_objective"] == _GOAL
        and _same(job["root"], root)
        and job["start_utc"] == _START
        and job["end_utc"] == _END
        and type(job["broker_calls"]) is int
        and job["broker_calls"] == 0
        and job["private_bank_access"] is False
        and job["existing_opportunities_changed"] is False,
        "job_scope",
    )
    source = _pins(job["source_pins"])
    _require(
        source.get(_join(_DATA, "plan.json").casefold()) == controls.data_plan_sha
        and _same(job["engine"]["template_path"], _join(root, "engine-template.json"))
        and source.get(_path(job["engine"]["template_path"]).casefold())
        == controls.engine_template_sha
        and data["kind"] == _KIND
        and _same(data["cache_root"], _CACHE)
        and data["anchor"] == "20261016"
        and data["opportunity"] == {"not_before_utc": _START, "end_utc": _DATA_END},
        "control_binding",
    )
    metadata = data["metadata"]
    declared_data = (
        {**_pins(data["source_pins"]), **_pins(data["reference_inputs"])}
        if data["reference_inputs"]
        else _pins(data["source_pins"])
    )
    aliases = template["data_source_paths"]
    normalized_aliases = {_path(host).casefold(): alias for host, alias in aliases.items()}
    _require(
        len(normalized_aliases) == len(aliases) and set(normalized_aliases) == set(declared_data),
        "data_source_binding",
    )
    for host, wanted in declared_data.items():
        alias = normalized_aliases[host]
        _require(
            template["pins"].get(alias) == wanted
            and source.get(_path(template["host_paths"][alias]).casefold()) == wanted,
            "data_source_binding",
        )
    keys = metadata["keys"]
    _require(
        type(keys) is list
        and len(keys) == len(set(keys)) == 512
        and metadata["original_target_keys"] == keys[:128]
        and len(metadata["scheduled_dates"]) == 21
        and metadata["scheduled_dates"][0] == "2026-09-18"
        and metadata["scheduled_dates"][-1] == "2026-10-16",
        "identity_calendar_binding",
    )
    _pin(metadata["calendar26_sha256"])
    _require(
        template["input_plan_sha256"] == controls.data_plan_sha
        and template["input_metadata_sha256"] == _sha(_canonical(metadata))
        and template["runtime_image"] == job["runtime_image"]
        and template["input_manifest_sha256"] is None
        and template["fits"] == template["broker_calls"] == 0
        and type(template["fits"]) is type(template["broker_calls"]) is int
        and type(template["max_inference_calls"]) is int
        and template["max_inference_calls"] == 1,
        "engine_template_binding",
    )
    # Preserve the frozen producer clock, never normalize/backdate it into success.
    _require(
        _clock(template["entry_valid_until"]) == _clock("2026-10-19T13:40:00+00:00"),
        "engine_entry_clock",
    )
    return job, data, template, source, metadata, keys


def validate_shadow_controls(controls: ShadowControls) -> tuple[tuple[str, object], ...]:
    """Pure pinned-control preflight; no callback, claim or source-file reads."""
    try:
        job, data, template, source, _, _ = _validate_controls(controls)
        return (
            ("job_sha", controls.job_sha),
            ("data_plan_sha", controls.data_plan_sha),
            ("engine_template_sha", controls.engine_template_sha),
            ("source_count", len(source)),
            ("expected_delivery_root", _path(controls.expected_delivery_root)),
        )
    except ShadowLinkError:
        raise
    except Exception:
        raise ShadowLinkError("controls_unavailable_or_invalid") from None


def _verify(claim_bytes, controls, read_metadata, observed_at):
    _require(callable(read_metadata), "controls_invalid")
    _require(
        type(observed_at) is datetime and observed_at.utcoffset() == timedelta(0), "clock_invalid"
    )
    job, data, template, source, metadata, keys = _validate_controls(controls)
    root = _path(controls.expected_delivery_root)
    records = {}

    def read(path, wanted=None, cap=4 * 1024**2):
        path = _path(path)
        _require(
            PureWindowsPath(path).drive.lower() == "d:" and PureWindowsPath(path).suffix == ".json",
            "metadata_only_path",
        )
        _require(path not in records and len(records) < 1040, "duplicate_metadata_link")
        raw = read_metadata(path, cap)
        value = _document(raw, wanted, cap)
        records[path] = (raw, cap)
        return value

    claim = _fields(
        _document(claim_bytes),
        "job_sha256 started_at_utc invocation_id output_root terminal_receipt_path",
    )
    invocation = claim["invocation_id"]
    _require(type(invocation) is str and bool(_ID.fullmatch(invocation)), "invocation_invalid")
    output = _join(root, "runtime", invocation)
    _require(
        claim["job_sha256"] == controls.job_sha
        and _same(claim["output_root"], output)
        and _same(claim["terminal_receipt_path"], _join(output, "receipt.json")),
        "claim_binding",
    )
    _require(
        read_metadata(_join(root, "runtime", "opportunity.claim.json"), 65536) == claim_bytes,
        "claim_readback",
    )
    records[_join(root, "runtime", "opportunity.claim.json")] = (claim_bytes, 65536)
    terminal = _fields(
        read(claim["terminal_receipt_path"]),
        "status job_sha256 invocation_id claim_sha256 actual_started_at_utc data_status "
        "broker_calls fits inference_calls future_monday_runtime data clock_guard_sha256 "
        "inference_attempt_status "
        "engine actual_completed_at_utc",
    )
    _require(
        terminal["status"] == "shadow_precommit_delivered"
        and terminal["job_sha256"] == controls.job_sha
        and terminal["invocation_id"] == invocation
        and terminal["claim_sha256"] == _sha(claim_bytes)
        and terminal["actual_started_at_utc"] == claim["started_at_utc"]
        and terminal["data_status"] == "input_ready"
        and terminal["inference_attempt_status"] == "worker_reported"
        and terminal["future_monday_runtime"] == "not_observed"
        and _count(terminal["broker_calls"], 0) == _count(terminal["fits"], 0) == 0
        and _count(terminal["inference_calls"], 1) == 1
        and terminal["clock_guard_sha256"]
        == source.get(_path(job["data"]["clock_guard_path"]).casefold()),
        "terminal_unavailable_or_unbound",
    )
    td = _fields(terminal["data"], "status completed_at_utc receipt_sha256 inference_calls")
    te = _fields(terminal["engine"], "status completed_at_utc receipt_sha256 inference_calls")
    _require(
        td["status"] == "input_ready"
        and _count(td["inference_calls"], 0) == 0
        and te["status"] == "shadow_precommit_created"
        and _count(te["inference_calls"], 1) == 1,
        "terminal_projection",
    )
    handoff = _fields(
        read(_join(output, "data-process", "handoff.json")),
        "kind job_sha256 plan_sha256 direct_receipt_path direct_receipt_sha256 "
        "actual_started_at_utc actual_completed_at_utc source_pins_sha256",
    )
    source_sha = _sha(_canonical(job["source_pins"]))
    _require(
        handoff["kind"] == "prospective512_data_child_handoff_v1"
        and handoff["job_sha256"] == controls.job_sha
        and handoff["plan_sha256"] == controls.data_plan_sha
        and handoff["source_pins_sha256"] == source_sha
        and handoff["direct_receipt_sha256"] == td["receipt_sha256"],
        "handoff_binding",
    )
    direct_path = PureWindowsPath(_path(handoff["direct_receipt_path"]))
    _require(
        direct_path.name == "receipt.json"
        and direct_path.parent.parent == PureWindowsPath(_path(_DATA))
        and bool(re.fullmatch(r"attempt-[0-9a-f]{32}", direct_path.parent.name)),
        "direct_path",
    )
    direct = _fields(
        read(str(direct_path), handoff["direct_receipt_sha256"]),
        _WORKER_FIELDS
        | {"direct_receipt_path", "owned_tree", "worker_receipt_sha256", "whole_elapsed_seconds"},
    )
    worker = _fields(
        read(str(direct_path.parent / "worker-receipt.json"), direct["worker_receipt_sha256"]),
        _WORKER_FIELDS,
    )
    _require(
        all(
            direct[key] == value and type(direct[key]) is type(value)
            for key, value in worker.items()
        )
        and _same(direct["direct_receipt_path"], str(direct_path)),
        "direct_worker_binding",
    )
    runtime = _fields(
        read(_join(_DATA, "runtime-contract.json"), direct["runtime_contract_sha256"]),
        "kind plan_sha256 epoch budget",
    )
    started = _fields(
        read(str(direct_path.parent / "started.json")),
        "kind plan_sha256 epoch started_at_utc phase opportunity_end_utc",
    )
    _require(
        runtime["kind"] == started["kind"] == _KIND
        and runtime["plan_sha256"]
        == started["plan_sha256"]
        == direct["plan_sha256"]
        == controls.data_plan_sha
        and runtime["epoch"] == started["epoch"]
        and type(runtime["epoch"]) in (int, float)
        and math.isfinite(runtime["epoch"])
        and runtime["budget"] == data["budget"]
        and started["phase"] == "source_preflight"
        and started["opportunity_end_utc"] == _DATA_END,
        "runtime_clock_binding",
    )
    tree = direct["owned_tree"]
    _require(
        type(tree) is dict
        and tree.get("timed_out") is False
        and tree.get("root_reaped") is True
        and tree.get("tree_reaped") is True
        and _count(tree.get("root_exit_code"), 0)
        == _count(tree.get("active_processes_after_reap"), 0)
        == 0,
        "reported_cleanup_invalid",
    )
    _seconds(direct["elapsed_seconds"], 1200)
    _seconds(direct["whole_elapsed_seconds"], 1200)
    _require(
        direct["whole_elapsed_seconds"] >= direct["elapsed_seconds"]
        and direct["status"] == "current_input_serialized"
        and direct["final_source_audit_passed"] is True
        and direct["raw_stdout_retained"] is False
        and direct["qualification"] is False
        and direct["availability"] == "assumed_not_observed"
        and direct["next_due"] is None
        and td["completed_at_utc"] == direct["materialization_completed_at_utc"],
        "data_receipt_invalid",
    )
    manifest_path = _join(_CACHE, "view", "manifest.json")
    manifest = _fields(
        read(manifest_path, direct["manifest_sha256"]),
        "kind plan_sha256 metadata source_pins source_chunks captured_at_utc physical_capture "
        "availability row_counts logical_record_sha256 record_count grid_count "
        "no_key_filter_or_replacement limitations packed",
    )
    _require(
        manifest["kind"] == _KIND
        and manifest["plan_sha256"] == controls.data_plan_sha
        and manifest["metadata"] == metadata
        and manifest["source_pins"] == data["source_pins"]
        and manifest["limitations"] == data["limitations"]
        and manifest["no_key_filter_or_replacement"] is True
        and manifest["availability"] == "assumed_not_observed",
        "manifest_binding",
    )
    packed = _fields(manifest["packed"], "path sha256 size_bytes")
    _require(
        packed["path"] == "bars.csv.gz"
        and _pin(packed["sha256"]) == direct["packed_sha256"]
        and type(packed["size_bytes"]) is int
        and packed["size_bytes"] > 0,
        "packed_link",
    )
    counts, chunks = manifest["row_counts"], manifest["source_chunks"]
    _require(
        type(counts) is dict
        and set(counts) == set(keys)
        and type(chunks) is list
        and len(chunks) == 512
        and [item["key"] for item in chunks] == keys
        and type(manifest["logical_record_sha256"]) is dict
        and set(manifest["logical_record_sha256"]) == set(keys),
        "manifest_identity_order",
    )
    for value in manifest["logical_record_sha256"].values():
        _pin(value)
    for value in counts.values():
        _count(value, 21)
    expected_counts = {
        "target_count": 512,
        "calendar_count": 21,
        "grid_count": 10752,
        "record_count": sum(counts.values()),
        "full_targets": sum(n == 21 for n in counts.values()),
        "sparse_targets": sum(0 < n < 21 for n in counts.values()),
        "empty_targets": sum(n == 0 for n in counts.values()),
        "position": 512,
    }
    _require(
        all(type(direct[k]) is int and direct[k] == v for k, v in expected_counts.items())
        and type(manifest["grid_count"]) is int
        and manifest["grid_count"] == 10752
        and type(manifest["record_count"]) is int
        and manifest["record_count"] == direct["record_count"],
        "data_counts",
    )
    _require(
        type(direct["supported"]) is bool
        and _count(direct["eligible_count"], 512) >= 0
        and type(direct["frame_sha256"]) is str
        and bool(re.fullmatch(r"[0-9a-f]{64}", direct["frame_sha256"])),
        "data_frame",
    )
    _count(direct["daily_attempts"], 1024)
    _count(direct["accepted_pages"], direct["daily_attempts"])
    captured = _clock(manifest["captured_at_utc"])
    accepted = _physical_links(chunks, counts, controls.data_plan_sha, captured, read)
    _require(accepted == direct["accepted_pages"], "accepted_page_binding")
    plan = read(_join(output, "engine-plan.json"))
    expected = _document(controls.engine_template_bytes)
    expected["input_manifest_sha256"] = direct["manifest_sha256"]
    expected["pins"]["/dataset/manifest.json"] = direct["manifest_sha256"]
    expected["pins"]["/dataset/bars.csv.gz"] = direct["packed_sha256"]
    _require(_canonical(plan) == _canonical(expected), "engine_plan_substitution")
    plan_sha = _sha(records[_join(output, "engine-plan.json")][0])
    _require(set(plan["pins"]) == set(plan["host_paths"]), "engine_aliases")
    fixed = {
        **source,
        **{
            _path(v["host"]).casefold(): _pin(v["sha256"])
            for v in job["engine"]["fixed_inputs"].values()
        },
    }
    for alias, host in plan["host_paths"].items():
        wanted = _pin(plan["pins"][alias])
        if alias in {"/dataset/manifest.json", "/dataset/bars.csv.gz"}:
            _require(_same(host, _join(_CACHE, "view", PurePosixPath(alias).name)), "dataset_alias")
        else:
            _require(fixed.get(_path(host).casefold()) == wanted, "engine_source_binding")
    data_paths = {**data["source_pins"], **data["reference_inputs"]}
    _require(
        set(plan["data_source_paths"]) == set(data_paths)
        and all(
            plan["pins"].get(alias) == data_paths[host]
            for host, alias in plan["data_source_paths"].items()
        ),
        "engine_data_sources",
    )
    attempt = _fields(read(_join(output, "engine-attempt.claim.json")), "plan_sha256")
    _require(attempt["plan_sha256"] == plan_sha, "inference_attempt_binding")
    result_path = _join(output, "engine-output", "result.json")
    result = _fields(read(result_path, te["receipt_sha256"]), _RESULT_FIELDS)
    links = {
        "plan_sha256": plan_sha,
        "worker_sha256": plan["pins"]["/worker/shadow_worker.py"],
        "source_pins_sha256": _sha(_canonical(plan["pins"])),
        "input_plan_sha256": controls.data_plan_sha,
        "input_manifest_sha256": direct["manifest_sha256"],
        "input_metadata_sha256": _sha(_canonical(metadata)),
        "physical_capture_sha256": _sha(_canonical(manifest["physical_capture"])),
        "source_chunks_sha256": _sha(_canonical(chunks)),
        "calendar26_sha256": metadata["calendar26_sha256"],
        "source_count": len(plan["pins"]),
        "data_source_count": len(data_paths),
        "input_captured_at": manifest["captured_at_utc"],
    }
    _require(
        all(result[k] == v and type(result[k]) is type(v) for k, v in links.items()),
        "engine_result_links",
    )
    _require(
        result["status"] in {"prepared", "no_intent"}
        and result["phase"] == "complete"
        and _count(result["fit_calls"], 0) == _count(result["broker_calls"], 0) == 0
        and _count(result["inference_calls"], 1) == 1
        and result["sources_reattested"] is True
        and result["shadow_only"] is True
        and result["order_consumer"] is False
        and result["raw_rows_retained"]
        is result["scores_retained"]
        is result["model_dump_retained"]
        is False
        and result["availability"] == "assumed_not_observed"
        and result["frame_sha256"] == "sha256:" + direct["frame_sha256"]
        and result["supported"] is direct["supported"]
        and type(result["eligible_count"]) is int
        and result["eligible_count"] == direct["eligible_count"]
        and _count(result["original_eligible"], 128) + _count(result["added_eligible"], 384)
        == result["eligible_count"]
        and _count(result["identity_count"], 512) == 512
        and _count(result["complete_prior21_count"], 512) == direct["full_targets"]
        and te["completed_at_utc"] == result["completed_at"],
        "engine_result_scope",
    )
    _seconds(result["elapsed_seconds"], 120)
    clock_values = (
        ("claim_started", claim["started_at_utc"]),
        ("data_child_started", handoff["actual_started_at_utc"]),
        ("data_started", started["started_at_utc"]),
        ("input_captured", manifest["captured_at_utc"]),
        ("data_materialized", direct["materialization_completed_at_utc"]),
        ("data_child_completed", handoff["actual_completed_at_utc"]),
        ("engine_started", result["worker_started_at"]),
        ("inference_completed", result["inference_completed_at"]),
        ("engine_completed", result["completed_at"]),
        ("terminal_completed", terminal["actual_completed_at_utc"]),
    )
    clocks = [_clock(value) for _, value in clock_values]
    epoch = datetime.fromtimestamp(runtime["epoch"], UTC)
    _require(
        _clock(_START) <= clocks[0] <= clocks[1] <= epoch <= clocks[2]
        and all(a <= b for a, b in zip(clocks[:-1], clocks[1:], strict=True))
        and clocks[5] <= _clock(_DATA_END)
        and clocks[-1] <= _clock(_END)
        and clocks[-1] <= observed_at
        and (clocks[-1] - clocks[0]).total_seconds() <= 1800
        and (clocks[8] - clocks[6]).total_seconds() <= 180
        and epoch <= clocks[4] <= epoch + timedelta(seconds=direct["elapsed_seconds"] + 0.000001)
        and epoch + timedelta(seconds=direct["whole_elapsed_seconds"] - 0.000001) <= clocks[5],
        "actual_clock_order",
    )
    # Re-read exact identities, not latest artifacts; changes during traversal fail.
    for path, (raw, cap) in records.items():
        _require(read_metadata(path, cap) == raw, "immutable_link_changed")
    links.update(
        result_sha256=te["receipt_sha256"],
        engine_started_at=result["worker_started_at"],
        engine_finished_at=result["completed_at"],
    )
    _require(
        set(links)
        == set(_ENGINE_LINKS) | {"result_sha256", "engine_started_at", "engine_finished_at"},
        "engine_map",
    )
    return VerifiedShadowLink(
        invocation,
        te["receipt_sha256"],
        plan_sha,
        MetadataLink(manifest_path, direct["manifest_sha256"]),
        direct["packed_sha256"],
        controls.job_sha,
        controls.data_plan_sha,
        source_sha,
        metadata["calendar26_sha256"],
        clock_values,
        tuple(MetadataLink(path, _sha(raw)) for path, (raw, _) in records.items()),
        tuple(links.items()),
    )


def _physical_links(chunks, counts, plan_sha, captured, read):
    previous, accepted_total, paths = _clock(_START), 0, set()
    for item in chunks:
        _fields(item, "key state chunk needed_rows physical_capture")
        n = counts[item["key"]]
        _require(
            type(item["needed_rows"]) is int
            and item["needed_rows"] == n
            and item["state"] == ("full" if n == 21 else "sparse" if n else "empty"),
            "chunk_count",
        )
        link_paths = []
        for field, name in (
            ("chunk", "manifest.json"),
            ("physical_capture", "physical-capture.json"),
        ):
            link = _fields(item[field], "path sha256")
            relative = link["path"]
            _require(
                type(relative) is str
                and len(relative) <= 256
                and "\\" not in relative
                and ":" not in relative
                and str(PurePosixPath(relative)) == relative
                and len(PurePosixPath(relative).parts) == 2
                and PurePosixPath(relative).parts[0].startswith("snapshot=")
                and PurePosixPath(relative).name == name
                and ".." not in PurePosixPath(relative).parts,
                "chunk_path",
            )
            path = _join(_CACHE, *PurePosixPath(relative).parts)
            _require(path not in paths, "duplicate_chunk_link")
            paths.add(path)
            link_paths.append(path)
        _require(
            PureWindowsPath(link_paths[0]).parent == PureWindowsPath(link_paths[1]).parent,
            "chunk_pair",
        )
        chunk = read(link_paths[0], item["chunk"]["sha256"], 1024**2)
        physical = _fields(
            read(link_paths[1], item["physical_capture"]["sha256"], 65536),
            "scope_started_at_utc requests chunk_write_started_at_utc chunk_write_completed_at_utc "
            "legacy_collected_at_semantics manifest_sha256",
        )
        symbol, exchange = item["key"].split("/")
        _require(
            chunk["kind"] == "kis_paper_private_daily_cache"
            and chunk["immutable_snapshot"] is True
            and chunk["code_revision"] == plan_sha
            and chunk["collector_version"] == chunk["collector_objective_id"] == _KIND
            and chunk["source"]["symbol"] == symbol
            and chunk["source"]["exchange"] == exchange
            and chunk["source"]["endpoint"] == "dailyprice"
            and chunk["source"]["adjustment_mode"] == "MODP=0_unadjusted"
            and chunk["requested_date_bounds"]["initial_anchor_bymd"] == "20261016"
            and chunk["requested_scope"]
            == {
                "floor_session": "2026-09-18",
                "anchor_session": "2026-10-16",
                "session_count": 21,
                "provider_continuation_preserved": True,
            },
            "chunk_source",
        )
        _require(
            physical["manifest_sha256"] == item["chunk"]["sha256"]
            and {**physical, "chunk_write_completed_at_utc": None, "manifest_sha256": None}
            == {**chunk["physical_capture"], "manifest_sha256": None}
            and physical["legacy_collected_at_semantics"] == "scope_start_not_response_completion",
            "physical_binding",
        )
        start, write, end = (
            _clock(physical[k])
            for k in (
                "scope_started_at_utc",
                "chunk_write_started_at_utc",
                "chunk_write_completed_at_utc",
            )
        )
        _require(
            previous <= start <= write <= end <= captured
            and _clock(chunk["collected_at_utc"]) == start,
            "physical_clock",
        )
        accepted = _count(chunk["requests"]["accepted_pages"], 2)
        attempts = _count(chunk["requests"]["page_attempts"], 2)
        requests = physical["requests"]
        _require(
            accepted <= attempts and type(requests) is list and len(requests) == attempts,
            "physical_coverage",
        )
        success, request_previous = 0, start
        for request in requests:
            _fields(request, "request_started_at_utc response_completed_at_utc transport_clock")
            call = _clock(request["request_started_at_utc"])
            done = (
                _clock(request["response_completed_at_utc"])
                if request["response_completed_at_utc"] is not None
                else None
            )
            _require(
                request_previous <= call <= write and (done is None or call <= done <= write),
                "physical_clock",
            )
            transport, body = request["transport_clock"], None
            if transport is not None:
                _fields(transport, "request_started_at_utc response_completed_at_utc")
                delegate = _clock(transport["request_started_at_utc"])
                body = (
                    _clock(transport["response_completed_at_utc"])
                    if transport["response_completed_at_utc"] is not None
                    else None
                )
                _require(
                    call <= delegate <= (done or write)
                    and (body is None or delegate <= body <= (done or write)),
                    "physical_clock",
                )
            success += int(done is not None and body is not None)
            request_previous = done or body or call
        _require(success >= accepted, "accepted_clock_coverage")
        accepted_total += accepted
        previous = end
    return accepted_total


def verify_shadow_link(
    claim_bytes: bytes,
    *,
    controls: ShadowControls,
    read_metadata: Callable[[str, int], bytes],
    observed_at: datetime,
) -> VerifiedShadowLink:
    """Verify one exact immutable metadata chain; missing/failed input stays scoped.

    Expected control hashes are independently frozen by the caller. A synthetic
    caller may supply synthetic pins; never derive trusted pins from untrusted
    inputs in production. No permission, provider or profitability conclusion.
    """
    try:
        return _verify(claim_bytes, controls, read_metadata, observed_at)
    except ShadowLinkError:
        raise
    except Exception:
        raise ShadowLinkError("linked_metadata_unavailable_or_invalid") from None
