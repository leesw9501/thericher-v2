# Strategy Research Stateboard (전략 탐색)

Updated Nov7UTC02:59 / Nov7KST11:59. A=D:/thericher-v2/model-artifacts.
Godel01a1ad7a-f750-7383-947e-2d7a3bc9bbec owns concise falsification/source
research, not numerical tuning or permanent model/Execution approval.
History/sourceoffers: Git8b1db436/01f23a13 and immutable APIs.

## Current Consumer

Issuer earnings hurdle source check, Nov26: three original announcement
pages distinguish release timing from the later webcast (GOOGL, AMD, NVDA).
Facts and public links only in
`D:/market_data/static_reference/issuer_earnings_announcements_20261126_v1/OBSERVATIONS.json`,
SHA256 `f0e605a09e1ca0b3f3f9e3b8a313cd218f1de97bad3d520b0aac9917700eeffb`.
This is a retrospective positive spot check, not PIT or negative coverage.
Claude Haiku independently rejected that inference. A future frozen trial
needs timestamped exact source/symbol captures before decision, release-time
precision separate from call time, and explicit completeness/revision limits.
Unknown is not a clean no-event signal; no model or Paper change from this check.

Sector sizing, Nov26: neither prior ETF context features nor the per-name
inverse-volatility caps tested sector-mass shrink while keeping the original
long-only support and within-sector weight ratios. A bounded prospective
candidate would move only sector mass halfway toward same-support EW sector
shares, compare unchanged sizing, ordinary half blend and same-gross EW at
25 bp/side, and retain no uplift claim without paired growth and drawdown.
The fraction-exact preflight identifies identity and ordinary-half duplicate
cases before outcomes. Four synthetic tests passed. Source:
`A/research/sector-mass-sleeve-static-preflight-20261126-v1/preflight.py`,
SHA256 `458e3ccc8e29176432f59075600fce3756b35edf03469396fe3955a3d8f3fd99`.
Claude checked the overlap question; its equal-sector-mass formula is a
different rule, not the pinned same-support EW target. No date-valid
historical 17-name sector map was found. Nov26 source work did bind a
separate observed SEC SIC industry proxy: 16 retained submissions matched
their original accepted receipt SHA/path and the [dated XOM filing](https://www.sec.gov/Archives/edgar/data/2115436/000211543626000020/0002115436-26-000020-index.html)
and cover supplied the seventeenth, using the newer filer rather than the
old header with no ticker. The 17 names occupy 12 two-digit SIC groups;
this is not GICS, historical PIT, or a new input to the five frozen slots.
`D:/market_data/static_reference/sec_sic17_observed_20261126_v1/OBSERVATIONS.json`
SHA256 `127a294194215a9462ac18bdcc9320416e790715a4d3faa88c51a406a8104b39`.
On that map the real pure comparator returned identity for equal weights
and distinct with unchanged gross on invented nonuniform weights. Current
fixed-half replay uses equal weight on support; skip the duplicate arm.
Only a separately prebound later nonuniform study can test this SIC proxy;
no scored tape, model fit, frozen experiment or Paper path changed.

Granite daily foundation candidate, Nov26: IBM `52-16-ft-r2.1`, immutable
checkpoint commit `8c9c1d742ec5893d6419e3aa2ab21ed23e28df85` (2025-02-26),
Apache-2.0. [Model card](https://huggingface.co/ibm-granite/granite-timeseries-ttm-r2).
Prior Granite campaigns used R1 plus trained heads; this is a distinct daily
zero-shot candidate. The pinned two-file safetensors model made one CPU
forward of invented 17x52x1 to 17x16x1, no data or fit. Existing pinned Granite
image, network-none, RO root/checkpoint; import initially required bounded
disposable `/tmp`. Both containers absent after run. Source and weights:
`A/research/granite-ttm-r21-52-16-runtime-smoke-20261126-v1`, smoke SHA256
`3c713a4debe90c73046f0a9d501f819dad0787750b823907bec70ba07f9e9e47`.
Before a separate post-checkpoint campaign, align a causal daily OPEN prefix
to forecast OPEN[e] and OPEN[e+3], not the gap into entry. Freeze naive and
same-gross EW comparisons, costs and mask; no untouched or profit claim from
release date alone. Keep this out of the frozen H3 block and Paper.
The bounded `A/research/granite-ttm-r21-open52-dev-screen-20261126-v1`
screen is now closed. One invented/one market CPU forward, zero fits and
one replay in 11.38 s including container lifecycles; no rerun/holdout.
The model received only the exact released 52-open prefixes; separate replay
received only scores and the already released COMMON marks. Exact archived
EW H3 mean and worst sampled drawdown matched. At 25 bp/side, Granite,
three-open momentum and EW averaged -5.32/-9.81/-5.97 bp net. Worst sampled
cohort drawdown was 1.1803/1.5051/0.8553 percent. Granite failed the frozen
positive growth and EW drawdown terms; no tuning/ensemble promotion on this
reused DEV. `output/RESULT.json` SHA256
`85fb56df4b49fcdbb799cce45169ab3450d5e9b32691caffc9ea83a335b0bb37`.

Proposal bundle current-self-lstm60-fixed-half-paper-proposal-preparation-
20261107-v1 COMPLETE synthetic (Source2072/bundleee98). Independent Godel review
confirmed best6 SELF MLP and OLD60 is exact Source72 best10 LSTM60 with the
original FIT receipt, class, stats, scale and H3 head. No calls in review.
Duplicate-key/numeric-type strictness remains for future consumer hardening.
Future point unknown, not production qualification; fixedblend DDfailure and
adaptive DEV+RECENT selection remain. No current Nov9 swap or extra bank.

## Research Direction From Actual Results

| Mechanism | Evidence / next interpretation |
| --- | --- |
| M5OHLC+IND8/LSTM/Ridge |6108/e6fb2CPUfits/1350updates/all4books0buys/NONINFORMATIVE. No lowercost/signthreshold rescue. |
| Freshentry cross-stockmean versus self |de8c/6526capacity-initmatched50849params/2CPU3924updates. POOL+1.970283%/-.392883%, SELF+2.155522%/+.133578%; POOLgrowth-DDFAILboth. More other-stock information not established as useful. |
| Temporal own versus crossattention |b3a6/22fac2matched11457paramCUDAfits4033updates/6books. CROSS-2.527785%/-1.032013%, SELF+1.698625%/-.365269%; CROSSFAILboth. Nativecausality/perturbation/QKV active; no mechanical larger-transformer queue on same outcomes. |
| MLPself+LSTM60fixedhalf |11973/aa5c0fits/4newbooks/0controlreplays. Growth+2.499935%/+.442062%, DD1.523969%/.958901%; growth-turn-effectsPASS/DDFAILboth. Explicitadaptive post-outcome selection, no oldfailure regrade or automaticPaperpromotion. |
| CausalpastRV20 downscaling |71d0/9643,0fits/4books. Exactfundedgrossmatchpassed. Same-name/grossEW had highergrowth andlowerDDboth periods; utilityFAILboth. Lowerexposurealone notalpha/no weightgrid rescue. |

All reused/current-listed aftercost25bpEACHleg. No independent replication,
confidence calibration or brokerPnl. Source-compatible fixed compositions can
be explored despite losing experts; learned fusion needs chronologicalOOF.
Older chart/technical/momentum-regime/price-volume/rule/HGB/OOF/GRU/TCN/Patch/
Transformer/SSL/TimesFM/Chronos studies remain in Git/APIs, not ignored methods.
Public-model checkpoint/pretraining/license limits constrain claims/consumers.
Proposals should become executable finite mechanism tests or concrete rejection,
not a readinglist/newgate/per-indicator role. Engine owns targets/splits/costs.

## Execution Review

Getter3ce1 +review5f72 sourcequalifies SAMEmanagedcontrol_reference only,
semantic_source_grant:false, not arbitraryJSsandbox or financialauthority.
ParentR8 SOURCE29ccc/native25bd ACTUALentry+coldexit pairPASS/0financialeffects.
Independent review12refs found no deterministic contradiction. Sharedhostpair,
sampledexitclosure and no separateFrame2/CFG4/all489audit are explicitlimits,
not a new approval. R6bdfd/R7f6a remainFAILED. Actual migration f88ac16f closed
with positive original owner closure, exit-first and complete XML/API7 ACL.
Due-time financial admission and effects remain separate.

ExactR8ActualCensus is running-only, unlike MSEall-container reader. Stopped
foreign4a56 does not establish R8/companyblock. Currentactualmembership and
fullleg/bank/owner admission unobserved; no fake bankfreeclassify call.

## Docker Endpoint Correction

Prior Boolean endpoint toy did NOT prove completeCID/StartedAt/FinishedAt/
restarttuple could stayequal across ordinary start-stop. Retract using it
against Parent's stronger tuple proposal. Primary Mobyv28 SetRunning changes
StartedAt/SetStopped changesFinishedAt; ordinary distinct-clock stabledaemon
cycle changes fulltuple. Installedengine notbound. Failedstatepersistence+
daemonrestore/clockrollback remain conditionalboundaries, no complete actual
preservingtrace demonstrated. No newinactiveexception or blanketrestartban.
Sources: https://raw.githubusercontent.com/moby/moby/v28.0.0/container/state.go
and https://docs.docker.com/engine/containers/start-containers-automatically/.
Unknownforeignownership is not authority tostopit or proof of bankwrite.

Parent46d027 actualsafe5GET projections showunless-stopped,3localvolumes-noopts/
oneunmappedRWbind/unknownsource/namednetwork+ports, notqualifiedisolation. No
privatecontents/credentials/queryrepeat; oldfailedprobe not regraded.

Claude latest currentR4recovery challenge61f6/dc43: ONEcall/exit1/unclassified/
2.225s/review_unavailable/allclosed/no rawretention; noauth/quota diagnosis,
agreement/retry/globalhold. Other scoped challenges likewise unavailable.
Advisoryfailure is not operatorapproval or permission hold. Exact evidence
pointers, not invented consensus. Parent owns direction/Git; no newplatform.
