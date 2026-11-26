import json
from datetime import timedelta
from hashlib import sha256

import pytest

from thericher_v2.ops import h20_phase_host as host
from thericher_v2.ops.h20_exact_phase_outcomes import _result, _unknown_phase


@pytest.fixture
def request_args(monkeypatch, tmp_path):
    reader = tmp_path / "reader.py"
    reader.write_bytes(b"invented native source")
    monkeypatch.setattr(host, "_READER", reader)
    monkeypatch.setattr(host, "_load", lambda _: {"REASONS": {"OK"}, "STAGES": {"COMPLETE"}})
    return dict(
        at=host.OPENS,
        source_sha256="a" * 64,
        image="sha256:" + "b" * 64,
        mounts=[
            dict(target=target, source=f"invented-{i}", type=kind, readonly=True)
            for i, (target, kind) in enumerate(host._TARGETS.items())
        ],
        admission_ready=lambda: True,
    )


def _completed():
    result = _result("OK", "COMPLETE")
    result["entry"] = dict(
        plan="LINKED", attempt="RECORDED", acceptance="ACKNOWLEDGED", fill="FULL", terminal="YES"
    )
    result["exit"] = dict(result["entry"])
    result["current_owned_inventory"] = "FLAT"
    return result


def test_exact_readonly_guest(request_args):
    answer = _completed()

    def transport(image, mounts, argv, parse):
        assert image == request_args["image"]
        assert mounts == request_args["mounts"]
        assert argv == ["-I", "-S", "-B", "/reader/guest.py", "--source-sha256", "a" * 64, "--read"]
        return parse(json.dumps(answer).encode())

    assert host.invoke_h20_phase_window(**request_args, transport=transport) == answer


@pytest.mark.parametrize("reason", ["early", "late", "write", "duplicate", "not_admitted"])
def test_denied_before_native_transport(request_args, reason):
    if reason == "early":
        request_args["at"] -= timedelta(microseconds=1)
    elif reason == "late":
        request_args["at"] = host.LAST_START
    elif reason == "write":
        request_args["mounts"][-1]["readonly"] = False
    elif reason == "duplicate":
        request_args["mounts"][-1] = request_args["mounts"][0]
    else:
        request_args["admission_ready"] = lambda: False
    with pytest.raises(ValueError, match="H20_PHASE_HOST_UNQUALIFIED"):
        host.invoke_h20_phase_window(**request_args, transport=lambda *_: pytest.fail("transport"))


@pytest.mark.parametrize(
    "fault",
    ["legacy", "old_phase", "unlinked", "no_entry_fill", "broker_pnl", "gross_unclosed", "raw"],
)
def test_reject_unqualified_guest_projection(request_args, fault):
    answer = _completed()
    if fault == "legacy":
        answer["schema"] = "H20_EXACT_OFFLINE_OUTCOME_V1"
    elif fault == "old_phase":
        answer["schema"] = "H20_EXACT_OFFLINE_PHASE_OUTCOMES_V1"
        del answer["gross_PnL_sign"], answer["gross_scope"]
    elif fault == "unlinked":
        answer["exit"] = _unknown_phase("NO_LINKED_PLAN")
    elif fault == "no_entry_fill":
        answer["entry"]["fill"] = "ZERO"
    elif fault == "broker_pnl":
        answer["net_PnL"] = "invented"
    elif fault == "gross_unclosed":
        answer["gross_PnL_sign"] = "POSITIVE"
        answer["exit"]["terminal"] = "UNKNOWN"
    else:
        answer["raw"] = "invented"
    with pytest.raises(ValueError, match="H20_PHASE_HOST_UNQUALIFIED"):
        host.invoke_h20_phase_window(
            **request_args, transport=lambda *args: args[-1](json.dumps(answer).encode())
        )


@pytest.mark.parametrize(
    "fault", [None, "stale", "wrong_caller", "no_job_closure", "replaced", "replayed"]
)
def test_public_projection_preserves_original_native_links(
    request_args, tmp_path, fault, monkeypatch
):
    if not host._PUBLIC.is_file():
        pytest.skip("pinned legacy H20 public reader not retained on this host")

    def put(name, value):
        path = tmp_path / name
        raw = json.dumps(value).encode()
        path.write_bytes(raw)
        return dict(path=str(path), bytes=len(raw), sha256=sha256(raw).hexdigest())

    binding = {
        name: put(name, {})
        for name in ("reader_source", "installed_host", "release", "plan", "contract")
    }
    binding.update(input_ref="input", policy_ref="policy")
    caller = dict(
        source_sha256="c" * 64,
        origin="actual_source_caller_not_OS_scheduler_proof",
        pid=20,
        created_filetime=42,
        argv_sha256="d" * 64,
    )
    admissions = [
        dict(
            phase=phase,
            actual_caller=dict(caller),
            verdict=put(
                "CAPABILITY-" + phase + ".json",
                {"status": "NO_CURRENT_PRIVATE_CUSTODY_WRITER_OBSERVED"},
            ),
        )
        for phase in ("before_create", "before_start", "before_read", "after_read", "after_remove")
    ]
    if fault == "wrong_caller":
        admissions[-1]["actual_caller"]["created_filetime"] += 1
    closure = put(
        "CLOSED.json",
        dict(
            status="PASS",
            CID_absent=True,
            admissions=admissions,
            Jobs=[dict(exit=0, active=1 if fault == "no_job_closure" else 0, closed=True)],
        ),
    )
    observed = host.OPENS - timedelta(seconds=1) if fault == "stale" else host.OPENS
    written = dict(
        source_sha256="e" * 64,
        observed_utc=observed.isoformat(),
        result=_completed(),
        admissions=admissions,
        closure=closure,
        broker_calls=0,
        private_writes=0,
        reservation_released=False,
        current_read_not_historical_OS_origin=True,
        fees_settlement_netPnL="NOT_OBSERVED",
        **{("H20_source" if k == "installed_host" else k): v for k, v in binding.items()},
    )
    published = put("RESULT.json", written)["sha256"]
    if fault == "replayed":
        written["result"]["current_owned_inventory"] = "UNKNOWN"
        put("RESULT.json", written)
    if fault == "replaced":
        read_original = host._read

        def read(path):
            result = read_original(path)
            if path == tmp_path / "RESULT.json":
                written["result"]["current_owned_inventory"] = "UNKNOWN"
                put(path.name, written)
            return result

        monkeypatch.setattr(host, "_read", read)

    def read_bound():
        return host.read_h20_phase_envelope(
            tmp_path, "e" * 64, binding, "c" * 64, published_result_pin=published
        )

    if fault:
        with pytest.raises(ValueError):
            read_bound()
    else:
        value = read_bound()
        assert value["exit"]["fill"] == "FULL"
        assert value["broker_holdings"] == "NOT_READ"
        assert value["OS_scheduler_origin"] == "NOT_CRYPTOGRAPHICALLY_PROVEN"
