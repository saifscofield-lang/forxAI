"""
Reusable Plotly chart components for the ForexAI dashboard.
All functions return plotly Figure objects — call st.plotly_chart(fig) to render.
"""
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import numpy as np


COLORS = {
    "profit": "#00C851",
    "loss": "#FF4444",
    "neutral": "#AAAAAA",
    "primary": "#1E88E5",
    "bg": "#0E1117",
    "grid": "#1E2130",
    "text": "#FAFAFA",
    "buy": "#00C851",
    "sell": "#FF4444",
    "ml_pass": "#00BCD4",
    "ml_block": "#FF9800",
}

LAYOUT_DEFAULTS = dict(
    paper_bgcolor=COLORS["bg"],
    plot_bgcolor=COLORS["bg"],
    font=dict(color=COLORS["text"], family="Inter, sans-serif"),
    margin=dict(l=10, r=10, t=40, b=10),
    xaxis=dict(gridcolor=COLORS["grid"], showgrid=True),
    yaxis=dict(gridcolor=COLORS["grid"], showgrid=True),
)


def equity_curve_chart(df: pd.DataFrame, show_balance: bool = True) -> go.Figure:
    """Equity and balance over time."""
    fig = go.Figure()

    if df.empty:
        fig.add_annotation(text="No snapshot data yet", x=0.5, y=0.5, showarrow=False,
                           font=dict(size=16, color=COLORS["neutral"]))
        fig.update_layout(**LAYOUT_DEFAULTS, title="منحنى رأس المال")
        return fig

    fig.add_trace(go.Scatter(
        x=df["time"], y=df["equity"],
        name="رأس المال", line=dict(color=COLORS["primary"], width=2),
        fill="tozeroy", fillcolor="rgba(30,136,229,0.1)",
        hovertemplate="<b>Equity:</b> $%{y:,.2f}<br>%{x}<extra></extra>",
    ))

    if show_balance and "balance" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["time"], y=df["balance"],
            name="الرصيد", line=dict(color=COLORS["neutral"], width=1, dash="dash"),
            hovertemplate="<b>Balance:</b> $%{y:,.2f}<br>%{x}<extra></extra>",
        ))

    fig.update_layout(**LAYOUT_DEFAULTS, title="منحنى رأس المال", legend=dict(
        orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
    ))
    return fig


def drawdown_chart(df: pd.DataFrame) -> go.Figure:
    """Drawdown chart from equity curve."""
    fig = go.Figure()

    if df.empty or "equity" not in df.columns:
        fig.add_annotation(text="No data", x=0.5, y=0.5, showarrow=False,
                           font=dict(size=14, color=COLORS["neutral"]))
        fig.update_layout(**LAYOUT_DEFAULTS, title="التراجع")
        return fig

    equity = df["equity"]
    rolling_max = equity.cummax()
    drawdown = (equity - rolling_max) / rolling_max * 100

    fig.add_trace(go.Scatter(
        x=df["time"], y=drawdown,
        name="التراجع %", fill="tozeroy",
        line=dict(color=COLORS["loss"], width=1),
        fillcolor="rgba(255,68,68,0.2)",
        hovertemplate="<b>Drawdown:</b> %{y:.2f}%<br>%{x}<extra></extra>",
    ))

    fig.update_layout(**LAYOUT_DEFAULTS, title="التراجع (%)")
    fig.update_yaxes(ticksuffix="%", gridcolor=COLORS["grid"])
    return fig


def pnl_distribution_chart(df: pd.DataFrame) -> go.Figure:
    """Histogram of trade P&L distribution."""
    fig = go.Figure()

    if df.empty or "pnl" not in df.columns:
        fig.add_annotation(text="No trade data", x=0.5, y=0.5, showarrow=False,
                           font=dict(size=14, color=COLORS["neutral"]))
        fig.update_layout(**LAYOUT_DEFAULTS, title="توزيع الربح/الخسارة")
        return fig

    wins = df[df["pnl"] > 0]["pnl"]
    losses = df[df["pnl"] <= 0]["pnl"]

    fig.add_trace(go.Histogram(
        x=wins, name="رابحة", marker_color=COLORS["profit"],
        opacity=0.75, nbinsx=30,
    ))
    fig.add_trace(go.Histogram(
        x=losses, name="خاسرة", marker_color=COLORS["loss"],
        opacity=0.75, nbinsx=30,
    ))

    fig.update_layout(**LAYOUT_DEFAULTS, title="توزيع الربح/الخسارة",
                      barmode="overlay", xaxis_title="P&L ($)", yaxis_title="Count")
    return fig


