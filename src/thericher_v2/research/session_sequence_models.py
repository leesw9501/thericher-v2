"""Fixed context-36/H180 CUDA fits; the caller owns targets, splits and storage."""

from __future__ import annotations

import numpy as np

from thericher_v2.research import firstrate_family_models as family
from thericher_v2.research import firstrate_m5_h30_lstm_dev_20260921 as h30

CONTEXT, FEATURES, EPOCHS, BATCH_SIZE = 36, 4, 32, 128
ARCHITECTURES = ("dilated_tcn", "compact_attention")
SEEDS = (101, 103)
DEVICE = "cuda:0"


def _validate_fold(fold: h30.PreparedFold):
    for values in (fold.train_x, fold.eval_x):
        if (
            not isinstance(values, np.ndarray)
            or values.ndim != 3
            or values.shape[1:] != (CONTEXT, FEATURES)
            or len(values) == 0
        ):
            raise h30.StudyFailure("session_feature_shape")
    if not isinstance(fold.train_y, np.ndarray) or fold.train_y.shape != (len(fold.train_x),):
        raise h30.StudyFailure("session_target_shape")
    for values in (fold.train_x, fold.eval_x, fold.train_y):
        if values.dtype != np.float32 or not np.isfinite(values).all():
            raise h30.StudyFailure("session_input_dtype_or_nonfinite")


def _require_cuda(value):
    if not value.is_cuda or value.device.index != 0:
        raise h30.StudyFailure("cuda_device_required")


def fit(torch, fold: h30.PreparedFold, architecture, seed, deadline):
    """Return normalized EVAL predictions, numeric final state, and TRAIN-only facts.

    This fitter never reads evaluation observations/targets or fold metadata.
    H180 labeling and chronological normalization are the caller's responsibility.
    """
    _validate_fold(fold)
    if architecture not in ARCHITECTURES or type(seed) is not int or seed not in SEEDS:
        raise h30.StudyFailure("session_architecture_or_seed")
    if not isinstance(deadline, (int, float)) or not np.isfinite(deadline):
        raise h30.StudyFailure("session_deadline")
    h30.check_time(deadline)
    if not torch.cuda.is_available():
        raise h30.StudyFailure("cuda_unavailable")
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.cuda.reset_peak_memory_stats(DEVICE)
    model = family.build_sequence(torch, architecture).to(DEVICE)
    for value in (*model.parameters(), *model.buffers()):
        _require_cuda(value)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=0.01)
    loss_fn = torch.nn.MSELoss()

    # Upload each cohort once; every training/inference batch is a device-side view.
    train_x, train_y, eval_x = (
        torch.tensor(values, dtype=torch.float32, device=DEVICE)
        for values in (fold.train_x, fold.train_y, fold.eval_x)
    )
    for value in (train_x, train_y, eval_x):
        _require_cuda(value)
    torch.cuda.synchronize(DEVICE)
    h30.check_time(deadline)

    def predict_batch(values):
        output = model(values)
        _require_cuda(output)
        if (
            tuple(output.shape) != (len(values), 1)
            or output.dtype != torch.float32
            or not bool(torch.isfinite(output).all().item())
        ):
            raise h30.StudyFailure("session_prediction_shape_or_nonfinite")
        return output[:, 0]

    def measure(values, targets=None):
        model.eval()
        predicted = (
            torch.empty(len(values), dtype=torch.float32, device=DEVICE)
            if targets is None
            else None
        )
        squared_error = torch.zeros((), dtype=torch.float64, device=DEVICE)
        with torch.no_grad():
            for start in range(0, len(values), BATCH_SIZE):
                h30.check_time(deadline)
                stop = start + BATCH_SIZE
                output = predict_batch(values[start:stop])
                if targets is None:
                    predicted[start:stop] = output
                else:
                    difference = output.double() - targets[start:stop].double()
                    squared_error += difference.square().sum()
                torch.cuda.synchronize(DEVICE)
                h30.check_time(deadline)
        if targets is None:
            return predicted.cpu().numpy().copy()
        result = float((squared_error / len(values)).item())
        if not np.isfinite(result):
            raise h30.StudyFailure("nonfinite_loss")
        return result

    initial = measure(train_x, train_y)
    updates = 0
    for _ in range(EPOCHS):
        model.train()
        for start in range(0, len(train_x), BATCH_SIZE):
            h30.check_time(deadline)
            stop = start + BATCH_SIZE
            optimizer.zero_grad(set_to_none=True)
            output = predict_batch(train_x[start:stop])
            loss = loss_fn(output, train_y[start:stop])
            if not bool(torch.isfinite(loss).item()):
                raise h30.StudyFailure("nonfinite_loss")
            loss.backward()
            if any(
                p.grad is not None and not bool(torch.isfinite(p.grad).all().item())
                for p in model.parameters()
            ):
                raise h30.StudyFailure("nonfinite_gradient")
            optimizer.step()
            torch.cuda.synchronize(DEVICE)
            h30.check_time(deadline)
            updates += 1
    final = measure(train_x, train_y)
    predicted = measure(eval_x)
    state = {
        "state." + name: value.detach().cpu().numpy().astype(np.float32, copy=True)
        for name, value in model.state_dict().items()
    }
    if any(not np.isfinite(value).all() for value in state.values()):
        raise h30.StudyFailure("nonfinite_state")
    targets = fold.train_y.astype(np.float64)
    baseline = float(np.mean((targets - targets.mean()) ** 2))
    if not np.isfinite(baseline):
        raise h30.StudyFailure("nonfinite_loss")
    h30.check_time(deadline)
    return (
        predicted,
        state,
        {
            "epochs": EPOCHS,
            "updates": updates,
            "train_rows": len(train_x),
            "initial_train_mse": initial,
            "final_train_mse": final,
            "train_mean_baseline_mse": baseline,
            "parameter_count": sum(p.numel() for p in model.parameters()),
            "peak_cuda_memory_bytes": int(torch.cuda.max_memory_allocated(DEVICE)),
        },
    )
