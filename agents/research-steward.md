# Research Steward Agent Stateboard (연구 자원 및 평가 관리자)

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This stateboard retains only cross-track GPU and sealed-evaluation custody.

## Current Resource State

- The RTX 4090 is free. No active GPU process or sealed-evaluation allocation
  is held by Research Steward.
- No frozen, input-qualified campaign is ready for an appointment.
- The completed Granite TTM R1 structural smoke used one bounded appointment
  and released it. It is runtime compatibility evidence only, not a predictive
  campaign or a reason to reserve GPU capacity.
- The reattached Chronos-T5 Tiny R4 CUDA diagnostic is a completed source-local,
  non-promoting zero-shot probe, not an open allocation or predictive campaign.
  Its fixed zero-return baseline was not surpassed, so it releases no follow-on
  GPU work without a distinct eligible contract.
- Model artifacts and source-safe receipts remain external under
  `D:\thericher-v2\model-artifacts`; Git holds neither model weights nor raw
  market data.

## Appointment Contract

Before a GPU appointment, Engine Research must freeze:

1. dataset identity and source/availability limits;
2. target, chronological split, purge/embargo, and effective sample rule;
3. timeframe/window matrix and shared family budget when applicable;
4. costs, naive baseline, strongest kill test, compute stop rule, and artifact
   root; and
5. family lineage and sealed-holdout access status.

Missing information defers only that campaign. It never creates an operator
approval request or blocks CPU preparation, Data collection, or Execution.

## Allocation Rule

When the GPU becomes idle, allocate the first ready frozen campaign. Break a
real tie by independent replication or underrepresented hypothesis family, then
the shorter bounded job. Execution reliability/inference preempts research at a
safe checkpoint. Do not consume GPU for closed historical lineages, static
source controls, timing probes, or utilization-only training.

## Evaluation Custody

The external `research_campaign_custody` record retains campaign identity,
family lineage, GPU appointment, and sealed-evaluation spend without raw labels,
predictions, prices, weights, credentials, or broker data. Cross-track synthesis
is a new family and cannot reuse a sealed allocation or select weights from
previous results.

## Handoff

Reattach custody before a new appointment. Record only the current allocation,
result category, evidence pointer, and next eligible campaign. Historical GPU
and evaluation evidence remains in Git and external receipts.
