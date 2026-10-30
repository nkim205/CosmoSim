#!/usr/bin/env python3
"""Classify what limits stock max-flow routing, snapshot by snapshot.

Runs the unmodified ``workflows.generate_capacities.generate_capacities`` with its
``max_flow_capacities`` step wrapped, so the census sees exactly the graph the stock
code solves (Ka assignment, GS pruning, super source/sink) without duplicating it.

Stock flow direction is T -> GS -> sat (-> ISLs -> sat) -> D{sat} -> S, i.e. ``T`` is
the actual source even though the stock code names it ``super_sink``.

Edge classes:
  gs_aggregate : T -> GS            (per-ground-station limit)
  feeder       : GS -> sat          (Ka feeder capacity assigned by the stock code)
  isl          : sat -> sat
  access       : sat -> D{sat}      (admitted demand of that satellite)
"""

from __future__ import annotations

import argparse
import csv
import sys
import tempfile
from collections import Counter, deque
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

import networkx as nx
import numpy as np

import workflows.generate_capacities as gc
from traffic_engineering.capacity_scaling import scale_capacities

CLASSES = ("access", "isl", "feeder", "gs_aggregate")


def edge_class(u, v, num_sats: int) -> str | None:
    if u == "T":
        return "gs_aggregate"
    if (isinstance(v, str) and v.startswith("D")) or (isinstance(u, str) and u.startswith("D")):
        return "access"
    if isinstance(u, int) and isinstance(v, int):
        if u >= num_sats and v < num_sats:
            return "feeder"
        if u < num_sats and v < num_sats:
            return "isl"
    return None


def hops_from_gateways(graph: nx.DiGraph, num_sats: int) -> Dict[int, int]:
    """Edges on the shortest path from any GS to each satellite (1 = sees a GS directly)."""
    dist: Dict[int, int] = {}
    queue = deque()
    for node in graph.nodes:
        if isinstance(node, int) and node >= num_sats:
            dist[node] = 0
            queue.append(node)
    while queue:
        u = queue.popleft()
        for v in graph.successors(u):
            if isinstance(v, int) and v < num_sats and v not in dist and graph[u][v].get("capacity", 0) > 0:
                dist[v] = dist[u] + 1
                queue.append(v)
    return {n: d for n, d in dist.items() if n < num_sats}


def census_snapshot(graph: nx.DiGraph, flow_dict, demands: np.ndarray, num_sats: int) -> Dict[str, float]:
    row: Dict[str, float] = {}
    admitted = float(sum(int(d) for d in demands if d > 0))
    delivered = float(sum(flow_dict["T"].values()))
    row["admitted_mbps"] = admitted
    row["delivered_mbps"] = delivered
    row["stranded_mbps"] = admitted - delivered

    cut_value, (reachable, _) = nx.minimum_cut(graph, "T", "S", capacity="capacity")
    row["min_cut_mbps"] = float(cut_value)
    cut_by_class = Counter()
    sat_by_class = Counter()
    for u in reachable:
        for v, data in graph[u].items():
            if v in reachable:
                continue
            cls = edge_class(u, v, num_sats)
            cut_by_class[cls] += data.get("capacity", 0)
            sat_by_class[cls] += 1
    for cls in CLASSES:
        row[f"cut_{cls}_mbps"] = float(cut_by_class.get(cls, 0))
        row[f"cut_{cls}_edges"] = int(sat_by_class.get(cls, 0))

    saturated = Counter()
    for u, nbrs in flow_dict.items():
        for v, f in nbrs.items():
            cap = graph[u][v].get("capacity", 0) if graph.has_edge(u, v) else 0
            if cap > 0 and f >= cap:
                saturated[edge_class(u, v, num_sats)] += 1
    for cls in CLASSES:
        row[f"saturated_{cls}_edges"] = int(saturated.get(cls, 0))

    demand_sats = [int(s) for s in np.nonzero(demands)[0] if int(demands[s]) > 0]
    hops = hops_from_gateways(graph, num_sats)
    demand_hops = [hops[s] for s in demand_sats if s in hops]
    unmet = [s for s in demand_sats if flow_dict.get(s, {}).get(f"D{s}", 0) < int(demands[s])]
    row["demand_sats"] = len(demand_sats)
    row["demand_sats_unreachable"] = len(demand_sats) - len(demand_hops)
    row["demand_sats_direct_gs"] = sum(1 for h in demand_hops if h == 1)
    row["demand_sats_mean_hops"] = float(np.mean(demand_hops)) if demand_hops else float("nan")
    row["demand_sats_max_hops"] = max(demand_hops) if demand_hops else -1
    row["unmet_sats"] = len(unmet)
    row["feeder_mbps_total"] = float(
        sum(d.get("capacity", 0) for u, v, d in graph.edges(data=True) if edge_class(u, v, num_sats) == "feeder")
    )
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("demands_dir", type=Path, help="Directory with the stock demands.txt.")
    parser.add_argument("graph_dir", type=Path)
    parser.add_argument("cells_file", type=Path)
    parser.add_argument("flow_time_s", type=int)
    parser.add_argument("beam_policy")
    parser.add_argument("--duration", type=int, default=1)
    parser.add_argument("--constellation", default="starlink_5shells")
    parser.add_argument("--groundstations", default="ground_stations_starlink")
    parser.add_argument("--country", default="haiti")
    parser.add_argument("--ku", type=float, default=1.28)
    parser.add_argument("--isl-scale", type=float, default=1.0)
    parser.add_argument("--gw-scale", type=float, default=1.0)
    parser.add_argument("--out", type=Path, required=True, help="Output CSV (one row per snapshot).")
    args = parser.parse_args()

    num_sats = len(gc.read_tles(str(gc.constellation_dir(args.constellation) / "tles.txt"))["satellites"])
    demands = gc.load_demands(gc.resolve_path(args.demands_dir) / "demands.txt")
    rows: List[Dict[str, float]] = []
    original = gc.max_flow_capacities

    def wrapped(demands_arg, graph, super_source, super_sink, n):
        scale_capacities(graph, n, args.isl_scale, args.gw_scale, super_node=super_sink)
        capacity, flow_dict = original(demands_arg, graph, super_source, super_sink, n)
        row = census_snapshot(graph, flow_dict, demands_arg, num_sats)
        row["timestamp_ns"] = (args.flow_time_s + len(rows)) * 1_000_000_000
        row["isl_scale"] = args.isl_scale
        row["gw_scale"] = args.gw_scale
        assert abs(row["delivered_mbps"] - capacity) < 1e-6
        rows.append(row)
        return capacity, flow_dict

    gc.max_flow_capacities = wrapped
    with tempfile.TemporaryDirectory() as scratch:
        flow_path, _ = gc.generate_capacities(
            Path(scratch), args.graph_dir, args.constellation, args.groundstations, args.cells_file,
            args.country, args.flow_time_s, args.beam_policy, args.ku,
            duration_s=args.duration, routing_policy="max_flow", demands_dir=args.demands_dir,
        )
        stock_totals = [float(line.split(",")[1]) for line in flow_path.read_text().split()]
    gc.max_flow_capacities = original

    for row, total in zip(rows, stock_totals):
        assert abs(row["delivered_mbps"] - total) < 1e-6, "census graph diverged from stock routing"

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["timestamp_ns"] + [k for k in rows[0] if k != "timestamp_ns"]
    with args.out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} snapshot rows to {args.out}")


if __name__ == "__main__":
    main()
