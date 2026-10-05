"""Synthetic-only paired study checks; no real-data fits, CUDA or Docker dispatch."""

import copy
import importlib.util
import json
import socket
import subprocess
import sys
import time
from contextlib import nullcontext
from dataclasses import replace
from decimal import Decimal, localcontext
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from thericher_v2.data.kis_paper_intraday_index_metadata import _legacy_chunk_key
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.research import kis_paired_lag_development as r

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_kis_paired_lag_development.py"
spec = importlib.util.spec_from_file_location("paired_lag_launcher", SCRIPT)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
PIN = "sha256:" + "1" * 64


def revise(catalog, *, bars=None, dataset_id=None, dataset_hash=None):
    return _cataloged_bars_from_verified_loader(
        dataset_id=dataset_id or catalog.dataset_id,
        dataset_hash=dataset_hash or catalog.dataset_hash,
        source_path=catalog.source_path,
        bars=catalog.bars if bars is None else bars,
    )


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", lambda *_: pytest.fail("network forbidden"))
    monkeypatch.setattr(socket, "create_connection", lambda *_: pytest.fail("network forbidden"))


@pytest.fixture(scope="module")
def panel():
    return r.synthetic_panel()


@pytest.fixture(scope="module")
def feedback(panel):
    return tuple(r.payoffs(*panel, dates) for dates in (r.TRAIN, r.COMPARISON))


@pytest.fixture(scope="module")
def checks(panel):
    return r.causal_audit(*panel)


@pytest.fixture(scope="module")
def actions(panel, feedback):
    controls = r.controls(panel[0], feedback[0])
    return tuple(
        controls.get(p, tuple(i % (j + 2) == 0 for i in range(96)))
        for j, p in enumerate(r.POLICIES)
    )


@pytest.fixture(scope="module")
def evaluation(panel, feedback, actions, checks):
    return r.aggregate(panel[0], feedback[1], actions, causal_checks=checks)


def test_frozen_calendar_geometry_and_budget(panel):
    windows, catalogs = panel
    c = r.configuration()
    assert len(r.DATES) == 25 and len(catalogs) == 50 and len(windows) == 1392
    assert len(r.split(windows, r.TRAIN)) == 1296 and len(r.split(windows, r.COMPARISON)) == 96
    assert str(r.TRAIN[0]) == "2026-08-28" and str(r.TRAIN[-1]) == "2026-09-15"
    assert str(r.EMBARGO) == "2026-09-16" and len(r.COMPARISON) == 12
    assert str(r.COMPARISON[0]) == "2026-09-17" and str(r.COMPARISON[-1]) == "2026-10-02"
    assert r.TRAIN_OFFSETS == tuple(range(60, 326, 5)) and len(r.TRAIN_OFFSETS) == 54
    assert r.COMPARISON_OFFSETS == (60, 150, 240, 300)
    assert c["cells"] == 48 and c["shared_session_blocks"] == c["shared_train_session_blocks"] == 12
    assert c["neural"] == dict(
        seed=109,
        epochs=128,
        batch=1296,
        optimizer="Adam",
        lr=0.001,
        weight_decay=0,
        loss="Huber",
        delta=0.1,
        hidden=16,
        heads=2,
        kernel=3,
        architectures=["lstm", "compact_attention"],
        dropout=0,
        final_epoch_only=True,
        selection=False,
    )
    assert c["budget"] == dict(
        actual_fits=4,
        attempts=1,
        cpu_threads=2,
        memory_bytes=6 * 1024**3,
        seconds=500,
        gpu=True,
        synthetic_smoke_fits=8,
    )
    assert set(c["kills"]) == set(r.KILLS)
    assert r.COSTS == ("3", "4.5", "6") and cli.SECONDS == 500
    assert cli.h.IMAGE == "sha256:d6b43213ee3877653e3c1e79c7238fb5caa71241abf238838fa0c3332cf4f039"
    assert len(cli.q.r.DATES) == 20 and str(cli.q.r.EMBARGO) == "2026-09-17"
    for w in windows:
        assert len(w.sequence) == 12 and len(w.sequence[0]) == len(w.features) == 8
        assert w.source_minute_starts == w.peer_minute_starts
        assert w.source_minute_starts[-1] + r.MINUTE == w.key.cutoff
        assert w.key.entry == w.key.cutoff + r.MINUTE and w.key.exit == w.key.cutoff + 61 * r.MINUTE
        assert w.peer_key.cutoff == w.key.cutoff and w.peer_key.symbol != w.key.symbol
        assert w.key.session_date != r.EMBARGO
        assert w.key.exit < r.us_equity_2026_session(w.key.session_date).window.close_ts


def test_exact_own_peer_feature_order_and_synchronized_prefix(panel):
    qqq = panel[0][0]
    spy = next(w for w in panel[0] if w.key.symbol == "SPY")
    assert qqq.features == spy.features[4:] + spy.features[:4]
    assert qqq.sequence == tuple(v[4:] + v[:4] for v in spy.sequence)
    for w in (qqq, spy):
        target = next(t for t in r.TARGETS if t[0] == w.key.symbol)
        _, starts, seq, features = r._prefix(
            panel[1][w.key.symbol, w.key.session_date], target, w.key.session_date, w.key.cutoff
        )
        assert starts == w.source_minute_starts and tuple(v[:4] for v in w.sequence) == seq
        assert w.features[:4] == features


