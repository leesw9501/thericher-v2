import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from threading import Barrier

import pytest

from thericher_v2.ops import h20_phase_entry as entry


def _pin(path):
    return sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    launcher = tmp_path / "launcher.py"
    launcher.write_bytes(b"invented launcher")
    protected = tmp_path / "protected"
    protected.mkdir()
    profile_path = protected / "PROFILE.json"
    profile = dict(
        schema=entry._SCHEMA,
        caller_sha256=_pin(Path(entry.__file__)),
        launcher=dict(path=str(launcher), sha256=_pin(launcher)),
        guest_sha256="a" * 64,
        source_pin="b" * 64,
        image="sha256:" + "c" * 64,
        binding=dict(invented=True),
        run=str(tmp_path / "run"),
        protected_digest=str(protected / "RESULT.sha256"),
        claim=str(protected / "ATTEMPT"),
    )
    monkeypatch.setattr(entry, "_utc_now", lambda: entry.OPENS)
    monkeypatch.setattr(
        entry, "run_h20_phase_transport", lambda **_: pytest.fail("unexpected transport")
    )
    monkeypatch.setattr(
        entry, "publish_h20_phase_result", lambda **_: pytest.fail("unexpected publication")
    )

    def prepare():
        profile_path.write_text(json.dumps(profile), encoding="ascii")
        return dict(profile_path=profile_path, profile_sha256=_pin(profile_path))

    return profile, prepare


def test_composes_pinned_transport_and_publication(scenario, monkeypatch, capsys):
    profile, prepare = scenario
    clock = entry.OPENS
    completed = object()
    publications = []
    monkeypatch.setattr(entry, "_utc_now", lambda: clock)

    def transport(**kwargs):
        nonlocal clock
        assert Path(profile["claim"]).is_file()
        assert kwargs == dict(
            binding=profile["binding"],
            out=Path(profile["run"]),
            entry_file=Path(profile["launcher"]["path"]),
            entry_sha256=profile["launcher"]["sha256"],
            guest_sha256=profile["guest_sha256"],
            image=profile["image"],
        )
        assert not list(kwargs["out"].iterdir())
        clock = entry.LAST_START
        return completed

    def publish(**kwargs):
        publications.append(kwargs)
        return {"not_returned": "raw sentinel"}

    monkeypatch.setattr(entry, "run_h20_phase_transport", transport)
    monkeypatch.setattr(entry, "publish_h20_phase_result", publish)
    arguments = prepare()
    assert entry.run_h20_phase_entry(**arguments) == "H20_PHASE_RESULT_PUBLISHED"
    assert publications == [
        dict(
            run=Path(profile["run"]),
            protected_digest=Path(profile["protected_digest"]),
            source_pin=profile["source_pin"],
            binding=profile["binding"],
            coordinator_pin=profile["launcher"]["sha256"],
            completed=completed,
        )
    ]
    assert capsys.readouterr() == ("", "")


def test_hashes_before_decoding(scenario, monkeypatch):
    profile, prepare = scenario
    arguments = prepare()
    arguments["profile_path"].write_bytes(b"untrusted malformed bytes")
    monkeypatch.setattr(entry, "_strict_json", lambda _: pytest.fail("decoded unpinned bytes"))
    with pytest.raises(ValueError, match="^H20_PHASE_ENTRY_ADMISSION$"):
        entry.run_h20_phase_entry(**arguments)
    assert not Path(profile["claim"]).exists()


