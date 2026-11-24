import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime

import numpy as np
import pytest

from thericher_v2.data.kis_paper_h3_daily_panel import (
    NET25_H3_AXIS,
    H3DailyPanel,
    H3DailyPanelPlan,
)
from thericher_v2.execution.kis_market_data import KisPaperDailyRawRow
from thericher_v2.models.h3_h123_input import write_h3_h123_input

DECISION = datetime(2026, 12, 4, 14, 25, tzinfo=UTC)
SOURCE = "3" * 64


@pytest.fixture(scope="module")
def panel():
    plan = H3DailyPanelPlan(NET25_H3_AXIS)
    return H3DailyPanel(
        plan,
        tuple(
            tuple(
                KisPaperDailyRawRow(
                    day.strftime("%Y%m%d"), str(i + 10), str(i + 12), "9", str(i + 11), "10"
                )
                for i in range(19)
            )
            for day in plan.sessions
        ),
    )


def features(ohlc, known, conditional):
    assert ohlc.shape == (60, 19, 4) and ohlc.dtype == np.float64
    assert ohlc[0, 0].tolist() == [10, 12, 9, 11]
    assert ohlc[0, 17, 0] == 27 and ohlc[0, 18, 0] == 28
    assert known.dtype == conditional.dtype == bool and known.all() and not conditional.any()
    return np.ones((17, 60, 12), np.float32), np.ones((17, 8), np.float64)


def reader(root, *, expected_source, role, expected_keys, synthetic):
    meta = json.loads((root / "INPUT.json").read_bytes())
    assert (expected_source, role, synthetic) == (SOURCE, "FUTURE_20261203_ASOF_20261204", True)
    assert (meta["source"], meta["role"], meta["synthetic"]) == (expected_source, role, synthetic)
    assert meta["producer"] == "Data.ShortSwingEndpointProducer"
    assert meta["consumer"] == "EngineResearch.ShortSwingHorizonInput"
    assert meta["payload_sha256"] == hashlib.sha256((root / "INPUT.npz").read_bytes()).hexdigest()
    with np.load(root / "INPUT.npz", allow_pickle=False) as arrays:
        result = dict(arrays)
    assert expected_keys == result["key"].tolist() == [f"20261204|{i:02d}" for i in range(17)]
    assert set(result["context_close"]) == {"2026-12-03T21:00:00+00:00"}
    assert set(result["decision_at"]) == {"2026-12-04T14:25:00+00:00"}
    return result, meta


def write(destination, panel, **overrides):
    params = dict(
        decision_at=DECISION,
        data_source_sha256=SOURCE,
        synthetic=True,
        prefix_features=features,
        parse_input=reader,
    )
    return write_h3_h123_input(destination, panel, **(params | overrides))


def test_exact_next_session_artifact_and_exclusive_destination(tmp_path, panel):
    dest = tmp_path / "next"
    digest = write(dest, panel)
    assert digest == hashlib.sha256((dest / "INPUT.npz").read_bytes()).hexdigest()
    assert {p.name for p in dest.iterdir()} == {"INPUT.json", "INPUT.npz"}
    with pytest.raises(FileExistsError):
        write(dest, panel)


@pytest.mark.parametrize(
    "stamp", ["2026-12-03T21:30:00", "2026-12-04T14:30:00", "2026-12-07T14:25:00"]
)
def test_refuses_stale_premature_or_open_clock(tmp_path, panel, stamp):
    with pytest.raises(ValueError, match="next_session_preopen"):
        write(
            tmp_path / "next", panel, decision_at=datetime.fromisoformat(stamp).replace(tzinfo=UTC)
        )
    assert not list(tmp_path.iterdir())


def test_wrong_row_date_and_nonfinite_features_are_not_publishable(tmp_path, panel):
    wrong = replace(panel, rows=(panel.rows[1], *panel.rows[1:]))
    with pytest.raises(ValueError, match="panel_grid_invalid"):
        write(tmp_path / "next", wrong)

    def invalid(*args):
        x, z = features(*args)
        x[0, 0, 0] = np.nan
        return x, z

    with pytest.raises(ValueError, match="feature_abi_invalid"):
        write(tmp_path / "next", panel, prefix_features=invalid)
    assert not list(tmp_path.iterdir())


def test_consumer_drift_withholds_success(tmp_path, panel):
    def drift(*args, **options):
        arrays, header = reader(*args, **options)
        arrays["x"][0, 0, 0] = -5
        return arrays, header

    dest = tmp_path / "unsealed"
    with pytest.raises(ValueError, match="readback_mismatch"):
        write(dest, panel, parse_input=drift)
    assert not (dest / "SEAL.json").exists()
    with pytest.raises(FileExistsError):
        write(dest, panel)
