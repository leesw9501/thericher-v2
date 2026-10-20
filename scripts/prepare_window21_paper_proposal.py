"""Offline CPU producer -> sealed untrusted NAS-profile input, never a broker call.

Actual intraday entry/pre-close exit is an execution proxy, not replay-equivalent
OPEN[e] -> CLOSE[e+4]. Exact linked fills and owned recovery remain authoritative.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.research.model_paper_proposal import (
    ModelPaperMetadata,
    ModelPaperRow,
    prepare_model_paper_input,
    serialize_model_paper_input,
)

ADAPTER_ROOT = Path(
    "D:/thericher-v2/model-artifacts/research/current-window21-paper-proposal-preparation-20261020-v1"
)
READY_PIN = "715d075b1d450616dc1e8c92f6be08baf1543a26e6df942845ef8debb6e9d655"
SOURCE_PIN = "665a483b35da3600b2ef11a021c5fbc2a0dbc4e7671dc0d90c56d78b2466d3be"
ADAPTER_PIN = "c909d5820438fbeb33089ea0692ffe27be21318dc6a49d926305e6e9b3b23050"
BINDING_PIN = "6e9d1225cf3b4a36e9b708444c77933e9517adf1b56f81e4c3973708c2eeabd2"
CHECKPOINT_PIN = "7be506a44a0870de0e27e5baf2ce6ff73781f8e9c0a6b5c17538ef385657baff"
AFFINE_PIN = "aad2fc0f30d49b33a47e1573ad25fae4c8c5be42840d3dafac05d5ece2bf0097"
WINDOW21_ROUTES = (
    "AAPL/NAS",
    "AMD/NAS",
    "AMZN/NAS",
    "GOOGL/NAS",
    "META/NAS",
    "MSFT/NAS",
    "NVDA/NAS",
    "TSLA/NAS",
    "JPM/NYS",
    "JNJ/NYS",
    "XOM/NYS",
    "PG/NYS",
    "KO/NYS",
    "HD/NYS",
    "V/NYS",
    "DIS/NYS",
    "UNH/NYS",
    "COST/NAS",
    "LLY/NYS",
    "CAT/NYS",
    "MS/NYS",
    "CVX/NYS",
    "NEE/NYS",
    "VZ/NYS",
    "ADBE/NAS",
)


def _need(ok, reason):
    if not ok:
        raise ValueError(reason)


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _read(path, pin, limit=2 * 1024 * 1024):
    path = Path(path)
    _need(
        path.is_file() and not path.is_symlink() and not path.is_junction(), "producer_regular_file"
    )
    with path.open("rb") as stream:
        payload = stream.read(limit + 1)
    _need(len(payload) <= limit and _sha(payload) == pin, "producer_file_pin_mismatch")
    return payload


def _json(payload):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            _need(k not in result, "producer_duplicate_key")
            result[k] = v
        return result

    return json.loads(
        payload,
        object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("producer_nonfinite")),
    )


def _utc(text):
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    _need(value.utcoffset() == timedelta(0), "producer_UTC_clock_required")
    return value.astimezone(UTC)


def official_sessions(entry_date):
    first = us_equity_2026_session(date.fromisoformat(entry_date))
    _need(first is not None, "producer_official_entry_session_required")
    prior = []
    day = first.window.open_ts.date() - timedelta(days=1)
    while len(prior) < 22:
        item = us_equity_2026_session(day)
        if item is not None:
            prior.append(item.window)
        day -= timedelta(days=1)
    future = []
    day = first.window.open_ts.date()
    while len(future) < 5:
        item = us_equity_2026_session(day)
        if item is not None:
            future.append(item.window)
        day += timedelta(days=1)
    return tuple(reversed(prior)), tuple(future)


def _native_infer(closes, metadata):
    """One fixed trusted adapter path; no caller-supplied Python/module location."""
    _read(ADAPTER_ROOT / "READY.json", READY_PIN)
    source = _json(_read(ADAPTER_ROOT / "SOURCE.json", SOURCE_PIN))
    for name, pin in source["files"].items():
        _need(Path(name).name == name, "producer_source_name_invalid")
        _read(ADAPTER_ROOT / name, pin)
    _read(ADAPTER_ROOT / "adapter.py", ADAPTER_PIN)
    binding = _json(_read(ADAPTER_ROOT / "BINDING.json", BINDING_PIN))
    _need(
        binding["checkpoint"]["manifest"]["sha256"] == CHECKPOINT_PIN
        and binding["affine"]["sha256"] == AFFINE_PIN,
        "producer_selected_state_identity",
    )
    import torch

    _need(not torch.cuda.is_initialized(), "producer_CPU_process_required")
    torch.set_num_threads(2)
    spec = importlib.util.spec_from_file_location(
        "trusted_window21_CPU_adapter", ADAPTER_ROOT / "adapter.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    result = module.Window21().propose(closes, metadata)
    _need(not torch.cuda.is_initialized(), "producer_zero_GPU_context")
    return result


def _fixed5_ceiling(output, rows, maximum):
    slots = output["positive_slots"]
    _need(
        type(slots) is int
        and slots == min(5, sum(r.score > 0 for r in rows))
        and type(output["unfilled_slots"]) is int
        and output["unfilled_slots"] == 5 - slots,
        "producer_fixed5_positive_mass_mismatch",
    )
    mass = sum((Fraction(r.weight) for r in rows), Fraction())
    _need(
        all(r.score > 0 or r.weight == 0 for r in rows)
        and (mass == 0 if slots == 0 else abs(mass - 1) <= Fraction(1, 10**12)),
        "producer_fixed5_normalized_mass_mismatch",
    )
    if slots == 0:
        # The generic DTO requires a positive bound. All weights are zero, so this
        # unused maximum creates no targets; it is not proposed or reserved gross.
        return maximum
    # Adapter weights sum to one over active slots, not the original fixed five.
    # Restore inactive cash once, before venue eligibility; never reweight rows.
    with localcontext() as context:
        context.prec = max(28, len(maximum.as_tuple().digits) + 2)
        return maximum * slots / 5


def prepare(
    input_payload,
    *,
    input_sha256,
    policy_payload,
    policy_sha256,
    input_directory,
    clock=lambda: datetime.now(UTC),
    infer=None,
):
    """A pinned Data22-close input and caller-frozen ceiling, with no execution state."""
    _need(
        _sha(input_payload) == input_sha256 and _sha(policy_payload) == policy_sha256,
        "producer_input_or_policy_pin",
    )
    document, policy = _json(input_payload), _json(policy_payload)
    _need(
        set(document) == {"schema", "close_ref", "entry_date", "metadata"}
        and document["schema"] == "WINDOW21_CANONICAL_CLOSE_INPUT_V1",
        "producer_input_schema",
    )
    _need(
        set(policy)
        == {
            "schema",
            "adapter_ready_sha256",
            "original_basis_gross_ceiling",
            "exit_minutes_before_close",
        }
        and policy["schema"] == "WINDOW21_MODEL_PAPER_POLICY_V1"
        and policy["adapter_ready_sha256"] == READY_PIN,
        "producer_policy_schema",
    )
    ceiling = Decimal(policy["original_basis_gross_ceiling"])
    _need(ceiling.is_finite() and 0 < ceiling <= 1, "producer_untrusted_ceiling_invalid")
    metadata = document["metadata"]
    _need(
        metadata["stock_routes"] == list(WINDOW21_ROUTES)
        and metadata["stock_slots"] == list(range(3, 28)),
        "producer_full25_exact_routes",
    )
    prior, future = official_sessions(document["entry_date"])
    lead = policy["exit_minutes_before_close"]
    _need(type(lead) is int and 0 < lead <= 390, "producer_trusted_exit_lead_required")
    exit_not_before = future[-1].close_ts - timedelta(minutes=lead)
    _need(
        future[-1].open_ts <= exit_not_before < future[-1].close_ts,
        "producer_exit_window_inside_fifth_session",
    )
    _need(
        tuple(map(_utc, metadata["past_close_utc"])) == tuple(v.close_ts for v in prior)
        and _utc(metadata["required_previous_close_utc"]) == prior[-1].close_ts
        and _utc(metadata["entry_open_utc"]) == future[0].open_ts,
        "producer_exact22_previous_sessions_and_entry",
    )
    _need(
        metadata["known"] == [[True] * 22 for _ in range(25)]
        and all(type(v) is bool for row in metadata["known"] for v in row),
        "producer_all25_known",
    )
    ordinal = metadata["entry_ordinal"]
    _need(
        type(ordinal) is int
        and ordinal >= 22
        and all(type(v) is int for v in metadata["past_ordinals"])
        and metadata["past_ordinals"] == list(range(ordinal - 22, ordinal)),
        "producer_exact22_prior_ordinals",
    )
    for name in ("canonical_source_ref", "capture_commit_ref", "calendar_ref"):
        _need(
            type(metadata[name]) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", metadata[name]),
            "producer_Data_reference",
        )
    _need(set(document["close_ref"]) == {"path", "sha256"}, "producer_close_reference_schema")
    path = Path(input_directory) / document["close_ref"]["path"]
    _need(
        Path(document["close_ref"]["path"]).name == document["close_ref"]["path"]
        and path.suffix == ".npz",
        "producer_local_numeric_input_only",
    )
    raw = _read(path, document["close_ref"]["sha256"])
    import io
    import zipfile

    import numpy as np

    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        _need(
            len(members) == 1
            and members[0].filename == "close22.npy"
            and members[0].file_size <= 25 * 22 * 8 + 1024,
            "producer_bounded_numeric_member",
        )
    with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
        _need(set(archive.files) == {"close22"}, "producer_target_free_close_member")
        closes = archive["close22"]
    _need(
        closes.dtype == np.float64
        and closes.shape == (25, 22)
        and np.isfinite(closes).all()
        and (closes > 0).all(),
        "producer_positive_canonical_close_geometry",
    )
    started = clock()
    _need(
        prior[-1].close_ts
        <= _utc(metadata["source_available_utc"])
        <= _utc(metadata["as_of"])
        <= started
        < future[0].open_ts,
        "producer_source_known_before_forward",
    )
    output = (infer or _native_infer)(closes, metadata)
    completed, observed = clock(), clock()
    _need(started <= completed <= observed < future[0].open_ts, "producer_actual_inference_clocks")
    _need(
        output["schema"] == "UNTRUSTED_WINDOW21_RANK_WEIGHTS_V1"
        and output["checkpoint_manifest_sha256"] == CHECKPOINT_PIN
        and output["affine_sha256"] == AFFINE_PIN
        and output["execution_authority"] is False
        and output["capital_targets_included"] is False,
        "producer_fixed_untrusted_adapter_ABI",
    )
    rows = output["rows"]
    _need(
        [r["stock_slot"] for r in rows] == list(range(3, 28))
        and [r["route"] for r in rows] == list(WINDOW21_ROUTES),
        "producer_output_all25_preserved",
    )
    _need(
        output["input_binding"]
        == {
            key: metadata[key]
            for key in (
                "as_of",
                "source_available_utc",
                "required_previous_close_utc",
                "entry_ordinal",
                "canonical_source_ref",
                "capture_commit_ref",
                "calendar_ref",
            )
        },
        "producer_output_input_receipt_match",
    )
    model_rows = tuple(
        ModelPaperRow(
            r["stock_slot"],
            r["route"],
            Decimal(str(r["score"])),
            r["rank"],
            Decimal(str(r["normalized_weight"])),
        )
        for r in rows
    )
    proposed_ceiling = _fixed5_ceiling(output, model_rows, ceiling)
    full_output = json.dumps(
        output, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    model = ModelPaperMetadata(
        "window21_simplest_not_selected_winner",
        "window21-close-return-fixed5-nas-provisional-v1",
        "sha256:" + CHECKPOINT_PIN,
        "sha256:" + SOURCE_PIN,
        "sha256:" + AFFINE_PIN,
        "sha256:" + input_sha256,
        metadata["calendar_ref"],
        "sha256:" + policy_sha256,
        "sha256:" + _sha(full_output),
        prior[-1].close_ts,
        _utc(metadata["source_available_utc"]),
        _utc(metadata["as_of"]),
        started,
        completed,
        observed,
        exit_not_before,
        proposed_ceiling,
        model_rows,
    )
    return prepare_model_paper_input(model, entry_session=future[0], exit_session=future[-1])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--policy-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    _need(not args.output.exists(), "producer_output_create_once")
    value = prepare(
        _read(args.input_manifest, args.input_sha256),
        input_sha256=args.input_sha256,
        policy_payload=_read(args.policy, args.policy_sha256),
        policy_sha256=args.policy_sha256,
        input_directory=args.input_manifest.parent,
    )
    payload = serialize_model_paper_input(value)
    with args.output.open("xb") as stream:
        stream.write(payload)
        stream.flush()
    _need(args.output.read_bytes() == payload, "producer_sealed_output_readback")
    print(
        json.dumps(
            dict(
                status="PROVISIONAL_NAS_PROPOSALS_NOT_EXECUTION_AUTHORITY",
                input_ref=value.input_ref,
                policy_ref=value.policy_ref,
                targets=len(value.targets),
                model_rows=len(value.metadata.rows),
                unsupported_venue_rows=sum(
                    r.eligibility == "UNSUPPORTED_VENUE" for r in value.metadata.rows
                ),
                model_choice="simplest_not_selected_winner",
                fixed5_inactive_cash_preserved=True,
                full_universe_performance_claim=False,
                replay_payoff_equivalent=False,
                exit_not_before_utc=value.metadata.exit_not_before.isoformat(),
            )
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
