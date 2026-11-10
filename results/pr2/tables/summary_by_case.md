Means over simulated seconds (± std for throughput). Per-cell metrics (Jain, starvation) use CosmoSim's estimated per-cell delivery.

### 10k-hotspot-north  (n = 60 s per method)

| Method | Delivered (Gbps) | Stranded (Gbps) | Demand sat. | Jain (delivered) | Worst-cell sat. | Active feeders ≥90% busy | Alloc. time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Proposed (scored-rf) | 251.2 ± 0.0 | 0.0 ± 0.0 | 0.251 | 0.968 | 0.064 | 0.778 | 25.34 |
| Equal RF | 250.5 ± 1.2 | 0.7 ± 1.2 | 0.250 | 0.968 | 0.062 | 0.481 | 0.42 |
| Demand-proportional | 251.2 ± 0.0 | 0.0 ± 0.0 | 0.251 | 0.968 | 0.064 | 0.480 | 0.07 |
| Greedy-uncoordinated | 218.9 ± 0.0 | 0.0 ± 0.0 | 0.219 | 0.968 | 0.064 | 0.501 | 0.01 |

### 10k-hotspot-pap  (n = 60 s per method)

| Method | Delivered (Gbps) | Stranded (Gbps) | Demand sat. | Jain (delivered) | Worst-cell sat. | Active feeders ≥90% busy | Alloc. time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Proposed (scored-rf) | 251.2 ± 0.0 | 0.0 ± 0.0 | 0.251 | 0.968 | 0.064 | 0.775 | 25.57 |
| Equal RF | 248.5 ± 3.1 | 0.1 ± 0.3 | 0.249 | 0.968 | 0.060 | 0.472 | 0.47 |
| Demand-proportional | 251.2 ± 0.0 | 0.0 ± 0.0 | 0.251 | 0.968 | 0.064 | 0.475 | 0.07 |
| Greedy-uncoordinated | 218.9 ± 0.0 | 0.0 ± 0.0 | 0.219 | 0.968 | 0.064 | 0.494 | 0.01 |

### 10k-uniform  (n = 60 s per method)

| Method | Delivered (Gbps) | Stranded (Gbps) | Demand sat. | Jain (delivered) | Worst-cell sat. | Active feeders ≥90% busy | Alloc. time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Proposed (scored-rf) | 986.7 ± 16.8 | 13.3 ± 16.8 | 0.987 | 1.000 | 0.954 | 0.739 | 89.36 |
| Equal RF | 922.7 ± 7.4 | 77.3 ± 7.4 | 0.923 | 0.987 | 0.701 | 0.703 | 0.52 |
| Demand-proportional | 921.0 ± 6.5 | 79.0 ± 6.5 | 0.921 | 0.985 | 0.678 | 0.692 | 0.22 |
| Greedy-uncoordinated | 939.4 ± 4.6 | 60.6 ± 4.6 | 0.939 | 0.996 | 0.808 | 0.693 | 0.05 |

### 10k-uniform · GW×0.25  (n = 60 s per method)

| Method | Delivered (Gbps) | Stranded (Gbps) | Demand sat. | Jain (delivered) | Worst-cell sat. | Active feeders ≥90% busy | Alloc. time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Proposed (scored-rf) | 774.0 ± 17.0 | 226.0 ± 17.0 | 0.774 | 0.985 | 0.563 | 0.940 | 64.57 |
| Equal RF | 796.0 ± 11.0 | 204.0 ± 11.0 | 0.796 | 0.890 | 0.217 | 0.940 | 0.27 |
| Demand-proportional | 792.7 ± 10.4 | 207.3 ± 10.4 | 0.793 | 0.877 | 0.199 | 0.933 | 0.10 |
| Greedy-uncoordinated | 812.4 ± 9.9 | 187.6 ± 9.9 | 0.812 | 0.959 | 0.345 | 0.932 | 0.05 |
| M3: no ISL awareness | 771.2 ± 18.3 | 228.8 ± 18.3 | 0.771 | 0.991 | 0.519 | 0.938 | 62.67 |
| M4: no gateway awareness | 770.3 ± 18.4 | 229.7 ± 18.4 | 0.770 | 0.995 | 0.585 | 0.945 | 61.69 |
| M5: no fairness | 773.9 ± 17.4 | 226.1 ± 17.4 | 0.774 | 0.987 | 0.570 | 0.942 | 49.98 |

