from __future__ import annotations

import ast
import importlib.util
import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.data import kis_paper_daily_forward_causal_qualification as qualification
from thericher_v2.data.kis_paper_daily_pair_forward_cache import (
    KisPaperDailyPairForwardRow,
    commit_kis_paper_daily_pair_forward_observation,
)


def test_every_single_condition_ablation_fails_closed() -> None:
    evidence = _all_satisfied_evidence()

    result = qualification.evaluate_kis_daily_forward_causal_qualification(evidence)
    assert result.status == "qualified"

    for condition_id in qualification.KIS_DAILY_FORWARD_CAUSAL_QUALIFICATION_CONDITION_IDS:
        ablated = replace(
            evidence,
            conditions=tuple(
                qualification.KisDailyForwardCausalCondition(
                    candidate_id,
                    "not_observed" if candidate_id == condition_id else "satisfied",
                )
                for candidate_id in (
                    qualification.KIS_DAILY_FORWARD_CAUSAL_QUALIFICATION_CONDITION_IDS
                )
            ),
        )
        result = qualification.evaluate_kis_daily_forward_causal_qualification(ablated)

        assert result.status == "input_unavailable"
        assert result.missing_condition_ids == (condition_id,)


def test_current_cache_names_unobserved_runtime_facts_without_inferring_them(
    tmp_path: Path,
) -> None:
    repo_root, artifact_root, cache_root, parent_receipt = _current_cache_fixture(tmp_path)

    result = qualification.qualify_current_kis_paper_daily_pair_forward_cache(
        cache_root=cache_root,
        parent_receipt_path=parent_receipt,
        artifact_root=artifact_root,
        repository_root=repo_root,
    )

    statuses = {
        condition.condition_id: condition.status for condition in result.evidence.conditions
    }
    assert result.status == "input_unavailable"
    assert statuses["source_pair_identity"] == "satisfied"
    assert statuses["non_overlapping_chronological_boundary"] == "satisfied"
    assert statuses["named_clock_session_rule"] == "not_observed"
    assert statuses["decision_time_availability"] == "not_observed"
    assert statuses["provider_finality"] == "not_observed"
    assert "decision_time_availability" in result.missing_condition_ids
    assert "provider_finality" in result.missing_condition_ids


def test_parent_identity_mismatch_is_a_scoped_unavailable_condition(tmp_path: Path) -> None:
    repo_root, artifact_root, cache_root, parent_receipt = _current_cache_fixture(tmp_path)
    document = json.loads(parent_receipt.read_text(encoding="utf-8"))
    document["payload"]["cache"]["cache_sha256"] = _sha("different")
    parent_receipt.write_bytes(_canonical_json(document).encode("utf-8"))

    result = qualification.qualify_current_kis_paper_daily_pair_forward_cache(
        cache_root=cache_root,
        parent_receipt_path=parent_receipt,
        artifact_root=artifact_root,
        repository_root=repo_root,
    )

    statuses = {
        condition.condition_id: condition.status for condition in result.evidence.conditions
    }
    assert result.status == "input_unavailable"
    assert statuses["source_pair_identity"] == "not_satisfied"


def test_receipt_is_external_immutable_and_source_safe(tmp_path: Path) -> None:
    repo_root, artifact_root, cache_root, parent_receipt = _current_cache_fixture(tmp_path)
    result = qualification.qualify_current_kis_paper_daily_pair_forward_cache(
        cache_root=cache_root,
        parent_receipt_path=parent_receipt,
        artifact_root=artifact_root,
        repository_root=repo_root,
    )

    receipt = qualification.write_kis_daily_forward_causal_qualification_receipt(
        result=result,
        artifact_root=artifact_root,
        repository_root=repo_root,
        run_label="current-r1",
    )

    assert receipt.receipt_path.is_relative_to(artifact_root)
    assert receipt.receipt_sha256 == _sha(receipt.receipt_path.read_bytes())
    payload = json.loads(receipt.receipt_path.read_text(encoding="utf-8"))
    _assert_source_safe(payload)
    assert payload["status"] == "input_unavailable"
    assert payload["limits"] == {
        "network_access": False,
        "credentials_read": False,
        "kis_client_constructed": False,
        "docker_or_scheduler_invoked": False,
        "broker_or_paper_action": False,
        "gpu_used": False,
        "raw_market_data_in_receipt": False,
        "research_or_execution_consumer_allowed": False,
    }

    with pytest.raises(qualification.KisDailyForwardCausalQualificationError):
        qualification.write_kis_daily_forward_causal_qualification_receipt(
            result=result,
            artifact_root=artifact_root,
            repository_root=repo_root,
            run_label="current-r1",
        )
    with pytest.raises(ValueError, match="outside the Git workspace"):
        qualification.write_kis_daily_forward_causal_qualification_receipt(
            result=result,
            artifact_root=repo_root,
            repository_root=repo_root,
            run_label="repo-output",
        )


