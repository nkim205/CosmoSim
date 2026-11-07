# CosmoSim

> CS 4251/6250 project fork: start with [PROJECT_NOTES.md](PROJECT_NOTES.md) for setup, experiments, and baselines.

CosmoSim is the an open-source simulator to model satellite network capacity released as part of the
_Assessing LEO Satellite Networks for National Emergency Failover_ paper at IMC 2025.  The code
bundled here is curated for public release: configuration generators, graph
builders, traffic-engineering runners, spectrum-management tooling, and plotting
scripts are organised around a shared data directory so you can reproduce the
pipeline end-to-end without hauling large intermediate artefacts.

The paper can be found [here](http://saeed.github.io/files/cosmosim-imc25.pdf).

The web app visualizing the output of this simulator can be found [here](https://saeed.github.io/cosmosim-webapp/).

If you use this codebase, please cite:
```
@inproceedings{bhosale2025leo,
  title     = {Assessing LEO Satellite Networks for National Emergency Failover},
  author    = {Vaibhav Bhosale and Ying Zhang and Sameer Kapoor and Robin Kim and Miguel Schlicht and Muskaan Gupta and Ekaterina Tumanova and Zachary Bischof and Fabián E. Bustamante and Alberto Dainotti and Ahmed Saeed},
  booktitle = {Proceedings of the 2025 ACM on Internet Measurement Conference (IMC~2025)},
  year      = {2025}
}
```

## Reproducing the pipeline

The bundled dataset covers the six study countries from the paper (Great Britain,
Ghana, Haiti, Lithuania, South Africa, and Tonga). For any additional geography
you must first obtain the appropriate shapefiles and population rasters,
generate an `inputs/cells/<country>.txt` file, and register the country in
`plotting_scripts/common.py`. Likewise, new constellations must be described
under `constellation_configurations/` (see the existing `starlink_*.yaml`
files) before they can be referenced by the workflows.

### Prerequisites

Install the required native libraries (no ns-3 toolchain needed):

```bash
sudo apt-get update && sudo apt-get install -y libproj-dev proj-data proj-bin libgeos-dev
```

Then install the Python dependencies:

```bash
python -m pip install -r requirements.txt
```

Run the following stages from the repository root using the dedicated helper
scripts. Each script spawns the required workflow jobs. Stages 2–5 log under
`data/command_logs/`; the terminal stage (1) logs under
`terminal_deployment/command_logs/`.

1. **Generate terminal distributions**

   ```bash
   python terminal_deployment/script_cell_allocation.py
   ```

   Adjust the country/population/distribution lists near the top of the script
   (or edit `terminal_deployment/generate_cell_allocations.py` for bespoke
   runs). This stage writes one terminal-allocation file per
   country/population/distribution combination into
   `terminal_deployment/terminals/`, named like
   `cells_<country>_0_<population>_<distribution>.txt` (e.g.
   `cells_britain_0_10000_uniform.txt`; GCB runs append the cap and Ku-band
   capacity). These files are later resolved by the flow/capacity runners — the
   `data/<scenario_id>_<beam_policy>/` directories and their `demands.txt`
   snapshots are produced in stage 3, not here.

2. **Generate graphs**

   ```bash
   python scripts/run_generate_graphs.py
   ```

   Graph snapshots for each constellation/country/time combination are produced
   under `graph_generation/graphs/<constellation>/<country>/`, one
   `graph_<timestamp_ns>.txt` file per snapshot.

3. **Generate flows (demand snapshots)**

   ```bash
   python scripts/run_generate_flows.py
   ```

   This invokes `workflows/generate_flows.py` for every scenario, storing
   `demands.txt` files directly under
   `data/<scenario>_<beam_policy>/demands.txt`.

4. **Generate capacities (routing policies)**

   ```bash
   python scripts/run_generate_capacities.py
   ```

   `workflows/generate_capacities.py` converts those demands into routed
   capacities, writing `{routing}_{t}.txt` and `flow_dict_{routing}_{t}.json`
   alongside `demands.txt` in `data/<scenario_id>_<beam_policy>/`.

5. **Generate capacities with competing traffic**

   ```bash
   python scripts/run_generate_capacities_competing_traffic.py
   ```

   This step calls `workflows/generate_capacities_competing_traffic.py` to
   evaluate emergency/incumbent demand priorities. Outputs are written into
   the same `data/<scenario_id>_<beam_policy>/` directory as the demands, tagged
   by routing/priority/incumbent-demand/time:
   `competing_flow_<routing>_<priority>_inc<demand>_t<t>.txt` (capacity series),
   `competing_fulfillment_<routing>_<priority>_inc<demand>_t<t>.txt`, and the
   `competing_first_pass_*.json` / `competing_second_pass_*.json` flow
   dictionaries (the incumbent-demand value is slugged, e.g. `0.05` -> `0p05`).

Each workflow shares the same positional arguments (output directory, graph
directory, constellation, ground stations, terminal file, country, flow time,
beam policy, KU-band capacity), so you can invoke them directly if you only need
a single scenario. Let each stage finish before starting the next to ensure all
dependencies are in place.

## Plotting

The figures from the paper, along with any custom visualizations, are generated
via the scripts under `plotting_scripts/`. Each entry reads the data products
from the workflow stages above and drops rendered assets (PDF + PNG) into
`plotting_scripts/out/`.

Run them as modules from the repository root so the shared
`plotting_scripts.common` helpers resolve and the default relative output
directory lands in the right place:

```bash
python -m plotting_scripts.beam_allocation britain
python -m plotting_scripts.routing britain
python -m plotting_scripts.td_bm britain
python -m plotting_scripts.td_bm_utilizations britain 10000 uniform greedy-coordinated max_flow
python -m plotting_scripts.mask_capacities britain
python -m plotting_scripts.vary_incumbent_demand britain
```