### 10k-uniform · GW×0.5  (n = 60 s per method)

| Method | Delivered (Gbps) | Stranded (Gbps) | Demand sat. | Jain (delivered) | Worst-cell sat. | Active feeders ≥90% busy | Alloc. time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Proposed (scored-rf) | 837.0 ± 31.6 | 163.0 ± 31.6 | 0.837 | 0.992 | 0.700 | 0.882 | 65.96 |
| Equal RF | 839.2 ± 9.1 | 160.8 ± 9.1 | 0.839 | 0.935 | 0.380 | 0.886 | 0.27 |
| Demand-proportional | 836.2 ± 8.0 | 163.8 ± 8.0 | 0.836 | 0.926 | 0.361 | 0.873 | 0.10 |
| Greedy-uncoordinated | 855.5 ± 6.9 | 144.4 ± 6.9 | 0.856 | 0.977 | 0.529 | 0.863 | 0.05 |
| M3: no ISL awareness | 814.5 ± 14.8 | 185.5 ± 14.8 | 0.815 | 0.989 | 0.647 | 0.872 | 65.14 |
| M4: no gateway awareness | 813.8 ± 14.8 | 186.2 ± 14.8 | 0.814 | 0.997 | 0.696 | 0.883 | 63.28 |
| M5: no fairness | 832.9 ± 25.8 | 167.1 ± 25.8 | 0.833 | 0.992 | 0.701 | 0.883 | 51.26 |

### 10k-uniform · GW×0.75  (n = 60 s per method)

| Method | Delivered (Gbps) | Stranded (Gbps) | Demand sat. | Jain (delivered) | Worst-cell sat. | Active feeders ≥90% busy | Alloc. time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Proposed (scored-rf) | 958.8 ± 21.4 | 41.2 ± 21.4 | 0.959 | 0.998 | 0.857 | 0.842 | 66.98 |
| Equal RF | 881.6 ± 8.0 | 118.4 ± 8.0 | 0.882 | 0.967 | 0.541 | 0.811 | 0.27 |
| Demand-proportional | 879.1 ± 6.6 | 120.9 ± 6.6 | 0.879 | 0.962 | 0.520 | 0.785 | 0.10 |
| M3: no ISL awareness | 857.9 ± 11.4 | 142.1 ± 11.4 | 0.858 | 0.996 | 0.741 | 0.802 | 66.88 |
| M4: no gateway awareness | 856.6 ± 11.1 | 143.4 ± 11.1 | 0.857 | 0.999 | 0.795 | 0.793 | 62.29 |
| M5: no fairness | 958.4 ± 21.6 | 41.6 ± 21.6 | 0.958 | 0.998 | 0.856 | 0.844 | 52.13 |

### 1k-uniform  (n = 60 s per method)

| Method | Delivered (Gbps) | Stranded (Gbps) | Demand sat. | Jain (delivered) | Worst-cell sat. | Active feeders ≥90% busy | Alloc. time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Proposed (scored-rf) | 100.0 ± 0.0 | 0.0 ± 0.0 | 1.000 | 1.000 | 1.000 | 0.662 | 7.32 |
| Equal RF | 100.0 ± 0.0 | 0.0 ± 0.0 | 1.000 | 1.000 | 1.000 | 0.396 | 0.51 |
| Demand-proportional | 100.0 ± 0.0 | 0.0 ± 0.0 | 1.000 | 1.000 | 1.000 | 0.398 | 0.03 |

