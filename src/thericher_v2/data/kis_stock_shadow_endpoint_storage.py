"""Bytes-only immutable endpoint records; callers own files, clocks and custody."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.execution.kis_market_data import (
    KisPaperDailyPage,
    KisPaperDailyRawPage,
    KisPaperDailyRawRow,
)

from . import kis_stock_shadow_endpoint as endpoint

ENDPOINT_WORKER_SHA256 = "sha256:54da0538dab04313bed80eaaa1ec704847f640b611e86735416f50b8ba5e654a"
LEG_DATES = {"entry": date(2026, 10, 12), "exit": date(2026, 10, 19)}
_RETRY = endpoint._YIELDS | {"provider_unavailable", "clock_invalid"}
_FAILURES = endpoint._PAGE_ERRORS | endpoint._YIELDS | {"provider_unavailable"}


class StorageError(ValueError):
    """Fixed categorical errors only; no supplied strings are interpolated."""


def _need(condition, code="record_invalid"):
    if not condition:
        raise StorageError(code)


def sha256(raw):
    _need(type(raw) is bytes)
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _pin(value):
    _need(
        type(value) is str and re.fullmatch(r"sha256:[a-f0-9]{64}", value) is not None,
        "binding_invalid",
    )


def _dump(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _load(raw):
    _need(type(raw) is bytes and len(raw) <= 4_000_000)

    def unique(pairs):
        result = {}
        for key, value in pairs:
            _need(key not in result)
            result[key] = value
        return result

    def invalid(value):
        raise StorageError("record_invalid")

    try:
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)
        _need(_dump(value) == raw, "noncanonical_record")
        return value
    except (ValueError, TypeError, UnicodeError, OverflowError):
        raise StorageError("record_invalid") from None


def _time(value):
    _need(
        type(value) is datetime and value.tzinfo is not None and value.utcoffset() is not None,
        "clock_invalid",
    )
    return value.astimezone(UTC).isoformat()


def _parse_time(value):
    _need(type(value) is str, "clock_invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise StorageError("clock_invalid") from None
    _need(_time(parsed) == value, "clock_invalid")
    return parsed


@dataclass(frozen=True, slots=True, repr=False)
class StorageBinding:
    scope: endpoint.EndpointScope
    leg: str
    source_contract_sha256: str
    source_pins: tuple[tuple[str, str], ...]

    def record(self):
        _need(
            type(self.scope) is endpoint.EndpointScope
            and type(self.leg) is str
            and self.leg in LEG_DATES,
            "binding_invalid",
        )
        try:
            peers = tuple(
                endpoint.EndpointPeer(p.key, p.symbol, p.exchange) for p in self.scope.peers
            )
            checked = endpoint.EndpointScope(
                peers,
                self.scope.expected_peer_sha256,
                self.scope.parent_seal_sha256,
                self.scope.session,
                self.scope.past_cutoff,
            )
        except Exception:
            raise StorageError("binding_invalid") from None
        _need(
            checked == self.scope and checked.session.session_date == LEG_DATES[self.leg],
            "binding_invalid",
        )
        _need(checked.past_cutoff < datetime(2026, 10, 12, 13, 30, tzinfo=UTC), "binding_invalid")
        _pin(self.source_contract_sha256)
        _need(type(self.source_pins) is tuple and bool(self.source_pins), "binding_invalid")
        pins = {}
        for item in self.source_pins:
            _need(type(item) is tuple and len(item) == 2, "binding_invalid")
            name, pin = item
            _need(
                type(name) is str
                and name
                and "\\" not in name
                and ":" not in name
                and not name.startswith("/")
                and all(p not in {"", ".", ".."} for p in name.split("/"))
                and name not in pins,
                "binding_invalid",
            )
            _pin(pin)
            pins[name] = pin
        _need(
            self.source_pins == tuple(sorted(pins.items()))
            and pins.get("endpoint_worker.py") == ENDPOINT_WORKER_SHA256,
            "binding_invalid",
        )
        return {
            "scope_sha256": checked.binding_sha256,
            "leg": self.leg,
            "session_date": checked.session.session_date.isoformat(),
            "open_at": _time(checked.session.open_at),
            "close_at": _time(checked.session.close_at),
            "past_cutoff": _time(checked.past_cutoff),
            "peer_sha256": checked.expected_peer_sha256,
            "parent_seal_sha256": checked.parent_seal_sha256,
            "source_contract_sha256": self.source_contract_sha256,
            "source_pins": pins,
        }


@dataclass(frozen=True, slots=True, repr=False)
class PageBytes:
    receipt: bytes
    payload: bytes


@dataclass(frozen=True, slots=True, repr=False)
class BatchBytes:
    receipt: bytes
    pages: tuple[PageBytes, ...]

    @property
    def receipt_sha256(self):
        return sha256(self.receipt)


@dataclass(frozen=True, slots=True, repr=False)
class EndpointReadback:
    binding: StorageBinding
    observations: tuple[endpoint.EndpointObservation, ...]
    next_index: int
    attempts: tuple[endpoint.EndpointBatch, ...]
    receipt_sha256s: tuple[str, ...]

    def safe_facts(self):
        return {
            "leg": self.binding.leg,
            "session_date": LEG_DATES[self.binding.leg].isoformat(),
            "peer_count": len(self.observations),
            "next_index": self.next_index,
            "available_count": sum(o.status == "available" for o in self.observations),
            "not_attempted_count": sum(o.status == "not_attempted" for o in self.observations),
            "endpoint_complete": all(o.status == "available" for o in self.observations),
            "missing_or_rejected_count": sum(
                o.status == "input_unavailable" for o in self.observations
            ),
            "attempt_receipt_count": len(self.attempts),
            "callback_attempts": sum(a.callback_attempts for a in self.attempts),
            "count_semantics": "callback entries; not measured wire starts",
            "receipt_sha256s": list(self.receipt_sha256s),
            "pit_or_finality_claimed": False,
        }


def _query(binding, position):
    query = binding.scope.query(position)
    return {
        "AUTH": "",
        "EXCD": query.exchange,
        "SYMB": query.symbol,
        "GUBN": "0",
        "BYMD": query.by_date,
        "MODP": "0",
        "tr_cont": "",
    }


def _observation(observation, position):
    return {
        "position": position,
        "status": observation.status,
        "reason": observation.reason,
        "request_entered_at": (
            _time(observation.request_entered_at)
            if observation.request_entered_at is not None
            else None
        ),
        "observed_at": (
            _time(observation.observed_at) if observation.observed_at is not None else None
        ),
    }


def _page(page, query):
    try:
        _need(
            type(page) is KisPaperDailyRawPage and type(page.page) is KisPaperDailyPage,
            "page_invalid",
        )
        _need(
            type(page.page.schema_version) is int
            and page.page.schema_version == SCHEMA_VERSION
            and type(page.page.required_ohlcv_fields_present) is bool
            and type(page.page.continuation_available) is bool
            and page.page.continuation_value in {None, "F"}
            and all(
                type(r.schema_version) is int and r.schema_version == SCHEMA_VERSION
                for r in page.rows
            ),
            "page_invalid",
        )
        return endpoint._validate_page(page, query)
    except Exception:
        raise StorageError("page_invalid") from None


def _validate_batch(binding, batch, start_index, completed_at, pages):
    _need(type(binding) is StorageBinding, "binding_invalid")
    record = binding.record()
    _need(type(batch) is endpoint.EndpointBatch and batch.scope == binding.scope, "batch_invalid")
    n, attempts = len(binding.scope.peers), batch.callback_attempts
    _need(
        type(start_index) is int
        and 0 <= start_index <= n
        and type(attempts) is int
        and 0 <= attempts <= n - start_index
        and type(batch.next_index) is int,
        "prefix_invalid",
    )
    _need(type(batch.observations) is tuple and len(batch.observations) == n, "batch_invalid")
    _time(completed_at)
    _need(
        batch.stop_reason is None
        or type(batch.stop_reason) is str
        and batch.stop_reason in _RETRY | {"endpoint_not_completed"},
        "batch_invalid",
    )
    expected_next = start_index + attempts - int(batch.stop_reason in _RETRY)
    _need(batch.next_index == expected_next and expected_next >= start_index, "prefix_invalid")
    used_pages, last_clock = set(), None
    for i, (peer, observation) in enumerate(
        zip(binding.scope.peers, batch.observations, strict=True)
    ):
        _need(
            type(observation) is endpoint.EndpointObservation and observation.key == peer.key,
            "observation_invalid",
        )
        _need(
            type(observation.status) is str
            and (observation.reason is None or type(observation.reason) is str)
            and type(observation.rows) is tuple,
            "observation_invalid",
        )
        attempted = start_index <= i < start_index + attempts
        if not attempted:
            _need(
                observation
                == endpoint.EndpointObservation(peer.key, "not_attempted", None, None, None),
                "prefix_invalid",
            )
            continue
        entered = observation.request_entered_at
        _time(entered)
        _need(
            binding.scope.session.close_at <= entered <= completed_at
            and (last_clock is None or entered >= last_clock),
            "clock_invalid",
        )
        last_clock = entered
        has_page = observation.status == "available" or observation.reason == "endpoint_missing"
        if has_page:
            _need(i in pages, "page_missing")
            raw_page = pages[i]
            try:
                selected, digest = _page(raw_page, binding.scope.query(i))
            except Exception:
                raise StorageError("page_invalid") from None
            expected_reason = None if selected is not None else "endpoint_missing"
            _need(
                observation.status == ("available" if selected is not None else "input_unavailable")
                and observation.reason == expected_reason
                and observation.rows == raw_page.rows
                and observation.endpoint_open == (selected.open if selected else None)
                and observation.canonical_rows_sha256 == digest,
                "observation_invalid",
            )
            _time(observation.observed_at)
            _need(entered <= observation.observed_at <= completed_at, "clock_invalid")
            last_clock = observation.observed_at
            used_pages.add(i)
        else:
            _need(
                observation.status == "input_unavailable"
                and observation.reason in _FAILURES
                and observation.observed_at is None
                and observation.rows == ()
                and observation.endpoint_open is None
                and observation.canonical_rows_sha256 is None,
                "observation_invalid",
            )
        if observation.reason in _RETRY:
            _need(
                i == start_index + attempts - 1 and batch.stop_reason == observation.reason,
                "prefix_invalid",
            )
    _need(set(pages) == used_pages, "page_binding_invalid")
    if batch.stop_reason in _RETRY:
        _need(batch.observations[expected_next].reason == batch.stop_reason, "prefix_invalid")
    return record


def dump_batch(binding, batch, *, pages_by_index, invocation_id, start_index, completed_at):
    """Return payload bytes for M and metadata receipt bytes for A; never write them."""
    _need(type(invocation_id) is str and re.fullmatch(r"[a-f0-9]{32}", invocation_id) is not None)
    _need(type(pages_by_index) is dict and all(type(i) is int for i in pages_by_index))
    record = _validate_batch(binding, batch, start_index, completed_at, pages_by_index)
    blobs, links = [], {}
    for i in sorted(pages_by_index):
        page = pages_by_index[i]
        payload = _dump([r.as_document() for r in page.rows])
        metadata = {
            name: getattr(page.page, name)
            for name in (
                "row_count",
                "newest_date",
                "oldest_date",
                "required_ohlcv_fields_present",
                "continuation_available",
                "continuation_value",
                "schema_version",
            )
        }
        receipt = _dump(
            {
                "kind": "endpoint_page",
                "version": 1,
                "binding": record,
                "invocation_id": invocation_id,
                "position": i,
                "peer_key": binding.scope.peers[i].key,
                "query": _query(binding, i),
                "metadata": metadata,
                "payload_sha256": sha256(payload),
                "observation": _observation(batch.observations[i], i),
            }
        )
        blobs.append(PageBytes(receipt, payload))
        links[i] = {"page_receipt_sha256": sha256(receipt), "payload_sha256": sha256(payload)}
    observations = [
        _observation(o, i) | links.get(i, {"page_receipt_sha256": None, "payload_sha256": None})
        for i, o in enumerate(batch.observations)
    ]
    receipt = _dump(
        {
            "kind": "endpoint_batch",
            "version": 1,
            "binding": record,
            "invocation_id": invocation_id,
            "start_index": start_index,
            "callback_attempts": batch.callback_attempts,
            "next_index": batch.next_index,
            "stop_reason": batch.stop_reason,
            "completed_at": _time(completed_at),
            "observations": observations,
        }
    )
    return BatchBytes(receipt, tuple(blobs))


def load_batch(binding, stored, *, receipt_sha256):
    """Strictly reconstruct typed observations, then round-trip the entire record."""
    _pin(receipt_sha256)
    _need(
        type(stored) is BatchBytes and sha256(stored.receipt) == receipt_sha256,
        "receipt_hash_mismatch",
    )
    try:
        doc = _load(stored.receipt)
        _need(doc["binding"] == binding.record(), "binding_invalid")
        _need(type(stored.pages) is tuple and len(stored.pages) <= endpoint.MAX_PEERS)
        pages, parsed = {}, {}
        for blob in stored.pages:
            _need(type(blob) is PageBytes)
            receipt, rows = _load(blob.receipt), _load(blob.payload)
            i = receipt["position"]
            _need(
                type(i) is int and 0 <= i < len(binding.scope.peers) and i not in pages,
                "page_binding_invalid",
            )
            _need(
                receipt["binding"] == binding.record()
                and receipt["invocation_id"] == doc["invocation_id"]
                and receipt["peer_key"] == binding.scope.peers[i].key
                and receipt["query"] == _query(binding, i)
                and receipt["payload_sha256"] == sha256(blob.payload),
                "page_binding_invalid",
            )
            _need(type(rows) is list and len(rows) <= 100, "page_invalid")
            typed = tuple(KisPaperDailyRawRow(**row) for row in rows)
            _need(_dump([r.as_document() for r in typed]) == blob.payload, "page_invalid")
            pages[i] = KisPaperDailyRawPage(
                KisPaperDailyPage(query=binding.scope.query(i), **receipt["metadata"]), typed
            )
            parsed[i] = receipt
        observations = []
        _need(
            type(doc["observations"]) is list
            and len(doc["observations"]) == len(binding.scope.peers),
            "observation_invalid",
        )
        for i, item in enumerate(doc["observations"]):
            entered = (
                _parse_time(item["request_entered_at"]) if item["request_entered_at"] else None
            )
            observed = _parse_time(item["observed_at"]) if item["observed_at"] else None
            selected, digest = (
                _page(pages[i], binding.scope.query(i)) if i in pages else (None, None)
            )
            observation = endpoint.EndpointObservation(
                binding.scope.peers[i].key,
                item["status"],
                item["reason"],
                entered,
                observed,
                pages[i].rows if i in pages else (),
                selected.open if selected else None,
                digest,
            )
            if i in parsed:
                _need(
                    parsed[i]["observation"] == _observation(observation, i)
                    and item["page_receipt_sha256"]
                    == sha256(stored.pages[list(pages).index(i)].receipt)
                    and item["payload_sha256"] == parsed[i]["payload_sha256"],
                    "page_binding_invalid",
                )
            observations.append(observation)
        batch = endpoint.EndpointBatch(
            binding.scope,
            tuple(observations),
            doc["callback_attempts"],
            doc["next_index"],
            doc["stop_reason"],
        )
        canonical = dump_batch(
            binding,
            batch,
            pages_by_index=pages,
            invocation_id=doc["invocation_id"],
            start_index=doc["start_index"],
            completed_at=_parse_time(doc["completed_at"]),
        )
        _need(canonical == stored, "record_invalid")
        return EndpointReadback(
            binding, batch.observations, batch.next_index, (batch,), (receipt_sha256,)
        )
    except StorageError:
        raise
    except Exception:
        raise StorageError("record_invalid") from None


def load_resume(binding, checkpoints, *, receipt_sha256s):
    """Keep immutable attempts; only a known yield permits retrying its same cursor."""
    _need(type(binding) is StorageBinding, "binding_invalid")
    binding.record()
    _need(
        type(checkpoints) is tuple
        and type(receipt_sha256s) is tuple
        and len(checkpoints) == len(receipt_sha256s) > 0,
        "resume_invalid",
    )
    observations = tuple(
        endpoint.EndpointObservation(p.key, "not_attempted", None, None, None)
        for p in binding.scope.peers
    )
    cursor, attempts, invocations, previous_completed = 0, [], set(), None
    for stored, pin in zip(checkpoints, receipt_sha256s, strict=True):
        read = load_batch(binding, stored, receipt_sha256=pin)
        doc = _load(stored.receipt)
        _need(
            doc["start_index"] == cursor and doc["invocation_id"] not in invocations,
            "resume_invalid",
        )
        invocations.add(doc["invocation_id"])
        completed = _parse_time(doc["completed_at"])
        _need(previous_completed is None or completed >= previous_completed, "clock_invalid")
        batch = read.attempts[0]
        if attempts and cursor < len(observations):
            existing = observations[cursor]
            _need(existing.status == "not_attempted" or existing.reason in _RETRY, "resume_invalid")
        for i in range(doc["start_index"], doc["start_index"] + batch.callback_attempts):
            observation = batch.observations[i]
            _need(
                previous_completed is None or observation.request_entered_at >= previous_completed,
                "clock_invalid",
            )
            observations = observations[:i] + (observation,) + observations[i + 1 :]
        attempts.append(batch)
        cursor, previous_completed = read.next_index, completed
    return EndpointReadback(binding, observations, cursor, tuple(attempts), receipt_sha256s)
