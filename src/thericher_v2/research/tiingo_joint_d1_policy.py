"""Frozen, seen-data three-ETF direct-utility development; never a Paper input."""

from __future__ import annotations

import importlib
import json
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path

import numpy as np

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.research import joint_d1_policy_context as context
from thericher_v2.research import tiingo_quarterly_joint_allocation as prior
from thericher_v2.research.artifact_paths import reject_repo_artifact_path
from thericher_v2.research.campaign_registry import register_campaign_outcome
from thericher_v2.research.differentiable_three_asset_nav import (
    WEIGHT_SUM_TOLERANCE,
    replay_torch,
)

ORIGINAL_NAME = "joint-d1-direct-utility-development-v1"
ORIGINAL_CONTRACT = "sha256:df42451eb7366d9d80231ae262c9bfcf6cdaddb61ebe3ab7dab28ed81d6564e0"
ORIGINAL_RESULT = "sha256:1d38b7b13ab308fe8bb9322c4e3e17d3c5a9704e0a011fe00dfb6b91bdab6079"
NAME = "joint-d1-direct-utility-development-v1-cpu-r2"
REPO, TRAIN, PERIODS, COSTS = prior.REPO, prior.TRAIN, prior.PERIODS, prior.COSTS
SYMBOLS = ("SPY", "QQQ", "IWM")
METHODS = ("constant", "linear", "tcn")
POLICIES = ("tcn", "linear", "constant", "cash", "quarter_ew", "tcn_beta_matched_quarter_ew_cash")
SEED, SECONDS = 101, 600
UPDATES = {"constant": 1024, "linear": 512, "tcn": 512}
CHANNELS, WINDOW, PAST_SESSIONS = 9, 31, 32
GPU_IMAGE = "sha256:d6b43213ee3877653e3c1e79c7238fb5caa71241abf238838fa0c3332cf4f039"
CODE = tuple(
    dict.fromkeys(
        (
            *prior.CODE,
            "src/thericher_v2/research/joint_d1_policy_context.py",
            "src/thericher_v2/research/differentiable_three_asset_nav.py",
            "src/thericher_v2/research/engine_research_agent.py",
            "src/thericher_v2/research/validation.py",
            "src/thericher_v2/research/tiingo_joint_d1_policy.py",
            "scripts/run_tiingo_joint_d1_policy.py",
        )
    )
)
TOL = Decimal("1e-10")
PARITY_ATOL, PARITY_RTOL = 1e-10, 1e-10
PHASES = {"synthetic_smoke", "source_input", "fit", "evaluate", "validate"}
INVARIANTS = {
    "analytic_parity",
    "gradient_parity",
    "smoke_gradient",
    "smoke_model",
    "source_symbols",
    "source_duplicate",
    "prepared_geometry",
    "train_unavailable",
    "torch_version",
    "gpu_unavailable",
    "desktop_headroom",
    "hard_timeout",
    "loss_nonfinite",
    "gradient_nonfinite",
    "vram_stop",
    "model_nonfinite",
    "model_method",
    "policy_geometry",
    "policy_simplex",
    "policy_weights",
    "policy_residual",
    "train_geometry",
    "scaled_context",
    "bundle_binding",
    "state_geometry",
    "state_keys",
    "beta_reference_zero_variance",
    "matched_fraction",
    "matching_replay_residual",
    "ledger_alignment",
    "ledger_nav",
    "ledger_returns",
    "ledger_fees",
    "ledger_terminal",
    "input_shape",
    "input_dtype",
    "input_device",
    "price_domain",
    "weight_domain",
    "fee_face_unavailable",
    "fee_faces_disagree",
    "fee_residual",
    "cashflow_residual",
    "numeric_range",
    "cost_bps_invalid",
    "runtime_changed",
    "code_changed",
    "result_binding",
    "cell_matrix",
    "fee_identity",
    "availability_binding",
    "fit_budget",
}
encode, digest, require, atomic_new = prior.encode, prior.digest, prior.require, prior.atomic_new


def configuration() -> dict:
    """No file, source, calendar, Torch or device access in the static plan."""
    return dict(
        symbols=list(SYMBOLS),
        train=list(TRAIN),
        periods=[list(p) for p in PERIODS],
        policies=list(POLICIES),
        costs_per_side_bps=list(COSTS),
        cells=36,
        inputs=dict(
            past_sessions=32,
            channel_count=9,
            ordered_observations=31,
            channels=list(context.CHANNELS),
            formulas=["log(C[t]/C[t-1])", "log(C[t]/O[t])", "log(H[t]/L[t])"],
            cutoff="NYSE OPEN; previous UTC-day-ended D1 sessions only",
            scaler="TRAIN population channel mean/std across windows; zero std ->1",
            missing="any required context gap -> period model input unavailable; "
            "any mark gap -> period replay unavailable; no shift/impute/support union",
            sample_rule="one scheduled causal window per session; overlapping windows and "
            "serial daily returns are not independent observations",
        ),
        models=dict(
            constant="four learned logits",
            linear="flatten9x31 ->4 logits",
            tcn="four left-padded Conv1d/ReLU: width8 kernel3 dilation1,2,4,8; "
            "last-step Linear8->4; receptive field31; no dropout/residual",
            output="four-way long-only softmax SPY/QQQ/IWM/cash",
            numeric="float64; CPU initialization then device transfer",
        ),
        fit=dict(
            seed=SEED,
            final_updates=dict(UPDATES),
            optimizer="AdamW",
            learning_rate={"constant": 0.01, "linear": 0.001, "tcn": 0.001},
            weight_decay={"constant": 0.0, "linear": 0.01, "tcn": 0.01},
            full_batch=True,
            continuous_train_path=True,
            final_update_only=True,
            detach_previous_actions=False,
            capital_reset_within_update=False,
            selection=False,
            training_cost_bps="10",
        ),
        objective="252*(mean daily log NAV growth-5*population variance)",
        ledger="exact eight analytic buy/sell faces; original absolute fee equation; "
        "vectorized daily prior-target OPEN drift/current CLOSE marking; "
        "shared cash/NAV1; initial entry/final CLOSE exit in existing observations",
        fee_face_tie="strict signs first; if none,32eps relative face roundoff; first valid "
        "(-1,+1) lexicographic face;256eps root/residual; one-sided kink gradient",
        decimal_targets="normalize four nonnegative float64 values; quantize first three45dp "
        "HALF_EVEN; cash exact residual; reject negative residual, no clipping",
        comparator="quarterly EW basket/cash; TRAIN0cost beta from aligned SIMPLE returns "
        "against zero-cost buyhold SPY marked daily CLOSE; endpoints sign bracket,"
        "64 bisections,residual<=1e-10; "
        "fraction quantized45dp, fixed across periods/costs; no monotonic assumption",
        matching_unresolved="matched comparison unavailable only; no substitute/outcome search",
        strongest_kill="10bps BOTH folds: positive growth; "
        "TCN NAV+utility>matched/constant/linear; "
        "TCN utility>quarterEW; all differences>1e-10",
        stress="each fixed-path calendar-year deletion at10bps; delete identical year keys "
        "from original daily log returns including partial2026; descriptive only, "
        "never rescues/changes criterion; no trades/refit/calibration/new execution",
        tolerances=dict(
            weight_sum=WEIGHT_SUM_TOLERANCE,
            ledger_atol=PARITY_ATOL,
            ledger_rtol=PARITY_RTOL,
            gradient_atol=1e-7,
            gradient_rtol=1e-5,
            improvement="1e-10",
            cpu_readback="exact canonical JSON",
            inference="authoritative CPU from retained float64 state; no fit",
        ),
        budget=dict(
            family_seconds=SECONDS,
            actual_fits=3,
            device="cpu",
            original_seconds_consumed=600,
            maximum_total_attempt_seconds=1200,
            maximum_total_fit_starts=6,
            additional_attempts=1,
            original_partial_fit_count="unknown",
            cpu_threads=2,
            memory_bytes=6 * 1024**3,
            container_cpus=2,
            network="none",
            swap_bytes=0,
            retries=False,
            worker_lock=f"research/{NAME}/cpu-attempt.lock",
            gpu_allocation=False,
        ),
        runtime=dict(
            image=GPU_IMAGE, torch="2.7.0+cu128", numpy="2.5.1", python="3.12.14", calendar="5.4.0"
        ),
        lineage=[
            "tiingo-adjusted-monthly-holding-development-v1",
            "firstrate-paired-allocation-development-20261005-v1",
            prior.NAME,
            ORIGINAL_NAME,
        ],
        technical_continuation=dict(
            original_contract_sha256=ORIGINAL_CONTRACT,
            original_result_sha256=ORIGINAL_RESULT,
            original_completion="hard_timeout; phase/partial fits unknown",
            reason="synthetic float64 CUDA TCN512 steps alone forecast648s vs56s CPU",
            changed="CPU execution and bounded pure logarithm memoization only",
            economic_changes=False,
            budget_refund=False,
            further_retry=False,
            numerical_trajectory="CPU may differ from CUDA; not identical fitted weights",
        ),
        scope=dict(
            holdout_access="none",
            seen_revised_non_pit=True,
            promotion=False,
            paper_input=False,
            selection=False,
            source_independence=False,
        ),
        limitations=[
            "retained revised OHLC; conditional availability, not decision-time proof",
            "fractional adjusted NAV proxy; not broker fills; cash interest zero",
            "three surviving correlated ETFs; no short/leverage/new assets",
            "earlier outcomes and these comparison periods already seen",
        ],
    )


