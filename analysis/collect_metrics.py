#!/usr/bin/env python3
"""Collect Stage-1 evaluation metrics for every finished run under an experiment.

Writes:
  <run>/metrics_<t>.json          full metrics (incl. per-cell)
  <experiment>/metrics_summary.csv  one row per run

Usage:
  .venv/bin/python analysis/collect_metrics.py data/runs/<name>
  .venv/bin/python analysis/collect_metrics.py data/runs/<name> --print
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.metrics import (  # noqa: E402
    compute_run_metrics,
    flat_summary_row,
    write_run_metrics,
)


def _infer_labels(run_dir: Path, exp: Path) -> dict:
    """Expect .../<scenario>/<policy>/islX_gwY/tN."""
    rel = run_dir.relative_to(exp)
    parts = rel.parts
    out = {"scenario": "", "policy": "", "isl_scale": "", "gw_scale": ""}
    if len(parts) >= 4:
        out["scenario"] = parts[0]
        out["policy"] = parts[1]
        scale = parts[2]
        if scale.startswith("isl") and "_gw" in scale:
            isl_s, gw_s = scale[3:].split("_gw", 1)
            out["isl_scale"] = isl_s
            out["gw_scale"] = gw_s
    return out


def collect_experiment(exp: Path, *, rebuild_caps: bool = True) -> list[dict]:
    rows: list[dict] = []
    for demands in sorted(exp.rglob("demands.txt")):
        run = demands.parent
        if not run.name.startswith("t"):
            continue
        mf = list(run.glob("max_flow_*.txt"))
        if not mf:
            continue
        labels = _infer_labels(run, exp)
        metrics = compute_run_metrics(run, rebuild_caps=rebuild_caps)
        write_run_metrics(run, metrics)
        rows.append(flat_summary_row(metrics, experiment=exp.name, **labels))
    return rows


def write_summary_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("experiment", type=Path, help="data/runs/<name>")
    p.add_argument("--print", action="store_true", help="Print a compact table")
    p.add_argument(
        "--no-rebuild-caps",
        action="store_true",
        help="Skip gateway/ISL util if edge_caps_*.json is missing",
    )
    args = p.parse_args()
    exp = args.experiment if args.experiment.is_absolute() else ROOT / args.experiment
    if not exp.exists():
        sys.exit(f"missing {exp}")

    rows = collect_experiment(exp, rebuild_caps=not args.no_rebuild_caps)
    out = exp / "metrics_summary.csv"
    write_summary_csv(out, rows)
    n_bad = sum(1 for r in rows if r.get("consistency_ok") is False)
    n_warn = sum(int(r.get("consistency_warnings") or 0) for r in rows)
    print(f"Wrote {len(rows)} rows -> {out}")
    if n_bad:
        print(f"WARNING: {n_bad}/{len(rows)} runs failed consistency checks (see metrics_*.json)")
    elif n_warn:
        print(f"Consistency OK with {n_warn} total warnings (often missing allocation_runtime_s.txt)")

    if args.print and rows:
        hdr = (
            f"{'scenario':22s} {'policy':22s} {'gw':>5s} {'del':>8s} {'sat%':>6s} "
            f"{'Jain_d':>7s} {'starve':>7s} {'gwU':>6s} {'isl90':>6s} {'cRF':>6s}"
        )
        print(hdr)
        for r in rows:
            print(
                f"{str(r.get('scenario','')):22s} {str(r.get('policy','')):22s} "
                f"{float(r.get('gw_scale') or 0):5.2g} "
                f"{float(r['delivered_gbps']):8.1f} "
                f"{float(r['demand_satisfaction'] or float('nan')):6.3f} "
                f"{float(r['jain_d']):7.3f} "
                f"{float(r['starve_deliv']):7.3f} "
                f"{float(r['gw_agg_util'] or float('nan')):6.3f} "
                f"{float(r['isl_frac_sat90'] or float('nan')):6.3f} "
                f"{float(r['cell_rf_fill'] or float('nan')):6.3f}"
            )


if __name__ == "__main__":
    main()
