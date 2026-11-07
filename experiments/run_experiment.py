#!/usr/bin/env python3
"""Run beam allocation + max-flow routing for scenarios x policies x capacity scales x seconds.

For every (scenario, policy, isl scale, gateway scale, second t) this runs:
  1. workflows/generate_flows.py              (the policy assigns beams -> demands.txt)
  2. workflows/generate_capacities_scaled.py  (max-flow routing with ISL/gateway scaling)
then checks the beam mapping against the allocation rules, writes data/runs/<name>/summary.csv,
and appends a summary to the shared log results/results_log.csv.

Examples (run from the repo root):
  .venv/bin/python experiments/run_experiment.py --quick --policies baselines my-policy   # ~1 min dev check
  .venv/bin/python experiments/run_experiment.py --policies baselines --gw-scale 1 0.5    # 2 gateway levels
  .venv/bin/python experiments/run_experiment.py --scenarios 5k-wide-shift --policies equal-rf --duration 10
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import os
import pickle
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import lru_cache
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
    "baselines": ["greedy-coordinated", "greedy-uncoordinated", "equal-rf", "demand-proportional"],
    "all": RUNNABLE_POLICIES,
}
# A scenario is a terminal file (<name>.txt) or a schedule (<name>.schedule) that picks a
# terminal file per second. Both live in terminal_deployment/terminals/.
SCENARIOS = {
    "1k-uniform": "cells_haiti_0_1000_uniform",
    "1k-pop": "cells_haiti_0_1000_population",
    "10k-uniform": "cells_haiti_0_10000_uniform",
    "10k-pop": "cells_haiti_0_10000_population",
    "10k-hotspot-pap": "cells_haiti_0_10000_hotspot_pap",
    "10k-hotspot-north": "cells_haiti_0_10000_hotspot_north",
    "5k-wide-pap": "cells_haiti_0_5000_wide_pap",
    "5k-wide-north": "cells_haiti_0_5000_wide_north",
    "5k-wide-south": "cells_haiti_0_5000_wide_south",
    "5k-wide-shift": "cells_haiti_0_5000_wide_shift",
}
SCENARIO_GROUPS = {
    "all": list(SCENARIOS),
    "light": ["1k-uniform", "1k-pop"],
    "heavy": ["10k-uniform", "10k-pop"],
    "hotspot": ["10k-hotspot-pap", "10k-hotspot-north"],
    "wide": ["5k-wide-pap", "5k-wide-north", "5k-wide-south"],
    "shift": ["5k-wide-shift"],
}
QUICK_SCENARIOS, QUICK_DURATION = ["10k-uniform", "10k-pop"], 5

GRAPH_DIR = ROOT / "graph_generation" / "graphs_noglobal" / "starlink_5shells" / "haiti"
TERMINALS = ROOT / "terminal_deployment" / "terminals"
CONSTELLATION, GROUNDSTATIONS, COUNTRY, KU_GBPS = "starlink_5shells", "ground_stations_starlink", "haiti", "1.28"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--name", help="Experiment name (results in data/runs/<name>/). Default: date + policies + scales.")
    p.add_argument("--scenarios", nargs="+",
                   help=f"{', '.join(SCENARIOS)}, or groups: {', '.join(SCENARIO_GROUPS)}. Default: all.")
    p.add_argument("--policies", nargs="+", default=["baselines"],
                   help=f"{', '.join(RUNNABLE_POLICIES)}, or groups: baselines, all. Default: baselines.")
    p.add_argument("--start", type=int, default=0, help="First simulated second (default 0; snapshots exist for 0-59).")
    p.add_argument("--duration", type=int, help="Number of seconds (default 60; 5 with --quick).")
    p.add_argument("--quick", action="store_true", help=f"Fast check: {' + '.join(QUICK_SCENARIOS)}, {QUICK_DURATION} s.")
    p.add_argument("--isl-scale", type=float, nargs="+", default=[1.0],
                   help="Multiply ISL capacity. Several values = a sweep (e.g. 1 0.5 0.25).")
    p.add_argument("--gw-scale", type=float, nargs="+", default=[1.0],
                   help="Multiply gateway feeder + ground-station capacity. Several values = a sweep.")
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2), help="Parallel runs.")
    p.add_argument("--overwrite", action="store_true", help="Delete an existing experiment folder and start over.")
    p.add_argument("--resume", action="store_true",
                   help="Continue an interrupted experiment: skip runs that already finished. Same command otherwise.")
    p.add_argument("--no-log", action="store_true", help="Don't append to results/results_log.csv (scratch runs).")
    args = p.parse_args()

    typed_policies = "+".join(args.policies)
    scen = args.scenarios or (QUICK_SCENARIOS if args.quick else ["all"])
    args.scenarios = list(dict.fromkeys(SCENARIOS.get(s, s) for g in scen for s in SCENARIO_GROUPS.get(g, [g])))
    args.policies = list(dict.fromkeys(x for g in args.policies for x in POLICY_GROUPS.get(g, [g])))
    bad = [x for x in args.policies if x not in RUNNABLE_POLICIES]
    if bad:
        p.error(f"unknown policy {bad}; available: {', '.join(RUNNABLE_POLICIES)} (register new ones in "
                "spectrum_management/beam_mapping.py NEW_POLICIES)")
    if args.duration is None:
        args.duration = QUICK_DURATION if args.quick else 60
    if not args.name:
        parts = [datetime.now().strftime("%m%d-%H%M%S"), typed_policies]
        parts += ["isl" + "+".join(f"{x:g}" for x in args.isl_scale)] if args.isl_scale != [1.0] else []
        parts += ["gw" + "+".join(f"{x:g}" for x in args.gw_scale)] if args.gw_scale != [1.0] else []
        parts += ["quick"] if args.quick else []
        args.name = "_".join(parts)
    return args


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


@lru_cache(maxsize=None)
def schedule(scenario: str) -> tuple[tuple[int, str], ...] | None:
    path = TERMINALS / f"{scenario}.schedule"
    if not path.exists():
        return None
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            start, name = (x.strip() for x in line.split(","))
            rows.append((int(start), name))
    return tuple(sorted(rows))


def terminal_file(scenario: str, t: int) -> str:
    """Terminal file (without .txt) used by `scenario` at second t."""
    rows = schedule(scenario)
    if rows is None:
        return scenario
    current = [name for start, name in rows if start <= t]
    if not current:
        raise ValueError(f"{scenario}.schedule has no entry for second {t}")
    return current[-1]


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


def _run(cmd: list[str], log_path: Path, what: str) -> float:
    env = dict(os.environ, MPLCONFIGDIR=os.environ.get("MPLCONFIGDIR", "/tmp/mpl"))
    t0 = time.time()
    with log_path.open("w") as log:
        rc = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env).returncode
    if rc != 0:
        raise RuntimeError(f"{what} failed; see {log_path}")
    return time.time() - t0


def _beams_done(d: Path, t: int) -> bool:
    # flows.done marks a finished beam assignment; commands.txt marks a finished run (both steps).
    return ((d / "flows.done").exists() or (d / "commands.txt").exists()) and \
        (d / "demands.txt").exists() and (d / f"beam_assignments_{t * 10**9}.pkl").exists()


def run_unit(scenario: str, policy: str, t: int, scales: list[tuple[float, float]], base: Path, name: str) -> list[dict]:
    """One scenario/policy/second: assign beams once, then route once per capacity setting.

    Beam assignment does not depend on ISL or gateway capacity, so its output is copied to every
    capacity setting's folder instead of being recomputed. Finished folders are skipped (--resume).
    """
    tfile = terminal_file(scenario, t)
    py = sys.executable
    pkl = f"beam_assignments_{t * 10**9}.pkl"
    dirs = {(isl, gw): base / f"isl{isl:g}_gw{gw:g}" / f"t{t}" for isl, gw in scales}
    flows = [py, "workflows/generate_flows.py", None, str(GRAPH_DIR), CONSTELLATION, GROUNDSTATIONS,
             f"{tfile}.txt", COUNTRY, str(t), policy, KU_GBPS]

    src = next((d for d in dirs.values() if _beams_done(d, t)), None)
    flows_s = 0.0
    if src is None:
        src = dirs[scales[0]]
        src.mkdir(parents=True, exist_ok=True)
        flows[2] = str(src)
        flows_s = _run(flows, src / "flows.log", f"beam assignment for {short_scenario(scenario)}/{policy}/t{t}")
        (src / "flows.done").write_text("")

    terminals = {l.split(",")[0]: int(l.split(",")[1]) for l in (TERMINALS / f"{tfile}.txt").read_text().split()}
    with_terminals = [c for c, v in terminals.items() if v > 0]
    mapping = pickle.loads((src / pkl).read_bytes())
    problems = validate_mapping(mapping, visible_satellites(t, with_terminals), with_terminals)
    served = {k.rsplit("_", 1)[0] for k in mapping}
    admitted = float(np.atleast_1d(np.loadtxt(src / "demands.txt")).sum())

    rows = []
    for (isl, gw), out in dirs.items():
        out.mkdir(parents=True, exist_ok=True)
        if out != src and not _beams_done(out, t):
            for f in ("demands.txt", pkl, "flows.log"):
                shutil.copyfile(src / f, out / f)
            (out / "flows.done").write_text(f"copied from {src.relative_to(base)}\n")
        caps = [py, "workflows/generate_capacities_scaled.py", str(out), str(GRAPH_DIR), CONSTELLATION,
                GROUNDSTATIONS, str(TERMINALS / f"{tfile}.txt"), COUNTRY, str(t), policy, KU_GBPS,
                "--routing", "max_flow", "--duration", "1", "--isl-scale", str(isl), "--gw-scale", str(gw)]
        caps_s = 0.0
        if not (out / "commands.txt").exists() or not (out / f"max_flow_{t}.txt").exists():
            caps_s = _run(caps, out / "capacities.log",
                          f"routing for {short_scenario(scenario)}/{policy}/isl{isl:g}_gw{gw:g}/t{t}")
            flows[2] = str(src)
            (out / "commands.txt").write_text(" ".join(flows) + "\n" + " ".join(caps) + "\n")
        if problems:
            (out / "rule_violations.txt").write_text("\n".join(problems) + "\n")
        delivered = float((out / f"max_flow_{t}.txt").read_text().split(",")[1])
        rows.append({
            "experiment": name, "scenario": scenario, "terminal_file": tfile, "policy": policy, "t_s": t,
            "isl_scale": isl, "gw_scale": gw,
            "requested_mbps": sum(terminals.values()) * 100, "admitted_mbps": admitted,
            "delivered_mbps": delivered, "stranded_mbps": admitted - delivered,
            "channels": len(mapping),
            "cells_with_terminals": len(with_terminals),
            "cells_with_no_channel": sum(1 for c in with_terminals if c not in served),
            "rule_violations": len(problems),
            "flows_s": round(flows_s, 2), "capacities_s": round(caps_s, 2),
        })
    return rows


def main() -> None:
    args = parse_args()
    exp = ROOT / "data" / "runs" / args.name
    if args.overwrite and args.resume:
        sys.exit("Use either --overwrite (start over) or --resume (continue), not both.")
    if exp.exists() and not (args.overwrite or args.resume):
        sys.exit(f"{exp} already exists. Pick a new --name, --resume to continue it, or --overwrite to start over.")
    if exp.exists() and args.overwrite:
        shutil.rmtree(exp)
    seconds = range(args.start, args.start + args.duration)
    missing = [s for s in args.scenarios
               if not (TERMINALS / f"{s}.txt").exists() and not (TERMINALS / f"{s}.schedule").exists()]
    if not missing:
        missing = sorted({f"{terminal_file(s, t)}.txt" for s in args.scenarios for t in seconds
                          if not (TERMINALS / f"{terminal_file(s, t)}.txt").exists()})
    missing += [f"graph_{t * 10**9}.txt" for t in seconds if not (GRAPH_DIR / f"graph_{t * 10**9}.txt").exists()]
    if missing:
        sys.exit(f"Missing inputs: {missing[:5]} (scenarios: {', '.join(SCENARIOS)}; snapshots exist for seconds 0-59)")
    exp.mkdir(parents=True, exist_ok=True)

    used_files = sorted({terminal_file(s, t) for s in args.scenarios for t in seconds})
    manifest = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "command": " ".join([Path(sys.executable).name] + sys.argv),
        "git_commit": git("rev-parse", "HEAD"), "git_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "git_uncommitted_files": git("status", "--porcelain").splitlines(),
        "args": vars(args), "graph_dir": str(GRAPH_DIR.relative_to(ROOT)),
        "terminal_sha256": {f: hashlib.sha256((TERMINALS / f"{f}.txt").read_bytes()).hexdigest() for f in used_files},
        "schedules": {s: schedule(s) for s in args.scenarios if schedule(s)},
    }
    (exp / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (exp / "git_diff.patch").write_text(git("diff"))

    scales = list(dict.fromkeys(itertools.product(args.isl_scale, args.gw_scale)))
    units = [(s, p, t) for s in args.scenarios for p in args.policies for t in seconds]
    total = len(units) * len(scales)
    print(f"Running {total} runs ({len(args.scenarios)} scenarios x {len(args.policies)} policies x "
          f"{len(scales)} capacity settings x {args.duration} s) with {args.jobs} parallel jobs -> data/runs/{args.name}")
    rows, failures, t0, done = [], [], time.time(), 0
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(run_unit, s, p, t, scales, exp / s / p, args.name) for s, p, t in units]
        for fut in futures:
            try:
                rows.extend(fut.result())
            except Exception as exc:  # keep going; report at the end
                failures.append(str(exc))
            done += len(scales)
            if done % (50 * len(scales)) < len(scales) or done == total:
                print(f"  {done}/{total} done ({time.time() - t0:.0f} s)", flush=True)

    rows.sort(key=lambda r: (r["scenario"], r["policy"], -r["isl_scale"], -r["gw_scale"], r["t_s"]))
    if rows:
        with (exp / "summary.csv").open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    groups = defaultdict(list)
    for r in rows:
        groups[(r["scenario"], r["policy"], r["isl_scale"], r["gw_scale"])].append(r)
    print("\nMeans over seconds (Gbps):")
    print(f"{'scenario':18s} {'policy':21s} {'isl':>4s} {'gw':>4s} {'requested':>9s} {'admitted':>9s} "
          f"{'delivered':>9s} {'stranded':>9s} {'no-ch cells':>11s} {'violations':>10s}")
    for (s, p, isl, gw), rs in groups.items():
        m = lambda k: np.mean([r[k] for r in rs]) / 1000  # noqa: E731
        print(f"{short_scenario(s):18s} {p:21s} {isl:4g} {gw:4g} {m('requested_mbps'):9.1f} {m('admitted_mbps'):9.1f} "
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
