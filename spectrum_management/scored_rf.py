"""Scored RF allocation: unmet demand + optional gateway/ISL congestion.

Option 2: score feasible cell-satellite pairs and greedily assign one channel at a time.

    Score = alpha * D + beta * F - gamma * C

D = normalized unmet demand (offered RF need minus already allocated).
F = fairness (not wired yet; beta defaults to 0).
C = congestion from route residual capacity vs traffic a new channel would add.
With USE_GATEWAY / USE_ISL, residual is the best available egress estimate:
  - local feeder budget (sat_gs_max_capacity - sat load) if the sat has a GS neighbor
  - and/or 1-hop ISL to a gateway-visible neighbor (min of ISL free and neighbor feeder)

Ablations (Methods 3-5) are the same loop with different flags/weights.
"""

from __future__ import annotations

import pickle
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Set, Tuple

from utils import global_variables as global_vars

from .common import candidate_sats, initialize_beam_state
from .constants import MAX_CHANNELS_PER_CELL
from .greedy_coordinated import _order_satellites
from .interference import check_interference

ROOT = Path(__file__).resolve().parents[1]
GRAPH_DIR = ROOT / "graph_generation" / "graphs_noglobal" / "starlink_5shells" / "haiti"

# Weights from the project sketch; fairness off until per-cell history exists.
ALPHA = 0.5
BETA = 0.0
GAMMA = 0.2

# Congestion feature flags.
# Method 3: gateway on, ISL off | Method 4: gateway off, ISL on | full: both on.
USE_GATEWAY = True
USE_ISL = True


def _offered_mbps(num_terminals: int) -> float:
    return float(num_terminals * global_vars.user_terminal_gsl_capacity)


def _channel_admit_mbps(terminals_on_ch: int) -> float:
    return min(
        terminals_on_ch * global_vars.user_terminal_gsl_capacity,
        float(global_vars.ku_beam_capacity),
    )


def _allocated_mbps(num_terminals: int, num_channels: int) -> float:
    if num_channels <= 0 or num_terminals <= 0:
        return 0.0
    total = 0.0
    for i in range(num_channels):
        terminals_on_ch = num_terminals // num_channels + (1 if i < num_terminals % num_channels else 0)
        total += _channel_admit_mbps(terminals_on_ch)
    return total


def _unmet_mbps(num_terminals: int, num_channels: int) -> float:
    return max(0.0, _offered_mbps(num_terminals) - _allocated_mbps(num_terminals, num_channels))


def _contrib_to_sat(num_terminals: int, sats: Sequence[int], sat: int) -> float:
    """Admitted Mbps this cell places on ``sat`` given its current channel→sat list."""
    n = len(sats)
    if n == 0 or num_terminals <= 0:
        return 0.0
    total = 0.0
    for i, s in enumerate(sats):
        if s != sat:
            continue
        terminals_on_ch = num_terminals // n + (1 if i < num_terminals % n else 0)
        total += _channel_admit_mbps(terminals_on_ch)
    return total


def _load_graph():
    t = int(getattr(global_vars, "current_simulation_time_s", 0))
    path = GRAPH_DIR / f"graph_{t * 10**9}.txt"
    with path.open("rb") as fh:
        return pickle.load(fh)


def _gateway_caps(graph, num_satellites: int) -> Dict[int, float]:
    """Feeder budget per sat: sat_gs_max_capacity if any GS neighbor, else 0."""
    cap = float(global_vars.sat_gs_max_capacity)
    out: Dict[int, float] = {}
    for sat in range(num_satellites):
        if sat not in graph:
            out[sat] = 0.0
            continue
        has_gs = any(isinstance(n, int) and n >= num_satellites for n in graph.predecessors(sat))
        out[sat] = cap if has_gs else 0.0
    return out


def _isl_adjacency(graph, num_satellites: int) -> Dict[int, List[Tuple[int, float]]]:
    """sat -> [(neighbor_sat, isl_capacity_mbps), ...] for satellite↔satellite edges."""
    adj: Dict[int, List[Tuple[int, float]]] = defaultdict(list)
    for u, v, data in graph.edges(data=True):
        if isinstance(u, int) and isinstance(v, int) and u < num_satellites and v < num_satellites:
            adj[u].append((v, float(data.get("capacity", 0))))
    return adj


def _route_residual(
    sat: int,
    sat_load: Mapping[int, float],
    gateway_caps: Mapping[int, float],
    isl_adj: Mapping[int, Sequence[Tuple[int, float]]],
) -> float:
    """Best egress residual (Mbps) under the active USE_GATEWAY / USE_ISL flags."""
    load_s = sat_load.get(sat, 0.0)
    local_gw = max(0.0, gateway_caps.get(sat, 0.0) - load_s)

    isl_best = 0.0
    if USE_ISL:
        for nbr, cap in isl_adj.get(sat, ()):
            if gateway_caps.get(nbr, 0.0) <= 0:
                continue
            # If this sat has no local feeder, its current load contends for the ISL.
            if gateway_caps.get(sat, 0.0) > 0:
                isl_free = cap
            else:
                isl_free = max(0.0, cap - load_s)
            nbr_gw = max(0.0, gateway_caps.get(nbr, 0.0) - sat_load.get(nbr, 0.0))
            isl_best = max(isl_best, min(isl_free, nbr_gw))

    if USE_GATEWAY and USE_ISL:
        return max(local_gw, isl_best)
    if USE_GATEWAY:
        return local_gw
    if USE_ISL:
        # Method 4: only penalize ISL-limited egress; local-GS sats are fine on this axis.
        if gateway_caps.get(sat, 0.0) > 0:
            return float("inf")
        return isl_best
    return float("inf")


