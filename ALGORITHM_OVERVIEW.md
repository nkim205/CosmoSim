# Algorithm overview

Policy implementation: [`spectrum_management/scored_rf.py`](spectrum_management/scored_rf.py)  
Registered as `scored-rf` in [`spectrum_management/beam_mapping.py`](spectrum_management/beam_mapping.py).

This file is at the **repo root**; links are relative from here.

---

## 1. How the algorithm works

`scored-rf` only does **RF beam assignment** (which satellite/channel serves which cell). CosmoSim still turns that map into admitted demand and runs **max-flow** to decide what is delivered. The policy’s job is to pick beams so admitted traffic is more likely to reach a gateway.

### Scoring formula

For each legal `(cell, satellite)` candidate, one channel at a time:

```text
Score = α·D + β·F − γ·C
```

| Symbol | Meaning | Default weight |
| --- | --- | --- |
| **D** | Normalized unmet RF demand | α = 0.5 (fixed) |
| **F** | Normalized underservice (fairness) | β = 0.3 |
| **C** | Estimated egress congestion | γ = 0.2 |

Higher score wins. Demand and fairness raise the score; congestion lowers it.

### Main loop (one simulated second)

1. CosmoSim calls `assign_beams(...)` with cells, visibility, free beams, shells.
2. Load the Haiti graph for that second; if γ ≠ 0 and gateway and/or ISL awareness is on, build a **shared egress residual** pool (scaled by `--gw-scale` / `--isl-scale`).
3. Repeat until unmet demand is gone or no legal assignment remains:
   - Recompute unmet demand and **re-normalize D**; if β ≠ 0, also **recompute F** from updated channel counts + history
   - Consider only **legal** candidates: the sat must be visible to the cell, a free beam/channel must exist, and CosmoSim interference checks must pass
   - Score every legal `(cell, sat)` with D, F, C
   - Assign **one** channel to the best pair
   - Update that cell’s channels, sat admitted load, and the heuristic residual pool
4. Return `{cell_channel → color_sat_channel}` like every other CosmoSim policy.

### D — unmet demand

How much of a cell’s **offered** traffic still cannot be **admitted** given channels already assigned:

- **Offered** = `num_terminals × 100 Mbps`
- **Allocated (admitted)** = CosmoSim channel-fill: terminals are divided across the cell’s current channels; each channel admits `min(terminals_on_channel × 100 Mbps, Ku beam capacity)`
- **Unmet** = `max(0, offered − allocated)`
- **D** = `unmet / max_unmet` over cells that still have unmet demand

`unmet` and `max_unmet` are rebuilt **after every channel assignment**, so D stays up to date through the greedy loop.

### F — fairness

**F** measures how underserved a cell is based on its **current and historical RF admission** satisfaction (`allocated / offered`). Cells that have received a smaller fraction of their requested RF capacity get a higher fairness score. This is **not** delivered/offered after max-flow.

```text
effective_sat = HISTORY_BLEND·hist + (1 − HISTORY_BLEND)·sat_now
underservice  = 1 − effective_sat
F             = underservice / max_underservice   # if max_underservice > 0
```

- If every cell has underservice ≈ 0 (`max_underservice ≤ 1e-12`), **F = 0 for all cells** (no fairness pressure; avoids divide-by-zero).
- Cross-second history is an EMA in `<scale_dir>/scored_rf_history.json`
- After each second: `hist ← HISTORY_EMA·hist + (1 − HISTORY_EMA)·sat_this_second`
- Defaults: `HISTORY_EMA = 0.7`, `HISTORY_BLEND = 0.7`
- β = 0 turns fairness off

A cell can look fully served in **F** and still strand under gateway congestion. Report headline fairness from delivered-based metrics, not from this history alone.

### C — congestion

```text
additional = Mbps this new channel would place on the sat
residual   = best shared egress residual (local feeder+GS, or 1-hop ISL→GS)
C          = 1 − min(1, residual / additional)
```

`residual` is **estimated** available downstream capacity in the heuristic, not actual free capacity from CosmoSim max-flow. Example: a channel that would add 1 280 Mbps with estimated residual 640 Mbps gets `C = 1 − 640/1280 = 0.5` before the weight γ is applied.