@pytest.mark.parametrize(
    "kind",
    (
        "subset",
        "duplicate",
        "order",
        "date",
        "hash",
        "peer_hash",
        "peer_date",
        "peer_future",
        "missing_timestamps",
        "own_peer_order",
        "symbol",
        "shape",
        "nan",
    ),
)
def test_cohort_rejects_exact_binding_or_geometry_fault(panel, kind):
    windows = list(panel[0])
    w = windows[0]
    if kind == "subset":
        windows.pop()
    elif kind == "duplicate":
        windows[0] = windows[1]
    elif kind == "order":
        windows.reverse()
    elif kind == "date":
        windows[0] = replace(w, key=replace(w.key, session_date=r.DATES[1]))
    elif kind == "hash":
        windows[0] = replace(w, key=replace(w.key, dataset_hash=PIN))
    elif kind == "peer_hash":
        windows[0] = replace(w, peer_key=replace(w.peer_key, dataset_hash=PIN))
    elif kind == "peer_date":
        windows[0] = replace(w, peer_key=replace(w.peer_key, session_date=r.DATES[1]))
    elif kind == "peer_future":
        windows[0] = replace(w, peer_key=replace(w.peer_key, cutoff=w.peer_key.cutoff + r.MINUTE))
    elif kind == "missing_timestamps":
        windows[0] = replace(w, peer_minute_starts=w.peer_minute_starts[:-1])
    elif kind == "own_peer_order":
        windows[0] = replace(
            w,
            features=w.features[4:] + w.features[:4],
            sequence=tuple(v[4:] + v[:4] for v in w.sequence),
        )
    elif kind == "symbol":
        windows[0] = replace(w, key=replace(w.key, symbol="IWM"))
    elif kind == "shape":
        windows[0] = replace(w, sequence=w.sequence[:-1])
    else:
        windows[0] = replace(w, features=(float("nan"), *w.features[1:]))
    with pytest.raises(ValueError):
        r.check_cohort(tuple(windows))


def test_aligned_prefix_future_peer_corruption_leaves_inputs_scalers_and_actions(panel, checks):
    w = r.split(panel[0], r.COMPARISON)[0]
    own, peer = (panel[1][k.symbol, k.session_date] for k in (w.key, w.peer_key))
    prefix = revise(peer, bars=tuple(b for b in peer.bars if b.start_ts < w.key.cutoff))
    changed = revise(
        peer,
        bars=tuple(
            replace(
                b,
                open=b.open * 2,
                high=b.high * 2,
                low=b.low * 2,
                close=b.close * 2,
                volume=b.volume * 3,
            )
            if b.start_ts >= w.key.cutoff
            else b
            for b in peer.bars
        ),
    )
    assert r.build_window(own, prefix, day=w.key.session_date, offset=60) == w
    assert r.build_window(own, changed, day=w.key.session_date, offset=60) == w
    assert checks == dict.fromkeys(r.CAUSAL_CHECKS, True)
    x = np.asarray([v.sequence for v in r.split(panel[0], r.TRAIN)], dtype=np.float64)
    z = np.asarray([w.sequence], dtype=np.float64)
    before = r.standardized(x, z)
    after = r.standardized(
        x,
        np.asarray(
            [r.build_window(own, changed, day=w.key.session_date, offset=60).sequence],
            dtype=np.float64,
        ),
    )
    assert all(np.array_equal(a, b) for a, b in zip(before, after, strict=True))
    # Identical deterministic inference inputs imply identical decisions, without a refit.
    assert tuple(v > 6 for v in before[1].sum(axis=(1, 2))) == tuple(
        v > 6 for v in after[1].sum(axis=(1, 2))
    )


@pytest.mark.parametrize(
    "kind", ("missing", "incomplete", "wrong_date", "wrong_id", "invalid_hash")
)
def test_missing_required_peer_history_rejects_only_this_input(panel, kind):
    w = panel[0][0]
    own, peer = (panel[1][k.symbol, k.session_date] for k in (w.key, w.peer_key))
    if kind == "missing":
        peer = revise(peer, bars=peer.bars[1:])
    elif kind == "incomplete":
        peer = revise(peer, bars=(replace(peer.bars[0], complete=False), *peer.bars[1:]))
    elif kind == "wrong_date":
        peer = panel[1][w.peer_key.symbol, r.DATES[1]]
    elif kind == "wrong_id":
        peer = revise(peer, dataset_id=own.dataset_id)
    else:
        with pytest.raises(ValueError):
            revise(peer, dataset_hash="private invalid hash")
        return
    with pytest.raises(ValueError):
        r.build_window(own, peer, day=w.key.session_date, offset=60)


def test_target_exact_opens_missing_future_is_postdecision_censoring(
    panel, feedback, actions, checks
):
    w = r.split(panel[0], r.COMPARISON)[0]
    own = panel[1][w.key.symbol, w.key.session_date]
    peer = panel[1][w.peer_key.symbol, w.peer_key.session_date]
    bars = {b.start_ts: b for b in own.bars}
    with localcontext() as ctx:
        ctx.prec = 50
        assert r.gross_bps(w, own) == 10000 * (bars[w.key.exit].open / bars[w.key.entry].open - 1)
    missing = revise(own, bars=tuple(b for b in own.bars if b.start_ts != w.key.exit))
    assert r.build_window(missing, peer, day=w.key.session_date, offset=60) == w
    seal = r.commitment(actions)
    assert r.gross_bps(w, missing, censor=True) is None
    with pytest.raises(ValueError, match="target_support"):
        r.gross_bps(w, missing)
    censored = (None, *feedback[1][1:])
    value = r.aggregate(panel[0], censored, actions, causal_checks=checks)
    assert value["commit_sha256"] == seal and len(value["cells"]) == 48
    assert "target_replay_inconsistency" in value["descriptive"]["kill_categories"]
    assert value["cells"][0]["decisions"] == 48 and value["cells"][0]["censored"] == 1
    with pytest.raises(ValueError, match="payoff_source"):
        r.gross_bps(w, peer)


