# Fresh-clone reproduction test

Fresh-clone verification performed on 2026-09-30 against the initial public release of this repository. The repository was cloned into an empty directory and run there; nothing was copied in from the authors' working tree, and the only external inputs are the two public sources named in `docs/DATA_AVAILABILITY.md`.

Environment: Linux, CPU only; Python 3.12.13; numpy 2.2.6; pandas 2.2.3; scipy 1.13.1; statsmodels 0.14.4; matplotlib 3.10.8.

## Stage A — from the shipped aggregates (no external data)

```bash
git clone <repository url> five-back-transition
cd five-back-transition
pip install -r requirements.txt
python3 tests/test_smoke.py
```

Runtime 1.7 s. Result: **PASS** — 15 of 15 headline assertions, namely 631 games; 48,083 possession starts; 32,835 first-field-goal-attempt possessions; median T5 5.63 s with IQR 4.82–6.39 s; 56.6 % five back by 6 s; 10.4 % not back by 8 s; five back associated with −17.3 pp rim-attempt probability (95 % CI −19.3 to −15.3); the 2 s − 10 s contrast +42.0 → +23.5 pp (44 % attenuation); dose response +29.3 / +14.5 / +8.4 pp; the 6–7 s bin 59.5 % versus 38.4 %; and the time-bin fixed-effects model −13.9 pp (95 % CI −16.2 to −11.6).

Both figures are regenerated from `results/*.json` during the test. Re-rendering them directly with `python3 src/figures_final.py` also succeeds. The regenerated PNGs are byte-identical to the shipped files:

| file | sha256 (first 16) |
|---|---|
| `figures/FIG1_recovery_clock.png` | `fefa3bf66b69ff0f` |
| `figures/FIG2_clock_vs_defenders.png` | `66a1292a72c1499f` |

The PDFs are visually identical but not byte-identical across renders, because matplotlib embeds a creation timestamp in the PDF metadata.

`MANIFEST.sha256.json` was verified against the clone: every listed file present, every sha256 matching.

## Stage B — from the public sources (user-supplied)

```bash
export FIVEBACK_SPORTVU_JSON=<directory of mirror JSON files>
export FIVEBACK_PBP=<PlayByPlayV3 parquet for 2015-16>
bash scripts/run_all.sh
```

This stage requires the two third-party sources, which are not redistributed here (see `docs/DATA_AVAILABILITY.md`). It rebuilds the possession, trajectory and shot tables locally, validates the `N_BACK` construct, re-fits the models, runs the three pre-specified robustness checks and re-renders the figures, overwriting the shipped `results/*.json` with the user's own regeneration. A 25-game subset of the build stage (`python3 src/build_fiveback.py --workers 16 --limit 25`, followed by `python3 src/validate_nback.py`) completes in about 35 s on 16 cores and reproduces the per-game intermediates exactly; the full 631-game run takes roughly an hour on the same hardware and is what regenerates the shipped aggregates.

## Boundary

- Reproducible with no external data: every number in the abstract and in this repository's README, and both figures (Stage A).
- Requires the user-supplied public sources: re-estimation of the −17.3 pp model, the time decomposition, the dose response, and the common-support, frontcourt-entry and selection checks. These consume the shot and possession tables, which are derived from the tracking data, are withheld from this repository, and are rebuilt locally by `scripts/run_all.sh`.
- Classification: code reproducible; source data obtained manually by the user; results reproducible from user-supplied sources — see `docs/DATA_AVAILABILITY.md`.
