"""Check that a beam mapping obeys CosmoSim's allocation rules.

Usable from tests:  problems = validate_mapping(mapping, cell_satellites, cells_with_terminals)
An empty list means the mapping is valid. Rules checked:
  - keys look like "<cell>_<channel>" and values like "<color>_<satellite>_<channel>", channel 0-7, color 0-3
  - the cell has terminals, and the satellite can currently see the cell
  - no beam (value) is used twice
  - co-channel rule: a cell and its 1-ring neighbours never share a (satellite, channel), and a cell never
    uses the same channel index twice (same check the built-in policies apply while assigning)
"""

from __future__ import annotations

from typing import Iterable, List, Mapping, Sequence

from utils import global_variables as global_vars

from .constants import MAX_CHANNELS_PER_CELL
from .interference import check_interference


def validate_mapping(
    mapping: Mapping[str, str],
    cell_satellites: Mapping[str, Sequence[int]],
    cells_with_terminals: Iterable[str],
    max_report: int = 20,
) -> List[str]:
    problems: List[str] = []
    allowed_cells = set(cells_with_terminals)
    seen_beams: dict[str, str] = {}

    for key, beam in mapping.items():
        cell, _, ch = key.rpartition("_")
        parts = beam.split("_")
        if not ch.isdigit() or not 0 <= int(ch) < MAX_CHANNELS_PER_CELL or len(parts) != 3 or not all(p.isdigit() for p in parts):
            problems.append(f"bad format: {key} -> {beam}")
            continue
        color, sat, beam_ch = (int(p) for p in parts)
        if not 0 <= color < global_vars.spatial_channel_reuse_factor or not 0 <= beam_ch < MAX_CHANNELS_PER_CELL:
            problems.append(f"color/channel out of range: {key} -> {beam}")
        if cell not in allowed_cells:
            problems.append(f"cell without terminals got a beam: {key}")
        if sat not in set(cell_satellites.get(cell, [])):
            problems.append(f"satellite {sat} cannot see cell {cell}: {key} -> {beam}")
        if beam in seen_beams:
            problems.append(f"beam {beam} used twice: {seen_beams[beam]} and {key}")
        seen_beams[beam] = key
        others = {k: v for k, v in mapping.items() if k != key}
        if not check_interference(cell, others, beam):
            problems.append(f"co-channel conflict: {key} -> {beam}")
        if len(problems) >= max_report:
            problems.append("... (stopped after first problems)")
            break
    return problems
