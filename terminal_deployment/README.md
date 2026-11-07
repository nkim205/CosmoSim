# Terminal Deployment

This package owns every step required to turn population rasters into per-cell terminal allocations that the workflows consume.

## Layout

| Component | Purpose |
| --- | --- |
| `generate_cell_allocations.py` | Entry point for producing terminal layouts from inputs/cells rasters and distribution configs. |
| `generate_hotspots.py` | Project script: writes the Haiti hotspot files (`cells_haiti_0_10000_hotspot_*`, `cells_haiti_0_5000_wide_*`) and the shifting schedule `cells_haiti_0_5000_wide_shift.schedule`. |
| `terminals/` | Generated allocation files (`cells_<country>_0_<pop>_<distribution>[_<cap>][_ku].txt`). Gitignored, except the shared Haiti project files listed in `.gitignore`. |
| `command_logs/` | Run logs emitted by the generator scripts for reproducibility. |

## Input Expectations

`generate_cell_allocations.py` expects:

- A country cells file under `inputs/cells/<country>.txt`.
- A distribution configuration YAML (see the templates in `inputs/`).
- Optional GCB cap values and KU-band choices to annotate the output filename.

The script writes one terminal file per (country, population, distribution, cap, KU) combination and stores it in `terminal_deployment/terminals/`.

## Adding a New Distribution

1. Extend the configuration templates to describe the new distribution label and parameters.
2. Update the generator so it can build terminal counts for that label (typically by adding a branch in the distribution resolver).
3. Ensure filenames keep the canonical slug format so downstream workflows (`scenario_identifier` + optional cap/KU) find the files automatically.

Re-run the generator whenever underlying population rasters or distribution logic changes; commit only the templates, not the generated terminal files.
