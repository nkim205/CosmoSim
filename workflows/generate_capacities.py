#!/usr/bin/env python3
"""Single-scenario helper to compute satellite capacities, mirroring generate_flows arguments."""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
from pathlib import Path
from typing import Dict, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

import networkx as nx
import numpy as np
from networkx.algorithms.flow import max_flow_min_cost

import utils.global_variables as global_vars
from spectrum_management.beam_mapping import NEW_POLICIES
from traffic_engineering.hot_potato import hot_potato_modifications
from utils.ground_stations import read_ground_stations_extended
from utils.tles import read_tles
CONSTELLATION_ROOT = PROJECT_ROOT / "constellation_configurations" / "configs"
GROUNDSTATION_ROOT = PROJECT_ROOT / "inputs" / "groundstations"
CELLS_ROOT = PROJECT_ROOT / "inputs" / "cells"
CAPACITY_BEAM_POLICIES = ["greedy-uncoordinated", "greedy-coordinated"] + list(NEW_POLICIES)


def read_properties(path: Path) -> Dict[str, str]:
    properties: Dict[str, str] = {}
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            properties[key.strip()] = value.strip()
    if not properties:
        raise ValueError(f"No properties found in {path}")
    return properties


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def constellation_dir(constellation_name: str) -> Path:
    path = CONSTELLATION_ROOT / constellation_name
    if not path.exists():
        raise FileNotFoundError(
            f"Constellation '{constellation_name}' not found at {path}. "
            "Generate it under constellation_configurations/configs first."
        )
    return path


def groundstations_path(name: str) -> Path:
    filename = name if name.endswith(".txt") else f"{name}.txt"
    path = GROUNDSTATION_ROOT / filename
    if not path.exists():
        raise FileNotFoundError(f"Ground station catalogue '{name}' not found at {path}")
    return path


def validate_country(country: str) -> None:
    cells_path = CELLS_ROOT / f"{country}.txt"
    if not cells_path.exists():
        raise FileNotFoundError(
            f"Country '{country}' missing cells file at {cells_path}. "
            "Generate inputs/cells/{country}.txt first."
        )


def load_demands(demands_path: Path) -> np.ndarray:
    if not demands_path.exists():
        raise FileNotFoundError(f"Demands file not found: {demands_path}")
    values = np.atleast_1d(np.loadtxt(demands_path, dtype=float))
    if values.ndim != 1:
        raise ValueError(f"Demands file must be 1-D; got shape {values.shape} from {demands_path}")
    return values


def assign_sat_capacity(graph: nx.DiGraph, demands: np.ndarray, start_node: str, num_satellites: int) -> nx.DiGraph:
    for sat in range(num_satellites):
        dummy = f"D{sat}"
        demand = float(demands[sat]) if sat < len(demands) else 0.0
        if demand <= 0:
            continue
        capacity = int(demand)
        graph.add_edge(dummy, start_node, capacity=capacity, weight=0)
        graph.add_edge(sat, dummy, capacity=capacity, weight=0)
    return graph


def max_flow_capacities(
    demands: np.ndarray,
    graph: nx.DiGraph,
    super_source: str,
    super_sink: str,
    num_satellites: int,
) -> Tuple[float, Dict[str, Dict[str, float]]]:
    graph = assign_sat_capacity(graph, demands, super_source, num_satellites)
    flow_dict = max_flow_min_cost(graph, super_sink, super_source)
    capacity = sum(flow_dict[super_sink].values())
    return capacity, flow_dict


def hot_potato_capacities(
    demands: np.ndarray,
    graph: nx.DiGraph,
    super_source: str,
    super_sink: str,
    num_satellites: int,
    num_groundstations: int,
) -> Tuple[float, Dict[str, Dict[str, float]]]:
    graph = hot_potato_modifications(graph, demands, num_groundstations, num_satellites)
    graph = assign_sat_capacity(graph, demands, super_source, num_satellites)
    flow_value, flow_dict = nx.maximum_flow(graph, super_sink, super_source)
    return flow_value, flow_dict


def _edge_capacity(graph: nx.DiGraph, u: int, v: int) -> int:
    data = graph[u][v]
    return int(data.get("capacity", 0))


def _increment_capacity(graph: nx.DiGraph, u: int, v: int, delta: float) -> None:
    graph[u][v]["capacity"] = int(graph[u][v].get("capacity", 0) + delta)


