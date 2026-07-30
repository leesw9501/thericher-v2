# Research Steward Agent Stateboard

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is the current scarce-resource projection, not a strategy queue, campaign
ledger, approval gate, or second objective.

## Ownership

Own cross-track custody of the exclusive GPU appointment and sealed-evaluation
family/allocation record. Maintain source-safe campaign lineage in the external
`research_campaign_custody` control namespace. Do not choose hypotheses, tune
models, access raw labels, create features, train a model, select portfolio
weights, modify execution risk, or call a broker.

## Current Resource State

- GPU: free. No frozen labelled campaign is eligible while the historical D1
  input remains quarantined. This is not a request to manufacture training and
  does not block independent Data, Execution, or CPU Research preparation.
- Sealed evaluation: no newly allocated family. Earlier target-free and sealed
  receipts remain historical evidence; they cannot be reused as a new campaign
  or selection pass.
- Custody substrate: append-only external `research_campaign_custody` ledger
  plus immutable artifact receipts. No raw labels, predictions, prices,
  weights, credentials, account identifiers, or broker bodies belong here.

## Dispatch Contract

1. Engine Research freezes the dataset, target, split, cost model, naive
   baseline, compute stop rule, strongest kill test, artifact root, and family
   lineage before a GPU or sealed-evaluation request is eligible.
2. When the GPU is free, allocate the first ready frozen campaign. Break a real
   tie with independent replication or an underrepresented hypothesis family,
   then the shorter bounded job. Do not use fixed rotation or train merely for
   utilization.
3. A Cross-Track Synthesis proposal creates a new family record. It may combine
   frozen out-of-fold evidence, but it cannot consume a sealed evaluation or
   become a promoted ensemble until its own frozen campaign is allocated.
4. Research-side portfolio/allocation candidates state correlation, capacity,
   turnover, and availability assumptions. Execution may reject those inputs
   independently; Steward records linkage only.
5. A missing field or unavailable resource defers only that candidate. It never
   asks the operator for routine approval or blocks another ready package.

## Durable Knowledge

- Target-free r6 artifacts are not transferable labelled-model weights.
- Historical D1 remains quarantined for new labelled campaigns.
- One GPU job runs at a time; a KIS Paper inference or reliability need
  preempts research at a safe checkpoint.

## Recovery And Next Handoff

Current class: `complete` for topology establishment and `resume` for the next
eligible allocation. On resume, reattach the latest custody receipt, verify
that an active GPU job and allocation record agree, then dispatch the first
eligible frozen campaign or record the exact scoped eligibility fact.
