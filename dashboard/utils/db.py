"""
Database query helpers for the dashboard.
All functions return DataFrames or dicts — no ORM objects exposed.
Smart caching via @st.cache_data with appropriate TTLs.
"""
import sys
import json
from datetime import datetime, timedelta, timezone, date
from typing import Optional

import pandas as pd
import streamlit as st

sys.path.insert(0, ".")

from storage.database import SessionLocal, Trade, SignalLog, TradeResult, AccountSnapshot, NewsEvent, ScanLog, MarketContext, MonitorState


# ── Helpers ──────────────────────────────────────────────────────────────────

def _session():
    return SessionLocal()


# ── Account Snapshots ─────────────────────────────────────────────────────────

@st.cache_data(ttl=120, show_spinner=False)
def get_equity_curve(days: int = 30) -> pd.DataFrame:
    """Return account snapshots as DataFrame sorted by time."""
    session = _session()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        rows = (
            session.query(AccountSnapshot)
            .filter(AccountSnapshot.time >= cutoff)
            .order_by(AccountSnapshot.time)
            .all()
        )
        if not rows:
            return pd.DataFrame(columns=["time", "balance", "equity", "margin", "free_margin", "profit"])
        data = [
            {
                "time": r.time,
                "balance": r.balance,
                "equity": r.equity,
                "margin": r.margin,
                "free_margin": r.free_margin,
                "profit": r.profit,
            }
            for r in rows
        ]
        return pd.DataFrame(data)
    finally:
        session.close()


@st.cache_data(ttl=60, show_spinner=False)
def get_latest_snapshot() -> Optional[dict]:
    """Return the most recent account snapshot."""
    session = _session()
    try:
        row = session.query(AccountSnapshot).order_by(AccountSnapshot.time.desc()).first()
        if not row:
            return None
        return {
            "time": row.time,
            "balance": row.balance,
            "equity": row.equity,
            "margin": row.margin,
            "free_margin": row.free_margin,
            "profit": row.profit,
        }
    finally:
        session.close()


# ── Trades ────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=15, show_spinner=False)
def get_open_trades() -> pd.DataFrame:
    """Return all open (not closed) trades."""
    session = _session()
    try:
        rows = (
            session.query(Trade)
            .filter(Trade.is_closed == False)
            .order_by(Trade.open_time.desc())
            .all()
        )
        return _trades_to_df(rows)
    finally:
        session.close()


@st.cache_data(ttl=15, show_spinner=False)
def get_monitor_states() -> dict:
    """Return monitor states as {ticket: {phase, tp1_closed, ...}}."""
    session = _session()
    try:
        rows = session.query(MonitorState).all()
        states = {}
        for r in rows:
            states[r.ticket] = {
                "phase": r.phase,
                "tp1_closed": r.tp1_closed,
                "original_volume": r.original_volume,
                "original_tp": r.original_tp,
                "entry_atr": getattr(r, "entry_atr", None),
                "updated_at": r.updated_at,
            }
        return states
    except Exception:
        return {}
    finally:
        session.close()


@st.cache_data(ttl=120, show_spinner=False)
def get_closed_trades(limit: int = 500, symbol: Optional[str] = None) -> pd.DataFrame:
    """Return closed trades, most recent first."""
    session = _session()
    try:
        q = session.query(Trade).filter(Trade.is_closed == True)
        if symbol:
            q = q.filter(Trade.symbol == symbol)
        rows = q.order_by(Trade.close_time.desc()).limit(limit).all()
        return _trades_to_df(rows)
    finally:
        session.close()


def _trades_to_df(rows) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=[
            "id", "ticket", "symbol", "order_type", "volume",
            "open_price", "close_price", "open_time", "close_time",
            "profit", "stop_loss", "take_profit", "strategy", "is_closed"
        ])
    return pd.DataFrame([
        {
            "id": r.id,
            "ticket": r.ticket,
            "symbol": r.symbol,
            "order_type": r.order_type,
            "volume": r.volume,
            "open_price": r.open_price,
            "close_price": r.close_price,
            "open_time": r.open_time,
            "close_time": r.close_time,
            "profit": r.profit,
            "stop_loss": r.stop_loss,
            "take_profit": r.take_profit,
            "strategy": r.strategy,
            "is_closed": r.is_closed,
        }
        for r in rows
    ])


