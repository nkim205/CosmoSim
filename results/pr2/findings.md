# PR2 auto-generated findings (verify before quoting)

- Runs: 5340 kept, 480 dropped so every method in a case covers the same seconds.
- Rule violations: 0; consistency failures: 0.
- Max starvation rate (cells with demand but zero delivery) in any run: 0.000.

## Proposed vs best baseline (delivered throughput)

| Case | Best baseline | Baseline | Proposed | Δ Gbps | Δ % | vs Equal RF | Stranded (base→prop) | Jain (base→prop) | n s |
|---|---|---:|---:|---:|---:|---:|---|---|---:|
| 10k-hotspot-north | Demand-proportional | 251.2 | 251.2 | +0.0 | +0.0% | +0.3% | 0.0→0.0 | 0.968→0.968 | 60 |
| 10k-hotspot-pap | Demand-proportional | 251.2 | 251.2 | +0.0 | +0.0% | +1.1% | 0.0→0.0 | 0.968→0.968 | 60 |
| 10k-uniform | Greedy-uncoordinated | 939.4 | 986.7 | +47.3 | +5.0% | +6.9% | 60.6→13.3 | 0.996→1.000 | 60 |
| 10k-uniform · GW×0.25 | Greedy-uncoordinated | 812.4 | 774.0 | -38.4 | -4.7% | -2.8% | 187.6→226.0 | 0.959→0.985 | 60 |
| 10k-uniform · GW×0.5 | Greedy-uncoordinated | 855.5 | 837.0 | -18.5 | -2.2% | -0.3% | 144.4→163.0 | 0.977→0.992 | 60 |
| 10k-uniform · GW×0.75 | Equal RF | 881.6 | 958.8 | +77.2 | +8.8% | +8.8% | 118.4→41.2 | 0.967→0.998 | 60 |
| 1k-uniform | Equal RF | 100.0 | 100.0 | +0.0 | +0.0% | +0.0% | 0.0→0.0 | 1.000→1.000 | 60 |
| 1k-uniform · GW×0.25 | Equal RF | 100.0 | 100.0 | +0.0 | +0.0% | +0.0% | 0.0→0.0 | 1.000→1.000 | 60 |
| 1k-uniform · GW×0.5 | Equal RF | 100.0 | 100.0 | +0.0 | +0.0% | +0.0% | 0.0→0.0 | 1.000→1.000 | 60 |
| 1k-uniform · GW×0.75 | Equal RF | 100.0 | 100.0 | +0.0 | +0.0% | +0.0% | 0.0→0.0 | 1.000→1.000 | 60 |
| 5k-wide-north | Greedy-uncoordinated | 494.1 | 498.2 | +4.1 | +0.8% | +4.7% | 0.0→0.2 | 1.000→1.000 | 60 |
| 5k-wide-pap | Greedy-uncoordinated | 494.1 | 498.3 | +4.2 | +0.9% | +3.9% | 0.0→0.1 | 1.000→1.000 | 60 |
| 5k-wide-pap · GW×0.25 | Greedy-uncoordinated | 417.6 | 492.1 | +74.5 | +17.8% | +21.9% | 76.5→6.3 | 0.952→0.999 | 60 |
| 5k-wide-pap · GW×0.5 | Greedy-uncoordinated | 458.7 | 498.3 | +39.6 | +8.6% | +12.0% | 35.4→0.1 | 0.990→1.000 | 60 |
| 5k-wide-pap · GW×0.75 | Equal RF | 464.8 | 498.2 | +33.4 | +7.2% | +7.2% | 27.2→0.2 | 0.991→1.000 | 60 |
| 5k-wide-shift | Greedy-uncoordinated | 494.1 | 498.3 | +4.2 | +0.8% | +4.6% | 0.0→0.1 | 1.000→1.000 | 60 |
| 5k-wide-south | Equal RF | 488.3 | 498.3 | +10.0 | +2.1% | +2.1% | 2.1→0.1 | 0.999→1.000 | 60 |

Note: not every baseline ran in these cases, so 'best baseline' is best of those run: 10k-uniform · GW×0.75 (Equal RF, Demand-proportional); 1k-uniform (Equal RF, Demand-proportional); 1k-uniform · GW×0.25 (Equal RF, Demand-proportional); 1k-uniform · GW×0.5 (Equal RF, Demand-proportional); 1k-uniform · GW×0.75 (Equal RF, Demand-proportional); 5k-wide-pap · GW×0.75 (Equal RF, Demand-proportional); 5k-wide-south (Equal RF, Demand-proportional)

## RF admission ceilings (from terminal files)

Sum over cells of min(terminals×100 Mbps, 8 channels × 1.28 Gbps). No allocator can admit more.

