"""Synthetic-only month-start study tests; no retained market data or credentials."""

from __future__ import annotations

import copy
import json
import runpy
import socket
import time
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_UP, Decimal, localcontext
from types import SimpleNamespace

import pytest

from thericher_v2.data import tiingo_etf_daily as daily
from thericher_v2.data.tiingo_etf_daily import TiingoEtfDailyRow
from thericher_v2.research import tiingo_month_start_development as s


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("network, credentials and real data are forbidden in synthetic tests")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(s, "load_verified_tiingo_etf_d1_snapshot", forbidden)


@pytest.fixture(scope="module")
def sessions():
    start, end = date(2000, 12, 1), date(2026, 8, 31)
    return tuple(
        day
        for i in range((end - start).days + 1)
        if (day := start + timedelta(days=i)).weekday() < 5
    )


@pytest.fixture
def contract(sessions, monkeypatch):
    monkeypatch.setattr(s, "calendar_plan", lambda: s.build_plan(sessions))
    return s.proposed_contract()


def make_rows(contract, *, candidate="0.01", control="0.002", price="100"):
    rows = {}
    for symbol in s.SYMBOLS:
        items = []
        for plan in contract["plan"]:
            for policy, change in (("month_start", candidate), ("session_11", control)):
                opening = Decimal(price)
                closing = opening * (1 + Decimal(change))
                items.append(
                    TiingoEtfDailyRow(
                        symbol=symbol,
                        session_date=date.fromisoformat(plan[policy]),
                        open=opening,
                        high=max(opening, closing),
                        low=min(opening, closing),
                        close=closing,
                        volume=Decimal(1000),
                        div_cash=Decimal(0),
                        split_factor=Decimal(1),
                    )
                )
        rows[symbol] = tuple(items)
    return rows


def evaluate(contract, rows=None):
    return s.evaluate(
        make_rows(contract) if rows is None else rows,
        contract,
        s.digest(s.encode(contract)),
        deadline=time.monotonic() + 30,
    )


def cell(result, *, symbol="SPY", period="2013-2019", cost=20, policy="month_start"):
    return next(
        c
        for c in result["cells"]
        if (c["symbol"], c["period"], c["cost_bps"], c["policy"]) == (symbol, period, cost, policy)
    )


def test_exact_matrix_formula_and_six_group_criterion(contract):
    result = evaluate(contract)
    assert result["status"] == "complete"
    assert result["criterion"] == "descriptive_criterion_met"
    assert len(result["cells"]) == 54
    assert [g["scheduled_count"] for g in result["groups"]] == [84, 79] * 3
    assert [g["paired_count"] for g in result["groups"]] == [84, 79] * 3
    for c in result["cells"]:
        gross = {"month_start": Decimal(100), "session_11": Decimal(20), "cash": Decimal(0)}[
            c["policy"]
        ]
        expected = gross - (0 if c["policy"] == "cash" else c["cost_bps"])
        assert Decimal(c["observed_mean_net_bps"]) == expected
        assert Decimal(c["paired_mean_net_bps"]) == expected
        assert c["observed_count"] == c["paired_count"]
    assert Decimal(cell(result)["paired_difference_vs_session_11_bps"]) == 80
    assert result["scope"]["descriptive_only"] is True
    assert result["scope"]["local_paper_parity"] is False


@pytest.mark.parametrize("symbol", s.SYMBOLS)
@pytest.mark.parametrize("period,start,end", s.PERIODS)
def test_every_one_of_six_groups_can_kill_without_tuning(contract, symbol, period, start, end):
    rows = make_rows(contract)
    starts = {p["month_start"] for p in contract["plan"] if p["period"] == period}
    rows[symbol] = tuple(
        replace(r, close=r.open) if r.session_date.isoformat() in starts else r
        for r in rows[symbol]
    )
    result = evaluate(contract, rows)
    assert result["criterion"] == "descriptive_criterion_not_met"
    assert result["status"] == "complete"
    assert len(result["cells"]) == 54


@pytest.mark.parametrize("candidate,control", (("0.002", "0"), ("0.01", "0.01")))
def test_criterion_is_strict_at_zero_and_tie(contract, candidate, control):
    assert (
        evaluate(contract, make_rows(contract, candidate=candidate, control=control))["criterion"]
        == "descriptive_criterion_not_met"
    )