# ── Signal Log ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def get_signal_log(
    limit: int = 500,
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    days: int = 30,
) -> pd.DataFrame:
    """Return signal log entries."""
    session = _session()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        q = session.query(SignalLog).filter(SignalLog.time >= cutoff)
        if status:
            q = q.filter(SignalLog.status == status)
        if symbol:
            q = q.filter(SignalLog.symbol == symbol)
        rows = q.order_by(SignalLog.time.desc()).limit(limit).all()
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([
            {
                "id": r.id,
                "time": r.time,
                "symbol": r.symbol,
                "action": r.action,
                "price": r.price,
                "stop_loss": r.stop_loss,
                "take_profit": r.take_profit,
                "atr": r.atr,
                "rsi": r.rsi,
                "strategy": r.strategy,
                "status": r.status,
                "reason": r.reason,
                "ml_confidence": r.ml_confidence,
                "ml_threshold": r.ml_threshold,
                "ticket": r.ticket,
            }
            for r in rows
        ])
    finally:
        session.close()


# ── Trade Results ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=120, show_spinner=False)
def get_trade_results(limit: int = 500, symbol: Optional[str] = None) -> pd.DataFrame:
    """Return closed trade results with P&L details."""
    session = _session()
    try:
        q = session.query(TradeResult)
        if symbol:
            q = q.filter(TradeResult.symbol == symbol)
        rows = q.order_by(TradeResult.close_time.desc()).limit(limit).all()
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([
            {
                "ticket": r.ticket,
                "symbol": r.symbol,
                "action": r.action,
                "open_price": r.open_price,
                "close_price": r.close_price,
                "open_time": r.open_time,
                "close_time": r.close_time,
                "pnl": r.pnl,
                "pnl_pips": r.pnl_pips,
                "exit_reason": r.exit_reason,
                "profitable": r.profitable,
                "ml_confidence": r.ml_confidence,
                "strategy": r.strategy,
                "news_nearby": getattr(r, "news_nearby", False),
                "news_event_name": getattr(r, "news_event_name", None),
                "news_impact": getattr(r, "news_impact", None),
            }
            for r in rows
        ])
    finally:
        session.close()


# ── Aggregated Stats ──────────────────────────────────────────────────────────

@st.cache_data(ttl=120, show_spinner=False)
def get_performance_summary() -> dict:
    """Compute high-level performance metrics from trade results."""
    df = get_trade_results(limit=10000)
    if df.empty:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "profit_factor": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
            "max_drawdown": 0.0,
            "sharpe": 0.0,
        }

    wins = df[df["pnl"] > 0]["pnl"]
    losses = df[df["pnl"] <= 0]["pnl"]

    total_win = wins.sum() if not wins.empty else 0.0
    total_loss = abs(losses.sum()) if not losses.empty else 0.0
    profit_factor = total_win / total_loss if total_loss > 0 else 0.0

    # Max drawdown from cumulative PnL
    cumulative = df.sort_values("close_time")["pnl"].cumsum()
    rolling_max = cumulative.cummax()
    drawdown = (cumulative - rolling_max)
    max_dd = drawdown.min()

    # Sharpe (daily returns approximation)
    daily = df.groupby(pd.to_datetime(df["close_time"]).dt.date)["pnl"].sum()
    sharpe = (daily.mean() / daily.std() * (252**0.5)) if len(daily) > 1 and daily.std() > 0 else 0.0

    return {
        "total_trades": len(df),
        "win_rate": len(wins) / len(df) * 100 if len(df) > 0 else 0.0,
        "total_pnl": df["pnl"].sum(),
        "profit_factor": profit_factor,
        "avg_win": wins.mean() if not wins.empty else 0.0,
        "avg_loss": losses.mean() if not losses.empty else 0.0,
        "best_trade": df["pnl"].max(),
        "worst_trade": df["pnl"].min(),
        "max_drawdown": max_dd,
        "sharpe": sharpe,
    }


