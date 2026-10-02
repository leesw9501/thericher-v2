"""Two fixed pooled monthly net-utility fits; revised seen-data, non-promoting."""

from __future__ import annotations

import importlib.metadata
import io
import json
import os
import re
import stat
import time
import uuid
import zipfile
from datetime import date
from decimal import Decimal
from types import MappingProxyType

import numpy as np

from thericher_v2.data.tiingo_adjusted_etf_daily import AdjustedEtfRow
from thericher_v2.research import adjusted_monthly_net_utility as math
from thericher_v2.research import adjusted_monthly_policy_inputs as inputs
from thericher_v2.research import tiingo_monthly_holding_development as monthly

base = monthly.base
NAME = "tiingo-adjusted-monthly-net-utility-development-v1"
REPO, SYMBOLS, PERIODS, COSTS = monthly.REPO, monthly.SYMBOLS, monthly.PERIODS, monthly.COSTS
TRAIN = ("2002-01-01", "2012-12-31")
ARCHITECTURES, SEED, EPOCHS, SECONDS = ("linear", "lstm"), 101, 128, 900
POLICIES = (
    "linear",
    "lstm",
    "riskmatched_linear",
    "riskmatched_lstm",
    "fixed_half",
    "always_long",
    "cash",
)
METRICS = (
    *monthly.METRICS[:5],
    "net_utility",
    "difference_vs_riskmatched_linear_nav",
    "difference_vs_riskmatched_lstm_nav",
    "difference_vs_half_nav",
    "difference_vs_long_nav",
)
CODE = (
    *monthly.CODE,
    "src/thericher_v2/research/adjusted_monthly_policy_inputs.py",
    "src/thericher_v2/research/adjusted_monthly_net_utility.py",
    "src/thericher_v2/research/engine_research_agent.py",
    "src/thericher_v2/research/validation.py",
    "src/thericher_v2/research/tiingo_monthly_net_utility_development.py",
    "scripts/run_tiingo_monthly_net_utility_development.py",
)
encode, digest, require = monthly.encode, monthly.digest, monthly.require
atomic_new, _read, number = monthly.atomic_new, monthly._read, monthly.number
source_identity, verify_metadata, load_adjusted = (
    monthly.source_identity,
    base.verify_metadata,
    monthly.load_adjusted,
)
COUNTS = ("sessions", "months", "support_dates", "missing", "invalid")
GROUP_FIELDS = (
    *COUNTS,
    "symbol",
    "period",
    "train",
    "risk_sha256",
    "status",
    "inputs_sha256",
    "benchmark_growth",
)
CELL_FIELDS = (
    "symbol",
    "period",
    "cost_per_side_bps",
    "policy",
    "status",
    "trades",
    "action_sha256",
    *METRICS,
)


def configuration():
    return dict(
        symbols=list(SYMBOLS),
        train=list(TRAIN),
        periods=[list(p) for p in PERIODS],
        architectures=list(ARCHITECTURES),
        policies=list(POLICIES),
        cells=126,
        pooled_fits=2,
        feature="252 prior signed close-return bps/100 clipped[-20,20]; no fitted scaling/symbol",
        decision="first scheduled monthly OPEN; previous completed CLOSE features only",
        payoff="adjusted gap and daily close/entry-open growth; no next-month OPEN target",
        models="flattened sigmoid Linear252->1; one-layer LSTM16/no-dropout sigmoid Linear16->1",
        optimizer=dict(
            name="Adam",
            lr="0.003",
            weight_decay="0.001",
            betas=["0.9", "0.999"],
            eps="1e-8",
            epochs=EPOCHS,
            full_batch=True,
            seed=SEED,
        ),
        objective="mean3 independent ETF utilities:252*(mean daily logNAV - population variance)",
        train_cost_per_side_bps="10",
        costs_per_side_bps=list(COSTS),
        timing="initial OPEN NAV1; overnight stock carry; exact postfee target; final CLOSE exit",
        calibration="per model/ETF min1 std(zero-fee final-model TRAIN NAV returns)/std(passive)",
        missing="required gap -> exact cohort unavailable; any TRAIN gap -> neither pooled fit",
        weights="final epoch only; numeric float32 NPZ, no pickle; exact schema/hash/readback",
        action_reconstruction_atol="0.000001",
        numeric="Decimal50 replay; float64 utility/ledger",
        cpu_preflight="synthetic two-architecture CPU gradient step + NumPy/Decimal NAV parity",
        budget=dict(
            wall_seconds=SECONDS,
            cpu_threads=2,
            memory_bytes=6 * 1024**3,
            gpu=True,
            vram="observed available VRAM ceiling",
            passes=1,
            fits=2,
        ),
        image="sha256:d6b43213ee3877653e3c1e79c7238fb5caa71241abf238838fa0c3332cf4f039",
        freeze_runtime="main freezes inside pinned Docker CPU image, NOT host Torch runtime",
        cuda_guard="min(totalVRAM*0.9,freeVRAM-1GiB); allocator fraction before fitting",
        inference="final CUDA-trained weights rebuilt on CPU for authoritative TRAIN/EVAL actions",
        strongest_kill="fails own TRAIN-risk-matched control or advantage only surviving upmarket",
        scope=base.configuration()["scope"],
        selection=False,
        early_stopping=False,
        assumptions=monthly.configuration()["assumptions"][:-1]
        + [
            "outcome-informed development; no disjoint holdout, model/seed/epoch/cost selection",
            "pooled correlated surviving ETFs are3 separate sleeves, NOT an actual portfolio",
            "DeePM net-turnover concept inspiration only, NOT Sharpe/SoftMin replication",
            "synthetic CPU preflight is runtime/parity evidence, not market-performance evidence",
        ],
        reference="main re-retrieved DeePM; MIT code concept only, no upstream adoption",
        prior_families=monthly.configuration()["prior_families"]
        + [monthly.NAME, "tiingo-adjusted-monthly-momentum-development-v1"],
    )


