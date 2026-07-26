# Codex Orchestration Stateboard

AGENTS.md owns policy and NEXT_CODEX_GOAL.md owns the company objective. This
is a cross-lane projection, not a role lane, queue ledger, or second goal.

## Current Cross-Lane View

- Data has implemented, smoke-tested, and integrated the KIS Paper
  single-client, concurrency-one session-capture worker with the one existing
  intraday-head task. Its capture-scoped QQQ coverage is zero of 390
  regular-session minutes because the measured terminal page is extended-session
  evidence; that is correctly excluded from Research. The scheduled task's
  future result is Data-local evidence, not a company-wide dependency.
- Engine Research completed the fixed QQQ/SPY daily sequence breadth screen:
  one CPU smoke and one Docker CUDA screen over LSTM, causal TCN, and compact
  attention. Both produced only external checkpoints and six `local_paper`
  replay cells; neither selected a model, ensemble, promotion, or Paper action.
- Execution completed the deterministic target-weight-to-local-paper-intent
  binding without changing local/KIS/live route isolation.
- The only shared resources are KIS Paper market-data throughput and one GPU.
  Data owns the first; Research owns the second. There is no current storage
  conflict.

## Current Bottleneck

The material Data unknown is continuous, source-qualified KIS 1m session
coverage. The completed daily screen remains development-only evidence with
unqualified corporate-action semantics, so it cannot become a model-selection
or execution input. The capture worker does not prove historical pagination or
a complete regular session.

## Current Operating Improvement

The first PyTorch CUDA image build was slow, while the source and scripts are
already read-only mounted into the research container. Reuse that image for
code-only bounded research runs and rebuild only when the Dockerfile or runtime
dependency contract changes. Keep prospective readiness local to its consumer;
a worker owns its own backoff and recovery, and Codex does not sleep while
another lane is ready. At task resume or an observed unexplained foreground idle
period, invoke one bounded Throughput Review from the existing stateboards and
active-job facts; retain only one measured, reversible improvement here rather
than creating a standing process lane.

## External Waits

- The scheduled intraday head has a due time, but it does not hold the capture
  worker implementation, historical evidence preservation, or Execution.
- Claude CLI OAuth is expired. Retry it at the next material decision boundary;
  do not block ordinary private work.

## Recovery

Current class: resume. Reattest an individual cache, campaign, or exact Paper
intent before relying on it. Scope failure to that item and continue independent
lanes.

## Next Handoff

Integrate the completed daily breadth evidence, then advance the next single
company objective without treating a descriptive screen as a selected model.
Record only an actual shared resource conflict, new external wait, bottleneck,
or reversible operating improvement here.
