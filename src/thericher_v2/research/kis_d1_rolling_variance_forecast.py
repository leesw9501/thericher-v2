"""Causal monthly refits of the closed variance recipe; parent owns dispatch.

Related outcome-informed development, not replication or a Paper input.
Readback validates cached original predictions, not saved-model reinference.
Source bytes may contain future rows; only explicit scheduled subsets are used.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np

from thericher_v2.research import kis_d1_variance_forecast as fixed

base, lifecycle = fixed.base, fixed.lifecycle
require, encode, digest = fixed.require, fixed.encode, fixed.digest
NAME = "kis-d1-rolling-variance-forecast-development-v1"
REPO = Path(__file__).resolve().parents[3]
SECONDS, VERIFY_SECONDS, WINDOW, MONTHS, FITS = 300, 120, 504, 33, 66
UPDATES, SEED = fixed.UPDATES, fixed.SEED
CANDIDATES, METHODS, METRICS, RUNTIME = (
    fixed.CANDIDATES,
    fixed.METHODS,
    fixed.METRICS,
    fixed.RUNTIME,
)
CODE = fixed.CODE + ("src/thericher_v2/research/kis_d1_rolling_variance_forecast.py",)
GEOMETRY_RELATIVE = "data/" + NAME + "/geometry-20261008-v1.json"
GEOMETRY_PIN = "sha256:24a82d3d18f891a67e6e22e89e0db95d4bc6cd04ee12eb7c3e0cb8857b503247"
PHASES, PROGRESS = fixed.PHASES, fixed.PROGRESS
MONTH_FILES = ("scaler.json", "ols.npz", "gru.safetensors", "predictions.json") + PROGRESS
ARTIFACTS = ("started.json", "predictions.json") + tuple(
    f"months/{month:02d}/{name}" for month in range(MONTHS) for name in MONTH_FILES
)


def configuration():
    config = fixed.configuration()
    for key in ("train_entries", "embargo_entries", "source_receipt_sha256"):
        config.pop(key)
    config.update(
        name=NAME,
        geometry_receipt=dict(artifact_relative_path=GEOMETRY_RELATIVE, sha256=GEOMETRY_PIN),
        geometry=dict(
            train_entries_per_month=WINDOW,
            dev_entries=MONTHS,
            view_entries=[12, 21],
            required_dates=1278,
            distinct_train_entries=1172,
            train_entry_occurrences=16632,
            monthly_disjoint_21_return_label_windows=24,
            unique_disjoint_label_windows=56,
            dev_adjacent_label_overlaps=12,
            effective_sample_size="unknown",
            independent_sample_count="not_claimed",
        ),
        training="latest504 scheduled entries at each monthly decision; j+20<=d-2; "
        "label exit strictly before previous-session decision CLOSE; no row substitution",
        refit="33 fresh OLS and33 fresh seed101 GRU;512 final updates each; no warm starts",
        cache="invocation-local immutable-source features and mature labels; no retained cache",
        prediction_seal="each month before scoring; all33 sealed before comparative evaluation",
        fits=FITS,
        seconds=SECONDS,
        verify_seconds=VERIFY_SECONDS,
        fit_accounting="month-local start/completion/update receipts, aggregate0..66; "
        "completion before validation/inference/save/deadline",
        sources=[
            "https://escholarship.org/content/qt5jk0j5jh/qt5jk0j5jh.pdf",
            "https://onlinelibrary.wiley.com/doi/10.1111/j.1468-0262.2006.00718.x",
        ],
        source_scope="Engine independently retrieved2026-10-08 04:43UTC;2003 working paper/2006 "
        "publisher record; motivates moving estimation windows, not504/ETF results; "
        "no source code/license adoption",
        related_trial_number=2,
        registry_trial_index="record actual index; not forced to2",
        predecessor=dict(
            study=fixed.NAME,
            contract_sha256="sha256:b198df9d26bc1e588ab29303c41cf0367b23ce0b5c0467334746cd1c1489ec4e",
            result_sha256="sha256:b400bd371bb9eb4475cf992bd6abe173a8342655bbd28db2d3698ac601936fbc",
        ),
        lineage="closed static variance family; related outcome-informed DEV trial2; "
        "original verdict unchanged; NOT independent replication",
    )
    config["limitations"] = config["limitations"] + [
        "one scheduled-session training label lag is not provider availability proof",
        "earlier DEV labels enter later training only after strict maturity",
        "incomplete66 fits never yields partial-month scores or adaptive budget extension",
    ]
    return config


@dataclass(frozen=True, slots=True)
class StudyPlan:
    sessions: tuple = field(repr=False)
    train_windows: tuple[tuple[int, ...], ...] = field(repr=False)
    dev_indices: tuple[int, ...]
    block_cut: int = 12

    def month(self, month):
        require(type(month) is int and 0 <= month < MONTHS, "month_scope")
        return fixed.StudyPlan(
            self.sessions, self.train_windows[month], (self.dev_indices[month],), 1
        )

    def window_record(self, month):
        plan = self.month(month)
        first, last = plan.train_indices[0], plan.train_indices[-1]
        entry = plan.dev_indices[0]
        return dict(
            month=month,
            entry=self.sessions[entry].session_date.isoformat(),
            decision_at=self.sessions[entry - 1].close_at.isoformat(),
            train_count=WINDOW,
            train_first=self.sessions[first].session_date.isoformat(),
            train_last=self.sessions[last].session_date.isoformat(),
            latest_label_exit=self.sessions[last + 20].close_at.isoformat(),
            first_required_close=self.sessions[first - 64].session_date.isoformat(),
            train_membership_sha256=digest(
                encode([self.sessions[i].session_date.isoformat() for i in plan.train_indices])
            ),
        )

    def record(self):
        return dict(
            dev_entries=[self.sessions[i].session_date.isoformat() for i in self.dev_indices],
            decisions=[self.sessions[i - 1].close_at.isoformat() for i in self.dev_indices],
            label_exits=[self.sessions[i + 20].close_at.isoformat() for i in self.dev_indices],
            block_cut=self.block_cut,
            monthly_windows=[self.window_record(m) for m in range(MONTHS)],
        )


def build_plan(sessions=None):
    sessions = base.calendar_sessions() if sessions is None else sessions
    require(type(sessions) is tuple and bool(sessions), "calendar_scope")
    for session in sessions:
        require(type(session) is base.CrossAssetSession, "calendar_type")
        session.__post_init__()
    require(
        all(
            a.session_date < b.session_date and a.close_at < b.open_at
            for a, b in zip(sessions, sessions[1:], strict=False)
        ),
        "calendar_order",
    )
    dev = tuple(
        i
        for i, s in enumerate(sessions)
        if date(2024, 1, 2) <= s.session_date <= date(2026, 9, 30)
        and i > 0
        and (s.session_date.year, s.session_date.month)
        != (sessions[i - 1].session_date.year, sessions[i - 1].session_date.month)
    )
    require(
        len(dev) == MONTHS
        and sum(sessions[i].session_date.year == 2024 for i in dev) == 12
        and sessions[dev[0]].session_date == date(2024, 1, 2)
        and sessions[dev[-1]].session_date == date(2026, 9, 1),
        "dev_calendar",
    )
    windows = tuple(tuple(range(i - 22 - WINDOW + 1, i - 21)) for i in dev)
    require(
        all(
            len(w) == WINDOW
            and w[0] >= 64
            and i + 20 < len(sessions)
            and w[-1] + 20 == i - 2
            and sessions[w[-1] + 20].close_at < sessions[i - 1].close_at
            for i, w in zip(dev, windows, strict=True)
        ),
        "rolling_calendar",
    )
    return StudyPlan(sessions, windows, dev)


def _prepare(rows, plan, month, vintage_ref, features, labels, deadline):
    local = plan.month(month)
    decision = local.dev_indices[0]
    require(local.train_indices == tuple(range(decision - 525, decision - 21)), "train_membership")
    raw, targets = [], []
    for i in local.train_indices + local.dev_indices:
        require(time.monotonic() < deadline, "compute_stop")
        if i not in features:
            features[i] = fixed.past_features(rows, local, i, vintage_ref)
            features[i].flags.writeable = False
        raw.append(features[i])
    for i in local.train_indices:
        require(i + 20 <= decision - 2, "immature_label")
        require(time.monotonic() < deadline, "compute_stop")
        if i not in labels:
            labels[i] = fixed.forward_target(rows, local, i, vintage_ref)
            labels[i].flags.writeable = False
        targets.append(labels[i])
    return fixed.prepare_arrays(raw, targets, local)


def prepare_month(rows, plan, month, *, vintage_ref):
    """Pure preparation with fresh caches; future rows never determine support."""
    require(build_plan(plan.sessions) == plan, "plan_changed")
    return _prepare(rows, plan, month, vintage_ref, {}, {}, float("inf"))


class PreparationCache:
    """Private invocation-local cache bound to one already-attested immutable source."""

    def __init__(self, source, plan):
        require(build_plan(plan.sessions) == plan, "plan_changed")
        self.source, self.plan = source, plan
        self._features, self._labels = {}, {}

    def prepare(self, month, *, deadline):
        local = self.plan.month(month)
        dates = fixed.required_dates(local, local.train_indices + local.dev_indices)
        dates |= fixed.required_dates(local, local.train_indices, forward=True)
        # Validate this month's entire required support even when values are memoized.
        rows = fixed.load_closes(self.source, dates)
        return _prepare(
            rows, self.plan, month, base.INPUT_PIN, self._features, self._labels, deadline
        )


def _root(root, artifact_root):
    root, artifact_root = Path(root).absolute(), Path(artifact_root).absolute()
    require(root == artifact_root / "research" / NAME and root.is_dir(), "study_root")
    base.reject_repo_artifact_path(root, REPO)
    return root


def read_contract(root, artifact_root, pin):
    require(
        type(GEOMETRY_PIN) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", GEOMETRY_PIN),
        "geometry_not_ready",
    )
    root = _root(root, artifact_root)
    contract = base._json(root / "precommit.json", pin)
    require(contract["name"] == NAME and contract["config"] == configuration(), "contract_config")
    require(contract["runtime"] == fixed.runtime_identity() == RUNTIME, "runtime_identity")
    require(Path(contract["source_root"]).absolute() == REPO, "frozen_source_root")
    require(set(contract["code_sha256"]) >= set(CODE), "code_pins")
    for relative, expected in contract["code_sha256"].items():
        require(digest(base._read(base._relative(REPO, relative))) == expected, "code_changed")
    commitment = base._json(base._relative(artifact_root, base.INPUT_RELATIVE), base.INPUT_PIN)
    require(
        contract["input_commitment_sha256"] == base.INPUT_PIN
        and commitment["calendar_sha256"] == base.CALENDAR_PIN
        and commitment["kind"] == "kis-cross-asset-d1-price-only-input-v1"
        and commitment["no_date_fill"] is True,
        "input_identity",
    )
    require(
        all(contract["code_sha256"].get(p) == h for p, h in commitment["source_pins"].items()),
        "producer_code_pins",
    )
    geometry = base._json(base._relative(artifact_root, GEOMETRY_RELATIVE), GEOMETRY_PIN)
    plan = build_plan()
    require(plan.record() == contract["plan"], "plan_changed")
    validate_geometry(geometry, plan)
    return contract, commitment


def validate_geometry(geometry, plan):
    bindings, recipe = geometry["source_bindings"], geometry["contract"]
    require(
        geometry["goal"] == NAME
        and geometry["kind"] == "kis_d1_rolling_variance_geometry_v1"
        and all(
            bindings[key][field] == pin[7:]
            for key, pin in (("input_commitment", base.INPUT_PIN), ("calendar", base.CALENDAR_PIN))
            for field in ("sha256_before", "sha256_after")
        )
        and recipe["canonical_symbols"] == list(base.INSTRUMENT_ORDER)
        and recipe["maturity_predicate"] == "j+20<=d-2"
        and recipe["training_entry_count_per_decision"] == WINDOW
        and recipe["monthly_entry_count"] == MONTHS
        and recipe["view_entry_counts"] == [12, 21]
        and len(geometry["windows"]) == MONTHS,
        "geometry_binding",
    )
    needed = set()
    for m, row in enumerate(geometry["windows"]):
        local, window = plan.month(m), plan.window_record(m)
        require(
            row["entry_date"] == window["entry"]
            and datetime.fromisoformat(row["decision_close_at_utc"])
            == local.sessions[local.dev_indices[0] - 1].close_at
            and row["first_train_entry_date"] == window["train_first"]
            and row["last_train_entry_date"] == window["train_last"]
            and row["train_entry_count"] == WINDOW
            and row["latest_train_target_close_date"]
            == local.sessions[local.train_indices[-1] + 20].session_date.isoformat()
            and row["train_required_close_support"]["first_date"] == window["first_required_close"]
            and all(
                n == 0
                for scope in row["required_missing_date_counts_by_symbol"].values()
                for n in scope.values()
            ),
            "geometry_binding",
        )
        needed.update(fixed.required_dates(local, local.train_indices + local.dev_indices))
        needed.update(
            fixed.required_dates(local, local.train_indices + local.dev_indices, forward=True)
        )
    support = geometry["aggregate"]["all_required_close_support"]
    require(
        support
        == dict(
            first_date=min(needed).isoformat(),
            last_date=max(needed).isoformat(),
            session_count=len(needed),
        ),
        "geometry_binding",
    )


def _artifacts(root):
    return {name: digest(base._read(root / name)) for name in ARTIFACTS if (root / name).exists()}


def _progress_specs(month, pin):
    offset = month * 2
    return {
        f"months/{month:02d}/{name}": dict(
            contract_sha256=pin,
            month=month,
            completed_fits=offset + fits,
            fit_starts=offset + starts,
            updates=updates,
            **({"training_completion": completion} if completion is not None else {}),
        )
        for name, (fits, starts, updates, completion) in fixed._progress_specs().items()
    }


def _verify_progress(root, result, pin):
    previous_complete = 0
    for month in range(MONTHS):
        specs = _progress_specs(month, pin)
        local = f"months/{month:02d}/"
        present = {name for name in specs if name in result["artifact_sha256"]}
        if not present:
            require(result["fit_starts"] <= month * 2, "progress_binding")
            continue
        require(previous_complete == month * 2, "progress_binding")
        for name in present:
            record = specs[name]
            require(
                base._json(root / name, canonical=True) == record
                and result["actual_fits"] >= record["completed_fits"]
                and result["fit_starts"] >= record["fit_starts"],
                "progress_binding",
            )
        for start, complete in (("ols", "ols"), ("gru", "gru")):
            begun, done = (
                local + f"progress-{start}-start.json",
                local + f"progress-{complete}-complete.json",
            )
            if done in present:
                require(begun in present, "progress_binding")
        if local + "progress-gru-start.json" in present:
            require(local + "progress-ols-complete.json" in present, "progress_binding")
        updates = [
            n for n in (128, 256, 384, 512) if local + f"progress-gru-{n:04d}.json" in present
        ]
        require(updates == [128, 256, 384, 512][: len(updates)], "progress_binding")
        if updates:
            require(local + "progress-gru-start.json" in present, "progress_binding")
        if local + "progress-gru-complete.json" in present:
            require(updates == [128, 256, 384, 512], "progress_binding")
            previous_complete = month * 2 + 2
        elif local + "progress-ols-complete.json" in present:
            previous_complete = month * 2 + 1
    require(previous_complete == result["actual_fits"], "progress_binding")
    starts = sum(name.endswith("-start.json") for name in result["artifact_sha256"])
    require(starts == result["fit_starts"], "progress_binding")


def _month_prediction(root, plan, month, prepared, pin, ols, gru):
    for values in (ols, gru):
        fixed.forecast_variance(values, 1)
    return dict(
        contract_sha256=pin,
        input_sha256=base.INPUT_PIN,
        window=plan.window_record(month),
        scaler_sha256=digest(encode(prepared.scaler)),
        model_sha256={
            name: digest(base._read(root / name)) for name in ("ols.npz", "gru.safetensors")
        },
        log_forecasts=dict(ols=ols, gru=gru),
        baseline=prepared.baseline.tolist(),
        inference_kind="original_worker",
    )


def assemble_predictions(plan, parts, pin):
    require(len(parts) == MONTHS, "incomplete_months")
    require(
        all(
            part["contract_sha256"] == pin
            and part["input_sha256"] == base.INPUT_PIN
            and part["window"] == plan.window_record(m)
            and part["inference_kind"] == "original_worker"
            for m, part in enumerate(parts)
        ),
        "prediction_binding",
    )
    forecasts = {name: [] for name in CANDIDATES}
    baseline = []
    for part in parts:
        require(set(part["log_forecasts"]) == set(CANDIDATES), "prediction_binding")
        for name in CANDIDATES:
            fixed.forecast_variance(part["log_forecasts"][name], 1)
            forecasts[name].extend(part["log_forecasts"][name])
        values = np.asarray(part["baseline"], dtype="<f8")
        require(
            values.shape == (1, 3) and np.isfinite(values).all() and (values >= fixed.FLOOR).all(),
            "baseline_binding",
        )
        baseline.extend(part["baseline"])
    return dict(
        contract_sha256=pin,
        input_sha256=base.INPUT_PIN,
        plan=plan.record(),
        month_prediction_sha256=[digest(encode(part)) for part in parts],
        log_forecasts=forecasts,
        baseline=baseline,
        inference_kind="original_worker",
    )


def evaluate(targets, predictions, plan, *, completed_fits):
    require(type(completed_fits) is int and completed_fits == FITS, "incomplete_fits")
    require(len(predictions["month_prediction_sha256"]) == MONTHS, "incomplete_months")
    return fixed.evaluate(targets, predictions, plan)


criterion = fixed.criterion


def _failure(error):
    unavailable = {
        "required_date_gap",
        "required_price",
        "required_session_missing",
        "required_session_duplicate",
        "required_row_binding",
        "price_close_invalid",
        "price_basis_invalid",
        "return_numeric",
        "target_numeric",
        "feature_numeric",
    }
    allowed = unavailable | {
        "compute_stop",
        "source_changed",
        "plan_changed",
        "feature_shape",
        "fit_nonfinite",
        "cuda_unavailable",
        "forecast_numeric",
        "metric_numeric",
        "train_membership",
        "immature_label",
        "incomplete_fits",
        "incomplete_months",
    }
    code = (
        str(error)
        if isinstance(error, (base.StudyFault, fixed.CrossAssetInputUnavailable))
        and str(error) in allowed
        else "numeric_range"
        if isinstance(error, (ArithmeticError, np.linalg.LinAlgError))
        else "worker_failed"
    )
    return code, "input_unavailable" if code in unavailable else "failed"


def run(root, market_root, artifact_root, pin):
    start = time.monotonic()
    deadline = start + SECONDS
    contract, commitment = read_contract(root, artifact_root, pin)
    root = _root(root, artifact_root)
    require(not _artifacts(root) and not (root / "worker-result.json").exists(), "attempt_exists")
    base.atomic_new(root / "started.json", dict(contract_sha256=pin, input_sha256=base.INPUT_PIN))
    result = dict(
        status="failed",
        reason="worker_failed",
        phase="source_input",
        actual_fits=0,
        fit_starts=0,
        contract_sha256=pin,
        elapsed_seconds=0,
        criterion={},
        cells=[],
        artifact_sha256={},
        resources={},
    )
    try:
        source = base.load_committed_source(
            commitment, artifact_root, market_root, deadline=deadline
        )
        plan = build_plan(source.plan.sessions)
        require(plan.record() == contract["plan"], "plan_changed")
        cache, parts = PreparationCache(source, plan), []
        for month in range(MONTHS):
            result["phase"] = "prepare"
            prepared = cache.prepare(month, deadline=deadline)
            local = root / "months" / f"{month:02d}"
            local.mkdir(parents=True, exist_ok=False)
            base.atomic_new(local / "scaler.json", prepared.scaler)
            specs = _progress_specs(month, pin)

            def progress(name, *, month=month, specs=specs):
                path = f"months/{month:02d}/{name}"
                base.atomic_new(root / path, specs[path])

            def ols_completed(*, month=month, progress=progress):
                result["actual_fits"] = month * 2 + 1
                progress("progress-ols-complete.json")

            def gru_progress(update, *, month=month, progress=progress):
                require(update in (128, 256, 384, 512), "progress_update")
                if update == UPDATES:
                    result["actual_fits"] = month * 2 + 2
                progress(f"progress-gru-{update:04d}.json")
                if update == UPDATES:
                    progress("progress-gru-complete.json")

            result["phase"], result["fit_starts"] = "fit_ols", month * 2 + 1
            progress("progress-ols-start.json")
            ols, weights, resources = fixed.fit_ols(
                prepared, deadline=deadline, progress=ols_completed
            )
            lifecycle.atomic_bytes(local / "ols.npz", weights)
            result["resources"][f"{month:02d}-ols"] = resources
            result["phase"], result["fit_starts"] = "fit_gru", month * 2 + 2
            progress("progress-gru-start.json")
            gru, weights, resources = fixed.fit_gru(
                prepared, deadline=deadline, progress=gru_progress
            )
            lifecycle.atomic_bytes(local / "gru.safetensors", weights)
            result["resources"][f"{month:02d}-gru"] = resources
            result["phase"] = "prediction_seal"
            part = _month_prediction(local, plan, month, prepared, pin, ols, gru)
            base.atomic_new(local / "predictions.json", part)
            parts.append(part)
            require(time.monotonic() < deadline, "compute_stop")
        predictions = assemble_predictions(plan, parts, pin)
        base.atomic_new(root / "predictions.json", predictions)
        result["phase"] = "forward_input"
        targets = fixed.load_dev_targets(source, plan, deadline=deadline)
        result["phase"] = "evaluate"
        cells = evaluate(targets, predictions, plan, completed_fits=result["actual_fits"])
        result["phase"] = "validate"
        require(
            base.load_committed_source(
                commitment, artifact_root, market_root, deadline=deadline
            ).files
            == source.files,
            "source_changed",
        )
        require(time.monotonic() < deadline, "compute_stop")
        result.update(status="complete", reason=None, cells=cells, criterion=criterion(cells))
    except Exception as error:
        reason, status = _failure(error)
        result.update(reason=reason, status=status)
    result.update(elapsed_seconds=time.monotonic() - start, artifact_sha256=_artifacts(root))
    base.atomic_new(root / "worker-result.json", result)
    return fixed._safe(result)


def verify(root, market_root, artifact_root, pin, result_pin):
    deadline = time.monotonic() + VERIFY_SECONDS
    contract, commitment = read_contract(root, artifact_root, pin)
    root = _root(root, artifact_root)
    result = base._json(root / "worker-result.json", result_pin, canonical=True)
    require(
        set(result)
        == {
            "status",
            "reason",
            "phase",
            "actual_fits",
            "fit_starts",
            "contract_sha256",
            "elapsed_seconds",
            "criterion",
            "cells",
            "artifact_sha256",
            "resources",
        }
        and result["contract_sha256"] == pin
        and result["phase"] in PHASES
        and type(result["actual_fits"]) is int
        and type(result["fit_starts"]) is int
        and 0 <= result["actual_fits"] <= result["fit_starts"] <= FITS
        and type(result["elapsed_seconds"]) in (int, float)
        and math.isfinite(result["elapsed_seconds"])
        and result["elapsed_seconds"] >= 0,
        "result_binding",
    )
    require(result["artifact_sha256"] == _artifacts(root), "artifact_binding")
    require(
        base._json(root / "started.json", canonical=True)
        == dict(contract_sha256=pin, input_sha256=base.INPUT_PIN),
        "start_binding",
    )
    _verify_progress(root, result, pin)
    if result["status"] in {"failed", "input_unavailable"}:
        require(
            type(result["reason"]) is str and result["cells"] == [] and result["criterion"] == {},
            "failure_binding",
        )
        return fixed._safe(result) | dict(
            replay="failure_binding_only", fits=0, inference=0, searches=0, writes=0
        )
    require(
        result["status"] == "complete"
        and result["reason"] is None
        and result["phase"] == "validate"
        and result["actual_fits"] == result["fit_starts"] == FITS
        and set(result["artifact_sha256"]) == set(ARTIFACTS),
        "complete_binding",
    )
    source = base.load_committed_source(commitment, artifact_root, market_root, deadline=deadline)
    plan = build_plan(source.plan.sessions)
    require(plan.record() == contract["plan"], "plan_changed")
    cache, parts = PreparationCache(source, plan), []
    for month in range(MONTHS):
        prepared = cache.prepare(month, deadline=deadline)
        local = root / "months" / f"{month:02d}"
        require(
            base._json(local / "scaler.json", canonical=True) == prepared.scaler, "scaler_replay"
        )
        part = base._json(local / "predictions.json", canonical=True)
        expected = _month_prediction(
            local,
            plan,
            month,
            prepared,
            pin,
            part["log_forecasts"]["ols"],
            part["log_forecasts"]["gru"],
        )
        require(part == expected, "prediction_binding")
        parts.append(part)
    predictions = assemble_predictions(plan, parts, pin)
    require(
        base._json(root / "predictions.json", canonical=True) == predictions, "prediction_binding"
    )
    cells = evaluate(
        fixed.load_dev_targets(source, plan, deadline=deadline),
        predictions,
        plan,
        completed_fits=result["actual_fits"],
    )
    require(
        encode(cells) == encode(result["cells"]) and criterion(cells) == result["criterion"],
        "numeric_replay",
    )
    require(
        base.load_committed_source(commitment, artifact_root, market_root, deadline=deadline).files
        == source.files,
        "source_changed",
    )
    require(time.monotonic() < deadline, "compute_stop")
    return fixed._safe(result) | dict(
        replay="exact_metrics/cached_prediction_binding", fits=0, inference=0, searches=0, writes=0
    )


def _synthetic_sessions():
    day, end, sessions = date(2020, 1, 1), date(2026, 10, 7), []
    while day <= end:
        if day.weekday() < 5 and (day.month, day.day) != (1, 1):
            sessions.append(
                base.CrossAssetSession(
                    day,
                    datetime(day.year, day.month, day.day, 14, 30, tzinfo=UTC),
                    datetime(day.year, day.month, day.day, 21, tzinfo=UTC),
                )
            )
        day += timedelta(days=1)
    return tuple(sessions)


def synthetic_smoke():
    import torch

    plan = build_plan(_synthetic_sessions())
    rng = np.random.default_rng(SEED)
    raw = rng.normal(0, 0.01, (WINDOW + 1, 3, 63))
    prepared = fixed.prepare_arrays(raw, np.full((WINDOW, 3), 0.0001), plan.month(0))
    threads = torch.get_num_threads()
    torch.set_num_threads(2)
    try:
        with torch.random.fork_rng(devices=[]):
            torch.default_generator.manual_seed(SEED)
            model = fixed.make_gru()
            require(sum(p.numel() for p in model.parameters()) == 3651, "gru_parameters")
            tensor = torch.from_numpy(np.array(prepared.train_x, copy=True))
            elapsed = []
            for _ in range(3):
                model.zero_grad(set_to_none=True)
                start = time.monotonic()
                loss = model(tensor).square().mean()
                require(bool(torch.isfinite(loss).item()), "smoke_model")
                loss.backward()
                elapsed.append(time.monotonic() - start)
    finally:
        torch.set_num_threads(threads)
    parts = [
        dict(
            contract_sha256="synthetic",
            input_sha256=base.INPUT_PIN,
            window=plan.window_record(m),
            log_forecasts=dict(ols=[[math.log(0.0001)] * 3], gru=[[math.log(0.0001)] * 3]),
            baseline=[[0.0001] * 3],
            inference_kind="original_worker",
        )
        for m in range(MONTHS)
    ]
    cells = evaluate(
        np.full((MONTHS, 3), 0.0001),
        assemble_predictions(plan, parts, "synthetic"),
        plan,
        completed_fits=FITS,
    )
    require(set(criterion(cells).values()) == {"rejected"}, "smoke_matrix")
    return dict(
        status="smoke_passed",
        train_entries_per_month=WINDOW,
        dev_entries=MONTHS,
        cells=6,
        planned_fits=FITS,
        actual_fits=0,
        fit_starts=0,
        actual_market_reads=0,
        optimizer_steps=0,
        gpu=False,
        cpu_gru_parameters=3651,
        synthetic_cpu_forward_backward_seconds=elapsed,
        timing_scope="three source-free CPU kernels, not33-fit CUDA budget assurance",
        paper_input=False,
    )


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True, choices=("smoke", "run", "verify"))
    for name in ("root", "market-root", "artifact-root"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--contract-sha256")
    parser.add_argument("--result-sha256")
    args = parser.parse_args(argv)
    bound = args.phase != "smoke"
    if any(
        bool(v) != bound
        for v in (args.root, args.market_root, args.artifact_root, args.contract_sha256)
    ) or bool(args.result_sha256) != (args.phase == "verify"):
        parser.error(
            "run/verify require roots+contract pin; verify requires result pin; smoke none"
        )
    try:
        result = (
            synthetic_smoke()
            if not bound
            else run(args.root, args.market_root, args.artifact_root, args.contract_sha256)
            if args.phase == "run"
            else verify(
                args.root,
                args.market_root,
                args.artifact_root,
                args.contract_sha256,
                args.result_sha256,
            )
        )
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0 if result["status"] in {"complete", "smoke_passed"} else 2
    except Exception:
        print(json.dumps(dict(status="failed", reason="study_unavailable")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
