"""
صفحة الصفقات المفتوحة
عرض جميع صفقات MT5 المفتوحة وإغلاقها يدوياً.
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import pandas as pd
from datetime import datetime

st.title("📊 الصفقات المفتوحة")
st.caption("الصفقات الحية من MT5 — حدّث لرؤية الربح/الخسارة الحالية.")

# ── Controls ──────────────────────────────────────────────────────────────────
col_btn, col_space = st.columns([2, 6])
with col_btn:
    refresh = st.button("🔄 تحديث الصفقات", type="primary", use_container_width=True)

# ── Load Data ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=15, show_spinner=False)
def _load_positions():
    from dashboard.utils.mt5_helper import get_open_positions, get_account_info
    positions = get_open_positions()
    account = get_account_info()
    return positions, account

if refresh:
    st.cache_data.clear()

positions_df, account = _load_positions()

# ── Account Summary ───────────────────────────────────────────────────────────
if account:
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("الرصيد", f"${account.get('balance', 0):,.2f}")
    with col2:
        st.metric("الملكية", f"${account.get('equity', 0):,.2f}")
    with col3:
        profit = account.get("profit", 0)
        st.metric("الربح المفتوح", f"${profit:+,.2f}",
                  delta_color="normal" if profit >= 0 else "inverse")
    with col4:
        st.metric("الهامش المستخدم", f"${account.get('margin', 0):,.2f}")
    with col5:
        st.metric("الهامش المتاح", f"${account.get('free_margin', 0):,.2f}")
else:
    st.warning("MT5 غير متصل — عرض سجلات قاعدة البيانات بدلاً من ذلك.")

st.divider()

# ── Positions Table ───────────────────────────────────────────────────────────
# Try MT5 live positions first, fall back to DB
if positions_df is not None and not positions_df.empty:
    st.subheader(f"الصفقات الحية ({len(positions_df)})")

    # Color P&L
    def color_pnl(val):
        if isinstance(val, (int, float)):
            return "color: #00C851" if val >= 0 else "color: #FF4444"
        return ""

    display_df = positions_df.copy()

    # ── Add Monitor Phase Info ────────────────────────────────────────────────
    from dashboard.utils.db import get_monitor_states
    monitor_states = get_monitor_states()

    PHASE_LABELS = {
        0: "⏳ انتظار",
        1: "🔒 بريك إيفن",
        2: "🎯 TP1 (50%)",
        3: "📈 تتبع",
        4: "🔥 تتبع ضيق",
    }

    ticket_col = "ticket" if "ticket" in display_df.columns else None
    if ticket_col:
        display_df["المرحلة"] = display_df[ticket_col].apply(
            lambda t: PHASE_LABELS.get(monitor_states.get(t, {}).get("phase", 0), "⏳ انتظار")
        )
        display_df["إغلاق جزئي"] = display_df[ticket_col].apply(
            lambda t: "✅" if monitor_states.get(t, {}).get("tp1_closed", False) else "—"
        )
        display_df["الحجم الأصلي"] = display_df[ticket_col].apply(
            lambda t: monitor_states.get(t, {}).get("original_volume")
        )

    # Identify P&L column (different MT5 adapters may use different names)
    pnl_col = None
    for candidate in ["profit", "pnl", "unrealized_pnl"]:
        if candidate in display_df.columns:
            pnl_col = candidate
            break

    fmt = {}
    for col in ["open_price", "current_price", "price_open", "price_current", "sl", "tp",
                "stop_loss", "take_profit"]:
        if col in display_df.columns:
            fmt[col] = "{:.5f}"
    if pnl_col:
        fmt[pnl_col] = "${:+,.2f}"
    if "volume" in display_df.columns:
        fmt["volume"] = "{:.2f}"
    if "الحجم الأصلي" in display_df.columns:
        fmt["الحجم الأصلي"] = lambda x: f"{x:.2f}" if pd.notna(x) else "—"

    styled = display_df.style.format(fmt)
    if pnl_col:
        styled = styled.map(color_pnl, subset=[pnl_col])

    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Close Position ────────────────────────────────────────────────────────
    st.divider()
    st.subheader("إغلاق صفقة")
    st.caption("⚠️ سيتم إغلاق الصفقة فوراً بسعر السوق.")

    # Build ticket list
    ticket_col = "ticket" if "ticket" in positions_df.columns else positions_df.columns[0]
    tickets = positions_df[ticket_col].tolist()
    symbol_col = "symbol" if "symbol" in positions_df.columns else None

    if symbol_col:
        options = [
            f"{row[ticket_col]} — {row[symbol_col]} {row.get('type', '')}"
            for _, row in positions_df.iterrows()
        ]
    else:
        options = [str(t) for t in tickets]

    col_sel, col_close = st.columns([4, 2])
    with col_sel:
        selected_idx = st.selectbox("اختر الصفقة للإغلاق", range(len(options)),
                                     format_func=lambda i: options[i])
    with col_close:
        st.write("")  # spacing
        st.write("")
        if st.button("❌ إغلاق الصفقة", type="primary", use_container_width=True):
            ticket = tickets[selected_idx]
            with st.spinner(f"جاري إغلاق التذكرة {ticket}..."):
                from dashboard.utils.mt5_helper import close_position
                success, msg = close_position(int(ticket))
            if success:
                st.success(msg)
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(f"فشل الإغلاق: {msg}")

else:
    # Fall back to DB open trades with live PnL from last scan
    from dashboard.utils.db import get_open_trades
    import sqlite3

    db_trades = get_open_trades()

    if db_trades.empty:
        st.markdown("""
        <div style="text-align:center;padding:60px 0;color:#666">
            <h3>لا توجد صفقات مفتوحة</h3>
            <p>انتقل إلى <b>الماسح</b> للبحث عن إشارات وتنفيذها</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.subheader(f"صفقات من قاعدة البيانات ({len(db_trades)})")

        # Try to get last known PnL from account snapshot
        try:
            conn = sqlite3.connect("data/trading.db")
            snap = pd.read_sql_query(
                "SELECT balance, equity, profit FROM account_snapshots ORDER BY id DESC LIMIT 1",
                conn
            )
            conn.close()
            if not snap.empty:
                total_open_pnl = snap.iloc[0].get("profit", 0) or 0
                st.caption(f"آخر تحديث من المحرك — الربح المفتوح الإجمالي: ${total_open_pnl:+,.2f}")
            else:
                st.caption("بيانات MT5 الحية غير متاحة — عرض السجلات المحفوظة")
        except Exception:
            st.caption("بيانات MT5 الحية غير متاحة — عرض السجلات المحفوظة")

        # Drop the zero profit column and show useful info
        display_cols = [c for c in db_trades.columns if c != "profit"]
        display_df = db_trades[display_cols] if display_cols else db_trades

        fmt = {}
        for col in ["open_price", "stop_loss", "take_profit"]:
            if col in display_df.columns:
                fmt[col] = "{:.5f}"
        if "volume" in display_df.columns:
            fmt["volume"] = "{:.2f}"

        st.dataframe(display_df.style.format(fmt), use_container_width=True, hide_index=True)

