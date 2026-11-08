"""PR1-aligned evaluation metrics for CosmoSim beam + routing runs.

See ``analysis/METRICS.md`` for the Progress Report 1 audit table, formulas,
and limitations.

Primary sources (already produced by the CosmoSim pipeline):
  - ``demands.txt``, ``max_flow_*.txt``, ``flow_dict_*.json``, ``beam_assignments_*.pkl``
  - ``edge_caps_*.json`` (solver capacities; dumped or rebuilt)
  - ``allocation_runtime_s.txt`` (RF allocation wall time inside generate_flows)

Per-cell *delivered* is an **estimate**: CosmoSim max-flow only has per-satellite
sinks. We attribute each sat's delivered traffic to its admitted cells in proportion
to cell admitted Mbps. Field ``per_cell_delivered_method`` labels this; cell totals
are checked against aggregate delivered.
"""

from __future__ import annotations

import json
import pickle
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

import numpy as np

from analysis.edge_capacities import load_or_rebuild
from spectrum_management.constants import MAX_CHANNELS_PER_CELL
from utils import global_variables as global_vars

ROOT = Path(__file__).resolve().parents[1]
TERMINALS = ROOT / "terminal_deployment" / "terminals"

# Congestion indicator: fraction of *active* (flow > 0) edges at or above this util.
SATURATION_THRESHOLD = 0.90

LATENCY_UNSUPPORTED = (
    "CosmoSim's max-flow capacity workflow does not model queues, propagation delay, "
    "or end-to-end latency. Link utilization and saturation are congestion *indicators*, "
    "not queue-buildup measurements."
)


def jain(values: Sequence[float]) -> float:
    """Jain's fairness index over non-empty satisfaction ratios."""
    xs = np.asarray(values, dtype=float)
    if xs.size == 0:
        return float("nan")
    s = float(xs.sum())
    if s <= 0:
        # All zeros → perfectly equal (all starved). Index is 1 by definition when
        # every cell has the same satisfaction (here 0).
        return 1.0 if np.allclose(xs, 0.0) else float("nan")
    return float((s * s) / (xs.size * float((xs * xs).sum())))


def _flow_lookup(flow_dict: Mapping[str, Mapping[str, float]], u: Any, v: Any) -> float:
    """Return directed flow u→v in Mbps.

    NetworkX ``flow_dict`` omits zero-flow neighbors; absence means 0 flow on a
    known capacity edge, not a missing measurement. Do not use this to invent
    flows for edges that are absent from ``edge_caps``.
    """
    su, sv = str(u), str(v)
    row = flow_dict.get(su)
    if row is None and not isinstance(u, str):
        row = flow_dict.get(u)  # type: ignore[arg-type]
    if not row:
        return 0.0
    if sv in row:
        return float(row[sv] or 0.0)
    if not isinstance(v, str) and v in row:
        return float(row[v] or 0.0)
    return 0.0


def per_sat_delivered(flow_dict: Mapping[str, Mapping[str, float]]) -> Dict[int, float]:
    """Mbps delivered into each demand sink ``D<sat>`` (post max-flow)."""
    out: Dict[int, float] = defaultdict(float)
    for u, vs in flow_dict.items():
        u_s = str(u)
        if u_s.startswith("D") or u_s in ("S", "T"):
            continue
        try:
            sat = int(u_s)
        except ValueError:
            continue
        dkey = f"D{sat}"
        flow = float(vs.get(dkey, 0) or 0)
        if flow > 0:
            out[sat] += flow
    return dict(out)


def per_sat_admitted(demands: np.ndarray) -> Dict[int, float]:
    return {int(i): float(demands[i]) for i in np.nonzero(demands)[0]}


def load_terminals(path: Path) -> Dict[str, int]:
    return {
        a: int(b)
        for a, b in (line.split(",") for line in path.read_text().split() if line.strip())
    }


