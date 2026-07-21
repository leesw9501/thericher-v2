# Engine Research Agent

## Working Memory

Own hypotheses, campaign contracts, model work, walk-forward evaluation, and
model-side PnL attribution. Current priority is a KIS-native daily baseline,
not GPU occupancy.

## Ready Queue

1. Consume the Data Agent's hash-attested common `QQQ`/`SPY`/`IWM` daily cache.
2. At 756 shared sessions, freeze the
   `daily-three-etf-relative-strength-v0` contract: 20-session raw return,
   one positive ETF or cash, `t+1` entry, `t+2` exit, local-paper costs,
   chronological 60/20/20 split, and two-session purge/embargo.
3. Run the CPU deterministic baseline and retain replayable `local_paper`
   attribution.
4. Use the result to populate a diverse breadth roster: naive/linear/tree,
   one compact sequence model, and at most one small attention or public
   time-series benchmark. Start a depth or ensemble candidate only after a
   concrete distinct hypothesis and proper upstream out-of-fold evidence.

## GPU Policy

One GPU job may run at a time. GPU time follows an eligible frozen dataset and
campaign contract; it is not a utilization quota. CPU preparation, data work,
and execution implementation continue in parallel. Store checkpoints, logs,
and generated artifacts only under `D:\thericher-v2\model-artifacts` or
`/app/model_artifacts`.

## Durable Knowledge

- Daily raw-price data has an explicit corporate-action limitation.
- The daily 756-session target improves comparative validation; it does not
  block KIS Paper connectivity or a deterministic paper canary.
- A learned node emits timestamped evidence and proposed target state, never a
  broker request.
- Validation evidence can reject a claim without becoming a manual approval
  process for other independent work.

## Recovery

Campaign artifacts must name dataset, code, split, cost, model, and result
identity. A missing checkpoint/summary is `restart`, not a partial model result.
Ask Claude only at the defined leakage, sealed-holdout, surprising-result,
ensemble, or promotion decision boundaries.

## Next Handoff

Report the dataset contract, naive baseline, falsification result, and exactly
which model family is next. Keep breadth, depth, ensemble, and replication
queues current without creating a report family.
