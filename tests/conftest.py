"""Keep collector/model unit storage independent of the host scratch volume."""

from __future__ import annotations

import os
import shutil
from collections import namedtuple
from pathlib import Path

import pytest

ScratchUsage = namedtuple("ScratchUsage", "total used free")
SCRATCH_USAGE = ScratchUsage(10**12, 10**11, 9 * 10**11)
_REAL_DISK_USAGE = shutil.disk_usage
_ACTIVE_ROOT: Path | None = None


def scratch_disk_usage(path, *, root: Path, real):
    try:
        candidate = Path(os.path.realpath(os.fsdecode(os.fspath(path))))
    except (TypeError, ValueError, OSError):
        return real(path)
    if candidate.is_relative_to(root):
        real(path)  # Preserve missing/denied-path errors before replacing capacity facts.
        return SCRATCH_USAGE
    return real(path)


def _scoped_disk_usage(path):
    if _ACTIVE_ROOT is None:
        return _REAL_DISK_USAGE(path)
    return scratch_disk_usage(path, root=_ACTIVE_ROOT, real=_REAL_DISK_USAGE)


def pytest_configure(config):
    # Install before collection so imported default arguments retain this proxy.
    patch = pytest.MonkeyPatch()
    patch.setattr(shutil, "disk_usage", _scoped_disk_usage)
    config._thericher_scratch_disk_patch = patch


def pytest_unconfigure(config):
    patch = getattr(config, "_thericher_scratch_disk_patch", None)
    if patch is not None:
        patch.undo()


@pytest.fixture(scope="session", autouse=True)
def owned_scratch_capacity(tmp_path_factory):
    global _ACTIVE_ROOT
    previous = _ACTIVE_ROOT
    _ACTIVE_ROOT = tmp_path_factory.getbasetemp().resolve()
    try:
        yield
    finally:
        _ACTIVE_ROOT = previous
