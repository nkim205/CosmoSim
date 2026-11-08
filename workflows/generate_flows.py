#!/usr/bin/env python3
"""Single-scenario helper to build satellite demands using CosmoSim beam mapping."""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

import exputil

from spectrum_management.beam_mapping import POLICY_NAMES, beam_mapping
from utils.cells import read_cells
from utils.ground_stations import read_ground_stations_extended
from utils.tles import read_tles
import utils.global_variables as global_vars
CONSTELLATION_ROOT = PROJECT_ROOT / "constellation_configurations" / "configs"
GROUNDSTATION_ROOT = PROJECT_ROOT / "inputs" / "groundstations"
CELLS_ROOT = PROJECT_ROOT / "inputs" / "cells"
TERMINAL_ROOT = PROJECT_ROOT / "terminal_deployment" / "terminals"
MAX_CHANNELS_PER_CELL = 8


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def load_cell_population(country: str, cell_ids: Iterable[str]) -> Dict[str, int]:
    population = {cell: 0 for cell in cell_ids}
    cells_path = CELLS_ROOT / f"{country}.txt"
    if not cells_path.exists():
        raise FileNotFoundError(
            f"Population file not found for '{country}'. Expected: {cells_path}"
        )

    with cells_path.open() as fh:
        header_skipped = False
        for line in fh:
            line = line.strip()
            if not line:
                continue
            if not header_skipped:
                header_skipped = True
                continue
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 2:
                continue
            cell, pop = parts[:2]
            if cell in population:
                population[cell] = int(float(pop))
    return population


def shell_satellite_ranges(constellation_dir: Path) -> List[Sequence[int]]:
    description = exputil.PropertiesConfig(str(constellation_dir / "description.txt"))
    num_orbits = json.loads(description.get_property_or_fail("num_orbits"))
    num_sats_per_orbit = json.loads(description.get_property_or_fail("num_sats_per_orbit"))

    ranges: List[Sequence[int]] = []
    start = 0
    for orbits, sats_per_orbit in zip(num_orbits, num_sats_per_orbit):
        count = orbits * sats_per_orbit
        ranges.append((start, start + count))
        start += count
    return ranges


def resolve_terminals_path(cells_file: Path) -> Path:
    if cells_file.is_absolute() and cells_file.exists():
        return cells_file
    candidate = resolve_path(cells_file)
    if candidate.exists():
        return candidate
    fallback = TERMINAL_ROOT / cells_file.name
    if fallback.exists():
        return fallback
    raise FileNotFoundError(f"Terminal allocation file not found: {cells_file}")


