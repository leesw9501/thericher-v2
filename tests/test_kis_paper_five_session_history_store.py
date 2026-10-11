"""Private journal integrity and fixed DTO restore using synthetic fixtures."""

import copy
import json

import pytest

from test_kis_paper_five_session_runtime import Bank, finite_decision
from test_kis_paper_five_session_successor import arguments
from thericher_v2.execution import kis_paper_five_session_history_store as store
from thericher_v2.execution import kis_paper_five_session_runtime as runtime
from thericher_v2.execution.kis_paper_five_session_successor import prepare_five_session_successor


def staged(bank):
    args = bank.args
    prepared = prepare_five_session_successor(**args)
    reserve = runtime._arguments(
        bank.load(),
        args["cohort"],
        args["cohort"].entry_request_id,
        args["as_of"],
        args["valid_until"],
        side="buy",
        proposal=args["proposal"],
        receipt=args["receipt"],
        reads=args["reads"],
    )
    transition = runtime._transition(
        (), prepared.history, "buy", reserve, prepared.plan, args["cohort"]
    )
    anchor = dict(account_ref=args["expected_account_ref"], basis_ref=args["expected_basis_ref"])
    return anchor, transition


def test_constructor_is_inert_and_repr_has_no_private_path(tmp_path):
    instance = store.KisPaperFiveSessionHistoryStore(
        tmp_path / "SECRET", repository_root=tmp_path / "repo", artifact_root=tmp_path / "evidence"
    )
    assert not instance.root.exists() and "SECRET" not in repr(instance)


def test_prepared_committed_hashchain_roundtrip_preserves_read_dtos(tmp_path):
    bank = Bank(tmp_path, arguments())
    anchor, transition = staged(bank)
    with bank.store.locked():
        bank.store.bootstrap(anchor, ())
        pending = bank.store.prepare(transition)
        assert pending.pending == transition and pending.history == ()
        assert bank.store.prepare(copy.deepcopy(transition)) == pending
        committed = bank.store.commit(pending.head_ref)
        assert committed.history == transition["after"] and committed.pending is None
        assert committed.record_count == 3 and bank.store.read() == committed


@pytest.mark.parametrize(
    "mutation", ["body", "previous", "gap", "extra", "duplicate", "unknown_dto"]
)
def test_corrupt_missing_or_extra_journal_never_resets(tmp_path, mutation):
    bank = Bank(tmp_path, arguments())
    anchor, transition = staged(bank)
    with bank.store.locked():
        bank.store.bootstrap(anchor, ())
        bank.store.prepare(transition)
    path = bank.store.root / "00000001.json"
    payload = json.loads(path.read_bytes())
    if mutation == "gap":
        (bank.store.root / "00000000.json").unlink()
    elif mutation == "extra":
        (bank.store.root / "unexpected.json").write_text("{}")
    elif mutation == "duplicate":
        path.write_text('{"kind":"prepared",' + path.read_text()[1:])
    else:
        if mutation == "previous":
            payload["previous"] = "sha256:" + "0" * 64
        elif mutation == "body":
            payload["payload"]["map"]["side"] = "sell"
        else:
            payload["payload"] = {"dto": "KisPaperConfig", "fields": {}}
            payload["ref"] = store._digest({k: v for k, v in payload.items() if k != "ref"})
        path.write_text(json.dumps(payload))
    before = tuple(p.read_bytes() for p in sorted(bank.store.root.glob("*.json")))
    with (
        bank.store.locked(),
        pytest.raises(store.FiveSessionHistoryError, match="^history_store_invalid$"),
    ):
        bank.store.bootstrap(anchor, ())
    assert tuple(p.read_bytes() for p in sorted(bank.store.root.glob("*.json"))) == before


def test_writer_failure_before_commit_retains_prepared_bytes(tmp_path, monkeypatch):
    bank = Bank(tmp_path, arguments())
    anchor, transition = staged(bank)
    with bank.store.locked():
        bank.store.bootstrap(anchor, ())
        pending = bank.store.prepare(transition)
        monkeypatch.setattr(
            store.budget, "_atomic_json", lambda *_: (_ for _ in ()).throw(OSError())
        )
        with pytest.raises(OSError):
            bank.store.commit(pending.head_ref)
        assert bank.store.read() == pending


def test_retained_metadata_survives_commit_without_fresh_input(tmp_path):
    bank = Bank(tmp_path, arguments())
    dto, cohort = finite_decision(bank.args)
    result = bank.visit(dto, cohort)
    assert result["execute_calls"] == 1, result
    metadata = runtime.load_retained_runtime_metadata(bank.store, cohort.fingerprint)
    assert metadata.decision == dto


def test_private_root_cannot_be_inside_repository(tmp_path):
    instance = store.KisPaperFiveSessionHistoryStore(
        tmp_path / "repo" / "state",
        repository_root=tmp_path / "repo",
        artifact_root=tmp_path / "artifacts",
    )
    with pytest.raises(ValueError), instance.locked():
        pytest.fail("private_root_accepted")


def test_codec_rejects_arbitrary_objects_and_config_not_pickle():
    with pytest.raises(store.FiveSessionHistoryError):
        store._encode(object())
    with pytest.raises(store.FiveSessionHistoryError):
        store._decode({"dto": "KisPaperConfig", "fields": {}})
