"""Independent consistency checks for evaluation metrics vs CosmoSim raw outputs.

Recomputes key quantities from ``demands.txt``, ``max_flow_*.txt``, ``flow_dict_*.json``,
``beam_assignments_*.pkl``, terminals, and ``edge_caps_*.json`` without trusting
pre-baked ``metrics_*.json`` fields. Intended to catch unit mistakes, traffic-
accounting violations, mismatched capacities, and missing artifacts.
"""

from __future__ import annotations

import json
import pickle
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from analysis.edge_capacities import edge_caps_path, load_or_rebuild
from utils import global_variables as global_vars

# Mbps tolerances: CosmoSim capacities/flows are integer Mbps; allow tiny float noise.
TOL_MBPS = 1e-3
TOL_UTIL_OVER = 1.0  # flag flow > capacity + 1 Mbps


def _jain_independent(xs: Sequence[float]) -> float:
    vals = [float(x) for x in xs]
    n = len(vals)
    if n == 0:
        return float("nan")
    s = sum(vals)
    if s <= 0:
        return 1.0 if all(abs(v) <= 1e-15 for v in vals) else float("nan")
    ss = sum(v * v for v in vals)
    return (s * s) / (n * ss)


def _parse_terminals_from_commands(run_dir: Path) -> Path:
    cmds = run_dir / "commands.txt"
    if cmds.exists():
        for tok in cmds.read_text().split():
            if "cells_" in tok and tok.endswith(".txt"):
                p = Path(tok)
                if p.exists():
                    return p
                alt = Path(__file__).resolve().parents[1] / "terminal_deployment" / "terminals" / Path(tok).name
                if alt.exists():
                    return alt
    raise FileNotFoundError(f"terminals path not found via commands.txt in {run_dir}")


def _load_terminals(path: Path) -> Dict[str, int]:
    return {
        a: int(b)
        for a, b in (line.split(",") for line in path.read_text().split() if line.strip())
    }


def _ku_mbps(run_dir: Path) -> float:
    default = 1.28 * 1000.0
    cmds = run_dir / "commands.txt"
    if not cmds.exists():
        return default
    for line in cmds.read_text().splitlines():
        if "generate_flows" not in line and "generate_capacities" not in line:
            continue
        parts = line.split()
        pos: List[str] = []
        i = 0
        # skip to after .py
        try:
            idx = next(i for i, p in enumerate(parts) if p.endswith(".py"))
        except StopIteration:
            continue
        args = parts[idx + 1 :]
        while i < len(args):
            if args[i].startswith("--"):
                i += 2
                continue
            pos.append(args[i])
            i += 1
        if len(pos) >= 9:
            try:
                return float(pos[8]) * 1000.0
            except ValueError:
                pass
    return default