def win_loss_pie(df: pd.DataFrame) -> go.Figure:
    """Win/loss ratio pie chart."""
    fig = go.Figure()

    if df.empty or "pnl" not in df.columns:
        fig.add_annotation(text="No data", x=0.5, y=0.5, showarrow=False,
                           font=dict(size=14, color=COLORS["neutral"]))
        fig.update_layout(**LAYOUT_DEFAULTS, title="ربح/خسارة")
        return fig

    wins = (df["pnl"] > 0).sum()
    losses = (df["pnl"] <= 0).sum()

    fig.add_trace(go.Pie(
        labels=["رابحة", "خاسرة"],
        values=[wins, losses],
        hole=0.55,
        marker=dict(colors=[COLORS["profit"], COLORS["loss"]]),
        textinfo="label+percent",
        hovertemplate="<b>%{label}:</b> %{value}<extra></extra>",
    ))

    fig.update_layout(**LAYOUT_DEFAULTS, title="نسبة الربح/الخسارة",
                      showlegend=False)
    return fig


def monthly_pnl_chart(df: pd.DataFrame) -> go.Figure:
    """Monthly P&L bar chart."""
    fig = go.Figure()

    if df.empty:
        fig.add_annotation(text="No data", x=0.5, y=0.5, showarrow=False,
                           font=dict(size=14, color=COLORS["neutral"]))
        fig.update_layout(**LAYOUT_DEFAULTS, title="الربح/الخسارة الشهري")
        return fig

    colors = [COLORS["profit"] if v >= 0 else COLORS["loss"] for v in df["PnL"]]

    fig.add_trace(go.Bar(
        x=df["Month"].astype(str), y=df["PnL"],
        marker_color=colors,
        hovertemplate="<b>%{x}:</b> $%{y:,.2f}<extra></extra>",
    ))

    fig.update_layout(**LAYOUT_DEFAULTS, title="الربح/الخسارة الشهري",
                      xaxis_title="Month", yaxis_title="P&L ($)")
    return fig


def cumulative_pnl_by_symbol(df: pd.DataFrame) -> go.Figure:
    """Cumulative P&L per symbol."""
    fig = go.Figure()

    if df.empty or "pnl" not in df.columns:
        fig.add_annotation(text="No data", x=0.5, y=0.5, showarrow=False,
                           font=dict(size=14, color=COLORS["neutral"]))
        fig.update_layout(**LAYOUT_DEFAULTS, title="الربح التراكمي حسب الزوج")
        return fig

    palette = [COLORS["primary"], "#AB47BC", "#26C6DA", "#FFCA28", "#EF5350"]
    for i, (symbol, g) in enumerate(df.groupby("symbol")):
        g = g.sort_values("close_time")
        fig.add_trace(go.Scatter(
            x=g["close_time"], y=g["pnl"].cumsum(),
            name=symbol,
            line=dict(color=palette[i % len(palette)], width=2),
            hovertemplate=f"<b>{symbol}:</b> $%{{y:,.2f}}<br>%{{x}}<extra></extra>",
        ))

    fig.update_layout(**LAYOUT_DEFAULTS, title="الربح التراكمي حسب الزوج",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    return fig


def signal_status_bar(signal_stats: dict) -> go.Figure:
    """Horizontal bar chart of signal outcomes."""
    labels = ["منفذة", "مرشحة ML", "محجوبة أخبار", "مرفوضة مخاطر", "خطأ"]
    values = [
        signal_stats.get("executed", 0),
        signal_stats.get("ml_filtered", 0),
        signal_stats.get("news_filtered", 0),
        signal_stats.get("risk_rejected", 0),
        signal_stats.get("error", 0),
    ]
    colors_list = [COLORS["profit"], COLORS["ml_block"], "#9C27B0", COLORS["loss"], COLORS["neutral"]]

    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker_color=colors_list,
        hovertemplate="<b>%{y}:</b> %{x}<extra></extra>",
        text=values, textposition="outside",
    ))
    fig.update_layout(**{k: v for k, v in LAYOUT_DEFAULTS.items() if k != "margin"},
                      title="نتائج الإشارات (آخر 90 يوم)",
                      xaxis_title="Count", height=250,
                      margin=dict(l=10, r=30, t=40, b=10))
    return fig