def cell_channel_admits(
    mapping: Mapping[str, str],
    terminals: Mapping[str, int],
    ku_band_capacity_gbps: float = 1.28,
) -> Dict[str, List[Tuple[int, float]]]:
    """Per cell: list of (sat_id, admitted_mbps) for each assigned channel."""
    by_cell: Dict[str, List[str]] = defaultdict(list)
    for key in mapping:
        by_cell[key.rsplit("_", 1)[0]].append(key)

    out: Dict[str, List[Tuple[int, float]]] = {}
    ku_mbps = ku_band_capacity_gbps * 1000.0
    for cell, n_term in terminals.items():
        if n_term <= 0:
            continue
        keys = sorted(by_cell.get(cell, []))
        if not keys:
            out[cell] = []
            continue
        n_ch = len(keys)
        allocations = [
            n_term // n_ch + (1 if i < n_term % n_ch else 0) for i in range(n_ch)
        ]
        rows: List[Tuple[int, float]] = []
        for idx, key in enumerate(keys):
            sat = int(mapping[key].split("_")[1])
            admit = min(
                allocations[idx] * global_vars.user_terminal_gsl_capacity,
                ku_mbps,
            )
            rows.append((sat, float(admit)))
        out[cell] = rows
    return out


def attribute_cell_delivered(
    channel_admits: Mapping[str, List[Tuple[int, float]]],
    sat_admitted: Mapping[int, float],
    sat_delivered: Mapping[int, float],
) -> Dict[str, float]:
    """Estimate per-cell delivered Mbps via sat delivery ratios × cell admit.

    Not exact path-level cell delivery — CosmoSim does not track cell identity
    through max-flow.
    """
    ratios = {
        sat: (sat_delivered.get(sat, 0.0) / adm if adm > 0 else 0.0)
        for sat, adm in sat_admitted.items()
    }
    out: Dict[str, float] = {}
    for cell, rows in channel_admits.items():
        total = 0.0
        for sat, admit in rows:
            total += admit * ratios.get(sat, 0.0)
        out[cell] = total
    return out


def _util_stats(flows: Sequence[float], caps: Sequence[float]) -> Dict[str, float]:
    f = np.asarray(flows, dtype=float)
    c = np.asarray(caps, dtype=float)
    empty = {
        "flow_mbps": 0.0,
        "capacity_mbps": 0.0,
        "aggregate_util": float("nan"),
        "mean_edge_util": float("nan"),
        "p95_edge_util": float("nan"),
        "mean_used_edge_util": float("nan"),
        "p95_used_edge_util": float("nan"),
        "saturated_edges_099": 0,
        "n_edges": 0,
        "n_used_edges": 0,
        "frac_active_saturated_090": float("nan"),
        "n_active_saturated_090": 0,
    }
    if c.size == 0 or float(c.sum()) <= 0:
        return empty
    mask = c > 0
    f, c = f[mask], c[mask]
    edge_util = np.divide(f, c, out=np.zeros_like(f), where=c > 0)
    used_mask = f > 0
    used = edge_util[used_mask]
    n_sat90 = int(np.sum(used >= SATURATION_THRESHOLD)) if used.size else 0
    return {
        "flow_mbps": float(f.sum()),
        "capacity_mbps": float(c.sum()),
        "aggregate_util": float(f.sum() / c.sum()),
        "mean_edge_util": float(edge_util.mean()) if edge_util.size else float("nan"),
        "p95_edge_util": float(np.percentile(edge_util, 95)) if edge_util.size else float("nan"),
        "mean_used_edge_util": float(used.mean()) if used.size else float("nan"),
        "p95_used_edge_util": float(np.percentile(used, 95)) if used.size else float("nan"),
        "saturated_edges_099": int(np.sum(edge_util >= 0.99)),
        "n_edges": int(edge_util.size),
        "n_used_edges": int(used.size),
        "frac_active_saturated_090": (n_sat90 / used.size) if used.size else float("nan"),
        "n_active_saturated_090": n_sat90,
    }


def link_utilization(
    flow_dict: Mapping[str, Mapping[str, float]],
    edge_caps: Mapping[str, Any],
) -> Dict[str, Dict[str, float]]:
    """Post-routing flow / solver capacity for gateway aggregate, feeder, and ISL.

    - ``gateway``: T→GS aggregate edges (ground-station egress budget)
    - ``feeder``: GS→sat Ka feeder edges (do not sum with gateway for total capacity)
    - ``isl``: sat→sat edges

    Capacities already include ``isl-scale`` / ``gw-scale`` when taken from the
    scaled solver graph.
    """
    groups = {
        "gateway": edge_caps.get("gateway_agg", []),
        "feeder": edge_caps.get("feeder", []),
        "isl": edge_caps.get("isl", []),
    }
    out: Dict[str, Dict[str, float]] = {}
    for name, edges in groups.items():
        flows = [_flow_lookup(flow_dict, e["u"], e["v"]) for e in edges]
        caps = [float(e["capacity_mbps"]) for e in edges]
        out[name] = _util_stats(flows, caps)
    return out


