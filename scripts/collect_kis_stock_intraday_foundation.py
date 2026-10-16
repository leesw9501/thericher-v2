"""One explicitly frozen, read-only Paper stock-minute foundation capture."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / ".venv/Lib/site-packages")]
from thericher_v2.execution import kis_market_data as m  # noqa: E402
from thericher_v2.execution import kis_market_data_rate_gate as gates  # noqa: E402
from thericher_v2.execution.kis_stock_intraday_foundation import (  # noqa: E402
    FoundationLedger,
    atomic_json,
    file_ref,
    observed_coverage,
    run_foundation,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    args = parser.parse_args()
    artifact = args.contract.resolve().parent
    contract = json.loads(args.contract.read_bytes())
    start = datetime.fromisoformat(contract["appointment_utc"].replace("Z", "+00:00"))
    ready = json.loads((artifact / "patch-ready.json").read_bytes())
    for path, digest in ready["source_pins"].items():
        if file_ref(Path(path))["sha256"] != digest:
            raise ValueError("foundation_frozen_source_changed")
    if Path(sys.executable) != Path(sys._base_executable):
        raise ValueError("foundation_direct_base_interpreter_required")
    market = Path(contract["capture_root"]).resolve()
    if not market.is_relative_to(Path("D:/market_data").resolve()):
        raise ValueError("foundation_market_root_invalid")
    control = Path("D:/market_data/us_equities/kis_paper_private/collection-control-v1")
    probe = Path(ready["owner_probe"])
    routes = json.loads((artifact / "source-routes.json").read_bytes())["ordered_targets"]
    sessions = json.loads((artifact / "calendar.json").read_bytes())
    ledger = FoundationLedger(
        artifact_root=artifact,
        market_root=market,
        targets=[tuple(t) for t in routes],
        sessions=sessions,
    )
    if ledger.state["POST"]:
        raise ValueError("foundation_prior_auth_debit_requires_new_explicit_recovery_allowance")
    env = {
        key: os.environ[key]
        for key in (
            "SYSTEMROOT",
            "WINDIR",
            "PATH",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "APPDATA",
            "LOCALAPPDATA",
            "COMSPEC",
            "PATHEXT",
            "SystemDrive",
            "ProgramData",
        )
        if key in os.environ
    }
    lease = market / "owner.lock.d"
    identity = None
    client = None
    request_query = None
    wire_retry = False
    last_raw = None
    last_capture = None
    last_tick = None

    def check(reserve: float = 120) -> None:
        elapsed = (datetime.now(UTC) - start).total_seconds()
        if elapsed + reserve >= contract["active_cap_seconds"]:
            raise ValueError("foundation_active_cap")
        if elapsed + reserve >= contract["end_cap_seconds"]:
            raise ValueError("foundation_end_cap")
        disk = shutil.disk_usage("D:/")
        if (disk.free - 134217728) / disk.total < 0.15:
            raise ValueError("foundation_disk_floor")

    def pause(seconds: float, reason: str = "request_pacing") -> None:
        check(seconds + 120)
        ledger.state["next_due"] = (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()
        ledger.state["wait_reason"] = reason
        ledger.save()
        time.sleep(seconds)
        ledger.state["next_due"] = None

    def owners() -> dict:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(probe),
                "-OwnerPid",
                str(os.getpid()),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=12,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode:
            raise ValueError("foundation_owner_probe_technical_failure")
        fact = json.loads(result.stdout.decode("utf-8-sig"))
        if fact["model_task_found"] < 1 or fact["observer_task_found"] < 1:
            raise ValueError("foundation_required_owner_facts_absent")
        ledger.state["last_owner_fact"] = fact
        ledger.save()
        return fact

    def owner_clear(fact: dict) -> bool:
        age = (
            datetime.now(UTC) - datetime.fromisoformat(fact["observed_utc"].replace("Z", "+00:00"))
        ).total_seconds()
        due = fact["nearest_future_due_seconds"]
        return not any(
            fact[k]
            for k in (
                "running_relevant_tasks",
                "named_market_account_actors",
                "paper_account_data_containers",
            )
        ) and (due is None or due - age > 18)

    def wait_clear() -> None:
        while True:
            check()
            if owner_clear(owners()):
                return
            pause(5, "Paper_owner_active_or_due")

    class Token(gates.KisPaperMarketDataTokenStartGate):
        claimed_mark = None

        def claim_token_request_start(self) -> bool:
            wait_clear()
            claimed = super().claim_token_request_start()
            if claimed:
                self.claimed_mark = self.snapshot().last_token_request_started_at_utc
            return claimed

    token = Token(control_root=control, minimum_request_interval_seconds=60)
    rate = gates.KisPaperMarketDataRateGate(
        control_root=control, minimum_request_interval_seconds=2, sleeper=pause
    )

    class Wire:
        def __init__(self, opener):
            self.opener = opener

        def open(self, request, timeout):
            nonlocal last_tick
            check()
            wait_clear()
            parts = urlsplit(request.full_url)
            method = request.get_method()
            if parts.scheme != "https" or parts.netloc != "openapivts.koreainvestment.com:29443":
                raise ValueError("foundation_paper_host")
            if last_tick is not None:
                delay = max(0, last_tick + 2 - time.monotonic())
                if delay:
                    pause(delay)
            if method == "POST":
                if parts.path != m.KIS_PAPER_TOKEN_PATH:
                    raise ValueError("foundation_auth_path")
                if token.snapshot().last_token_request_started_at_utc != token.claimed_mark:
                    raise m.KisPaperMarketDataError("token_request_not_due")
            else:
                if (
                    method != "GET"
                    or parts.path != m.KIS_PAPER_MINUTE_PATH
                    or request_query is None
                ):
                    raise ValueError("foundation_market_scope")
                q = request_query
                expected = dict(
                    AUTH=[""],
                    EXCD=[q.exchange],
                    SYMB=[q.symbol],
                    NMIN=["1"],
                    PINC=["1" if q.include_previous_day else "0"],
                    NREC=["120"],
                    FILL=[""],
                    KEYB=[q.continuation_key or ""],
                    NEXT=[q.continuation_next or ""],
                )
                if parse_qs(parts.query, keep_blank_values=True) != expected:
                    raise ValueError("foundation_query_scope")
            ledger.begin_wire(
                method, query=request_query if method == "GET" else None, retry=wire_retry
            )
            tick = time.monotonic()
            ledger.state.setdefault("delegate_gaps", []).append(
                None if last_tick is None else tick - last_tick
            )
            last_tick = tick
            try:
                return self.opener.open(request, timeout=min(timeout, 5))
            finally:
                ledger.wire_finished()

    class Transport(m.UrllibKisPaperMarketDataTransport):
        def request(self, request):
            nonlocal last_raw, last_capture
            response = super().request(request)
            if request.method == "GET":
                for secret in (
                    config.app_key,
                    config.app_secret,
                    request.headers["authorization"].removeprefix("Bearer "),
                ):
                    if secret.encode() in response.body:
                        raise ValueError("foundation_secret_echo")
                last_raw = ledger.retain_raw(response.body)
                last_capture = datetime.now(UTC).isoformat()
            return response

    def fetch(query, retry):
        nonlocal request_query, wire_retry, last_raw, last_capture
        check()
        wait_clear()
        request_query, wire_retry = query, retry
        last_raw = last_capture = None
        return client.fetch_minute_page(query), last_raw, last_capture

    try:
        check()
        wait_clear()
        market.mkdir(parents=True, exist_ok=True)
        lease.mkdir()
        identity = lease.stat(follow_symlinks=False)
        atomic_json(lease / "owner.json", dict(pid=os.getpid(), version=ledger.state["version"]))
        ledger.state.update(pid=os.getpid(), status="running", owner_released=False)
        ledger.save()
        config = m.load_kis_paper_market_data_config(
            REPO / ".env", environment={"THERICHER_MODE": "off"}
        )
        transport = Transport(timeout_seconds=5, request_gate=rate, token_start_gate=token)
        transport._opener = Wire(transport._opener)
        client = m.KisPaperMarketDataClient(
            config=config,
            transport=transport,
            minute_route="historical_timestamp",
            minute_symbol_exchanges=ledger.scope,
            max_minute_page_attempts=602,
        )
        while True:
            check()
            wait_clear()
            due = token.snapshot().next_token_request_not_before_utc
            if due is not None and due > datetime.now(UTC):
                pause(min(10, (due - datetime.now(UTC)).total_seconds()), "shared_token_floor")
                continue
            try:
                client.ensure_authenticated()
                break
            except m.KisPaperMarketDataError as error:
                if str(error) != "token_request_not_due" or ledger.state["POST"]:
                    raise
        prior = max(
            s["close_utc"]
            for s in sessions
            if datetime.fromisoformat(s["close_utc"]) < datetime.now(UTC)
        )
        prior_key = (
            (datetime.fromisoformat(prior) - timedelta(minutes=1))
            .astimezone(__import__("zoneinfo").ZoneInfo("America/New_York"))
            .strftime("%Y%m%d%H%M%S")
        )
        run_foundation(ledger, fetch, lambda: last_raw, check, prior_close_key=prior_key)
    except Exception as error:
        ledger.state.update(
            status="closed_partial",
            failure_type=type(error).__name__,
            failure_category=str(error)
            if isinstance(error, (ValueError, m.KisPaperMarketDataError))
            else "technical_failure",
        )
    finally:
        if client is not None:
            client._access_token = None
        if identity is not None:
            current = lease.stat(follow_symlinks=False)
            if (identity.st_dev, identity.st_ino) != (current.st_dev, current.st_ino):
                raise ValueError("foundation_lease_identity_changed")
            (lease / "owner.json").unlink()
            lease.rmdir()
        ledger.state.update(
            owner_released=True,
            next_due=None,
            conservative_charge_seconds=(datetime.now(UTC) - start).total_seconds(),
        )
        ledger.save()
        coverage = observed_coverage(ledger)
        atomic_json(
            artifact / "manifest.json",
            dict(
                version=ledger.state["version"],
                pages=ledger.state["pages"],
                targets=routes,
                coverage=coverage,
                source_pins=ready["source_pins"],
                GET=ledger.state["GET"],
                POST=ledger.state["POST"],
                retry=ledger.state["retry"],
                availability="actual capture only; bar-end/units/PIT unknown",
                consumer=contract["consumer"],
                no_old_source_fit_Paper_change=True,
            ),
        )
        atomic_json(
            artifact / "completion.json",
            dict(
                **{
                    k: ledger.state.get(k)
                    for k in [
                        "status",
                        "GET",
                        "POST",
                        "retry",
                        "failure_category",
                        "conservative_charge_seconds",
                        "owner_released",
                        "pending",
                    ]
                },
                coverage=coverage,
                manifest=file_ref(artifact / "manifest.json"),
            ),
        )
        print(
            json.dumps(
                {
                    k: ledger.state.get(k)
                    for k in ["status", "GET", "POST", "retry", "failure_category"]
                }
            )
        )


if __name__ == "__main__":
    main()
