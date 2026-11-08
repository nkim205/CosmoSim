# PR1 evaluation pipeline

Runs one Progress Report 1 **method** across the PR1 **test-scenario matrix**, then
collects the validated evaluation metrics (`analysis/metrics.py`).

## Switch methods

```bash
.venv/bin/python experiments/pr1_evaluation/run.py --list-methods

# Method 1 — Equal RF (default)
.venv/bin/python experiments/pr1_evaluation/run.py --method 1 --matrix smoke

# Later methods (same pipeline)
.venv/bin/python experiments/pr1_evaluation/run.py --method 2 --matrix pr1 --duration 5
.venv/bin/python experiments/pr1_evaluation/run.py --method 3 --matrix pr1
.venv/bin/python experiments/pr1_evaluation/run.py --method full --matrix pr1
```

| Id | Method | CosmoSim |
|---|---|---|
| `1` | Equal RF | `equal-rf` |
| `2` | Demand-proportional | `demand-proportional` |
| `3` | Demand- and gateway-aware RF **without ISL** awareness | `scored-rf` gateway on, ISL off |
| `4` | Demand- and ISL-aware RF **without gateway** awareness | `scored-rf` ISL on, gateway off |
| `5` | Full without fairness | `scored-rf` β=0 |
| `full` | Proposed scored-rf | `scored-rf` β=0.3 γ=0.2 |

Methods 3–5 and `full` share the same `scored-rf` loop; only flags/weights change. See [`ALGORITHM_OVERVIEW.md`](../../ALGORITHM_OVERVIEW.md).

## Scenario matrices

- `--matrix smoke` — uniform + pap hotspot + limited GW (fast)
- `--matrix pr1` — full PR1 coverage (uniform, hotspot, wide, shift, limited GW/ISL, combined)

## Outputs (`data/runs/<name>/`)

| File | Contents |
|---|---|
| `pr1_manifest.json` | Method + cases + duration |
| `metrics_summary.csv` | Per-snapshot validated metrics |
| `pr1_case_summary.csv` | Means over seconds per case |
| `pr1_findings.md` | Delivered vs stranded table |
| run tree | Same as `run_experiment` (`summary.csv`, `metrics_*.json`, …) |

Re-summarize only:

```bash
.venv/bin/python experiments/pr1_evaluation/run.py --method 1 --name <folder> --skip-run
```
