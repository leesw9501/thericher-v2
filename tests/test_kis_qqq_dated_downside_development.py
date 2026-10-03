"""Synthetic/mocked tests only; no external market roots or container execution."""

import copy
import importlib.util
import json
import socket
import subprocess
import sys
import time
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from sklearn.ensemble import HistGradientBoostingRegressor

from thericher_v2.data.kis_paper_intraday_index_metadata import _legacy_chunk_key
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.research import kis_qqq_dated_downside_development as r

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_kis_qqq_dated_downside_development.py"
spec = importlib.util.spec_from_file_location("qqq_downside_launcher", SCRIPT)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
PIN = "sha256:" + "1" * 64


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", lambda *_: pytest.fail("network forbidden"))
    monkeypatch.setattr(socket, "create_connection", lambda *_: pytest.fail("network forbidden"))


@pytest.fixture(scope="module")
def panel():
    return r.synthetic_panel()


@pytest.fixture(scope="module")
def feedback(panel):
    windows, catalogs = panel
    return (cli.payoffs(windows, catalogs, r.TRAIN), cli.payoffs(windows, catalogs, r.COMPARISON))


@pytest.fixture(scope="module")
def actions(panel, feedback):
    return r.fit_actions(panel[0], feedback[0], dict(linear=0, downside=0), time.monotonic() + 30)


def test_exact_recipe_geometry_and_counts(panel):
    windows, catalogs = panel
    assert len(windows) == 80 and len(catalogs) == 20
    assert len(r.TRAIN) == 10 and len(r.COMPARISON) == 9 and str(r.EMBARGO) == "2026-09-17"
    assert r.PARAMETERS == dict(
        loss="quantile",
        quantile=0.25,
        max_iter=16,
        max_depth=1,
        max_leaf_nodes=2,
        min_samples_leaf=10,
        max_bins=8,
        learning_rate=0.1,
        l2_regularization=1.0,
        early_stopping=False,
        random_state=103,
    )
    assert r.configuration()["budget"]["fits"] == 2
    for w in windows:
        assert len(w.sequence) == 24 and len(w.source_minute_starts) == 120
        assert w.key.entry == w.key.cutoff + r.MINUTE
        assert w.key.exit == w.key.cutoff + 31 * r.MINUTE
    assert len({w.key.dataset_hash for w in windows}) == 20


@pytest.mark.parametrize(
    "kind", ("subset", "duplicate", "order", "foreign", "source", "future", "nonfinite")
)
def test_rejects_broken_cohort(panel, kind):
    windows = list(panel[0])
    if kind == "subset":
        windows.pop()
    elif kind == "duplicate":
        windows[1] = windows[0]
    elif kind == "order":
        windows.reverse()
    elif kind == "foreign":
        windows[0] = replace(windows[0], key=replace(windows[0].key, symbol="SPY"))
    elif kind == "source":
        windows[1] = replace(windows[1], key=replace(windows[1].key, dataset_hash=PIN))
    elif kind == "future":
        windows[0] = replace(windows[0], key=replace(windows[0].key, entry=windows[0].key.cutoff))
    else:
        windows[0] = replace(windows[0], features=(float("nan"), 1.0, 2.0, 3.0))
    with pytest.raises(ValueError):
        r.check_cohort(tuple(windows))


