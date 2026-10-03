from __future__ import annotations

import warnings

import pytest

torch = pytest.importorskip("torch", reason="research-only sequence models require PyTorch")

from thericher_v2.research.sequence_architecture_models import (  # noqa: E402
    SEQUENCE_ARCHITECTURE_IDS,
    build_torch_patch_sequence_model,
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


def _patch_model(**overrides: object) -> object:
    geometry = dict(feature_count=3, hidden_size=8, attention_heads=2, patch_length=4)
    geometry.update(overrides)
    return build_torch_patch_sequence_model(torch=torch, **geometry)


@pytest.mark.parametrize(
    "field", ("feature_count", "hidden_size", "attention_heads", "patch_length")
)
@pytest.mark.parametrize("value", (0, -1, True, False, 2.0, "2", None))
def test_patch_builder_rejects_non_exact_positive_integers(field: str, value: object) -> None:
    geometry = dict(feature_count=3, hidden_size=8, attention_heads=2, patch_length=4)
    geometry[field] = value
    with pytest.raises(ValueError, match="patch sequence geometry is invalid"):
        build_torch_patch_sequence_model(torch=None, **geometry)


def test_patch_builder_rejects_incompatible_heads_without_registering_new_id() -> None:
    with pytest.raises(ValueError, match="patch sequence geometry is invalid"):
        _patch_model(hidden_size=7)
    with pytest.raises(ValueError, match="sequence architecture geometry is invalid"):
        _model("patch_tst")
    assert SEQUENCE_ARCHITECTURE_IDS == frozenset(
        {"gru", "lstm", "causal_tcn", "compact_attention"}
    )


@pytest.mark.parametrize("hidden", (1, 3, 8))
def test_patch_output_shape_finite_and_whole_patch_lengths(hidden: int) -> None:
    model = _patch_model(hidden_size=hidden, attention_heads=1).eval()
    for length in (4, 8, 20):
        values = torch.arange(2 * length * 3, dtype=torch.float32).reshape(2, length, 3) / 100
        with torch.no_grad():
            output = model(values)
            states = model.encode_patches(values)
        assert tuple(output.shape) == (2, 1)
        assert tuple(states.shape) == (2, 3, length // 4, hidden)
        assert bool(torch.isfinite(output).all()) and bool(torch.isfinite(states).all())


def test_patch_backprop_updates_parameters_without_mutating_inputs() -> None:
    torch.manual_seed(103)
    model = _patch_model().train()
    values = torch.linspace(-1, 1, 4 * 12 * 3).reshape(4, 12, 3).requires_grad_()
    before_input = values.detach().clone()
    before_weights = [p.detach().clone() for p in model.parameters()]
    optimizer = torch.optim.SGD(model.parameters(), lr=0.03)
    optimizer.zero_grad(set_to_none=True)
    loss = torch.nn.functional.binary_cross_entropy_with_logits(
        model(values), torch.tensor([[0.0], [1.0], [0.0], [1.0]])
    )
    loss.backward()
    assert bool(torch.isfinite(loss))
    assert values.grad is not None and bool(torch.isfinite(values.grad).all())
    assert all(
        p.grad is not None and bool(torch.isfinite(p.grad).all()) for p in model.parameters()
    )
    optimizer.step()
    assert any(
        not torch.equal(a, b) for a, b in zip(before_weights, model.parameters(), strict=True)
    )
    assert torch.equal(values.detach(), before_input)


def test_patch_batch_equivariance_and_single_item_identity() -> None:
    torch.manual_seed(103)
    model = _patch_model().double().eval()
    values = torch.arange(3 * 12 * 3, dtype=torch.float64).reshape(3, 12, 3) / 100
    with torch.no_grad():
        together = model(values)
        shuffled = model(values[[2, 0, 1]])
        individually = torch.cat([model(v.unsqueeze(0)) for v in values])
    torch.testing.assert_close(shuffled, together[[2, 0, 1]], rtol=0, atol=1e-10)
    torch.testing.assert_close(individually, together, rtol=0, atol=1e-10)


def test_patch_shared_channel_isolation_permutation_and_fixed_mean_head() -> None:
    torch.manual_seed(103)
    model = _patch_model().double().eval()
    single = _patch_model(feature_count=1).double().eval()
    single.load_state_dict(model.state_dict())
    assert sum(p.numel() for p in model.parameters()) == sum(p.numel() for p in single.parameters())
    values = torch.arange(2 * 12 * 3, dtype=torch.float64).reshape(2, 12, 3) / 100
    changed = values.clone()
    changed[:, :, 1] += 100
    with torch.no_grad():
        baseline = model.encode_patches(values)
        mutated = model.encode_patches(changed)
        alone = single.encode_patches(values[:, :, :1])
        permuted = model.encode_patches(values[:, :, [2, 0, 1]])
        output = model(values)
        permuted_output = model(values[:, :, [2, 0, 1]])
        mean_score = model.head(baseline[:, :, -1, :]).mean(dim=1)
    torch.testing.assert_close(mutated[:, [0, 2]], baseline[:, [0, 2]], rtol=0, atol=1e-10)
    assert not torch.allclose(mutated[:, 1], baseline[:, 1], rtol=0, atol=1e-10)
    torch.testing.assert_close(alone[:, 0], baseline[:, 0], rtol=0, atol=1e-10)
    torch.testing.assert_close(permuted, baseline[:, [2, 0, 1]], rtol=0, atol=1e-10)
    torch.testing.assert_close(permuted_output, output, rtol=0, atol=1e-10)
    torch.testing.assert_close(output, mean_score, rtol=0, atol=1e-10)


def test_patch_completed_prefix_is_invariant_to_later_complete_patches() -> None:
    torch.manual_seed(103)
    model = _patch_model().double().eval()
    values = torch.arange(2 * 20 * 3, dtype=torch.float64).reshape(2, 20, 3) / 100
    changed = values.clone()
    changed[:, 8:, :] += 1000
    with torch.no_grad():
        full = model.encode_patches(values)
        altered = model.encode_patches(changed)
        prefix = model.encode_patches(values[:, :8, :])
    torch.testing.assert_close(full[:, :, :2], altered[:, :, :2], rtol=0, atol=1e-10)
    torch.testing.assert_close(full[:, :, :2], prefix, rtol=0, atol=1e-10)
    assert not torch.allclose(full[:, :, 2:], altered[:, :, 2:])


@pytest.mark.parametrize(
    "shape", ((0, 8, 3), (2, 0, 3), (2, 3, 3), (2, 10, 3), (2, 8, 2), (8, 3), (1, 2, 8, 3))
)
def test_patch_input_rejects_wrong_geometry_and_incomplete_tail(shape: tuple[int, ...]) -> None:
    model = _patch_model()
    with pytest.raises(ValueError, match="patch sequence input is invalid"):
        model(torch.zeros(shape))


@pytest.mark.parametrize("dtype", (torch.int64, torch.bool, torch.complex64, torch.float64))
def test_patch_input_rejects_nonfloating_or_parameter_dtype_mismatch(dtype: object) -> None:
    with pytest.raises(ValueError, match="patch sequence input is invalid"):
        _patch_model()(torch.ones((2, 8, 3), dtype=dtype))


@pytest.mark.parametrize("bad", (float("nan"), float("inf"), -float("inf")))
def test_patch_input_rejects_nonfinite_without_mutation(bad: float) -> None:
    values = torch.zeros((2, 8, 3))
    values[0, 0, 0] = bad
    before = values.clone()
    with pytest.raises(ValueError, match="patch sequence input is invalid"):
        _patch_model()(values)
    torch.testing.assert_close(values, before, rtol=0, atol=0, equal_nan=True)


def test_patch_input_rejects_non_tensor_sparse_and_foreign_device_without_gpu() -> None:
    model = _patch_model()
    for values in (
        [[[1.0, 2.0, 3.0]]],
        torch.zeros((2, 8, 3)).to_sparse(),
        torch.empty((2, 8, 3), device="meta"),
    ):
        with pytest.raises(ValueError, match="patch sequence input is invalid"):
            model(values)


def test_patch_noncontiguous_input_is_not_modified() -> None:
    model = _patch_model().eval()
    values = torch.arange(72, dtype=torch.float32).reshape(2, 3, 12).transpose(1, 2)
    before = values.clone()
    assert not values.is_contiguous()
    with torch.no_grad():
        output = model(values)
    assert output.shape == (2, 1) and bool(torch.isfinite(output).all())
    assert torch.equal(values, before)