The congestion penalty estimates how much of a new channel’s traffic may exceed available downstream capacity. It is **not** a measurement of actual network congestion, which is evaluated separately using CosmoSim’s max-flow results. The heuristic also **does not reserve** capacity in the real routing graph.

Shared residual pool (so two sats cannot both treat the same resource as free):

| Resource | Initial residual |
| --- | --- |
| Per-sat feeder | `sat_gs_max_capacity × gw_scale` if the sat has a GS neighbor, else 0 |
| Per ground station | `ground_station_gsl_capacity × gw_scale` |
| Per ISL edge | graph edge capacity × `isl_scale` |

Egress options considered for scoring: **direct feeder→GS** or **one-hop ISL then neighbor feeder→GS**. CosmoSim max-flow may use longer paths; the heuristic does not.

Toggle gateway vs ISL awareness with `--scored-rf-use-gateway` / `--scored-rf-use-isl` (Methods 3 and 4). See Method 4 notes below for what “gateway off” actually means in code.
---

## 2. Files and runtime flow

### What happens when you run an experiment

```text
terminals + graphs
        │
        ▼
┌─────────────────────────────────────┐
│ experiments/run_experiment.py       │  orchestrates scenarios × policies × scales × seconds
│   or experiments/pr1_evaluation/    │  same runner, one PR method + scenario matrix
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│ workflows/generate_flows.py         │  visibility → beam_mapping(policy) → demands.txt
│   → spectrum_management/            │  scored-rf scores D,F,C here (admission only)
│      scored_rf.py / beam_mapping.py │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│ workflows/generate_capacities_      │  Ka assignment, apply isl/gw scales, max-flow
│   scaled.py                         │  → delivered / stranded
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│ analysis/metrics.py (+ collect /    │  throughput, satisfaction, Jain, util, runtime
│   validate / consistency)           │  → metrics_*.json, metrics_summary.csv
└─────────────────────────────────────┘
```

| Quantity | Who computes it |
| --- | --- |
| Offered | terminals × 100 Mbps |
| Admitted | beam map → `demands.txt` |
| Delivered | CosmoSim max-flow into gateway sinks |
| Stranded | admitted − delivered |

### Key files

| Path | Role |
| --- | --- |
| `spectrum_management/scored_rf.py` | Allocator: score loop, D/F/C, shared residuals, fairness history |
| `spectrum_management/beam_mapping.py` | Registers `scored-rf` (and baselines) for workflows |
| `spectrum_management/equal_rf.py` / `demand_proportional.py` | Baseline policies |
| `workflows/generate_flows.py` | Calls the policy; passes scales, β/γ, gateway/ISL flags, history path; times allocation |
| `workflows/generate_capacities_scaled.py` | Scaled max-flow routing |
| `experiments/run_experiment.py` | Main runner: scenarios, policies, scales, duration → `data/runs/<name>/` |
| `experiments/pr1_evaluation/run.py` | One PR method across a scenario matrix; writes findings |
| `experiments/pr1_evaluation/methods.py` | Method ids (1–5, full, ablations) → policy flags |
| `experiments/pr1_evaluation/scenarios.py` | Smoke / full scenario matrices |
| `analysis/metrics.py` | PR-aligned metric definitions |
| `analysis/collect_metrics.py` | Walk a run tree and write `metrics_summary.csv` |
| `analysis/validate_metrics.py` | Unit + consistency checks |
| `analysis/METRICS.md` | Metric audit table |
| `experiments/verify_scored_rf_fairness.py` | Sanity check that history changes allocation |
| `experiments/analyze_allocation_fairness.py` | Inspect allocation Jain on a finished run |
| `terminal_deployment/terminals/` | Scenario demand layouts (uniform, hotspot, wide, …) |
| `graph_generation/graphs_noglobal/.../haiti/` | Per-second network graphs |
| `data/runs/<name>/` | Experiment outputs (gitignored) |

---

## 3. How to run

Always from the **repository root** (`.venv/bin/python …`).

### Tests (no full simulation)