@pytest.mark.parametrize("available,expected", ((59, "input_unavailable"), (60, "complete")))
def test_exact_60_paired_month_floor(contract, available, expected):
    rows = make_rows(contract)
    remove = {p["session_11"] for p in contract["plan"] if p["period"] == "2013-2019"}
    remove = set(sorted(remove)[available:])
    rows["SPY"] = tuple(r for r in rows["SPY"] if r.session_date.isoformat() not in remove)
    result = evaluate(contract, rows)
    assert result["status"] == expected
    assert result["groups"][0]["paired_count"] == available
    assert len(result["cells"]) == 54
    if available == 59:
        assert result["criterion"] == "not_evaluable"
        assert all(c[k] is None for c in result["cells"] for k in s.METRICS)


def test_calendar_keeps_all_earlier_augusts_and_excludes_only_2026_tail(contract):
    months = [p["month"] for p in contract["plan"]]
    assert all(f"{year}-08" in months for year in range(2001, 2026))
    assert months[-1] == "2026-07" and "2026-08" not in months
    assert len(months) == 307
    assert sum(p["period"] == "preparation" for p in contract["plan"]) == 144
    assert "EOD_open_is_not_proven_primary_auction_execution" in contract["config"]["assumptions"]
    assert any("revision_bias" in x for x in contract["config"]["assumptions"])
    assert any("zero_cost_differential" in x for x in contract["config"]["assumptions"])
    assert any("not_causally_clean" in x for x in contract["config"]["assumptions"])


def test_missing_target_does_not_renumber_or_backfill(contract):
    rows = make_rows(contract)
    plan = next(p for p in contract["plan"] if p["month"] == "2013-01")
    target = date.fromisoformat(plan["month_start"])
    original = next(r for r in rows["SPY"] if r.session_date == target)
    extra = replace(
        original, session_date=target + timedelta(days=1), close=Decimal("200"), high=Decimal("200")
    )
    rows["SPY"] = tuple(
        sorted(
            [r for r in rows["SPY"] if r.session_date != target] + [extra],
            key=lambda r: r.session_date,
        )
    )
    result = evaluate(contract, rows)
    group = result["groups"][0]
    assert group["legs"]["month_start"]["censored"] == [
        {"month": "2013-01", "date": target.isoformat(), "reason": "missing_row"}
    ]
    assert group["paired_count"] == 83 and group["pair_censored_count"] == 1
    assert cell(result)["observed_count"] == 83
    assert cell(result, policy="session_11")["observed_count"] == 84
    assert Decimal(cell(result)["paired_mean_net_bps"]) == 80
    assert contract["plan"][144]["month_start"] == target.isoformat()


def test_month_pairing_is_intersection_not_union_and_means_are_distinct(contract):
    rows = make_rows(contract)
    plans = [p for p in contract["plan"] if p["period"] == "2013-2019"]
    missing = {plans[0]["month_start"], plans[1]["session_11"]}
    special = plans[1]["month_start"]
    rows["SPY"] = tuple(
        replace(r, close=Decimal("110"), high=Decimal("110"))
        if r.session_date.isoformat() == special
        else r
        for r in rows["SPY"]
        if r.session_date.isoformat() not in missing
    )
    result = evaluate(contract, rows)
    c = cell(result)
    assert c["observed_count"] == 83 and c["paired_count"] == 82
    assert Decimal(c["observed_mean_net_bps"]) > Decimal(c["paired_mean_net_bps"])
    assert Decimal(c["paired_mean_net_bps"]) == 80


@pytest.mark.parametrize("bad", (Decimal("NaN"), Decimal("Infinity"), Decimal("0"), Decimal("-1")))
def test_invalid_target_is_censored_not_a_decision_filter(contract, bad):
    rows = make_rows(contract)
    target = date(2013, 1, 1)
    rows["SPY"] = tuple(
        replace(r, open=bad) if r.session_date == target else r for r in rows["SPY"]
    )
    result = evaluate(contract, rows)
    assert result["groups"][0]["legs"]["month_start"]["censored"][0]["reason"] == "invalid_ohlc"
    assert result["groups"][0]["scheduled_count"] == 84


