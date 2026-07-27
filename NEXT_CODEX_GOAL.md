# Next Codex Goal

## Objective

Run the first bounded source-local NAS D1 candidate-breadth package from the
frozen campaign contract.

First prove one independent per-symbol CPU L2-logistic smoke path. Then, when
that path is sound and the existing Docker/PyTorch CUDA environment is usable,
run the fixed per-symbol GPU architecture breadth across LSTM, causal TCN, and
compact attention. This is model plumbing and descriptive candidate evidence,
not a selection, ensemble, replay, PnL, or Paper decision.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `DECISIONS.md`, and the active stateboards.
2. Reattest the NAS phase input and precommit before consuming a sample:
   - panel dataset: `sha256:7e8d6fe54dd5252fc4b9548b70e3bb31aefcd282922a50c1ca7c58a94d57dc8e`
   - campaign contract: `sha256:5a9ceb6df7b6c1909ef452b8851fbd7bd23ec03660e9fc75bb278377079aaea5`
   - precommit: `sha256:c54e795b3fb2caa76c9367a72aadc1c0ac685241bd5c59e2e12bdb0af603d37e`
3. Use Claude only at a material promotion, sealed-label/holdout, depth-training,
   source/routing authority, or major-runtime boundary. Initial bounded breadth
   work does not wait on the expired local Claude OAuth session.

## Frozen Input

- Six source-local current NAS streams only: `AAPL`, `AMZN`, `GOOGL`, `META`,
  `MSFT`, and `NVDA`; do not infer point-in-time membership, liquidity, or rank.
- Exact `1,510 / 22 / 647` common D1 development / purge / validation sessions.
- One per-symbol feature column: 20 completed close returns at `t-19..t`, with
  the `t-20` return anchor inside the same phase.
- Development labels only: strict-positive one-share after-cost return from
  `t+1` open to `t+2` open using 1 bps fee and 2 bps slippage per fill.
- Validation input is target-free. Do not materialize, inspect, reconstruct, or
  persist validation labels in this objective.

## Work

1. **Engine Research / CPU:** implement the fixed
   `nas-d1-per-symbol-l2-logistic-smoke-v1` package. Fit six independent L2
   logistic models from development samples only, with per-symbol
   development-only standardization, deterministic seeds, a bounded CPU budget,
   finite-loss checks, and target-free validation forward-shape checks.
2. **Infra / Engine Research / GPU:** reuse the existing Docker PyTorch CUDA
   runtime and shared sequence builders to implement and run
   `nas-d1-per-symbol-sequence-breadth-v1`: LSTM, causal TCN, and compact
   attention for each symbol. One GPU job runs at a time; preparation and tests
   may run on CPU concurrently. Freeze architecture and budget settings before
   the first fit. If CUDA is unavailable, record the exact runtime fact and
   complete every non-GPU package without foreground waiting.
3. **Validation:** add focused tests for development-only fitting,
   per-symbol-only standardization, target-free validation inputs, deterministic
   CPU smoke, GPU/Docker command construction, external-only artifacts,
   safe checkpoint handling, and no network/credential/KIS/broker route.
4. **Artifacts:** checkpoints and generated model data stay only under
   `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`. Persist only
   source-safe aggregate receipts and hashes in Git-visible evidence; no raw
   bars, feature rows, labels, per-decision probabilities, PnL, or broker
   events.

## Boundaries

- No KIS call, credential or `.env` read, provider download, paid asset, public
  service, account/quote/order route, or live behavior.
- No validation-label reveal, local-paper replay, PnL metric, parameter sweep,
  winner selection, ensemble, promotion, or Paper order.
- Do not change the source panel, split, feature window, target/cost semantics,
  comparator contract, or source limitations.
- Do not commit generated artifacts, checkpoints, weights, caches, or Docker
  volumes.

## Completion

- Six deterministic CPU smoke fits prove the frozen input path without using a
  validation label or cross-symbol feature/standardizer.
- The Docker CUDA breadth package has source-safe external evidence for every
  attempted architecture/symbol, or an exact bounded CUDA-unavailable fact while
  all CPU work is complete.
- No outcome is interpreted as profitable, selected, ensembled, replayed, or
  eligible for Paper trading.
- Refresh stateboards and replace this file with exactly one next company
  objective before ending.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add NAS D1 sequence architecture breadth`