def test_future_bar_mutation_cannot_change_current_features_or_action(panel, feedback, actions):
    windows, catalogs = panel
    day = r.COMPARISON[0]
    catalog = catalogs[day]
    bars = tuple(
        replace(b, open=b.open * 2, high=b.high * 2, low=b.low * 2, close=b.close * 2)
        if b.start_ts == r.us_equity_2026_session(day).window.open_ts + 151 * r.MINUTE
        else b
        for b in catalog.bars
    )
    changed = _cataloged_bars_from_verified_loader(
        dataset_id=catalog.dataset_id,
        dataset_hash=catalog.dataset_hash,
        source_path=catalog.source_path,
        bars=bars,
    )
    prepared = r.data.prepare_kis_paper_intraday_feature_input(changed, session_dates=(day,))
    new_day = r.build_windows(prepared)
    old_day = tuple(w for w in windows if w.key.session_date == day)
    assert new_day[0].features == old_day[0].features and new_day[0].sequence == old_day[0].sequence
    # Preserve the original identity while mutating only synthetic future values.
    replacement = tuple(replace(w, key=old.key) for w, old in zip(new_day, old_day, strict=True))
    changed_windows = tuple(
        replacement[r.OFFSETS.index(int((w.key.cutoff - w.key.session_open) / r.MINUTE))]
        if w.key.session_date == day
        else w
        for w in windows
    )
    new_actions = r.fit_actions(
        changed_windows, feedback[0], dict(linear=0, downside=0), time.monotonic() + 30
    )
    assert all(new_actions[p][0] == actions[p][0] for p in r.POLICIES)
    assert r.gross_bps(replacement[0], changed) != feedback[1][0]


def test_train_only_features_labels_and_fixed_normalization(panel, feedback, monkeypatch):
    captured = {}
    original = r._fit_logistic

    def linear(samples, labels):
        captured["dates"] = {w.key.session_date for w in samples}
        captured["model"] = original(samples, labels)
        captured["labels"] = labels
        return captured["model"]

    monkeypatch.setattr(r, "_fit_logistic", linear)
    changed = tuple(
        replace(w, features=tuple(v + 1000 for v in w.features))
        if w.key.session_date in r.COMPARISON
        else w
        for w in panel[0]
    )
    counts = dict(linear=0, downside=0)
    r.fit_actions(changed, feedback[0], counts, time.monotonic() + 30)
    raw = np.asarray([w.features for w in panel[0] if w.key.session_date in r.TRAIN])
    assert captured["dates"] == set(r.TRAIN) and r.EMBARGO not in captured["dates"]
    assert captured["labels"] == [int(v > 6) for v in feedback[0]]
    assert np.array_equal(captured["model"].means, raw.mean(axis=0))
    assert np.array_equal(captured["model"].scales, np.maximum(raw.std(axis=0), 1e-12))
    assert counts == dict(linear=1, downside=1)


@pytest.mark.parametrize(
    "bad", ((), (1.0,) * 40, (Decimal("NaN"),) * 40, (Decimal("Infinity"),) * 40)
)
def test_malformed_training_targets(panel, bad):
    with pytest.raises(ValueError):
        r.fit_actions(panel[0], bad, dict(linear=0, downside=0), time.monotonic() + 30)


def test_model_recipe_and_timeout_cannot_fit(panel, feedback, monkeypatch):
    calls = []
    monkeypatch.setattr(HistGradientBoostingRegressor, "fit", lambda *_: calls.append("fit"))
    counts = dict(linear=0, downside=0)
    with pytest.raises(ValueError, match="hard_timeout"):
        r.fit_actions(panel[0], feedback[0], counts, time.monotonic() - 1)
    assert not calls and counts == dict(linear=0, downside=0)


def test_synthetic_smoke_deterministic_zero_actual_fits():
    assert r.cpu_smoke(time.monotonic() + 30) == dict(
        synthetic_windows=80, synthetic_fits=4, actual_fits=0, cells=18, verified=True
    )