def test_future_outcomes_do_not_change_plan_and_prep_outcomes_are_unused(contract):
    original = copy.deepcopy(contract)
    rows = make_rows(contract)
    for symbol in s.SYMBOLS:
        rows[symbol] = tuple(
            replace(r, open=Decimal("NaN"), close=Decimal("NaN"))
            if r.session_date.year < 2013
            else r
            for r in rows[symbol]
        )
    before = evaluate(contract)
    after = evaluate(contract, rows)
    assert before == after
    for symbol in s.SYMBOLS:
        rows[symbol] += (
            replace(rows[symbol][-1], session_date=date(2026, 8, 3), open=Decimal("NaN")),
        )
    assert evaluate(contract, rows) == before
    assert contract == original


def test_scale_invariance_and_event_counts_do_not_mask_any_trade(contract):
    rows = make_rows(contract)
    scaled = {}
    for symbol, stream in rows.items():
        scaled[symbol] = tuple(
            replace(
                r,
                **{
                    k: getattr(r, k) * Decimal(str((i % 13 + 1) / 10))
                    for k in ("open", "high", "low", "close")
                },
                div_cash=Decimal("123.456"),
                split_factor=Decimal("0.5"),
            )
            for i, r in enumerate(stream)
        )
    baseline, changed = evaluate(contract, rows), evaluate(contract, scaled)
    assert changed["cells"] == baseline["cells"]
    assert changed["criterion"] == baseline["criterion"]
    assert all(
        g["legs"][p]["event_observed_count"] == g["scheduled_count"]
        for g in changed["groups"]
        for p in s.POLICIES[:2]
    )


@pytest.mark.parametrize("kind", ("duplicate", "order", "symbol"))
def test_row_identity_kills(contract, kind):
    rows = make_rows(contract)
    if kind == "duplicate":
        rows["SPY"] = rows["SPY"] + (rows["SPY"][-1],)
    elif kind == "order":
        rows["SPY"] = tuple(reversed(rows["SPY"]))
    else:
        rows["SPY"] = (replace(rows["SPY"][0], symbol="QQQ"),) + rows["SPY"][1:]
    with pytest.raises(ValueError):
        evaluate(contract, rows)


def test_wall_deadline_stops_without_partial_results(contract):
    with pytest.raises(ValueError, match="wall_limit"):
        s.evaluate(make_rows(contract), contract, s.digest(s.encode(contract)), deadline=0)


@pytest.mark.parametrize(
    "mutation",
    (
        "config_hash",
        "source_hash",
        "contract_hash",
        "source",
        "header_bool",
        "extra",
        "cell_extra",
        "group_extra",
        "count_bool",
        "pair_count",
        "censor",
        "partial",
        "duplicate",
        "cost",
        "nan",
        "fee",
        "cross_cost",
        "difference",
        "criterion",
        "cash",
    ),
)
def test_result_validator_rejects_tampering(contract, mutation):
    r = evaluate(contract)
    c = r["cells"][0]
    if mutation in {"config_hash", "source_hash", "contract_hash"}:
        r[mutation.replace("_hash", "_sha256")] = "sha256:" + "f" * 64
    elif mutation == "source":
        r["source"] = {**r["source"], "dataset_id": "wrong"}
    elif mutation == "header_bool":
        r["schema_version"] = True
    elif mutation == "extra":
        r["raw_rows"] = ["PRIVATE"]
    elif mutation == "cell_extra":
        c["forecast"] = "PRIVATE"
    elif mutation == "group_extra":
        r["groups"][0]["raw"] = "PRIVATE"
    elif mutation == "count_bool":
        c["observed_count"] = True
    elif mutation == "pair_count":
        r["groups"][0]["paired_count"] -= 1
    elif mutation == "censor":
        r["groups"][0]["legs"]["month_start"]["censored"].append(
            {"month": "2013-01", "date": "2013-01-02", "reason": "PRIVATE"}
        )
    elif mutation == "partial":
        r["cells"].pop()
    elif mutation == "duplicate":
        r["cells"][1] = copy.deepcopy(c)
    elif mutation == "cost":
        c["cost_bps"] = 1
    elif mutation == "nan":
        c[s.METRICS[0]] = "NaN"
    elif mutation == "fee":
        c["observed_mean_net_bps"] = "100.000000000000"
    elif mutation == "cross_cost":
        c["observed_mean_gross_bps"] = "101.000000000000"
        c["observed_mean_net_bps"] = "96.000000000000"
    elif mutation == "difference":
        c[s.METRICS[-1]] = "1.000000000000"
    elif mutation == "criterion":
        r["criterion"] = "descriptive_criterion_not_met"
    elif mutation == "cash":
        r["cells"][2]["paired_mean_net_bps"] = "1.000000000000"
    with pytest.raises((ValueError, KeyError, TypeError)):
        s.validate_result(r, contract, s.digest(s.encode(contract)))


