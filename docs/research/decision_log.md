# Decision Log

Running log of every formal go/no-go and architectural decision. Each entry matches one row in `improvements.db::go_no_go_decisions` where applicable.

Format:
```
## YYYY-MM-DD — Phase N — VERDICT (gates_passed/gates_total)
**Decided by:** ...
**Rationale:** ...
**Next action:** ...
**Artifacts:** ...
```

---

## 2026-04-21 (later same day) — Phase 10 — YELLOW (verdict updated)

**Decided by:** user, after reviewing step 5 correlation results

**Change:** Downgrading earlier RED to YELLOW. The diversification case is decisive: ρ(BTC) in OOS is 0.57 (below the 0.7 proxy threshold), while ρ(FX)=0.13 and ρ(SPY)=0.21 both sit comfortably under the 0.3 diversification bar. The strategy is a crypto-beta harvester with risk management, not a BTC clone — and it meaningfully diversifies the existing FX book. This changes the calculus from "reject" to "rescue attempt".

**Next action:** Activate Phase 10.5 (regime-filter rescue). Phase 10.5 step 1 (define filter spec) in progress — spec drafted at `docs/research/regime_filter_spec.md`, awaiting user sign-off before implementation (step 2).

**Scope of Phase 10.5 (locked):** one filter, one knob (80th-percentile 4-week basket vol), no parameter sweep in the initial run. If the filter fails the 5-gate OOS panel (the 4 original gates + gated > ungated), v4 crypto-momentum is formally rejected — no further iteration permitted (iterating would reintroduce the overfitting risk Phase 10 step 4 is designed to detect).

---

## 2026-04-21 — Phase 10 (v4 Crypto Momentum) — RED (3/4 secondary, 2/4 primary)

**Decided by:** Claude Code audit + user review

**Summary of path:** Phase 10 steps 1–5 complete in a single working session. Step 3 ran 8 in-sample variants (direction × lookback × cost); all cleared the Sharpe-0.4 gate in-sample. Step 4 OOS validation on 2025-01-01 → 2026-04-17 (69 weeks) exposed regime dependence. Step 5 correlation analysis clarified the rescue case.

**Key numbers**

| Metric | Primary (LO/12m) | Secondary (LO/12w) |
|---|---:|---:|
| Train Sharpe | 1.263 | 1.270 |
| OOS Sharpe | **0.030** | **0.553** |
| OOS MaxDD | −8.5% | −4.4% |
| OOS vs BH BTC | strat +0.03 vs BH −0.33 | strat +0.55 vs BH −0.33 |
| Gates passed (of 4) | 2 | 3 |

Fold stability (K=5 on train window): both variants have one deeply negative fold (≈2022 crypto winter), mean fold Sharpe 0.89 (12m) / 1.18 (12w), std ≈ 1.2 — regime-dependent performance.

**Correlations (weekly, full vs OOS)**

| Counterparty | Full ρ | OOS ρ |
|---|---:|---:|
| BH BTC | 0.710 | 0.573 |
| BH ETH | 0.672 | 0.667 |
| BH BNB | 0.613 | 0.671 |
| BH SOL | 0.630 | 0.703 |
| SPY | 0.211 | 0.206 |
| FX TSMOM weekly | 0.122 | 0.127 |

**Rationale:** OOS Sharpe collapsed from train 1.27 to 0.03 (12m) and 0.55 (12w). The 2025-2026 bear regime is a legitimate stress scenario; TSMOM has almost no long signal in a dominant downtrend. However, both variants beat buy-and-hold BTC decisively in OOS (flat/positive vs −18%), confirming the risk-management design works. The BTC-proxy threshold of ρ > 0.7 was not cleanly met in OOS (0.573), and ρ against FX and SPY was well below the 0.3 diversification threshold — v4 genuinely diversifies from the existing FX book. This makes the case for a rescue attempt (Option 4) rather than outright rejection (Option 1).

**Next action:** Activate Phase 10.5 (TSMOM Crypto + Regime Filter, encoded as `phase_number=105` in DB). Six PENDING steps seeded: define filter spec, implement as overlay, re-run full backtest IS, re-run OOS, compare gated vs ungated, updated go/no-go. If Phase 10.5 also fails the 4-gate OOS panel, formal reject and pivot to a different Phase-10 track (commodities, crypto basis, volatility selling).

**Artifacts:**
- `docs/research/tsmom_crypto_prototype.md` — step 3 (in-sample)
- `docs/research/tsmom_crypto_oos_report.md` — step 4 (OOS)
- `docs/research/tsmom_crypto_corr_report.md` — step 5 (correlations)
- `docs/research/tsmom_crypto_equity_curves.png` — step 3 equity
- `docs/research/tsmom_crypto_oos_equity.png` — step 4 train vs OOS
- `docs/research/tsmom_crypto_corr_heatmap.png` — step 5 correlation heatmap
- `data/raw_crypto/*/D1.parquet` — Binance D1 data (BTC/ETH/BNB/SOL USDT)
- `improvements.db::tsmom_runs` — 12 crypto rows (8 IS + 4 OOS/train slices)
- `improvements.db::go_no_go_decisions` — this decision, id=1

---