@pytest.mark.parametrize(
    "fault",
    [
        "early", "late", "own_pin", "launcher_pin", "same_claim_digest", "digest_under_run",
        "claim_under_run", "claim_is_profile", "run_under_claim", "dotdot", "ads",
        "trailing_dot", "existing_run", "existing_digest",
    ],
)
def test_rejects_before_claim(scenario, monkeypatch, fault):
    profile, prepare = scenario
    claim = Path(profile["claim"])
    if fault == "early":
        monkeypatch.setattr(entry, "_utc_now", lambda: entry.OPENS - timedelta(microseconds=1))
    elif fault == "late":
        monkeypatch.setattr(entry, "_utc_now", lambda: entry.LAST_START)
    elif fault == "own_pin":
        profile["caller_sha256"] = "0" * 64
    elif fault == "launcher_pin":
        profile["launcher"]["sha256"] = "0" * 64
    elif fault == "same_claim_digest":
        profile["claim"] = profile["protected_digest"]
    elif fault == "digest_under_run":
        profile["protected_digest"] = str(Path(profile["run"]) / "RESULT.sha256")
    elif fault == "claim_under_run":
        profile["claim"] = str(Path(profile["run"]) / "ATTEMPT")
    elif fault == "run_under_claim":
        profile["run"] = str(claim / "run")
    elif fault == "claim_is_profile":
        profile["claim"] = str(claim.with_name("PROFILE.json"))
    elif fault == "dotdot":
        profile["claim"] = str(claim.parent / ".." / "ATTEMPT")
    elif fault == "ads":
        profile["claim"] = str(claim) + ":hidden"
    elif fault == "trailing_dot":
        profile["claim"] = str(claim) + "."
    elif fault == "existing_run":
        Path(profile["run"]).mkdir()
    elif fault == "existing_digest":
        Path(profile["protected_digest"]).write_bytes(b"existing")

    with pytest.raises(ValueError, match="^H20_PHASE_ENTRY_ADMISSION$"):
        entry.run_h20_phase_entry(**prepare())
    assert not claim.exists()


def test_expiring_while_claiming_does_not_start_transport(scenario, monkeypatch):
    profile, prepare = scenario
    original = entry._new

    def acquire(*args):
        result = original(*args)
        monkeypatch.setattr(entry, "_utc_now", lambda: entry.LAST_START)
        return result

    monkeypatch.setattr(entry, "_new", acquire)
    with pytest.raises(ValueError, match="^H20_PHASE_ENTRY_TRANSPORT$"):
        entry.run_h20_phase_entry(**prepare())
    assert Path(profile["claim"]).is_file()


@pytest.mark.parametrize("fault", ["transport", "publication", "hard_stop", "source_changed"])
def test_failure_consumes_claim_even_without_run_directory(scenario, monkeypatch, fault):
    profile, prepare = scenario
    arguments = prepare()

    def transport(**_):
        if fault == "transport":
            raise RuntimeError("private diagnostic")
        if fault == "hard_stop":
            monkeypatch.setattr(entry, "_utc_now", lambda: entry.HARD_STOP)
        if fault == "source_changed":
            Path(profile["launcher"]["path"]).write_bytes(b"changed launcher")
        return object()

    def publish(**_):
        assert fault == "publication"
        raise RuntimeError("private diagnostic")

    monkeypatch.setattr(entry, "run_h20_phase_transport", transport)
    monkeypatch.setattr(entry, "publish_h20_phase_result", publish)
    stage = "TRANSPORT" if fault == "transport" else "PUBLICATION"
    with pytest.raises(ValueError, match=f"^H20_PHASE_ENTRY_{stage}$") as error:
        entry.run_h20_phase_entry(**arguments)
    assert error.value.__context__ is None
    assert Path(profile["claim"]).is_file()
    Path(profile["run"]).rmdir()
    monkeypatch.setattr(entry, "_utc_now", lambda: entry.OPENS)
    Path(profile["launcher"]["path"]).write_bytes(b"invented launcher")
    with pytest.raises(ValueError, match="^H20_PHASE_ENTRY_ADMISSION$"):
        entry.run_h20_phase_entry(**arguments)
    assert not Path(profile["run"]).exists()


def test_atomic_claim_allows_only_one_caller(scenario, monkeypatch):
    _, prepare = scenario
    arguments = prepare()
    barrier = Barrier(2)
    original = entry._new
    started = []

    def acquire(*args):
        barrier.wait(timeout=5)
        return original(*args)

    def transport(**_):
        started.append(True)

    def invoke():
        try:
            return entry.run_h20_phase_entry(**arguments)
        except ValueError as error:
            return str(error)

    monkeypatch.setattr(entry, "_new", acquire)
    monkeypatch.setattr(entry, "run_h20_phase_transport", transport)
    monkeypatch.setattr(entry, "publish_h20_phase_result", lambda **_: None)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(invoke) for _ in range(2)]
        results = [future.result(timeout=10) for future in futures]
    assert sorted(results) == ["H20_PHASE_ENTRY_CLAIM", "H20_PHASE_RESULT_PUBLISHED"]
    assert started == [True]
