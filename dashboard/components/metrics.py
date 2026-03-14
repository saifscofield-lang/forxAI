"""
KPI metric card components for the ForexAI dashboard.
"""
import streamlit as st


def metric_card(label: str, value: str, delta: str = None, delta_color: str = "normal"):
    """Single styled metric card."""
    st.metric(label=label, value=value, delta=delta, delta_color=delta_color)


def kpi_row(metrics: list):
    """
    Render a row of KPI cards.
    metrics: list of dicts with keys: label, value, delta (optional), delta_color (optional)
    """
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            st.metric(
                label=m["label"],
                value=m["value"],
                delta=m.get("delta"),
                delta_color=m.get("delta_color", "normal"),
                help=m.get("help"),
            )


def status_badge(text: str, color: str = "green") -> str:
    """Return HTML for a colored status badge."""
    bg_map = {
        "green": "#00C851",
        "red": "#FF4444",
        "orange": "#FF9800",
        "blue": "#1E88E5",
        "gray": "#666666",
    }
    bg = bg_map.get(color, "#666666")
    return f'<span style="background:{bg};color:white;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600">{text}</span>'


def signal_card(signal: dict) -> None:
    """Render a single signal card with execute button."""
    action = signal.get("action", "?")
    symbol = signal.get("symbol", "?")
    price = signal.get("price", 0)
    sl = signal.get("stop_loss", 0)
    tp = signal.get("take_profit", 0)
    ml_conf = signal.get("ml_confidence")
    reason = signal.get("reason", "")
    strategy = signal.get("strategy", "")
    status = signal.get("status", "ACTIVE")

    action_color = "#00C851" if action == "BUY" else "#FF4444"
    status_color = "green" if status == "ACTIVE" else "orange"

    with st.container():
        st.markdown(f"""
        <div style="border:1px solid #2D3748;border-radius:8px;padding:12px 16px;margin:6px 0;background:#1A1F2E">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <span style="font-size:18px;font-weight:700;color:{action_color}">{action}</span>
                <span style="font-size:16px;font-weight:600">{symbol}</span>
                {status_badge(status, status_color)}
            </div>
            <div style="margin-top:8px;font-size:13px;color:#AAA">
                <span>الدخول: <b style="color:#FFF">{price:.5f}</b></span>&nbsp;&nbsp;
                <span>وقف الخسارة: <b style="color:#FF4444">{sl:.5f}</b></span>&nbsp;&nbsp;
                <span>جني الأرباح: <b style="color:#00C851">{tp:.5f}</b></span>
            </div>
            {"<div style='margin-top:4px;font-size:12px;color:#888'>" + reason[:80] + "</div>" if reason else ""}
            {"<div style='margin-top:6px;font-size:12px'>ثقة ML: <b style='color:#00BCD4'>" + f"{ml_conf:.1%}" + "</b></div>" if ml_conf is not None else ""}
        </div>
        """, unsafe_allow_html=True)


def connection_status_bar(connected: bool, account_info: dict = None):
    """Display MT5 connection status in sidebar."""
    if connected and account_info:
        st.sidebar.success("MT5 متصل")
        st.sidebar.markdown(f"""
        **الحساب:** {account_info.get('login', 'N/A')}
        **السيرفر:** {account_info.get('server', 'N/A')}
        **الرصيد:** ${account_info.get('balance', 0):,.2f}
        **الملكية:** ${account_info.get('equity', 0):,.2f}
        **الربح:** ${account_info.get('profit', 0):+,.2f}
        """)
    else:
        st.sidebar.error("MT5 غير متصل")
        st.sidebar.caption("يجب تشغيل منصة MT5")
