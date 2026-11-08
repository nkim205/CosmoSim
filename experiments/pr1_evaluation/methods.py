"""Progress Report 1 allocation methods — switch with ``--method N``.

Method definitions follow PR1 Evaluation Plan §1–2. CosmoSim mapping:

| PR1 | Name | CosmoSim policy | Notes |
|---|---|---|---|
| 1 | Equal RF | ``equal-rf`` | Baseline |
| 2 | Demand-proportional | ``demand-proportional`` | Baseline |
| 3 | Demand + gateway, no ISL | ``scored-rf`` | gateway on, ISL off; β/γ on |
| 4 | Demand + ISL, no gateway | ``scored-rf`` | ISL on, gateway off; β/γ on |
| 5 | Full coord. without fairness | ``scored-rf`` | both on; β=0 |
| full | Proposed (demand+cong+fair) | ``scored-rf`` | both on; β=0.3, γ=0.2 |
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MethodSpec:
    """One PR1 evaluation method."""

    key: str                 # CLI id: "1", "2", ..., "full"
    title: str               # human label
    policy: str              # CosmoSim beam policy name
    beta: Optional[float] = None
    gamma: Optional[float] = None
    use_gateway: Optional[bool] = None
    use_isl: Optional[bool] = None
    pr1_section: str = ""

    def run_experiment_flags(self) -> list[str]:
        """Extra CLI flags for ``experiments/run_experiment.py``."""
        flags: list[str] = ["--policies", self.policy]
        if self.beta is not None:
            flags += ["--scored-rf-beta", str(self.beta)]
        if self.gamma is not None:
            flags += ["--scored-rf-gamma", str(self.gamma)]
        if self.use_gateway is not None:
            flags += ["--scored-rf-use-gateway", "1" if self.use_gateway else "0"]
        if self.use_isl is not None:
            flags += ["--scored-rf-use-isl", "1" if self.use_isl else "0"]
        return flags


# Default scored-rf weights from the project sketch (when a method uses scored-rf).
_ALPHA_NOTE = "α=0.5 fixed in scored_rf.py"
_BETA = 0.3
_GAMMA = 0.2

METHODS: dict[str, MethodSpec] = {
    "1": MethodSpec(
        key="1",
        title="Equal RF allocation",
        policy="equal-rf",
        pr1_section="Method 1 baseline",
    ),
    "2": MethodSpec(
        key="2",
        title="Demand-proportional RF allocation",
        policy="demand-proportional",
        pr1_section="Method 2 baseline",
    ),
    "3": MethodSpec(
        key="3",
        title="Demand- and gateway-aware RF allocation without ISL awareness",
        policy="scored-rf",
        beta=_BETA,
        gamma=_GAMMA,
        use_gateway=True,
        use_isl=False,
        pr1_section="Method 3 — demand + gateway + fairness; no ISL",
    ),
    "4": MethodSpec(
        key="4",
        title="Demand- and ISL-aware RF allocation without gateway awareness",
        policy="scored-rf",
        beta=_BETA,
        gamma=_GAMMA,
        use_gateway=False,
        use_isl=True,
        pr1_section="Method 4 — demand + ISL + fairness; no gateway",
    ),
    "5": MethodSpec(
        key="5",
        title="Full coordination without fairness",
        policy="scored-rf",
        beta=0.0,
        gamma=_GAMMA,
        use_gateway=True,
        use_isl=True,
        pr1_section="Method 5 — RF+ISL+gateway; β=0",
    ),
    "full": MethodSpec(
        key="full",
        title="Proposed scored-rf (demand + congestion + fairness)",
        policy="scored-rf",
        beta=_BETA,
        gamma=_GAMMA,
        use_gateway=True,
        use_isl=True,
        pr1_section="Proposed policy — αD + βF − γC",
    ),
    # Scoring-component ablations (same scored-rf loop; weights only).
    "ablate-demand": MethodSpec(
        key="ablate-demand",
        title="Ablation: demand only (β=0, γ=0)",
        policy="scored-rf",
        beta=0.0,
        gamma=0.0,
        use_gateway=True,
        use_isl=True,
        pr1_section="Ablation — αD only",
    ),
    "ablate-cong": MethodSpec(
        key="ablate-cong",
        title="Ablation: demand + congestion (β=0)",
        policy="scored-rf",
        beta=0.0,
        gamma=_GAMMA,
        use_gateway=True,
        use_isl=True,
        pr1_section="Ablation — αD − γC (no fairness)",
    ),
    "ablate-fair": MethodSpec(
        key="ablate-fair",
        title="Ablation: demand + fairness (γ=0)",
        policy="scored-rf",
        beta=_BETA,
        gamma=0.0,
        use_gateway=True,
        use_isl=True,
        pr1_section="Ablation — αD + βF (no congestion)",
    ),
}


def resolve_method(key: str) -> MethodSpec:
    k = str(key).strip().lower()
    aliases = {
        "equal": "1",
        "equal-rf": "1",
        "demand": "2",
        "demand-proportional": "2",
        "no-isl": "3",
        "no-gateway": "4",
        "no-gw": "4",
        "no-fair": "5",
        "nofair": "5",
        "proposed": "full",
        "scored-rf": "full",
        "demand-only": "ablate-demand",
        "cong-only": "ablate-cong",
        "fair-only": "ablate-fair",
    }
    k = aliases.get(k, k)
    if k not in METHODS:
        known = ", ".join(METHODS)
        raise KeyError(f"Unknown method '{key}'. Choose one of: {known} (aliases: {', '.join(aliases)})")
    return METHODS[k]


def list_methods() -> str:
    lines = [f"  {m.key:>4s}  {m.title}  [{m.policy}]  {m.pr1_section}" for m in METHODS.values()]
    return "\n".join(lines)
