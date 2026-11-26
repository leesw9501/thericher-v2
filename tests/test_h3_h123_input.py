import hashlib
import json
import runpy
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.data import us_equity_session
from thericher_v2.data.kis_paper_h3_capture import H3DailyCapture
from thericher_v2.data.kis_paper_h3_daily_panel import (
    NET25_H3_AXIS,
    H3DailyPanel,
    H3DailyPanelPlan,
)
from thericher_v2.execution import paper_account_session
from thericher_v2.execution.kis_market_data import KisPaperDailyRawRow
from thericher_v2.execution.kis_paper_current_stock_cycle import StockCycleProfile
from thericher_v2.execution.kis_readonly import KisPaperConfig
from thericher_v2.execution.paper_account_round import PaperRoundSlot
from thericher_v2.models import h3_shadow_point
from thericher_v2.models.h3_h123_input import write_h3_h123_input
from thericher_v2.models.h3_publisher_input import (
    H3InputBinding,
    read_h3_publisher_input,
    write_h3_publisher_input,
)
from thericher_v2.ops import h3_dec4_paper_input, h3_dec4_point_owner
from thericher_v2.ops.h3_dec4_paper_input import DEC4_NET25_PROFILE, prepare_dec4_paper_input
from thericher_v2.ops.h3_dec4_retained_input import restore_dec4_h3_input
from thericher_v2.ops.h3_dec4_run import Dec4H3Run
from thericher_v2.research.model_paper_weights import load_model_paper_weights_input

DECISION = datetime(2026, 12, 4, 14, 25, tzinfo=UTC)
SOURCE = "3" * 64


@pytest.fixture(scope="module")
def panel():
    plan = H3DailyPanelPlan(NET25_H3_AXIS)
    return H3DailyPanel(
        plan,
        tuple(
            tuple(
                KisPaperDailyRawRow(
                    day.strftime("%Y%m%d"), str(i + 10), str(i + 12), "9", str(i + 11), "10"
                )
                for i in range(19)
            )
            for day in plan.sessions
        ),
    )


def features(ohlc, known, conditional):
    assert ohlc.shape == (60, 19, 4) and ohlc.dtype == np.float64
    assert ohlc[0, 0].tolist() == [10, 12, 9, 11]
    assert ohlc[0, 17, 0] == 27 and ohlc[0, 18, 0] == 28
    assert known.dtype == conditional.dtype == bool and known.all() and not conditional.any()
    return np.ones((17, 60, 12), np.float32), np.ones((17, 8), np.float64)


def reader(root, *, expected_source, role, expected_keys, synthetic):
    meta = json.loads((root / "INPUT.json").read_bytes())
    assert (expected_source, role, synthetic) == (SOURCE, "FUTURE_20261203_ASOF_20261204", True)
    assert (meta["source"], meta["role"], meta["synthetic"]) == (expected_source, role, synthetic)
    assert meta["producer"] == "Data.ShortSwingEndpointProducer"
    assert meta["consumer"] == "EngineResearch.ShortSwingHorizonInput"
    assert meta["payload_sha256"] == hashlib.sha256((root / "INPUT.npz").read_bytes()).hexdigest()
    with np.load(root / "INPUT.npz", allow_pickle=False) as arrays:
        result = dict(arrays)
    assert expected_keys == result["key"].tolist() == [f"20261204|{i:02d}" for i in range(17)]
    assert set(result["context_close"]) == {"2026-12-03T21:00:00+00:00"}
    assert set(result["decision_at"]) == {"2026-12-04T14:25:00+00:00"}
    return result, meta


def write(destination, panel, **overrides):
    params = dict(
        decision_at=DECISION,
        data_source_sha256=SOURCE,
        synthetic=True,
        prefix_features=features,
        parse_input=reader,
    )
    return write_h3_h123_input(destination, panel, **(params | overrides))


def test_exact_next_session_artifact_and_exclusive_destination(tmp_path, panel):
    dest = tmp_path / "next"
    digest = write(dest, panel)
    assert digest == hashlib.sha256((dest / "INPUT.npz").read_bytes()).hexdigest()
    assert {p.name for p in dest.iterdir()} == {"INPUT.json", "INPUT.npz"}
    with pytest.raises(FileExistsError):
        write(dest, panel)


@pytest.mark.parametrize(
    "stamp", ["2026-12-03T21:30:00", "2026-12-04T14:30:00", "2026-12-07T14:25:00"]
)
def test_refuses_stale_premature_or_open_clock(tmp_path, panel, stamp):
    with pytest.raises(ValueError, match="next_session_preopen"):
        write(
            tmp_path / "next", panel, decision_at=datetime.fromisoformat(stamp).replace(tzinfo=UTC)
        )
    assert not list(tmp_path.iterdir())


