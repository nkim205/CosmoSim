#!/usr/bin/env python3
"""Allocation-fairness metrics from a finished experiment folder.

Reports mean delivered / stranded / no-channel cells, plus Jain's index over
per-cell RF allocation satisfaction (allocated/offered), which is what scored-rf
history tracks — not post-routing delivered/offered.

  .venv/bin/python experiments/analyze_allocation_fairness.py data/runs/<name>
"""

from __future__ import annotations

import argparse
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spectrum_management.scored_rf import _allocated_mbps, _offered_mbps  # noqa: E402
from experiments.run_experiment import SCENARIOS, short_scenario  # noqa: E402

TERMINALS = ROOT / "terminal_deployment" / "terminals"


def jain(values: list[float]) -> float:
    xs = np.asarray(values, dtype=float)
    if xs.size == 0:
        return float("nan")
    s = xs.sum()
    if s <= 0:
        return float("nan")
    return float((s * s) / (xs.size * (xs * xs).sum()))


def cell_alloc_satisfaction(mapping: dict, terminals: dict[str, int]) -> dict[str, float]:
    channels: dict[str, int] = defaultdict(int)
    for key in mapping:
        channels[key.rsplit("_", 1)[0]] += 1
    out = {}
    for cell, n in terminals.items():
        if n <= 0:
            continue
        offered = _offered_mbps(n)
        alloc = _allocated_mbps(n, channels.get(cell, 0))
        out[cell] = min(1.0, alloc / offered) if offered > 0 else 1.0
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("experiment", type=Path, help="data/runs/<name> folder")
    args = p.parse_args()
    exp = args.experiment if args.experiment.is_absolute() else ROOT / args.experiment
    if not exp.exists():
        sys.exit(f"missing {exp}")

    scen_dirs = {v: k for k, v in SCENARIOS.items()}
    rows = []
    for demands in exp.rglob("demands.txt"):
        out = demands.parent
        if not out.name.startswith("t"):
            continue
        t = int(out.name[1:])
        scale = out.parent.name
        policy = out.parent.parent.name
        scenario_dir = out.parent.parent.parent.name
        scenario = scen_dirs.get(scenario_dir, scenario_dir)
        if not scale.startswith("isl"):
            continue
        isl_s, gw_s = scale[3:].split("_gw")
        isl, gw = float(isl_s), float(gw_s)
        mf = out / f"max_flow_{t}.txt"
        pkl = out / f"beam_assignments_{t * 10**9}.pkl"
        if not mf.exists() or not pkl.exists():
            continue
        # terminal file name is scenario_dir for non-schedules
        tfile = scenario_dir
        terms = {
            a: int(b)
            for a, b in (
                line.split(",")
                for line in (TERMINALS / f"{tfile}.txt").read_text().split()
            )
        }
        mapping = pickle.loads(pkl.read_bytes())
        sat = cell_alloc_satisfaction(mapping, terms)
        with_terms = [c for c, n in terms.items() if n > 0]
        served = {k.rsplit("_", 1)[0] for k in mapping}
        admitted = float(np.atleast_1d(np.loadtxt(demands)).sum())
        delivered = float(mf.read_text().split(",")[1])
        rows.append({
            "scenario": scenario,
            "policy": policy,
            "isl": isl,
            "gw": gw,
            "t": t,
            "requested": sum(terms.values()) * 100.0,
            "admitted": admitted,
            "delivered": delivered,
            "stranded": admitted - delivered,
            "no_ch": sum(1 for c in with_terms if c not in served),
            "starvation_rate": sum(1 for c in with_terms if c not in served) / max(1, len(with_terms)),
            "alloc_jain": jain(list(sat.values())),
            "alloc_sat_mean": float(np.mean(list(sat.values()))),
            "alloc_sat_min": float(np.min(list(sat.values()))),
        })

    groups = defaultdict(list)
    for r in rows:
        groups[(r["scenario"], r["policy"], r["isl"], r["gw"])].append(r)

    print(f"{'scenario':12s} {'policy':22s} {'gw':>5s} {'del':>8s} {'str':>8s} {'adm%':>7s} "
          f"{'del%':>7s} {'no_ch':>6s} {'starve':>7s} {'Jain_a':>7s} {'sat_min':>7s}")
    for (scen, pol, isl, gw), rs in sorted(groups.items()):
        if abs(isl - 1.0) > 1e-9:
            continue
        m = lambda k: float(np.mean([r[k] for r in rs]))  # noqa: E731
        req, adm, deliv = m("requested"), m("admitted"), m("delivered")
        print(
            f"{short_scenario(scen):12s} {pol:22s} {gw:5g} {deliv/1000:8.1f} {m('stranded')/1000:8.1f} "
            f"{100*adm/req:6.1f}% {100*deliv/req:6.1f}% {m('no_ch'):6.1f} {100*m('starvation_rate'):6.1f}% "
            f"{m('alloc_jain'):7.3f} {m('alloc_sat_min'):7.3f}"
        )
    print("\nNote: Jain_a / sat_min are over RF allocated/offered per cell (allocation fairness),")
    print("not delivered/offered after routing.")


if __name__ == "__main__":
    main()
