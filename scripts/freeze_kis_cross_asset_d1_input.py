"""Offline, exact-chain price-only input freezing for the fixed KIS MODP0 trio."""

from __future__ import annotations

import argparse
import csv
import gzip
import importlib.util
import io
import json
import os
import re
import shutil
import uuid
from collections.abc import Sequence
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "kis_cross_asset_history_freezer", ROOT / "scripts/acquire_kis_cross_asset_d1_history.py"
)
assert _SPEC is not None and _SPEC.loader is not None
history = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(history)
probe = history.probe
VERSION = "kis-cross-asset-d1-price-only-input-v1"
COLUMNS = ("symbol", "exchange", "session_date", "open", "close", "source_chunk_id")


class FreezeError(RuntimeError):
    """Code-only errors; input contents and dynamic exceptions are never printed."""


def _pins(repository: Path) -> dict:
    return {
        **history._pins(repository),
        "scripts/freeze_kis_cross_asset_d1_input.py": probe._sha(Path(__file__).read_bytes()),
    }


def _calendar(data: bytes) -> tuple[str, ...]:
    try:
        document = json.loads(data)
        sessions = tuple(document["session_dates"])
        expected_start = date.fromisoformat("2007-08-21").isoformat()
        if (
            document["kind"] != "caller_nyse_session_dates_v1"
            or document["calendar_attestation"] != "caller_predeclared_full_scope_nyse_sessions"
            or document["start"] != expected_start
            or document["end"] != "2026-10-07"
            or not sessions
            or sessions != tuple(sorted(set(sessions)))
            or sessions[0] != expected_start
            or sessions[-1] != "2026-10-07"
            or any(date.fromisoformat(s).isoformat() != s for s in sessions)
        ):
            raise ValueError("calendar invalid")
        return sessions
    except (KeyError, TypeError, ValueError) as error:
        raise FreezeError("calendar_invalid") from error


