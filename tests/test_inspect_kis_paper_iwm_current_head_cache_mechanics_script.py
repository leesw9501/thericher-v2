from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

from thericher_v2.data.kis_paper_iwm_current_head_cache_mechanics import (
    KisPaperIwmCurrentHeadCacheMechanics,
    KisPaperIwmCurrentHeadCacheMechanicsReceipt,
)

SCRIPT = (
    Path(__file__).parents[1]
    / "scripts"
    / "inspect_kis_paper_iwm_current_head_cache_mechanics.py"
)


def test_script_prints_only_safe_mechanics_payload(monkeypatch, tmp_path: Path, capsys) -> None:
    script = _load_script()
    receipt = KisPaperIwmCurrentHeadCacheMechanicsReceipt(
        mechanics=KisPaperIwmCurrentHeadCacheMechanics(
            index_generation=1,
            indexed_retained_chunk_count=1,
            collection_scope="head",
            bar_count=3,
            complete_bar_count=2,
            incomplete_bar_count=1,
            adjacent_m1_pair_count=2,
            non_adjacent_pair_count=0,
            maximum_interbar_seconds=60,
        ),
        evidence_path=tmp_path / "private-path" / "receipt.json",
        evidence_sha256="sha256:" + "a" * 64,
    )
    monkeypatch.setattr(
        script,
        "inspect_and_write_kis_paper_iwm_current_head_cache_mechanics",
        lambda **_kwargs: receipt,
    )

    assert script.main([]) == 0

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["status"] == "verified"
    assert payload["evidence_sha256"] == receipt.evidence_sha256
    assert str(receipt.evidence_path) not in output
    assert "access_token" not in output


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "inspect_kis_paper_iwm_current_head_cache_mechanics_for_test",
        SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("script module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