def test_wrong_row_date_and_nonfinite_features_are_not_publishable(tmp_path, panel):
    wrong = replace(panel, rows=(panel.rows[1], *panel.rows[1:]))
    with pytest.raises(ValueError, match="panel_grid_invalid"):
        write(tmp_path / "next", wrong)

    def invalid(*args):
        x, z = features(*args)
        x[0, 0, 0] = np.nan
        return x, z

    with pytest.raises(ValueError, match="feature_abi_invalid"):
        write(tmp_path / "next", panel, prefix_features=invalid)
    assert not list(tmp_path.iterdir())


def test_consumer_drift_withholds_success(tmp_path, panel):
    def drift(*args, **options):
        arrays, header = reader(*args, **options)
        arrays["x"][0, 0, 0] = -5
        return arrays, header

    dest = tmp_path / "unsealed"
    with pytest.raises(ValueError, match="readback_mismatch"):
        write(dest, panel, parse_input=drift)
    assert not (dest / "SEAL.json").exists()
    with pytest.raises(FileExistsError):
        write(dest, panel)


@pytest.fixture
def publisher(tmp_path, panel):
    state = tmp_path / "capture-state.json"
    state.write_bytes(b"invented closed state")
    closed = datetime(2026, 12, 3, 21, 35, tzinfo=UTC)
    limit = datetime(2026, 12, 3, 21, 45, tzinfo=UTC)
    binding = H3InputBinding(SOURCE, DECISION, limit, True)
    capture = H3DailyCapture(panel, hashlib.sha256(state.read_bytes()).hexdigest(), closed)
    root = tmp_path / "input"

    def publish(*, clock=lambda: closed, parser=reader):
        return write_h3_publisher_input(
            root,
            capture,
            binding=binding,
            clock=clock,
            prefix_features=features,
            parse_input=parser,
        )

    return root, state, binding, publish


def test_publisher_binds_closed_state_and_both_input_files(publisher):
    root, state, binding, publish = publisher
    ready_sha = publish()
    arrays, _ = read_publisher(root, state, binding, ready_sha)
    assert arrays["x"].shape == (17, 60, 12)
    with pytest.raises(ValueError, match="ready_binding_mismatch"):
        read_publisher(root, state, replace(binding, synthetic=False), ready_sha)
    with pytest.raises(ValueError, match="read_clock_mismatch"):
        read_publisher(root, state, binding, ready_sha, clock=lambda: binding.decision_at)
    state.write_bytes(b"different next capture")
    with pytest.raises(ValueError, match="member_digest_mismatch"):
        read_publisher(root, state, binding, ready_sha)


def read_publisher(root, state, binding, digest, *, clock=None):
    def validate(arrays, header, **pins):
        assert arrays["key"].tolist() == pins["expected_keys"]
        assert header["source"] == pins["expected_source"] == SOURCE
        assert header["role"] == pins["role"] == "FUTURE_20261203_ASOF_20261204"
        assert header["synthetic"] is pins["synthetic"] is True

    return read_h3_publisher_input(
        root,
        state,
        binding=binding,
        ready_sha256=digest,
        clock=clock or (lambda: binding.hard_stop),
        validate_input=validate,
    )


@pytest.mark.parametrize("member", ["INPUT.json", "INPUT.npz", "READY.json"])
def test_publisher_rejects_swapped_member(publisher, member):
    root, state, binding, publish = publisher
    ready_sha = publish()
    (root / member).write_bytes(b"swapped")
    with pytest.raises(ValueError, match="digest_mismatch"):
        read_publisher(root, state, binding, ready_sha)


def test_publisher_expiry_before_rename_does_not_publish(publisher):
    root, state, binding, publish = publisher
    stamps = iter([binding.hard_stop.replace(minute=40)] * 2 + [binding.hard_stop])
    with pytest.raises(ValueError, match="outside_window"):
        publish(clock=lambda: next(stamps))
    assert not (root / "READY.json").exists()
    with pytest.raises(ValueError, match="unreadable"):
        read_publisher(root, state, binding, "2" * 64)


