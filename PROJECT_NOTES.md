# Team guide: CosmoSim for our LEO project

Do sections 1-2 once. After that you only need sections 3-5. Questions: ask Nathan in the team chat.

## 1. Setup (once, about 10 minutes)

WSL2 Ubuntu-22.04. Keep the repo on the Linux side (`~/CosmoSim`), not under `/mnt/c`.

```bash
git clone https://github.com/nkim205/CosmoSim.git ~/CosmoSim && cd ~/CosmoSim
git checkout dev
sudo apt-get update && sudo apt-get install -y libproj-dev proj-data proj-bin libgeos-dev build-essential python3-dev python3.10-venv
python3 -m venv .venv
.venv/bin/pip install -r requirements-lock.txt      # do NOT pip install "cosmosim" (unrelated package)
echo 'export MPLCONFIGDIR=/tmp/mpl' >> ~/.bashrc && source ~/.bashrc
git config --global user.name "Your Name"          # shows up in the results log
```

All inputs are in the repo (terminal files and the 60 network snapshots). You don't generate anything.

## 2. First run (under a minute)

```bash
.venv/bin/python experiments/run_experiment.py --scenarios 1k-uniform --policies greedy-coordinated --duration 3 --no-log
```

Expected last lines:
```
scenario           policy                 isl   gw requested  admitted delivered  stranded no-ch cells violations
1k-uniform         greedy-coordinated       1    1     100.0     100.0     100.0       0.0         0.0          0
```

The numbers (all Gbps, mean per second):
- **requested**: terminals x 100 Mbps.
- **admitted**: what the policy's beams accepted.
- **delivered**: what reached a gateway after routing.
- **stranded**: admitted minus delivered. Accepted by the radio, stuck in the network. Our algorithm should cut this.
- **no-ch cells**: cells with terminals but zero channels. **violations**: broken allocation rules; must be 0.

Read admitted and delivered together. A policy that admits little strands nothing but serves badly.

## 3. Running experiments

```bash
.venv/bin/python experiments/run_experiment.py --quick --no-log --policies baselines my-policy  # while coding, ~1 min
.venv/bin/python experiments/run_experiment.py --policies my-policy --gw-scale 1 0.75 0.5 0.25  # full, logged
```

| Option | Default | Meaning |
|---|---|---|
| `--policies` | `baselines` | Policy names, or `baselines` (the 4 below) or `all`. |
| `--scenarios` | `all` | Names below, or groups `light`, `heavy`, `hotspot`, `wide`, `shift`, `all`. |
| `--gw-scale` | `1` | Multiply gateway capacity (satellite-to-ground links and per-ground-station limit). Several values = sweep. |
| `--isl-scale` | `1` | Multiply inter-satellite link capacity. Several values = sweep. |
| `--start`, `--duration` | `0`, `60` | Simulated seconds (snapshots exist for 0-59). |
| `--quick` | off | `10k-uniform` + `10k-pop`, 5 seconds. |
| `--no-log` | off | Don't add rows to the shared results log. Use for scratch runs. |
| `--resume` | off | Continue an interrupted experiment (same command plus `--resume`). Finished runs are skipped. |
| `--overwrite` | off | Delete the experiment folder and start over. Use this after changing code. |
| `--name`, `--jobs` | auto, cores-2 | Results folder name, parallel runs. |

### Scenarios (demand settings)

| Name | Terminals | Where the demand is |
|---|---|---|
| `1k-uniform`, `10k-uniform` | 1,000 / 10,000 | Even over Haiti's 136 cells |
| `1k-pop`, `10k-pop` | 1,137* / 10,000 | By real population |
| `10k-hotspot-pap`, `10k-hotspot-north` | 10,000 | 8,000 on 5 cells. More than 8 channels can carry, so this tests the radio limit |
| `5k-wide-pap`, `5k-wide-north`, `5k-wide-south` | 5,000 | 2,000 on 20 cells (100 each, about what 8 channels carry). This tests the network |
| `5k-wide-shift` | 5,000 | The wide hotspot moves: pap for seconds 0-19, north 20-39, south 40-59 |

\* upstream rounding bug (appendix B). Locations: pap = Port-au-Prince, north = north coast, south = Les Cayes.

Demand level = 1k vs 5k vs 10k. Hotspot location = pap / north / south. Capacity limits = `--gw-scale`, `--isl-scale`.
Every policy runs on the same files, snapshots, and routing, so results are directly comparable.

Runtime on 12 cores (one run = one scenario x policy x capacity setting x second): about 0.9 runs/s, or about 1.6
runs/s in a capacity sweep (beams are assigned once and reused for every capacity setting). One policy on all 10
scenarios x 60 s at 4 gateway settings is 2,400 runs, about 25 minutes.

## 4. Comparing results (evaluation group)