@pytest.fixture
def frozen(contract, tmp_path, monkeypatch):
    artifact, market = tmp_path / "artifacts", tmp_path / "market"
    receipt, manifest = artifact / s.RECEIPT, market / s.SNAPSHOT / "manifest.json"
    receipt.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)
    receipt.write_bytes(b'{"synthetic":"receipt"}\n')
    manifest.write_bytes(b'{"synthetic":"manifest"}\n')
    monkeypatch.setattr(s, "RECEIPT_HASH", s.digest(receipt.read_bytes()))
    monkeypatch.setattr(s, "MANIFEST_HASH", s.digest(manifest.read_bytes()))
    pin = s.freeze(artifact, market)
    output, bound = s.verify(artifact, market, pin)
    return SimpleNamespace(
        artifact=artifact,
        market=market,
        output=output,
        contract=bound,
        pin=pin,
        receipt=receipt,
        manifest=manifest,
    )


def test_metadata_freeze_is_atomic_before_any_loader_and_cannot_overwrite(frozen):
    original = (frozen.output / "precommit.json").read_bytes()
    assert s.digest(original) == frozen.pin
    assert {p.name for p in frozen.output.iterdir()} == {"precommit.json"}
    with pytest.raises(FileExistsError):
        s.freeze(frozen.artifact, frozen.market)
    assert (frozen.output / "precommit.json").read_bytes() == original


def test_atomic_publication_failure_leaves_no_partial_target(tmp_path, monkeypatch):
    def failed(*_):
        raise OSError("synthetic")

    monkeypatch.setattr(s.os, "link", failed)
    with pytest.raises(OSError):
        s.atomic_new(tmp_path / "result.json", {"complete": True})
    assert list(tmp_path.iterdir()) == []


def test_atomic_new_never_replaces_existing_output(tmp_path):
    path = tmp_path / "closed.json"
    path.write_bytes(b"immutable")
    with pytest.raises(FileExistsError):
        s.atomic_new(path, {"replacement": True})
    assert path.read_bytes() == b"immutable"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("which", ("manifest", "receipt", "precommit", "code"))
def test_source_contract_code_tampering_fails_before_loader(frozen, monkeypatch, which):
    if which == "code":
        monkeypatch.setattr(s, "CODE", s.CODE[:-1])
    else:
        path = frozen.output / "precommit.json" if which == "precommit" else getattr(frozen, which)
        path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        s.verify(frozen.artifact, frozen.market, frozen.pin)


def bind_synthetic_loader(frozen, monkeypatch, rows=None, *, bad_identity=False):
    calls = []

    def loader(path, **kwargs):
        assert path == frozen.market / s.SNAPSHOT
        assert kwargs["dataset_id"] == s.DATASET_ID
        assert kwargs["expected_dataset_hash"] == s.DATASET_HASH
        assert kwargs["expected_manifest_hash"] == s.MANIFEST_HASH
        assert kwargs["market_data_root"] == frozen.market
        assert (frozen.output / "precommit.json").is_file()
        assert (frozen.output / "started.json").is_file()
        calls.append(True)
        return SimpleNamespace(
            snapshot=SimpleNamespace(
                dataset_id=s.DATASET_ID,
                dataset_hash="wrong" if bad_identity else s.DATASET_HASH,
                manifest_hash=s.MANIFEST_HASH,
            ),
            rows_by_symbol=make_rows(frozen.contract) if rows is None else rows,
        )

    monkeypatch.setattr(s, "load_verified_tiingo_etf_d1_snapshot", loader)
    return calls


