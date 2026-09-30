#!/usr/bin/env python3
"""Smoke test (no tracking data needed): regenerate the two figures from the shipped aggregate results and assert
the headline numbers quoted in the abstract / README.  Run:  python3 tests/test_smoke.py
"""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]


def close(a, b, tol):
    return abs(a - b) <= tol


def main() -> int:
    v = json.loads((R / "results" / "nback_validation.json").read_text()); r = json.loads((R / "results" / "fiveback_results.json").read_text()); c = r["corrected"]
    cs = json.loads((R / "results" / "check1_common_support.json").read_text())
    checks = {
        "games == 631": r["n_games"] == 631,
        "starts == 48,083": v["n_starts_total"] == 48083,
        "first-FGA possessions == 32,835": r["n_possessions"] == 32835,
        "median T5 == 5.63 s": close(v["median_time_to_five_s"], 5.63, 0.005),
        "IQR == [4.82, 6.39]": close(v["p25_p75_time_to_five_s"][0], 4.82, 0.005) and close(v["p25_p75_time_to_five_s"][1], 6.39, 0.005),
        "P(five back by 6 s) == 56.6 %": close(100 * v["p_five_back_by_s"]["6"], 56.6, 0.05),
        "not five back by 8 s == 10.4 %": close(100 * v["never_reach_5_within_8s_among_8s_possessions"], 10.4, 0.05),
        "FIVE_BACK -> rim == -17.3 pp": close(c["model_T"]["beta_pp"], -17.3, 0.05),
        "95 % CI == [-19.3, -15.3]": close(c["model_T"]["ci95_pp"][0], -19.3, 0.05) and close(c["model_T"]["ci95_pp"][1], -15.3, 0.05),
        "time-only 2 s - 10 s contrast == +42.0": close(c["B7"]["time_only"]["early_contrast_pp"], 42.0, 0.05),
        "combined contrast == +23.5": close(c["B7"]["combined"]["early_contrast_pp"], 23.5, 0.05),
        "attenuation == 44 %": close(100 * c["B7"]["early_contrast_attenuation"], 44.0, 0.5),
        "dose response +29.3 / +14.5 / +8.4": close(c["B8"]["le2"]["beta_pp"], 29.3, 0.05) and close(c["B8"]["3"]["beta_pp"], 14.5, 0.05) and close(c["B8"]["4"]["beta_pp"], 8.4, 0.05),
        "6-7 s bin: 59.5 % vs 38.4 %": close(100 * cs["bins"][2]["rim_rate_0"], 59.5, 0.05) and close(100 * cs["bins"][2]["rim_rate_1"], 38.4, 0.05),
        "time-bin FE model == -13.9 [-16.2, -11.6]": close(cs["stratified_model"]["beta_pp"], -13.9, 0.05) and close(cs["stratified_model"]["ci95_pp"][0], -16.2, 0.05) and close(cs["stratified_model"]["ci95_pp"][1], -11.6, 0.06),
    }
    bad = [k for k, ok in checks.items() if not ok]
    for k, ok in checks.items():
        print(("PASS " if ok else "FAIL ") + k)
    out = R / "tests" / "_out"; out.mkdir(parents=True, exist_ok=True)   # render out-of-tree so the working tree stays clean
    proc = subprocess.run([sys.executable, str(R / "src" / "figures_final.py"), str(out)], capture_output=True, text=True)
    import hashlib
    names = ("FIG1_recovery_clock", "FIG2_clock_vs_defenders")
    figs_ok = proc.returncode == 0 and all((out / f"{n}.png").exists() and (out / f"{n}.pdf").exists() for n in names)
    same = figs_ok and all(hashlib.sha256((out / f"{n}.png").read_bytes()).hexdigest()
                           == hashlib.sha256((R / "figures" / f"{n}.png").read_bytes()).hexdigest() for n in names)
    print(("PASS " if figs_ok else "FAIL ") + "figures regenerated from results JSON" + ("" if figs_ok else f"\n{proc.stderr[-800:]}"))
    print(("PASS " if same else "FAIL ") + "regenerated figures identical to the released PNGs")
    figs_ok = figs_ok and same
    if bad or not figs_ok:
        print("SMOKE TEST FAILED:", bad); return 1
    print("SMOKE TEST PASSED"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