```bash
# Metric definitions + consistency checks
.venv/bin/python analysis/validate_metrics.py

# Fairness term actually changes who gets channels when β > 0
.venv/bin/python experiments/verify_scored_rf_fairness.py
```

After you have a finished run:

```bash
.venv/bin/python analysis/validate_metrics.py --experiment data/runs/<name>
.venv/bin/python analysis/collect_metrics.py data/runs/<name> --print
.venv/bin/python experiments/analyze_allocation_fairness.py data/runs/<name>
```

### Quick scored-rf run

```bash
.venv/bin/python experiments/run_experiment.py \
  --quick --policies scored-rf --name smoke_scored --no-log --overwrite
```

### Methods (`--method`) — what you are comparing

Defined in [`experiments/pr1_evaluation/methods.py`](experiments/pr1_evaluation/methods.py). One run = **one method** across a scenario matrix.

| Id | What it is | CosmoSim settings | Why run it |
| --- | --- | --- | --- |
| `1` | **Equal RF** baseline | Policy `equal-rf`: ignore demand; round-robin channels | Simple demand-independent baseline used to evaluate whether more informed allocation decisions improve performance |
| `2` | **Demand-proportional** baseline | Policy `demand-proportional`: split channels by terminal share | Demand-aware RF that still **ignores** gateway/ISL congestion |
| `3` | Demand- and **gateway**-aware RF **without ISL** | `scored-rf`, β=0.3, γ=0.2, gateway **on**, ISL **off** | Ablation: score **C** using only direct feeder+GS residuals |
| `4` | Demand- and **ISL**-aware RF **without local gateway scoring** | `scored-rf`, β=0.3, γ=0.2, gateway **off**, ISL **on** | Ablation: stress 1-hop ISL awareness (see note below) |
| `5` | Full coordination **without fairness** | `scored-rf`, β=**0**, γ=0.2, gateway+ISL **on** | Ablation: remove **F**; isolate demand + congestion |
| `full` | **Proposed** policy | `scored-rf`, αD + βF − γC, β=0.3, γ=0.2, gateway+ISL **on** | Headline algorithm for the report |
| `ablate-demand` | Demand only | `scored-rf`, β=0, γ=0 | Score ≈ αD only (no fairness, no congestion) |
| `ablate-cong` | Demand + congestion | `scored-rf`, β=0, γ=0.2, both awareness on | Same as Method 5; named for ablation plots |
| `ablate-fair` | Demand + fairness | `scored-rf`, β=0.3, γ=0 | No congestion term — expect weaker gains when GW/ISL is tight |

**Method 4 / `USE_GATEWAY = False` (verified in `SharedEgress.best_egress`):**

- Sats that **already have** a local feeder+GS get residual = ∞ → **C = 0** (no local gateway congestion penalty).
- Sats **without** a local GS are scored on 1-hop ISL paths only. Those paths still use `min(ISL, neighbor feeder, neighbor GS residual)` — so Method 4 still needs a neighbor that can reach a gateway, and still accounts for that neighbor’s feeder/GS capacity when estimating ISL residual.
- Disabling gateway awareness therefore means “do not penalize congestion on **direct** local feeder paths,” **not** “pretend gateways do not exist on ISL egress.”

Aliases: `equal`, `demand`, `no-isl`, `no-gateway`, `no-fair`, `proposed`, `demand-only`, `cong-only`, `fair-only`.

```bash
.venv/bin/python experiments/pr1_evaluation/run.py --list-methods
```

### Demand layouts (scenario short names)

These are terminal files under `terminal_deployment/terminals/`. Pass them to `run_experiment.py --scenarios …`, or they are pulled in automatically by matrix **cases** below.

| Short name | Terminals | Layout | What it stresses |
| --- | ---: | --- | --- |
| `10k-uniform` | 10 000 | Spread evenly across Haiti cells | Balanced load; good control / baseline throughput |
| `10k-pop` | 10 000 | Weighted by the project’s population raster | Uneven demand (population-based, not claimed as a validated real-world forecast) |
| `10k-hotspot-pap` | 10 000 | Sharp peak around Port-au-Prince | Dense local demand → RF admission ceiling often binds |
| `10k-hotspot-north` | 10 000 | Sharp peak in the north | Same idea, different geography / visibility |
| `5k-wide-pap` | 5 000 | Broader hotspot around PaP | More admitted traffic than sharp 10k hotspots → better for GW/ISL stress |
| `5k-wide-north` / `5k-wide-south` | 5 000 | Wide hotspot elsewhere | Geographic robustness |
| `5k-wide-shift` | 5 000 | Wide hotspot that **moves over time** (`.schedule`) | Time-varying demand; fairness history can matter |
| `1k-uniform` / `1k-pop` | 1 000 | Same patterns, smaller | Fast debugging only |