def test_worker_attaches_pinned_loader_after_atomic_precommit_and_attempt(frozen, monkeypatch):
    calls = bind_synthetic_loader(frozen, monkeypatch)
    s.atomic_new(frozen.output / "started.json", {"contract_sha256": frozen.pin})
    path = frozen.output / "worker-result.json"
    s.run_worker(frozen.artifact, frozen.market, frozen.pin, path, time.monotonic() + 30)
    result = json.loads(path.read_bytes())
    assert result["status"] == "complete" and len(result["cells"]) == 54
    assert calls == [True]
    assert result["contract_sha256"] == frozen.pin
    assert result["source_sha256"] == frozen.contract["source_sha256"]
    assert result["config_sha256"] == frozen.contract["config_sha256"]
    assert all(
        k not in path.read_text() for k in ('"open":', '"close":', '"volume":', '"forecast":')
    )


def test_worker_requires_attempt_before_loader(frozen, monkeypatch):
    calls = bind_synthetic_loader(frozen, monkeypatch)
    with pytest.raises(ValueError):
        s.run_worker(
            frozen.artifact, frozen.market, frozen.pin, frozen.output / "worker-result.json", 0
        )
    assert calls == []


def test_worker_rejects_loader_identity_substitution(frozen, monkeypatch):
    bind_synthetic_loader(frozen, monkeypatch, bad_identity=True)
    s.atomic_new(frozen.output / "started.json", {"contract_sha256": frozen.pin})
    path = frozen.output / "worker-result.json"
    s.run_worker(frozen.artifact, frozen.market, frozen.pin, path, time.monotonic() + 30)
    result = json.loads(path.read_bytes())
    assert result == s.failure(frozen.contract, frozen.pin, "runtime_or_invariant_failure")


@pytest.fixture
def runner(frozen, monkeypatch):
    ns = runpy.run_path(str(s.REPO / "scripts/run_tiingo_month_start_development.py"))
    state = SimpleNamespace(ns=ns, calls=[], mode="success")
    bind_synthetic_loader(frozen, monkeypatch)

    def supervise(target, args, *, seconds):
        assert 0 < seconds <= 600
        assert target is ns["worker"]
        state.calls.append(args)
        if state.mode == "interrupt":
            raise KeyboardInterrupt
        if state.mode == "exception":
            raise RuntimeError("PRIVATE")
        if state.mode in {"success", "invalid"}:
            s.run_worker(*args)
            if state.mode == "invalid":
                path = args[-2]
                payload = json.loads(path.read_bytes())
                payload["raw_rows"] = "PRIVATE"
                path.write_bytes(s.encode(payload))
        return {
            "timed_out": state.mode == "timeout",
            "exit_code": 1 if state.mode == "failed" else 0,
        }

    monkeypatch.setitem(ns["dispatch"].__globals__, "supervise", supervise)
    state.argv = [
        "--run",
        "--contract-sha256",
        frozen.pin,
        "--artifact-root",
        str(frozen.artifact),
        "--market-data-root",
        str(frozen.market),
    ]
    return state


def test_cli_single_pass_and_safe_summary(frozen, runner, capsys):
    assert runner.ns["main"](runner.argv) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "complete" and report["cells"] == 54
    original = (frozen.output / "summary.json").read_bytes()
    assert runner.ns["main"](runner.argv) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "dispatch_unavailable"
    assert (frozen.output / "summary.json").read_bytes() == original
    assert len(runner.calls) == 1


@pytest.mark.parametrize(
    "mode,reason",
    (
        ("timeout", "hard_timeout"),
        ("missing", "worker_result_invalid"),
        ("invalid", "worker_result_invalid"),
        ("interrupt", "execution_preempted"),
        ("exception", "worker_result_invalid"),
        ("failed", "worker_failed"),
    ),
)
def test_runner_failure_is_categorical_not_partial_or_private(frozen, runner, capsys, mode, reason):
    runner.mode = mode
    assert runner.ns["main"](runner.argv) == 1
    capsys.readouterr()
    result = json.loads((frozen.output / "summary.json").read_bytes())
    assert result == s.failure(frozen.contract, frozen.pin, reason)
    assert "PRIVATE" not in (frozen.output / "summary.json").read_text()


