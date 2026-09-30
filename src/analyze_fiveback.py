#!/usr/bin/env python3
"""FIVE BACK — primary analysis under the pre-specified rules (configs/analysis_definitions.yaml). Run only after the construct
validation passes. Builds data/shots_fiveback_{naive,corrected}.parquet, runs MODEL T / MODEL D / clock-vs-fifth-defender / dose
response for both axes, and applies the pre-specified classification rules mechanically. Writes results/fiveback_results.json,
audit/PRIMARY_RESULTS.md, audit/NAIVE_VS_CORRECTED.md.
"""
from __future__ import annotations
import glob, json
from pathlib import Path
import numpy as np, pandas as pd
import statsmodels.api as sm
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

R = Path(__file__).resolve().parents[1]
SEED = 20260920


def rcs_basis(x, knots):
    k = np.asarray(knots, float); kn = len(k); cols = []
    for j in range(kn - 2):
        t = (np.clip(x - k[j], 0, None) ** 3 - np.clip(x - k[kn - 2], 0, None) ** 3 * (k[kn - 1] - k[j]) / (k[kn - 1] - k[kn - 2])
             + np.clip(x - k[kn - 1], 0, None) ** 3 * (k[kn - 2] - k[j]) / (k[kn - 1] - k[kn - 2])) / (k[kn - 1] - k[0]) ** 2
        cols.append(t)
    return np.column_stack(cols)


def design(d, knots, time=True, five=False, dose=False, defender=False, start=True):
    X = pd.DataFrame(index=d.index)
    if five:
        X["five_back"] = d.five_back.values.astype(float)
    if dose:
        for c in ("le2", "3", "4"):
            X[f"nb_{c}"] = (d.nb_cat == c).astype(float).values
    if time:
        X["t"] = d.time_into_possession.values; X["t_rcs1"] = rcs_basis(d.time_into_possession.values, knots)[:, 0]
    if start:
        X["start_lbt"] = (d.start_type == "LIVE_BALL_TURNOVER").astype(float).values
    for p in (2, 3, 4):
        X[f"per{p}"] = (d.period.clip(upper=4) == p).astype(float).values
    X["margin"] = d.score_margin.values; X["abs_margin"] = d.score_margin.abs().values
    if defender:
        X["def_dist"] = d.defender_dist_ft.values; X["def_le4"] = (d.defender_dist_ft <= 4).astype(float).values
    return X


def fit(y, X, groups):
    m = sm.OLS(y, sm.add_constant(X, has_constant="add")).fit(cov_type="cluster", cov_kwds={"groups": groups}); return m


def coef(m, name):
    b, se = float(m.params[name]), float(m.bse[name]); return {"beta_pp": 100 * b, "se_pp": 100 * se, "ci95_pp": [100 * (b - 1.96 * se), 100 * (b + 1.96 * se)], "p": float(m.pvalues[name])}


def early_contrast(m, X, knots):
    """predicted outcome at t = 2 s minus at t = 10 s, other covariates at sample means (pp)."""
    xbar = X.mean(); rows = []
    for t in (2.0, 10.0):
        x = xbar.copy(); x["t"] = t; x["t_rcs1"] = rcs_basis(np.array([t]), knots)[0, 0]; rows.append(x)
    Xp = sm.add_constant(pd.DataFrame(rows), has_constant="add")[m.params.index]; p = m.predict(Xp); return 100 * float(p[0] - p[1])


def cv_logloss(y, X, groups, seed=SEED):
    gkf = GroupKFold(n_splits=5); ll = []
    rng = np.random.default_rng(seed); ug = np.unique(groups); perm = dict(zip(ug, rng.permutation(len(ug)))); g2 = np.array([perm[g] for g in groups])
    for tr, te in gkf.split(X, y, g2):
        clf = LogisticRegression(max_iter=2000, C=1e6).fit(X.iloc[tr], y[tr]); p = np.clip(clf.predict_proba(X.iloc[te])[:, 1], 1e-9, 1 - 1e-9)
        ll.append(-np.mean(y[te] * np.log(p) + (1 - y[te]) * np.log(1 - p)))
    return float(np.mean(ll))


