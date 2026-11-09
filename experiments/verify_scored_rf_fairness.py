#!/usr/bin/env python3
"""Check scored-rf fairness and the ISL-only ablation on small inputs.

Run from repo root:
  .venv/bin/python experiments/verify_scored_rf_fairness.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import utils.global_variables as gv
from spectrum_management import scored_rf as sr
from utils.h3_compat import k_ring

SHELLS = [(0, 1584), (1584, 3168), (3168, 4752), (4752, 6336), (6336, 6364)]


def _nonadjacent_cells(n: int = 8) -> list[str]:
    rows = [
        line.strip().split(",")[0]
        for line in (ROOT / "terminal_deployment/terminals/cells_haiti_0_1000_uniform.txt").read_text().splitlines()
        if line.strip()
    ]
    picked: list[str] = []
    for cell in rows:
        if any(cell in k_ring(p, 1) or p in k_ring(cell, 1) for p in picked):
            continue
        picked.append(cell)
        if len(picked) >= n:
            break
    if len(picked) < n:
        raise RuntimeError(f"Only found {len(picked)} mutually non-adjacent cells")
    return picked


def main() -> None:
    cells = _nonadjacent_cells(8)
    cell_a, cell_b = cells[0], cells[1]
    sats = [42]  # 32 beams; 8 cells x 8 channels needed => contended
    prepared = [{"cell": c, "num_terminals": 100} for c in cells]
    cell_satellites = {c: sats for c in cells}
    satellite_cells = {42: cells}
    base = {c: 1.0 for c in cells}
    terms = {c: 100 for c in cells}
    empty = {c: [] for c in cells}

    f_a = sr.fairness_scores(terms, empty, {**base, cell_a: 0.05})
    f_b = sr.fairness_scores(terms, empty, {**base, cell_b: 0.05})
    assert f_a[cell_a] > f_a[cell_b]
    assert f_b[cell_b] > f_b[cell_a]

    def first_winner(history: dict[str, float], beta: float = 0.5) -> str:
        scores_f = sr.fairness_scores(terms, empty, history)
        scores = {c: sr.ALPHA + beta * scores_f[c] for c in terms}
        return max(scores, key=lambda c: (scores[c], c))

    assert first_winner({**base, cell_a: 0.05}) == cell_a
    assert first_winner({**base, cell_b: 0.05}) == cell_b
    print("PASS: first-assignment preference flips with history")

    def run(history: dict[str, float], beta: float = 0.5) -> Counter:
        gv.scored_rf_beta = beta
        gv.scored_rf_gamma = 0.0
        mapping = sr.assign_beams(
            prepared, sats, satellite_cells, cell_satellites, "test", SHELLS, 12, {}, history=history,
        )
        return Counter(key.rsplit("_", 1)[0] for key in mapping)

    counts_a = run({**base, cell_a: 0.05})
    counts_b = run({**base, cell_b: 0.05})
    print(f"A underserved: A={counts_a[cell_a]} B={counts_a[cell_b]}")
    print(f"B underserved: A={counts_b[cell_a]} B={counts_b[cell_b]}")
    assert counts_a[cell_a] > counts_a[cell_b]
    assert counts_b[cell_b] > counts_b[cell_a]
    print("PASS: scarce-beam channel counts follow service history")

    h1 = sr.update_service_history({}, {cell_a: 0.0})
    h2 = sr.update_service_history(h1, {cell_a: 1.0})
    assert h2[cell_a] > h1[cell_a]
    print("PASS: delivered service history update")

    # Both serving satellites need an ISL to reach satellite 2's gateway.
    graph = nx.DiGraph()
    for sat, capacity in ((0, 100), (1, 1000)):
        graph.add_edge(sat, 2, capacity=capacity)
        graph.add_edge(2, sat, capacity=capacity)
    graph.add_edge(3, 2, capacity=1000)
    gv.scored_rf_beta = 0.0
    gv.scored_rf_gamma = sr.GAMMA

    def allocate(use_gateway: bool, use_isl: bool, gw_scale: float) -> int:
        gv.scored_rf_use_gateway = use_gateway
        gv.scored_rf_use_isl = use_isl
        gv.gw_scale = gw_scale
        mapping = sr.assign_beams(
            [{"cell": cell_a, "num_terminals": 10}], [0, 1], {}, {cell_a: [0, 1]},
            "test", [(0, 3)], 12, {}, graph=graph,
        )
        return int(mapping[f"{cell_a}_0"].split("_")[1])

    without_isl = allocate(True, False, 1.0)
    isl_only = allocate(False, True, 1.0)
    assert isl_only == allocate(False, True, 0.0) == 1
    assert sr.SharedEgress.from_graph(graph, 3).best_egress(0)[0] == 100
    assert nx.maximum_flow_value(graph, 3, without_isl) == 100
    assert nx.maximum_flow_value(graph, 3, isl_only) == 1000
    print("PASS: ISL awareness picks the higher-throughput path independently of gateway scale")
    print("ALL PASS")


if __name__ == "__main__":
    main()
