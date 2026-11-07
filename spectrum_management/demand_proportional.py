"""Demand-proportional baseline: channels follow terminal share, with no look at the network.

Each cell's target is its share of one fixed channel budget. The budget equals the total
number of channels greedy-coordinated would request (sum of min(8, ceil(terminals / 12))),
so the two policies ask for the same amount of radio and differ only in who receives it.
Shares are terminal counts, turned into integers with largest-remainder rounding and a cap
of 8 channels per cell. Leftover channels from the cap go to the next-highest shares.

This is not greedy-uncoordinated. That policy scales every cell to the single largest cell,
so at 10k population almost every cell is asked for one channel. A cell with one terminal
has a tiny share here and usually gets zero; those channels go to heavier cells.

Satellite choice and the co-channel check match equal-rf. Nothing in this file reads ISL
or gateway capacity.
"""

from __future__ import annotations

import math
from typing import Dict, Mapping, Sequence

from utils import global_variables as global_vars

from .common import candidate_sats, initialize_beam_state
from .constants import MAX_CHANNELS_PER_CELL
from .greedy_coordinated import _order_satellites
from .interference import check_interference


def channel_targets(
    prepared_cells: Sequence[Mapping[str, int]],
    users_per_channel: int,
    cap: int = MAX_CHANNELS_PER_CELL,
) -> Dict[str, int]:
    """Integer channel counts proportional to terminals, summing to the coordinated budget."""
    if users_per_channel <= 0:
        raise ValueError("users_per_channel must be a positive integer.")
    weights = {cell["cell"]: int(cell["num_terminals"]) for cell in prepared_cells}  # type: ignore[index]
    budget = sum(min(cap, math.ceil(n / users_per_channel)) for n in weights.values() if n > 0)
    return _apportion(weights, budget, cap)


def _apportion(weights: Mapping[str, int], budget: int, cap: int) -> Dict[str, int]:
    """Largest remainder. Cells already at `cap` are frozen and their unused share is reassigned."""
    assigned = {k: 0 for k in weights}
    eligible = {k for k, w in weights.items() if w > 0}
    remaining = min(budget, cap * len(eligible))
    for _ in range(cap + 1):
        if remaining <= 0 or not eligible:
            break
        wsum = sum(weights[k] for k in eligible)
        quotas = {k: remaining * weights[k] / wsum for k in eligible}
        base = {k: min(cap - assigned[k], math.floor(quotas[k])) for k in eligible}
        for k, n in base.items():
            assigned[k] += n
        leftover = remaining - sum(base.values())
        order = sorted(
            eligible,
            key=lambda k: (quotas[k] - math.floor(quotas[k]), weights[k], k),
            reverse=True,
        )
        for k in order:
            if leftover <= 0:
                break
            if assigned[k] < cap:
                assigned[k] += 1
                leftover -= 1
        eligible = {k for k in eligible if assigned[k] < cap}
        remaining = leftover
    return assigned


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
    del satellite_cells, config, cell_population  # no network state, no population layer

    if not satellites or not prepared_cells:
        return {}

    targets = channel_targets(prepared_cells, users_per_channel)
    terminals = {cell["cell"]: int(cell["num_terminals"]) for cell in prepared_cells}  # type: ignore[index]
    beams_available, sat_cells_assigned = initialize_beam_state(satellites)
    mapping: Dict[str, str] = {}
    num_shells = len(shell_satellite_indices)
    ordered_cells = sorted(targets, key=lambda cid: (-terminals[cid], cid))
    given = {cid: 0 for cid in targets}
    blocked = set()

    def try_assign_one(cell_id: str) -> bool:
        candidates = _order_satellites(
            candidate_sats(cell_id, cell_satellites), shell_satellite_indices, sat_cells_assigned, num_shells
        )
        for channel_idx in range(MAX_CHANNELS_PER_CELL):
            key = f"{cell_id}_{channel_idx}"
            if key in mapping:
                continue
            for sat in candidates:
                for freq in range(global_vars.spatial_channel_reuse_factor):
                    beam_id = f"{freq}_{sat}_{channel_idx}"
                    if beam_id in beams_available and check_interference(cell_id, mapping, beam_id):
                        mapping[key] = beam_id
                        beams_available.remove(beam_id)
                        sat_cells_assigned.setdefault(sat, []).append(cell_id)
                        return True
        return False

    for _ in range(MAX_CHANNELS_PER_CELL):
        progress = False
        for cell_id in ordered_cells:
            if cell_id in blocked or given[cell_id] >= targets[cell_id]:
                continue
            if try_assign_one(cell_id):
                given[cell_id] += 1
                progress = True
            else:
                blocked.add(cell_id)
        if not progress:
            break

    print(f"[beam-mapping] policy=demand-proportional mapped_slots={len(mapping)} "
          f"target_slots={sum(targets.values())}")
    return mapping