def generate_capacities(
    output_dir: Path,
    graph_dir: Path,
    constellation_name: str,
    groundstations_name: str,
    terminals_file: Path,
    country: str,
    flow_time_s: int,
    beam_policy: str,
    ku_band_capacity_gbps: float,
    *,
    duration_s: int = 15,
    routing_policy: str = "max_flow",
    update_interval_ms: int = 1000,
    demands_dir: Path | None = None,
) -> Tuple[Path, Path]:
    output_dir = resolve_path(output_dir)
    graph_dir = resolve_path(graph_dir)
    terminals_file = resolve_path(terminals_file)
    if not terminals_file.exists():
        raise FileNotFoundError(f"Terminal allocation file not found: {terminals_file}")
    validate_country(country)
    if beam_policy not in CAPACITY_BEAM_POLICIES:
        raise ValueError("Beam policy must match CosmoSim beam mapping choices.")

    demands_base = resolve_path(demands_dir) if demands_dir is not None else output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    constellation_path = constellation_dir(constellation_name)
    groundstations_file = groundstations_path(groundstations_name)

    ground_stations = read_ground_stations_extended(str(groundstations_file))
    tles = read_tles(str(constellation_path / "tles.txt"))
    satellites = tles["satellites"]

    description = read_properties(constellation_path / "description.txt")
    num_orbits = json.loads(description["num_orbits"])
    num_sats_per_orbit = json.loads(description["num_sats_per_orbit"])
    total_sats = sum(o * s for o, s in zip(num_orbits, num_sats_per_orbit))
    if total_sats != len(satellites):
        raise ValueError(
            f"Constellation metadata inconsistent: description lists {total_sats} satellites, "
            f"but TLE contains {len(satellites)} entries."
        )

    if duration_s <= 0:
        raise ValueError("Duration must be positive.")
    if update_interval_ms <= 0:
        raise ValueError("Update interval must be positive.")

    start_ns = flow_time_s * 1_000_000_000
    end_ns = (flow_time_s + duration_s) * 1_000_000_000
    interval_ns = update_interval_ms * 1_000_000

    demands_path = demands_base / "demands.txt"
    demands = load_demands(demands_path)

    flow_path = output_dir / f"{routing_policy}_{flow_time_s}.txt"
    flow_dict_path = output_dir / f"flow_dict_{routing_policy}_{flow_time_s}.json"
    flow_path.write_text("")

    gs_base_index = len(satellites)
    ut_base_index = len(satellites) + len(ground_stations)
    subgraph_nodes = list(range(len(satellites) + len(ground_stations)))

    final_flow_dict: Dict[str, Dict[str, float]] = {}
    for timestamp in range(start_ns, end_ns, interval_ns):
        graph_path = graph_dir / f"graph_{timestamp}.txt"
        if not graph_path.exists():
            raise FileNotFoundError(f"Graph snapshot not found: {graph_path}")
        with graph_path.open("rb") as fh:
            graph_data = pickle.load(fh)

        di_graph = nx.DiGraph(graph_data.subgraph(subgraph_nodes))
        gs_capacity_used: Dict[int, float] = {
            idx + gs_base_index: 0.0 for idx in range(len(ground_stations))
        }
        sat_capacity: Dict[int, float] = {sat: 0.0 for sat in range(len(satellites))}

        non_zero_sats = np.nonzero(demands)[0]
        for sat in non_zero_sats:
            sat_idx = int(sat)
            if not di_graph.has_node(sat_idx):
                continue
            predecessors = list(di_graph.predecessors(sat_idx))
            gs_neighbors = [
                node
                for node in predecessors
                if isinstance(node, int) and gs_base_index <= node < ut_base_index
            ]
            if not gs_neighbors:
                continue
            gs_neighbors.sort(key=lambda neighbor: gs_capacity_used[neighbor])

            for neighbor in gs_neighbors:
                if (
                    sat_capacity[sat_idx] >= global_vars.ground_station_sat_capacity
                    or gs_capacity_used[neighbor] >= global_vars.ground_station_gsl_capacity
                ):
                    continue
                ka_beams_required = min(
                    math.floor(demands[sat_idx] / global_vars.ka_beam_capacity),
                    8 - int(sat_capacity[sat_idx] // global_vars.ka_beam_capacity),
                )
                if ka_beams_required <= 0:
                    continue
                gs_capacity = min(
                    global_vars.ground_station_gsl_capacity - gs_capacity_used[neighbor],
                    ka_beams_required * global_vars.ka_beam_capacity,
                )
                gs_capacity = (gs_capacity // global_vars.ka_beam_capacity) * global_vars.ka_beam_capacity
                if gs_capacity <= 0:
                    continue
                _increment_capacity(di_graph, neighbor, sat_idx, gs_capacity)
                gs_capacity_used[neighbor] += gs_capacity
                sat_capacity[sat_idx] += gs_capacity

        for sat in range(len(satellites)):
            if sat_capacity[sat] >= global_vars.sat_gs_max_capacity or not di_graph.has_node(sat):
                continue
            predecessors = list(di_graph.predecessors(sat))
            gs_neighbors = [
                node
                for node in predecessors
                if isinstance(node, int) and gs_base_index <= node < ut_base_index
            ]
            if not gs_neighbors:
                continue
            gs_neighbors.sort(key=lambda neighbor: gs_capacity_used[neighbor])
            for neighbor in gs_neighbors:
                if sat_capacity[sat] >= global_vars.sat_gs_max_capacity:
                    break
                extra = min(
                    global_vars.sat_gs_max_capacity - sat_capacity[sat],
                    global_vars.ground_station_gsl_capacity - gs_capacity_used[neighbor],
                )
                if extra <= 0:
                    continue
                _increment_capacity(di_graph, neighbor, sat, extra)
                sat_capacity[sat] += extra
                gs_capacity_used[neighbor] += extra

        for sat in range(len(satellites)):
            if not di_graph.has_node(sat):
                continue
            predecessors = list(di_graph.predecessors(sat))
            for neighbor in predecessors:
                if isinstance(neighbor, int) and gs_base_index <= neighbor < ut_base_index:
                    if di_graph.has_edge(neighbor, sat) and _edge_capacity(di_graph, neighbor, sat) == 0:
                        di_graph.remove_edge(neighbor, sat)

        if math.isclose(ku_band_capacity_gbps, 2.5, rel_tol=1e-3):
            for sat in range(len(satellites)):
                isl_neighbors = [
                    node for node in di_graph.predecessors(sat) if isinstance(node, int) and node < gs_base_index
                ]
                for neighbor in isl_neighbors:
                    di_graph[neighbor][sat]["capacity"] = global_vars.isl_capacity * 2

        super_source = "S"
        super_sink = "T"
        di_graph.add_node(super_source)
        di_graph.add_node(super_sink)

        for gs in ground_stations:
            node_id = len(satellites) + gs["gid"]
            di_graph.add_edge(super_sink, node_id, capacity=global_vars.ground_station_gsl_capacity, weight=0)

        if routing_policy == "max_flow":
            capacity, flow_dict = max_flow_capacities(
                demands, di_graph, super_source, super_sink, len(satellites)
            )
        elif routing_policy == "hot_potato":
            capacity, flow_dict = hot_potato_capacities(
                demands, di_graph, super_source, super_sink, len(satellites), len(ground_stations)
            )
        else:
            raise ValueError(f"Unsupported routing policy '{routing_policy}'")

        final_flow_dict = flow_dict
        with flow_path.open("a", encoding="utf-8") as fh:
            fh.write(f"{timestamp},{capacity}\n")

    with flow_dict_path.open("w", encoding="utf-8") as fh:
        json.dump(final_flow_dict, fh)

    return flow_path, flow_dict_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate per-snapshot satellite->ground capacities for a scenario."
    )
    parser.add_argument("output_dir", type=Path, help="Directory to store capacity time-series.")
    parser.add_argument("graph_dir", type=Path, help="Directory containing graph_*.txt snapshots.")
    parser.add_argument("constellation", help="Constellation name under constellation_configurations/configs.")
    parser.add_argument("groundstations", help="Ground station file prefix under inputs/groundstations.")
    parser.add_argument(
        "cells_file",
        type=Path,
        help="Terminal allocation file (relative to repo root or terminal_deployment/terminals).",
    )
    parser.add_argument("country", help="Country name (matches inputs/cells/<country>.txt).")
    parser.add_argument("flow_time_s", type=int, help="Simulation time (seconds) for the snapshot.")
    parser.add_argument(
        "beam_policy",
        choices=CAPACITY_BEAM_POLICIES,
        help="Beam-mapping policy used when generating demands (for bookkeeping).",
    )
    parser.add_argument(
        "ku_band_capacity",
        type=float,
        help="Available KU-band capacity per beam in Gbps (e.g., 1.28).",
    )
    parser.add_argument(
        "--routing",
        choices=["max_flow", "hot_potato"],
        default="max_flow",
        help="Routing policy for forwarding (default: max_flow).",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=15,
        help="Duration (seconds) to cover starting from flow_time_s. Default: 15s.",
    )
    parser.add_argument(
        "--update-interval-ms",
        type=int,
        default=1000,
        help="Graph sampling interval in milliseconds. Default: 1000ms.",
    )
    parser.add_argument(
        "--demands-dir",
        type=Path,
        help="Directory containing demands.txt (defaults to output_dir).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    flow_path, flow_dict_path = generate_capacities(
        args.output_dir,
        args.graph_dir,
        args.constellation,
        args.groundstations,
        args.cells_file,
        args.country,
        args.flow_time_s,
        args.beam_policy,
        args.ku_band_capacity,
        duration_s=args.duration,
        routing_policy=args.routing,
        update_interval_ms=args.update_interval_ms,
        demands_dir=args.demands_dir,
    )
    print(f"Wrote capacity samples to {flow_path}")
    print(f"Wrote final flow dictionary to {flow_dict_path}")


if __name__ == "__main__":
    main()
