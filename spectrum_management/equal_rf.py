"""Equal RF baseline: demand-oblivious round-robin channel allocation.

Every cell with at least one terminal is treated the same. In each pass, cells are visited
in a fixed order (sorted H3 id) and each gets at most one more channel, until all cells
have MAX_CHANNELS_PER_CELL channels or no further beam fits. Satellite choice and the
co-channel check are the same as greedy-coordinated, so the two differ only in which
cells are served and in what order.
"""

from __future__ import annotations

from typing import Dict, Mapping, Sequence

from utils import global_variables as global_vars

from .common import candidate_sats, initialize_beam_state
from .constants import MAX_CHANNELS_PER_CELL
from .greedy_coordinated import _order_satellites
from .interference import check_interference


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
    del satellite_cells, config, users_per_channel, cell_population  # demand-oblivious

    if not satellites or not prepared_cells:
        return {}

    beams_available, sat_cells_assigned = initialize_beam_state(satellites)
    mapping: Dict[str, str] = {}
    num_shells = len(shell_satellite_indices)
    ordered_cells = sorted(cell["cell"] for cell in prepared_cells)  # type: ignore[index]
    blocked = set()  # cells for which no further beam fits

    def try_assign_one(cell_id: str) -> bool:
        candidates = _order_satellites(
            candidate_sats(cell_id, cell_satellites), shell_satellite_indices, sat_cells_assigned, num_shells
        )
        for channel_idx in range(MAX_CHANNELS_PER_CELL):
            dummy = f"{cell_id}_{channel_idx}"
            if dummy in mapping:
                continue
            for sat in candidates:
                for freq in range(global_vars.spatial_channel_reuse_factor):
                    beam_id = f"{freq}_{sat}_{channel_idx}"
                    if beam_id in beams_available and check_interference(cell_id, mapping, beam_id):
                        mapping[dummy] = beam_id
                        beams_available.remove(beam_id)
                        sat_cells_assigned.setdefault(sat, []).append(cell_id)
                        return True
        return False

    for _ in range(MAX_CHANNELS_PER_CELL):
        for cell_id in ordered_cells:
            if cell_id not in blocked and not try_assign_one(cell_id):
                blocked.add(cell_id)

    print(f"[beam-mapping] policy=equal-rf mapped_slots={len(mapping)}")
    return mapping
