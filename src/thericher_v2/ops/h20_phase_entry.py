"""Protected, import-only caller for the single Dec1 H20 read opportunity."""

import os
from hashlib import sha256
from pathlib import Path

from thericher_v2.execution.paper_peer_visit import _new, _read, ordinary
from thericher_v2.ops.h20_phase_host import HARD_STOP, LAST_START, OPENS, _need, _strict_json
from thericher_v2.ops.h20_phase_publication import publish_h20_phase_result
from thericher_v2.ops.h20_phase_transport import _utc_now, run_h20_phase_transport

_SCHEMA = "H20_DEC1_PHASE_ENTRY_V1"
_FIELDS = {
    "schema", "caller_sha256", "launcher", "guest_sha256", "source_pin", "image",
    "binding", "run", "claim", "protected_digest",
}


def _pin(value):
    return (
        type(value) is str
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


def _path(value):
    path = Path(value)
    _need(path.is_absolute())
    if os.name == "nt":
        _need(len(path.drive) == 2 and path.drive[0].isascii() and path.drive[0].isalpha())
    for part in path.parts[1:]:
        _need(":" not in part and part.rstrip(" .") == part)
        if os.name == "nt":
            is_reserved = getattr(os.path, "isreserved", None)
            _need(not (is_reserved(part) if is_reserved is not None else Path(part).is_reserved()))
    ordinary(path)
    _need(path.resolve() == path)
    return path


def _separate(left, right):
    return not left.is_relative_to(right) and not right.is_relative_to(left)


def run_h20_phase_entry(*, profile_path, profile_sha256):
    """Consume a prebound protected profile once, returning only a status.

    The trusted launcher supplies the profile pin independently of its bytes.
    "launcher" names the actual source file used by native caller identity;
    "caller_sha256" pins this module. The release/bootstrap must protect and
    verify executing code before import and bind the Scheduler action, owner,
    and ACLs independently. This function does not attest Scheduler origin.
    The claim and run are never cleared here, including on failure.
    """
    stage = "ADMISSION"
    try:
        observed = _utc_now()
        _need(OPENS <= observed < LAST_START and _pin(profile_sha256))
        profile_path = _path(profile_path)
        profile_snapshot = _read(profile_path)
        _need(sha256(profile_snapshot[0]).hexdigest() == profile_sha256)
        profile = _strict_json(profile_snapshot[0])
        _need(type(profile) is dict and profile.keys() == _FIELDS and profile["schema"] == _SCHEMA)
        _need(all(_pin(profile[key]) for key in ("caller_sha256", "guest_sha256", "source_pin")))
        image, binding, launcher_ref = (profile[key] for key in ("image", "binding", "launcher"))
        _need(type(image) is str and image.startswith("sha256:") and _pin(image[7:]))
        _need(type(binding) is dict and type(launcher_ref) is dict)
        _need(launcher_ref.keys() == {"path", "sha256"} and _pin(launcher_ref["sha256"]))

        caller, launcher = _path(__file__), _path(launcher_ref["path"])
        snapshots = {profile_path: profile_snapshot}
        for path, pin in ((caller, profile["caller_sha256"]), (launcher, launcher_ref["sha256"])):
            snapshot = _read(path)
            _need(sha256(snapshot[0]).hexdigest() == pin)
            _need(snapshots.setdefault(path, snapshot) == snapshot)

        run, claim, digest = (_path(profile[key]) for key in ("run", "claim", "protected_digest"))
        outputs = (run, claim, digest)
        for index, path in enumerate(outputs):
            _need(path.parent.is_dir() and not path.exists())
            _need(all(_separate(path, other) for other in (*outputs[:index], *snapshots)))

        def unchanged():
            return all(_read(path) == snapshot for path, snapshot in snapshots.items())

        _need(unchanged() and observed <= _utc_now() < LAST_START)
        stage = "CLAIM"
        claim_snapshot = _new(claim, b"H20_DEC1_PHASE_ATTEMPT_CONSUMED\n")
        ordinary(run)
        run.mkdir(mode=0o700)

        stage = "TRANSPORT"
        _need(
            unchanged()
            and _read(claim) == claim_snapshot
            and observed <= _utc_now() < LAST_START
        )
        completed = run_h20_phase_transport(
            binding=binding,
            out=run,
            entry_file=launcher,
            entry_sha256=launcher_ref["sha256"],
            guest_sha256=profile["guest_sha256"],
            image=image,
        )

        stage = "PUBLICATION"
        _need(unchanged() and _read(claim) == claim_snapshot and observed <= _utc_now() < HARD_STOP)
        publish_h20_phase_result(
            run=run,
            protected_digest=digest,
            source_pin=profile["source_pin"],
            binding=binding,
            coordinator_pin=launcher_ref["sha256"],
            completed=completed,
        )
        return "H20_PHASE_RESULT_PUBLISHED"
    except Exception:
        # A launcher must never emit native exception details or file contents.
        pass
    raise ValueError("H20_PHASE_ENTRY_" + stage)
