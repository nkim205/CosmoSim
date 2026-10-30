#!/usr/bin/env python3
"""Run beam allocation + max-flow routing for scenarios x policies x seconds, then summarize.

For every (scenario, policy, second t) this runs:
  1. workflows/generate_flows.py              (the policy assigns beams -> demands.txt)
  2. workflows/generate_capacities_scaled.py  (max-flow routing with optional ISL/gateway scaling)
then checks the beam mapping against the allocation rules, writes data/runs/<name>/summary.csv,
and appends a summary to the shared log results/results_log.csv.

Examples (run from the repo root):
  .venv/bin/python experiments/run_experiment.py --quick --policies baselines my-policy   # ~1 min dev check
  .venv/bin/python experiments/run_experiment.py --policies baselines --gw-scale 0.5      # full 60 s, 4 scenarios
  .venv/bin/python experiments/run_experiment.py --scenarios 10k-pop --policies equal-rf --duration 10
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import pickle
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.results_log import LOG, log_experiment, short_scenario  # noqa: E402
from spectrum_management.beam_mapping import NEW_POLICIES  # noqa: E402
from spectrum_management.validate_mapping import validate_mapping  # noqa: E402

BUILTIN_POLICIES = ["greedy-coordinated", "greedy-uncoordinated"]
RUNNABLE_POLICIES = BUILTIN_POLICIES + list(NEW_POLICIES)
POLICY_GROUPS = {
    "baselines": ["greedy-coordinated", "greedy-uncoordinated", "equal-rf"],
    "all": RUNNABLE_POLICIES,
}
SCENARIOS = {
    "1k-uniform": "cells_haiti_0_1000_uniform",
    "1k-pop": "cells_haiti_0_1000_population",
    "10k-uniform": "cells_haiti_0_10000_uniform",
    "10k-pop": "cells_haiti_0_10000_population",
}
SCENARIO_GROUPS = {"all": list(SCENARIOS), "heavy": ["10k-uniform", "10k-pop"], "light": ["1k-uniform", "1k-pop"]}
QUICK_SCENARIOS, QUICK_DURATION = ["10k-uniform", "10k-pop"], 5

GRAPH_DIR = ROOT / "graph_generation" / "graphs_noglobal" / "starlink_5shells" / "haiti"
TERMINALS = ROOT / "terminal_deployment" / "terminals"
CONSTELLATION, GROUNDSTATIONS, COUNTRY, KU_GBPS = "starlink_5shells", "ground_stations_starlink", "haiti", "1.28"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--name", help="Experiment name (results in data/runs/<name>/). Default: date + policies + scales.")
    p.add_argument("--scenarios", nargs="+", help=f"{', '.join(SCENARIOS)}, or groups: all, heavy, light. Default: all.")
    p.add_argument("--policies", nargs="+", default=["baselines"],
                   help=f"{', '.join(RUNNABLE_POLICIES)}, or groups: baselines, all. Default: baselines.")
    p.add_argument("--start", type=int, default=0, help="First simulated second (default 0; snapshots exist for 0-59).")
    p.add_argument("--duration", type=int, help="Number of seconds (default 60; 5 with --quick).")
    p.add_argument("--quick", action="store_true", help=f"Fast check: {' + '.join(QUICK_SCENARIOS)}, {QUICK_DURATION} s.")
    p.add_argument("--isl-scale", type=float, default=1.0, help="Multiply ISL capacity (e.g. 0.5).")
    p.add_argument("--gw-scale", type=float, default=1.0, help="Multiply gateway feeder + ground-station capacity.")
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2), help="Parallel runs.")
    p.add_argument("--overwrite", action="store_true", help="Allow reusing an existing experiment name.")
    p.add_argument("--no-log", action="store_true", help="Don't append to results/results_log.csv (scratch runs).")
    args = p.parse_args()

    typed_policies = "+".join(args.policies)
    scen = args.scenarios or (QUICK_SCENARIOS if args.quick else ["all"])
    args.scenarios = [SCENARIOS.get(s, s) for g in scen for s in SCENARIO_GROUPS.get(g, [g])]
    args.policies = list(dict.fromkeys(x for g in args.policies for x in POLICY_GROUPS.get(g, [g])))
    bad = [x for x in args.policies if x not in RUNNABLE_POLICIES]
    if bad:
        p.error(f"unknown policy {bad}; available: {', '.join(RUNNABLE_POLICIES)} (register new ones in "
                "spectrum_management/beam_mapping.py NEW_POLICIES)")
    if args.duration is None:
        args.duration = QUICK_DURATION if args.quick else 60
    if not args.name:
        parts = [datetime.now().strftime("%m%d-%H%M%S"), typed_policies]
        parts += [f"isl{args.isl_scale:g}"] if args.isl_scale != 1 else []
        parts += [f"gw{args.gw_scale:g}"] if args.gw_scale != 1 else []
        parts += ["quick"] if args.quick else []
        args.name = "_".join(parts)
    return args


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def visible_satellites(t: int, cells: list[str]) -> dict[str, list[int]]:
    """Same candidate rule as workflows/generate_flows.py: a satellite that sees the cell and has an ISL or
    ground-station neighbour (all integer nodes in the graph are satellites or ground stations)."""
    with (GRAPH_DIR / f"graph_{t * 10**9}.txt").open("rb") as fh:
        graph = pickle.load(fh)
    return {
        cell: [s for s in graph.predecessors(cell) if any(isinstance(n, int) for n in graph.predecessors(s))]
        if cell in graph else []
        for cell in cells
    }


def run_one(scenario: str, policy: str, t: int, out: Path, args: argparse.Namespace) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    flows = [py, "workflows/generate_flows.py", str(out), str(GRAPH_DIR), CONSTELLATION, GROUNDSTATIONS,
             f"{scenario}.txt", COUNTRY, str(t), policy, KU_GBPS]
    caps = [py, "workflows/generate_capacities_scaled.py", str(out), str(GRAPH_DIR), CONSTELLATION, GROUNDSTATIONS,
            str(TERMINALS / f"{scenario}.txt"), COUNTRY, str(t), policy, KU_GBPS, "--routing", "max_flow",
            "--duration", "1", "--isl-scale", str(args.isl_scale), "--gw-scale", str(args.gw_scale)]
    env = dict(os.environ, MPLCONFIGDIR=os.environ.get("MPLCONFIGDIR", "/tmp/mpl"))
    timings = {}
    for label, cmd in (("flows", flows), ("capacities", caps)):
        t0 = time.time()
        with (out / f"{label}.log").open("w") as log:
            rc = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env).returncode
        timings[label] = time.time() - t0
        if rc != 0:
            raise RuntimeError(f"{label} failed for {short_scenario(scenario)}/{policy}/t{t}; see {out / f'{label}.log'}")
    (out / "commands.txt").write_text(" ".join(flows) + "\n" + " ".join(caps) + "\n")

    terminals = {l.split(",")[0]: int(l.split(",")[1]) for l in (TERMINALS / f"{scenario}.txt").read_text().split()}
    with_terminals = [c for c, v in terminals.items() if v > 0]
    mapping = pickle.loads((out / f"beam_assignments_{t * 10**9}.pkl").read_bytes())
    problems = validate_mapping(mapping, visible_satellites(t, with_terminals), with_terminals)
    if problems:
        (out / "rule_violations.txt").write_text("\n".join(problems) + "\n")
    served = {k.rsplit("_", 1)[0] for k in mapping}
    admitted = float(np.atleast_1d(np.loadtxt(out / "demands.txt")).sum())
    delivered = float((out / f"max_flow_{t}.txt").read_text().split(",")[1])
    return {
        "experiment": args.name, "scenario": scenario, "policy": policy, "t_s": t,
        "isl_scale": args.isl_scale, "gw_scale": args.gw_scale,
        "requested_mbps": sum(terminals.values()) * 100, "admitted_mbps": admitted,
        "delivered_mbps": delivered, "stranded_mbps": admitted - delivered,
        "channels": len(mapping),
        "cells_with_terminals": len(with_terminals),
        "cells_with_no_channel": sum(1 for c in with_terminals if c not in served),
        "rule_violations": len(problems),
        "flows_s": round(timings["flows"], 2), "capacities_s": round(timings["capacities"], 2),
    }


def main() -> None:
    args = parse_args()
    exp = ROOT / "data" / "runs" / args.name
    if exp.exists() and not args.overwrite:
        sys.exit(f"{exp} already exists. Pick a new --name or pass --overwrite.")
    missing = [s for s in args.scenarios if not (TERMINALS / f"{s}.txt").exists()]
    missing += [f"graph_{t * 10**9}.txt" for t in range(args.start, args.start + args.duration)
                if not (GRAPH_DIR / f"graph_{t * 10**9}.txt").exists()]
    if missing:
        sys.exit(f"Missing inputs: {missing[:5]} (scenarios: {', '.join(SCENARIOS)}; snapshots exist for seconds 0-59)")
    exp.mkdir(parents=True, exist_ok=True)

    manifest = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "command": " ".join([Path(sys.executable).name] + sys.argv),
        "git_commit": git("rev-parse", "HEAD"), "git_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "git_uncommitted_files": git("status", "--porcelain").splitlines(),
        "args": vars(args), "graph_dir": str(GRAPH_DIR.relative_to(ROOT)),
        "terminal_sha256": {s: hashlib.sha256((TERMINALS / f"{s}.txt").read_bytes()).hexdigest() for s in args.scenarios},
    }
    (exp / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (exp / "git_diff.patch").write_text(git("diff"))

    tasks = [(s, p, t) for s in args.scenarios for p in args.policies for t in range(args.start, args.start + args.duration)]
    print(f"Running {len(tasks)} runs ({len(args.scenarios)} scenarios x {len(args.policies)} policies x "
          f"{args.duration} s) with {args.jobs} parallel jobs -> data/runs/{args.name}")
    rows, failures, t0 = [], [], time.time()
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(run_one, s, p, t, exp / s / p / f"t{t}", args): (s, p, t) for s, p, t in tasks}
        for i, fut in enumerate(futures, 1):
            try:
                rows.append(fut.result())
            except Exception as exc:  # keep going; report at the end
                failures.append(str(exc))
            if i % 20 == 0 or i == len(tasks):
                print(f"  {i}/{len(tasks)} done ({time.time() - t0:.0f} s)")

    rows.sort(key=lambda r: (r["scenario"], r["policy"], r["t_s"]))
    if rows:
        with (exp / "summary.csv").open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    groups = defaultdict(list)
    for r in rows:
        groups[(r["scenario"], r["policy"])].append(r)
    print(f"\nMeans over seconds (Gbps), isl_scale={args.isl_scale} gw_scale={args.gw_scale}:")
    print(f"{'scenario':12s} {'policy':22s} {'requested':>9s} {'admitted':>9s} {'delivered':>9s} {'stranded':>9s} "
          f"{'no-ch cells':>11s} {'violations':>10s}")
    for (s, p), rs in groups.items():
        m = lambda k: np.mean([r[k] for r in rs]) / 1000  # noqa: E731
        print(f"{short_scenario(s):12s} {p:22s} {m('requested_mbps'):9.1f} {m('admitted_mbps'):9.1f} "
              f"{m('delivered_mbps'):9.1f} {m('stranded_mbps'):9.1f} "
              f"{np.mean([r['cells_with_no_channel'] for r in rs]):11.1f} {sum(r['rule_violations'] for r in rs):10d}")
    print(f"\nPer-second table: data/runs/{args.name}/summary.csv")

    violations = sum(r["rule_violations"] for r in rows)
    if violations:
        print(f"\nWARNING: {violations} rule violations. See rule_violations.txt in the run folders, e.g.\n  "
              + next(str(p.relative_to(ROOT)) for p in exp.rglob("rule_violations.txt")))
    if rows and not failures and not args.no_log:
        print(f"Appended {log_experiment(exp)} rows to {LOG.relative_to(ROOT)} (view: experiments/results_log.py show)")
    elif failures and not args.no_log:
        print("Not added to the shared results log because some runs failed.")
    if failures:
        print(f"\n{len(failures)} runs FAILED:")
        for f in failures[:10]:
            print("  " + f)
        sys.exit(1)


if __name__ == "__main__":
    main()