def analyze(d, knots, tag):
    d = d[d.n_back.notna()].copy(); d["five_back"] = (d.n_back == 5).astype(int); y = d.rim.values.astype(float); g = d.game_id.values
    out = {"axis": tag, "n_shots": int(len(d)), "n_games": int(d.game_id.nunique()), "five_back_share": float(d.five_back.mean()), "rim_rate": float(d.rim.mean()),
           "n_back_dist": d.n_back.value_counts(normalize=True).sort_index().round(4).to_dict()}
    XT = design(d, knots, five=True); mT = fit(y, XT, g); out["model_T"] = coef(mT, "five_back") | {"r2": float(mT.rsquared), "early_contrast_pp": early_contrast(mT, XT, knots)}
    for sec, col in (("shot_distance_ft", d.shot_distance_ft.values), ("three_pa", (d.shot_value == 3).astype(float).values), ("made", d.made.values.astype(float)), ("efg", (d.made * (1 + 0.5 * (d.shot_value == 3))).values.astype(float))):
        ms = fit(col, XT, g); b, se = float(ms.params["five_back"]), float(ms.bse["five_back"]); out[f"model_T_{sec}"] = {"beta": b, "ci95": [b - 1.96 * se, b + 1.96 * se]}
    dd = d[d.defender_dist_ft.notna()]; XD = design(dd, knots, five=True, defender=True); mD = fit(dd.rim.values.astype(float), XD, dd.game_id.values)
    out["model_D"] = coef(mD, "five_back") | {"n": int(len(dd)), "def_dist_beta_pp_per_ft": 100 * float(mD.params["def_dist"]), "def_le4_beta_pp": 100 * float(mD.params["def_le4"])}
    out["model_D"]["attenuation_vs_T"] = 1 - out["model_D"]["beta_pp"] / out["model_T"]["beta_pp"] if out["model_T"]["beta_pp"] != 0 else None
    # B7 clock vs fifth defender
    Xt = design(d, knots, time=True); Xf = design(d, knots, time=False, five=True); Xc = XT
    mt, mf = fit(y, Xt, g), fit(y, Xf, g)
    ec_t, ec_c = early_contrast(mt, Xt, knots), early_contrast(mT, Xc, knots)
    out["B7"] = {"time_only": {"early_contrast_pp": ec_t, "r2": float(mt.rsquared), "cv_logloss": cv_logloss(y, Xt, g)},
                 "five_back_only": coef(mf, "five_back") | {"r2": float(mf.rsquared), "cv_logloss": cv_logloss(y, Xf, g)},
                 "combined": coef(mT, "five_back") | {"early_contrast_pp": ec_c, "r2": float(mT.rsquared), "cv_logloss": cv_logloss(y, Xc, g)}}
    out["B7"]["early_contrast_attenuation"] = 1 - ec_c / ec_t if ec_t != 0 else None
    out["B7"]["cv_logloss_gain_vs_time_only"] = out["B7"]["time_only"]["cv_logloss"] - out["B7"]["combined"]["cv_logloss"]
    # B8 dose response
    cnt = d.n_back.value_counts(); pool = any(cnt.get(k, 0) < 200 for k in (0, 1, 2))
    d["nb_cat"] = np.where(d.n_back <= 2, "le2", d.n_back.astype(int).astype(str)); out["B8_pooled_012"] = bool(pool)
    Xd = design(d, knots, dose=True); md = fit(y, Xd, g)
    out["B8"] = {c: coef(md, f"nb_{c}") for c in ("le2", "3", "4")} | {"raw_rim_rate_by_cat": d.groupby("nb_cat").rim.mean().round(4).to_dict(), "n_by_cat": d.nb_cat.value_counts().to_dict()}
    # within start type
    out["by_start_type"] = {}
    for st, gs in d.groupby("start_type"):
        Xs = design(gs, knots, five=True, start=False); ms = fit(gs.rim.values.astype(float), Xs, gs.game_id.values); out["by_start_type"][st] = coef(ms, "five_back") | {"n": int(len(gs))}
    # descriptive bands
    d["band"] = pd.cut(d.time_into_possession, [0, 2, 4, 6, 8, 12, 24], right=True, include_lowest=True, labels=["0-2", "2-4", "4-6", "6-8", "8-12", "12-24"])
    out["bands"] = d.groupby(["band", "five_back"], observed=True).agg(n=("rim", "size"), rim=("rim", "mean")).reset_index().assign(rim=lambda x: x.rim.round(4)).to_dict("records")
    return out


def substantive(res):
    T = res["model_T"]; return bool(T["beta_pp"] <= -5 and T["ci95_pp"][1] < 0)