def calendar_days():
    require(importlib.metadata.version("pandas-market-calendars") == "5.4.0", "calendar_version")
    import pandas_market_calendars as calendars

    return [
        t.date().isoformat()
        for t in calendars.get_calendar("NYSE")
        .schedule(start_date="2000-12-01", end_date="2026-08-03")
        .index
    ]


def build_plan(days):
    require(
        days
        and all(type(d) is str and date.fromisoformat(d).isoformat() == d for d in days)
        and all(a < b for a, b in zip(days, days[1:], strict=False)),
        "calendar",
    )
    require(days[0] >= "2000-12-01" and days[-1] == "2026-08-03", "calendar_bracket")

    def segment(first, last):
        months = []
        for month in base._months(first[:7], last[:7]):
            indices = [i for i, d in enumerate(days) if d[:7] == month]
            require(bool(indices), "calendar_month_missing")
            a, b = indices[0], indices[-1] + 1
            require(
                a >= 253 and b < len(days) and days[a - 1][:7] != month and days[b][:7] != month,
                "calendar_month_context",
            )
            months.append(dict(bounds=[a, b]))
        support = sorted({d for m in months for d in days[m["bounds"][0] - 253 : m["bounds"][1]]})
        return dict(
            bounds=[months[0]["bounds"][0], months[-1]["bounds"][1]], months=months, support=support
        )

    return dict(
        days=list(days),
        train=segment(*TRAIN),
        periods=[dict(period=p, **segment(a, b)) for p, a, b in PERIODS],
    )


def runtime_versions():
    return {p: importlib.metadata.version(p) for p in ("torch", "numpy", "pandas-market-calendars")}


def proposed_contract():
    config, source, plan = configuration(), source_identity(), build_plan(calendar_days())
    return dict(
        name=NAME,
        config=config,
        config_sha256=digest(encode(config)),
        source=source,
        source_sha256=digest(encode(source)),
        plan=plan,
        inputs_sha256=digest(encode([source, plan, config["feature"], config["payoff"]])),
        runtime=runtime_versions(),
        code_sha256={p: digest((REPO / p).read_bytes()) for p in CODE},
    )


def _fields(value, keys):
    require(type(value) is dict and set(value) == set(keys), "closed_fields")


def _hash(value):
    return type(value) is str and re.fullmatch(monthly.HASH, value) is not None


def header(contract, pin):
    _fields(
        contract,
        (
            "name",
            "config",
            "config_sha256",
            "source",
            "source_sha256",
            "plan",
            "inputs_sha256",
            "runtime",
            "code_sha256",
        ),
    )
    require(contract["name"] == NAME and digest(encode(contract)) == pin, "contract_binding")
    for key, value in (("config", configuration()), ("source", source_identity())):
        require(
            encode(contract[key]) == encode(value)
            and contract[key + "_sha256"] == digest(encode(value)),
            key + "_changed",
        )
    require(
        encode(contract["plan"]) == encode(build_plan(contract["plan"]["days"])), "plan_changed"
    )
    require(contract["runtime"] == runtime_versions(), "runtime_changed")
    require(
        set(contract["code_sha256"]) == set(CODE)
        and all(_hash(v) for v in contract["code_sha256"].values()),
        "code_pins",
    )
    require(
        contract["inputs_sha256"]
        == digest(
            encode(
                [
                    contract["source"],
                    contract["plan"],
                    contract["config"]["feature"],
                    contract["config"]["payoff"],
                ]
            )
        ),
        "inputs_binding",
    )
    return dict(
        name=NAME,
        contract_sha256=pin,
        config_sha256=contract["config_sha256"],
        source_sha256=contract["source_sha256"],
        inputs_sha256=contract["inputs_sha256"],
        scope=configuration()["scope"],
    )


