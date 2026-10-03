from __future__ import annotations

import importlib.util
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import thericher_v2.execution.kis_private_intraday_backfill as collector
from thericher_v2.execution.kis_market_data import (
    KisMarketDataResponse,
    KisPaperMarketDataClient,
    KisPaperMarketDataConfig,
    KisPaperMarketDataError,
    KisPaperMinutePage,
    KisPaperMinuteQuery,
    KisPaperMinuteRawBar,
)


@pytest.fixture
def scope(tmp_path, monkeypatch):
    root = tmp_path / "market-data/us_equities/kis_paper_private/intraday-dated/qqq-20260901"
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(collector, "KIS_PAPER_QQQ_DATED_CACHE_ROOT", root)
    return root, repo


def rows(start="0800", count=480):
    stamp = datetime.strptime("20260901" + start, "%Y%m%d%H%M")
    result = []
    for i in range(count):
        exchange = stamp + timedelta(minutes=i)
        korea = exchange + timedelta(hours=13)
        result.append(
            KisPaperMinuteRawBar(
                exchange_date=exchange.strftime("%Y%m%d"),
                exchange_time=exchange.strftime("%H%M%S"),
                korea_date=korea.strftime("%Y%m%d"),
                korea_time=korea.strftime("%H%M%S"),
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                last=Decimal("100"),
                volume=Decimal("10"),
            )
        )
    return tuple(result)


class Client:
    def __init__(self, pages, root=None):
        self.pages = list(pages)
        self.queries = []
        self.root = root

    def fetch_minute_page(self, query, *, before_request=None):
        if self.root and not self.queries:
            state = json.loads((self.root / "v1/index.json").read_text())["targets"][0]
            assert state["next_cursor"]["keyb"] == query.continuation_key
        self.queries.append(query)
        if before_request:
            before_request()
        value = self.pages.pop(0)
        if isinstance(value, BaseException):
            raise value
        return KisPaperMinutePage(query=query, bars=value, next_cursor=None, more="0")


def pages(source=None):
    source = rows() if source is None else source
    return [source[360:], source[240:360], source[120:240], source[:120]]


def run(scope, client, **kwargs):
    root, repo = scope
    return collector.run_kis_paper_qqq_dated_session_cycle(
        client=client,
        cache_root=root,
        repo_root=repo,
        code_revision="synthetic",
        observed_at=datetime(2026, 10, 3, tzinfo=UTC),
        sleeper=lambda _: None,
        monotonic_clock=lambda: 0.0,
        **kwargs,
    )


def complete(scope):
    return collector.kis_paper_qqq_dated_session_complete(cache_root=scope[0], repo_root=scope[1])


def test_four_full_terminal_pages_are_exactly_complete_and_never_restart(scope):
    client = Client(pages(), scope[0])
    result = run(scope, client)
    assert result.row_count == 480 and result.status == "collected" and complete(scope)
    assert [q.continuation_key for q in client.queries] == [
        "20260901155900",
        "20260901135900",
        "20260901115900",
        "20260901095900",
    ]
    assert all(q.include_previous_day and q.continuation_next == "1" for q in client.queries)
    index = json.loads((scope[0] / "v1/index.json").read_text())
    assert len(index["targets"]) == 1
    assert index["targets"][0]["next_cursor"]["keyb"] == "20260901075900"
    assert index["targets"][0]["last_reason"] != "source_exhausted"
    repeated = Client([])
    assert run(scope, repeated).reason == "dated_session_complete"
    assert repeated.queries == []


def test_interior_missing_minute_cannot_complete_or_restart_from_head(scope):
    source = list(rows())
    source[180] = rows("0759", 1)[0]
    run(scope, Client(pages(tuple(source))))
    assert not complete(scope)
    client = Client([])
    assert run(scope, client).reason == "dated_session_incomplete"
    assert client.queries == []