@st.cache_data(ttl=120, show_spinner=False)
def get_symbol_breakdown() -> pd.DataFrame:
    """Performance breakdown per symbol."""
    df = get_trade_results(limit=10000)
    if df.empty:
        return pd.DataFrame()

    groups = []
    for symbol, g in df.groupby("symbol"):
        wins = g[g["pnl"] > 0]["pnl"]
        losses = g[g["pnl"] <= 0]["pnl"]
        total_win = wins.sum() if not wins.empty else 0.0
        total_loss = abs(losses.sum()) if not losses.empty else 1e-9
        groups.append({
            "symbol": symbol,
            "trades": len(g),
            "win_rate": len(wins) / len(g) * 100,
            "total_pnl": g["pnl"].sum(),
            "profit_factor": total_win / total_loss,
            "avg_pnl": g["pnl"].mean(),
        })
    return pd.DataFrame(groups).sort_values("total_pnl", ascending=False)


@st.cache_data(ttl=300, show_spinner=False)
def get_monthly_pnl() -> pd.DataFrame:
    """Monthly P&L aggregation."""
    df = get_trade_results(limit=10000)
    if df.empty:
        return pd.DataFrame()
    df = df.dropna(subset=["close_time"])
    df["month"] = pd.to_datetime(df["close_time"]).dt.to_period("M")
    return df.groupby("month")["pnl"].sum().reset_index().rename(columns={"month": "Month", "pnl": "PnL"})


@st.cache_data(ttl=60, show_spinner=False)
def get_signal_stats() -> dict:
    """Signal distribution stats."""
    df = get_signal_log(limit=10000, days=90)
    if df.empty:
        return {"total": 0, "executed": 0, "ml_filtered": 0, "risk_rejected": 0}
    counts = df["status"].value_counts().to_dict()
    return {
        "total": len(df),
        "executed": counts.get("EXECUTED", 0),
        "ml_filtered": counts.get("ML_FILTERED", 0),
        "news_filtered": counts.get("NEWS_FILTERED", 0),
        "risk_rejected": counts.get("RISK_REJECTED", 0),
        "error": counts.get("ERROR", 0),
    }


# ── News Events ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def get_upcoming_news(hours_ahead: int = 24) -> pd.DataFrame:
    """Return upcoming news events from DB."""
    session = _session()
    try:
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=hours_ahead)
        rows = (
            session.query(NewsEvent)
            .filter(NewsEvent.time >= now, NewsEvent.time <= cutoff)
            .order_by(NewsEvent.time)
            .all()
        )
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([
            {
                "time": r.time,
                "currency": r.currency,
                "event_name": r.event_name,
                "impact": r.impact,
                "forecast": r.forecast,
                "previous": r.previous,
                "actual": r.actual,
                "surprise": r.surprise,
            }
            for r in rows
        ])
    finally:
        session.close()


@st.cache_data(ttl=60, show_spinner=False)
def get_recent_news(hours_behind: int = 24) -> pd.DataFrame:
    """Return recent past news events from DB."""
    session = _session()
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=hours_behind)
        rows = (
            session.query(NewsEvent)
            .filter(NewsEvent.time >= cutoff, NewsEvent.time <= now)
            .order_by(NewsEvent.time.desc())
            .all()
        )
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([
            {
                "time": r.time,
                "currency": r.currency,
                "event_name": r.event_name,
                "impact": r.impact,
                "forecast": r.forecast,
                "previous": r.previous,
                "actual": r.actual,
                "surprise": r.surprise,
            }
            for r in rows
        ])
    finally:
        session.close()


@st.cache_data(ttl=300, show_spinner=False)
def get_news_stats(days: int = 30) -> dict:
    """News event statistics."""
    session = _session()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        rows = session.query(NewsEvent).filter(NewsEvent.time >= cutoff).all()
        if not rows:
            return {"total": 0, "high": 0, "medium": 0, "low": 0}
        impacts = [r.impact for r in rows]
        return {
            "total": len(rows),
            "high": impacts.count("HIGH"),
            "medium": impacts.count("MEDIUM"),
            "low": impacts.count("LOW"),
        }
    finally:
        session.close()