def register_contract(root, contract, pin):
    header(contract, pin)
    base.register_frozen_campaign(
        contract_hash=pin,
        dataset_hash=contract["source_sha256"],
        split_hash=digest(encode(contract["plan"])),
        cost_model_hash=digest(encode(COSTS)),
        trial_family=NAME,
        holdout_access="none",
        artifact_root=root,
        repo_root=REPO,
    )


def freeze(artifact_root, market_data_root):
    verify_metadata(artifact_root, market_data_root)
    contract = proposed_contract()
    output = base.ensure_external_artifact_directory(artifact_root, REPO, "research") / NAME
    output.mkdir()
    atomic_new(output / "precommit.json", contract)
    pin = digest(encode(contract))
    register_contract(artifact_root, contract, pin)
    return pin


def verify(artifact_root, market_data_root, pin):
    output = base.ensure_external_artifact_directory(artifact_root, REPO, "research", NAME)
    raw = _read(output / "precommit.json")
    require(digest(raw) == pin and raw == encode(proposed_contract()), "precommit_changed")
    verify_metadata(artifact_root, market_data_root)
    if (output / "worker-result.json").exists():
        result = json.loads(_read(output / "worker-result.json"))
        validate_result(result, json.loads(raw), pin)
        for model in result.get("models", []):
            read_weights(output / model["file"], model["architecture"], model["weights_sha256"])
    return output, json.loads(raw)


def weight_shapes(architecture):
    require(architecture in ARCHITECTURES, "architecture")
    return (
        dict(head_weight=(1, 252), head_bias=(1,))
        if architecture == "linear"
        else dict(
            encoder_weight_ih_l0=(64, 1),
            encoder_weight_hh_l0=(64, 16),
            encoder_bias_ih_l0=(64,),
            encoder_bias_hh_l0=(64,),
            head_weight=(1, 16),
            head_bias=(1,),
        )
    )


def _state_keys(architecture):
    return {
        k: k.replace("head_", "head.").replace("encoder_", "encoder.")
        for k in weight_shapes(architecture)
    }


def validate_weights(values, architecture):
    require(set(values) == set(weight_shapes(architecture)), "weight_keys")
    for k, shape in weight_shapes(architecture).items():
        a = values[k]
        require(
            type(a) is np.ndarray
            and a.shape == shape
            and a.dtype == np.dtype("float32")
            and np.isfinite(a).all(),
            "weight_shape_dtype_numeric",
        )


def extract_weights(model, architecture):
    state, keys = model.state_dict(), _state_keys(architecture)
    require(set(state) == set(keys.values()), "state_keys")
    values = {k: state[v].detach().cpu().numpy().copy() for k, v in keys.items()}
    validate_weights(values, architecture)
    return values


def rebuild_policy(torch, values, architecture, *, device="cpu"):
    validate_weights(values, architecture)
    model = math.build_torch_monthly_policy(torch, architecture).to(device)
    model.load_state_dict(
        {
            v: torch.tensor(values[k].copy(), dtype=torch.float32, device=device)
            for k, v in _state_keys(architecture).items()
        },
        strict=True,
    )
    return model.eval()


def write_weights(output, values, architecture):
    validate_weights(values, architecture)
    buffer = io.BytesIO()
    np.savez(buffer, **values)
    raw = buffer.getvalue()
    path = output / f"weights-{architecture}.npz"
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    read_weights(path, architecture, digest(raw))
    return dict(
        architecture=architecture,
        file=path.name,
        weights_sha256=digest(raw),
        epochs=EPOCHS,
        seed=SEED,
        reconstructed=True,
    )


def read_weights(path, architecture, pin):
    """Offline numeric-only reader; no Torch, model code dispatch, source IO or pickle."""
    before = path.lstat()
    require(
        stat.S_ISREG(before.st_mode)
        and not path.is_symlink()
        and before.st_nlink == 1
        and not getattr(before, "st_file_attributes", 0) & 0x400,
        "weight_file_link",
    )
    raw = _read(path, 1024**2)
    require(digest(raw) == pin, "weights_hash")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        expected = {k + ".npy" for k in weight_shapes(architecture)}
        entries = archive.infolist()
        require(
            len(entries) == len(expected)
            and {e.filename for e in entries} == expected
            and sum(e.file_size for e in entries) <= 1024**2,
            "weight_archive",
        )
    with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
        values = {k: archive[k].copy() for k in archive.files}
    validate_weights(values, architecture)
    after = path.lstat()
    require(
        (before.st_ino, before.st_size, before.st_mtime_ns, before.st_nlink)
        == (after.st_ino, after.st_size, after.st_mtime_ns, after.st_nlink),
        "weights_changed",
    )
    for a in values.values():
        a.setflags(write=False)
    return MappingProxyType(values)


