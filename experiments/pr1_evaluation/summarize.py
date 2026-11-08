"""Aggregate PR1 evaluation metrics into per-case means for one method run."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

# Headline PR1-aligned columns (from analysis/metrics flat_summary_row).
HEADLINE = [
    "requested_gbps",
    "admitted_gbps",
    "delivered_gbps",
    "stranded_gbps",
    "demand_satisfaction",  # delivered / requested (overall)
    "jain_d",
    "jain_a",
    "starve_deliv",
    "starve_alloc",
    "cell_rf_fill",
    "sat_rf_util",
    "gw_agg_util",
    "feeder_util",
    "isl_util",
    "gw_frac_sat90",
    "feeder_frac_sat90",
    "isl_frac_sat90",
    "allocation_s",
    "flows_s",
    "caps_s",
]


def _safe_div(num: float, den: float) -> float:
    if den is None or den == 0 or (isinstance(den, float) and np.isnan(den)):
        return float("nan")
    if num is None or (isinstance(num, float) and np.isnan(num)):
        return float("nan")
    return float(num) / float(den)


def enrich_breakdown(row: dict[str, Any]) -> dict[str, Any]:
    """Add RF admission / delivery efficiency / overall satisfaction fractions."""
    req = float(row.get("requested_gbps") or float("nan"))
    adm = float(row.get("admitted_gbps") or float("nan"))
    deliv = float(row.get("delivered_gbps") or float("nan"))
    row["rf_admission_rate"] = _safe_div(adm, req)          # admitted / offered
    row["delivery_efficiency"] = _safe_div(deliv, adm)       # delivered / admitted
    row["overall_satisfaction"] = _safe_div(deliv, req)      # delivered / offered (= demand_satisfaction)
    # Keep alias explicit for reports
    row["demand_sat"] = row["overall_satisfaction"]
    return row


def _mean(vals: Iterable[Any]) -> float:
    xs = [float(v) for v in vals if v is not None and v != "" and str(v).lower() != "nan"]
    xs = [x for x in xs if not (isinstance(x, float) and np.isnan(x))]
    if not xs:
        return float("nan")
    return float(np.mean(xs))


def load_metrics_summary(exp_dir: Path) -> list[dict[str, str]]:
    path = exp_dir / "metrics_summary.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def aggregate_by_case(
    rows: list[dict[str, str]],
    case_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Mean metrics over seconds, grouped by (case, scenario, isl, gw)."""
    # Attach case label by matching scenario + scales to case_index entries.
    groups: dict[tuple, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        scen = r.get("scenario", "")
        isl = float(r.get("isl_scale") or 1)
        gw = float(r.get("gw_scale") or 1)
        case_key = None
        for ck, meta in case_index.items():
            if scen in meta["scenario_dirs"] and abs(isl - meta["isl"]) < 1e-12 and abs(gw - meta["gw"]) < 1e-12:
                case_key = ck
                break
        groups[(case_key or "?", scen, isl, gw)].append(r)

    out = []
    for (case_key, scen, isl, gw), rs in sorted(groups.items(), key=lambda x: (str(x[0][0]), x[0][1], -x[0][2], -x[0][3])):
        meta = case_index.get(case_key or "", {})
        row: dict[str, Any] = {
            "case": case_key,
            "pr1_tag": meta.get("pr1_tag", ""),
            "scenario": scen,
            "isl_scale": isl,
            "gw_scale": gw,
            "n_seconds": len(rs),
            "consistency_ok": all(str(r.get("consistency_ok", "")).lower() in ("true", "1") for r in rs),
        }
        for col in HEADLINE:
            row[col] = _mean(r.get(col) for r in rs)
        out.append(enrich_breakdown(row))
    return out


def write_case_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("")
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def write_findings_stub(
    path: Path,
    *,
    method_key: str,
    method_title: str,
    exp_dir: Path,
    case_rows: list[dict[str, Any]],
) -> None:
    rows = [enrich_breakdown(dict(r)) for r in case_rows]
    lines = [
        f"# PR1 evaluation — Method {method_key}: {method_title}",
        "",
        f"Experiment folder: `{exp_dir}`",
        "",
        "## Throughput (means over seconds, Gbps)",
        "",
        "| Case | Scenario | isl | gw | requested | admitted | delivered | stranded | demand_sat | Jain_d | starve |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['case']} | {r['scenario']} | {r['isl_scale']:g} | {r['gw_scale']:g} | "
            f"{r['requested_gbps']:.1f} | {r['admitted_gbps']:.1f} | {r['delivered_gbps']:.1f} | "
            f"{r['stranded_gbps']:.1f} | {r['demand_sat']:.3f} | "
            f"{r['jain_d']:.3f} | {r['starve_deliv']:.3f} |"
        )
    lines += [
        "",
        "## Admission vs delivery breakdown",
        "",
        "Percentages. Read fairness together with overall satisfaction."
        "",
        "| Case | RF admission rate | Delivery efficiency | Overall satisfaction |",
        "|---|---:|---:|---:|",
        "",
    ]
    # Remove blank line before rows — fix table
    lines.pop()  # remove trailing ""
    for r in rows:
        lines.append(
            f"| {r['case']} | {100 * r['rf_admission_rate']:.1f}% | "
            f"{100 * r['delivery_efficiency']:.1f}% | {100 * r['overall_satisfaction']:.1f}% |"
        )
    lines += [
        "",
        "- **RF admission rate** = admitted / requested — how much offered demand gets RF capacity.",
        "- **Delivery efficiency** = delivered / admitted — how much admitted traffic reaches a gateway.",
        "- **Overall satisfaction** = delivered / requested — end-to-end demand satisfaction "
        "(`demand_sat`; formerly labeled `sat%`).",
        "",
        "## Notes",
        "",
        "- High Jain_d with low overall satisfaction means cells are served *evenly but poorly* "
        "(e.g. hotspot RF ceiling).",
        "- Do not compare absolute Gbps across cases with different offered load "
        "(10k vs 5k terminals).",
        "- Per-cell delivery / Jain_d / starve use estimated sat-ratio attribution "
        "(see `analysis/METRICS.md`).",
        "- Switch method: `experiments/pr1_evaluation/run.py --method 2` (etc.).",
        "",
    ]
    path.write_text("\n".join(lines))


def build_case_index(manifest_cases: list[dict[str, Any]], scenario_dir_map: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Map each (case, scenario_dir, isl, gw) for joining metrics rows."""
    index: dict[str, dict[str, Any]] = {}
    for c in manifest_cases:
        key = c["key"]
        dirs = [scenario_dir_map[s] for s in c["scenarios"] if s in scenario_dir_map]
        # One index entry per scale combo under this case (for matching).
        for isl in c["isl_scales"]:
            for gw in c["gw_scales"]:
                # Store under case key; matching uses scenario_dirs list + scales.
                index[key] = {
                    "pr1_tag": c["pr1_tag"],
                    "scenario_dirs": dirs,
                    "isl": float(isl),
                    "gw": float(gw),
                }
        # Re-store once with all dirs (overwrite is fine; dirs are the same).
        index[key] = {
            "pr1_tag": c["pr1_tag"],
            "scenario_dirs": dirs,
            "isl": float(c["isl_scales"][0]),
            "gw": float(c["gw_scales"][0]),
        }
    # Better: match any scale in the case. Rebuild matching differently in aggregate.
    return index


def aggregate_rows_with_cases(
    rows: list[dict[str, str]],
    cases: list[dict[str, Any]],
    scenario_dir_map: dict[str, str],
) -> list[dict[str, Any]]:
    """Join metrics rows to PR1 cases (scenario may appear in multiple cases with different scales)."""
    # Expand cases into match rules.
    rules = []
    for c in cases:
        dirs = {scenario_dir_map[s] for s in c["scenarios"] if s in scenario_dir_map}
        for isl in c["isl_scales"]:
            for gw in c["gw_scales"]:
                rules.append((c["key"], c["pr1_tag"], dirs, float(isl), float(gw)))

    groups: dict[tuple, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        scen = r.get("scenario", "")
        isl = float(r.get("isl_scale") or 1)
        gw = float(r.get("gw_scale") or 1)
        matched = None
        for key, tag, dirs, risl, rgw in rules:
            if scen in dirs and abs(isl - risl) < 1e-12 and abs(gw - rgw) < 1e-12:
                matched = (key, tag, scen, isl, gw)
                break
        if matched is None:
            matched = ("unassigned", "", scen, isl, gw)
        groups[matched].append(r)

    out = []
    for (case_key, tag, scen, isl, gw), rs in sorted(groups.items()):
        row: dict[str, Any] = {
            "case": case_key,
            "pr1_tag": tag,
            "scenario": scen,
            "isl_scale": isl,
            "gw_scale": gw,
            "n_seconds": len(rs),
            "consistency_ok": all(str(r.get("consistency_ok", "")).lower() in ("true", "1") for r in rs),
        }
        for col in HEADLINE:
            row[col] = _mean(r.get(col) for r in rs)
        out.append(enrich_breakdown(row))
    return out
