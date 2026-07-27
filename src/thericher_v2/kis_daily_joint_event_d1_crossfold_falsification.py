"""Fixed, aggregate-only falsification for the three D1 screen folds.

This deliberately verifies fixed external summary evidence instead of creating a
campaign, pooled score, selection result, replay, or execution input.
"""

from __future__ import annotations

import hashlib
import json
import math
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from thericher_v2.kis_daily_joint_event_window_contract import (
    is_container_external_mount,
)

KIS_DAILY_JOINT_EVENT_D1_CROSSFOLD_FALSIFICATION_SCHEMA_VERSION = 1
KIS_DAILY_JOINT_EVENT_D1_CROSSFOLD_FALSIFICATION_ID = (
    "kis-daily-joint-event-d1-crossfold-falsification-v1"
)
KIS_DAILY_JOINT_EVENT_D1_CROSSFOLD_FALSIFICATION_KIND = (
    "kis_daily_joint_event_d1_crossfold_falsification"
)
KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_ID = "kis-daily-joint-event-d1-sequence-screen-v1"
KIS_DAILY_JOINT_EVENT_D1_CROSSFOLD_RULE_ID = "strictly_exceeds_fold_local_class_majority_v1"
KIS_DAILY_JOINT_EVENT_D1_CROSSFOLD_CANDIDATE_IDS = ("linear", "compact_gru")

ScreenMode = Literal["cpu-smoke", "cuda-screen"]
Conclusion = Literal["falsified", "inconclusive"]


@dataclass(frozen=True, slots=True)
class KisDailyJointEventD1CrossfoldCandidateSpec:
    """One frozen candidate specification expected in a source summary."""

    candidate_id: str
    backend: str
    epochs: int
    family: str
    hidden_size: int
    seed: int

    def document(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "epochs": self.epochs,
            "family": self.family,
            "hidden_size": self.hidden_size,
            "seed": self.seed,
        }


@dataclass(frozen=True, slots=True)
class KisDailyJointEventD1CrossfoldFoldPin:
    """One fold's immutable lineage and expected aggregate screen shape."""

    fold_id: str
    fold_input_identity: str
    materializer_identity: str
    target_cost_identity: str
    normalization_identity: str
    development_decision_count: int
    validation_decision_count: int
    legacy_source_without_fold_id: bool = False

    def source_document(self) -> dict[str, object]:
        source: dict[str, object] = {
            "fold_input_identity": self.fold_input_identity,
            "materializer_identity": self.materializer_identity,
            "normalization_identity": self.normalization_identity,
            "target_cost_identity": self.target_cost_identity,
        }
        if not self.legacy_source_without_fold_id:
            source["fold_id"] = self.fold_id
        return source


@dataclass(frozen=True, slots=True)
class KisDailyJointEventD1CrossfoldArtifactPin:
    """One exact immutable source summary/precommit pair."""

    fold: KisDailyJointEventD1CrossfoldFoldPin
    mode: ScreenMode
    run_label: str
    summary_sha256: str
    precommit_sha256: str
    result_identity: str
    screen_precommit_identity: str

    def source_document(self) -> dict[str, object]:
        return {
            "candidate_spec_identity": _candidate_spec_identity(self.mode),
            "development_decision_count": self.fold.development_decision_count,
            "fold_id": self.fold.fold_id,
            "fold_input_identity": self.fold.fold_input_identity,
            "materializer_identity": self.fold.materializer_identity,
            "mode": self.mode,
            "normalization_identity": self.fold.normalization_identity,
            "precommit_sha256": self.precommit_sha256,
            "result_identity": self.result_identity,
            "run_label": self.run_label,
            "screen_precommit_identity": self.screen_precommit_identity,
            "summary_sha256": self.summary_sha256,
            "target_cost_identity": self.fold.target_cost_identity,
            "validation_decision_count": self.fold.validation_decision_count,
        }


@dataclass(frozen=True, slots=True)
class KisDailyJointEventD1CrossfoldObservation:
    """One fold-local candidate conclusion, never a cross-fold ranking."""

    fold_id: str
    mode: ScreenMode
    run_label: str
    candidate_id: str
    evaluated_count: int
    observed_positive_count: int
    class_majority_correct_count: int
    candidate_correct_count: int
    conclusion: Conclusion

    def document(self) -> dict[str, object]:
        return {
            "candidate_correct_count": self.candidate_correct_count,
            "candidate_id": self.candidate_id,
            "class_majority_correct_count": self.class_majority_correct_count,
            "conclusion": self.conclusion,
            "evaluated_count": self.evaluated_count,
            "fold_id": self.fold_id,
            "mode": self.mode,
            "observed_positive_count": self.observed_positive_count,
            "run_label": self.run_label,
        }


