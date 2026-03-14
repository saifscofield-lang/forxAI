"""
صفحة الاختبار الخلفي
تشغيل اختبارات خلفية على البيانات التاريخية بمعلمات مخصصة.
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import pandas as pd
import os

st.title("⚡ الاختبار الخلفي")
st.caption("تشغيل اختبارات على البيانات التاريخية بمعلمات مخصصة.")

# ── Load Optimized Params ─────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _load_optimized_params():
    path = "data/optimized_params.yaml"
    if not os.path.exists(path):
        return {}
    import yaml
    with open(path) as f:
        return yaml.safe_load(f) or {}

optimized_params = _load_optimized_params()

# ── Parameter Panel ───────────────────────────────────────────────────────────
st.subheader("معلمات الاختبار")

col1, col2 = st.columns([2, 3])

with col1:
    symbol = st.selectbox("الزوج", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"])
    timeframe = st.selectbox("الإطار الزمني", ["H1", "H4", "D1"], index=0)

    if st.button("📥 تحميل المعلمات المحسّنة", use_container_width=True):
        sym_params = optimized_params.get(symbol, {})
        for k, v in sym_params.items():
            st.session_state[f"bt_{k}"] = v
        st.success(f"تم تحميل المعلمات المحسّنة لـ {symbol}")

with col2:
    st.markdown("**معلمات SMA**")
    sma_col1, sma_col2 = st.columns(2)
    with sma_col1:
        sma_fast = st.number_input(
            "SMA السريع",
            min_value=5, max_value=100,
            value=int(st.session_state.get("bt_sma_fast",
                      optimized_params.get(symbol, {}).get("sma_fast", 20))),
            key="bt_sma_fast_input"
        )
    with sma_col2:
        sma_slow = st.number_input(
            "SMA البطيء",
            min_value=20, max_value=300,
            value=int(st.session_state.get("bt_sma_slow",
                      optimized_params.get(symbol, {}).get("sma_slow", 50))),
            key="bt_sma_slow_input"
        )

    st.markdown("**معلمات RSI و ATR**")
    rsi_col, atr_col = st.columns(2)
    with rsi_col:
        rsi_period = st.number_input(
            "فترة RSI",
            min_value=5, max_value=30,
            value=int(st.session_state.get("bt_rsi_period",
                      optimized_params.get(symbol, {}).get("rsi_period", 14))),
            key="bt_rsi_input"
        )
    with atr_col:
        atr_period = st.number_input(
            "فترة ATR",
            min_value=5, max_value=50,
            value=int(st.session_state.get("bt_atr_period",
                      optimized_params.get(symbol, {}).get("atr_period", 14))),
            key="bt_atr_input"
        )

    st.markdown("**معلمات المخاطرة**")
    sl_col, tp_col = st.columns(2)
    with sl_col:
        sl_mult = st.number_input(
            "مضاعف وقف الخسارة (ATR)",
            min_value=0.5, max_value=5.0, step=0.25,
            value=float(st.session_state.get("bt_sl_mult",
                        optimized_params.get(symbol, {}).get("sl_mult", 1.5))),
            key="bt_sl_input"
        )
    with tp_col:
        tp_mult = st.number_input(
            "مضاعف جني الأرباح (ATR)",
            min_value=0.5, max_value=10.0, step=0.25,
            value=float(st.session_state.get("bt_tp_mult",
                        optimized_params.get(symbol, {}).get("tp_mult", 2.0))),
            key="bt_tp_input"
        )

# ── Run Button ────────────────────────────────────────────────────────────────
st.divider()
col_run, col_info = st.columns([2, 5])

with col_run:
    run_clicked = st.button("▶ تشغيل الاختبار", type="primary", use_container_width=True)

with col_info:
    data_path = f"data/raw/{symbol}/H1.parquet"
    if os.path.exists(data_path):
        try:
            df_check = pd.read_parquet(data_path)
            n_bars = len(df_check)
            date_range = f"{df_check.index[0].date() if hasattr(df_check.index[0], 'date') else '?'} → {df_check.index[-1].date() if hasattr(df_check.index[-1], 'date') else '?'}"
            st.info(f"البيانات: {n_bars:,} شمعة | {date_range}")
        except Exception:
            st.warning(f"تعذرت قراءة {data_path}")
    else:
        st.warning(f"لا توجد بيانات في {data_path}. شغّل `python scripts/download_historical_data.py` أولاً.")

# ── Session State for Results ─────────────────────────────────────────────────
if "bt_results" not in st.session_state:
    st.session_state.bt_results = None

if run_clicked:
    params = {
        "symbol": symbol,
        "timeframe": timeframe,
        "sma_fast": sma_fast,
        "sma_slow": sma_slow,
        "rsi_period": rsi_period,
        "atr_period": atr_period,
        "sl_mult": sl_mult,
        "tp_mult": tp_mult,
    }

    with st.spinner(f"جاري تشغيل الاختبار لـ {symbol}..."):
        try:
            from backtest.fast_backtest import FastBacktester

            data_file = f"data/raw/{symbol}/{timeframe}.parquet"
            if not os.path.exists(data_file):
                st.error(f"لا توجد بيانات: {data_file}")
            else:
                df = pd.read_parquet(data_file)
                bt = FastBacktester(
                    sma_fast=sma_fast,
                    sma_slow=sma_slow,
                    rsi_period=rsi_period,
                    atr_period=atr_period,
                    sl_mult=sl_mult,
                    tp_mult=tp_mult,
                )
                result = bt.run(df, symbol=symbol)
                st.session_state.bt_results = result
                st.success("اكتمل الاختبار!")
        except ImportError as e:
            st.error(f"خطأ استيراد: {e}")
        except Exception as e:
            st.error(f"خطأ في الاختبار: {e}")
            import traceback
            st.code(traceback.format_exc())

# ── Display Results ───────────────────────────────────────────────────────────
results = st.session_state.bt_results

if results is not None:
    st.divider()
    st.subheader("نتائج الاختبار")

    def _get(r, *keys, default=0):
        for k in keys:
            if hasattr(r, k):
                return getattr(r, k)
            if isinstance(r, dict) and k in r:
                return r[k]
        return default

    total_trades = _get(results, "total_trades", "n_trades")
    win_rate = _get(results, "win_rate") * 100 if _get(results, "win_rate", default=0) <= 1 else _get(results, "win_rate")
    profit_factor = _get(results, "profit_factor")
    total_pnl = _get(results, "total_pnl", "pnl")
    max_dd = _get(results, "max_drawdown")
    sharpe = _get(results, "sharpe")

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.metric("إجمالي الصفقات", f"{int(total_trades)}")
    with col2:
        st.metric("نسبة الفوز", f"{win_rate:.1f}%")
    with col3:
        st.metric("عامل الربح", f"{profit_factor:.3f}",
                  delta="جيد" if profit_factor >= 1.2 else ("مقبول" if profit_factor >= 1.0 else "ضعيف"),
                  delta_color="normal" if profit_factor >= 1.0 else "inverse")
    with col4:
        st.metric("إجمالي الربح", f"${total_pnl:+,.2f}",
                  delta_color="normal" if total_pnl >= 0 else "inverse")
    with col5:
        st.metric("أقصى تراجع", f"{max_dd:.1%}" if max_dd <= 1 else f"${max_dd:,.2f}")
    with col6:
        st.metric("شارب", f"{sharpe:.3f}",
                  delta_color="normal" if sharpe >= 0.5 else "inverse")

    # Equity curve
    equity_attr = None
    for attr in ["equity_curve", "equity", "cumulative_pnl"]:
        if hasattr(results, attr) and getattr(results, attr) is not None:
            equity_attr = attr
            break
        if isinstance(results, dict) and attr in results:
            equity_attr = attr
            break

    if equity_attr:
        import plotly.graph_objects as go
        equity_data = getattr(results, equity_attr) if hasattr(results, equity_attr) else results[equity_attr]

        fig = go.Figure()
        if isinstance(equity_data, pd.Series):
            fig.add_trace(go.Scatter(
                y=equity_data.values,
                x=equity_data.index,
                name="رأس المال",
                line=dict(color="#1E88E5", width=2),
                fill="tozeroy", fillcolor="rgba(30,136,229,0.1)",
            ))
        elif isinstance(equity_data, (list, pd.Index)):
            fig.add_trace(go.Scatter(
                y=list(equity_data),
                name="رأس المال",
                line=dict(color="#1E88E5", width=2),
                fill="tozeroy", fillcolor="rgba(30,136,229,0.1)",
            ))

        fig.update_layout(
            paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
            font=dict(color="#FAFAFA"),
            title=f"منحنى رأس المال — {symbol}",
            xaxis=dict(gridcolor="#1E2130"),
            yaxis=dict(gridcolor="#1E2130"),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Trades DataFrame
    trades_attr = None
    for attr in ["trades", "trade_log", "trade_history"]:
        if hasattr(results, attr) and getattr(results, attr) is not None:
            trades_attr = attr
            break
        if isinstance(results, dict) and attr in results:
            trades_attr = attr
            break

    if trades_attr:
        trades_data = getattr(results, trades_attr) if hasattr(results, trades_attr) else results[trades_attr]
        if isinstance(trades_data, list) and trades_data:
            df_trades = pd.DataFrame(trades_data)
        elif isinstance(trades_data, pd.DataFrame):
            df_trades = trades_data
        else:
            df_trades = pd.DataFrame()

        if not df_trades.empty:
            st.subheader(f"سجل الصفقات ({len(df_trades)} صفقة)")
            st.dataframe(df_trades, use_container_width=True, hide_index=True)

            csv = df_trades.to_csv(index=False)
            st.download_button(
                "⬇ تصدير صفقات الاختبار",
                data=csv,
                file_name=f"backtest_{symbol}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
            )

# ── Optimized Params Reference ────────────────────────────────────────────────
st.divider()
st.subheader("مرجع المعلمات المحسّنة")
st.caption("أفضل المعلمات التي وجدها Optuna (500 تجربة/زوج).")

if optimized_params:
    opt_rows = []
    for sym, params in optimized_params.items():
        opt_rows.append({"الزوج": sym, **params})
    st.dataframe(pd.DataFrame(opt_rows), use_container_width=True, hide_index=True)
else:
    st.info("لم يتم العثور على معلمات محسّنة. شغّل `python scripts/optimize_strategy.py`.")
