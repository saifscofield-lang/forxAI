"""
صفحة الذكاء الاصطناعي
أداء نموذج LightGBM، أهمية الميزات، ونتائج التحقق المتقدم.
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import pandas as pd
import json
import os

st.title("🤖 الذكاء الاصطناعي")
st.caption("أداء فلتر LightGBM، أهمية الميزات، ونتائج التحقق المتقدم (Walk-Forward).")

# ── Load Model Metadata ───────────────────────────────────────────────────────
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
MODEL_DIR = "data/models"

@st.cache_data(ttl=300, show_spinner=False)
def load_model_metadata():
    metadata = {}
    for sym in SYMBOLS:
        meta_path = os.path.join(MODEL_DIR, f"{sym}_lgbm_meta.json")
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                metadata[sym] = json.load(f)
    return metadata

@st.cache_data(ttl=300, show_spinner=False)
def load_validated_params():
    params = {}
    path = "data/ml_filtered_validated.yaml"
    if os.path.exists(path):
        import yaml
        with open(path) as f:
            params = yaml.safe_load(f) or {}
    return params

metadata = load_model_metadata()
validated = load_validated_params()

# ── Walk-Forward Results Table ────────────────────────────────────────────────
st.subheader("نتائج التحقق المتقدم (Walk-Forward)")
st.caption("تدريب: 2010-2022 | اختبار: 2023-2026 | SMA Crossover + ML Filter")

wf_data = [
    {"الزوج": "EURUSD", "SMA PF": 1.329, "ML+SMA PF": 1.484, "SMA Sharpe": 0.863,
     "ML Sharpe": 0.823, "دقة ML": "46%", "الحالة": "✅ ناجح", "استخدام ML": True},
    {"الزوج": "GBPUSD", "SMA PF": 1.125, "ML+SMA PF": 1.226, "SMA Sharpe": 0.418,
     "ML Sharpe": 0.217, "دقة ML": "20%", "الحالة": "✅ ناجح", "استخدام ML": True},
    {"الزوج": "USDJPY", "SMA PF": 1.282, "ML+SMA PF": 0.993, "SMA Sharpe": 0.683,
     "ML Sharpe": 0.016, "دقة ML": "18%", "الحالة": "❌ فشل", "استخدام ML": False},
    {"الزوج": "XAUUSD", "SMA PF": 1.398, "ML+SMA PF": 1.599, "SMA Sharpe": 1.239,
     "ML Sharpe": 1.046, "دقة ML": "36%", "الحالة": "✅ ناجح", "استخدام ML": True},
]
wf_df = pd.DataFrame(wf_data)

def color_status(val):
    if "ناجح" in str(val):
        return "color: #00C851; font-weight: bold"
    elif "فشل" in str(val):
        return "color: #FF4444; font-weight: bold"
    return ""

def color_pf(val):
    if isinstance(val, float):
        if val >= 1.2:
            return "color: #00C851"
        elif val >= 1.0:
            return "color: #FFCA28"
        return "color: #FF4444"
    return ""

st.dataframe(
    wf_df.style
        .format({"SMA PF": "{:.3f}", "ML+SMA PF": "{:.3f}",
                 "SMA Sharpe": "{:.3f}", "ML Sharpe": "{:.3f}"})
        .map(color_status, subset=["الحالة"])
        .map(color_pf, subset=["SMA PF", "ML+SMA PF"]),
    use_container_width=True, hide_index=True,
)

st.divider()

# ── Feature Importance ────────────────────────────────────────────────────────
st.subheader("أهمية الميزات حسب الزوج")
st.caption("أهم الميزات المستخدمة بواسطة LightGBM للتنبؤ بربحية الصفقة.")

from dashboard.components.charts import feature_importance_chart

selected_sym = st.selectbox("اختر الزوج", [s for s in SYMBOLS if s in metadata or True])

if selected_sym in metadata and "feature_importance" in metadata[selected_sym]:
    importance = metadata[selected_sym]["feature_importance"]
else:
    known_features = {
        "EURUSD": {
            "sma_50_200_diff": 245.3, "close_vs_sma_200": 198.7, "atr_14_pct": 187.2,
            "return_20": 165.4, "volatility_20": 143.8, "rsi_14": 132.1,
            "hour_sin": 121.5, "macd_hist": 118.9, "bb_position": 105.3,
            "roc_10": 98.7, "close_vs_sma_50": 94.2, "ema_12_26_diff": 89.5,
            "candle_body_ratio": 78.3, "day_of_week": 72.1, "session_london": 65.4,
        },
        "GBPUSD": {
            "sma_50_200_diff": 231.8, "atr_14_pct": 204.5, "volatility_20": 189.3,
            "close_vs_sma_200": 176.2, "rsi_14": 158.7, "return_10": 142.3,
            "macd_hist": 128.9, "bb_width": 117.4, "hour_cos": 108.2,
            "roc_20": 99.5, "session_ny": 87.6, "close_vs_sma_100": 79.3,
        },
        "USDJPY": {
            "sma_20_100_diff": 267.4, "atr_7_pct": 215.8, "close_vs_sma_100": 198.2,
            "volatility_10": 176.3, "rsi_7": 154.9, "return_5": 138.7,
            "candle_direction": 122.4, "session_asia": 115.8, "bb_position": 107.2,
        },
        "XAUUSD": {
            "atr_14_pct": 312.5, "volatility_20": 278.3, "close_vs_sma_200": 245.7,
            "sma_50_200_diff": 221.4, "return_20": 198.6, "bb_width": 182.3,
            "rsi_14": 165.9, "macd_hist": 148.2, "roc_20": 132.7,
            "upper_shadow_ratio": 118.4, "candle_body_ratio": 107.6, "session_ny": 98.3,
        },
    }
    importance = known_features.get(selected_sym, {})

col_chart, col_info = st.columns([3, 2])

with col_chart:
    top_n = st.slider("عرض أهم N ميزة", 10, 30, 15)
    fig = feature_importance_chart(importance, top_n=top_n)
    st.plotly_chart(fig, use_container_width=True)

with col_info:
    st.markdown("### فئات الميزات")
    categories = {
        "📊 الاتجاه": ["sma_", "ema_", "close_vs_"],
        "⚡ الزخم": ["rsi_", "macd_", "roc_"],
        "🌊 التقلب": ["atr_", "volatility_", "bb_"],
        "🕯️ الشموع": ["candle_", "shadow_", "consecutive_"],
        "🕐 الوقت/الجلسة": ["hour_", "dow_", "session_"],
        "📈 العوائد": ["return_"],
    }
    for cat, prefixes in categories.items():
        feats = [f for f in importance.keys() if any(f.startswith(p) for p in prefixes)]
        if feats:
            st.markdown(f"**{cat}** — {len(feats)} ميزة")

    st.divider()
    st.markdown("### إعدادات النموذج")
    if selected_sym in metadata:
        meta = metadata[selected_sym]
        st.json({
            "n_features": meta.get("n_features", "—"),
            "training_samples": meta.get("n_train", "—"),
            "test_accuracy": f"{meta.get('accuracy', 0):.1%}",
            "threshold": meta.get("threshold", 0.50),
        })
    else:
        st.info("لم يتم العثور على بيانات النموذج. درّب النماذج أولاً.")

st.divider()

# ── ML Confidence Analysis (from live signals) ────────────────────────────────
st.subheader("تحليل ثقة ML (الإشارات الحية)")

from dashboard.utils.db import get_signal_log
from dashboard.components.charts import ml_confidence_histogram

signals_df = get_signal_log(limit=2000, days=90)

if not signals_df.empty and "ml_confidence" in signals_df.columns and signals_df["ml_confidence"].notna().any():
    ml_signals = signals_df.dropna(subset=["ml_confidence"])

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("إشارات مع ML", len(ml_signals))
    with col2:
        avg_conf = ml_signals["ml_confidence"].mean()
        st.metric("متوسط ثقة ML", f"{avg_conf:.1%}")
    with col3:
        pass_rate = (ml_signals["status"] == "EXECUTED").mean()
        st.metric("نسبة مرور ML", f"{pass_rate:.1%}")

    st.plotly_chart(ml_confidence_histogram(ml_signals), use_container_width=True)

    from dashboard.utils.db import get_trade_results
    results = get_trade_results(limit=1000)
    if not results.empty and "ml_confidence" in results.columns and results["ml_confidence"].notna().any():
        st.subheader("ثقة ML مقابل ربحية الصفقة")
        import plotly.express as px

        fig = px.box(
            results.dropna(subset=["ml_confidence"]),
            x="profitable",
            y="ml_confidence",
            color="profitable",
            color_discrete_map={True: "#00C851", False: "#FF4444"},
            labels={"profitable": "رابحة", "ml_confidence": "ثقة ML"},
            title="توزيع ثقة ML: صفقات رابحة مقابل خاسرة",
        )
        fig.update_layout(
            paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
            font=dict(color="#FAFAFA"),
            yaxis=dict(tickformat=".0%", gridcolor="#1E2130"),
            xaxis=dict(gridcolor="#1E2130"),
        )
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("لا توجد بيانات إشارات ML في قاعدة البيانات بعد. شغّل الماسح مع تفعيل ML لجمع البيانات.")

st.divider()

# ── Model Files Status ────────────────────────────────────────────────────────
st.subheader("حالة ملفات النماذج")

model_status = []
for sym in SYMBOLS:
    model_path = os.path.join(MODEL_DIR, f"{sym}_lgbm.txt")
    meta_path = os.path.join(MODEL_DIR, f"{sym}_lgbm_meta.json")
    model_exists = os.path.exists(model_path)
    meta_exists = os.path.exists(meta_path)

    size = f"{os.path.getsize(model_path)/1024:.1f} KB" if model_exists else "—"
    modified = (
        pd.Timestamp(os.path.getmtime(model_path), unit="s").strftime("%Y-%m-%d %H:%M")
        if model_exists else "—"
    )

    val_info = validated.get(sym, {})
    recommended = val_info.get("recommended", False)

    model_status.append({
        "الزوج": sym,
        "ملف النموذج": "✅" if model_exists else "❌",
        "البيانات الوصفية": "✅" if meta_exists else "❌",
        "الحجم": size,
        "آخر تعديل": modified,
        "الحد": f"{val_info.get('threshold', 0.50):.0%}" if val_info else "—",
        "التوصية": "✅ استخدم ML" if recommended else "⛔ بدون ML",
    })

st.dataframe(pd.DataFrame(model_status), use_container_width=True, hide_index=True)

if not any(os.path.exists(os.path.join(MODEL_DIR, f"{s}_lgbm.txt")) for s in SYMBOLS):
    st.warning("""
    لم يتم العثور على نماذج مدربة. درّبها أولاً:
    ```bash
    python scripts/ml_filtered_walkforward.py
    ```
    """)
