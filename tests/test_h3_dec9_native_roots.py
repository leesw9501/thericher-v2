"""Exercise only synthetic directories through the actual Dec9 Windows ABI."""

import sys
from contextlib import ExitStack

import pytest

from thericher_v2.ops.h3_dec9_native_roots import NativeRootScope, _Native

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="requires Windows")


def test_creator_and_ancestors_remain_pinned_until_scope_exit(tmp_path):
    parent = tmp_path / "parent"
    parent.mkdir()
    run = parent / "run"
    capture = run / "capture"
    api = _Native()
    with ExitStack() as lifetime:
        scope = NativeRootScope(lifetime)
        chain = scope.parents(run)
        assert tuple(item.path for item in chain) == tuple(reversed(run.parents))
        creator = scope.create(run)
        assert scope.parents(capture)[-1] is creator
        child = scope.create(capture)
        (capture / "invented.txt").write_text("child mutation is not prevented", encoding="ascii")
        scope.verify()
        for held in (chain[-1], creator, child):
            assert api.identity(held.handle) == held.identity
            with pytest.raises(OSError) as failure:
                held.path.rename(held.path.with_name(f"{held.path.name}-moved"))
            assert failure.value.winerror in {5, 32}
        (capture / "invented.txt").unlink()
        with pytest.raises(OSError) as failure:
            capture.rmdir()
        assert failure.value.winerror in {5, 32}

    for held in (chain[-1], creator, child):
        moved = held.path.with_name(f"{held.path.name}-moved")
        held.path.rename(moved)
        moved.rename(held.path)
    capture.rmdir()


def test_create_new_cannot_register_or_alter_an_existing_leaf(tmp_path):
    existing = tmp_path / "existing"
    existing.mkdir()
    sentinel = existing / "untouched.txt"
    sentinel.write_bytes(b"untouched")
    with ExitStack() as lifetime:
        scope = NativeRootScope(lifetime)
        scope.parents(existing)
        with pytest.raises(ValueError, match="^dec9_native_directory_custody$"):
            scope.create(existing)
        scope.verify()
    assert tuple(existing.iterdir()) == (sentinel,)
    assert sentinel.read_bytes() == b"untouched"