def test_all_cells_exact_cost_identity_and_readback_without_fit(
    panel, feedback, actions, monkeypatch
):
    result = r.aggregate(panel[0], feedback[1], actions)
    assert len(result["cells"]) == 18
    for p in r.POLICIES:
        cells = [c for c in result["cells"] if c["policy"] == p]
        assert len({c["action_sha256"] for c in cells}) == len({c["trades"] for c in cells}) == 1
        with localcontext() as ctx:
            ctx.prec = 50
            for c in cells:
                assert (
                    Decimal(c["mean_net_unit_bps"])
                    == (
                        Decimal(c["gross_sum_unit_bps"])
                        - 2 * Decimal(c["cost_per_side_bps"]) * c["trades"]
                    )
                    / 36
                )
    monkeypatch.setattr(r, "fit_actions", lambda *_: pytest.fail("readback must not fit"))
    r.verify_evaluation(panel[0], *feedback, result)
    reversed_payoff = tuple(-g for g in feedback[1])
    assert (
        r.aggregate(panel[0], reversed_payoff, actions)["cells"][0]["action_sha256"]
        == result["cells"][0]["action_sha256"]
    )


@pytest.mark.parametrize(
    "kind", ("cell", "cost", "trades", "action", "cash", "days", "kill", "extra")
)
def test_readback_rejects_corruption(panel, feedback, actions, kind):
    result = r.aggregate(panel[0], feedback[1], actions)
    if kind == "cell":
        result["cells"].pop()
    elif kind == "cost":
        result["cells"][0]["cost_per_side_bps"] = "0"
    elif kind == "trades":
        result["daily"][0]["policies"][0]["trades"] = True
    elif kind == "action":
        result["daily"][0]["policies"][0]["action_sha256"] = PIN
    elif kind == "cash":
        record = result["daily"][0]["policies"][4]
        record["action_sha256"] = r.action_hash(
            tuple(w for w in panel[0] if w.key.session_date == r.COMPARISON[0]), (True,) * 4
        )
    elif kind == "days":
        result["daily"].reverse()
    elif kind == "kill":
        result["descriptive"]["kill_categories"] = [{"foreign": "category"}]
    else:
        result["private"] = "not allowed"
    with pytest.raises(ValueError):
        r.verify_evaluation(panel[0], *feedback, result)


def test_kills_use_stress_and_leave_day_out_without_refit(panel, feedback):
    actions = r.controls(panel[0], feedback[0])
    actions.update(downside_q25=(False,) * 36, linear=(False,) * 36, momentum=(False,) * 36)
    result = r.aggregate(panel[0], (Decimal(-10),) * 36, actions)
    assert result["descriptive"]["kill_categories"] == list(r.KILLS)
    assert result["descriptive"]["stress_mean_net_unit_bps"] == "0"


@pytest.fixture
def metadata(monkeypatch):
    indices, pins = {}, {}
    for day in r.DATES:
        session = r.us_equity_2026_session(day).window
        stamps = {
            (session.open_ts + i * r.MINUTE)
            .astimezone(ZoneInfo("Asia/Seoul"))
            .strftime("%Y%m%dT%H%M%S"): PIN
            for i in range(-90, 390)
        }
        initial = dict(next="1", keyb=f"{day:%Y%m%d}155900")
        final = dict(next="1", keyb=f"{day:%Y%m%d}075900")
        chunk = dict(
            chunk_key=_legacy_chunk_key(target_key="QQQ/NAS/1m", input_cursor=initial),
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
            collected_at_utc=(session.close_ts + timedelta(minutes=1)).isoformat(),
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
                    target_key="QQQ/NAS/1m",
                    symbol="QQQ",
                    exchange="NAS",
                    next_cursor=final,
                    chunks=[chunk],
                )
            ],
        )
        indices[day] = index
        pins[str(day)] = r.digest(r.encode(index))

    def read(path, limit=0):
        assert path.name == "index.json" and limit == cli.INDEX_LIMIT
        day = next(d for d in r.DATES if d.strftime("%Y%m%d") in path.as_posix())
        return r.encode(indices[day])

    monkeypatch.setattr(cli.h, "_read", read)
    monkeypatch.setattr(cli.h, "_json", lambda path, pin: {"safe": "metadata"})
    monkeypatch.setattr(
        cli.data, "_validate_manifest", lambda **kw: ("rows.csv.gz", kw["chunk"]["raw_sha256"])
    )
    monkeypatch.setattr(
        cli.data,
        "load_verified_kis_paper_private_intraday_catalog",
        lambda **_: pytest.fail("raw forbidden"),
    )
    return indices, pins


