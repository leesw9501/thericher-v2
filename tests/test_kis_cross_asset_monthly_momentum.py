"""Synthetic-only finite worker and continuous-capital comparison proofs."""

from __future__ import annotations

import csv
import gzip
import io
import json
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import ROUND_DOWN, Decimal, localcontext

import pytest

from thericher_v2.research import kis_cross_asset_monthly_momentum as study

D = Decimal


@pytest.fixture(scope="module")
def plan():
    # Deliberately small caller-frozen synthetic calendar, not a NYSE claim.
    sessions = []
    for index in range(69):
        year, month = 2021 + index // 12, index % 12 + 1
        for day in (1, 28):
            sessions.append(
                study.CrossAssetSession(
                    date(year, month, day),
                    datetime(year, month, day, 14, tzinfo=UTC),
                    datetime(year, month, day, 21, tzinfo=UTC),
                )
            )
    return study.build_plan(tuple(sessions))


@pytest.fixture(scope="module")
def rows(plan):
    return {
        s: tuple(
            study.PriceClose(s, day, "synthetic", D(100 + day.toordinal()))
            for day in sorted(study.required_past_dates(plan))
        )
        for s in study.INSTRUMENT_ORDER
    }


@pytest.fixture(scope="module")
def seal(plan, rows):
    return study.prepare_actions(rows, plan, "synthetic")


@pytest.fixture(scope="module")
def days(plan):
    return tuple(study.nav.ThreeAssetDay(day, (D(100),) * 3, (D(100),) * 3) for day in plan.dates)


@pytest.fixture(scope="module")
def cells(seal, days):
    return study.evaluate_sealed(days, seal)


def source_fixture(plan):
    files = []
    for symbol in study.INSTRUMENT_ORDER:
        text = io.StringIO()
        writer = csv.writer(text, lineterminator="\n")
        writer.writerow(study.COLUMNS)
        for session in plan.sessions:
            day = session.session_date
            writer.writerow(
                [
                    symbol,
                    study.EXCHANGES[symbol],
                    day.isoformat(),
                    "100",
                    str(100 + day.toordinal()),
                    "synthetic-chunk",
                ]
            )
        files.append((symbol, gzip.compress(text.getvalue().encode(), mtime=0)))
    return study.SourceInputs(tuple(files), {}, plan)


def test_fixed_contract_geometry():
    config = study.configuration()
    assert config["cells"] == 24 and config["blocks"] == [
        ["2022-09", "2023-12", 16],
        ["2024-01", "2026-09", 33],
    ]
    assert config["seconds"] == 120 and config["actual_fits"] == 0
    assert config["gpu"] is False and config["network"] == "none"
    assert config["costs_bps_side"] == ["2.5", "5", "10"]
    assert "Tiingo" not in study.__doc__


def test_plan_and_controls(plan, seal):
    assert len(plan.boundaries) == 49 and plan.block_cut == 32
    assert plan.dates[plan.block_cut] == date(2024, 1, 1)
    actions = seal.record()["actions"]
    assert [len(actions[p]) for p in study.POLICIES] == [49, 49, 49, 1]
    assert actions["candidate"] == actions["monthly_balanced"]
    assert all(row[1:4] == ["0", "0", "0"] for row in actions["cash"])
    assert actions["buyhold"][0][0] == "2022-09-01"
    assert study.allocation().weights3 == (study.THIRD,) * 3
    assert study.allocation().cash_weight == D("1e-45")


def test_actions_cost_independent_and_private(seal, days):
    before = study.encode(seal.record())
    study.evaluate_sealed(days, seal)
    assert study.encode(seal.record()) == before
    assert "weights" not in repr(seal) and "synthetic" not in repr(seal)
    assert "adj_open" not in repr(days[0])


def test_unused_old_and_future_rows_are_not_inputs(plan, rows, seal):
    class UnreadPrice:
        def __init__(self, day):
            self.session_date = day

        @property
        def close(self):
            raise AssertionError("unused source price accessed")

    changed = {
        s: tuple(reversed(values)) + (UnreadPrice(date(1900, 1, 1)), UnreadPrice(date(2027, 1, 1)))
        for s, values in reversed(tuple(rows.items()))
    }
    assert study.prepare_actions(changed, plan, "synthetic").record() == seal.record()