def main() -> int:
    val = json.loads((R / "results" / "nback_validation.json").read_text()); assert val["decision"] == "PASS", "construct validation not PASS"
    d = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(str(R / "data" / "games" / "00*[0-9].parquet")))], ignore_index=True)
    d["rim"] = (d.shot_distance_ft <= 4).astype(int)
    corr = d[d.axis == "corrected"].copy(); naive = d[d.axis == "naive"].copy()
    knots = [float(np.percentile(corr.time_into_possession, q)) for q in (10, 50, 90)]
    if len(set(knots)) < 3:   # PBP 1-s granularity can tie percentiles; use unique sorted percentiles at 10/50/90 of the unique-value grid
        knots = sorted(set(knots)); knots = [knots[0], float(np.median(corr.time_into_possession)), knots[-1]] if len(knots) == 2 else knots
    corr.to_parquet(R / "data" / "shots_fiveback_corrected.parquet", index=False); naive.to_parquet(R / "data" / "shots_fiveback_naive.parquet", index=False)
    res = {"freeze_sha": "153b1ac", "knots_time_p10_p50_p90": knots, "n_possessions": int(len(corr)), "n_games": int(corr.game_id.nunique()),
           "start_type_counts": corr.start_type.value_counts().to_dict(), "missing_pre_shot_frame": {"corrected": int(corr.n_back.isna().sum()), "naive": int(naive.n_back.isna().sum())},
           "corrected": analyze(corr, knots, "corrected"), "naive": analyze(naive, knots, "naive")}
    c, n = res["corrected"], res["naive"]; sc, sn = substantive(c), substantive(n)
    bc, bn = c["model_T"]["beta_pp"], n["model_T"]["beta_pp"]
    if sc and (not sn or bn * bc < 0 or abs(bn) < 0.5 * abs(bc)):
        b9 = "REVEALED_BY_CORRECTION"
    elif sc and sn and abs(bn - bc) <= 0.5 * abs(bc):
        b9 = "STABLE_TO_ALIGNMENT"
    elif sn and not sc:
        b9 = "DESTROYED_BY_CORRECTION"
    elif not sc and not sn:
        b9 = "NO_FIVE_BACK_SIGNAL"
    else:
        b9 = "STABLE_TO_ALIGNMENT"
    res["B9_classification"] = b9
    crit = {"validation_pass": True, "T_substantive": sc, "persists_with_time": bool(c["B7"]["combined"]["beta_pp"] <= -5 and c["B7"]["combined"]["ci95_pp"][1] < 0),
            "attenuates_or_improves": bool((c["B7"]["early_contrast_attenuation"] or 0) >= 0.25 or c["B7"]["cv_logloss_gain_vs_time_only"] >= 0.002),
            "holds_within_start_types": all(v["beta_pp"] < 0 and v["ci95_pp"][1] < 0 for v in c["by_start_type"].values()),
            "corrected_not_weaker_than_naive": bool(abs(bc) >= abs(bn))}
    res["B10_criteria"] = crit; res["status"] = "FIVE_BACK_STRONG_CANDIDATE" if all(crit.values()) else "FIVE_BACK_STOP"
    (R / "results" / "fiveback_results.json").write_text(json.dumps(res, indent=2, default=float))
    write_md(res); print(json.dumps({"B9": b9, "criteria": crit, "status": res["status"], "T_corr": c["model_T"], "T_naive": n["model_T"]}, indent=1, default=float)); return 0


def f(r): return f"{r['beta_pp']:+.2f} pp [{r['ci95_pp'][0]:+.2f}, {r['ci95_pp'][1]:+.2f}]"