@pytest.mark.parametrize("shape", ((1296, 4), (1296, 8), (1296, 12, 8)))
def test_scaler_float64_train_only_and_floor_no_comparison_statistics(shape):
    train = np.arange(np.prod(shape), dtype=np.float64).reshape(shape)
    train[..., -1] = 7
    future = train[:96].copy()
    a, b = r.standardized(train, future)
    c, d = r.standardized(train, future + 1e7)
    np.testing.assert_array_equal(a, c)
    assert np.max(d[..., -1]) > 1e18 and not np.array_equal(b, d)
    np.testing.assert_array_equal(a[..., -1], 0)
    np.testing.assert_array_equal(future, train[:96])


@pytest.mark.parametrize("fault", ("nan", "float32", "channels", "bars", "comp_shape"))
def test_strict_scaler_geometry(fault):
    x, z = np.zeros((16, 12, 8)), np.zeros((4, 12, 8))
    if fault == "nan":
        z[0, 0, 0] = np.nan
    elif fault == "float32":
        x = x.astype(np.float32)
    elif fault == "channels":
        x, z = x[:, :, :5], z[:, :, :5]
    elif fault == "bars":
        x, z = x[:, :11], z[:, :11]
    else:
        z = z[:, :, :4]
    with pytest.raises(ValueError):
        r.standardized(x, z)


@pytest.mark.parametrize("channels", (4, 8))
def test_ridge_penalty_intercept_and_train_only_aggregate(channels):
    x = np.sin(np.arange(16 * channels, dtype=np.float64).reshape(16, channels))
    z, y = x[:4] + 3, np.full(16, 37.0, dtype=np.float64)
    np.testing.assert_allclose(r.fit_ridge(x, y, z), 37, atol=1e-11)
    a, b = r.standardized(x, z)
    a, b = np.column_stack((a, np.ones(16))), np.column_stack((b, np.ones(4)))
    expected = b @ np.linalg.solve(a.T @ a + np.diag([1.0] * channels + [0.0]), a.T @ y)
    np.testing.assert_array_equal(r.fit_ridge(x, y, z), expected)


def test_synthetic_smoke_small_deterministic_no_source_or_gpu(monkeypatch):
    torch = pytest.importorskip("torch")
    steps, built = [], []
    step, builder = torch.optim.Adam.step, r.build_torch_sequence_model

    def adam(self, *args, **kw):
        assert self.param_groups[0]["lr"] == 0.001 and self.param_groups[0]["weight_decay"] == 0
        steps.append(1)
        return step(self, *args, **kw)

    def build(**kw):
        built.append(kw)
        return builder(**kw)

    monkeypatch.setattr(torch.optim.Adam, "step", adam)
    monkeypatch.setattr(r, "build_torch_sequence_model", build)
    monkeypatch.setattr(r, "synthetic_panel", lambda: pytest.fail("large smoke panel"))
    monkeypatch.setattr(cli, "load_panel", lambda *_: pytest.fail("actual market smoke"))
    assert r.cpu_smoke(time.monotonic() + 45) == r.smoke_result()
    assert len(steps) == 8 and [v["architecture_id"] for v in built] == [
        "lstm",
        "compact_attention",
        "lstm",
        "compact_attention",
    ]
    assert all(
        v["feature_count"] == 8
        and v["hidden_size"] == 16
        and v["attention_heads"] == 2
        and v["tcn_kernel_size"] == 3
        for v in built
    )


def test_neural_final_128_epoch_recipe_on_small_synthetic_only(monkeypatch):
    torch = pytest.importorskip("torch")
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    steps = []
    step = torch.optim.Adam.step

    def adam(self, *args, **kw):
        steps.append(1)
        return step(self, *args, **kw)

    monkeypatch.setattr(torch.optim.Adam, "step", adam)
    x = np.sin(np.arange(4 * 12 * 8, dtype=np.float64).reshape(4, 12, 8))
    a, b = r.standardized(x, x[:2])
    for name in r.MODELS[2:]:
        y = r.fit_network(
            torch, name, a, np.array([-3.0, 2.0, 7.0, 9.0]), b, "cpu", time.monotonic() + 45
        )
        assert y.shape == (2,) and np.isfinite(y).all()
    assert len(steps) == 256


