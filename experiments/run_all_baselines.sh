#!/usr/bin/env bash
# Recompute every baseline row the evaluation team compares against (about 2 hours on 12 cores).
# Results: experiments baselines_gw_sweep and baselines_isl_sweep in results/results_log.csv.
# Extra arguments go to both runs: --resume continues after an interruption, --overwrite starts over,
# --jobs N sets parallel runs.
set -euo pipefail
cd "$(dirname "$0")/.."

.venv/bin/python experiments/run_experiment.py --name baselines_gw_sweep --policies baselines \
    --scenarios all --gw-scale 1 0.75 0.5 0.25 "$@"

# ISL capacity never limited Haiti in earlier tests (x0.5: no change), so one strong cut is enough.
.venv/bin/python experiments/run_experiment.py --name baselines_isl_sweep --policies baselines \
    --scenarios heavy wide shift --isl-scale 0.1 "$@"
