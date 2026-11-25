"""One bounded forward for the frozen Dec4 NET25 H3 proposal, never an order."""

import hashlib
import io
import json
import math
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import numpy as np

from thericher_v2.data.kis_paper_h3_capture import _read_native
from thericher_v2.execution.kis_paper_data_capture import _safe_path
from thericher_v2.models.h3_publisher_input import H3InputBinding, read_h3_publisher_input
from thericher_v2.research.model_paper_weights import (
    MODEL_PAPER_US_CASH_H3_OPS_ROUTES,
    ModelPaperWeightRow,
    append_derived_cash_h3_row,
)

DEC4_BINDING_CLOCK = datetime(2026, 12, 4, 14, 25, tzinfo=UTC)
DEC4_DATA_HARD = datetime(2026, 12, 3, 21, 45, tzinfo=UTC)
_START = datetime(2026, 12, 3, 21, 47, tzinfo=UTC)
_LAST_START = datetime(2026, 12, 3, 21, 52, tzinfo=UTC)
_HARD = datetime(2026, 12, 3, 22, tzinfo=UTC)
WEIGHTS_SHA = "2b758ff87e9253987f55de024655ee2be83c5be9e7aff3899f4adfa080b14613"
STATS_SHA = "4e08e63623cf514fad4cd4acf38ae55bc786939839b712beab514f639b7868da"
MODEL_SHA = "093ac13628921672e35fef9289b0c02d11bac827163e6f95eb9a544e5b1d6ee7"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _checked_clock(clock, cutoff):
    now = clock()
    if type(now) is not datetime or now.utcoffset() != timedelta(0) or not _START <= now < cutoff:
        raise ValueError("h3_point_clock_denied")
    return now


def _require_binding(binding, ready_sha256):
    if (
        binding.decision_at != DEC4_BINDING_CLOCK
        or binding.hard_stop != DEC4_DATA_HARD
        or re.fullmatch(r"[0-9a-f]{64}", ready_sha256) is None
    ):
        raise ValueError("h3_point_binding_denied")


def _frozen_lstm(arrays, source_code, stats, weights, *, before_forward):
    # Keep Torch and the checkpoint reader out of the base Data/Execution runtime.
    import torch
    from safetensors.torch import load

    if tuple(map(_sha, (source_code, stats, weights))) != (MODEL_SHA, STATS_SHA, WEIGHTS_SHA):
        raise ValueError("h3_point_model_pin_mismatch")
    with np.load(io.BytesIO(stats), allow_pickle=False) as archive:
        fields = {"mean": (12,), "std": (12,), "zmean": (8,), "zstd": (8,), "scale": ()}
        if set(archive.files) != set(fields):
            raise ValueError("h3_point_stats_invalid")
        affines = dict(archive)
    if (
        any(
            affines[k].shape != shape or not np.isfinite(affines[k]).all()
            for k, shape in fields.items()
        )
        or not (affines["std"] > 0).all()
        or not (affines["zstd"] > 0).all()
        or float(affines["scale"]) <= 0
    ):
        raise ValueError("h3_point_stats_invalid")
    x = ((arrays["x"].astype(np.float64) - affines["mean"]) / affines["std"]).astype(np.float32)
    z = ((arrays["z"] - affines["zmean"]) / affines["zstd"]).astype(np.float32)
    if not np.isfinite(x).all() or not np.isfinite(z).all():
        raise ValueError("h3_point_input_nonfinite")
    models = ModuleType("frozen_h3_lstm")
    exec(compile(source_code, "<pinned H3 model>", "exec"), vars(models))
    model = models.HorizonModel("LSTM").cpu()
    state = load(weights)
    slots = model.state_dict()
    if set(state) != set(slots) or any(
        v.shape != slots[k].shape or v.dtype != slots[k].dtype or not torch.isfinite(v).all()
        for k, v in state.items()
    ):
        raise ValueError("h3_point_checkpoint_invalid")
    model.load_state_dict(state, strict=True)
    model.requires_grad_(False).eval()
    before_forward()
    with torch.inference_mode():
        output = model(torch.from_numpy(x), torch.from_numpy(z)).double().numpy()
    output *= float(affines["scale"])
    if output.shape != (17, 3) or not np.isfinite(output).all():
        raise ValueError("h3_point_output_invalid")
    return output[:, 2]


def _rows(scores):
    if len(scores) != 17 or any(type(v) is not float or not math.isfinite(v) for v in scores):
        raise ValueError("h3_point_scores_invalid")
    limit = Decimal("0.029411764705882352941176")
    encoded = float(limit)
    if Decimal(repr(encoded)) > limit:
        encoded = math.nextafter(encoded, 0.0)
    stock = tuple(
        ModelPaperWeightRow(i, route, True, Decimal(repr(encoded)) if score > 0 else Decimal(0))
        for i, (route, score) in enumerate(
            zip(MODEL_PAPER_US_CASH_H3_OPS_ROUTES[:17], scores, strict=True)
        )
    )
    return [
        dict(slot=r.slot, route=r.route, known=True, weight=str(r.weight))
        for r in append_derived_cash_h3_row(stock)
    ]