def test_freeze_source_projection_metadata_only_exact_twenty_dates(metadata):
    sources = cli.source_metadata(Path("/synthetic"), metadata[1])
    assert [s["date"] for s in sources] == [str(d) for d in r.DATES]
    assert len({s["dataset_sha256"] for s in sources}) == 20
    assert all(s["root"] == "qqq-" + s["date"].replace("-", "") for s in sources)
    assert all(
        s["manifests"]
        == {"snapshots/unit/manifest.json": dict(manifest_sha256=PIN, raw_sha256=PIN)}
        for s in sources
    )
    assert "row_fingerprints" not in r.encode(sources).decode()
    for day, index in metadata[0].items():
        chunks = index["targets"][0]["chunks"]
        assert len(chunks) == 1 and chunks[0]["row_count"] == 480
        assert chunks[0]["input_cursor"]["keyb"] == f"{day:%Y%m%d}155900"
        assert chunks[0]["output_cursor"]["keyb"] == f"{day:%Y%m%d}075900"
        assert next(s for s in sources if s["date"] == str(day))["dataset_sha256"] == (
            cli.data._dataset_hash(
                index_bytes=r.encode(index), lineage=[dict(manifest_hash=PIN, raw_sha256=PIN)]
            )
        )


def test_metadata_optional_target_preserves_qqq_default_and_spy_custody(metadata):
    indices, pins = metadata
    assert cli.source_metadata(Path("/synthetic"), pins) == cli.source_metadata(
        Path("/synthetic"), pins, target=("QQQ", "NAS")
    )
    for day, index in indices.items():
        state = index["targets"][0]
        state.update(target_key="SPY/AMS/1m", symbol="SPY", exchange="AMS")
        for chunk in state["chunks"]:
            chunk["chunk_key"] = _legacy_chunk_key(
                target_key=state["target_key"], input_cursor=chunk["input_cursor"]
            )
        pins[str(day)] = r.digest(r.encode(index))
    sources = cli.source_metadata(Path("/synthetic"), pins, target=("SPY", "AMS"))
    assert all(s["root"].startswith("spy-") for s in sources)
    assert all(s["dataset_id"] == "kis.paper.private.intraday.spy.ams.m1.v1" for s in sources)
    with pytest.raises(ValueError):
        cli.source_metadata(Path("/synthetic"), pins)


@pytest.mark.parametrize("target", (("SPY", "NAS"), ("QQQ", "AMS"), ["QQQ", "NAS"], None))
def test_metadata_unknown_target_rejected_before_reads(monkeypatch, target):
    monkeypatch.setattr(cli.h, "_read", lambda *_: pytest.fail("unknown target read"))
    with pytest.raises(ValueError, match="target"):
        cli.source_metadata(Path("/synthetic"), {}, target=target)


def _split_recovered_index(index, day):
    state = index["targets"][0]
    original = state["chunks"][0]
    boundary = r.us_equity_2026_session(day).window.open_ts + 270 * r.MINUTE
    first, second = copy.deepcopy(original), copy.deepcopy(original)
    first["row_fingerprints"] = {
        stamp: pin
        for stamp, pin in original["row_fingerprints"].items()
        if cli.data._korea_timestamp_key_to_utc(stamp) >= boundary
    }
    second["row_fingerprints"] = {
        stamp: pin
        for stamp, pin in original["row_fingerprints"].items()
        if cli.data._korea_timestamp_key_to_utc(stamp) < boundary
    }
    first.update(
        row_count=120,
        outcome="partial",
        reason="rate_limited",
        output_cursor=dict(next="1", keyb=f"{day:%Y%m%d}135900"),
    )
    second.update(
        row_count=360,
        input_cursor=copy.deepcopy(first["output_cursor"]),
        manifest_path="snapshots/recovered/manifest.json",
        manifest_hash="sha256:" + "2" * 64,
        raw_sha256="sha256:" + "3" * 64,
        collected_at_utc=(boundary + timedelta(days=1)).isoformat(),
    )
    second["chunk_key"] = _legacy_chunk_key(
        target_key="QQQ/NAS/1m", input_cursor=second["input_cursor"]
    )
    state["chunks"] = [first, second]
    return index


