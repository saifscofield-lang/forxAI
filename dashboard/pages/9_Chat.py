"""
Trading Chat - Ask questions about your trades, performance, and data.
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta

st.title("💬 Trading Chat")
st.caption("Ask questions about your trades, performance, and data.")

# ── Database helper ──────────────────────────────────────────────────────────
def query_db(sql, params=None):
    """Run a SQL query and return DataFrame."""
    db = sqlite3.connect("data/trading.db")
    try:
        return pd.read_sql_query(sql, db, params=params or [])
    except Exception as e:
        return pd.DataFrame({"error": [str(e)]})
    finally:
        db.close()


def get_balance():
    df = query_db("SELECT balance, equity FROM account_snapshots ORDER BY id DESC LIMIT 1")
    if df.empty:
        return 0, 0
    return df.iloc[0]["balance"], df.iloc[0].get("equity", 0)


def get_overview():
    total = query_db("SELECT COUNT(*) as c FROM trades").iloc[0]["c"]
    closed = query_db("SELECT COUNT(*) as c FROM trades WHERE is_closed=1").iloc[0]["c"]
    open_t = query_db("SELECT COUNT(*) as c FROM trades WHERE is_closed=0").iloc[0]["c"]
    wins = query_db("SELECT COUNT(*) as c FROM trades WHERE is_closed=1 AND profit>0").iloc[0]["c"]
    losses = query_db("SELECT COUNT(*) as c FROM trades WHERE is_closed=1 AND profit<0").iloc[0]["c"]
    pnl = query_db("SELECT COALESCE(SUM(profit),0) as p FROM trades WHERE is_closed=1").iloc[0]["p"]
    balance, equity = get_balance()
    wr = (wins / closed * 100) if closed > 0 else 0
    return {
        "total": total, "closed": closed, "open": open_t,
        "wins": wins, "losses": losses, "pnl": pnl,
        "balance": balance, "equity": equity, "win_rate": wr,
    }


def get_open_positions():
    return query_db("""
        SELECT ticket, symbol, order_type, volume, open_price, profit, stop_loss, take_profit, strategy, open_time
        FROM trades WHERE is_closed=0
    """)


def get_today_trades():
    return query_db("""
        SELECT ticket, symbol, order_type, volume, open_price, close_price, profit, strategy, close_time
        FROM trades WHERE is_closed=1 AND date(close_time)=date('now')
        ORDER BY close_time DESC
    """)


def get_best_worst_trades(n=5):
    best = query_db(f"SELECT ticket, symbol, order_type, profit, strategy, close_time FROM trades WHERE is_closed=1 ORDER BY profit DESC LIMIT {n}")
    worst = query_db(f"SELECT ticket, symbol, order_type, profit, strategy, close_time FROM trades WHERE is_closed=1 ORDER BY profit ASC LIMIT {n}")
    return best, worst


def get_strategy_stats():
    return query_db("""
        SELECT strategy,
               COUNT(*) as trades,
               SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END) as wins,
               SUM(CASE WHEN profit<0 THEN 1 ELSE 0 END) as losses,
               ROUND(SUM(CASE WHEN profit>0 THEN 1.0 ELSE 0 END)/COUNT(*)*100, 1) as win_rate,
               ROUND(COALESCE(SUM(profit),0), 2) as pnl
        FROM trades WHERE is_closed=1
        GROUP BY strategy ORDER BY pnl DESC
    """)


def get_symbol_stats():
    return query_db("""
        SELECT symbol,
               COUNT(*) as trades,
               SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END) as wins,
               SUM(CASE WHEN profit<0 THEN 1 ELSE 0 END) as losses,
               ROUND(SUM(CASE WHEN profit>0 THEN 1.0 ELSE 0 END)/COUNT(*)*100, 1) as win_rate,
               ROUND(COALESCE(SUM(profit),0), 2) as pnl
        FROM trades WHERE is_closed=1
        GROUP BY symbol ORDER BY pnl DESC
    """)


def get_recent_trades(n=10):
    return query_db(f"""
        SELECT ticket, symbol, order_type, volume, open_price, close_price, profit, strategy, close_time
        FROM trades WHERE is_closed=1 ORDER BY close_time DESC LIMIT {n}
    """)


def get_trade_by_ticket(ticket):
    return query_db("SELECT * FROM trades WHERE ticket=?", [ticket])


def get_daily_pnl(days=7):
    return query_db(f"""
        SELECT date(close_time) as day,
               COUNT(*) as trades,
               SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END) as wins,
               ROUND(SUM(profit),2) as pnl
        FROM trades WHERE is_closed=1 AND close_time >= date('now', '-{days} days')
        GROUP BY date(close_time) ORDER BY day DESC
    """)


def get_scan_count():
    df = query_db("SELECT COUNT(*) as c FROM scan_logs")
    return df.iloc[0]["c"] if not df.empty else 0


# ── Chat Logic ───────────────────────────────────────────────────────────────
def process_question(q):
    """Process user question and return answer."""
    q_lower = q.lower().strip()

    # Balance / Account
    if any(w in q_lower for w in ["balance", "account", "equity", "money", "capital"]):
        o = get_overview()
        return (
            f"**Account Status:**\n"
            f"- Balance: **${o['balance']:,.2f}**\n"
            f"- Total PnL (closed): **${o['pnl']:+,.2f}**\n"
            f"- Total Trades: {o['total']} ({o['closed']} closed, {o['open']} open)\n"
            f"- Wins: {o['wins']} | Losses: {o['losses']} | Win Rate: {o['win_rate']:.1f}%"
        )

    # Open positions
    if any(w in q_lower for w in ["open position", "open trade", "current position", "running"]):
        df = get_open_positions()
        if df.empty:
            return "No open positions right now."
        lines = ["**Open Positions:**"]
        for _, r in df.iterrows():
            lines.append(
                f"- #{r['ticket']} {r['order_type']} {r['symbol']} {r['volume']}lots | "
                f"Entry: {r['open_price']} | SL: {r['stop_loss']} | TP: {r['take_profit']} | "
                f"Strategy: {r['strategy']}"
            )
        return "\n".join(lines)

    # Today
    if any(w in q_lower for w in ["today", "this day"]):
        df = get_today_trades()
        if df.empty:
            return "No closed trades today."
        total_pnl = df["profit"].sum()
        wins = (df["profit"] > 0).sum()
        losses = (df["profit"] < 0).sum()
        lines = [f"**Today: {len(df)} trades | {wins}W/{losses}L | PnL: ${total_pnl:+,.2f}**"]
        for _, r in df.iterrows():
            lines.append(f"- #{r['ticket']} {r['order_type']} {r['symbol']} | ${r['profit']:+,.2f} | {r['strategy']}")
        return "\n".join(lines)

    # Best / worst trades
    if any(w in q_lower for w in ["best trade", "top trade", "biggest win"]):
        best, _ = get_best_worst_trades()
        lines = ["**Top 5 Best Trades:**"]
        for _, r in best.iterrows():
            lines.append(f"- #{r['ticket']} {r['order_type']} {r['symbol']} | **${r['profit']:+,.2f}** | {r['strategy']} | {r['close_time']}")
        return "\n".join(lines)

    if any(w in q_lower for w in ["worst trade", "biggest loss", "worst"]):
        _, worst = get_best_worst_trades()
        lines = ["**Top 5 Worst Trades:**"]
        for _, r in worst.iterrows():
            lines.append(f"- #{r['ticket']} {r['order_type']} {r['symbol']} | **${r['profit']:+,.2f}** | {r['strategy']} | {r['close_time']}")
        return "\n".join(lines)

    # Strategy performance
    if any(w in q_lower for w in ["strategy", "strategies", "which strategy"]):
        df = get_strategy_stats()
        lines = ["**Strategy Performance:**"]
        for _, r in df.iterrows():
            lines.append(f"- **{r['strategy']}**: {r['trades']} trades | {r['wins']}W/{r['losses']}L | WR: {r['win_rate']}% | PnL: ${r['pnl']:+,.2f}")
        return "\n".join(lines)

    # Symbol performance
    if any(w in q_lower for w in ["symbol", "pair", "which pair", "which symbol", "instrument"]):
        df = get_symbol_stats()
        lines = ["**Symbol Performance:**"]
        for _, r in df.iterrows():
            lines.append(f"- **{r['symbol']}**: {r['trades']} trades | {r['wins']}W/{r['losses']}L | WR: {r['win_rate']}% | PnL: ${r['pnl']:+,.2f}")
        return "\n".join(lines)

    # Recent trades
    if any(w in q_lower for w in ["recent", "last trade", "latest", "history"]):
        df = get_recent_trades()
        lines = [f"**Last {len(df)} Trades:**"]
        for _, r in df.iterrows():
            lines.append(f"- #{r['ticket']} {r['order_type']} {r['symbol']} {r['volume']}lots | ${r['profit']:+,.2f} | {r['strategy']} | {r['close_time']}")
        return "\n".join(lines)

    # Ticket lookup
    if any(w in q_lower for w in ["ticket", "#"]):
        import re
        numbers = re.findall(r'\d{8,}', q)
        if numbers:
            df = get_trade_by_ticket(int(numbers[0]))
            if df.empty:
                return f"Trade #{numbers[0]} not found."
            r = df.iloc[0]
            return (
                f"**Trade #{r['ticket']}**\n"
                f"- {r['order_type']} {r['symbol']} {r['volume']} lots\n"
                f"- Entry: {r['open_price']} | Close: {r.get('close_price', 'Open')}\n"
                f"- SL: {r['stop_loss']} | TP: {r['take_profit']}\n"
                f"- PnL: ${r['profit']:+,.2f}\n"
                f"- Strategy: {r['strategy']}\n"
                f"- Opened: {r['open_time']}\n"
                f"- Closed: {r.get('close_time', 'Still open')}\n"
                f"- Status: {'Closed' if r['is_closed'] else 'Open'}"
            )

    # Daily PnL
    if any(w in q_lower for w in ["daily", "per day", "day by day", "weekly"]):
        df = get_daily_pnl(14)
        if df.empty:
            return "No daily data available."
        lines = ["**Daily PnL (last 14 days):**"]
        for _, r in df.iterrows():
            lines.append(f"- {r['day']}: {r['trades']} trades | {r['wins']}W | PnL: ${r['pnl']:+,.2f}")
        return "\n".join(lines)

    # Scan count
    if any(w in q_lower for w in ["scan", "how many scan"]):
        c = get_scan_count()
        return f"Total scans completed: **{c}**"

    # Win rate
    if any(w in q_lower for w in ["win rate", "winrate", "win %"]):
        o = get_overview()
        return f"Overall win rate: **{o['win_rate']:.1f}%** ({o['wins']}W / {o['losses']}L out of {o['closed']} closed trades)"

    # Profit
    if any(w in q_lower for w in ["profit", "pnl", "p&l", "gain", "loss", "how much"]):
        o = get_overview()
        return (
            f"**Profit Summary:**\n"
            f"- Net PnL: **${o['pnl']:+,.2f}**\n"
            f"- Balance: ${o['balance']:,.2f}\n"
            f"- Started with: $100,000\n"
            f"- Return: {o['pnl']/1000:.2f}%"
        )

    # Help
    if any(w in q_lower for w in ["help", "what can", "command"]):
        return (
            "**You can ask me:**\n"
            "- `balance` / `account` - Account status\n"
            "- `open positions` - Current running trades\n"
            "- `today` - Today's trades\n"
            "- `recent` / `last trades` - Last 10 trades\n"
            "- `best trades` / `worst trades` - Top winners/losers\n"
            "- `strategy` - Strategy performance\n"
            "- `symbol` / `pairs` - Symbol performance\n"
            "- `daily` - Daily PnL breakdown\n"
            "- `profit` / `pnl` - Profit summary\n"
            "- `win rate` - Win rate stats\n"
            "- `#55841108281` - Look up specific trade by ticket\n"
            "- `scans` - Total scan count"
        )

    # Default
    return (
        "I didn't understand that. Try asking about:\n"
        "`balance`, `open positions`, `today`, `recent trades`, `strategy`, "
        "`symbol`, `best trades`, `worst trades`, `daily`, `profit`, `win rate`, "
        "or a ticket number like `#55841108281`.\n\n"
        "Type `help` for full list."
    )


# ── Chat UI ──────────────────────────────────────────────────────────────────
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = [
        {"role": "assistant", "content": "Hi! Ask me anything about your trades. Type `help` to see what I can answer."}
    ]

# Display chat history
for msg in st.session_state.chat_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
if prompt := st.chat_input("Ask about your trades..."):
    # Show user message
    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Process and show response
    response = process_question(prompt)
    st.session_state.chat_messages.append({"role": "assistant", "content": response})
    with st.chat_message("assistant"):
        st.markdown(response)