Capacity knobs (independent of demand layout):

- `--gw-scale` — multiply feeder + ground-station capacity (e.g. `1`, `0.5`, `0.25`)
- `--isl-scale` — multiply ISL edge capacity (e.g. `1`, `0.1`)

### Evaluation cases (`--matrix` / `--cases`)

Defined in [`experiments/pr1_evaluation/scenarios.py`](experiments/pr1_evaluation/scenarios.py). A **case** bundles demand layout(s) + capacity scales so you know which research question you are answering.

#### `--matrix smoke` (smoke / preliminary test — not comprehensive evidence)

Use this for plumbing checks and early comparisons. Do **not** treat smoke results as the full evaluation.

| Case | Runs | Scales | Intent |
| --- | --- | --- | --- |
| `uniform` | `10k-uniform` | isl=1, gw=1 | Happy path / control |
| `hotspot` | `10k-hotspot-pap` only | isl=1, gw=1 | Sharp hotspot RF ceiling |
| `limited_gw` | `5k-wide-pap` | isl=1, gw=**0.5** | Mild gateway bottleneck |

#### `--matrix pr1` (full coverage)

| Case | Runs | Scales | Intent |
| --- | --- | --- | --- |
| `uniform` | `10k-uniform` | isl=1, gw=1 | Uniform demand baseline |
| `hotspot` | `10k-hotspot-pap` **and** `10k-hotspot-north` | isl=1, gw=1 | Sharp hotspots in two regions |
| `wide` | `5k-wide-pap` **and** `5k-wide-north` | isl=1, gw=1 | Wider hotspots (more admit → more routing pressure) |
| `shift` | `5k-wide-shift` | isl=1, gw=1 | Demand moves over simulated seconds |
| `limited_gw` | `10k-uniform` + `5k-wide-pap` | isl=1, gw=**0.5 and 0.25** | Gateway scarcity (control + stressed demand) |
| `limited_isl` | `10k-uniform` + `5k-wide-pap` | isl=**0.1**, gw=1 | ISL scarcity |
| `combined` | `5k-wide-pap` | isl=**0.1**, gw=**0.5** | Both bottlenecks at once |

### Example commands

```bash
# Compare policies on uniform + pap hotspot
.venv/bin/python experiments/run_experiment.py \
  --scenarios 10k-uniform 10k-hotspot-pap \
  --policies scored-rf equal-rf \
  --duration 5 --name cmp_uniform_hotspot --no-log

# Capacity sweep on one layout
.venv/bin/python experiments/run_experiment.py \
  --scenarios 10k-uniform \
  --policies scored-rf \
  --gw-scale 1 0.5 0.25 --isl-scale 1 0.1 \
  --duration 5 --name scale_sweep --no-log

# Smoke matrix for the proposed method
.venv/bin/python experiments/pr1_evaluation/run.py \
  --method full --matrix smoke --name pr1_mfull_smoke

# Full matrix for Equal RF (Method 1)
.venv/bin/python experiments/pr1_evaluation/run.py \
  --method 1 --matrix pr1 --duration 5 --name pr1_m1_full

# Only the cases you care about right now
.venv/bin/python experiments/pr1_evaluation/run.py \
  --method full --matrix pr1 --cases uniform hotspot limited_gw \
  --name pr1_subset --duration 5

# Method 3 vs Method 4 (gateway-only vs ISL-only awareness)
.venv/bin/python experiments/pr1_evaluation/run.py \
  --method 3 --matrix smoke --name pr1_m3_smoke
.venv/bin/python experiments/pr1_evaluation/run.py \
  --method 4 --matrix smoke --name pr1_m4_smoke
```