def test_partial_then_recovered_two_chunks_keep_full_480_lineage(metadata, monkeypatch):
    indices, pins = metadata
    day = r.DATES[5]  # September10: first120 + resumed360, not a merged replacement.
    index = _split_recovered_index(indices[day], day)
    pins[str(day)] = r.digest(r.encode(index))
    observed = []
    validator = cli._validate_dated_qqq_state

    def validate(index, *, session_date, observed_at, target=("QQQ", "NAS")):
        observed.append((session_date, observed_at))
        return validator(index, session_date=session_date, observed_at=observed_at, target=target)

    monkeypatch.setattr(cli, "_validate_dated_qqq_state", validate)
    source = next(s for s in cli.source_metadata(Path("/synthetic"), pins) if s["date"] == str(day))
    chunks = index["targets"][0]["chunks"]
    assert [c["row_count"] for c in chunks] == [120, 360]
    assert source["manifests"] == {
        "snapshots/unit/manifest.json": dict(manifest_sha256=PIN, raw_sha256=PIN),
        "snapshots/recovered/manifest.json": dict(
            manifest_sha256="sha256:" + "2" * 64, raw_sha256="sha256:" + "3" * 64
        ),
    }
    assert source["dataset_sha256"] == cli.data._dataset_hash(
        index_bytes=r.encode(index),
        lineage=[
            dict(manifest_hash=c["manifest_hash"], raw_sha256=c["raw_sha256"]) for c in chunks
        ],
    )
    assert dict(observed)[day].isoformat() == max(c["collected_at_utc"] for c in chunks)


@pytest.mark.parametrize(
    "change",
    (
        "null_current",
        "null_input",
        "null_output",
        "non_dated",
        "foreign_date",
        "wrong_initial",
        "broken_chain",
        "reordered",
        "chunk_frontier",
    ),
)
def test_nine_malformed_dated_custodies_reject_before_manifests_targets_or_registry(
    metadata, monkeypatch, change
):
    indices, pins = metadata
    day = r.DATES[0]
    index = _split_recovered_index(indices[day], day)
    state = index["targets"][0]
    first, second = state["chunks"]
    if change == "null_current":
        state["next_cursor"] = None
    elif change == "null_input":
        first["input_cursor"] = None
    elif change == "null_output":
        second["output_cursor"] = None
    elif change == "non_dated":
        first["collection_scope"] = "head"
    elif change == "foreign_date":
        state["next_cursor"] = dict(next="1", keyb="20260901075900")
    elif change == "wrong_initial":
        first["input_cursor"]["keyb"] = f"{day:%Y%m%d}155800"
    elif change == "broken_chain":
        second["input_cursor"]["keyb"] = f"{day:%Y%m%d}135800"
    elif change == "reordered":
        state["chunks"].reverse()
    else:
        second["output_cursor"]["keyb"] = f"{day:%Y%m%d}075800"
        state["next_cursor"] = copy.deepcopy(second["output_cursor"])
    for chunk in state["chunks"]:
        chunk["chunk_key"] = _legacy_chunk_key(
            target_key="QQQ/NAS/1m", input_cursor=chunk["input_cursor"]
        )
    pins[str(day)] = r.digest(r.encode(index))

    def forbidden(*_, **__):
        pytest.fail("custody must reject before manifests/raw targets/registry")

    monkeypatch.setattr(cli.h, "_json", forbidden)
    monkeypatch.setattr(cli.data, "load_verified_kis_paper_private_intraday_catalog", forbidden)
    monkeypatch.setattr(cli, "register_frozen_campaign", forbidden)
    with pytest.raises(ValueError):
        cli.source_metadata(Path("/synthetic"), pins)


