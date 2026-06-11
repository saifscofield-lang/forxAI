"""Golden cases — historical hypotheses with KNOWN verdicts, for validating the engine.

Each case is transcribed verbatim from its frozen results doc. They declare the gates that
were actually frozen at the time (NOT the lessons-corrected canonical set) — so the engine
must reproduce the historical verdict faithfully, with no retroactive relaxation.

Sources:
  Carry  -> docs/research/phase11_carry_results.md  (FAIL on C1,C3,C4,C5)
  Trend  -> docs/research/phase12_trend_premium_results.md  (FAIL on D5; D5 mis-specified)
"""

# --------------------------------------------------------------------------- #
# Phase 11 — Carry premise test.  Expected: FAIL {C1, C3, C4, C5}, PASS {C2}.
# --------------------------------------------------------------------------- #
CARRY = {
    "hypothesis_id": "phase11_carry",
    "title": "FX carry / rate-differential premium",
    "economic_rationale": "Higher-yielding currencies earn a carry premium over lower-yielding ones.",
    "prereg_commit": "01770f4",
    "declared_gates": [
        {"id": "C1", "kind": "all_of", "desc": "premise: mean>0 & t>=2.0",
         "subs": [{"path": "mean_period", "op": ">", "th": 0.0},
                  {"path": "t_stat", "op": ">=", "th": 2.0}]},
        {"id": "C2", "kind": "threshold", "desc": "spot drift not significantly negative",
         "path": "spot_t", "op": ">", "th": -2.0},
        {"id": "C3", "kind": "n_positive", "desc": ">=3 of 4 calendar years positive",
         "path": "years", "th": 3},
        {"id": "C4", "kind": "threshold", "desc": ">=4/6 pairs positive",
         "path": "breadth.n_positive", "op": ">=", "th": 4},
        {"id": "C5", "kind": "all_positive", "desc": "both macro regimes net-positive",
         "path": "regimes"},
    ],
    "metrics": {
        "mean_period": 0.001519, "t_stat": 0.56, "sharpe_ann": 0.27,
        "n_obs": 50, "mpy": 12, "skew": 0.0, "kurtosis": 3.0,
        "spot_t": -0.02,
        # calendar years scored for C3 (drop the 3-month 2026 stub used the 4 full years)
        "years": {"2022": 4.10, "2023": -0.55, "2024": 8.61, "2025": -4.05},
        "breadth": {"n_positive": 3, "n_total": 6},
        "regimes": {"hike_2022_2024": 0.003560, "ease_2025_2026": -0.003244},
    },
    "expected_verdict": "FAIL",
    "expected_failed": {"C1", "C3", "C4", "C5"},
    "expected_flags": {"DEF-2-single-regime"},
}

# --------------------------------------------------------------------------- #
# Phase 12 — Cross-asset trend premium.  Expected: FAIL {D5} only + DEF-1 flag.
# --------------------------------------------------------------------------- #
TREND = {
    "hypothesis_id": "phase12_trend",
    "title": "Cross-asset trend premium (TSMOM)",
    "economic_rationale": "A persistent trend-following premium exists across asset classes after costs.",
    "prereg_commit": "9fa6ee2",
    "declared_gates": [
        {"id": "D1", "kind": "all_of", "desc": "significance",
         "subs": [{"path": "mean_period", "op": ">", "th": 0.0},
                  {"path": "t_stat", "op": ">=", "th": 2.0}]},
        {"id": "D2", "kind": "all_of", "desc": "OOS hold-out + no drift",
         "subs": [{"path": "oos.mean", "op": ">", "th": 0.0},
                  {"path": "oos.sharpe", "op": ">=", "th": 0.30},
                  {"path": "oos.drift_p", "op": ">", "th": 0.05}]},
        {"id": "D3", "kind": "all_positive", "desc": "halves + eras all positive",
         "path": "regimes"},
        {"id": "D4", "kind": "threshold", "desc": ">=4/7 classes positive",
         "path": "breadth.n_positive", "op": ">=", "th": 4},
        {"id": "D5", "kind": "all_of", "desc": "diversification validity (FROZEN, incl max-corr)",
         "subs": [{"path": "diversification.enb", "op": ">=", "th": 10.4},
                  {"path": "diversification.pc1", "op": "<", "th": 0.50},
                  {"path": "diversification.max_corr", "op": "<", "th": 0.70}]},
        {"id": "D6", "kind": "all_of", "desc": "cost stress @1.5x + beats passive",
         "subs": [{"path": "cost.net_mean_1_5x", "op": ">", "th": 0.0},
                  {"path": "beats_passive", "op": "==", "th": True}]},
    ],
    "metrics": {
        "mean_period": 0.002200, "t_stat": 3.36, "sharpe_ann": 0.67,
        "n_obs": 305, "mpy": 12, "skew": 0.0, "kurtosis": 3.0,
        "oos": {"mean": 0.001787, "sharpe": 0.57, "drift_p": 0.34},
        "regimes": {"half1": 0.00211, "half2": 0.00229,
                    "era_pre2015": 0.00239, "era_2015plus": 0.00197},
        "breadth": {"n_positive": 6, "n_total": 7},
        "cost": {"net_mean_1x": 0.002200, "net_mean_1_5x": 0.002184, "pf_net": 1.15},
        "diversification": {"enb": 12.27, "pc1": 0.17, "max_corr": 0.93, "n_instruments": 26},
        "beats_passive": True,
    },
    "expected_verdict": "FAIL",
    "expected_failed": {"D5"},
    "expected_flags": {"DEF-1-gate-defect"},
}

GOLDEN_CASES = [CARRY, TREND]
