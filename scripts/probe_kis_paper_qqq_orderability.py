"""One-shot endpoint diagnostic, not an order-limit or buying-power attestation.

Preview performs no operational I/O. Execution uses the existing Data owner's
token-start control (pass its shared mount as --control-root in a container).
No token, account snapshot, quote, order, or private identity is persisted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True

from thericher_v2.execution.kis_market_data_rate_gate import (  # noqa: E402
    KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY,
    KisPaperMarketDataTokenStartGate,
)
from thericher_v2.execution.kis_readonly import (  # noqa: E402
    KIS_PAPER_BASE_URL,
    KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT,
    KIS_PAPER_TOKEN_PATH,
    KisHttpRequest,
    KisHttpResponse,
    KisHttpTransport,
    KisPaperReadOnlyClient,
    KisPaperReadOnlyError,
    UrllibKisHttpTransport,
    load_kis_paper_config,
    load_kis_paper_config_from_environment,
    safe_kis_paper_upstream_code,
    validate_kis_paper_readonly_request,
)
from thericher_v2.research.artifact_paths import (  # noqa: E402
    ensure_external_artifact_directory,
    resolve_model_artifact_root,
)


class _ProbeFailure(Exception):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class _Deferred(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _ProbeFailure("arguments_invalid")


class _ScopedTransport:
    """Allow only the exact diagnostic pair, without exposing request values."""

    def __init__(self, transport: KisHttpTransport, token_gate: object) -> None:
        self._transport = transport
        self._gate = token_gate
        self.auth_requests = 0
        self.query_requests = 0
        self._auth_attempted = False
        self.owned_next_due: str | None = None

    def request(self, request: KisHttpRequest) -> KisHttpResponse:
        validate_kis_paper_readonly_request(request)
        if request.method == "POST" and request.url == KIS_PAPER_BASE_URL + KIS_PAPER_TOKEN_PATH:
            if self._auth_attempted or self.query_requests:
                raise _ProbeFailure("request_scope_invalid")
            self._auth_attempted = True
            if not self._gate.claim_token_request_start():
                due = self._gate.snapshot().next_token_request_not_before_utc
                if due is not None:
                    if not isinstance(due, datetime) or due.utcoffset() != UTC.utcoffset(due):
                        raise _ProbeFailure("token_control_invalid")
                    self.owned_next_due = due.isoformat()
                raise _Deferred
            self.auth_requests = 1
        elif (
            request.method == "GET"
            and request.url == KIS_PAPER_BASE_URL + KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.path
            and request.headers.get("tr_id") == "VTTS3007R"
            and request.query.get("ITEM_CD") == "QQQ"
            and request.query.get("OVRS_EXCG_CD") == "NASD"
            and request.query.get("OVRS_ORD_UNPR") == "1"
            and request.headers.get("tr_cont", "") == ""
            and self.auth_requests == 1
            and self.query_requests == 0
        ):
            self.query_requests = 1
        else:
            raise _ProbeFailure("request_scope_invalid")
        response = self._transport.request(request)
        payload = response.payload(reject_duplicate_keys=True)
        if response.status_code != 200 or ("rt_cd" in payload and payload["rt_cd"] != "0"):
            code = safe_kis_paper_upstream_code(payload.get("msg_cd"))
            category = (
                code
                if code in {"paper_account_user_mismatch", "paper_account_expired"}
                else "upstream_unclassified"
            )
            raise _ProbeFailure(category)
        return response


def _payload(status: str, category: str, scoped: _ScopedTransport | None = None) -> dict:
    return {
        "kind": "kis_paper_qqq_orderability_probe",
        "status": status,
        "category": category,
        "environment": "paper",
        "read_only": True,
        "submit": False,
        "symbol": "QQQ",
        "exchange": "NASD",
        "endpoint": "VTTS3007R",
        "diagnostic_scope": "synthetic_price_endpoint_acceptance_only",
        "actual_order_limit": False,
        "funds_readiness_proof": False,
        "prior_rejection_explanation": False,
        "auth_requests": scoped.auth_requests if scoped else 0,
        "query_requests": scoped.query_requests if scoped else 0,
        "owned_next_due": scoped.owned_next_due if scoped else None,
    }


def main(
    argv: list[str] | None = None,
    *,
    transport: KisHttpTransport | None = None,
    token_gate: object | None = None,
    config_loader=None,
) -> int:
    """Production CLI with injectable offline dependencies for focused tests."""
    scoped = None
    receipt = None
    receipt_path = None
    payload = _payload("deferred", "execute_flag_required")
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--artifact-root", type=Path)
        parser.add_argument("--control-root", type=Path, help="Existing Data token-control root")
        args = parser.parse_args(argv)
        if not args.execute:
            print(json.dumps(payload, sort_keys=True))
            return 0

        root = ensure_external_artifact_directory(
            args.artifact_root or resolve_model_artifact_root(),
            Path(__file__).resolve().parents[1],
            "execution",
            "kis-paper-qqq-orderability-probe",
        )
        # Reserve an immutable receipt before any credential use or network start.
        receipt_path = root / f"{uuid.uuid4().hex}.json"
        receipt = receipt_path.open("xb")
        control_root = args.control_root or (
            Path(os.environ.get("THERICHER_MARKET_DATA_ROOT") or r"D:\market_data")
            / "us_equities"
            / "kis_paper_private"
            / KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY
        )
        gate = (
            token_gate
            if token_gate is not None
            else KisPaperMarketDataTokenStartGate(control_root=control_root)
        )
        if config_loader is not None:
            config = config_loader(os.environ)
        elif Path("/.dockerenv").is_file():
            config = load_kis_paper_config_from_environment(os.environ)
        else:
            config = load_kis_paper_config(Path(__file__).resolve().parents[1] / ".env")
        scoped = _ScopedTransport(
            transport if transport is not None else UrllibKisHttpTransport(), gate
        )
        client = KisPaperReadOnlyClient(config=config, transport=scoped)
        client.orderable_funds_at_limit(symbol="QQQ", exchange="NASD", limit_price=Decimal("1"))
        payload = _payload("accepted", "endpoint_response_accepted", scoped)
    except _Deferred:
        payload = _payload("deferred", "token_request_not_due", scoped)
    except _ProbeFailure as exc:
        payload = _payload("failed", exc.category, scoped)
    except KisPaperReadOnlyError as exc:
        category = "transport_failure" if exc.code == "transport_failure" else "parse_failure"
        if scoped is None:
            category = "paper_config_invalid"
        payload = _payload("failed", category, scoped)
    except Exception:
        payload = _payload("failed", "local_failure", scoped)

    observed_at = datetime.now(UTC).isoformat()
    payload = {
        **payload,
        "observed_at": observed_at,
        "evidence_path": str(receipt_path) if receipt is not None else None,
    }
    if receipt is not None:
        try:
            raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
            with receipt:
                receipt.write(raw)
                receipt.flush()
                os.fsync(receipt.fileno())
            payload = {**payload, "receipt_sha256": hashlib.sha256(raw).hexdigest()}
        except Exception:
            payload = {
                **_payload("failed", "receipt_unavailable", scoped),
                "observed_at": observed_at,
                "evidence_path": None,
            }
    print(json.dumps(payload, sort_keys=True))
    return 1 if payload["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
