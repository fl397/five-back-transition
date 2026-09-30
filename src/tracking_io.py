"""tracking_io — minimal SportVU/PBP readers inlined from the alignment toolkit (clock_latency_calibration.py)
so this repository is self-contained.  Sign convention: tracking_clock = pbp_clock + lead (lead > 0 <=> the
play-by-play stamp lags the tracking clock).  Dedup key (period, game_clock, player_id) keep-first, as in the source method.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd

LOOKBACK_S = 2.0
MIN_FRAMES = 5
BALL_ID = -1


def tracking_clock_target(pbp_clock: float, lead: float) -> float:
    """The sign convention used throughout: tracking clock (s remaining) matching a PBP event clock."""
    return pbp_clock + lead

def parse_clock(s: str) -> float | None:
    m = re.match(r"PT(\d+)M([\d.]+)S", str(s))
    return float(m.group(1)) * 60 + float(m.group(2)) if m else None

def load_game_json(path: Path) -> tuple[str, list, dict]:
    g = json.loads(path.read_text())
    return str(g["gameid"]), g["events"], g

def frames_from_events(events: list) -> tuple[pd.DataFrame, dict]:
    """Source parse: every moment row (team, player, x, y, z) with period/game_clock; dedup keep-first."""
    per, gc, sc, tid, pid, xs, ys, zs, evid = [], [], [], [], [], [], [], [], []
    n_containers = len(events); n_moments_raw = 0
    for ev in events:
        eid = ev.get("eventId")
        for m in ev.get("moments") or []:
            period, _utc, g, s = m[0], m[1], m[2], m[3]
            if g is None:
                continue
            n_moments_raw += 1
            for t, p, x, y, z in m[5]:
                per.append(period); gc.append(g); sc.append(s); tid.append(t); pid.append(p); xs.append(x); ys.append(y); zs.append(z); evid.append(eid)
    df = pd.DataFrame({"period": per, "game_clock": gc, "shot_clock": sc, "team_id": tid, "player_id": pid, "x": xs, "y": ys, "z": zs, "event_id": evid})
    raw_rows = len(df)
    df = df.drop_duplicates(subset=["period", "game_clock", "player_id"], keep="first")
    n_unique_moments = int(df[["period", "game_clock"]].drop_duplicates().shape[0])
    inv = {"n_event_containers": n_containers, "n_raw_moments": n_moments_raw, "n_raw_rows": raw_rows, "n_dedup_rows": int(len(df)),
           "n_unique_moments": n_unique_moments, "duplication_factor_moments": round(n_moments_raw / max(n_unique_moments, 1), 3),
           "periods": sorted(int(p) for p in df.period.unique())}
    return df, inv