Every logged experiment adds rows to `results/results_log.csv` (in git): one row per scenario x policy x capacity
setting, means over its seconds. Commit and push it with your code. Simultaneous appends merge without conflicts.

```bash
.venv/bin/python experiments/results_log.py show --experiment baselines_gw_sweep --scenario 10k-pop
.venv/bin/python experiments/results_log.py show --policy my-policy --last 20
```

To compare: take rows with the same `scenario`, `isl_scale`, and `gw_scale`, and read across `policy`. The baselines are
already computed (`baselines_gw_sweep`, `baselines_isl_sweep`). You don't need to rerun them. Run your policy with the
same settings:

```bash
.venv/bin/python experiments/run_experiment.py --policies my-policy --scenarios all --gw-scale 1 0.75 0.5 0.25
.venv/bin/python experiments/run_experiment.py --policies my-policy --scenarios heavy wide shift --isl-scale 0.1
```

To recompute every baseline from scratch: `./experiments/run_all_baselines.sh --overwrite` (about 2 hours).

Useful columns: `delivered_gbps` (throughput), `delivered_pct_of_requested` (demand satisfaction), `stranded_gbps`,
`delivered_min_gbps` (worst second), `no_channel_cells` (starved cells), `rule_violations` (must be 0).

Not available yet: fairness (Jain's index) and per-cell satisfaction after routing. Routing only reports totals per
satellite (section 7).

Per-second detail for plots: `data/runs/<name>/summary.csv` (local, not in git; rerun the experiment to get it).
`manifest.json` in the same folder records the command, commit, and input checksums.

## 5. Adding your own policy

1. Copy `spectrum_management/equal_rf.py` to `spectrum_management/my_policy.py` and change the logic inside
   `assign_beams(...)`. It receives:
   - `prepared_cells`: `[{"cell": h3_id, "num_terminals": n}]`, only cells with terminals
   - `cell_satellites`: `{cell: [satellites that can see it now]}`; `satellite_cells` is the reverse
   - `satellites`, `shell_satellite_indices` (shell 0 = ids 0-1583), `users_per_channel` (12), `cell_population`
2. Return `{"<cell>_<channel>": "<color>_<satellite>_<channel>"}`, channel 0-7, color 0-3.
   Rules: at most 8 channels per cell, each beam used once, only visible satellites, only cells with terminals,
   and call `check_interference(cell, mapping, beam_id)` before assigning. The runner checks all of this.
3. Register it with one line in `spectrum_management/beam_mapping.py`:
   `NEW_POLICIES = {..., "my-policy": assign_my_policy}` (plus the import).
4. Run it (section 3). A crash shows up in that run's `flows.log`.

Each channel admits `min(terminals_on_it x 100, 1280)` Mbps, so extra channels beyond what a cell's terminals need add
nothing.

**Limitation:** a policy does not receive network state (gateway or ISL capacity, or past seconds). If yours needs it,
read the current second from `utils.global_variables.current_simulation_time_s` and load
`graph_generation/graphs_noglobal/starlink_5shells/haiti/graph_<t*10**9>.txt` (pickled NetworkX DiGraph: satellites
0-6363, ground stations 6364+, cells are H3 strings). Each satellite can send at most 20.8 Gbps to the ground.

## 6. Baselines and results

| Policy | What it does |
|---|---|
| `greedy-coordinated` (stock) | Each cell asks for `min(8, ceil(terminals/12))` channels. Busiest cells first, one cell at a time. |
| `greedy-uncoordinated` (stock) | Channel targets scaled to the largest cell. One channel per cell per pass. |
| `equal-rf` (ours) | **Equal allocation of RF.** Ignores demand. Every cell gets one more channel per pass until 8 or no beam fits. |
| `demand-proportional` (ours) | **Demand-based, ignores congestion.** Same total channels as coordinated, split by each cell's share of terminals. |

None of the four looks at ISL or gateway capacity.

All baselines are computed: `baselines_gw_sweep` (all 10 scenarios, gateway x 1, 0.75, 0.5, 0.25) and
`baselines_isl_sweep` (ISL x 0.1 on `heavy`, `wide`, `shift`). 0 rule violations in all 11,040 runs. The sweep
reproduces the earlier experiments (`baselines_normal`, `baselines_gw50`, ...) exactly; use the sweep.

Delivered (stranded), Gbps, mean of 60 s, normal capacity:

| Scenario | Requested | coordinated | uncoordinated | equal-rf | demand-prop. |
|---|---|---|---|---|---|
| 1k-uniform | 100 | 100 (0) | 100 (0) | 100 (0) | 100 (0) |
| 1k-pop | 113.7 | 109.3 (0) | 102.6 (0) | 108.8 (0) | 105.4 (0) |
| 10k-uniform | 1000 | 914.5 (71.7) | **939.4** (60.6) | 922.7 (77.3) | 921.0 (79.0) |
| 10k-pop | 1000 | 577.1 (107.3) | 190.0 (0) | **662.0** (17.9) | 577.3 (106.1) |
| 10k-hotspot-pap | 1000 | **251.2** (0) | 218.9 (0) | 248.5 (0.1) | **251.2** (0) |
| 10k-hotspot-north | 1000 | **251.2** (0) | 218.9 (0) | 250.5 (0.7) | **251.2** (0) |
| 5k-wide-pap | 500 | 415.9 (82.5) | **494.1** (0) | 479.4 (12.6) | 427.6 (70.8) |
| 5k-wide-north | 500 | 415.4 (83.0) | **494.1** (0) | 475.7 (22.7) | 422.3 (76.1) |
| 5k-wide-south | 500 | 415.4 (83.0) | **494.1** (0) | 488.3 (2.1) | 422.9 (75.5) |
| 5k-wide-shift | 500 | 415.7 (82.7) | **494.1** (0) | 476.3 (16.5) | 424.4 (74.0) |

Delivered at gateway x 1 / 0.75 / 0.5 / 0.25:

| Scenario | coordinated | uncoordinated | equal-rf | demand-prop. |
|---|---|---|---|---|
| 10k-uniform | 914 / 873 / 831 / 788 | 939 / 898 / 856 / 812 | 923 / 882 / 839 / 796 | 921 / 879 / 836 / 793 |
| 10k-pop | 577 / 546 / 512 / 470 | 190 / 190 / 190 / 182 | 662 / 630 / 590 / 547 | 577 / 546 / 512 / 470 |
| 5k-wide-pap | 416 / 388 / 361 / 319 | 494 / 494 / 459 / 418 | 479 / 465 / 445 / 404 | 428 / 401 / 373 / 332 |

What it shows:
1. **No baseline wins everywhere.** The best one depends on the scenario (bold). Compare a new algorithm against
   the best baseline for each scenario, not one fixed baseline.
2. **All stranding at normal capacity is shell-0 overload.** Shell 0 (satellites 0-1583) has no ISLs, and each
   satellite can send at most 20.8 Gbps to a gateway. In every case we checked (10k-uniform, 10k-pop, 5k-wide-pap,
   all 4 policies), stranded traffic equals shell-0 demand above 20.8 Gbps per satellite. Coordinated and
   demand-proportional put about 40% of concentrated demand on shell 0; uncoordinated and equal-rf about 25%.
   This is where a gateway-aware algorithm can gain.
3. **ISL capacity barely matters in Haiti.** At ISL x 0.1, delivered drops by at most 8.4 Gbps (10k-uniform). Report it
   as a finding.
4. **Gateway capacity matters.** Each 25% cut costs about 40 Gbps on 10k-uniform for every policy.
5. **Sharp hotspots hit the radio limit.** 5 cells x 8 channels x 1.28 Gbps = 51.2 Gbps for 800 Gbps of demand there.
   251.2 is the most any policy can admit, so no algorithm can beat it at normal capacity.
6. **Light load (1k) has nothing to fix.** Demand-proportional leaves 17 cells with no channel on 1k-pop (their
   terminal share rounds to 0 channels). Coordinated gives every cell at least one.
7. **Shifting hotspot:** these 4 baselines don't use past seconds, so each second equals the fixed-location file for
   that second (checked: all 960 rows match). Shifting only changes results for a policy that remembers past seconds.

## 7. Open items

| Item | Owner |
|---|---|
| Per-cell delivered traffic (needed for fairness and per-cell satisfaction) | **Unassigned** |
| Network state passed to policies | Algorithm group |
| Is "shell 0 has no ISLs" intentional upstream? Our bottleneck finding relies on it. | Ask Prof. Saeed |
| Latency, queues, loss | Not modeled by CosmoSim. Report as unsupported. |

## 8. Ground rules
- Don't edit or regenerate shared inputs (terminal files, schedules, graphs).
- Don't change original policies or `utils/global_variables.py`. Add new files and flags.
- Always `max_flow` routing and Ku 1.28. Never Ku 2.5 (it silently doubles ISL capacity).
- Commit code before runs you plan to report. Report numbers from `results/results_log.csv`.

---

# Appendix (reference)

## A. Pipeline (what the runner calls)
| Step | Script | Output |
|---|---|---|
| Terminals | `terminal_deployment/generate_cell_allocations.py`, `generate_hotspots.py` | `terminal_deployment/terminals/cells_haiti_0_<N>_<kind>.txt` (cell, terminals) |
| Graphs | `graph_generation/generate_graphs.py` | `graph_generation/graphs_noglobal/starlink_5shells/haiti/graph_<t_ns>.txt` (one per second) |
| Beams + demand | `workflows/generate_flows.py` | `beam_assignments_<t_ns>.pkl`, `demands.txt` (admitted per satellite) |
| Routing | `workflows/generate_capacities_scaled.py` | `max_flow_<t>.txt` (`time_ns,delivered_Mbps`) |

One second by hand:
```bash
G=graph_generation/graphs_noglobal/starlink_5shells/haiti; S=cells_haiti_0_10000_uniform; O=data/mine/t5
.venv/bin/python workflows/generate_flows.py $O $G starlink_5shells ground_stations_starlink $S.txt haiti 5 greedy-coordinated 1.28
.venv/bin/python workflows/generate_capacities_scaled.py $O $G starlink_5shells ground_stations_starlink \
  terminal_deployment/terminals/$S.txt haiti 5 greedy-coordinated 1.28 --routing max_flow --duration 1 --gw-scale 0.5
.venv/bin/python analysis/summarize_run.py $O $S.txt
.venv/bin/python analysis/bottleneck_census.py $O $G terminal_deployment/terminals/$S.txt 5 greedy-coordinated \
  --duration 1 --gw-scale 0.5 --out $O/census.csv     # which link type limits throughput
```

## B. Shared inputs
| File (`cells_haiti_0_...`) | Terminals | Min / max per cell | sha256 prefix |
|---|---|---|---|
| `1000_uniform` | 1000 | 7 / 9 | a7eb7c00 |
| `1000_population` | 1137 | 1 / 146 | 7e186414 |
| `10000_uniform` | 10000 | 73 / 76 | 81e273f6 |
| `10000_population` | 10000 | 1 / 1455 | 4a50e4f4 |
| `10000_hotspot_pap`, `_north` | 10000 | 15 / 1600 | 92ca374f, b05eb267 |
| `5000_wide_pap`, `_north`, `_south` | 5000 | 25 / 100 | 9e74d8cd, 2bed6524, c9eb3826 |

- Uniform and population files: `generate_cell_allocations.py haiti {1000,10000} {uniform,population}`. Upstream bug:
  `density_cells` overshoots on rounding (1001) and then adds one terminal to every cell (1137). `uniform` places
  leftovers with unseeded randomness, so never regenerate these.
- Hotspot files and `cells_haiti_0_5000_wide_shift.schedule`: `terminal_deployment/generate_hotspots.py`. A hotspot
  is the N cells nearest a fixed point (pap 18.490,-72.320; north 19.900,-72.841; south 18.193,-73.750), with
  terminals split evenly inside it and outside it. Hotspots of the same kind don't overlap. The script refuses
  to change existing files.
- A `.schedule` file is `first_second,terminal_file` lines. The runner uses each file from its second until the next
  line. Results report the schedule as one scenario, and `summary.csv` has a `terminal_file` column per second.
- Graphs: `generate_graphs.py ... --skip-global-cells --graphs-dir graph_generation/graphs_noglobal`, one per second
  for 0-59. The flag skips about 6,500 worldwide cells this workflow never uses (16 min -> 32 s per snapshot).
  Verified at t=0: identical edges and identical demands, beam assignments, and max_flow vs the stock graph.

## C. What we changed (original policies unchanged; verified byte-identical on 80 runs)
- `graph_generation/generate_graphs.py`: opt-in `--skip-global-cells`.
- `spectrum_management/beam_mapping.py`: `NEW_POLICIES` registry.
- `workflows/generate_flows.py`, `workflows/generate_capacities.py`: accept names from the registry.

New: `spectrum_management/{equal_rf,demand_proportional,validate_mapping}.py`,
`terminal_deployment/generate_hotspots.py` + hotspot/schedule files, `experiments/{run_experiment,results_log}.py`,
`experiments/run_all_baselines.sh`, `results/results_log.csv`, `.gitattributes`,
`workflows/generate_capacities_scaled.py` + `traffic_engineering/capacity_scaling.py` (scale the routing graph
after the stock gateway assignment; identical to stock at 1.0), `analysis/{bottleneck_census,summarize_run}.py`,
`experiments/phase1_stock_baselines.sh` (older runner), `requirements-lock.txt`.

## D. Code facts
- Routing flow: `T -> ground station -> satellite -> (ISLs) -> D<sat> -> S`.
- Gateway capacity: assigned by demand in 2,600 Mbps steps, then each gateway-visible satellite is topped up to
  20.8 Gbps. Each ground station tops out at 166.4 Gbps.
- Co-channel rule: a cell and its 1-ring neighbors can't share a (satellite, channel). 4 colors x 8 channels =
  32 beams per satellite (about 41 Gbps, about 2x its 20.8 Gbps gateway cap).
- Shell 0 (satellites 0-1583) has no ISLs in this constellation file. Its traffic must go straight to a gateway.
- Don't use `scripts/run_*.py`: every flow time writes to the same folder.
