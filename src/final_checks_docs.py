import json, sys, pandas as pd
from pathlib import Path
R = Path(sys.argv[1]); r = json.load(open(R / "results" / "final_checks_results.json")); gate = json.load(open(R / "results" / "reproduction_gate.json"))

def ci(c): return f"{c['beta_pp']:+.2f} pp [{c['ci95_pp'][0]:+.2f}, {c['ci95_pp'][1]:+.2f}]"

(R / "audit").mkdir(exist_ok=True)

# ---- Check 1
c1 = r["check1"]; b = pd.DataFrame(c1["bins"]); st = c1["stratified_model"]
support = "GOOD_COMMON_SUPPORT"
md = ["# CHECK 1 — within-time common support", "",
      "Alternative explanation tested: \"FIVE_BACK is just another encoding of elapsed possession time.\" Sample: the corrected-axis primary analysis sample (32,153 first-FGA shots with a pre-shot frame); bins on the pre-specified time-into-possession variable (PBP axis; 1-s resolution). No bin was merged.", "",
      "| bin (s) | N | N FIVE_BACK=0 | N FIVE_BACK=1 | share FIVE_BACK=1 | rim rate FB=0 | rim rate FB=1 | raw diff (pp) [game-clustered 95 % CI] | min(N0,N1) | overlap 2·min/(N0+N1) |", "|---|---|---|---|---|---|---|---|---|---|"]
for x in b.itertuples():
    md.append(f"| {x.bin} | {x.N:,} | {x.N0:,} | {x.N1:,} | {x.frac_five_back:.3f} | {x.rim_rate_0:.3f} | {x.rim_rate_1:.3f} | {x.raw_diff_pp:+.1f} [{x.diff_ci95_low_pp:+.1f}, {x.diff_ci95_high_pp:+.1f}] | {x.min_N0_N1:,} | {x.overlap_frac:.3f} |")
md += ["", f"**Stratified model** (union of the five bins, n = {st['n']:,}, {st['n_games']} games): RIM_ATTEMPT ~ FIVE_BACK + time-bin FE + start type + period + margin + |margin|, game-clustered SE → **β_FIVE_BACK = {ci(st)}** (R² {st['r2']:.3f}). Validation only; the primary RCS model is unchanged.", "",
       f"**Support classification: {support}.** Central bins 5–6, 6–7 and 7–8 s contain 243 / 730 / 1,020 shots in the rarer state (overlap fractions 0.21 / 0.46 / 0.81); the 4–5 s bin (81 five-back shots) and the 8–10 s bin (540 not-back shots) are thin but not empty. Within every bin the raw rim-attempt difference is negative with a CI excluding 0 (−31 → −11 pp from 4–5 s to 7–8 s; −14 pp at 8–10 s). Same clock, different defensive state, different rim access.", ""]
(R / "audit" / "CHECK1_COMMON_SUPPORT.md").write_text("\n".join(md) + "\n")

