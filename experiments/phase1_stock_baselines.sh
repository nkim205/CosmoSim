#!/usr/bin/env bash
# Stock CosmoSim baselines (greedy-coordinated / greedy-uncoordinated, max_flow) for Haiti.
#
# Modes:
#   stock    : generate_flows at t=START, then generate_capacities over the whole window.
#              Demand is fixed across snapshots, as in the stock workflow.
#   snapshot : generate_flows + generate_capacities (--duration 1) separately for every t,
#              each in its own directory, so demand follows the moving constellation.
#
# Usage: experiments/phase1_stock_baselines.sh <stock|snapshot> [START] [DURATION] [JOBS]
set -euo pipefail

MODE=${1:?mode: stock|snapshot}
START=${2:-0}
DURATION=${3:-60}
JOBS=${4:-10}

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
export MPLCONFIGDIR=${MPLCONFIGDIR:-/tmp/mpl}

CONSTELLATION=starlink_5shells
GROUNDSTATIONS=ground_stations_starlink
COUNTRY=haiti
KU=1.28
GRAPH_DIR=graph_generation/graphs_noglobal/$CONSTELLATION/$COUNTRY
SCENARIOS=(cells_haiti_0_1000_uniform cells_haiti_0_1000_population cells_haiti_0_10000_uniform cells_haiti_0_10000_population)
POLICIES=(greedy-coordinated greedy-uncoordinated)

OUT_ROOT=data/phase1/$MODE/start${START}_dur${DURATION}
mkdir -p "$OUT_ROOT"
MANIFEST=$OUT_ROOT/manifest.txt
{
  echo "date: $(date -Is)"
  echo "git_commit: $(git rev-parse HEAD)"
  echo "git_dirty_files: $(git status --porcelain | wc -l)"
  echo "mode: $MODE start: $START duration: $DURATION ku_gbps: $KU"
  echo "graph_dir: $GRAPH_DIR (generated with --skip-global-cells)"
  echo "terminal_sha256:"
  for s in "${SCENARIOS[@]}"; do sha256sum "terminal_deployment/terminals/$s.txt"; done
} > "$MANIFEST"
git diff > "$OUT_ROOT/git_diff.patch"

run_pair() {
  # $1 out_dir  $2 scenario  $3 policy  $4 flow_time  $5 duration
  local out=$1 scen=$2 pol=$3 t=$4 dur=$5
  mkdir -p "$out"
  local flows_cmd="$PY workflows/generate_flows.py $out $GRAPH_DIR $CONSTELLATION $GROUNDSTATIONS $scen.txt $COUNTRY $t $pol $KU"
  local caps_cmd="$PY workflows/generate_capacities.py $out $GRAPH_DIR $CONSTELLATION $GROUNDSTATIONS terminal_deployment/terminals/$scen.txt $COUNTRY $t $pol $KU --routing max_flow --duration $dur"
  local t0=$(date +%s.%N)
  $flows_cmd > "$out/generate_flows.log" 2>&1
  local t1=$(date +%s.%N)
  $caps_cmd > "$out/generate_capacities.log" 2>&1
  local t2=$(date +%s.%N)
  printf '%s\n%s\nflows_s=%.2f capacities_s=%.2f\n' "$flows_cmd" "$caps_cmd" \
    "$(echo "$t1 - $t0" | bc)" "$(echo "$t2 - $t1" | bc)" > "$out/commands.txt"
}
export -f run_pair
export PY GRAPH_DIR CONSTELLATION GROUNDSTATIONS COUNTRY KU

if [[ $MODE == stock ]]; then
  for s in "${SCENARIOS[@]}"; do for p in "${POLICIES[@]}"; do
    echo "$OUT_ROOT/$s/$p $s $p $START $DURATION"
  done; done
elif [[ $MODE == snapshot ]]; then
  for s in "${SCENARIOS[@]}"; do for p in "${POLICIES[@]}"; do
    for ((t = START; t < START + DURATION; t++)); do
      echo "$OUT_ROOT/$s/$p/t$t $s $p $t 1"
    done
  done; done
else
  echo "unknown mode $MODE" >&2; exit 1
fi | xargs -P "$JOBS" -L 1 bash -c 'run_pair "$@" || echo "FAIL $*"' _

echo "done: $OUT_ROOT"
