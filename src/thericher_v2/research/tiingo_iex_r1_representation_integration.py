"""Source-isolated Tiingo IEX r1 masked-reconstruction integration evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.corporate_actions import CORPORATE_ACTION_SYMBOLS
from thericher_v2.data.tiingo_iex_intraday import load_tiingo_iex_intraday_snapshot

from .artifact_paths import ensure_external_artifact_directory

TIINGO_IEX_R1_REPRESENTATION_INTEGRATION_ID = "tiingo-iex-r1-representation-integration-v1"
TIINGO_IEX_R1_SNAPSHOT_DIR = Path(
    r"D:\market_data\us_equities\fixed_etf_intraday\canonical\tiingo_iex_5m"
    r"\snapshot=2026-07-19-tiingo-iex-5m-r1"
)
TIINGO_IEX_R1_DATASET_ID = (
    "us_equities.fixed_etf_tiingo_iex_intraday.5m."
    "snapshot=2026-07-19-tiingo-iex-5m-r1"
)
TIINGO_IEX_R1_DATASET_HASH = (
    "sha256:1531d803fb259c5f2233cc1b5f94441eb52bab9f31938232644879cc4aa1fcb6"
)
TIINGO_IEX_R1_MANIFEST_HASH = (
    "sha256:a1dee1cddf12e22b9448806094ce6fbbcc6aa16ed13719ab720f3e9fbd1d3ab8"
)
TIINGO_IEX_R1_ARCHITECTURES = ("lstm", "causal_tcn", "compact_attention")
TIINGO_IEX_R1_SEQUENCE_LENGTH = 24
TIINGO_IEX_R1_MASKED_TAIL_LENGTH = 3
TIINGO_IEX_R1_WINDOW_STRIDE = 6
TIINGO_IEX_R1_MAX_SAMPLES = 1536
TIINGO_IEX_R1_VALUE_FEATURE_COUNT = 5
TIINGO_IEX_R1_INPUT_FEATURE_COUNT = TIINGO_IEX_R1_VALUE_FEATURE_COUNT + 1
TIINGO_IEX_R1_HIDDEN_SIZE = 16
TIINGO_IEX_R1_ATTENTION_HEADS = 4
TIINGO_IEX_R1_TCN_KERNEL_SIZE = 3
TIINGO_IEX_R1_EPOCHS = 2
TIINGO_IEX_R1_BATCH_SIZE = 128
TIINGO_IEX_R1_SEED = 20_260_810

RepresentationPhase = Literal["cpu", "cuda"]
RepresentationArchitectureId = Literal["lstm", "causal_tcn", "compact_attention"]

_NEW_YORK = ZoneInfo("America/New_York")
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)


@dataclass(frozen=True, slots=True)
class TiingoIexR1RepresentationContract:
    """One in-memory, target-free reconstruction input bound to the r1 snapshot."""

    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    window_count: int
    gap_window_count: int
    symbol_window_counts: tuple[tuple[str, int], ...]
    input_contract_hash: str
    values: Any = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        shape = getattr(self.values, "shape", ())
        if (
            self.dataset_id != TIINGO_IEX_R1_DATASET_ID
            or self.dataset_hash != TIINGO_IEX_R1_DATASET_HASH
            or self.manifest_hash != TIINGO_IEX_R1_MANIFEST_HASH
            or self.window_count <= 0
            or self.window_count > TIINGO_IEX_R1_MAX_SAMPLES
            or self.gap_window_count < 0
            or tuple(symbol for symbol, _count in self.symbol_window_counts)
            != tuple(CORPORATE_ACTION_SYMBOLS)
            or any(count <= 0 for _symbol, count in self.symbol_window_counts)
            or sum(count for _symbol, count in self.symbol_window_counts) != self.window_count
            or tuple(shape)
            != (
                self.window_count,
                TIINGO_IEX_R1_SEQUENCE_LENGTH,
                TIINGO_IEX_R1_VALUE_FEATURE_COUNT,
            )
            or self.input_contract_hash
            != _contract_hash(
                dataset_id=self.dataset_id,
                dataset_hash=self.dataset_hash,
                manifest_hash=self.manifest_hash,
                window_count=self.window_count,
                gap_window_count=self.gap_window_count,
                symbol_window_counts=self.symbol_window_counts,
            )
        ):
            raise ValueError("Tiingo IEX r1 representation contract is invalid")

    def safe_payload(self) -> dict[str, object]:
        """Return only non-price, non-predictive contract facts."""

        return {
            "integration_id": TIINGO_IEX_R1_REPRESENTATION_INTEGRATION_ID,
            "source": {
                "dataset_id": self.dataset_id,
                "dataset_hash": self.dataset_hash,
                "manifest_hash": self.manifest_hash,
                "symbols": list(CORPORATE_ACTION_SYMBOLS),
                "provider_scope": "IEX_only_unadjusted_ohlcv",
                "source_training_eligible": False,
                "paper_input_eligible": False,
            },
            "task": {
                "kind": "masked_same_window_reconstruction",
                "timeframe": "5m",
                "sequence_length": TIINGO_IEX_R1_SEQUENCE_LENGTH,
                "masked_terminal_bars": TIINGO_IEX_R1_MASKED_TAIL_LENGTH,
                "window_stride": TIINGO_IEX_R1_WINDOW_STRIDE,
                "sample_cap": TIINGO_IEX_R1_MAX_SAMPLES,
                "return_labels_materialized": False,
                "holdout_materialized": False,
                "selection_enabled": False,
            },
            "geometry": {
                "window_count": self.window_count,
                "gap_window_count": self.gap_window_count,
                "window_counts_by_symbol": dict(self.symbol_window_counts),
            },
            "input_contract_hash": self.input_contract_hash,
        }


@dataclass(frozen=True, slots=True)
class TiingoIexR1RepresentationArchitectureRun:
    """One categorical result from a frozen architecture without a score."""

    architecture_id: RepresentationArchitectureId
    status: Literal["completed"]
    training_loss_finite: bool
    memory_released: bool

    def __post_init__(self) -> None:
        if (
            self.architecture_id not in TIINGO_IEX_R1_ARCHITECTURES
            or self.status != "completed"
            or not self.training_loss_finite
            or not self.memory_released
        ):
            raise ValueError("Tiingo IEX r1 representation result is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "architecture_id": self.architecture_id,
            "status": self.status,
            "training_loss_finite": self.training_loss_finite,
            "memory_released": self.memory_released,
        }


@dataclass(frozen=True, slots=True)
class TiingoIexR1RepresentationRun:
    """One external-only source-safe receipt for the frozen integration matrix."""

    contract: TiingoIexR1RepresentationContract
    phase: RepresentationPhase
    summary_path: Path
    architecture_runs: tuple[TiingoIexR1RepresentationArchitectureRun, ...]

    def __post_init__(self) -> None:
        if (
            self.phase not in {"cpu", "cuda"}
            or tuple(item.architecture_id for item in self.architecture_runs)
            != TIINGO_IEX_R1_ARCHITECTURES
            or not self.summary_path.is_file()
        ):
            raise ValueError("Tiingo IEX r1 representation run is invalid")


MatrixRunner = Callable[
    [TiingoIexR1RepresentationContract, RepresentationPhase],
    tuple[TiingoIexR1RepresentationArchitectureRun, ...],
]


def freeze_tiingo_iex_r1_representation_contract(
    *,
    snapshot_dir: Path = TIINGO_IEX_R1_SNAPSHOT_DIR,
    dataset_id: str = TIINGO_IEX_R1_DATASET_ID,
    dataset_hash: str = TIINGO_IEX_R1_DATASET_HASH,
    manifest_hash: str = TIINGO_IEX_R1_MANIFEST_HASH,
    market_data_root: Path = Path(r"D:\market_data"),
    repo_root: Path | None = None,
) -> TiingoIexR1RepresentationContract:
    """Reattest r1 offline and freeze only in-memory reconstruction windows."""

    if (
        dataset_id != TIINGO_IEX_R1_DATASET_ID
        or dataset_hash != TIINGO_IEX_R1_DATASET_HASH
        or manifest_hash != TIINGO_IEX_R1_MANIFEST_HASH
    ):
        raise ValueError("Tiingo IEX r1 representation requires the pinned r1 identity")
    snapshot = load_tiingo_iex_intraday_snapshot(
        Path(snapshot_dir),
        dataset_id=dataset_id,
        expected_dataset_hash=dataset_hash,
        expected_manifest_hash=manifest_hash,
        market_data_root=Path(market_data_root),
        repo_root=repo_root,
    )
    values, gap_window_count, symbol_window_counts = _representation_windows(
        snapshot.bars_by_symbol
    )
    return TiingoIexR1RepresentationContract(
        dataset_id=snapshot.dataset_id,
        dataset_hash=snapshot.dataset_hash,
        manifest_hash=snapshot.manifest_hash,
        window_count=int(values.shape[0]),
        gap_window_count=gap_window_count,
        symbol_window_counts=symbol_window_counts,
        input_contract_hash=_contract_hash(
            dataset_id=snapshot.dataset_id,
            dataset_hash=snapshot.dataset_hash,
            manifest_hash=snapshot.manifest_hash,
            window_count=int(values.shape[0]),
            gap_window_count=gap_window_count,
            symbol_window_counts=symbol_window_counts,
        ),
        values=values,
    )


def run_tiingo_iex_r1_representation_integration(
    contract: TiingoIexR1RepresentationContract,
    *,
    phase: RepresentationPhase,
    artifact_root: Path,
    run_label: str,
    repo_root: Path | None = None,
    matrix_runner: MatrixRunner | None = None,
) -> TiingoIexR1RepresentationRun:
    """Run the fixed, non-selective reconstruction matrix and persist no weights."""

    if phase not in {"cpu", "cuda"}:
        raise ValueError("Tiingo IEX r1 representation phase is invalid")
    if _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        raise ValueError("Tiingo IEX r1 representation run label is invalid")
    architecture_runs = (matrix_runner or _run_torch_matrix)(contract, phase)
    if tuple(item.architecture_id for item in architecture_runs) != TIINGO_IEX_R1_ARCHITECTURES:
        raise ValueError("Tiingo IEX r1 representation matrix is incomplete")

    base_directory = ensure_external_artifact_directory(
        artifact_root,
        repo_root,
        "research",
        TIINGO_IEX_R1_REPRESENTATION_INTEGRATION_ID,
    )
    run_directory = base_directory / run_label
    if run_directory.exists() or run_directory.is_symlink():
        raise FileExistsError("Tiingo IEX r1 representation artifact already exists")
    run_directory.mkdir()
    summary_path = run_directory / "summary.json"
    _write_json_new(
        summary_path,
        {
            "status": "complete",
            "phase": phase,
            "research_steward_custody": {
                "allocation_kind": "source_isolated_target_free_representation",
                "family_lineage": TIINGO_IEX_R1_REPRESENTATION_INTEGRATION_ID,
                "gpu_appointment": (
                    "not_requested" if phase == "cpu" else "one_bounded_appointment"
                ),
                "sealed_evaluation_spent": False,
                "promotion_eligible": False,
                "completion_category": "non_promoting_runtime_evidence",
            },
            "contract": contract.safe_payload(),
            "architecture_order": list(TIINGO_IEX_R1_ARCHITECTURES),
            "architecture_geometry": {
                "hidden_size": TIINGO_IEX_R1_HIDDEN_SIZE,
                "attention_heads": TIINGO_IEX_R1_ATTENTION_HEADS,
                "tcn_kernel_size": TIINGO_IEX_R1_TCN_KERNEL_SIZE,
                "epochs": TIINGO_IEX_R1_EPOCHS,
                "batch_size": TIINGO_IEX_R1_BATCH_SIZE,
                "seed": TIINGO_IEX_R1_SEED,
            },
            "runs": [item.safe_payload() for item in architecture_runs],
            "scope": {
                "trading_prediction": False,
                "model_selection": False,
                "return_metrics_persisted": False,
                "numeric_losses_persisted": False,
                "holdout_accessed": False,
                "paper_input_eligible": False,
                "kis_input_eligible": False,
                "weights_persisted": False,
                "normalized_arrays_persisted": False,
                "raw_market_data_persisted": False,
            },
            "artifact_policy": {
                "repo_storage_allowed": False,
                "source_derived_weights_retained": False,
            },
        },
    )
    return TiingoIexR1RepresentationRun(
        contract=contract,
        phase=phase,
        summary_path=summary_path,
        architecture_runs=architecture_runs,
    )


def _representation_windows(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
) -> tuple[Any, int, tuple[tuple[str, int], ...]]:
    numpy = _numpy()
    windows_by_symbol: dict[str, list[list[list[float]]]] = {}
    gap_window_count = 0
    for symbol in CORPORATE_ACTION_SYMBOLS:
        symbol_bars = tuple(bars_by_symbol.get(symbol, ()))
        if not symbol_bars:
            raise ValueError("Tiingo IEX r1 representation source is incomplete")
        symbol_windows: list[list[list[float]]] = []
        sessions: dict[object, list[Bar]] = {}
        for bar in symbol_bars:
            sessions.setdefault(bar.start_ts.astimezone(_NEW_YORK).date(), []).append(bar)
        for session_bars in sessions.values():
            for start in range(
                0,
                len(session_bars) - TIINGO_IEX_R1_SEQUENCE_LENGTH + 1,
                TIINGO_IEX_R1_WINDOW_STRIDE,
            ):
                window = tuple(session_bars[start : start + TIINGO_IEX_R1_SEQUENCE_LENGTH])
                if not _contiguous_m5(window):
                    gap_window_count += 1
                    continue
                symbol_windows.append(_normalized_window(window))
        if not symbol_windows:
            raise ValueError("Tiingo IEX r1 representation source has no complete windows")
        windows_by_symbol[symbol] = symbol_windows
    selected_by_symbol = {symbol: 0 for symbol in CORPORATE_ACTION_SYMBOLS}
    selected: list[list[list[float]]] = []
    for index in range(max(len(value) for value in windows_by_symbol.values())):
        for symbol in CORPORATE_ACTION_SYMBOLS:
            symbol_windows = windows_by_symbol[symbol]
            if index >= len(symbol_windows):
                continue
            selected.append(symbol_windows[index])
            selected_by_symbol[symbol] += 1
            if len(selected) == TIINGO_IEX_R1_MAX_SAMPLES:
                values = numpy.asarray(selected, dtype=numpy.float32)
                return (
                    _validate_window_values(values),
                    gap_window_count,
                    tuple(
                        (symbol, selected_by_symbol[symbol])
                        for symbol in CORPORATE_ACTION_SYMBOLS
                    ),
                )
    values = numpy.asarray(selected, dtype=numpy.float32)
    return (
        _validate_window_values(values),
        gap_window_count,
        tuple((symbol, selected_by_symbol[symbol]) for symbol in CORPORATE_ACTION_SYMBOLS),
    )


def _contiguous_m5(window: Sequence[Bar]) -> bool:
    return len(window) == TIINGO_IEX_R1_SEQUENCE_LENGTH and all(
        later.start_ts - earlier.start_ts == Timeframe.M5.duration
        for earlier, later in zip(window[:-1], window[1:], strict=True)
    )


def _normalized_window(window: Sequence[Bar]) -> list[list[float]]:
    anchor_price = window[0].close
    anchor_volume = max(window[0].volume, 1)
    if anchor_price <= 0:
        raise ValueError("Tiingo IEX r1 representation anchor is invalid")
    rows = [
        [
            float(bar.open / anchor_price),
            float(bar.high / anchor_price),
            float(bar.low / anchor_price),
            float(bar.close / anchor_price),
            float(bar.volume / anchor_volume),
        ]
        for bar in window
    ]
    if any(not math.isfinite(value) for row in rows for value in row):
        raise ValueError("Tiingo IEX r1 representation values are invalid")
    return rows


def _validate_window_values(values: Any) -> Any:
    numpy = _numpy()
    if (
        values.ndim != 3
        or values.shape[0] <= 0
        or values.shape[1:] != (TIINGO_IEX_R1_SEQUENCE_LENGTH, TIINGO_IEX_R1_VALUE_FEATURE_COUNT)
        or not bool(numpy.isfinite(values).all())
    ):
        raise ValueError("Tiingo IEX r1 representation window geometry is invalid")
    return values


def _run_torch_matrix(
    contract: TiingoIexR1RepresentationContract,
    phase: RepresentationPhase,
) -> tuple[TiingoIexR1RepresentationArchitectureRun, ...]:
    torch = _torch()
    if phase == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("PyTorch CUDA is unavailable")
    device = torch.device("cuda" if phase == "cuda" else "cpu")
    _configure_torch(torch, phase)
    target = torch.tensor(contract.values, dtype=torch.float32, device=device)
    observed = target.clone()
    observed[:, -TIINGO_IEX_R1_MASKED_TAIL_LENGTH :, :] = 0.0
    mask = torch.zeros(
        (contract.window_count, TIINGO_IEX_R1_SEQUENCE_LENGTH, 1),
        dtype=torch.float32,
        device=device,
    )
    mask[:, -TIINGO_IEX_R1_MASKED_TAIL_LENGTH :, :] = 1.0
    features = torch.cat((observed, mask), dim=2)
    runs: list[TiingoIexR1RepresentationArchitectureRun] = []
    try:
        for architecture_id in TIINGO_IEX_R1_ARCHITECTURES:
            model = _build_reconstruction_model(torch, architecture_id).to(device)
            optimizer = torch.optim.AdamW(model.parameters(), lr=0.001)
            loss_finite = _train_masked_reconstruction(
                torch,
                model=model,
                optimizer=optimizer,
                features=features,
                target=target,
                mask=mask,
            )
            del optimizer
            del model
            if phase == "cuda":
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
            runs.append(
                TiingoIexR1RepresentationArchitectureRun(
                    architecture_id=architecture_id,
                    status="completed",
                    training_loss_finite=loss_finite,
                    memory_released=True,
                )
            )
    finally:
        del features
        del mask
        del observed
        del target
        if phase == "cuda":
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
    return tuple(runs)


def _configure_torch(torch: Any, phase: RepresentationPhase) -> None:
    torch.manual_seed(TIINGO_IEX_R1_SEED)
    torch.use_deterministic_algorithms(True)
    if phase == "cuda":
        torch.cuda.manual_seed_all(TIINGO_IEX_R1_SEED)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True


def _build_reconstruction_model(torch: Any, architecture_id: str) -> Any:
    nn = torch.nn
    if architecture_id == "lstm":

        class LstmReconstruction(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.encoder = nn.LSTM(
                    input_size=TIINGO_IEX_R1_INPUT_FEATURE_COUNT,
                    hidden_size=TIINGO_IEX_R1_HIDDEN_SIZE,
                    batch_first=True,
                )
                self.head = nn.Linear(TIINGO_IEX_R1_HIDDEN_SIZE, TIINGO_IEX_R1_VALUE_FEATURE_COUNT)

            def forward(self, values: Any) -> Any:
                encoded, _ = self.encoder(values)
                return self.head(encoded)

        return LstmReconstruction()
    if architecture_id == "causal_tcn":

        class CausalTcnReconstruction(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.convolution = nn.Conv1d(
                    TIINGO_IEX_R1_INPUT_FEATURE_COUNT,
                    TIINGO_IEX_R1_HIDDEN_SIZE,
                    kernel_size=TIINGO_IEX_R1_TCN_KERNEL_SIZE,
                    padding=TIINGO_IEX_R1_TCN_KERNEL_SIZE - 1,
                )
                self.head = nn.Linear(TIINGO_IEX_R1_HIDDEN_SIZE, TIINGO_IEX_R1_VALUE_FEATURE_COUNT)

            def forward(self, values: Any) -> Any:
                length = values.shape[1]
                encoded = self.convolution(values.transpose(1, 2))[:, :, :length]
                return self.head(torch.relu(encoded).transpose(1, 2))

        return CausalTcnReconstruction()
    if architecture_id != "compact_attention":
        raise ValueError("Tiingo IEX r1 representation architecture is invalid")

    class CompactAttentionReconstruction(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.input_projection = nn.Linear(
                TIINGO_IEX_R1_INPUT_FEATURE_COUNT,
                TIINGO_IEX_R1_HIDDEN_SIZE,
            )
            layer = nn.TransformerEncoderLayer(
                d_model=TIINGO_IEX_R1_HIDDEN_SIZE,
                nhead=TIINGO_IEX_R1_ATTENTION_HEADS,
                dim_feedforward=TIINGO_IEX_R1_HIDDEN_SIZE * 2,
                dropout=0.0,
                batch_first=True,
            )
            self.encoder = nn.TransformerEncoder(layer, num_layers=1)
            self.head = nn.Linear(TIINGO_IEX_R1_HIDDEN_SIZE, TIINGO_IEX_R1_VALUE_FEATURE_COUNT)

        def forward(self, values: Any) -> Any:
            length = values.shape[1]
            causal_mask = torch.triu(
                torch.full(
                    (length, length),
                    float("-inf"),
                    dtype=values.dtype,
                    device=values.device,
                ),
                diagonal=1,
            )
            return self.head(self.encoder(self.input_projection(values), mask=causal_mask))

    return CompactAttentionReconstruction()


def _train_masked_reconstruction(
    torch: Any,
    *,
    model: Any,
    optimizer: Any,
    features: Any,
    target: Any,
    mask: Any,
) -> bool:
    model.train()
    for _ in range(TIINGO_IEX_R1_EPOCHS):
        for start in range(0, int(features.shape[0]), TIINGO_IEX_R1_BATCH_SIZE):
            end = min(start + TIINGO_IEX_R1_BATCH_SIZE, int(features.shape[0]))
            optimizer.zero_grad(set_to_none=True)
            loss = _masked_mse(
                model(features[start:end]),
                target[start:end],
                mask[start:end],
            )
            if not bool(torch.isfinite(loss).item()):
                raise RuntimeError("Tiingo IEX r1 reconstruction loss is non-finite")
            loss.backward()
            optimizer.step()
    model.eval()
    with torch.no_grad():
        final_loss = _masked_mse(model(features), target, mask)
    return bool(torch.isfinite(final_loss).item())


def _masked_mse(prediction: Any, target: Any, mask: Any) -> Any:
    denominator = mask.sum() * TIINGO_IEX_R1_VALUE_FEATURE_COUNT
    if denominator <= 0:
        raise RuntimeError("Tiingo IEX r1 reconstruction mask is empty")
    return ((prediction - target).square() * mask).sum() / denominator


def _contract_hash(
    *,
    dataset_id: str,
    dataset_hash: str,
    manifest_hash: str,
    window_count: int,
    gap_window_count: int,
    symbol_window_counts: tuple[tuple[str, int], ...],
) -> str:
    payload = {
        "integration_id": TIINGO_IEX_R1_REPRESENTATION_INTEGRATION_ID,
        "dataset_id": dataset_id,
        "dataset_hash": dataset_hash,
        "manifest_hash": manifest_hash,
        "timeframe": "5m",
        "sequence_length": TIINGO_IEX_R1_SEQUENCE_LENGTH,
        "masked_terminal_bars": TIINGO_IEX_R1_MASKED_TAIL_LENGTH,
        "window_stride": TIINGO_IEX_R1_WINDOW_STRIDE,
        "sample_cap": TIINGO_IEX_R1_MAX_SAMPLES,
        "window_count": window_count,
        "gap_window_count": gap_window_count,
        "symbol_window_counts": list(symbol_window_counts),
        "architectures": list(TIINGO_IEX_R1_ARCHITECTURES),
        "hidden_size": TIINGO_IEX_R1_HIDDEN_SIZE,
        "attention_heads": TIINGO_IEX_R1_ATTENTION_HEADS,
        "tcn_kernel_size": TIINGO_IEX_R1_TCN_KERNEL_SIZE,
        "epochs": TIINGO_IEX_R1_EPOCHS,
        "batch_size": TIINGO_IEX_R1_BATCH_SIZE,
        "seed": TIINGO_IEX_R1_SEED,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _write_json_new(path: Path, payload: Mapping[str, object]) -> None:
    with path.open("x", encoding="ascii") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")


def _numpy() -> Any:
    import numpy

    return numpy


def _torch() -> Any:
    import torch

    return torch
