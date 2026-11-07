# scored-rf — how the algorithm works

Policy file: `spectrum_management/scored_rf.py`  
Registered name: `scored-rf` in `beam_mapping.py` `NEW_POLICIES`

## Role in CosmoSim

`scored-rf` only chooses **beams** (which satellite/channel serves which cell). That is RF **admission**.

Afterward, CosmoSim still:

1. Turns the beam map into per-satellite admitted demand (`demands.txt`)
2. Runs **max-flow routing** to compute how much of that demand reaches a ground gateway (**delivered**)
3. Reports **stranded** = admitted − delivered

The policy’s job is to pick beams so admitted traffic is more likely to be deliverable, by scoring demand against estimated egress congestion.

## Scoring formula

Each candidate assignment is scored as:

```text
Score = α·D + β·F − γ·C
```

| Symbol | Meaning | Current value |
|---|---|---|
| **D** | Normalized unmet demand for the cell | used (`α = 0.5`) |
| **F** | Fairness (underserved cells) | not implemented (`β = 0`) |
| **C** | Estimated egress congestion for the satellite | used (`γ = 0.2`) |

Higher score wins. Demand and fairness push a pair up; congestion pushes it down.

## Main loop (Option 2: cell–satellite pairs)

For one simulated second:

1. CosmoSim calls `assign_beams(...)` with cells that have terminals, visible satellites per cell, free beams, shell info, etc.
2. Load the Haiti network graph for that second (`current_simulation_time_s`) to learn:
   - which sats have a ground-station (gateway) neighbor
   - ISL edges and their capacities
3. Repeat until every cell’s unmet demand is 0, or no legal assignment remains:
   - Only consider cells that still have unmet demand
   - For every **legal** `(cell, sat)` pair:
     - visible sat for that cell
     - free channel slot on the cell (at most 8)
     - free beam on the sat
     - passes interference check
     - compute D, F (0), C → score
   - Assign **one** channel to the highest-scoring pair
   - Update the cell’s channel list and that sat’s admitted load (`sat_load`)
4. Return the beam mapping dict: `{cell_channel → color_sat_channel}`

Tie-break if scores are equal: higher raw unmet demand, then cell id, then satellite id.

## D — unmet demand

For each cell:

- **Offered** ≈ number of terminals × 100 Mbps
- **Allocated** = CosmoSim-style admit model: terminals are split across the channels already given to that cell; each channel is capped at Ku beam capacity (1.28 Gbps)
- **Unmet** = max(0, offered − allocated)
- **D** = this cell’s unmet ÷ maximum unmet among all cells (so D ∈ \[0, 1\])

Cells that still need more RF capacity get higher D and are preferred, all else equal.

## F — fairness

Not implemented yet. `β = 0`, so F does not affect the score. Intended later: prefer cells that have been underserved relative to demand over a recent history window.

## C — estimated egress congestion

`C` is a **heuristic inside the policy**, computed while choosing beams. It is **not** CosmoSim’s max-flow result.

**Egress** = how traffic leaves a satellite toward Earth:

- **Local feeder / gateway path:** sat → ground station  
- **1-hop ISL path:** sat → neighboring sat → ground station  

### Capacity

- If the sat has a GS neighbor: local feeder budget = `sat_gs_max_capacity` (~20.8 Gbps)
- Otherwise: local feeder budget = 0
- ISL: use graph edge capacity between sats; the neighbor must have its own feeder budget

### Load

- `sat_load[sat]` = Mbps already admitted onto that sat from channels assigned earlier in this same second

### Residual (remaining egress capacity)

- Local residual = max(0, feeder budget − sat_load)
- For each 1-hop ISL neighbor that has a gateway:  
  residual via that neighbor = min(ISL free capacity, neighbor’s feeder residual)  
  Take the best such neighbor
- With both gateway and ISL awareness on:  
  `residual = max(local residual, best ISL residual)`

### Congestion value for a candidate pair

```text
additional = extra Mbps this new channel would place on the sat
C = 1 − min(1, residual / additional)
```

- Plenty of residual relative to additional → `C ≈ 0` (not congested for this offer)
- Little or no residual → `C → 1` (congested; score is penalized)

So `C` asks: “If I put this next channel on this sat, does it still have path capacity out to ground?”  
It is load-vs-capacity on **satellite egress**, not a full per-link utilization map of the whole network, and it does not currently adjust for `--gw-scale` or custom path impairments.

## Flags

| Flag | Current | Effect |
|---|---|---|
| `USE_GATEWAY` | `True` | Use local feeder residual in `C` |
| `USE_ISL` | `True` | Use 1-hop ISL→gateway residual in `C` |

With both true, the policy uses the **best** of local feeder vs ISL egress when scoring congestion.

## What happens after scored-rf finishes

1. Beam map → admitted demand per satellite  
2. Max-flow on the real capacity graph → delivered traffic  
3. Metrics: requested, admitted, delivered, stranded  

Max-flow is the ground-truth check of whether the network could carry what the policy admitted. `C` only steers beam choices beforehand.