def test_four_actual_fit_geometry_order_fixed_hurdle_no_comparison_targets(
    panel, feedback, monkeypatch
):
    pytest.importorskip("torch")
    calls = []

    def ridge(x, y, z):
        calls.append(x.shape[-1])
        assert x.shape == (1296, x.shape[-1]) and z.shape == (96, x.shape[-1])
        np.testing.assert_array_equal(y, np.asarray(feedback[0], dtype=np.float64))
        return np.array([6.0, 6.001, 5.0, 7.0] * 24)

    def network(torch, name, x, y, z, device, deadline, **kw):
        calls.append(name)
        assert x.shape == (1296, 12, 8) and z.shape == (96, 12, 8) and device == "cuda"
        assert "epochs" not in kw
        return np.array([6.0, 6.001, 5.0, 7.0] * 24)

    monkeypatch.setattr(r, "fit_ridge", ridge)
    monkeypatch.setattr(r, "fit_network", network)
    counts = dict.fromkeys(r.MODELS, 0)
    result = r.fit_actions(panel[0], feedback[0], counts, time.monotonic() + 30)
    assert calls == [4, 8, "paired_lstm", "paired_attention"] and counts == dict.fromkeys(
        r.MODELS, 1
    )
    assert all(bits == (False, True, False, True) * 24 for bits in result[:4])
    assert type(result) is tuple
    with pytest.raises(ValueError, match="fit_retry"):
        r.fit_actions(panel[0], feedback[0], counts, time.monotonic() + 30)


def test_comparison_never_enters_train_scaler_or_targets(panel, feedback, monkeypatch):
    pytest.importorskip("torch")
    seen = []

    def ridge(x, y, z):
        seen.append((x.copy(), y.copy()))
        return np.zeros(96)

    def network(torch, name, x, y, z, device, deadline, **kw):
        seen.append((x.copy(), y.copy()))
        return np.zeros(96)

    monkeypatch.setattr(r, "fit_ridge", ridge)
    monkeypatch.setattr(r, "fit_network", network)
    r.fit_actions(panel[0], feedback[0], dict.fromkeys(r.MODELS, 0), time.monotonic() + 30)
    revised = tuple(
        replace(
            w,
            features=tuple(v + 1e6 for v in w.features),
            sequence=tuple(tuple(v + 1e6 for v in row) for row in w.sequence),
        )
        if w.key.session_date in r.COMPARISON
        else w
        for w in panel[0]
    )
    r.fit_actions(revised, feedback[0], dict.fromkeys(r.MODELS, 0), time.monotonic() + 30)
    for a, b in zip(seen[:4], seen[4:], strict=True):
        np.testing.assert_array_equal(a[0], b[0])
        np.testing.assert_array_equal(a[1], b[1])


def test_48_cost_invariant_cells_exact_replay_no_fit(
    panel, feedback, evaluation, checks, monkeypatch
):
    assert len(evaluation["cells"]) == 48 and len(evaluation["daily"]) == 24
    for symbol, _ in r.TARGETS:
        for policy in r.POLICIES:
            cells = [
                c for c in evaluation["cells"] if c["symbol"] == symbol and c["policy"] == policy
            ]
            assert (
                len({c["action_sha256"] for c in cells}) == len({c["trades"] for c in cells}) == 1
            )
            for c in cells:
                with localcontext() as ctx:
                    ctx.prec = 50
                    assert (
                        Decimal(c["mean_net_unit_bps"])
                        == (
                            Decimal(c["gross_sum_unit_bps"])
                            - 2 * Decimal(c["cost_per_side_bps"]) * c["trades"]
                        )
                        / 48
                    )
    monkeypatch.setattr(r, "fit_actions", lambda *_: pytest.fail("readback fit"))
    r.verify_evaluation(panel[0], *feedback, evaluation, causal_checks=checks)
    assert not any(s in r.encode(evaluation).decode() for s in ("weights", "forecasts", "labels"))


def test_shared_day_and_etf_deletion_formula(evaluation):
    with localcontext() as ctx:
        ctx.prec = 50
        nets = {
            (d["symbol"], d["date"]): {
                p["policy"]: (Decimal(p["gross_sum_unit_bps"]) - 12 * p["trades"]) / 4
                for p in d["policies"]
            }
            for d in evaluation["daily"]
        }
        for base in r.MODELS[:2]:
            delta = {k: v["paired_attention"] - v[base] for k, v in nets.items()}
            assert abs(
                Decimal(evaluation["descriptive"]["increments"][base]) - sum(delta.values()) / 24
            ) < Decimal("1e-45")
            assert Decimal(
                evaluation["descriptive"]["min_leave_one_ETF_out_increments"][base]
            ) == min(
                sum(v for (s, d), v in delta.items() if s != symbol) / 12 for symbol, _ in r.TARGETS
            )
            expected = min(
                sum(v for (s, d), v in delta.items() if d != str(day)) / 22 for day in r.COMPARISON
            )
            assert abs(
                Decimal(evaluation["descriptive"]["min_leave_one_shared_day_out_increments"][base])
                - expected
            ) < Decimal("1e-45")


@pytest.mark.parametrize(
    "fault",
    (
        "cells",
        "daily",
        "commit",
        "cost",
        "net",
        "trades",
        "kill",
        "control",
        "order",
        "causal",
        "target",
    ),
)
def test_exact_replay_rejects_tampering(panel, feedback, evaluation, actions, checks, fault):
    value = copy.deepcopy(evaluation)
    gross = feedback[1]
    if fault in ("cells", "daily"):
        value[fault].pop()
    elif fault == "commit":
        value["commit_sha256"] = PIN
    elif fault == "cost":
        value["cells"][0]["cost_per_side_bps"] = "2"
    elif fault == "net":
        value["cells"][0]["mean_net_unit_bps"] = "999"
    elif fault == "trades":
        value["daily"][0]["policies"][0]["trades"] = True
    elif fault == "kill":
        value["descriptive"]["kill_categories"] = []
    elif fault == "control":
        changed = (*actions[:-1], (False,) * 96)
        value = r.aggregate(panel[0], gross, changed, causal_checks=checks)
    elif fault == "order":
        value["daily"].reverse()
    elif fault == "causal":
        value["causal_checks"]["prefix_invariant"] = False
    else:
        gross = (feedback[1][0] + Decimal(19), *feedback[1][1:])
    with pytest.raises(ValueError):
        r.verify_evaluation(panel[0], feedback[0], gross, value, causal_checks=checks)


