"""Small shared PyTorch sequence encoders for isolated Research-only screens."""

from __future__ import annotations

import math
from typing import Literal

SequenceArchitectureId = Literal["gru", "lstm", "causal_tcn", "compact_attention"]
SEQUENCE_ARCHITECTURE_IDS = frozenset({"gru", "lstm", "causal_tcn", "compact_attention"})


def build_torch_sequence_model(
    *,
    torch: object,
    architecture_id: SequenceArchitectureId,
    feature_count: int,
    hidden_size: int,
    attention_heads: int,
    tcn_kernel_size: int,
) -> object:
    """Construct one causal architecture without importing PyTorch at module import time."""

    if (
        architecture_id not in SEQUENCE_ARCHITECTURE_IDS
        or feature_count <= 0
        or hidden_size <= 0
        or attention_heads <= 0
        or hidden_size % attention_heads != 0
        or tcn_kernel_size <= 0
    ):
        raise ValueError("sequence architecture geometry is invalid")
    nn = torch.nn

    if architecture_id == "gru":

        class GruModel(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.encoder = nn.GRU(
                    input_size=feature_count,
                    hidden_size=hidden_size,
                    batch_first=True,
                )
                self.head = nn.Linear(hidden_size, 1)

            def forward(self, values: object) -> object:
                encoded, _ = self.encoder(values)
                return self.head(encoded[:, -1, :])

        return GruModel()

    if architecture_id == "lstm":

        class LstmModel(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.encoder = nn.LSTM(
                    input_size=feature_count,
                    hidden_size=hidden_size,
                    batch_first=True,
                )
                self.head = nn.Linear(hidden_size, 1)

            def forward(self, values: object) -> object:
                encoded, _ = self.encoder(values)
                return self.head(encoded[:, -1, :])

        return LstmModel()

    if architecture_id == "causal_tcn":

        class CausalTcnModel(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.convolution = nn.Conv1d(
                    feature_count,
                    hidden_size,
                    kernel_size=tcn_kernel_size,
                    padding=tcn_kernel_size - 1,
                )
                self.head = nn.Linear(hidden_size, 1)

            def forward(self, values: object) -> object:
                length = values.shape[1]
                encoded = self.convolution(values.transpose(1, 2))[:, :, :length]
                encoded = torch.relu(encoded)
                return self.head(encoded[:, :, -1])

        return CausalTcnModel()

    class CompactAttentionModel(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.input_projection = nn.Linear(feature_count, hidden_size)
            layer = nn.TransformerEncoderLayer(
                d_model=hidden_size,
                nhead=attention_heads,
                dim_feedforward=hidden_size * 2,
                dropout=0.0,
                batch_first=True,
            )
            self.encoder = nn.TransformerEncoder(layer, num_layers=1)
            self.head = nn.Linear(hidden_size, 1)

        def forward(self, values: object) -> object:
            length = values.shape[1]
            positions = torch.arange(length, dtype=values.dtype, device=values.device).unsqueeze(1)
            divisors = torch.exp(
                torch.arange(0, hidden_size, 2, dtype=values.dtype, device=values.device)
                * (-math.log(10000.0) / hidden_size)
            )
            positional = torch.zeros(
                (length, hidden_size), dtype=values.dtype, device=values.device
            )
            positional[:, 0::2] = torch.sin(positions * divisors)
            positional[:, 1::2] = torch.cos(positions * divisors)
            causal_mask = torch.triu(
                torch.full(
                    (length, length), float("-inf"), dtype=values.dtype, device=values.device
                ),
                diagonal=1,
            )
            encoded = self.encoder(
                self.input_projection(values) + positional.unsqueeze(0),
                mask=causal_mask,
            )
            return self.head(encoded[:, -1, :])

    return CompactAttentionModel()
