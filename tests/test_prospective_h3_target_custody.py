import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

import pytest

from thericher_v2.data.kis_paper_h3_daily_panel import NET25_H3_AXIS, H3DailyPanelPlan
from thericher_v2.data.kis_paper_h3_producer import (
    CAPTURE_CLOSES_UTC,
    CAPTURE_OPENS_UTC,
    INPUT_HARD_STOP_UTC,
)
from thericher_v2.execution.kis_paper_data_capture import CaptureResult
from thericher_v2.research import prospective_h3_target_custody as target

TICK = timedelta(microseconds=1)
RELEASE = datetime(2026, 12, 28, 21, 15, tzinfo=UTC)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def run(tmp_path):
    pins = target.Nov30H3TargetPins(
        owner="invented-dec3-capture",
        source_sha256="1" * 64,
        attempt_sha256="2" * 64,
        market_root=tmp_path / "market",
        artifact_root=tmp_path / "artifact",
        target_root=tmp_path / "target",
        prebound_at=datetime(2026, 12, 3, 20, tzinfo=UTC),
        release_at=RELEASE,
        synthetic=True,
    )
    prebind = pins.prebind_sha256
    plan = H3DailyPanelPlan(NET25_H3_AXIS)
    state = {
        "version": "kis-paper-data-capture-v1",
        "GET": 19,
        "POST": 1,
        "retry": 0,
        "pending": None,
        "started_utc": CAPTURE_OPENS_UTC.isoformat(),
        "failed_attempts": [],
        "contract": dict(
            market_root=str(pins.market_root),
            artifact_root=str(pins.artifact_root),
            queries=[q.document() for q in plan.queries],
        ),
        "completed": {
            q.key: asdict(
                CaptureResult(
                    q.key,
                    "ACCEPTED",
                    row_count=60,
                    native=dict(
                        path=str(pins.market_root / f"GET-{i:06d}.native.json"),
                        sha256=sha(f"invented page {i}".encode()),
                    ),
                )
            )
            for i, q in enumerate(plan.queries, 1)
        },
    }
    pins.artifact_root.mkdir()
    # No market root or feature READY exists: the custody path only opens metadata.
    return pins, prebind, state


def save_state(pins, state):
    raw = json.dumps(state, sort_keys=True, indent=2).encode("ascii")
    (pins.artifact_root / "capture-state.json").write_bytes(raw)
    return sha(raw)


def write(run, **changes):
    pins, prebind, state = run
    options = dict(
        prebind_sha256=prebind,
        capture_state_sha256=save_state(pins, state),
        capture_closed_at=CAPTURE_CLOSES_UTC - TICK,
        clock=lambda: CAPTURE_CLOSES_UTC,
    )
    return target.write_nov30_h3_target_custody(pins, **(options | changes))


def read(run, digest, **changes):
    pins, prebind, _ = run
    options = dict(prebind_sha256=prebind, expected_sha256=digest, now=RELEASE)
    return target.read_nov30_h3_target_custody(pins, **(options | changes))


def test_exact_metadata_roundtrip_and_exclusive_write(run):
    pins, _, _ = run
    digest = write(run)
    receipt = pins.target_root / "TARGET-CUSTODY.json"
    raw = receipt.read_bytes()
    assert sha(raw) == digest
    result = read(run, digest)
    assert result.capture_closed_at == CAPTURE_CLOSES_UTC - TICK
    assert result.sealed_at == CAPTURE_CLOSES_UTC
    assert result.capture_state_sha256 == sha(
        (pins.artifact_root / "capture-state.json").read_bytes()
    )
    assert list(pins.target_root.iterdir()) == [receipt]
    assert not pins.market_root.exists()
    assert set(json.loads(raw)) == {
        "schema",
        "cohort",
        "prebind_sha256",
        "capture_state_sha256",
        "capture_closed_at",
        "sealed_at",
    }
    with pytest.raises(FileExistsError):
        write(run)
    assert receipt.read_bytes() == raw