Outputs: `data/runs/<name>/` (`summary.csv`, `metrics_*.json`, `metrics_summary.csv`, and for the PR runner also `pr1_findings.md` / `pr1_case_summary.csv`).

Re-summarize without re-simulating (same `--method` / `--matrix` as the original run):

```bash
.venv/bin/python experiments/pr1_evaluation/run.py \
  --method full --matrix smoke --name pr1_mfull_smoke --skip-run
```

---

## 4. Preliminary evaluation findings

Mean delivered throughput from early **smoke** comparisons of Equal-RF vs full scored-rf (demand + congestion + fairness). These are preliminary, not the full PR matrix:

| Scenario | Equal-RF | Full scored-rf | Improvement |
| --- | ---: | ---: | ---: |
| Uniform | 930.5 Gbps | 998.4 Gbps | +7.3% |
| Limited gateway | 461.6 Gbps | 498.3 Gbps | +8.0% |
| Hotspot | 251.2 Gbps | 251.2 Gbps | 0% |

Preliminary experiments show that scored-rf improves delivered throughput over equal-RF in the uniform and gateway-limited scenarios. Ablation testing indicates that **congestion awareness** accounts for most of these improvements, while **fairness** has little effect on throughput in the tested scenarios. The sharp hotspot scenario shows identical results across methods, suggesting an **RF admission bottleneck** that needs further investigation.

---

## 5. Next steps for PR2

Scored-rf is **implemented** and **preliminarily validated** on smoke tests (§4). The items below are a team checklist for Progress Report 2: what still needs evaluation, what limitations to discuss, and what we can already claim.

**Already supportable (with caveats):** smoke-test throughput gains of ~7–8% over equal-RF in uniform and gateway-limited cases; congestion awareness as the main driver of those gains in the tested ablations; identical hotspot throughput across methods (cause still unverified).

**Not yet supportable:** universal superiority, fairness improving network fairness, a proven RF capacity ceiling at 251.2 Gbps, real-time feasibility, or latency improvements.

Priority legend: **Essential** for PR2 · **Important** · **Optional** (nice to have / deeper investigation)

### A. Evaluation and investigation tasks

Do **not** treat these as requests to change the algorithm for PR2 unless investigation shows a clear bug. Document findings; algorithm changes are out of scope unless the team decides otherwise.

1. **Investigate the hotspot RF bottleneck** — **Essential**
   - Determine why the sharp hotspot scenario produces identical throughput across allocation methods.
   - Check satellite visibility, interference constraints, available RF channels, and whether competing cells can actually receive additional allocations.
   - Do **not** claim that 251.2 Gbps is a proven RF capacity ceiling until the limiting constraint is verified.

2. **Expand evaluation beyond smoke tests** — **Essential**
   - Run or plan comparisons across uniform, population-weighted, sharp hotspot, wide hotspot, gateway-limited, ISL-limited, combined-congestion, and shifting-demand scenarios (see §3 matrices).
   - Keep conditions identical across methods (same duration, scales, scenarios).
   - Check whether the initial 7–8% throughput improvements remain consistent across additional snapshots and conditions.
   - This doc update does **not** run those experiments; teammates should schedule them separately.

3. **Evaluate historical fairness under resource contention** — **Important**
   - Smoke ablations suggest enabling fairness has little effect on **throughput**.
   - Test whether shifting demand and competition for limited RF channels produce meaningful differences in Jain’s fairness, starvation, or per-cell satisfaction.
   - Always distinguish **RF allocation fairness** (what **F** uses) from **estimated delivered fairness** (what report metrics use).

4. **Evaluate allocation runtime and scalability** — **Important**
   - Compare `allocation_s` across methods from saved metrics.
   - Discuss overhead of repeatedly scoring feasible cell–satellite pairs and assigning one channel at a time.
   - Do **not** claim real-time feasibility without supporting measurements.

5. **Generate PR2 evaluation figures and tables** — **Essential**
   - Prefer saved metrics (`metrics_summary.csv`, `pr1_case_summary.csv`) over hand-entered numbers.
   - Include delivered throughput, demand satisfaction, RF admission rate, delivery efficiency, stranded traffic, Jain’s fairness, starvation, and RF/ISL/gateway utilization.
   - Include method comparisons and component ablations (Methods 3–5 / `ablate-*`).
   - Explain throughput–fairness tradeoffs together; do not evaluate each metric in isolation.

