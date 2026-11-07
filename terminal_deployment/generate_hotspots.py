"""Write the shared hotspot terminal files and the shifting-hotspot schedule for Haiti.

Two patterns. In both, a hotspot is the N Haiti cells nearest a fixed point, the hotspot
cells share their terminals evenly, and every other cell gets an even share of the rest.

  hotspot (sharp): 10,000 terminals, 8,000 on 5 cells (1,600 each). Far more than 8 channels
                   can carry, so it tests the radio limit, not the network.
  wide:            5,000 terminals, 2,000 on 20 cells (100 each, about what 8 channels carry).
                   Most of it can be admitted, so gateway limits can show.

Locations (latitude, longitude):
  pap    18.490, -72.320   Port-au-Prince
  north  19.900, -72.841   north coast
  south  18.193, -73.750   Les Cayes (wide pattern only)

The shifting schedule moves the wide hotspot: pap for seconds 0-19, north for 20-39,
south for 40-59. It is a fixed schedule, not random.

Run from the repo root (refuses to change existing files unless --overwrite):
  .venv/bin/python terminal_deployment/generate_hotspots.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import h3

ROOT = Path(__file__).resolve().parents[1]
TERMINALS = ROOT / "terminal_deployment" / "terminals"
CELL_LIST = TERMINALS / "cells_haiti_0_10000_uniform.txt"  # the 136 Haiti cells, in file order

CENTERS = {
    "pap": (18.490, -72.320),
    "north": (19.900, -72.841),
    "south": (18.193, -73.750),
}

# (kind, total terminals, hotspot cells, terminals on the hotspot, locations)
PATTERNS = [
    ("hotspot", 10_000, 5, 8_000, ["pap", "north"]),
    ("wide", 5_000, 20, 2_000, ["pap", "north", "south"]),
]

# (schedule name, kind, total, [(first second, location), ...])
SCHEDULES = [
    ("wide_shift", "wide", 5_000, [(0, "pap"), (20, "north"), (40, "south")]),
]


def haiti_cells() -> list[str]:
    return [line.split(",")[0] for line in CELL_LIST.read_text().splitlines() if line.strip()]


def nearest(cells: list[str], lat: float, lng: float, k: int) -> list[str]:
    coords = {cell: h3.cell_to_latlng(cell) for cell in cells}
    return sorted(cells, key=lambda cell: (coords[cell][0] - lat) ** 2 + (coords[cell][1] - lng) ** 2)[:k]


def split_even(cells: list[str], total: int) -> dict[str, int]:
    """Equal split. The remainder goes one each to the lowest H3 ids, so the file is deterministic."""
    ordered = sorted(cells)
    base, extra = divmod(total, len(ordered))
    return {cell: base + (1 if i < extra else 0) for i, cell in enumerate(ordered)}


def allocate(cells: list[str], hot: list[str], total: int, hot_terminals: int) -> dict[str, int]:
    counts = split_even([c for c in cells if c not in set(hot)], total - hot_terminals)
    counts.update(split_even(hot, hot_terminals))
    if sum(counts.values()) != total:
        raise RuntimeError(f"terminal total is {sum(counts.values())}, expected {total}")
    return counts


def write(path: Path, text: str, overwrite: bool) -> None:
    if path.exists() and path.read_text() != text and not overwrite:
        raise SystemExit(f"{path.name} already exists with different contents. It is a shared input; "
                         "pass --overwrite only if the team agreed to change it.")
    path.write_text(text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    cells = haiti_cells()
    clusters: dict[tuple[str, str], set[str]] = {}
    for kind, total, n_hot, hot_terminals, locations in PATTERNS:
        for loc in locations:
            hot = nearest(cells, *CENTERS[loc], n_hot)
            clusters[(kind, loc)] = set(hot)
            counts = allocate(cells, hot, total, hot_terminals)
            path = TERMINALS / f"cells_haiti_0_{total}_{kind}_{loc}.txt"
            write(path, "".join(f"{c},{counts[c]}\n" for c in cells), args.overwrite)
            other = [counts[c] for c in cells if c not in set(hot)]
            print(f"{path.name}: {n_hot} hotspot cells x {hot_terminals // n_hot}, "
                  f"other {len(other)} cells {min(other)}-{max(other)}")
        for i, a in enumerate(locations):
            for b in locations[i + 1:]:
                if clusters[(kind, a)] & clusters[(kind, b)]:
                    raise RuntimeError(f"{kind} hotspots {a} and {b} overlap")

    for name, kind, total, segments in SCHEDULES:
        path = TERMINALS / f"cells_haiti_0_{total}_{name}.schedule"
        lines = ["# first_second,terminal_file (used until the next line's second)"]
        lines += [f"{start},cells_haiti_0_{total}_{kind}_{loc}" for start, loc in segments]
        write(path, "\n".join(lines) + "\n", args.overwrite)
        print(f"{path.name}: " + ", ".join(f"{loc} from {start} s" for start, loc in segments))


if __name__ == "__main__":
    main()