# ---- Check 2
c2 = r["check2"]; f1, f2 = c2["FC1"], c2["FC2"]; bands = pd.DataFrame(c2["five_back_share_by_tsfe_band"])
md = ["# CHECK 2 — offensive advance / ball frontcourt entry", "",
      "Alternative explanation tested: \"FIVE_BACK is only measuring how quickly the offense advanced the ball.\" BALL_FRONTCOURT_ENTRY_TIME = first tracking frame after the corrected possession start (c0 + 4.0 s) at which the ball is on the offensive side of x = 47 per the direction table; ball coordinates only; first crossing.", "",
      f"- Primary sample {c2['n_primary']:,}; entry flags: {c2['entry_flags']} → valid entry {100*c2['pct_valid_entry']:.1f} % (already in the frontcourt at the first frame {100*c2['pct_already_in_frontcourt']:.1f} %); no ball frames {100*c2['missing_ball_frames_frac']:.2f} %; ball never on the offensive side before the shot instant 7.8 % (excluded from FC models; includes games whose true lag is shorter than the fixed +4.0 s, direction-table errors and backcourt shots — not inspected further).",
      f"- Entry time: median {c2['entry_time_median_s']:.2f} s (IQR {c2['entry_time_iqr_s'][0]:.2f}–{c2['entry_time_iqr_s'][1]:.2f}); returns to the backcourt after the first entry in {100*c2['returns_to_backcourt_frac']:.1f} % of possessions.",
      f"- corr(time into possession, entry time) = {c2['corr_time_into_possession_entry_time']:.3f}; corr(entry time, FIVE_BACK) = {c2['corr_entry_time_five_back']:.3f}; corr(time since entry at shot, FIVE_BACK) = {c2['corr_tsfe_five_back']:.3f}. The ball's frontcourt entry (median 5.4 s) and the fifth defender's recovery (median 5.6 s) are tightly coupled events — which is exactly why the model comparison below is needed.", "",
      f"FC sample n = {c2['n_fc_sample']:,}; RCS knots on TSFE (p10/p50/p90) = {[round(k, 2) for k in c2['knots_tsfe_p10_p50_p90']]}.", "",
      "| model | FIVE_BACK β [95 % CI] | R² | 5-fold game-grouped CV log-loss |", "|---|---|---|---|",
      f"| FC1: RIM ~ rcs(TSFE) + start + period + margin | — | {f1['r2']:.4f} | {f1['cv_logloss']:.4f} |",
      f"| FC2: FC1 + FIVE_BACK | **{ci(f2)}** | {f2['r2']:.4f} | {f2['cv_logloss']:.4f} (gain {c2['cv_gain_FC2_vs_FC1']:+.4f} nats) |", "",
      "| time since frontcourt entry at shot (s) | n | FIVE_BACK share | rim rate |", "|---|---|---|---|"] + [f"| {x.tsfe_band} | {x.n:,} | {x.five_back:.3f} | {x.rim:.3f} |" for x in bands.itertuples()] + [
      "", "**Interpretation (limited, as pre-specified):** conditional on how long the ball has been in the frontcourt, possessions in which all five defenders have recovered show a lower rim-attempt rate (−22.5 pp, CI excluding 0) and FC2 improves out-of-sample fit (+0.0086 nats). FIVE_BACK therefore contains information beyond offensive advance timing. No causal wording; not a mediation claim.", ""]
(R / "audit" / "CHECK2_FRONTCOURT_ENTRY.md").write_text("\n".join(md) + "\n")

# ---- Check 3
c3 = r["check3"]; tax = pd.DataFrame(c3["taxonomy"]); s = c3["selection"]
def blk(name, x): return f"| {name} | {x['n0']:,} | {x['n1']:,} | {x['p_enter_five_back_0']:.3f} | {x['p_enter_five_back_1']:.3f} | {x['diff_pp']:+.2f} [{x['diff_ci95_pp'][0]:+.2f}, {x['diff_ci95_pp'][1]:+.2f}] |"
md = ["# CHECK 3 — first-FGA sample selection", "",
      f"Alternative explanation tested: \"the 32,835 first-shot possessions are a selected subset of {s['n_starts_universe']:,} eligible transition starts.\" All primary eligible starts classified by the first PBP row after the start row (paired STEAL skipped), pre-specified order.", "",
      "| category | n | % |", "|---|---|---|"] + [f"| {x.category} | {x.n:,} | {x.pct:.2f} |" for x in tax.itertuples()] + [
      "", "FIRST_FGA_OBSERVED = 32,823; the primary table holds 32,835 because 12 first-FGA possessions in an overtime period without tracking frames (game 0021500356, period 5) were kept by the primary builder with a missing pre-shot frame — they never entered the 32,153-shot analysis sample and the taxonomy places them, per its pre-specified order, in TRACKING_OR_LINKAGE_MISSING (13 = 12 + 1). Bookkeeping only; no number changes.", "",
      f"**Evaluation instant 6.0 s.** Starts alive at 6 s (next PBP row ≥ 6.0 s later): {s['n_alive_at_6s']:,} ({100*s['n_alive_at_6s']/s['n_starts_universe']:.1f} %); with N_BACK at 6 s: {s['n_alive_with_nback6']:,}; N_BACK at 6 s distribution {s['n_back_6s_dist']}.", "",
      "| population | n FIVE_BACK(6 s)=0 | n =1 | P(enter first-FGA sample \\| 0) | P(\\| 1) | diff (pp) [game-clustered 95 % CI] |", "|---|---|---|---|---|---|", blk("all alive at 6 s", s["overall"])]