def rf_utilization(
    mapping: Mapping[str, str],
    n_active_cells: int,
    visible_sats: Optional[Set[int]] = None,
) -> Dict[str, Any]:
    """RF resource use: cell-slot fill + satellite beam-ID utilization.

    ``cell_rf_fill`` = allocated cell-channels / (active_cells × 8).
    This is *not* satellite RF utilization.

    ``satellite_rf_util`` = unique allocated ``color_sat_beam`` IDs /
    (visible_sats × 8 × spatial_reuse). Denominator ignores interference and
    geometry constraints that prevent using every beam ID concurrently.
    """
    allocated = len(mapping)
    available_slots = n_active_cells * MAX_CHANNELS_PER_CELL
    unique_beam_ids = {v for v in mapping.values()} if mapping else set()
    beams_per_sat = MAX_CHANNELS_PER_CELL * int(global_vars.spatial_channel_reuse_factor)

    if visible_sats is None:
        visible_sats = {int(v.split("_")[1]) for v in unique_beam_ids} if unique_beam_ids else set()
        visible_approx = True
    else:
        visible_approx = False

    available_sat_beams = len(visible_sats) * beams_per_sat
    return {
        "allocated_channels": float(allocated),
        "available_cell_channel_slots": float(available_slots),
        "cell_rf_fill": (allocated / available_slots) if available_slots else float("nan"),
        # Back-compat alias (old name was misleading).
        "channel_slot_util": (allocated / available_slots) if available_slots else float("nan"),
        "unique_sat_beam_ids": float(len(unique_beam_ids)),
        "n_visible_sats": float(len(visible_sats)),
        "beams_per_sat": float(beams_per_sat),
        "available_sat_beam_ids": float(available_sat_beams),
        "satellite_rf_util": (
            len(unique_beam_ids) / available_sat_beams if available_sat_beams else float("nan")
        ),
        "satellite_rf_denominator": (
            "visible_sats_serving_active_cells × 8 channels × 4 colors"
            if not visible_approx
            else "sats_appearing_in_mapping × 8 × 4 (graph visibility unavailable)"
        ),
        "satellite_rf_note": (
            "Denominator is the CosmoSim beam-ID pool size; it does not subtract "
            "IDs blocked by interference or visibility of individual cells."
        ),
    }


def _visible_sats_for_cells(
    run_dir: Path,
    t_s: int,
    active_cells: Sequence[str],
) -> Optional[Set[int]]:
    """Sats that can serve at least one active cell (same filter as generate_flows)."""
    cmds = run_dir / "commands.txt"
    if not cmds.exists():
        return None
    graph_dir = None
    for line in cmds.read_text().splitlines():
        if "generate_flows" not in line:
            continue
        parts = line.split()
        try:
            idx = next(i for i, p in enumerate(parts) if p.endswith("generate_flows.py"))
        except StopIteration:
            continue
        args = parts[idx + 1 :]
        pos = []
        i = 0
        while i < len(args):
            if args[i].startswith("--"):
                i += 2
                continue
            pos.append(args[i])
            i += 1
        if len(pos) >= 2:
            graph_dir = Path(pos[1])
        break
    if graph_dir is None:
        return None
    if not graph_dir.is_absolute():
        graph_dir = ROOT / graph_dir
    gpath = graph_dir / f"graph_{t_s * 10**9}.txt"
    if not gpath.exists():
        return None
    try:
        with gpath.open("rb") as fh:
            graph = pickle.load(fh)
    except Exception:
        return None

    # Match generate_flows: sat must have a predecessor below ut_base (GS or sat).
    # We don't have GS count here; use any int predecessor as CosmoSim does loosely.
    visible: Set[int] = set()
    for cell in active_cells:
        if cell not in graph:
            continue
        for sat in graph.predecessors(cell):
            if not isinstance(sat, int):
                continue
            preds = list(graph.predecessors(sat))
            if any(isinstance(n, int) for n in preds):
                visible.add(int(sat))
    return visible