# ── Scan Logs ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=30, show_spinner=False)
def get_scan_logs(limit: int = 100, days: int = 7) -> pd.DataFrame:
    """Return recent scan logs."""
    session = _session()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        rows = (
            session.query(ScanLog)
            .filter(ScanLog.time >= cutoff)
            .order_by(ScanLog.time.desc())
            .limit(limit)
            .all()
        )
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([
            {
                "time": r.time,
                "scan_number": r.scan_number,
                "duration_ms": r.duration_ms,
                "signals_total": r.signals_total,
                "signals_executed": r.signals_executed,
                "signals_ml_filtered": r.signals_ml_filtered,
                "signals_news_filtered": r.signals_news_filtered,
                "signals_risk_rejected": r.signals_risk_rejected,
                "open_positions": r.open_positions,
                "balance": r.balance,
                "equity": r.equity,
                "news_blocked": r.news_blocked,
                "news_event_name": r.news_event_name,
            }
            for r in rows
        ])
    finally:
        session.close()


# ── NEW: News-Trade Cross-Reference ──────────────────────────────────────────

@st.cache_data(ttl=120, show_spinner=False)
def get_trades_near_news(hours_window: int = 1) -> pd.DataFrame:
    """Return trades that occurred near news events."""
    session = _session()
    try:
        # Get trades with news_nearby flag
        results = (
            session.query(TradeResult)
            .filter(TradeResult.news_nearby == True)
            .order_by(TradeResult.close_time.desc())
            .limit(500)
            .all()
        )
        if not results:
            return pd.DataFrame()

        data = []
        for r in results:
            data.append({
                "ticket": r.ticket,
                "symbol": r.symbol,
                "action": r.action,
                "pnl": r.pnl,
                "profitable": r.profitable,
                "open_time": r.open_time,
                "close_time": r.close_time,
                "strategy": r.strategy,
                "exit_reason": r.exit_reason,
                "news_event_name": r.news_event_name,
                "news_impact": r.news_impact,
                "ml_confidence": r.ml_confidence,
            })
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()
    finally:
        session.close()


# ── NEW: ML Predictions vs Actuals ───────────────────────────────────────────

@st.cache_data(ttl=120, show_spinner=False)
def get_ml_predictions_vs_actuals(symbol: Optional[str] = None) -> pd.DataFrame:
    """Return signal log entries that have both ml_confidence and matching trade results."""
    session = _session()
    try:
        from sqlalchemy import and_
        q = (
            session.query(
                SignalLog.symbol,
                SignalLog.ml_confidence,
                SignalLog.ticket,
                TradeResult.profitable,
                TradeResult.pnl,
            )
            .join(TradeResult, SignalLog.ticket == TradeResult.ticket)
            .filter(
                SignalLog.ml_confidence.isnot(None),
                SignalLog.ticket.isnot(None),
            )
        )
        if symbol:
            q = q.filter(SignalLog.symbol == symbol)

        rows = q.all()
        if not rows:
            return pd.DataFrame()

        return pd.DataFrame([
            {
                "symbol": r.symbol,
                "ml_confidence": r.ml_confidence,
                "ticket": r.ticket,
                "profitable": r.profitable,
                "pnl": r.pnl,
            }
            for r in rows
        ])
    except Exception:
        return pd.DataFrame()
    finally:
        session.close()


# ── NEW: Error/Connection Signals ────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def get_error_signals(days: int = 7) -> pd.DataFrame:
    """Return signals with errors or technical issues."""
    session = _session()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        from sqlalchemy import or_
        rows = (
            session.query(SignalLog)
            .filter(
                SignalLog.time >= cutoff,
                or_(
                    SignalLog.status == "ERROR",
                    SignalLog.reason.like("%filling%"),
                    SignalLog.reason.like("%AutoTrading%"),
                    SignalLog.reason.like("%No money%"),
                    SignalLog.reason.like("%connection%"),
                    SignalLog.reason.like("%Market closed%"),
                )
            )
            .order_by(SignalLog.time.desc())
            .limit(500)
            .all()
        )
        if not rows:
            return pd.DataFrame()

        data = []
        for r in rows:
            reason = r.reason or ""
            if "filling" in reason.lower():
                error_type = "Filling Mode"
            elif "autotrading" in reason.lower():
                error_type = "AutoTrading Disabled"
            elif "no money" in reason.lower():
                error_type = "No Money"
            elif "market closed" in reason.lower():
                error_type = "Market Closed"
            elif "connection" in reason.lower():
                error_type = "Connection Error"
            else:
                error_type = "Other Error"

            data.append({
                "time": r.time,
                "symbol": r.symbol,
                "action": r.action,
                "strategy": r.strategy,
                "status": r.status,
                "reason": reason,
                "error_type": error_type,
            })
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()
    finally:
        session.close()


