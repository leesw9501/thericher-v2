from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.data import firstrate_source_semantics as semantics


def test_retrieves_rereads_and_retains_only_source_safe_semantics(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return _pages()[url]

    result = semantics.retrieve_firstrate_source_semantics(
        artifact_root=artifact_root,
        fetch=fetch,
        now=datetime(2026, 8, 19, 0, 0, tzinfo=UTC),
    )

    assert result == {
        "status": "completed",
        "receipt_path_relative_to_artifact_root": (
            "data-receipts/firstrate-free-intraday/"
            "firstrate-source-semantics-retrieval-v1.json"
        ),
        "source_count": 2,
    }
    assert calls == [
        "https://firstratedata.com/free-intraday-data",
        "https://firstratedata.com/free-intraday-data",
        "https://firstratedata.com/about/license",
        "https://firstratedata.com/about/license",
    ]
    receipt = _receipt(artifact_root)
    assert receipt["status"] == "completed"
    assert [fact["status"] for fact in receipt["facts"]] == [
        "confirmed",
        "not_disclosed",
        "not_disclosed",
        "confirmed",
        "confirmed",
        "confirmed",
    ]
    assert all(source["reread_hash_matches"] is True for source in receipt["sources"])
    assert receipt["safety"] == {
        "credentials_read": False,
        "official_no_auth_network_access_only": True,
        "market_data_acquired": False,
        "raw_market_rows_retained_in_receipt": False,
        "raw_page_body_retained_in_receipt": False,
        "kis_or_broker_called": False,
        "model_or_gpu_used": False,
        "git_tracked_files_changed": False,
    }
    assert "<html" not in json.dumps(receipt).lower()


def test_missing_statement_or_unstable_reread_is_source_unverified(tmp_path: Path) -> None:
    pages = _pages()
    pages["https://firstratedata.com/free-intraday-data"] = pages[
        "https://firstratedata.com/free-intraday-data"
    ].replace(b"All datasets are in US Eastern Time (ie New York time)", b"")

    first = semantics.retrieve_firstrate_source_semantics(
        artifact_root=tmp_path / "missing",
        fetch=pages.__getitem__,
        now=datetime(2026, 8, 19, 0, 0, tzinfo=UTC),
    )

    assert first["status"] == "source_unverified"
    assert _receipt(tmp_path / "missing")["facts"] == [
        {
            "fact": "official_source_retrieval",
            "status": "source_unverified",
            "interpretation": "no FirstRate data-contract limit changed",
        }
    ]

    calls = 0

    def unstable_fetch(url: str) -> bytes:
        nonlocal calls
        calls += 1
        if url.endswith("free-intraday-data") and calls == 2:
            return pages[url] + b"changed"
        return pages[url]

    second = semantics.retrieve_firstrate_source_semantics(
        artifact_root=tmp_path / "unstable",
        fetch=unstable_fetch,
        now=datetime(2026, 8, 19, 0, 0, tzinfo=UTC),
    )

    assert second["status"] == "source_unverified"


def test_idempotent_when_reread_semantics_match(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    first = semantics.retrieve_firstrate_source_semantics(
        artifact_root=artifact_root,
        fetch=_pages().__getitem__,
        now=datetime(2026, 8, 19, 0, 0, tzinfo=UTC),
    )
    second = semantics.retrieve_firstrate_source_semantics(
        artifact_root=artifact_root,
        fetch=_pages().__getitem__,
        now=datetime(2026, 8, 19, 0, 1, tzinfo=UTC),
    )

    assert second == first
    assert _receipt(artifact_root)["retrieved_at_utc"] == "2026-08-19T00:00:00+00:00"


def test_resolves_review_limits_without_rewriting_source_receipt(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    semantics.retrieve_firstrate_source_semantics(
        artifact_root=artifact_root,
        fetch=_pages().__getitem__,
        now=datetime(2026, 8, 19, 0, 0, tzinfo=UTC),
    )
    source_path = (
        artifact_root
        / "data-receipts"
        / "firstrate-free-intraday"
        / "firstrate-source-semantics-retrieval-v1.json"
    )
    source_before = source_path.read_bytes()

    result = semantics.resolve_firstrate_source_semantics(
        artifact_root=artifact_root,
        now=datetime(2026, 8, 19, 0, 1, tzinfo=UTC),
    )

    assert result == {
        "status": "completed",
        "receipt_path_relative_to_artifact_root": (
            "data-receipts/firstrate-free-intraday/"
            "firstrate-source-semantics-interpretation-v1.json"
        ),
    }
    interpretation = json.loads(
        (
            artifact_root
            / "data-receipts"
            / "firstrate-free-intraday"
            / "firstrate-source-semantics-interpretation-v1.json"
        ).read_text(encoding="utf-8")
    )
    assert interpretation["claude_challenge"]["verdict"] == "supported-with-limits"
    assert [fact["status"] for fact in interpretation["facts"]] == [
        "confirmed_vendor_declared",
        "not_disclosed",
        "not_disclosed",
        "confirmed_vendor_declared",
        "confirmed_catalog_offer_only",
        "conservative_project_policy",
    ]
    assert source_path.read_bytes() == source_before


def test_resolution_rejects_incomplete_source_receipt(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    semantics.retrieve_firstrate_source_semantics(
        artifact_root=artifact_root,
        fetch=_pages().__getitem__,
        now=datetime(2026, 8, 19, 0, 0, tzinfo=UTC),
    )
    source_path = (
        artifact_root
        / "data-receipts"
        / "firstrate-free-intraday"
        / "firstrate-source-semantics-retrieval-v1.json"
    )
    receipt = json.loads(source_path.read_text(encoding="utf-8"))
    receipt["status"] = "source_unverified"
    source_path.write_text(
        json.dumps(receipt, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not a completed retrieval"):
        semantics.resolve_firstrate_source_semantics(artifact_root=artifact_root)


def test_rejects_repository_and_outside_receipt_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="artifact_root must stay outside Git"):
        semantics.retrieve_firstrate_source_semantics(
            artifact_root=Path(__file__).parents[1], fetch=_pages().__getitem__
        )

    with pytest.raises(ValueError, match="receipt_path must stay under its external root"):
        semantics.retrieve_firstrate_source_semantics(
            artifact_root=tmp_path / "artifacts",
            receipt_path=Path(__file__),
            fetch=_pages().__getitem__,
        )


def test_rejects_non_official_fetch_url() -> None:
    with pytest.raises(ValueError, match="official FirstRate URL is invalid"):
        semantics._fetch_official_page("https://example.com/free-intraday-data")


def _receipt(artifact_root: Path) -> dict[str, object]:
    return json.loads(
        (
            artifact_root
            / "data-receipts"
            / "firstrate-free-intraday"
            / "firstrate-source-semantics-retrieval-v1.json"
        ).read_text(encoding="utf-8")
    )


def _pages() -> dict[str, bytes]:
    return {
        "https://firstratedata.com/free-intraday-data": b"""
            <html><body>
            For backtesting and analysis purposes we offer 1 year of free intraday
            data for our most popular datasets.
            All data are 1-minute intraday bars (format : timestamp,open,high,low,close,volume)
            Note : Zero volume bars are not included therefore gaps in the sequence
            are periods with no trading.
            All datasets are in US Eastern Time (ie New York time)
            SPY (SPDR S&amp;P 500)
            QQQ (Invesco QQQ Trust)
            </body></html>
        """,
        "https://firstratedata.com/about/license": b"""
            <html><body>
            the Data is for the private use of the Subscriber only.
            create derivative works, including, but not limited to, incorporating the
            Data into its internal models, published market research, or published
            academic research papers.
            not to resell or otherwise redistribute the Data as part of a commercial
            agreement with other third-parties.
            </body></html>
        """,
    }