@dataclass(frozen=True, slots=True)
class KisDailyJointEventD1CrossfoldFalsificationRun:
    """External evidence paths plus in-memory fold-local conclusions."""

    precommit_path: Path
    precommit_identity: str
    summary_path: Path
    result_identity: str
    observations: tuple[KisDailyJointEventD1CrossfoldObservation, ...]


@dataclass(frozen=True, slots=True)
class _AttestedCandidateAggregate:
    candidate_id: str
    evaluated_count: int
    observed_positive_count: int
    candidate_correct_count: int


@dataclass(frozen=True, slots=True)
class _AttestedScreenSummary:
    pin: KisDailyJointEventD1CrossfoldArtifactPin
    candidates: tuple[_AttestedCandidateAggregate, ...]


_E1_FOLD = KisDailyJointEventD1CrossfoldFoldPin(
    fold_id="expanding-1",
    fold_input_identity="sha256:b019c7e9a10eb2add48bbaa815c046a9b216ca9069c4ca8e4f836bc91085a1db",
    materializer_identity="sha256:d8b096b6bb9e38aad7976cebff61ffb628a913da0e05be4a345dec4f8e41d772",
    target_cost_identity="sha256:2c0ecbb889b8f1660929e87458e4a90d01f2390e41b25ed47e7201ab8a94b842",
    normalization_identity="sha256:afc094bc5d10dc3d0bd75265cd834a8c3a150f336491244bf8b8786756e24ddc",
    development_decision_count=2345,
    validation_decision_count=146,
    # E1 predates the explicit source fold_id field and is accepted only by this pin.
    legacy_source_without_fold_id=True,
)
_E2_FOLD = KisDailyJointEventD1CrossfoldFoldPin(
    fold_id="expanding-2",
    fold_input_identity="sha256:6507570e49022133ff1055d49d610a6c32e80b92c0f881115f67d9e68e899f4e",
    materializer_identity="sha256:280c3cfd8cd920aa412ea446a68d26de97e5f84c6580dd2511ccf1d94744d4bc",
    target_cost_identity="sha256:cd58b52816a7d0a744f8fce42a384091ce8ea9290c73316b699579a1a16291a0",
    normalization_identity="sha256:e44d8a1cd54579eb1bf520bf842f03450746a1d98520f15157396e5e3292d287",
    development_decision_count=2511,
    validation_decision_count=128,
)
_E3_FOLD = KisDailyJointEventD1CrossfoldFoldPin(
    fold_id="expanding-3",
    fold_input_identity="sha256:1cf334306f1e2cc0e907d688d697c850aaf6ca0ef7ed2c42ee807f2c9633d11e",
    materializer_identity="sha256:72c41ae3a2d6494d65879839ff8e93d6652352e8873928769b775f44726de43d",
    target_cost_identity="sha256:5511c3f072e81debe81c39792d6ca4b9500773ebf0d4029b9c7d501286176cc3",
    normalization_identity="sha256:0541d174b139feee5cbe7717fda81a3d7fe107c083790c038cbb83b184e8a312",
    development_decision_count=2671,
    validation_decision_count=145,
)

_CANDIDATE_SPECS_BY_MODE: dict[
    ScreenMode, tuple[KisDailyJointEventD1CrossfoldCandidateSpec, ...]
] = {
    "cpu-smoke": (
        KisDailyJointEventD1CrossfoldCandidateSpec(
            candidate_id="linear",
            backend="torch_cpu",
            epochs=2,
            family="linear",
            hidden_size=0,
            seed=2026072701,
        ),
        KisDailyJointEventD1CrossfoldCandidateSpec(
            candidate_id="compact_gru",
            backend="torch_cpu",
            epochs=2,
            family="compact_sequence_gru",
            hidden_size=16,
            seed=2026072702,
        ),
    ),
    "cuda-screen": (
        KisDailyJointEventD1CrossfoldCandidateSpec(
            candidate_id="linear",
            backend="torch_cuda",
            epochs=12,
            family="linear",
            hidden_size=0,
            seed=2026072701,
        ),
        KisDailyJointEventD1CrossfoldCandidateSpec(
            candidate_id="compact_gru",
            backend="torch_cuda",
            epochs=12,
            family="compact_sequence_gru",
            hidden_size=16,
            seed=2026072702,
        ),
    ),
}