@pytest.mark.parametrize(
    "existing", ("started.json", "summary.json", "worker-result.json", ".partial")
)
def test_existing_attempt_blocks_only_its_own_namespace(frozen, runner, capsys, existing):
    (frozen.output / existing).write_bytes(b"immutable")
    assert runner.ns["main"](runner.argv) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "dispatch_unavailable"
    assert runner.calls == [] and (frozen.output / existing).read_bytes() == b"immutable"


@pytest.mark.parametrize(
    "argv", ([], ["--run"], ["--freeze", "--contract-sha256", "wrong"], ["--gpu"], ["--cost", "1"])
)
def test_cli_has_no_tuning_or_unbound_run_options(argv):
    ns = runpy.run_path(str(s.REPO / "scripts/run_tiingo_month_start_development.py"))
    with pytest.raises(SystemExit) as error:
        ns["main"](argv)
    assert error.value.code == 2


def test_supervisor_delegates_to_existing_bounded_runner(monkeypatch):
    ns = runpy.run_path(str(s.REPO / "scripts/run_tiingo_month_start_development.py"))
    calls = []
    report = {"timed_out": True, "exit_code": -1}

    def existing(target, arguments, *, seconds, name):
        calls.append((target, arguments, seconds, name))
        return report

    def load(path):
        assert path == str(s.REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py")
        return {"supervise": existing}

    monkeypatch.setattr(ns["runpy"], "run_path", load)
    assert ns["supervise"](ns["worker"], ("synthetic",), seconds=17) is report
    assert calls == [(ns["worker"], ("synthetic",), 17, s.NAME)]


def test_worker_suppresses_private_exceptions(monkeypatch, capsys):
    ns = runpy.run_path(str(s.REPO / "scripts/run_tiingo_month_start_development.py"))

    def fail(*args):
        raise ValueError("PRIVATE")

    monkeypatch.setattr(s, "run_worker", fail)
    with pytest.raises(SystemExit) as error:
        ns["worker"](None, None, None, None, None)
    assert error.value.code == 1
    assert capsys.readouterr().out == ""


def test_existing_supervisor_runs_and_reaps_synthetic_child():
    ns = runpy.run_path(str(s.REPO / "scripts/run_tiingo_month_start_development.py"))
    report = ns["supervise"](time.sleep, (0.01,), seconds=15)
    assert report["name"] == s.NAME
    assert report["exit_code"] == 0 and report["timed_out"] is False


def test_actual_pinned_calendar_ordinals_and_holiday_previous_decision():
    plan = s.calendar_plan()
    first = next(p for p in plan if p["month"] == "2024-01")
    assert first["month_start"] == "2024-01-02"
    assert first["month_start_decision"] == "2023-12-29"
    assert first["session_11"] == "2024-01-17"
    assert first["session_11_decision"] == "2024-01-16"
    assert len(plan) == 307


def test_synthetic_snapshot_through_real_verified_loader(contract, tmp_path, monkeypatch):
    artifact, market = tmp_path / "artifacts", tmp_path / "market"
    snapshot = market / s.SNAPSHOT
    raw_dir = snapshot / "raw"
    raw_dir.mkdir(parents=True)
    rows = make_rows(contract)
    hashes = {}
    for symbol, stream in rows.items():
        payload = [
            {
                "date": r.session_date.isoformat(),
                **{key: str(getattr(r, key)) for key in ("open", "high", "low", "close", "volume")},
                "divCash": str(r.div_cash),
                "splitFactor": str(r.split_factor),
            }
            for r in stream
        ]
        raw = s.encode(payload)
        (raw_dir / f"{symbol}.json").write_bytes(raw)
        hashes[symbol] = s.digest(raw)
    canonical = daily._gzip_bytes(daily._canonical_csv_bytes(rows))
    (snapshot / "ohlcv_1d.csv.gz").write_bytes(canonical)
    manifest = daily._manifest(
        target=snapshot,
        requested_start=date(2001, 1, 1),
        requested_end=date(2026, 7, 31),
        retrieved_at=datetime(2026, 8, 9, tzinfo=UTC),
        canonical_hash=s.digest(canonical),
        canonical_size=len(canonical),
        raw_hashes=hashes,
        rows_by_symbol=rows,
        raw_dir=raw_dir,
        free_percent=50,
    )
    manifest_raw = s.encode(manifest)
    (snapshot / "manifest.json").write_bytes(manifest_raw)
    receipt = artifact / s.RECEIPT
    receipt.parent.mkdir(parents=True)
    receipt.write_bytes(
        s.encode({"synthetic_source": True, "manifest_hash": s.digest(manifest_raw)})
    )
    monkeypatch.setattr(s, "DATASET_HASH", s.digest(canonical))
    monkeypatch.setattr(s, "MANIFEST_HASH", s.digest(manifest_raw))
    monkeypatch.setattr(s, "RECEIPT_HASH", s.digest(receipt.read_bytes()))
    monkeypatch.setattr(
        s, "load_verified_tiingo_etf_d1_snapshot", daily.load_verified_tiingo_etf_d1_snapshot
    )
    pin = s.freeze(artifact, market)
    output, bound = s.verify(artifact, market, pin)
    s.atomic_new(output / "started.json", {"contract_sha256": pin})
    path = output / "worker-result.json"
    s.run_worker(artifact, market, pin, path, time.monotonic() + 30)
    result = json.loads(path.read_bytes())
    assert result["status"] == "complete" and len(result["cells"]) == 54
    s.validate_result(result, bound, pin)
    assert result["criterion"] == "descriptive_criterion_met"
    with pytest.raises(ValueError, match="worker_output_exists"):
        s.run_worker(artifact, market, pin, path, time.monotonic() + 30)


def test_numerical_context_does_not_change_scoring(contract):
    baseline = evaluate(contract)
    with localcontext() as context:
        context.prec = 18
        context.rounding = ROUND_UP
        assert evaluate(contract) == baseline


def test_failure_schema_refuses_bool_integer_substitution(contract):
    pin = s.digest(s.encode(contract))
    result = s.failure(contract, pin, "hard_timeout")
    result["schema_version"] = True
    with pytest.raises(ValueError, match="invalid_failure"):
        s.validate_result(result, contract, pin)


def test_unavailable_cannot_smuggle_performance(contract):
    result = evaluate(contract, {symbol: () for symbol in s.SYMBOLS})
    assert result["status"] == "input_unavailable"
    assert all(c["observed_count"] == 0 for c in result["cells"] if c["policy"] != "cash")
    result["cells"][0]["observed_mean_net_bps"] = "0.000000000000"
    with pytest.raises(ValueError, match="unavailable_metric"):
        s.validate_result(result, contract, s.digest(s.encode(contract)))


def test_no_event_or_price_fields_in_precommit(contract):
    raw = s.encode(contract).decode()
    assert all(key not in raw for key in ('"open":', '"close":', '"volume":', '"forecasts":'))
    assert contract["config"]["budget"] == {
        "cpu_threads": 1,
        "wall_seconds": 600,
        "memory_bytes": 1024**3,
        "gpu": False,
        "passes": 1,
        "training": False,
        "retries": False,
    }


def test_future_evaluation_outcome_changes_scores_never_plans_or_past_period(contract):
    before_plan = copy.deepcopy(contract["plan"])
    rows = make_rows(contract)
    target = next(p["month_start"] for p in contract["plan"] if p["month"] == "2020-08")
    rows["SPY"] = tuple(
        replace(r, close=Decimal(90), low=Decimal(90))
        if r.session_date.isoformat() == target
        else r
        for r in rows["SPY"]
    )
    before, after = evaluate(contract), evaluate(contract, rows)
    assert contract["plan"] == before_plan
    assert before["groups"] == after["groups"]
    assert cell(before) == cell(after)
    assert cell(before, period="2020-2026-07") != cell(after, period="2020-2026-07")
