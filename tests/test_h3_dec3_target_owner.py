import hashlib
import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from test_kis_paper_h3_producer import dated_run as dated_run
from thericher_v2.ops import h3_dec3_target_owner as owner
from thericher_v2.research.prospective_h3_target_custody import read_nov30_h3_target_custody


@pytest.fixture
def invocation(dated_run, tmp_path):
    options, requests, set_clock = dated_run
    run = owner.Dec4H3Run(
        **{
            key: options.pop(key)
            for key in (
                "market_root",
                "artifact_root",
                "input_root",
                "data_source_sha256",
                "synthetic",
            )
        },
        point_root=tmp_path / "point",
    )
    target = owner.Nov30H3TargetPins(
        owner="invented-dec3-owner",
        source_sha256=run.data_source_sha256,
        attempt_sha256="4" * 64,
        market_root=run.market_root,
        artifact_root=run.artifact_root,
        target_root=tmp_path / "target",
        prebound_at=owner.CAPTURE_OPENS_UTC - timedelta(hours=1),
        release_at=datetime(2026, 12, 28, 21, 15, tzinfo=UTC),
        synthetic=True,
    )
    attempt = tmp_path / "attempt"
    prebind = target.prebind_sha256

    def invoke(**overrides):
        return owner.run_dec3_target_owner(
            run,
            **(
                options
                | dict(attempt_root=attempt, target_pins=target, prebind_sha256=prebind)
                | overrides
            ),
        )

    return run, target, attempt, invoke, options, requests, set_clock


def test_native_owner_retains_independent_target_digest_before_features(invocation):
    run, target, attempt, invoke, options, requests, _ = invocation
    load = options["config_loader"]
    features = options["prefix_features"]

    def config_loader():
        record = json.loads((attempt / "ATTEMPT.json").read_bytes())
        assert record["owner"] == target.owner
        assert record["launch_attempt_sha256"] == target.attempt_sha256
        assert record["pid"] == os.getpid()
        assert not requests
        return load()

    def prefix_features(*args):
        assert (attempt / "TARGET-PIN.json").is_file()
        return features(*args)

    result = invoke(config_loader=config_loader, prefix_features=prefix_features)
    claim = (attempt / "ATTEMPT.json").read_bytes()
    pin = json.loads((attempt / "TARGET-PIN.json").read_bytes())
    assert requests == ["POST"] + ["GET"] * 19
    assert result.target_status == "pinned"
    assert result.target_custody_sha256 == pin["target_custody_sha256"]
    assert pin["attempt_record_sha256"] == hashlib.sha256(claim).hexdigest()
    assert pin["prebind_sha256"] == target.prebind_sha256
    custody = read_nov30_h3_target_custody(
        target,
        prebind_sha256=target.prebind_sha256,
        expected_sha256=result.target_custody_sha256,
        now=target.release_at,
    )
    assert custody.capture_state_sha256 == pin["capture_state_sha256"]
    assert custody.capture_closed_at.isoformat() == pin["capture_closed_at"]
    assert (run.input_root / "DATA-READY.json").is_file()
    assert (
        result.ready_sha256
        == hashlib.sha256((run.input_root / "READY.json").read_bytes()).hexdigest()
    )
    assert not (attempt / "TARGET-PIN.pending").exists()


@pytest.mark.parametrize(
    "failure", ["destination_exists", "wrong_prebind", "wrong_release", "overlap", "pin_io"]
)
def test_target_local_failure_does_not_withhold_feature_ready(invocation, monkeypatch, failure):
    run, target, attempt, invoke, _, requests, _ = invocation
    overrides = {}
    if failure == "destination_exists":
        target.target_root.mkdir()
        (target.target_root / "TARGET-CUSTODY.json").write_bytes(b"do not replace")
    elif failure == "wrong_prebind":
        overrides["prebind_sha256"] = "5" * 64
    elif failure == "wrong_release":
        overrides["target_pins"] = replace(target, release_at=owner.CAPTURE_OPENS_UTC)
    elif failure == "overlap":
        unsafe = replace(target, target_root=run.input_root / "unsafe")
        overrides = dict(target_pins=unsafe, prebind_sha256=unsafe.prebind_sha256)
    else:
        write = owner._write_once

        def fail_pin(path, **document):
            if path.name == "TARGET-PIN.pending":
                write(path, **document)
                raise OSError("invented post-seal write interruption")
            return write(path, **document)

        monkeypatch.setattr(owner, "_write_once", fail_pin)

    result = invoke(**overrides)
    assert result.target_custody_sha256 is None
    assert (
        result.target_status
        == {
            "destination_exists": "seal_failed",
            "wrong_prebind": "not_bound",
            "wrong_release": "not_bound",
            "overlap": "not_bound",
            "pin_io": "pin_failed",
        }[failure]
    )
    assert (run.input_root / "DATA-READY.json").is_file()
    assert not (attempt / "TARGET-PIN.json").exists()
    if failure == "destination_exists":
        assert (target.target_root / "TARGET-CUSTODY.json").read_bytes() == b"do not replace"
    elif failure == "pin_io":
        assert (attempt / "TARGET-PIN.pending").is_file()
        assert (target.target_root / "TARGET-CUSTODY.json").is_file()
    else:
        assert not target.target_root.exists()
    with pytest.raises(FileExistsError):
        invoke(**overrides)
    assert requests == ["POST"] + ["GET"] * 19


def test_capture_mutation_can_publish_neither_pin_nor_ready(invocation, monkeypatch):
    run, _, attempt, invoke, _, requests, _ = invocation
    seal = owner.write_nov30_h3_target_custody

    def mutate_after_seal(*args, **kwargs):
        digest = seal(*args, **kwargs)
        (run.artifact_root / "capture-state.json").write_bytes(b"{}")
        return digest

    monkeypatch.setattr(owner, "write_nov30_h3_target_custody", mutate_after_seal)
    with pytest.raises(ValueError, match="capture_state_changed"):
        invoke()
    assert not run.input_root.exists()
    assert not (attempt / "TARGET-PIN.json").exists()
    assert requests == ["POST"] + ["GET"] * 19


def test_feature_failure_does_not_erase_target_pin(invocation):
    run, _, attempt, invoke, _, _, _ = invocation

    def fail_features(*args):
        raise ValueError("invented_feature_failure")

    with pytest.raises(ValueError, match="invented_feature_failure"):
        invoke(prefix_features=fail_features)
    assert not (run.input_root / "DATA-READY.json").exists()
    assert (attempt / "TARGET-PIN.json").is_file()


def test_early_launch_and_pre_capture_interruption(invocation, monkeypatch):
    run, target, attempt, invoke, _, requests, set_clock = invocation
    set_clock(owner.CAPTURE_OPENS_UTC - timedelta(seconds=1))
    with pytest.raises(ValueError, match="start_denied"):
        invoke()
    assert not attempt.exists()
    set_clock(owner.CAPTURE_OPENS_UTC)

    def interrupt(*args, **kwargs):
        raise OSError("invented interruption before capture")

    monkeypatch.setattr(owner, "run_dec3_data", interrupt)
    with pytest.raises(OSError, match="before capture"):
        invoke()
    claim = (attempt / "ATTEMPT.json").read_bytes()
    assert not target.target_root.exists() and not run.artifact_root.exists()
    with pytest.raises(FileExistsError):
        invoke()
    assert (attempt / "ATTEMPT.json").read_bytes() == claim
    assert not requests