KIS_DAILY_JOINT_EVENT_D1_CROSSFOLD_ARTIFACT_PINS = (
    KisDailyJointEventD1CrossfoldArtifactPin(
        fold=_E1_FOLD,
        mode="cpu-smoke",
        run_label="cpu-smoke-20260727-r1",
        summary_sha256="sha256:0a05df755d311c86938fddb66edc49632bb3306f3a567e7277b1f7d0ca6a991c",
        precommit_sha256="sha256:4b71f7da97b9fea29d9bd77b74d22a2197413dd87e364b0be0c8fda92adf9ede",
        result_identity="sha256:81e486a4d7e89ad5699b152dad7a725ce011476213617595abb8442ed65247f5",
        screen_precommit_identity="sha256:357147a59fd27efeb32fb2002b45ca380460f19aaadbbe4fb5dda13ac39d813b",
    ),
    KisDailyJointEventD1CrossfoldArtifactPin(
        fold=_E1_FOLD,
        mode="cuda-screen",
        run_label="cuda-screen-20260727-r1",
        summary_sha256="sha256:20626e7a68a9abee45c5bddceb5ba8d290ca9036bfdda7bd60c8a45268a0b246",
        precommit_sha256="sha256:259230e3718754594ba6325a80904acb19c5599a2d32b88d69e3a3e7d64ef748",
        result_identity="sha256:8c4e492c4d3976de94aa1b5bc45904c148696c24985aaaad953c0836aea32068",
        screen_precommit_identity="sha256:7e4ac65859f087073c27fcda13b641ce2c75c3f633c4f820d91fb07e2eed60e9",
    ),
    KisDailyJointEventD1CrossfoldArtifactPin(
        fold=_E2_FOLD,
        mode="cpu-smoke",
        run_label="cpu-smoke-expanding-2-20260727-r1",
        summary_sha256="sha256:384ca348052dc4db5fa1153ab3332e86576fbedde2da737d21f7ff709f5482ce",
        precommit_sha256="sha256:6127cd1c65ed51eb9f23482c1d0c1414d0af361dfdd91dfe1d7ce3563d6c3b2c",
        result_identity="sha256:96a29b18e95e495a8ccfb0146b8654dadde37118ca99c672ef48c55b20a7106e",
        screen_precommit_identity="sha256:ae59bc53356d215a8fd10babb195f14afcdde175600d45b12b52153f6c034acb",
    ),
    KisDailyJointEventD1CrossfoldArtifactPin(
        fold=_E2_FOLD,
        mode="cuda-screen",
        run_label="cuda-screen-expanding-2-20260727-r1",
        summary_sha256="sha256:bbb99e6a99bf90cb7bf6a1e418c754d5e97fd9e7ad4112bd134953af40d70e20",
        precommit_sha256="sha256:a35031db2a073a8e11842e75352b7862bd2197e8e799f66713ebffa5072651da",
        result_identity="sha256:233629de1a3fc1a4c0a1ab2a1d86f7a0d0c4c387c3a6a26a169442f380b2826e",
        screen_precommit_identity="sha256:d75d27de2fb5bc9c2401c3f243b3053cc03ad34c9970e4591c0433f870fa04eb",
    ),
    KisDailyJointEventD1CrossfoldArtifactPin(
        fold=_E3_FOLD,
        mode="cpu-smoke",
        run_label="cpu-smoke-expanding-3-20260727-r1",
        summary_sha256="sha256:d9ff89bd98d24f4c496968a6d8d6186cbf243d2180e100c2e02f9506d26e8d85",
        precommit_sha256="sha256:f0614bb27abe5f4dd1e281c49862f315ece0213b865d6e9c36ebef4956d89716",
        result_identity="sha256:438b720b0aeb6e95b884d03b9e60add9e10b63030544af94a4451783b7c20e87",
        screen_precommit_identity="sha256:ed1e07fe352cf3659fe86aef209dcdf967eac2bf6ab039566c2dc6fb139ec025",
    ),
    KisDailyJointEventD1CrossfoldArtifactPin(
        fold=_E3_FOLD,
        mode="cuda-screen",
        run_label="cuda-screen-expanding-3-20260727-r1",
        summary_sha256="sha256:3b53f03628e121f03e1ae269f376f5526b5c7fdae88900682cd9b13805d80119",
        precommit_sha256="sha256:1c369f8ac052b21c297330ac0db5fee97618a3794a7f32c4472a5086835c7fe8",
        result_identity="sha256:f3ad319969ac2b59965e1a545ef52cd17bb7afef9135c45cb4b250402803922a",
        screen_precommit_identity="sha256:2ed3c0abfa510205b2c1a9517354005964e99c7b9aac6a1bc32fb21312778474",
    ),
)

