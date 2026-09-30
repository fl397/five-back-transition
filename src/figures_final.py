#!/usr/bin/env python3
"""FIVE BACK — figures, rendered ONLY from persisted results JSON (no tracking access, no recomputation).

Inputs : results/nback_validation.json, results/fiveback_results.json, results/check1_common_support.json
Outputs: figures/FIG1_recovery_clock.{pdf,png}   recovery clock + defenders-back dose response (inset)
         figures/FIG2_clock_vs_defenders.{pdf,png} same-clock comparison (1-s bins) + early-possession gradient before/after
         figures/FIG{1,2}_caption.txt               self-contained captions
Every plotted number is listed in docs/validation/FIGURE_VALUES.md against its result field.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

R = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else R / "figures"
INK, BLUE, ORANGE, GREEN, GRID = "#262626", "#2E6F9E", "#C9622B", "#4F7F3A", "#D9D9D9"
plt.rcParams.update({"font.size": 10, "axes.titlesize": 11, "axes.labelsize": 10, "legend.fontsize": 9, "xtick.labelsize": 9, "ytick.labelsize": 9})

CAPTION1 = ("Figure 1. Defensive numerical recovery is gradual: all five defenders return after a median {med:.2f} s, while rim access "
            "decreases as more defenders recover. Main panel: share of transition possessions (after a defensive rebound or a live-ball "
            "turnover) in which all five defenders have returned to their own half of the court, by time since the possession started "
            "(2015-16 NBA, 631 games, {n8:,} possessions tracked for 8 s). Dashed line and shaded band: median ({med:.2f} s) and interquartile "
            "range ({q1:.2f}-{q3:.2f} s) of the time until all five are back; {never:.1f}% of possessions still lack a fifth defender at 8 s. "
            "Grey line (right axis): mean number of defenders back. Inset: difference in the probability that the first field-goal attempt "
            "is a rim attempt (within 4 ft) when two or fewer, three, or four defenders are back, relative to all five back, from a linear "
            "probability model that adjusts for elapsed possession time, start type, period and score margin; bars are 95% confidence "
            "intervals with standard errors clustered by game. Values are associations, not causal effects.")
CAPTION2 = ("Figure 2. Elapsed time does not uniquely determine transition state: at the same possession time, rim-attempt rates remain "
            "substantially higher before the fifth defender recovers (6-7 s: {r0:.1f}% with fewer than five back vs {r1:.1f}% with five). Left: raw rim-attempt rate of the first field-goal attempt among shots taken in the same "
            "one-second window of elapsed possession time, split by whether all five defenders were back one second before the shot "
            "(numbers above/below the points are shot counts; {n_strat:,} shots in the 4-10 s windows). Right: the model-estimated difference in "
            "rim-attempt probability between shots taken 2 s and 10 s into the possession, from a model using elapsed time only "
            "(+{t_only:.1f} points) and from the same model after adding the five-back state (+{comb:.1f} points; five-back coefficient "
            "{fb:.1f} points, 95% CI {lo:.1f} to {hi:.1f}, clustered by game). Corrected play-by-play/tracking timing; {n_shots:,} first "
            "field-goal attempts, 631 games, 2015-16. Associations only.")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    v = json.loads((R / "results" / "nback_validation.json").read_text()); res = json.loads((R / "results" / "fiveback_results.json").read_text()); c = res["corrected"]
    cs = json.loads((R / "results" / "check1_common_support.json").read_text())
    # ---------------- FIG 1 ----------------
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    ts = np.array([0, 2, 4, 6, 8]); p = np.array([0.0] + [v["p_five_back_by_s"][k] for k in ("2", "4", "6", "8")])
    ax.plot(ts, 100 * p, "o-", color=BLUE, lw=2.2, ms=6, label="all five defenders back (cumulative %)")
    med, (q1, q3) = v["median_time_to_five_s"], v["p25_p75_time_to_five_s"]; never = 100 * v["never_reach_5_within_8s_among_8s_possessions"]
    ax.axvspan(q1, q3, color=BLUE, alpha=0.08, lw=0); ax.axvline(med, color=BLUE, lw=1.0, ls="--")
    ax.text(q3 + 0.12, 36, f"median {med:.2f} s\nIQR {q1:.2f}-{q3:.2f} s", fontsize=9, color=BLUE, va="bottom", ha="left")
    for t, y in zip(ts[1:], p[1:]):
        ax.text(t, 100 * y + 3.5, f"{100*y:.1f}%", ha="center", fontsize=9, color=INK)
    ax2 = ax.twinx(); curve = v["mean_n_back_curve"]; xs = np.array([float(k) for k in curve]); ys = np.array([curve[k] for k in curve])
    ax2.plot(xs, ys, color="#8A8A8A", lw=1.3, label="mean defenders back (right axis)"); ax2.set_ylim(0, 5.3); ax2.set_ylabel("mean number of defenders back", color="#666"); ax2.tick_params(colors="#666")
    ax.set_xlim(0, 8.4); ax.set_ylim(0, 108); ax.set_xlabel("time since the possession started (seconds)"); ax.set_ylabel("possessions with all five defenders back (%)")
    ax.set_title("How long does it take the defense to get five back?")
    ax.grid(color=GRID, lw=0.5); ax.spines[["top"]].set_visible(False); ax2.spines[["top"]].set_visible(False)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels(); ax.legend(h1 + h2, l1 + l2, frameon=False, loc="lower right")
    ins = ax.inset_axes([0.115, 0.50, 0.27, 0.40]); cats = ["le2", "3", "4"]; labs = ["2 or fewer", "3", "4"]
    b = [c["B8"][k]["beta_pp"] for k in cats]; lo = [c["B8"][k]["ci95_pp"][0] for k in cats]; hi = [c["B8"][k]["ci95_pp"][1] for k in cats]
    ins.errorbar(range(3), b, yerr=[np.subtract(b, lo), np.subtract(hi, b)], fmt="o", color=ORANGE, capsize=4, ms=5, lw=1.3)
    for i, bb in enumerate(b):
        ins.text(i + 0.12, bb, f"+{bb:.1f}", fontsize=8, va="center", color=ORANGE)
    ins.axhline(0, color="#666", lw=0.8); ins.set_xticks(range(3)); ins.set_xticklabels(labs, fontsize=8); ins.set_xlabel("defenders back (vs. all five)", fontsize=8); ins.set_ylabel("rim-attempt points\nabove five back", fontsize=8)
    ins.set_title("time-adjusted; 95% CI", fontsize=8); ins.tick_params(labelsize=8); ins.set_ylim(0, 36); ins.set_xlim(-0.4, 2.6); ins.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(OUT / "FIG1_recovery_clock.png", dpi=300); fig.savefig(OUT / "FIG1_recovery_clock.pdf"); plt.close(fig)
    (OUT / "FIG1_caption.txt").write_text(CAPTION1.format(n8=v["possessions_with_8s_tracking"], med=med, q1=q1, q3=q3, never=never) + "\n")
    # ---------------- FIG 2 ----------------
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.6), gridspec_kw={"width_ratios": [1.3, 1]})
    bins = cs["bins"]; x = np.arange(len(bins)); labels = [f"{b_['bin']} s" for b_ in bins]
    for key, nkey, col, lab, dy in (("rim_rate_0", "N0", ORANGE, "fewer than five defenders back", 3.0), ("rim_rate_1", "N1", BLUE, "all five defenders back", -5.0)):
        rr = np.array([b_[key] for b_ in bins]); nn = [b_[nkey] for b_ in bins]
        ax[0].plot(x, 100 * rr, "o-", color=col, lw=2.0, ms=6, label=lab)
        for xi, r_, n_ in zip(x, rr, nn):
            ax[0].text(xi, 100 * r_ + dy, f"n={n_:,}", ha="center", fontsize=8, color=col)
    i67 = next(i for i, b_ in enumerate(bins) if b_["bin"] == "6-7"); b67h = bins[i67]
    ax[0].axvspan(i67 - 0.32, i67 + 0.32, color="#F2E6D8", alpha=0.7, lw=0, zorder=0)
    ax[0].annotate(f"6-7 s: {100*b67h['rim_rate_0']:.1f}% vs {100*b67h['rim_rate_1']:.1f}%", xy=(i67, 100 * b67h["rim_rate_0"] + 9), ha="center", fontsize=9, color=INK, fontweight="bold")
    ax[0].set_xticks(x); ax[0].set_xticklabels(labels); ax[0].set_ylabel("first shot is a rim attempt (%)"); ax[0].set_xlabel("time since the possession started (one-second windows)")
    ax[0].set_title("Same clock, different defensive state"); ax[0].legend(frameon=False, loc="upper right"); ax[0].grid(color=GRID, lw=0.5); ax[0].spines[["top", "right"]].set_visible(False); ax[0].set_ylim(20, 95)
    B7 = c["B7"]; vals = [B7["time_only"]["early_contrast_pp"], B7["combined"]["early_contrast_pp"]]
    ax[1].bar([0, 1], vals, width=0.55, color=[GREEN, BLUE]); ax[1].set_xticks([0, 1]); ax[1].set_xticklabels(["elapsed time only", "elapsed time +\nfive-back state"])
    for i, v_ in enumerate(vals):
        ax[1].text(i, v_ + 1.2, f"+{v_:.1f} points", ha="center", fontsize=10)
    att = 100 * B7["early_contrast_attenuation"]; ax[1].annotate(f"{att:.0f}% attenuation", xy=(1, vals[1] + 9.5), ha="center", fontsize=12, color=INK, fontweight="bold")
    ax[1].set_ylabel("rim-attempt probability difference,\nshots at 2 s minus shots at 10 s (points)"); ax[1].set_ylim(0, 52)
    fb = B7["combined"]; ax[1].set_title(f"Early-possession gradient before / after five-back\n(five-back coefficient {fb['beta_pp']:.1f} points, 95% CI {fb['ci95_pp'][0]:.1f} to {fb['ci95_pp'][1]:.1f})", fontsize=10)
    ax[1].spines[["top", "right"]].set_visible(False); ax[1].grid(axis="y", color=GRID, lw=0.5)
    fig.suptitle(f"First field-goal attempts after a defensive rebound or live-ball turnover; {c['n_shots']:,} shots, {c['n_games']} games, 2015-16; corrected play-by-play/tracking timing", fontsize=9)
    fig.tight_layout(); fig.savefig(OUT / "FIG2_clock_vs_defenders.png", dpi=300); fig.savefig(OUT / "FIG2_clock_vs_defenders.pdf"); plt.close(fig)
    b67 = next(b_ for b_ in bins if b_["bin"] == "6-7")
    (OUT / "FIG2_caption.txt").write_text(CAPTION2.format(r0=100 * b67["rim_rate_0"], r1=100 * b67["rim_rate_1"], n_strat=cs["stratified_model"]["n"], t_only=vals[0], comb=vals[1], fb=fb["beta_pp"], lo=fb["ci95_pp"][0], hi=fb["ci95_pp"][1], n_shots=c["n_shots"]) + "\n")
    print("final figures written to", OUT); return 0


if __name__ == "__main__":
    raise SystemExit(main())
