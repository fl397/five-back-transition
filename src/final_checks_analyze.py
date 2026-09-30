#!/usr/bin/env python3
"""FIVE BACK — robustness checks, analysis (configs/final_adversarial_checks.yaml).
Stage 'gate'   : regeneration comparison — compare a scratch re-run of the unchanged analyze_fiveback / validate_nback outputs to the shipped results.
Stage 'checks' : Check 1 (within-time common support), Check 2 (frontcourt entry FC1/FC2), Check 3 (first-FGA selection), summary.
Reuses design/fit/rcs_basis/cv_logloss from analyze_fiveback.py unchanged. Writes results/check{1,2,3}_*.{csv,json}, audit/CHECK*.md, audit/CHECK_SUMMARY.md.
"""
from __future__ import annotations
import os
import argparse, glob, json, sys
from pathlib import Path
import numpy as np, pandas as pd, statsmodels.api as sm

R = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(R / "src"))
from build_fiveback import PBP  # noqa: E402
from analyze_fiveback import design, fit, coef, rcs_basis, cv_logloss  # noqa: E402
FREEZE_SHA = "f029d0b"
BINS = [("4-5", 4.0, 5.0, False), ("5-6", 5.0, 6.0, False), ("6-7", 6.0, 7.0, False), ("7-8", 7.0, 8.0, False), ("8-10", 8.0, 10.0, True)]


def walk(d: dict, path=""):
    for k, v in d.items():
        p = f"{path}/{k}"
        if isinstance(v, dict):
            yield from walk(v, p)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            yield p, float(v)


def stage_gate(scratch: Path) -> int:
    out = {}
    for name in ("fiveback_results.json", "nback_validation.json"):
        a = json.loads((R / "results" / name).read_text()); b = json.loads((scratch / "results" / name).read_text())
        da, db = dict(walk(a)), dict(walk(b)); keys = sorted(set(da) | set(db)); diffs = {k: abs(da.get(k, np.nan) - db.get(k, np.nan)) for k in keys}
        bad = {k: v for k, v in diffs.items() if not (v <= 1e-6)}
        out[name] = {"n_numeric_fields": len(keys), "max_abs_diff": float(np.nanmax(list(diffs.values()))), "n_fields_over_1e-6_or_missing": len(bad), "examples": dict(list(bad.items())[:10])}
    # meta byte-identity
    import hashlib
    mism = []
    for f in sorted((R / "data" / "games_committed_meta").glob("*_meta.json")):
        g = R / "data" / "games" / f.name
        if not g.exists() or hashlib.sha256(f.read_bytes()).hexdigest() != hashlib.sha256(g.read_bytes()).hexdigest():
            mism.append(f.name)
    out["meta_json_byte_identity"] = {"n_committed": len(list((R / "data" / "games_committed_meta").glob("*_meta.json"))), "n_mismatch": len(mism), "examples": mism[:10]}
    out["pass"] = bool(all(v["n_fields_over_1e-6_or_missing"] == 0 for k, v in out.items() if k.endswith(".json")) and len(mism) == 0)
    (R / "results" / "reproduction_gate.json").write_text(json.dumps(out, indent=2)); print(json.dumps(out, indent=1)); return 0 if out["pass"] else 1


def bin_of(t):
    for name, lo, hi, closed in BINS:
        if (lo <= t < hi) or (closed and lo <= t <= hi):
            return name
    return None