_EXPECTED_SCOPE = {
    "offline_only": True,
    "candidate_only": True,
    "model_execution_eligible": False,
    "candidate_selection_eligible": False,
    "ensemble_eligible": False,
    "replay_materialized": False,
    "paper_decision_eligible": False,
    "raw_market_data_persisted": False,
    "feature_values_persisted": False,
    "target_values_persisted": False,
    "per_decision_outputs_persisted": False,
    "credentials_persisted": False,
}
_EXPECTED_ARTIFACT_POLICY = {"repo_storage_allowed": False, "immutable_write_only": True}
_EXPECTED_SHAPE = {"sequence_length": 20, "column_count": 3}
_EXPECTED_CLASSIFICATION = {"classification_only": True, "score_threshold": 0.5}
_EXPECTED_METRIC_KEYS = frozenset(
    {
        "accuracy",
        "evaluated_count",
        "f1",
        "false_negative_count",
        "false_positive_count",
        "observed_positive_count",
        "precision",
        "recall",
        "true_negative_count",
        "true_positive_count",
    }
)
_ALLOWED_ARTIFACT_KEYS = frozenset(
    {
        "artifact_policy",
        "candidate_correct_count",
        "candidate_id",
        "candidate_only",
        "candidate_selection_eligible",
        "candidate_spec_identity",
        "class_majority_correct_count",
        "conclusion",
        "credentials_persisted",
        "development_decision_count",
        "ensemble_eligible",
        "evaluated_count",
        "falsification_id",
        "feature_values_persisted",
        "fold_id",
        "fold_input_identity",
        "immutable_write_only",
        "input_pin_set_identity",
        "kind",
        "materializer_identity",
        "mode",
        "model_execution_eligible",
        "normalization_identity",
        "observation_count",
        "observations",
        "observed_positive_count",
        "offline_only",
        "paper_decision_eligible",
        "per_decision_outputs_persisted",
        "precommit_identity",
        "precommit_sha256",
        "raw_market_data_persisted",
        "replay_materialized",
        "repo_storage_allowed",
        "result_identity",
        "result_sha256",
        "rule_id",
        "run_label",
        "schema_version",
        "screen_precommit_identity",
        "scope",
        "source_summary_count",
        "sources",
        "status",
        "summary_sha256",
        "target_cost_identity",
        "target_values_persisted",
        "validation_decision_count",
    }
)


def run_kis_daily_joint_event_d1_crossfold_falsification(
    *,
    artifact_root: Path,
    run_label: str,
    repo_root: Path,
    pins: Sequence[
        KisDailyJointEventD1CrossfoldArtifactPin
    ] = KIS_DAILY_JOINT_EVENT_D1_CROSSFOLD_ARTIFACT_PINS,
) -> KisDailyJointEventD1CrossfoldFalsificationRun:
    """Verify six fixed summaries and persist fold-local falsification evidence."""

    _validate_run_label(run_label)
    resolved_root = _validate_external_artifact_root(
        artifact_root=artifact_root, repo_root=repo_root
    )
    pinned_summaries = _attest_pinned_summaries(artifact_root=resolved_root, pins=pins)
    output_dir = _create_external_output_dir(
        artifact_root=resolved_root,
        repo_root=repo_root,
        run_label=run_label,
    )
    precommit_payload = _precommit_document(pins=pins)
    precommit_identity = _sha256_json(precommit_payload)
    precommit_payload["precommit_identity"] = precommit_identity
    precommit_path = output_dir / "precommit.json"
    _write_source_safe_json_new(precommit_path, precommit_payload)
    observations = _build_fold_local_observations(pinned_summaries)
    summary_payload = _summary_document(
        pins=pins,
        precommit_identity=precommit_identity,
        observations=observations,
    )
    result_identity = _sha256_json(summary_payload)
    summary_payload["result_identity"] = result_identity
    summary_path = output_dir / "summary.json"
    _write_source_safe_json_new(summary_path, summary_payload)
    return KisDailyJointEventD1CrossfoldFalsificationRun(
        precommit_path=precommit_path,
        precommit_identity=precommit_identity,
        summary_path=summary_path,
        result_identity=result_identity,
        observations=observations,
    )