def rebuild_cell_admits(
    mapping: Mapping[str, str],
    terminals: Mapping[str, int],
    ku_mbps: float,
) -> Tuple[Dict[str, float], Dict[int, float], List[str]]:
    """Mirror ``generate_flows`` demand construction. Returns per-cell, per-sat, issues."""
    issues: List[str] = []
    by_cell: Dict[str, List[str]] = defaultdict(list)
    for key in mapping:
        by_cell[key.rsplit("_", 1)[0]].append(key)

    cell_admit: Dict[str, float] = {}
    sat_admit: Dict[int, float] = defaultdict(float)
    ut = float(global_vars.user_terminal_gsl_capacity)

    for cell, n_term in terminals.items():
        if n_term <= 0:
            continue
        keys = sorted(by_cell.get(cell, []))
        if not keys:
            cell_admit[cell] = 0.0
            continue
        n_ch = len(keys)
        alloc = [n_term // n_ch + (1 if i < n_term % n_ch else 0) for i in range(n_ch)]
        total = 0.0
        for i, key in enumerate(keys):
            parts = mapping[key].split("_")
            if len(parts) != 3:
                issues.append(f"error: bad mapping value {key}={mapping[key]}")
                continue
            try:
                sat = int(parts[1])
                ch = int(key.rsplit("_", 1)[1])
            except ValueError:
                issues.append(f"error: unparsable mapping key/value {key}->{mapping[key]}")
                continue
            if not (0 <= ch < 8):
                issues.append(f"error: channel index out of range in {key}")
            admit = min(alloc[i] * ut, ku_mbps)
            sat_admit[sat] += admit
            total += admit
        cell_admit[cell] = total
    return cell_admit, dict(sat_admit), issues


def check_run_consistency(
    run_dir: Path,
    *,
    t_s: Optional[int] = None,
    routing: str = "max_flow",
    metrics: Optional[Mapping[str, Any]] = None,
    rebuild_caps: bool = True,
) -> Dict[str, Any]:
    """Independently audit one run folder.

    Returns ``{ok, errors, warnings, independent, compared_to_metrics}``.
    """
    run_dir = Path(run_dir)
    errors: List[str] = []
    warnings: List[str] = []

    if t_s is None:
        if run_dir.name.startswith("t") and run_dir.name[1:].isdigit():
            t_s = int(run_dir.name[1:])
        else:
            mfs = sorted(run_dir.glob("max_flow_*.txt"))
            if not mfs:
                return {
                    "ok": False,
                    "errors": ["error: no max_flow_*.txt"],
                    "warnings": [],
                    "independent": {},
                    "compared_to_metrics": {},
                }
            t_s = int(mfs[0].stem.split("_")[-1])

    required = {
        "demands": run_dir / "demands.txt",
        "max_flow": run_dir / f"{routing}_{t_s}.txt",
        "flow_dict": run_dir / f"flow_dict_{routing}_{t_s}.json",
        "beams": run_dir / f"beam_assignments_{t_s * 10**9}.pkl",
        "commands": run_dir / "commands.txt",
    }
    missing = [name for name, path in required.items() if not path.exists()]
    if missing:
        # beams/commands soft; demands+max_flow hard
        hard = [m for m in missing if m in ("demands", "max_flow")]
        soft = [m for m in missing if m not in ("demands", "max_flow")]
        for m in hard:
            errors.append(f"error: missing required file ({m})")
        for m in soft:
            warnings.append(f"warning: missing file ({m})")
        if hard:
            return {
                "ok": False,
                "errors": errors,
                "warnings": warnings,
                "independent": {},
                "compared_to_metrics": {},
            }

    try:
        term_path = _parse_terminals_from_commands(run_dir)
    except FileNotFoundError as exc:
        errors.append(f"error: {exc}")
        return {
            "ok": False,
            "errors": errors,
            "warnings": warnings,
            "independent": {},
            "compared_to_metrics": {},
        }

    terminals = _load_terminals(term_path)
    active = sorted(c for c, n in terminals.items() if n > 0)
    ut = float(global_vars.user_terminal_gsl_capacity)
    offered = float(sum(terminals[c] * ut for c in active))

    demands = np.atleast_1d(np.loadtxt(required["demands"], dtype=float))
    admitted = float(demands.sum())
    delivered = float(required["max_flow"].read_text().split(",")[1])

    flow_dict: Dict[str, Any] = {}
    if required["flow_dict"].exists():
        flow_dict = json.loads(required["flow_dict"].read_text())
    else:
        errors.append("error: missing flow_dict — cannot verify per-cell delivery or link utilization")

    mapping: Dict[str, str] = {}
    if required["beams"].exists():
        mapping = pickle.loads(required["beams"].read_bytes())
    else:
        errors.append("error: missing beam_assignments — cannot rebuild per-cell admits")

    ku_mbps = _ku_mbps(run_dir)
    cell_admit, sat_admit_from_cells, map_issues = rebuild_cell_admits(mapping, terminals, ku_mbps)
    errors.extend([i for i in map_issues if i.startswith("error:")])
    warnings.extend([i for i in map_issues if i.startswith("warning:")])

    # Units / ordering: offered >= admitted >= delivered (Mbps)
    if offered + TOL_MBPS < admitted:
        errors.append(
            f"error: traffic accounting offered < admitted ({offered} < {admitted} Mbps)"
        )
    if admitted + TOL_MBPS < delivered:
        errors.append(
            f"error: traffic accounting admitted < delivered ({admitted} < {delivered} Mbps)"
        )

    # Cell-rebuilt admits must match demands.txt
    cell_admit_sum = float(sum(cell_admit.values()))
    if abs(cell_admit_sum - admitted) > TOL_MBPS:
        errors.append(
            f"error: sum of per-cell admits ({cell_admit_sum}) != demands.txt sum ({admitted})"
        )
    max_sat_diff = 0.0
    for s in range(len(demands)):
        a = float(demands[s])
        b = float(sat_admit_from_cells.get(s, 0.0))
        max_sat_diff = max(max_sat_diff, abs(a - b))
        if abs(a - b) > TOL_MBPS and (a > 0 or b > 0):
            errors.append(
                f"error: sat {s} admit mismatch demands.txt={a} cell_rebuild={b}"
            )

    # Per-sat delivered from flow_dict
    sat_del: Dict[int, float] = defaultdict(float)
    into_s = 0.0
    if flow_dict:
        for u, vs in flow_dict.items():
            into_s += float(vs.get("S", 0) or 0)
            u_s = str(u)
            if u_s.startswith("D") or u_s in ("S", "T"):
                continue
            try:
                sat = int(u_s)
            except ValueError:
                continue
            f = float(vs.get(f"D{sat}", 0) or 0)
            if f > 0:
                sat_del[sat] += f
        deliv_dict = float(sum(sat_del.values()))
        if abs(deliv_dict - delivered) > TOL_MBPS:
            errors.append(
                f"error: sum sat→Dsat flows ({deliv_dict}) != max_flow file ({delivered})"
            )
        if abs(into_s - delivered) > TOL_MBPS:
            errors.append(f"error: sum into S ({into_s}) != max_flow file ({delivered})")
        t_out = sum(float(v or 0) for v in flow_dict.get("T", {}).values())
        if abs(t_out - delivered) > TOL_MBPS:
            errors.append(f"error: sum T→GS flows ({t_out}) != max_flow file ({delivered})")
        for sat, d in sat_del.items():
            adm = float(demands[sat]) if sat < len(demands) else 0.0
            if d > adm + TOL_MBPS:
                errors.append(f"error: sat {sat} delivered {d} > admitted {adm}")

    # Attribution (estimate) — only if flow_dict present
    cell_del_est: Dict[str, float] = {}
    jain_d = float("nan")
    starve = float("nan")
    if flow_dict and mapping is not None:
        ratios = {
            int(s): (sat_del.get(int(s), 0.0) / float(demands[s]) if float(demands[s]) > 0 else 0.0)
            for s in np.nonzero(demands)[0]
        }
        by_cell: Dict[str, List[str]] = defaultdict(list)
        for key in mapping:
            by_cell[key.rsplit("_", 1)[0]].append(key)
        for cell in active:
            keys = sorted(by_cell.get(cell, []))
            n_term = terminals[cell]
            if not keys:
                cell_del_est[cell] = 0.0
                continue
            n_ch = len(keys)
            alloc = [n_term // n_ch + (1 if i < n_term % n_ch else 0) for i in range(n_ch)]
            total = 0.0
            for i, key in enumerate(keys):
                sat = int(mapping[key].split("_")[1])
                admit = min(alloc[i] * ut, ku_mbps)
                total += admit * ratios.get(sat, 0.0)
            cell_del_est[cell] = total
        cell_sum = float(sum(cell_del_est.values()))
        if abs(cell_sum - delivered) > TOL_MBPS:
            errors.append(
                f"error: estimated per-cell delivered sum ({cell_sum}) != aggregate ({delivered})"
            )
        xs = [cell_del_est[c] / (terminals[c] * ut) for c in active]
        jain_d = _jain_independent(xs)
        starve = sum(1 for c in active if cell_del_est[c] <= 1e-6) / len(active) if active else float("nan")

    # RF channel / beam ID handling
    dup_keys = [k for k, n in Counter(mapping.keys()).items() if n > 1]
    if dup_keys:
        errors.append(f"error: duplicate mapping keys ({len(dup_keys)})")
    beam_ctr = Counter(mapping.values())
    dup_beams = {b: n for b, n in beam_ctr.items() if n > 1}
    if dup_beams:
        # CosmoSim rules forbid sharing a beam ID; flag as error.
        errors.append(
            f"error: duplicate satellite beam IDs in mapping ({len(dup_beams)} ids reused)"
        )

    # Utilization vs edge caps
    util_ind: Dict[str, Any] = {}
    caps: Any = None
    if flow_dict and rebuild_caps:
        try:
            caps = load_or_rebuild(run_dir, t_s, routing, cache=True)
        except Exception as exc:
            errors.append(f"error: edge capacity load/rebuild failed: {exc}")
            caps = None
        if caps is not None:
            cap_index: Dict[Tuple[str, str], Tuple[str, float]] = {}
            for group in ("gateway_agg", "feeder", "isl"):
                label = {"gateway_agg": "gateway", "feeder": "feeder", "isl": "isl"}[group]
                for e in caps.get(group, []):
                    cap_index[(str(e["u"]), str(e["v"]))] = (label, float(e["capacity_mbps"]))

            # Every positive routing flow (non-demand) must have a capacity edge.
            for u, vs in flow_dict.items():
                for v, f in vs.items():
                    f = float(f or 0)
                    if f <= 0:
                        continue
                    su, sv = str(u), str(v)
                    if sv.startswith("D") or sv == "S" or su.startswith("D"):
                        continue
                    if (su, sv) not in cap_index:
                        errors.append(
                            f"error: positive flow on {su}->{sv} ({f} Mbps) has no matching edge_caps entry"
                        )
                    else:
                        label, c = cap_index[(su, sv)]
                        if f > c + TOL_UTIL_OVER:
                            errors.append(
                                f"error: flow exceeds capacity on {label} {su}->{sv}: {f} > {c}"
                            )

            for group, label in (
                ("gateway_agg", "gateway"),
                ("feeder", "feeder"),
                ("isl", "isl"),
            ):
                flow_sum = 0.0
                cap_sum = 0.0
                for e in caps.get(group, []):
                    u, v = str(e["u"]), str(e["v"])
                    c = float(e["capacity_mbps"])
                    row = flow_dict.get(u) or {}
                    # NX omits zero-flow neighbors; absence means 0, not missing data.
                    f = float(row.get(v, 0) or 0)
                    flow_sum += f
                    cap_sum += c
                util_ind[label] = {
                    "flow_mbps": flow_sum,
                    "capacity_mbps": cap_sum,
                    "aggregate_util": (flow_sum / cap_sum) if cap_sum > 0 else float("nan"),
                }
            # Gateway aggregate flow must equal delivered
            if "gateway" in util_ind and abs(util_ind["gateway"]["flow_mbps"] - delivered) > TOL_MBPS:
                errors.append(
                    f"error: gateway aggregate flow ({util_ind['gateway']['flow_mbps']}) "
                    f"!= delivered ({delivered})"
                )
            # Feeder aggregate flow must equal delivered (same cut)
            if "feeder" in util_ind and abs(util_ind["feeder"]["flow_mbps"] - delivered) > TOL_MBPS:
                errors.append(
                    f"error: feeder aggregate flow ({util_ind['feeder']['flow_mbps']}) "
                    f"!= delivered ({delivered})"
                )

    # Scale sanity from dirname / commands
    scale_dir = run_dir.parent.name
    if scale_dir.startswith("isl") and "_gw" in scale_dir:
        try:
            isl_s = float(scale_dir[3:].split("_gw")[0])
            gw_s = float(scale_dir.split("_gw")[1])
            if caps is not None and util_ind:
                # Unscaled GS aggregate capacity is ground_station_gsl_capacity per GS.
                gs_cap = float(global_vars.ground_station_gsl_capacity)
                n_gw = len(caps.get("gateway_agg", []))
                expected = gs_cap * gw_s * n_gw
                actual = util_ind["gateway"]["capacity_mbps"]
                if n_gw > 0 and abs(actual - expected) > max(1.0, 1e-6 * expected):
                    errors.append(
                        f"error: gateway capacity sum {actual} != gsl_cap×gw_scale×n "
                        f"({gs_cap}×{gw_s}×{n_gw}={expected})"
                    )
                isl_cap = float(global_vars.isl_capacity)
                # Ku=2.5 would double ISL; we require Ku=1.28 in project rules.
                n_isl = len(caps.get("isl", []))
                expected_isl = isl_cap * isl_s * n_isl
                actual_isl = util_ind["isl"]["capacity_mbps"]
                if n_isl > 0 and abs(actual_isl - expected_isl) > max(1.0, 1e-6 * expected_isl):
                    # Only warn: some graphs may have non-uniform ISL caps.
                    warnings.append(
                        f"warning: ISL capacity sum {actual_isl} != isl_cap×isl_scale×n "
                        f"({isl_cap}×{isl_s}×{n_isl}={expected_isl}); check Ku≠1.28 or nonuniform caps"
                    )
        except ValueError:
            warnings.append(f"warning: could not parse scales from {scale_dir}")

    # Runtime file presence (allocation-only)
    alloc_path = run_dir / "allocation_runtime_s.txt"
    alloc_s = None
    if alloc_path.exists():
        try:
            alloc_s = float(alloc_path.read_text().strip().split()[0])
            if alloc_s < 0:
                errors.append("error: negative allocation_runtime_s")
        except ValueError:
            errors.append("error: unreadable allocation_runtime_s.txt")
    else:
        warnings.append(
            "warning: allocation_runtime_s.txt missing — allocation runtime unknown "
            "(rerun generate_flows to record beam_mapping-only time)"
        )

    independent = {
        "units": "Mbps",
        "offered_mbps": offered,
        "admitted_mbps": admitted,
        "delivered_mbps": delivered,
        "demand_satisfaction_delivered_over_offered": (
            delivered / offered if offered > 0 else float("nan")
        ),
        "jain_delivered_over_offered": jain_d,
        "starvation_rate_zero_delivery": starve,
        "allocated_channels": len(mapping),
        "unique_sat_beam_ids": len(set(mapping.values())),
        "duplicate_beam_ids": len(dup_beams),
        "max_sat_admit_diff_mbps": max_sat_diff,
        "utilization": util_ind,
        "runtime_allocation_s": alloc_s,
        "per_cell_delivered_is_estimate": True,
    }

    compared: Dict[str, Any] = {}
    if metrics is not None:
        pairs = [
            ("requested_mbps", offered, metrics.get("requested_mbps")),
            ("admitted_mbps", admitted, metrics.get("admitted_mbps")),
            ("delivered_mbps", delivered, metrics.get("delivered_mbps")),
            (
                "demand_satisfaction",
                independent["demand_satisfaction_delivered_over_offered"],
                metrics.get("demand_satisfaction"),
            ),
            ("jain_fairness", jain_d, metrics.get("jain_fairness")),
            ("starvation_rate", starve, metrics.get("starvation_rate")),
        ]
        for name, a, b in pairs:
            if b is None or (isinstance(b, float) and np.isnan(b)):
                if not (isinstance(a, float) and np.isnan(a)):
                    warnings.append(f"warning: metrics missing {name} while independent has value")
                continue
            if isinstance(a, float) and np.isnan(a):
                continue
            if abs(float(a) - float(b)) > 1e-6:
                errors.append(f"error: metrics.{name}={b} != independent {a}")
            compared[name] = {"independent": a, "metrics": b, "match": abs(float(a) - float(b)) <= 1e-6}

        # Utilization compare when both present
        m_util = metrics.get("utilization") or {}
        for label in ("gateway", "feeder", "isl"):
            if label in util_ind and isinstance(m_util.get(label), dict):
                iu = util_ind[label]["aggregate_util"]
                mu = m_util[label].get("aggregate_util")
                if mu is not None and not (isinstance(iu, float) and np.isnan(iu)):
                    if abs(float(iu) - float(mu)) > 1e-6:
                        errors.append(
                            f"error: metrics utilization.{label}={mu} != independent {iu}"
                        )

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "independent": independent,
        "compared_to_metrics": compared,
    }
