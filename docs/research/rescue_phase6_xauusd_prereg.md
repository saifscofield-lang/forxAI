# Rescue Plan — Phase 6: XAUUSD + D1 Filter — PRE-REGISTRATION

**Status:** PRE-REGISTERED 2026-06-03. Gates fixed BEFORE running the test.
**Purpose:** confirm or kill the only rescue survivor — D1-trend-filtered
MACD-M15 on XAUUSD (gold) — under a dedicated, honest, out-of-sample test.

## Why this is pre-registered

Phase 5c found XAUUSD net-positive (PF_net 1.246) — but it was selected *post-hoc*
from a 7-symbol sweep. Phase 7 already proved that path is dangerous: a symbol
whitelist looked great on a single corpus, then failed walk-forward as an
**artifact** (commit 64a3507). To avoid moving the goalposts after seeing results,
the pass criteria below are committed to the repo NOW, before the test is built.

## What the test does

XAUUSD only. D1-trend-filtered (EMA50>EMA200 daily, no-lookahead) MACD-M15, same
ATR(1.2) filter, ordered SL/TP (2.5/3.5×ATR), horizon 100, per-trade
spread+slippage in ATR units (base XAUUSD cost = 0.38 price ≈ 14% of median ATR).
Script: `scripts/validate_xauusd_d1_oos.py` (reuses 5b/5c machinery).

PF_net = sum(net wins) / |sum(net losses)|, net = gross R ± per-trade cost in ATR.

## PASS gates (ALL five must hold)

| Gate | Criterion |
|---|---|
| **X1 OOS** | Chronological 70% train / 30% hold-out. OOS-segment PF_net ≥ 1.05. |
| **X2 Walk-forward** | ≥ 6 of 8 contiguous XAUUSD-only folds PF_net ≥ 1.0 (per-fold, not pooled). |
| **X3 Regime** | PF_net ≥ 1.0 in BOTH 2022-2024 (gold bull) AND 2025-2026 (recent). Not a trend-up artifact. |
| **X4 Cost stress** | PF_net ≥ 1.0 at 1.5× base spread+slippage. |
| **X5 Filter adds value** | On the OOS segment, D1-filtered PF_net > unfiltered XAUUSD PF_net. |

## Decision rule (pre-registered)

- **Pass all 5** → XAUUSD+D1 MACD-M15 is the surviving cornerstone engine. Build
  forward from it: proper per-trade risk, trade management, then forward paper
  collection toward an evaluation gate. This becomes the real "foundation stone."
- **Fail any one** → the price-only-TA hypothesis is fully closed (consistent with
  the Phase 4a/5b meta-finding). Pivot to non-price information: carry / rate
  differentials, cross-asset signals, or higher-timeframe structure. Do NOT add
  more TA variants on the same bars.

## Caveats (carried forward, honestly)

- Clean ATR-exit sim: no intrabar path within a bar, no partial fills, no live
  breakeven/trailing management. Management can move PF a few points but cannot
  manufacture an edge from nothing.
- XAUUSD has ~5.5k D1 bars back to 2004 but M15 only to ~2021-12; the test uses
  the ~100k M15 sample (2021-2026), which spans one large gold bull plus a chop
  era — adequate for X3 but not multi-decade.
- n≈218 trades total on XAUUSD is modest; a 30% OOS slice is ~65 trades. Treat a
  marginal pass with appropriate skepticism and confirm in forward paper.