def _check_deadline(deadline):
    require(time.monotonic() < deadline, "hard_timeout")


def cpu_smoke(torch, *, deadline=None):
    """Fixed manufactured marks only; this happens before CUDA or market-row loading."""
    deadline = time.monotonic() + 60 if deadline is None else deadline
    _check_deadline(deadline)
    torch.set_num_threads(1)
    data = math.MonthlyUtilityArrays(
        "SPY",
        (date(2002, 1, 2), date(2002, 2, 1)),
        (date(2001, 12, 31), date(2002, 1, 31)),
        np.linspace(-1, 1, 504, dtype=np.float32).reshape(2, 252, 1),
        np.array([1.1, 0.94]),
        np.array([[1.02, 0.98], [1.04, 1.0]]),
        np.array([[True, True], [True, False]]),
    )
    days = ("2002-01-02", "2002-01-31", "2002-02-01")
    rows = {}
    for i, d in enumerate(days):
        opening = Decimal(100) if i < 2 else Decimal("92.12")
        close = opening * Decimal(str(data.close_growth[i // 2, i % 2]))
        rows[d] = AdjustedEtfRow(
            "SPY",
            date.fromisoformat(d),
            opening,
            max(opening, close) + 1,
            min(opening, close) - 1,
            close,
        )
    for architecture in ARCHITECTURES:
        _check_deadline(deadline)
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(SEED)
            model = math.build_torch_monthly_policy(torch, architecture)
            before = extract_weights(model, architecture)
            weights = model(torch.tensor(data.features.copy()))
            nav = math.torch_monthly_nav(torch, weights, data)
            loss = -math.torch_net_utility(torch, nav)
            loss.backward()
            require(
                all(
                    p.grad is not None and bool(torch.isfinite(p.grad).all())
                    for p in model.parameters()
                )
                and any(bool((p.grad != 0).any()) for p in model.parameters()),
                "cpu_gradient",
            )
            torch.optim.Adam(model.parameters(), lr=0.003, weight_decay=0.001).step()
            after = extract_weights(model, architecture)
            rebuilt = rebuild_policy(torch, after, architecture)
            require(
                np.allclose(
                    predict(torch, model.eval(), data),
                    predict(torch, rebuilt, data),
                    rtol=0,
                    atol=1e-6,
                ),
                "cpu_reconstruction",
            )
            require(
                any(not np.array_equal(before[k], after[k]) for k in before), "cpu_weight_update"
            )
            w = weights.detach().numpy().astype(np.float64)
            expected = math.numpy_monthly_nav(w, data, cost_bps=10)
            require(
                np.allclose(nav.detach().numpy(), expected, rtol=0, atol=1e-10), "cpu_numpy_parity"
            )
            replay = monthly.replay(
                rows,
                days,
                (0, 3),
                {0: Decimal(str(w[0])), 2: Decimal(str(w[1]))},
                "10",
                deadline=deadline,
            )
            require(
                np.allclose(expected, [float(v) for v in replay["navs"]], rtol=0, atol=1e-10)
                and abs(
                    float(math.torch_net_utility(torch, nav).detach())
                    - math.numpy_net_utility(expected)
                )
                <= 1e-9,
                "cpu_decimal_parity",
            )
    return dict(cpu_smoke_passed=True, cpu_smoke_models=2)


def fit_policy(torch, arrays, architecture, *, device, deadline):
    require(tuple(arrays) == SYMBOLS, "pooled_symbol_order")
    features = torch.tensor(np.concatenate([arrays[s].features for s in SYMBOLS]), device=device)
    lengths = [len(arrays[s].decision_dates) for s in SYMBOLS]
    with torch.random.fork_rng(devices=[] if device == "cpu" else [0]):
        torch.manual_seed(SEED)
        model = math.build_torch_monthly_policy(torch, architecture).to(device)
        model.train()
        optimizer = torch.optim.Adam(
            model.parameters(), lr=0.003, weight_decay=0.001, betas=(0.9, 0.999), eps=1e-8
        )
        for _ in range(EPOCHS):
            _check_deadline(deadline)
            optimizer.zero_grad(set_to_none=True)
            weights = model(features)
            chunks = torch.split(weights, lengths)
            utilities = [
                math.torch_net_utility(
                    torch, math.torch_monthly_nav(torch, w, arrays[s], cost_bps=10)
                )
                for s, w in zip(SYMBOLS, chunks, strict=True)
            ]
            loss = -torch.stack(utilities).mean()
            require(bool(torch.isfinite(loss)), "training_loss")
            loss.backward()
            require(
                all(
                    p.grad is not None and bool(torch.isfinite(p.grad).all())
                    for p in model.parameters()
                ),
                "training_gradients",
            )
            optimizer.step()
    return extract_weights(model, architecture)


def predict(torch, model, arrays):
    with torch.no_grad():
        weights = model(torch.tensor(arrays.features.copy(), dtype=torch.float32)).cpu().numpy()
    require(
        weights.shape == (len(arrays.decision_dates),)
        and np.isfinite(weights).all()
        and ((weights >= 0) & (weights <= 1)).all(),
        "prediction_domain",
    )
    return weights.astype(np.float64)


def prepare(rows_by_symbol, plan):
    require(set(rows_by_symbol) == set(SYMBOLS), "symbol_set")
    calendar = tuple(date.fromisoformat(d) for d in plan["days"])
    prepared = {}
    for symbol in SYMBOLS:
        stream = rows_by_symbol[symbol]
        require(
            type(stream) is tuple
            and all(
                type(r) is AdjustedEtfRow and r.symbol == symbol and type(r.session_date) is date
                for r in stream
            ),
            "source_identity",
        )
        require(
            all(a.session_date < b.session_date for a, b in zip(stream, stream[1:], strict=False)),
            "source_order",
        )
        rows = {r.session_date.isoformat(): r for r in stream}
        for name, segment in [("TRAIN", plan["train"])] + [
            (p["period"], p) for p in plan["periods"]
        ]:
            marks = [rows.get(d) for d in segment["support"]]
            facts = dict(
                sessions=segment["bounds"][1] - segment["bounds"][0],
                months=len(segment["months"]),
                support_dates=len(segment["support"]),
                missing=sum(r is None for r in marks),
                invalid=sum(r is not None and not monthly.valid(r) for r in marks),
            )
            records = (
                None
                if facts["missing"] or facts["invalid"]
                else tuple(
                    inputs.build_adjusted_monthly_policy_inputs(
                        stream, symbol=symbol, calendar=calendar, month_bounds=tuple(m["bounds"])
                    )
                    for m in segment["months"]
                )
            )
            prepared[symbol, name] = dict(
                rows=rows,
                records=records,
                facts=facts,
                arrays=math.prepare_monthly_utility_arrays(records)
                if records is not None
                else None,
            )
    return prepared


def _actions(segment, values):
    require(len(values) == len(segment["months"]), "action_count")
    return {
        m["bounds"][0]: Decimal(str(float(w)))
        for m, w in zip(segment["months"], values, strict=True)
    }


@monthly._decimal
def risk_constants(prepared, plan, train_predictions, *, deadline):
    result = {}
    for symbol in SYMBOLS:
        rows, segment = prepared[symbol, "TRAIN"]["rows"], plan["train"]
        passive = monthly.replay(
            rows,
            plan["days"],
            segment["bounds"],
            _actions(segment, np.ones(len(segment["months"]))),
            "0",
            deadline=deadline,
        )
        raw = monthly.variance(passive["returns"])
        constants = {}
        for architecture in ARCHITECTURES:
            managed = monthly.replay(
                rows,
                plan["days"],
                segment["bounds"],
                _actions(segment, train_predictions[architecture, symbol]),
                "0",
                deadline=deadline,
            )
            constants[architecture] = (
                min(Decimal(1), (monthly.variance(managed["returns"]) / raw).sqrt())
                if raw > 0
                else None
            )
        result[symbol] = constants
    return result


def _cohort_hash(contract, symbol, segment):
    return digest(encode([contract["inputs_sha256"], symbol, segment]))


@monthly._decimal
def evaluate(prepared, contract, pin, models, predictions, risks, *, runtime, deadline):
    result, groups, cells = header(contract, pin), [], []
    for symbol in SYMBOLS:
        training = prepared[symbol, "TRAIN"]["facts"]
        for segment in contract["plan"]["periods"]:
            item = prepared[symbol, segment["period"]]
            available = (
                item["arrays"] is not None
                and bool(models)
                and all(v is not None for v in risks[symbol].values())
            )
            rows, days, bounds = item["rows"], contract["plan"]["days"], segment["bounds"]
            group = dict(
                item["facts"],
                symbol=symbol,
                period=segment["period"],
                train=training,
                risk_sha256={a: digest(encode(str(risks[symbol][a]))) for a in ARCHITECTURES}
                if available
                else None,
                status="evaluated" if available else "input_unavailable",
                inputs_sha256=_cohort_hash(contract, symbol, segment),
                benchmark_growth=number(
                    rows[days[bounds[1] - 1]].adj_close / rows[days[bounds[0]]].adj_open
                )
                if available
                else None,
            )
            groups.append(group)
            actions = None
            if available:
                actions = {
                    a: _actions(segment, predictions[a, symbol, segment["period"]])
                    for a in ARCHITECTURES
                }
                actions.update(
                    {
                        "riskmatched_" + a: dict.fromkeys(actions["linear"], risks[symbol][a])
                        for a in ARCHITECTURES
                    }
                )
                actions.update(
                    {
                        p: dict.fromkeys(actions["linear"], w)
                        for p, w in (
                            ("fixed_half", Decimal(".5")),
                            ("always_long", Decimal(1)),
                            ("cash", Decimal(0)),
                        )
                    }
                )
            for cost in COSTS:
                batch = []
                for policy in POLICIES:
                    cell = dict(
                        symbol=symbol,
                        period=segment["period"],
                        cost_per_side_bps=cost,
                        policy=policy,
                        status=group["status"],
                        trades=None,
                        action_sha256=None,
                        **dict.fromkeys(METRICS),
                    )
                    if available:
                        cell["action_sha256"] = digest(
                            encode(
                                [(days[i], str(w.normalize())) for i, w in actions[policy].items()]
                            )
                        )
                        scored = monthly.replay(
                            rows, days, bounds, actions[policy], cost, deadline=deadline
                        )
                        cell.update({k: number(scored[k]) for k in METRICS[:5]})
                        cell["net_utility"] = number(
                            Decimal(
                                str(
                                    math.numpy_net_utility(
                                        np.array([float(v) for v in scored["navs"]])
                                    )
                                )
                            )
                        )
                        cell["trades"] = scored["trades"]
                    batch.append(cell)
                if available:
                    for cell in batch:
                        for field, control in zip(METRICS[6:], batch[2:6], strict=True):
                            cell[field] = number(
                                Decimal(cell["final_nav"]) - Decimal(control["final_nav"])
                            )
                cells.extend(batch)
    result.update(
        status="complete"
        if all(g["status"] == "evaluated" for g in groups)
        else "input_unavailable",
        criterion="descriptive_only_no_selection",
        cpu_smoke_passed=True,
        cpu_smoke_models=2,
        runtime=runtime,
        models=models,
        groups=groups,
        cells=cells,
    )
    validate_result(result, contract, pin)
    return result


def failure(contract, pin, reason, *, cpu_smoke_passed=False, runtime=None):
    require(reason in base.FAILURES, "failure_category")
    return dict(
        header(contract, pin),
        status="failed",
        reason=reason,
        criterion="not_evaluable",
        cpu_smoke_passed=cpu_smoke_passed,
        cpu_smoke_models=2 if cpu_smoke_passed else 0,
        runtime=runtime,
        models=[],
        groups=[],
        cells=[],
    )


def _counts(record, segment):
    _fields(record, COUNTS)
    require(
        all(type(record[k]) is int and record[k] >= 0 for k in COUNTS)
        and record["sessions"] == segment["bounds"][1] - segment["bounds"][0]
        and record["months"] == len(segment["months"])
        and record["support_dates"] == len(segment["support"])
        and record["missing"] + record["invalid"] <= record["support_dates"],
        "cohort_counts",
    )


def _numeric(value):
    require(type(value) is str and len(value) <= 80, "metric_type")
    v = Decimal(value)
    require(v.is_finite() and value == number(v), "metric_numeric")
    return v


def _runtime(value, contract):
    _fields(
        value,
        (
            "device",
            "torch",
            "cuda",
            "torch_threads",
            "free_before_bytes",
            "total_bytes",
            "memory_budget_bytes",
            "peak_allocated_bytes",
            "training_device",
            "inference_device",
        ),
    )
    require(
        type(value["device"]) is str
        and 0 < len(value["device"]) <= 128
        and value["torch"] == contract["runtime"]["torch"]
        and value["cuda"] == "12.8"
        and type(value["torch_threads"]) is int
        and value["torch_threads"] == 2
        and value["training_device"] == "cuda:0"
        and value["inference_device"] == "cpu",
        "runtime_identity",
    )
    require(
        all(
            type(value[k]) is int
            for k in (
                "free_before_bytes",
                "total_bytes",
                "memory_budget_bytes",
                "peak_allocated_bytes",
            )
        )
        and 0 < value["free_before_bytes"] <= value["total_bytes"]
        and value["memory_budget_bytes"]
        == min(int(value["total_bytes"] * 0.9), value["free_before_bytes"] - 1024**3)
        and 0 <= value["peak_allocated_bytes"] <= value["memory_budget_bytes"],
        "runtime_memory",
    )


@monthly._decimal
def validate_result(result, contract, pin):
    expected = header(contract, pin)
    if result.get("status") == "failed":
        require(type(result.get("cpu_smoke_passed")) is bool, "cpu_smoke_type")
        if result.get("runtime") is not None:
            _runtime(result["runtime"], contract)
        require(
            encode(result)
            == encode(
                failure(
                    contract,
                    pin,
                    result.get("reason"),
                    cpu_smoke_passed=result["cpu_smoke_passed"],
                    runtime=result.get("runtime"),
                )
            ),
            "failure_shape",
        )
        return
    _fields(
        result,
        (
            *expected,
            "status",
            "criterion",
            "cpu_smoke_passed",
            "cpu_smoke_models",
            "runtime",
            "models",
            "groups",
            "cells",
        ),
    )
    require(
        encode({k: result[k] for k in expected}) == encode(expected)
        and result["criterion"] == "descriptive_only_no_selection"
        and result["cpu_smoke_passed"] is True
        and type(result["cpu_smoke_models"]) is int
        and result["cpu_smoke_models"] == 2,
        "result_binding",
    )
    _runtime(result["runtime"], contract)
    models = result["models"]
    require(
        type(models) is list
        and (not models or [m["architecture"] for m in models] == list(ARCHITECTURES)),
        "model_matrix",
    )
    for m in models:
        _fields(m, ("architecture", "file", "weights_sha256", "epochs", "seed", "reconstructed"))
        require(
            m["file"] == f"weights-{m['architecture']}.npz"
            and _hash(m["weights_sha256"])
            and type(m["epochs"]) is int
            and m["epochs"] == EPOCHS
            and type(m["seed"]) is int
            and m["seed"] == SEED
            and m["reconstructed"] is True,
            "model_attestation",
        )
    keys = [(s, p) for s in SYMBOLS for p, _, _ in PERIODS]
    require([(g["symbol"], g["period"]) for g in result["groups"]] == keys, "group_matrix")
    train_facts, risk_facts = {}, {}
    for g in result["groups"]:
        _fields(g, GROUP_FIELDS)
        segment = next(p for p in contract["plan"]["periods"] if p["period"] == g["period"])
        _counts({k: g[k] for k in COUNTS}, segment)
        _counts(g["train"], contract["plan"]["train"])
        require(
            train_facts.setdefault(g["symbol"], g["train"]) == g["train"], "TRAIN_recalibration"
        )
        require(
            g["inputs_sha256"] == _cohort_hash(contract, g["symbol"], segment), "cohort_binding"
        )
        if g["status"] == "evaluated":
            require(
                bool(models)
                and g["missing"] == g["invalid"] == 0
                and g["risk_sha256"] is not None
                and g["train"]["missing"] == g["train"]["invalid"] == 0,
                "available_group",
            )
            _fields(g["risk_sha256"], ARCHITECTURES)
            require(
                all(_hash(v) for v in g["risk_sha256"].values())
                and risk_facts.setdefault(g["symbol"], g["risk_sha256"]) == g["risk_sha256"]
                and _numeric(g["benchmark_growth"]) > 0,
                "risk_binding",
            )
        else:
            require(
                g["status"] == "input_unavailable"
                and g["risk_sha256"] is None
                and g["benchmark_growth"] is None,
                "unavailable_group",
            )
    any_train_gap = any(t["missing"] or t["invalid"] for t in train_facts.values())
    require(bool(models) != any_train_gap, "pooled_fit_availability")
    require(
        result["status"]
        == (
            "complete"
            if all(g["status"] == "evaluated" for g in result["groups"])
            else "input_unavailable"
        ),
        "status",
    )
    cells, paths, previous = result["cells"], {}, {}
    require(
        [(c["symbol"], c["period"], c["cost_per_side_bps"], c["policy"]) for c in cells]
        == [(s, p, c, n) for s, p in keys for c in COSTS for n in POLICIES],
        "cell_matrix",
    )
    for i, c in enumerate(cells):
        _fields(c, CELL_FIELDS)
        g = result["groups"][i // 21]
        require(c["status"] == g["status"], "cell_status")
        key = c["symbol"], c["period"], c["policy"]
        require(
            paths.setdefault(key, c["action_sha256"]) == c["action_sha256"], "cost_changes_actions"
        )
        if c["status"] == "input_unavailable":
            require(
                c["action_sha256"] is None
                and c["trades"] is None
                and all(c[k] is None for k in METRICS),
                "unavailable_metrics",
            )
            continue
        require(_hash(c["action_sha256"]), "action_hash")
        nav, dd, std, fees, turnover, *_ = [_numeric(c[k]) for k in METRICS]
        require(
            nav > 0
            and 0 <= dd < 1
            and std >= 0
            and fees >= 0
            and turnover >= 0
            and type(c["trades"]) is int
            and 0 <= c["trades"] <= g["months"] + 1,
            "metric_domain",
        )
        tol, fee = (
            Decimal("3e-11") * (1 + nav + fees + turnover),
            Decimal(c["cost_per_side_bps"]) / 10000,
        )
        require(
            abs(fees - fee * turnover) <= tol and nav <= previous.get(key, nav) + tol,
            "cost_identity",
        )
        previous[key] = nav
        if c["policy"] == "cash":
            require(
                nav == 1
                and dd == std == fees == turnover == c["trades"] == 0
                and Decimal(c["net_utility"]) == 0,
                "cash_identity",
            )
        if c["policy"] == "always_long":
            growth = Decimal(g["benchmark_growth"])
            require(
                c["trades"] == 2
                and abs(nav - growth * (1 - fee) / (1 + fee)) <= tol
                and abs(turnover - (1 + growth) / (1 + fee)) <= tol,
                "long_endpoints",
            )
        batch = cells[i // 7 * 7 : i // 7 * 7 + 7]
        for field, control in zip(METRICS[6:], batch[2:6], strict=True):
            require(
                abs(nav - Decimal(control["final_nav"]) - Decimal(c[field])) <= tol,
                "paired_difference",
            )


def execute(torch, prepared, contract, pin, output, *, device, runtime, deadline):
    models, predictions = [], {}
    complete = all(prepared[s, "TRAIN"]["arrays"] is not None for s in SYMBOLS)
    risks = {s: dict.fromkeys(ARCHITECTURES) for s in SYMBOLS}
    if complete:
        training = {s: prepared[s, "TRAIN"]["arrays"] for s in SYMBOLS}
        for architecture in ARCHITECTURES:
            weights = fit_policy(torch, training, architecture, device=device, deadline=deadline)
            policy = rebuild_policy(torch, weights, architecture)
            metadata = write_weights(output, weights, architecture)
            recovered = rebuild_policy(
                torch,
                read_weights(output / metadata["file"], architecture, metadata["weights_sha256"]),
                architecture,
            )
            for symbol in SYMBOLS:
                w = predict(torch, policy, training[symbol])
                require(
                    np.allclose(w, predict(torch, recovered, training[symbol]), rtol=0, atol=1e-6),
                    "weights_reconstruction",
                )
                predictions[architecture, symbol] = w
                for period, _, _ in PERIODS:
                    arrays = prepared[symbol, period]["arrays"]
                    if arrays is not None:
                        w = predict(torch, recovered, arrays)
                        require(
                            np.allclose(w, predict(torch, policy, arrays), rtol=0, atol=1e-6),
                            "weights_reconstruction",
                        )
                        predictions[architecture, symbol, period] = w
            models.append(metadata)
        risks = risk_constants(prepared, contract["plan"], predictions, deadline=deadline)
    return evaluate(
        prepared, contract, pin, models, predictions, risks, runtime=runtime, deadline=deadline
    )


def run_worker(artifact_root, market_data_root, pin, path, deadline):
    output, contract = verify(artifact_root, market_data_root, pin)
    require(
        path == output / "worker-result.json"
        and not path.exists()
        and not path.is_symlink()
        and not (output / "summary.json").exists(),
        "worker_path",
    )
    require(
        json.loads(_read(output / "started.json")) == {"contract_sha256": pin}, "attempt_binding"
    )
    smoked, runtime = False, None
    try:
        import torch

        require(
            cpu_smoke(torch, deadline=deadline) == dict(cpu_smoke_passed=True, cpu_smoke_models=2),
            "cpu_smoke_required",
        )
        smoked = True
        torch.set_num_threads(2)
        require(
            torch.cuda.is_available()
            and torch.cuda.device_count() >= 1
            and str(torch.__version__) == contract["runtime"]["torch"],
            "CUDA_runtime",
        )
        torch.use_deterministic_algorithms(True)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cuda.matmul.allow_tf32 = False
        free, total = torch.cuda.mem_get_info(0)
        budget = min(int(total * 0.9), free - 1024**3)
        require(budget > 0, "available_VRAM")
        torch.cuda.set_per_process_memory_fraction(budget / total, 0)
        torch.cuda.reset_peak_memory_stats(0)
        runtime = dict(
            device=torch.cuda.get_device_name(0),
            torch=str(torch.__version__),
            cuda=str(torch.version.cuda),
            torch_threads=torch.get_num_threads(),
            free_before_bytes=free,
            total_bytes=total,
            memory_budget_bytes=budget,
            peak_allocated_bytes=0,
            training_device="cuda:0",
            inference_device="cpu",
        )
        rows = load_adjusted(market_data_root / base.SNAPSHOT, market_data_root)
        result = execute(
            torch,
            prepare(rows, contract["plan"]),
            contract,
            pin,
            output,
            device="cuda:0",
            runtime=runtime,
            deadline=deadline,
        )
        torch.cuda.synchronize(0)
        runtime["peak_allocated_bytes"] = torch.cuda.max_memory_allocated(0)
        _runtime(runtime, contract)
        validate_result(result, contract, pin)
        verify(artifact_root, market_data_root, pin)
        for model in result["models"]:
            read_weights(output / model["file"], model["architecture"], model["weights_sha256"])
    except Exception:
        result = failure(
            contract, pin, "runtime_or_invariant_failure", cpu_smoke_passed=smoked, runtime=runtime
        )
    atomic_new(path, result)


def worker_entry(*args):
    try:
        run_worker(*args)
    except BaseException:
        raise SystemExit(1) from None