def detect_t_and_routing(run_dir: Path) -> Tuple[int, str]:
    mfs = sorted(run_dir.glob("max_flow_*.txt"))
    if mfs:
        return int(mfs[0].stem.split("_")[-1]), "max_flow"
    for p in run_dir.glob("flow_dict_*_*.json"):
        parts = p.stem.split("_")
        return int(parts[-1]), "_".join(parts[2:-1]) or "max_flow"
    if run_dir.name.startswith("t") and run_dir.name[1:].isdigit():
        return int(run_dir.name[1:]), "max_flow"
    raise FileNotFoundError(f"No max_flow / flow_dict in {run_dir}")


def _ku_from_commands(run_dir: Path, default: float = 1.28) -> float:
    cmds = run_dir / "commands.txt"
    if not cmds.exists():
        return default
    for line in cmds.read_text().splitlines():
        if "generate_flows" in line or "generate_capacities" in line:
            parts = line.split()
            try:
                idx = next(i for i, p in enumerate(parts) if p.endswith(".py"))
            except StopIteration:
                continue
            args = parts[idx + 1 :]
            pos = []
            i = 0
            while i < len(args):
                if args[i].startswith("--"):
                    i += 2
                    continue
                pos.append(args[i])
                i += 1
            if len(pos) >= 9:
                try:
                    return float(pos[8])
                except ValueError:
                    pass
    return default


def _terminals_path_for_run(run_dir: Path, terminal_file: Optional[str] = None) -> Path:
    if terminal_file:
        p = Path(terminal_file)
        if not p.exists():
            p = TERMINALS / f"{Path(terminal_file).stem}.txt"
        return p
    cmds = run_dir / "commands.txt"
    if cmds.exists():
        for line in cmds.read_text().splitlines():
            if "generate_flows" in line or "generate_capacities" in line:
                for tok in line.split():
                    if "cells_" in tok and tok.endswith(".txt"):
                        cand = Path(tok)
                        if cand.exists():
                            return cand
                        alt = TERMINALS / Path(tok).name
                        if alt.exists():
                            return alt
    scen = run_dir.parent.parent.parent.name
    alt = TERMINALS / f"{scen}.txt"
    if alt.exists():
        return alt
    raise FileNotFoundError(f"Cannot resolve terminals file for {run_dir}")


def _read_allocation_runtime(run_dir: Path) -> Optional[float]:
    path = run_dir / "allocation_runtime_s.txt"
    if not path.exists():
        return None
    try:
        return float(path.read_text().strip().split()[0])
    except (ValueError, IndexError):
        return None