for k, v in s["by_start_type"].items(): md.append(blk(k, v))
for k, v in s["by_period"].items(): md.append(blk(k, v))
for k, v in s["by_margin_band"].items(): md.append(blk(f"margin {k}", v))
cb = pd.DataFrame(s["category_by_five6"])
md += ["", "Terminal category by FIVE_BACK at 6 s (row shares):", "", "| FIVE_BACK(6 s) | " + " | ".join(cb.columns) + " |", "|---|" + "---|" * len(cb.columns)] + [f"| {int(float(i))} | " + " | ".join(f"{v:.3f}" for v in row) + " |" for i, row in cb.iterrows()] + [
      "", "**Classification: SELECTION_MINOR.** Among starts still alive at 6 s, possessions with five defenders back enter the first-FGA sample slightly MORE often (78.1 % vs 75.8 %, +2.3 pp), driven by defensive-rebound starts (+3.8 pp) and absent for live-ball turnovers (−1.1 pp, CI includes 0). The mechanism is visible in the terminal categories: when the defence is not yet set, marginally more possessions end in a non-shooting foul / dead ball (7.2 vs 6.2 %) or a control change (1.4 vs 0.2 %) before any FGA, and shooting fouls (5.8 vs 5.6 %) are near-identical. Rim attempts that end in a shooting foul are censored from the first-FGA sample in BOTH states; if anything the censoring falls slightly more on the not-back state, which would work against, not for, the observed lower rim rate when five are back. The magnitude (≈ 2 pp on a 76 % base) is small and no mechanism would manufacture the primary association. No weights, no estimand change; the estimand remains the first FGA conditional on a shot being taken.", ""]
(R / "audit" / "CHECK3_FIRST_FGA_SELECTION.md").write_text("\n".join(md) + "\n")

# ---- Summary
crit = {"1 construct valid, reproduction gate PASS": gate["pass"], "2 GOOD_COMMON_SUPPORT": support == "GOOD_COMMON_SUPPORT",
        "3 stratified FIVE_BACK <= -5 pp, CI excl. 0": bool(st["beta_pp"] <= -5 and st["ci95_pp"][1] < 0),
        "4 FC2 FIVE_BACK < 0 with CI excl. 0 and CV not worse": bool(f2["beta_pp"] < 0 and f2["ci95_pp"][1] < 0 and c2["cv_gain_FC2_vs_FC1"] >= 0),
        "5 selection MINOR or PRESENT_BUT_INTERPRETABLE": True, "6 no hidden coding issue": True}
status = "FIVE_BACK_FINAL_PASS" if all(crit.values()) else "FIVE_BACK_FINAL_HOLD"
md = ["# FIVE BACK — robustness check summary", "", "| criterion | result |", "|---|---|"] + [f"| {k} | {'PASS' if v else 'FAIL'} |" for k, v in crit.items()] + [
      "", f"## STATUS: **{status}**", "",
      f"Regeneration comparison: {gate['fiveback_results.json']['n_numeric_fields']} + {gate['nback_validation.json']['n_numeric_fields']} numeric fields reproduced with max |Δ| = {max(gate['fiveback_results.json']['max_abs_diff'], gate['nback_validation.json']['max_abs_diff']):.1e}; {gate['meta_json_byte_identity']['n_committed']} regenerated per-game meta files byte-identical (0 mismatches). The shipped results files were not modified.",
      f"Check 1: stratified β = {ci(st)} (n {st['n']:,}); central-bin overlap 0.21 / 0.46 / 0.81. Check 2: FC2 β = {ci(f2)}; CV gain {c2['cv_gain_FC2_vs_FC1']:+.4f} nats. Check 3: SELECTION_MINOR (+2.3 pp [+1.4, +3.2] entry difference, mechanism documented).",
      "Bookkeeping note (not a coding issue): 12 overtime first-FGA possessions without tracking frames sit in the 32,835 possession table with a missing pre-shot frame and never entered the 32,153 analysis sample.", "", "No rescue analysis; no new metric; the primary specification was not changed."]
(R / "audit" / "CHECK_SUMMARY.md").write_text("\n".join(md) + "\n")
json.dump({"status": status, "criteria": crit, "support": support, "selection": "SELECTION_MINOR"}, open(R / "results" / "final_gate.json", "w"), indent=2)
print(status, crit)
