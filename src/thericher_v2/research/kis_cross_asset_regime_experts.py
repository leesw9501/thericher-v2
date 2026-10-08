"""Pure fixed-expert composition; no IO, fitting, dispatch or promotion.

Fixed experts need no learned-expert OOF predictions. The gate's expanding
OOF is diagnostic only. Caller binds raw cohort/calendar, seals decisions and
separately supplies TRAIN payoffs. No prior campaign numeric artifacts enter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal, localcontext

import numpy as np

from thericher_v2.research import kis_cross_asset_direct_utility as kernel

NAME = "kis-cross-asset-regime-expert-composition-development-v1"
EXPERTS = ("momentum63", "minvar63", "cash")
CANDIDATES = ("tree", "mlp")
POLICIES = CANDIDATES + EXPERTS + ("uniform_blend",)
STATE_NAMES = (
    "SPY_momentum63",
    "TLT_momentum63",
    "GLD_momentum63",
    "SPY_volatility63",
    "SPY_TLT_correlation63",
    "SPY_GLD_correlation63",
)
COSTS = kernel.allocation.COSTS
CONTEXT, nav, require = kernel.CONTEXT, kernel.nav, kernel.require
SEED, UPDATES, SECONDS = 101, 512, 300


def configuration():
    return dict(
        name=NAME,
        symbols=list(kernel.SYMBOLS),
        experts=list(EXPERTS),
        policies=list(POLICIES),
        cells=36,
        state_features=list(STATE_NAMES),
        context_closes=64,
        returns=63,
        state="three sums63 CLOSE log changes; sqrt(252*C00); raw-C correlations C01/C02",
        covariance="population63 simple returns; .75*C+.25*diag(C) ONCE for cap/solver",
        minvar="existing10%-shrink solver receives(5/6)*C+(1/6)*diag(C)",
        momentum="top strictly positive sum63 log returns; ties SPY/TLT/GLD; else cash",
        risk="each risky expert min(1,.10/sqrt(252*w'C_shrunk*w)); no leverage",
        blend="uniform three experts; convex mixture, no second shrink or cap",
        tree=dict(
            depth=2,
            min_leaf=5,
            seed=SEED,
            input_dtype="float32",
            serialization="safe JSON",
            target="local21-day 10bps/side normalized episode net utility winner",
            ties="cash>minvar63>momentum63; local classifier proxy NOT global utility loss",
        ),
        mlp=dict(
            widths=[6, 8, 3],
            activation="tanh",
            output="softmax expert mixture",
            dtype="float32",
            updates=UPDATES,
            seed=SEED,
            optimizer="AdamW",
            lr=0.001,
            weight_decay=0.01,
            loss="negative full continuous TRAIN net utility",
        ),
        scaler="qualified prefix only; population state mean/std; zero std divisor1; both gates",
        oof=dict(
            warmup=15,
            validation_groups=[13, 13, 14],
            folds=3,
            train="all prefix groups with exit<=decision's previous scheduled CLOSE",
            scaler="only those qualified groups; no label/state from OOF/future",
            purpose="diagnostic only, no tuning/selection",
            fits=6,
        ),
        final="one fit/gate on all 55 qualified TRAIN groups; no DEV-dependent eligibility",
        final_fits=2,
        fits=8,
        family_seconds=SECONDS,
        horizon=21,
        costs_bps_side=[str(c) for c in COSTS],
        train_cost_bps_side="10",
        accounting="continuous NAV1, group first OPEN/21st CLOSE exit, actual-notional fees; "
        "all daily marks/cross-view capital, cash tails; no per-group reset",
        objective="252*(mean daily log-5*population variance)",
        kill="10bps BOTH views growth>0; tree utility>all four fixed controls by>1e-10; "
        "MLP utility>those controls AND tree by>1e-10; no wealth dominance",
        input_sha256=kernel.controls.INPUT_PIN,
        lineage=[
            kernel.NAME,
            kernel.allocation.NAME,
            "kis-cross-asset-conditional-hedge-utility-development-v1",
        ],
        grade="RELATED_OUTCOME_INFORMED_SEEN_RAW_PRICE_ONLY_DEVELOPMENT",
        limitations=[
            "non-PIT/raw CA-dividend omissions",
            "availability/finality not observed",
            "55 groups not independent samples",
            "OOF gate proxy/global loss differ",
        ],
        source_io=False,
        actual_fits=0,
        paper_input=False,
        holdout="none",
    )


def _target(risky):
    with localcontext(CONTEXT) as context:
        context.prec = max(100, max(-v.as_tuple().exponent for v in risky) + 3)
        cash = 1 - sum(risky, Decimal(0))
    return nav.ThreeAssetTarget(tuple(risky), cash)


def _cap(simplex, covariance):
    values = np.asarray(simplex, dtype=np.float64)
    variance = float(values @ covariance @ values)
    require(math.isfinite(variance) and variance > 0, "risk_numeric")
    vol = math.sqrt(252 * variance)
    require(math.isfinite(vol) and vol > 0, "risk_numeric")
    exposure = Decimal.from_float(min(1.0, 0.10 / vol))
    return kernel.controls.prior.scaled_target(simplex, exposure)


@dataclass(frozen=True, slots=True)
class ExpertContext:
    state: tuple[float, ...] = field(repr=False)
    targets: tuple[nav.ThreeAssetTarget, ...] = field(repr=False)
    covariance: tuple[tuple[float, ...], ...] = field(repr=False)

    def __post_init__(self):
        require(
            type(self.state) is tuple
            and len(self.state) == 6
            and all(type(v) is float and math.isfinite(v) for v in self.state),
            "state_values",
        )
        require(type(self.targets) is tuple and len(self.targets) == 3, "expert_geometry")
        for target in self.targets:
            require(type(target) is nav.ThreeAssetTarget, "expert_type")
            target.__post_init__()
        require(
            self.targets[2] == nav.ThreeAssetTarget((Decimal(0),) * 3, Decimal(1)), "cash_expert"
        )
        kernel._covariance(self.covariance)


def experts_from_context(context):
    require(type(context) is kernel.CausalRiskContext, "context_type")
    context.__post_init__()
    c = kernel._covariance(context.covariance)
    diagonal = np.diag(np.diag(c))
    shrunk = 0.75 * c + 0.25 * diagonal
    with localcontext(CONTEXT):
        momentum = tuple(sum(context.features.features[2 * k], Decimal(0)) for k in range(3))
    state = (
        tuple(float(v) for v in momentum)
        + (math.sqrt(252 * c[0, 0]),)
        + tuple(float(c[0, j] / math.sqrt(c[0, 0] * c[j, j])) for j in (1, 2))
    )
    cash = nav.ThreeAssetTarget((Decimal(0),) * 3, Decimal(1))
    selected = max(range(3), key=lambda k: momentum[k])
    mom = (
        cash
        if momentum[selected] <= 0
        else _cap(tuple(Decimal(int(k == selected)) for k in range(3)), shrunk)
    )
    minimum = kernel.controls.solver.minimum_variance_weights((5 / 6) * c + (1 / 6) * diagonal)
    return ExpertContext(state, (mom, _cap(minimum, shrunk), cash), context.covariance)


def prepare_context(rows_by_symbol, **kwargs):
    return experts_from_context(kernel.prepare_context(rows_by_symbol, **kwargs))


def uniform_blend(context):
    require(type(context) is ExpertContext, "context_type")
    context.__post_init__()
    with localcontext(CONTEXT):
        risky = tuple(
            sum((t.weights3[k] for t in context.targets), Decimal(0)) / 3 for k in range(3)
        )
    return _target(risky)


def local_utility_labels(group, targets):
    """Separate TRAIN-only payoff API; normalized episodes do NOT reset policy NAV."""
    require(type(targets) is tuple and len(targets) == 3, "expert_geometry")
    require(targets[2] == nav.ThreeAssetTarget((Decimal(0),) * 3, Decimal(1)), "cash_expert")
    with localcontext(CONTEXT):
        scores = []
        for target in targets:
            trace = kernel.decimal_reference((group,), (target,), cost_bps=Decimal(10))
            logs = tuple(d.log_return for d in trace.daily)
            mean = sum(logs, Decimal(0)) / 21
            scores.append(252 * (mean - 5 * sum(((v - mean) ** 2 for v in logs), Decimal(0)) / 21))
    require(scores[2] == 0, "cash_target")
    winner = max((2, 1, 0), key=lambda k: scores[k])
    return tuple(scores), winner


@dataclass(frozen=True, slots=True)
class OOFSplit:
    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]

    def __post_init__(self):
        for indices in (self.train_indices, self.test_indices):
            require(
                type(indices) is tuple
                and bool(indices)
                and all(type(i) is int and 0 <= i < 55 for i in indices)
                and all(a < b for a, b in zip(indices, indices[1:], strict=False)),
                "oof_indices",
            )
        require(self.train_indices[-1] < self.test_indices[0], "oof_order")


def qualified_prefix(groups, sessions, decision_at, prefix_end):
    """A full scheduled session between exit and decision CLOSE, not a date guess."""
    require(type(groups) is tuple and len(groups) == 55, "train_groups")
    kernel.allocation._calendar(sessions)
    positions = {s.close_at: i for i, s in enumerate(sessions)}
    openings = {s.open_at: i for i, s in enumerate(sessions)}
    require(decision_at in positions and positions[decision_at] > 0, "decision_clock")
    require(type(prefix_end) is int and 0 < prefix_end <= 55, "prefix_end")
    for entry, exit_at in groups:
        require(
            entry in openings
            and exit_at in positions
            and positions[exit_at] == openings[entry] + 20,
            "group_clock",
        )
    require(all(a[1] < b[0] for a, b in zip(groups, groups[1:], strict=False)), "group_order")
    cutoff = sessions[positions[decision_at] - 1].close_at
    return tuple(i for i in range(prefix_end) if groups[i][1] <= cutoff)


def build_oof(groups, sessions):
    require(type(groups) is tuple and len(groups) == 55, "train_groups")
    openings = {s.open_at: i for i, s in enumerate(sessions)}
    splits = []
    for start, end in ((15, 28), (28, 41), (41, 55)):
        require(groups[start][0] in openings and openings[groups[start][0]] > 0, "group_clock")
        decision = sessions[openings[groups[start][0]] - 1].close_at
        splits.append(
            OOFSplit(qualified_prefix(groups, sessions, decision, start), tuple(range(start, end)))
        )
    return tuple(splits)


@dataclass(frozen=True, slots=True)
class PrefixScaler:
    mean: tuple[float, ...] = field(repr=False)
    scale: tuple[float, ...] = field(repr=False)
    train_indices: tuple[int, ...]

    def __post_init__(self):
        require(
            type(self.mean) is type(self.scale) is tuple
            and len(self.mean) == len(self.scale) == 6
            and all(type(v) is float and math.isfinite(v) for v in self.mean + self.scale)
            and all(v > 0 for v in self.scale),
            "scaler_values",
        )


def prefix_scaler(contexts, split):
    require(type(split) is OOFSplit, "oof_type")
    split.__post_init__()
    selected = tuple(contexts[i] for i in split.train_indices)
    for context in selected:
        require(type(context) is ExpertContext, "context_type")
        context.__post_init__()
    values = np.asarray([c.state for c in selected], dtype=np.float64)
    with np.errstate(over="raise", invalid="raise"):
        relative = values - values[0]
        mean, scale = values[0] + relative.mean(0), relative.std(0)
    scale = np.where(scale == 0, 1.0, scale)
    return PrefixScaler(tuple(map(float, mean)), tuple(map(float, scale)), split.train_indices)


def scale_states(contexts, scaler, indices):
    require(type(scaler) is PrefixScaler, "scaler_type")
    scaler.__post_init__()
    values = np.asarray([contexts[i].state for i in indices], dtype=np.float64)
    require(values.ndim == 2 and values.shape[1] == 6 and np.isfinite(values).all(), "state_values")
    result = (values - scaler.mean) / scaler.scale
    require(np.isfinite(result).all(), "scaled_values")
    return result


def make_gate():
    """Construct CPU parameters only; never fits, reserves or probes a GPU."""
    import torch

    with torch.random.fork_rng(devices=[]):
        torch.random.default_generator.manual_seed(SEED)
        return torch.nn.Sequential(
            torch.nn.Linear(6, 8, dtype=torch.float32, device="cpu"),
            torch.nn.Tanh(),
            torch.nn.Linear(8, 3, dtype=torch.float32, device="cpu"),
        )


def mix_experts(logits, expert_weights):
    import torch

    require(
        isinstance(logits, torch.Tensor) and logits.ndim == 2 and logits.shape[1] == 3,
        "gate_geometry",
    )
    count = logits.shape[0]
    kernel._tensor(torch, logits, (count, 3), "gate_values")
    kernel._tensor(torch, expert_weights, (count, 3, 4), "expert_values")
    require(
        count > 0
        and logits.device == expert_weights.device
        and bool(((expert_weights >= 0) & (expert_weights <= 1)).all())
        and bool((abs(expert_weights.sum(-1) - 1) <= 64 * torch.finfo(torch.float64).eps).all()),
        "expert_domain",
    )
    return torch.einsum("ge,gea->ga", logits.softmax(-1), expert_weights)


def tree_to_record(model):
    """Extract only bounded numeric decision nodes, never pickle/public model code."""
    tree, classes = model.tree_, tuple(int(v) for v in model.classes_)
    require(
        0 < tree.node_count <= 7
        and tree.max_depth <= 2
        and classes == tuple(sorted(set(classes)))
        and set(classes) <= {0, 1, 2},
        "tree_shape",
    )
    nodes = []
    for i in range(tree.node_count):
        if tree.children_left[i] == -1:
            scores = [0.0, 0.0, 0.0]
            for k, v in zip(classes, tree.value[i, 0], strict=True):
                require(math.isfinite(float(v)) and v >= 0, "tree_values")
                scores[k] = float(v)
            require(sum(scores) > 0, "tree_values")
            nodes.append(dict(action=max((2, 1, 0), key=lambda k: scores[k])))
        else:
            nodes.append(
                dict(
                    feature=int(tree.feature[i]),
                    threshold=float(tree.threshold[i]),
                    left=int(tree.children_left[i]),
                    right=int(tree.children_right[i]),
                )
            )
    record = dict(kind="fixed_depth2_numeric_gate_v1", nodes=nodes)
    tree_decisions(np.zeros((1, 6)), record)
    return record


def tree_decisions(states, record):
    require(
        type(record) is dict
        and set(record) == {"kind", "nodes"}
        and record["kind"] == "fixed_depth2_numeric_gate_v1",
        "tree_record",
    )
    nodes = record["nodes"]
    require(type(nodes) is list and 0 < len(nodes) <= 7, "tree_shape")
    pending, visited = [(0, 0)], set()
    while pending:
        index, depth = pending.pop()
        require(index not in visited and depth <= 2, "tree_shape")
        visited.add(index)
        node = nodes[index]
        require(type(node) is dict, "tree_record")
        if set(node) == {"action"}:
            require(type(node["action"]) is int and node["action"] in (0, 1, 2), "tree_record")
        else:
            require(
                set(node) == {"feature", "threshold", "left", "right"}
                and type(node["feature"]) is int
                and 0 <= node["feature"] < 6
                and type(node["threshold"]) is float
                and math.isfinite(node["threshold"]),
                "tree_record",
            )
            for child in (node["left"], node["right"]):
                require(type(child) is int and index < child < len(nodes), "tree_shape")
                pending.append((child, depth + 1))
    require(len(visited) == len(nodes), "tree_shape")
    values = np.asarray(states, dtype=np.float32)
    require(values.ndim == 2 and values.shape[1] == 6 and np.isfinite(values).all(), "state_values")
    actions = []
    for row in values:
        i = 0
        while "action" not in nodes[i]:
            n = nodes[i]
            i = n["left"] if row[n["feature"]] <= n["threshold"] else n["right"]
        actions.append(nodes[i]["action"])
    return tuple(actions)


def criterion(cells):
    expected = {(b, p, str(c)) for b in (0, 1) for p in POLICIES for c in COSTS}
    require(
        len(cells) == 36 and {(v["block"], v["policy"], v["cost_bps"]) for v in cells} == expected,
        "cell_geometry",
    )
    table = {(v["block"], v["policy"], v["cost_bps"]): v["metrics"] for v in cells}
    require(
        all(
            type(m[k]) is str and Decimal(m[k]).is_finite()
            for m in table.values()
            for k in ("growth", "utility")
        ),
        "metric_values",
    )
    with localcontext(CONTEXT):
        return {
            candidate: "development_survivor"
            if all(
                Decimal(table[b, candidate, "10"]["growth"]) > 0
                and all(
                    Decimal(table[b, candidate, "10"]["utility"])
                    - Decimal(table[b, p, "10"]["utility"])
                    > Decimal("1e-10")
                    for p in EXPERTS
                    + ("uniform_blend",)
                    + (("tree",) if candidate == "mlp" else ())
                )
                for b in (0, 1)
            )
            else "rejected"
            for candidate in CANDIDATES
        }
