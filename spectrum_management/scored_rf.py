"""Scored RF allocation: unmet demand + fairness + shared gateway/ISL egress congestion.

Option 2: score feasible cell-satellite pairs and greedily assign one channel at a time.

    Score = alpha * D + beta * F - gamma * C

D = normalized unmet demand (offered RF need minus already allocated).
F = normalized underservice from recent service history (and this second's progress).
C = congestion from shared route residual vs traffic a new channel would add.

Unlike the first marie cut, downstream capacity is tracked as a shared pool:
  - per-sat feeder residual (sat_gs_max_capacity)
  - per-ground-station residual (ground_station_gsl_capacity)
  - per-ISL edge residual (graph capacity)

When a sat is given load, that load consumes residual on one chosen egress path
(local feeder+GS, or 1-hop ISL then neighbor feeder+GS). Later candidates see
the reduced pool, so two sats cannot both treat the same gateway/ISL as free.

Feeder/GS residuals are multiplied by ``global_vars.gw_scale`` and ISL residuals by
``global_vars.isl_scale`` (both default to 1.0) so congestion matches
``generate_capacities_scaled`` stress scenarios.

Cross-second fairness history is an EMA of estimated delivered/offered per cell,
updated by the experiment runner after routing.

Ablations (Methods 3-5) are the same loop with different flags/weights.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Set, Tuple

from utils import global_variables as global_vars

from .common import candidate_sats, initialize_beam_state
from .constants import MAX_CHANNELS_PER_CELL
from .greedy_coordinated import _order_satellites
from .interference import check_interference

# Weights from the project sketch.
ALPHA = 0.5
BETA = 0.3  # fairness on; override with global_vars.scored_rf_beta
GAMMA = 0.2

# EMA weight on prior satisfaction when updating history after a second.
HISTORY_EMA = 0.7
# Blend of historical vs this-second satisfaction when scoring F.
HISTORY_BLEND = 0.7

# Congestion feature flags.
# Method 3: gateway on, ISL off | Method 4: gateway off, ISL on | full: both on.
USE_GATEWAY = True
USE_ISL = True

# Experiment runner: re-assign beams per --gw-scale/--isl-scale instead of reusing one mapping.
CAPACITY_AWARE = True


def _capacity_scales() -> Tuple[float, float]:
    """Return (isl_scale, gw_scale) from global_vars; missing attrs mean 1.0."""
    isl = float(getattr(global_vars, "isl_scale", 1.0))
    gw = float(getattr(global_vars, "gw_scale", 1.0))
    if isl < 0 or gw < 0:
        raise ValueError(f"Capacity scales must be non-negative (isl_scale={isl}, gw_scale={gw}).")
    return isl, gw


def _gamma() -> float:
    """Congestion weight; override with global_vars.scored_rf_gamma for sweeps."""
    return float(getattr(global_vars, "scored_rf_gamma", GAMMA))


def _beta() -> float:
    """Fairness weight; override with global_vars.scored_rf_beta."""
    return float(getattr(global_vars, "scored_rf_beta", BETA))


def _use_gateway() -> bool:
    """Gateway congestion term; override with global_vars.scored_rf_use_gateway (PR1 Methods 3/4)."""
    return bool(getattr(global_vars, "scored_rf_use_gateway", USE_GATEWAY))


def _use_isl() -> bool:
    """ISL congestion term; override with global_vars.scored_rf_use_isl (PR1 Methods 3/4)."""
    return bool(getattr(global_vars, "scored_rf_use_isl", USE_ISL))


@dataclass
class SharedEgress:
    """Shared downstream residuals matching CosmoSim's limited egress resources."""

    feeder: Dict[int, float] = field(default_factory=dict)
    gs: Dict[int, float] = field(default_factory=dict)
    isl: Dict[Tuple[int, int], float] = field(default_factory=dict)
    isl_adj: Dict[int, List[int]] = field(default_factory=dict)
    sat_to_gs: Dict[int, List[int]] = field(default_factory=dict)
    routed_load: Dict[int, float] = field(default_factory=lambda: defaultdict(float))
    path_of: Dict[int, Optional[tuple]] = field(default_factory=dict)
    isl_scale: float = 1.0
    gw_scale: float = 1.0

    @classmethod
    def from_graph(cls, graph, num_satellites: int) -> "SharedEgress":
        isl_scale, gw_scale = _capacity_scales()
        feeder_cap = float("inf")
        gs_cap = float("inf")
        if _use_gateway():
            feeder_cap = float(global_vars.sat_gs_max_capacity) * gw_scale
            gs_cap = float(global_vars.ground_station_gsl_capacity) * gw_scale
        state = cls(isl_scale=isl_scale, gw_scale=gw_scale)

        sat_to_gs: Dict[int, List[int]] = defaultdict(list)
        gs_ids: Set[int] = set()
        isl_adj: Dict[int, List[int]] = defaultdict(list)
        for u, v, data in graph.edges(data=True):
            if not (isinstance(u, int) and isinstance(v, int)):
                continue
            if u >= num_satellites and v < num_satellites:
                sat_to_gs[v].append(u)
                gs_ids.add(u)
            elif u < num_satellites and v < num_satellites:
                cap = float(data.get("capacity", 0)) * isl_scale
                state.isl[(u, v)] = cap
                isl_adj[u].append(v)

        state.sat_to_gs = {sat: gss for sat, gss in sat_to_gs.items()}
        state.isl_adj = {sat: nbrs for sat, nbrs in isl_adj.items()}
        for gs in gs_ids:
            state.gs[gs] = gs_cap
        for sat in range(num_satellites):
            state.feeder[sat] = feeder_cap if sat in state.sat_to_gs else 0.0
            state.path_of[sat] = None
        return state

    def _best_gs(self, sat: int) -> Optional[Tuple[int, float]]:
        gss = self.sat_to_gs.get(sat) or ()
        if not gss:
            return None
        best_gs = None
        best_res = -1.0
        for gs in gss:
            res = self.gs.get(gs, 0.0)
            if res > best_res:
                best_res = res
                best_gs = gs
        if best_gs is None:
            return None
        return best_gs, best_res

    def best_egress(self, sat: int) -> Tuple[float, Optional[tuple]]:
        """Return (residual_mbps, path) under gateway/ISL awareness flags. Residual clipped at 0."""
        use_gw, use_isl = _use_gateway(), _use_isl()
        local_path = None
        local_res = 0.0
        if use_gw:
            gs_info = self._best_gs(sat)
            if gs_info is not None and self.feeder.get(sat, 0.0) > 0:
                gs, gs_res = gs_info
                local_res = max(0.0, min(self.feeder[sat], gs_res))
                local_path = ("local", sat, gs)

        isl_path = None
        isl_res = 0.0
        if use_isl:
            for nbr in self.isl_adj.get(sat, ()):
                if self.feeder.get(nbr, 0.0) <= 0:
                    continue
                gs_info = self._best_gs(nbr)
                if gs_info is None:
                    continue
                gs, gs_res = gs_info
                isl_cap = self.isl.get((sat, nbr), 0.0)
                cand = max(0.0, min(isl_cap, self.feeder[nbr], gs_res))
                if cand > isl_res:
                    isl_res = cand
                    isl_path = ("isl", sat, nbr, gs)

        if use_gw and use_isl:
            if local_res >= isl_res and local_path is not None:
                return local_res, local_path
            if isl_path is not None:
                return isl_res, isl_path
            return local_res, local_path
        if use_gw:
            return local_res, local_path
        if use_isl:
            # Method 4: sats with local feeder are unconstrained on this axis.
            if self.sat_to_gs.get(sat):
                return float("inf"), None
            return isl_res, isl_path
        return float("inf"), None

    def _release_path(self, path: tuple, amount: float) -> None:
        if amount <= 0 or path is None:
            return
        if path[0] == "local":
            _, sat, gs = path
            self.feeder[sat] = self.feeder.get(sat, 0.0) + amount
            if gs is not None:
                self.gs[gs] = self.gs.get(gs, 0.0) + amount
        elif path[0] == "isl":
            _, sat, nbr, gs = path
            self.isl[(sat, nbr)] = self.isl.get((sat, nbr), 0.0) + amount
            self.feeder[nbr] = self.feeder.get(nbr, 0.0) + amount
            if gs is not None:
                self.gs[gs] = self.gs.get(gs, 0.0) + amount

    def _consume_path(self, path: tuple, amount: float) -> None:
        if amount <= 0 or path is None:
            return
        if path[0] == "local":
            _, sat, gs = path
            self.feeder[sat] = self.feeder.get(sat, 0.0) - amount
            if gs is not None:
                self.gs[gs] = self.gs.get(gs, 0.0) - amount
        elif path[0] == "isl":
            _, sat, nbr, gs = path
            self.isl[(sat, nbr)] = self.isl.get((sat, nbr), 0.0) - amount
            self.feeder[nbr] = self.feeder.get(nbr, 0.0) - amount
            if gs is not None:
                self.gs[gs] = self.gs.get(gs, 0.0) - amount

    def set_sat_load(self, sat: int, new_load: float) -> None:
        """Rebind this sat's admitted load onto the current best shared egress path."""
        new_load = max(0.0, float(new_load))
        old_load = float(self.routed_load.get(sat, 0.0))
        old_path = self.path_of.get(sat)
        if old_load > 0 and old_path is not None:
            self._release_path(old_path, old_load)
        self.routed_load[sat] = 0.0
        self.path_of[sat] = None
        if new_load <= 0:
            return
        _, path = self.best_egress(sat)
        if path is None:
            # No modeled egress; keep load unrouted so C stays high for future adds.
            self.routed_load[sat] = new_load
            return
        self._consume_path(path, new_load)
        self.routed_load[sat] = new_load
        self.path_of[sat] = path


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