def stage_checks() -> int:
    d = pd.read_parquet(R / "data" / "shots_fiveback_corrected.parquet"); d["rim"] = (d.shot_distance_ft <= 4).astype(int)
    d = d[d.n_back.notna()].copy(); d["five_back"] = (d.n_back == 5).astype(int); assert len(d) == 32153, len(d)
    res = {"freeze_sha": FREEZE_SHA, "n_primary_sample": int(len(d))}
    # ---------------- Check 1
    d["bin"] = d.time_into_possession.map(bin_of); u = d[d.bin.notna()].copy(); rows = []
    for name, *_ in BINS:
        s = u[u.bin == name]; n0, n1 = int((s.five_back == 0).sum()), int((s.five_back == 1).sum())
        r0 = float(s[s.five_back == 0].rim.mean()) if n0 else np.nan; r1 = float(s[s.five_back == 1].rim.mean()) if n1 else np.nan
        if n0 >= 2 and n1 >= 2:
            m = fit(s.rim.values.astype(float), pd.DataFrame({"five_back": s.five_back.values.astype(float)}, index=s.index), s.game_id.values); c = coef(m, "five_back")
        else:
            c = {"beta_pp": np.nan, "ci95_pp": [np.nan, np.nan]}
        rows.append({"bin": name, "N": n0 + n1, "N0": n0, "N1": n1, "frac_five_back": n1 / max(n0 + n1, 1), "rim_rate_0": r0, "rim_rate_1": r1, "raw_diff_pp": 100 * (r1 - r0) if n0 and n1 else np.nan,
                     "diff_ci95_low_pp": c["ci95_pp"][0], "diff_ci95_high_pp": c["ci95_pp"][1], "min_N0_N1": min(n0, n1), "overlap_frac": 2 * min(n0, n1) / max(n0 + n1, 1)})
    c1 = pd.DataFrame(rows); c1.to_csv(R / "results" / "check1_common_support.csv", index=False)
    X = design(u, [0, 1, 2], time=False, five=True)   # knots unused (time=False)
    for name, *_ in BINS[1:]:
        X[f"bin_{name}"] = (u.bin == name).astype(float).values
    ms = fit(u.rim.values.astype(float), X, u.game_id.values); strat = coef(ms, "five_back") | {"n": int(len(u)), "n_games": int(u.game_id.nunique()), "r2": float(ms.rsquared)}
    central = c1[c1.bin.isin(["5-6", "6-7", "7-8"])]
    res["check1"] = {"bins": rows, "stratified_model": strat, "central_bins_min_N0_N1": central.min_N0_N1.tolist(), "central_bins_overlap": central.overlap_frac.round(3).tolist()}
    # ---------------- Check 2
    e = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(str(R / "data" / "checks" / "*_entry.parquet")))], ignore_index=True)
    de = d.merge(e, on=["game_id", "start_an", "shot_an"], how="left", suffixes=("", "_e"))
    flags = de.entry_flag.fillna("NO_ENTRY_ROW").value_counts().to_dict()
    fc = de[de.entry_flag.isin(["ENTRY", "ALREADY_IN_FRONTCOURT"]) & de.tsfe_s.notna()].copy()
    ent = de[de.entry_flag.isin(["ENTRY", "ALREADY_IN_FRONTCOURT"])]
    kn = [float(np.percentile(fc.tsfe_s, q)) for q in (10, 50, 90)]
    if len(set(kn)) < 3:
        kn = sorted(set(kn)); kn = [kn[0], float(np.median(fc.tsfe_s)), kn[-1]] if len(kn) == 2 else kn
    def fc_design(dd, five):
        Xf = design(dd, [0, 1, 2], time=False, five=five); Xf["tsfe"] = dd.tsfe_s.values; Xf["tsfe_rcs1"] = rcs_basis(dd.tsfe_s.values, kn)[:, 0]; return Xf
    y = fc.rim.values.astype(float); g = fc.game_id.values
    X1, X2 = fc_design(fc, False), fc_design(fc, True); m1, m2 = fit(y, X1, g), fit(y, X2, g)
    fc["tsfe_band"] = pd.cut(fc.tsfe_s, [-0.01, 1, 2, 3, 4, 6, 8, 24], labels=["0-1", "1-2", "2-3", "3-4", "4-6", "6-8", "8+"])
    res["check2"] = {"n_primary": int(len(de)), "entry_flags": flags, "pct_valid_entry": float(len(ent) / len(de)), "pct_already_in_frontcourt": float((de.entry_flag == "ALREADY_IN_FRONTCOURT").mean()),
                     "entry_time_median_s": float(ent.entry_time_s.median()), "entry_time_iqr_s": [float(ent.entry_time_s.quantile(.25)), float(ent.entry_time_s.quantile(.75))],
                     "returns_to_backcourt_frac": float((ent.n_returns_to_backcourt >= 1).mean()), "missing_ball_frames_frac": float((de.entry_flag == "NO_BALL_FRAMES").mean()),
                     "n_fc_sample": int(len(fc)), "knots_tsfe_p10_p50_p90": kn,
                     "FC1": {"r2": float(m1.rsquared), "cv_logloss": cv_logloss(y, X1, g)}, "FC2": coef(m2, "five_back") | {"r2": float(m2.rsquared), "cv_logloss": cv_logloss(y, X2, g)},
                     "corr_time_into_possession_entry_time": float(np.corrcoef(ent.time_into_possession, ent.entry_time_s)[0, 1]),
                     "corr_entry_time_five_back": float(np.corrcoef(ent.entry_time_s, ent.five_back)[0, 1]), "corr_tsfe_five_back": float(np.corrcoef(fc.tsfe_s, fc.five_back)[0, 1]),
                     "five_back_share_by_tsfe_band": fc.groupby("tsfe_band", observed=True).agg(n=("rim", "size"), five_back=("five_back", "mean"), rim=("rim", "mean")).round(4).reset_index().to_dict("records")}
    res["check2"]["cv_gain_FC2_vs_FC1"] = res["check2"]["FC1"]["cv_logloss"] - res["check2"]["FC2"]["cv_logloss"]
    # ---------------- Check 3
    s = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(str(R / "data" / "checks" / "*_starts.parquet")))], ignore_index=True)
    tax = s.category.value_counts(); tax_rows = [{"category": k, "n": int(v), "pct": 100 * v / len(s)} for k, v in tax.items()]
    pd.DataFrame(tax_rows).to_csv(R / "results" / "check3_selection.csv", index=False)
    alive = s[(s.alive_at_6s == 1)].copy(); alive["five6"] = (alive.n_back_6s == 5).astype(float).where(alive.n_back_6s.notna()); alive["enters"] = (alive.category == "FIRST_FGA_OBSERVED").astype(float)
    a = alive[alive.five6.notna()].copy()
    def sel_block(x):
        n0, n1 = int((x.five6 == 0).sum()), int((x.five6 == 1).sum()); p0 = float(x[x.five6 == 0].enters.mean()) if n0 else np.nan; p1 = float(x[x.five6 == 1].enters.mean()) if n1 else np.nan
        if n0 >= 2 and n1 >= 2:
            m = fit(x.enters.values, pd.DataFrame({"five6": x.five6.values}, index=x.index), x.game_id.values); c = coef(m, "five6")
        else:
            c = {"beta_pp": np.nan, "ci95_pp": [np.nan, np.nan]}
        return {"n0": n0, "n1": n1, "p_enter_five_back_0": p0, "p_enter_five_back_1": p1, "diff_pp": c["beta_pp"], "diff_ci95_pp": c["ci95_pp"]}
    sel = {"n_starts_universe": int(len(s)), "n_alive_at_6s": int(len(alive)), "n_alive_with_nback6": int(len(a)), "n_back_6s_dist": a.n_back_6s.value_counts(normalize=True).sort_index().round(4).to_dict(),
           "overall": sel_block(a), "by_start_type": {k: sel_block(x) for k, x in a.groupby("start_type")},
           "by_period": {k: sel_block(x) for k, x in a.groupby(np.where(a.period <= 2, "P1-2", "P3+"))},
           "category_by_five6": pd.crosstab(a.five6, a.category, normalize="index").round(4).to_dict()}
    # margin band: need running score -> derive from PBP once
    pbp = pd.read_parquet(PBP, columns=["gameId", "actionNumber", "teamId", "location", "scoreHome", "scoreAway"])
    pbp["gameId"] = pbp.gameId.astype(str).str.zfill(10); pbp = pbp[pbp.gameId.isin(a.game_id.unique())].sort_values(["gameId", "actionNumber"])
    pbp[["scoreHome", "scoreAway"]] = pbp.groupby("gameId")[["scoreHome", "scoreAway"]].ffill().fillna(0.0)
    home_team = pbp[pbp.location.astype(str).str.strip() == "h"].groupby("gameId").teamId.agg(lambda x: pd.to_numeric(x, errors="coerce").dropna().mode().iloc[0]).astype(int).to_dict()
    sc = pbp.drop_duplicates(["gameId", "actionNumber"], keep="last").set_index(["gameId", "actionNumber"])[["scoreHome", "scoreAway"]]
    a = a.join(sc, on=["game_id", "start_an"]); a["is_home"] = a.team == a.game_id.map(home_team)
    a["margin"] = np.where(a.is_home, a.scoreHome - a.scoreAway, a.scoreAway - a.scoreHome)
    a["mband"] = np.where(a.margin <= -6, "trailing<=-6", np.where(a.margin >= 6, "leading>=6", "within5"))
    sel["by_margin_band"] = {k: sel_block(x) for k, x in a.groupby("mband")}
    res["check3"] = {"taxonomy": tax_rows, "selection": sel}
    (R / "results" / "check3_selection.json").write_text(json.dumps(res["check3"], indent=2, default=float))
    (R / "results" / "check1_common_support.json").write_text(json.dumps(res["check1"], indent=2, default=float))
    (R / "results" / "check2_frontcourt_entry.json").write_text(json.dumps(res["check2"], indent=2, default=float))
    (R / "results" / "final_checks_results.json").write_text(json.dumps(res, indent=2, default=float))
    print(json.dumps({"check1_strat": strat, "central": res["check1"]["central_bins_overlap"], "check2_FC2": res["check2"]["FC2"], "cv_gain": res["check2"]["cv_gain_FC2_vs_FC1"], "check3": sel["overall"]}, indent=1, default=float))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--stage", choices=["gate", "checks"], required=True); ap.add_argument("--scratch", default=""); a = ap.parse_args()
    raise SystemExit(stage_gate(Path(a.scratch)) if a.stage == "gate" else stage_checks())