@pytest.mark.parametrize("change", ("foreign_row", "future_row", "before_midnight", "forming_row"))
def test_retained_non_rth_rows_cannot_escape_date_or_observation_bounds(
    metadata, monkeypatch, change
):
    indices, pins = metadata
    day = r.DATES[0]
    chunk = indices[day]["targets"][0]["chunks"][0]
    if change == "forming_row":
        chunk["collected_at_utc"] = (
            r.us_equity_2026_session(day).window.close_ts - r.MINUTE
        ).isoformat()
    else:
        first = next(iter(chunk["row_fingerprints"]))
        instant = cli.data._korea_timestamp_key_to_utc(first)
        chunk["row_fingerprints"].pop(first)
        instant = (
            instant - timedelta(days=1)
            if change == "foreign_row"
            else r.us_equity_2026_session(day).window.close_ts
            if change == "future_row"
            else r.us_equity_2026_session(day).window.open_ts - timedelta(hours=9, minutes=30)
        )
        chunk["row_fingerprints"][
            instant.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y%m%dT%H%M%S")
        ] = PIN
    pins[str(day)] = r.digest(r.encode(indices[day]))
    monkeypatch.setattr(cli.h, "_json", lambda *_: pytest.fail("reject before manifests"))
    with pytest.raises(ValueError):
        cli.source_metadata(Path("/synthetic"), pins)


@pytest.mark.parametrize("change", ("missing", "pin", "partial", "foreign", "head", "manifest"))
def test_metadata_contract_failures_before_raw_or_fits(metadata, monkeypatch, change):
    indices, pins = metadata
    if change == "missing":
        pins.pop(str(r.DATES[0]))
    elif change == "pin":
        pins[str(r.DATES[0])] = PIN
    elif change == "manifest":
        monkeypatch.setattr(
            cli.h, "_json", lambda *_: (_ for _ in ()).throw(ValueError("bad manifest"))
        )
    else:
        index = indices[r.DATES[0]]
        chunk = index["targets"][0]["chunks"][0]
        if change == "partial":
            stamp = (
                r.us_equity_2026_session(r.DATES[0])
                .window.open_ts.astimezone(ZoneInfo("Asia/Seoul"))
                .strftime("%Y%m%dT%H%M%S")
            )
            chunk["row_fingerprints"].pop(stamp)
            chunk["row_count"] -= 1
        elif change == "foreign":
            index["targets"][0]["symbol"] = "SPY"
        else:
            chunk["collection_scope"] = "head"
        pins[str(r.DATES[0])] = r.digest(r.encode(index))
    with pytest.raises(ValueError):
        cli.source_metadata(Path("/synthetic"), pins)


