"""Compare PR1 runs with the same scenarios, capacity scales, and time window."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from experiments.pr1_evaluation.summarize import aggregate_rows_with_cases, load_metrics_summary
from experiments.run_experiment import SCENARIOS, terminal_file

BASELINES = {"1", "2", "greedy-coordinated", "greedy-uncoordinated"}


def comparison_rows(run_dirs: list[Path]) -> list[dict]:
    groups = {}
    reference_setup = None
    methods = set()
    for folder in run_dirs:
        manifest = json.loads((folder / "pr1_manifest.json").read_text())
        setup = (manifest["start_s"], manifest["duration_s"], manifest["cases"])
        if reference_setup is not None and setup != reference_setup:
            raise ValueError(f"Scenario matrix or time window differs in {folder}")
        reference_setup = setup
        method = manifest["method"]["key"]
        if method in methods:
            raise ValueError(f"More than one run for method {method}")
        methods.add(method)

        snapshots = load_metrics_summary(folder)
        phases = {"all": snapshots}
        shift = SCENARIOS["5k-wide-shift"]
        for row in snapshots:
            if row["scenario"] == shift:
                region = terminal_file(shift, int(row["t_s"])).rsplit("_", 1)[-1]
                phases.setdefault(region, []).append(row)
        for phase, phase_rows in phases.items():
            for row in aggregate_rows_with_cases(phase_rows, manifest["cases"], SCENARIOS):
                key = (row["case"], row["scenario"], row["isl_scale"], row["gw_scale"], phase)
                groups.setdefault(key, {})[method] = {"method": method, "phase": phase, **row}

    output = []
    for key, by_method in sorted(groups.items()):
        rows = by_method.values()
        if by_method.keys() != methods or len({r["n_seconds"] for r in rows}) != 1:
            raise ValueError(f"Missing matched snapshots for {key}")
        if not all(row["consistency_ok"] for row in rows):
            raise ValueError(f"Metrics consistency failed for {key}")
        baselines = [r for r in rows if r["method"] in BASELINES]
        best = max(baselines, key=lambda row: row["delivered_gbps"], default=None)
        for row in rows:
            row["best_baseline"] = best["method"] if best else ""
            row["delivered_delta_gbps"] = row["delivered_gbps"] - best["delivered_gbps"] if best else ""
            output.append(row)
    if not output:
        raise ValueError("No metrics to compare")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path, nargs="+", help="PR1 run folders under data/runs/.")
    args = parser.parse_args()
    try:
        rows = comparison_rows(args.runs)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    writer = csv.DictWriter(sys.stdout, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)


if __name__ == "__main__":
    main()