@pytest.fixture
def metadata(monkeypatch):
    indices, pins = {}, {t[0]: {} for t in r.TARGETS}
    for symbol, exchange in r.TARGETS:
        for day in r.DATES:
            session = r.us_equity_2026_session(day).window
            initial, final = (
                dict(next="1", keyb=f"{day:%Y%m%d}155900"),
                dict(next="1", keyb=f"{day:%Y%m%d}075900"),
            )
            target_key = f"{symbol}/{exchange}/1m"
            stamps = {
                (session.open_ts + i * r.MINUTE)
                .astimezone(ZoneInfo("Asia/Seoul"))
                .strftime("%Y%m%dT%H%M%S"): PIN
                for i in range(-90, 390)
            }
            chunk = dict(
                chunk_key=_legacy_chunk_key(target_key=target_key, input_cursor=initial),
                input_cursor=initial,
                output_cursor=final,
                manifest_path="snapshots/unit/manifest.json",
                manifest_hash=PIN,
                raw_sha256=PIN,
                raw_market_data_retained=True,
                row_count=480,
                row_fingerprints=stamps,
                exact_overlap_rows=0,
                conflicting_overlap_rows=0,
                collected_at_utc=(session.close_ts + r.MINUTE).isoformat(),
                outcome="committed",
                reason=None,
                collection_scope="historical",
            )
            index = dict(
                schema_version=1,
                kind="kis_paper_private_intraday_backfill",
                backfill_version="v1",
                generation=1,
                targets=[
                    dict(
                        target_key=target_key,
                        symbol=symbol,
                        exchange=exchange,
                        next_cursor=final,
                        chunks=[chunk],
                    )
                ],
            )
            indices[symbol, day] = index
            pins[symbol][str(day)] = r.digest(r.encode(index))

    def read(path, limit=0):
        assert path.name == "index.json" and limit == cli.INDEX_LIMIT
        symbol = "QQQ" if "qqq-" in path.as_posix() else "SPY"
        day = next(d for d in r.DATES if d.strftime("%Y%m%d") in path.as_posix())
        return r.encode(indices[symbol, day])

    monkeypatch.setattr(cli.h, "_read", read)
    monkeypatch.setattr(cli.h, "_json", lambda *_: {"safe": "metadata"})
    monkeypatch.setattr(
        cli.q.data, "_validate_manifest", lambda **kw: ("rows.csv.gz", kw["chunk"]["raw_sha256"])
    )
    monkeypatch.setattr(
        cli.q.data,
        "load_verified_kis_paper_private_intraday_catalog",
        lambda **_: pytest.fail("metadata raw access"),
    )
    return indices, pins


def test_metadata_50_explicit_dated_sources_stable_loader_ids_no_old_mutation(metadata):
    sources = [
        s
        for t in r.TARGETS
        for s in cli.source_metadata(Path("/synthetic"), metadata[1][t[0]], target=t)
    ]
    assert len(sources) == len({s["dataset_sha256"] for s in sources}) == 50
    assert len(cli.q.r.DATES) == 20
    for target in r.TARGETS:
        rows = [s for s in sources if s["symbol"] == target[0]]
        assert [s["date"] for s in rows] == [str(d) for d in r.DATES]
        assert all(s["dataset_id"] == r.dataset_id(target) for s in rows)
        assert all(s["root"] == target[0].lower() + "-" + s["date"].replace("-", "") for s in rows)
    assert "row_fingerprints" not in r.encode(sources).decode()


@pytest.mark.parametrize(
    "fault", ("short_pins", "hash", "date", "cursor", "missing_minute", "wrong_target")
)
def test_metadata_malformed_scope_rejected(metadata, fault):
    indices, pins = metadata
    day = r.DATES[0]
    target = r.TARGETS[0]
    pinmap = pins["QQQ"].copy()
    index = indices["QQQ", day]
    chunk = index["targets"][0]["chunks"][0]
    if fault == "short_pins":
        pinmap.pop(str(day))
    elif fault == "hash":
        pinmap[str(day)] = PIN
    elif fault == "date":
        chunk["input_cursor"]["keyb"] = "20260827155900"
    elif fault == "cursor":
        chunk["output_cursor"]["keyb"] = "20260828075901"
    elif fault == "missing_minute":
        stamp = (
            r.us_equity_2026_session(day)
            .window.open_ts.astimezone(ZoneInfo("Asia/Seoul"))
            .strftime("%Y%m%dT%H%M%S")
        )
        chunk["row_fingerprints"].pop(stamp)
        chunk["row_count"] -= 1
    else:
        target = ("QQQ", "AMS")
    if fault in ("date", "cursor", "missing_minute"):
        pinmap[str(day)] = r.digest(r.encode(index))
    with pytest.raises(ValueError):
        cli.source_metadata(Path("/synthetic"), pinmap, target=target)


