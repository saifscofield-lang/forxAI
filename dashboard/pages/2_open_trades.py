"""
صفحة الصفقات المفتوحة
عرض الصفقات الحية مع شارت تفاعلي + تحليل فني + حالة المونيتور.
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import os

st.title("الصفقات المفتوحة")
st.caption("اضغط على أي صفقة لعرض الشارت التفاعلي مع التحليل الفني الكامل.")


def color_pnl(val):
    if isinstance(val, (int, float)):
        return "color: #00C851" if val >= 0 else "color: #FF4444"
    return ""


PHASE_LABELS = {
    0: "انتظار", 1: "بريك إيفن", 2: "TP1 (50%)",
    3: "تتبع", 4: "تتبع ضيق",
}

# ── Controls ──────────────────────────────────────────────────────────────────
col_btn, col_space = st.columns([2, 6])
with col_btn:
    refresh = st.button("تحديث الصفقات", type="primary", use_container_width=True)

# ── Load Data ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=15, show_spinner=False)
def _load_positions():
    from dashboard.utils.mt5_helper import get_open_positions, get_account_info
    return get_open_positions(), get_account_info()

@st.cache_data(ttl=300, show_spinner=False)
def _load_candles(symbol, timeframe="H1"):
    path = f"data/raw/{symbol}/{timeframe}.parquet"
    if os.path.exists(path):
        return pd.read_parquet(path).tail(200)
    return pd.DataFrame()

@st.cache_data(ttl=60, show_spinner=False)
def _get_signal_for_ticket(ticket):
    """Get the signal log entry for a trade ticket."""
    from storage.database import SessionLocal, SignalLog
    session = SessionLocal()
    try:
        sig = session.query(SignalLog).filter(SignalLog.ticket == ticket).first()
        if sig:
            return {
                "strategy": sig.strategy,
                "ml_confidence": sig.ml_confidence,
                "rsi": sig.rsi,
                "atr": sig.atr,
                "reason": sig.reason,
                "time": sig.time,
                "price": sig.price,
            }
        return None
    finally:
        session.close()

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
    st.warning("MT5 غير متصل - عرض سجلات قاعدة البيانات.")

st.divider()

# ── Load Monitor States ───────────────────────────────────────────────────────
from dashboard.utils.db import get_monitor_states, get_open_trades
monitor_states = get_monitor_states()

# ── Phase Summary KPIs ────────────────────────────────────────────────────────
if monitor_states:
    phase_counts = {i: 0 for i in range(5)}
    for state in monitor_states.values():
        phase_counts[state.get("phase", 0)] = phase_counts.get(state.get("phase", 0), 0) + 1

    cp1, cp2, cp3, cp4, cp5 = st.columns(5)
    with cp1:
        st.metric("انتظار", phase_counts[0])
    with cp2:
        st.metric("بريك إيفن", phase_counts[1])
    with cp3:
        st.metric("TP1", phase_counts[2])
    with cp4:
        st.metric("تتبع", phase_counts[3])
    with cp5:
        st.metric("تتبع ضيق", phase_counts[4])
    st.divider()

# ── Get positions source ─────────────────────────────────────────────────────
if positions_df is not None and not positions_df.empty:
    source_df = positions_df
else:
    source_df = get_open_trades()

if source_df is not None and not source_df.empty:
    st.subheader(f"الصفقات الحية ({len(source_df)})")

    ticket_col = "ticket" if "ticket" in source_df.columns else None
    pnl_col = next((c for c in ["profit", "pnl", "unrealized_pnl"] if c in source_df.columns), None)

    # ── Each Trade as Interactive Card ─────────────────────────────────────
    for idx, row in source_df.iterrows():
        ticket = row.get("ticket") or row.get(source_df.columns[0])
        symbol = row.get("symbol", "?")
        action = row.get("order_type") or row.get("type", "?")
        pnl_val = row.get(pnl_col, 0) if pnl_col else 0
        pnl_val = pnl_val if pd.notna(pnl_val) else 0
        entry_p = row.get("open_price") or row.get("price_open", 0)
        current_p = row.get("current_price") or row.get("price_current", 0)
        sl = row.get("stop_loss") or row.get("sl", 0)
        tp = row.get("take_profit") or row.get("tp", 0)
        vol = row.get("volume", 0)
        strategy = row.get("strategy", "--")

        # Monitor state
        m_state = monitor_states.get(ticket, {})
        phase = m_state.get("phase", 0)
        tp1_closed = m_state.get("tp1_closed", False)
        orig_vol = m_state.get("original_volume")
        orig_tp = m_state.get("original_tp")
        entry_atr = m_state.get("entry_atr")

        # Signal data
        signal = _get_signal_for_ticket(ticket)

        pnl_color = "#00C851" if pnl_val >= 0 else "#FF4444"
        action_color = "#00C851" if action == "BUY" else "#FF4444"
        phase_label = PHASE_LABELS.get(phase, "?")

        # Risk/Reward
        if entry_p and sl and tp:
            risk_pips = abs(entry_p - sl)
            reward_pips = abs(tp - entry_p)
            rr_ratio = reward_pips / risk_pips if risk_pips > 0 else 0
            # Current position in R
            current_r = (current_p - entry_p) / risk_pips if risk_pips > 0 and current_p else 0
            if action == "SELL":
                current_r = -current_r
        else:
            rr_ratio = 0
            current_r = 0

        # Phase progress bar
        phase_steps = ""
        for p in range(5):
            if p < phase:
                c = "#00C851"
            elif p == phase:
                c = "#1E88E5"
            else:
                c = "#2D3748"
            phase_steps += f'<div style="flex:1;height:6px;background:{c};border-radius:3px;margin:0 2px"></div>'

        # Comment (entry reason)
        comment = row.get("comment", "")

        # ── Trade Card Header ─────────────────────────────────────────────
        st.markdown(f"""
        <div style="border:1px solid #2D3748;border-radius:10px;padding:16px;margin:8px 0;background:linear-gradient(135deg,#1A1F2E,#151A28)">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                <div>
                    <span style="font-size:20px;font-weight:800;color:{action_color}">{action}</span>
                    <span style="font-size:17px;font-weight:700;margin-left:12px">{symbol}</span>
                    <span style="margin-left:8px;background:#2D3748;padding:2px 8px;border-radius:4px;font-size:11px">{strategy}</span>
                    <span style="margin-left:8px;font-size:12px;color:#888">#{ticket}</span>
                </div>
                <div style="text-align:right">
                    <span style="font-size:20px;font-weight:800;color:{pnl_color}">${pnl_val:+,.2f}</span>
                    <span style="font-size:12px;color:#888;margin-left:8px">{current_r:+.1f}R</span>
                </div>
            </div>
            <div style="display:flex;margin:8px 0">{phase_steps}</div>
            <div style="display:flex;justify-content:space-between;font-size:12px;color:#888">
                <span>المرحلة: <b style="color:#FFF">{phase_label}</b>{' | TP1 تم' if tp1_closed else ''}</span>
                <span>R:R = 1:{rr_ratio:.1f} | الحجم: {vol:.2f}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Expandable Chart + Details ────────────────────────────────────
        with st.expander(f"شارت + تحليل {symbol} #{ticket}", expanded=False):

            # ── Build Professional Chart ──────────────────────────────────
            candles = _load_candles(symbol, "H1")

            if not candles.empty:
                fig = make_subplots(
                    rows=2, cols=1, shared_xaxes=True,
                    row_heights=[0.8, 0.2], vertical_spacing=0.03,
                )

                x_axis = candles.index.tolist() if hasattr(candles.index, 'strftime') else list(range(len(candles)))

                # Candlestick
                fig.add_trace(go.Candlestick(
                    x=x_axis,
                    open=candles["open"], high=candles["high"],
                    low=candles["low"], close=candles["close"],
                    name="السعر",
                    increasing_line_color="#00C851", decreasing_line_color="#FF4444",
                ), row=1, col=1)

                # Volume
                if "volume" in candles.columns:
                    vol_colors = ["rgba(0,200,81,0.4)" if c >= o else "rgba(255,68,68,0.4)"
                                  for c, o in zip(candles["close"], candles["open"])]
                    fig.add_trace(go.Bar(
                        x=x_axis, y=candles["volume"],
                        name="الحجم", marker_color=vol_colors, opacity=0.5,
                    ), row=2, col=1)

                last_x = x_axis[-1]

                # ── Entry Line ────────────────────────────────────────────
                if entry_p:
                    fig.add_hline(
                        y=entry_p, line_dash="solid", line_color="#1E88E5", line_width=2,
                        annotation_text=f"الدخول {entry_p:.5f}",
                        annotation_font_color="#1E88E5",
                        annotation_font_size=11,
                        row=1, col=1,
                    )

                # ── SL Zone (red shaded) ──────────────────────────────────
                if sl and entry_p:
                    fig.add_hline(
                        y=sl, line_dash="dash", line_color="#FF4444", line_width=2,
                        annotation_text=f"SL {sl:.5f}",
                        annotation_font_color="#FF4444",
                        annotation_font_size=11,
                        annotation_position="bottom left",
                        row=1, col=1,
                    )
                    # Shaded SL zone
                    sl_zone_y = [min(entry_p, sl), min(entry_p, sl), max(entry_p, sl), max(entry_p, sl)]
                    fig.add_shape(
                        type="rect", xref="paper", yref="y",
                        x0=0.7, x1=1, y0=sl, y1=entry_p,
                        fillcolor="rgba(255,68,68,0.08)", line_width=0,
                        row=1, col=1,
                    )

                # ── TP Zone (green shaded) ────────────────────────────────
                if tp and entry_p:
                    fig.add_hline(
                        y=tp, line_dash="dash", line_color="#00C851", line_width=2,
                        annotation_text=f"TP {tp:.5f}",
                        annotation_font_color="#00C851",
                        annotation_font_size=11,
                        row=1, col=1,
                    )
                    fig.add_shape(
                        type="rect", xref="paper", yref="y",
                        x0=0.7, x1=1, y0=entry_p, y1=tp,
                        fillcolor="rgba(0,200,81,0.08)", line_width=0,
                        row=1, col=1,
                    )

                # ── Original TP (if modified) ─────────────────────────────
                if orig_tp and tp and abs(orig_tp - tp) > 0.00001:
                    fig.add_hline(
                        y=orig_tp, line_dash="dot", line_color="#FFCA28", line_width=1,
                        annotation_text=f"TP1 {orig_tp:.5f}",
                        annotation_font_color="#FFCA28",
                        annotation_font_size=10,
                        row=1, col=1,
                    )

                # ── Entry Arrow Marker ────────────────────────────────────
                if signal and signal.get("time"):
                    entry_time = pd.to_datetime(signal["time"])
                    if hasattr(candles.index, 'strftime'):
                        fig.add_trace(go.Scatter(
                            x=[entry_time], y=[entry_p],
                            mode="markers+text",
                            marker=dict(
                                symbol="triangle-up" if action == "BUY" else "triangle-down",
                                size=16, color=action_color,
                                line=dict(width=2, color="white"),
                            ),
                            text=[action],
                            textposition="top center" if action == "BUY" else "bottom center",
                            textfont=dict(color=action_color, size=11, family="Arial Black"),
                            showlegend=False,
                            hovertemplate=f"<b>{action} Entry</b><br>Price: {entry_p:.5f}<br>Time: {entry_time}<extra></extra>",
                        ), row=1, col=1)

                # Layout
                fig.update_layout(
                    paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
                    font=dict(color="#FAFAFA", size=11),
                    title=dict(
                        text=f"{symbol} H1 | {action} @ {entry_p:.5f} | {strategy}",
                        font=dict(size=14),
                    ),
                    xaxis_rangeslider_visible=False,
                    yaxis=dict(gridcolor="#1E2130", title=""),
                    yaxis2=dict(gridcolor="#1E2130", title=""),
                    xaxis2=dict(gridcolor="#1E2130"),
                    height=500,
                    margin=dict(l=50, r=20, t=40, b=10),
                    showlegend=False,
                )

                st.plotly_chart(fig, width="stretch")
            else:
                st.warning(f"لا توجد بيانات شموع لـ {symbol}/H1. شغّل download_historical_data.py")

            # ── Trade Info Panel ───────────────────────────────────────────
            st.markdown("---")

            # Row 1: Prices
            ic1, ic2, ic3, ic4 = st.columns(4)
            with ic1:
                st.metric("سعر الدخول", f"{entry_p:.5f}" if entry_p else "--")
            with ic2:
                st.metric("السعر الحالي", f"{current_p:.5f}" if current_p else "--")
            with ic3:
                st.metric("وقف الخسارة", f"{sl:.5f}" if sl else "--")
            with ic4:
                st.metric("جني الأرباح", f"{tp:.5f}" if tp else "--")

            # Row 2: Risk/Monitor
            ic5, ic6, ic7, ic8 = st.columns(4)
            with ic5:
                st.metric("R:R المخطط", f"1:{rr_ratio:.1f}")
            with ic6:
                st.metric("الربح بالـ R", f"{current_r:+.2f}R")
            with ic7:
                st.metric("الحجم", f"{vol:.2f}" + (f" (من {orig_vol:.2f})" if orig_vol and orig_vol != vol else ""))
            with ic8:
                st.metric("المرحلة", f"{phase} - {phase_label}")

            # ── Signal Analysis ────────────────────────────────────────────
            if signal or comment:
                st.markdown("---")
                st.markdown("**تحليل الدخول**")

                sa1, sa2, sa3, sa4 = st.columns(4)
                with sa1:
                    if signal and signal.get("rsi"):
                        rsi = signal["rsi"]
                        rsi_status = "ذروة شراء" if rsi > 70 else ("ذروة بيع" if rsi < 30 else "محايد")
                        st.metric("RSI", f"{rsi:.1f}", delta=rsi_status, delta_color="off")
                    else:
                        st.metric("RSI", "--")
                with sa2:
                    if signal and signal.get("atr"):
                        st.metric("ATR", f"{signal['atr']:.5f}")
                    elif entry_atr:
                        st.metric("ATR", f"{entry_atr:.5f}")
                    else:
                        st.metric("ATR", "--")
                with sa3:
                    if signal and signal.get("ml_confidence"):
                        st.metric("ثقة ML", f"{signal['ml_confidence']:.1%}")
                    else:
                        st.metric("ثقة ML", "--")
                with sa4:
                    st.metric("الاستراتيجية", strategy)

                # Entry reason from comment
                if comment:
                    st.markdown(f"""
                    <div style="background:#151A28;border:1px solid #2D3748;border-radius:8px;padding:12px;margin-top:8px">
                        <div style="font-size:12px;color:#888;margin-bottom:4px">سبب الدخول</div>
                        <div style="font-size:14px;color:#FFF">{comment}</div>
                    </div>
                    """, unsafe_allow_html=True)

                # Prediction/Expectation
                if entry_p and sl and tp:
                    risk_dollars = abs(entry_p - sl)
                    reward_dollars = abs(tp - entry_p)

                    st.markdown(f"""
                    <div style="display:flex;gap:10px;margin-top:10px">
                        <div style="flex:1;background:#1A0005;border:1px solid #B71C1C;border-radius:8px;padding:10px;text-align:center">
                            <div style="font-size:11px;color:#EF5350">المخاطرة</div>
                            <div style="font-size:16px;font-weight:700;color:#FF4444">{risk_dollars:.5f}</div>
                            <div style="font-size:11px;color:#888">إلى SL</div>
                        </div>
                        <div style="flex:1;background:#0D2818;border:1px solid #1B5E20;border-radius:8px;padding:10px;text-align:center">
                            <div style="font-size:11px;color:#66BB6A">المكافأة</div>
                            <div style="font-size:16px;font-weight:700;color:#00C851">{reward_dollars:.5f}</div>
                            <div style="font-size:11px;color:#888">إلى TP</div>
                        </div>
                        <div style="flex:1;background:#1A1505;border:1px solid #F57F17;border-radius:8px;padding:10px;text-align:center">
                            <div style="font-size:11px;color:#FFCA28">التوقع</div>
                            <div style="font-size:16px;font-weight:700;color:#FFCA28">1:{rr_ratio:.1f}</div>
                            <div style="font-size:11px;color:#888">R:R</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

            if m_state.get("updated_at"):
                st.caption(f"آخر تحديث مونيتور: {m_state['updated_at']}")

    # ── Close Position ────────────────────────────────────────────────────────
    st.divider()
    st.subheader("إغلاق صفقة")

    if ticket_col and ticket_col in source_df.columns:
        tickets = source_df[ticket_col].tolist()
        symbol_col = "symbol" if "symbol" in source_df.columns else None
        if symbol_col:
            options = [f"{row[ticket_col]} -- {row[symbol_col]} {row.get('order_type', '')}"
                       for _, row in source_df.iterrows()]
        else:
            options = [str(t) for t in tickets]

        col_sel, col_close = st.columns([4, 2])
        with col_sel:
            selected_idx = st.selectbox("اختر الصفقة", range(len(options)),
                                         format_func=lambda i: options[i])
        with col_close:
            st.write("")
            st.write("")
            if st.button("إغلاق الصفقة", type="primary", use_container_width=True):
                ticket = tickets[selected_idx]
                with st.spinner(f"جاري إغلاق #{ticket}..."):
                    from dashboard.utils.mt5_helper import close_position
                    success, msg = close_position(int(ticket))
                if success:
                    st.success(msg)
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(f"فشل الإغلاق: {msg}")

else:
    st.markdown("""
    <div style="text-align:center;padding:60px 0;color:#666">
        <h3>لا توجد صفقات مفتوحة</h3>
        <p>انتقل إلى الماسح للبحث عن إشارات وتنفيذها</p>
    </div>
    """, unsafe_allow_html=True)

# ── Position Size Calculator ──────────────────────────────────────────────────
st.divider()
st.subheader("حاسبة حجم الصفقة")

col_a, col_b, col_c, col_d = st.columns(4)
with col_a:
    balance_input = st.number_input("رصيد الحساب ($)", value=100000.0, step=1000.0)
with col_b:
    risk_pct = st.number_input("نسبة المخاطرة %", value=1.0, min_value=0.1, max_value=10.0, step=0.1)
with col_c:
    sl_pips = st.number_input("وقف الخسارة (نقاط)", value=20, min_value=1, step=1)
with col_d:
    pip_val = st.selectbox("نوع الزوج", ["فوركس (0.0001)", "ين (0.01)", "ذهب (0.01)"])
    pip_dollar_map = {"فوركس (0.0001)": 10.0, "ين (0.01)": 6.5, "ذهب (0.01)": 1.0}
    pip_dollar = pip_dollar_map[pip_val]

risk_amount = balance_input * (risk_pct / 100)
lot_size = risk_amount / (sl_pips * pip_dollar) if sl_pips > 0 and pip_dollar > 0 else 0

col_r1, col_r2, col_r3 = st.columns(3)
with col_r1:
    st.metric("مبلغ المخاطرة", f"${risk_amount:,.2f}")
with col_r2:
    st.metric("حجم اللوت", f"{lot_size:.2f}")
with col_r3:
    st.metric("قيمة النقطة", f"${pip_dollar * lot_size:.2f}")