@pytest.mark.parametrize("symbol", study.INSTRUMENT_ORDER)
def test_required_past_gap_no_observed_fallback(plan, rows, symbol):
    changed = dict(rows)
    changed[symbol] = rows[symbol][1:]
    with pytest.raises(ValueError, match="required_session_missing"):
        study.prepare_actions(changed, plan, "synthetic")


@pytest.mark.parametrize("change", ["vintage", "duplicate", "symbol"])
def test_past_binding_errors(plan, rows, change):
    changed = dict(rows)
    first = rows["SPY"][0]
    if change == "duplicate":
        changed["SPY"] += (first,)
    else:
        changed["SPY"] = (
            replace(
                first,
                **{
                    "vintage_ref" if change == "vintage" else "symbol": "another"
                    if change == "vintage"
                    else "TLT"
                },
            ),
        ) + rows["SPY"][1:]
    with pytest.raises(ValueError):
        study.prepare_actions(changed, plan, "synthetic")


def test_forged_action_geometry_rejected(seal):
    with pytest.raises(study.StudyFault, match="action_geometry"):
        replace(seal, candidate=seal.candidate[:-1])
    with pytest.raises(study.StudyFault, match="action_target"):
        replace(seal, candidate=(study.allocation((D("0.5"), D(0), D(0))),) * 49)


def test_24_cells_carry_and_no_buyhold_boundary_trade(cells, plan):
    assert len(cells) == 24 and study.criterion(cells) == "rejected"
    for policy in study.POLICIES:
        for cost in study.COSTS:
            first, second = [
                c["metrics"] for c in cells if c["policy"] == policy and c["cost_bps"] == str(cost)
            ]
            assert second["entering_nav"] == first["nav"]
            assert first["months"] == 16 and second["months"] == 33
            assert first["days"] + second["days"] == len(plan.dates)
            if policy != "cash":
                assert D(second["entering_nav"]) < 1
    by_policy = {
        c["policy"]: c["metrics"] for c in cells if c["cost_bps"] == "10" and c["block"] == 1
    }
    assert D(by_policy["buyhold"]["fees"]) < D(by_policy["monthly_balanced"]["fees"])
    assert by_policy["cash"]["nav"] == "1"


def test_buyhold_matches_one_continuous_path(days, seal, cells):
    ledger = study.nav.replay(days, {seal.plan.dates[0]: study.allocation()}, D(10))
    assert ledger.daily[seal.plan.block_cut].fees == 0
    assert not ledger.daily[seal.plan.block_cut - 1].flat
    metrics = next(
        c["metrics"]
        for c in cells
        if c["block"] == 1 and c["policy"] == "buyhold" and c["cost_bps"] == "10"
    )
    assert metrics == study._metrics(
        ledger.daily[seal.plan.block_cut :], ledger.daily[seal.plan.block_cut - 1].nav, 33
    )


def test_forward_price_mutation_cannot_change_actions(days, seal):
    pin = seal.sha256
    changed = tuple(replace(d, adj_close3=(D(110),) * 3) for d in days)
    assert study.evaluate_sealed(changed, seal) != study.evaluate_sealed(days, seal)
    assert seal.sha256 == pin


@pytest.mark.parametrize("kind", ["missing", "extra", "reorder"])
def test_forward_support_gap_is_not_cash_or_date_deletion(kind, days, seal):
    changed = (
        days[:-1]
        if kind == "missing"
        else days + (days[-1],)
        if kind == "extra"
        else tuple(reversed(days))
    )
    pin = seal.sha256
    with pytest.raises(study.StudyFault, match="forward_mark_gap"):
        study.evaluate_sealed(changed, seal)
    assert seal.sha256 == pin


def test_hostile_decimal_and_price_scale(days, seal, cells):
    with localcontext() as context:
        context.prec, context.rounding = 6, ROUND_DOWN
        assert study.evaluate_sealed(days, seal) == cells
    scaled = tuple(
        replace(d, adj_open3=(D(200), D(300), D(400)), adj_close3=(D(200), D(300), D(400)))
        for d in days
    )
    scaled_cells = study.evaluate_sealed(scaled, seal)
    for before, after in zip(cells, scaled_cells, strict=True):
        for key in ("entering_nav", "nav", "growth", "utility", "fees", "traded_notional"):
            assert abs(D(before["metrics"][key]) - D(after["metrics"][key])) < D("1e-40")
    assert study.criterion(scaled_cells) == study.criterion(cells)