def contract():
    return dict(
        name=r.NAME,
        config=cli.configuration(),
        runtime={"torch": "pinned"},
        sources=[
            dict(
                date=str(d),
                root=t[0].lower() + "-" + d.strftime("%Y%m%d"),
                index_sha256=PIN,
                dataset_id=r.dataset_id(t),
                dataset_sha256=r.digest(r.encode([t, str(d)])),
                manifests={},
                symbol=t[0],
                exchange=t[1],
            )
            for t, d in r.product(r.TARGETS, r.DATES)
        ],
        code_sha256={"owned": PIN},
    )


def test_proposed_metadata_only_no_raw_writes_or_old_fixed_reader(monkeypatch):
    seen = []

    def metadata(inputs, pins, *, target):
        seen.append(target)
        assert len(pins) == 25
        return [s for s in contract()["sources"] if s["symbol"] == target[0]]

    monkeypatch.setattr(cli, "source_metadata", metadata)
    monkeypatch.setattr(cli.q, "source_metadata", lambda *_, **__: pytest.fail("old20 reader"))
    monkeypatch.setattr(cli, "runtime", lambda: {"torch": "pinned"})
    monkeypatch.setattr(cli.h, "_read", lambda *_: b"public code")
    monkeypatch.setattr(cli, "atomic", lambda *_: pytest.fail("metadata write"))
    value = cli.proposed(
        Path("/synthetic"), {s: {str(d): PIN for d in r.DATES} for s, _ in r.TARGETS}
    )
    assert seen == list(r.TARGETS) and len(value["sources"]) == 50
    assert "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py" in cli.CODE
    assert "src/thericher_v2/execution/kis_market_data.py" in cli.CODE


def test_freeze_external_immutable_no_labels_and_no_holdout_registry(tmp_path, monkeypatch):
    artifacts, inputs = tmp_path / "artifacts", tmp_path / "inputs"
    (artifacts / "research").mkdir(parents=True)
    inputs.mkdir()
    monkeypatch.setattr(cli, "_external_location", lambda *_: True)
    value, calls = contract(), []
    monkeypatch.setattr(cli, "proposed", lambda *_: value)
    monkeypatch.setattr(cli.q, "register_frozen_campaign", lambda **kw: calls.append(kw))
    pin = cli.freeze(artifacts, inputs, {})
    output = artifacts / "research" / r.NAME
    assert {p.name for p in output.iterdir()} == {"precommit.json"}
    assert calls[0]["holdout_access"] == "none" and calls[0]["contract_hash"] == pin
    with pytest.raises(FileExistsError):
        cli.freeze(artifacts, inputs, {})


@pytest.mark.parametrize(
    "fault", ("config", "code_sha256", "runtime", "sources", "order", "subset", "peer")
)
def test_contract_pin_rejects_mutation(tmp_path, monkeypatch, fault):
    value = contract()
    cli.atomic(tmp_path / "precommit.json", value)
    monkeypatch.setattr(cli, "paths", lambda *_: tmp_path)
    monkeypatch.setattr(cli, "proposed", lambda *_: copy.deepcopy(value))
    pin = r.digest(r.encode(value))
    assert cli.verify_contract(tmp_path, tmp_path, pin)[1] == value
    changed = copy.deepcopy(value)
    if fault in ("order", "subset", "peer"):
        if fault == "order":
            changed["sources"].reverse()
        elif fault == "subset":
            changed["sources"].pop()
        else:
            changed["sources"][0]["exchange"] = "AMS"
        monkeypatch.setattr(cli.h, "_json", lambda *_: changed)
    else:
        changed[fault] = {}
        monkeypatch.setattr(cli, "proposed", lambda *_: changed)
    with pytest.raises(ValueError):
        cli.verify_contract(tmp_path, tmp_path, pin)


def smoke_receipt():
    return dict(
        name=r.NAME,
        contract_sha256=PIN,
        phase="cpu-smoke",
        status="complete",
        fits_started=dict.fromkeys(r.MODELS, 0),
        smoke=r.smoke_result(),
    )


def completed(panel, evaluation):
    return dict(
        name=r.NAME,
        contract_sha256=PIN,
        phase="cuda",
        status="complete",
        fits_started=dict.fromkeys(r.MODELS, 1),
        cohort_sha256=cli.cohort_hash(panel[0]),
        evaluation=copy.deepcopy(evaluation),
        worker_elapsed_seconds=1.0,
        peak_cuda_bytes=1234,
    )


def dispatch_setup(tmp_path, monkeypatch, cuda=True):
    cli.atomic(tmp_path / "precommit.json", {})
    smoke = smoke_receipt()
    if cuda:
        cli.atomic(tmp_path / "cpu-smoke-started.json", dict(contract_sha256=PIN))
        cli.atomic(tmp_path / "cpu-smoke-worker.json", smoke)
        cli.atomic(tmp_path / "cpu-smoke-summary.json", smoke)
    monkeypatch.setattr(cli, "verify_contract", lambda *_: (tmp_path, {}))
    monkeypatch.setattr(
        cli, "resolve_agent_root", lambda _: tmp_path.parent / (tmp_path.name + "-control")
    )
    monkeypatch.setattr(cli.q, "register_campaign_outcome", lambda **_: None)
    return r.digest(r.encode(smoke))


