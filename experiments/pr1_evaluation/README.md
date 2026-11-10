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
| `greedy-coordinated`, `greedy-uncoordinated` | Stock references | Original CosmoSim policies |

Methods 3–5 and `full` share the same `scored-rf` loop; only flags/weights change. See [`ALGORITHM_OVERVIEW.md`](../../ALGORITHM_OVERVIEW.md).

## Scenario matrices

- `--matrix smoke` uses five seconds by default.
- `--matrix pr1` uses all 60 Haiti snapshots by default, including the hotspot shifts at seconds 20 and 40. It covers light and heavy demand, population-weighted and hotspot demand, multiple gateway and ISL scales, and combined constraints.

Start a fresh scored-rf run for this version. The allocator now uses estimated delivery from the previous snapshot for fairness, and the ISL-only ablation scores ISL capacity with gateway reachability. Prior scored-rf results used different scoring inputs.

## Compare matched runs

```bash
for method in 1 2 3 4 5 full greedy-coordinated greedy-uncoordinated; do
  .venv/bin/python -m experiments.pr1_evaluation.run \
    --method "$method" --matrix pr1 --name "pr1-$method" || break
done
.venv/bin/python -m experiments.pr1_evaluation.compare \
  data/runs/pr1-{1,2,3,4,5,full,greedy-coordinated,greedy-uncoordinated} > data/pr1-comparison.csv
```

The CSV includes throughput relative to the highest-throughput supplied baseline, satisfaction, Jain fairness, starvation, utilization, and allocation runtime. Shifting-hotspot rows include both the full interval and separate results for each region. A full comparison can take hours. Use identical `--cases` and `--duration` across methods for a shorter comparison.

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
.venv/bin/python experiments/pr1_evaluation/run.py --method 1 --matrix pr1 --name <folder> --skip-run
```
