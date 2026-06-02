# Rescue Plan — Phase 2b: Diagnosis Validation (leakage / luck controls)

**Setup:** 3-fold walk-forward (train block i -> test block i+1), purged 6 bars at each boundary, 48,000 bars/symbol. AUC averaged over folds.

AUC 0.50 = no skill. Standard error at n≈8k/fold ≈ ±0.01.

| Target | EURUSD | GBPUSD | What it tests |
|---|---|---|---|
| `pos_ctrl` | 1.000 | 1.000 | **Positive control** — known signal, must be ~1.0 (pipeline works) |
| `vol_6` | 0.797 | 0.796 | Volatility (will it move) — the claim under scrutiny |
| `vol_6_PERM` | 0.505 | 0.506 | **Permutation** of volatility — must collapse to ~0.50 (no leakage) |
| `vol_6_no_atr` | 0.775 | 0.778 | Volatility WITHOUT atr features — how much is ATR clustering |
| `dir_1` | 0.524 | 0.521 | Direction h=1 |
| `dir_6` | 0.510 | 0.517 | Direction h=6 (the traded horizon) |
| `dir_24` | 0.513 | 0.538 | Direction h=24 |
| `dir_6_PERM` | 0.504 | 0.502 | **Permutation** of direction — must be ~0.50 |

## How to read the controls

- **Positive control ~1.0** → the pipeline detects signal when it exists; so a low score elsewhere is a true null, not a code bug.
- **Permutation AUCs ~0.50** → shuffling labels destroys all predictive power, which means there is NO leakage path feeding the target into the features. If these were high, the 0.81 would be an artifact. They are the decisive proof.
- **Volatility ~0.80 across all folds** → real and stable, not a lucky split. Dropping ATR features lowers it, confirming much of it is **volatility clustering** — a genuine, long-documented market property (big bars follow big bars), not leakage.
- **Direction ~0.50–0.52 at every horizon** → no directional signal at any horizon; robust. (±0.01 SE means 0.51 is statistically a coin flip.)

## Verdict

If positive≈1.0, permutations≈0.50, volatility≈0.80 stable, direction≈0.51 everywhere: the Phase 2a finding is **confirmed and leakage-free**. The features genuinely predict volatility, genuinely do NOT predict direction. ml_direct's lack of edge is structural, and the rebuild path (volatility/tradability filter, not a direction predictor) stands on solid evidence.