"""Native JSON-only current20 Paper worker; default never reads stdin or state."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
ENTRY_STARTED = time.monotonic()
ARTIFACT = APP / "model_artifacts"
CONTROL = APP / "market_data/us_equities/kis_paper_private/collection-control-v1"
RUNTIME_RELATIVE = "execution/current20-ensemble-paper-runtime-20261018-v1"
KIND = "current20-paper-worker-v1"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _helpers():
    sys.path.insert(0, str(APP / "src"))
    return _load(
        "current20_native_stock_worker_helpers",
        APP / "scripts/run_kis_paper_current_stock_cycle_worker.py",
    )


def _host():
    module = _load(
        "current20_pinned_input_reader", APP / "scripts/run_current20_paper_candidate.py"
    )
    module.ARTIFACT = ARTIFACT
    return module


def _api():
    sys.path.insert(0, str(APP / "src"))
    from thericher_v2.research import current20_paper_candidate

    return current20_paper_candidate


def _no_model_runtime():
    if any(name in sys.modules for name in ("numpy", "torch", "sklearn")):
        raise ValueError("native_JSON_runtime_only")


def load_input(path, pin, source_manifest, source_manifest_ref):
    host = _host()
    host.read_source_manifest(source_manifest, source_manifest_ref)
    document, value = host.read_input_manifest(path, pin)
    # Explicitly distinct: bytes authorize the read; semantic input/policy refs
    # bind the native pointer, recovery and targets. Neither is derived anew.
    if (value.input_ref, value.policy_ref) != (document["input_ref"], document["policy_ref"]):
        raise ValueError("native_semantic_reference_mismatch")
    return document, value


class OwnerAdmission:
    def __init__(self, source, sink, *, monotonic=time.monotonic):
        self.source, self.sink, self.monotonic = source, sink, monotonic
        self.sequence = 0

    def __call__(self):
        self.sequence += 1
        if self.sequence > 128:
            raise ValueError("owner_admission_count_exhausted")
        requested = self.monotonic()
        self.sink.write(
            json.dumps(dict(kind="current20-owner-request-v1", sequence=self.sequence)) + "\n"
        )
        self.sink.flush()
        raw = self.source.readline(4097)
        if not raw or len(raw) > 4096 or not raw.endswith(b"\n"):
            raise ValueError("owner_admission_unknown")
        value = _host()._json(raw)
        if (
            type(value) is not dict
            or set(value) != {"kind", "sequence", "ready"}
            or value["kind"] != "current20-owner-answer-v1"
            or type(value["sequence"]) is not int
            or value["sequence"] != self.sequence
            or type(value["ready"]) is not bool
            or value["ready"] is not True
            or self.monotonic() - requested > 13
        ):
            raise ValueError("owner_admission_unavailable")


def request_budget(
    *,
    owner_ready,
    control_root=CONTROL,
    clock=lambda: datetime.now(UTC),
    monotonic=time.monotonic,
    sleeper=time.sleep,
    persist=None,
    started=None,
    bindings_ready=None,
):
    native = _helpers()

    class Current20RequestBudget(native.RequestBudget):
        """One wake budget; inherited native gates/default legacy class unchanged."""

        def __init__(self):
            super().__init__(
                control_root=control_root, clock=clock, monotonic=monotonic, sleeper=sleeper
            )
            self.deadline = (monotonic() if started is None else started) + 150

        def _check(self, key):
            if (
                key not in self.calls
                or self.monotonic() + 8 >= self.deadline
                or sum(self.calls.values()) >= 128
                or key == "token_posts"
                and self.calls[key] >= 1
                or key in {"buy_posts", "sell_posts"}
                and self.calls["buy_posts"] + self.calls["sell_posts"] >= 5
                or key == "cancel_posts"
                and self.calls[key] >= 5
            ):
                raise native.canary.KisPaperCanaryError("request_budget_exhausted")

        def start(self, request, before_wire):
            def admitted():
                if bindings_ready is not None:
                    bindings_ready()
                if request.method == "POST":
                    owner_ready()
                if before_wire is not None:
                    before_wire()

            super().start(request, admitted)
            if persist is not None:
                persist(dict(self.calls))

    return Current20RequestBudget()


def _safe_outcome(outcome):
    from thericher_v2.execution import kis_paper_current_stock_cycle as cycle

    value = outcome.safe_payload()
    if (
        type(value) is not dict
        or set(value) != {"status", "reason", "leg_count"}
        or value["status"] not in cycle._STATUSES
        or value["reason"] not in cycle._REASONS
        or type(value["leg_count"]) is not int
        or value["leg_count"] not in (0, 1)
    ):
        raise ValueError("native_output_invalid")
    return value


def run(
    config=None,
    *,
    execute=False,
    input_manifest=None,
    input_manifest_ref="",
    source_manifest=None,
    source_manifest_ref="",
    owner_ready=None,
    clock=lambda: datetime.now(UTC),
    monotonic=time.monotonic,
    sleeper=time.sleep,
    started=None,
):
    if not execute:
        return dict(status="inert", credential_reads=0, broker_calls=0)
    started = monotonic() if started is None else started
    native, api = _helpers(), _api()
    outcomes = []
    limits = None
    try:
        if not callable(owner_ready):
            raise ValueError("fresh_owner_callback_required")
        document, value = load_input(
            input_manifest, input_manifest_ref, source_manifest, source_manifest_ref
        )
        host = _host()
        manifest_path = Path(input_manifest)
        source_path = Path(source_manifest)

        def admission():
            # Immutable image source is read-only; only public artifact refs need
            # reattesting here, after pacing and before the fresh host callback.
            host._read(manifest_path, input_manifest_ref)
            host._read(manifest_path.parent / "proposal.json", document["payload_ref"])
            host._read(source_path, source_manifest_ref, 1024 * 1024)
            for key in ("contract", "data_binding"):
                item = document[key]
                host._read(ARTIFACT / item["path"], item["ref"], 131072)

        limits = request_budget(
            owner_ready=owner_ready,
            bindings_ready=admission,
            control_root=CONTROL,
            clock=clock,
            monotonic=monotonic,
            sleeper=sleeper,
            started=started,
        )
        paths = native.native_paths()
        results = api.run_current20_paper_visit(
            **paths,
            expected_account_ref=native.budget._digest(
                [config.base_url, config.account_number, config.account_product_code]
            ),
            expected_input_ref=value.input_ref,
            expected_policy_ref=value.policy_ref,
            target_loader=lambda: value,
            client_factory=native.client_factory(config, limits),
            clock=clock,
            execute=True,
        )
        outcomes = [_safe_outcome(result) for result in results]
        if not 1 <= len(outcomes) <= 6:
            raise ValueError("native_visit_count_invalid")
    except Exception:
        outcomes.append(dict(status="unavailable", reason="native_recovery_required", leg_count=0))
    calls = dict(token_posts=0, get_requests=0, buy_posts=0, sell_posts=0, cancel_posts=0)
    starts = []
    if limits is not None:
        calls, starts = dict(limits.calls), list(limits.starts)
    return dict(
        kind=KIND,
        status=outcomes[-1]["status"],
        reason=outcomes[-1]["reason"],
        leg_count=sum(v["leg_count"] for v in outcomes),
        outcomes=outcomes,
        calls=calls,
        paper_only=True,
        unknown_effects_not_assumed_zero=True,
        http_start_gaps_seconds=[round(b - a, 6) for a, b in zip(starts, starts[1:], strict=False)],
        pacing_basis="final_opener_delegate_boundary_not_socket_wire_measurement",
        observed_at_utc=clock().isoformat(),
        fees="not_observed",
        settled_cash="not_observed",
        net_pnl="not_observed",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--input-manifest", type=Path)
    parser.add_argument("--input-manifest-ref", default="")
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--source-manifest-ref", default="")
    parser.add_argument("--owner-admission-stdio", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        print('{"status":"inert","credential_reads":0,"broker_calls":0}')
        return 0
    entered = False
    try:
        if not args.owner_admission_stdio:
            raise ValueError("fresh_owner_callback_required")
        load_input(
            args.input_manifest,
            args.input_manifest_ref,
            args.source_manifest,
            args.source_manifest_ref,
        )
        _no_model_runtime()
        native = _helpers()
        packet = sys.stdin.buffer.readline(8194)
        if not packet.endswith(b"\n") or len(packet) > 8193:
            raise ValueError("Paper_packet_invalid")
        config = native.parse_packet(packet)
        entered = True
        result = run(
            config,
            execute=True,
            input_manifest=args.input_manifest,
            input_manifest_ref=args.input_manifest_ref,
            source_manifest=args.source_manifest,
            source_manifest_ref=args.source_manifest_ref,
            owner_ready=OwnerAdmission(sys.stdin.buffer, sys.stdout),
            started=ENTRY_STARTED,
        )
    except Exception:
        if entered:
            result = dict(
                kind=KIND,
                status="unavailable",
                reason="native_recovery_required",
                paper_only=True,
                unknown_effects_not_assumed_zero=True,
                request_counts="unknown",
            )
            print(json.dumps(result, sort_keys=True))
            return 20
        result = dict(
            kind=KIND,
            status="unavailable",
            reason="native_recovery_required",
            leg_count=0,
            outcomes=[dict(status="unavailable", reason="native_recovery_required", leg_count=0)],
            calls=dict(token_posts=0, get_requests=0, buy_posts=0, sell_posts=0, cancel_posts=0),
            paper_only=True,
            unknown_effects_not_assumed_zero=True,
            http_start_gaps_seconds=[],
            pacing_basis="final_opener_delegate_boundary_not_socket_wire_measurement",
            observed_at_utc=datetime.now(UTC).isoformat(),
            fees="not_observed",
            settled_cash="not_observed",
            net_pnl="not_observed",
        )
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 20 if result["status"] == "unavailable" else 0


if __name__ == "__main__":
    raise SystemExit(main())
