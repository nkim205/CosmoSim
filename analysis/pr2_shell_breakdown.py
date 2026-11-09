#!/usr/bin/env python3
"""Per-shell admitted / delivered / stranded traffic for PR2 runs.

Why: shell 0 (satellites 0-1583) has no ISLs in starlink_5shells, so its traffic can only
leave through a directly visible ground station, at most 20.8 Gbps per satellite.
PROJECT_NOTES found that all stranding at normal capacity is shell-0 overload. This tool
measures, per run, how much each policy loads each shell and where traffic is stranded,
so we can test whether scored-rf's gains come from steering load off shell 0.

Needs the full run folders (demands.txt + flow_dict_max_flow_<t>.json), so run it in the
repo on the machine that produced the runs:

    .venv/bin/python analysis/pr2_shell_breakdown.py data/runs/pr2_*
    # -> results/pr2/shell_breakdown.csv  (one row per run x shell)
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# starlink_5shells.yaml: 72x22, 72x22, 36x20, 6x58, 28x76 satellites, numbered in order.
SHELLS = [(0, 1584), (1584, 3168), (3168, 3888), (3888, 4236), (4236, 6364)]
SAT_GS_CAP_MBPS = 20_800  # stock per-satellite downlink-to-ground limit


def shell_of(sat: int) -> int:
    for i, (lo, hi) in enumerate(SHELLS):
        if lo <= sat < hi:
            return i
    return -1


def per_sat_delivered(flow_dict: dict) -> dict[int, float]:
    """Mbps into each demand sink D<sat> (same rule as analysis/metrics.py)."""
    out: dict[int, float] = {}
    for u, vs in flow_dict.items():
        try:
            sat = int(u)
        except (TypeError, ValueError):
            continue
        f = float((vs or {}).get(f"D{sat}", 0) or 0)
        if f > 0:
            out[sat] = out.get(sat, 0.0) + f
    return out


def labels(run: Path, exp: Path) -> dict:
    parts = run.relative_to(exp).parts  # <scenario>/<policy>/islX_gwY/tN
    isl, gw = parts[2][3:].split("_gw", 1)
    return {"experiment": exp.name, "scenario": parts[0], "policy": parts[1],
            "isl_scale": float(isl), "gw_scale": float(gw), "t_s": int(parts[3][1:])}


def breakdown(run: Path, exp: Path) -> list[dict]:
    lab = labels(run, exp)
    t = lab["t_s"]
    flow_path = run / f"flow_dict_max_flow_{t}.json"
    if not (run / "demands.txt").exists() or not flow_path.exists():
        return []
    adm = np.atleast_1d(np.loadtxt(run / "demands.txt", dtype=float))
    deliv = per_sat_delivered(json.loads(flow_path.read_text()))
    rows = []
    for s, (lo, hi) in enumerate(SHELLS):
        a = adm[lo:min(hi, len(adm))]
        d = np.array([deliv.get(i, 0.0) for i in range(lo, min(hi, len(adm)))])
        rows.append({
            **lab,
            "shell": s,
            "admitted_gbps": a.sum() / 1e3,
            "delivered_gbps": d.sum() / 1e3,
            "stranded_gbps": (a.sum() - d.sum()) / 1e3,
            "sats_loaded": int((a > 0).sum()),
            "sats_over_gs_cap": int((a > SAT_GS_CAP_MBPS + 1e-6).sum()),
            "sats_stranding": int(((a - d) > 1e-3).sum()),
        })
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("experiments", nargs="+", type=Path, help="data/runs/<name> folders")
    p.add_argument("--out", type=Path, default=ROOT / "results" / "pr2" / "shell_breakdown.csv")
    args = p.parse_args()

    rows: list[dict] = []
    for exp in args.experiments:
        exp = exp if exp.is_absolute() else ROOT / exp
        runs = sorted(d.parent for d in exp.rglob("demands.txt") if d.parent.name.startswith("t"))
        n0 = len(rows)
        for run in runs:
            try:
                rows += breakdown(run, exp)
            except Exception as exc:  # one bad run must not stop the census
                print(f"  skip {run.relative_to(exp)}: {exc}")
        print(f"{exp.name}: {(len(rows) - n0) // len(SHELLS)} runs")

    if not rows:
        sys.exit("no runs with demands.txt + flow_dict found")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {args.out}")


if __name__ == "__main__":
    main()