@pytest.mark.parametrize("candidate", (False, True))
def test_supervisor_timeout_preserves_partial_immutable_counts_no_retry(
    tmp_path, monkeypatch, candidate
):
    pin = dispatch_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "GpuFileLock", lambda _: nullcontext())

    def supervise(*_, **kw):
        assert 0 < kw["seconds"] <= 500
        if candidate:
            cli.atomic(
                tmp_path / "cuda-worker.json",
                cli.failure(
                    PIN,
                    "cuda",
                    "fit",
                    dict(own_ridge=1, paired_ridge=1, paired_lstm=0, paired_attention=0),
                ),
            )
        return dict(timed_out=True, exit_code=-1)

    monkeypatch.setattr(cli.runpy, "run_path", lambda *_: dict(supervise=supervise))
    result = cli.dispatch(tmp_path, tmp_path, PIN, "cuda", pin)
    assert result["status"] == "failed"
    assert result["fits_started"] == (
        dict(own_ridge=1, paired_ridge=1, paired_lstm=0, paired_attention=0)
        if candidate
        else "unobserved"
    )
    original = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    with pytest.raises(ValueError, match="single_attempt"):
        cli.dispatch(tmp_path, tmp_path, PIN, "cuda", pin)
    assert original == {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}


@pytest.mark.parametrize("tamper", (False, True))
def test_canonical_gpu_lock_held_through_reaping_and_validation(
    tmp_path, monkeypatch, panel, evaluation, tamper
):
    pin = dispatch_setup(tmp_path, monkeypatch)
    events = []

    class Lock:
        def __init__(self, path):
            assert path == cli.resolve_agent_root(tmp_path) / "locks/gpu.lock"

        def __enter__(self):
            events.append("locked")

        def __exit__(self, *_):
            assert "reaped" in events
            events.append("released")

    value = completed(panel, evaluation)
    if tamper:
        value["evaluation"]["cells"][0]["mean_net_unit_bps"] = "999"

    def supervise(*_, **kw):
        assert events == ["locked"] and 0 < kw["seconds"] <= 500
        cli.atomic(tmp_path / "cuda-worker.json", value)
        events.append("reaped")
        return dict(timed_out=False, exit_code=0)

    monkeypatch.setattr(cli, "GpuFileLock", Lock)
    monkeypatch.setattr(cli, "load_panel", lambda *_: panel)
    monkeypatch.setattr(cli.runpy, "run_path", lambda *_: dict(supervise=supervise))
    result = cli.dispatch(tmp_path, tmp_path, PIN, "cuda", pin)
    assert result["status"] == ("failed" if tamper else "complete")
    assert events == ["locked", "reaped", "released"]


def test_smoke_dispatch_cannot_touch_gpu_custody(tmp_path, monkeypatch):
    dispatch_setup(tmp_path, monkeypatch, False)
    monkeypatch.setattr(cli, "GpuFileLock", lambda *_: pytest.fail("smoke GPU lock"))
    monkeypatch.setattr(cli, "resolve_agent_root", lambda *_: pytest.fail("smoke GPU root"))

    def supervise(*_, **__):
        cli.atomic(tmp_path / "cpu-smoke-worker.json", smoke_receipt())
        return dict(timed_out=False, exit_code=0)

    monkeypatch.setattr(cli.runpy, "run_path", lambda *_: dict(supervise=supervise))
    assert cli.dispatch(tmp_path, tmp_path, PIN, "cpu-smoke")["status"] == "complete"


def test_worker_seals_before_any_comparison_payoff_and_telemetry_only(
    tmp_path, panel, feedback, actions, checks, monkeypatch
):
    torch = pytest.importorskip("torch")
    events = []
    monkeypatch.setenv("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    monkeypatch.setattr(cli, "verify_contract", lambda *_: (tmp_path, {}))
    monkeypatch.setattr(cli.h, "_json", lambda *_: dict(contract_sha256=PIN))
    monkeypatch.setattr(cli, "load_panel", lambda *_: panel)
    for name, fn in (
        ("is_available", lambda: True),
        ("reset_peak_memory_stats", lambda: None),
        ("synchronize", lambda: None),
        ("max_memory_allocated", lambda: 1234),
    ):
        monkeypatch.setattr(torch.cuda, name, fn)
    monkeypatch.setattr(r, "causal_audit", lambda *_: checks)

    def fit(windows, train, counts, deadline, **kw):
        assert train == feedback[0] and kw["device"] == "cuda"
        counts.update(dict.fromkeys(r.MODELS, 1))
        events.append("fit_infer")
        return actions

    def payoff(windows, catalogs, dates):
        if dates == r.TRAIN:
            events.append("TRAIN")
            return feedback[0]
        assert events == ["TRAIN", "fit_infer", "commit"]
        events.append("COMPARE")
        return feedback[1]

    original = r.commitment

    def seal(bits):
        if "COMPARE" not in events:
            events.append("commit")
        return original(bits)

    monkeypatch.setattr(r, "fit_actions", fit)
    monkeypatch.setattr(r, "payoffs", payoff)
    monkeypatch.setattr(r, "commitment", seal)
    cli.worker(tmp_path, tmp_path, PIN, "cuda", time.monotonic() + 30)
    result = json.loads((tmp_path / "cuda-worker.json").read_bytes())
    assert events[:4] == ["TRAIN", "fit_infer", "commit", "COMPARE"]
    assert result["status"] == "complete" and result["peak_cuda_bytes"] == 1234
    assert 0 <= result["worker_elapsed_seconds"] < 30


def test_verify_all_ro_no_fit_write_or_lock_admits_unretained_inference(
    tmp_path, monkeypatch, panel, evaluation
):
    dispatch_setup(tmp_path, monkeypatch)
    value = completed(panel, evaluation)
    cli.atomic(tmp_path / "cuda-started.json", dict(contract_sha256=PIN))
    cli.atomic(tmp_path / "cuda-worker.json", value)
    cli.atomic(tmp_path / "cuda-summary.json", value)
    monkeypatch.setattr(cli, "load_panel", lambda *_: panel)
    monkeypatch.setattr(r, "fit_actions", lambda *_: pytest.fail("verify fit"))
    monkeypatch.setattr(cli, "atomic", lambda *_: pytest.fail("verify writes"))
    monkeypatch.setattr(cli, "GpuFileLock", lambda *_: pytest.fail("verify lock"))
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    result = cli.readback(tmp_path, tmp_path, PIN, r.digest(r.encode(value)))
    assert result["status"] == "verified_complete" and result["cells"] == 48
    assert result["learned_inference_reconstructed"] is False
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}


