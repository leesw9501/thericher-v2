import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from conftest import SCRATCH_USAGE, scratch_disk_usage
from thericher_v2.execution import kis_private_daily_collector as storage


def captured_default(path, disk_usage=shutil.disk_usage):
    return disk_usage(path)


@pytest.fixture(scope="module")
def module_capacity(tmp_path_factory):
    return captured_default(tmp_path_factory.mktemp("module-disk-capacity"))


def test_module_scoped_setup_has_owned_scratch_capacity(module_capacity):
    assert module_capacity == SCRATCH_USAGE


def test_default_captured_during_collection_uses_owned_scratch(tmp_path):
    assert captured_default(tmp_path) == SCRATCH_USAGE


def test_only_owned_resolved_scratch_has_synthetic_capacity(tmp_path):
    queried = []
    real_value = object()

    def real(path):
        queried.append(path)
        return real_value

    assert scratch_disk_usage(tmp_path / "absent", root=tmp_path, real=real) == SCRATCH_USAGE
    outside = tmp_path / ".." / "not-owned"
    assert scratch_disk_usage(outside, root=tmp_path, real=real) is real_value
    assert scratch_disk_usage(42, root=tmp_path, real=real) is real_value
    assert queried == [tmp_path / "absent", outside, 42]


def test_real_capacity_error_outside_scratch_is_not_hidden(tmp_path):
    def real(_):
        raise PermissionError("synthetic denied volume")

    with pytest.raises(PermissionError):
        scratch_disk_usage(tmp_path.parent, root=tmp_path, real=real)


def test_missing_owned_path_keeps_its_actual_filesystem_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        scratch_disk_usage(tmp_path / "missing", root=tmp_path, real=os.stat)


def test_actual_link_escape_uses_real_capacity_and_keeps_target(tmp_path):
    owned, outside = tmp_path / "owned", tmp_path / "outside"
    owned.mkdir()
    outside.mkdir()
    identity = (outside.stat().st_dev, outside.stat().st_ino)
    link = owned / "escape"
    try:
        if os.name == "nt":
            result = subprocess.run(
                [
                    str(Path("C:/Windows/System32/cmd.exe")),
                    "/d",
                    "/c",
                    "mklink",
                    "/J",
                    str(link),
                    str(outside),
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=5,
            )
            assert result.returncode == 0
            assert link.lstat().st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT
        else:
            link.symlink_to(outside, target_is_directory=True)
        real_value = object()
        queried = []

        def real(path):
            queried.append(path)
            return real_value

        assert scratch_disk_usage(link, root=owned, real=real) is real_value
        assert queried == [link]
    finally:
        if os.path.lexists(link):
            assert link.resolve(strict=True) == outside.resolve(strict=True)
            assert (outside.stat().st_dev, outside.stat().st_ino) == identity
            if os.name == "nt":
                assert link.lstat().st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT
                link.rmdir()
            else:
                assert link.is_symlink()
                link.unlink()
        assert not os.path.lexists(link)
        assert (outside.stat().st_dev, outside.stat().st_ino) == identity


def test_actual_projected_floor_still_rejects_inside_scratch(tmp_path):
    boundary = SCRATCH_USAGE.free - int(SCRATCH_USAGE.total * 0.15)
    kwargs = dict(cache_root=tmp_path / "cache", repo_root=tmp_path / "repo")
    assert not storage.private_daily_cache_would_cross_free_space_floor(
        **kwargs, projected_bytes=boundary
    )
    assert storage.private_daily_cache_would_cross_free_space_floor(
        **kwargs, projected_bytes=boundary + 1
    )
    assert not Path(kwargs["cache_root"]).exists()
