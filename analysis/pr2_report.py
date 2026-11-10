#!/usr/bin/env python3
"""PR2 tables and figures from finished runs.

Reads every metrics_<t>.json under the given experiment folders (layout
<exp>/<scenario>/<policy>/islX_gwY/tN/), labels each experiment as a method, keeps only
the seconds every method has in a case (so comparisons are like-for-like), and writes:

  tables/runs_tidy.csv           one row per run (case x method x second)
  tables/summary_by_case.csv/.md mean (std over seconds) per case x method
  tables/vs_best_baseline.md     proposed vs the best baseline in each case
  tables/shell_summary.md        per-shell load + stranding (if shell_breakdown.csv given)
  figures/*.png                  see FIGURES below
  findings.md                    auto-written headline numbers to check and quote

Usage (repo root):
    .venv/bin/python analysis/pr2_report.py data/runs/pr2_* \
        --shell-csv results/pr2/shell_breakdown.csv --out results/pr2
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# --- method labels: experiment folder name -> method -----------------------------------
METHOD_RULES = [  # first regex that matches the experiment name wins
    (r"full", "Proposed (scored-rf)"),
    (r"_m1(_|$)", "Equal RF"),
    (r"_m2(_|$)", "Demand-proportional"),
    (r"uncoord", "Greedy-uncoordinated"),
    (r"_m3(_|$)", "M3: no ISL awareness"),
    (r"_m4(_|$)", "M4: no gateway awareness"),
    (r"_m5(_|$)", "M5: no fairness"),
]
PROPOSED = "Proposed (scored-rf)"
BASELINES = ["Equal RF", "Demand-proportional", "Greedy-uncoordinated"]
ABLATIONS = ["M3: no ISL awareness", "M4: no gateway awareness", "M5: no fairness"]
ORDER = [PROPOSED] + BASELINES + ABLATIONS

# Fixed colour per method (validated categorical palette, light mode), never by rank.
COLOR = dict(zip(ORDER, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"]))
MARKER = dict(zip(ORDER, ["o", "s", "^", "D", "v", "P", "X"]))  # secondary encoding
DASH = {"M5: no fairness": (0, (4, 2))}  # M5 often overlaps Proposed exactly; dash it so both show

SCENARIO_SHORT = {
    "cells_haiti_0_10000_uniform": "10k-uniform",
    "cells_haiti_0_10000_population": "10k-pop",
    "cells_haiti_0_10000_hotspot_pap": "10k-hotspot-pap",
    "cells_haiti_0_10000_hotspot_north": "10k-hotspot-north",
    "cells_haiti_0_5000_wide_pap": "5k-wide-pap",
    "cells_haiti_0_5000_wide_north": "5k-wide-north",
    "cells_haiti_0_5000_wide_south": "5k-wide-south",
    "cells_haiti_0_5000_wide_shift": "5k-wide-shift",
    "cells_haiti_0_1000_uniform": "1k-uniform",
    "cells_haiti_0_1000_population": "1k-pop",
}

METRICS = {  # column -> (label for tables, json getter)
    "requested_gbps": ("Requested (Gbps)", lambda m: m["requested_mbps"] / 1e3),
    "admitted_gbps": ("Admitted (Gbps)", lambda m: m["admitted_mbps"] / 1e3),
    "delivered_gbps": ("Delivered (Gbps)", lambda m: m["delivered_mbps"] / 1e3),
    "stranded_gbps": ("Stranded (Gbps)", lambda m: m["stranded_mbps"] / 1e3),
    "demand_satisfaction": ("Demand sat.", lambda m: m.get("demand_satisfaction")),
    "jain_d": ("Jain (delivered)", lambda m: m.get("jain_delivered_over_offered")),
    "starve_deliv": ("Starved cells", lambda m: m.get("starvation_rate_zero_delivery")),
    "min_cell_sat": ("Worst-cell sat.", lambda m: m.get("min_cell_satisfaction_delivered")),
    "gw_util": ("GS util", lambda m: _g(m, "utilization", "gateway", "aggregate_util")),
    "feeder_util": ("Feeder util", lambda m: _g(m, "utilization", "feeder", "aggregate_util")),
    "isl_util": ("ISL util", lambda m: _g(m, "utilization", "isl", "aggregate_util")),
    "feeder_sat90": ("Active feeders ≥90% busy", lambda m: _g(m, "utilization", "feeder", "frac_active_saturated_090")),
    "cell_rf_fill": ("Cell RF fill", lambda m: _g(m, "rf", "cell_rf_fill")),
    "allocation_s": ("Alloc. time (s)", lambda m: m.get("runtime_allocation_s")),
}
TABLE_COLS = ["delivered_gbps", "stranded_gbps", "demand_satisfaction", "jain_d",
              "min_cell_sat", "feeder_sat90", "allocation_s"]


def _g(m, *keys):
    for k in keys:
        if not isinstance(m, dict):
            return None
        m = m.get(k)
    return m


def method_of(exp_name: str, policy: str) -> str:
    for pat, label in METHOD_RULES:
        if re.search(pat, exp_name):
            return label
    return policy


# --- loading -----------------------------------------------------------------------------
def load(exps: list[Path]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, cells = [], []
    for exp in exps:
        for f in sorted(exp.rglob("metrics_*.json")):
            parts = f.relative_to(exp).parts
            if len(parts) != 5 or not parts[3].startswith("t"):
                continue
            scen, policy, scale, tdir, _ = parts
            isl, gw = scale[3:].split("_gw", 1)
            m = json.loads(f.read_text())
            base = {
                "experiment": exp.name,
                "method": method_of(exp.name, policy),
                "scenario": SCENARIO_SHORT.get(scen, scen),
                "isl_scale": float(isl), "gw_scale": float(gw), "t_s": int(tdir[1:]),
            }
            row = dict(base)
            for col, (_, get) in METRICS.items():
                try:
                    v = get(m)
                    row[col] = float(v) if v is not None else np.nan
                except (KeyError, TypeError, ValueError):
                    row[col] = np.nan
            row["consistency_ok"] = _g(m, "consistency", "ok")
            row["rule_violations"] = int((f.parent / "rule_violations.txt").exists())
            rows.append(row)
            for c, pc in (m.get("per_cell") or {}).items():
                s = pc.get("satisfaction_delivered_estimated")
                if s is not None:
                    cells.append({**base, "cell": c, "sat": float(s)})
    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("no metrics_*.json found under the given folders")
    df["case"] = df.apply(case_name, axis=1)
    cdf = pd.DataFrame(cells)
    if not cdf.empty:
        cdf["case"] = cdf.apply(case_name, axis=1)
    return df, cdf


def case_name(r) -> str:
    s = r["scenario"]
    if r["isl_scale"] != 1:
        s += f" · ISL×{r['isl_scale']:g}"
    if r["gw_scale"] != 1:
        s += f" · GW×{r['gw_scale']:g}"
    return s


def common_seconds(df: pd.DataFrame) -> pd.DataFrame:
    """Within each case, keep only seconds that every method in that case has."""
    keep = []
    for _, g in df.groupby("case"):
        ts = set.intersection(*(set(x.t_s) for _, x in g.groupby("method")))
        keep.append(g[g.t_s.isin(ts)])
    return pd.concat(keep, ignore_index=True)


def ordered(methods) -> list[str]:
    ms = list(dict.fromkeys(methods))
    return [m for m in ORDER if m in ms] + [m for m in ms if m not in ORDER]


# --- tables ------------------------------------------------------------------------------
def summarize(df: pd.DataFrame) -> pd.DataFrame:
    cols = list(METRICS)
    g = df.groupby(["case", "method"])
    out = g[cols].mean().add_suffix("_mean").join(g[cols].std().add_suffix("_std"))
    out["n_seconds"] = g.size()
    out["violations"] = g["rule_violations"].sum()
    return out.reset_index()


def fmt(v, col):
    if pd.isna(v):
        return "–"
    if col in ("demand_satisfaction", "starve_deliv", "feeder_util", "jain_d", "min_cell_sat", "feeder_sat90"):
        return f"{v:.3f}"
    if col == "allocation_s":
        return f"{v:.2f}"
    return f"{v:.1f}"


def summary_md(s: pd.DataFrame) -> str:
    out = []
    for case in sorted(s.case.unique()):
        g = s[s.case == case].set_index("method").loc[ordered(s[s.case == case].method)]
        n = int(g.n_seconds.min())
        out.append(f"\n### {case}  (n = {n} s per method)\n")
        out.append("| Method | " + " | ".join(METRICS[c][0] for c in TABLE_COLS) + " |")
        out.append("|---|" + "---:|" * len(TABLE_COLS))
        for meth, r in g.iterrows():
            vals = [f"{fmt(r[c + '_mean'], c)} ± {fmt(r[c + '_std'], c)}" if c in ("delivered_gbps", "stranded_gbps")
                    else fmt(r[c + "_mean"], c) for c in TABLE_COLS]
            out.append(f"| {meth} | " + " | ".join(vals) + " |")
    return "\n".join(out) + "\n"


def vs_best(s: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for case, g in s.groupby("case"):
        g = g.set_index("method")
        if PROPOSED not in g.index:
            continue
        b = g.loc[[m for m in BASELINES if m in g.index]]
        if b.empty:
            continue
        best = b.delivered_gbps_mean.idxmax()
        p, q = g.loc[PROPOSED], g.loc[best]
        rows.append({
            "case": case, "best_baseline": best,
            "baseline_delivered": q.delivered_gbps_mean, "proposed_delivered": p.delivered_gbps_mean,
            "delta_gbps": p.delivered_gbps_mean - q.delivered_gbps_mean,
            "delta_pct": 100 * (p.delivered_gbps_mean / q.delivered_gbps_mean - 1),
            "baseline_stranded": q.stranded_gbps_mean, "proposed_stranded": p.stranded_gbps_mean,
            "baseline_jain": q.jain_d_mean, "proposed_jain": p.jain_d_mean,
            "baseline_starve": q.starve_deliv_mean, "proposed_starve": p.starve_deliv_mean,
            "proposed_vs_equal_pct": (100 * (p.delivered_gbps_mean / g.loc["Equal RF"].delivered_gbps_mean - 1)
                                      if "Equal RF" in g.index else np.nan),
            "n_seconds": int(g.n_seconds.min()),
            "baselines_run": ", ".join(m for m in BASELINES if m in g.index),
        })
    return pd.DataFrame(rows)


# --- figures -----------------------------------------------------------------------------
def style(ax, ylabel=None, xlabel=None):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#9a9994")
    ax.tick_params(colors="#52514e", labelsize=8)
    ax.grid(axis="y", color="#e6e5e1", linewidth=0.6)
    ax.set_axisbelow(True)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9, color="#52514e")
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=9, color="#52514e")


def save(fig, out: Path, name: str):
    fig.savefig(out / f"{name}.png", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  figures/{name}.png")


def legend_below(fig, methods):
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLOR.get(m, "#888")) for m in methods]
    fig.legend(handles, methods, loc="lower center", ncol=min(4, len(methods)), frameon=False,
               fontsize=8, bbox_to_anchor=(0.5, -0.02))


def fig_bars(s: pd.DataFrame, cases: list[str], methods: list[str], out: Path, name: str, title: str,
             ceilings: dict | None = None):
    cases = [c for c in cases if c in set(s.case)]
    if not cases:
        return
    n = len(cases)
    fig, axes = plt.subplots(1, n, figsize=(2.6 * n + 0.6, 3.4), squeeze=False)
    used = set()
    for ax, case in zip(axes[0], cases):
        g = s[s.case == case].set_index("method")
        ms = [m for m in ordered(methods) if m in g.index]
        used |= set(ms)
        x = np.arange(len(ms))
        d = g.loc[ms, "delivered_gbps_mean"].values
        st = g.loc[ms, "stranded_gbps_mean"].clip(lower=0).values
        cols = [COLOR.get(m, "#888") for m in ms]
        ax.bar(x, d, 0.7, color=cols, edgecolor="white", linewidth=1)
        ax.bar(x, st, 0.7, bottom=d, color="white", edgecolor=cols, hatch="////", linewidth=0.8)
        for xi, v in zip(x, d):
            ax.text(xi, v / 2, f"{v:.0f}", ha="center", va="center", fontsize=7, color="white", rotation=90)
        req = g.requested_gbps_mean.max()
        ax.axhline(req, color="#52514e", linestyle=":", linewidth=1)
        ax.text(len(ms) - 0.6, req, "requested", fontsize=7, color="#52514e", va="bottom", ha="right")
        sc = case.split(" ·")[0]
        if ceilings and sc in ceilings and ceilings[sc] < req - 1:
            ax.axhline(ceilings[sc], color="#52514e", linestyle="--", linewidth=1)
            ax.text(len(ms) - 0.6, ceilings[sc], "RF ceiling", fontsize=7, color="#52514e", va="bottom", ha="right")
        ax.set_xticks([])
        ax.set_title(case, fontsize=9, color="#0b0b0b")
        style(ax, "Gbps (mean per second)" if ax is axes[0][0] else None)
        ax.set_ylim(0, req * 1.1)
    legend_below(fig, ordered(used))
    fig.suptitle(title, fontsize=10, x=0.01, y=0.99, ha="left", color="#0b0b0b")
    fig.text(0.01, 0.905, "Solid = delivered; hatched = admitted but stranded in the network", fontsize=7.5,
             color="#52514e")
    fig.tight_layout(rect=(0, 0.08, 1, 0.86))
    save(fig, out, name)


def fig_gw_sweep(s: pd.DataFrame, out: Path):
    s = s.copy()
    s["scen"] = s.case.str.split(" ·").str[0]
    s["gw"] = s.case.str.extract(r"GW×([\d.]+)")[0].astype(float).fillna(1.0)
    s = s[~s.case.str.contains("ISL")]
    scens = [x for x in ["10k-uniform", "5k-wide-pap"]
             if s[(s.scen == x) & (s.method == PROPOSED)].gw.nunique() > 1]  # sweep only where proposed was swept
    if not scens:
        return
    fig, axes = plt.subplots(1, len(scens), figsize=(4.2 * len(scens), 3.4), squeeze=False)
    used = set()
    for ax, sc in zip(axes[0], scens):
        g = s[s.scen == sc]
        for m in ordered(g.method):
            if m not in [PROPOSED] + BASELINES:
                continue
            h = g[g.method == m].sort_values("gw")
            if h.gw.nunique() < 2:
                continue
            used.add(m)
            ax.errorbar(h.gw, h.delivered_gbps_mean, yerr=h.delivered_gbps_std, color=COLOR.get(m),
                        marker=MARKER.get(m, "o"), markersize=6, linewidth=2, capsize=2,
                        markeredgecolor="white", markeredgewidth=1, label=m)
        ax.set_xticks(sorted(g.gw.unique()))
        ax.set_xticklabels([f"×{v:g}" for v in sorted(g.gw.unique())])
        ax.set_title(sc, fontsize=9)
        style(ax, "Delivered (Gbps)" if ax is axes[0][0] else None, "Gateway capacity scale")
    handles = [plt.Line2D([], [], color=COLOR[m], marker=MARKER[m], linewidth=2) for m in ordered(used)]
    fig.legend(handles, ordered(used), loc="lower center", ncol=4, frameon=False, fontsize=8,
               bbox_to_anchor=(0.5, -0.04))
    fig.suptitle("Delivered throughput as gateway capacity shrinks", fontsize=10, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.08, 1, 0.95))
    save(fig, out, "fig2_gateway_sweep")


def fig_cdf(cdf: pd.DataFrame, cases: list[str], out: Path):
    if cdf.empty:
        return
    cases = [c for c in cases if c in set(cdf.case)]
    if not cases:
        return
    fig, axes = plt.subplots(1, len(cases), figsize=(4.0 * len(cases), 3.4), squeeze=False)
    used = set()
    for ax, case in zip(axes[0], cases):
        g = cdf[cdf.case == case]
        for m in ordered(g.method):
            if m in ("M3: no ISL awareness", "M4: no gateway awareness"):
                continue  # keep the CDF readable: baselines, proposed, and the fairness ablation
            v = np.sort(g[g.method == m].sat.clip(0, 1).values)
            if not len(v):
                continue
            used.add(m)
            ax.step(v, np.arange(1, len(v) + 1) / len(v), where="post", color=COLOR.get(m, "#888"), linewidth=2,
                    linestyle=DASH.get(m, "-"))
        ax.set_xlim(0, 1.02)
        ax.set_ylim(0, 1.02)
        ax.set_title(case, fontsize=9)
        style(ax, "Fraction of cell-seconds" if ax is axes[0][0] else None,
              "Per-cell satisfaction (delivered / offered, est.)")
    legend_below(fig, ordered(used))
    fig.suptitle("Distribution of per-cell service (further right = better served)", fontsize=10, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.1, 1, 0.95))
    save(fig, out, "fig3_cell_satisfaction_cdf")


def fig_timeseries(df: pd.DataFrame, case: str, out: Path):
    g = df[df.case == case]
    if g.empty or g.method.nunique() < 2:
        return
    fig, axes = plt.subplots(2, 1, figsize=(6.4, 4.8), sharex=True)
    for m in ordered(g.method):
        h = g[g.method == m].sort_values("t_s")
        for ax, col in zip(axes, ["delivered_gbps", "jain_d"]):
            ax.plot(h.t_s, h[col], color=COLOR.get(m, "#888"), linewidth=2, label=m, linestyle=DASH.get(m, "-"))
    style(axes[0], "Delivered (Gbps)")
    style(axes[1], "Jain's fairness (delivered)", "Simulated second")
    for t0, lab in [(20, "→ north"), (40, "→ south")]:
        if g.t_s.max() >= t0:
            for ax in axes:
                ax.axvline(t0, color="#9a9994", linestyle=":", linewidth=1)
            axes[0].text(t0 + 0.3, 1.01, lab, fontsize=7, color="#52514e", va="bottom",
                         transform=axes[0].get_xaxis_transform())
    legend_below(fig, ordered(g.method))
    fig.suptitle(f"{case}: throughput and fairness over time (hotspot starts at Port-au-Prince)", fontsize=10,
                 x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.07, 1, 0.95))
    save(fig, out, "fig4_shift_timeseries")


def fig_runtime(df: pd.DataFrame, out: Path):
    g = df.dropna(subset=["allocation_s"])
    if g.empty:
        return
    ms = ordered(g.method)
    fig, ax = plt.subplots(figsize=(1.1 * len(ms) + 1.5, 3.2))
    for i, m in enumerate(ms):
        v = g[g.method == m].allocation_s.clip(lower=1e-3)
        jitter = np.random.default_rng(0).uniform(-0.18, 0.18, len(v))
        ax.scatter(np.full(len(v), i) + jitter, v, s=9, color=COLOR.get(m, "#888"), alpha=0.5, linewidths=0)
        ax.plot([i - 0.3, i + 0.3], [v.median()] * 2, color="#0b0b0b", linewidth=1.5)
        med = v.median()
        ax.text(i + 0.33, med, f"{med:.0f} s" if med >= 10 else f"{med:.2g} s", fontsize=7, va="center",
                color="#52514e")
    ax.set_yscale("log")
    ax.set_xticks(range(len(ms)))
    wrap = {"Demand-proportional": "Demand-\nproportional", "Greedy-uncoordinated": "Greedy-\nuncoordinated",
            "M3: no ISL awareness": "M3: no ISL\nawareness", "M4: no gateway awareness": "M4: no\ngateway aware.",
            "M5: no fairness": "M5: no\nfairness"}
    ax.set_xticklabels([wrap.get(m, m.replace(": ", ":\n").replace(" (", "\n(")) for m in ms], fontsize=7)
    style(ax, "Allocation time per second (s, log)")
    ax.set_title("Beam-allocation runtime per simulated second (bar = median)", fontsize=10, loc="left")
    fig.tight_layout()
    save(fig, out, "fig7_allocation_runtime")


def shell_outputs(path: Path, out: Path, tables: Path) -> str:
    sh = pd.read_csv(path)
    sh["method"] = [method_of(e, p) for e, p in zip(sh.experiment, sh.policy)]
    sh["scenario"] = sh.scenario.map(lambda s: SCENARIO_SHORT.get(s, s))
    sh["case"] = sh.apply(case_name, axis=1)
    sh["is0"] = np.where(sh.shell == 0, "shell 0 (no ISLs)", "shells 1–4")
    per = (sh.groupby(["case", "method", "t_s", "is0"])[["admitted_gbps", "stranded_gbps", "sats_over_gs_cap"]]
           .sum().groupby(["case", "method", "is0"]).mean().reset_index())
    piv = per.pivot_table(index=["case", "method"], columns="is0",
                          values=["admitted_gbps", "stranded_gbps", "sats_over_gs_cap"])
    piv.columns = [f"{a}|{b}" for a, b in piv.columns]
    piv = piv.reset_index()
    a0, a1 = "admitted_gbps|shell 0 (no ISLs)", "admitted_gbps|shells 1–4"
    s0, s1 = "stranded_gbps|shell 0 (no ISLs)", "stranded_gbps|shells 1–4"
    piv["shell0_share"] = piv[a0] / (piv[a0] + piv[a1])
    piv["stranded_on_shell0_share"] = piv[s0] / (piv[s0] + piv[s1]).replace(0, np.nan)
    piv.to_csv(tables / "shell_summary.csv", index=False)
    md = ["| Case | Method | Admitted on shell 0 (Gbps) | Shell-0 share | Stranded shell 0 | Stranded shells 1–4 | Shell-0 sats over 20.8 Gbps |",
          "|---|---|---:|---:|---:|---:|---:|"]
    for _, r in piv.iterrows():
        md.append(f"| {r.case} | {r.method} | {r[a0]:.1f} | {r.shell0_share:.0%} | {r[s0]:.1f} | {r[s1]:.1f} | "
                  f"{r['sats_over_gs_cap|shell 0 (no ISLs)']:.1f} |")
    (tables / "shell_summary.md").write_text("\n".join(md) + "\n")
    print("  tables/shell_summary.md")

    cases = [c for c in ["10k-uniform", "5k-wide-pap", "5k-wide-pap · GW×0.5"] if c in set(piv.case)]
    if cases:
        fig, axes = plt.subplots(1, len(cases), figsize=(3.0 * len(cases) + 0.6, 3.4), squeeze=False)
        used = set()
        for ax, case in zip(axes[0], cases):
            g = piv[piv.case == case].set_index("method")
            ms = [m for m in ordered(g.index) if m in [PROPOSED] + BASELINES]
            used |= set(ms)
            x = np.arange(len(ms))
            cols = [COLOR.get(m, "#888") for m in ms]
            ax.bar(x, g.loc[ms, a0], 0.7, color=cols, edgecolor="white")
            ax.bar(x, g.loc[ms, s0], 0.7, color="white", edgecolor=cols, hatch="////")
            for xi, m in zip(x, ms):
                ax.text(xi, g.loc[m, a0], f"{g.loc[m, 'shell0_share']:.0%}", ha="center", va="bottom", fontsize=7,
                        color="#52514e")
            ax.set_xticks([])
            ax.set_title(case, fontsize=9)
            style(ax, "Gbps on shell 0 (mean per second)" if ax is axes[0][0] else None)
        legend_below(fig, ordered(used))
        fig.suptitle("Load placed on shell 0 (no ISLs) and how much of it strands", fontsize=10, x=0.01, ha="left")
        fig.text(0.01, 0.9, "Bar = admitted on shell 0 (label: share of all admitted); hatched = stranded on shell 0",
                 fontsize=7.5, color="#52514e")
        fig.tight_layout(rect=(0, 0.08, 1, 0.88))
        save(fig, out, "fig6_shell0_load")
    return "\n".join(md)


def rf_ceilings(terminals_dir: Path | None) -> dict:
    """Max admissible Gbps per scenario from RF alone: sum over cells of min(n*100, 8*1280) Mbps."""
    out = {}
    if not terminals_dir or not terminals_dir.exists():
        return out
    for f in terminals_dir.glob("cells_haiti_0_*.txt"):
        n = [int(l.split(",")[1]) for l in f.read_text().split()]
        out[SCENARIO_SHORT.get(f.stem, f.stem)] = sum(min(k * 100, 8 * 1280) for k in n) / 1e3
    return out


# --- main --------------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("experiments", nargs="+", type=Path)
    p.add_argument("--out", type=Path, default=Path("results/pr2"))
    p.add_argument("--shell-csv", type=Path, default=None)
    p.add_argument("--terminals", type=Path, default=Path("terminal_deployment/terminals"))
    a = p.parse_args()

    figs, tables = a.out / "figures", a.out / "tables"
    figs.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)

    raw, cells = load([e for e in a.experiments if e.is_dir()])
    df = common_seconds(raw)
    multi = df.groupby("case").method.transform("nunique") > 1  # drop cases only one method ran
    df = df[multi].reset_index(drop=True)
    dropped = len(raw) - len(df)
    df.to_csv(tables / "runs_tidy.csv", index=False)
    if not cells.empty:
        cells = cells.merge(df[["case", "method", "t_s"]].drop_duplicates(), on=["case", "method", "t_s"])

    s = summarize(df)
    s.to_csv(tables / "summary_by_case.csv", index=False)
    (tables / "summary_by_case.md").write_text(
        "Means over simulated seconds (± std for throughput). Per-cell metrics (Jain, starvation) use "
        "CosmoSim's estimated per-cell delivery.\n" + summary_md(s))
    vb = vs_best(s)
    vb.to_csv(tables / "vs_best_baseline.csv", index=False)
    print(f"{len(df)} runs kept ({dropped} dropped to equalise seconds), {df.case.nunique()} cases, "
          f"{df.method.nunique()} methods")

    ceil = rf_ceilings(a.terminals)
    main_cases = ["10k-uniform", "5k-wide-pap", "5k-wide-north", "5k-wide-shift", "10k-hotspot-pap"]
    fig_bars(s, main_cases, [PROPOSED] + BASELINES, figs, "fig1_main_comparison",
             "Proposed allocator vs. baselines at normal capacity", ceil)
    fig_gw_sweep(s, figs)
    cdf_cases = [c for c in ["5k-wide-shift", "5k-wide-pap · GW×0.5", "10k-uniform"] if c in set(s.case)][:2]
    fig_cdf(cells, cdf_cases, figs)
    fig_timeseries(df, "5k-wide-shift", figs)
    lgw = sorted(c for c in s.case.unique() if "GW×" in c and not c.startswith("1k-")
                 and s[s.case == c].method.isin(ABLATIONS).any())
    fig_bars(s, lgw, [PROPOSED] + ABLATIONS + ["Greedy-uncoordinated"], figs, "fig5_ablations",
             "Ablations under limited gateway capacity", ceil)
    fig_runtime(df, figs)
    shell_md = shell_outputs(a.shell_csv, figs, tables) if a.shell_csv and a.shell_csv.exists() else ""

    # findings.md: numbers to check, not prose to paste blindly
    L = ["# PR2 auto-generated findings (verify before quoting)\n",
         f"- Runs: {len(df)} kept, {dropped} dropped so every method in a case covers the same seconds.",
         f"- Rule violations: {int(df.rule_violations.sum())}; consistency failures: "
         f"{int((df.consistency_ok == False).sum())}.",  # noqa: E712
         f"- Max starvation rate (cells with demand but zero delivery) in any run: {df.starve_deliv.max():.3f}.\n",
         "## Proposed vs best baseline (delivered throughput)\n",
         "| Case | Best baseline | Baseline | Proposed | Δ Gbps | Δ % | vs Equal RF | Stranded (base→prop) | Jain (base→prop) | n s |",
         "|---|---|---:|---:|---:|---:|---:|---|---|---:|"]
    for _, r in vb.iterrows():
        L.append(f"| {r.case} | {r.best_baseline} | {r.baseline_delivered:.1f} | {r.proposed_delivered:.1f} | "
                 f"{r.delta_gbps:+.1f} | {r.delta_pct:+.1f}% | {r.proposed_vs_equal_pct:+.1f}% | "
                 f"{r.baseline_stranded:.1f}→{r.proposed_stranded:.1f} | {r.baseline_jain:.3f}→{r.proposed_jain:.3f} | "
                 f"{r.n_seconds} |")
    partial = vb[vb.baselines_run.str.count(",") < len(BASELINES) - 1] if not vb.empty else vb
    if not partial.empty:
        L += ["\nNote: not every baseline ran in these cases, so 'best baseline' is best of those run: " +
              "; ".join(f"{r.case} ({r.baselines_run})" for _, r in partial.iterrows())]
    if ceil:
        L += ["\n## RF admission ceilings (from terminal files)\n",
              "Sum over cells of min(terminals×100 Mbps, 8 channels × 1.28 Gbps). No allocator can admit more.\n"]
        L += [f"- {k}: {v:.1f} Gbps" for k, v in sorted(ceil.items())]
    rt = df.groupby("method").allocation_s.median().dropna()
    if not rt.empty:
        L += ["\n## Median allocation time per simulated second\n"] + [f"- {m}: {v:.3g} s" for m, v in rt.items()]
    if shell_md:
        L += ["\n## Shell-0 load\n", shell_md]
    (a.out / "findings.md").write_text("\n".join(L) + "\n")
    (tables / "vs_best_baseline.md").write_text("\n".join(L[5:7 + len(vb)]) + "\n")
    print(f"wrote {a.out}/findings.md")


if __name__ == "__main__":
    main()