@pytest.mark.parametrize("stage", cli.STAGES)
def test_categorical_failure_no_raw_errors_and_strict_counts(stage):
    counts = dict(own_ridge=1, paired_ridge=0, paired_lstm=0, paired_attention=0)
    value = cli.failure(PIN, "cuda", stage, counts)
    cli.validate_result(value, PIN, "cuda")
    value["failure_stage"] = "private message"
    with pytest.raises(ValueError):
        cli.validate_result(value, PIN, "cuda")
    counts["own_ridge"] = True
    value["failure_stage"] = stage
    with pytest.raises(ValueError):
        cli.validate_result(value, PIN, "cuda")


def test_preview_no_io_secret_access_or_error_leak(monkeypatch, capsys):
    def forbidden(*_, **__):
        pytest.fail("preview operational IO")

    for name in ("freeze", "dispatch", "readback", "runtime", "proposed", "paths"):
        monkeypatch.setattr(cli, name, forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    assert cli.main([]) == 0
    assert json.loads(capsys.readouterr().out)["actual_fits"] == 4
    assert cli.main(["--cuda", "--contract-sha256", "private-value"]) == 1
    assert "private-value" not in capsys.readouterr().out
    assert cli.main(["--contract-sha256", PIN]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "unavailable"


def test_native_preview_no_runtime_dispatch():
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT)], capture_output=True, text=True, timeout=20, check=False
    )
    assert result.returncode == 0 and json.loads(result.stdout)["status"] == "preview"
    assert not result.stderr


def test_cli_import_preserves_caller_cublas_environment():
    code = (
        "import os,runpy; os.environ['CUBLAS_WORKSPACE_CONFIG']='caller-sentinel'; "
        f"runpy.run_path({str(SCRIPT)!r}); "
        "assert os.environ['CUBLAS_WORKSPACE_CONFIG']=='caller-sentinel'; print('preserved')"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", code], capture_output=True, text=True, timeout=20, check=False
    )
    assert result.returncode == 0 and result.stdout.strip() == "preserved" and not result.stderr


@pytest.mark.parametrize("elapsed", (float("nan"), float("inf"), 500.0, True))
def test_complete_telemetry_must_be_finite_bounded_float(panel, evaluation, elapsed):
    value = completed(panel, evaluation)
    value["worker_elapsed_seconds"] = elapsed
    with pytest.raises(ValueError, match="telemetry"):
        cli.validate_result(value, PIN, "cuda")


def test_actual_cuda_rejects_wrong_environment_before_any_fit(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "verify_contract", lambda *_: (tmp_path, {}))
    monkeypatch.setattr(cli.h, "_json", lambda *_: dict(contract_sha256=PIN))
    monkeypatch.setenv("CUBLAS_WORKSPACE_CONFIG", "caller-invalid")
    monkeypatch.setattr(cli, "load_panel", lambda *_: pytest.fail("invalid environment loader"))
    monkeypatch.setattr(r, "fit_actions", lambda *_: pytest.fail("invalid environment fit"))
    cli.worker(tmp_path, tmp_path, PIN, "cuda", time.monotonic() + 30)
    result = json.loads((tmp_path / "cuda-worker.json").read_bytes())
    assert result["status"] == "failed" and result["failure_stage"] == "load"
    assert result["fits_started"] == dict.fromkeys(r.MODELS, 0)


def test_external_roots_not_repo_or_unapproved_drive(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="external_root"):
        cli.paths(cli.REPO, tmp_path)
    monkeypatch.setattr(cli, "_external_location", lambda *_: True)
    with pytest.raises(ValueError, match="root_overlap"):
        cli.paths(tmp_path, tmp_path)


def test_source_code_no_network_credentials_broker_weights_or_holdout_access():
    for path in (
        SCRIPT,
        SCRIPT.parents[1] / "src/thericher_v2/research/kis_paired_lag_development.py",
    ):
        source = path.read_text(encoding="utf-8")
        assert not any(
            s in source
            for s in (
                "KIS_LIVE_",
                "KIS_PAPER_",
                "requests.",
                "urlopen(",
                "LocalPaperBroker(",
                "torch.save(",
                "torch.load(",
                "load_state_dict(",
                "getenv(",
            )
        )
