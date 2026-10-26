"""Invented private artifacts and mocked wire only; no provider or account access."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import socket
import traceback
import urllib.request
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_kis_paper_current_stock_cycle import NativeSyntheticStockClient
from test_kis_paper_current_stock_cycle import h as h
from test_kis_paper_portfolio_execute import CONFIG
from test_kis_paper_stock_canary import INSTRUMENT, _generic_request, _quote_request
from test_run_kis_paper_current_stock_cycle import w as host
from thericher_v2.execution import kis_paper_current_stock_cycle as cycle
from thericher_v2.execution.kis_paper_stock_quote import KisPaperStockInstrument
from thericher_v2.models.current_nas_frozen_rank_target import (
    FrozenScoreInput,
    SupportedScore,
    prepare_targets,
)

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "current_stock_worker", REPO / "scripts/run_kis_paper_current_stock_cycle_worker.py"
)
w = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(w)
NOW = datetime(2026, 10, 15, 14, tzinfo=UTC)


@pytest.fixture(autouse=True)
def no_network_or_credentials(monkeypatch):
    def deny(*_args, **_kwargs):
        pytest.fail("real_provider_or_credentials_forbidden")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", deny)
    monkeypatch.setattr(w.readonly, "load_kis_paper_config", deny)


def packet():
    return dict(
        KIS_PAPER_APP_KEY="synthetic-key",
        KIS_PAPER_APP_SECRET="synthetic-secret",
        KIS_PAPER_ACCOUNT_NO="12345678",
        KIS_PAPER_ACCOUNT_PRODUCT_CODE="01",
        THERICHER_MODE="kis_paper",
    )


def test_default_does_not_read_stdin_or_run(monkeypatch, capsys):
    monkeypatch.setattr(w.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"not-read")))
    monkeypatch.setattr(w, "run", lambda _: pytest.fail("inert worker executed"))
    assert w.main([]) == 0
    assert w.sys.stdin.buffer.tell() == 0
    assert json.loads(capsys.readouterr().out) == dict(
        status="inert", credential_reads=0, broker_calls=0
    )


@pytest.mark.parametrize(
    "fault", ["live", "mode", "extra", "missing", "bool", "nested", "duplicate", "large", "nan"]
)
def test_only_exact_paper_stdin_packet(fault, monkeypatch, capsys):
    body = packet()
    if fault == "live":
        body["KIS_LIVE_APP_KEY"] = "never-route"
    elif fault == "mode":
        body["THERICHER_MODE"] = "kis_live"
    elif fault == "extra":
        body["base_url"] = "https://untrusted.invalid"
    elif fault == "missing":
        del body["KIS_PAPER_APP_KEY"]
    elif fault == "bool":
        body["KIS_PAPER_APP_KEY"] = True
    elif fault == "nested":
        body["KIS_PAPER_APP_KEY"] = dict(secret="nested")
    encoded = json.dumps(body).encode()
    if fault == "duplicate":
        encoded = b'{"KIS_PAPER_APP_KEY":"one","KIS_PAPER_APP_KEY":"two"}'
    elif fault == "large":
        encoded = b" " * 8193
    elif fault == "nan":
        encoded = b'{"KIS_PAPER_APP_KEY":NaN}'
    monkeypatch.setattr(w.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(encoded)))
    monkeypatch.setattr(w, "run", lambda _: pytest.fail("invalid packet reached runtime"))
    assert w.main(["--execute"]) == 20
    output = capsys.readouterr().out
    assert json.loads(output)["status"] == "unavailable"
    assert "synthetic-secret" not in output and "never-route" not in output


def test_virtual_config_only():
    config = w.parse_packet(json.dumps(packet()).encode())
    assert config.base_url == w.readonly.KIS_PAPER_BASE_URL


def test_run_default_inert_even_with_injected_config(monkeypatch):
    monkeypatch.setattr(w, "RequestBudget", lambda: pytest.fail("inert budget construction"))
    assert w.run(None) == dict(status="inert", credential_reads=0, broker_calls=0)


@pytest.mark.parametrize("fault", ["extra", "reason", "kind", "limitation", "leg_count", "status"])
def test_worker_safe_payload_cannot_forward_private_native_values(fault):
    value = dict(status="pending", reason="exact_request_retained", leg_count=1)
    value["private" if fault == "extra" else fault] = "synthetic-secret"
    with pytest.raises(ValueError, match="^native_cycle_output_invalid$"):
        w._categorical(value)


@pytest.mark.parametrize(
    "status,reason",
    [
        (status, reason)
        for status, reasons in w.NATIVE_REASONS.items()
        for reason in sorted(reasons)
    ],
)
def test_every_native_categorical_reason_projects_to_closed_host_protocol(status, reason):
    native = cycle.CurrentStockCycleOutcome(status, reason, int(status in {"advanced", "pending"}))
    projected = w._categorical(native.safe_payload())
    projected.update(
        paper_only=True,
        unknown_effects_not_assumed_zero=True,
        calls=dict(token_posts=0, get_requests=0, buy_posts=0, sell_posts=0, cancel_posts=0),
        visits=1,
        http_start_gaps_seconds=[],
        pacing_basis="final_opener_delegate_boundary_not_socket_wire_measurement",
        observed_at_utc=NOW.isoformat(),
        fees="not_observed",
        settled_cash="not_observed",
        net_pnl="not_observed",
    )
    assert host.validate_result(projected) == projected


def test_runtime_contract_covers_exact_native_status_and_reason_enumerations():
    assert set(w.NATIVE_REASONS) == cycle._STATUSES - {"inert"}
    reasons = set().union(*w.NATIVE_REASONS.values())
    assert reasons == cycle._REASONS - {"execution_not_requested"}
    assert sum(map(len, w.NATIVE_REASONS.values())) == len(reasons)
    for status, reason in (
        ("no_intent", "cycle_never_reserved_retired"),
        ("unavailable", "cycle_retirement_unproven"),
        ("unavailable", "cycle_retired_request_restored"),
        ("unavailable", "cycle_owned_not_flat"),
        ("unavailable", "cycle_no_order_state_changed"),
        ("complete", "policy_no_order_complete"),
        ("no_intent", "cycle_target_quote_unavailable"),
        ("unavailable", "cycle_quote_timestamp_unavailable"),
        ("unavailable", "cycle_quote_timestamp_invalid"),
        ("unavailable", "cycle_quote_timestamp_stale"),
        ("unavailable", "cycle_quote_tick_invalid"),
        ("unavailable", "cycle_quote_bid_ask_invalid"),
        ("unavailable", "cycle_readonly_snapshot_unavailable"),
    ):
        assert {key for key, allowed in w.NATIVE_REASONS.items() if reason in allowed} == {status}


def test_native_fifth_session_inclusive_skips_weekend_and_holiday():
    entry, exit_session = w.fifth_session(date(2026, 10, 15))
    assert entry.open_ts == datetime(2026, 10, 15, 13, 30, tzinfo=UTC)
    assert exit_session.close_ts == datetime(2026, 10, 21, 20, tzinfo=UTC)
    entry, exit_session = w.fifth_session(date(2026, 11, 25))
    assert entry.open_ts.date() == date(2026, 11, 25)
    assert exit_session.close_ts.date() == date(2026, 12, 2)
    assert w.us_equity_2026_session(date(2026, 11, 26)) is None


def _encoded(value):
    def convert(v):
        if isinstance(v, datetime):
            return v.isoformat()
        if isinstance(v, Decimal):
            return str(v)
        if isinstance(v, Fraction):
            return [v.numerator, v.denominator]
        raise TypeError("synthetic_encoder")

    return json.dumps(value, default=convert, sort_keys=True, separators=(",", ":")).encode()


@pytest.fixture
def frozen_bundle(tmp_path, monkeypatch):
    artifact_root = tmp_path / "frozen_artifacts"
    root = artifact_root / w.PREPARATION
    root.mkdir(parents=True)
    keys = ["SYN" + chr(65 + slot // 26) + chr(65 + slot % 26) + "/NAS" for slot in range(512)]
    supported = list(range(62)) + list(range(128, 309))
    engine = dict(
        models=list(w.MODELS),
        frozen=dict(
            checkpoint_sha256={
                name: hashlib.sha256(name.encode()).hexdigest() for name in w.MODELS
            },
            scalers_sha256="1" * 64,
        ),
    )
    upstream = {
        w.ORIGINAL + "/engine-contract.json": engine,
        w.ORIGINAL + "/data-contract.json": dict(keys=keys, supported_slots=supported),
        w.ORIGINAL + "/review-output/final-current-linked-r2.json": dict(
            status="independent_current_score_math_bindings_checked", counts=dict(supported=243)
        ),
    }
    pins = {}
    for name, value in upstream.items():
        path = artifact_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = _encoded(value)
        path.write_bytes(raw)
        pins[name] = hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(w, "INPUT_PINS", pins)
    observation = dict(
        kind="consumer_byte_observation_not_original_publication",
        byte_observed_at=NOW - timedelta(minutes=2),
        completion_observed_bound=w.COMPLETION_BOUND,
        completion_receipt_ref="sha256:" + w.CLEANUP_PIN,
        score_ref="sha256:" + w.SCORE_PIN,
        input_ref="sha256:" + pins[w.ORIGINAL + "/data-contract.json"],
        original_score_publication_at=None,
        original_inference_completed_at=None,
        mtime_used=False,
    )
    observation_pin = hashlib.sha256(_encoded(observation)).hexdigest()
    metadata = w.FrozenScoreMetadata(
        score_ref="sha256:" + w.SCORE_PIN,
        input_ref=observation["input_ref"],
        independent_readback_ref="sha256:"
        + pins[w.ORIGINAL + "/review-output/final-current-linked-r2.json"],
        data_producer_ref="sha256:" + w.DATA_RECEIPT_PIN,
        score_producer_ref="sha256:" + observation_pin,
        feature_window_end=w.PREVIOUS,
        data_first_available_at=w.DATA_AVAILABLE,
        input_asof=w.INPUT_ASOF,
        inference_completed_at=w.COMPLETION_BOUND,
        score_first_available_at=observation["byte_observed_at"],
    )
    rows = tuple(
        SupportedScore(slot, keys[slot].split("/")[0], (Decimal(512 - slot),) * 5)
        for slot in supported
    )
    entry, _ = w.fifth_session(date(2026, 10, 15))
    targets = prepare_targets(
        FrozenScoreInput(rows, w.MODELS, metadata),
        intended_session=entry,
        latest_completed_close=w.PREVIOUS,
        official_calendar_ref="sha256:"
        + w.SOURCE_PINS["src/thericher_v2/data/us_equity_session.py"],
        decided_at=NOW - timedelta(minutes=1),
        valid_until=entry.close_ts,
    )
    source_pins = {
        "C:/Users/Public/Documents/thericher-v2/" + name: pin for name, pin in w.SOURCE_PINS.items()
    }
    weights = w.ORIGIN + "research/retained-relative-ranking-completion-20261015-v1/study/output/"
    bindings = dict(
        checked_current_source_pins=source_pins,
        checked_artifact_pins={w.ORIGIN + name: pin for name, pin in pins.items()},
        checked_weight_pins={
            weights + f"final-{name}-checkpoint.npz": pin
            for name, pin in engine["frozen"]["checkpoint_sha256"].items()
        }
        | {weights + "final-scalers.npz": engine["frozen"]["scalers_sha256"]},
    )
    consumer_pins = {
        name: hashlib.sha256(b"synthetic" + name.encode()).hexdigest()
        for name in ("consumer.py", "test_consumer.py")
    }
    docs = {
        "consumer.py": b"syntheticconsumer.py",
        "test_consumer.py": b"synthetictest_consumer.py",
        "score-observation.json": observation,
        "source-bindings.private.json": bindings,
        "prep-v3.json": dict(
            status="PREP_passed", tests=7, consumer_pins=consumer_pins, source_pins=source_pins
        ),
        "targets.private.json": dict(
            metadata=asdict(metadata),
            intended_session=asdict(entry),
            targets=[asdict(target) for target in targets],
            source_bindings_ref="sha256:" + hashlib.sha256(_encoded(bindings)).hexdigest(),
            units="desired_ORIGINAL_basis_fractions_not_cash_or_allocated_capital",
        ),
    }

    def publish():
        current = {
            name: hashlib.sha256(value if type(value) is bytes else _encoded(value)).hexdigest()
            for name, value in docs.items()
        }
        outcome = dict(
            status="actual_pure_target_preparation_complete",
            supported=243,
            experts=5,
            proposals=10,
            independent_rank_parity=True,
            untrusted_proposals=True,
            profit_qualified=False,
            deployment_claim=False,
            temporal_semantics=docs["score-observation.json"],
            **dict.fromkeys(
                (
                    "fits",
                    "GPU",
                    "broker_API",
                    "account_reads",
                    "credentials",
                    "orders",
                    "schedules",
                ),
                0,
            ),
        )
        for field, name in (
            ("target_sha256", "targets.private.json"),
            ("source_bindings_sha256", "source-bindings.private.json"),
            ("score_observation_sha256", "score-observation.json"),
            ("prep_sha256", "prep-v3.json"),
            ("source_sha256", "consumer.py"),
        ):
            outcome[field] = current[name]
        docs["outcome.json"] = outcome
        for name, value in docs.items():
            raw = value if type(value) is bytes else _encoded(value)
            (root / name).write_bytes(raw)
            current[name] = hashlib.sha256(raw).hexdigest()
        monkeypatch.setattr(w, "PRIVATE_PINS", current)

    publish()
    return SimpleNamespace(
        root=root, artifacts=artifact_root, docs=docs, publish=publish, upstream=upstream
    )


def _load(bundle, **changes):
    return w.load_targets(
        artifact_root=bundle.artifacts, repository_root=REPO, clock=lambda: NOW, **changes
    )


def test_strict_bundle_reconstructs_native_targets_and_refs(frozen_bundle):
    loaded = _load(frozen_bundle)
    assert type(loaded) is cycle.CurrentStockCycleInput
    assert len(loaded.targets) == 10
    assert all(type(t) is w.PreparedTarget for t in loaded.targets)
    assert sum(Fraction(t.proposal.target_exposure) for t in loaded.targets) == Fraction(1, 20)
    assert loaded.input_ref == "sha256:" + w.PRIVATE_PINS["targets.private.json"]
    assert loaded.policy_ref == "sha256:" + w.POLICY_PIN
    assert loaded.exit_session.close_ts.date() == date(2026, 10, 21)


def test_windows_origin_pin_maps_work_in_container_loader(frozen_bundle):
    bindings = frozen_bundle.docs["source-bindings.private.json"]
    for field in ("checked_current_source_pins", "checked_artifact_pins", "checked_weight_pins"):
        bindings[field] = {key.replace("/", "\\"): pin for key, pin in bindings[field].items()}
    frozen_bundle.docs["prep-v3.json"]["source_pins"] = bindings["checked_current_source_pins"]
    target = frozen_bundle.docs["targets.private.json"]
    target["source_bindings_ref"] = "sha256:" + hashlib.sha256(_encoded(bindings)).hexdigest()
    frozen_bundle.publish()
    assert len(_load(frozen_bundle).targets) == 10


def test_windows_alias_collision_rejected_not_silently_rebound():
    with pytest.raises(ValueError, match="current_targets_unavailable"):
        w._pin_map({"D:/fixed/source": "a" * 64, "D:\\fixed\\source": "a" * 64})


@pytest.mark.parametrize("name", list(w.INPUT_PINS))
def test_each_upstream_pin_checked(frozen_bundle, name):
    (frozen_bundle.artifacts / name).write_bytes(b"tampered-upstream")
    with pytest.raises(ValueError, match="^current_targets_unavailable$"):
        _load(frozen_bundle)


@pytest.mark.parametrize("fault", ["expert", "support", "readback"])
def test_linked_expert_and_243_support_contracts_reject(frozen_bundle, fault):
    if fault == "expert":
        name = w.ORIGINAL + "/engine-contract.json"
        frozen_bundle.upstream[name]["models"][0] = "other_model"
    elif fault == "support":
        name = w.ORIGINAL + "/data-contract.json"
        frozen_bundle.upstream[name]["supported_slots"].pop()
    else:
        name = w.ORIGINAL + "/review-output/final-current-linked-r2.json"
        frozen_bundle.upstream[name]["counts"]["supported"] = 242
    raw = _encoded(frozen_bundle.upstream[name])
    (frozen_bundle.artifacts / name).write_bytes(raw)
    w.INPUT_PINS[name] = hashlib.sha256(raw).hexdigest()
    bindings = frozen_bundle.docs["source-bindings.private.json"]
    bindings["checked_artifact_pins"][w.ORIGIN + name] = w.INPUT_PINS[name]
    frozen_bundle.docs["targets.private.json"]["source_bindings_ref"] = (
        "sha256:" + hashlib.sha256(_encoded(bindings)).hexdigest()
    )
    frozen_bundle.publish()
    with pytest.raises(ValueError, match="^current_targets_unavailable$"):
        _load(frozen_bundle)


@pytest.mark.parametrize("name", list(w.PRIVATE_PINS))
def test_each_private_chain_tamper_rejected_before_client(frozen_bundle, name, monkeypatch):
    (frozen_bundle.root / name).write_bytes(b"tampered-synthetic-private-value")
    monkeypatch.setattr(
        w, "client_factory", lambda *a: pytest.fail("invalid target reached client")
    )
    with pytest.raises(ValueError, match="^current_targets_unavailable$") as caught:
        _load(frozen_bundle)
    assert "tampered-synthetic" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize(
    "fault",
    [
        "nine",
        "eleven",
        "duplicate",
        "symbol",
        "fraction",
        "future",
        "publication",
        "expiry",
        "rank",
        "policy",
    ],
)
def test_relinked_semantic_faults_reject(frozen_bundle, fault):
    doc = frozen_bundle.docs["targets.private.json"]
    if fault == "nine":
        doc["targets"].pop()
    elif fault == "eleven":
        doc["targets"].append(doc["targets"][0])
    elif fault == "duplicate":
        doc["targets"][-1] = doc["targets"][0]
    elif fault == "symbol":
        doc["targets"][0]["proposal"]["symbol"] = "WRONG"
    elif fault == "fraction":
        doc["targets"][0]["proposal"]["target_exposure"] = ".05"
    elif fault == "future":
        doc["metadata"]["score_first_available_at"] = (NOW + timedelta(minutes=1)).isoformat()
    elif fault == "publication":
        frozen_bundle.docs["score-observation.json"]["original_score_publication_at"] = (
            NOW.isoformat()
        )
    elif fault == "expiry":
        doc["targets"][0]["proposal"]["valid_until"] = (NOW + timedelta(days=365)).isoformat()
    elif fault == "rank":
        doc["targets"] = list(reversed(doc["targets"]))
    else:
        frozen_bundle.docs["source-bindings.private.json"]["checked_current_source_pins"] = {}
    frozen_bundle.publish()
    with pytest.raises(ValueError, match="^current_targets_unavailable$"):
        _load(frozen_bundle)


def test_stale_new_entry_rejected_no_perpetual_snapshot(frozen_bundle):
    with pytest.raises(ValueError, match="^current_targets_unavailable$"):
        w.load_targets(
            artifact_root=frozen_bundle.artifacts,
            repository_root=REPO,
            clock=lambda: datetime(2026, 10, 15, 20, tzinfo=UTC),
        )


class Response:
    status = 200
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self):
        return b"{}"


@pytest.fixture
def wire(tmp_path):
    ticks = [0.0]

    def sleep(n):
        ticks[0] += n

    limits = w.RequestBudget(
        control_root=tmp_path / "control",
        clock=lambda: NOW + timedelta(seconds=ticks[0]),
        monotonic=lambda: ticks[0],
        sleeper=sleep,
    )
    seen = []

    class Opener:
        def open(self, request, **kwargs):
            assert kwargs["timeout"] == 8
            seen.append((ticks[0], request))
            return Response()

    transport = w.OwnedTransport(instrument=INSTRUMENT, limits=limits)
    transport._opener = Opener()
    return SimpleNamespace(
        ticks=ticks, limits=limits, transport=transport, seen=seen, opener=transport._opener
    )


def test_native_wire_pacing_and_shared_call_limit(wire):
    for _ in range(128):
        wire.transport.request(_quote_request())
    assert len(wire.seen) == wire.limits.calls["get_requests"] == 128
    assert all(b[0] - a[0] >= 1.25 for a, b in zip(wire.seen, wire.seen[1:], strict=False))
    with pytest.raises(w.canary.KisPaperCanaryError, match="request_budget_exhausted"):
        wire.transport.request(_quote_request())
    assert len(wire.seen) == 128


@pytest.mark.parametrize("kind", ["submit", "cancel", "token"])
def test_each_side_effect_cap_shared_across_instrument_transports(wire, kind):
    request = _generic_request(kind)
    wire.transport.request(request)
    other = w.OwnedTransport(instrument=INSTRUMENT, limits=wire.limits)
    other._opener = wire.opener
    with pytest.raises(w.canary.KisPaperCanaryError, match="request_budget_exhausted"):
        other.request(request)
    assert len(wire.seen) == 1


def test_buy_and_sell_share_one_side_effect_cap(wire):
    buy = _generic_request("submit")
    sell = replace(
        buy,
        headers=dict(buy.headers)
        | {
            "tr_id": w.canary.KIS_PAPER_US_SELL_LIMIT_ORDER_TR_ID,
        },
        json_body=dict(buy.json_body) | {"SLL_TYPE": "00"},
    )
    wire.transport.request(buy)
    with pytest.raises(w.canary.KisPaperCanaryError, match="request_budget_exhausted"):
        wire.transport.request(sell)
    assert wire.limits.calls["buy_posts"] == 1 and wire.limits.calls["sell_posts"] == 0


def test_wrong_stock_post_rejected_before_budget_or_wire(wire):
    request = _generic_request("submit")
    request = replace(request, json_body=dict(request.json_body) | {"PDNO": "OTHER"})
    with pytest.raises(w.canary.KisPaperCanaryError, match="stock_instrument_mismatch"):
        wire.transport.request(request)
    assert sum(wire.limits.calls.values()) == 0 and not wire.seen


@pytest.mark.parametrize("fault", ["live", "symbol", "venue"])
def test_exact_stock_validator_rejects_before_gate_or_wire(wire, fault):
    request = _quote_request()
    if fault == "live":
        request = replace(
            request, url=request.url.replace("openapivts", "openapi").replace("29443", "9443")
        )
    else:
        request = replace(
            request,
            query=dict(request.query)
            | ({"SYMB": "OTHER"} if fault == "symbol" else {"EXCD": "NYS"}),
        )
    with pytest.raises(w.canary.KisPaperCanaryError):
        wire.transport.request(request)
    assert not wire.seen and sum(wire.limits.calls.values()) == 0


def test_failed_auth_start_charged_and_not_retried(wire):
    class Broken:
        def open(self, *_args, **_kwargs):
            raise OSError("synthetic-secret")

    wire.transport._opener = Broken()
    with pytest.raises(w.canary.KisPaperCanaryError, match="transport_failure"):
        wire.transport.request(_generic_request("token"))
    assert wire.limits.calls["token_posts"] == 1
    with pytest.raises(w.canary.KisPaperCanaryError, match="request_budget_exhausted"):
        wire.transport.request(_generic_request("token"))


def test_deadline_rechecked_after_pacing_and_callback(wire):
    wire.limits.deadline = 8.5
    wire.transport.request(_quote_request())
    with pytest.raises(w.canary.KisPaperCanaryError, match="request_budget_exhausted"):
        wire.transport.request(_quote_request())
    assert len(wire.seen) == 1
    wire.limits.deadline = 100
    with pytest.raises(w.canary.KisPaperCanaryError, match="request_budget_exhausted"):
        wire.transport._request(
            _quote_request(), before_wire=lambda: wire.ticks.__setitem__(0, 100)
        )
    assert len(wire.seen) == 1


def test_shared_rate_limit_cooldown_is_bounded_not_foreground_wait(wire):
    class LimitedResponse(Response):
        status = 429

    class LimitedOpener:
        def open(self, *_args, **_kwargs):
            return LimitedResponse()

    wire.transport._opener = LimitedOpener()
    assert wire.transport.request(_quote_request()).status_code == 429
    with pytest.raises(w.canary.KisPaperCanaryError, match="request_budget_exhausted"):
        wire.transport.request(_quote_request())
    assert wire.limits.calls["get_requests"] == 1


def test_auth_timing_gate_preserves_not_due_start(wire):
    assert wire.limits.token.claim_token_request_start() is True
    with pytest.raises(w.canary.KisPaperCanaryError, match="token_request_not_due"):
        wire.transport.request(_generic_request("token"))
    assert wire.limits.calls["token_posts"] == 0 and not wire.seen


def test_shared_client_factory_issues_one_token_for_all_stocks(wire, monkeypatch):
    issued = []
    monkeypatch.setattr(
        w.KisPaperStockCanaryClient,
        "_issue_access_token",
        lambda self: issued.append(self.instrument) or "synthetic-bearer",
    )
    factory = w.client_factory(w.parse_packet(json.dumps(packet()).encode()), wire.limits)
    first = factory(INSTRUMENT)
    second = factory(KisPaperStockInstrument("OTHER", "ref:" + "b" * 64))
    assert factory(INSTRUMENT) is first
    assert len(issued) == 1 and first._access_token == second._access_token == "synthetic-bearer"
    assert first._transport.limits is second._transport.limits is wire.limits


@pytest.fixture
def native_worker(frozen_bundle, h, monkeypatch):
    """Real coordinator/plans/custody; only provider operations are synthetic."""
    paths = {
        key: h["call"][key]
        for key in (
            "state_root",
            "repository_root",
            "artifact_root",
            "runtime_projection_path",
            "paper_account_snapshot_path",
            "emergency_state_path",
            "execution_control_path",
        )
    }
    paths["artifact_root"] = frozen_bundle.artifacts
    for name in w.SOURCE_PINS:
        if name.startswith("src/"):
            target = paths["repository_root"] / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((REPO / name).read_bytes())
    monkeypatch.setattr(w, "native_paths", lambda: paths)
    monkeypatch.setattr(w, "CONTROL", frozen_bundle.artifacts.parent / "timing")
    h["now"] = NOW
    issued = []

    class BoundSyntheticClient(NativeSyntheticStockClient):
        def __init__(self, *, config, transport, instrument):
            assert config == CONFIG
            super().__init__(h, instrument)
            self._transport = transport

        def _issue_access_token(self):
            issued.append(self.instrument)
            return "synthetic-bearer"

    monkeypatch.setattr(w, "KisPaperStockCanaryClient", BoundSyntheticClient)

    def visit():
        result = w.run(CONFIG, execute=True, clock=lambda: h["now"])
        assert host.validate_result(result) == result
        assert result["paper_only"] is True
        assert "synthetic-bearer" not in json.dumps(result)
        return result

    return SimpleNamespace(h=h, visit=visit, issued=issued, paths=paths, bundle=frozen_bundle)


def test_native_coordinator_full_worker_ten_entries_and_fifth_session_owned_exits(
    native_worker, monkeypatch
):
    h = native_worker.h
    for number in range(10):
        result = native_worker.visit()
        assert (result["status"], result["reason"], result["leg_count"]) == (
            "advanced",
            "native_leg_closed",
            1,
        )
        assert len(h["submits"]) == number + 1
    assert native_worker.visit()["status"] == "hold"
    h["now"] = datetime(2026, 10, 21, 19, 56, tzinfo=UTC)
    for number in range(10):
        result = native_worker.visit()
        assert (result["status"], result["reason"], result["leg_count"]) == (
            "advanced",
            "native_leg_closed",
            1,
        )
        assert len(h["submits"]) == 11 + number
    result = native_worker.visit()
    assert (result["status"], result["reason"]) == ("complete", "policy_owned_flat")
    assert all(intent.side == "buy" for intent in h["submits"][:10])
    assert all(intent.side == "sell" for intent in h["submits"][10:])
    assert all(intent.quantity == Decimal(5) for intent in h["submits"])
    binding = w.budget._load_binding(h["root"])
    for key in ("basis_ref", "allocated_usd", "orders", "qqq", "portfolio"):
        assert binding[key] == h["initial"][key]
    assert len(native_worker.issued) == 20
    monkeypatch.setattr(
        w, "load_targets", lambda **k: pytest.fail("completed cycle loaded expired targets")
    )
    h["now"] = datetime(2026, 10, 22, 14, tzinfo=UTC)
    result = native_worker.visit()
    assert (result["status"], result["reason"], result["leg_count"]) == (
        "complete",
        "already_completed",
        0,
    )
    assert len(native_worker.issued) == 20 and len(h["submits"]) == 20
    assert sum(result["calls"].values()) == 0


def test_explicit_coordinator_ABI_accepts_compiled_input_and_policy_hints(monkeypatch):
    seen = []

    def native(
        *,
        state_root,
        repository_root,
        artifact_root,
        runtime_projection_path,
        paper_account_snapshot_path,
        emergency_state_path,
        execution_control_path,
        expected_account_ref,
        expected_input_ref,
        expected_policy_ref,
        target_loader,
        client_factory,
        clock,
        execute=False,
    ):
        assert execute is True
        assert expected_account_ref == w.budget._digest(
            [CONFIG.base_url, CONFIG.account_number, CONFIG.account_product_code]
        )
        assert expected_input_ref == (
            "sha256:597c1e80577b9724da729a0eae45214b45bf03a49f7713ffaaec2594cac36b0b"
        )
        assert expected_policy_ref == (
            "sha256:9fe47f72500a02a535d74e1a6607314f237310a70f89a5e2a22bccae6ed672f0"
        )
        assert callable(target_loader) and callable(client_factory) and clock() == NOW
        seen.append(True)
        return cycle.CurrentStockCycleOutcome("complete", "already_completed", 0)

    monkeypatch.setattr(cycle, "run_kis_paper_current_stock_cycle", native)
    monkeypatch.setattr(w, "load_targets", lambda **k: pytest.fail("ABI called target loader"))
    result = w.run(CONFIG, execute=True, clock=lambda: NOW)
    assert result["status"] == "complete" and result["reason"] == "already_completed"
    assert sum(result["calls"].values()) == 0 and seen == [True]


def test_native_unknown_recovery_precedes_expired_loader_without_resubmit(
    native_worker, monkeypatch
):
    h = native_worker.h
    h["unknown"] = True
    first = native_worker.visit()
    assert (first["status"], first["reason"]) == ("pending", "exact_request_retained")
    h["now"] += timedelta(days=1)
    monkeypatch.setattr(w, "load_targets", lambda **k: pytest.fail("recovery loaded new targets"))
    second = native_worker.visit()
    assert second["status"] == "pending" and second["unknown_effects_not_assumed_zero"] is True
    assert len(h["submits"]) == 1


def test_real_native_never_reserved_retirement_preserves_categorical_projection(
    native_worker, monkeypatch
):
    def crash_before_reservation(**_kwargs):
        raise RuntimeError("synthetic_before_reservation")

    with monkeypatch.context() as patch:
        patch.setattr(cycle.entries, "reserve_kis_paper_stock_plan", crash_before_reservation)
        assert native_worker.visit()["status"] == "unavailable"
    h = native_worker.h
    before = (h["root"] / w.budget.BUDGET_FILE).read_bytes()
    issued = len(native_worker.issued)
    h["now"] += timedelta(minutes=6)
    monkeypatch.setattr(w, "load_targets", lambda **k: pytest.fail("retirement loaded targets"))
    result = native_worker.visit()
    assert (result["status"], result["reason"], result["leg_count"]) == (
        "no_intent",
        "cycle_never_reserved_retired",
        1,
    )
    assert sum(result["calls"].values()) == 0
    assert len(native_worker.issued) == issued and h["submits"] == []
    record = w.budget._read_json(h["root"] / cycle.POINTER)
    assert record["pending"] is None and len(record["retired"]) == 1
    assert (h["root"] / w.budget.BUDGET_FILE).read_bytes() == before


def test_native_risk_no_intent_and_safe_projection_not_a_fill(native_worker):
    native_worker.h["funds"] = Decimal(0)
    result = native_worker.visit()
    assert (result["status"], result["reason"], result["leg_count"]) == (
        "no_intent",
        "native_risk_no_intent",
        0,
    )
    assert native_worker.h["submits"] == []


def test_native_unavailable_quote_skips_only_original_unreserved_buy(native_worker, monkeypatch):
    h = native_worker.h
    loaded = _load(native_worker.bundle)
    original_targets = loaded.targets
    first_symbol = original_targets[0].proposal.symbol
    before = (h["root"] / w.budget.BUDGET_FILE).read_bytes()
    original_preview = NativeSyntheticStockClient.stock_preview_snapshot
    previewed = []

    def preview(self, **kwargs):
        previewed.append(self.instrument.symbol)
        if self.instrument.symbol == first_symbol:
            raise w.readonly.KisPaperReadOnlyError("quote_timestamp_unavailable")
        return original_preview(self, **kwargs)

    monkeypatch.setattr(NativeSyntheticStockClient, "stock_preview_snapshot", preview)
    result = native_worker.visit()
    assert (result["status"], result["reason"], result["leg_count"]) == (
        "no_intent",
        "cycle_target_quote_unavailable",
        0,
    )
    assert h["submits"] == [] and previewed == [first_symbol]
    assert (h["root"] / w.budget.BUDGET_FILE).read_bytes() == before
    record = w.budget._read_json(h["root"] / cycle.POINTER)
    assert record["pending"] is None and record["owners"] == {}
    assert record["active"]["entries_done"] == [first_symbol]
    assert cycle._unpack(record["active"]["targets"]) == original_targets
    assert record["active"]["input_ref"] == loaded.input_ref
    assert record["policy_ref"] == loaded.policy_ref
    assert cycle._unpack(record["active"]["entry_session"]) == loaded.entry_session
    assert cycle._unpack(record["active"]["exit_session"]) == loaded.exit_session

    for target in original_targets[1:]:
        result = native_worker.visit()
        assert (result["status"], result["reason"], result["leg_count"]) == (
            "advanced",
            "native_leg_closed",
            1,
        )
        assert h["submits"][-1].symbol == target.proposal.symbol
    assert [intent.symbol for intent in h["submits"]] == [
        target.proposal.symbol for target in original_targets[1:]
    ]
    assert previewed.count(first_symbol) == 1
    record = w.budget._read_json(h["root"] / cycle.POINTER)
    assert cycle._unpack(record["active"]["targets"]) == original_targets
    assert record["active"]["entries_done"] == [
        target.proposal.symbol for target in original_targets
    ]
    result = native_worker.visit()
    assert (result["status"], result["reason"]) == ("hold", "await_declared_exit")


@pytest.mark.parametrize(
    "code,reason",
    [
        ("quote_timestamp_invalid", "cycle_quote_timestamp_invalid"),
        ("quote_timestamp_stale", "cycle_quote_timestamp_stale"),
        ("quote_tick_invalid", "cycle_quote_tick_invalid"),
        ("quote_bid_ask_invalid", "cycle_quote_bid_ask_invalid"),
        ("balance_response_incomplete", "cycle_readonly_snapshot_unavailable"),
    ],
)
def test_native_quote_faults_keep_unavailable_without_skipping(
    native_worker, monkeypatch, code, reason
):
    h = native_worker.h
    before = (h["root"] / w.budget.BUDGET_FILE).read_bytes()

    def preview(self, **kwargs):
        raise w.readonly.KisPaperReadOnlyError(code)

    monkeypatch.setattr(NativeSyntheticStockClient, "stock_preview_snapshot", preview)
    result = native_worker.visit()
    assert (result["status"], result["reason"], result["leg_count"]) == ("unavailable", reason, 0)
    record = w.budget._read_json(h["root"] / cycle.POINTER)
    assert record["active"]["entries_done"] == []
    assert record["pending"] is None and record["owners"] == {}
    assert h["submits"] == []
    assert (h["root"] / w.budget.BUDGET_FILE).read_bytes() == before


@pytest.mark.parametrize("lane", ["pending_buy", "owned_sell"])
def test_native_unavailable_timestamp_never_skips_pending_or_sell(native_worker, monkeypatch, lane):
    h = native_worker.h
    h["partial"] = lane == "pending_buy"
    assert native_worker.visit()["status"] == ("pending" if lane == "pending_buy" else "advanced")
    pointer = h["root"] / cycle.POINTER
    before = w.budget._read_json(pointer)
    if lane == "owned_sell":
        h["now"] = datetime(2026, 10, 21, 14, tzinfo=UTC)

    def unavailable(self, **kwargs):
        raise w.readonly.KisPaperReadOnlyError("quote_timestamp_unavailable")

    monkeypatch.setattr(NativeSyntheticStockClient, "stock_preview_snapshot", unavailable)
    monkeypatch.setattr(NativeSyntheticStockClient, "stock_exit_snapshot", unavailable)
    result = native_worker.visit()
    assert (result["status"], result["reason"], result["leg_count"]) == (
        "unavailable",
        "cycle_quote_timestamp_unavailable",
        int(lane == "pending_buy"),
    )
    after = w.budget._read_json(pointer)
    assert after["active"]["entries_done"] == before["active"]["entries_done"]
    assert after["owners"] == before["owners"]
    if lane == "pending_buy":
        assert after["pending"]["arguments"] == before["pending"]["arguments"]
        assert after["pending"]["plan_ref"] == before["pending"]["plan_ref"]
    else:
        assert after["pending"] is None
    assert len(h["submits"]) == 1 and h["submits"][0].side == "buy"


def test_loader_tamper_reaches_real_coordinator_without_constructing_client(native_worker):
    (native_worker.bundle.root / "targets.private.json").write_bytes(b"synthetic-tamper")
    result = native_worker.visit()
    assert result["status"] == "unavailable" and result["reason"] == "native_recovery_required"
    assert native_worker.issued == [] and native_worker.h["submits"] == []


def test_cli_fixed_projection_exits_zero_for_native_advanced_and_hold(monkeypatch, capsys):
    for status, reason, leg_count in (
        ("advanced", "native_leg_closed", 1),
        ("hold", "await_declared_exit", 0),
    ):
        result = w._categorical(
            cycle.CurrentStockCycleOutcome(status, reason, leg_count).safe_payload()
        )
        monkeypatch.setattr(
            w.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(json.dumps(packet()).encode()))
        )
        monkeypatch.setattr(w, "run", lambda *a, result=result, **k: result)
        assert w.main(["--execute"]) == 0
        assert json.loads(capsys.readouterr().out) == result


def test_account_session_default_is_inert_before_config_state_or_callbacks(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("inert_account_session_touched_runtime")

    monkeypatch.setattr(w, "RequestBudget", forbidden)
    monkeypatch.setattr(w, "client_factory", forbidden)
    monkeypatch.setattr(w, "native_paths", forbidden)
    assert w.run_account_session(owner_ready=forbidden, source_ready=forbidden) == dict(
        status="inert", credential_reads=0, broker_calls=0
    )


def test_account_session_rejects_nonvirtual_config_before_native_state(monkeypatch):
    monkeypatch.setattr(w, "native_paths", lambda: pytest.fail("untrusted_config_reached_state"))
    config = replace(CONFIG)
    object.__setattr__(config, "base_url", "https://openapi.koreainvestment.com:9443")
    with pytest.raises(w.readonly.KisPaperReadOnlyError):
        w.run_account_session(config, execute=True)


@pytest.mark.parametrize("execute", [None, 0, 1, "true"])
def test_account_session_requires_explicit_boolean_execution(execute):
    with pytest.raises(ValueError, match="account_session_configuration_invalid"):
        w.run_account_session(CONFIG, execute=execute)
