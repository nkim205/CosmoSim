#!/usr/bin/env python3
"""Stock generate_capacities with ISL / gateway capacity scaling for stress scenarios.

Same positional arguments and options as ``workflows/generate_capacities.py`` plus
``--isl-scale`` and ``--gw-scale``. The stock workflow runs unmodified; only the graph
handed to the routing solver is rescaled (see ``traffic_engineering/capacity_scaling.py``).
With both scales at 1.0 the output is identical to the stock workflow.

After scaling, writes ``edge_caps_<routing>_<flow_time>.json`` so evaluation metrics can
compute post-routing gateway/ISL utilization without replaying Ka assignment.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

import workflows.generate_capacities as gc
from analysis.edge_capacities import edge_caps_path, write_edge_caps
from traffic_engineering.capacity_scaling import scale_capacities

# Filled by main() before calling stock generate_capacities.
_DUMP_DIR: Optional[Path] = None
_FLOW_TIME_S: Optional[int] = None
_ROUTING: str = "max_flow"


def install_scaling(isl_scale: float, gw_scale: float) -> None:
    """Rescale the routing graph inside both stock routing entry points."""
    original_max_flow = gc.max_flow_capacities
    original_hot_potato = gc.hot_potato_capacities

    def _dump(graph, num_satellites: int) -> None:
        if _DUMP_DIR is None or _FLOW_TIME_S is None:
            return
        write_edge_caps(edge_caps_path(_DUMP_DIR, _ROUTING, _FLOW_TIME_S), graph, num_satellites)

    def max_flow_scaled(demands, graph, super_source, super_sink, num_satellites):
        scale_capacities(graph, num_satellites, isl_scale, gw_scale, super_node=super_sink)
        _dump(graph, num_satellites)
        return original_max_flow(demands, graph, super_source, super_sink, num_satellites)

    def hot_potato_scaled(demands, graph, super_source, super_sink, num_satellites, num_groundstations):
        scale_capacities(graph, num_satellites, isl_scale, gw_scale, super_node=super_sink)
        _dump(graph, num_satellites)
        return original_hot_potato(demands, graph, super_source, super_sink, num_satellites, num_groundstations)

    gc.max_flow_capacities = max_flow_scaled
    gc.hot_potato_capacities = hot_potato_scaled


def _peek_stock_args(remaining: list[str]) -> tuple[Path, int, str]:
    peek = argparse.ArgumentParser(add_help=False)
    peek.add_argument("output_dir", type=Path)
    peek.add_argument("graph_dir", type=Path)
    peek.add_argument("constellation")
    peek.add_argument("groundstations")
    peek.add_argument("cells_file", type=Path)
    peek.add_argument("country")
    peek.add_argument("flow_time_s", type=int)
    peek.add_argument("beam_policy")
    peek.add_argument("ku_band_capacity", type=float)
    peek.add_argument("--routing", default="max_flow")
    peek.add_argument("--duration", type=int, default=15)
    peek.add_argument("--update-interval-ms", type=int, default=1000)
    peek.add_argument("--demands-dir", type=Path, default=None)
    known, _ = peek.parse_known_args(remaining)
    return known.output_dir, known.flow_time_s, known.routing


def main() -> None:
    global _DUMP_DIR, _FLOW_TIME_S, _ROUTING
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--isl-scale", type=float, default=1.0)
    parser.add_argument("--gw-scale", type=float, default=1.0)
    scales, remaining = parser.parse_known_args()
    _DUMP_DIR, _FLOW_TIME_S, _ROUTING = _peek_stock_args(remaining)
    install_scaling(scales.isl_scale, scales.gw_scale)
    print(f"[scaling] isl_scale={scales.isl_scale} gw_scale={scales.gw_scale}")
    sys.argv = [sys.argv[0]] + remaining
    gc.main()


if __name__ == "__main__":
    main()
