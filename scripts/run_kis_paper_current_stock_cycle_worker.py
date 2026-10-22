"""Bounded frozen-target intake for the native owned stock Paper cycle.

No collection, fitting, bank initialization or credential discovery. The
explicit execute path accepts only a private Paper packet on stdin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
from dataclasses import fields, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from urllib.parse import urlsplit

from thericher_v2.contracts import TargetExposureProposal
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_canary as canary
from thericher_v2.execution import kis_readonly as readonly
from thericher_v2.execution.kis_market_data_rate_gate import (
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)
from thericher_v2.execution.kis_paper_portfolio_execute import _unlinked
from thericher_v2.execution.kis_paper_stock_canary import (
    KisPaperStockCanaryClient,
    UrllibKisPaperStockCanaryTransport,
)
from thericher_v2.execution.kis_paper_stock_quote import KisPaperStockInstrument
from thericher_v2.models.current_nas_frozen_rank_target import (
    FEATURE_SCHEMA_ID,
    MODELS,
    FrozenScoreMetadata,
    PreparedTarget,
)
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    ResearchDecisionReceipt,
    receipt_from_target_exposure_proposal,
)

APP = Path("/app")
ARTIFACT = APP / "model_artifacts"
CONTROL = APP / "market_data/us_equities/kis_paper_private/collection-control-v1"
PREPARATION = "execution/current-nas-frozen-target-preparation-20261015-v1"
ORIGINAL = "research/current-nas512-frozen-expert-score-panel-20261015-v1"
LINKED = "research/current-nas512-frozen-expert-score-launch-recovery-20261015-v1"
ORIGIN = "D:/thericher-v2/model-artifacts/"
POLICY_SOURCE = "src/thericher_v2/models/current_nas_frozen_rank_target.py"
POLICY_PIN = "9fe47f72500a02a535d74e1a6607314f237310a70f89a5e2a22bccae6ed672f0"
PRIVATE_PINS = {
    "outcome.json": "98d58064ec8a756fa11bccebd88e180c9a24252940f60cf3b8ec767e2c2d9807",
    "targets.private.json": "597c1e80577b9724da729a0eae45214b45bf03a49f7713ffaaec2594cac36b0b",
    "score-observation.json": "ffa08a4fccce9c6846f52e1aa84161e1e8ff1511fd50cad302737b82e53398a5",
    "source-bindings.private.json": (
        "9730edf1e1c4809a1dc3416672c2a3272c35e40a1c1ab559a01f64f97a57796b"
    ),
    "prep-v3.json": "7684ce37b059c38f16c7391a885d928002a26df495ce9db3339848001f9651d5",
    "consumer.py": "3c9858e3b28870f0971fcf1d3337a862590d3183520d4c9c7518e0d0b89d6964",
    "test_consumer.py": "d7c9d70fe1ac84d07b9a43c9a678e78bccf2b03421991da664ee302afe486551",
}
SOURCE_PINS = {
    POLICY_SOURCE: POLICY_PIN,
    "tests/test_current_nas_frozen_rank_target.py": (
        "0fd689aef4c473cae199b6c34411af5c17735f60105ea21df6818bbed61f935c"
    ),
    "src/thericher_v2/contracts.py": (
        "cfee0f6a46eed7955be6e9385fef54b1edb892142f6775d945d65b9dd6b3e603"
    ),
    "src/thericher_v2/market/resample.py": (
        "5a716dad2f2e762f349367cf2e9dd1db09740da397b3b3cb277dff828e972449"
    ),
    "src/thericher_v2/research/decision_receipt.py": (
        "d7dfbdd16a0798f28f2d5692945219c56874c6a0a210e96ad059ac915889220a"
    ),
    "src/thericher_v2/data/us_equity_session.py": (
        "c9bb9d1ef8d8564477595e4b36f69a7ba75b75cfefe3dcedf40eb8f27c45ae4e"
    ),
    "src/thericher_v2/data/resample.py": (
        "855cdf3d2b555293d62399691c750cff078e4c134444f9917fde6fac1c6c8c54"
    ),
}
INPUT_PINS = {
    ORIGINAL
    + "/engine-contract.json": "505cb396010f36e00ca98397e0be084a06330e3c4abe237912ee4a59c1b21e0f",
    ORIGINAL
    + "/data-contract.json": "9a9d226f5c4b1c03b731ee76e753a8b08711af56312fc7c105011bc094823d29",
    ORIGINAL + "/review-output/final-current-linked-r2.json": (
        "2f3ee3a847c75d95e177b758f84f65e4235d339f5df5e7497149137670f25fd6"
    ),
}
SCORE_PIN = "173166055beca0f2a80a99d855a81a870e8a82cadb1cdb2b4f2a9269bffafcca"
DATA_RECEIPT_PIN = "e8eb0ffc23a77acba8aae4689af85bdefc4a14126da7cd657289a9c0f2d07898"
CLEANUP_PIN = "01e0464a220c2daba6096dada7815564cce759bb7413a3137b9899f39354f55a"
PREVIOUS = datetime(2026, 10, 14, 20, tzinfo=UTC)
DATA_AVAILABLE = datetime.fromisoformat("2026-10-14T20:47:49.826785+00:00")
INPUT_ASOF = datetime.fromisoformat("2026-10-14T21:31:19.063233+00:00")
COMPLETION_BOUND = datetime(2026, 10, 14, 22, 6, 59, tzinfo=UTC)
ENV_KEYS = frozenset((*readonly.KIS_PAPER_ENV_KEYS, "THERICHER_MODE"))
MAX_BYTES = 2 * 1024 * 1024
NATIVE_REASONS = {
    "advanced": {"native_leg_closed"},
    "pending": {"exact_request_retained"},
    "hold": {"await_declared_exit", "outside_declared_session"},
    "complete": {"already_completed", "policy_owned_flat"},
    "no_intent": {
        "native_risk_no_intent",
        "cycle_never_reserved_retired",
        "cycle_target_quote_unavailable",
    },
    "unavailable": {
        "native_recovery_required",
        "cycle_reference_invalid",
        "cycle_value_invalid",
        "cycle_checkpoint_invalid",
        "cycle_existing_basis_required",
        "cycle_basis_changed",
        "cycle_client_unavailable",
        "cycle_client_invalid",
        "cycle_account_changed",
        "cycle_owner_missing",
        "cycle_foreign_stock_registration",
        "cycle_input_invalid",
        "cycle_session_invalid",
        "cycle_ten_targets_required",
        "cycle_target_invalid",
        "cycle_target_duplicate",
        "cycle_target_clock_invalid",
        "cycle_input_binding_mismatch",
        "cycle_receipt_invalid",
        "cycle_reservation_missing",
        "cycle_request_changed",
        "cycle_reservation_changed",
        "cycle_retained_quote_stale",
        "cycle_configuration_invalid",
        "cycle_target_unavailable",
        "cycle_quote_timestamp_unavailable",
        "cycle_quote_timestamp_invalid",
        "cycle_quote_timestamp_stale",
        "cycle_quote_tick_invalid",
        "cycle_quote_bid_ask_invalid",
        "cycle_readonly_snapshot_unavailable",
        "cycle_policy_changed",
        "cycle_retirement_unproven",
        "cycle_retired_request_restored",
        "cycle_owned_not_flat",
    },
}


def _require(ok, category="current_targets_unavailable"):
    if not ok:
        raise ValueError(category)


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result)
            result[key] = value
        return result

    return json.loads(
        raw,
        object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid_number")),
    )


def parse_packet(payload: bytes):
    _require(type(payload) is bytes and len(payload) <= 8192, "paper_packet_invalid")
    values = _json(payload)
    _require(
        type(values) is dict
        and set(values) == ENV_KEYS
        and all(
            type(value) is str and value.strip() == value and value for value in values.values()
        )
        and values["THERICHER_MODE"] == "kis_paper",
        "paper_packet_invalid",
    )
    return readonly.load_kis_paper_config_from_environment(values)


def _checked(path, pin):
    _require(type(pin) is str and re.fullmatch(r"[0-9a-f]{64}", pin) is not None)
    _unlinked(path)
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    _require(len(raw) <= MAX_BYTES and hashlib.sha256(raw).hexdigest() == pin)
    return raw


def _utc(value):
    _require(type(value) is str)
    at = datetime.fromisoformat(value)
    _require(at.utcoffset() == timedelta(0))
    return at


def _decimal(value):
    _require(type(value) is str and len(value) <= 128)
    result = Decimal(value)
    _require(result.is_finite())
    return result


def _metadata(value):
    _require(
        type(value) is dict and set(value) == {field.name for field in fields(FrozenScoreMetadata)}
    )
    clocks = {
        "feature_window_end",
        "data_first_available_at",
        "input_asof",
        "inference_completed_at",
        "score_first_available_at",
    }
    return FrozenScoreMetadata(**{key: _utc(v) if key in clocks else v for key, v in value.items()})


def _pin_map(value):
    _require(type(value) is dict)
    result = {}
    for name, pin in value.items():
        _require(type(name) is str and type(pin) is str)
        normalized = name.replace("\\", "/")
        _require(normalized not in result and re.fullmatch(r"[0-9a-f]{64}", pin) is not None)
        result[normalized] = pin
    return result


def fifth_session(entry_date):
    """Count official sessions inclusively; weekends/holidays return None."""
    sessions = []
    for offset in range(32):
        session = us_equity_2026_session(entry_date + timedelta(days=offset))
        if session is not None:
            sessions.append(session)
            if len(sessions) == 5:
                return sessions[0].window, session.window
    raise ValueError("official_session_unavailable")


def _load_targets(*, artifact_root, repository_root, clock):
    root = artifact_root / PREPARATION
    raw = {name: _checked(root / name, pin) for name, pin in PRIVATE_PINS.items()}
    docs = {name: _json(value) for name, value in raw.items() if name.endswith(".json")}
    upstream = {
        name: _json(_checked(artifact_root / name, pin)) for name, pin in INPUT_PINS.items()
    }
    outcome, target_doc, observation, bindings, prep = (
        docs[name]
        for name in (
            "outcome.json",
            "targets.private.json",
            "score-observation.json",
            "source-bindings.private.json",
            "prep-v3.json",
        )
    )
    data = upstream[ORIGINAL + "/data-contract.json"]
    engine = upstream[ORIGINAL + "/engine-contract.json"]
    independent = upstream[ORIGINAL + "/review-output/final-current-linked-r2.json"]
    _require(
        outcome["status"] == "actual_pure_target_preparation_complete"
        and tuple(outcome[key] for key in ("supported", "experts", "proposals")) == (243, 5, 10)
        and all(type(outcome[key]) is int for key in ("supported", "experts", "proposals"))
        and outcome["independent_rank_parity"] is True
        and outcome["untrusted_proposals"] is True
        and outcome["profit_qualified"] is False
        and outcome["deployment_claim"] is False
        and all(
            type(outcome[key]) is int and outcome[key] == 0
            for key in (
                "fits",
                "GPU",
                "broker_API",
                "account_reads",
                "credentials",
                "orders",
                "schedules",
            )
        )
    )
    for field, name in (
        ("target_sha256", "targets.private.json"),
        ("source_bindings_sha256", "source-bindings.private.json"),
        ("score_observation_sha256", "score-observation.json"),
        ("prep_sha256", "prep-v3.json"),
        ("source_sha256", "consumer.py"),
    ):
        _require(outcome[field] == PRIVATE_PINS[name])
    _require(
        prep["status"] == "PREP_passed"
        and prep["tests"] == 7
        and prep["consumer_pins"]
        == {name: PRIVATE_PINS[name] for name in ("consumer.py", "test_consumer.py")}
        and prep["source_pins"] == bindings["checked_current_source_pins"]
        and target_doc["source_bindings_ref"]
        == "sha256:" + PRIVATE_PINS["source-bindings.private.json"]
    )
    _require(
        _pin_map(bindings["checked_current_source_pins"])
        == {
            "C:/Users/Public/Documents/thericher-v2/" + name: pin
            for name, pin in SOURCE_PINS.items()
        }
    )
    policy_ref = (
        "sha256:"
        + hashlib.sha256(_checked(repository_root / POLICY_SOURCE, POLICY_PIN)).hexdigest()
    )
    for origin_path, pin in bindings["checked_current_source_pins"].items():
        prefix = "C:/Users/Public/Documents/thericher-v2/"
        normalized = origin_path.replace("\\", "/")
        _require(normalized.startswith(prefix))
        relative = normalized[len(prefix) :]
        _require(".." not in Path(relative).parts and relative.startswith(("src/", "tests/")))
        # Tests are historical PREP evidence, not required in the baked image.
        if relative.startswith("src/"):
            _checked(repository_root / relative, pin)
    for relative, pin in INPUT_PINS.items():
        _require(_pin_map(bindings["checked_artifact_pins"])[ORIGIN + relative] == pin)
    _require(
        independent["status"] == "independent_current_score_math_bindings_checked"
        and type(independent["counts"]["supported"]) is int
        and independent["counts"]["supported"] == 243
        and engine["models"] == list(MODELS)
        and set(engine["frozen"]["checkpoint_sha256"]) == set(MODELS)
    )
    weights = ORIGIN + "research/retained-relative-ranking-completion-20261015-v1/study/output/"
    expected_weights = {
        weights + f"final-{name}-checkpoint.npz": pin
        for name, pin in engine["frozen"]["checkpoint_sha256"].items()
    }
    expected_weights[weights + "final-scalers.npz"] = engine["frozen"]["scalers_sha256"]
    _require(_pin_map(bindings["checked_weight_pins"]) == expected_weights)
    keys, supported = data["keys"], data["supported_slots"]
    _require(
        type(keys) is list
        and len(keys) == len(set(keys)) == 512
        and all(type(key) is str and re.fullmatch(r"[A-Z]{1,10}/NAS", key) for key in keys)
        and type(supported) is list
        and len(supported) == len(set(supported)) == 243
        and all(type(slot) is int and 0 <= slot < 512 for slot in supported)
        and supported == sorted(supported)
        and sum(slot >= 128 for slot in supported) == 181
    )
    metadata = _metadata(target_doc["metadata"])
    _require(
        metadata.score_ref == "sha256:" + SCORE_PIN
        and metadata.input_ref == "sha256:" + INPUT_PINS[ORIGINAL + "/data-contract.json"]
        and metadata.independent_readback_ref
        == "sha256:" + INPUT_PINS[ORIGINAL + "/review-output/final-current-linked-r2.json"]
        and metadata.data_producer_ref == "sha256:" + DATA_RECEIPT_PIN
        and metadata.score_producer_ref == "sha256:" + PRIVATE_PINS["score-observation.json"]
        and metadata.feature_window_end == PREVIOUS
        and metadata.data_first_available_at == DATA_AVAILABLE
        and metadata.input_asof == INPUT_ASOF
        and metadata.inference_completed_at == COMPLETION_BOUND
        and observation["kind"] == "consumer_byte_observation_not_original_publication"
        and observation["original_score_publication_at"] is None
        and observation["original_inference_completed_at"] is None
        and observation["mtime_used"] is False
        and _utc(observation["byte_observed_at"]) == metadata.score_first_available_at
        and _utc(observation["completion_observed_bound"]) == COMPLETION_BOUND
        and observation["completion_receipt_ref"] == "sha256:" + CLEANUP_PIN
        and observation["score_ref"] == metadata.score_ref
        and observation["input_ref"] == metadata.input_ref
        and outcome["temporal_semantics"] == observation
    )
    entry, exit_session = fifth_session(date(2026, 10, 15))
    _require(
        entry.open_ts == datetime(2026, 10, 15, 13, 30, tzinfo=UTC)
        and exit_session.close_ts == datetime(2026, 10, 21, 20, tzinfo=UTC)
        and target_doc["intended_session"]
        == {"open_ts": entry.open_ts.isoformat(), "close_ts": entry.close_ts.isoformat()}
        and target_doc["units"] == "desired_ORIGINAL_basis_fractions_not_cash_or_allocated_capital"
    )
    now = clock()
    _require(type(now) is datetime and now.utcoffset() == timedelta(0))
    _require(metadata.score_first_available_at <= now < entry.close_ts)
    results = []
    _require(type(target_doc["targets"]) is list and len(target_doc["targets"]) == 10)
    for row in target_doc["targets"]:
        _require(type(row) is dict and set(row) == {field.name for field in fields(PreparedTarget)})
        _require(type(row["slot"]) is int and row["slot"] in supported)
        _require(row["metadata"] == target_doc["metadata"])
        proposal_values, receipt_values = dict(row["proposal"]), dict(row["receipt"])
        for key in ("target_exposure", "confidence"):
            proposal_values[key] = _decimal(proposal_values[key])
        for key in ("decided_at", "valid_until", "feature_window_end"):
            proposal_values[key] = _utc(proposal_values[key])
        for key in ("decided_at", "valid_until"):
            receipt_values[key] = _utc(receipt_values[key])
        proposal = TargetExposureProposal(**proposal_values)
        receipt = ResearchDecisionReceipt(**receipt_values)
        references = DecisionReceiptReferences(
            receipt.campaign_ref,
            receipt.model_ref,
            receipt.input_manifest_ref,
            receipt.proposal_ref,
        )
        _require(receipt_from_target_exposure_proposal(proposal, references=references) == receipt)
        rank = row["mean_ordinal_rank"]
        _require(type(rank) is list and len(rank) == 2 and all(type(n) is int for n in rank))
        mean = Fraction(*rank)
        _require(1 <= mean <= 243 and (mean * 5).denominator == 1)
        _require(
            proposal.symbol == keys[row["slot"]].split("/")[0]
            and proposal.market == "US"
            and proposal.action == "enter"
            and proposal.input_status == "ready"
            and proposal.feature_schema_id == FEATURE_SCHEMA_ID
            and proposal.reason
            == "fixed_five_ordinal_mean_untrusted_uncalibrated_not_profit_qualified"
            and proposal.target_exposure == Decimal(".005")
            and proposal.confidence == 0
            and _decimal(row["research_weight"]) == Decimal(".05")
            and proposal.feature_window_end == PREVIOUS
            and metadata.score_first_available_at <= proposal.decided_at <= now
            and max(proposal.decided_at, entry.open_ts) < proposal.valid_until == entry.close_ts
            and receipt.input_manifest_ref == metadata.input_ref
            and receipt.model_ref == "ref:" + SCORE_PIN
            and receipt.campaign_ref == receipt.proposal_ref
            and proposal.proposal_id == f"current-nas-{receipt.campaign_ref[4:]}-{row['slot']}"
        )
        results.append(
            PreparedTarget(row["slot"], mean, Decimal(".05"), proposal, receipt, metadata)
        )
    _require(
        len(results) == len({target.slot for target in results}) == 10
        and len({target.proposal.symbol for target in results}) == 10
        and len({target.receipt.campaign_ref for target in results}) == 1
        and [(target.mean_ordinal_rank, target.slot) for target in results]
        == sorted((target.mean_ordinal_rank, target.slot) for target in results)
        and sum(Fraction(target.proposal.target_exposure) for target in results) == Fraction(1, 20)
    )
    from thericher_v2.execution.kis_paper_current_stock_cycle import CurrentStockCycleInput

    return CurrentStockCycleInput(
        targets=tuple(results),
        entry_session=entry,
        exit_session=exit_session,
        input_ref="sha256:" + PRIVATE_PINS["targets.private.json"],
        policy_ref=policy_ref,
    )


def load_targets(*, artifact_root=ARTIFACT, repository_root=APP, clock=lambda: datetime.now(UTC)):
    try:
        return _load_targets(
            artifact_root=artifact_root, repository_root=repository_root, clock=clock
        )
    except Exception:
        raise ValueError("current_targets_unavailable") from None


class RequestBudget:
    """One shared, non-retrying budget for the whole native visit."""

    def __init__(
        self,
        *,
        control_root=CONTROL,
        clock=lambda: datetime.now(UTC),
        monotonic=time.monotonic,
        sleeper=time.sleep,
    ):
        self.clock, self.monotonic, self.sleeper = clock, monotonic, sleeper
        self.deadline = monotonic() + 280
        self.calls = dict(token_posts=0, get_requests=0, buy_posts=0, sell_posts=0, cancel_posts=0)
        self.starts = []
        self.token = KisPaperMarketDataTokenStartGate(
            control_root=control_root,
            minimum_request_interval_seconds=60,
            clock=clock,
        )
        self.rate = KisPaperMarketDataRateGate(
            control_root=control_root,
            minimum_request_interval_seconds=1.25,
            clock=clock,
            sleeper=self.sleep,
        )
        self.pacer = readonly.KisPaperRequestPacer(
            minimum_request_interval_seconds=1.25,
            monotonic_clock=monotonic,
            sleeper=self.sleep,
        )

    def sleep(self, duration):
        if (
            not math.isfinite(duration)
            or not 0 <= duration <= 2
            or self.monotonic() + duration + 8 >= self.deadline
        ):
            raise canary.KisPaperCanaryError("request_budget_exhausted")
        self.sleeper(duration)

    def _check(self, key):
        if (
            self.monotonic() + 8 >= self.deadline
            or sum(self.calls.values()) >= 128
            or key == "token_posts"
            and self.calls[key] >= 1
            or key in {"buy_posts", "sell_posts"}
            and self.calls["buy_posts"] + self.calls["sell_posts"] >= 1
            or key == "cancel_posts"
            and self.calls[key] >= 1
        ):
            raise canary.KisPaperCanaryError("request_budget_exhausted")

    def start(self, request, before_wire):
        path = urlsplit(request.url).path
        if request.method == "GET":
            key = "get_requests"
        elif path == readonly.KIS_PAPER_TOKEN_PATH:
            key = "token_posts"
        elif path == canary.KIS_PAPER_US_CANCEL_PATH:
            key = "cancel_posts"
        elif request.headers.get("tr_id") == canary.KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID:
            key = "buy_posts"
        else:
            key = "sell_posts"
        self._check(key)
        self.rate.wait_for_request_slot()
        self._check(key)
        if before_wire is not None:
            before_wire()
        self._check(key)
        if key == "token_posts" and not self.token.claim_token_request_start():
            raise canary.KisPaperCanaryError("token_request_not_due")
        self.calls[key] += 1
        self.starts.append(self.monotonic())
        self.pacer.record_request_start()


class OwnedTransport(UrllibKisPaperStockCanaryTransport):
    def __init__(self, *, instrument, limits):
        super().__init__(instrument=instrument, timeout_seconds=8, pacer=limits.pacer)
        self.limits = limits

    def _request(self, request, *, before_wire=None):
        if type(request) is not readonly.KisHttpRequest:
            raise canary.KisPaperCanaryError("request_not_allowlisted")
        request = replace(
            request,
            headers=dict(request.headers),
            query=dict(request.query),
            json_body=None if request.json_body is None else dict(request.json_body),
        )
        # The native exact-stock transport validates before invoking this callback.
        response = super()._request(
            request, before_wire=lambda: self.limits.start(request, before_wire)
        )
        if response.status_code == 429:
            self.limits.rate.record_rate_limit()
        return response


def client_factory(config, limits):
    clients, shared_token = {}, None

    def client(instrument):
        nonlocal shared_token
        _require(type(instrument) is KisPaperStockInstrument, "stock_instrument_invalid")
        if instrument not in clients:
            transport = OwnedTransport(instrument=instrument, limits=limits)
            bound = KisPaperStockCanaryClient(
                config=config, transport=transport, instrument=instrument
            )
            if shared_token is None:
                shared_token = bound._issue_access_token()
            bound._access_token = shared_token
            clients[instrument] = bound
        return clients[instrument]

    return client


def _categorical(value):
    _require(
        type(value) is dict
        and set(value) == {"status", "reason", "leg_count"}
        and type(value["status"]) is str
        and value["status"] in NATIVE_REASONS
        and type(value["reason"]) is str
        and value["reason"] in NATIVE_REASONS[value["status"]]
        and type(value["leg_count"]) is int
        and value["leg_count"] in {0, 1},
        "native_cycle_output_invalid",
    )
    return dict(
        value,
        kind="kis_paper_current_stock_cycle_v1",
        limitation="cycle_status_not_current_inventory_or_net_pnl",
    )


def native_paths():
    return dict(
        state_root=APP / "private/canary",
        repository_root=APP,
        artifact_root=ARTIFACT,
        runtime_projection_path=APP / "runtime/state/kis_paper_canary.json",
        paper_account_snapshot_path=APP / "runtime/state/paper_account_snapshot.json",
        emergency_state_path=APP / "emergency/emergency_state.json",
        execution_control_path=APP / "emergency/paper_execution_control.json",
    )


def first_failure_file_sink(output_child):
    """Caller must bind this exact existing child to its owned wake/output mount.

    Confinement is not ownership proof. Never create directories or replace records.
    """

    def write(value):
        from thericher_v2.execution import kis_paper_current_stock_cycle as cycle

        value = cycle.safe_current_stock_first_failure(value)
        child = Path(output_child)
        _unlinked(child)
        root = (ARTIFACT / "execution").resolve()
        child = child.resolve(strict=True)
        _require(
            child.is_dir()
            and child.is_relative_to(root)
            and len(child.relative_to(root).parts) >= 2,
            "first_failure_output_invalid",
        )
        path = child / "first-failure.json"
        _unlinked(path)
        with path.open("x", encoding="ascii") as stream:
            stream.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")

    return write


def run(
    config,
    *,
    execute=False,
    clock=lambda: datetime.now(UTC),
    first_failure_sink=None,
    profile=None,
    target_loader=None,
    expected_input_ref=None,
    expected_policy_ref=None,
):
    if not execute:
        return dict(status="inert", credential_reads=0, broker_calls=0)
    from thericher_v2.execution.kis_paper_current_stock_cycle import (
        StockCycleProfile,
        run_kis_paper_current_stock_cycle,
    )

    injected = {}
    if profile is not None:
        if (
            type(profile) is not StockCycleProfile
            or profile not in {
                StockCycleProfile.MODEL_PROPOSAL_NAS,
                StockCycleProfile.MODEL_WEIGHTS_NAS,
            }
            or not callable(target_loader)
            or any(
                type(ref) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", ref) is None
                for ref in (expected_input_ref, expected_policy_ref)
            )
        ):
            raise ValueError("model_profile_injection_invalid")
        injected["profile"] = profile
    elif any(
        value is not None for value in (target_loader, expected_input_ref, expected_policy_ref)
    ):
        raise ValueError("model_profile_injection_invalid")
    limits = RequestBudget(control_root=CONTROL, clock=clock)
    paths = native_paths()
    try:
        result = _categorical(
            run_kis_paper_current_stock_cycle(
                **paths,
                expected_account_ref=budget._digest(
                    [config.base_url, config.account_number, config.account_product_code]
                ),
                expected_input_ref=expected_input_ref
                if injected
                else "sha256:" + PRIVATE_PINS["targets.private.json"],
                expected_policy_ref=expected_policy_ref if injected else "sha256:" + POLICY_PIN,
                target_loader=target_loader
                if injected
                else lambda: load_targets(
                    artifact_root=paths["artifact_root"],
                    repository_root=paths["repository_root"],
                    clock=clock,
                ),
                client_factory=client_factory(config, limits),
                clock=clock,
                execute=True,
                **injected,
                **(
                    {"first_failure_sink": first_failure_sink}
                    if first_failure_sink is not None
                    else {}
                ),
            ).safe_payload()
        )
    except Exception:
        result = dict(
            status="unavailable",
            reason="worker_recovery_required",
            unknown_effects_not_assumed_zero=True,
        )
    result.update(
        paper_only=True,
        calls=limits.calls,
        visits=1,
        http_start_gaps_seconds=[
            round(b - a, 6) for a, b in zip(limits.starts, limits.starts[1:], strict=False)
        ],
        pacing_basis="final_opener_delegate_boundary_not_socket_wire_measurement",
        observed_at_utc=clock().isoformat(),
        fees="not_observed",
        settled_cash="not_observed",
        net_pnl="not_observed",
        unknown_effects_not_assumed_zero=True,
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--first-failure-output-child", type=Path)
    args = parser.parse_args(argv)
    if not args.execute:
        print('{"status":"inert","credential_reads":0,"broker_calls":0}')
        return 0
    try:
        result = run(
            parse_packet(sys.stdin.buffer.read(8193)),
            execute=True,
            **(
                {"first_failure_sink": first_failure_file_sink(args.first_failure_output_child)}
                if args.first_failure_output_child is not None
                else {}
            ),
        )
    except Exception:
        result = dict(
            status="unavailable",
            reason="worker_recovery_required",
            paper_only=True,
            unknown_effects_not_assumed_zero=True,
        )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"complete", "no_intent", "pending", "advanced", "hold"} else 20


if __name__ == "__main__":
    raise SystemExit(main())
