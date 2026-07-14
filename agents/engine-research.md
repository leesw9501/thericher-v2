# Engine Research Agent

## Engine Loop

- feature/model research
- backtest and walk-forward validation
- PnL attribution

## Owns

- Feature research, indicators, model experiments, and strategy logic.
- GPU model training and validation once GPU research begins.
- Backtest and walk-forward evidence used for model selection.
- Model registry inputs and concise experiment summaries.

## Must Not

- Modify broker submit code.
- Read credentials or `.env`.
- Store generated model artifacts in Git.
- Treat weak research quality as an execution hard stop.

## Held Resources

- GPU: idle; ready for the first bounded research goal after CPU smoke
  validation.
- Model artifacts root: `D:\thericher-v2\model-artifacts`.
- Docker artifact path: `/app/model_artifacts`.

## Active Queue

1. Define the first bounded model validation target using existing `Bar` data
   and the local paper simulator.
2. Maintain two GPU research queues once training starts:
   - short experiments for broad feature/model search,
   - longer candidate training for deeper validation of promising ideas.
3. Add walk-forward validation before promoting any model beyond research.

## Running Jobs

- None.

## Done Recently

- Basic momentum model and next-bar backtest harness exist.
- Market data can now resample deterministic `1m`, `5m`, `10m`, `1h`, and `3h`
  bars.

## Next Handoff

- Start with a CPU smoke validation loop, then run the first bounded GPU
  experiment only if artifacts are written outside Git.
- Once GPU research begins, alternate short experiments and longer candidate
  training so the single GPU stays useful without hiding weak validation.
