"""Finite, resumable price-only endpoint collection for one frozen shadow pair."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path("D:/thericher-v2/model-artifacts/data/kis-stock-prospective-pair-owned-endpoints-v1")
MARKET = Path("D:/market_data/us_equities/kis_paper_private/stock-shadow-endpoints/v1")
CONTROL = Path("D:/market_data/us_equities/kis_paper_private/collection-control-v1")
REPO = Path("C:/Users/Public/Documents/thericher-v2")
DATES = {"entry": "2026-10-12", "exit": "2026-10-19"}
DUE = {leg: day + "T21:40:00+00:00" for leg, day in DATES.items()}
CLOSURE = "sha256:016e67dcfda3458ec33826a448bd7ed1295ec2d3d07d39882c59739cd8c75130"
KINDS = "kis_stock_prospective_pair_owned_endpoints_v1"


class Stop(ValueError):
    pass


def require(ok, code="contract_invalid"):
    if not ok:
        raise Stop(code)


def sha(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def decode(raw):
    require(type(raw) is bytes and len(raw) <= 4_000_000)

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result)
            result[key] = value
        return result

    def nonfinite(_):
        raise Stop("contract_invalid")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def plain(path):
    path = Path(path).absolute()
    require(
        not any(p.is_symlink() or (p.exists() and p.is_junction()) for p in (path, *path.parents)),
        "path_invalid",
    )
    return path.resolve()


def child(root, relative):
    require(type(relative) is str and relative and "\\" not in relative and ":" not in relative)
    parts = Path(relative)
    require(not parts.is_absolute() and all(p not in {".", ".."} for p in parts.parts))
    root = plain(root)
    target = plain(root / parts)
    require(target.is_relative_to(root))
    return target


def read(path):
    path = plain(path)
    require(path.stat().st_size <= 4_000_000, "record_oversize")
    return path.read_bytes()


def pinned(path, pin):
    require(
        type(pin) is str
        and pin.startswith("sha256:")
        and len(pin) == 71
        and all(c in "0123456789abcdef" for c in pin[7:]),
        "binding_invalid",
    )
    raw = read(path)
    require(sha(raw) == pin, "evidence_changed")
    return raw


def publish(path, raw, *, replace=False):
    path = plain(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = plain(path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp"))
    try:
        with temporary.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError:
                require(read(path) == raw, "immutable_conflict")
    finally:
        if temporary.exists():
            plain(temporary).unlink()
    require(read(path) == raw, "publication_changed")
    return sha(raw)


def moment(value):
    parsed = datetime.fromisoformat(value)
    require(parsed.utcoffset() == timedelta(0), "clock_invalid")
    return parsed


def load_job(path, pin):
    require(plain(path) == plain(ROOT / "job.json"))
    job = decode(pinned(path, pin))
    require(
        job["kind"] == KINDS
        and job["forecast_closure_sha256"] == CLOSURE
        and job["market_root"] == str(MARKET)
        and job["control_root"] == str(CONTROL)
        and job["package_root"] == str(ROOT / "source")
        and job["dates"] == DATES
        and job["due"] == DUE
        and job["work_seconds"] == 230
        and job["total_seconds"] == 270
        and job["peer_count"] == 42
        and job["paper_only"] is True
        and job["account_calls"] == job["order_calls"] == job["live_calls"] == 0,
        "contract_invalid",
    )
    require(sha(read(Path(__file__))) == job["runner_sha256"], "source_changed")
    require(
        plain(sys.executable) == plain(job["python_path"])
        and sha(read(Path(sys.executable))) == job["python_sha256"],
        "runtime_changed",
    )
    peers = decode(pinned(ROOT / "peer-source.json", job["peer_source_sha256"]))
    frozen = decode(pinned(ROOT / "peer-freeze-return.json", job["peer_freeze_return_sha256"]))
    require(
        frozen["status"] == "peers_frozen"
        and frozen["peer_source_sha256"] == job["peer_source_sha256"]
        and frozen["peer_count"] == 42
        and frozen["peer_publication_observed"] is True
        and moment(frozen["completed_at"]) < moment("2026-10-12T13:30:00+00:00")
        and type(frozen["observed_elapsed_seconds"]) in (int, float)
        and math.isfinite(frozen["observed_elapsed_seconds"])
        and 0 <= frozen["observed_elapsed_seconds"] < 120,
        "peer_freeze_invalid",
    )
    require(
        peers["forecast_closure_sha256"] == CLOSURE
        and len(peers["peers"]) == 42
        and peers["entry_session"] == DATES["entry"]
        and peers["exit_session"] == DATES["exit"]
        and peers["entry_due"] == DUE["entry"]
        and peers["exit_due"] == DUE["exit"]
        and peers["provider_calls"] == peers["fits"] == peers["raw_target_reads"] == 0,
        "peer_binding_invalid",
    )
    require(set(job["helper_pins"]) == {"endpoint_worker.py", "endpoint_storage.py"})
    for name, expected in job["helper_pins"].items():
        pinned(child(ROOT, name), expected)
    require(type(job["package_pins"]) is dict and bool(job["package_pins"]))
    actual_files = {
        p.relative_to(ROOT / "source").as_posix() for p in (ROOT / "source").rglob("*.py")
    }
    require(actual_files == set(job["package_pins"]), "package_source_set_changed")
    for name, expected in job["package_pins"].items():
        pinned(child(ROOT / "source", name), expected)
    return job, peers


def runtime(job, peers, leg, pin):
    sys.path.insert(0, str(ROOT / "source"))
    from thericher_v2.data import kis_stock_shadow_endpoint as endpoint
    from thericher_v2.data import kis_stock_shadow_endpoint_storage as storage
    from thericher_v2.data.us_equity_session import us_equity_2026_session
    from thericher_v2.research.cross_asset_etf_input import CrossAssetSession

    require(sha(read(Path(endpoint.__file__))) == job["helper_pins"]["endpoint_worker.py"])
    require(sha(read(Path(storage.__file__))) == job["helper_pins"]["endpoint_storage.py"])
    official = us_equity_2026_session(datetime.fromisoformat(DATES[leg]).date())
    require(official is not None)
    scope = endpoint.EndpointScope(
        tuple(endpoint.EndpointPeer(**p) for p in peers["peers"]),
        peers["peer_sha256"],
        CLOSURE,
        CrossAssetSession(official.session_date, official.window.open_ts, official.window.close_ts),
        moment(peers["past_cutoff"]),
    )
    binding = storage.StorageBinding(scope, leg, pin, tuple(sorted(job["helper_pins"].items())))
    binding.record()
    return endpoint, storage, binding


def initial(pin, leg):
    return dict(
        kind=KINDS,
        job_sha256=pin,
        leg=leg,
        checkpoints=[],
        pending=None,
        outcome=None,
        next_due=DUE[leg],
    )


def cursor_path(leg):
    return ROOT / leg / "current.json"


def read_checkpoint(storage, link):
    raw = pinned(child(ROOT, link["path"]), link["sha256"])
    doc = decode(raw)
    identity = doc["invocation_id"]
    require(
        type(identity) is str
        and len(identity) == 32
        and all(c in "0123456789abcdef" for c in identity),
        "cursor_invalid",
    )
    require(
        link["path"] == doc["binding"]["leg"] + "/checkpoints/" + identity + ".json",
        "cursor_invalid",
    )
    pages = []
    for observation in doc["observations"]:
        receipt_pin, payload_pin = observation["page_receipt_sha256"], observation["payload_sha256"]
        if receipt_pin is not None:
            pages.append(
                storage.PageBytes(
                    pinned(ROOT / "pages" / (receipt_pin[7:] + ".json"), receipt_pin),
                    pinned(MARKET / "pages" / (payload_pin[7:] + ".json"), payload_pin),
                )
            )
    return storage.BatchBytes(raw, tuple(pages))


def resume(storage, binding, current, pin, leg):
    require(
        current["kind"] == KINDS
        and current["job_sha256"] == pin
        and current["leg"] == leg
        and type(current["checkpoints"]) is list
        and len(current["checkpoints"]) <= 600,
        "cursor_invalid",
    )
    links = current["checkpoints"]
    if not links:
        return None
    return storage.load_resume(
        binding,
        tuple(read_checkpoint(storage, link) for link in links),
        receipt_sha256s=tuple(link["sha256"] for link in links),
    )


def accept_pending(storage, binding, current, pin, leg):
    pending = current["pending"]
    if pending is None:
        return resume(storage, binding, current, pin, leg)
    require(type(pending) is dict and set(pending) == {"id", "start"})
    prior = resume(storage, binding, current, pin, leg)
    require(
        type(pending["start"]) is int and pending["start"] == (prior.next_index if prior else 0),
        "cursor_invalid",
    )
    require(
        type(pending["id"]) is str
        and len(pending["id"]) == 32
        and all(c in "0123456789abcdef" for c in pending["id"])
    )
    path = child(ROOT, leg + "/checkpoints/" + pending["id"] + ".json")
    if path.exists():
        current["checkpoints"].append(
            dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(read(path)))
        )
        recovered = resume(storage, binding, current, pin, leg)
        require(recovered.attempts[-1].callback_attempts == 1, "cursor_invalid")
        current["pending"] = None
        publish(cursor_path(leg), encode(current), replace=True)
        return recovered
    return prior


def read_current(job, peers, pin, leg):
    _, storage, binding = runtime(job, peers, leg, pin)
    path = cursor_path(leg)
    if not path.exists():
        return dict(status="not_observed", leg=leg, next_due=DUE[leg], peer_count=42)
    current = decode(read(path))
    readback = resume(storage, binding, current, pin, leg)
    facts = readback.safe_facts() if readback else dict(peer_count=42, next_index=0)
    outcome = current.get("outcome")
    parent_link = current.get("parent_return")
    if outcome is None or parent_link is None:
        return dict(status="not_observed", next_due=current["next_due"], **facts)
    parent = decode(pinned(child(ROOT, parent_link["path"]), parent_link["sha256"]))
    require(
        parent["job_sha256"] == pin
        and parent["leg"] == leg
        and parent["outcome"] == outcome
        and parent["checkpoint_chain_sha256"] == sha(encode(current["checkpoints"]))
        and parent["child_reaped"] is True
        and parent["source_after"] is True
        and parent["exit_code"] == 0
        and type(parent["child_observed_seconds"]) in (int, float)
        and math.isfinite(parent["child_observed_seconds"])
        and 0 <= parent["child_observed_seconds"] < 280,
        "parent_binding_invalid",
    )
    capture = decode(pinned(child(ROOT, outcome["path"]), outcome["sha256"]))
    require(
        outcome["path"].startswith(leg + "/runs/") and outcome["path"].endswith(".capture.json"),
        "outcome_binding_invalid",
    )
    terminal = decode(pinned(child(ROOT, capture["terminal_path"]), capture["terminal_sha256"]))
    require(
        capture["job_sha256"] == terminal["job_sha256"] == pin
        and capture["leg"] == terminal["leg"] == leg
        and capture["checkpoint_chain_sha256"] == sha(encode(current["checkpoints"]))
        and capture["publication_observed"] is True
        and capture["source_after"] is True
        and type(capture["observed_elapsed_seconds"]) in (int, float)
        and math.isfinite(capture["observed_elapsed_seconds"])
        and 0 <= capture["observed_elapsed_seconds"] < 270
        and moment(terminal["completed_at"]) >= moment(DUE[leg])
        and moment(terminal["completed_at"]) < moment(DUE[leg]) + timedelta(hours=1)
        and terminal["account_calls"] == terminal["order_calls"] == terminal["live_calls"] == 0,
        "outcome_binding_invalid",
    )
    require(terminal["status"] in {"scope_complete", "yielded", "input_unavailable"})
    if terminal["status"] == "scope_complete":
        require(readback is not None and readback.next_index == 42, "outcome_binding_invalid")
    return dict(
        status=terminal["status"],
        next_due=current["next_due"],
        **facts,
        outcome_sha256=outcome["sha256"],
        wire_token_starts=terminal["wire_token_starts"],
        wire_daily_starts=terminal["wire_daily_starts"],
        provider_finality="not_observed",
    )


def store_batch(storage, binding, current, batch, pages, completed, leg):
    pending = current["pending"]
    require(pending is not None)
    stored = storage.dump_batch(
        binding,
        batch,
        pages_by_index=pages,
        invocation_id=pending["id"],
        start_index=pending["start"],
        completed_at=completed,
    )
    storage.load_batch(binding, stored, receipt_sha256=stored.receipt_sha256)
    for page in stored.pages:
        publish(MARKET / "pages" / (sha(page.payload)[7:] + ".json"), page.payload)
        publish(ROOT / "pages" / (sha(page.receipt)[7:] + ".json"), page.receipt)
    path = child(ROOT, leg + "/checkpoints/" + pending["id"] + ".json")
    publish(path, stored.receipt)
    current["checkpoints"].append(
        dict(path=path.relative_to(ROOT).as_posix(), sha256=stored.receipt_sha256)
    )
    current["pending"] = None


class WireOpener:
    def __init__(self, inner, deadline):
        self.inner, self.deadline = inner, deadline
        self.token, self.daily = 0, 0

    def open(self, request, *, timeout):
        require(time.monotonic() + timeout < self.deadline, "runtime_budget")
        if request.get_method() == "POST":
            require(self.token == 0, "token_budget")
            self.token += 1
        else:
            require(request.get_method() == "GET" and self.daily < 42, "page_budget")
            self.daily += 1
        return self.inner.open(request, timeout=timeout)


def run(job, peers, pin, leg, *, clock=lambda: datetime.now(UTC)):
    began = time.monotonic()
    load_job(ROOT / "job.json", pin)
    now = clock()
    due = moment(DUE[leg])
    require(now.utcoffset() == timedelta(0), "clock_invalid")
    if now < due or now >= due + timedelta(hours=1):
        return dict(status="not_due" if now < due else "expired", next_due=DUE[leg])
    endpoint, storage, binding = runtime(job, peers, leg, pin)
    from thericher_v2.execution import kis_market_data as market
    from thericher_v2.execution import kis_market_data_rate_gate as pace
    from thericher_v2.execution import kis_private_daily_backfill as locks

    work_deadline = began + 230
    require(time.monotonic() + 20 < work_deadline, "runtime_budget")
    for root in (ROOT, MARKET, CONTROL):
        plain(root).mkdir(parents=True, exist_ok=True)
    disk = shutil.disk_usage(plain(MARKET))
    require(disk.free / disk.total >= 0.15, "storage_floor")
    lock = locks._acquire_worker_lock(root=MARKET, observed_at=now)
    if lock is None:
        return dict(status="worker_busy", next_due=(now + timedelta(minutes=5)).isoformat())
    wire, current = None, None
    result = dict(status="input_unavailable", reason="runtime_failed", job_sha256=pin, leg=leg)
    phase = "resume"
    try:
        path = cursor_path(leg)
        current = decode(read(path)) if path.exists() else initial(pin, leg)
        recovered = accept_pending(storage, binding, current, pin, leg)
        position = recovered.next_index if recovered else 0
        if position == 42:
            return finish(
                dict(
                    status="scope_complete",
                    job_sha256=pin,
                    next_due=None,
                    **recovered.safe_facts(),
                ),
                current,
                pin,
                leg,
                began,
                None,
                clock,
            )
        if current["next_due"] is not None and clock() < moment(current["next_due"]):
            return dict(status="yielded", job_sha256=pin, leg=leg, next_due=current["next_due"])
        current["outcome"] = None
        current["parent_return"] = None
        phase = "client_prepare"

        def sleeper(seconds):
            require(math.isfinite(seconds) and seconds >= 0, "runtime_budget")
            if seconds > 2 or time.monotonic() + seconds + 16 >= work_deadline:
                raise market.KisPaperMarketDataError("rate_limited")
            time.sleep(seconds)

        gate = pace.KisPaperMarketDataRateGate(control_root=CONTROL, sleeper=sleeper)
        token_gate = pace.KisPaperMarketDataTokenStartGate(control_root=CONTROL)
        load_job(ROOT / "job.json", pin)
        require(time.monotonic() + 20 < work_deadline, "runtime_budget")
        config = market.load_kis_paper_market_data_config(
            REPO / ".env", environment={"THERICHER_MODE": "off"}
        )
        transport = market.UrllibKisPaperMarketDataTransport(
            request_gate=gate, token_start_gate=token_gate
        )
        wire = WireOpener(transport._opener, work_deadline)
        transport._opener = wire
        client = market.KisPaperMarketDataClient(
            config=config, transport=transport, max_daily_page_attempts=42
        )
        stop = None
        while position < 42:
            phase = "page_prepare"
            require(time.monotonic() + 20 < work_deadline, "runtime_budget")
            if current["pending"] is None:
                current["pending"] = dict(id=uuid.uuid4().hex, start=position)
                publish(path, encode(current), replace=True)
            require(current["pending"]["start"] == position, "cursor_invalid")
            pages = {}

            def fetch(query, _position=position, _pages=pages):
                require(query == binding.scope.query(_position), "query_invalid")
                page = client.fetch_daily_raw_page(query)
                # Never retain headers, tokens or broker bodies; only typed raw market rows.
                secret_values = (config.app_key, config.app_secret, client._access_token)
                encoded_rows = encode([row.as_document() for row in page.rows])
                require(
                    not any(v and v.encode() in encoded_rows for v in secret_values), "secret_echo"
                )
                _pages[_position] = page
                return page

            batch = endpoint.collect_endpoints(
                binding.scope,
                fetch_daily_raw_page=fetch,
                clock=clock,
                start_index=position,
                max_attempts=1,
            )
            # Rejected typed pages are evidence about that peer, not usable retained inputs.
            if batch.observations[position].reason not in {None, "endpoint_missing"}:
                pages.clear()
            phase = "page_persist"
            store_batch(storage, binding, current, batch, pages, clock(), leg)
            stop, position = batch.stop_reason, batch.next_index
            current["next_due"] = (
                None if position == 42 else (clock() + timedelta(minutes=5)).isoformat()
            )
            publish(path, encode(current), replace=True)
            if stop is not None:
                break
        readback = resume(storage, binding, current, pin, leg)
        require(readback is not None and readback.next_index == position, "cursor_invalid")
        result = dict(
            status="scope_complete" if position == 42 else "yielded",
            reason=stop,
            job_sha256=pin,
            next_due=current["next_due"],
            **readback.safe_facts(),
        )
    except Exception as error:
        result["failure_phase"] = phase
        result["reason"] = (
            str(error)
            if isinstance(error, Stop)
            and str(error)
            in {
                "runtime_budget",
                "cursor_invalid",
                "immutable_conflict",
                "secret_echo",
            }
            else "runtime_failed"
        )
        if current is not None:
            current["next_due"] = (clock() + timedelta(minutes=5)).isoformat()
            publish(cursor_path(leg), encode(current), replace=True)
    finally:
        locks._release_worker_lock(lock)
    return finish(result, current, pin, leg, began, wire, clock)


def finish(result, current, pin, leg, began, wire, clock):
    result.update(
        wire_token_starts=wire.token if wire else 0,
        wire_daily_starts=wire.daily if wire else 0,
        count_semantics="direct opener starts after shared gate; not callback entries",
        account_calls=0,
        order_calls=0,
        live_calls=0,
        credentials_persisted=False,
        leg=leg,
    )
    load_job(ROOT / "job.json", pin)
    elapsed = time.monotonic() - began
    require(elapsed < 270, "runtime_budget")
    run_path = ROOT / leg / "runs" / (uuid.uuid4().hex + ".json")
    publish(
        run_path,
        encode(dict(result, completed_at=clock().isoformat(), pre_publication_seconds=elapsed)),
    )
    capture = dict(
        job_sha256=pin,
        leg=leg,
        terminal_sha256=sha(read(run_path)),
        terminal_path=run_path.relative_to(ROOT).as_posix(),
        checkpoint_chain_sha256=sha(encode(current["checkpoints"])),
        observed_elapsed_seconds=time.monotonic() - began,
        publication_observed=True,
        source_after=True,
        own_future_publication_observed=False,
    )
    require(capture["observed_elapsed_seconds"] < 270, "runtime_budget")
    capture_path = run_path.with_name(run_path.stem + ".capture.json")
    capture_pin = publish(capture_path, encode(capture))
    current["outcome"] = dict(path=capture_path.relative_to(ROOT).as_posix(), sha256=capture_pin)
    publish(cursor_path(leg), encode(current), replace=True)
    # This observes the terminal record's fsync, not this return value's own publication.
    result.update(
        terminal_sha256=sha(read(run_path)),
        terminal_path=str(run_path),
        observed_elapsed_seconds=time.monotonic() - began,
        publication_observed=True,
        own_return_publication_observed=False,
    )
    require(result["observed_elapsed_seconds"] < 270, "runtime_budget")
    return result


def attest_child(result, pin, leg, elapsed, exit_code):
    require(
        type(elapsed) in (int, float) and math.isfinite(elapsed) and 0 <= elapsed < 280,
        "runtime_budget",
    )
    require(
        exit_code == 0 and result["job_sha256"] == pin and result["leg"] == leg,
        "child_result_invalid",
    )
    require(
        result["publication_observed"] is True
        and type(result["observed_elapsed_seconds"]) in (int, float)
        and math.isfinite(result["observed_elapsed_seconds"])
        and 0 <= result["observed_elapsed_seconds"] <= elapsed
        and result["observed_elapsed_seconds"] < 270,
        "child_result_invalid",
    )
    terminal_path = plain(result["terminal_path"])
    require(terminal_path.is_relative_to(plain(ROOT / leg / "runs")), "child_result_invalid")
    terminal = decode(pinned(terminal_path, result["terminal_sha256"]))
    require(
        terminal["status"] == result["status"]
        and terminal["job_sha256"] == pin
        and terminal["leg"] == leg,
        "child_result_invalid",
    )
    current = decode(read(cursor_path(leg)))
    outcome = current["outcome"]
    capture = decode(pinned(child(ROOT, outcome["path"]), outcome["sha256"]))
    require(
        capture["terminal_sha256"] == result["terminal_sha256"]
        and capture["checkpoint_chain_sha256"] == sha(encode(current["checkpoints"])),
        "child_result_invalid",
    )
    load_job(ROOT / "job.json", pin)
    parent = dict(
        kind="endpoint_child_return_v1",
        job_sha256=pin,
        leg=leg,
        outcome=outcome,
        checkpoint_chain_sha256=sha(encode(current["checkpoints"])),
        child_observed_seconds=elapsed,
        exit_code=exit_code,
        child_reaped=True,
        source_after=True,
        own_future_publication_observed=False,
    )
    path = ROOT / leg / "returns" / (uuid.uuid4().hex + ".json")
    parent_pin = publish(path, encode(parent))
    current["parent_return"] = dict(path=path.relative_to(ROOT).as_posix(), sha256=parent_pin)
    publish(cursor_path(leg), encode(current), replace=True)
    return parent_pin


def dispatch(job, peers, pin, leg):
    began = time.monotonic()
    load_job(ROOT / "job.json", pin)
    args = [
        sys.executable,
        "-I",
        "-B",
        str(Path(__file__).resolve()),
        "--job",
        str(ROOT / "job.json"),
        "--job-sha256",
        pin,
        "--leg",
        leg,
        "--child",
    ]
    environment = {
        key: os.environ[key]
        for key in (
            "PATH",
            "SystemRoot",
            "WINDIR",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "APPDATA",
            "LOCALAPPDATA",
        )
        if key in os.environ
    }
    completed = subprocess.run(
        args,
        cwd=REPO,
        env=environment,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=280,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    elapsed = time.monotonic() - began
    require(len(completed.stdout) <= 262144 and elapsed < 280, "runtime_budget")
    result = decode(completed.stdout.strip())
    load_job(ROOT / "job.json", pin)
    if "terminal_path" in result:
        result["parent_return_sha256"] = attest_child(
            result, pin, leg, elapsed, completed.returncode
        )
    else:
        require(
            completed.returncode == 0
            and result["status"]
            in {
                "not_due",
                "expired",
                "worker_busy",
                "yielded",
                "scope_complete",
            },
            "child_result_invalid",
        )
    require(time.monotonic() - began < 300, "runtime_budget")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--job-sha256", required=True)
    parser.add_argument("--leg", choices=tuple(DATES), required=True)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        job, peers = load_job(args.job, args.job_sha256)
        if args.read_only:
            result = read_current(job, peers, args.job_sha256, args.leg)
        elif args.preview:
            runtime(job, peers, args.leg, args.job_sha256)
            result = dict(
                status="prepared",
                leg=args.leg,
                peer_count=42,
                next_due=DUE[args.leg],
                provider_calls=0,
            )
        elif args.child:
            result = run(job, peers, args.job_sha256, args.leg)
        else:
            result = dispatch(job, peers, args.job_sha256, args.leg)
    except Exception:
        result = dict(status="input_unavailable", reason="owned_endpoint_runtime_unavailable")
    print(encode(result).decode())
    return int(result["status"] == "input_unavailable")


if __name__ == "__main__":
    raise SystemExit(main())