def _attest_pinned_summaries(
    *,
    artifact_root: Path,
    pins: Sequence[KisDailyJointEventD1CrossfoldArtifactPin],
) -> tuple[_AttestedScreenSummary, ...]:
    expected_pins = tuple(pins)
    if len(expected_pins) != 6 or len({(pin.fold.fold_id, pin.mode) for pin in expected_pins}) != 6:
        raise ValueError("cross-fold falsification pin set is invalid")
    source_root = artifact_root / KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_ID
    if _is_link_or_reparse_point(source_root) or not source_root.is_dir():
        raise ValueError("cross-fold source root is invalid")
    resolved_source_root = source_root.resolve(strict=True)
    if not resolved_source_root.is_relative_to(artifact_root):
        raise ValueError("cross-fold source root is invalid")
    return tuple(
        _attest_screen_pair(source_root=resolved_source_root, pin=pin) for pin in expected_pins
    )


def _attest_screen_pair(
    *,
    source_root: Path,
    pin: KisDailyJointEventD1CrossfoldArtifactPin,
) -> _AttestedScreenSummary:
    run_dir = source_root / pin.run_label
    if (
        _is_link_or_reparse_point(run_dir)
        or not run_dir.is_dir()
        or not run_dir.resolve().is_relative_to(source_root)
    ):
        raise ValueError("cross-fold pinned run directory is invalid")
    precommit = _read_pinned_document(
        path=run_dir / "precommit.json",
        root=source_root,
        expected_sha256=pin.precommit_sha256,
    )
    summary = _read_pinned_document(
        path=run_dir / "summary.json",
        root=source_root,
        expected_sha256=pin.summary_sha256,
    )
    _attest_precommit_document(document=precommit, pin=pin)
    candidates = _attest_summary_document(document=summary, pin=pin, precommit=precommit)
    return _AttestedScreenSummary(pin=pin, candidates=candidates)


def _read_pinned_document(*, path: Path, root: Path, expected_sha256: str) -> Mapping[str, object]:
    resolved_path = path.resolve(strict=True)
    if (
        _is_link_or_reparse_point(path)
        or not resolved_path.is_file()
        or not resolved_path.is_relative_to(root)
    ):
        raise ValueError("cross-fold pinned artifact path is invalid")
    encoded = resolved_path.read_bytes()
    if "sha256:" + hashlib.sha256(encoded).hexdigest() != expected_sha256:
        raise ValueError("cross-fold pinned artifact hash does not match")
    try:
        document = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("cross-fold pinned artifact is invalid") from error
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
    if encoded != canonical.encode("utf-8") or not isinstance(document, Mapping):
        raise ValueError("cross-fold pinned artifact is not canonical")
    return document


def _attest_precommit_document(
    *,
    document: Mapping[str, object],
    pin: KisDailyJointEventD1CrossfoldArtifactPin,
) -> None:
    if set(document) != {
        "artifact_policy",
        "candidates",
        "classification",
        "kind",
        "mode",
        "normalization",
        "precommit_identity",
        "schema_version",
        "scope",
        "screen_id",
        "shape",
        "source",
        "split",
        "status",
    }:
        raise ValueError("cross-fold screen precommit shape is invalid")
    identity = document.get("precommit_identity")
    identity_payload = dict(document)
    identity_payload.pop("precommit_identity", None)
    if identity != pin.screen_precommit_identity or _sha256_json(identity_payload) != identity:
        raise ValueError("cross-fold screen precommit identity is invalid")
    _attest_shared_screen_fields(document=document, pin=pin, expected_status="precommitted")
    if document.get("candidates") != _candidate_spec_documents(pin.mode):
        raise ValueError("cross-fold screen candidate specification is invalid")


def _attest_summary_document(
    *,
    document: Mapping[str, object],
    pin: KisDailyJointEventD1CrossfoldArtifactPin,
    precommit: Mapping[str, object],
) -> tuple[_AttestedCandidateAggregate, ...]:
    if set(document) != {
        "artifact_policy",
        "candidates",
        "classification",
        "kind",
        "mode",
        "normalization",
        "precommit_identity",
        "result_identity",
        "schema_version",
        "scope",
        "screen_id",
        "shape",
        "source",
        "split",
        "status",
    }:
        raise ValueError("cross-fold screen summary shape is invalid")
    identity = document.get("result_identity")
    identity_payload = dict(document)
    identity_payload.pop("result_identity", None)
    if identity != pin.result_identity or _sha256_json(identity_payload) != identity:
        raise ValueError("cross-fold screen result identity is invalid")
    if document.get("precommit_identity") != precommit.get("precommit_identity"):
        raise ValueError("cross-fold screen precommit linkage is invalid")
    _attest_shared_screen_fields(document=document, pin=pin, expected_status="complete")
    for key in (
        "artifact_policy",
        "classification",
        "normalization",
        "scope",
        "shape",
        "source",
        "split",
    ):
        if document.get(key) != precommit.get(key):
            raise ValueError("cross-fold screen summary diverges from precommit")
    return _attest_summary_candidates(candidates=document.get("candidates"), pin=pin)


