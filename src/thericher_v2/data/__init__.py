"""Data helpers with a lazy compatibility surface for direct source leaves."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

_PACKAGE_DIRECTORY = Path(__file__).resolve().parent


def __getattr__(name: str) -> Any:
    """Load a direct data leaf first, then retain legacy public imports on demand."""

    if not name.startswith("_") and (_PACKAGE_DIRECTORY / f"{name}.py").is_file():
        return import_module(f".{name}", __name__)
    return getattr(import_module("._public_api", __name__), name)


def __dir__() -> list[str]:
    """Expose legacy public names without eager package import at startup."""

    public_api = import_module("._public_api", __name__)
    return sorted(set(globals()) | set(public_api.__all__))