def test_early_read_denied_before_any_file_access(run, monkeypatch):
    def forbidden(*args):
        pytest.fail("early custody file access")

    monkeypatch.setattr(target, "_read_native", forbidden)
    for now in (RELEASE - TICK, RELEASE.replace(tzinfo=None)):
        with pytest.raises(ValueError, match="h3_target_release_denied"):
            read(run, "0" * 64, now=now)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("owner", "substituted-owner"),
        ("source_sha256", "a" * 64),
        ("attempt_sha256", "a" * 64),
        ("synthetic", False),
        ("release_at", RELEASE + TICK),
    ],
)
def test_wrong_prebind_cannot_seal(run, field, value):
    pins, prebind, state = run
    with pytest.raises(ValueError, match="h3_target_prebind_mismatch"):
        write((replace(pins, **{field: value}), prebind, state))
    assert not pins.target_root.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("prebound_at", datetime(2026, 12, 3, 21, tzinfo=UTC)),
        ("release_at", datetime(2026, 12, 28, 21, tzinfo=UTC) - TICK),
    ],
)
def test_pin_rejects_ineligible_clocks(run, field, value):
    with pytest.raises(ValueError, match="h3_target_pin_clock_invalid"):
        _ = replace(run[0], **{field: value}).prebind_sha256


@pytest.mark.parametrize(
    ("closed", "sealed"),
    [
        (CAPTURE_OPENS_UTC - TICK, CAPTURE_OPENS_UTC),
        (CAPTURE_CLOSES_UTC, CAPTURE_CLOSES_UTC),
        (CAPTURE_CLOSES_UTC - TICK, CAPTURE_CLOSES_UTC - 2 * TICK),
        (CAPTURE_CLOSES_UTC - TICK, INPUT_HARD_STOP_UTC),
    ],
)
def test_seal_rejects_wrong_window(run, closed, sealed):
    with pytest.raises(ValueError, match="h3_target_seal_clock_invalid"):
        write(run, capture_closed_at=closed, clock=lambda: sealed)
    assert not run[0].target_root.exists()


def test_hard_stop_crossed_during_write_consumes_destination(run):
    instants = iter((INPUT_HARD_STOP_UTC - TICK, INPUT_HARD_STOP_UTC))
    with pytest.raises(ValueError, match="h3_target_seal_clock_invalid"):
        write(run, clock=lambda: next(instants))
    with pytest.raises(FileExistsError):
        write(run)


@pytest.mark.parametrize("fault", ["mode", "identity", "pending", "count", "member", "start"])
def test_wrong_native_contract_rejected_even_at_matching_digest(run, fault):
    _, _, state = run
    first = state["contract"]["queries"][0]
    if fault == "mode":
        first["parameters"]["MODP"] = "0"
    elif fault == "identity":
        first.pop("require_response_rsym")
    elif fault == "pending":
        state["pending"] = {"method": "GET"}
    elif fault == "count":
        state["POST"] = True
    elif fault == "member":
        next(iter(state["completed"].values()))["native"]["path"] += ".substitute"
    else:
        state["started_utc"] = CAPTURE_CLOSES_UTC.isoformat()
    with pytest.raises(ValueError, match="h3_target_capture_"):
        write(run)
    assert not run[0].target_root.exists()


def test_reader_needs_exact_attested_seal_and_unchanged_state(run):
    pins, _, state = run
    digest = write(run)
    with pytest.raises(ValueError, match="h3_target_seal_digest_mismatch"):
        read(run, "a" * 64)
    state["GET"] = 0
    save_state(pins, state)
    with pytest.raises(ValueError, match="h3_target_capture_digest_mismatch"):
        read(run, digest)


def test_reader_rejects_noncanonical_seal_even_with_matching_hash(run):
    digest = write(run)
    receipt = run[0].target_root / "TARGET-CUSTODY.json"
    raw = receipt.read_bytes()
    assert sha(raw) == digest
    raw += b" "
    receipt.write_bytes(raw)
    with pytest.raises(ValueError, match="h3_target_seal_binding_mismatch"):
        read(run, sha(raw))
