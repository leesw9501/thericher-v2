"""Write one next-session H123 input from a qualified NET25 daily panel."""

import hashlib
import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas_market_calendars as mcal

from thericher_v2.data.kis_paper_h3_daily_panel import NET25_H3_AXIS, H3DailyPanel


def write_h3_h123_input(
    destination: Path,
    panel: H3DailyPanel,
    *,
    data_source_sha256: str,
    decision_at: datetime,
    synthetic: bool,
    prefix_features: Callable[..., tuple[np.ndarray, np.ndarray]],
    parse_input: Callable[..., tuple[dict, dict]],
) -> str:
    """Write an unsealed input and require readback by the pinned H123 parser.

    The publisher must pin both callables and attest the panel's post-close
    source and custody before calling. A returned digest is not a point seal.
    The caller owns the destination; interrupted directories are not reused.
    """
    if (
        not destination.is_absolute()
        or any(p.is_symlink() or p.is_junction() for p in (destination, *destination.parents))
        or re.fullmatch(r"[0-9a-f]{64}", data_source_sha256) is None
        or type(synthetic) is not bool
        or type(decision_at) is not datetime
        or decision_at.utcoffset() != timedelta(0)
        or panel.plan.axis != NET25_H3_AXIS
    ):
        raise ValueError("h3_h123_binding_invalid")

    as_of = panel.plan.as_of
    schedule = mcal.get_calendar("NASDAQ").schedule(
        as_of + timedelta(days=1), as_of + timedelta(days=14)
    )
    if schedule.empty:
        raise ValueError("h3_h123_next_session_unavailable")
    next_day = schedule.index[0].date()
    if (
        decision_at.date() != next_day
        or not panel.plan.as_of_close_utc < decision_at < schedule.iloc[0]["market_open"]
    ):
        raise ValueError("h3_h123_not_next_session_preopen")

    sessions = tuple(day.strftime("%Y%m%d") for day in panel.plan.sessions)
    if len(panel.rows) != 60 or any(
        len(row) != 19 or any(bar.xymd != session for bar in row)
        for row, session in zip(panel.rows, sessions, strict=True)
    ):
        raise ValueError("h3_h123_panel_grid_invalid")
    ohlc = np.array(
        [[(bar.open, bar.high, bar.low, bar.clos) for bar in row] for row in panel.rows],
        dtype=np.float64,
    )
    if not np.isfinite(ohlc).all() or not (ohlc > 0).all():
        raise ValueError("h3_h123_panel_value_invalid")
    x, z = prefix_features(ohlc, np.ones(ohlc.shape, bool), np.zeros((60, 19), bool))
    if (
        x.shape != (17, 60, 12)
        or x.dtype != np.float32
        or z.shape != (17, 8)
        or z.dtype != np.float64
        or not np.isfinite(x).all()
        or not np.isfinite(z).all()
    ):
        raise ValueError("h3_h123_feature_abi_invalid")

    day = next_day.strftime("%Y%m%d")
    keys = [f"{day}|{i:02d}" for i in range(17)]
    role = f"FUTURE_{as_of:%Y%m%d}_ASOF_{day}"
    arrays = dict(
        x=x,
        z=z,
        key=np.array(keys),
        known=np.ones(17, bool),
        entry_index=np.zeros(17, np.int64),
        context_close=np.full(17, panel.plan.as_of_close_utc.isoformat()),
        decision_at=np.full(17, decision_at.isoformat()),
    )
    destination.mkdir(exist_ok=False)
    payload = destination / "INPUT.npz"
    with payload.open("xb") as stream:
        np.savez_compressed(stream, **arrays)
    digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    header = dict(
        schema="SHORT_SWING_H123_INPUT_V1",
        producer="Data.ShortSwingEndpointProducer",
        consumer="EngineResearch.ShortSwingHorizonInput",
        source=data_source_sha256,
        role=role,
        synthetic=synthetic,
        unit="ORIGINAL_LOG_OHLC_LAST_CLOSE_PLUS_IND8",
        shape=[60, 12, 8],
        role_start=0,
        role_stop=1,
        payload_sha256=digest,
    )
    with (destination / "INPUT.json").open("x", encoding="ascii") as stream:
        json.dump(header, stream, sort_keys=True)
    observed, metadata = parse_input(
        destination,
        expected_source=data_source_sha256,
        role=role,
        expected_keys=keys,
        synthetic=synthetic,
    )
    if (
        metadata != header
        or observed.keys() != arrays.keys()
        or any(not np.array_equal(observed[name], value) for name, value in arrays.items())
    ):
        raise ValueError("h3_h123_readback_mismatch")
    return digest
