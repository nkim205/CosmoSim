#!/usr/bin/env python3
"""PR1 evaluation pipeline — run one method across the Progress Report 1 scenario matrix.

Switch methods without changing code:

  .venv/bin/python experiments/pr1_evaluation/run.py --method 1
  .venv/bin/python experiments/pr1_evaluation/run.py --method 2
  .venv/bin/python experiments/pr1_evaluation/run.py --method full

Matrices:
  --matrix smoke   small subset (default for plumbing)
  --matrix pr1     full PR1 scenario coverage

Reuse validated metrics (``analysis/collect_metrics.py``). Does not modify scoring logic.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from analysis.collect_metrics import collect_experiment, write_summary_csv  # noqa: E402
from experiments.pr1_evaluation.methods import list_methods, resolve_method  # noqa: E402
from experiments.pr1_evaluation.scenarios import resolve_matrix, select_cases  # noqa: E402
from experiments.pr1_evaluation.summarize import (  # noqa: E402
    aggregate_rows_with_cases,
    load_metrics_summary,
    write_case_summary,
    write_findings_stub,
)
from experiments.run_experiment import SCENARIOS  # noqa: E402

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--method",
        default="1",
        help="PR1 method id to run (default: 1 = equal-rf). Use --list-methods.",
    )
    p.add_argument(
        "--list-methods",
        action="store_true",
        help="Print method registry and exit.",
    )
    p.add_argument(
        "--matrix",
        default="smoke",
        choices=["smoke", "pr1"],
        help="Scenario matrix: smoke (default) or full pr1.",
    )
    p.add_argument(
        "--cases",
        nargs="+",
        default=None,
        help="Optional subset of matrix case keys (e.g. uniform hotspot limited_gw).",
    )
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--duration", type=int, help="Seconds per case (default: 5 for smoke, through t=59 for PR1).")
    p.add_argument("--jobs", type=int, default=None)
    p.add_argument("--name", default=None, help="Experiment folder under data/runs/.")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--resume", action="store_true")
    p.add_argument(
        "--skip-run",
        action="store_true",
        help="Only (re)collect metrics + summarize an existing --name folder.",
    )
    p.add_argument(
        "--no-log",
        action="store_true",
        default=True,
        help="Do not append to shared results_log (default: true for PR1 eval).",
    )
    return p.parse_args()


def _run_case(
    *,
    method_flags: list[str],
    case,
    exp_name: str,
    start: int,
    duration: int,
    jobs: int | None,
    overwrite: bool,
    resume: bool,
    no_log: bool,
) -> None:
    cmd = [
        sys.executable,
        "experiments/run_experiment.py",
        "--name",
        exp_name,
        "--scenarios",
        *case.scenarios,
        "--isl-scale",
        *[str(x) for x in case.isl_scales],
        "--gw-scale",
        *[str(x) for x in case.gw_scales],
        "--start",
        str(start),
        "--duration",
        str(duration),
        *method_flags,
    ]
    if jobs is not None:
        cmd += ["--jobs", str(jobs)]
    if overwrite:
        cmd.append("--overwrite")
    if resume:
        cmd.append("--resume")
    if no_log:
        cmd.append("--no-log")

    print(f"\n=== Case '{case.key}' ({case.pr1_tag}) ===", flush=True)
    print(" ", " ".join(cmd), flush=True)
    # First case may create the experiment; later cases must --resume into the same folder.
    rc = subprocess.run(cmd, cwd=ROOT).returncode
    if rc != 0:
        raise SystemExit(f"run_experiment failed for case {case.key} (exit {rc})")


def main() -> None:
    args = parse_args()
    if args.list_methods:
        print("PR1 methods (pass --method <id>):\n")
        print(list_methods())
        return

    method = resolve_method(args.method)
    matrix = resolve_matrix(args.matrix)
    cases = select_cases(matrix, args.cases)
    if args.duration is None:
        args.duration = 5 if args.matrix == "smoke" else 60 - args.start
    if args.start < 0 or args.duration <= 0 or args.start + args.duration > 60:
        sys.exit("Select a positive interval within snapshots 0–59.")

    exp_name = args.name or (
        f"pr1_m{method.key}_{args.matrix}_{datetime.now().strftime('%m%d-%H%M%S')}"
    )
    exp_dir = ROOT / "data" / "runs" / exp_name

    manifest = {
        "pipeline": "pr1_evaluation",
        "created": datetime.now().isoformat(timespec="seconds"),
        "method": {
            "key": method.key,
            "title": method.title,
            "policy": method.policy,
            "beta": method.beta,
            "gamma": method.gamma,
            "use_gateway": method.use_gateway,
            "use_isl": method.use_isl,
            "pr1_section": method.pr1_section,
        },
        "matrix": args.matrix,
        "duration_s": args.duration,
        "start_s": args.start,
        "cases": [
            {
                "key": c.key,
                "title": c.title,
                "pr1_tag": c.pr1_tag,
                "scenarios": list(c.scenarios),
                "isl_scales": list(c.isl_scales),
                "gw_scales": list(c.gw_scales),
            }
            for c in cases
        ],
    }

    print(f"PR1 evaluation pipeline")
    print(f"  method  : {method.key} — {method.title} ({method.policy})")
    print(f"  matrix  : {args.matrix} ({len(cases)} cases)")
    print(f"  duration: {args.duration}s from t={args.start}")
    print(f"  output  : data/runs/{exp_name}")

    manifest_path = exp_dir / "pr1_manifest.json"
    if (args.resume or args.skip_run) and manifest_path.exists():
        saved = json.loads(manifest_path.read_text())
        if any(saved[key] != manifest[key] for key in ("method", "cases", "start_s", "duration_s")):
            sys.exit("Method, cases or interval differ from the saved manifest. Use the original settings or a new name.")

    if not args.skip_run:
        # Case 0 creates data/runs/<name>/; later cases --resume into it.
        for i, case in enumerate(cases):
            _run_case(
                method_flags=method.run_experiment_flags(),
                case=case,
                exp_name=exp_name,
                start=args.start,
                duration=args.duration,
                jobs=args.jobs,
                overwrite=(args.overwrite and i == 0),
                resume=(i > 0) or (args.resume and i == 0),
                no_log=args.no_log,
            )
        exp_dir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2))
    elif not exp_dir.exists():
        sys.exit(f"--skip-run but missing {exp_dir}")

    print("\nCollecting validated metrics…", flush=True)
    mrows = collect_experiment(exp_dir, rebuild_caps=True)
    write_summary_csv(exp_dir / "metrics_summary.csv", mrows)
    n_bad = sum(1 for r in mrows if r.get("consistency_ok") is False)
    print(f"  metrics_summary.csv: {len(mrows)} rows; consistency failures: {n_bad}")
    seconds = range(args.start, args.start + args.duration)
    expected = {
        (SCENARIOS[scenario], isl, gw, t)
        for case in cases
        for scenario, isl, gw, t in product(case.scenarios, case.isl_scales, case.gw_scales, seconds)
    }
    actual = Counter(
        (row["scenario"], float(row["isl_scale"]), float(row["gw_scale"]), row["t_s"])
        for row in mrows if row["policy"] == method.policy
    )
    if actual != Counter(expected) or len(mrows) != len(expected):
        missing = sorted(expected - actual.keys())
        sys.exit(f"Incomplete or unexpected PR1 coverage. First missing snapshots: {missing[:3]}")

    case_rows = aggregate_rows_with_cases(
        load_metrics_summary(exp_dir) or [{k: str(v) for k, v in r.items()} for r in mrows],
        manifest["cases"],
        SCENARIOS,
    )
    write_case_summary(exp_dir / "pr1_case_summary.csv", case_rows)
    write_findings_stub(
        exp_dir / "pr1_findings.md",
        method_key=method.key,
        method_title=method.title,
        exp_dir=exp_dir,
        case_rows=case_rows,
    )
    print(f"  pr1_case_summary.csv + pr1_findings.md written")

    from experiments.pr1_evaluation.summarize import enrich_breakdown

    print("\nDelivered vs stranded (Gbps, means):")
    print(
        f"{'case':12s} {'scenario':28s} {'gw':>5s} {'del':>8s} {'str':>8s} "
        f"{'adm_rate':>8s} {'del_eff':>8s} {'demand_sat':>10s}"
    )
    for r in case_rows:
        r = enrich_breakdown(dict(r))
        print(
            f"{str(r['case']):12s} {str(r['scenario'])[:28]:28s} {float(r['gw_scale']):5.2g} "
            f"{float(r['delivered_gbps']):8.1f} {float(r['stranded_gbps']):8.1f} "
            f"{100 * float(r['rf_admission_rate']):7.1f}% "
            f"{100 * float(r['delivery_efficiency']):7.1f}% "
            f"{100 * float(r['demand_sat']):9.1f}%"
        )

    if n_bad:
        sys.exit(f"{n_bad} runs failed consistency checks — see metrics_*.json")


if __name__ == "__main__":
    main()
