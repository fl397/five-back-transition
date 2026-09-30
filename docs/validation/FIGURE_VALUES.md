# Figure values

Every value plotted in the two figures, traced to the result file it comes from.

Producer: `src/figures_final.py` (renders ONLY from `results/nback_validation.json`, `results/fiveback_results.json`, `results/check1_common_support.json`; no tracking access). Outputs in `figures/`: `FIG1_recovery_clock.{pdf,png}`, `FIG2_clock_vs_defenders.{pdf,png}` (PNG 300 dpi), captions `FIG1_caption.txt`, `FIG2_caption.txt`. Rendered from the result files shipped in `results/`.

Presentation conventions: axis names in basketball language with units; "N_BACK"/"FIVE_BACK" replaced by "defenders back"/"five-back state" in figure text; CI meaning stated in caption and inset title ("95% CI, clustered by game"); legends ≥ 9 pt; captions self-contained; no claim stronger than the abstract (associations only).

## Figure 1 — `FIG1_recovery_clock`
| element | plotted value | artifact field | match |
|---|---|---|---|
| cumulative % five back at 2 / 4 / 6 / 8 s | 2.7 / 10.1 / 56.6 / 89.6 % | `nback_validation.json:p_five_back_by_s` = 0.0273 / 0.1006 / 0.5660 / 0.8956 | ✔ |
| median T5 (dashed line) | 5.63 s | `median_time_to_five_s` = 5.63 | ✔ |
| IQR band | 4.82–6.39 s | `p25_p75_time_to_five_s` = [4.82, 6.39] | ✔ |
| "still lack a fifth defender at 8 s" (caption) | 10.4 % | `never_reach_5_within_8s_among_8s_possessions` = 0.1044 | ✔ |
| possessions tracked 8 s (caption) | 31,794 | `possessions_with_8s_tracking` = 31794 | ✔ |
| games | 631 | `n_games` = 631 | ✔ |
| mean defenders back curve (grey) | 0.0–8.0 s, 0.225 → 4.8 | `mean_n_back_curve` (81 points) | ✔ |
| inset: 2 or fewer back vs five | +29.3 [26.8, 31.8] | `fiveback_results.json:corrected.B8.le2` = 29.29 [26.81, 31.78] | ✔ |
| inset: 3 back | +14.5 [11.4, 17.5] | `corrected.B8.3` = 14.46 [11.43, 17.50] | ✔ |
| inset: 4 back | +8.4 [5.8, 10.9] | `corrected.B8.4` = 8.37 [5.82, 10.91] | ✔ |

## Figure 2 — `FIG2_clock_vs_defenders`
| element | plotted value | artifact field | match |
|---|---|---|---|
| left, rim rate fewer-than-five, bins 4–5 / 5–6 / 6–7 / 7–8 / 8–10 s | 82.0 / 72.4 / 59.5 / 49.5 / 46.3 % | `check1_common_support.json:bins[*].rim_rate_0` = 0.8203 / 0.7243 / 0.5948 / 0.4951 / 0.4630 | ✔ |
| left, rim rate five back, same bins | 50.6 / 43.2 / 38.4 / 38.8 / 32.5 % | `bins[*].rim_rate_1` = 0.5062 / 0.4321 / 0.3836 / 0.3881 / 0.3250 | ✔ |
| left, shot counts fewer-than-five | 1,530 / 2,093 / 2,426 / 1,020 / 540 | `bins[*].N0` | ✔ |
| left, shot counts five back | 81 / 243 / 730 / 1,492 / 6,755 | `bins[*].N1` | ✔ |
| caption: shots in 4–10 s windows | 16,910 | `stratified_model.n` = 16910 | ✔ |
| right, time-only 2 s − 10 s contrast | +42.0 points | `fiveback_results.json:corrected.B7.time_only.early_contrast_pp` = 42.00 | ✔ |
| right, time + five-back contrast | +23.5 points | `corrected.B7.combined.early_contrast_pp` = 23.54 | ✔ |
| right, attenuation label | 44 % attenuation | `corrected.B7.early_contrast_attenuation` = 0.4396 | ✔ |
| right title, five-back coefficient | −17.3 [−19.3, −15.3] | `corrected.B7.combined.beta_pp / ci95_pp` = −17.33 [−19.35, −15.31] | ✔ |
| suptitle: shots / games | 32,153 / 631 | `corrected.n_shots` = 32153; `corrected.n_games` = 631 | ✔ |

Not plotted in either figure: the naive-timing comparison, the frontcourt-entry diagnostic and the first-shot selection analysis; their numbers are in `results/` and are discussed in the text only.