@pytest.mark.parametrize("bad", ["latest", "mixed", "overlap", "wrong_symbol", "empty"])
def test_bad_later_page_keeps_exact_prefix_and_its_frontier(scope, bad):
    source = pages()
    invalid = source[1]
    if bad == "latest":
        invalid = tuple(replace(row, exchange_date="20261002") for row in invalid)
    elif bad == "mixed":
        invalid = (*invalid[:-1], replace(invalid[-1], exchange_date="20260831"))
    elif bad == "overlap":
        invalid = source[0]
    elif bad == "empty":
        invalid = ()
    client = Client([source[0], invalid])
    if bad == "wrong_symbol":
        original = client.fetch_minute_page

        def fetch(query, **kwargs):
            page = original(query, **kwargs)
            return replace(page, query=KisPaperMinuteQuery(exchange="AMS", symbol="SPY"))

        client.fetch_minute_page = fetch
    result = run(scope, client)
    expected = 0 if bad == "wrong_symbol" else 120
    assert result.row_count == expected
    assert result.status == ("rejected" if expected == 0 else "partial")
    assert not complete(scope)
    state = json.loads((scope[0] / "v1/index.json").read_text())["targets"][0]
    assert state["next_cursor"]["keyb"] == ("20260901135900" if expected else "20260901155900")


def test_budgeted_prefix_resumes_own_frontier_only(scope):
    source = pages()
    run(scope, Client(source[:2]), pages=2)
    assert not complete(scope)
    second = Client(source[2:], scope[0])
    run(scope, second, pages=2)
    assert second.queries[0].continuation_key == "20260901115900"
    assert complete(scope)


@pytest.mark.parametrize("field", ["continuation_key", "continuation_next", "include_previous_day"])
def test_page_request_metadata_cannot_be_rebound(scope, field):
    client = Client(pages())
    original = client.fetch_minute_page

    def fetch(query, **kwargs):
        page = original(query, **kwargs)
        if len(client.queries) == 2:
            changes = {
                "continuation_key": "20260901120000",
                "continuation_next": None,
                "include_previous_day": False,
            }
            if field == "continuation_next":
                changed = replace(query, continuation_next=None, continuation_key=None)
            else:
                changed = replace(query, **{field: changes[field]})
            return replace(page, query=changed)
        return page

    client.fetch_minute_page = fetch
    result = run(scope, client)
    assert result.status == "partial" and result.row_count == 120
    assert result.reason == "minute_response_invalid" and not complete(scope)


@pytest.mark.parametrize("bad", ["unseeded", "reseeded", "wrong_date", "head_chunk"])
def test_existing_index_custody_cannot_be_reset_or_repurposed(scope, bad):
    run(scope, Client(pages()[:1]), pages=1)
    path = scope[0] / "v1/index.json"
    document = json.loads(path.read_text())
    state = document["targets"][0]
    if bad == "head_chunk":
        state["chunks"][0]["collection_scope"] = "head"
    else:
        state["next_cursor"] = {
            "unseeded": None,
            "reseeded": {"next": "1", "keyb": "20260901155900"},
            "wrong_date": {"next": "1", "keyb": "20260831135900"},
        }[bad]
    path.write_text(json.dumps(document))
    before = path.read_bytes()
    client = Client([])
    with pytest.raises(ValueError, match="dated-session"):
        run(scope, client)
    assert client.queries == [] and path.read_bytes() == before


def test_short_page_or_empty_is_not_a_provider_history_floor(scope):
    client = Client([rows("1550", 10)])
    result = run(scope, client)
    assert result.status == "collected" and not complete(scope)
    assert len(client.queries) == 1
    second = Client([()])
    result = run(scope, second)
    assert second.queries[0].continuation_key == "20260901154900"
    assert result.status == "rejected" and result.reason == "minute_response_empty"
    state = json.loads((scope[0] / "v1/index.json").read_text())["targets"][0]
    assert state["last_reason"] == "minute_response_empty"
    assert state["next_cursor"]["keyb"] == "20260901154900"


