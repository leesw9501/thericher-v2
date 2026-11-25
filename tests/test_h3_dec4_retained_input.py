import hashlib
import json
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from test_model_paper_net25_open_elapsed3 import PROFILE, metadata
from test_model_paper_weights_h5 import _metadata, _window
from thericher_v2.ops.h3_dec4_retained_input import (
    restore_dec4_h3_input,
    retain_dec4_h3_input,
)
from thericher_v2.research import model_paper_weights as weights

SOURCE = "a" * 64
POINT = "b" * 64


def _native(*, entry=4, exit=9, ceiling="0.1", profile=PROFILE):
    first, last = _window(date(2026, 12, entry)), _window(date(2026, 12, exit))
    meta = replace(
        _metadata(first, last, metadata().rows),
        exit_not_before=last.open_ts,
        original_basis_gross_ceiling=Decimal(ceiling),
        full_output_ref="sha256:" + POINT,
    )
    return weights.prepare_model_paper_weights_input(
        meta, entry_session=first, exit_session=last, profile=profile
    )


def _retain(path, value):
    return retain_dec4_h3_input(
        path,
        weights.serialize_model_paper_weights_input(value),
        source_sha256=SOURCE,
        point_sha256=POINT,
        policy_ref=value.policy_ref,
        synthetic=False,
    )


def test_exact_native_bytes_restore_without_point_or_writes(tmp_path):
    path = tmp_path / "retained"
    value = _native()
    ref = _retain(path, value)
    before = path.stat()
    original = path.read_bytes()
    header, _, payload = original.partition(b"\n")
    assert payload == weights.serialize_model_paper_weights_input(value)
    assert ref.payload_sha256 == hashlib.sha256(payload).hexdigest()
    assert json.loads(header) == {
        "schema": "DEC4_H3_RETAINED_INPUT_V2",
        "source_sha256": SOURCE,
        "point_sha256": POINT,
        "policy_ref": value.policy_ref,
        "payload_sha256": ref.payload_sha256,
        "synthetic": False,
        "entry_open": "2026-12-04T14:30:00+00:00",
        "exit_open": "2026-12-09T14:30:00+00:00",
    }
    assert restore_dec4_h3_input(ref) == value
    assert path.read_bytes() == original
    assert path.stat().st_mtime_ns == before.st_mtime_ns
    assert list(tmp_path.iterdir()) == [path]


def test_existing_file_not_overwritten_even_for_same_input(tmp_path):
    path = tmp_path / "retained"
    value = _native()
    ref = _retain(path, value)
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        _retain(path, value)
    assert path.read_bytes() == before
    assert restore_dec4_h3_input(ref) == value


@pytest.mark.parametrize(
    "changes",
    [
        {"entry": 7, "exit": 10},
        {"ceiling": "0.11"},
        {"ceiling": "0.09"},
        {"profile": weights.MODEL_PAPER_WEIGHTS_US_CASH_RAW_OPEN_ELAPSED3_PROFILE},
    ],
)
def test_valid_native_bytes_outside_exact_contract_never_written(tmp_path, changes):
    value = _native(**changes)
    path = tmp_path / "retained"
    with pytest.raises(ValueError, match="h3_retained_contract_mismatch"):
        _retain(path, value)
    assert not path.exists()


def test_writer_uses_native_parser_and_checks_policy_before_creation(tmp_path):
    value = _native()
    path = tmp_path / "retained"
    payload = weights.serialize_model_paper_weights_input(value)
    for raw, policy, error in (
        (payload + b" ", value.policy_ref, "weights_payload_not_canonical_or_derived"),
        (payload, "sha256:" + "c" * 64, "weights_policy_pin_mismatch"),
    ):
        with pytest.raises(ValueError, match=error):
            retain_dec4_h3_input(
                path,
                raw,
                source_sha256=SOURCE,
                point_sha256=POINT,
                policy_ref=policy,
                synthetic=False,
            )
        assert not path.exists()


@pytest.mark.parametrize(
    "change",
    [
        {"source_sha256": "c" * 64},
        {"point_sha256": "c" * 64},
        {"policy_ref": "sha256:" + "c" * 64},
        {"payload_sha256": "c" * 64},
    ],
)
def test_restore_rejects_each_mismatched_owner_pin(tmp_path, change):
    ref = _retain(tmp_path / "retained", _native())
    with pytest.raises(ValueError, match="h3_retained_binding_mismatch"):
        restore_dec4_h3_input(replace(ref, **change))


def test_restore_rejects_missing_path_and_torn_or_changed_bytes(tmp_path):
    path = tmp_path / "retained"
    ref = _retain(path, _native())
    missing = tmp_path / "missing"
    with pytest.raises(FileNotFoundError):
        restore_dec4_h3_input(replace(ref, path=missing))
    assert not missing.exists()
    original = path.read_bytes()
    for changed in (original[:-1], original[:-1] + b"]"):
        path.write_bytes(changed)
        with pytest.raises(ValueError, match="weights_input_pin_mismatch"):
            restore_dec4_h3_input(ref)


def test_restore_rejects_hardlink_without_altering_either_path(tmp_path):
    path = tmp_path / "retained"
    ref = _retain(path, _native())
    alias = tmp_path / "alias"
    alias.hardlink_to(path)
    try:
        with pytest.raises(ValueError, match="capture_hardlink_refused"):
            restore_dec4_h3_input(ref)
        assert alias.samefile(path)
    finally:
        alias.unlink()
