# Provenance

| input | source | version / scope | how it enters the study |
|---|---|---|---|
| Player tracking (SportVU, 25 Hz; ball + 10 players per frame) | public GitHub mirror "NBA-Player-Movements" (linouk23), 2015-16 regular season, one JSON per game inside per-game `.7z` archives | 632 game files in the mirror; 631 used (one file contains no tracking moments); file stem ↔ NBA game id in `configs/game_universe.json` | raw frames are de-duplicated on (period, game clock, player) keep-first; defenders' x-coordinates give `N_BACK`; ball x gives attacking direction and frontcourt entry |
| Play-by-play | stats.nba.com `PlayByPlayV3` via the `nba_api` package, pulled once for all 1,230 2015-16 regular-season games | PBP clock format `PT11M41.00S`, converted to seconds remaining in the period | possession starts (defensive rebounds, steal-paired turnovers), first FGA, shot distance, shot result, running score |
| Clock alignment between the two sources | constant **+4.0 s** added to the play-by-play clock before selecting tracking frames; the constant was chosen and validated (on held-out turnovers, shot-team agreement) in a separate alignment study and is held fixed here; no per-game tuning and no tuning on any Five Back outcome | see `configs/analysis_definitions.yaml` | every tracking lookup |
| Attacking direction | inferred per (game, period, team) from the ball position at made field goals; checked against an independently derived basket-side table (`data/reference/court_direction_reference.json`), agreement 0.9997 | — | sign of "own defensive half" |
| Game universe | the 631 calibratable games (alignment quality label carried as metadata only) | `configs/game_universe.json` | which games are processed |

Nothing in this repository was fitted, tuned or selected after looking at Five Back outcomes: the rules in `configs/*.yaml` were fixed before the corresponding numbers were computed, and the construct validation (`results/nback_validation.json`) was settled before any shot outcome was examined.

Companion work: the timing correction and its validation are documented in separate work on temporal alignment of this corpus; this repository depends on it only through the constant +4.0 s.