# ── NEW: Daily Report Data ───────────────────────────────────────────────────

def get_daily_report_data(report_date: Optional[date] = None) -> dict:
    """Collect all data for a daily report."""
    if report_date is None:
        report_date = datetime.now(timezone.utc).date()

    day_start = datetime.combine(report_date, datetime.min.time())
    day_end = datetime.combine(report_date, datetime.max.time())

    session = _session()
    try:
        # Trades opened or closed today
        trades_closed = session.query(Trade).filter(
            Trade.is_closed == True,
            Trade.close_time >= day_start,
            Trade.close_time <= day_end,
        ).all()

        trades_opened = session.query(Trade).filter(
            Trade.open_time >= day_start,
            Trade.open_time <= day_end,
        ).all()

        open_positions = session.query(Trade).filter(Trade.is_closed == False).all()

        # Signals today
        signals = session.query(SignalLog).filter(
            SignalLog.time >= day_start,
            SignalLog.time <= day_end,
        ).all()

        # Latest snapshot
        snap = session.query(AccountSnapshot).order_by(AccountSnapshot.time.desc()).first()

        # Errors today
        from sqlalchemy import or_
        errors = session.query(SignalLog).filter(
            SignalLog.time >= day_start,
            SignalLog.time <= day_end,
            or_(
                SignalLog.status == "ERROR",
                SignalLog.reason.like("%filling%"),
                SignalLog.reason.like("%AutoTrading%"),
                SignalLog.reason.like("%No money%"),
            )
        ).all()

        # Build report
        closed_pnl = sum(t.profit or 0 for t in trades_closed)
        closed_wins = sum(1 for t in trades_closed if (t.profit or 0) > 0)
        closed_losses = sum(1 for t in trades_closed if (t.profit or 0) < 0)

        signal_counts = {}
        for s in signals:
            signal_counts[s.status] = signal_counts.get(s.status, 0) + 1

        return {
            "date": str(report_date),
            "balance": snap.balance if snap else 0,
            "equity": snap.equity if snap else 0,
            "pnl": closed_pnl,
            "trades_closed": len(trades_closed),
            "trades_opened": len(trades_opened),
            "open_count": len(open_positions),
            "wins": closed_wins,
            "losses": closed_losses,
            "win_rate": (closed_wins / len(trades_closed) * 100) if trades_closed else 0,
            "signals_total": len(signals),
            "signals_executed": signal_counts.get("EXECUTED", 0),
            "signals_rejected": signal_counts.get("RISK_REJECTED", 0),
            "signals_ml_filtered": signal_counts.get("ML_FILTERED", 0),
            "signals_news_filtered": signal_counts.get("NEWS_FILTERED", 0),
            "errors_count": len(errors),
            "closed_trades_detail": [
                {
                    "ticket": t.ticket,
                    "symbol": t.symbol,
                    "order_type": t.order_type,
                    "profit": t.profit,
                    "strategy": t.strategy,
                }
                for t in trades_closed
            ],
            "open_positions_detail": [
                {
                    "ticket": t.ticket,
                    "symbol": t.symbol,
                    "order_type": t.order_type,
                    "profit": t.profit,
                    "open_price": t.open_price,
                    "stop_loss": t.stop_loss,
                    "take_profit": t.take_profit,
                    "strategy": t.strategy,
                }
                for t in open_positions
            ],
            "error_details": [
                {"time": str(e.time), "symbol": e.symbol, "reason": e.reason}
                for e in errors
            ],
        }
    finally:
        session.close()


# ── NEW: Connection Timeline ─────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def get_connection_timeline(days: int = 7) -> pd.DataFrame:
    """Return scan timestamps to identify connection gaps."""
    session = _session()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        rows = (
            session.query(ScanLog.time, ScanLog.scan_number, ScanLog.balance, ScanLog.equity)
            .filter(ScanLog.time >= cutoff)
            .order_by(ScanLog.time)
            .all()
        )
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([
            {"time": r.time, "scan_number": r.scan_number, "balance": r.balance, "equity": r.equity}
            for r in rows
        ])
    except Exception:
        return pd.DataFrame()
    finally:
        session.close()
