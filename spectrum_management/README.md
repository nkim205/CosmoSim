# Spectrum Management

This package tracks the beam-management experiments that sit between terminal placement and the traffic-routing workflows. It contains:

| Component | Purpose |
| --- | --- |
| `common.py`, `interference.py`, `constants.py` | Shared helpers for normalizing cells/satellites, enforcing per-beam constraints, running interference checks, and defining limits such as `MAX_CHANNELS_PER_CELL`. |
| `beam_mapping.py` | Policy dispatcher used by workflows. It prepares the inputs and routes the request to a specific algorithm. |
| `greedy_uncoordinated.py` | Baseline algorithm that greedily assigns beams without cross-shell coordination. |
| `greedy_coordinated.py` | Coordinated variant that balances assignments across shells and honors user-priority heuristics. |
| `greedy_uncoordinated_inr_aware.py` | INR-aware variant of the greedy-uncoordinated policy that verifies aggregate $I/N$ on all cells receiving a particular channel against a specified threshold before accepting a beam assignment. |
| `greedy_coordinated_inr_aware.py` | INR-aware variant of the greedy-coordinated policy that verifies aggregate $I/N$ on all cells receiving a particular channel against a specified threshold before accepting a beam assignment. |
| `equal_rf.py` | Project baseline: equal RF allocation. Ignores demand; round-robin, one more channel per cell per pass. |
| `demand_proportional.py` | Project baseline: greedy-coordinated's total channel count, split by each cell's terminal share (largest remainder, cap 8). Ignores network state. |
| `validate_mapping.py` | Checks a mapping against the allocation rules (channel range, visibility, unique beams, co-channel). Used by `experiments/run_experiment.py`. |

## Input and Output Contract

Every beam-mapping policy implements an `assign_beams(...)` function with the signature used in the greedy implementations:

```python
assign_beams(
    prepared_cells: Sequence[Mapping[str, int]],
    satellites: Sequence[int],
    satellite_cells: Mapping[int, Sequence[str]],
    cell_satellites: Mapping[str, Sequence[int]],
    config: str,
    shell_satellite_indices: Sequence[Sequence[int]],
    users_per_channel: int,
    cell_population: Mapping[str, int],
) -> Dict[str, str]
```

Key expectations:

- `prepared_cells` is produced via `common.prepare_cells` and contains per-cell demand metadata.
- `satellites` is the normalized list of satellite IDs (`common.normalize_satellite_list`).
- `satellite_cells` and `cell_satellites` describe feasible connections; algorithms may ignore whichever mapping they do not need.
- `shell_satellite_indices` lists `[start, end)` index ranges per orbital shell.
- The return value maps `"{cell_id}_{channel_idx}"` ➜ `"{freq}_{sat}_{channel_idx}"`, i.e., user channels to beam identifiers.

Algorithms should only mutate their local state and return the mapping; all logging is optional but encouraged (see the greedy variants for formatting).

## Adding a New Beam-Management Algorithm

1. Create a module (e.g., `my_policy.py`) inside `spectrum_management/` and implement `assign_beams` with the signature above. Reuse helpers from `common.py` such as `initialize_beam_state`, `candidate_sats`, or `coordinated_priorities` when possible.
2. Register the policy in `beam_mapping.py` by importing your `assign_beams` function and adding it to `NEW_POLICIES`. The workflows and `experiments/run_experiment.py` then accept the name.
3. Document any configuration knobs or assumptions inside the module and ensure the function returns the mapping described above.
4. Update any scripts or configs that reference beam policies so they can opt into the new identifier.

Following this pattern keeps algorithms discoverable and ensures they work with the existing workflows and plotting utilities.

## Interference Checks

`interference.py` exposes `check_interference(...)`, which each policy calls before committing a beam. The helper currently enforces co-channel isolation through `check_cochannel_interference(...)`, preventing the same satellite/beam index from being reused by a cell or any of its adjacent hex neighbors. Additional interference screens can be layered into `check_interference` without modifying the greedy policies, so keep this module in mind when introducing new spatial or spectral guardrails.

`interference_rf.py` exposes RF geometry, TLE orbital propagation, and ITU antenna gain pattern standards (ITU-R S.1528 for satellite transmitters and ITU-R S.1428 for ground receivers). It powers the INR-aware policies by calculating path loss, off-axis directional gains, and received co-channel interference power in Watts to verify aggregate $I/N$ against designated thresholds.
