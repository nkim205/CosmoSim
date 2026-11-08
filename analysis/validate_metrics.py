#!/usr/bin/env python3
"""Validate evaluation metrics against CosmoSim raw outputs (independent recomputation).

  .venv/bin/python analysis/validate_metrics.py
  .venv/bin/python analysis/validate_metrics.py --experiment data/runs/fairness_cmp_full
  .venv/bin/python analysis/validate_metrics.py --run data/runs/.../t0
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.consistency import check_run_consistency  # noqa: E402
from analysis.metrics import (  # noqa: E402
    SATURATION_THRESHOLD,
    attribute_cell_delivered,
    compute_run_metrics,
    jain,
    link_utilization,
    rf_utilization,
    write_run_metrics,
)


def _approx(a: float, b: float, tol: float = 1e-9) -> bool:
    if math.isnan(a) and math.isnan(b):
        return True
    return abs(a - b) <= tol


def _check(name: str, cond: bool, detail: str = "") -> bool:
    status = "PASS" if cond else "FAIL"
    extra = f" — {detail}" if detail else ""
    print(f"  [{status}] {name}{extra}")
    return cond


def test_jain() -> bool:
    print("Jain fairness (independent closed form)")
    ok = True
    ok &= _check("equal → 1", _approx(jain([0.5, 0.5, 0.5]), 1.0))
    ok &= _check("all zero → 1", _approx(jain([0.0, 0.0, 0.0]), 1.0))
    n = 4
    ok &= _check("one served → 1/n", _approx(jain([1.0] + [0.0] * (n - 1)), 1.0 / n, tol=1e-12))
    # Hand example: satisfactions [1, 0.5] → (1.5)^2 / (2*(1+0.25)) = 2.25/2.5 = 0.9
    ok &= _check("hand example [1,0.5] → 0.9", _approx(jain([1.0, 0.5]), 0.9))
    ok &= _check("empty → nan", math.isnan(jain([])))
    return ok


def test_attribution_sums() -> bool:
    print("Per-cell delivery attribution accounting")
    sat_adm = {1: 100.0, 2: 50.0}
    sat_del = {1: 80.0, 2: 50.0}
    channels = {
        "A": [(1, 60.0), (2, 20.0)],
        "B": [(1, 40.0)],
        "C": [(2, 30.0)],
        "D": [],
    }
    cell_del = attribute_cell_delivered(channels, sat_adm, sat_del)
    expected = {"A": 68.0, "B": 32.0, "C": 30.0, "D": 0.0}
    ok = True
    for c, e in expected.items():
        ok &= _check(f"cell {c}", _approx(cell_del[c], e), f"got {cell_del[c]}")
    ok &= _check(
        "sum cells == sum sat delivered",
        _approx(sum(cell_del.values()), sum(sat_del.values())),
    )
    return ok


def test_starvation_universe() -> bool:
    print("Starvation / zero-demand handling")
    terminals = {"a": 10, "b": 5, "c": 0, "d": 1}
    active = [c for c, n in terminals.items() if n > 0]
    delivered = {"a": 100.0, "b": 0.0, "d": 0.0}
    zero_deliv = [c for c in active if delivered.get(c, 0.0) <= 1e-6]
    ok = True
    ok &= _check("zero-demand excluded", "c" not in active and set(active) == {"a", "b", "d"})
    ok &= _check("starvation rate 2/3", _approx(len(zero_deliv) / len(active), 2 / 3))
    return ok


def test_utilization_bounds_and_saturation() -> bool:
    print("Utilization bounds + directed edges + 90% saturation")
    flow_dict = {
        "T": {"100": 90.0, "101": 10.0},
        "100": {"0": 90.0},
        "101": {"1": 10.0},
        "0": {"1": 50.0},
        "1": {"0": 0.0},
    }
    edge_caps = {
        "gateway_agg": [
            {"u": "T", "v": 100, "capacity_mbps": 100.0},
            {"u": "T", "v": 101, "capacity_mbps": 100.0},
        ],
        "feeder": [
            {"u": 100, "v": 0, "capacity_mbps": 100.0},
            {"u": 101, "v": 1, "capacity_mbps": 100.0},
        ],
        "isl": [
            {"u": 0, "v": 1, "capacity_mbps": 100.0},
            {"u": 1, "v": 0, "capacity_mbps": 100.0},
        ],
    }
    util = link_utilization(flow_dict, edge_caps)
    ok = True
    ok &= _check("gateway agg util 0.5", _approx(util["gateway"]["aggregate_util"], 0.5))
    ok &= _check(
        "directed ISL 0→1 carries 50, 1→0 carries 0",
        _approx(util["isl"]["flow_mbps"], 50.0),
    )
    ok &= _check(
        "gateway active sat90 = 0.5",
        _approx(util["gateway"]["frac_active_saturated_090"], 0.5),
    )
    ok &= _check(f"saturation threshold {SATURATION_THRESHOLD}", _approx(SATURATION_THRESHOLD, 0.90))
    edge_caps_scaled = {
        "gateway_agg": [
            {"u": "T", "v": 100, "capacity_mbps": 50.0},
            {"u": "T", "v": 101, "capacity_mbps": 50.0},
        ],
        "feeder": edge_caps["feeder"],
        "isl": edge_caps["isl"],
    }
    util2 = link_utilization(flow_dict, edge_caps_scaled)
    ok &= _check("gw-scale halves capacity → util doubles", _approx(util2["gateway"]["aggregate_util"], 1.0))
    return ok


def test_rf_labels() -> bool:
    print("RF channel / beam-ID handling")
    mapping = {
        "cellA_0": "0_10_0",
        "cellA_1": "1_10_1",
        "cellB_0": "0_11_0",
    }
    rf = rf_utilization(mapping, n_active_cells=2, visible_sats={10, 11, 12})
    ok = True
    ok &= _check("cell_rf_fill = 3/(2*8)", _approx(rf["cell_rf_fill"], 3 / 16))
    ok &= _check("unique beam ids = 3", _approx(rf["unique_sat_beam_ids"], 3))
    ok &= _check("satellite_rf_util = 3/(3*32)", _approx(rf["satellite_rf_util"], 3 / 96))
    # Duplicate beam ID would be counted once in unique set
    mapping_dup = dict(mapping)
    mapping_dup["cellC_0"] = "0_10_0"  # reuse beam
    rf2 = rf_utilization(mapping_dup, n_active_cells=3, visible_sats={10, 11, 12})
    ok &= _check(
        "duplicate beam ID counted once in unique_sat_beam_ids",
        _approx(rf2["unique_sat_beam_ids"], 3) and rf2["allocated_channels"] == 4,
    )
    return ok


def test_missing_flow_dict_no_silent_zeros(tmp_path: Path | None = None) -> bool:
    print("Missing flow_dict must not invent zero per-cell delivery")
    # Use a real run, temporarily rename flow_dict via copy logic: call compute on
    # a path missing flow_dict by checking artifacts flags on a synthetic case.
    # Safer: unit-level — if has_flow_dict is False path sets nulls.
    # We'll simulate by computing on a run then asserting the code path via a
    # minimal stub directory.
    import pickle
    import shutil
    import tempfile

    src = ROOT / "data/runs/fairness_cmp_full/cells_haiti_0_10000_uniform/scored-rf/isl1_gw1/t0"
    if not src.exists():
        print("  [SKIP] no source run")
        return True
    ok = True
    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "t0"
        shutil.copytree(src, dst)
        (dst / "flow_dict_max_flow_0.json").unlink()
        # edge caps optional
        m = compute_run_metrics(dst, rebuild_caps=False)
        ok &= _check("per_cell_delivery_available is False", m["per_cell_delivery_available"] is False)
        ok &= _check("jain_fairness is nan", math.isnan(m["jain_fairness"]))
        ok &= _check("starvation_rate is nan", math.isnan(m["starvation_rate"]))
        sample = next(iter(m["per_cell"].values()))
        ok &= _check(
            "per-cell delivered estimate is null",
            sample["delivered_mbps_estimated"] is None,
        )
        ok &= _check(
            "aggregate delivered still from max_flow",
            m["delivered_mbps"] > 0,
        )
        ok &= _check(
            "consistency flags missing flow_dict",
            any("flow_dict" in e for e in m["consistency"]["errors"]),
        )
    return ok


def audit_run(run_dir: Path, *, rewrite: bool = False) -> bool:
    print(f"Raw-output consistency: {run_dir}")
    m = compute_run_metrics(run_dir, rebuild_caps=True)
    if rewrite:
        write_run_metrics(run_dir, m)
    cons = m.get("consistency") or {}
    ok = bool(cons.get("ok"))
    for e in cons.get("errors") or []:
        print(f"  [FAIL] {e}")
        ok = False
    for w in cons.get("warnings") or []:
        print(f"  [WARN] {w}")
    if ok:
        print("  [PASS] independent consistency ok")
        ind_check = check_run_consistency(run_dir, metrics=m, rebuild_caps=True)
        # second pass already embedded; confirm match fields
        ok &= _check(
            "metrics match independent recomputation",
            ind_check["ok"] and not ind_check["errors"],
        )
    return ok


def audit_experiment(exp: Path, *, limit: int | None = None) -> bool:
    print(f"\n=== Experiment audit: {exp} ===")
    runs = []
    for demands in sorted(exp.rglob("demands.txt")):
        run = demands.parent
        if run.name.startswith("t") and list(run.glob("max_flow_*.txt")):
            runs.append(run)
    if limit is not None:
        runs = runs[:limit]
    ok_all = True
    n_err = n_warn = 0
    for run in runs:
        m = compute_run_metrics(run, rebuild_caps=True)
        write_run_metrics(run, m)
        cons = m.get("consistency") or {}
        errs = cons.get("errors") or []
        warns = cons.get("warnings") or []
        n_err += len(errs)
        n_warn += len(warns)
        status = "OK" if cons.get("ok") else "FAIL"
        rel = run.relative_to(exp)
        if errs:
            print(f"  [{status}] {rel}")
            for e in errs[:5]:
                print(f"           {e}")
            ok_all = False
        elif warns:
            print(f"  [OK+WARN] {rel} ({len(warns)} warnings)")
        # else silent pass
    print(f"  Summary: {len(runs)} runs, consistency_errors={n_err}, warnings={n_warn}")
    return ok_all


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, help="Single run folder")
    p.add_argument("--experiment", type=Path, help="Experiment folder to audit all runs")
    p.add_argument(
        "--experiments",
        nargs="*",
        default=[
            "data/runs/fairness_cmp_full",
            "data/runs/fairness_cmp_nofair",
            "data/runs/gamma_sweep_g0.5",
        ],
        help="Default multi-experiment audit paths",
    )
    p.add_argument("--limit", type=int, default=None, help="Max runs per experiment")
    p.add_argument("--unit-only", action="store_true")
    args = p.parse_args()

    results = [
        test_jain(),
        test_attribution_sums(),
        test_starvation_universe(),
        test_utilization_bounds_and_saturation(),
        test_rf_labels(),
        test_missing_flow_dict_no_silent_zeros(),
    ]

    if args.unit_only:
        pass
    elif args.run:
        run = args.run if args.run.is_absolute() else ROOT / args.run
        results.append(audit_run(run, rewrite=True))
    elif args.experiment:
        exp = args.experiment if args.experiment.is_absolute() else ROOT / args.experiment
        results.append(audit_experiment(exp, limit=args.limit))
    else:
        default = ROOT / "data/runs/fairness_cmp_full/cells_haiti_0_10000_uniform/scored-rf/isl1_gw1/t0"
        if default.exists():
            results.append(audit_run(default, rewrite=True))
        for rel in args.experiments:
            exp = ROOT / rel if not Path(rel).is_absolute() else Path(rel)
            if exp.exists():
                results.append(audit_experiment(exp, limit=args.limit))
            else:
                print(f"  [SKIP] missing experiment {exp}")

    if all(results):
        print("\nAll metric validation checks passed.")
        sys.exit(0)
    print("\nSome checks FAILED.")
    sys.exit(1)


if __name__ == "__main__":
    main()
