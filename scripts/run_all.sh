#!/usr/bin/env bash
# Five Back — end-to-end reproduction from USER-SUPPLIED public source data.
# Stage 0 (no data needed): python3 tests/test_smoke.py   -> regenerates figures from shipped aggregates and checks headline numbers.
#
# Stage 1 requires the two public sources, obtained by the user (they are NOT redistributed here; see docs/DATA_AVAILABILITY.md):
#   (a) 2015-16 SportVU tracking JSON, one file per game, from the public "NBA-Player-Movements" mirror
#       (github.com/linouk23/NBA-Player-Movements, data/2016.NBA.Raw.SportVU.Game.Logs/*.7z -> extract the *.json files);
#       place them in data/external/sportvu/json/<stem>.json (stems as listed in configs/game_universe.json), or set FIVEBACK_SPORTVU_JSON.
#   (b) stats.nba.com PlayByPlayV3 for every 2015-16 regular-season game, as one parquet with the endpoint's columns
#       (gameId, actionNumber, clock 'PT11M41.00S', period, teamId, personId, actionType, subType, shotDistance, shotResult,
#       isFieldGoal, shotValue, location, scoreHome, scoreAway, description) — e.g. via the nba_api package
#       (nba_api.stats.endpoints.PlayByPlayV3, one call per game id); place it at data/external/pbp/2015-16/all.parquet or set FIVEBACK_PBP.
# Runtime: ~1 h for the build on 16 cores (631 games); the remaining steps take minutes. Outputs go to data/ (withheld tables),
# results/ (aggregate JSON — overwrites the shipped copies with your regeneration) and audit/ (generated markdown reports).
set -euo pipefail
cd "$(dirname "$0")/.."
export FIVEBACK_SPORTVU_JSON="${FIVEBACK_SPORTVU_JSON:-$PWD/data/external/sportvu/json}"
export FIVEBACK_PBP="${FIVEBACK_PBP:-$PWD/data/external/pbp/2015-16/all.parquet}"
WORKERS="${WORKERS:-16}"
mkdir -p audit data/games data/checks

echo "[1/6] build possessions, N_BACK trajectories and first-FGA shot rows (corrected +4.0 s and naive 0 s axes)"
python3 src/build_fiveback.py --workers "$WORKERS" ${LIMIT:+--limit "$LIMIT"}

echo "[2/6] validate the N_BACK construct (decided before any outcome; must print PASS)"
python3 src/validate_nback.py

echo "[3/6] primary models, decomposition, dose response, naive-vs-corrected"
python3 src/analyze_fiveback.py

echo "[4/6] robustness checks — build (frontcourt entry, selection taxonomy)"
python3 src/final_checks_build.py --workers "$WORKERS" ${LIMIT:+--limit "$LIMIT"}

echo "[5/6] robustness checks — analysis (common support, frontcourt entry, selection) + reports"
python3 src/final_checks_analyze.py --stage checks
python3 src/final_checks_docs.py "$PWD"

echo "[6/6] figures from results/*.json"
python3 src/figures_final.py
echo "done — compare results/*.json with the shipped values listed in README.md / docs/validation/FIGURE_VALUES.md"
