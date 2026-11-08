"""Post-routing edge capacities for utilization metrics.

Gateway and ISL utilization must use the same capacities the max-flow solver saw
(after Ka assignment and ``--isl-scale`` / ``--gw-scale``), not scored-rf residuals.

``generate_capacities_scaled`` dumps ``edge_caps_<routing>_<t>.json`` after scaling.
For older runs without that file, ``load_or_rebuild`` replays Ka assignment + scaling
from ``commands.txt`` (no max-flow re-solve).
"""

from __future__ import annotations

import json
import math
import pickle
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from traffic_engineering.capacity_scaling import scale_capacities  # noqa: E402
from utils import global_variables as global_vars  # noqa: E402
from utils.ground_stations import read_ground_stations_extended  # noqa: E402
from utils.tles import read_tles  # noqa: E402
from workflows import generate_capacities as gc  # noqa: E402

SUPER_SINK = "T"


def edge_caps_path(run_dir: Path, routing: str, t_s: int) -> Path:
    return run_dir / f"edge_caps_{routing}_{t_s}.json"


def serialize_edge_caps(graph: nx.DiGraph, num_satellites: int) -> Dict[str, Any]:
    """Classify capacity edges the routing solver uses for delivery."""
    gateways: List[Dict[str, float]] = []
    feeders: List[Dict[str, float]] = []
    isls: List[Dict[str, float]] = []

    for u, v, data in graph.edges(data=True):
        cap = float(data.get("capacity", 0) or 0)
        if cap <= 0:
            continue
        if u == SUPER_SINK and isinstance(v, int) and v >= num_satellites:
            gateways.append({"u": str(u), "v": int(v), "capacity_mbps": cap})
        elif (
            isinstance(u, int)
            and isinstance(v, int)
            and u >= num_satellites
            and v < num_satellites
        ):
            feeders.append({"u": int(u), "v": int(v), "capacity_mbps": cap})
        elif (
            isinstance(u, int)
            and isinstance(v, int)
            and u < num_satellites
            and v < num_satellites
        ):
            isls.append({"u": int(u), "v": int(v), "capacity_mbps": cap})

    return {
        "num_satellites": num_satellites,
        "gateway_agg": gateways,  # T -> GS aggregate
        "feeder": feeders,  # GS -> sat
        "isl": isls,
    }


