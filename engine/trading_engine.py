"""
محرك التداول — Trading Engine
يربط الاستراتيجية بإدارة المخاطر والتنفيذ والأخبار
"""
import json
import time as _time
import yaml
import numpy as np
import pandas as pd
from datetime import datetime
from loguru import logger

from execution.broker_adapters.mt5_adapter import MT5Adapter
from risk.risk_manager import RiskManager
from storage.database import (
    SessionLocal, Trade, AccountSnapshot, SignalLog, TradeResult,
    MarketContext, ScanLog, SymbolScanDetail, IndicatorSnapshot,
    MonitorState,
)
from observability.telegram_notifier import TelegramNotifier
from features.technical.indicators import add_sma, add_rsi, add_atr, add_macd, add_bollinger_bands


ENGINE_VERSION = "2.1"  # Hybrid monitor: scaled TP, partial close, dynamic trailing
ML_TRAINING_THRESHOLD = 200  # Minimum closed trades needed for ML training


class TradingEngine:
    """محرك التداول الرئيسي"""

    def __init__(self, config_path: str = "config/base.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.adapter = MT5Adapter()
        self.risk_manager = RiskManager(config_path)
        self.strategies = []
        self.instruments = {
            inst["symbol"]: inst for inst in self.config.get("instruments", [])
        }
        self.running = False
        self._last_ticket = None
        self.notifier = TelegramNotifier()
        self.news_filter = None
        self.scan_count = 0
        self._ml_ready_notified = False  # Track if we already sent ML-ready notification

        # Hybrid Monitor: per-position state tracking (loaded from DB on start)
        # {ticket: {"phase": int, "tp1_closed": bool, "original_volume": float, "original_tp": float, "entry_atr": float}}
        self._position_states = {}

        # Load optimized params for TP multipliers
        try:
            with open("data/optimized_params.yaml", "r") as f:
                self._optimized_params = yaml.safe_load(f) or {}
        except Exception:
            self._optimized_params = {}

    def set_news_filter(self, news_filter):
        """Set news filter for blocking trades during high-impact events."""
        self.news_filter = news_filter
        logger.info("News filter enabled")

    def add_strategy(self, strategy):
        """Register a strategy"""
        self.strategies.append(strategy)
        logger.info(f"Strategy registered: {strategy.name}")

    def start(self) -> bool:
        """Connect to MT5 and initialize"""
        if not self.adapter.connect():
            logger.error("Failed to connect to MT5")
            return False

        account = self.adapter.get_account_info()
        self.risk_manager.set_balance(account["balance"])
        self.running = True
        self._load_monitor_states()
        logger.success(
            f"Engine started | Balance: ${account['balance']:,.2f} | "
            f"Strategies: {len(self.strategies)} | "
            f"Instruments: {list(self.instruments.keys())} | "
            f"Monitor states restored: {len(self._position_states)}"
        )
        return True

    def stop(self):
        """Shutdown engine"""
        self.running = False
        self._save_monitor_states()
        self.adapter.disconnect()
        logger.info("Engine stopped")

    def _load_monitor_states(self):
        """Load persisted monitor states from DB for open positions."""
        session = SessionLocal()
        try:
            states = session.query(MonitorState).all()
            for s in states:
                self._position_states[s.ticket] = {
                    "phase": s.phase,
                    "tp1_closed": s.tp1_closed,
                    "original_volume": s.original_volume,
                    "original_tp": s.original_tp,
                    "entry_atr": s.entry_atr,
                    "symbol": s.symbol,
                }
            if states:
                logger.info(f"[MONITOR] Restored {len(states)} position states from DB")
        except Exception as e:
            logger.debug(f"Monitor state load error: {e}")
        finally:
            session.close()

    def _save_monitor_states(self):
        """Persist all current monitor states to DB."""
        session = SessionLocal()
        try:
            # Clear old states and write current ones
            session.query(MonitorState).delete()
            for ticket, state in self._position_states.items():
                ms = MonitorState(
                    ticket=ticket,
                    symbol=state.get("symbol", "UNKNOWN"),
                    phase=state.get("phase", 0),
                    tp1_closed=state.get("tp1_closed", False),
                    original_volume=state.get("original_volume"),
                    original_tp=state.get("original_tp"),
                    entry_atr=state.get("entry_atr"),
                )
                session.add(ms)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.debug(f"Monitor state save error: {e}")
        finally:
            session.close()

    def scan_signals(self) -> tuple[list[dict], list[dict]]:
        """Run all strategies on all instruments, collect all signals.

        Returns (signals, scan_details) where scan_details is per-symbol diagnostic info.
        """
        signals = []
        scan_details = []
        tf_config = self.config.get("timeframes", {})
        primary_tf = tf_config.get("primary", "H1")
        secondary_tf = tf_config.get("secondary", "H4")
        confirm_tf = tf_config.get("confirmation", "M15")
        bars = self.config.get("data", {}).get("history_bars", 500)

        for symbol in self.instruments:
            detail = {"symbol": symbol, "signal_generated": False, "rejection_reason": ""}

            # ── Fetch multi-timeframe data ──
            df_h1 = self.adapter.get_ohlcv(symbol, primary_tf, bars)
            if df_h1.empty:
                detail["rejection_reason"] = "Failed to fetch H1 data"
                logger.warning(f"[{symbol}] No H1 data received from MT5")
                scan_details.append(detail)
                continue

            df_h4 = self.adapter.get_ohlcv(symbol, secondary_tf, 200)
            df_m15 = self.adapter.get_ohlcv(symbol, confirm_tf, 100)

            # ── Build market context ──
            market_ctx = self._build_market_context(symbol, df_h1, df_h4, df_m15)

            # ── Check news filter ──
            news_blocked = False
            news_reason = None
            upcoming_news = []
            if self.news_filter:
                news_blocked, news_reason = self.news_filter.should_block_trading(symbol)
                upcoming_news = self.news_filter.get_nearby_events(symbol, window_hours=4.0)

            detail["news_blocked"] = news_blocked
            detail["news_event"] = news_reason
            detail["upcoming_news"] = upcoming_news
            detail["h1_trend"] = market_ctx.get("h1_trend")
            detail["h4_trend"] = market_ctx.get("h4_trend")
            detail["volatility"] = market_ctx.get("volatility_regime")

            # ── Compute basic indicators for logging ──
            try:
                _tmp = df_h1.copy()
                _tmp = add_rsi(_tmp, 14)
                _tmp = add_atr(_tmp, 14)
                _last = _tmp.dropna(subset=["rsi_14", "atr_14"])
                if len(_last) > 0:
                    detail["rsi"] = float(_last.iloc[-1]["rsi_14"])
                    detail["atr"] = float(_last.iloc[-1]["atr_14"])
                    detail["price"] = float(_last.iloc[-1]["close"])
            except Exception:
                pass

            # Track all signals from all strategies for this symbol
            symbol_signals = []

            for strategy in self.strategies:
                if hasattr(strategy, "symbol") and strategy.symbol != symbol:
                    continue

                # Get SMA diagnostic only for strategies with SMA params
                if hasattr(strategy, "fast_period") and hasattr(strategy, "slow_period"):
                    sma_diag = self._diagnose_sma(df_h1, strategy)
                    detail.update(sma_diag)

                signal = strategy.generate_signal(df_h1)
                if signal:
                    detail["signal_generated"] = True
                    detail["signal_action"] = signal["action"]
                    detail["signal_status"] = signal.get("status", "ACTIVE")

                    signal["symbol"] = symbol
                    signal["h1_trend"] = market_ctx.get("h1_trend")
                    signal["h4_trend"] = market_ctx.get("h4_trend")
                    signal["volatility_regime"] = market_ctx.get("volatility_regime")
                    signal["spread_at_entry"] = market_ctx.get("spread")

                    # Attach feature snapshot for ML training
                    if not signal.get("features_json"):
                        signal["features_json"] = self._build_feature_snapshot(df_h1)

                    if self.news_filter:
                        nearby = self.news_filter.get_nearby_events(symbol, window_hours=1.0)
                        if nearby:
                            signal["news_nearby"] = True
                            signal["news_event_name"] = nearby[0]["event_name"]
                            signal["news_impact"] = nearby[0]["impact"]
                        else:
                            signal["news_nearby"] = False

                    if news_blocked and signal.get("status") == "ACTIVE":
                        signal["status"] = "NEWS_FILTERED"
                        signal["news_filter_reason"] = news_reason
                        detail["signal_status"] = "NEWS_FILTERED"

                    signal.setdefault("status", "ACTIVE")
                    market_ctx["signal_action"] = signal["action"]
                    market_ctx["signal_status"] = signal["status"]
                    signals.append(signal)
                    symbol_signals.append(signal)

            # Save indicator snapshot for this symbol (regardless of signals)
            self._save_indicator_snapshot(
                symbol, df_h1, market_ctx,
                signal_fired=len(symbol_signals) > 0,
                signal_action=symbol_signals[0]["action"] if symbol_signals else None,
                signal_strategy=symbol_signals[0].get("strategy") if symbol_signals else None,
            )

            if not symbol_signals:
                # Log no-signal info
                logger.info(
                    f"[{symbol}] NO SIGNAL | "
                    f"RSI={detail.get('rsi', 0):.1f} | ATR={detail.get('atr', 0):.5f} | "
                    f"H1={detail.get('h1_trend')} H4={detail.get('h4_trend')}"
                )

            self._save_market_context(symbol, market_ctx)
            scan_details.append(detail)

        return signals, scan_details

    def _diagnose_sma(self, df: pd.DataFrame, strategy) -> dict:
        """Compute detailed SMA crossover diagnostic for a symbol."""
        diag = {}
        try:
            tmp = df.copy()
            tmp = add_sma(tmp, strategy.fast_period)
            tmp = add_sma(tmp, strategy.slow_period)
            tmp = add_rsi(tmp, strategy.rsi_period)
            tmp = add_atr(tmp, strategy.atr_period)
            tmp = add_macd(tmp)
            tmp = add_bollinger_bands(tmp, 20)

            fast_col = f"sma_{strategy.fast_period}"
            slow_col = f"sma_{strategy.slow_period}"
            rsi_col = f"rsi_{strategy.rsi_period}"
            atr_col = f"atr_{strategy.atr_period}"

            clean = tmp.dropna(subset=[fast_col, slow_col, rsi_col, atr_col])
            if len(clean) < 2:
                diag["rejection_reason"] = "Not enough data for indicators"
                return diag

            curr = clean.iloc[-1]
            prev = clean.iloc[-2]

            sma_fast = float(curr[fast_col])
            sma_slow = float(curr[slow_col])
            prev_fast = float(prev[fast_col])
            prev_slow = float(prev[slow_col])

            diag["price"] = float(curr["close"])
            diag["sma_fast"] = sma_fast
            diag["sma_slow"] = sma_slow
            diag["sma_prev_fast"] = prev_fast
            diag["sma_prev_slow"] = prev_slow
            diag["sma_gap_pct"] = ((sma_fast - sma_slow) / sma_slow) * 100 if sma_slow else 0
            diag["rsi"] = float(curr[rsi_col])
            diag["atr"] = float(curr[atr_col])
            diag["macd"] = float(curr.get("macd_line", 0))
            diag["macd_signal"] = float(curr.get("macd_signal", 0))

            # Bollinger position
            bb_range = curr.get("bb_upper", 0) - curr.get("bb_lower", 0)
            if bb_range > 0:
                diag["bb_position"] = float((curr["close"] - curr.get("bb_lower", 0)) / bb_range)

            # Crossover detection
            inst = self.instruments.get(strategy.symbol, {})
            pip_value = inst.get("pip_value", 0.0001)
            cross_distance = abs(sma_fast - sma_slow) / pip_value

            if prev_fast <= prev_slow and sma_fast > sma_slow:
                diag["crossover"] = "BULLISH"
            elif prev_fast >= prev_slow and sma_fast < sma_slow:
                diag["crossover"] = "BEARISH"
            else:
                diag["crossover"] = "NONE"

            diag["cross_distance"] = cross_distance

        except Exception as e:
            diag["rejection_reason"] = f"Diagnostic error: {e}"
            logger.debug(f"SMA diagnostic error: {e}")

        return diag

    def _build_market_context(self, symbol: str, df_h1: pd.DataFrame,
                              df_h4: pd.DataFrame, df_m15: pd.DataFrame) -> dict:
        """Build multi-timeframe market context for a symbol."""
        ctx = {"symbol": symbol}

        # ── H1 context ──
        try:
            h1 = df_h1.copy()
            h1 = add_sma(h1, 20)
            h1 = add_sma(h1, 50)
            h1 = add_rsi(h1, 14)
            h1 = add_atr(h1, 14)
            h1 = add_macd(h1)
            h1 = add_bollinger_bands(h1, 20)

            last = h1.iloc[-1]
            ctx["h1_close"] = float(last["close"])
            ctx["h1_atr"] = float(last.get("atr_14", 0))
            ctx["h1_rsi"] = float(last.get("rsi_14", 50))
            ctx["h1_sma_fast"] = float(last.get("sma_20", 0))
            ctx["h1_sma_slow"] = float(last.get("sma_50", 0))
            ctx["h1_macd"] = float(last.get("macd_line", 0))
            ctx["h1_macd_signal"] = float(last.get("macd_signal", 0))

            # Bollinger position
            bb_range = last.get("bb_upper", 0) - last.get("bb_lower", 0)
            if bb_range > 0:
                ctx["h1_bb_position"] = float((last["close"] - last.get("bb_lower", 0)) / bb_range)

            # H1 trend
            if last.get("sma_20", 0) > last.get("sma_50", 0):
                ctx["h1_trend"] = "UP"
            elif last.get("sma_20", 0) < last.get("sma_50", 0):
                ctx["h1_trend"] = "DOWN"
            else:
                ctx["h1_trend"] = "RANGE"

            # Volatility regime (ATR relative to 20-period average)
            atr_series = h1["atr_14"].dropna()
            if len(atr_series) >= 20:
                atr_avg = atr_series.tail(20).mean()
                atr_current = float(last.get("atr_14", 0))
                if atr_current > atr_avg * 1.3:
                    ctx["volatility_regime"] = "HIGH"
                elif atr_current < atr_avg * 0.7:
                    ctx["volatility_regime"] = "LOW"
                else:
                    ctx["volatility_regime"] = "NORMAL"
        except Exception as e:
            logger.debug(f"H1 context error for {symbol}: {e}")

        # ── H4 context ──
        try:
            if not df_h4.empty and len(df_h4) >= 50:
                h4 = df_h4.copy()
                h4 = add_sma(h4, 50)
                h4 = add_sma(h4, 200)
                h4 = add_rsi(h4, 14)
                h4 = add_atr(h4, 14)

                last4 = h4.iloc[-1]
                ctx["h4_close"] = float(last4["close"])
                ctx["h4_atr"] = float(last4.get("atr_14", 0))
                ctx["h4_rsi"] = float(last4.get("rsi_14", 50))
                ctx["h4_sma_50"] = float(last4.get("sma_50", 0))
                ctx["h4_sma_200"] = float(last4.get("sma_200", 0)) if "sma_200" in last4 else None

                if last4.get("sma_50", 0) > last4.get("sma_200", last4.get("sma_50", 0)):
                    ctx["h4_trend"] = "UP"
                elif last4.get("sma_50", 0) < last4.get("sma_200", last4.get("sma_50", 0)):
                    ctx["h4_trend"] = "DOWN"
                else:
                    ctx["h4_trend"] = "RANGE"
        except Exception as e:
            logger.debug(f"H4 context error for {symbol}: {e}")

        # ── M15 context ──
        try:
            if not df_m15.empty and len(df_m15) >= 14:
                m15 = df_m15.copy()
                m15 = add_rsi(m15, 14)
                m15 = add_atr(m15, 14)

                last15 = m15.iloc[-1]
                ctx["m15_close"] = float(last15["close"])
                ctx["m15_rsi"] = float(last15.get("rsi_14", 50))
                ctx["m15_atr"] = float(last15.get("atr_14", 0))
        except Exception as e:
            logger.debug(f"M15 context error for {symbol}: {e}")

        # ── Spread ──
        try:
            tick = self.adapter.get_tick(symbol)
            if tick:
                ctx["spread"] = tick.get("spread", 0)
        except Exception:
            pass

        return ctx

    def _save_market_context(self, symbol: str, ctx: dict):
        """Save market context snapshot to database."""
        session = SessionLocal()
        try:
            mc = MarketContext(
                symbol=symbol,
                h1_close=ctx.get("h1_close"),
                h1_atr=ctx.get("h1_atr"),
                h1_rsi=ctx.get("h1_rsi"),
                h1_sma_fast=ctx.get("h1_sma_fast"),
                h1_sma_slow=ctx.get("h1_sma_slow"),
                h1_macd=ctx.get("h1_macd"),
                h1_macd_signal=ctx.get("h1_macd_signal"),
                h1_bb_position=ctx.get("h1_bb_position"),
                h4_close=ctx.get("h4_close"),
                h4_atr=ctx.get("h4_atr"),
                h4_rsi=ctx.get("h4_rsi"),
                h4_sma_50=ctx.get("h4_sma_50"),
                h4_sma_200=ctx.get("h4_sma_200"),
                h4_trend=ctx.get("h4_trend"),
                m15_close=ctx.get("m15_close"),
                m15_rsi=ctx.get("m15_rsi"),
                m15_atr=ctx.get("m15_atr"),
                volatility_regime=ctx.get("volatility_regime"),
                spread=ctx.get("spread"),
                signal_action=ctx.get("signal_action"),
                signal_status=ctx.get("signal_status"),
            )
            session.add(mc)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.debug(f"Market context save error: {e}")
        finally:
            session.close()

    def _build_feature_snapshot(self, df: pd.DataFrame) -> str | None:
        """Build full ML feature snapshot as JSON for any signal."""
        try:
            from features.ml.feature_engine import build_features, get_feature_columns
            feat_df = build_features(df, dropna=True)
            if len(feat_df) > 0:
                cols = get_feature_columns(feat_df)
                row = feat_df[cols].iloc[-1]
                return json.dumps({k: round(float(v), 6) for k, v in row.items()})
        except Exception:
            pass
        return None

    def _save_indicator_snapshot(self, symbol: str, df: pd.DataFrame,
                                 market_ctx: dict, signal_fired: bool = False,
                                 signal_action: str = None,
                                 signal_strategy: str = None):
        """Save full indicator snapshot for every scan — even without signals."""
        session = SessionLocal()
        try:
            from features.ml.feature_engine import build_features, get_feature_columns
            feat_df = build_features(df, dropna=True)
            features_json = None
            snap_data = {}
            if len(feat_df) > 0:
                cols = get_feature_columns(feat_df)
                row = feat_df[cols].iloc[-1]
                features_json = json.dumps({k: round(float(v), 6) for k, v in row.items()})
                snap_data = {c: float(row[c]) for c in cols if c in row.index}

            snap = IndicatorSnapshot(
                scan_number=self.scan_count,
                symbol=symbol,
                features_json=features_json,
                price=float(df.iloc[-1]["close"]) if len(df) > 0 else None,
                rsi_14=snap_data.get("rsi_14"),
                atr_14=snap_data.get("atr_14_pct"),
                macd=snap_data.get("macd"),
                macd_signal=snap_data.get("macd_signal"),
                bb_position=snap_data.get("bb_position"),
                sma_20=snap_data.get("close_vs_sma_20"),
                sma_50=snap_data.get("close_vs_sma_50"),
                ema_12=snap_data.get("ema_12_26_diff"),
                volatility_10=snap_data.get("volatility_10"),
                return_1=snap_data.get("return_1"),
                return_5=snap_data.get("return_5"),
                volume_ratio=snap_data.get("volume_ratio"),
                h1_trend=market_ctx.get("h1_trend"),
                h4_trend=market_ctx.get("h4_trend"),
                signal_fired=signal_fired,
                signal_action=signal_action,
                signal_strategy=signal_strategy,
            )
            session.add(snap)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.debug(f"Indicator snapshot error: {e}")
        finally:
            session.close()

    def execute_signal(self, signal: dict) -> tuple[bool, str]:
        """Validate and execute a single signal.

        Returns (success, reason) for logging purposes.
        Integrates: IMP-01 (tick_value sizing), IMP-13 (min SL),
        IMP-19 (spread adjustment), IMP-30 (correlated check), IMP-18 (portfolio risk)
        """
        symbol = signal["symbol"]
        inst = self.instruments.get(symbol)
        if not inst:
            logger.error(f"Unknown instrument: {symbol}")
            return False, f"Unknown instrument: {symbol}"

        # Check risk limits
        open_positions = self.adapter.get_open_positions()
        if not self.risk_manager.can_open_trade(len(open_positions)):
            return False, "Max positions or daily drawdown/loss limit"

        # Prevent conflicting directions on same symbol (IMP-02)
        if len(open_positions) > 0:
            symbol_positions = open_positions[
                open_positions["symbol"] == symbol
            ]
            if len(symbol_positions) > 0:
                existing_dir = symbol_positions.iloc[0]["type"]
                new_dir = signal["action"]
                if existing_dir != new_dir:
                    return False, (
                        f"Conflicting {existing_dir} already open on {symbol}"
                    )
                return False, f"Position already open on {symbol}"

        # IMP-30: Check correlated exposure
        if not open_positions.empty:
            pos_list = open_positions[["symbol", "type"]].to_dict("records")
            corr_ok, corr_reason = self.risk_manager.check_correlated_exposure(
                symbol, signal["action"], pos_list
            )
            if not corr_ok:
                return False, corr_reason

        # H4 trend filter: only trade with the trend (IMP-10)
        h4_trend = signal.get("h4_trend")
        if h4_trend and h4_trend != "RANGE":
            action = signal["action"]
            if h4_trend == "UP" and action == "SELL":
                return False, f"H4 trend is UP, blocking SELL on {symbol}"
            if h4_trend == "DOWN" and action == "BUY":
                return False, f"H4 trend is DOWN, blocking BUY on {symbol}"

        # IMP-15: Session filter — block low-liquidity hours
        session_ok, session_reason = self._check_session(symbol)
        if not session_ok:
            return False, session_reason

        pip_value = inst["pip_value"]
        entry = signal["price"]
        atr = signal.get("atr", 0)

        # IMP-13: Enforce minimum SL distance
        sl = signal["stop_loss"]
        if atr > 0:
            sl = self.risk_manager.enforce_min_sl(
                entry, sl, atr, signal["action"], pip_value
            )
            signal["stop_loss"] = sl

        # IMP-19: Adjust SL/TP for spread
        spread_info = self.adapter.get_symbol_info(symbol)
        if spread_info:
            spread_price = spread_info.get("spread", 0) * spread_info.get("point", 0)
            if spread_price > 0:
                if signal["action"] == "BUY":
                    sl = sl - spread_price  # Widen SL by spread
                    signal["take_profit"] = signal["take_profit"] - spread_price
                else:
                    sl = sl + spread_price
                    signal["take_profit"] = signal["take_profit"] + spread_price
                signal["stop_loss"] = round(sl, 5)
                signal["take_profit"] = round(signal["take_profit"], 5)

        sl_pips = abs(entry - sl) / pip_value

        # IMP-01: Use MT5 tick_value for accurate position sizing
        sym_info = self.adapter.get_symbol_info(symbol)
        tick_value = sym_info.get("trade_tick_value") if sym_info else None
        tick_size = sym_info.get("trade_tick_size") if sym_info else None

        account = self.adapter.get_account_info()
        lot_size = self.risk_manager.calculate_position_size(
            balance=account["balance"],
            stop_loss_pips=sl_pips,
            pip_value=pip_value,
            tick_value=tick_value,
            tick_size=tick_size,
        )

        # IMP-18: Portfolio-level risk cap
        new_risk = lot_size * sl_pips * (tick_value * (pip_value / tick_size) if tick_value and tick_size else pip_value * 100_000)
        open_risk = self._calculate_open_risk(open_positions)
        port_ok, port_reason = self.risk_manager.check_portfolio_risk(new_risk, open_risk)
        if not port_ok:
            return False, port_reason

        # Validate trade
        ok, msg = self.risk_manager.validate_trade(
            symbol=symbol,
            order_type=signal["action"],
            lot_size=lot_size,
            stop_loss=sl,
            take_profit=signal["take_profit"],
            entry_price=entry,
        )
        if not ok:
            logger.warning(f"Trade rejected: {msg}")
            return False, msg

        # Execute
        result = self.adapter.place_order(
            symbol=symbol,
            order_type=signal["action"],
            volume=lot_size,
            stop_loss=sl,
            take_profit=signal["take_profit"],
            comment=f"ForexAI-{signal['strategy']}",
        )

        if result["success"]:
            requested_price = signal["price"]
            filled_price = result["price"]
            slippage_pips = abs(filled_price - requested_price) / pip_value
            signal["slippage_pips"] = round(slippage_pips, 2)
            signal["filled_price"] = filled_price
            signal["volume"] = lot_size

            self._record_trade(signal, result, lot_size)
            return True, ""

        return False, result.get("error", "Order failed")

    def _check_session(self, symbol: str) -> tuple[bool, str]:
        """Check if current hour is in active session for this symbol (IMP-15)."""
        from datetime import datetime, timezone
        utc_hour = datetime.now(timezone.utc).hour

        # Define active sessions per symbol group
        # London: 07-16, NY: 12-20, Tokyo: 00-08
        eur_gbp_chf = ["EURUSD", "GBPUSD", "USDCHF"]
        jpy_pairs = ["USDJPY"]
        commodity = ["XAUUSD"]
        aud_nzd = ["AUDUSD", "NZDUSD", "USDCAD"]

        if symbol in eur_gbp_chf:
            # London + NY overlap: 07-20 UTC
            if not (7 <= utc_hour < 20):
                return False, f"Session filter: {symbol} inactive at {utc_hour}:00 UTC (active 07-20)"
        elif symbol in jpy_pairs:
            # Tokyo + London: 00-16 UTC
            if not (0 <= utc_hour < 16):
                return False, f"Session filter: {symbol} inactive at {utc_hour}:00 UTC (active 00-16)"
        elif symbol in commodity:
            # London + NY: 07-20 UTC
            if not (7 <= utc_hour < 20):
                return False, f"Session filter: {symbol} inactive at {utc_hour}:00 UTC (active 07-20)"
        elif symbol in aud_nzd:
            # Sydney + London: 00-20 UTC (wide window for AUD/NZD)
            if not (0 <= utc_hour < 20):
                return False, f"Session filter: {symbol} inactive at {utc_hour}:00 UTC (active 00-20)"

        return True, "OK"

    def _calculate_open_risk(self, open_positions) -> float:
        """Calculate total dollar risk of all open positions (IMP-18)."""
        if open_positions.empty:
            return 0.0

        total_risk = 0.0
        for _, pos in open_positions.iterrows():
            sl = pos.get("sl", 0)
            if sl and sl > 0:
                inst = self.instruments.get(pos["symbol"])
                if inst:
                    pip_value = inst["pip_value"]
                    sl_pips = abs(pos["open_price"] - sl) / pip_value
                    sym_info = self.adapter.get_symbol_info(pos["symbol"])
                    if sym_info and sym_info.get("trade_tick_value") and sym_info.get("trade_tick_size"):
                        pip_cost = sym_info["trade_tick_value"] * (pip_value / sym_info["trade_tick_size"])
                    else:
                        pip_cost = pip_value * 100_000
                    total_risk += pos["volume"] * sl_pips * pip_cost
        return total_risk

    def _record_trade(self, signal: dict, result: dict, lot_size: float):
        """Save trade to database"""
        self._last_ticket = result["ticket"]
        session = SessionLocal()
        try:
            trade = Trade(
                ticket=result["ticket"],
                symbol=signal["symbol"],
                order_type=signal["action"],
                volume=lot_size,
                open_price=result["price"],
                open_time=datetime.now(),
                stop_loss=signal["stop_loss"],
                take_profit=signal["take_profit"],
                strategy=signal["strategy"],
                comment=signal.get("reason", ""),
                engine_version=ENGINE_VERSION,
            )
            session.add(trade)
            session.commit()
            logger.info(f"Trade recorded: #{result['ticket']}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to record trade: {e}")
        finally:
            session.close()

    def take_snapshot(self):
        """Save account snapshot to database"""
        account = self.adapter.get_account_info()
        if not account:
            return

        session = SessionLocal()
        try:
            snap = AccountSnapshot(
                balance=account["balance"],
                equity=account["equity"],
                margin=account["margin"],
                free_margin=account["free_margin"],
                profit=account["profit"],
            )
            session.add(snap)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Snapshot error: {e}")
        finally:
            session.close()

    def _log_signal(self, signal: dict, status: str, reason: str = None, ticket: int = None):
        """Write signal to SignalLog table."""
        session = SessionLocal()
        try:
            log = SignalLog(
                symbol=signal["symbol"],
                action=signal["action"],
                price=signal.get("price"),
                stop_loss=signal.get("stop_loss"),
                take_profit=signal.get("take_profit"),
                atr=signal.get("atr"),
                rsi=signal.get("rsi"),
                strategy=signal.get("strategy", ""),
                status=status,
                reason=reason,
                ml_confidence=signal.get("ml_confidence"),
                ml_threshold=signal.get("ml_threshold"),
                ticket=ticket,
                features_json=signal.get("features_json"),
            )
            session.add(log)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to log signal: {e}")
        finally:
            session.close()

    def check_closed_trades(self):
        """Check for trades that closed since last scan and record results."""
        session = SessionLocal()
        try:
            # Get open trades from our DB that we haven't recorded results for
            open_trades = session.query(Trade).filter(Trade.is_closed == False).all()
            if not open_trades:
                return

            # Get currently open positions from MT5
            mt5_positions = self.adapter.get_open_positions()
            open_tickets = set(mt5_positions["ticket"].tolist()) if not mt5_positions.empty else set()

            for trade in open_trades:
                if trade.ticket not in open_tickets:
                    # Trade was closed -- record the result
                    self._record_trade_result(session, trade)

            session.commit()

            # Check if we have enough v2.0 trades for ML training
            if not self._ml_ready_notified:
                v2_count = session.query(TradeResult).filter(
                    TradeResult.engine_version == ENGINE_VERSION
                ).count()
                if v2_count >= ML_TRAINING_THRESHOLD:
                    self._ml_ready_notified = True
                    self.notifier.send(
                        f"<b>ML TRAINING READY</b>\n"
                        f"Collected {v2_count} closed trades (v{ENGINE_VERSION}).\n"
                        f"Run: <code>python scripts/train_ml.py</code>"
                    )
                    logger.info(f"ML training threshold reached: {v2_count} trades")
        except Exception as e:
            session.rollback()
            logger.error(f"check_closed_trades error: {e}")
        finally:
            session.close()

    def _record_trade_result(self, session, trade: Trade):
        """Record a closed trade's final result for ML retraining."""
        import MetaTrader5 as mt5

        # Try to get the deal from MT5 history
        now = datetime.now()
        deals = mt5.history_deals_get(position=trade.ticket)

        close_price = None
        close_time = None
        pnl = 0.0
        exit_reason = "UNKNOWN"

        if deals and len(deals) > 1:
            # Last deal is the closing deal
            close_deal = deals[-1]
            close_price = close_deal.price
            close_time = datetime.fromtimestamp(close_deal.time)
            pnl = close_deal.profit + close_deal.swap + close_deal.commission

            # Determine exit reason from comment
            comment = (close_deal.comment or "").upper()
            if "SL" in comment or "STOP LOSS" in comment:
                exit_reason = "SL_HIT"
            elif "TP" in comment or "TAKE PROFIT" in comment:
                exit_reason = "TP_HIT"
            else:
                exit_reason = "MANUAL"
        else:
            # Fallback: estimate from trade record
            close_time = now
            exit_reason = "UNKNOWN"

        # IMP-17: Track realized losses for daily limit
        if pnl < 0:
            self.risk_manager.record_realized_loss(pnl)

        # Calculate pips
        inst = self.instruments.get(trade.symbol)
        pip_value = inst["pip_value"] if inst else 0.0001
        if close_price and trade.open_price:
            if trade.order_type == "BUY":
                pnl_pips = (close_price - trade.open_price) / pip_value
            else:
                pnl_pips = (trade.open_price - close_price) / pip_value
        else:
            pnl_pips = 0.0

        # Update trade record
        trade.close_price = close_price
        trade.close_time = close_time
        trade.profit = pnl
        trade.is_closed = True

        # Calculate trade duration
        duration_minutes = None
        if trade.open_time and close_time:
            duration_minutes = int((close_time - trade.open_time).total_seconds() / 60)

        # Calculate planned R:R ratio
        rr_planned = None
        if trade.stop_loss and trade.take_profit and trade.open_price:
            sl_dist = abs(trade.open_price - trade.stop_loss)
            tp_dist = abs(trade.take_profit - trade.open_price)
            if sl_dist > 0:
                rr_planned = round(tp_dist / sl_dist, 2)

        # Calculate actual R:R ratio
        rr_actual = None
        if trade.stop_loss and close_price and trade.open_price:
            sl_dist = abs(trade.open_price - trade.stop_loss)
            if sl_dist > 0:
                actual_dist = abs(close_price - trade.open_price)
                rr_actual = round(actual_dist / sl_dist, 2)
                if pnl < 0:
                    rr_actual = -rr_actual

        # Write to TradeResult for ML retraining
        result = TradeResult(
            ticket=trade.ticket,
            symbol=trade.symbol,
            action=trade.order_type,
            open_price=trade.open_price,
            close_price=close_price,
            open_time=trade.open_time,
            close_time=close_time,
            pnl=pnl,
            pnl_pips=round(pnl_pips, 1),
            exit_reason=exit_reason,
            profitable=(pnl > 0),
            strategy=trade.strategy,
            volume=trade.volume,
            swap=trade.swap,
            commission=trade.commission,
            trade_duration_minutes=duration_minutes,
            risk_reward_planned=rr_planned,
            risk_reward_actual=rr_actual,
            engine_version=ENGINE_VERSION,
        )

        # Try to attach ML confidence, features, and context from SignalLog
        signal_log = session.query(SignalLog).filter(
            SignalLog.ticket == trade.ticket
        ).first()
        if signal_log:
            result.ml_confidence = signal_log.ml_confidence
            result.features_json = signal_log.features_json
            result.atr_at_entry = signal_log.atr
            result.rsi_at_entry = signal_log.rsi

        session.add(result)
        logger.info(
            f"Trade result: #{trade.ticket} {trade.symbol} {trade.order_type} | "
            f"PnL: ${pnl:+.2f} ({pnl_pips:+.1f} pips) | Exit: {exit_reason}"
        )
        self.notifier.trade_closed(
            symbol=trade.symbol, action=trade.order_type,
            pnl=pnl, pnl_pips=round(pnl_pips, 1),
            exit_reason=exit_reason, ticket=trade.ticket,
        )

    def run_once(self) -> tuple[list[dict], list[dict]]:
        """Run one scan cycle: generate signals -> log -> execute -> check closed.

        Returns (executed_signals, scan_details) for Telegram reporting.
        """
        if not self.running:
            logger.warning("Engine not running")
            return [], []

        self.scan_count += 1
        scan_start = _time.time()

        # Update P&L
        account = self.adapter.get_account_info()
        self.risk_manager.update_pnl(account.get("profit", 0))

        # Save news events to DB (if filter active)
        if self.news_filter:
            self.news_filter.save_events_to_db()

        # Check for trades that closed since last scan
        self.check_closed_trades()

        signals, scan_details = self.scan_signals()
        executed = []

        # IMP-31: Sort signals by strategy priority (best first)
        STRATEGY_PRIORITY = {
            "macd_crossover": 1,
            "rsi_reversal": 2,
            "bollinger_bounce": 3,
            "sma_crossover": 4,
            "ml_filtered_sma": 5,
        }
        signals.sort(key=lambda s: STRATEGY_PRIORITY.get(s.get("strategy", ""), 99))

        # Track signal counts for scan log
        counts = {
            "total": len(signals), "active": 0, "ml_filtered": 0,
            "news_filtered": 0, "risk_rejected": 0, "executed": 0,
        }
        news_block_event = None

        for signal in signals:
            status = signal.get("status", "ACTIVE")

            if status == "ML_FILTERED":
                counts["ml_filtered"] += 1
                self._log_signal(signal, "ML_FILTERED",
                                 reason=f"ML confidence {signal.get('ml_confidence', 0):.1%} < threshold")
                continue

            if status == "NEWS_FILTERED":
                counts["news_filtered"] += 1
                news_block_event = signal.get("news_filter_reason", "")
                self._log_signal(signal, "NEWS_FILTERED",
                                 reason=signal.get("news_filter_reason", "High-impact news"))
                self.notifier.signal_filtered(
                    signal, reason=f"NEWS: {signal.get('news_filter_reason', '')}")
                continue

            counts["active"] += 1

            logger.info(
                f"Signal: {signal['action']} {signal['symbol']} | "
                f"{signal['reason']}"
            )
            success, reject_reason = self.execute_signal(signal)

            if success:
                counts["executed"] += 1
                ticket = self._last_ticket
                self._log_signal(signal, "EXECUTED", ticket=ticket)
                self.notifier.signal_executed(signal, ticket=ticket)
                executed.append(signal)
            else:
                counts["risk_rejected"] += 1
                logger.warning(
                    f"REJECTED: {signal['action']} {signal['symbol']} "
                    f"[{signal.get('strategy', '?')}] | Reason: {reject_reason}"
                )
                self._log_signal(signal, "RISK_REJECTED", reason=reject_reason)
                self.notifier.signal_filtered(signal, reason=reject_reason)

        self.take_snapshot()

        # ── Save scan log + details ──
        scan_duration = int((_time.time() - scan_start) * 1000)
        positions = self.adapter.get_open_positions()
        self._save_scan_log(
            scan_duration=scan_duration,
            counts=counts,
            open_positions=len(positions) if not positions.empty else 0,
            account=account,
            news_blocked=counts["news_filtered"] > 0,
            news_event=news_block_event,
            scan_details=scan_details,
        )

        # Save per-symbol details to DB
        self._save_scan_details(scan_details)

        return executed, scan_details

    def _save_scan_log(self, scan_duration: int, counts: dict,
                       open_positions: int, account: dict,
                       news_blocked: bool, news_event: str = None,
                       scan_details: list = None):
        """Save scan cycle log to database."""
        import json
        session = SessionLocal()
        try:
            # Serialize scan details summary
            details_json = None
            if scan_details:
                summary = []
                for d in scan_details:
                    s = {
                        "symbol": d.get("symbol"),
                        "crossover": d.get("crossover", "NONE"),
                        "sma_gap_pct": round(d.get("sma_gap_pct", 0), 4),
                        "rsi": round(d.get("rsi", 0), 1),
                        "signal": d.get("signal_generated", False),
                        "reason": d.get("rejection_reason", ""),
                    }
                    summary.append(s)
                details_json = json.dumps(summary, ensure_ascii=False)

            log = ScanLog(
                scan_number=self.scan_count,
                duration_ms=scan_duration,
                symbols_scanned=len(self.instruments),
                signals_total=counts["total"],
                signals_active=counts["active"],
                signals_ml_filtered=counts["ml_filtered"],
                signals_news_filtered=counts["news_filtered"],
                signals_risk_rejected=counts["risk_rejected"],
                signals_executed=counts["executed"],
                open_positions=open_positions,
                balance=account.get("balance"),
                equity=account.get("equity"),
                news_blocked=news_blocked,
                news_event_name=news_event,
                details_json=details_json,
            )
            session.add(log)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.debug(f"Scan log save error: {e}")
        finally:
            session.close()

    def monitor_positions(self):
        """Hybrid Monitor: breakeven, partial close at TP1, dynamic TP2, trailing.

        Called every 5 minutes by APScheduler. 4-phase position management:
        Phase 1: Move SL to breakeven when price moves +1.0x ATR in favor
        Phase 2: Partial close 50% at original TP, move SL to mid-profit
        Phase 3: Set TP2 = TP1 + 1.0x ATR, trail at 1.0x ATR
        Phase 4: Tighten trail to 0.7x ATR after +3.0x ATR from entry
        """
        if not self.running:
            return

        positions = self.adapter.get_open_positions()
        if positions.empty:
            # Clean up states for closed positions
            if self._position_states:
                self._position_states.clear()
                self._save_monitor_states()
            return

        # Clean up states for positions that no longer exist
        active_tickets = set(positions["ticket"].tolist())
        closed = [t for t in self._position_states if t not in active_tickets]
        for t in closed:
            del self._position_states[t]

        # Batch-fetch ATR for all unique symbols at once
        atr_cache = {}
        for symbol in positions["symbol"].unique():
            df = self.adapter.get_ohlcv(symbol, "H1", 50)
            if df.empty:
                continue
            df = add_atr(df, 14)
            atr_vals = df["atr_14"].dropna()
            if len(atr_vals) > 0:
                atr_cache[symbol] = float(atr_vals.iloc[-1])

        for _, pos in positions.iterrows():
            try:
                self._manage_position(pos, atr_cache)
            except Exception as e:
                logger.debug(f"Monitor error #{pos['ticket']}: {e}")

        # Persist states to DB after each monitor cycle
        self._save_monitor_states()

    def _get_digits(self, symbol: str) -> int:
        """Get decimal digits for rounding prices per symbol."""
        inst = self.instruments.get(symbol)
        if inst:
            return inst.get("digits", 5)
        return 5

    def _manage_position(self, pos, atr_cache: dict):
        """Hybrid 4-phase position management."""
        symbol = pos["symbol"]
        inst = self.instruments.get(symbol)
        if not inst:
            return

        ticket = pos["ticket"]
        entry_price = pos["open_price"]
        current_price = pos["current_price"]
        current_sl = pos.get("sl", 0)
        current_tp = pos.get("tp", 0)
        current_volume = pos["volume"]
        action = pos["type"]  # "BUY" or "SELL"
        pip_value = inst["pip_value"]
        digits = self._get_digits(symbol)

        atr = atr_cache.get(symbol)
        if not atr or atr <= 0:
            return

        # Initialize position state if new
        if ticket not in self._position_states:
            self._position_states[ticket] = {
                "phase": 0,
                "tp1_closed": False,
                "original_volume": current_volume,
                "original_tp": current_tp,
                "entry_atr": atr,
                "symbol": symbol,
            }

        state = self._position_states[ticket]

        # Calculate price movement in ATR units
        if action == "BUY":
            move_in_favor = current_price - entry_price
        else:
            move_in_favor = entry_price - current_price

        atr_units_moved = move_in_favor / atr if atr > 0 else 0

        # ── Phase 4: Tighten trail after +3.0x ATR ──
        if atr_units_moved >= 3.0 and state["tp1_closed"]:
            if state["phase"] < 4:
                state["phase"] = 4
                logger.info(f"[MONITOR] #{ticket} {symbol} → Phase 4 (tight trail)")
            self._apply_trailing(ticket, symbol, action, current_price, current_sl,
                                 atr, trail_mult=0.7, digits=digits, phase="P4-TIGHT")
            return

        # ── Phase 3: Trail at 0.5x ATR after partial close ──
        if state["tp1_closed"]:
            if state["phase"] < 3:
                state["phase"] = 3
                logger.info(f"[MONITOR] #{ticket} {symbol} → Phase 3 (trailing)")
            self._apply_trailing(ticket, symbol, action, current_price, current_sl,
                                 atr, trail_mult=0.5, digits=digits, phase="P3-TRAIL")
            return

        # ── Phase 1.5: Trail at 0.5x ATR after breakeven, before TP ──
        if state["phase"] >= 1 and not state["tp1_closed"] and atr_units_moved >= 0.5:
            self._apply_trailing(ticket, symbol, action, current_price, current_sl,
                                 atr, trail_mult=0.5, digits=digits, phase="P1-TRAIL")

        # ── Phase 2: Partial close at original TP ──
        original_tp = state["original_tp"]
        if original_tp > 0 and not state["tp1_closed"]:
            tp_reached = False
            if action == "BUY" and current_price >= original_tp:
                tp_reached = True
            elif action == "SELL" and current_price <= original_tp:
                tp_reached = True

            if tp_reached:
                close_volume = round(state["original_volume"] * 0.5, 2)
                if close_volume >= 0.01:
                    result = self.adapter.partial_close(ticket, close_volume)
                    if result.get("success"):
                        state["tp1_closed"] = True
                        state["phase"] = 2

                        # Move SL to mid-profit point
                        if action == "BUY":
                            mid_sl = entry_price + (current_price - entry_price) * 0.5
                        else:
                            mid_sl = entry_price - (entry_price - current_price) * 0.5
                        mid_sl = round(mid_sl, digits)

                        # Set TP2 = original TP + 1.0x ATR
                        if action == "BUY":
                            new_tp = round(original_tp + atr * 1.0, digits)
                        else:
                            new_tp = round(original_tp - atr * 1.0, digits)

                        self.adapter.modify_position(ticket, stop_loss=mid_sl, take_profit=new_tp)

                        logger.info(
                            f"[MONITOR] #{ticket} {symbol} {action} | PARTIAL CLOSE 50% "
                            f"({close_volume} lots @ {result['price']:.{digits}f}) | "
                            f"SL → {mid_sl:.{digits}f} | TP2 → {new_tp:.{digits}f}"
                        )
                        self.notifier.send(
                            f"🎯 [MONITOR] #{ticket} {symbol} {action}\n"
                            f"TP1 HIT — Closed 50% ({close_volume} lots)\n"
                            f"SL → {mid_sl:.{digits}f} (mid-profit)\n"
                            f"TP2 → {new_tp:.{digits}f} (+1 ATR)"
                        )
                        return

        # ── Phase 1: Breakeven at +0.3x ATR ──
        if atr_units_moved >= 0.3 and state["phase"] < 1:
            if action == "BUY":
                be_sl = entry_price + (pip_value * 2)
            else:
                be_sl = entry_price - (pip_value * 2)
            be_sl = round(be_sl, digits)

            should_move = False
            if action == "BUY" and current_sl < be_sl:
                should_move = True
            elif action == "SELL" and (current_sl == 0 or current_sl > be_sl):
                should_move = True

            if should_move:
                result = self.adapter.modify_position(ticket, stop_loss=be_sl)
                if result.get("success"):
                    state["phase"] = 1
                    logger.info(
                        f"[MONITOR] #{ticket} {symbol} {action} | BREAKEVEN "
                        f"SL → {be_sl:.{digits}f} | Move: {atr_units_moved:.1f}x ATR"
                    )
                    self.notifier.send(
                        f"🔒 [MONITOR] #{ticket} {symbol} {action}\n"
                        f"BREAKEVEN: SL → {be_sl:.{digits}f}\n"
                        f"Price moved {atr_units_moved:.1f}x ATR in favor"
                    )

    def _apply_trailing(self, ticket, symbol, action, current_price, current_sl,
                        atr, trail_mult, digits, phase):
        """Apply trailing stop at trail_mult * ATR distance."""
        # Get current TP for reporting
        positions = self.adapter.get_open_positions()
        current_tp = 0
        if not positions.empty:
            pos_row = positions[positions["ticket"] == ticket]
            if not pos_row.empty:
                current_tp = pos_row.iloc[0].get("tp", 0)

        if action == "BUY":
            trail_sl = round(current_price - atr * trail_mult, digits)
            if trail_sl > current_sl:
                result = self.adapter.modify_position(ticket, stop_loss=trail_sl)
                if result.get("success"):
                    logger.info(
                        f"[MONITOR] #{ticket} {symbol} BUY | {phase} "
                        f"SL: {current_sl:.{digits}f} → {trail_sl:.{digits}f}"
                    )
                    self.notifier.send(
                        f"📈 [MONITOR] #{ticket} {symbol} BUY\n"
                        f"{phase}: SL {current_sl:.{digits}f} → {trail_sl:.{digits}f}\n"
                        f"Price: {current_price:.{digits}f} | TP: {current_tp:.{digits}f}"
                    )
        else:  # SELL
            trail_sl = round(current_price + atr * trail_mult, digits)
            if current_sl == 0 or trail_sl < current_sl:
                result = self.adapter.modify_position(ticket, stop_loss=trail_sl)
                if result.get("success"):
                    logger.info(
                        f"[MONITOR] #{ticket} {symbol} SELL | {phase} "
                        f"SL: {current_sl:.{digits}f} → {trail_sl:.{digits}f}"
                    )
                    self.notifier.send(
                        f"📉 [MONITOR] #{ticket} {symbol} SELL\n"
                        f"{phase}: SL {current_sl:.{digits}f} → {trail_sl:.{digits}f}\n"
                        f"Price: {current_price:.{digits}f} | TP: {current_tp:.{digits}f}"
                    )

    def _save_scan_details(self, scan_details: list):
        """Save per-symbol scan details to database."""
        import json
        session = SessionLocal()
        try:
            for d in scan_details:
                upcoming_json = None
                if d.get("upcoming_news"):
                    upcoming_json = json.dumps(
                        [{"name": e.get("event_name", ""), "impact": e.get("impact", ""),
                          "time": str(e.get("time", "")), "currency": e.get("currency", "")}
                         for e in d["upcoming_news"]],
                        ensure_ascii=False,
                    )

                detail = SymbolScanDetail(
                    scan_number=self.scan_count,
                    symbol=d.get("symbol", ""),
                    sma_fast=d.get("sma_fast"),
                    sma_slow=d.get("sma_slow"),
                    sma_gap_pct=d.get("sma_gap_pct"),
                    sma_prev_fast=d.get("sma_prev_fast"),
                    sma_prev_slow=d.get("sma_prev_slow"),
                    crossover=d.get("crossover"),
                    cross_distance=d.get("cross_distance"),
                    price=d.get("price"),
                    rsi=d.get("rsi"),
                    atr=d.get("atr"),
                    macd=d.get("macd"),
                    macd_signal=d.get("macd_signal"),
                    bb_position=d.get("bb_position"),
                    h1_trend=d.get("h1_trend"),
                    h4_trend=d.get("h4_trend"),
                    volatility=d.get("volatility"),
                    signal_generated=d.get("signal_generated", False),
                    signal_action=d.get("signal_action"),
                    signal_status=d.get("signal_status"),
                    rejection_reason=d.get("rejection_reason"),
                    news_blocked=d.get("news_blocked", False),
                    news_event=d.get("news_event"),
                    upcoming_news=upcoming_json,
                )
                session.add(detail)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.debug(f"Scan details save error: {e}")
        finally:
            session.close()