def test_preview_no_operational_io_or_private_output(monkeypatch, capsys):
    def forbidden(*_, **__):
        pytest.fail("preview IO")

    for name in ("freeze", "dispatch", "readback", "runtime", "source_metadata"):
        monkeypatch.setattr(cli, name, forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    assert cli.main([]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "preview"
    assert cli.main(["--cpu", "--contract-sha256", "private-string"]) == 1
    output = capsys.readouterr().out
    assert "private-string" not in output and "unavailable" in output


@pytest.mark.parametrize("stage", cli.STAGES)
def test_failure_closed_categories_counts_and_no_exception_values(stage):
    result = cli.failure(PIN, "cpu", stage, dict(linear=1, downside=0))
    cli.validate_result(result, PIN, "cpu")
    result["failure_stage"] = "exception private value"
    with pytest.raises(ValueError):
        cli.validate_result(result, PIN, "cpu")


def test_worker_load_failure_never_fits(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "verify_contract", lambda *_: (tmp_path, {}))
    monkeypatch.setattr(cli.h, "_json", lambda *_: dict(contract_sha256=PIN))
    monkeypatch.setattr(cli, "load_panel", lambda *_: (_ for _ in ()).throw(ValueError("secret")))
    monkeypatch.setattr(r, "fit_actions", lambda *_: pytest.fail("no subset fits"))
    cli.worker(tmp_path, tmp_path, PIN, "cpu", time.monotonic() + 10)
    value = json.loads((tmp_path / "cpu-worker.json").read_bytes())
    assert value["failure_stage"] == "load" and value["fits_started"] == dict(linear=0, downside=0)
    assert "secret" not in json.dumps(value)


@pytest.mark.parametrize("candidate", (False, True))
def test_dispatch_timeout_reports_unobserved_or_verified_counts(tmp_path, monkeypatch, candidate):
    cli.atomic(tmp_path / "precommit.json", {})
    monkeypatch.setattr(cli, "verify_contract", lambda *_: (tmp_path, {}))
    monkeypatch.setattr(cli, "register_campaign_outcome", lambda **_: None)
    monkeypatch.setattr(
        cli.runpy,
        "run_path",
        lambda *_: {"supervise": lambda *_, **__: dict(timed_out=True, exit_code=-1)},
    )
    if candidate:
        # The helper owns this receipt; simulate its write after dispatch starts.
        def supervise(*_, **__):
            cli.atomic(
                tmp_path / "cpu-smoke-worker.json",
                cli.failure(PIN, "cpu-smoke", "fit", dict(linear=1, downside=0)),
            )
            return dict(timed_out=True, exit_code=-1)

        monkeypatch.setattr(cli.runpy, "run_path", lambda *_: {"supervise": supervise})
    result = cli.dispatch(tmp_path, tmp_path, PIN, "cpu-smoke")
    assert result["status"] == "failed"
    assert result["fits_started"] == (dict(linear=1, downside=0) if candidate else "unobserved")
    with pytest.raises(ValueError, match="single_attempt"):
        cli.dispatch(tmp_path, tmp_path, PIN, "cpu-smoke")


def test_contract_code_config_and_runtime_mismatch(tmp_path, monkeypatch):
    contract = dict(
        name=cli.NAME,
        config=cli.configuration(),
        runtime={"torch": "pinned"},
        sources=[dict(date=str(d), index_sha256=PIN) for d in r.DATES],
        code_sha256={"owned": PIN},
    )
    cli.atomic(tmp_path / "precommit.json", contract)
    pin = r.digest(r.encode(contract))
    monkeypatch.setattr(cli, "paths", lambda *_: tmp_path)
    monkeypatch.setattr(cli, "proposed", lambda *_: copy.deepcopy(contract))
    assert cli.verify_contract(tmp_path, tmp_path, pin)[1] == contract
    for key in ("config", "runtime", "code_sha256", "sources"):
        changed = copy.deepcopy(contract)
        changed[key] = {}
        monkeypatch.setattr(cli, "proposed", lambda *_, c=changed: c)
        with pytest.raises(ValueError, match="contract_changed"):
            cli.verify_contract(tmp_path, tmp_path, pin)


def test_actual_readback_no_fit(panel, feedback, actions, tmp_path, monkeypatch):
    evaluation = r.aggregate(panel[0], feedback[1], actions)
    result = dict(
        name=cli.NAME,
        contract_sha256=PIN,
        phase="cpu",
        status="complete",
        fits_started=dict(linear=1, downside=1),
        cohort_sha256=cli.cohort_hash(panel[0]),
        evaluation=evaluation,
    )
    cli.atomic(tmp_path / "cpu-summary.json", result)
    monkeypatch.setattr(cli, "verify_contract", lambda *_: (tmp_path, {}))
    monkeypatch.setattr(cli, "load_panel", lambda *_: panel)
    monkeypatch.setattr(r, "fit_actions", lambda *_: pytest.fail("readback fit forbidden"))
    assert (
        cli.readback(tmp_path, tmp_path, PIN, r.digest(r.encode(result)))["status"]
        == "verified_complete"
    )


def test_native_console_preview():
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT)], capture_output=True, text=True, timeout=15, check=False
    )
    assert result.returncode == 0 and json.loads(result.stdout)["status"] == "preview"
    assert not result.stderr


