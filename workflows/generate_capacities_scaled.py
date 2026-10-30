#!/usr/bin/env python3
"""Stock generate_capacities with ISL / gateway capacity scaling for stress scenarios.

Same positional arguments and options as ``workflows/generate_capacities.py`` plus
``--isl-scale`` and ``--gw-scale``. The stock workflow runs unmodified; only the graph
handed to the routing solver is rescaled (see ``traffic_engineering/capacity_scaling.py``).
With both scales at 1.0 the output is identical to the stock workflow.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

import workflows.generate_capacities as gc
from traffic_engineering.capacity_scaling import scale_capacities


def install_scaling(isl_scale: float, gw_scale: float) -> None:
    """Rescale the routing graph inside both stock routing entry points."""
    original_max_flow = gc.max_flow_capacities
    original_hot_potato = gc.hot_potato_capacities

    def max_flow_scaled(demands, graph, super_source, super_sink, num_satellites):
        scale_capacities(graph, num_satellites, isl_scale, gw_scale, super_node=super_sink)
        return original_max_flow(demands, graph, super_source, super_sink, num_satellites)

    def hot_potato_scaled(demands, graph, super_source, super_sink, num_satellites, num_groundstations):
        scale_capacities(graph, num_satellites, isl_scale, gw_scale, super_node=super_sink)
        return original_hot_potato(demands, graph, super_source, super_sink, num_satellites, num_groundstations)

    gc.max_flow_capacities = max_flow_scaled
    gc.hot_potato_capacities = hot_potato_scaled


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--isl-scale", type=float, default=1.0)
    parser.add_argument("--gw-scale", type=float, default=1.0)
    scales, remaining = parser.parse_known_args()
    install_scaling(scales.isl_scale, scales.gw_scale)
    print(f"[scaling] isl_scale={scales.isl_scale} gw_scale={scales.gw_scale}")
    sys.argv = [sys.argv[0]] + remaining
    gc.main()


if __name__ == "__main__":
    main()
