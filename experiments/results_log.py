#!/usr/bin/env python3
"""Shared team results log: results/results_log.csv (tracked in git).

Each experiment appends one row per (scenario, policy) with means over its seconds.
The file is append-only and merged with git's "union" driver (.gitattributes), so two
people pushing new rows never conflict.

  .venv/bin/python experiments/results_log.py show                                  # everything
  .venv/bin/python experiments/results_log.py show --scenario 10k-pop --policy equal  # filter
  .venv/bin/python experiments/results_log.py log data/runs/<name>                  # add an older run by hand
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "results" / "results_log.csv"
FIELDS = [
    "logged_at", "who", "experiment", "scenario", "policy", "start_s", "seconds", "isl_scale", "gw_scale",
    "requested_gbps", "admitted_gbps", "delivered_gbps", "delivered_min_gbps", "stranded_gbps",
    "stranded_pct_of_admitted", "delivered_pct_of_requested", "no_channel_cells", "rule_violations", "sec_per_run",
]
SHOW_COLUMNS = {  # column -> header in `show`
    "experiment": "experiment", "who": "who", "scenario": "scenario", "policy": "policy", "seconds": "secs",
    "isl_scale": "isl", "gw_scale": "gw", "requested_gbps": "requested", "admitted_gbps": "admitted",
    "delivered_gbps": "delivered", "stranded_gbps": "stranded", "stranded_pct_of_admitted": "stranded_%",
    "no_channel_cells": "no_ch_cells", "rule_violations": "violations",
}


def short_scenario(name: str) -> str:
    """cells_haiti_0_10000_population -> 10k-pop"""
    parts = name.replace("cells_haiti_0_", "").split("_")
    if len(parts) == 2 and parts[0].isdigit():
        n = int(parts[0])
        size = f"{n // 1000}k" if n % 1000 == 0 else str(n)
        return f"{size}-{'pop' if parts[1] == 'population' else parts[1]}"
    return name


def _who() -> str:
    name = subprocess.run(["git", "config", "user.name"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return name or os.environ.get("USER", "unknown")


def summarize(exp_dir: Path) -> list[dict]:
    manifest = json.loads((exp_dir / "manifest.json").read_text())
    with (exp_dir / "summary.csv").open() as fh:
        rows = list(csv.DictReader(fh))
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["scenario"], r["policy"])].append(r)

    out = []
    for (scenario, policy), rs in sorted(groups.items()):
        mean = lambda k: sum(float(r[k]) for r in rs) / len(rs)  # noqa: E731
        req, adm, dl, st = (mean(k) for k in ("requested_mbps", "admitted_mbps", "delivered_mbps", "stranded_mbps"))
        out.append({
            "logged_at": datetime.now().isoformat(timespec="seconds"),
            "who": _who(),
            "experiment": manifest["args"]["name"],
            "scenario": short_scenario(scenario),
            "policy": policy,
            "start_s": min(int(r["t_s"]) for r in rs),
            "seconds": len(rs),
            "isl_scale": rs[0]["isl_scale"],
            "gw_scale": rs[0]["gw_scale"],
            "requested_gbps": round(req / 1000, 1),
            "admitted_gbps": round(adm / 1000, 1),
            "delivered_gbps": round(dl / 1000, 1),
            "delivered_min_gbps": round(min(float(r["delivered_mbps"]) for r in rs) / 1000, 1),
            "stranded_gbps": round(st / 1000, 1),
            "stranded_pct_of_admitted": round(100 * st / adm, 1) if adm else 0.0,
            "delivered_pct_of_requested": round(100 * dl / req, 1) if req else 0.0,
            "no_channel_cells": round(mean("cells_with_no_channel"), 1),
            "rule_violations": int(sum(int(r.get("rule_violations", 0) or 0) for r in rs)),
            "sec_per_run": round(mean("flows_s") + mean("capacities_s"), 1),
        })
    return out


def append(rows: list[dict]) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a+", newline="") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        empty = fh.read(1) == ""
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        if empty:
            writer.writeheader()
        writer.writerows(rows)
        fcntl.flock(fh, fcntl.LOCK_UN)


def log_experiment(exp_dir: Path) -> int:
    rows = summarize(exp_dir)
    append(rows)
    return len(rows)


def show(args: argparse.Namespace) -> None:
    if not LOG.exists():
        sys.exit(f"No results yet ({LOG}).")
    with LOG.open() as fh:
        rows = list(csv.DictReader(fh))
    for key in ("experiment", "scenario", "policy", "who"):
        value = getattr(args, key)
        if value:
            rows = [r for r in rows if value.lower() in r[key].lower()]
    rows = rows[-args.last:] if args.last else rows
    cols, headers = list(SHOW_COLUMNS), list(SHOW_COLUMNS.values())
    widths = [max([len(h)] + [len(str(r[c])) for r in rows]) for h, c in zip(headers, cols)]
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    for r in rows:
        print("  ".join(str(r[c]).ljust(w) for c, w in zip(cols, widths)))
    print(f"\n{len(rows)} rows (Gbps; means over each experiment's seconds). All columns: {LOG.relative_to(ROOT)}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    lg = sub.add_parser("log", help="Append an experiment folder's results.")
    lg.add_argument("exp_dir", type=Path)
    sh = sub.add_parser("show", help="Print the results log as a table.")
    for key in ("experiment", "scenario", "policy", "who"):
        sh.add_argument(f"--{key}", default="")
    sh.add_argument("--last", type=int, default=0, help="Only the last N rows.")
    args = p.parse_args()
    if args.cmd == "log":
        print(f"Appended {log_experiment(args.exp_dir)} rows to {LOG.relative_to(ROOT)}")
    else:
        show(args)


if __name__ == "__main__":
    main()
