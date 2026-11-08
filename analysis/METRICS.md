# Evaluation metrics (Progress Report 1 alignment)

Collector: `analysis/collect_metrics.py`  
Core library: `analysis/metrics.py`  
Validation: `analysis/validate_metrics.py`

```bash
.venv/bin/python analysis/validate_metrics.py
.venv/bin/python analysis/collect_metrics.py data/runs/<name> --print
```

Outputs per snapshot: `metrics_<t>.json`, `edge_caps_max_flow_<t>.json`  
Per experiment: `metrics_summary.csv`  
Allocation timer (new runs): `allocation_runtime_s.txt`

---

## Audit table (PR1 §3 Evaluation Metrics)

| # | PR1 metric | Implementation | Formula / definition | Primary output fields | Validation | Limitations |
|---|---|---|---|---|---|---|
| 1 | **End-to-end throughput** | Post-routing max-flow delivered Mbps from `max_flow_<t>.txt` (matches `flow_dict` into `Dsat` sinks) | \(\sum\) flow into demand sinks | `throughput_delivered_mbps`, `delivered_gbps` | ✓ matches `max_flow` file; sat-delivered sum equals aggregate | Not RF-allocated (admitted) traffic |
| 2a | **Demand satisfaction (overall)** | Delivered / offered | `delivered_mbps / requested_mbps` where offered = terminals × 100 Mbps | `demand_satisfaction` (= `sat_del_offered`) | ✓ | Primary PR1 definition |
| 2b | Demand satisfaction diagnostic | Delivered / admitted | `delivered_mbps / admitted_mbps` | `demand_satisfaction_delivered_over_admitted` | ✓ | Diagnostic only — not the PR1 headline |
| 2c | **Demand satisfaction (per cell)** | Estimated delivered / offered per positive-demand cell | cell offered = \(n_{\mathrm{term}}×100\); cell delivered = \(\sum_{\mathrm{ch}} a_{c,s}·(D_s/A_s)\) | `per_cell.*.satisfaction_delivered_estimated`, `mean_cell_sat_d` | ✓ cell sum = aggregate delivered | **Estimate**: CosmoSim has no per-cell flow; labeled `per_cell_delivered_is_estimate` |
| 3a | **Jain’s fairness** | Jain over per-cell delivered/offered for all cells with positive demand | \(J=(\sum x_i)^2/(n\sum x_i^2)\), \(x_i=\hat{d}_i/o_i\) | `jain_fairness` / `jain_d` | ✓ equal→1; one-served→1/n; all-zero→1 | Uses estimated per-cell delivery |
| 3b | Allocation fairness (diagnostic) | Jain over allocated/offered | same with \(x_i=\min(1,a_i/o_i)\) | `jain_a` | ✓ | Not the PR1 headline |
| 3c | **Starvation** | Fraction of positive-demand cells with zero **estimated delivery** in the snapshot | \(n_{\mathrm{zero\ deliv}}/n_{\mathrm{active}}\) | `starvation_rate` / `starve_deliv` | ✓ zero-demand cells excluded | Uses estimated delivery |
| 3d | Zero-RF starvation (diagnostic) | Fraction with zero channels | \(n_{\mathrm{no\ ch}}/n_{\mathrm{active}}\) | `starve_alloc` | ✓ | Separate from PR1 “no service” |
| 4a | **ISL utilization** | Post-routing ISL flow / solver ISL capacity (includes `isl-scale`) | per-edge \(f/c\); aggregate \(\sum f/\sum c\) | `utilization.isl.*`, `isl_util`, `isl_frac_sat90` | ✓ scale halves cap → util doubles (unit test) | Capacities from Ka+scale graph, not scored-rf residuals |
| 4b | **Gateway utilization** | Split: **GS aggregate** `T→GS` vs **feeder** `GS→sat` | same; report separately (same traffic volume; **do not sum capacities**) | `utilization.gateway.*`, `utilization.feeder.*` | ✓ | Both include `gw-scale` |
| 4c | Congestion / saturation | Share of **active** (flow>0) edges with util ≥ 0.90 | `n_active_sat90 / n_used` | `*_frac_sat90` | ✓ | Congestion **indicator**, not queue length |
| 4d | RF utilization — cell fill | Allocated cell-channels / (active cells × 8) | labeled **cell RF fill**, not sat RF | `rf.cell_rf_fill`, `cell_rf_fill` | ✓ | Cell-slot fill only |
| 4e | RF utilization — satellite | Unique allocated `color_sat_beam` IDs / (visible sats × 8 × 4) | `rf.satellite_rf_util` | ✓ | Denominator ignores interference / per-cell visibility; documented in `rf.satellite_rf_note` |
| 5 | **Latency and congestion** | **Unsupported** for delay/queues | — | `latency.supported=false` | N/A | CosmoSim max-flow path has no delay/queue model. Use util/saturation as congestion indicators only |
| 6a | **Runtime (allocation)** | `time.perf_counter` around `beam_mapping()` in `generate_flows.py` | wall seconds | `runtime_allocation_s`, `allocation_s`, file `allocation_runtime_s.txt` | ✓ written for new runs | Missing on older runs until re-run generate_flows |
| 6b | Runtime (pipeline walls) | Subprocess timers in `run_experiment.py` | full `generate_flows` / `generate_capacities_scaled` | `flows_s`, `caps_s` | ✓ | Includes I/O; not allocation-only |

