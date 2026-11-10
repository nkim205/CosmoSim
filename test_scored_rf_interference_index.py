"""Run from the CosmoSim repository root: python test_scored_rf_interference_index.py"""
import random
from unittest.mock import patch

from spectrum_management.interference import check_interference
from spectrum_management.scored_rf import _InterferenceIndex


def main():
    # Synthetic one-ring graph. Both implementations receive identical neighbors.
    cells = [f'cell{i}' for i in range(12)]
    adjacency = {
        cell: {cell, cells[(i - 1) % len(cells)], cells[(i + 1) % len(cells)]}
        for i, cell in enumerate(cells)
    }

    def neighbors(cell, radius):
        assert radius == 1
        return adjacency[cell]

    mapping = {}
    index = _InterferenceIndex()
    rnd = random.Random(20261109)
    checks = 0
    # Use consistent beam IDs, including colors. Check all proposed candidates
    # against the untouched original implementation at every incremental state.
    with patch('spectrum_management.interference.k_ring', side_effect=neighbors), patch(
        'spectrum_management.scored_rf.k_ring', side_effect=neighbors
    ):
        for _ in range(80):
            proposals = [(c, sat, ch) for c in cells for sat in range(4) for ch in range(8)]
            rnd.shuffle(proposals)
            chosen = None
            for cell, sat, ch in proposals:
                beam = f'0_{sat}_{ch}'
                expected = check_interference(cell, mapping, beam)
                actual = index.feasible(cell, sat, ch)
                assert expected == actual, (cell, sat, ch, expected, actual)
                checks += 1
                if expected and chosen is None and f'{cell}_{ch}' not in mapping:
                    chosen = (cell, sat, ch)
            if chosen is None:
                break
            cell, sat, ch = chosen
            mapping[f'{cell}_{ch}'] = f'0_{sat}_{ch}'
            index.add(cell, sat, ch)
    print(f'PASS: {checks} interference decisions matched the original implementation.')


if __name__ == '__main__':
    main()
