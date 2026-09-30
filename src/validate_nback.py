#!/usr/bin/env python3
"""FIVE BACK — N_BACK construct validation (read BEFORE any shot outcome). Rules/thresholds: configs/analysis_definitions.yaml.
Reads data/games/*_traj.parquet, *_meta.json; the court-direction reference table (read-only). Writes results/nback_validation.json,
audit/NBACK_VALIDATION.md. No outcome column (shot distance / made / rim) is read here.
"""
from __future__ import annotations
import glob, json
from pathlib import Path
import numpy as np, pandas as pd

R = Path(__file__).resolve().parents[1]
DIRECTION_REF = R / "data" / "reference" / "court_direction_reference.json"   # independent (game, period, team) basket-side table


def main() -> int:
    metas = [json.load(open(f)) for f in sorted(glob.glob(str(R / "data" / "games" / "*_meta.json")))]
    # direction agreement with the court-direction reference table
    sc = pd.DataFrame(json.load(open(DIRECTION_REF))["rows"]); sc["game_id"] = sc.game_id.astype(str); ours = []
    for m in metas:
        for k, s in m["direction"].items():
            p, t = k.split("|"); ours.append({"game_id": m["game_id"], "period": int(p), "offense_team_id": int(t), "side_ours": s})
    ours = pd.DataFrame(ours); j = sc.merge(ours, on=["game_id", "period", "offense_team_id"]); j = j[j.basket_side.isin(["L", "R"])]
    dir_agree = float((j.basket_side == j.side_ours).mean()); n_dir = int(len(j))
    pp_groups = sum(m["direction_diag"]["per_period_groups"] for m in metas); pp_agree = sum(m["direction_diag"]["per_period_agree"] for m in metas)
    excl = {}
    for m in metas:
        for k, v in m["exclusions"].items():
            if isinstance(v, dict):
                for kk, vv in v.items():
                    excl[f"next_event_not_fga:{kk}"] = excl.get(f"next_event_not_fga:{kk}", 0) + vv
            else:
                excl[k] = excl.get(k, 0) + v
    # trajectories
    T = pd.concat([pd.read_parquet(f).assign(game_id=Path(f).name.split("_")[0]) for f in sorted(glob.glob(str(R / "data" / "games" / "*_traj.parquet")))], ignore_index=True)
    T["key"] = T.game_id + "|" + T.start_an.astype(str)
    start = T[T.t_since_start <= 0.05].groupby("key").n_back.first()
    dist_start = start.value_counts(normalize=True).sort_index().round(4).to_dict()
    first5 = T[T.n_back == 5].groupby("key").t_since_start.min()
    keys = T.key.unique(); n_poss = len(keys); reach = first5.reindex(keys)
    span = T.groupby("key").t_since_start.max(); full = span[span >= 7.5].index   # possessions with tracking through 8 s
    reach_full = reach.reindex(full)
    by = {s: float((reach_full <= s).mean()) for s in (2, 4, 6, 8)}
    never8 = float(reach_full.isna().mean())
    # monotonicity: after first reaching 5, any later frame < 5 within window
    viol = 0
    for k, g in T.groupby("key"):
        f5 = first5.get(k)
        if f5 is None or np.isnan(f5):
            continue
        viol += int((g[g.t_since_start > f5].n_back < 5).any())
    viol_rate = viol / max(int(first5.shape[0]), 1)
    mean_curve = T.groupby(T.t_since_start.round(1)).n_back.mean().round(3)
    out = {"n_games": len(metas), "n_starts_total": excl.get("n_starts", 0), "n_eligible_possessions": n_poss, "exclusions": excl,
           "direction": {"screen_audit_overlap_groups": n_dir, "agreement_with_screen_audit": dir_agree, "per_period_groups": pp_groups, "per_period_majority_agreement": pp_agree / max(pp_groups, 1),
                         "groups_ball_within_10ft_majority_share": sum(m["direction_diag"]["groups_ball_within_10ft_majority"] for m in metas) / max(pp_groups, 1)},
           "n_back_at_start_distribution": dist_start, "median_time_to_five_s": float(first5.median()), "p25_p75_time_to_five_s": [float(first5.quantile(.25)), float(first5.quantile(.75))],
           "possessions_with_8s_tracking": int(len(full)), "p_five_back_by_s": by, "never_reach_5_within_8s_among_8s_possessions": never8,
           "monotonicity_violation_rate": viol_rate, "mean_n_back_curve": {str(k): float(v) for k, v in mean_curve.items()}}
    stop = (dir_agree < 0.90) or (out["direction"]["per_period_majority_agreement"] < 0.90) or (never8 > 0.15) or (viol_rate > 0.25)
    out["decision"] = "STOP" if stop else "PASS"
    (R / "results" / "nback_validation.json").write_text(json.dumps(out, indent=2))
    md = ["# FIVE BACK — N_BACK construct validation (decided BEFORE any shot outcome)", "",
          f"Producer `src/validate_nback.py`. Games {len(metas)}; primary starts found {excl.get('n_starts', 0):,}; eligible possessions (first FGA with no intervening event, ≤ 24 s) **{n_poss:,}**.", "",
          "## Exclusions (counts)", "", "| reason | n |", "|---|---|"] + [f"| {k} | {v:,} |" for k, v in sorted(excl.items(), key=lambda x: -x[1]) if k != "n_starts"] + [
          "", "## Direction (deterministic checks)", "",
          f"- Agreement with the court-direction reference table on {n_dir:,} overlapping (game, period, team) groups: **{dir_agree:.4f}** (threshold 0.90).",
          f"- Per-period majority agreement with the pooled half rule: **{pp_agree / max(pp_groups, 1):.4f}** over {pp_groups:,} groups (threshold 0.90).",
          f"- Groups where the majority of made-FG ball positions at c + 4.0 lie within 10 ft of the inferred basket: {out['direction']['groups_ball_within_10ft_majority_share']:.3f} (informational: the +4 s instant precedes release by ~1 s, so jump shots are farther than 10 ft).", "",
          "## N_BACK trajectories (corrected axis, first 8 s)", "",
          f"- N_BACK at possession start: " + ", ".join(f"{k}: {v:.3f}" for k, v in dist_start.items()),
          f"- Median time to five back: **{out['median_time_to_five_s']:.2f} s** (IQR {out['p25_p75_time_to_five_s'][0]:.2f}–{out['p25_p75_time_to_five_s'][1]:.2f}).",
          f"- Among {len(full):,} possessions tracked through 8 s: P(five back by 2/4/6/8 s) = {by[2]:.3f} / {by[4]:.3f} / {by[6]:.3f} / {by[8]:.3f}; never within 8 s: {never8:.3f} (threshold 0.15).",
          f"- Monotonicity violations (N_BACK drops below 5 after first reaching 5 inside the window): **{viol_rate:.3f}** of possessions that reach 5 (threshold 0.25).", "",
          "Mean N_BACK by time since start (s): " + ", ".join(f"{k}: {v:.2f}" for k, v in list(out["mean_n_back_curve"].items())[::5]), "",
          f"## Decision: **{out['decision']}**"]
    (R / "audit").mkdir(exist_ok=True)
    (R / "audit" / "NBACK_VALIDATION.md").write_text("\n".join(md) + "\n"); print(json.dumps({k: v for k, v in out.items() if k != "mean_n_back_curve"}, indent=1)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
