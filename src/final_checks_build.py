#!/usr/bin/env python3
"""FIVE BACK — robustness checks, per-game builder (configs/final_adversarial_checks.yaml).

For every game: (Check 3) classify ALL primary eligible starts by the first PBP row after the start row and, for starts alive at
6.0 s, N_BACK at 6.0 s on the corrected axis; (Check 2) for first-FGA possessions, the ball frontcourt-entry time on the corrected
axis (first frame with the ball on the offensive side of x = 47), back-and-forth count, and flags.  The primary rules are reused verbatim
from src/build_fiveback.py (start typing, direction table, N_BACK, nearest-frame rule).  No basketball outcome is summarised here.
Writes data/checks/<game_id>_starts.parquet and data/checks/<game_id>_entry.parquet.  CPU only; resume-safe.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np, pandas as pd

R = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(R / "src"))
from build_fiveback import (JSON_DIR, PBP, SHARED, LEAD_C, MID, nearest_frame, direction_table,  # noqa: E402
                            frames_from_events, load_game_json, parse_clock)

SHOOTING_FOUL = {"Shooting", "Shooting Block", "Flagrant Type 1", "Flagrant Type 2", "Clear Path"}
DEAD_TYPES = {"Foul", "Violation", "Timeout", "Substitution", "Instant Replay", "Jump Ball", "Ejection"}
EVAL_T = 6.0


def game_checks(gid: str, stem: str, pbp_g: pd.DataFrame, out: Path) -> dict:
    _, events, _ = load_game_json(JSON_DIR / f"{stem}.json"); df, _ = frames_from_events(events)
    pbp_g = pbp_g.sort_values("actionNumber", kind="stable").reset_index(drop=True).copy()
    pbp_g["c"] = pbp_g.clock.map(parse_clock); pbp_g["team"] = pd.to_numeric(pbp_g.teamId, errors="coerce").fillna(0).astype(int)
    pbp_g["pid"] = pd.to_numeric(pbp_g.personId, errors="coerce").fillna(0).astype(int)
    side, _ = direction_table(df, pbp_g)
    players = df[df.player_id != -1]; byp_all = {int(p): g for p, g in players.groupby("period")}
    clocks_by_p = {p: np.sort(g.game_clock.unique()) for p, g in byp_all.items()}
    ball = df[df.player_id == -1]; ball_by_p = {int(p): g.sort_values("game_clock") for p, g in ball.groupby("period")}

    def n_back(period: int, clk: float, off_team: int, sd: str):
        g = byp_all.get(period)
        if g is None:
            return None
        f = g[g.game_clock == clk]; d = f[(f.team_id != off_team) & (f.player_id > 0)]
        if d.player_id.nunique() != 5 or len(d) != 5:
            return None
        return int(((d.x > MID) if sd == "R" else (d.x < MID)).sum())

    steal_rows = pbp_g[pbp_g.actionType.isna() & pbp_g.description.str.contains("STEAL", na=False)]
    steal_an = set(steal_rows.actionNumber); steal_team = steal_rows.set_index("actionNumber").team.to_dict()
    typed = pbp_g[pbp_g.actionType.notna()].reset_index()
    starts, entries = [], []
    for i, r in typed.iterrows():
        start_type = None; gain = None
        if r.actionType == "Turnover":
            if int(r.actionNumber) not in steal_an:
                continue
            start_type = "LIVE_BALL_TURNOVER"; gain = int(steal_team[int(r.actionNumber)])
        elif r.actionType == "Rebound":
            if int(r.pid) <= 0:
                continue
            prev = typed.iloc[i - 1] if i > 0 else None
            if prev is None or prev.actionType != "Missed Shot" or int(prev.isFieldGoal) != 1 or int(prev.team) == int(r.team):
                continue
            start_type = "DEFENSIVE_REBOUND"; gain = int(r.team)
        else:
            continue
        if gain == 0 or r.c is None or np.isnan(r.c):
            continue          # the primary builder does not count these as starts either
        per = int(r.period); c0 = float(r.c); sd = side.get((per, gain))
        rec = {"game_id": gid, "period": per, "start_an": int(r.actionNumber), "start_type": start_type, "start_clock": c0, "team": gain}
        pos = int(r["index"]); nxt = None
        for j in range(pos + 1, len(pbp_g)):
            rr = pbp_g.iloc[j]
            if pd.isna(rr.actionType) and int(rr.actionNumber) == int(r.actionNumber) and "STEAL" in str(rr.description):
                continue
            nxt = rr; break
        # --- Check 3 taxonomy (pre-specified order)
        if sd is None or per not in clocks_by_p:
            cat = "TRACKING_OR_LINKAGE_MISSING"
        elif nxt is None or pd.isna(nxt.actionType) or nxt.actionType == "period":
            cat = "POSSESSION_END_OR_CONTROL_CHANGE_WITHOUT_FGA"
        elif nxt.actionType in ("Made Shot", "Missed Shot") and int(nxt.isFieldGoal) == 1 and int(nxt.team) == gain:
            tip = c0 - float(nxt.c) if nxt.c is not None and not np.isnan(nxt.c) else np.nan
            ok = int(nxt.period) == per and 0 <= tip <= 24.0 and int(nxt.pid) > 0 and int(nxt.shotValue) in (2, 3) and nxt.shotResult in ("Made", "Missed")
            cat = "FIRST_FGA_OBSERVED" if ok else "OTHER_RESOLVED"
        elif nxt.actionType == "Turnover" and int(nxt.team) == gain:
            cat = "TURNOVER_BEFORE_FGA"
        elif nxt.actionType == "Free Throw" or (nxt.actionType == "Foul" and int(nxt.team) != gain and str(nxt.subType) in SHOOTING_FOUL):
            cat = "SHOOTING_FOUL_OR_FREE_THROWS_BEFORE_FGA"
        elif nxt.actionType in DEAD_TYPES:
            cat = "NONSHOOTING_FOUL_OR_DEAD_BALL_BEFORE_FGA"
        elif nxt.actionType in ("Made Shot", "Missed Shot", "Rebound", "Turnover") and int(nxt.team) != gain:
            cat = "POSSESSION_END_OR_CONTROL_CHANGE_WITHOUT_FGA"
        else:
            cat = "UNRESOLVED"
        rec["category"] = cat; rec["next_type"] = None if nxt is None else str(nxt.actionType); rec["next_subtype"] = None if nxt is None else str(nxt.subType)
        rec["next_dt_s"] = np.nan if (nxt is None or nxt.c is None or np.isnan(nxt.c) or int(nxt.period) != per) else c0 - float(nxt.c)
        # alive at 6 s
        alive = bool(nxt is not None and not np.isnan(rec["next_dt_s"]) and rec["next_dt_s"] >= EVAL_T)
        rec["alive_at_6s"] = int(alive); rec["n_back_6s"] = np.nan; rec["frame_offset_6s"] = np.nan
        if alive and sd is not None and per in clocks_by_p:
            clks = clocks_by_p[per]; k = nearest_frame(clks, c0 + LEAD_C - EVAL_T)
            if k is not None:
                nb = n_back(per, float(clks[k]), gain, sd); rec["frame_offset_6s"] = float(clks[k]) - (c0 + LEAD_C - EVAL_T)
                if nb is not None:
                    rec["n_back_6s"] = nb
        starts.append(rec)
        # --- Check 2 frontcourt entry for FIRST_FGA_OBSERVED
        if cat == "FIRST_FGA_OBSERVED":
            cs = float(nxt.c); t_start = c0 + LEAD_C; t_shot = cs + LEAD_C
            b = ball_by_p.get(per); e = {"game_id": gid, "start_an": int(r.actionNumber), "shot_an": int(nxt.actionNumber), "attack_side": sd, "entry_time_s": np.nan, "entry_flag": "NO_BALL_FRAMES", "n_returns_to_backcourt": np.nan, "n_ball_frames": 0}
            if b is not None:
                w = b[(b.game_clock <= t_start) & (b.game_clock >= t_shot)].sort_values("game_clock", ascending=False)   # forward in time
                e["n_ball_frames"] = int(len(w))
                if len(w):
                    front = (w.x.values > MID) if sd == "R" else (w.x.values < MID)
                    idx = np.argmax(front) if front.any() else None
                    if idx is None:
                        e["entry_flag"] = "NO_ENTRY_BEFORE_SHOT"
                    else:
                        e["entry_time_s"] = float(t_start - w.game_clock.values[idx]); e["entry_flag"] = "ALREADY_IN_FRONTCOURT" if idx == 0 else "ENTRY"
                        after = front[idx:]; e["n_returns_to_backcourt"] = int(np.sum((~after[1:]) & after[:-1]))
            e["tsfe_s"] = float((t_start - e["entry_time_s"]) - t_shot) if not np.isnan(e["entry_time_s"]) else np.nan
            entries.append(e)
    pd.DataFrame(starts).to_parquet(out / f"{gid}_starts.parquet", index=False); pd.DataFrame(entries).to_parquet(out / f"{gid}_entry.parquet", index=False)
    return {"game_id": gid, "n_starts": len(starts), "n_first_fga": len(entries)}


def _job(args):
    gid, stem, pbp_g, out = args
    try:
        return gid, game_checks(gid, stem, pbp_g, Path(out)), ""
    except Exception as e:  # noqa: BLE001
        return gid, None, repr(e)


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=16); ap.add_argument("--limit", type=int, default=0); a = ap.parse_args()
    al = pd.DataFrame(json.load(open(SHARED))["games"]); al = al[al.lead_status != "NO_TRACKING_MOMENTS"]
    games = al.game_id.tolist()[: a.limit or None]; stems = al.set_index("game_id").stem.to_dict()
    pbp = pd.read_parquet(PBP); pbp["gameId"] = pbp.gameId.astype(str).str.zfill(10)
    out = R / "data" / "checks"; out.mkdir(parents=True, exist_ok=True)
    todo = [g for g in games if not (out / f"{g}_entry.parquet").exists()]
    from concurrent.futures import ProcessPoolExecutor, as_completed
    fails = []
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(_job, (g, stems[g], pbp[pbp.gameId == g], str(out))) for g in todo]
        for i, fu in enumerate(as_completed(futs)):
            gid, meta, err = fu.result(); print(f"[{i + 1}/{len(todo)}] {gid} {meta} {err}", flush=True)
            if meta is None:
                fails.append((gid, err))
    print("CHECKS_BUILD_DONE", len(games), "failed", len(fails)); (out / "build_failures.json").write_text(json.dumps(fails, indent=1)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