def write_edge_caps(path: Path, graph: nx.DiGraph, num_satellites: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = serialize_edge_caps(graph, num_satellites)
    path.write_text(json.dumps(payload))
    return path


def load_edge_caps(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def _parse_caps_command(commands_txt: Path) -> Optional[Dict[str, Any]]:
    """Parse the generate_capacities_scaled line from commands.txt."""
    if not commands_txt.exists():
        return None
    caps_line = None
    for line in commands_txt.read_text().splitlines():
        if "generate_capacities" in line:
            caps_line = line.strip()
            break
    if not caps_line:
        return None

    # Tokenize respecting that paths may contain spaces only rarely; our cmds don't.
    parts = caps_line.split()
    # Find script index
    try:
        idx = next(i for i, p in enumerate(parts) if "generate_capacities" in p)
    except StopIteration:
        return None
    args = parts[idx + 1 :]

    def _flag(name: str, default: str) -> str:
        if name in args:
            return args[args.index(name) + 1]
        return default

    # Positionals after script: output_dir graph_dir constellation groundstations
    # cells_file country flow_time beam_policy ku_band [--flags...]
    if len(args) < 9:
        return None
    return {
        "output_dir": Path(args[0]),
        "graph_dir": Path(args[1]),
        "constellation": args[2],
        "groundstations": args[3],
        "cells_file": Path(args[4]),
        "country": args[5],
        "flow_time_s": int(args[6]),
        "beam_policy": args[7],
        "ku_band_capacity": float(args[8]),
        "routing": _flag("--routing", "max_flow"),
        "isl_scale": float(_flag("--isl-scale", "1.0")),
        "gw_scale": float(_flag("--gw-scale", "1.0")),
    }


def rebuild_edge_caps(run_dir: Path, t_s: int | None = None) -> Dict[str, Any]:
    """Replay Ka assignment + capacity scaling; do not run max-flow."""
    parsed = _parse_caps_command(run_dir / "commands.txt")
    if parsed is None:
        raise FileNotFoundError(f"Cannot rebuild edge caps: no capacities command in {run_dir}")

    if t_s is None:
        t_s = int(parsed["flow_time_s"])
    isl_scale = float(parsed["isl_scale"])
    gw_scale = float(parsed["gw_scale"])
    ku = float(parsed["ku_band_capacity"])

    graph_dir = gc.resolve_path(parsed["graph_dir"])
    constellation_path = gc.constellation_dir(parsed["constellation"])
    groundstations_file = gc.groundstations_path(parsed["groundstations"])
    ground_stations = read_ground_stations_extended(str(groundstations_file))
    tles = read_tles(str(constellation_path / "tles.txt"))
    satellites = tles["satellites"]
    description = gc.read_properties(constellation_path / "description.txt")
    num_orbits = json.loads(description["num_orbits"])
    num_sats_per_orbit = json.loads(description["num_sats_per_orbit"])
    total_sats = sum(o * s for o, s in zip(num_orbits, num_sats_per_orbit))
    if total_sats != len(satellites):
        raise ValueError("Constellation metadata inconsistent with TLE count.")

    demands = gc.load_demands(run_dir / "demands.txt")
    timestamp = t_s * 1_000_000_000
    graph_path = graph_dir / f"graph_{timestamp}.txt"
    with graph_path.open("rb") as fh:
        graph_data = pickle.load(fh)

    gs_base_index = len(satellites)
    ut_base_index = len(satellites) + len(ground_stations)
    subgraph_nodes = list(range(len(satellites) + len(ground_stations)))
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
            gc._increment_capacity(di_graph, neighbor, sat_idx, gs_capacity)
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
            gc._increment_capacity(di_graph, neighbor, sat, extra)
            sat_capacity[sat] += extra
            gs_capacity_used[neighbor] += extra

    for sat in range(len(satellites)):
        if not di_graph.has_node(sat):
            continue
        predecessors = list(di_graph.predecessors(sat))
        for neighbor in predecessors:
            if isinstance(neighbor, int) and gs_base_index <= neighbor < ut_base_index:
                if di_graph.has_edge(neighbor, sat) and gc._edge_capacity(di_graph, neighbor, sat) == 0:
                    di_graph.remove_edge(neighbor, sat)

    if math.isclose(ku, 2.5, rel_tol=1e-3):
        for sat in range(len(satellites)):
            isl_neighbors = [
                node for node in di_graph.predecessors(sat) if isinstance(node, int) and node < gs_base_index
            ]
            for neighbor in isl_neighbors:
                di_graph[neighbor][sat]["capacity"] = global_vars.isl_capacity * 2

    di_graph.add_node(SUPER_SINK)
    for gs in ground_stations:
        node_id = len(satellites) + gs["gid"]
        di_graph.add_edge(
            SUPER_SINK, node_id, capacity=global_vars.ground_station_gsl_capacity, weight=0
        )

    scale_capacities(di_graph, len(satellites), isl_scale, gw_scale, super_node=SUPER_SINK)
    return serialize_edge_caps(di_graph, len(satellites))


def load_or_rebuild(
    run_dir: Path,
    t_s: int,
    routing: str = "max_flow",
    *,
    cache: bool = True,
) -> Dict[str, Any]:
    path = edge_caps_path(run_dir, routing, t_s)
    if path.exists():
        return load_edge_caps(path)
    caps = rebuild_edge_caps(run_dir, t_s)
    if cache:
        path.write_text(json.dumps(caps))
    return caps


def parse_scales_from_dirname(scale_dir_name: str) -> Tuple[float, float]:
    """Parse ``isl1_gw0.5`` → (1.0, 0.5)."""
    m = re.fullmatch(r"isl(?P<isl>[0-9.]+)_gw(?P<gw>[0-9.]+)", scale_dir_name)
    if not m:
        raise ValueError(f"Unexpected scale dir name: {scale_dir_name}")
    return float(m.group("isl")), float(m.group("gw"))
