"""Bounded canonical Data-to-native Paper worker. Default execution is inert."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from thericher_v2.data.kis_paper_etf_daily_context import (
    collect_daily_contexts,
    read_daily_context,
)
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_canary as canary
from thericher_v2.execution import kis_readonly as readonly
from thericher_v2.execution.kis_market_data import KisPaperMarketDataConfig
from thericher_v2.execution.kis_market_data_rate_gate import (
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)

APP = Path("/app")
MARKET = APP / "market_data/us_equities/kis_paper_private/etf-daily-context-v1"
CONTROL = MARKET.parent / "collection-control-v1"
ARTIFACT = APP / "model_artifacts"
MAX_NATIVE_VISITS = 12
ENV_KEYS = frozenset(
    {
        "KIS_PAPER_APP_KEY",
        "KIS_PAPER_APP_SECRET",
        "KIS_PAPER_ACCOUNT_NO",
        "KIS_PAPER_ACCOUNT_PRODUCT_CODE",
        "THERICHER_MODE",
    }
)


class OwnedTransport(canary.UrllibKisPaperCanaryTransport):
    """One virtual-host client, final request-start guards and bounded side effects."""

    def __init__(
        self,
        *,
        control_root: Path,
        clock=lambda: datetime.now(UTC),
        monotonic=time.monotonic,
        sleeper=time.sleep,
    ):
        super().__init__(timeout_seconds=8, pacer=readonly.KisPaperRequestPacer())
        self.clock, self.monotonic, self.sleeper = clock, monotonic, sleeper
        self.deadline = monotonic() + 280
        self.calls = dict(token_posts=0, get_requests=0, buy_posts=0, sell_posts=0, cancel_posts=0)
        self.token = KisPaperMarketDataTokenStartGate(
            control_root=control_root, minimum_request_interval_seconds=60, clock=clock
        )
        self.rate = KisPaperMarketDataRateGate(
            control_root=control_root,
            minimum_request_interval_seconds=1.25,
            clock=clock,
            sleeper=self._sleep,
        )

    def _sleep(self, duration):
        if duration > 2 or self.monotonic() + duration + 8 >= self.deadline:
            raise canary.KisPaperCanaryError("request_budget_exhausted")
        self.sleeper(duration)

    def can_advance(self):
        # Leave room for one native reconciliation; final wire guards still apply.
        return (self.monotonic() + 30 < self.deadline
                and sum(self.calls.values()) < 128 - 16)

    def _request(self, request, *, before_wire=None):
        canary.validate_kis_paper_canary_request(request)
        path = urlsplit(request.url).path

        def start():
            if self.monotonic() + 8 >= self.deadline or sum(self.calls.values()) >= 128:
                raise canary.KisPaperCanaryError("request_budget_exhausted")
            self.rate.wait_for_request_slot()
            if before_wire is not None:
                before_wire()
            if request.method == "POST" and path == readonly.KIS_PAPER_TOKEN_PATH:
                if self.calls["token_posts"] or not self.token.claim_token_request_start():
                    raise canary.KisPaperCanaryError("token_request_not_due")
                key = "token_posts"
            elif request.method == "GET":
                key = "get_requests"
            elif path == canary.KIS_PAPER_US_CANCEL_PATH:
                if self.calls["cancel_posts"] >= 3:
                    raise canary.KisPaperCanaryError("request_budget_exhausted")
                key = "cancel_posts"
            else:
                if self.calls["buy_posts"] + self.calls["sell_posts"] >= 3:
                    raise canary.KisPaperCanaryError("request_budget_exhausted")
                key = (
                    "buy_posts"
                    if request.headers.get("tr_id") == canary.KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
                    else "sell_posts"
                )
            self.calls[key] += 1
            self._pacer.record_request_start()

        return super()._request(request, before_wire=start)


def parse_packet(payload: bytes):
    def unique(rows):
        result = {}
        for key, value in rows:
            if key not in ENV_KEYS or key in result:
                raise ValueError("paper_packet_invalid")
            result[key] = value
        return result

    if len(payload) > 8192:
        raise ValueError("paper_packet_invalid")
    values = json.loads(
        payload,
        object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid_number")),
    )
    if (
        type(values) is not dict
        or set(values) != ENV_KEYS
        or values["THERICHER_MODE"] != "kis_paper"
    ):
        raise ValueError("paper_packet_invalid")
    return readonly.load_kis_paper_config_from_environment(values)


def run(config):
    from thericher_v2.execution.kis_paper_current_daily_session import (
        run_kis_paper_current_daily_session,
    )

    transport = OwnedTransport(control_root=CONTROL)
    client = canary.KisPaperCanaryClient(config=config, transport=transport)
    account = budget._digest([config.base_url, config.account_number, config.account_product_code])
    collection = None

    def load_data():
        nonlocal collection
        token = client._issue_access_token()
        market_config = KisPaperMarketDataConfig(
            app_key=config.app_key, app_secret=config.app_secret
        )
        collection = collect_daily_contexts(
            market_config,
            cache_root=MARKET,
            artifact_root=ARTIFACT / "data/etf-daily-context-v1",
            control_root=CONTROL,
            repository_root=APP,
            token_interval_seconds=60,
            access_token=token,
        )
        if collection.status != "complete":
            raise ValueError("current_daily_data_unavailable")
        contexts = {}
        for path, pin in collection.receipts:
            if path.parent.name in {"SPY", "TLT", "GLD"}:
                contexts[path.parent.name] = read_daily_context(
                    path, pin, cache_root=MARKET, required_count=253, repository_root=APP
                )
        return contexts

    def reads():
        return readonly.KisPaperReadOnlyClient(
            config=config, transport=transport, access_token=client._issue_access_token()
        ).portfolio_preview_snapshot(expected_account_ref=account)

    visits = []
    paths = dict(
        state_root=APP / "private/canary",
        repository_root=APP,
        artifact_root=ARTIFACT,
        runtime_projection_path=APP / "runtime/state/kis_paper_canary.json",
        paper_account_snapshot_path=APP / "runtime/state/paper_account_snapshot.json",
        emergency_state_path=APP / "emergency/emergency_state.json",
        execution_control_path=APP / "emergency/paper_execution_control.json",
    )
    for _ in range(MAX_NATIVE_VISITS):
        if visits and not transport.can_advance():
            break
        outcome = run_kis_paper_current_daily_session(
            **paths, client=client, data_loader=load_data, reads_factory=reads, execute=True
        )
        visits.append(outcome.safe_payload())
        if outcome.status != "pending":
            break
    result = outcome.safe_payload()
    result.update(
        paper_only=True,
        visits=visits,
        calls=transport.calls,
        market_daily_gets=collection.daily_gets if collection else 0,
        collection_reason=collection.reason if collection else None,
        next_due_utc=collection.next_due_utc.isoformat()
        if collection and collection.next_due_utc
        else None,
        observed_at_utc=datetime.now(UTC).isoformat(),
        fees="not_observed",
        settled_cash="not_observed",
        net_pnl="not_observed",
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        print('{"status":"inert","credential_reads":0,"broker_calls":0}')
        return 0
    try:
        result = run(parse_packet(sys.stdin.buffer.read(8193)))
    except Exception:
        result = dict(
            status="unavailable",
            reason="worker_recovery_required",
            paper_only=True,
            unknown_effects_not_assumed_zero=True,
        )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"complete", "no_intent", "pending"} else 20


if __name__ == "__main__":
    raise SystemExit(main())
