#!/usr/bin/env python3
"""Print requested / admitted / delivered / stranded for one run folder.

Usage:
  python analysis/summarize_run.py <run_folder> <terminal_file>

<run_folder> is the output folder you gave generate_flows / generate_capacities.
<terminal_file> is the terminal file used (name or path), e.g. cells_haiti_0_10000_uniform.txt.
If the folder holds several seconds (generate_capacities --duration N), each second is listed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    run = Path(sys.argv[1])
    term = Path(sys.argv[2])
    if not term.exists():
        term = ROOT / "terminal_deployment" / "terminals" / term.name
    for path, what in ((run / "demands.txt", "demands.txt (step 3: generate_flows)"), (term, "terminal file")):
        if not path.exists():
            sys.exit(f"Missing {what}: {path}\nRun from the repo root and use the same folder you gave steps 3 and 4.")
    flow_files = sorted(run.glob("max_flow_*.txt"))
    if not flow_files:
        sys.exit(f"No max_flow_*.txt in {run}. Run step 4 (generate_capacities) first.")

    requested = sum(int(line.split(",")[1]) for line in term.read_text().split()) * 100  # Mbps
    admitted = float(np.atleast_1d(np.loadtxt(run / "demands.txt")).sum())
    print(f"requested {requested/1e3:.1f} Gbps | admitted {admitted/1e3:.1f} Gbps (from demands.txt)")
    for ff in flow_files:
        rows = np.atleast_2d(np.loadtxt(ff, delimiter=","))
        for t_ns, delivered in rows:
            print(
                f"  t={t_ns/1e9:>5.0f}s  delivered {delivered/1e3:8.1f}  stranded {(admitted-delivered)/1e3:7.1f} Gbps"
            )


if __name__ == "__main__":
    main()