def compute_run_metrics(
    run_dir: Path,
    *,
    t_s: Optional[int] = None,
    routing: Optional[str] = None,
    terminals_path: Optional[Path] = None,
    flows_s: Optional[float] = None,
    capacities_s: Optional[float] = None,
    rebuild_caps: bool = True,
) -> Dict[str, Any]:
    run_dir = Path(run_dir)
    if t_s is None or routing is None:
        det_t, det_r = detect_t_and_routing(run_dir)
        t_s = det_t if t_s is None else t_s
        routing = det_r if routing is None else routing
    assert t_s is not None and routing is not None

    term_path = Path(terminals_path) if terminals_path else _terminals_path_for_run(run_dir)
    terminals = load_terminals(term_path)
    # Positive-demand cells only (PR1 starvation / fairness universe).
    active_cells = sorted(c for c, n in terminals.items() if n > 0)
    n_active = len(active_cells)

    pkl = run_dir / f"beam_assignments_{t_s * 10**9}.pkl"
    mapping: Dict[str, str] = pickle.loads(pkl.read_bytes()) if pkl.exists() else {}
    demands = np.atleast_1d(np.loadtxt(run_dir / "demands.txt", dtype=float))
    delivered_total = float((run_dir / f"{routing}_{t_s}.txt").read_text().split(",")[1])
    flow_path = run_dir / f"flow_dict_{routing}_{t_s}.json"
    has_flow_dict = flow_path.exists()
    flow_dict: Dict[str, Any] = json.loads(flow_path.read_text()) if has_flow_dict else {}

    sat_adm = per_sat_admitted(demands)
    ku = _ku_from_commands(run_dir)
    channel_admits = cell_channel_admits(mapping, terminals, ku)

    offered = {
        c: float(terminals[c] * global_vars.user_terminal_gsl_capacity) for c in active_cells
    }
    allocated = {
        c: float(sum(a for _, a in channel_admits.get(c, []))) for c in active_cells
    }
    cell_admit_total = float(sum(allocated.values()))

    sat_alloc = {
        c: (min(1.0, allocated[c] / offered[c]) if offered[c] > 0 else float("nan"))
        for c in active_cells
    }
    served = {k.rsplit("_", 1)[0] for k in mapping}
    zero_alloc = [c for c in active_cells if c not in served]

    admitted_total = float(demands.sum())
    requested_total = float(sum(offered.values()))

    # Per-cell delivery estimates require flow_dict. Do NOT invent zeros.
    sat_del: Dict[int, float] = {}
    delivered_cell: Dict[str, Optional[float]] = {c: None for c in active_cells}
    sat_deliv: Dict[str, float] = {c: float("nan") for c in active_cells}
    zero_deliv: List[str] = []
    cell_delivered_sum = float("nan")
    sat_delivered_sum = float("nan")
    jain_d = float("nan")
    starve_deliv = float("nan")
    mean_sat_d = float("nan")
    min_sat_d = float("nan")

    if has_flow_dict:
        sat_del = per_sat_delivered(flow_dict)
        cell_delivered_est = attribute_cell_delivered(channel_admits, sat_adm, sat_del)
        delivered_cell = {c: float(cell_delivered_est.get(c, 0.0)) for c in active_cells}
        sat_deliv = {
            c: (delivered_cell[c] / offered[c] if offered[c] > 0 else float("nan"))  # type: ignore[operator]
            for c in active_cells
        }
        zero_deliv = [c for c in active_cells if (delivered_cell[c] or 0.0) <= 1e-6]
        cell_delivered_sum = float(sum(delivered_cell[c] or 0.0 for c in active_cells))
        sat_delivered_sum = float(sum(sat_del.values()))
        jain_d = jain([sat_deliv[c] for c in active_cells])
        starve_deliv = len(zero_deliv) / n_active if n_active else float("nan")
        mean_sat_d = float(np.nanmean(list(sat_deliv.values()))) if sat_deliv else float("nan")
        min_sat_d = float(np.nanmin(list(sat_deliv.values()))) if sat_deliv else float("nan")

    visible = _visible_sats_for_cells(run_dir, t_s, active_cells)
    rf = rf_utilization(mapping, n_active, visible)

    util: Dict[str, Any] = {}
    if has_flow_dict and rebuild_caps:
        try:
            edge_caps = load_or_rebuild(run_dir, t_s, routing, cache=True)
            util = link_utilization(flow_dict, edge_caps)
            util["notes"] = {
                "gateway": "T→GS aggregate capacity (gw-scale applied); egress budget per ground station",
                "feeder": "GS→sat Ka edges after stock assignment (gw-scale); do not add to gateway capacity",
                "isl": "sat→sat edges (isl-scale); capacity from solver graph",
                "flow_lookup": (
                    "NX flow_dict omits zero-flow neighbors; missing neighbor ⇒ 0 flow on that "
                    "directed capacity edge (not an imputed measurement)"
                ),
                "no_double_count": (
                    "gateway and feeder carry the same end-to-end traffic volume at "
                    "steady state; report them separately, never sum capacities"
                ),
            }
        except Exception as exc:
            util = {"error": str(exc)}
    elif not has_flow_dict:
        util = {"error": "missing flow_dict; utilization not computed"}

    alloc_runtime = _read_allocation_runtime(run_dir)

    metrics: Dict[str, Any] = {
        "run_dir": str(run_dir),
        "t_s": t_s,
        "routing": routing,
        "terminals_file": str(term_path),
        "n_active_cells": n_active,
        "units": "Mbps (CSV summary uses Gbps = Mbps/1000)",
        "artifacts": {
            "demands": True,
            "max_flow": True,
            "flow_dict": has_flow_dict,
            "beam_assignments": pkl.exists(),
            "allocation_runtime": alloc_runtime is not None,
        },
        # 1. End-to-end throughput (post-routing) — exact from max_flow file
        "throughput_delivered_mbps": delivered_total,
        "delivered_mbps": delivered_total,
        "requested_mbps": requested_total,
        "admitted_mbps": admitted_total,
        "stranded_mbps": admitted_total - delivered_total,
        "cell_admit_sum_mbps": cell_admit_total,
        # 2. Demand satisfaction — PR1 primary is delivered/offered
        "demand_satisfaction": (
            delivered_total / requested_total if requested_total > 0 else float("nan")
        ),
        "demand_satisfaction_delivered_over_offered": (
            delivered_total / requested_total if requested_total > 0 else float("nan")
        ),
        "demand_satisfaction_delivered_over_admitted": (
            delivered_total / admitted_total if admitted_total > 0 else float("nan")
        ),
        "admission_ratio": (
            admitted_total / requested_total if requested_total > 0 else float("nan")
        ),
        # 3. Fairness + starvation (null if flow_dict missing — do not invent)
        "jain_fairness": jain_d,
        "jain_delivered_over_offered": jain_d,
        "jain_allocated_over_offered": jain([sat_alloc[c] for c in active_cells]),
        "mean_cell_satisfaction_delivered": mean_sat_d,
        "min_cell_satisfaction_delivered": min_sat_d,
        "mean_cell_satisfaction_allocated": (
            float(np.nanmean(list(sat_alloc.values()))) if sat_alloc else float("nan")
        ),
        "starvation_rate": starve_deliv,
        "starvation_rate_zero_delivery": starve_deliv,
        "starvation_rate_zero_allocation": (
            len(zero_alloc) / n_active if n_active else float("nan")
        ),
        "n_zero_delivery_cells": len(zero_deliv) if has_flow_dict else None,
        "n_zero_allocation_cells": len(zero_alloc),
        # 4. Resource utilization
        "rf": rf,
        "utilization": util,
        # 5. Latency — unsupported
        "latency": {
            "supported": False,
            "end_to_end_delay": None,
            "queue_buildup": None,
            "reason": LATENCY_UNSUPPORTED,
        },
        # 6. Runtime
        "runtime_allocation_s": alloc_runtime,
        "runtime_generate_flows_wall_s": flows_s,
        "runtime_routing_wall_s": capacities_s,
        "runtime_beam_assignment_s": flows_s,
        "runtime_routing_s": capacities_s,
        "runtime_notes": {
            "allocation": (
                "Wall time of beam_mapping() inside generate_flows "
                "(allocation_runtime_s.txt); comparable across policies. "
                "null if file missing — not replaced with 0."
            ),
            "generate_flows_wall": (
                "Full workflows/generate_flows.py subprocess (I/O + visibility + allocation)"
            ),
            "routing_wall": (
                "Full workflows/generate_capacities_scaled.py subprocess (Ka assign + max-flow)"
            ),
        },
        # Attribution / accounting
        "per_cell_delivered_method": (
            "estimated_sat_delivery_ratio_x_cell_admit" if has_flow_dict else None
        ),
        "per_cell_delivered_is_estimate": True,
        "per_cell_delivery_available": has_flow_dict,
        "accounting": {
            "sum_estimated_cell_delivered_mbps": cell_delivered_sum,
            "sum_sat_delivered_mbps": sat_delivered_sum,
            "aggregate_delivered_mbps": delivered_total,
            "cell_vs_aggregate_abs_diff_mbps": (
                abs(cell_delivered_sum - delivered_total)
                if has_flow_dict and not np.isnan(cell_delivered_sum)
                else None
            ),
            "sat_vs_aggregate_abs_diff_mbps": (
                abs(sat_delivered_sum - delivered_total)
                if has_flow_dict and not np.isnan(sat_delivered_sum)
                else None
            ),
            "cell_admit_vs_demands_abs_diff_mbps": abs(cell_admit_total - admitted_total),
        },
        "per_cell": {
            c: {
                "offered_mbps": offered[c],
                "allocated_mbps": allocated[c],
                "delivered_mbps_estimated": delivered_cell[c],
                "satisfaction_delivered_estimated": sat_deliv[c],
                "satisfaction_allocated": sat_alloc[c],
            }
            for c in active_cells
        },
    }

    # Independent consistency audit against raw files (flags errors; does not invent data).
    from analysis.consistency import check_run_consistency

    consistency = check_run_consistency(
        run_dir, t_s=t_s, routing=routing, metrics=metrics, rebuild_caps=rebuild_caps
    )
    metrics["consistency"] = {
        "ok": consistency["ok"],
        "errors": consistency["errors"],
        "warnings": consistency["warnings"],
    }
    return metrics