def torch_cpu():
    import torch

    torch.set_num_threads(2)
    return torch


def model(method: str):
    """Initialize CPU only; never call a CUDA availability or seed API here."""
    require(method in METHODS, "model_method")
    torch = torch_cpu()

    class Constant(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.logits = torch.nn.Parameter(torch.zeros(4, dtype=torch.float64))

        def forward(self, x):
            return self.logits.softmax(-1).expand(len(x), 4)

    class Linear(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.output = torch.nn.Linear(CHANNELS * WINDOW, 4, dtype=torch.float64)

        def forward(self, x):
            return self.output(x.flatten(1)).softmax(-1)

    class TCN(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.layers = torch.nn.ModuleList(
                [
                    torch.nn.Conv1d(
                        CHANNELS if i == 0 else 8, 8, 3, dilation=d, dtype=torch.float64
                    )
                    for i, d in enumerate((1, 2, 4, 8))
                ]
            )
            self.output = torch.nn.Linear(8, 4, dtype=torch.float64)

        def representation(self, x):
            for layer in self.layers:
                x = torch.relu(layer(torch.nn.functional.pad(x, (2 * layer.dilation[0], 0))))
            return x

        def forward(self, x):
            return self.output(self.representation(x)[:, :, -1]).softmax(-1)

    # Fork only the CPU generator so restoration has no GPU side effects.
    state = torch.random.default_generator.get_state()
    try:
        torch.random.default_generator.manual_seed(SEED)
        return {"constant": Constant, "linear": Linear, "tcn": TCN}[method]()
    finally:
        torch.random.default_generator.set_state(state)


def array(values, shape: tuple | None, category: str) -> np.ndarray:
    try:
        result = np.asarray(values, dtype=np.float64)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(category) from None
    require((shape is None or result.shape == shape) and np.isfinite(result).all(), category)
    return result


def json_numbers(value, category):
    require((type(value) in {int, float} and np.isfinite(value)) or type(value) is list, category)
    if type(value) is list:
        for child in value:
            json_numbers(child, category)


@dataclass(frozen=True, slots=True)
class ChannelScaler:
    mean: np.ndarray = field(repr=False)
    scale: np.ndarray = field(repr=False)

    def payload(self):
        return dict(mean=self.mean.tolist(), scale=self.scale.tolist())

    def transform(self, x):
        x = array(x, None, "context_array")
        require(x.ndim == 3 and x.shape[1:] == (CHANNELS, WINDOW), "context_geometry")
        return array(
            (x - self.mean[None, :, None]) / self.scale[None, :, None], x.shape, "scaled_context"
        )

    @classmethod
    def restore(cls, payload):
        require(type(payload) is dict and set(payload) == {"mean", "scale"}, "scaler_fields")
        json_numbers(payload["mean"], "scaler_mean")
        json_numbers(payload["scale"], "scaler_scale")
        mean = array(payload["mean"], (CHANNELS,), "scaler_mean")
        scale = array(payload["scale"], (CHANNELS,), "scaler_scale")
        require(np.all(scale > 0), "scaler_positive")
        return cls(mean, scale)


def train_scaler(x) -> ChannelScaler:
    x = array(x, None, "train_context")
    require(x.ndim == 3 and x.shape[1:] == (CHANNELS, WINDOW) and len(x) > 0, "train_geometry")
    mean = array(x.mean(axis=(0, 2)), (CHANNELS,), "train_scaler_mean")
    scale = array(x.std(axis=(0, 2), ddof=0), (CHANNELS,), "train_scaler_scale")
    return ChannelScaler(mean, np.where(scale == 0, 1.0, scale))


def numeric_state(net) -> dict:
    state = {k: t.detach().cpu().tolist() for k, t in net.state_dict().items()}
    require(all(np.isfinite(v).all() for v in state.values()), "model_nonfinite")
    return state


def restore_model(method: str, payload):
    torch, net = torch_cpu(), model(method)
    template = net.state_dict()
    require(type(payload) is dict and set(payload) == set(template), "state_keys")
    for value in payload.values():
        json_numbers(value, "state_geometry")
    net.load_state_dict(
        {
            k: torch.tensor(
                array(payload[k], tuple(t.shape), "state_geometry"), dtype=torch.float64
            )
            for k, t in template.items()
        },
        strict=True,
    )
    net.eval()
    return net


def infer(method: str, state: dict, scaler: ChannelScaler, x) -> np.ndarray:
    torch, net = torch_cpu(), restore_model(method, state)
    with torch.no_grad():
        out = net(torch.tensor(scaler.transform(x), dtype=torch.float64)).numpy()
    out = array(out, (len(x), 4), "policy_geometry")
    require(np.all(out >= 0) and np.allclose(out.sum(1), 1, atol=1e-14, rtol=0), "policy_simplex")
    return out


def decimal_target(weights):
    """A fixed conversion lattice, not a data-dependent feasibility repair."""
    ledger = importlib.import_module(prior.LEDGER_MODULE)
    values = array(weights, (4,), "policy_weights")
    require(
        np.all((values >= 0) & (values <= 1)) and abs(values.sum() - 1) <= WEIGHT_SUM_TOLERANCE,
        "policy_weights",
    )
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 50, ROUND_HALF_EVEN
        numeric = tuple(Decimal.from_float(float(v)) for v in values)
        total = sum(numeric, Decimal(0))
        assets = tuple((v / total).quantize(prior.WEIGHT_QUANTUM) for v in numeric[:3])
        cash = Decimal(1) - sum(assets, Decimal(0))
        require(cash >= 0, "policy_residual")
        return ledger.ThreeAssetTarget(assets, cash)


def utility_logs(logs) -> Decimal:
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 50, ROUND_HALF_EVEN
        require(bool(logs) and all(type(v) is Decimal and v.is_finite() for v in logs), "log_path")
        mean = sum(logs, Decimal(0)) / len(logs)
        variance = sum(((v - mean) ** 2 for v in logs), Decimal(0)) / len(logs)
        return 252 * (mean - 5 * variance)


def torch_utility(path):
    logs = path.log_returns
    return 252 * (logs.mean() - 5 * ((logs - logs.mean()) ** 2).mean())


def mark_tensors(inputs: PreparedPeriod, *, device="cpu"):
    torch = torch_cpu()
    require(inputs.marks is not None, "training_marks_unavailable")
    return tuple(
        torch.tensor(
            [[float(v) for v in getattr(day, field)] for day in inputs.marks],
            dtype=torch.float64,
            device=device,
        )
        for field in ("adj_open3", "adj_close3")
    )


def fit_final(
    method,
    inputs,
    scaler,
    *,
    updates: int,
    device: str,
    deadline: float,
    vram_bytes=None,
    progress=None,
):
    """One continuous TRAIN path and global population variance on each update."""
    torch = torch_cpu()
    require(inputs.x is not None and inputs.marks is not None, "train_unavailable")
    net = model(method).to(device)
    x = torch.tensor(scaler.transform(inputs.x), dtype=torch.float64, device=device)
    opened, closed = mark_tensors(inputs, device=device)
    config = configuration()["fit"]
    optimizer = torch.optim.AdamW(
        net.parameters(),
        lr=config["learning_rate"][method],
        weight_decay=config["weight_decay"][method],
    )
    for update in range(updates):
        require(time.monotonic() < deadline, "hard_timeout")
        optimizer.zero_grad(set_to_none=True)
        loss = -torch_utility(replay_torch(opened, closed, net(x), 10.0))
        require(bool(torch.isfinite(loss)), "loss_nonfinite")
        loss.backward()
        require(
            all(
                p.grad is not None and bool(torch.isfinite(p.grad).all()) for p in net.parameters()
            ),
            "gradient_nonfinite",
        )
        optimizer.step()
        if progress is not None and ((update + 1) % 128 == 0 or update + 1 == updates):
            progress("fit", method, update + 1)
        if device == "cuda":
            torch.cuda.synchronize()
            require(torch.cuda.max_memory_allocated() <= vram_bytes, "vram_stop")
    require(time.monotonic() < deadline, "hard_timeout")
    return numeric_state(net)


def bundle_identity(bundle, pin):
    require(
        type(bundle) is dict
        and set(bundle) == {"version", "contract_sha256", "scaler", "states", "updates"}
        and bundle["version"] == 1
        and bundle["contract_sha256"] == pin
        and bundle["updates"] == UPDATES
        and set(bundle["states"]) == set(METHODS),
        "bundle_binding",
    )
    ChannelScaler.restore(bundle["scaler"])
    for method in METHODS:
        restore_model(method, bundle["states"][method])


def fit_bundle(train, pin, *, deadline, progress=None):
    require(train.x is not None and train.marks is not None, "train_unavailable")
    torch = torch_cpu()
    require(torch.__version__ == configuration()["runtime"]["torch"], "torch_version")
    torch.use_deterministic_algorithms(True)
    scaler, states, measured = train_scaler(train.x), {}, []
    for method in METHODS:
        start = time.monotonic()
        if progress is not None:
            progress("fit", method, 0)
        states[method] = fit_final(
            method,
            train,
            scaler,
            updates=UPDATES[method],
            device="cpu",
            deadline=deadline,
            progress=progress,
        )
        measured.append(
            dict(method=method, updates=UPDATES[method], elapsed_seconds=time.monotonic() - start)
        )
    bundle = dict(
        version=1,
        contract_sha256=pin,
        scaler=scaler.payload(),
        states=states,
        updates=dict(UPDATES),
    )
    bundle_identity(bundle, pin)
    return bundle, dict(
        device="cpu",
        fits=3,
        peak_allocated_bytes=0,
        allocator_cap_bytes=0,
        fit_durations=measured,
    )


def synthetic_inputs() -> PreparedPeriod:
    ledger = importlib.import_module(prior.LEDGER_MODULE)
    start = date(2001, 1, 1)
    rows = {s: [] for s in SYMBOLS}
    for i in range(39):
        day = start + timedelta(days=i)
        for j, symbol in enumerate(SYMBOLS):
            with localcontext() as ctx:
                ctx.prec = 50
                opened = Decimal(100 + j * 12 + i) / 100
                closed = opened * (1 + Decimal(((i + j) % 5) - 2) / 100)
                rows[symbol].append(
                    prior.data.AdjustedEtfRow(
                        symbol,
                        day,
                        opened,
                        max(opened, closed) * Decimal("1.01"),
                        min(opened, closed) * Decimal(".99"),
                        closed,
                    )
                )
    days = [(start + timedelta(days=i)).isoformat() for i in range(39)]
    plan = dict(
        days=days,
        periods=[
            dict(
                period="TRAIN",
                bounds=[32, 38],
                quarters=[32],
                decisions=[
                    dict(
                        index=i,
                        session_date=days[i],
                        decision_at=f"{days[i]}T14:30:00+00:00",
                        scheduled_dates=days[i - 32 : i],
                    )
                    for i in range(32, 38)
                ],
            )
        ],
    )
    prepared = prepare_inputs(rows, plan, deadline=float("inf"))[0]
    require(prepared.x is not None and prepared.marks is not None, "synthetic_input")
    require(tuple(m.date for m in prepared.marks) == prepared.dates, "synthetic_alignment")
    require(tuple(ledger.SYMBOLS) == SYMBOLS, "ledger_columns")
    return prepared


def analytical_parity() -> dict:
    """Actual core APIs, synthetic CPU only, before constructing any model."""
    torch, inputs = torch_cpu(), synthetic_inputs()
    opened, closed = mark_tensors(inputs)
    scenarios = (
        np.tile([0.0, 0.0, 0.0, 1.0], (6, 1)),
        np.tile([1.0, 0.0, 0.0, 0.0], (6, 1)),
        np.array(
            [
                [0.2, 0.3, 0.1, 0.4],
                [0.3, 0.1, 0.4, 0.2],
                [0.1, 0.4, 0.2, 0.3],
                [0.4, 0.2, 0.3, 0.1],
                [0.2, 0.1, 0.3, 0.4],
                [0.3, 0.2, 0.1, 0.4],
            ]
        ),
    )
    for weights in scenarios:
        for cost in (0.0, 2.5, 5.0, 10.0):
            expected = replay_decimal(inputs, weights, str(cost))
            actual = replay_torch(opened, closed, torch.tensor(weights, dtype=torch.float64), cost)
            for got, wanted in (
                (actual.nav, expected.navs),
                (actual.log_returns, expected.log_returns),
                (actual.fees, tuple(d.fees for d in expected.daily)),
                (actual.traded_notional, tuple(d.traded_notional for d in expected.daily)),
                (actual.cash, tuple(d.cash for d in expected.daily)),
            ):
                require(
                    np.allclose(
                        got.detach().numpy(),
                        [float(v) for v in wanted],
                        atol=PARITY_ATOL,
                        rtol=PARITY_RTOL,
                    ),
                    "analytic_parity",
                )
    logits = torch.tensor(np.log(scenarios[-1]), dtype=torch.float64, requires_grad=True)
    value = torch_utility(replay_torch(opened, closed, logits.softmax(-1), 10.0))
    (gradient,) = torch.autograd.grad(value, logits)
    checks = 0
    for row, col in ((0, 0), (2, 1), (5, 3)):
        plus, minus = logits.detach().clone(), logits.detach().clone()
        plus[row, col] += 1e-6
        minus[row, col] -= 1e-6
        difference = (
            torch_utility(replay_torch(opened, closed, plus.softmax(-1), 10.0))
            - torch_utility(replay_torch(opened, closed, minus.softmax(-1), 10.0))
        ) / 2e-6
        require(
            torch.isclose(gradient[row, col], difference, atol=1e-7, rtol=1e-5), "gradient_parity"
        )
        checks += 1
    return dict(
        status="parity_passed",
        scenarios=12,
        fields_per_scenario=5,
        gradient_checks=checks,
        device="cpu",
        source_rows=0,
        gpu_probes=0,
    )


def smoke(*, contract: dict | None = None, pin: str | None = None) -> dict:
    start = time.monotonic()
    if contract is not None:
        header(contract, pin)
    parity = analytical_parity()
    inputs = synthetic_inputs()
    scaler = train_scaler(inputs.x)
    torch = torch_cpu()
    for method in METHODS:
        net = model(method)
        x = torch.tensor(scaler.transform(inputs.x), dtype=torch.float64)
        opened, closed = mark_tensors(inputs)
        value = torch_utility(replay_torch(opened, closed, net(x), 10.0))
        value.backward()
        require(
            all(
                p.grad is not None and bool(torch.isfinite(p.grad).all()) for p in net.parameters()
            ),
            "smoke_gradient",
        )
        state = numeric_state(net)
        weights = infer(method, state, scaler, inputs.x)
        require(weights.shape == (6, 4), "smoke_model")
    return dict(
        status="synthetic_cpu_passed",
        config_sha256=digest(encode(configuration())),
        contract_sha256=pin,
        code_sha256=code_identity(),
        runtime=runtime_identity(),
        parity=parity,
        model_smokes=3,
        actual_fits=0,
        synthetic_fits=0,
        optimizer_constructions=0,
        actual_source_rows=0,
        registry_access=False,
        gpu_probes=0,
        elapsed_seconds=time.monotonic() - start,
    )


def build_plan(schedule: Sequence[Mapping]) -> dict:
    # Reuse calendar validation, but all scheduled sessions now have their own causal input.
    old = prior.build_plan(schedule)
    periods = []
    for p in old["periods"]:
        a, b = p["bounds"]
        require(a >= PAST_SESSIONS, "calendar_prior_context")
        periods.append(
            dict(
                period=p["period"],
                bounds=[a, b],
                quarters=[d["index"] for d in p["decisions"]],
                counts=dict(
                    scheduled_sessions=b - a,
                    windows=b - a,
                    unique_required_past_sessions=b - a + PAST_SESSIONS - 1,
                    calendar_year_blocks=sorted(
                        {date.fromisoformat(d).year for d in old["days"][a:b]}
                    ),
                ),
                decisions=[
                    dict(
                        index=i,
                        session_date=old["days"][i],
                        decision_at=schedule[i]["open_at"],
                        scheduled_dates=old["days"][i - PAST_SESSIONS : i],
                    )
                    for i in range(a, b)
                ],
            )
        )
    return dict(schedule=old["schedule"], days=old["days"], periods=periods)


@dataclass(frozen=True, slots=True)
class PreparedPeriod:
    period: str
    dates: tuple[date, ...]
    quarters: tuple[int, ...]
    x: np.ndarray | None = field(repr=False)
    marks: tuple | None = field(repr=False)
    facts: dict = field(repr=False)


def prepare_inputs(
    rows_by_symbol: Mapping, plan: dict, *, deadline: float
) -> tuple[PreparedPeriod, ...]:
    require(set(rows_by_symbol) == set(SYMBOLS), "source_symbols")
    ledger = importlib.import_module(prior.LEDGER_MODULE)
    rows, bars = {}, {}
    for symbol in SYMBOLS:
        rows[symbol], bars[symbol] = {}, {}
        for row in rows_by_symbol[symbol]:
            require(row.session_date not in rows[symbol], "source_duplicate")
            rows[symbol][row.session_date] = row
            try:
                bars[symbol][row.session_date] = Bar(
                    symbol=symbol,
                    market="US",
                    timeframe=Timeframe.D1,
                    start_ts=datetime.combine(row.session_date, datetime.min.time(), UTC),
                    open=row.adj_open,
                    high=row.adj_high,
                    low=row.adj_low,
                    close=row.adj_close,
                    volume=Decimal(0),
                    complete=True,
                )
            except (ValueError, TypeError, ArithmeticError):
                # Invalid required past values are unavailable, never replaced/imputed.
                bars[symbol][row.session_date] = None
    vintages = dict.fromkeys(SYMBOLS, digest(encode(prior.source_identity())))
    result = []
    with context.JointD1PolicyLogMemo() as log_memo:
        for spec in plan["periods"]:
            a, b = spec["bounds"]
            dates = tuple(date.fromisoformat(d) for d in plan["days"][a:b])
            features, input_facts = [], []
            for decision in spec["decisions"]:
                require(time.monotonic() < deadline, "hard_timeout")
                needed = tuple(date.fromisoformat(d) for d in decision["scheduled_dates"])
                try:
                    past = {
                        s: tuple(bars[s][d] for d in needed if bars[s].get(d) is not None)
                        for s in SYMBOLS
                    }
                    window = context.build_joint_d1_policy_context(
                        past,
                        vintage_ref_by_symbol=vintages,
                        scheduled_dates=needed,
                        decision_at=datetime.fromisoformat(decision["decision_at"]),
                        log_memo=log_memo,
                    )
                    features.append(window.features)
                    facts = dict(session_date=decision["session_date"], status="ready")
                except context.JointD1PolicyInputUnavailable as exc:
                    facts = dict(session_date=decision["session_date"], **exc.safe_facts())
                input_facts.append(facts)
            marks, missing, invalid = [], 0, 0
            # Mark availability is separate from causal feature eligibility.
            for day in dates:
                if any(day not in rows[s] for s in SYMBOLS):
                    missing += 1
                    continue
                try:
                    marks.append(
                        ledger.ThreeAssetDay(
                            day,
                            tuple(rows[s][day].adj_open for s in SYMBOLS),
                            tuple(rows[s][day].adj_close for s in SYMBOLS),
                        )
                    )
                except (ValueError, TypeError, ArithmeticError):
                    invalid += 1
            ready = len(features) == len(dates)
            result.append(
                PreparedPeriod(
                    spec["period"],
                    dates,
                    tuple(i - a for i in spec["quarters"]),
                    array(features, (len(dates), CHANNELS, WINDOW), "prepared_geometry")
                    if ready
                    else None,
                    tuple(marks) if not (missing or invalid) else None,
                    dict(
                        period=spec["period"],
                        sessions=len(dates),
                        quarters=len(spec["quarters"]),
                        missing_marks=missing,
                        invalid_marks=invalid,
                        missing_inputs=sum(f["status"] != "ready" for f in input_facts),
                        inputs=input_facts,
                    ),
                )
            )
    return tuple(result)


def replay_decimal(inputs: PreparedPeriod, weights, cost: str, *, quarterly: bool = False):
    ledger = importlib.import_module(prior.LEDGER_MODULE)
    require(inputs.marks is not None, "replay_marks_unavailable")
    weights = array(weights, (len(inputs.dates), 4), "replay_weights")
    indices = inputs.quarters if quarterly else range(len(inputs.dates))
    return ledger.replay(
        inputs.marks, {inputs.dates[i]: decimal_target(weights[i]) for i in indices}, Decimal(cost)
    )


def basket_weights(inputs: PreparedPeriod, fraction: Decimal = Decimal(1)) -> np.ndarray:
    assets = prior._scaled_equal_weight(fraction)
    with localcontext() as ctx:
        ctx.prec = 50
        cash = Decimal(1) - sum(assets, Decimal(0))
    return np.tile([float(v) for v in (*assets, cash)], (len(inputs.dates), 1))


def replay_basket(inputs: PreparedPeriod, cost: str, fraction: Decimal):
    # Keep TRAIN matching on the exact45dp Decimal fraction, not a float round trip.
    ledger = importlib.import_module(prior.LEDGER_MODULE)
    require(inputs.marks is not None, "replay_marks_unavailable")
    assets = prior._scaled_equal_weight(fraction)
    with localcontext() as ctx:
        ctx.prec = 50
        target = ledger.ThreeAssetTarget(assets, Decimal(1) - sum(assets, Decimal(0)))
    return ledger.replay(
        inputs.marks, {inputs.dates[i]: target for i in inputs.quarters}, Decimal(cost)
    )


def train_match(inputs: PreparedPeriod, tcn_weights, *, restored=None, deadline=float("inf")):
    require(time.monotonic() < deadline, "hard_timeout")
    if inputs.x is None or inputs.marks is None or tcn_weights is None:
        return prior.BetaMatch(None, "comparison_unresolved", "train_input_unavailable", 0)
    spy = np.tile([1.0, 0.0, 0.0, 0.0], (len(inputs.dates), 1))
    ledger = importlib.import_module(prior.LEDGER_MODULE)
    reference = ledger.replay(inputs.marks, {inputs.dates[0]: decimal_target(spy[0])}, Decimal(0))
    if len(set(reference.simple_returns)) == 1:
        return prior.BetaMatch(None, "comparison_unresolved", "beta_reference_zero_variance", 0)
    target = prior.beta(
        replay_decimal(inputs, tcn_weights, "0").simple_returns, reference.simple_returns
    )

    def callback(c):
        require(time.monotonic() < deadline, "hard_timeout")
        return prior.beta(replay_basket(inputs, "0", c).simple_returns, reference.simple_returns)

    if restored is None:
        return prior.match_beta(target, callback)
    if restored.fraction is not None:
        require(abs(callback(restored.fraction) - target) <= TOL, "matching_replay_residual")
    else:
        left, right = callback(Decimal(0)) - target, callback(Decimal(1)) - target
        require(abs(left) > TOL and abs(right) > TOL, "matching_replay_endpoints")
        if restored.reason == "beta_not_bracketed":
            require((left > 0) == (right > 0), "matching_replay_bracket")
        else:
            require(
                restored.reason == "beta_residual_exceeded"
                and restored.iterations == 64
                and (left > 0) != (right > 0)
                and restored.residual_probe is not None
                and abs(callback(restored.residual_probe) - target) > TOL,
                "matching_replay_failure",
            )
    return restored


def _numeric(v: Decimal) -> str:
    require(type(v) is Decimal and v.is_finite(), "numeric_result")
    return str(v)


def matching_payload(match) -> dict:
    return dict(
        match.safe_facts(),
        invested_fraction=None if match.fraction is None else str(match.fraction),
        residual_probe=None if match.residual_probe is None else str(match.residual_probe),
    )


def restore_match(payload):
    match = prior.BetaMatch(
        None if payload["invested_fraction"] is None else Decimal(payload["invested_fraction"]),
        payload["status"],
        payload["reason_code"],
        payload["iterations"],
        None if payload["residual_probe"] is None else Decimal(payload["residual_probe"]),
    )
    require(matching_payload(match) == payload, "match_identity")
    return match


def primary_verdict(cells: Sequence[Mapping]) -> str:
    primary = [c for c in cells if c["cost_per_side_bps"] == "10"]
    if len(primary) != 12 or any(c["status"] != "evaluated" for c in primary):
        return "input_unavailable"
    with localcontext() as ctx:
        ctx.prec = 50
        for period, _, _ in PERIODS:
            group = {c["policy"]: c for c in primary if c["period"] == period}
            candidate = group["tcn"]
            if Decimal(candidate["final_nav"]) - 1 <= TOL:
                return "rejected"
            for policy in ("constant", "linear", "tcn_beta_matched_quarter_ew_cash"):
                if any(
                    Decimal(candidate[k]) - Decimal(group[policy][k]) <= TOL
                    for k in ("final_nav", "utility")
                ):
                    return "rejected"
            if Decimal(candidate["utility"]) - Decimal(group["quarter_ew"]["utility"]) <= TOL:
                return "rejected"
    return "supported_with_limits"


def yearly_attribution(inputs: PreparedPeriod, paths: dict) -> list[dict]:
    """Delete retained daily return keys, not trades or rebalanced strategy paths."""
    result = []
    for year in sorted({d.year for d in inputs.dates}):
        kept = [i for i, d in enumerate(inputs.dates) if d.year != year]
        for policy in POLICIES:
            path = paths.get(policy)
            item = dict(
                period=inputs.period,
                deleted_year=year,
                policy=policy,
                remaining_sessions=len(kept),
                status="input_unavailable",
                final_growth=None,
                utility=None,
            )
            if path is not None and kept:
                logs = tuple(path.log_returns[i] for i in kept)
                with localcontext() as ctx:
                    ctx.prec = 50
                    growth = sum(logs, Decimal(0)).exp()
                item.update(
                    status="descriptive_only",
                    final_growth=_numeric(growth),
                    utility=_numeric(utility_logs(logs)),
                )
            result.append(item)
    return result


def evaluate(prepared, bundle, contract, pin, *, deadline: float, restored_match=None) -> dict:
    result = header(contract, pin)
    scaler = None if bundle is None else ChannelScaler.restore(bundle["scaler"])
    predictions = []
    for inputs in prepared:
        require(time.monotonic() < deadline, "hard_timeout")
        predictions.append(
            {m: infer(m, bundle["states"][m], scaler, inputs.x) for m in METHODS}
            if bundle is not None and inputs.x is not None
            else {}
        )
    match = train_match(
        prepared[0], predictions[0].get("tcn"), restored=restored_match, deadline=deadline
    )
    cells, attribution = [], []
    for inputs, predicted in zip(prepared[1:], predictions[1:], strict=True):
        primary_paths = {}
        for cost in COSTS:
            for policy in POLICIES:
                require(time.monotonic() < deadline, "hard_timeout")
                cell = dict(
                    period=inputs.period,
                    policy=policy,
                    cost_per_side_bps=cost,
                    status="input_unavailable",
                    action_sha256=None,
                    trades=None,
                    **dict.fromkeys(prior.METRICS),
                )
                path, action_identity = None, None
                if inputs.marks is not None:
                    if policy in METHODS and policy in predicted:
                        weights = predicted[policy]
                        path = replay_decimal(inputs, weights, cost)
                        action_identity = [
                            [
                                d.isoformat(),
                                [
                                    str(v)
                                    for v in (
                                        *decimal_target(w).weights3,
                                        decimal_target(w).cash_weight,
                                    )
                                ],
                            ]
                            for d, w in zip(inputs.dates, weights, strict=True)
                        ]
                    elif policy == "cash":
                        path = replay_decimal(
                            inputs, np.tile([0.0, 0.0, 0.0, 1.0], (len(inputs.dates), 1)), cost
                        )
                        action_identity = "cash"
                    elif policy == "quarter_ew" or (
                        policy == "tcn_beta_matched_quarter_ew_cash" and match.fraction is not None
                    ):
                        fraction = Decimal(1) if policy == "quarter_ew" else match.fraction
                        path = replay_basket(inputs, cost, fraction)
                        action_identity = dict(
                            quarter_indices=list(inputs.quarters), fraction=str(fraction)
                        )
                if path is not None:
                    checked = prior.checked_path(
                        dict(
                            navs=path.navs,
                            returns=path.simple_returns,
                            fees_initial_nav=path.total_fees,
                            turnover_initial_nav=path.total_traded_notional,
                            final_nav=path.final_nav,
                            trades=sum(d.traded_notional > 0 for d in path.daily),
                        ),
                        len(inputs.dates),
                        cost,
                    )
                    cell.update(
                        status="evaluated",
                        action_sha256=digest(encode(action_identity)),
                        trades=checked.trades,
                        final_nav=_numeric(checked.navs[-1]),
                        utility=_numeric(utility_logs(path.log_returns)),
                        fees_initial_nav=_numeric(checked.fees),
                        turnover_initial_nav=_numeric(checked.turnover),
                    )
                    if cost == "10":
                        primary_paths[policy] = path
                cells.append(cell)
        attribution.extend(yearly_attribution(inputs, primary_paths))
    result.update(
        status="complete"
        if all(c["status"] == "evaluated" for c in cells)
        else "input_unavailable",
        criterion=primary_verdict(cells),
        coverage=[p.facts for p in prepared],
        matching=matching_payload(match),
        cells=cells,
        year_deletions=attribution,
        model_sha256=None if bundle is None else digest(encode(bundle)),
    )
    return result


def runtime_identity() -> dict:
    from importlib.metadata import version
    from platform import python_version

    return dict(
        python=python_version(),
        numpy=np.__version__,
        torch=torch_cpu().__version__,
        calendar=version("pandas-market-calendars"),
    )


def code_identity() -> dict:
    return {p: digest((REPO / p).read_bytes()) for p in CODE}


def proposed_contract() -> dict:
    config, source, runtime = configuration(), prior.source_identity(), runtime_identity()
    require(all(runtime[k] == config["runtime"][k] for k in runtime), "runtime_version")
    return dict(
        name=NAME,
        config=config,
        config_sha256=digest(encode(config)),
        source=source,
        source_sha256=digest(encode(source)),
        runtime=runtime,
        plan=build_plan(prior.calendar_schedule()),
        code_sha256=code_identity(),
    )


def header(contract: dict, pin: str) -> dict:
    require(
        set(contract)
        == {
            "name",
            "config",
            "config_sha256",
            "source",
            "source_sha256",
            "runtime",
            "plan",
            "code_sha256",
        },
        "contract_fields",
    )
    require(contract["name"] == NAME and digest(encode(contract)) == pin, "contract_binding")
    config, source = configuration(), prior.source_identity()
    require(
        contract["config"] == config and contract["config_sha256"] == digest(encode(config)),
        "config_changed",
    )
    require(
        contract["source"] == source and contract["source_sha256"] == digest(encode(source)),
        "source_changed",
    )
    require(contract["runtime"] == runtime_identity(), "runtime_changed")
    require(contract["plan"] == build_plan(contract["plan"]["schedule"]), "plan_changed")
    require(contract["code_sha256"] == code_identity(), "code_changed")
    return dict(
        name=NAME,
        contract_sha256=pin,
        config_sha256=contract["config_sha256"],
        source_sha256=contract["source_sha256"],
        scope=config["scope"],
    )


def _output(root: Path) -> Path:
    path = Path(root).absolute() / "research" / NAME
    reject_repo_artifact_path(path, REPO)
    require(all(not p.is_symlink() for p in (path, *path.parents)), "artifact_link")
    require(path.is_dir(), "artifact_missing")
    return path


def register_contract(root: Path, contract: dict, pin: str):
    header(contract, pin)
    prior.base.register_frozen_campaign(
        contract_hash=pin,
        dataset_hash=digest(encode(contract["source"])),
        split_hash=digest(encode(contract["plan"])),
        cost_model_hash=digest(encode({"costs": COSTS, "ledger": configuration()["ledger"]})),
        trial_family=ORIGINAL_NAME,
        holdout_access="none",
        artifact_root=root,
        repo_root=REPO,
    )


def freeze(artifact_root: Path, market_data_root: Path) -> str:
    verify_original_attempt(artifact_root)
    prior.base.verify_metadata(artifact_root, market_data_root)
    contract = proposed_contract()
    parent = prior.base.ensure_external_artifact_directory(artifact_root, REPO, "research")
    output = parent / NAME
    output.mkdir()
    atomic_new(output / "precommit.json", contract)
    pin = digest(encode(contract))
    register_contract(artifact_root, contract, pin)
    return pin


def verify(artifact_root, market_data_root, pin):
    verify_original_attempt(artifact_root)
    output = _output(artifact_root)
    raw = prior._read(output / "precommit.json")
    require(digest(raw) == pin, "precommit_changed")
    contract = json.loads(raw)
    header(contract, pin)
    require(raw == encode(contract), "precommit_encoding")
    prior.base.verify_metadata(artifact_root, market_data_root)
    return output, contract


def verify_original_attempt(root):
    """Technical continuation cannot refund, replace or silently lose its failed parent."""
    path = Path(root) / "research" / ORIGINAL_NAME
    reject_repo_artifact_path(path, REPO)
    require(all(not p.is_symlink() for p in (path, *path.parents)), "original_attempt_link")
    raw_contract = prior._read(path / "precommit.json")
    raw_result = prior._read(path / "summary.json")
    require(digest(raw_contract) == ORIGINAL_CONTRACT, "original_contract_changed")
    require(digest(raw_result) == ORIGINAL_RESULT, "original_result_changed")
    failed = json.loads(raw_result)
    require(
        failed.get("name") == ORIGINAL_NAME
        and failed.get("contract_sha256") == ORIGINAL_CONTRACT
        and failed.get("status") == "failed"
        and failed.get("reason") == "hard_timeout"
        and failed.get("model_sha256") is None,
        "original_failure_binding",
    )


def progress_recorder(output, pin, deadline):
    """Bounded diagnostic counters, never partial weights or comparative outcomes."""

    def record(phase, method=None, updates=None):
        require(phase in PHASES, "progress_phase")
        if phase == "fit":
            require(method in METHODS, "progress_method")
            require(type(updates) is int and 0 <= updates <= UPDATES[method], "progress_updates")
            require(updates % 128 == 0 or updates == UPDATES[method], "progress_interval")
            name = f"progress-fit-{method}-{updates:04d}.json"
        else:
            require(method is None and updates is None, "progress_fields")
            name = f"progress-{phase}.json"
        elapsed = time.monotonic() - (deadline - SECONDS)
        require(0 <= elapsed <= SECONDS, "hard_timeout")
        atomic_new(
            output / name,
            dict(
                contract_sha256=pin,
                phase=phase,
                method=method,
                completed_updates=updates,
                elapsed_seconds=elapsed,
            ),
        )

    return record


def safe_result(result: dict) -> dict:
    safe = dict(
        status=result["status"],
        criterion=result["criterion"],
        cells=len(result["cells"]),
        contract_sha256=result["contract_sha256"],
        result_sha256=digest(encode(result)),
    )
    if result["status"] == "failed":
        safe.update(phase=result["phase"], invariant_code=result["invariant_code"])
    return safe


def failure(contract, pin, reason, *, phase=None, invariant_code=None):
    require(reason in prior.base.FAILURES, "failure_category")
    require(phase is None or phase in PHASES, "failure_phase")
    require(invariant_code is None or invariant_code in INVARIANTS, "failure_invariant")
    return dict(
        header(contract, pin),
        status="failed",
        criterion="not_evaluable",
        reason=reason,
        phase=phase,
        invariant_code=invariant_code,
        coverage=[],
        matching=None,
        cells=[],
        year_deletions=[],
        model_sha256=None,
        resources=None,
    )


def validate_result(result, contract, pin):
    expected = header(contract, pin)
    if result.get("status") == "failed":
        require(
            result
            == failure(
                contract,
                pin,
                result.get("reason"),
                phase=result.get("phase"),
                invariant_code=result.get("invariant_code"),
            ),
            "failure_shape",
        )
        return
    require(
        set(result)
        == set(expected)
        | {
            "status",
            "criterion",
            "coverage",
            "matching",
            "cells",
            "year_deletions",
            "model_sha256",
            "resources",
        }
        and {k: result[k] for k in expected} == expected,
        "result_binding",
    )
    require(len(result["coverage"]) == 3, "coverage_count")
    for facts, spec in zip(result["coverage"], contract["plan"]["periods"], strict=True):
        require(
            set(facts)
            == {
                "period",
                "sessions",
                "quarters",
                "missing_marks",
                "invalid_marks",
                "missing_inputs",
                "inputs",
            },
            "coverage_fields",
        )
        require(
            all(
                type(facts[k]) is int and facts[k] >= 0
                for k in facts
                if k not in {"period", "inputs"}
            ),
            "coverage_counts",
        )
        require(
            facts["period"] == spec["period"]
            and facts["sessions"] == spec["bounds"][1] - spec["bounds"][0]
            and facts["quarters"] == len(spec["quarters"])
            and [i["session_date"] for i in facts["inputs"]]
            == [i["session_date"] for i in spec["decisions"]],
            "coverage_binding",
        )
        require(
            facts["missing_inputs"] == sum(i["status"] != "ready" for i in facts["inputs"]),
            "input_counts",
        )
        for item in facts["inputs"]:
            require(
                (set(item) == {"session_date", "status"} and item["status"] == "ready")
                or (
                    set(item) == {"session_date", "status", "reason_code"}
                    and item["status"] == "input_unavailable"
                    and item["reason_code"]
                    in {
                        "source_vintage_mismatch",
                        "required_session_duplicate",
                        "required_session_missing",
                        "required_session_alignment_or_order",
                        "required_bar_identity",
                        "required_bar_incomplete",
                        "required_bar_values_invalid",
                        "features_not_representable",
                    }
                ),
                "input_facts",
            )
    match = restore_match(result["matching"])
    require(match.iterations in {0, 64}, "matching_iterations")
    require(
        (
            match.status == "matched"
            and match.reason is None
            and match.fraction is not None
            and match.fraction.is_finite()
            and 0 <= match.fraction <= 1
        )
        or (
            match.status == "comparison_unresolved"
            and match.fraction is None
            and match.reason
            in {
                "train_input_unavailable",
                "beta_reference_zero_variance",
                "beta_not_bracketed",
                "beta_residual_exceeded",
            }
        ),
        "matching_status",
    )
    cells, hashes = result["cells"], {}
    require(
        [(c["period"], c["cost_per_side_bps"], c["policy"]) for c in cells]
        == [(p, c, m) for p, _, _ in PERIODS for c in COSTS for m in POLICIES],
        "cell_matrix",
    )
    for cell in cells:
        require(
            set(cell)
            == {"period", "policy", "cost_per_side_bps", "status", "action_sha256", "trades"}
            | set(prior.METRICS),
            "cell_fields",
        )
        require(cell["status"] in {"evaluated", "input_unavailable"}, "cell_status")
        facts = next(f for f in result["coverage"] if f["period"] == cell["period"])
        available = not (facts["missing_marks"] or facts["invalid_marks"])
        if cell["policy"] in METHODS:
            available &= not facts["missing_inputs"] and result["model_sha256"] is not None
        if cell["policy"] == "tcn_beta_matched_quarter_ew_cash":
            available &= match.status == "matched"
        require(
            cell["status"] == ("evaluated" if available else "input_unavailable"),
            "availability_binding",
        )
        key = cell["period"], cell["policy"]
        require(
            hashes.setdefault(key, cell["action_sha256"]) == cell["action_sha256"],
            "cost_changed_actions",
        )
        if not available:
            require(
                cell["action_sha256"] is None
                and cell["trades"] is None
                and all(cell[k] is None for k in prior.METRICS),
                "unavailable_metrics",
            )
            continue
        require(
            type(cell["action_sha256"]) is str and re.fullmatch(prior.HASH, cell["action_sha256"]),
            "action_hash",
        )
        require(
            all(
                type(cell[k]) is str and len(cell[k]) <= 180 and Decimal(cell[k]).is_finite()
                for k in prior.METRICS
            ),
            "metric_fields",
        )
        nav, _, fees, turnover = (Decimal(cell[k]) for k in prior.METRICS)
        require(
            nav > 0
            and fees >= 0
            and turnover >= 0
            and type(cell["trades"]) is int
            and cell["trades"] >= 0,
            "metric_domain",
        )
        with localcontext() as ctx:
            ctx.prec = 50
            require(
                abs(fees - Decimal(cell["cost_per_side_bps"]) * turnover / 10000)
                <= prior.EPS * (1 + fees),
                "fee_identity",
            )
    expected_stress = [
        (p["period"], y, policy)
        for p in contract["plan"]["periods"][1:]
        for y in sorted(
            {date.fromisoformat(d).year for d in contract["plan"]["days"][slice(*p["bounds"])]}
        )
        for policy in POLICIES
    ]
    require(
        [(a["period"], a["deleted_year"], a["policy"]) for a in result["year_deletions"]]
        == expected_stress,
        "year_deletion_keys",
    )
    for item in result["year_deletions"]:
        require(
            set(item)
            == {
                "period",
                "deleted_year",
                "policy",
                "remaining_sessions",
                "status",
                "final_growth",
                "utility",
            },
            "year_deletion_fields",
        )
        p = next(p for p in contract["plan"]["periods"] if p["period"] == item["period"])
        kept = sum(
            date.fromisoformat(d).year != item["deleted_year"]
            for d in contract["plan"]["days"][slice(*p["bounds"])]
        )
        evaluated = (
            next(
                c
                for c in cells
                if c["period"] == item["period"]
                and c["policy"] == item["policy"]
                and c["cost_per_side_bps"] == "10"
            )["status"]
            == "evaluated"
        )
        require(
            item["remaining_sessions"] == kept
            and item["status"]
            == ("descriptive_only" if evaluated and kept else "input_unavailable"),
            "year_deletion_binding",
        )
        if item["status"] == "descriptive_only":
            require(
                all(
                    type(item[k]) is str and len(item[k]) <= 180 and Decimal(item[k]).is_finite()
                    for k in ("final_growth", "utility")
                )
                and Decimal(item["final_growth"]) > 0,
                "year_deletion_domain",
            )
        else:
            require(
                item["final_growth"] is None and item["utility"] is None,
                "year_deletion_unavailable",
            )
    require(
        result["criterion"] == primary_verdict(cells)
        and result["status"]
        == ("complete" if all(c["status"] == "evaluated" for c in cells) else "input_unavailable"),
        "result_status",
    )
    resources = result["resources"]
    if result["model_sha256"] is None:
        require(
            resources
            == dict(
                device="cpu",
                fits=0,
                peak_allocated_bytes=0,
                allocator_cap_bytes=0,
                fit_durations=[],
            ),
            "no_fit_resources",
        )
    else:
        require(
            type(result["model_sha256"]) is str
            and re.fullmatch(prior.HASH, result["model_sha256"]),
            "model_hash",
        )
        require(
            set(resources)
            == {"device", "fits", "peak_allocated_bytes", "allocator_cap_bytes", "fit_durations"}
            and resources["device"] == "cpu"
            and resources["fits"] == 3,
            "resource_fields",
        )
        require(
            type(resources["peak_allocated_bytes"]) is int
            and type(resources["allocator_cap_bytes"]) is int
            and resources["peak_allocated_bytes"] == resources["allocator_cap_bytes"] == 0,
            "resource_memory",
        )
        require([r["method"] for r in resources["fit_durations"]] == list(METHODS), "fit_order")
        for item in resources["fit_durations"]:
            require(
                set(item) == {"method", "updates", "elapsed_seconds"}
                and item["updates"] == UPDATES[item["method"]]
                and type(item["elapsed_seconds"]) in {float, int}
                and 0 <= item["elapsed_seconds"] <= SECONDS,
                "fit_facts",
            )
        require(
            sum(r["elapsed_seconds"] for r in resources["fit_durations"]) <= SECONDS, "fit_budget"
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
        json.loads(prior._read(output / "started.json")) == {"contract_sha256": pin},
        "attempt_binding",
    )
    phase = "synthetic_smoke"
    progress = progress_recorder(output, pin, deadline)
    try:
        progress(phase)
        smoke(contract=contract, pin=pin)
        phase = "source_input"
        progress(phase)
        prepared = prepare_inputs(
            prior.load_adjusted(market_data_root), contract["plan"], deadline=deadline
        )
        bundle, resources = (
            None,
            dict(
                device="cpu",
                fits=0,
                peak_allocated_bytes=0,
                allocator_cap_bytes=0,
                fit_durations=[],
            ),
        )
        if prepared[0].x is not None and prepared[0].marks is not None:
            phase = "fit"
            bundle, resources = fit_bundle(prepared[0], pin, deadline=deadline, progress=progress)
            atomic_new(output / "numeric-models.json", bundle)
        phase = "evaluate"
        progress(phase)
        result = evaluate(prepared, bundle, contract, pin, deadline=deadline)
        result["resources"] = resources
        phase = "validate"
        progress(phase)
        validate_result(result, contract, pin)
        verify(artifact_root, market_data_root, pin)
    except Exception as exc:
        code = exc.args[0] if len(exc.args) == 1 and type(exc.args[0]) is str else None
        code = code if code in INVARIANTS else None
        result = failure(
            contract, pin, "runtime_or_invariant_failure", phase=phase, invariant_code=code
        )
    atomic_new(path, result)


def worker_entry(*args):
    try:
        run_worker(*args)
    except BaseException:
        raise SystemExit(1) from None


def _replay_result(artifact_root, market_data_root, pin, *, result_sha256, deadline, result_name):
    """CPU restoration/replay only; no optimizer, beta search, GPU or writes."""
    require(result_name in {"summary.json", "worker-result.json"}, "result_name")
    output, contract = verify(artifact_root, market_data_root, pin)
    require(
        json.loads(prior._read(output / "started.json")) == {"contract_sha256": pin},
        "attempt_binding",
    )
    raw = prior._read(output / result_name)
    require(digest(raw) == result_sha256, "result_hash")
    retained = json.loads(raw)
    require(encode(retained) == raw, "result_encoding")
    validate_result(retained, contract, pin)
    if retained["status"] == "failed":
        return dict(
            safe_result(retained), replay="immutable_failure", refits=0, beta_searches=0, writes=0
        )
    require(prior._read(output / "worker-result.json") == raw, "worker_summary_binding")
    analytical_parity()
    prepared = prepare_inputs(
        prior.load_adjusted(market_data_root), contract["plan"], deadline=deadline
    )
    bundle = None
    if retained["model_sha256"] is not None:
        model_bytes = prior._read(output / "numeric-models.json")
        require(digest(model_bytes) == retained["model_sha256"], "model_hash")
        bundle = json.loads(model_bytes)
        require(encode(bundle) == model_bytes, "model_encoding")
        bundle_identity(bundle, pin)
        require(
            prepared[0].x is not None and bundle["scaler"] == train_scaler(prepared[0].x).payload(),
            "TRAIN_scaler_replay",
        )
    rebuilt = evaluate(
        prepared,
        bundle,
        contract,
        pin,
        deadline=deadline,
        restored_match=restore_match(retained["matching"]),
    )
    rebuilt["resources"] = retained["resources"]
    validate_result(rebuilt, contract, pin)
    verify(artifact_root, market_data_root, pin)
    require(encode(rebuilt) == raw, "zero_refit_replay_mismatch")
    return dict(safe_result(retained), replay="exact", refits=0, beta_searches=0, writes=0)


def readback(artifact_root, market_data_root, pin, *, result_sha256, deadline):
    return _replay_result(
        artifact_root,
        market_data_root,
        pin,
        result_sha256=result_sha256,
        deadline=deadline,
        result_name="summary.json",
    )


def recover_terminal(artifact_root, market_data_root, pin, *, result_sha256, deadline):
    """Finalize an exact retained worker result; never redispatch a fit."""
    lock = Path(artifact_root) / configuration()["budget"]["worker_lock"]
    require(not lock.exists(), "cpu_owner_active")
    replayed = _replay_result(
        artifact_root,
        market_data_root,
        pin,
        result_sha256=result_sha256,
        deadline=deadline,
        result_name="worker-result.json",
    )
    output, contract = verify(artifact_root, market_data_root, pin)
    raw = prior._read(output / "worker-result.json")
    require(digest(raw) == result_sha256, "recovery_result_changed")
    validate_result(json.loads(raw), contract, pin)
    require(not lock.exists() and time.monotonic() < deadline, "terminal_owner_or_timeout")
    terminal = output / "summary.json"
    created = 0
    if terminal.exists():
        require(prior._read(terminal) == raw, "terminal_conflict")
    else:
        atomic_new(terminal, json.loads(raw))
        created = 1
    entry = register_campaign_outcome(
        contract_hash=pin,
        outcome_class="non_promoting_failed"
        if replayed["status"] == "failed"
        else "non_promoting_completed",
        outcome_reference_sha256=result_sha256,
        artifact_root=artifact_root,
        repo_root=REPO,
    )
    return dict(
        replayed,
        recovery="terminal_finalization",
        summary_artifact_writes=created,
        model_writes=0,
        outcome_record_sha256=entry.record_sha256,
    )


def recover_registry(artifact_root, market_data_root, pin, *, result_sha256, deadline):
    replayed = readback(
        artifact_root, market_data_root, pin, result_sha256=result_sha256, deadline=deadline
    )
    output, contract = verify(artifact_root, market_data_root, pin)
    raw = prior._read(output / "summary.json")
    require(digest(raw) == result_sha256, "recovery_result_changed")
    validate_result(json.loads(raw), contract, pin)
    require(time.monotonic() < deadline, "hard_timeout")
    entry = register_campaign_outcome(
        contract_hash=pin,
        outcome_class="non_promoting_failed"
        if replayed["status"] == "failed"
        else "non_promoting_completed",
        outcome_reference_sha256=result_sha256,
        artifact_root=artifact_root,
        repo_root=REPO,
    )
    return dict(
        replayed,
        recovery="registry_only",
        attempt_artifact_writes=0,
        outcome_record_sha256=entry.record_sha256,
    )