def generate_flows(
    output_dir: Path,
    graph_dir: Path,
    constellation_name: str,
    groundstations_name: str,
    terminals_file: Path,
    country: str,
    flow_time_s: int,
    beam_policy: str,
    ku_band_capacity_gbps: float,
    isl_scale: float = 1.0,
    gw_scale: float = 1.0,
    scored_rf_gamma: float | None = None,
    scored_rf_beta: float | None = None,
    scored_rf_use_gateway: bool | None = None,
    scored_rf_use_isl: bool | None = None,
) -> Path:
    output_dir = resolve_path(output_dir)
    graph_dir = resolve_path(graph_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    constellation_dir = CONSTELLATION_ROOT / constellation_name
    if not constellation_dir.exists():
        raise FileNotFoundError(
            f"Constellation '{constellation_name}' not found at {constellation_dir}"
        )

    groundstations_path = GROUNDSTATION_ROOT / f"{groundstations_name}.txt"
    if not groundstations_path.exists():
        raise FileNotFoundError(
            f"Ground stations '{groundstations_name}' not found at {groundstations_path}"
        )

    terminals_path = resolve_terminals_path(terminals_file)

    ground_stations = read_ground_stations_extended(str(groundstations_path))
    cells = [cell for cell in read_cells(str(terminals_path)) if cell["num_terminals"] > 0]
    cell_count = len(cells)
    ground_station_count = len(ground_stations)

    tles = read_tles(str(constellation_dir / "tles.txt"))
    satellites = list(range(len(tles["satellites"])))
    satellite_count = len(satellites)

    shell_ranges = shell_satellite_ranges(constellation_dir)
    users_per_channel = max(1, math.floor(ku_band_capacity_gbps * 10))

    timestamp = flow_time_s * 1000 * 1000 * 1000
    graph_path = graph_dir / f"graph_{timestamp}.txt"
    if not graph_path.exists():
        raise FileNotFoundError(f"Graph snapshot not found: {graph_path}")
    with graph_path.open("rb") as fh:
        graph = pickle.load(fh)

    gs_base_index = len(satellites)
    ut_base_index = len(satellites) + len(ground_stations)

    sat_demands = {sat: 0 for sat in satellites}
    cell_satellites: Dict[str, List[int]] = {}
    satellite_cells: Dict[int, List[str]] = {}
    all_cell_satellites = set()

    for cell in cells:
        cell_id = cell["cell"]
        current_sats: List[int] = []
        for sat in graph.predecessors(cell_id):
            sat_neighbors = list(graph.predecessors(sat))
            if any(isinstance(neighbor_id, int) and neighbor_id < ut_base_index for neighbor_id in sat_neighbors):
                current_sats.append(sat)
        cell_satellites[cell_id] = current_sats
        for sat in current_sats:
            satellite_cells.setdefault(sat, []).append(cell_id)
        all_cell_satellites.update(current_sats)

    cell_population = load_cell_population(country, (cell["cell"] for cell in cells))
    config_id = f"{constellation_name}_cells_{country}"

    print(
        f"[info] Loaded {cell_count} populated cells, {ground_station_count} ground stations, "
        f"{satellite_count} satellites for {constellation_name}/{country} (t={flow_time_s}s)."
    )
    global_vars.current_simulation_time_s = flow_time_s
    # Capacity-aware policies (e.g. scored-rf) read these to match generate_capacities_scaled.
    global_vars.isl_scale = float(isl_scale)
    global_vars.gw_scale = float(gw_scale)
    if scored_rf_gamma is not None:
        global_vars.scored_rf_gamma = float(scored_rf_gamma)
    if scored_rf_beta is not None:
        global_vars.scored_rf_beta = float(scored_rf_beta)
    if scored_rf_use_gateway is not None:
        global_vars.scored_rf_use_gateway = bool(scored_rf_use_gateway)
    if scored_rf_use_isl is not None:
        global_vars.scored_rf_use_isl = bool(scored_rf_use_isl)
    # Cross-second fairness history for scored-rf (shared across t* under the same scale dir).
    policy_norm = beam_policy.replace("_", "-").lower()
    if policy_norm == "scored-rf" or policy_norm.startswith("scored-rf-"):
        hist_path = output_dir.parent / "scored_rf_history.json"
        global_vars.scored_rf_history_path = str(hist_path)
        # Always reload from this scale dir's file (isolated per policy/scale; fresh process
        # per second). Unit tests inject history by calling assign_beams directly.
        if hist_path.exists():
            with hist_path.open() as fh:
                payload = json.load(fh)
            satisfaction = payload.get("satisfaction", payload) if isinstance(payload, dict) else {}
            global_vars.scored_rf_history = {str(k): float(v) for k, v in satisfaction.items()}
        else:
            global_vars.scored_rf_history = {}
    # Wall time for the RF allocation / beam-mapping algorithm only (not graph I/O).
    alloc_t0 = time.perf_counter()
    mapping = beam_mapping(
        beam_policy,
        cells,
        all_cell_satellites,
        satellite_cells,
        cell_satellites,
        config_id,
        shell_ranges,
        users_per_channel,
        cell_population,
    )
    allocation_runtime_s = time.perf_counter() - alloc_t0
    (output_dir / "allocation_runtime_s.txt").write_text(f"{allocation_runtime_s:.6f}\n")
    print(f"[info] Beam allocation runtime: {allocation_runtime_s:.4f}s")

    beam_assignments_path = output_dir / f"beam_assignments_{timestamp}.pkl"
    with beam_assignments_path.open("wb") as fh:
        pickle.dump(mapping, fh)
    print(f"[info] Wrote beam assignments to {beam_assignments_path}")
    
    total_channels = cell_count * MAX_CHANNELS_PER_CELL
    allocated_slots = len(mapping)
    unique_beams = len(set(mapping.values()))
    active_cells = len({key.split("_")[0] for key in mapping})
    print(
        f"[info] Beam mapping assigned {allocated_slots} of {total_channels} channel slots "
        f"across {active_cells} cells ({unique_beams} unique satellite/beam pairs)."
    )

    for cell in cells:
        cell_id = cell["cell"]
        num_terminals = cell["num_terminals"]
        dummy_nodes = [f"{cell_id}_{idx}" for idx in range(MAX_CHANNELS_PER_CELL)]
        mapped_nodes = [node for node in dummy_nodes if node in mapping]
        if not mapped_nodes:
            continue

        num_channels = len(mapped_nodes)
        allocations = [
            num_terminals // num_channels + (1 if i < num_terminals % num_channels else 0)
            for i in range(num_channels)
        ]
        for idx, channel in enumerate(mapped_nodes):
            sat = int(mapping[channel].split("_")[1])
            channel_demand = min(
                allocations[idx] * global_vars.user_terminal_gsl_capacity,
                ku_band_capacity_gbps * 1000,
            )
            sat_demands[sat] += channel_demand

    demands_path = output_dir / "demands.txt"
    with demands_path.open("w") as fh:
        for sat in satellites:
            fh.write(f"{sat_demands[sat]}\n")

    return demands_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a single demands.txt file for a given snapshot."
    )
    parser.add_argument("output_dir", type=Path, help="Directory to store demands output.")
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
        choices=POLICY_NAMES,
        help="Beam-mapping policy to use.",
    )
    parser.add_argument(
        "ku_band_capacity",
        type=float,
        help="Available KU-band capacity per beam in Gbps (e.g., 1.28).",
    )
    parser.add_argument(
        "--isl-scale",
        type=float,
        default=1.0,
        help="Multiply ISL capacities for capacity-aware beam policies (default 1.0).",
    )
    parser.add_argument(
        "--gw-scale",
        type=float,
        default=1.0,
        help="Multiply gateway feeder + GS capacities for capacity-aware beam policies (default 1.0).",
    )
    parser.add_argument(
        "--scored-rf-gamma",
        type=float,
        default=None,
        help="Override scored-rf congestion weight gamma (default: module GAMMA).",
    )
    parser.add_argument(
        "--scored-rf-beta",
        type=float,
        default=None,
        help="Override scored-rf fairness weight beta (0 disables fairness; default: module BETA).",
    )
    parser.add_argument(
        "--scored-rf-use-gateway",
        type=int,
        choices=[0, 1],
        default=None,
        help="Override scored-rf gateway congestion awareness (1/0). PR1 Methods 3/4.",
    )
    parser.add_argument(
        "--scored-rf-use-isl",
        type=int,
        choices=[0, 1],
        default=None,
        help="Override scored-rf ISL congestion awareness (1/0). PR1 Methods 3/4.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    # Avoid leaking history across sequential CLI invocations in the same process.
    if hasattr(global_vars, "scored_rf_history"):
        delattr(global_vars, "scored_rf_history")
    for attr in ("scored_rf_use_gateway", "scored_rf_use_isl", "scored_rf_gamma", "scored_rf_beta"):
        if hasattr(global_vars, attr):
            delattr(global_vars, attr)
    demands_path = generate_flows(
        args.output_dir,
        args.graph_dir,
        args.constellation,
        args.groundstations,
        args.cells_file,
        args.country,
        args.flow_time_s,
        args.beam_policy,
        args.ku_band_capacity,
        isl_scale=args.isl_scale,
        gw_scale=args.gw_scale,
        scored_rf_gamma=args.scored_rf_gamma,
        scored_rf_beta=args.scored_rf_beta,
        scored_rf_use_gateway=(None if args.scored_rf_use_gateway is None else bool(args.scored_rf_use_gateway)),
        scored_rf_use_isl=(None if args.scored_rf_use_isl is None else bool(args.scored_rf_use_isl)),
    )
    print(f"Wrote demands to {demands_path}")


if __name__ == "__main__":
    main()