def artificial_cells(growth="1", utility="1", control="0"):
    return tuple(
        dict(
            block=b,
            policy=p,
            cost_bps=str(c),
            status="complete",
            metrics=dict(
                growth=growth if p == "candidate" else control,
                utility=utility if p == "candidate" else control,
            ),
        )
        for b in (0, 1)
        for p in study.POLICIES
        for c in study.COSTS
    )


@pytest.mark.parametrize(
    "growth,utility,expected",
    [
        ("1", "1", "development_survivor"),
        ("0", "1", "rejected"),
        ("1", "0", "rejected"),
        ("1e-10", "1", "rejected"),
        ("1.00000000001e-10", "1", "development_survivor"),
    ],
)
def test_strict_unrounded_decimal_kill(growth, utility, expected):
    with localcontext() as ctx:
        ctx.prec = 6
        assert study.criterion(artificial_cells(growth, utility)) == expected


def test_both_blocks_and_all_metrics_required():
    cells = list(artificial_cells())
    next(
        c for c in cells if c["block"] == 1 and c["policy"] == "candidate" and c["cost_bps"] == "10"
    )["metrics"]["utility"] = "0"
    assert study.criterion(cells) == "rejected"
    cells = list(artificial_cells(growth="0"))
    cells[-1]["metrics"]["growth"] = "NaN"
    with pytest.raises(study.StudyFault, match="cell_metrics"):
        study.criterion(cells)
    with pytest.raises(study.StudyFault, match="cell_matrix"):
        study.criterion(cells[:-1])


def test_positive_growth_need_not_exceed_tolerance():
    assert study.criterion(artificial_cells(growth="1e-12", control="-1")) == "development_survivor"


def test_calendar_absolute_clocks_bound(plan):
    calendar = dict(
        calendar_name="NYSE",
        library_version="5.4.0",
        scheduled_sessions=[
            dict(
                date=s.session_date.isoformat(),
                open_at_utc=s.open_at.isoformat(),
                close_at_utc=s.close_at.isoformat(),
            )
            for s in plan.sessions
        ],
    )
    assert study.calendar_matches(calendar, plan.sessions)
    calendar["scheduled_sessions"][0]["open_at_utc"] = "2021-01-01T23:00:00+09:00"
    assert study.calendar_matches(calendar, plan.sessions)
    calendar["scheduled_sessions"][0]["close_at_utc"] = "2021-01-01T20:00:00+00:00"
    assert not study.calendar_matches(calendar, plan.sessions)


def test_selected_close_ignores_unused_open_and_future_support(plan):
    source = source_fixture(plan)
    before = study.load_past_closes(source)
    changed = []
    for symbol, raw in source.files:
        text = (
            gzip.decompress(raw).decode().replace(",100,", ",NaN,")
            + f"{symbol},{study.EXCHANGES[symbol]},2027-01-01,NaN,NaN,x\n"
        )
        changed.append((symbol, gzip.compress(text.encode())))
    altered = replace(source, files=tuple(changed))
    assert study.load_past_closes(altered) == before
    with pytest.raises(study.StudyFault, match="required_price"):
        study.load_forward_marks(altered)
    assert "synthetic-chunk" not in repr(source)


@pytest.mark.parametrize("path", ["../escape", "D:/secret", "/secret", "a\\b", ""])
def test_relative_paths_reject_escape(tmp_path, path):
    with pytest.raises(study.StudyFault, match="input_path"):
        study._relative(tmp_path, path)


@pytest.fixture
def worker(tmp_path, monkeypatch, plan):
    source = source_fixture(plan)
    root = tmp_path / "artifacts"
    output = root / "research" / study.NAME
    output.mkdir(parents=True)
    precommit = output / "precommit.json"
    study.atomic_new(precommit, {"synthetic": True})
    pin = study.digest(precommit.read_bytes())
    monkeypatch.setattr(study, "read_contract", lambda *a: ({}, {}))
    monkeypatch.setattr(study, "load_committed_source", lambda *a, **kw: source)
    return root, output, precommit, pin


