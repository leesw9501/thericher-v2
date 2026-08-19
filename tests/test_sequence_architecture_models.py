from __future__ import annotations

import warnings

import pytest

torch = pytest.importorskip("torch", reason="research-only sequence models require PyTorch")

from thericher_v2.research.sequence_architecture_models import (  # noqa: E402
    SEQUENCE_ARCHITECTURE_IDS,
    build_torch_sequence_model,
)


@pytest.mark.parametrize("architecture_id", ("gru", "lstm", "causal_tcn", "compact_attention"))
def test_shared_sequence_encoders_do_not_look_ahead(architecture_id: str) -> None:
    torch.manual_seed(17)
    model = _model(architecture_id).eval()
    values = torch.arange(48, dtype=torch.float32).reshape(2, 8, 3) / 10
    changed_future = values.clone()
    changed_future[:, 5:, :] += 1000

    with torch.no_grad():
        baseline_prefix = _encoded_prefix(model, architecture_id, values)
        changed_prefix = _encoded_prefix(model, architecture_id, changed_future)
        output = model(values)

    torch.testing.assert_close(
        baseline_prefix[:, :5, :],
        changed_prefix[:, :5, :],
        rtol=0,
        atol=1e-6,
    )
    assert tuple(output.shape) == (2, 1)
    assert bool(torch.isfinite(output).all())


def test_shared_sequence_builder_rejects_unknown_architecture() -> None:
    with pytest.raises(ValueError, match="sequence architecture geometry is invalid"):
        _model("unknown")


def test_shared_compact_attention_accepts_odd_hidden_size() -> None:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="enable_nested_tensor is True",
            category=UserWarning,
        )
        model = build_torch_sequence_model(
            torch=torch,
            architecture_id="compact_attention",
            feature_count=3,
            hidden_size=3,
            attention_heads=1,
            tcn_kernel_size=3,
        ).eval()

        with torch.no_grad():
            output = model(torch.arange(12, dtype=torch.float32).reshape(1, 4, 3))

    assert tuple(output.shape) == (1, 1)
    assert bool(torch.isfinite(output).all())


def _model(architecture_id: str) -> object:
    return build_torch_sequence_model(
        torch=torch,
        architecture_id=architecture_id,
        feature_count=3,
        hidden_size=8,
        attention_heads=2,
        tcn_kernel_size=3,
    )


def _encoded_prefix(model: object, architecture_id: str, values: object) -> object:
    if architecture_id in {"gru", "lstm"}:
        encoded, _ = model.encoder(values)
        return encoded
    if architecture_id == "causal_tcn":
        length = values.shape[1]
        encoded = model.convolution(values.transpose(1, 2))[:, :, :length]
        return torch.relu(encoded).transpose(1, 2)
    if architecture_id != "compact_attention":  # pragma: no cover - parametrized above.
        raise AssertionError("unexpected shared sequence architecture")

    captured: list[object] = []

    def capture(_module: object, _inputs: tuple[object, ...], output: object) -> None:
        captured.append(output.detach().clone())

    handle = model.encoder.register_forward_hook(capture)
    try:
        model(values)
    finally:
        handle.remove()
    assert len(captured) == 1
    return captured[0]


def test_shared_sequence_architecture_ids_match_the_supported_contract() -> None:
    assert SEQUENCE_ARCHITECTURE_IDS == frozenset(
        {"gru", "lstm", "causal_tcn", "compact_attention"}
    )
