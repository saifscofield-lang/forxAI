"""
Trade Chart - Visualize trades with entry, SL, TP on candlestick chart.
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sqlite3
import os

st.title("📈 Trade Chart")
st.caption("Visualize trades on price chart with Entry, SL, TP levels.")

# ── Load trades from DB ──────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_trades():
    db = sqlite3.connect("data/trading.db")
    df = pd.read_sql_query("""
        SELECT ticket, symbol, order_type, volume, open_price, close_price,
               open_time, close_time, profit, stop_loss, take_profit, strategy
        FROM trades WHERE is_closed=1
        ORDER BY close_time DESC
    """, db)
    db.close()
    return df


@st.cache_data(ttl=60)
def load_open_trades():
    db = sqlite3.connect("data/trading.db")
    df = pd.read_sql_query("""
        SELECT ticket, symbol, order_type, volume, open_price, profit,
               stop_loss, take_profit, strategy, open_time
        FROM trades WHERE is_closed=0
    """, db)
    db.close()
    return df


@st.cache_data(ttl=300)
def load_candles(symbol, timeframe="H1", bars=500):
    path = f"data/raw/{symbol}/{timeframe}.parquet"
    if os.path.exists(path):
        df = pd.read_parquet(path)
        return df.tail(bars)
    return pd.DataFrame()


trades = load_trades()
open_trades = load_open_trades()

if trades.empty and open_trades.empty:
    st.info("No trades found. Start the bot to collect data.")
    st.stop()

# ── Controls ─────────────────────────────────────────────────────────────────
all_symbols = sorted(set(
    trades["symbol"].unique().tolist() +
    (open_trades["symbol"].unique().tolist() if not open_trades.empty else [])
))

col1, col2, col3 = st.columns([2, 2, 2])
with col1:
    symbol = st.selectbox("Symbol", all_symbols, index=0)
with col2:
    timeframe = st.selectbox("Timeframe", ["H1", "H4", "D1"], index=0)
with col3:
    show_count = st.selectbox("Show last N trades", [5, 10, 20, 50, "All"], index=1)

# Filter trades for selected symbol
sym_trades = trades[trades["symbol"] == symbol].copy()
sym_open = open_trades[open_trades["symbol"] == symbol].copy() if not open_trades.empty else pd.DataFrame()

if show_count != "All":
    sym_trades = sym_trades.head(int(show_count))

# ── Trade Summary Table ──────────────────────────────────────────────────────
st.subheader(f"{symbol} Trades ({len(sym_trades)} closed, {len(sym_open)} open)")

if not sym_trades.empty:
    total_pnl = sym_trades["profit"].sum()
    wins = (sym_trades["profit"] > 0).sum()
    losses = (sym_trades["profit"] < 0).sum()
    wr = wins / len(sym_trades) * 100 if len(sym_trades) > 0 else 0

    mc1, mc2, mc3, mc4 = st.columns(4)
    with mc1:
        st.metric("Total PnL", f"${total_pnl:+,.2f}",
                  delta_color="normal" if total_pnl >= 0 else "inverse")
    with mc2:
        st.metric("Win Rate", f"{wr:.1f}%")
    with mc3:
        st.metric("Wins / Losses", f"{wins}W / {losses}L")
    with mc4:
        avg_pnl = sym_trades["profit"].mean()
        st.metric("Avg PnL", f"${avg_pnl:+,.2f}",
                  delta_color="normal" if avg_pnl >= 0 else "inverse")

# ── Candlestick Chart with Trades ────────────────────────────────────────────
candles = load_candles(symbol, timeframe)

if candles.empty:
    st.warning(f"No candle data for {symbol}/{timeframe}. Run `python scripts/download_historical_data.py` first.")
    st.info("Showing trade table only.")
else:
    st.subheader("Price Chart with Trades")

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.8, 0.2], vertical_spacing=0.02)

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=candles.index.tolist() if hasattr(candles.index, 'strftime') else list(range(len(candles))),
        open=candles["open"], high=candles["high"],
        low=candles["low"], close=candles["close"],
        name="Price", increasing_line_color="#00C851", decreasing_line_color="#FF4444",
    ), row=1, col=1)

    # Volume bars
    if "volume" in candles.columns:
        colors = ["#00C851" if c >= o else "#FF4444"
                  for c, o in zip(candles["close"], candles["open"])]
        fig.add_trace(go.Bar(
            x=candles.index.tolist() if hasattr(candles.index, 'strftime') else list(range(len(candles))),
            y=candles["volume"], name="Volume",
            marker_color=colors, opacity=0.5,
        ), row=2, col=1)

    # Plot closed trades
    for _, trade in sym_trades.iterrows():
        try:
            open_time = pd.to_datetime(trade["open_time"])
            close_time = pd.to_datetime(trade["close_time"])
            is_buy = trade["order_type"] == "BUY"
            is_win = trade["profit"] > 0

            entry = trade["open_price"]
            exit_p = trade["close_price"]
            sl = trade["stop_loss"]
            tp = trade["take_profit"]

            # Entry marker
            fig.add_trace(go.Scatter(
                x=[open_time], y=[entry],
                mode="markers",
                marker=dict(
                    symbol="triangle-up" if is_buy else "triangle-down",
                    size=12,
                    color="#00C851" if is_buy else "#FF4444",
                    line=dict(width=1, color="white"),
                ),
                name=f"{'BUY' if is_buy else 'SELL'} {entry:.5f}",
                showlegend=False,
                hovertemplate=(
                    f"<b>{'BUY' if is_buy else 'SELL'} Entry</b><br>"
                    f"Price: {entry}<br>"
                    f"SL: {sl}<br>"
                    f"TP: {tp}<br>"
                    f"Strategy: {trade['strategy']}<br>"
                    f"<extra></extra>"
                ),
            ), row=1, col=1)

            # Exit marker
            fig.add_trace(go.Scatter(
                x=[close_time], y=[exit_p],
                mode="markers",
                marker=dict(
                    symbol="x",
                    size=10,
                    color="#00E676" if is_win else "#FF1744",
                    line=dict(width=2, color="#00E676" if is_win else "#FF1744"),
                ),
                name=f"Exit ${trade['profit']:+,.2f}",
                showlegend=False,
                hovertemplate=(
                    f"<b>EXIT {'WIN' if is_win else 'LOSS'}</b><br>"
                    f"Price: {exit_p}<br>"
                    f"PnL: ${trade['profit']:+,.2f}<br>"
                    f"<extra></extra>"
                ),
            ), row=1, col=1)

            # Trade line (entry to exit)
            fig.add_trace(go.Scatter(
                x=[open_time, close_time], y=[entry, exit_p],
                mode="lines",
                line=dict(
                    color="#00E676" if is_win else "#FF1744",
                    width=1, dash="dot",
                ),
                showlegend=False, hoverinfo="skip",
            ), row=1, col=1)

            # SL line
            if sl and sl > 0:
                fig.add_trace(go.Scatter(
                    x=[open_time, close_time], y=[sl, sl],
                    mode="lines",
                    line=dict(color="#FF4444", width=1, dash="dash"),
                    showlegend=False, hoverinfo="skip",
                ), row=1, col=1)

            # TP line
            if tp and tp > 0:
                fig.add_trace(go.Scatter(
                    x=[open_time, close_time], y=[tp, tp],
                    mode="lines",
                    line=dict(color="#00C851", width=1, dash="dash"),
                    showlegend=False, hoverinfo="skip",
                ), row=1, col=1)

        except Exception:
            continue

    # Plot open trades
    for _, trade in sym_open.iterrows():
        try:
            open_time = pd.to_datetime(trade["open_time"])
            is_buy = trade["order_type"] == "BUY"
            entry = trade["open_price"]
            sl = trade["stop_loss"]
            tp = trade["take_profit"]

            # Entry marker (larger for open)
            fig.add_trace(go.Scatter(
                x=[open_time], y=[entry],
                mode="markers+text",
                marker=dict(
                    symbol="triangle-up" if is_buy else "triangle-down",
                    size=16,
                    color="#FFD600",
                    line=dict(width=2, color="white"),
                ),
                text=[f"OPEN {'BUY' if is_buy else 'SELL'}"],
                textposition="top center",
                textfont=dict(color="#FFD600", size=10),
                showlegend=False,
                hovertemplate=(
                    f"<b>OPEN {'BUY' if is_buy else 'SELL'}</b><br>"
                    f"Entry: {entry}<br>"
                    f"SL: {sl}<br>"
                    f"TP: {tp}<br>"
                    f"PnL: ${trade['profit']:+,.2f}<br>"
                    f"<extra></extra>"
                ),
            ), row=1, col=1)

            # SL line (extend to right edge)
            if sl and sl > 0:
                last_time = candles.index[-1] if hasattr(candles.index, 'strftime') else len(candles)
                fig.add_hline(y=sl, line_dash="dash", line_color="#FF4444",
                              annotation_text=f"SL {sl:.5f}", row=1, col=1)

            # TP line
            if tp and tp > 0:
                fig.add_hline(y=tp, line_dash="dash", line_color="#00C851",
                              annotation_text=f"TP {tp:.5f}", row=1, col=1)

        except Exception:
            continue

    fig.update_layout(
        paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
        font=dict(color="#FAFAFA"),
        title=f"{symbol} - Trades on {timeframe} Chart",
        xaxis_rangeslider_visible=False,
        xaxis2=dict(gridcolor="#1E2130"),
        yaxis=dict(gridcolor="#1E2130", title="Price"),
        yaxis2=dict(gridcolor="#1E2130", title="Volume"),
        height=700,
        margin=dict(l=60, r=20, t=50, b=20),
    )

    st.plotly_chart(fig, width="stretch")

# ── Trade Details Table ──────────────────────────────────────────────────────
st.subheader("Trade Details")

tab1, tab2 = st.tabs(["Closed Trades", "Open Trades"])

with tab1:
    if not sym_trades.empty:
        display = sym_trades[["ticket", "order_type", "volume", "open_price", "close_price",
                              "stop_loss", "take_profit", "profit", "strategy", "open_time", "close_time"]].copy()

        def color_pnl(val):
            if isinstance(val, (int, float)):
                return "color: #00C851" if val >= 0 else "color: #FF4444"
            return ""

        fmt = {"profit": "${:+,.2f}", "open_price": "{:.5f}", "close_price": "{:.5f}",
               "stop_loss": "{:.5f}", "take_profit": "{:.5f}", "volume": "{:.2f}"}
        styled = display.style.format(fmt).map(color_pnl, subset=["profit"])
        st.dataframe(styled, width="stretch", hide_index=True)

        # PnL distribution chart
        fig_pnl = go.Figure()
        colors = ["#00C851" if p > 0 else "#FF4444" for p in sym_trades["profit"]]
        fig_pnl.add_trace(go.Bar(
            x=list(range(len(sym_trades))),
            y=sym_trades["profit"].values,
            marker_color=colors,
            hovertemplate="Trade %{x}<br>PnL: $%{y:+,.2f}<extra></extra>",
        ))
        fig_pnl.update_layout(
            paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
            font=dict(color="#FAFAFA"),
            title=f"{symbol} - PnL per Trade",
            xaxis=dict(title="Trade #", gridcolor="#1E2130"),
            yaxis=dict(title="PnL ($)", gridcolor="#1E2130"),
            height=300,
        )
        st.plotly_chart(fig_pnl, width="stretch")
    else:
        st.info(f"No closed trades for {symbol}")

with tab2:
    if not sym_open.empty:
        fmt = {"profit": "${:+,.2f}", "open_price": "{:.5f}",
               "stop_loss": "{:.5f}", "take_profit": "{:.5f}", "volume": "{:.2f}"}
        st.dataframe(sym_open.style.format(fmt), width="stretch", hide_index=True)
    else:
        st.info(f"No open trades for {symbol}")

# ── Strategy Breakdown ───────────────────────────────────────────────────────
if not sym_trades.empty:
    st.subheader(f"{symbol} - By Strategy")
    strat_stats = sym_trades.groupby("strategy").agg(
        trades=("profit", "count"),
        wins=("profit", lambda x: (x > 0).sum()),
        losses=("profit", lambda x: (x < 0).sum()),
        pnl=("profit", "sum"),
        avg_pnl=("profit", "mean"),
    ).reset_index()
    strat_stats["win_rate"] = (strat_stats["wins"] / strat_stats["trades"] * 100).round(1)

    fmt = {"pnl": "${:+,.2f}", "avg_pnl": "${:+,.2f}", "win_rate": "{:.1f}%"}
    st.dataframe(strat_stats.style.format(fmt), width="stretch", hide_index=True)