def test_worker_seals_before_forward_and_verifies_ro(worker, monkeypatch):
    root, output, precommit, pin = worker
    original = study.load_forward_marks

    def forward(source):
        assert (output / "actions.json").is_file()
        return original(source)

    monkeypatch.setattr(study, "load_forward_marks", forward)
    result = study.run_campaign(precommit, pin, root, root / "unused-market")
    assert result["status"] == "complete" and result["cells"] == 24
    assert "metrics" not in json.dumps(result) and "nav" not in json.dumps(result)
    originals = {p.name: p.read_bytes() for p in output.iterdir()}
    monkeypatch.setattr(study, "atomic_new", lambda *a: pytest.fail("verification wrote"))
    verified = study.verify_result(
        precommit, pin, root, root / "unused-market", result["result_sha256"]
    )
    assert verified["replay"] == "exact" and verified["actual_fits"] == 0
    assert verified["writes"] == verified["searches"] == 0
    assert originals == {p.name: p.read_bytes() for p in output.iterdir()}


@pytest.mark.parametrize("failure", ["before_seal", "after_seal", "after_write"])
def test_immutable_failure_binding(worker, monkeypatch, failure):
    root, output, precommit, pin = worker
    original = study.atomic_new
    if failure == "before_seal":

        def missing(source):
            raise study.StudyFault("required_date_gap")

        monkeypatch.setattr(study, "load_past_closes", missing)
    elif failure == "after_seal":

        def missing(source):
            raise study.StudyFault("forward_mark_gap")

        monkeypatch.setattr(study, "load_forward_marks", missing)
    else:

        def partial(path, value):
            original(path, value)
            if path.name == "actions.json":
                raise OSError("private exception body must not appear")

        monkeypatch.setattr(study, "atomic_new", partial)
    result = study.run_campaign(precommit, pin, root, root)
    assert result["cells"] == 0 and result["status"] != "complete"
    assert "private" not in json.dumps(result)
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    verified = study.verify_result(precommit, pin, root, root, result["result_sha256"])
    assert verified["replay"] == "failure_binding_only"
    assert before == {p.name: p.read_bytes() for p in output.iterdir()}
    with pytest.raises(study.StudyFault, match="attempt_already_exists"):
        study.run_campaign(precommit, pin, root, root)


def test_result_mutation_and_wrong_output_contract(worker):
    root, output, precommit, pin = worker
    result = study.run_campaign(precommit, pin, root, root)
    (output / "worker-result.json").write_bytes(b"{}")
    with pytest.raises(study.StudyFault, match="artifact_hash"):
        study.verify_result(precommit, pin, root, root, result["result_sha256"])
    with pytest.raises(study.StudyFault, match="output_contract_binding"):
        study.verify_result(precommit, "sha256:" + "0" * 64, root, root, result["result_sha256"])


def test_cpu_smoke_has_no_source_io(monkeypatch, plan):
    monkeypatch.setattr(study, "calendar_sessions", lambda: plan.sessions)
    monkeypatch.setattr(study, "_read", lambda *a: pytest.fail("source read in smoke"))
    result = study.synthetic_smoke()
    assert result["months"] == 49 and result["cells"] == 24
    assert result["actual_market_reads"] == result["actual_fits"] == 0


def test_cli_shape_and_safe_smoke(monkeypatch, capsys):
    monkeypatch.setattr(study, "synthetic_smoke", lambda: {"status": "smoke_passed"})
    assert study.main(["--smoke"]) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "smoke_passed"}
    with pytest.raises(SystemExit):
        study.main(["--run"])
    with pytest.raises(SystemExit):
        study.main(["--smoke", "--market-root", "D:/market_data"])