### 1k-uniform · GW×0.25  (n = 60 s per method)

| Method | Delivered (Gbps) | Stranded (Gbps) | Demand sat. | Jain (delivered) | Worst-cell sat. | Active feeders ≥90% busy | Alloc. time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Proposed (scored-rf) | 100.0 ± 0.0 | 0.0 ± 0.0 | 1.000 | 1.000 | 1.000 | 0.825 | 6.23 |
| Equal RF | 100.0 ± 0.0 | 0.0 ± 0.0 | 1.000 | 1.000 | 1.000 | 0.663 | 0.30 |
| Demand-proportional | 99.9 ± 0.2 | 0.1 ± 0.2 | 0.999 | 1.000 | 0.987 | 0.650 | 0.02 |
| M3: no ISL awareness | 100.0 ± 0.0 | 0.0 ± 0.0 | 1.000 | 1.000 | 1.000 | 0.812 | 6.13 |
| M4: no gateway awareness | 26.8 ± 1.1 | 73.2 ± 1.1 | 0.268 | 0.711 | 0.196 | 0.862 | 5.74 |
| M5: no fairness | 100.0 ± 0.0 | 0.0 ± 0.0 | 1.000 | 1.000 | 1.000 | 0.825 | 4.41 |

### 1k-uniform · GW×0.5  (n = 60 s per method)

| Method | Delivered (Gbps) | Stranded (Gbps) | Demand sat. | Jain (delivered) | Worst-cell sat. | Active feeders ≥90% busy | Alloc. time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Proposed (scored-rf) | 100.0 ± 0.0 | 0.0 ± 0.0 | 1.000 | 1.000 | 1.000 | 0.750 | 6.18 |
| Equal RF | 100.0 ± 0.0 | 0.0 ± 0.0 | 1.000 | 1.000 | 1.000 | 0.510 | 0.30 |
| Demand-proportional | 100.0 ± 0.0 | 0.0 ± 0.0 | 1.000 | 1.000 | 1.000 | 0.519 | 0.02 |
| M3: no ISL awareness | 100.0 ± 0.0 | 0.0 ± 0.0 | 1.000 | 1.000 | 1.000 | 0.745 | 6.11 |
| M4: no gateway awareness | 48.4 ± 2.1 | 51.6 ± 2.1 | 0.484 | 0.921 | 0.392 | 0.772 | 5.81 |
| M5: no fairness | 100.0 ± 0.0 | 0.0 ± 0.0 | 1.000 | 1.000 | 1.000 | 0.750 | 4.46 |

### 1k-uniform · GW×0.75  (n = 60 s per method)

| Method | Delivered (Gbps) | Stranded (Gbps) | Demand sat. | Jain (delivered) | Worst-cell sat. | Active feeders ≥90% busy | Alloc. time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Proposed (scored-rf) | 100.0 ± 0.0 | 0.0 ± 0.0 | 1.000 | 1.000 | 1.000 | 0.890 | 6.01 |
| Equal RF | 100.0 ± 0.0 | 0.0 ± 0.0 | 1.000 | 1.000 | 1.000 | 0.401 | 0.30 |
| Demand-proportional | 100.0 ± 0.0 | 0.0 ± 0.0 | 1.000 | 1.000 | 1.000 | 0.412 | 0.02 |
| M3: no ISL awareness | 100.0 ± 0.0 | 0.0 ± 0.0 | 1.000 | 1.000 | 1.000 | 0.890 | 5.88 |
| M4: no gateway awareness | 69.1 ± 2.1 | 30.9 ± 2.1 | 0.691 | 0.980 | 0.589 | 0.733 | 5.83 |
| M5: no fairness | 100.0 ± 0.0 | 0.0 ± 0.0 | 1.000 | 1.000 | 1.000 | 0.890 | 4.53 |

### 5k-wide-north  (n = 60 s per method)