# ── Position Size Calculator ──────────────────────────────────────────────────
st.divider()
st.subheader("حاسبة حجم الصفقة")
st.caption("حساب حجم اللوت بناءً على معايير المخاطرة.")

col_a, col_b, col_c, col_d = st.columns(4)
with col_a:
    balance = st.number_input("رصيد الحساب ($)", value=100000.0, step=1000.0)
with col_b:
    risk_pct = st.number_input("نسبة المخاطرة %", value=1.0, min_value=0.1, max_value=10.0, step=0.1)
with col_c:
    sl_pips = st.number_input("وقف الخسارة (نقاط)", value=20, min_value=1, step=1)
with col_d:
    pip_val = st.selectbox("نوع الزوج", ["فوركس (0.0001)", "ين (0.01)", "ذهب (0.01)"])
    pip_value_map = {"فوركس (0.0001)": 0.0001, "ين (0.01)": 0.01, "ذهب (0.01)": 0.01}
    pip_value = pip_value_map[pip_val]

risk_amount = balance * (risk_pct / 100)
lot_size = risk_amount / (sl_pips * pip_value * 100000) if sl_pips > 0 else 0

col_r1, col_r2, col_r3 = st.columns(3)
with col_r1:
    st.metric("مبلغ المخاطرة", f"${risk_amount:,.2f}")
with col_r2:
    st.metric("حجم اللوت", f"{lot_size:.2f} لوت")
with col_r3:
    st.metric("قيمة النقطة", f"${pip_value * lot_size * 100000:.2f} / نقطة")
