"""PR1 test-scenario matrix mapped onto CosmoSim Haiti inputs.

PR1 Evaluation Plan §2:
  - Uniform demand
  - Demand hotspots (incl. shifting)
  - Limited ISL capacity
  - Limited gateway capacity
  - Combined ISL + gateway constraints

Each case is one ``run_experiment`` invocation (scenarios × scales × duration).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ScenarioCase:
    """One PR1 scenario family with capacity settings."""

    key: str
    title: str
    pr1_tag: str
    scenarios: tuple[str, ...]   # CosmoSim scenario short names
    isl_scales: tuple[float, ...]
    gw_scales: tuple[float, ...]


# Full PR1 coverage (used by default / --matrix pr1).
PR1_MATRIX: dict[str, ScenarioCase] = {
    "uniform": ScenarioCase(
        key="uniform",
        title="Uniform demand",
        pr1_tag="Uniform demand",
        scenarios=("1k-uniform", "10k-uniform"),
        isl_scales=(1.0,),
        gw_scales=(1.0,),
    ),
    "population": ScenarioCase(
        key="population",
        title="Population-weighted demand",
        pr1_tag="Demand distribution",
        scenarios=("1k-pop", "10k-pop"),
        isl_scales=(1.0,),
        gw_scales=(1.0,),
    ),
    "hotspot": ScenarioCase(
        key="hotspot",
        title="Sharp demand hotspots",
        pr1_tag="Demand hotspots",
        scenarios=("10k-hotspot-pap", "10k-hotspot-north"),
        isl_scales=(1.0,),
        gw_scales=(1.0,),
    ),
    "wide": ScenarioCase(
        key="wide",
        title="Wide demand hotspots",
        pr1_tag="Demand hotspots",
        scenarios=("5k-wide-pap", "5k-wide-north", "5k-wide-south"),
        isl_scales=(1.0,),
        gw_scales=(1.0,),
    ),
    "shift": ScenarioCase(
        key="shift",
        title="Shifting wide hotspot",
        pr1_tag="Demand hotspots (shift over time)",
        scenarios=("5k-wide-shift",),
        isl_scales=(1.0,),
        gw_scales=(1.0,),
    ),
    "limited_gw": ScenarioCase(
        key="limited_gw",
        title="Limited gateway capacity",
        pr1_tag="Limited gateway capacity",
        scenarios=("1k-uniform", "10k-uniform", "5k-wide-pap"),
        isl_scales=(1.0,),
        gw_scales=(0.75, 0.5, 0.25),
    ),
    "limited_isl": ScenarioCase(
        key="limited_isl",
        title="Limited ISL capacity",
        pr1_tag="Limited ISL capacity",
        scenarios=("10k-uniform", "5k-wide-pap"),
        isl_scales=(0.5, 0.1),
        gw_scales=(1.0,),
    ),
    "combined": ScenarioCase(
        key="combined",
        title="Combined ISL + gateway constraints",
        pr1_tag="Combined ISL and gateway constraints",
        scenarios=("5k-wide-pap",),
        isl_scales=(0.1,),
        gw_scales=(0.5,),
    ),
}

# Faster subset for plumbing checks.
SMOKE_MATRIX: dict[str, ScenarioCase] = {
    "uniform": ScenarioCase(
        key="uniform",
        title="Uniform demand",
        pr1_tag="Uniform demand",
        scenarios=("10k-uniform",),
        isl_scales=(1.0,),
        gw_scales=(1.0,),
    ),
    "hotspot": ScenarioCase(
        key="hotspot",
        title="Sharp demand hotspot (pap only)",
        pr1_tag="Demand hotspots",
        scenarios=("10k-hotspot-pap",),
        isl_scales=(1.0,),
        gw_scales=(1.0,),
    ),
    "limited_gw": ScenarioCase(
        key="limited_gw",
        title="Limited gateway (wide pap)",
        pr1_tag="Limited gateway capacity",
        scenarios=("5k-wide-pap",),
        isl_scales=(1.0,),
        gw_scales=(0.5,),
    ),
}


def resolve_matrix(name: str) -> dict[str, ScenarioCase]:
    n = name.strip().lower()
    if n in ("pr1", "full", "all"):
        return dict(PR1_MATRIX)
    if n in ("smoke", "quick"):
        return dict(SMOKE_MATRIX)
    raise KeyError(f"Unknown matrix '{name}'. Use: pr1, smoke")


def select_cases(matrix: dict[str, ScenarioCase], only: Sequence[str] | None) -> list[ScenarioCase]:
    if not only:
        return list(matrix.values())
    out = []
    for key in only:
        if key not in matrix:
            raise KeyError(f"Unknown case '{key}'. Available: {', '.join(matrix)}")
        out.append(matrix[key])
    return out
