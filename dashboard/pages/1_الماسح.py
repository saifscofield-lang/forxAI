"""
صفحة ماسح الإشارات
مسح إشارات التداول وتنفيذها يدوياً.
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import pandas as pd
from datetime import datetime, timezone

st.title("📡 ماسح الإشارات")
st.caption("مسح جميع الأدوات للبحث عن إشارات تداول، ثم اختيار ما تريد تنفيذه.")

# ── Sidebar Controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("إعدادات المسح")
    use_ml = st.toggle("استخدام فلتر ML", value=True,
                        help="تطبيق فلتر LightGBM على الإشارات (مُوصى به)")
    symbols_all = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
    selected_symbols = st.multiselect("الأزواج", symbols_all, default=symbols_all)
    st.divider()
    st.caption("ML معطّل لزوج USDJPY افتراضياً — يُستخدم SMA فقط.")

# ── Session State ─────────────────────────────────────────────────────────────
if "scan_results" not in st.session_state:
    st.session_state.scan_results = []
if "last_scan_time" not in st.session_state:
    st.session_state.last_scan_time = None
if "executed_tickets" not in st.session_state:
    st.session_state.executed_tickets = set()

# ── Scan Button ───────────────────────────────────────────────────────────────
col_btn, col_info, col_refresh = st.columns([2, 4, 2])

with col_btn:
    scan_clicked = st.button("🔍 مسح الآن", type="primary", use_container_width=True)

with col_info:
    if st.session_state.last_scan_time:
        st.info(f"آخر مسح: {st.session_state.last_scan_time.strftime('%H:%M:%S')} UTC")

with col_refresh:
    if st.button("🗑️ مسح النتائج", use_container_width=True):
        st.session_state.scan_results = []
        st.session_state.last_scan_time = None
        st.rerun()

# ── Run Scan ──────────────────────────────────────────────────────────────────
if scan_clicked:
    with st.spinner("جاري الاتصال بـ MT5 ومسح الأدوات..."):
        from dashboard.utils.mt5_helper import run_scan
        signals = run_scan(use_ml=use_ml)

    # Filter by selected symbols
    if selected_symbols:
        signals = [s for s in signals if s.get("symbol") in selected_symbols or "error" in s]

    st.session_state.scan_results = signals
    st.session_state.last_scan_time = datetime.now(timezone.utc)

    if signals and "error" not in signals[0]:
        st.success(f"اكتمل المسح — {len(signals)} إشارة")
    elif signals and "error" in signals[0]:
        st.error(f"خطأ في المسح: {signals[0]['error']}")
    else:
        st.info("لم تُولّد إشارات — ظروف السوق غير مناسبة أو MT5 غير متصل")

# ── Display Signals ───────────────────────────────────────────────────────────
signals = st.session_state.scan_results

if not signals:
    st.markdown("""
    <div style="text-align:center;padding:60px 0;color:#666">
        <h3>لا توجد نتائج مسح</h3>
        <p>اضغط "مسح الآن" للبحث عن إشارات تداول</p>
    </div>
    """, unsafe_allow_html=True)
else:
    # Split into active vs filtered
    active = [s for s in signals if s.get("status") not in ("ML_FILTERED", "RISK_REJECTED") and "error" not in s]
    filtered = [s for s in signals if s.get("status") in ("ML_FILTERED", "RISK_REJECTED")]

    tabs = st.tabs([
        f"✅ إشارات نشطة ({len(active)})",
        f"🚫 إشارات مُرشّحة ({len(filtered)})",
        "📋 البيانات الخام",
    ])

    # ── Active Signals Tab ────────────────────────────────────────────────────
    with tabs[0]:
        if not active:
            st.info("لا توجد إشارات نشطة. جميع الإشارات تمت تصفيتها بواسطة ML أو إدارة المخاطر.")
        else:
            for sig in active:
                _key = f"{sig.get('symbol')}_{sig.get('action')}_{sig.get('price', 0):.5f}"
                action = sig.get("action", "?")
                symbol = sig.get("symbol", "?")
                price = sig.get("price", 0)
                sl = sig.get("stop_loss", 0)
                tp = sig.get("take_profit", 0)
                ml_conf = sig.get("ml_confidence")
                reason = sig.get("reason", "")
                strategy = sig.get("strategy", "")

                action_color = "#00C851" if action == "BUY" else "#FF4444"

                # Risk/reward ratio
                if price and sl and tp:
                    risk = abs(price - sl)
                    reward = abs(tp - price)
                    rr = reward / risk if risk > 0 else 0
                else:
                    rr = 0

                with st.container():
                    st.markdown(f"""
                    <div style="border:1px solid #2D3748;border-radius:10px;padding:16px;margin:8px 0;background:#1A1F2E">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
                            <div>
                                <span style="font-size:22px;font-weight:700;color:{action_color}">{action}</span>
                                <span style="font-size:18px;font-weight:600;margin-left:12px">{symbol}</span>
                            </div>
                            <div style="text-align:right">
                                <span style="background:#2D3748;padding:3px 10px;border-radius:4px;font-size:12px">{strategy}</span>
                                {f'&nbsp;<span style="background:#004D40;color:#00BCD4;padding:3px 10px;border-radius:4px;font-size:12px">ML: {ml_conf:.1%}</span>' if ml_conf is not None else ''}
                            </div>
                        </div>
                        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;font-size:14px">
                            <div><span style="color:#888">الدخول</span><br><b>{price:.5f}</b></div>
                            <div><span style="color:#888">وقف الخسارة</span><br><b style="color:#FF4444">{sl:.5f}</b></div>
                            <div><span style="color:#888">جني الأرباح</span><br><b style="color:#00C851">{tp:.5f}</b></div>
                            <div><span style="color:#888">مخاطرة:مكافأة</span><br><b>1:{rr:.1f}</b></div>
                        </div>
                        {"<div style='margin-top:10px;font-size:12px;color:#888'>" + reason + "</div>" if reason else ""}
                    </div>
                    """, unsafe_allow_html=True)

                    col_exec, col_skip = st.columns([1, 5])
                    with col_exec:
                        already_executed = _key in st.session_state.executed_tickets
                        if already_executed:
                            st.success("✓ تم التنفيذ")
                        else:
                            if st.button(f"▶ تنفيذ {action} {symbol}", key=f"exec_{_key}",
                                         type="primary"):
                                with st.spinner(f"جاري تنفيذ {action} {symbol}..."):
                                    from dashboard.utils.mt5_helper import execute_signal_manual
                                    success, msg = execute_signal_manual(sig)
                                if success:
                                    st.session_state.executed_tickets.add(_key)
                                    st.success(f"تم وضع الأمر! {msg}")
                                    st.balloons()
                                else:
                                    st.error(f"فشل: {msg}")

    # ── Filtered Signals Tab ──────────────────────────────────────────────────
    with tabs[1]:
        if not filtered:
            st.info("لم تتم تصفية أي إشارات.")
        else:
            for sig in filtered:
                action = sig.get("action", "?")
                symbol = sig.get("symbol", "?")
                status = sig.get("status", "FILTERED")
                ml_conf = sig.get("ml_confidence")
                ml_thresh = sig.get("ml_threshold")
                reason = sig.get("reason", "")

                status_color = "#FF9800" if status == "ML_FILTERED" else "#FF4444"
                action_color = "#00C851" if action == "BUY" else "#FF4444"

                st.markdown(f"""
                <div style="border:1px solid #2D2015;border-radius:8px;padding:12px 16px;margin:6px 0;background:#1A1505;opacity:0.8">
                    <span style="color:{action_color};font-weight:700">{action}</span>
                    <span style="margin-left:10px;font-weight:600">{symbol}</span>
                    <span style="margin-left:12px;background:{status_color}22;color:{status_color};padding:2px 8px;border-radius:4px;font-size:12px">{status}</span>
                    {f'<span style="margin-left:8px;font-size:12px;color:#888">ML: {ml_conf:.1%} (الحد {ml_thresh:.0%})</span>' if ml_conf is not None and ml_thresh is not None else ''}
                    {"<div style='margin-top:6px;font-size:12px;color:#666'>" + reason + "</div>" if reason else ""}
                </div>
                """, unsafe_allow_html=True)

    # ── Raw Data Tab ──────────────────────────────────────────────────────────
    with tabs[2]:
        df = pd.DataFrame(signals)
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            csv = df.to_csv(index=False)
            st.download_button("⬇ تحميل CSV", csv, "scan_results.csv", "text/csv")

# ── Price Chart ───────────────────────────────────────────────────────────────
st.divider()
st.subheader("الرسم البياني للسعر")

col_sym, col_tf = st.columns([2, 2])
with col_sym:
    chart_symbol = st.selectbox("الزوج", symbols_all, key="chart_sym")
with col_tf:
    chart_tf = st.selectbox("الإطار الزمني", ["M15", "H1", "H4", "D1"], index=1)

if st.button("تحميل الرسم", key="load_chart"):
    with st.spinner("جاري تحميل بيانات الأسعار..."):
        from dashboard.utils.mt5_helper import get_ohlcv
        from dashboard.components.charts import candlestick_chart
        df_price = get_ohlcv(chart_symbol, chart_tf, bars=200)
        if not df_price.empty:
            fig = candlestick_chart(df_price, chart_symbol)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("تعذر تحميل بيانات الأسعار. هل MT5 متصل؟")