def ml_confidence_histogram(df: pd.DataFrame) -> go.Figure:
    """ML confidence score distribution split by pass/fail."""
    fig = go.Figure()

    if df.empty or "ml_confidence" not in df.columns:
        fig.add_annotation(text="No ML data", x=0.5, y=0.5, showarrow=False,
                           font=dict(size=14, color=COLORS["neutral"]))
        fig.update_layout(**LAYOUT_DEFAULTS, title="توزيع ثقة ML")
        return fig

    df = df.dropna(subset=["ml_confidence"])
    passed = df[df["status"] == "EXECUTED"]["ml_confidence"]
    blocked = df[df["status"] == "ML_FILTERED"]["ml_confidence"]

    if not passed.empty:
        fig.add_trace(go.Histogram(
            x=passed, name="مرّت (منفذة)", marker_color=COLORS["profit"],
            opacity=0.75, nbinsx=20,
        ))
    if not blocked.empty:
        fig.add_trace(go.Histogram(
            x=blocked, name="محجوبة (مرشحة ML)", marker_color=COLORS["loss"],
            opacity=0.75, nbinsx=20,
        ))

    fig.update_layout(**LAYOUT_DEFAULTS, title="توزيع ثقة ML",
                      barmode="overlay", xaxis_title="ML Confidence", yaxis_title="Count")
    fig.update_xaxes(tickformat=".0%", gridcolor=COLORS["grid"])
    return fig


def feature_importance_chart(importance: dict, top_n: int = 20) -> go.Figure:
    """Horizontal bar chart of feature importances."""
    fig = go.Figure()

    if not importance:
        fig.add_annotation(text="No feature importance data", x=0.5, y=0.5,
                           showarrow=False, font=dict(size=14, color=COLORS["neutral"]))
        fig.update_layout(**LAYOUT_DEFAULTS, title="أهمية الميزات")
        return fig

    items = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:top_n]
    features, values = zip(*items)

    fig.add_trace(go.Bar(
        x=list(values), y=list(features), orientation="h",
        marker_color=COLORS["primary"],
        hovertemplate="<b>%{y}:</b> %{x:.2f}<extra></extra>",
    ))

    fig.update_layout(
        **{k: v for k, v in LAYOUT_DEFAULTS.items() if k != "margin"},
        title=f"أهم {top_n} ميزة",
        height=max(300, top_n * 22),
        margin=dict(l=150, r=10, t=40, b=10),
    )
    fig.update_yaxes(autorange="reversed", gridcolor=COLORS["grid"])
    return fig


def candlestick_chart(df: pd.DataFrame, symbol: str) -> go.Figure:
    """OHLCV candlestick chart."""
    fig = go.Figure()

    if df.empty:
        fig.add_annotation(text="No price data", x=0.5, y=0.5, showarrow=False,
                           font=dict(size=14, color=COLORS["neutral"]))
        fig.update_layout(**LAYOUT_DEFAULTS, title=f"{symbol} Price")
        return fig

    fig.add_trace(go.Candlestick(
        x=df.index if "time" not in df.columns else df["time"],
        open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name=symbol,
        increasing_line_color=COLORS["buy"],
        decreasing_line_color=COLORS["sell"],
    ))

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title=f"{symbol} Price",
        xaxis_rangeslider_visible=False,
    )
    return fig


def symbol_performance_radar(df_symbols: pd.DataFrame) -> go.Figure:
    """Radar chart comparing symbols across metrics."""
    fig = go.Figure()

    if df_symbols.empty:
        fig.add_annotation(text="No data", x=0.5, y=0.5, showarrow=False,
                           font=dict(size=14, color=COLORS["neutral"]))
        fig.update_layout(**LAYOUT_DEFAULTS, title="مقارنة الأزواج")
        return fig

    metrics = ["win_rate", "profit_factor", "trades"]
    palette = [COLORS["primary"], "#AB47BC", "#26C6DA", "#FFCA28"]

    for i, row in df_symbols.iterrows():
        values = [row.get(m, 0) for m in metrics]
        values_norm = []
        for j, v in enumerate(values):
            col_max = df_symbols[metrics[j]].max()
            values_norm.append(v / col_max * 100 if col_max > 0 else 0)
        values_norm.append(values_norm[0])  # close shape

        fig.add_trace(go.Scatterpolar(
            r=values_norm + [values_norm[0]],
            theta=metrics + [metrics[0]],
            fill="toself",
            name=row["symbol"],
            line_color=palette[i % len(palette)],
        ))

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title="مقارنة أداء الأزواج",
        polar=dict(
            bgcolor=COLORS["bg"],
            radialaxis=dict(visible=True, range=[0, 100], gridcolor=COLORS["grid"]),
            angularaxis=dict(gridcolor=COLORS["grid"]),
        ),
    )
    return fig