def test_snapshot_publication_crash_recovers_without_fetch_or_other_root_mutation(
    scope, monkeypatch
):
    unrelated = scope[0].parents[1] / "intraday/v1/index.json"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_bytes(b"untouched June cursor")
    head = scope[0].parents[1] / "intraday-head/v1/index.json"
    head.parent.mkdir(parents=True)
    head.write_bytes(b"untouched current head")
    original = collector._write_index

    def fail_after_snapshot(*, root, index, **kwargs):
        if index["generation"] == 1:
            raise OSError("synthetic publication crash")
        return original(root=root, index=index, **kwargs)

    monkeypatch.setattr(collector, "_write_index", fail_after_snapshot)
    with pytest.raises(OSError, match="publication crash"):
        run(scope, Client(pages()))
    assert json.loads((scope[0] / "v1/index.json").read_text())["targets"][0]["next_cursor"] == {
        "next": "1",
        "keyb": "20260901155900",
    }
    monkeypatch.setattr(collector, "_write_index", original)
    client = Client([])
    assert run(scope, client).status == "recovered"
    assert not client.queries and complete(scope)
    assert unrelated.read_bytes() == b"untouched June cursor"
    assert head.read_bytes() == b"untouched current head"


def test_initial_cursor_write_crash_never_fetches_and_recreates_only_original_seed(
    scope, monkeypatch
):
    original = collector._write_index
    monkeypatch.setattr(collector, "_write_index", lambda **_: (_ for _ in ()).throw(OSError()))
    client = Client([])
    with pytest.raises(OSError):
        run(scope, client)
    assert not client.queries
    monkeypatch.setattr(collector, "_write_index", original)
    client = Client(pages(), scope[0])
    run(scope, client)
    assert client.queries[0].continuation_key == "20260901155900"


@pytest.mark.parametrize("kind", ["head", "june", "workspace", "outside", "date", "pages", "bool"])
def test_invalid_binding_fails_before_client_or_cache_creation(scope, kind):
    root, repo = scope
    kwargs = {"cache_root": root, "repo_root": repo, "session_date": date(2026, 9, 1), "pages": 4}
    if kind in {"head", "june", "outside", "workspace"}:
        kwargs["cache_root"] = repo / "cache" if kind == "workspace" else root.parent / kind
    elif kind == "date":
        kwargs["session_date"] = date(2026, 8, 3)
    else:
        kwargs["pages"] = True if kind == "bool" else 5
    with pytest.raises(ValueError):
        collector.run_kis_paper_qqq_dated_session_cycle(
            client=Client([]),
            code_revision="synthetic",
            **kwargs,
        )
    assert not root.exists()


def test_reparse_ancestor_rejected_before_io(scope, monkeypatch):
    scope[0].mkdir(parents=True)
    original = Path.lstat

    class Reparse:
        st_file_attributes = 0x400

    def lstat(path, *args, **kwargs):
        return Reparse() if path == scope[0].parent else original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", lstat)
    original_iterdir = Path.iterdir

    def iterdir(path):
        if path == scope[0]:
            pytest.fail("must not traverse through a reparse ancestor")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    with pytest.raises(ValueError, match="path is invalid"):
        run(scope, Client([]))
    assert not (scope[0] / "v1").exists()


