# Rescue Plan — Phase 3c: SMA + ADX Gate Validation (sweep)

**Data:** 7 symbols × 60,000 H1 bars. SMA 20/50, exits SL=2.0×/TP=3.0×ATR. ADX via project compute_adx. Walk-forward 3 folds.

| Gate | Mean Gated PF | Folds>1.0 | Trades/symbol-yr | Fold PFs |
|---|---:|---:|---:|---|
| Ungated | **1.10** | 2/3 | 9 | 1.18, 1.13, 0.98 |
| ADX≥20 | **1.18** | 3/3 | 6 | 1.30, 1.15, 1.09 |
| ADX≥22 | **1.17** | 3/3 | 5 | 1.31, 1.10, 1.11 |
| ADX≥25 | **1.36** | 3/3 | 3 | 1.58, 1.38, 1.12 |

## Acceptance (PF≥1.15, ≥2/3 folds, ≥20 trades/symbol-yr)

**⚠️ No gate meets BOTH the PF and the ≥20 trades/symbol-yr floor simultaneously.**
The ADX gate raises quality sharply but SMA crosses are intrinsically rare, so trade frequency collapses. This is a quality-vs-quantity tradeoff for the owner:
- Tight gate (ADX≥25): high PF (~1.36) but only ~3/symbol-yr — a few high-quality trades, negligible contribution to the trade-accumulation goal.
- Ungated: PF ~1.10 (thin, spread-risky) at ~9/symbol-yr.
- SMA is a minor contributor either way; MACD-M15 (~87/symbol-yr) remains the frequency engine. Reasonable options: (a) ship ADX≥20/22 as a quality-tilted compromise, (b) keep SMA ungated as-is, or (c) retire SMA and rely on MACD-M15.

## VERDICT: TRADEOFF — owner decision