def _congestion(
    sat: int,
    additional_mbps: float,
    sat_load: Mapping[int, float],
    gateway_caps: Mapping[int, float],
    isl_adj: Mapping[int, Sequence[Tuple[int, float]]],
) -> float:
    """C = 1 - min(1, residual / additional)."""
    if additional_mbps <= 0:
        return 0.0
    residual = _route_residual(sat, sat_load, gateway_caps, isl_adj)
    if residual == float("inf"):
        return 0.0
    return 1.0 - min(1.0, residual / additional_mbps)


def _find_assignment(
    cell_id: str,
    sat: int,
    mapping: Mapping[str, str],
    beams_available: Set[str],
) -> Optional[Tuple[str, str]]:
    """Return (dummy_key, beam_id) for the first feasible channel/color on this sat, else None."""
    for channel_idx in range(MAX_CHANNELS_PER_CELL):
        dummy = f"{cell_id}_{channel_idx}"
        if dummy in mapping:
            continue
        for freq in range(global_vars.spatial_channel_reuse_factor):
            beam_id = f"{freq}_{sat}_{channel_idx}"
            if beam_id in beams_available and check_interference(cell_id, mapping, beam_id):
                return dummy, beam_id
    return None


def assign_beams(
    prepared_cells: Sequence[Mapping[str, int]],
    satellites: Sequence[int],
    satellite_cells: Mapping[int, Sequence[str]],
    cell_satellites: Mapping[str, Sequence[int]],
    config: str,
    shell_satellite_indices: Sequence[Sequence[int]],
    users_per_channel: int,
    cell_population: Mapping[str, int],
) -> Dict[str, str]:
    del satellite_cells, config, users_per_channel, cell_population

    if not satellites or not prepared_cells:
        return {}

    terminals = {str(cell["cell"]): int(cell["num_terminals"]) for cell in prepared_cells}
    beams_available, sat_cells_assigned = initialize_beam_state(satellites)
    mapping: Dict[str, str] = {}
    cell_sats: Dict[str, List[int]] = {cid: [] for cid in terminals}
    sat_load: Dict[int, float] = defaultdict(float)
    num_shells = len(shell_satellite_indices)
    num_satellites = max((end for _, end in shell_satellite_indices), default=max(satellites) + 1)

    gateway_caps: Dict[int, float] = {}
    isl_adj: Dict[int, List[Tuple[int, float]]] = {}
    if GAMMA != 0 and (USE_GATEWAY or USE_ISL):
        graph = _load_graph()
        gateway_caps = _gateway_caps(graph, num_satellites)
        if USE_ISL:
            isl_adj = _isl_adjacency(graph, num_satellites)

    max_assignments = len(terminals) * MAX_CHANNELS_PER_CELL
    for _ in range(max_assignments):
        unmet = {cid: _unmet_mbps(n, len(cell_sats[cid])) for cid, n in terminals.items()}
        max_unmet = max(unmet.values(), default=0.0)
        if max_unmet <= 0:
            break

        best: Optional[Tuple[float, str, int, str, str]] = None

        for cell_id, n_term in terminals.items():
            if unmet[cell_id] <= 0:
                continue
            d_norm = unmet[cell_id] / max_unmet
            fairness = 0.0  # beta term reserved
            old_sats = cell_sats[cell_id]
            candidates = _order_satellites(
                candidate_sats(cell_id, cell_satellites),
                shell_satellite_indices,
                sat_cells_assigned,
                num_shells,
            )
            for sat in candidates:
                found = _find_assignment(cell_id, sat, mapping, beams_available)
                if found is None:
                    continue
                dummy, beam_id = found
                new_sats = old_sats + [sat]
                additional = _contrib_to_sat(n_term, new_sats, sat) - _contrib_to_sat(n_term, old_sats, sat)

                congestion = 0.0
                if GAMMA != 0 and (USE_GATEWAY or USE_ISL):
                    congestion = _congestion(sat, additional, sat_load, gateway_caps, isl_adj)

                score = ALPHA * d_norm + BETA * fairness - GAMMA * congestion
                key = (score, unmet[cell_id], cell_id, -sat)
                if best is None or key > (best[0], unmet[best[1]], best[1], -best[2]):
                    best = (score, cell_id, sat, dummy, beam_id)

        if best is None:
            break

        _, cell_id, sat, dummy, beam_id = best
        n_term = terminals[cell_id]
        old_sats = cell_sats[cell_id]
        new_sats = old_sats + [sat]
        touched = set(old_sats) | {sat}
        for s in touched:
            sat_load[s] -= _contrib_to_sat(n_term, old_sats, s)
        for s in touched:
            sat_load[s] += _contrib_to_sat(n_term, new_sats, s)
        cell_sats[cell_id] = new_sats
        mapping[dummy] = beam_id
        beams_available.remove(beam_id)
        sat_cells_assigned.setdefault(sat, []).append(cell_id)

    print(
        f"[beam-mapping] policy=scored-rf mapped_slots={len(mapping)} "
        f"gateway={USE_GATEWAY} isl={USE_ISL} gamma={GAMMA}",
        flush=True,
    )
    return mapping
