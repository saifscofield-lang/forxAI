"""
Central-bank policy-rate history (monthly step function), 2022-2026.
Phase 11 carry test input — see docs/research/phase11_carry_prereg.md.

Each currency maps to a list of (effective YYYY-MM, rate%) CHANGE-POINTS — the
rate is held constant (forward-filled) until the next change-point. Rates are the
headline policy rate:
  USD = Fed funds target, UPPER bound
  EUR = ECB deposit facility rate
  GBP = BoE Bank Rate
  AUD = RBA cash rate
  CAD = BoC overnight target
  CHF = SNB policy rate
  JPY = BoJ policy rate (short-term)

Confidence: HIGH through 2024-12 (well-documented decisions). 2025-2026 values are
APPROXIMATE (knowledge cutoff) — flagged so they can be corrected on review. For a
premise test the SIGN of differentials (often >3%) is robust to small magnitude
errors; precise 2025-26 levels are not.
"""
import pandas as pd

CHANGES = {
    "USD": [  # Federal Reserve (target upper bound)
        ("2022-01", 0.25), ("2022-03", 0.50), ("2022-05", 1.00), ("2022-06", 1.75),
        ("2022-07", 2.50), ("2022-09", 3.25), ("2022-11", 4.00), ("2022-12", 4.50),
        ("2023-02", 4.75), ("2023-03", 5.00), ("2023-05", 5.25), ("2023-07", 5.50),
        ("2024-09", 5.00), ("2024-11", 4.75), ("2024-12", 4.50),
        ("2025-09", 4.25), ("2025-11", 4.00), ("2025-12", 3.75),   # 2025: approx
    ],
    "EUR": [  # ECB deposit facility
        ("2022-01", -0.50), ("2022-07", 0.00), ("2022-09", 0.75), ("2022-10", 1.50),
        ("2022-12", 2.00), ("2023-02", 2.50), ("2023-03", 3.00), ("2023-05", 3.25),
        ("2023-06", 3.50), ("2023-08", 3.75), ("2023-09", 4.00),
        ("2024-06", 3.75), ("2024-09", 3.50), ("2024-10", 3.25), ("2024-12", 3.00),
        ("2025-02", 2.75), ("2025-03", 2.50), ("2025-04", 2.25), ("2025-06", 2.00),  # 2025: approx
    ],
    "GBP": [  # Bank of England Bank Rate
        ("2022-01", 0.25), ("2022-02", 0.50), ("2022-03", 0.75), ("2022-05", 1.00),
        ("2022-06", 1.25), ("2022-08", 1.75), ("2022-09", 2.25), ("2022-11", 3.00),
        ("2022-12", 3.50), ("2023-02", 4.00), ("2023-03", 4.25), ("2023-05", 4.50),
        ("2023-06", 5.00), ("2023-08", 5.25),
        ("2024-08", 5.00), ("2024-11", 4.75),
        ("2025-02", 4.50), ("2025-05", 4.25), ("2025-08", 4.00),  # 2025: approx
    ],
    "AUD": [  # Reserve Bank of Australia cash rate
        ("2022-01", 0.10), ("2022-05", 0.35), ("2022-06", 0.85), ("2022-07", 1.35),
        ("2022-08", 1.85), ("2022-09", 2.35), ("2022-10", 2.60), ("2022-11", 2.85),
        ("2022-12", 3.10), ("2023-02", 3.35), ("2023-03", 3.60), ("2023-05", 3.85),
        ("2023-06", 4.10), ("2023-11", 4.35),
        ("2025-02", 4.10), ("2025-05", 3.85), ("2025-08", 3.60),  # 2025: approx
    ],
    "CAD": [  # Bank of Canada overnight target
        ("2022-01", 0.25), ("2022-03", 0.50), ("2022-04", 1.00), ("2022-06", 1.50),
        ("2022-07", 2.50), ("2022-09", 3.25), ("2022-10", 3.75), ("2022-12", 4.25),
        ("2023-01", 4.50), ("2023-06", 4.75), ("2023-07", 5.00),
        ("2024-06", 4.75), ("2024-07", 4.50), ("2024-09", 4.25), ("2024-10", 3.75),
        ("2024-12", 3.25), ("2025-01", 3.00), ("2025-03", 2.75),  # 2025: approx
    ],
    "CHF": [  # Swiss National Bank policy rate
        ("2022-01", -0.75), ("2022-06", -0.25), ("2022-09", 0.50), ("2022-12", 1.00),
        ("2023-03", 1.50), ("2023-06", 1.75),
        ("2024-03", 1.50), ("2024-06", 1.25), ("2024-09", 1.00), ("2024-12", 0.50),
        ("2025-03", 0.25), ("2025-06", 0.00),  # 2025: approx
    ],
    "JPY": [  # Bank of Japan short-term policy rate
        ("2022-01", -0.10),
        ("2024-03", 0.10), ("2024-07", 0.25),
        ("2025-01", 0.50),  # 2025: approx
    ],
}

# Each pair's (base, quote): rate_diff = rate(base) - rate(quote)
PAIR_LEGS = {
    "EURUSD": ("EUR", "USD"), "GBPUSD": ("GBP", "USD"), "AUDUSD": ("AUD", "USD"),
    "USDCAD": ("USD", "CAD"), "USDCHF": ("USD", "CHF"), "USDJPY": ("USD", "JPY"),
}


def rate_series(ccy: str, month_index: pd.DatetimeIndex) -> pd.Series:
    """Forward-filled monthly policy rate for a currency over the given month index."""
    pts = pd.Series(
        {pd.Timestamp(m + "-01"): r for m, r in CHANGES[ccy]}
    ).sort_index()
    # reindex onto the target months, forward-filling the step function
    full = pts.reindex(pts.index.union(month_index)).ffill()
    return full.reindex(month_index)


def rate_diff_series(pair: str, month_index: pd.DatetimeIndex) -> pd.Series:
    base, quote = PAIR_LEGS[pair]
    return rate_series(base, month_index) - rate_series(quote, month_index)