def _attest_shared_screen_fields(
    *,
    document: Mapping[str, object],
    pin: KisDailyJointEventD1CrossfoldArtifactPin,
    expected_status: str,
) -> None:
    if (
        document.get("schema_version") != 1
        or document.get("kind") != "kis_daily_joint_event_d1_sequence_screen"
        or document.get("status") != expected_status
        or document.get("screen_id") != KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_ID
        or document.get("mode") != pin.mode
        or document.get("source") != pin.fold.source_document()
        or document.get("split")
        != {
            "development_decision_count": pin.fold.development_decision_count,
            "validation_decision_count": pin.fold.validation_decision_count,
            "untouched_tail_session_count": 151,
            "pre_validation_gap_consumed": False,
        }
        or document.get("shape") != _EXPECTED_SHAPE
        or document.get("normalization")
        != {
            "fit_scope": "development_only",
            "normalization_identity": pin.fold.normalization_identity,
        }
        or document.get("classification") != _EXPECTED_CLASSIFICATION
        or document.get("scope") != _EXPECTED_SCOPE
        or document.get("artifact_policy") != _EXPECTED_ARTIFACT_POLICY
    ):
        raise ValueError("cross-fold screen lineage or scope is incompatible")


def _attest_summary_candidates(
    *,
    candidates: object,
    pin: KisDailyJointEventD1CrossfoldArtifactPin,
) -> tuple[_AttestedCandidateAggregate, ...]:
    if not isinstance(candidates, list) or len(candidates) != len(
        KIS_DAILY_JOINT_EVENT_D1_CROSSFOLD_CANDIDATE_IDS
    ):
        raise ValueError("cross-fold screen candidates are invalid")
    expected_specs = _candidate_spec_documents(pin.mode)
    aggregates: list[_AttestedCandidateAggregate] = []
    for candidate, expected_spec in zip(candidates, expected_specs, strict=True):
        if not isinstance(candidate, Mapping) or set(candidate) != {
            *expected_spec,
            "backend",
            "device",
            "metrics",
        }:
            raise ValueError("cross-fold screen candidate is invalid")
        if {key: candidate.get(key) for key in expected_spec} != expected_spec:
            raise ValueError("cross-fold screen candidate changed the frozen specification")
        expected_backend = _CANDIDATE_SPECS_BY_MODE[pin.mode][0].backend
        if candidate.get("backend") != expected_backend:
            raise ValueError("cross-fold screen candidate backend is invalid")
        expected_device = "cpu" if pin.mode == "cpu-smoke" else "cuda"
        if candidate.get("device") != expected_device:
            raise ValueError("cross-fold screen candidate device is invalid")
        metrics = candidate.get("metrics")
        if not isinstance(metrics, Mapping) or set(metrics) != _EXPECTED_METRIC_KEYS:
            raise ValueError("cross-fold screen candidate metrics are invalid")
        aggregates.append(
            _attest_candidate_metrics(
                metrics=metrics, pin=pin, candidate_id=expected_spec["candidate_id"]
            )
        )
    observed_counts = {aggregate.observed_positive_count for aggregate in aggregates}
    if len(observed_counts) != 1:
        raise ValueError("cross-fold screen target aggregates are inconsistent")
    return tuple(aggregates)