def _point(scores, binding, ready_sha256, input_verified, started, completed, observed):
    return dict(
        schema="DEC4_FROZEN_LSTM_H3_SHADOW_V2",
        input_verified_at=input_verified.isoformat(),
        inference_started_at=started.isoformat(),
        inference_completed_at=completed.isoformat(),
        observed_at=observed.isoformat(),
        source_sha256=binding.source_sha256,
        ready_sha256=ready_sha256,
        model_sha256=MODEL_SHA,
        weights_sha256=WEIGHTS_SHA,
        stats_sha256=STATS_SHA,
        synthetic=binding.synthetic,
        financial_authority=False,
        not_before=binding.decision_at.isoformat(),
        valid_until="2026-12-04T14:35:00+00:00",
        entry_open="2026-12-04T14:30:00+00:00",
        exit_open="2026-12-09T14:30:00+00:00",
        scores=scores,
        rows=_rows(scores),
    )


def publish_dec4_h3_shadow_point(
    destination: Path,
    *,
    input_root: Path,
    capture_state_path: Path,
    binding: H3InputBinding,
    ready_sha256: str,
    clock: Callable[[], datetime],
    validate_input: Callable,
    model_source: bytes,
    stats: bytes,
    weights: bytes,
) -> str:
    """Publish one non-authoritative proposal under the caller's fresh owned root."""
    _require_binding(binding, ready_sha256)
    _checked_clock(clock, _LAST_START)
    if not destination.is_absolute() or _safe_path(destination) != destination:
        raise ValueError("h3_point_root_invalid")
    arrays, header = read_h3_publisher_input(
        input_root,
        capture_state_path,
        binding=binding,
        ready_sha256=ready_sha256,
        clock=clock,
        validate_input=validate_input,
    )
    if (
        not np.all(arrays["known"])
        or not np.all(arrays["entry_index"] == 0)
        or header["shape"] != [60, 12, 8]
    ):
        raise ValueError("h3_point_cohort_incomplete")
    if not all(arrays["decision_at"] == binding.decision_at.isoformat()) or not all(
        arrays["context_close"] == "2026-12-03T21:00:00+00:00"
    ):
        raise ValueError("h3_point_input_clock_mismatch")
    input_verified = _checked_clock(clock, _LAST_START)
    destination.mkdir(exist_ok=False)
    started = None

    def before_forward():
        nonlocal started
        if started is not None:
            raise ValueError("h3_point_forward_already_started")
        started = _checked_clock(clock, _LAST_START)

    scores = _frozen_lstm(
        arrays,
        model_source,
        stats,
        weights,
        before_forward=before_forward,
    )
    completed = _checked_clock(clock, _HARD)
    observed = _checked_clock(clock, _HARD)
    if started is None or not input_verified <= started <= completed <= observed:
        raise ValueError("h3_point_forward_clock_mismatch")
    raw = _json(
        _point(scores.tolist(), binding, ready_sha256, input_verified, started, completed, observed)
    )
    pending = destination / "POINT.pending"
    with pending.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    _checked_clock(clock, _HARD)
    pending.rename(destination / "POINT.json")
    _checked_clock(clock, _HARD)
    return _sha(raw)


def read_dec4_h3_shadow_point(
    root: Path, *, binding: H3InputBinding, ready_sha256: str, point_sha256: str
) -> dict:
    """Accept only an exactly bound proposal; runtime financial gates are separate."""
    _require_binding(binding, ready_sha256)
    raw = _read_native(root, str(root / "POINT.json"))
    if _sha(raw) != point_sha256:
        raise ValueError("h3_point_digest_mismatch")
    point = json.loads(raw)
    input_verified = datetime.fromisoformat(point["input_verified_at"])
    started = datetime.fromisoformat(point["inference_started_at"])
    completed = datetime.fromisoformat(point["inference_completed_at"])
    observed = datetime.fromisoformat(point["observed_at"])
    _checked_clock(lambda: input_verified, _LAST_START)
    _checked_clock(lambda: started, _LAST_START)
    _checked_clock(lambda: completed, _HARD)
    _checked_clock(lambda: observed, _HARD)
    if not input_verified <= started <= completed <= observed or raw != _json(
        _point(point["scores"], binding, ready_sha256, input_verified, started, completed, observed)
    ):
        raise ValueError("h3_point_readback_mismatch")
    return point