@pytest.mark.parametrize("version", ("1.6.1", "2.0.0"))
def test_runtime_rejects_changed_library_before_source(monkeypatch, version):
    monkeypatch.setattr(cli.h, "runtime_constraints", lambda: {"torch": "2.7.0+cu128"})
    monkeypatch.setattr(
        cli.importlib.metadata,
        "version",
        lambda name: version if name == "scikit-learn" else "3.6.0",
    )
    with pytest.raises(ValueError, match="sklearn_runtime"):
        cli.runtime()


def test_freeze_immutable_metadata_and_registry_only(tmp_path, monkeypatch):
    contract = dict(name=cli.NAME, metadata_only=True)
    calls = []
    artifacts, inputs = tmp_path / "artifacts", tmp_path / "inputs"
    (artifacts / "research").mkdir(parents=True)
    inputs.mkdir()
    output = artifacts / "research" / cli.NAME
    monkeypatch.setattr(cli, "proposed", lambda *_: contract)
    monkeypatch.setattr(cli, "register_frozen_campaign", lambda **kw: calls.append(kw))
    contract["sources"] = [{"index_sha256": PIN}]
    pin = cli.freeze(artifacts, inputs, {})
    assert json.loads((output / "precommit.json").read_bytes()) == contract
    assert calls[0]["holdout_access"] == "none" and calls[0]["contract_hash"] == pin
    with pytest.raises(FileExistsError):
        cli.freeze(artifacts, inputs, {})


def test_dispatch_validates_full_cpu_replay_before_success(
    tmp_path, panel, feedback, actions, monkeypatch
):
    for name in ("precommit", "cpu-smoke-started", "cpu-smoke-worker"):
        cli.atomic(tmp_path / (name + ".json"), {})
    smoke = dict(
        name=cli.NAME,
        contract_sha256=PIN,
        phase="cpu-smoke",
        status="complete",
        fits_started=dict(linear=0, downside=0),
        smoke=dict(synthetic_windows=80, synthetic_fits=4, actual_fits=0, cells=18, verified=True),
    )
    cli.atomic(tmp_path / "cpu-smoke-summary.json", smoke)
    bad = dict(
        name=cli.NAME,
        contract_sha256=PIN,
        phase="cpu",
        status="complete",
        fits_started=dict(linear=1, downside=1),
        cohort_sha256=cli.cohort_hash(panel[0]),
        evaluation=r.aggregate(panel[0], feedback[1], actions),
    )
    bad["evaluation"]["cells"][0]["mean_net_unit_bps"] = "123456"

    def supervisor(*_, **__):
        cli.atomic(tmp_path / "cpu-worker.json", bad)
        return dict(timed_out=False, exit_code=0)

    monkeypatch.setattr(cli, "verify_contract", lambda *_: (tmp_path, {}))
    monkeypatch.setattr(cli, "load_panel", lambda *_: panel)
    monkeypatch.setattr(cli, "register_campaign_outcome", lambda **_: None)
    monkeypatch.setattr(cli.runpy, "run_path", lambda *_: {"supervise": supervisor})
    result = cli.dispatch(tmp_path, tmp_path, PIN, "cpu", r.digest(r.encode(smoke)))
    assert result["status"] == "failed" and result["fits_started"] == dict(linear=1, downside=1)


def test_payoff_catalog_identity_cannot_be_swapped(panel):
    windows, catalogs = panel
    with pytest.raises(ValueError, match="payoff_source"):
        r.gross_bps(windows[0], catalogs[r.DATES[1]])