def write_run_metrics(run_dir: Path, metrics: Mapping[str, Any], t_s: Optional[int] = None) -> Path:
    t = int(metrics.get("t_s", t_s if t_s is not None else 0))
    path = run_dir / f"metrics_{t}.json"
    path.write_text(json.dumps(metrics, indent=2, sort_keys=True))
    return path


def flat_summary_row(metrics: Mapping[str, Any], **extra: Any) -> Dict[str, Any]:
    """One CSV-friendly row (no per-cell blob)."""
    util = metrics.get("utilization") or {}
    rf = metrics.get("rf") or {}

    def u(group: str, key: str) -> float:
        g = util.get(group) or {}
        if not isinstance(g, dict):
            return float("nan")
        val = g.get(key, float("nan"))
        try:
            return float(val)
        except (TypeError, ValueError):
            return float("nan")

    row = {
        **extra,
        "t_s": metrics.get("t_s"),
        "requested_gbps": float(metrics["requested_mbps"]) / 1e3,
        "admitted_gbps": float(metrics["admitted_mbps"]) / 1e3,
        "delivered_gbps": float(metrics["delivered_mbps"]) / 1e3,
        "stranded_gbps": float(metrics["stranded_mbps"]) / 1e3,
        "demand_satisfaction": metrics.get("demand_satisfaction"),
        "sat_del_offered": metrics.get("demand_satisfaction_delivered_over_offered"),
        "sat_del_admitted": metrics.get("demand_satisfaction_delivered_over_admitted"),
        "jain_d": metrics.get("jain_delivered_over_offered"),
        "jain_a": metrics.get("jain_allocated_over_offered"),
        "mean_cell_sat_d": metrics.get("mean_cell_satisfaction_delivered"),
        "min_cell_sat_d": metrics.get("min_cell_satisfaction_delivered"),
        "starve_deliv": metrics.get("starvation_rate_zero_delivery"),
        "starve_alloc": metrics.get("starvation_rate_zero_allocation"),
        "cell_rf_fill": rf.get("cell_rf_fill", rf.get("channel_slot_util")),
        "sat_rf_util": rf.get("satellite_rf_util"),
        "gw_agg_util": u("gateway", "aggregate_util"),
        "feeder_util": u("feeder", "aggregate_util"),
        "isl_util": u("isl", "aggregate_util"),
        "gw_frac_sat90": u("gateway", "frac_active_saturated_090"),
        "feeder_frac_sat90": u("feeder", "frac_active_saturated_090"),
        "isl_frac_sat90": u("isl", "frac_active_saturated_090"),
        "gw_p95_used": u("gateway", "p95_used_edge_util"),
        "feeder_p95_used": u("feeder", "p95_used_edge_util"),
        "isl_p95_used": u("isl", "p95_used_edge_util"),
        "allocation_s": metrics.get("runtime_allocation_s"),
        "flows_s": metrics.get("runtime_generate_flows_wall_s")
        if metrics.get("runtime_generate_flows_wall_s") is not None
        else metrics.get("runtime_beam_assignment_s"),
        "caps_s": metrics.get("runtime_routing_wall_s")
        if metrics.get("runtime_routing_wall_s") is not None
        else metrics.get("runtime_routing_s"),
        "latency_supported": False,
        "cell_vs_agg_diff_mbps": (metrics.get("accounting") or {}).get(
            "cell_vs_aggregate_abs_diff_mbps"
        ),
        "per_cell_delivery_available": metrics.get("per_cell_delivery_available"),
        "consistency_ok": (metrics.get("consistency") or {}).get("ok"),
        "consistency_errors": len((metrics.get("consistency") or {}).get("errors") or []),
        "consistency_warnings": len((metrics.get("consistency") or {}).get("warnings") or []),
    }
    return row