def script():
    path = Path(__file__).parents[1] / "scripts/backfill_kis_paper_qqq_dated_session.py"
    spec = importlib.util.spec_from_file_location("dated_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preview_performs_no_filesystem_or_credentials_io(monkeypatch, capsys):
    cli = script()

    def forbidden(*args, **kwargs):
        raise AssertionError("preview IO")

    monkeypatch.setattr(cli, "_load_paper_config", forbidden)
    monkeypatch.setattr(Path, "lstat", forbidden)
    monkeypatch.setattr(Path, "exists", forbidden)
    assert cli.main([]) == 0
    assert json.loads(capsys.readouterr().out)["max_gets"] == 4


def test_native_config_only_uses_approved_dotenv_whitelist(monkeypatch):
    cli = script()
    calls = []

    def load(path, *, environment):
        calls.append((path, environment))
        return KisPaperMarketDataConfig(app_key="synthetic", app_secret="synthetic")

    monkeypatch.setattr(cli, "load_kis_paper_market_data_config", load)
    cli._load_paper_config()
    assert calls == [(cli._REPO_ROOT / ".env", {})]


@pytest.mark.parametrize(
    "args",
    [
        ["--pages", "5"],
        ["--session-date", "2026-08-03"],
        ["--cache-root", "D:/market_data/us_equities/kis_paper_private/intraday"],
    ],
)
def test_cli_invalid_prefails_before_credentials(monkeypatch, args):
    cli = script()
    monkeypatch.setattr(cli, "_load_paper_config", lambda: pytest.fail("credentials"))
    with pytest.raises(SystemExit):
        cli.main(["--execute", "--code-revision", "synthetic", *args])


def test_real_client_one_token_four_gets_and_cli_safe_output(scope, monkeypatch, capsys):
    cli = script()
    source = pages()
    requests = []

    class Transport:
        def request(self, request):
            requests.append(request)
            if request.method == "POST":
                return KisMarketDataResponse.from_payload(
                    {"access_token": "synthetic-secret-token"}
                )
            return KisMarketDataResponse.from_payload(
                {
                    "rt_cd": "0",
                    "output1": {"next": "", "more": "0"},
                    "output2": [row.as_document() for row in source.pop(0)],
                }
            )

    transport = Transport()
    monkeypatch.setattr(cli, "KIS_PAPER_QQQ_DATED_CACHE_ROOT", scope[0])
    monkeypatch.setattr(cli, "_REPO_ROOT", scope[1])
    monkeypatch.setattr(
        cli,
        "_load_paper_config",
        lambda: KisPaperMarketDataConfig(app_key="synthetic-key", app_secret="synthetic-secret"),
    )
    monkeypatch.setattr(cli, "UrllibKisPaperMarketDataTransport", lambda **_: transport)
    monkeypatch.setattr(cli, "KisPaperMarketDataRateGate", lambda **_: None)
    monkeypatch.setattr(cli, "KisPaperMarketDataTokenStartGate", lambda **_: None)
    original = cli.run_kis_paper_qqq_dated_session_cycle
    monkeypatch.setattr(
        cli,
        "run_kis_paper_qqq_dated_session_cycle",
        lambda **kw: original(**kw, sleeper=lambda _: None, monotonic_clock=lambda: 0.0),
    )
    assert cli.main(["--execute", "--code-revision", "synthetic"]) == 0
    assert [request.method for request in requests] == ["POST", "GET", "GET", "GET", "GET"]
    output = capsys.readouterr().out
    assert json.loads(output)["regular_session_complete"] is True
    assert all(secret not in output for secret in ["synthetic-secret", '"open"', '"last"'])


def test_real_client_enforces_fifth_get_cap_without_transport():
    class Transport:
        def request(self, request):
            raise AssertionError("transport")

    client = KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="fake", app_secret="fake"),
        transport=Transport(),
        max_minute_page_attempts=4,
    )
    client._minute_page_attempts = 4
    with pytest.raises(KisPaperMarketDataError, match="minute_page_limit_exceeded"):
        client.fetch_minute_page(KisPaperMinuteQuery(exchange="NAS", symbol="QQQ"))


@pytest.mark.parametrize(
    "status,reason", [("rejected", "minute_response_empty"), ("locked", "worker_locked")]
)
def test_cli_preserves_nonretaining_reason_without_catalog_read(
    scope, monkeypatch, capsys, status, reason
):
    cli = script()
    monkeypatch.setattr(cli, "KIS_PAPER_QQQ_DATED_CACHE_ROOT", scope[0])
    monkeypatch.setattr(cli, "_REPO_ROOT", scope[1])
    monkeypatch.setattr(
        cli,
        "_load_paper_config",
        lambda: KisPaperMarketDataConfig(app_key="fake", app_secret="fake"),
    )
    monkeypatch.setattr(cli, "UrllibKisPaperMarketDataTransport", lambda **_: object())
    monkeypatch.setattr(cli, "KisPaperMarketDataRateGate", lambda **_: None)
    monkeypatch.setattr(cli, "KisPaperMarketDataTokenStartGate", lambda **_: None)
    result = collector.KisPaperPrivateIntradayBackfillRun(
        status=status,
        target_key="QQQ/NAS/1m",
        row_count=0,
        exact_overlap_rows=0,
        reason=reason,
    )
    monkeypatch.setattr(cli, "run_kis_paper_qqq_dated_session_cycle", lambda **_: result)
    monkeypatch.setattr(
        cli, "kis_paper_qqq_dated_session_complete", lambda **_: pytest.fail("catalog read")
    )
    assert cli.main(["--execute", "--code-revision", "synthetic"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "incomplete" and payload["reason"] == reason
    assert payload["regular_session_complete"] is False