def freeze_input(
    *,
    history_receipt: Path,
    history_sha256: str,
    calendar_path: Path,
    calendar_sha256: str,
    market_root: Path,
    artifact_root: Path,
    repository_root: Path,
    run_label: str,
    seed_source_root: Path | None = None,
) -> dict:
    """Freeze indexed rows only; a partial terminal is not a collection-wide gate."""
    if (
        repository_root.resolve() != ROOT
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_label)
        or any(
            not re.fullmatch(r"sha256:[0-9a-f]{64}", h) for h in (history_sha256, calendar_sha256)
        )
    ):
        raise FreezeError("argument_invalid")
    market = probe._external(market_root, repository_root)
    artifacts = probe._external(artifact_root, repository_root)
    if market == artifacts or market.is_relative_to(artifacts) or artifacts.is_relative_to(market):
        raise FreezeError("root_invalid")
    pins = _pins(repository_root)
    bindings = {}

    def bound(path: Path, digest: str, label: str) -> bytes:
        base = market if label == "MARKET" else artifacts
        path = probe._external(path, repository_root)
        if not path.is_relative_to(base):
            raise FreezeError("source_path_invalid")
        data = path.read_bytes()
        if probe._sha(data) != digest:
            raise FreezeError("source_hash_mismatch")
        key = (label, path.relative_to(base).as_posix())
        if key in bindings and bindings[key]["sha256"] != digest:
            raise FreezeError("source_hash_mismatch")
        bindings[key] = {"root": label, "path": key[1], "sha256": digest}
        return data

    receipt_bytes = bound(history_receipt, history_sha256, "ARTIFACT")
    sessions = _calendar(bound(calendar_path, calendar_sha256, "ARTIFACT"))
    receipt = json.loads(receipt_bytes)
    contract_path = history_receipt.parent / "contract.json"
    contract = json.loads(bound(contract_path, receipt["contract_sha256"], "ARTIFACT"))
    if (
        receipt["kind"] != history.VERSION
        or receipt["goal"] != history.GOAL
        or receipt["status"] not in {"partial", "complete", "recovered", "unavailable"}
        or receipt["source_reattestation"] != "matched"
        or receipt["source_pins"] != history._pins(repository_root)
        or contract["source_pins"] != receipt["source_pins"]
        or contract["kind"] != history.VERSION
        or contract["goal"] != history.GOAL
        or contract["start"] != history.START
        or contract["end"] != history.END
        or receipt["catalog"]["status"] != "matched"
        or receipt["catalog"]["immutable_artifact_snapshot"] != "index.json"
        or receipt["pending_projection"] != "verified"
    ):
        raise FreezeError("history_chain_invalid")
    index_bytes = bound(
        history_receipt.parent / "index.json", receipt["catalog"]["sha256"], "ARTIFACT"
    )
    live_index_path = history._child(
        market, receipt["catalog"]["market_relative_path"], repository_root
    )
    if bound(live_index_path, receipt["catalog"]["sha256"], "MARKET") != index_bytes:
        raise FreezeError("catalog_changed")
    cache_root = live_index_path.parent
    expected_root = (
        market / f"us_equities/kis_paper_private/cross-asset-d1/{history.GOAL}/canonical-trio-v1"
    )
    if cache_root != expected_root:
        raise FreezeError("history_chain_invalid")
    index = json.loads(index_bytes)
    if receipt["pending"] != index["pending"] or contract["seed_binding"] != index["seed_binding"]:
        raise FreezeError("history_chain_invalid")
    output_root = history._child(
        market,
        f"us_equities/kis_paper_private/cross-asset-d1/{history.GOAL}/research-input/{run_label}",
        repository_root,
    )
    artifact_dir = history._child(
        artifacts, f"research/{history.GOAL}/input/{run_label}", repository_root
    )
    if output_root.exists() or artifact_dir.exists():
        raise FreezeError("immutable_destination_exists")
    artifact_dir.mkdir(parents=True)
    # Calendar/terminal identities are committed before any private price parsing.
    freeze_contract_hash = probe._write_json(
        artifact_dir / "contract.json",
        {
            "kind": VERSION,
            "history_receipt_sha256": history_sha256,
            "calendar_sha256": calendar_sha256,
            "source_pins": pins,
            "calendar_attestation_owned_by": "caller",
            "start": history.START,
            "end": history.END,
            "columns": list(COLUMNS),
            "no_date_fill": True,
        },
    )
    stage = None
    try:
        history._verify_index(index, cache_root, repository_root, index["seed_binding"])
        if index["seed_binding"] is not None:
            seed = index["seed_binding"]
            seed_path = history._child(artifacts, seed["artifact_relative_path"], repository_root)
            seed_data = bound(seed_path, seed["sha256"], "ARTIFACT")
            seed_receipt = json.loads(seed_data)
            seed_root = seed_source_root or seed_path.parent / "source-before-terminal-pin-repair"
            history._seed_pages(
                path=seed_path,
                digest=seed["sha256"],
                market=market,
                artifacts=artifacts,
                repository=repository_root,
                source_root=seed_root,
            )
            bound(seed_path.parent / "contract.json", seed_receipt["contract_sha256"], "ARTIFACT")
            for item in seed_receipt["private_daily_responses"]:
                bound(
                    history._child(market, item["market_relative_path"], repository_root),
                    item["sha256"],
                    "MARKET",
                )
            if seed_receipt["source_pins"] != probe._source_pins(repository_root):
                for name, digest in seed_receipt["source_pins"].items():
                    bound(history._child(seed_root, name, repository_root), digest, "ARTIFACT")
        rows_by_asset = {}
        chunks = []
        coverage = {}
        expected_dates = set(sessions)
        for symbol, target in index["targets"].items():
            rows_by_date = {}
            for ordinal, chunk in enumerate(target["chunks"], 1):
                snapshot = history._snapshot(cache_root, chunk["manifest_path"], repository_root)
                if any(
                    snapshot[k] != chunk[k]
                    for k in (
                        "manifest_hash",
                        "raw_sha256",
                        "row_count",
                        "row_fingerprints",
                        "collected_at_utc",
                    )
                ):
                    raise FreezeError("history_chain_invalid")
                intent_path = history._child(cache_root, chunk["intent_path"], repository_root)
                intent = json.loads(bound(intent_path, chunk["intent_sha256"], "MARKET"))
                manifest_path = history._child(cache_root, chunk["manifest_path"], repository_root)
                manifest = json.loads(bound(manifest_path, chunk["manifest_hash"], "MARKET"))
                chunk_id = f"{symbol.lower()}-{ordinal:06d}"
                source = {
                    "chunk_id": chunk_id,
                    "symbol": symbol,
                    "exchange": target["exchange"],
                    "manifest_market_relative_path": manifest_path.relative_to(market).as_posix(),
                    "manifest_sha256": chunk["manifest_hash"],
                    "raw_sha256": chunk["raw_sha256"],
                    "observed_at_utc": chunk["collected_at_utc"],
                    "seed": chunk["seed"],
                    "producer_source_pins": intent["source_pins"],
                }
                chunks.append(source)
                raw_doc = manifest["files"]["raw_daily_rows"]
                if raw_doc is None:
                    continue
                raw_path = history._child(manifest_path.parent, raw_doc["path"], repository_root)
                raw = bound(raw_path, chunk["raw_sha256"], "MARKET")
                reader = csv.DictReader(io.StringIO(gzip.decompress(raw).decode(), newline=""))
                for row in reader:
                    session_date = row["session_date"]
                    if session_date not in expected_dates:
                        raise FreezeError("off_calendar_source_date")
                    if session_date not in rows_by_date:
                        rows_by_date[session_date] = (
                            symbol,
                            target["exchange"],
                            session_date,
                            row["open"],
                            row["close"],
                            chunk_id,
                        )
            actual_dates = set(rows_by_date)
            rows_by_asset[symbol] = tuple(rows_by_date[d] for d in sorted(rows_by_date))
            coverage[symbol] = {
                "expected_session_count": len(sessions),
                "price_row_count": len(actual_dates),
                "oldest_date": min(actual_dates) if actual_dates else None,
                "newest_date": max(actual_dates) if actual_dates else None,
                "missing_session_count": len(expected_dates - actual_dates),
                "missing_session_dates": sorted(expected_dates - actual_dates),
                "cursor": target["cursor"],
                "collection_state": target["state"],
            }

        def reattest():
            if _pins(repository_root) != pins:
                raise FreezeError("source_code_changed")
            for item in tuple(bindings.values()):
                base = market if item["root"] == "MARKET" else artifacts
                bound(
                    history._child(base, item["path"], repository_root),
                    item["sha256"],
                    item["root"],
                )

        reattest()
        output_root.parent.mkdir(parents=True, exist_ok=True)
        stage = output_root.parent / f".stage-{uuid.uuid4().hex}"
        stage.mkdir()
        output_files = {}
        for symbol, rows in rows_by_asset.items():
            buffer = io.StringIO(newline="")
            writer = csv.writer(buffer, lineterminator="\n")
            writer.writerow(COLUMNS)
            writer.writerows(rows)
            payload = gzip.compress(buffer.getvalue().encode(), mtime=0)
            if history.private_daily_cache_would_cross_free_space_floor(
                cache_root=output_root, repo_root=repository_root, projected_bytes=len(payload)
            ):
                raise FreezeError("storage_floor")
            name = f"{symbol.lower()}-price-only.csv.gz"
            digest = probe._write_new(stage / name, payload)
            output_files[symbol] = {
                "market_relative_path": (output_root / name).relative_to(market).as_posix(),
                "sha256": digest,
                "size_bytes": len(payload),
                "row_count": len(rows),
            }
        commitment = {
            "kind": VERSION,
            "goal": history.GOAL,
            "run_label": run_label,
            "history_receipt_sha256": history_sha256,
            "freeze_contract_sha256": freeze_contract_hash,
            "source_pins": pins,
            "source_bindings": list(bindings.values()),
            "calendar_sha256": calendar_sha256,
            "calendar_attestation_owned_by": "caller",
            "window": {"start": "2007-08-21", "end": "2026-10-07"},
            "coverage": coverage,
            "chunks": chunks,
            "price_only_files": output_files,
            "shared_observed_session_count": len(
                set.intersection(*(set(row[2] for row in rows) for rows in rows_by_asset.values()))
            ),
            "no_date_fill": True,
            "adjustment_mode": "MODP0_opaque",
            "qualification": "not_claimed",
            "vintage_contract": "One commitment identity; distinct per-chunk observation times.",
            "limitations": [
                "Caller attests the full NYSE calendar; freezer does not acquire or certify it.",
                "Price only; no adjusted/dividend/total-return/PIT/finality claim.",
                "Indexed available rows only; missing sessions explicit, never imputed.",
                "Stored proofs attest byte/structural consistency, not source authenticity.",
            ],
        }
        commitment["commitment_id"] = probe._sha(
            json.dumps(commitment, sort_keys=True, separators=(",", ":")).encode()
        )
        manifest_hash = probe._write_json(stage / "manifest.json", commitment)
        reattest()
        os.rename(stage, output_root)
        stage = None
        reattest()
        commitment_hash = probe._write_json(artifact_dir / "input-commitment.json", commitment)
        return {
            "status": "available" if any(rows_by_asset.values()) else "input_unavailable",
            "commitment_path": str(artifact_dir / "input-commitment.json"),
            "commitment_sha256": commitment_hash,
            "commitment_id": commitment["commitment_id"],
            "market_manifest_sha256": manifest_hash,
            "coverage": coverage,
        }
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        allowed = {
            "source_path_invalid",
            "source_hash_mismatch",
            "history_chain_invalid",
            "off_calendar_source_date",
            "source_code_changed",
            "storage_floor",
        }
        reason = (
            str(error)
            if isinstance(error, FreezeError) and str(error) in allowed
            else "source_chain_unavailable"
        )
        probe._write_json(
            artifact_dir / "failure.json",
            {
                "status": "input_unavailable",
                "reason": reason,
                "freeze_contract_sha256": freeze_contract_hash,
                "source_pins": pins,
            },
        )
        return {"status": "input_unavailable", "reason": reason}
    finally:
        # Only this invocation's freshly created staging directory is cleaned up.
        if stage is not None:
            resolved = stage.resolve()
            if (
                resolved.parent != output_root.parent.resolve()
                or stage.is_symlink()
                or not stage.name.startswith(".stage-")
            ):
                raise FreezeError("staging_path_invalid")
            for child in stage.rglob("*"):
                if child.is_symlink() or not child.resolve().is_relative_to(resolved):
                    raise FreezeError("staging_path_invalid")
            shutil.rmtree(stage)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-receipt", required=True, type=Path)
    parser.add_argument("--history-sha256", required=True)
    parser.add_argument("--calendar", required=True, type=Path)
    parser.add_argument("--calendar-sha256", required=True)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--market-root", type=Path, default=Path("D:/market_data"))
    parser.add_argument(
        "--artifact-root", type=Path, default=Path("D:/thericher-v2/model-artifacts")
    )
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--seed-source-root", type=Path)
    args = parser.parse_args(argv)
    try:
        result = freeze_input(
            history_receipt=args.history_receipt,
            history_sha256=args.history_sha256,
            calendar_path=args.calendar,
            calendar_sha256=args.calendar_sha256,
            market_root=args.market_root,
            artifact_root=args.artifact_root,
            repository_root=args.repository_root,
            run_label=args.run_label,
            seed_source_root=args.seed_source_root,
        )
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        result = {"status": "input_unavailable", "reason": "source_chain_unavailable"}
    projection = dict(result)
    if "coverage" in result:
        projection["coverage"] = {
            symbol: {
                field: coverage[field]
                for field in (
                    "expected_session_count",
                    "price_row_count",
                    "oldest_date",
                    "newest_date",
                    "missing_session_count",
                )
            }
            for symbol, coverage in result["coverage"].items()
        }
    print(json.dumps(projection, sort_keys=True))
    return 0 if result["status"] == "available" else 20


if __name__ == "__main__":
    raise SystemExit(main())
