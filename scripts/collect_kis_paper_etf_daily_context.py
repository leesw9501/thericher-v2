"""Inert by default. Explicit selective Paper configuration enables one bounded intake.

Data token floor defaults to300s; --token-interval-seconds60 explicitly joins the
observer issuance floor. Replay requires exact receipt path/hash and never auths.
``--paper-config-stdin`` accepts a UTF-8 JSON object containing exactly
KIS_PAPER_APP_KEY and KIS_PAPER_APP_SECRET, at most8192bytes; never a whole dotenv.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import BinaryIO

from thericher_v2.data.kis_paper_etf_daily_context import (
    ARTIFACT_ROOT,
    CACHE_ROOT,
    CONTROL_ROOT,
    DailyContextError,
    collect_daily_contexts,
    read_daily_context,
)
from thericher_v2.execution.kis_market_data import (
    load_kis_paper_market_data_config,
    load_kis_paper_market_data_environment_config,
)

_PAPER_KEYS = frozenset({"KIS_PAPER_APP_KEY", "KIS_PAPER_APP_SECRET"})
_STDIN_CONFIG_MAX_BYTES = 8192


def _stdin_config(stream: BinaryIO):
    def unique_fields(pairs):
        result = {}
        for key, value in pairs:
            if key not in _PAPER_KEYS or key in result:
                raise DailyContextError("config_missing")
            result[key] = value
        return result

    def invalid_constant(_value):
        raise DailyContextError("config_missing")

    try:
        raw = stream.read(_STDIN_CONFIG_MAX_BYTES + 1)
        if type(raw) is not bytes or len(raw) > _STDIN_CONFIG_MAX_BYTES:
            raise DailyContextError("config_missing")
        values = json.loads(
            raw.decode("utf-8"), object_pairs_hook=unique_fields, parse_constant=invalid_constant
        )
        if type(values) is not dict or set(values) != _PAPER_KEYS:
            raise DailyContextError("config_missing")
        return load_kis_paper_market_data_environment_config(environment=values)
    except Exception:
        # Syntax/loader errors may contain submitted values; keep only the category.
        raise DailyContextError("config_missing") from None


def main(argv: Sequence[str] | None = None, *, stdin: BinaryIO | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    config = parser.add_mutually_exclusive_group()
    config.add_argument("--paper-from-env", action="store_true")
    config.add_argument("--paper-dotenv", type=Path)
    config.add_argument("--paper-config-stdin", action="store_true")
    parser.add_argument("--cache-root", type=Path, default=CACHE_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=ARTIFACT_ROOT)
    parser.add_argument("--control-root", type=Path, default=CONTROL_ROOT)
    parser.add_argument("--token-interval-seconds", type=int, choices=(60, 300), default=300)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--receipt-sha256")
    parser.add_argument("--required-count", type=int, choices=(2, 21, 253), default=253)
    args = parser.parse_args(argv)
    try:
        if args.receipt is not None:
            if args.execute or args.paper_from_env or args.paper_dotenv or args.paper_config_stdin:
                raise DailyContextError("invalid_contract")
            result = read_daily_context(
                args.receipt,
                args.receipt_sha256,
                cache_root=args.cache_root,
                required_count=args.required_count,
            )
            print(json.dumps(result.safe_payload(), sort_keys=True))
            return 0
        if not args.execute:
            print(json.dumps(dict(status="not_executed", reason="execute_flag_required")))
            return 0
        if not (args.paper_from_env or args.paper_dotenv or args.paper_config_stdin):
            raise DailyContextError("config_missing")
        if args.paper_config_stdin:
            configured = _stdin_config(stdin if stdin is not None else sys.stdin.buffer)
        elif args.paper_from_env:
            configured = load_kis_paper_market_data_environment_config()
        else:
            configured = load_kis_paper_market_data_config(
                args.paper_dotenv, environment={"THERICHER_MODE": "off"}
            )
        result = collect_daily_contexts(
            configured,
            cache_root=args.cache_root,
            artifact_root=args.artifact_root,
            control_root=args.control_root,
            token_interval_seconds=args.token_interval_seconds,
        )
        print(json.dumps(result.safe_payload(), sort_keys=True))
        return 0 if result.status == "complete" else 20
    except Exception as error:
        # Never serialize credentials, provider bodies or unexpected exception messages.
        reason = error.reason if isinstance(error, DailyContextError) else "input_unavailable"
        print(json.dumps(dict(status="unavailable", reason=reason), sort_keys=True))
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
