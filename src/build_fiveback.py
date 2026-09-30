#!/usr/bin/env python3
"""FIVE BACK — build per-game possession starts, direction table, N_BACK trajectories and first-FGA shot rows at
lead 0.0 (naive) and 4.0 (corrected). Rules: configs/analysis_definitions.yaml.

Per game writes data/games/<game_id>.parquet (shot rows, one per eligible possession x lead), data/games/<game_id>_traj.parquet
(N_BACK per frame for the first 8 s of each eligible possession, corrected axis), data/games/<game_id>_meta.json (direction
table, exclusion counts). No basketball outcome is summarised here. CPU only; resume-safe.
"""
from __future__ import annotations
import os
import argparse, json, sys
from pathlib import Path
import numpy as np, pandas as pd, yaml

R = Path(__file__).resolve().parents[1]
from tracking_io import frames_from_events, load_game_json, parse_clock  # noqa: E402

CFG = yaml.safe_load((R / "configs" / "analysis_definitions.yaml").read_text())
JSON_DIR = Path(os.environ.get("FIVEBACK_SPORTVU_JSON", str(R / "data" / "external" / "sportvu" / "json")))
PBP = Path(os.environ.get("FIVEBACK_PBP", str(R / "data" / "external" / "pbp" / "2015-16" / "all.parquet")))
SHARED = R / "configs" / "game_universe.json"   # per-game ids/stems/quality label (metadata only)
LEAD_C, LEAD_N, MID, WIN = 4.0, 0.0, 47.0, 8.0
BASKET_X = {"R": 88.75, "L": 5.25}


def nearest_frame(clocks: np.ndarray, target: float):
    """index of the nearest clock within 0.06 s, else 0.20 s, else None (clocks sorted ascending)."""
    if len(clocks) == 0:
        return None
    j = np.searchsorted(clocks, target); cands = [k for k in (j - 1, j) if 0 <= k < len(clocks)]
    k = min(cands, key=lambda k: abs(clocks[k] - target)); d = abs(clocks[k] - target)
    return k if d <= 0.20 else None


def direction_table(df: pd.DataFrame, pbp: pd.DataFrame) -> tuple[dict, dict]:
    """Empirical basket side per (period, team) from ball x at frame nearest c+4.0 of MADE FGs; periods 1-2 pooled, >=3 opposite."""
    ball = df[df.player_id == -1]; byp = {int(p): g.sort_values("game_clock") for p, g in ball.groupby("period")}
    made = pbp[(pbp.actionType == "Made Shot") & (pbp.isFieldGoal.astype(int) == 1)]
    obs = {}   # (period, team) -> list of x
    for s in made.itertuples():
        g = byp.get(int(s.period))
        if g is None:
            continue
        k = nearest_frame(g.game_clock.values, float(s.c) + LEAD_C)
        if k is None:
            continue
        obs.setdefault((int(s.period), int(s.team)), []).append(float(g.x.values[k]))
    teams = sorted({t for (_, t) in obs})
    side = {}; diag = {"per_period": {}, "n_made_used": int(sum(len(v) for v in obs.values()))}
    for t in teams:
        h1 = [x for (p, tt), v in obs.items() if tt == t and p <= 2 for x in v]
        h2 = [x for (p, tt), v in obs.items() if tt == t and p >= 3 for x in v]
        if len(h1) >= 3:
            s1 = "R" if np.mean(np.array(h1) > MID) > 0.5 else "L"
        elif len(h2) >= 3:
            s1 = "L" if np.mean(np.array(h2) > MID) > 0.5 else "R"
        else:
            continue
        s2 = "L" if s1 == "R" else "R"
        for p in range(1, 9):
            side[(p, t)] = s1 if p <= 2 else s2
    # per-period majority agreement + within-10ft fraction
    agree = tot = near = 0
    for (p, t), v in obs.items():
        if (p, t) not in side or len(v) < 3:
            continue
        maj = "R" if np.mean(np.array(v) > MID) > 0.5 else "L"; tot += 1; agree += int(maj == side[(p, t)])
        near += int(np.mean(np.abs(np.array(v) - BASKET_X[side[(p, t)]]) <= 10.0) >= 0.5)
    diag["per_period_groups"] = tot; diag["per_period_agree"] = agree; diag["groups_ball_within_10ft_majority"] = near
    return side, diag