def test_frozen_contract_source_code_and_runtime_bindings(tmp_path, monkeypatch):
    monkeypatch.setattr(study, "REPO", tmp_path / "frozen-source")
    code = {}
    for relative in study.CORE:
        path = study.REPO / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic frozen code")
        code[relative] = study.digest(path.read_bytes())
    commitment = dict(
        calendar_sha256=study.CALENDAR_PIN,
        kind="kis-cross-asset-d1-price-only-input-v1",
        no_date_fill=True,
        source_pins={study.CORE[-1]: code[study.CORE[-1]]},
    )
    input_path = tmp_path / study.INPUT_RELATIVE
    input_path.parent.mkdir(parents=True)
    study.atomic_new(input_path, commitment)
    monkeypatch.setattr(study, "INPUT_PIN", study.digest(input_path.read_bytes()))
    monkeypatch.setattr(study, "runtime_identity", lambda: dict(study.RUNTIME))
    contract = dict(
        name=study.NAME,
        config=study.configuration(),
        runtime=dict(study.RUNTIME),
        code_sha256=code,
        input_commitment_sha256=study.INPUT_PIN,
    )
    path = tmp_path / "precommit.json"
    study.atomic_new(path, contract)
    pin = study.digest(path.read_bytes())
    assert study.read_contract(path, pin, tmp_path) == (contract, commitment)
    monkeypatch.setattr(study, "runtime_identity", lambda: {})
    with pytest.raises(study.StudyFault, match="runtime_identity"):
        study.read_contract(path, pin, tmp_path)
    monkeypatch.setattr(study, "runtime_identity", lambda: dict(study.RUNTIME))
    (study.REPO / study.CORE[0]).write_bytes(b"changed")
    with pytest.raises(study.StudyFault, match="code_changed"):
        study.read_contract(path, pin, tmp_path)


@pytest.mark.parametrize("corruption", [None, "source", "output", "manifest", "clock"])
def test_all_140_bindings_and_calendar_clocks(tmp_path, monkeypatch, plan, corruption):
    artifact, market = tmp_path / "artifact", tmp_path / "market"
    artifact.mkdir()
    market.mkdir()
    calendar = dict(
        kind="caller_nyse_session_dates_v1",
        calendar_name="NYSE",
        library_version="5.4.0",
        session_dates=[s.session_date.isoformat() for s in plan.sessions],
        scheduled_sessions=[
            dict(
                date=s.session_date.isoformat(),
                open_at_utc=s.open_at.isoformat(),
                close_at_utc=s.close_at.isoformat(),
            )
            for s in plan.sessions
        ],
    )
    if corruption == "clock":
        calendar["scheduled_sessions"][0]["close_at_utc"] = "2021-01-01T20:00:00+00:00"
    calendar_bytes = study.encode(calendar)
    monkeypatch.setattr(study, "CALENDAR_PIN", study.digest(calendar_bytes))
    monkeypatch.setattr(study, "calendar_sessions", lambda: plan.sessions)
    (artifact / "calendar.json").write_bytes(calendar_bytes)
    bindings = [dict(root="ARTIFACT", path="calendar.json", sha256=study.CALENDAR_PIN)]
    for index in range(135):
        path = market / f"source-{index}"
        path.write_bytes(b"synthetic retained source")
        bindings.append(dict(root="MARKET", path=path.name, sha256=study.digest(path.read_bytes())))
    outputs = {}
    for symbol in study.INSTRUMENT_ORDER:
        path = market / f"{symbol}.csv.gz"
        raw = gzip.compress(b"synthetic output, not parsed during binding check", mtime=0)
        path.write_bytes(raw)
        outputs[symbol] = dict(
            market_relative_path=path.name,
            sha256=study.digest(raw),
            size_bytes=len(raw),
            row_count=1288,
        )
    commitment = dict(source_bindings=bindings, price_only_files=outputs)
    manifest = market / "manifest.json"
    manifest.write_bytes(study.encode(commitment))
    monkeypatch.setattr(study, "INPUT_PIN", study.digest(manifest.read_bytes()))
    if corruption in ("source", "output", "manifest"):
        path = (
            market
            / {"source": "source-134", "output": "TLT.csv.gz", "manifest": "manifest.json"}[
                corruption
            ]
        )
        path.write_bytes(b"changed bytes")
    if corruption is not None:
        code = {
            "source": "source_changed",
            "output": "output_binding",
            "manifest": "market_manifest_binding",
            "clock": "calendar_clock_binding",
        }
        with pytest.raises(study.StudyFault, match=code[corruption]):
            study.load_committed_source(commitment, artifact, market)
    else:
        result = study.load_committed_source(commitment, artifact, market)
        assert result.plan == plan and len(result.files) == 3
        assert len(bindings) + len(outputs) + 1 == 140
