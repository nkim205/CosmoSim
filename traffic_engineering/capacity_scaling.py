"""Scale ISL and gateway capacities on a routing graph for stress scenarios.

Applied to the graph that stock ``generate_capacities`` hands to its solver, i.e. after the
stock Ka assignment and GS-edge pruning. Gateway scaling therefore keeps the stock Ka
assignment pattern and shrinks every feeder edge (GS -> sat) and every per-ground-station
aggregate edge (T -> GS) by the same factor. Capacities stay integers, as the stock code uses.
"""

from __future__ import annotations

import networkx as nx


def scale_capacities(
    graph: nx.DiGraph,
    num_satellites: int,
    isl_scale: float = 1.0,
    gw_scale: float = 1.0,
    super_node: str = "T",
) -> nx.DiGraph:
    if isl_scale < 0 or gw_scale < 0:
        raise ValueError("Capacity scales must be non-negative.")
    if isl_scale == 1.0 and gw_scale == 1.0:
        return graph

    for u, v, data in graph.edges(data=True):
        if u == super_node:
            scale = gw_scale
        elif isinstance(u, int) and isinstance(v, int) and v < num_satellites:
            scale = isl_scale if u < num_satellites else gw_scale
        else:
            continue
        data["capacity"] = int(round(data.get("capacity", 0) * scale))
    return graph
