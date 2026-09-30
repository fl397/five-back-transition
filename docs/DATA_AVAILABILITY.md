# Data availability

Redistribution rights for the third-party inputs are not confirmed, so those inputs are not included here.

**Raw third-party tracking and play-by-play data are not redistributed in this repository.**

| item | status in this repository | where to obtain |
|---|---|---|
| 2015-16 NBA SportVU player-tracking JSON (one file per game, 25 Hz) | **not included** (event/frame-level; redistribution rights unresolved) | the public "NBA-Player-Movements" mirror on GitHub (linouk23), `data/2016.NBA.Raw.SportVU.Game.Logs/*.7z`; file stems ↔ NBA game ids are listed in `configs/game_universe.json` |
| stats.nba.com PlayByPlayV3 play-by-play (2015-16 regular season) | **not included** | stats.nba.com endpoint `playbyplayv3` (e.g. via the `nba_api` Python package), one call per game id; expected columns are listed in `scripts/run_all.sh` |
| possession / shot / frame-level derived tables (`data/games/*.parquet`, `data/shots_fiveback_*.parquet`, `data/checks/*.parquet`) | **not included** (derived from the tracking data; withheld pending rights) | regenerated deterministically by `scripts/run_all.sh` from the two sources above |
| aggregate results (`results/*.json`): season-level counts, model coefficients, confidence intervals, recovery-clock summary, per-bin rates | included | — |
| per-game metadata (`configs/game_universe.json`: game id, mirror file stem, alignment quality label; `data/reference/court_direction_reference.json`: basket side per game/period/team) | included (metadata only; no positions, no players) | — |
| code, analysis configuration, figures, captions, abstract | included | — |

The released `data/reference/` directory contains a single basket-side reference table with one row per (game, period, offensive team) — 3,653 rows holding the inferred attacking side and the counts of made field goals used to infer it. It contains no frame-, shot-, possession-, event- or player-level tracking data, and no coordinates or timestamps.

Every number in the abstract, README and figures can be reproduced (a) from the shipped aggregates for the figures and headline checks (`tests/test_smoke.py`), and (b) in full — including the withheld tables — by a user who obtains the two public sources independently and runs `scripts/run_all.sh`.

**Scope.** This repository provides complete code, the analysis configuration, source and provenance pointers, legally releasable aggregate outputs and deterministic reconstruction instructions, while omitting the third-party raw and event-level tracking data themselves.

**License.** The software in this repository is released under the MIT License. Third-party NBA tracking and play-by-play data are not covered by this license and are not redistributed here.