6. **Investigate multipath routing limitations** — **Optional**
   - The allocator estimates downstream capacity using direct gateway and one-hop ISL paths, one estimated egress path at a time.
   - CosmoSim max-flow can use multiple paths at once, including longer multi-hop routes.
   - Look for snapshots where the allocator may **underestimate** deliverable capacity because it cannot combine capacity across paths.
   - If feasible, compare estimated egress capacity with post-routing delivery where multiple routes exist.
   - Investigation only — **not** a requirement to implement multipath-aware allocation for PR2.

7. **Analyze resource interactions** — **Important**
   - Explain how RF channel allocation, ISL capacity, gateway/feeder capacity, per-cell channel limits, and terminal demand interact.
   - Check whether gateway-only (Method 3) and ISL-focused (Method 4) awareness produce different allocation decisions.
   - Report utilization and saturation alongside throughput; high utilization is not automatically bad.

### B. Limitations and disclaimers to address in PR2

Write these up in the report even if we do not fix them before PR2. None of these alone require an algorithm change for the report.

1. **Heuristic congestion estimation** — Discuss in methodology
   - Approximate residual downstream capacity, not a global network optimization during allocation.
   - Greedy, capacity-aware RF heuristic — not an optimal multicommodity-flow or max-min-fairness solver.
   - CosmoSim max-flow is the evaluation ground truth for delivery.

2. **Single-path and limited-hop awareness** — Discuss in methodology / limitations
   - Considers direct feeder and one-hop ISL options; updates a shared **heuristic** residual pool.
   - Does not aggregate deliverable capacity across multiple simultaneous routes or longer ISL paths.
   - May overestimate congestion and avoid sats that could deliver more via multipath routing.
   - Residual updates are internal to the heuristic and do **not** modify the real routing graph.

3. **Estimated per-cell fairness** — Discuss when reporting Jain / starvation
   - Aggregate delivered throughput comes from max-flow; per-cell delivered traffic is **estimated** via proportional attribution from satellite-level delivery.
   - Jain’s fairness and delivered starvation therefore use estimates, not exact per-cell flows.
   - The score **F** itself uses historical **RF admission** satisfaction, not delivered satisfaction.

4. **Fairness component effectiveness** — Do not over-claim
   - Smoke ablations: congestion awareness drives throughput gains; fairness does not significantly change throughput in tested scenarios.
   - Do **not** claim the fairness component improves network fairness without contention-focused results (§A.3).

5. **Scenario-dependent performance** — Frame results carefully
   - ~7–8% delivered-throughput gain over equal-RF in initial uniform and gateway-limited smoke tests; sharp hotspot showed no improvement.
   - These results do **not** establish universal superiority or optimality.

6. **Short evaluation duration** — Note in evaluation setup
   - Preliminary results cover a limited number of simulated seconds.
   - Longer / more varied runs are needed for consistency, changing topology, and historical fairness effects.

7. **Workload and capacity assumptions** — Be explicit in scenario descriptions
   - Terminal layouts and artificially scaled gateway/ISL capacities are **controlled experimental conditions**.
   - Call out which scenarios are synthetic; do not present them as validated real-world traffic unless the underlying data supports that.

8. **Latency and queueing limitations** — Do not invent latency claims
   - Max-flow evaluation does not model packet-level latency or queue buildup.
   - ISL/gateway utilization and saturation are congestion **indicators**, not latency measurements.
   - Do **not** report latency improvements without a supported model or measurements.

9. **Computational complexity** — Pair with §A.4
   - Repeated candidate scoring adds overhead vs simpler RF policies.
   - Discuss runtime / scalability tradeoffs once `allocation_s` (and related) measurements are in hand.

---

More detail: [`analysis/METRICS.md`](analysis/METRICS.md), [`experiments/pr1_evaluation/README.md`](experiments/pr1_evaluation/README.md), [`PROJECT_NOTES.md`](PROJECT_NOTES.md).