---

## Naming map (CSV ↔ JSON)

| `metrics_summary.csv` | JSON field | Role |
|---|---|---|
| `delivered_gbps` | `delivered_mbps` / 1000 | E2E throughput |
| `demand_satisfaction` | `demand_satisfaction` | PR1 overall satisfaction |
| `sat_del_admitted` | `demand_satisfaction_delivered_over_admitted` | Diagnostic |
| `jain_d` | `jain_fairness` | PR1 fairness |
| `jain_a` | `jain_allocated_over_offered` | Diagnostic |
| `starve_deliv` | `starvation_rate` | PR1 starvation |
| `starve_alloc` | `starvation_rate_zero_allocation` | Diagnostic |
| `cell_rf_fill` | `rf.cell_rf_fill` | Cell RF fill |
| `sat_rf_util` | `rf.satellite_rf_util` | Satellite RF util (approx.) |
| `gw_agg_util` / `feeder_util` / `isl_util` | `utilization.{gateway,feeder,isl}.aggregate_util` | Resource util |
| `*_frac_sat90` | `utilization.*.frac_active_saturated_090` | Saturation |
| `allocation_s` | `runtime_allocation_s` | Allocation runtime |
| `flows_s` / `caps_s` | generate_flows / routing wall times | Pipeline runtime |
| `latency_supported` | always `false` | PR1 latency N/A |

---

## What `flows_s` and `capacities_s` measure

| Timer | Scope |
|---|---|
| `allocation_s` / `allocation_runtime_s.txt` | **Only** `beam_mapping()` (equal-rf, demand-proportional, scored-rf, …) |
| `flows_s` | Entire `workflows/generate_flows.py` subprocess (load graph, visibility, allocation, write demands) |
| `caps_s` | Entire `workflows/generate_capacities_scaled.py` (Ka assignment, scale, max-flow) |

For ablation runtime comparisons, use **`allocation_s`**.

---

## Accuracy validation (raw CosmoSim outputs)

```bash
.venv/bin/python analysis/validate_metrics.py
.venv/bin/python analysis/validate_metrics.py --experiment data/runs/fairness_cmp_full
```

`analysis/consistency.py` independently recomputes offered / admitted / delivered, per-sat
admits from beam maps, Jain/starvation, and gateway/feeder/ISL util from
`flow_dict` + solver capacities. Each `metrics_<t>.json` embeds
`consistency.{ok,errors,warnings}`.

| Check | Result |
|---|---|
| Units | All internal quantities in **Mbps**; CSV Gbps = Mbps/1000 |
| `offered ≥ admitted ≥ delivered` | Enforced (tol 1e-3 Mbps) |
| Cell admits ↔ `demands.txt` | Per-sat rebuild from mapping matches exactly |
| Estimated cell delivered Σ | Equals aggregate delivered when `flow_dict` present |
| Jain / starvation | Match independent closed-form on same ratios |
| RF channels | `allocated_channels` = `len(mapping)`; `unique_sat_beam_ids` = unique values (dups flagged) |
| GW/feeder/ISL util | Post-routing directed flows ÷ dumped/rebuilt solver caps (incl. scales); dump≡rebuild |
| Missing `flow_dict` | Per-cell delivery / Jain_d / starve_deliv = **null/NaN** (not zero) |
| Missing `allocation_runtime_s.txt` | `allocation_s` = **null** + warning (not zero) |
| Latency | Unsupported (explicit) |

**Approximate (by design):** per-cell delivered / Jain_d / starve_deliv use sat delivery-ratio
attribution. Aggregate throughput and demand satisfaction do **not**.

**Backfill:** re-run `analysis/collect_metrics.py data/runs/<name>` (or `validate_metrics.py
--experiment …`) to refresh `metrics_*.json` / `metrics_summary.csv`. Existing simulation
outputs do **not** need rerunning for accuracy of throughput/util/fairness except
`allocation_s`, which requires re-running `generate_flows` to create
`allocation_runtime_s.txt`.