| Method | Delivered (Gbps) | Stranded (Gbps) | Demand sat. | Jain (delivered) | Worst-cell sat. | Active feeders ≥90% busy | Alloc. time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Proposed (scored-rf) | 498.2 ± 0.3 | 0.2 ± 0.3 | 0.996 | 1.000 | 0.990 | 0.652 | 48.07 |
| Equal RF | 475.7 ± 20.1 | 22.7 ± 20.1 | 0.951 | 0.994 | 0.760 | 0.650 | 0.33 |
| Demand-proportional | 422.3 ± 9.7 | 76.1 ± 9.7 | 0.845 | 0.976 | 0.572 | 0.747 | 0.09 |
| Greedy-uncoordinated | 494.1 ± 0.0 | 0.0 ± 0.0 | 0.988 | 1.000 | 0.985 | 0.498 | 0.02 |

### 5k-wide-pap  (n = 60 s per method)

| Method | Delivered (Gbps) | Stranded (Gbps) | Demand sat. | Jain (delivered) | Worst-cell sat. | Active feeders ≥90% busy | Alloc. time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Proposed (scored-rf) | 498.3 ± 0.1 | 0.1 ± 0.1 | 0.997 | 1.000 | 0.991 | 0.664 | 47.85 |
| Equal RF | 479.4 ± 5.1 | 12.6 ± 9.6 | 0.959 | 0.996 | 0.739 | 0.645 | 0.35 |
| Demand-proportional | 427.6 ± 8.5 | 70.8 ± 8.5 | 0.855 | 0.979 | 0.586 | 0.728 | 0.11 |
| Greedy-uncoordinated | 494.1 ± 0.0 | 0.0 ± 0.0 | 0.988 | 1.000 | 0.985 | 0.500 | 0.02 |

### 5k-wide-pap · GW×0.25  (n = 60 s per method)

| Method | Delivered (Gbps) | Stranded (Gbps) | Demand sat. | Jain (delivered) | Worst-cell sat. | Active feeders ≥90% busy | Alloc. time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Proposed (scored-rf) | 492.1 ± 11.1 | 6.3 ± 11.1 | 0.984 | 0.999 | 0.914 | 0.891 | 29.63 |
| Equal RF | 403.7 ± 12.7 | 88.3 ± 8.5 | 0.807 | 0.940 | 0.263 | 0.919 | 0.28 |
| Demand-proportional | 332.0 ± 12.8 | 166.4 ± 12.8 | 0.664 | 0.884 | 0.164 | 0.910 | 0.05 |
| Greedy-uncoordinated | 417.6 ± 4.5 | 76.5 ± 4.5 | 0.835 | 0.952 | 0.420 | 0.911 | 0.02 |
| M3: no ISL awareness | 297.6 ± 15.1 | 200.8 ± 15.1 | 0.595 | 0.940 | 0.335 | 0.874 | 28.46 |
| M4: no gateway awareness | 266.9 ± 14.9 | 231.5 ± 14.9 | 0.534 | 0.918 | 0.213 | 0.909 | 27.96 |
| M5: no fairness | 490.7 ± 10.2 | 7.7 ± 10.2 | 0.981 | 0.998 | 0.886 | 0.892 | 24.63 |

### 5k-wide-pap · GW×0.5  (n = 60 s per method)