def _attest_candidate_metrics(
    *,
    metrics: Mapping[str, object],
    pin: KisDailyJointEventD1CrossfoldArtifactPin,
    candidate_id: object,
) -> _AttestedCandidateAggregate:
    count_keys = {
        "evaluated_count",
        "false_negative_count",
        "false_positive_count",
        "observed_positive_count",
        "true_negative_count",
        "true_positive_count",
    }
    if not isinstance(candidate_id, str) or any(
        type(metrics.get(key)) is not int for key in count_keys
    ):
        raise ValueError("cross-fold screen candidate metrics are invalid")
    if any(
        type(metrics.get(key)) not in {int, float}
        for key in {"accuracy", "f1", "precision", "recall"}
    ):
        raise ValueError("cross-fold screen candidate metrics are invalid")
    evaluated_count = int(metrics["evaluated_count"])
    observed_positive_count = int(metrics["observed_positive_count"])
    true_positive_count = int(metrics["true_positive_count"])
    true_negative_count = int(metrics["true_negative_count"])
    false_positive_count = int(metrics["false_positive_count"])
    false_negative_count = int(metrics["false_negative_count"])
    candidate_correct_count = true_positive_count + true_negative_count
    if (
        evaluated_count != pin.fold.validation_decision_count
        or not 0 <= observed_positive_count <= evaluated_count
        or true_positive_count + false_negative_count != observed_positive_count
        or true_negative_count + false_positive_count != evaluated_count - observed_positive_count
        or any(
            value < 0
            for value in (
                true_positive_count,
                true_negative_count,
                false_positive_count,
                false_negative_count,
            )
        )
        or abs(float(metrics["accuracy"]) - candidate_correct_count / evaluated_count) > 1e-12
        or any(
            not math.isfinite(float(metrics[key]))
            for key in ("accuracy", "f1", "precision", "recall")
        )
    ):
        raise ValueError("cross-fold screen candidate metrics are inconsistent")
    return _AttestedCandidateAggregate(
        candidate_id=candidate_id,
        evaluated_count=evaluated_count,
        observed_positive_count=observed_positive_count,
        candidate_correct_count=candidate_correct_count,
    )


def _build_fold_local_observations(
    summaries: Sequence[_AttestedScreenSummary],
) -> tuple[KisDailyJointEventD1CrossfoldObservation, ...]:
    observations: list[KisDailyJointEventD1CrossfoldObservation] = []
    for summary in summaries:
        for candidate in summary.candidates:
            majority_correct_count = max(
                candidate.observed_positive_count,
                candidate.evaluated_count - candidate.observed_positive_count,
            )
            conclusion: Conclusion = (
                "inconclusive"
                if candidate.candidate_correct_count > majority_correct_count
                else "falsified"
            )
            observations.append(
                KisDailyJointEventD1CrossfoldObservation(
                    fold_id=summary.pin.fold.fold_id,
                    mode=summary.pin.mode,
                    run_label=summary.pin.run_label,
                    candidate_id=candidate.candidate_id,
                    evaluated_count=candidate.evaluated_count,
                    observed_positive_count=candidate.observed_positive_count,
                    class_majority_correct_count=majority_correct_count,
                    candidate_correct_count=candidate.candidate_correct_count,
                    conclusion=conclusion,
                )
            )
    if len(observations) != len(summaries) * len(KIS_DAILY_JOINT_EVENT_D1_CROSSFOLD_CANDIDATE_IDS):
        raise ValueError("cross-fold falsification observations are incomplete")
    return tuple(observations)


def _precommit_document(
    *,
    pins: Sequence[KisDailyJointEventD1CrossfoldArtifactPin],
) -> dict[str, object]:
    document = {
        "artifact_policy": _EXPECTED_ARTIFACT_POLICY,
        "falsification_id": KIS_DAILY_JOINT_EVENT_D1_CROSSFOLD_FALSIFICATION_ID,
        "input_pin_set_identity": _pin_set_identity(pins),
        "kind": KIS_DAILY_JOINT_EVENT_D1_CROSSFOLD_FALSIFICATION_KIND,
        "rule_id": KIS_DAILY_JOINT_EVENT_D1_CROSSFOLD_RULE_ID,
        "schema_version": KIS_DAILY_JOINT_EVENT_D1_CROSSFOLD_FALSIFICATION_SCHEMA_VERSION,
        "scope": _scope_document(),
        "source_summary_count": len(pins),
        "sources": [pin.source_document() for pin in pins],
        "status": "precommitted",
    }
    _assert_source_safe(document)
    return document