- 10k-hotspot-north: 251.2 Gbps
- 10k-hotspot-pap: 251.2 Gbps
- 10k-pop: 684.4 Gbps
- 10k-uniform: 1000.0 Gbps
- 1k-pop: 109.3 Gbps
- 1k-uniform: 100.0 Gbps
- 5k-wide-north: 500.0 Gbps
- 5k-wide-pap: 500.0 Gbps
- 5k-wide-south: 500.0 Gbps

## Median allocation time per simulated second

- Demand-proportional: 0.0719 s
- Equal RF: 0.309 s
- Greedy-uncoordinated: 0.0142 s
- M3: no ISL awareness: 28.3 s
- M4: no gateway awareness: 27.3 s
- M5: no fairness: 27.1 s
- Proposed (scored-rf): 32.2 s

## Shell-0 load

| Case | Method | Admitted on shell 0 (Gbps) | Shell-0 share | Stranded shell 0 | Stranded shells 1–4 | Shell-0 sats over 20.8 Gbps |
|---|---|---:|---:|---:|---:|---:|
| 10k-hotspot-north | Demand-proportional | 97.7 | 39% | 0.0 | 0.0 | 0.0 |
| 10k-hotspot-north | Equal RF | 80.9 | 32% | 0.7 | 0.0 | 0.3 |
| 10k-hotspot-north | Greedy-uncoordinated | 54.1 | 25% | 0.0 | 0.0 | 0.0 |
| 10k-hotspot-north | Proposed (scored-rf) | 165.5 | 66% | 0.0 | 0.0 | 0.0 |
| 10k-hotspot-north · GW×0.25 | Greedy-uncoordinated | 54.1 | 25% | 11.5 | 0.0 | 0.0 |
| 10k-hotspot-north · GW×0.5 | Greedy-uncoordinated | 54.1 | 25% | 0.0 | 0.0 | 0.0 |
| 10k-hotspot-pap | Demand-proportional | 97.3 | 39% | 0.0 | 0.0 | 0.0 |
| 10k-hotspot-pap | Equal RF | 65.4 | 26% | 0.1 | 0.0 | 0.1 |
| 10k-hotspot-pap | Greedy-uncoordinated | 53.7 | 25% | 0.0 | 0.0 | 0.0 |
| 10k-hotspot-pap | Proposed (scored-rf) | 164.2 | 65% | 0.0 | 0.0 | 0.0 |
| 10k-hotspot-pap · GW×0.25 | Greedy-uncoordinated | 53.7 | 25% | 11.6 | 0.0 | 0.0 |
| 10k-hotspot-pap · GW×0.5 | Greedy-uncoordinated | 53.7 | 25% | 0.0 | 0.0 | 0.0 |
| 10k-uniform | Demand-proportional | 251.3 | 25% | 79.0 | 0.0 | 8.1 |
| 10k-uniform | Equal RF | 248.1 | 25% | 77.3 | 0.0 | 7.9 |
| 10k-uniform | Greedy-uncoordinated | 231.7 | 23% | 60.6 | 0.0 | 8.0 |
| 10k-uniform | Proposed (scored-rf) | 183.7 | 18% | 13.3 | 0.0 | 3.7 |
| 10k-uniform · GW×0.25 | Demand-proportional | 251.3 | 25% | 207.3 | 0.0 | 8.1 |
| 10k-uniform · GW×0.25 | Equal RF | 248.1 | 25% | 204.0 | 0.0 | 7.9 |
| 10k-uniform · GW×0.25 | Greedy-uncoordinated | 231.7 | 23% | 187.6 | 0.0 | 8.0 |
| 10k-uniform · GW×0.25 | M3: no ISL awareness | 272.9 | 27% | 228.8 | 0.0 | 8.0 |
| 10k-uniform · GW×0.25 | M4: no gateway awareness | 273.7 | 27% | 229.7 | 0.0 | 8.0 |
| 10k-uniform · GW×0.25 | M5: no fairness | 270.1 | 27% | 226.1 | 0.0 | 7.8 |
| 10k-uniform · GW×0.25 | Proposed (scored-rf) | 270.0 | 27% | 226.0 | 0.0 | 7.8 |
| 10k-uniform · GW×0.5 | Demand-proportional | 251.3 | 25% | 163.8 | 0.0 | 8.1 |
| 10k-uniform · GW×0.5 | Equal RF | 248.1 | 25% | 160.8 | 0.0 | 7.9 |
| 10k-uniform · GW×0.5 | Greedy-uncoordinated | 231.7 | 23% | 144.4 | 0.0 | 8.0 |
| 10k-uniform · GW×0.5 | M3: no ISL awareness | 273.1 | 27% | 185.5 | 0.0 | 8.1 |
| 10k-uniform · GW×0.5 | M4: no gateway awareness | 273.8 | 27% | 186.2 | 0.0 | 8.0 |
| 10k-uniform · GW×0.5 | M5: no fairness | 254.6 | 25% | 167.1 | 0.0 | 7.2 |
| 10k-uniform · GW×0.5 | Proposed (scored-rf) | 250.5 | 25% | 163.0 | 0.0 | 7.0 |
| 10k-uniform · GW×0.75 | Demand-proportional | 251.3 | 25% | 120.9 | 0.0 | 8.1 |
| 10k-uniform · GW×0.75 | Equal RF | 248.1 | 25% | 118.4 | 0.0 | 7.9 |
| 10k-uniform · GW×0.75 | M3: no ISL awareness | 272.5 | 27% | 142.1 | 0.0 | 8.0 |
| 10k-uniform · GW×0.75 | M4: no gateway awareness | 273.8 | 27% | 143.4 | 0.0 | 8.0 |
| 10k-uniform · GW×0.75 | M5: no fairness | 171.7 | 17% | 41.6 | 0.0 | 2.4 |
| 10k-uniform · GW×0.75 | Proposed (scored-rf) | 171.3 | 17% | 41.2 | 0.0 | 2.5 |
| 1k-uniform | Demand-proportional | 29.2 | 29% | 0.0 | 0.0 | 0.0 |
| 1k-uniform | Equal RF | 24.8 | 25% | 0.0 | 0.0 | 0.0 |
| 1k-uniform | Proposed (scored-rf) | 100.0 | 100% | 0.0 | 0.0 | 0.0 |
| 1k-uniform · GW×0.25 | Demand-proportional | 29.2 | 29% | 0.1 | 0.0 | 0.0 |
| 1k-uniform · GW×0.25 | Equal RF | 24.8 | 25% | 0.0 | 0.0 | 0.0 |
| 1k-uniform · GW×0.25 | M3: no ISL awareness | 40.4 | 40% | 0.0 | 0.0 | 0.0 |
| 1k-uniform · GW×0.25 | M4: no gateway awareness | 100.0 | 100% | 73.2 | 0.0 | 3.8 |
| 1k-uniform · GW×0.25 | M5: no fairness | 40.4 | 40% | 0.0 | 0.0 | 0.0 |
| 1k-uniform · GW×0.25 | Proposed (scored-rf) | 40.4 | 40% | 0.0 | 0.0 | 0.0 |
| 1k-uniform · GW×0.5 | Demand-proportional | 29.2 | 29% | 0.0 | 0.0 | 0.0 |
| 1k-uniform · GW×0.5 | Equal RF | 24.8 | 25% | 0.0 | 0.0 | 0.0 |
| 1k-uniform · GW×0.5 | M3: no ISL awareness | 79.9 | 80% | 0.0 | 0.0 | 0.0 |
| 1k-uniform · GW×0.5 | M4: no gateway awareness | 100.0 | 100% | 51.6 | 0.0 | 3.8 |
| 1k-uniform · GW×0.5 | M5: no fairness | 79.9 | 80% | 0.0 | 0.0 | 0.0 |
| 1k-uniform · GW×0.5 | Proposed (scored-rf) | 79.9 | 80% | 0.0 | 0.0 | 0.0 |
| 1k-uniform · GW×0.75 | Demand-proportional | 29.2 | 29% | 0.0 | 0.0 | 0.0 |
| 1k-uniform · GW×0.75 | Equal RF | 24.8 | 25% | 0.0 | 0.0 | 0.0 |
| 1k-uniform · GW×0.75 | M3: no ISL awareness | 100.0 | 100% | 0.0 | 0.0 | 0.0 |
| 1k-uniform · GW×0.75 | M4: no gateway awareness | 100.0 | 100% | 30.9 | 0.0 | 3.8 |
| 1k-uniform · GW×0.75 | M5: no fairness | 100.0 | 100% | 0.0 | 0.0 | 0.0 |
| 1k-uniform · GW×0.75 | Proposed (scored-rf) | 100.0 | 100% | 0.0 | 0.0 | 0.0 |
| 5k-wide-north | Demand-proportional | 217.1 | 44% | 76.1 | 0.0 | 4.9 |
| 5k-wide-north | Equal RF | 153.4 | 31% | 22.7 | 0.0 | 2.8 |
| 5k-wide-north | Greedy-uncoordinated | 118.7 | 24% | 0.0 | 0.0 | 0.0 |
| 5k-wide-north | Proposed (scored-rf) | 169.3 | 34% | 0.2 | 0.0 | 0.9 |
| 5k-wide-north · GW×0.25 | Greedy-uncoordinated | 118.7 | 24% | 75.1 | 0.0 | 0.0 |
| 5k-wide-north · GW×0.5 | Greedy-uncoordinated | 118.7 | 24% | 32.2 | 0.0 | 0.0 |
| 5k-wide-pap | Demand-proportional | 209.7 | 42% | 70.8 | 0.0 | 5.1 |
| 5k-wide-pap | Equal RF | 131.7 | 27% | 12.6 | 0.0 | 1.9 |
| 5k-wide-pap | Greedy-uncoordinated | 119.8 | 24% | 0.0 | 0.0 | 0.0 |
| 5k-wide-pap | Proposed (scored-rf) | 167.4 | 34% | 0.1 | 0.0 | 0.5 |
| 5k-wide-pap · GW×0.25 | Demand-proportional | 209.7 | 42% | 166.4 | 0.0 | 5.1 |
| 5k-wide-pap · GW×0.25 | Equal RF | 131.7 | 27% | 88.3 | 0.0 | 1.9 |
| 5k-wide-pap · GW×0.25 | Greedy-uncoordinated | 119.8 | 24% | 76.5 | 0.0 | 0.0 |
| 5k-wide-pap · GW×0.25 | M3: no ISL awareness | 244.6 | 49% | 200.8 | 0.0 | 7.8 |
| 5k-wide-pap · GW×0.25 | M4: no gateway awareness | 275.2 | 55% | 231.5 | 0.0 | 7.8 |
| 5k-wide-pap · GW×0.25 | M5: no fairness | 50.5 | 10% | 7.7 | 0.0 | 0.1 |
| 5k-wide-pap · GW×0.25 | Proposed (scored-rf) | 49.1 | 10% | 6.3 | 0.0 | 0.1 |
| 5k-wide-pap · GW×0.5 | Demand-proportional | 209.7 | 42% | 125.2 | 0.0 | 5.1 |
| 5k-wide-pap · GW×0.5 | Equal RF | 131.7 | 27% | 47.2 | 0.0 | 1.9 |
| 5k-wide-pap · GW×0.5 | Greedy-uncoordinated | 119.8 | 24% | 35.4 | 0.0 | 0.0 |
| 5k-wide-pap · GW×0.5 | M3: no ISL awareness | 234.2 | 47% | 147.6 | 0.0 | 7.0 |
| 5k-wide-pap · GW×0.5 | M4: no gateway awareness | 274.3 | 55% | 187.8 | 0.0 | 7.9 |
| 5k-wide-pap · GW×0.5 | M5: no fairness | 85.4 | 17% | 0.1 | 0.0 | 0.0 |
| 5k-wide-pap · GW×0.5 | Proposed (scored-rf) | 85.3 | 17% | 0.1 | 0.0 | 0.0 |
| 5k-wide-pap · GW×0.75 | Demand-proportional | 209.7 | 42% | 97.5 | 0.0 | 5.1 |
| 5k-wide-pap · GW×0.75 | Equal RF | 131.7 | 27% | 27.2 | 0.0 | 1.9 |
| 5k-wide-pap · GW×0.75 | M3: no ISL awareness | 137.6 | 28% | 9.2 | 0.0 | 0.3 |
| 5k-wide-pap · GW×0.75 | M4: no gateway awareness | 274.3 | 55% | 145.8 | 0.0 | 7.9 |
| 5k-wide-pap · GW×0.75 | M5: no fairness | 126.6 | 25% | 0.2 | 0.0 | 0.0 |
| 5k-wide-pap · GW×0.75 | Proposed (scored-rf) | 126.6 | 25% | 0.2 | 0.0 | 0.0 |
| 5k-wide-shift | Demand-proportional | 213.3 | 43% | 74.0 | 0.0 | 5.1 |
| 5k-wide-shift | Equal RF | 141.4 | 29% | 16.5 | 0.0 | 2.3 |
| 5k-wide-shift | Greedy-uncoordinated | 120.4 | 24% | 0.0 | 0.0 | 0.0 |
| 5k-wide-shift | M5: no fairness | 167.7 | 34% | 0.2 | 0.0 | 1.3 |
| 5k-wide-shift | Proposed (scored-rf) | 167.5 | 34% | 0.1 | 0.0 | 0.6 |
| 5k-wide-shift · GW×0.25 | Greedy-uncoordinated | 120.4 | 24% | 77.1 | 0.0 | 0.0 |
| 5k-wide-shift · GW×0.5 | Greedy-uncoordinated | 120.4 | 24% | 35.8 | 0.0 | 0.0 |
| 5k-wide-south | Demand-proportional | 214.6 | 43% | 75.5 | 0.0 | 5.2 |
| 5k-wide-south | Equal RF | 114.4 | 23% | 2.1 | 0.0 | 0.6 |
| 5k-wide-south | Proposed (scored-rf) | 167.2 | 34% | 0.1 | 0.0 | 0.3 |