def test_dec4_point_one_attempt_and_exact_binding(publisher, monkeypatch):
    root, state, binding, publish = publisher
    ready = publish()
    output = root.parent / "point"
    forwards = []

    def forward(arrays, *_files, before_forward):
        assert arrays["x"].shape == (17, 60, 12)
        before_forward()
        forwards.append(1)
        return np.array([-0.5] + [0.0] * 7 + [0.5] + [0.0] * 8, np.float64)

    def validate(arrays, header, **pins):
        assert list(arrays["key"]) == pins["expected_keys"]
        assert header["source"] == pins["expected_source"]

    monkeypatch.setattr(h3_shadow_point, "_frozen_lstm", forward)
    options = dict(
        input_root=root,
        capture_state_path=state,
        binding=binding,
        ready_sha256=ready,
        clock=lambda: binding.hard_stop.replace(minute=48),
        validate_input=validate,
        model_source=b"not used in fixture",
        stats=b"",
        weights=b"",
    )
    digest = h3_shadow_point.publish_dec4_h3_shadow_point(output, **options)
    point = h3_shadow_point.read_dec4_h3_shadow_point(
        output, binding=binding, ready_sha256=ready, point_sha256=digest
    )
    assert not point["financial_authority"] and point["synthetic"]
    assert point["rows"][8]["weight"] == "0.02941176470588235"
    assert point["rows"][1]["weight"] == point["rows"][2]["weight"] == "0"
    assert point["rows"][-1]["route"] == "CASH"
    run = Dec4H3Run(root.parent / "market", state.parent, root, output, SOURCE, True)
    (root / "DATA-READY.json").write_bytes(run._receipt(ready))
    pins = dict(
        ready_sha256=ready,
        point_sha256=digest,
        policy_ref="sha256:" + "a" * 64,
        adapter_ref="sha256:"
        + hashlib.sha256(Path(h3_dec4_paper_input.__file__).read_bytes()).hexdigest(),
        calendar_ref="sha256:"
        + hashlib.sha256(Path(us_equity_session.__file__).read_bytes()).hexdigest(),
        fixture_now=DECISION,
    )
    encoded = prepare_dec4_paper_input(run, **pins)
    restored = load_model_paper_weights_input(
        encoded.payload, expected_sha256=encoded.sha256, expected_policy_ref=encoded.policy_ref
    )
    assert encoded.synthetic and restored.profile == DEC4_NET25_PROFILE
    assert restored.metadata.input_asof == binding.hard_stop.replace(minute=48)
    assert restored.metadata.source_available_at == binding.hard_stop.replace(minute=35)
    assert restored.exit_session.open_ts == datetime(2026, 12, 9, 14, 30, tzinfo=UTC)
    assert [target.proposal.symbol for target in restored.targets] == ["JPM"]
    owner = h3_dec4_point_owner
    monkeypatch.setattr(owner, "DATA_SOURCE_SHA256", SOURCE)
    point_source = "f" * 64
    (root.parent / "owner").mkdir()
    handoff = {
        "attempt_sha256": (
            root.parent / "POINT-ATTEMPT.json",
            dict(
                schema="H3_DEC4_POINT_ATTEMPT_V1",
                source_sha256=point_source,
                started_at=owner.OPENS.isoformat(),
            ),
        ),
        "data_attempt_sha256": (root.parent / "owner/ATTEMPT.json", {"fixture": True}),
    }
    refs = {}
    for key, (path, record) in handoff.items():
        raw = owner._json(record)
        path.write_bytes(raw)
        refs[key] = owner._sha(raw)
    data_done = owner._json(
        dict(
            schema="H3_DEC3_OWNER_CLOSED_V1",
            source_sha256=SOURCE,
            attempt_sha256=refs["data_attempt_sha256"],
            ready_sha256=ready,
            closed_at=owner.OPENS.replace(minute=44).isoformat(),
            native_start="win-filetime:1",
            target_status="pin_failed",
            target_custody_sha256=None,
        )
    )
    (root.parent / "OWNER-CLOSED.json").write_bytes(data_done)
    completion = dict(
        schema="H3_DEC4_POINT_OWNER_CLOSED_V1",
        source_sha256=point_source,
        source72_sha256=owner.SOURCE72_SHA256,
        data_source_sha256=SOURCE,
        data_owner_sha256=owner._sha(data_done),
        ready_sha256=ready,
        data_ready_sha256=owner._sha(run._receipt(ready)),
        point_sha256=digest,
        closed_at=owner.OPENS.replace(minute=50).isoformat(),
        financial_authority=False,
        **refs,
    )
    closure = output / "OWNER-CLOSED.json"
    closure_raw = owner._json(completion)
    path = root.parent / "retained-input"
    params = dict(
        point_source_sha256=point_source,
        point_owner_sha256=owner._sha(closure_raw),
        prove_point_closed=lambda pin: pin == owner._sha(closure_raw),
        retained_path=path,
        source_sha256=run.data_source_sha256,
        policy_ref=encoded.policy_ref,
        adapter_ref=pins["adapter_ref"],
        calendar_ref=pins["calendar_ref"],
        fixture_now=DECISION,
    )
    retain = h3_dec4_paper_input.retain_completed_dec4_paper_input
    with pytest.raises(FileNotFoundError):
        retain(run, **params)
    closure.write_bytes(closure_raw)
    with pytest.raises(ValueError, match="closure_unknown"):
        retain(run, **(params | {"prove_point_closed": lambda _pin: False}))
    with pytest.raises(ValueError, match="source_member_digest"):
        retain(
            run,
            **(params | {"point_owner_sha256": "0" * 64, "prove_point_closed": lambda _pin: True}),
        )
    pending = output / "OWNER-CLOSED.pending"
    pending.touch()
    with pytest.raises(FileExistsError):
        retain(run, **params)
    pending.unlink()
    late = owner._json(completion | {"closed_at": owner.HARD_STOP.isoformat()})
    closure.write_bytes(late)
    with pytest.raises(ValueError, match="point_clocks"):
        retain(
            run,
            **(
                params
                | {"point_owner_sha256": owner._sha(late), "prove_point_closed": lambda _pin: True}
            ),
        )
    closure.write_bytes(closure_raw)
    assert not path.exists()

    completion_pin = "e" * 64
    control_path = root.parent / "point-control"

    def joined(**binding):
        assert binding == dict(
            control=control_path,
            point_source_sha256=point_source,
            completion_sha256=completion_pin,
        )
        return params["point_owner_sha256"]

    monkeypatch.setattr(h3_dec4_paper_input, "read_supervised_point", joined)
    phase_input = h3_dec4_paper_input.Dec4BankPhaseInput(
        run=run,
        point_completion_pin=lambda: completion_pin,
        fixture_now=DECISION,
    )
    ready_entry = SimpleNamespace(
        plan=SimpleNamespace(phase="entry", source_sha256=run.data_source_sha256),
        source={
            "retained_input_path": str(path),
            "execution_policy_ref": encoded.policy_ref,
            "paper_input_adapter_ref": params["adapter_ref"],
            "paper_input_calendar_ref": params["calendar_ref"],
            "point_owner_source_sha256": point_source,
            "point_control_path": str(control_path),
        },
    )
    with pytest.raises(ValueError, match="phase_mismatch"):
        phase_input(ready_entry, "exit")
    retained = phase_input(ready_entry, "entry")
    assert retained.payload_sha256 == encoded.sha256
    with pytest.raises(FileExistsError):
        retain(run, **params)
    with pytest.raises(ValueError, match="fixture_mode_mismatch"):
        restore_dec4_h3_input(retained)

    def prohibited(*_a, **_k):
        pytest.fail("native custody or client callback reached")

    monkeypatch.setattr(paper_account_session, "_snapshot", prohibited)
    entry_at = restored.entry_session.open_ts
    last_start = entry_at.replace(minute=35)
    worker = (
        Path(__file__).resolve().parents[1] / "scripts/run_kis_paper_current_stock_cycle_worker.py"
    )
    guest = runpy.run_path(str(worker))["run_account_session"]
    with pytest.raises(ValueError, match="account_session_admission_denied"):
        guest(
            KisPaperConfig("invented-key", "invented-secret", "00000000", "00"),
            execute=True,
            cohort=paper_account_session.PaperAccountCohort(
                PaperRoundSlot(
                    "invented-dec4",
                    "entry",
                    entry_at,
                    last_start,
                    "sha256:" + encoded.sha256,
                    encoded.policy_ref,
                ),
                "sha256:" + run.data_source_sha256,
                "sha256:" + "e" * 64,
                StockCycleProfile.MODEL_WEIGHTS_US_CASH_NET25_OPEN_ELAPSED3,
            ),
            paths={},
            target_loader=prohibited,
            source_ready=lambda: True,
            owner_ready=lambda: False,
            clock=lambda: entry_at,
            deadline=last_start,
        )
    with pytest.raises(ValueError, match="fixture_clock_mode"):
        prepare_dec4_paper_input(replace(run, synthetic=False), **pins)
    with pytest.raises(ValueError, match="loaded_source_mismatch"):
        prepare_dec4_paper_input(run, **(pins | {"calendar_ref": "sha256:" + "c" * 64}))
    with pytest.raises(ValueError, match="receipt_mismatch"):
        prepare_dec4_paper_input(run, **(pins | {"ready_sha256": "d" * 64}))
    with pytest.raises(ValueError, match="outside_window"):
        prepare_dec4_paper_input(run, **(pins | {"fixture_now": DECISION.replace(minute=35)}))
    with pytest.raises(FileExistsError):
        h3_shadow_point.publish_dec4_h3_shadow_point(output, **options)
    with pytest.raises(ValueError, match="readback_mismatch"):
        h3_shadow_point.read_dec4_h3_shadow_point(
            output, binding=binding, ready_sha256="4" * 64, point_sha256=digest
        )
    with pytest.raises(ValueError, match="clock_denied"):
        h3_shadow_point.publish_dec4_h3_shadow_point(
            root.parent / "late", **(options | {"clock": lambda: binding.decision_at})
        )
    assert forwards == [1]
    (output / "POINT.json").unlink()
    ready_exit = SimpleNamespace(plan=SimpleNamespace(phase="exit"))
    with pytest.raises(ValueError, match="phase_mismatch"):
        phase_input(ready_exit, "exit")