def _summary_document(
    *,
    pins: Sequence[KisDailyJointEventD1CrossfoldArtifactPin],
    precommit_identity: str,
    observations: Sequence[KisDailyJointEventD1CrossfoldObservation],
) -> dict[str, object]:
    document = {
        "artifact_policy": _EXPECTED_ARTIFACT_POLICY,
        "falsification_id": KIS_DAILY_JOINT_EVENT_D1_CROSSFOLD_FALSIFICATION_ID,
        "input_pin_set_identity": _pin_set_identity(pins),
        "kind": KIS_DAILY_JOINT_EVENT_D1_CROSSFOLD_FALSIFICATION_KIND,
        "observation_count": len(observations),
        "observations": [observation.document() for observation in observations],
        "precommit_identity": precommit_identity,
        "rule_id": KIS_DAILY_JOINT_EVENT_D1_CROSSFOLD_RULE_ID,
        "schema_version": KIS_DAILY_JOINT_EVENT_D1_CROSSFOLD_FALSIFICATION_SCHEMA_VERSION,
        "scope": _scope_document(),
        "source_summary_count": len(pins),
        "sources": [pin.source_document() for pin in pins],
        "status": "complete",
    }
    _assert_source_safe(document)
    return document


def _scope_document() -> dict[str, bool]:
    return {
        "offline_only": True,
        "candidate_only": True,
        "model_execution_eligible": False,
        "candidate_selection_eligible": False,
        "ensemble_eligible": False,
        "replay_materialized": False,
        "paper_decision_eligible": False,
        "raw_market_data_persisted": False,
        "feature_values_persisted": False,
        "target_values_persisted": False,
        "per_decision_outputs_persisted": False,
        "credentials_persisted": False,
    }


def _validate_external_artifact_root(*, artifact_root: Path, repo_root: Path) -> Path:
    resolved_root = artifact_root.resolve()
    resolved_repo = repo_root.resolve()
    if _is_link_or_reparse_point(artifact_root) or (
        (resolved_root == resolved_repo or resolved_root.is_relative_to(resolved_repo))
        and not is_container_external_mount(resolved_root, resolved_repo)
    ):
        raise ValueError("cross-fold falsification artifacts must stay outside the Git workspace")
    resolved_root.mkdir(parents=True, exist_ok=True)
    return resolved_root


def _create_external_output_dir(*, artifact_root: Path, repo_root: Path, run_label: str) -> Path:
    resolved_root = _validate_external_artifact_root(
        artifact_root=artifact_root, repo_root=repo_root
    )
    output_root = resolved_root / KIS_DAILY_JOINT_EVENT_D1_CROSSFOLD_FALSIFICATION_ID
    if _is_link_or_reparse_point(output_root):
        raise ValueError("cross-fold falsification artifact destination is invalid")
    output_root.mkdir(exist_ok=True)
    if (
        _is_link_or_reparse_point(output_root)
        or not output_root.is_dir()
        or not output_root.resolve().is_relative_to(resolved_root)
    ):
        raise ValueError("cross-fold falsification artifact destination is invalid")
    output_dir = output_root / run_label
    if output_dir.exists() or _is_link_or_reparse_point(output_dir):
        raise FileExistsError("cross-fold falsification artifact run label already exists")
    output_dir.mkdir()
    if (
        _is_link_or_reparse_point(output_dir)
        or not output_dir.resolve().is_relative_to(resolved_root)
    ):
        raise ValueError("cross-fold falsification artifact destination is invalid")
    return output_dir


def _is_link_or_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction) and is_junction():
        return True
    try:
        attributes = path.lstat().st_file_attributes
    except (AttributeError, FileNotFoundError):
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _write_source_safe_json_new(path: Path, payload: Mapping[str, object]) -> None:
    _assert_source_safe(payload)
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    with path.open("xb") as handle:
        handle.write(encoded)


def _assert_source_safe(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str) or key not in _ALLOWED_ARTIFACT_KEYS:
                raise ValueError(f"cross-fold falsification artifact key is not source-safe: {key}")
            _assert_source_safe(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_source_safe(nested)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("cross-fold falsification artifact value is not source-safe")
    elif not isinstance(value, (str, int, float, bool)) and value is not None:
        raise ValueError("cross-fold falsification artifact value is not source-safe")


def _candidate_spec_documents(mode: ScreenMode) -> list[dict[str, object]]:
    return [spec.document() for spec in _CANDIDATE_SPECS_BY_MODE[mode]]


def _candidate_spec_identity(mode: ScreenMode) -> str:
    return _sha256_json(_candidate_spec_documents(mode))


def _pin_set_identity(pins: Sequence[KisDailyJointEventD1CrossfoldArtifactPin]) -> str:
    return _sha256_json([pin.source_document() for pin in pins])


def _validate_run_label(run_label: str) -> None:
    if (
        not isinstance(run_label, str)
        or not run_label
        or len(run_label) > 80
        or any(
            character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
            for character in run_label
        )
    ):
        raise ValueError("cross-fold falsification run label is invalid")


def _sha256_json(value: object) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    )
