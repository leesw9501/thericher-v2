from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def test_daily_head_uses_the_same_control_root_as_daily_and_intraday_workers() -> None:
    script = _load_script()

    root = script._shared_control_root(
        Path("D:/market_data/us_equities/kis_paper_private/daily-head/v1")
    )

    assert root == Path("D:/market_data/us_equities/kis_paper_private/collection-control-v1")


def _load_script() -> ModuleType:
    script_path = Path(__file__).parents[1] / "scripts" / "collect_kis_paper_daily_spy_head.py"
    spec = importlib.util.spec_from_file_location(
        "collect_kis_paper_daily_spy_head_for_test",
        script_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