def _congestion(sat: int, additional_mbps: float, egress: SharedEgress) -> float:
    """C = 1 - min(1, residual / additional) using shared residuals."""
    if additional_mbps <= 0:
        return 0.0
    residual, _ = egress.best_egress(sat)
    if residual == float("inf"):
        return 0.0
    return 1.0 - min(1.0, max(0.0, residual) / additional_mbps)


def _satisfaction_this_second(num_terminals: int, num_channels: int) -> float:
    offered = _offered_mbps(num_terminals)
    if offered <= 0:
        return 1.0
    return min(1.0, _allocated_mbps(num_terminals, num_channels) / offered)


def load_service_history(path: Optional[Path]) -> Dict[str, float]:
    """Load per-cell satisfaction EMA in [0, 1]. Missing cells default to 1.0 (no deficit)."""
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text())


def update_service_history(
    history: Mapping[str, float],
    delivered_satisfaction: Mapping[str, float],
) -> Dict[str, float]:
    """Update active cells from this second's estimated delivered/offered."""
    out: Dict[str, float] = dict(history)
    for cid, sat_now in delivered_satisfaction.items():
        prior = float(out.get(cid, 1.0))
        out[cid] = HISTORY_EMA * prior + (1.0 - HISTORY_EMA) * min(1.0, max(0.0, sat_now))
    return out