def game_build(gid: str, stem: str, pbp_g: pd.DataFrame, out: Path) -> dict:
    _, events, _ = load_game_json(JSON_DIR / f"{stem}.json"); df, _ = frames_from_events(events)
    pbp_g = pbp_g.sort_values("actionNumber", kind="stable").reset_index(drop=True).copy()
    pbp_g["c"] = pbp_g.clock.map(parse_clock); pbp_g["team"] = pd.to_numeric(pbp_g.teamId, errors="coerce").fillna(0).astype(int)
    pbp_g["pid"] = pd.to_numeric(pbp_g.personId, errors="coerce").fillna(0).astype(int)
    pbp_g[["scoreHome", "scoreAway"]] = pbp_g[["scoreHome", "scoreAway"]].ffill().fillna(0.0)
    side, ddiag = direction_table(df, pbp_g)
    players = df[df.player_id != -1]; byp_all = {int(p): g for p, g in players.groupby("period")}
    clocks_by_p = {p: np.sort(g.game_clock.unique()) for p, g in byp_all.items()}
    frame_cache = {}

    def frame(period: int, clk: float) -> pd.DataFrame:
        key = (period, clk)
        if key not in frame_cache:
            g = byp_all[period]; frame_cache[key] = g[g.game_clock == clk]
        return frame_cache[key]

    def n_back(period: int, clk: float, off_team: int, sd: str):
        f = frame(period, clk); d = f[(f.team_id != off_team) & (f.player_id > 0)]
        if d.player_id.nunique() != 5 or len(d) != 5:
            return None
        return int(((d.x > MID) if sd == "R" else (d.x < MID)).sum())

    # --- possession starts
    steal_an = set(pbp_g[pbp_g.actionType.isna() & pbp_g.description.str.contains("STEAL", na=False)].actionNumber)
    steal_team = pbp_g[pbp_g.actionType.isna() & pbp_g.description.str.contains("STEAL", na=False)].set_index("actionNumber").team.to_dict()
    typed = pbp_g[pbp_g.actionType.notna()].reset_index()   # 'index' = original row position
    excl = {"dead_ball_turnover": 0, "team_rebound": 0, "ft_miss_rebound": 0, "no_direction": 0, "next_event_not_fga": {}, "time_gt_24": 0, "shot_invalid": 0, "n_starts": 0}
    rows = []; traj = []
    for i, r in typed.iterrows():
        start_type = None; gain = None
        if r.actionType == "Turnover":
            if int(r.actionNumber) in steal_an:
                start_type = "LIVE_BALL_TURNOVER"; gain = int(steal_team[int(r.actionNumber)])
            else:
                excl["dead_ball_turnover"] += 1; continue
        elif r.actionType == "Rebound":
            if int(r.pid) <= 0:
                excl["team_rebound"] += 1; continue
            prev = typed.iloc[i - 1] if i > 0 else None
            if prev is None or prev.actionType != "Missed Shot" or int(prev.isFieldGoal) != 1 or int(prev.team) == int(r.team):
                if prev is not None and prev.actionType == "Free Throw":
                    excl["ft_miss_rebound"] += 1
                continue
            start_type = "DEFENSIVE_REBOUND"; gain = int(r.team)
        else:
            continue
        if gain == 0 or r.c is None or np.isnan(r.c):
            continue
        excl["n_starts"] += 1; per = int(r.period); c0 = float(r.c)
        sd = side.get((per, gain))
        if sd is None:
            excl["no_direction"] += 1; continue
        # next PBP row of any type after the start row (skipping only the paired STEAL row)
        pos = int(r["index"]); nxt = None
        for j in range(pos + 1, len(pbp_g)):
            rr = pbp_g.iloc[j]
            if pd.isna(rr.actionType) and int(rr.actionNumber) == int(r.actionNumber) and "STEAL" in str(rr.description):
                continue
            nxt = rr; break
        if nxt is None or pd.isna(nxt.actionType) or nxt.actionType not in ("Made Shot", "Missed Shot") or int(nxt.isFieldGoal) != 1 or int(nxt.team) != gain or int(nxt.period) != per:
            k = "none" if nxt is None else f"{nxt.actionType}" + ("" if (nxt is None or int(nxt.team) == gain) else "_opp")
            excl["next_event_not_fga"][k] = excl["next_event_not_fga"].get(k, 0) + 1; continue
        if int(nxt.pid) <= 0 or int(nxt.shotValue) not in (2, 3) or nxt.shotResult not in ("Made", "Missed") or nxt.c is None:
            excl["shot_invalid"] += 1; continue
        cs = float(nxt.c); tip = c0 - cs
        if tip < 0 or tip > 24.0:
            excl["time_gt_24"] += 1; continue
        # --- trajectory (corrected axis) for the construct validation
        clks = clocks_by_p.get(per, np.array([])); t_start = c0 + LEAD_C
        w = clks[(clks <= t_start) & (clks >= t_start - WIN)]
        for clk in w[::-1]:   # descending clock = forward in time
            nb = n_back(per, float(clk), gain, sd)
            if nb is not None:
                traj.append({"start_an": int(r.actionNumber), "t_since_start": round(t_start - float(clk), 2), "n_back": nb})
        # --- shot rows at both leads
        home = str(nxt.location).strip() == "h"
        post = (nxt.scoreHome - nxt.scoreAway) if home else (nxt.scoreAway - nxt.scoreHome)
        margin = float(post) - (int(nxt.shotValue) if nxt.shotResult == "Made" else 0)
        base = {"game_id": gid, "period": per, "start_an": int(r.actionNumber), "start_type": start_type, "start_clock": c0, "shot_an": int(nxt.actionNumber), "shot_clock": cs,
                "time_into_possession": tip, "team": gain, "shooter": int(nxt.pid), "shot_distance_ft": float(nxt.shotDistance), "shot_value": int(nxt.shotValue), "made": int(nxt.shotResult == "Made"),
                "sub_type": nxt.subType, "score_margin": margin, "attack_side": sd, "possession_lasts_8s": int(tip >= 8.0)}
        for lead, tag in ((LEAD_N, "naive"), (LEAD_C, "corrected")):
            rec = dict(base); rec["lead_s"] = lead; rec["axis"] = tag
            k = nearest_frame(clks, cs + lead + 1.0)
            rec["n_back"] = np.nan; rec["defender_dist_ft"] = np.nan; rec["frame_offset_s"] = np.nan
            if k is not None:
                clk = float(clks[k]); nb = n_back(per, clk, gain, sd); rec["frame_offset_s"] = clk - (cs + lead + 1.0)
                if nb is not None:
                    rec["n_back"] = nb
                    f = frame(per, clk); me = f[f.player_id == int(nxt.pid)]; d = f[(f.team_id != gain) & (f.player_id > 0)]
                    if len(me) == 1 and len(d) == 5:
                        rec["defender_dist_ft"] = float(np.sqrt((d.x.values - me.x.values[0]) ** 2 + (d.y.values - me.y.values[0]) ** 2).min())
            rows.append(rec)
    pd.DataFrame(rows).to_parquet(out / f"{gid}.parquet", index=False); pd.DataFrame(traj).to_parquet(out / f"{gid}_traj.parquet", index=False)
    meta = {"game_id": gid, "stem": stem, "direction": {f"{p}|{t}": s for (p, t), s in side.items()}, "direction_diag": ddiag, "exclusions": excl, "n_shot_rows": len(rows) // 2}
    (out / f"{gid}_meta.json").write_text(json.dumps(meta, indent=1)); return meta


def _job(args):
    gid, stem, pbp_g, out = args
    try:
        return gid, game_build(gid, stem, pbp_g, Path(out))["n_shot_rows"], ""
    except Exception as e:  # noqa: BLE001
        return gid, -1, repr(e)


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=16); ap.add_argument("--limit", type=int, default=0); a = ap.parse_args()
    al = pd.DataFrame(json.load(open(SHARED))["games"]); al = al[al.lead_status != "NO_TRACKING_MOMENTS"]
    games = al.game_id.tolist()[: a.limit or None]; stems = al.set_index("game_id").stem.to_dict()
    pbp = pd.read_parquet(PBP); pbp["gameId"] = pbp.gameId.astype(str).str.zfill(10)
    out = R / "data" / "games"; out.mkdir(parents=True, exist_ok=True)
    todo = [g for g in games if not (out / f"{g}_meta.json").exists()]
    from concurrent.futures import ProcessPoolExecutor, as_completed
    fails = []
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(_job, (g, stems[g], pbp[pbp.gameId == g], str(out))) for g in todo]
        for i, fu in enumerate(as_completed(futs)):
            gid, n, err = fu.result(); print(f"[{i + 1}/{len(todo)}] {gid} shots {n} {err}", flush=True)
            if n < 0:
                fails.append((gid, err))
    print("BUILD_DONE", len(games), "failed", len(fails)); (R / "data" / "build_failures.json").write_text(json.dumps(fails, indent=1)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