def test_module_and_runner_do_not_import_runtime_or_execution_paths() -> None:
    module_path = Path(qualification.__file__).resolve()
    runner_path = (
        module_path.parents[3]
        / "scripts"
        / "run_kis_daily_forward_causal_qualification.py"
    )

    for path in (module_path, runner_path):
        imports = _imports(path)
        assert not any(name.startswith("thericher_v2.execution") for name in imports)
        assert not any(
            name.split(".", 1)[0] in {"requests", "socket", "subprocess", "urllib"}
            for name in imports
        )
        source = path.read_text(encoding="utf-8")
        assert ".env" not in source
        assert "os.environ" not in source


def test_runner_writes_only_the_sanitized_projection(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _repo_root, artifact_root, cache_root, parent_receipt = _current_cache_fixture(tmp_path)
    runner = _load_runner()

    runner.main(
        [
            "--run-label",
            "script-r1",
            "--parent-receipt",
            str(parent_receipt),
            "--cache-root",
            str(cache_root),
            "--artifact-root",
            str(artifact_root),
        ]
    )

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["status"] == "input_unavailable"
    assert payload["receipt_sha256"].startswith("sha256:")
    assert payload["receipt_path_relative_to_artifact_root"].startswith(
        "data/kis-daily-forward-causal-qualification-v1/run=script-r1/"
    )
    assert str(cache_root) not in output


def _all_satisfied_evidence() -> qualification.KisDailyForwardCausalQualificationEvidence:
    return qualification.KisDailyForwardCausalQualificationEvidence(
        cache_id="kis.paper.private.daily.qqq-spy.forward-v1",
        cache_version="kis-paper-daily-qqq-spy-forward-v1",
        cache_index_sha256=_sha("index"),
        cache_sha256=_sha("cache"),
        frozen_boundary=date(2026, 7, 24),
        forward_common_session_count=3,
        forward_common_sessions_sha256=_sha("sessions"),
        parent_receipt_sha256=_sha("parent"),
        parent_receipt_relative_path=(
            "data/kis-paper-daily-pair-forward-v1/run=fixture/receipt.json"
        ),
        conditions=tuple(
            qualification.KisDailyForwardCausalCondition(condition_id, "satisfied")
            for condition_id in qualification.KIS_DAILY_FORWARD_CAUSAL_QUALIFICATION_CONDITION_IDS
        ),
    )


def _current_cache_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    repo_root = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    cache_root = tmp_path / "market" / "pair-forward"
    repo_root.mkdir()
    artifact_root.mkdir()
    run = commit_kis_paper_daily_pair_forward_observation(
        rows_by_target={
            "QQQ/NAS": _rows("QQQ", "NAS"),
            "SPY/AMS": _rows("SPY", "AMS"),
        },
        failure_reasons_by_target={},
        cache_root=cache_root,
        repo_root=repo_root,
    )
    parent_receipt = (
        artifact_root
        / "data"
        / "kis-paper-daily-pair-forward-v1"
        / "run=fixture"
        / "receipt.json"
    )
    parent_receipt.parent.mkdir(parents=True)
    parent_receipt.write_bytes(
        _canonical_json(
            {
                "kind": "kis_paper_daily_pair_forward_receipt",
                "observed_at_bucket": "2026-07-30T00:00Z",
                "payload": {
                    "status": "ready",
                    "runtime_contract_sha256": _sha("runtime-contract"),
                    "observed_at_bucket": "2026-07-30T00:00Z",
                    "accepted_page_count": 2,
                    "categorical_failure_count": 0,
                    "changed_target_count": 2,
                    "recovery": "complete",
                    "cache": run.cache.safe_payload(),
                    "route_isolation": {
                        "daily_market_data_only": True,
                        "account_endpoints_used": False,
                        "order_endpoints_used": False,
                        "live_endpoints_used": False,
                    },
                },
                "artifact_policy": {
                    "raw_market_data_in_receipt": False,
                    "credentials_in_receipt": False,
                    "account_data_in_receipt": False,
                    "repo_storage_allowed": False,
                },
            }
        ).encode("utf-8")
    )
    return repo_root, artifact_root, cache_root, parent_receipt


def _rows(symbol: str, exchange: str) -> tuple[KisPaperDailyPairForwardRow, ...]:
    return tuple(
        KisPaperDailyPairForwardRow(
            symbol=symbol,
            exchange=exchange,
            session_date=session,
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("1000"),
        )
        for session in (date(2026, 7, 27), date(2026, 7, 28), date(2026, 7, 29))
    )


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    return imports


def _load_runner():
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_kis_daily_forward_causal_qualification.py"
    )
    specification = importlib.util.spec_from_file_location(
        "daily_forward_qualification_runner", path
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _assert_source_safe(value: object) -> None:
    forbidden = {
        "account",
        "bars",
        "close",
        "credentials",
        "high",
        "low",
        "open",
        "order",
        "orders",
        "position",
        "price",
        "prices",
        "raw_row",
        "raw_rows",
        "rows",
        "volume",
    }
    if isinstance(value, dict):
        for key, nested in value.items():
            assert key.lower() not in forbidden
            _assert_source_safe(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_source_safe(nested)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"


def _sha(value: str | bytes) -> str:
    encoded = value.encode("utf-8") if isinstance(value, str) else value
    import hashlib

    return "sha256:" + hashlib.sha256(encoded).hexdigest()
