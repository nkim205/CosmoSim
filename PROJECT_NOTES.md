# Team guide: CosmoSim for our LEO project

Start here. Follow sections 1-2 once (about 15 minutes). After that you'll mostly use sections 3 and 4.
Questions: ask Nathan in the team chat.

---

## 1. One-time setup (about 10 minutes)

Use WSL2 **Ubuntu-22.04** (not the docker-desktop distro). Keep the repo on the Linux side (e.g. `~/CosmoSim`), not under `/mnt/c`.

```bash
git clone https://github.com/nkim205/CosmoSim.git ~/CosmoSim
cd ~/CosmoSim
git checkout nathan            # our working branch (until we set up a team branch)

sudo apt-get update && sudo apt-get install -y libproj-dev proj-data proj-bin libgeos-dev build-essential python3-dev python3.10-venv
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip wheel setuptools
.venv/bin/pip install -r requirements-lock.txt     # exact versions we used; do NOT pip install "cosmosim"
echo 'export MPLCONFIGDIR=/tmp/mpl' >> ~/.bashrc && source ~/.bashrc
git config --global user.name "Your Name"         # shows up in the shared results log; needed to commit
git config --global user.email "you@gatech.edu"
```

Everything you need is in the repo: the 4 Haiti terminal files and the 60 network snapshots. You don't have to
generate anything.

## 2. Your first run (under a minute)

From the repo root:

```bash
.venv/bin/python experiments/run_experiment.py --scenarios 1k-uniform --policies greedy-coordinated --duration 3 --no-log
```
(`--no-log` keeps this setup check out of the shared results log.)

You should see:

```
scenario     policy                 requested  admitted delivered  stranded no-ch cells violations
1k-uniform   greedy-coordinated         100.0     100.0     100.0       0.0         0.0          0
```

If your numbers match, your setup is correct.

**What just happened:** for each of 3 simulated seconds, the policy `greedy-coordinated` gave out satellite radio
beams to Haiti's 136 cells (1,000 user terminals spread evenly). Then max-flow routing computed how much of that
traffic actually reaches a ground gateway.

### The 4 numbers you will see everywhere (all in Gbps)
| Number | Meaning |
|---|---|
| **requested** | What users want: terminals x 100 Mbps. |
| **admitted** | What the policy's beams accepted (cells with few beams are not admitted in full). |
| **delivered** | What actually reaches a gateway after routing. |
| **stranded** | admitted - delivered: accepted on the radio link but stuck in the network. **This is the waste our algorithm should reduce.** |

Also **no-ch cells** = cells that have terminals but got zero beams (fully starved), and **violations** = broken
allocation rules (should always be 0; see section 4).

Always read admitted and delivered together. A policy that admits very little strands nothing but serves badly.

## 3. Running experiments

One command runs a set of scenarios and policies over a time window, then prints a summary and writes a table.

```bash
.venv/bin/python experiments/run_experiment.py [options]
```

| Option | Default | What it changes |
|---|---|---|
| `--quick` | off | Fast dev check: heavy scenarios only (`10k-uniform`, `10k-pop`), 5 seconds. About 30 s for 3 policies. |
| `--policies` | `baselines` | Which beam policies to compare: `greedy-coordinated`, `greedy-uncoordinated`, `equal-rf`, any you add (section 4). Shortcuts: `baselines` (those 3) and `all` (every runnable policy). Mix freely: `--policies baselines my-policy`. |
| `--scenarios` | `all` | `1k-uniform`, `1k-pop`, `10k-uniform`, `10k-pop`. Shortcuts: `all`, `heavy` (10k), `light` (1k). 1k vs 10k = light vs heavy load; uniform vs pop = even vs concentrated demand. |
| `--start`, `--duration` | `0`, `60` | Which simulated seconds (snapshots exist for 0-59). |
| `--isl-scale` | `1.0` | Multiply inter-satellite link capacity (e.g. `0.5` = half). |
| `--gw-scale` | `1.0` | Multiply gateway capacity (satellite-to-ground links and per-ground-station limit). |
| `--name` | automatic | Results folder `data/runs/<name>/`. Default is date + policies + scales, e.g. `1030-154210_baselines_gw0.5`. |
| `--no-log` | off | Don't add this run to the shared results log (use for scratch/debug runs). |
| `--jobs`, `--overwrite` | cores - 2, off | Parallel runs; allow reusing an existing `--name`. |

Typical commands:

```bash
.venv/bin/python experiments/run_experiment.py --quick --policies baselines my-policy   # while developing (~1 min)
.venv/bin/python experiments/run_experiment.py --policies baselines my-policy           # full: 4 scenarios x 60 s
.venv/bin/python experiments/run_experiment.py --policies baselines --gw-scale 0.5      # stress: gateways halved
```

Runtime: each run (one scenario x policy x second) takes about 7-10 s, and about 10 run in parallel. The full
4 scenarios x 3 policies x 60 s is 720 runs, about 13 minutes; `--quick` with 3 policies is about 30 s.

Every run is also checked against the allocation rules (section 4). If anything breaks a rule, the summary shows a
`violations` count and a warning pointing to `rule_violations.txt`. Treat any nonzero count as a bug in the policy.

### The shared results log (everyone's results in one place)
Every successful experiment adds rows to **`results/results_log.csv`**: one row per scenario x policy, with means over
the seconds it ran, plus who ran it and the capacity scales. The file is in git, so
**commit and push it with your code** and everyone sees your results after `git pull`. Two people appending at once
merge automatically (no conflicts; `.gitattributes` uses git's union merge).

```bash
.venv/bin/python experiments/results_log.py show                                   # everything
.venv/bin/python experiments/results_log.py show --scenario 10k-pop --policy equal  # filter (substring match)
.venv/bin/python experiments/results_log.py show --who Nathan --last 10            # also --experiment
.venv/bin/python experiments/results_log.py log data/runs/<name>                   # add a --no-log run later
```

Columns: `logged_at, who, experiment, scenario, policy, start_s, seconds, isl_scale, gw_scale, requested_gbps,
admitted_gbps, delivered_gbps, delivered_min_gbps, stranded_gbps, stranded_pct_of_admitted,
delivered_pct_of_requested, no_channel_cells, rule_violations, sec_per_run`. Never edit or delete other people's rows.
Use `--no-log` for scratch runs so the log stays readable.

### What you get in `data/runs/<name>/` (local; per-second detail)
- `summary.csv`: **the results table**, one row per scenario x policy x second. Columns: `experiment, scenario, policy, t_s,
  isl_scale, gw_scale, requested_mbps, admitted_mbps, delivered_mbps, stranded_mbps, channels, cells_with_terminals,
  cells_with_no_channel, rule_violations, flows_s, capacities_s` (the last two are runtimes in seconds). Load it with pandas for plots.
- `manifest.json`: the exact command, date, git commit and branch, uncommitted files, and terminal-file checksums. This is
  what makes a result reproducible; keep it with any number you report.
- `rule_violations.txt` (only if a rule was broken): inside the failing run's folder, one line per problem.
- `git_diff.patch`: your uncommitted code changes at run time.
- `<scenario>/<policy>/t<second>/`: raw files per run (beam assignments, `demands.txt`, `max_flow_<t>.txt`, logs).
  If a run fails, its `flows.log` / `capacities.log` says why.

## 4. Running your own policy (new code)

A policy is one Python function that decides which satellite beams serve which cells at one second. Use
`spectrum_management/equal_rf.py` as your template: it is short and complete.

**Step 1: create your file**, e.g. `spectrum_management/my_policy.py`, with this function:

```python
def assign_beams(prepared_cells, satellites, satellite_cells, cell_satellites, config,
                 shell_satellite_indices, users_per_channel, cell_population):
    ...
    return mapping
```

What you get:
| Argument | Contents |
|---|---|
| `prepared_cells` | list of `{"cell": "<h3 id>", "num_terminals": int}`, only cells with at least 1 terminal |
| `cell_satellites` | `{cell: [satellite ids that can see this cell now]}` |
| `satellites` | sorted list of all candidate satellite ids |
| `satellite_cells` | `{satellite: [cells it can see]}` |
| `shell_satellite_indices` | `[(first_id, last_id+1), ...]` per orbital shell (shell 0 = ids 0-1583) |
| `users_per_channel` | 12 (terminals one channel can serve at 1.28 Gbps) |
| `cell_population` | `{cell: population}` |

What you return: a dict `{"<cell>_<channel>": "<color>_<satellite>_<channel>"}`, channel 0-7, color 0-3.
Example: `{"854c8867fffffff_0": "2_4316_0"}` = cell 854c88... channel 0 is served by satellite 4316, color 2.

Rules your policy must follow (copy the pattern from `equal_rf.py`):
- At most 8 channels per cell; each beam string used at most once (track with `initialize_beam_state`).
- Only use satellites in `cell_satellites[cell]`.
- Check `check_interference(cell, mapping, beam_id)` before assigning. A cell and its neighbors can't share the same
  satellite and channel.
- Only give channels to cells that have terminals.

The runner checks all of these after every run (`spectrum_management/validate_mapping.py`) and reports `violations`.

How demand follows from your mapping: a cell's terminals are split across its channels, and each channel admits
`min(terminals_on_it x 100, 1280)` Mbps. Giving a cell more channels than it needs does not add demand.

**Step 2: register it (one line).** In `spectrum_management/beam_mapping.py`, import it and add it to `NEW_POLICIES`:

```python
from .my_policy import assign_beams as assign_my_policy
NEW_POLICIES = {
    "equal-rf": assign_equal_rf,
    "my-policy": assign_my_policy,     # <- add
}
```

That's all. The name now works everywhere (the runner, `generate_flows.py`, `generate_capacities*.py`).

**Step 3: run it next to the baselines,** under identical conditions:

```bash
.venv/bin/python experiments/run_experiment.py --quick --no-log --policies baselines my-policy   # while iterating
.venv/bin/python experiments/run_experiment.py --policies baselines my-policy                    # full 60 s, logged
```
If a run crashes, the runner prints which log to open (`flows.log` holds your policy's traceback).

**Current limitation (algorithm group, read this):** a policy only sees the inputs above. It does **not** yet receive
network state (ISL or gateway capacity, or last second's results). Until the per-snapshot workflow exists, a policy that
needs it can read the current second from `utils.global_variables.current_simulation_time_s` (set before the policy runs)
and load `graph_generation/graphs_noglobal/starlink_5shells/haiti/graph_<t*10**9>.txt` itself (a pickled NetworkX
DiGraph; satellites are ints 0-6363, ground stations 6364+, cells are H3 strings; ground-station->satellite edges are
gateway links, satellite<->satellite edges are ISLs). Note the stock code caps each satellite's total gateway capacity
at 20.8 Gbps (`utils/global_variables.py: sat_gs_max_capacity`).

## 5. What we know so far (Haiti, t=0-59 s, normal capacity)

Mean Gbps per second; demand recomputed every second.

Values are coordinated / uncoordinated / equal-rf (experiments `baselines_normal` and `baselines_gw50` in the log).

| Scenario | Requested | Admitted | Delivered | Stranded | Stranded, gateways x0.5 |
|---|---|---|---|---|---|
| 1k uniform | 100 | 100 / 100 / 100 | 100 / 100 / 100 | 0 / 0 / 0 | 0 / 0 / 0 |
| 1k population | 113.7* | 109.3 / 102.6 / 108.8 | 109.3 / 102.6 / 108.8 | 0 / 0 / 0 | 0.3 / 0 / 0 |
| 10k uniform | 1000 | 986.2 / 1000 / 1000 | 914.5 / 939.4 / 922.7 | 71.7 / 60.6 / 77.3 | 155.3 / 144.4 / 160.8 |
| 10k population | 1000 | 684.3 / 190.0 / 679.9 | 577.1 / 190.0 / 662.0 | 107.3 / 0 / 17.9 | 172.6 / 0 / 90.3 |

\* this file has 1,137 terminals, not 1,000, because of an upstream rounding bug (appendix B).

What it means:
1. **Light load (1k): nothing to fix.** Everything admitted is delivered.
2. **Heavy load (10k): the problem is real.** The simple policies strand 60-107 Gbps every second.
3. **The bottleneck is the satellite-to-gateway link, not ISLs.** Satellites 0-1583 (shell 0) have no ISLs in this
   constellation, and each satellite can send at most 20.8 Gbps to the ground. Policies give some shell-0 satellites
   about 29 Gbps, and the excess has no way out. ISLs never saturated: at 50% ISL capacity there was no change, and at 10%
   the loss was under 1%. At 50% gateway capacity, about 9% was lost.
4. **For the algorithm:** gateway awareness has room to help in Haiti; ISL awareness will likely show about zero gain
   here. That's a legitimate result, and we should report it, not hide it.
5. **Equal RF** admits about the same as greedy-coordinated at 10k population (679.9 vs 684.3) but strands far less
   (17.9 vs 107.3), so it delivers the most of any baseline there (662.0). Why is not yet measured. It is the baseline
   to beat at 10k population, not a straw man.
6. **Halving gateway capacity adds 65-84 Gbps of stranding** at 10k for every policy (except uncoordinated at 10k
   population, which admits too little to hit the limit), so `--gw-scale` is the stress knob that matters here.

Open question: is it intentional upstream that shell 0 has no ISLs? Check before we rely on it in the report.

## 6. What's missing and who needs it

| Gap | Why it matters | Owner |
|---|---|---|
| Per-cell delivered traffic | Needed for fairness (Jain's index), per-cell satisfaction, starved cells after routing. Today routing only knows totals per satellite. | **Unassigned: decide in chat** |
| Network state passed to policies | The bottleneck-aware algorithm needs it (see section 4 limitation). | Algorithm group + whoever takes per-cell |
| Demand-proportional baseline | Promised in PR1. Must differ clearly from `greedy-uncoordinated`, which is already roughly proportional. | Nathan |
| Hotspot / shifting-hotspot scenarios | Promised in PR1. | Nathan |
| Latency, queues, loss | CosmoSim doesn't model them. Report as unsupported. | n/a |

## 7. Ground rules
- Don't edit or regenerate the shared inputs (terminal files, graphs). Everyone must run on identical inputs.
- Don't change original policies or `utils/global_variables.py`. Add new files and flags instead.
- Use `max_flow` routing and Ku 1.28 for all comparisons. Never use Ku 2.5: it silently doubles ISL capacity.
- Commit your code before runs you plan to report, so `manifest.json` points to a real commit.
- Report numbers from `results/results_log.csv`, and keep the matching `data/runs/<name>/` folder (its
  `manifest.json` has the commit and exact command) until the report is done.

---

# Appendix (reference; skip unless you need it)

## A. How CosmoSim works (the 4 steps the runner calls)
| Step | Script | Output |
|---|---|---|
| 1. Terminals | `terminal_deployment/generate_cell_allocations.py` | `terminal_deployment/terminals/cells_haiti_0_<N>_<dist>.txt` (cell, terminals) |
| 2. Graphs | `graph_generation/generate_graphs.py` | `graph_generation/graphs_noglobal/starlink_5shells/haiti/graph_<t_ns>.txt`, the network at each second. It's a pickled Python object, not a picture. |
| 3. Beams + demand | `workflows/generate_flows.py` | `beam_assignments_<t_ns>.pkl`, `demands.txt` (admitted, per satellite) |
| 4. Routing | `workflows/generate_capacities.py` / `generate_capacities_scaled.py` | `max_flow_<t>.txt` (`time_ns,delivered_Mbps`) |

Running steps 3-4 by hand for one second (what the runner does for each row):
```bash
G=graph_generation/graphs_noglobal/starlink_5shells/haiti; S=cells_haiti_0_10000_uniform; POL=greedy-coordinated; O=data/mine/t5
.venv/bin/python workflows/generate_flows.py $O $G starlink_5shells ground_stations_starlink $S.txt haiti 5 $POL 1.28
.venv/bin/python workflows/generate_capacities_scaled.py $O $G starlink_5shells ground_stations_starlink \
  terminal_deployment/terminals/$S.txt haiti 5 $POL 1.28 --routing max_flow --duration 1 --gw-scale 0.5
.venv/bin/python analysis/summarize_run.py $O $S.txt                      # requested/admitted/delivered/stranded
.venv/bin/python analysis/bottleneck_census.py $O $G terminal_deployment/terminals/$S.txt 5 $POL \
  --duration 1 --gw-scale 0.5 --out $O/census.csv                           # which link type limits throughput
```
`G`, `S`, `POL`, `O` are just shell shortcuts: graph folder, terminal file, policy, output folder.

## B. Shared inputs and how they were made
- Terminal files: `generate_cell_allocations.py haiti {1000,10000} {uniform,population}`.

  | file | total terminals | min / max per cell | sha256 prefix |
  |---|---|---|---|
  | 1000_uniform | 1000 | 7 / 9 | a7eb7c00 |
  | 1000_population | 1137 | 1 / 146 | 7e186414 |
  | 10000_uniform | 10000 | 73 / 76 | 81e273f6 |
  | 10000_population | 10000 | 1 / 1455 | 4a50e4f4 |

  The upstream bug: `density_cells` rounds each cell's share. If rounding overshoots (Haiti 1000: 1001), the leftover
  loop never reaches 0 and adds a terminal to every cell (1001 + 136 = 1137). `uniform` places leftovers with unseeded
  randomness, so a regenerated file would differ.
- Graphs: `seq 0 59 | xargs -P 10 -I{} .venv/bin/python graph_generation/generate_graphs.py -c starlink_5shells -g ground_stations_starlink -n haiti --start {} --duration 1 --skip-global-cells --graphs-dir graph_generation/graphs_noglobal`
  (7.5 min). `--skip-global-cells` is our opt-in flag: it skips about 6,500 worldwide cells that only the deferred
  competing-traffic workflow uses (16 min -> 32 s per snapshot). Verified at t=0: identical edges, and identical
  `demands.txt` / beam assignments / `max_flow` vs stock graphs for both built-in policies.

## C. Bottleneck census (stock mode, t=0..59, normal capacity; mean Gbps)
`analysis/bottleneck_census.py` reruns the stock routing on the same graph (totals checked against stock) and reports
the min-cut capacity per link type. The largest class is the limit.

| scenario | policy | stranded | cut: access | cut: feeder | cut: ISL | cut: GS aggregate |
|---|---|---|---|---|---|---|
| 1k uniform | coordinated | 1.4 | 98.6 | 0 | 0 | 0 |
| 1k population | coordinated | 4.5 | 104.8 | 0 | 0 | 0 |
| 10k uniform | coordinated | 79.5 | 764.2 | 156.3 | 0 | 0 |
| 10k uniform | uncoordinated | 71.9 | 771.8 | 156.3 | 0 | 0 |
| 10k population | coordinated | 113.1 | 456.5 | 114.7 | 0 | 0 |
| 10k population | uncoordinated | 3.0 | 186.9 | 0 | 0 | 0 |

"Access" = satellite admitted demand (in the cut when fully served). "Feeder" = satellite-to-gateway links. In stock
mode the t=0 demand is reused while satellites move, so a few satellites drift out of gateway view. That's why the
runner recomputes demand every second.

Stress check (10k uniform, coordinated, stock mode, mean delivered): normal 920.5; gateway x0.5 -> 838.2; ISL x0.5 ->
920.5; ISL x0.1 -> 912.6.

## D. What we changed in the original code (behavior of original policies unchanged; verified)
- `graph_generation/generate_graphs.py`: opt-in `--skip-global-cells` flag.
- `spectrum_management/beam_mapping.py`: `NEW_POLICIES` registry and `POLICY_NAMES`. The original 4 policies run
  exactly as before.
- `workflows/generate_flows.py`: policy choices come from `POLICY_NAMES`.
- `workflows/generate_capacities.py`: also accepts names in `NEW_POLICIES` (the name is only a label there).
- Check: 80 built-in-policy runs through the new path (4 scenarios x 2 policies x 10 s) gave byte-identical
  `demands.txt`, beam assignments, and `max_flow` files vs the earlier baseline runs.

New files: `spectrum_management/equal_rf.py`, `spectrum_management/validate_mapping.py`, `experiments/run_experiment.py`, `experiments/results_log.py`,
`results/results_log.csv`, `.gitattributes`, `workflows/generate_capacities_scaled.py`,
`traffic_engineering/capacity_scaling.py` (scaling is applied to the routing graph after the stock gateway
assignment; byte-identical to stock at 1.0), `analysis/bottleneck_census.py`, `analysis/summarize_run.py`,
`experiments/phase1_stock_baselines.sh` (older runner, used for appendix C), `requirements-lock.txt`.

## E. Code facts worth knowing
- Stock routing flow: `T -> ground station -> satellite -> (ISLs) -> D<sat> -> S`. `T` is named `super_sink` but is the source.
- Gateway capacity is assigned in 2 passes: by demand in 2,600 Mbps steps, then every gateway-visible satellite is
  topped up to 20.8 Gbps whatever its demand. Each ground station tops out at 166.4 Gbps.
- The co-channel rule ignores color: a cell and its 1-ring neighbors can't share a (satellite, channel). The 4 colors
  give each satellite 32 beams (about 41 Gbps of access, roughly 2x its 20.8 Gbps gateway cap).
- `greedy-coordinated`: cells want `min(8, ceil(terminals/12))` channels; highest demand first. `greedy-uncoordinated`:
  one channel per cell per pass, targets scaled to the largest cell (at 10k population almost every cell gets 1 channel,
  hence 190 Gbps).
- Don't use `scripts/run_*.py` (the batch scripts): all flow times write to one folder and `demands.txt` is last-writer-wins.
- The timestamp bug (`10**10` -> `10**9` ns) was already fixed upstream on `dev`; credit upstream.
- Install on Oct 29 needed no build fixes. Versions are pinned in `requirements-lock.txt` (numpy 2.2.6, networkx 3.4.2,
  h3 4.5.0, ephem 4.2.1, astropy 6.1.7).