def _effective_satisfaction(
    cell_id: str,
    num_terminals: int,
    num_channels: int,
    history: Mapping[str, float],
) -> float:
    """Blend historical satisfaction with this-second progress."""
    blend = float(getattr(global_vars, "scored_rf_history_blend", HISTORY_BLEND))
    hist = float(history.get(cell_id, 1.0))
    now = _satisfaction_this_second(num_terminals, num_channels)
    return max(0.0, min(1.0, blend * hist + (1.0 - blend) * now))


def fairness_scores(
    terminals: Mapping[str, int],
    cell_sats: Mapping[str, Sequence[int]],
    history: Mapping[str, float],
) -> Dict[str, float]:
    """Normalized underservice F in [0, 1]; higher = more historically underserved."""
    underservice = {
        cid: 1.0 - _effective_satisfaction(cid, n_term, len(cell_sats.get(cid, ())), history)
        for cid, n_term in terminals.items()
    }
    max_u = max(underservice.values(), default=0.0)
    if max_u <= 1e-12:
        return {cid: 0.0 for cid in terminals}
    return {cid: underservice[cid] / max_u for cid in terminals}


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
    *,
    graph=None,
    history: Mapping[str, float] | None = None,
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

    gamma = _gamma()
    beta = _beta()
    use_gw, use_isl = _use_gateway(), _use_isl()
    history = history or {}

    egress: Optional[SharedEgress] = None
    if gamma != 0 and (use_gw or use_isl):
        if graph is None:
            raise ValueError("scored-rf needs the current graph for congestion scoring")
        egress = SharedEgress.from_graph(graph, num_satellites)

    max_assignments = len(terminals) * MAX_CHANNELS_PER_CELL
    for _ in range(max_assignments):
        unmet = {cid: _unmet_mbps(n, len(cell_sats[cid])) for cid, n in terminals.items()}
        max_unmet = max(unmet.values(), default=0.0)
        if max_unmet <= 0:
            break

        f_scores = fairness_scores(terminals, cell_sats, history) if beta != 0 else {}
        best: Optional[Tuple[float, str, int, str, str]] = None

        for cell_id, n_term in terminals.items():
            old_sats = cell_sats[cell_id]
            if unmet[cell_id] <= 0 or len(old_sats) == MAX_CHANNELS_PER_CELL:
                continue
            d_norm = unmet[cell_id] / max_unmet
            fairness = f_scores.get(cell_id, 0.0)
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
                if egress is not None and gamma != 0:
                    congestion = _congestion(sat, additional, egress)

                score = ALPHA * d_norm + beta * fairness - gamma * congestion
                key = (score, unmet[cell_id], fairness, cell_id, -sat)
                if best is None or key > (
                    best[0],
                    unmet[best[1]],
                    f_scores.get(best[1], 0.0),
                    best[1],
                    -best[2],
                ):
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
        if egress is not None:
            for s in touched:
                egress.set_sat_load(s, sat_load[s])
        cell_sats[cell_id] = new_sats
        mapping[dummy] = beam_id
        beams_available.remove(beam_id)
        sat_cells_assigned.setdefault(sat, []).append(cell_id)

    isl_scale, gw_scale = (egress.isl_scale, egress.gw_scale) if egress is not None else _capacity_scales()
    print(
        f"[beam-mapping] policy=scored-rf mapped_slots={len(mapping)} "
        f"gateway={use_gw} isl={use_isl} alpha={ALPHA:g} beta={beta:g} gamma={gamma:g} "
        f"isl_scale={isl_scale:g} gw_scale={gw_scale:g} shared_egress={egress is not None} "
        f"history_cells={len(history)}",
        flush=True,
    )
    return mapping
