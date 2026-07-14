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

- GPU: idle until the first GPU research goal is started.
- Model artifacts root: `D:\thericher-v2\model-artifacts`.
- Docker artifact path: `/app/model_artifacts`.

## Active Queue

1. After local paper execution exists, define the first bounded GPU research
   experiment using existing `Bar` data and external artifacts.
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

- Do not start GPU training until data and local paper execution can produce
  useful validation targets.
- Once GPU research begins, alternate short experiments and longer candidate
  training so the single GPU stays useful without hiding weak validation.
