"""Fixed context-36/H30 research fitters; callers own normalization and storage."""

from __future__ import annotations

import numpy as np

from thericher_v2.research import firstrate_m5_h30_lstm_dev_20260921 as h30
from thericher_v2.research.sequence_architecture_models import build_torch_sequence_model

CONTEXT, FEATURES, EPOCHS, BATCH_SIZE = 36, 4, 8, 128
ARCHITECTURES = ("dilated_tcn", "compact_attention")


def _validate_fold(fold: h30.PreparedFold):
    for values in (fold.train_x, fold.eval_x):
        if (
            not isinstance(values, np.ndarray)
            or values.ndim != 3
            or values.shape[1:] != (CONTEXT, FEATURES)
            or len(values) == 0
        ):
            raise h30.StudyFailure("family_feature_shape")
    if not isinstance(fold.train_y, np.ndarray) or fold.train_y.shape != (len(fold.train_x),):
        raise h30.StudyFailure("family_target_shape")
    for values in (fold.train_x, fold.eval_x, fold.train_y):
        if values.dtype != np.float32 or not np.isfinite(values).all():
            raise h30.StudyFailure("family_input_dtype_or_nonfinite")


def _prediction(values, rows):
    values = np.asarray(values)
    if values.shape != (rows,) or values.dtype.kind not in "fi" or not np.isfinite(values).all():
        raise h30.StudyFailure("family_prediction_shape_or_nonfinite")
    return values


def _mse(predicted, targets):
    result = float(np.mean((np.asarray(predicted, dtype=np.float64) - targets) ** 2))
    if not np.isfinite(result):
        raise h30.StudyFailure("nonfinite_loss")
    return result


def fit_lightgbm(fold: h30.PreparedFold):
    """Return (normalized EVAL predictions, booster text, TRAIN-only fit facts)."""
    _validate_fold(fold)

    # The pinned runtime obtains OpenMP from Torch before loading LightGBM.
    import torch  # noqa: F401, I001

    import lightgbm

    if lightgbm.__version__ != "4.6.0":
        raise h30.StudyFailure("lightgbm_version")
    model = lightgbm.LGBMRegressor(
        objective="regression",
        n_estimators=64,
        num_leaves=7,
        max_depth=3,
        learning_rate=0.05,
        min_child_samples=64,
        reg_lambda=1,
        subsample=1,
        colsample_bytree=1,
        random_state=101,
        n_jobs=1,
        deterministic=True,
        force_col_wise=True,
        verbosity=-1,
    )
    train = fold.train_x.reshape(len(fold.train_x), -1)
    evaluation = fold.eval_x.reshape(len(fold.eval_x), -1)
    baseline = _mse(float(fold.train_y.mean(dtype=np.float64)), fold.train_y)
    model.fit(train.copy(), fold.train_y.copy())
    fitted = _prediction(model.predict(train.copy()), len(train))
    predicted = _prediction(model.predict(evaluation.copy()), len(evaluation))
    return (
        predicted,
        model.booster_.model_to_string(),
        {
            "train_rows": len(train),
            "eval_rows": len(evaluation),
            "tree_count": int(model.booster_.num_trees()),
            "initial_train_mse": baseline,
            "final_train_mse": _mse(fitted, fold.train_y),
            "train_mean_baseline_mse": baseline,
        },
    )


def build_sequence(torch, architecture):
    """Build a fixed scalar head; the TCN's causal receptive field is 63 bars."""
    if architecture not in ARCHITECTURES:
        raise h30.StudyFailure("family_architecture")
    if architecture == "compact_attention":
        return build_torch_sequence_model(
            torch=torch,
            architecture_id=architecture,
            feature_count=FEATURES,
            hidden_size=16,
            attention_heads=2,
            tcn_kernel_size=3,
        )
    nn = torch.nn

    class DilatedTcn(nn.Module):
        def __init__(self):
            super().__init__()
            layers = []
            for index, dilation in enumerate((1, 2, 4, 8, 16)):
                layers.extend(
                    (
                        nn.ConstantPad1d((2 * dilation, 0), 0.0),
                        nn.Conv1d(FEATURES if index == 0 else 16, 16, 3, dilation=dilation),
                        nn.ReLU(),
                    )
                )
            self.encoder = nn.Sequential(*layers)
            self.head = nn.Linear(16, 1)

        def forward(self, values):
            return self.head(self.encoder(values.transpose(1, 2))[:, :, -1])

    return DilatedTcn()


def fit_sequence(torch, fold: h30.PreparedFold, architecture, seed, deadline):
    """Return (normalized EVAL predictions, numeric state arrays, TRAIN-only facts)."""
    _validate_fold(fold)
    if architecture not in ARCHITECTURES or seed not in (101, 103):
        raise h30.StudyFailure("family_architecture_or_seed")
    h30.check_time(deadline)
    if not torch.cuda.is_available():
        raise h30.StudyFailure("cuda_unavailable")
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    model = build_sequence(torch, architecture).to("cuda:0")
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=0.01)
    loss_fn = torch.nn.MSELoss()

    def tensor(values):
        return torch.tensor(values, dtype=torch.float32, device="cuda:0")

    def measure(values, targets=None):
        model.eval()
        predicted = np.empty(len(values), dtype=np.float32) if targets is None else None
        squared_error = 0.0
        with torch.no_grad():
            for start in range(0, len(values), BATCH_SIZE):
                h30.check_time(deadline)
                stop = min(start + BATCH_SIZE, len(values))
                output = model(tensor(values[start:stop])).flatten().cpu().numpy()
                output = _prediction(output, stop - start)
                if targets is None:
                    predicted[start:stop] = output
                else:
                    squared_error += _mse(output, targets[start:stop]) * (stop - start)
                h30.check_time(deadline)
        return predicted if targets is None else squared_error / len(values)

    initial = measure(fold.train_x, fold.train_y)
    updates = 0
    for _ in range(EPOCHS):
        model.train()
        for start in range(0, len(fold.train_x), BATCH_SIZE):
            h30.check_time(deadline)
            stop = start + BATCH_SIZE
            optimizer.zero_grad(set_to_none=True)
            output = model(tensor(fold.train_x[start:stop])).flatten()
            loss = loss_fn(output, tensor(fold.train_y[start:stop]))
            if not bool(torch.isfinite(loss).item()):
                raise h30.StudyFailure("nonfinite_loss")
            loss.backward()
            if any(
                p.grad is not None and not bool(torch.isfinite(p.grad).all().item())
                for p in model.parameters()
            ):
                raise h30.StudyFailure("nonfinite_gradient")
            optimizer.step()
            torch.cuda.synchronize()
            h30.check_time(deadline)
            updates += 1
    final = measure(fold.train_x, fold.train_y)
    predicted = measure(fold.eval_x)
    state = {
        "state." + name: value.detach().cpu().numpy().astype(np.float32, copy=True)
        for name, value in model.state_dict().items()
    }
    if any(not np.isfinite(value).all() for value in state.values()):
        raise h30.StudyFailure("nonfinite_state")
    h30.check_time(deadline)
    return (
        predicted,
        state,
        {
            "epochs": EPOCHS,
            "updates": updates,
            "train_rows": len(fold.train_x),
            "initial_train_mse": initial,
            "final_train_mse": final,
            "train_mean_baseline_mse": _mse(
                float(fold.train_y.mean(dtype=np.float64)), fold.train_y
            ),
            "parameter_count": sum(p.numel() for p in model.parameters()),
        },
    )