| Method | Delivered (Gbps) | Stranded (Gbps) | Demand sat. | Jain (delivered) | Worst-cell sat. | Active feeders ≥90% busy | Alloc. time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Proposed (scored-rf) | 498.3 ± 0.1 | 0.1 ± 0.1 | 0.997 | 1.000 | 0.991 | 0.849 | 29.33 |
| Equal RF | 444.8 ± 13.9 | 47.2 ± 8.7 | 0.890 | 0.980 | 0.440 | 0.852 | 0.28 |
| Demand-proportional | 373.2 ± 10.6 | 125.2 ± 10.6 | 0.746 | 0.932 | 0.305 | 0.863 | 0.05 |
| Greedy-uncoordinated | 458.7 ± 3.0 | 35.4 ± 3.0 | 0.917 | 0.990 | 0.720 | 0.810 | 0.02 |
| M3: no ISL awareness | 350.8 ± 6.1 | 147.6 ± 6.1 | 0.702 | 0.963 | 0.482 | 0.782 | 28.88 |
| M4: no gateway awareness | 310.6 ± 12.9 | 187.8 ± 12.9 | 0.621 | 0.954 | 0.346 | 0.836 | 28.27 |
| M5: no fairness | 498.3 ± 0.2 | 0.1 ± 0.2 | 0.997 | 1.000 | 0.988 | 0.856 | 24.61 |

### 5k-wide-pap · GW×0.75  (n = 60 s per method)

| Method | Delivered (Gbps) | Stranded (Gbps) | Demand sat. | Jain (delivered) | Worst-cell sat. | Active feeders ≥90% busy | Alloc. time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Proposed (scored-rf) | 498.2 ± 0.2 | 0.2 ± 0.2 | 0.996 | 1.000 | 0.989 | 0.775 | 29.54 |
| Equal RF | 464.8 ± 7.6 | 27.2 ± 8.1 | 0.930 | 0.991 | 0.598 | 0.651 | 0.28 |
| Demand-proportional | 400.9 ± 9.7 | 97.5 ± 9.7 | 0.802 | 0.959 | 0.446 | 0.596 | 0.05 |
| M3: no ISL awareness | 489.2 ± 7.6 | 9.2 ± 7.6 | 0.978 | 0.999 | 0.914 | 0.880 | 29.52 |
| M4: no gateway awareness | 352.6 ± 9.7 | 145.8 ± 9.7 | 0.705 | 0.972 | 0.475 | 0.773 | 28.43 |
| M5: no fairness | 498.2 ± 0.1 | 0.2 ± 0.1 | 0.996 | 1.000 | 0.989 | 0.774 | 24.95 |

### 5k-wide-shift  (n = 60 s per method)

| Method | Delivered (Gbps) | Stranded (Gbps) | Demand sat. | Jain (delivered) | Worst-cell sat. | Active feeders ≥90% busy | Alloc. time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Proposed (scored-rf) | 498.3 ± 0.2 | 0.1 ± 0.2 | 0.997 | 1.000 | 0.991 | 0.656 | 47.89 |
| Equal RF | 476.3 ± 10.6 | 16.5 ± 14.0 | 0.953 | 0.996 | 0.744 | 0.656 | 0.36 |
| Demand-proportional | 424.4 ± 9.5 | 74.0 ± 9.5 | 0.849 | 0.977 | 0.571 | 0.738 | 0.09 |
| Greedy-uncoordinated | 494.1 ± 0.0 | 0.0 ± 0.0 | 0.988 | 1.000 | 0.985 | 0.502 | 0.02 |
| M5: no fairness | 498.2 ± 0.2 | 0.2 ± 0.2 | 0.996 | 1.000 | 0.990 | 0.647 | 46.36 |

### 5k-wide-south  (n = 60 s per method)

| Method | Delivered (Gbps) | Stranded (Gbps) | Demand sat. | Jain (delivered) | Worst-cell sat. | Active feeders ≥90% busy | Alloc. time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Proposed (scored-rf) | 498.3 ± 0.1 | 0.1 ± 0.1 | 0.997 | 1.000 | 0.991 | 0.668 | 34.99 |
| Equal RF | 488.3 ± 10.2 | 2.1 ± 3.8 | 0.977 | 0.999 | 0.887 | 0.633 | 0.34 |
| Demand-proportional | 422.9 ± 8.8 | 75.5 ± 8.8 | 0.846 | 0.977 | 0.572 | 0.734 | 0.09 |