def write_md(res):
    c, n = res["corrected"], res["naive"]
    md = ["# FIVE BACK — primary results (pre-specified rules; construct validation read first)", "",
          f"Possessions (first-FGA, ≤ 24 s): **{res['n_possessions']:,}** in {res['n_games']} games; start types {res['start_type_counts']}; pre-shot frame missing: corrected {res['missing_pre_shot_frame']['corrected']}, naive {res['missing_pre_shot_frame']['naive']}. RCS knots on time into possession: {res['knots_time_p10_p50_p90']}.", ""]
    for tag, r in (("CORRECTED (+4.0 s)", c), ("NAIVE (0 s)", n)):
        md += [f"## {tag}", "", f"n = {r['n_shots']:,}; FIVE_BACK share {r['five_back_share']:.3f}; rim-attempt rate {r['rim_rate']:.3f}; N_BACK distribution {r['n_back_dist']}.", "",
               f"- **MODEL T (total)**: FIVE_BACK → RIM_ATTEMPT {f(r['model_T'])}; R² {r['model_T']['r2']:.4f}; early-possession contrast (2 s − 10 s) {r['model_T']['early_contrast_pp']:+.2f} pp.",
               f"  secondary: shot distance {r['model_T_shot_distance_ft']['beta']:+.2f} ft [{r['model_T_shot_distance_ft']['ci95'][0]:+.2f}, {r['model_T_shot_distance_ft']['ci95'][1]:+.2f}]; 3PA {100*r['model_T_three_pa']['beta']:+.2f} pp; made {100*r['model_T_made']['beta']:+.2f} pp; eFG {100*r['model_T_efg']['beta']:+.3f}.",
               f"- **MODEL D (direct, + defender distance)**: FIVE_BACK {f(r['model_D'])} (n {r['model_D']['n']:,}); defender distance {r['model_D']['def_dist_beta_pp_per_ft']:+.2f} pp/ft, ≤ 4 ft {r['model_D']['def_le4_beta_pp']:+.2f} pp; attenuation vs T {100*(r['model_D']['attenuation_vs_T'] or 0):.1f} %.",
               f"- **Clock vs fifth defender**: time-only early contrast {r['B7']['time_only']['early_contrast_pp']:+.2f} pp (R² {r['B7']['time_only']['r2']:.4f}, CV log-loss {r['B7']['time_only']['cv_logloss']:.4f}); FIVE_BACK-only {f(r['B7']['five_back_only'])} (R² {r['B7']['five_back_only']['r2']:.4f}, CV {r['B7']['five_back_only']['cv_logloss']:.4f}); combined FIVE_BACK {f(r['B7']['combined'])}, early contrast {r['B7']['combined']['early_contrast_pp']:+.2f} pp (attenuation {100*(r['B7']['early_contrast_attenuation'] or 0):.1f} %), R² {r['B7']['combined']['r2']:.4f}, CV {r['B7']['combined']['cv_logloss']:.4f} (gain vs time-only {r['B7']['cv_logloss_gain_vs_time_only']:+.4f} nats).",
               f"- **Dose response** (ref N_BACK = 5; pooled 0/1/2 = {r['B8_pooled_012']}): ≤2 {f(r['B8']['le2'])}; 3 {f(r['B8']['3'])}; 4 {f(r['B8']['4'])}; raw rim rate by category {r['B8']['raw_rim_rate_by_cat']}; n {r['B8']['n_by_cat']}.",
               f"- **By start type**: " + "; ".join(f"{k} {f(v)} (n {v['n']:,})" for k, v in r["by_start_type"].items()), "",
               "| time band | FIVE_BACK | n | rim rate |", "|---|---|---|---|"] + [f"| {b['band']} | {b['five_back']} | {b['n']:,} | {b['rim']:.3f} |" for b in r["bands"]] + [""]
    md += [f"## naive vs corrected: **{res['B9_classification']}**", "", f"## pre-specified criteria: {res['B10_criteria']}", "", f"## STATUS: **{res['status']}**"]
    (R / "audit").mkdir(exist_ok=True)
    (R / "audit" / "PRIMARY_RESULTS.md").write_text("\n".join(md) + "\n")
    md2 = ["# FIVE BACK — naive (0 s) vs corrected (+4.0 s), identical pipeline", "", "| quantity | naive | corrected |", "|---|---|---|",
           f"| n shots with pre-shot frame | {n['n_shots']:,} | {c['n_shots']:,} |", f"| FIVE_BACK share | {n['five_back_share']:.3f} | {c['five_back_share']:.3f} |",
           f"| MODEL T FIVE_BACK → rim | {f(n['model_T'])} | {f(c['model_T'])} |", f"| MODEL D FIVE_BACK → rim | {f(n['model_D'])} | {f(c['model_D'])} |",
           f"| early contrast time-only → combined | {n['B7']['time_only']['early_contrast_pp']:+.2f} → {n['B7']['combined']['early_contrast_pp']:+.2f} pp | {c['B7']['time_only']['early_contrast_pp']:+.2f} → {c['B7']['combined']['early_contrast_pp']:+.2f} pp |",
           f"| CV log-loss gain (nats) | {n['B7']['cv_logloss_gain_vs_time_only']:+.4f} | {c['B7']['cv_logloss_gain_vs_time_only']:+.4f} |",
           f"| dose ≤2 / 3 / 4 vs 5 | {f(n['B8']['le2'])} / {f(n['B8']['3'])} / {f(n['B8']['4'])} | {f(c['B8']['le2'])} / {f(c['B8']['3'])} / {f(c['B8']['4'])} |",
           "", f"Classification (pre-specified rule): **{res['B9_classification']}**"]
    (R / "audit" / "NAIVE_VS_CORRECTED.md").write_text("\n".join(md2) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
