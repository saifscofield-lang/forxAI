"""
متتبع المشروع — مراحل Strategy Lab وحالة النظام وسجل التحسينات
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timezone, timedelta

st.set_page_config(page_title="متتبع المشروع", page_icon="📋", layout="wide")

# ── CSS matching main dashboard ──
st.markdown("""
<style>
    .block-container { padding-top: 1rem; max-width: 1400px; }
    div[data-testid="metric-container"] {
        background: linear-gradient(135deg, #1A1F2E 0%, #151A28 100%);
        border: 1px solid #2D3748;
        border-radius: 10px;
        padding: 14px 18px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }
    hr { border-color: #1E2130 !important; margin: 0.8rem 0 !important; }
    .streamlit-expanderHeader { font-weight: 600; }

    .phase-card {
        background: linear-gradient(135deg, #1A1F2E 0%, #151A28 100%);
        border: 1px solid #2D3748;
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 12px;
    }
    .phase-active {
        border-left: 4px solid #FF9800;
    }
    .phase-done {
        border-left: 4px solid #4CAF50;
    }
    .phase-pending {
        border-left: 4px solid #444;
        opacity: 0.6;
    }
    .step-done { color: #4CAF50; }
    .step-active { color: #FF9800; font-weight: 700; }
    .step-pending { color: #666; }
    .decision-card {
        background: #12151C;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 10px;
    }
    .badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 4px;
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.5px;
    }
    .anomaly-box {
        background: #2D1111;
        border: 1px solid #B71C1C;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)

IMP_DB = "data/improvements.db"
TRADING_DB = "data/trading.db"


def get_conn(path):
    return sqlite3.connect(path)


# ══════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════
st.markdown("""
<div style="display:flex;align-items:baseline;gap:16px;margin-bottom:4px">
    <span style="font-size:26px;font-weight:800;color:#1E88E5">متتبع المشروع</span>
    <span style="font-size:13px;color:#666;letter-spacing:0.5px">Strategy Lab — المراحل والحالة والتحسينات</span>
</div>
""", unsafe_allow_html=True)

# ── Quick status bar ──
try:
    conn_t = get_conn(TRADING_DB)
    conn_i = get_conn(IMP_DB)

    # Current phase
    phase_row = pd.read_sql("SELECT phase_number, name FROM project_phases WHERE status = 'IN_PROGRESS' LIMIT 1", conn_i)
    current_phase = int(phase_row.iloc[0]["phase_number"]) if not phase_row.empty else 0
    phase_name = phase_row.iloc[0]["name"] if not phase_row.empty else "---"

    # Paper day
    phase1_start = datetime(2026, 3, 31, tzinfo=timezone.utc)
    paper_day = max(1, (datetime.now(timezone.utc) - phase1_start).days + 1)

    # Balance
    acc = pd.read_sql("SELECT balance FROM account_snapshots ORDER BY time DESC LIMIT 1", conn_t)
    balance = acc.iloc[0]["balance"] if not acc.empty else 0

    # Shadow signals
    shadow_total = pd.read_sql("SELECT COUNT(*) as n FROM shadow_signals", conn_t).iloc[0]["n"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("المرحلة الحالية", f"Phase {current_phase}", phase_name)
    c2.metric("يوم التداول التجريبي", f"{paper_day} / 14")
    c3.metric("الرصيد", f"${balance:,.0f}")
    c4.metric("إشارات الظل", f"{shadow_total}")

    conn_t.close()
    conn_i.close()
except Exception:
    pass

st.divider()

# ══════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════
tab_phases, tab_state, tab_regime, tab_decisions, tab_improvements, tab_shadow = st.tabs([
    "📊 المراحل",
    "⚡ حالة النظام",
    "🎯 تحليل الأنظمة",
    "📝 سجل القرارات",
    "🔧 التحسينات",
    "👁 التداول الظلي",
])


# ══════════════════════════════════════════════════════════════
# TAB 1: المراحل
# ══════════════════════════════════════════════════════════════
with tab_phases:
    st.markdown("""
    <div style="color:#888;font-size:13px;margin-bottom:16px">
        خارطة طريق المشروع من Strategy Lab — كل مرحلة تحتوي خطوات محددة يجب إكمالها قبل الانتقال للتالية.
        النظام يتقدم تلقائياً عند تحقق الشروط.
    </div>
    """, unsafe_allow_html=True)

    try:
        conn = get_conn(IMP_DB)
        phases = pd.read_sql("SELECT * FROM project_phases ORDER BY phase_number", conn)

        if not phases.empty:
            # Progress bar
            completed = len(phases[phases["status"] == "COMPLETED"])
            in_progress = len(phases[phases["status"] == "IN_PROGRESS"])
            total = len(phases)
            progress = (completed + in_progress * 0.5) / total
            st.progress(progress, text=f"التقدم العام: {completed} من {total} مراحل مكتملة")

            PHASE_DESC = {
                0: "بناء الأساس — كاشف النظام، قاعدة البيانات، نظام التقييم، قاطع الدائرة",
                1: "المنتج الأولي — استراتيجيتان جديدتان + تداول تجريبي + جمع بيانات الظل",
                2: "التوسع المحكوم — 6 فرضيات جديدة + تحسين Optuna + محرك القرار التلقائي",
                3: "التطور الذكي — Claude API يولّد فرضيات + دمج الاستراتيجيات + تداول حقيقي 0.01 لوت",
                4: "النخبة — بطولة أسبوعية + تقاعد تلقائي + إعادة تدريب شهري",
            }

            PHASE_WHY = {
                0: "لا يمكن بناء نظام تداول بدون بنية تحتية صلبة — كاشف النظام يمنع التداول في الظروف الخاطئة، والتقييم يفرز الاستراتيجيات الضعيفة",
                1: "الهدف ليس الربح بل جمع بيانات حقيقية — التداول الظلي يسجل كل إشارة بنتيجتها المحاكاة لتدريب ML لاحقاً",
                2: "بعد إثبات المفهوم، نوسّع بحذر — كل فرضية جديدة تمر بنفس القمع الصارم قبل التفعيل",
                3: "الذكاء الاصطناعي يبدأ بتوليد أفكار جديدة بناءً على ما نجح وما فشل — تطور ذاتي محكوم",
                4: "النظام يدير نفسه — أفضل الاستراتيجيات تستمر، الأضعف تتقاعد، النماذج تُحدَّث دورياً",
            }

            STATUS_AR = {"COMPLETED": "مكتمل", "IN_PROGRESS": "جاري", "NOT_STARTED": "لم يبدأ"}

            for _, phase in phases.iterrows():
                pn = int(phase["phase_number"])
                status = phase["status"]
                css_class = "phase-done" if status == "COMPLETED" else ("phase-active" if status == "IN_PROGRESS" else "phase-pending")
                status_color = "#4CAF50" if status == "COMPLETED" else ("#FF9800" if status == "IN_PROGRESS" else "#555")

                # Steps
                steps = pd.read_sql(f"SELECT * FROM phase_steps WHERE phase_number = {pn} ORDER BY step_order", conn)
                steps_done = len(steps[steps["status"] == "COMPLETED"]) if not steps.empty else 0
                steps_total = len(steps)

                with st.expander(
                    f"{'✅' if status == 'COMPLETED' else ('🔶' if status == 'IN_PROGRESS' else '⬜')} "
                    f"المرحلة {pn} — {phase['name']}  ({STATUS_AR.get(status, status)})",
                    expanded=(status == "IN_PROGRESS"),
                ):
                    # Description and why
                    st.markdown(f"""
                    <div style="background:#0D1117;border-radius:8px;padding:14px 18px;margin-bottom:12px">
                        <div style="color:#CCC;font-size:13px;line-height:1.8">{PHASE_DESC.get(pn, '')}</div>
                        <div style="color:#888;font-size:12px;margin-top:8px;border-top:1px solid #1E2130;padding-top:8px">
                            <b style="color:#FF9800">لماذا هذه المرحلة مهمة:</b> {PHASE_WHY.get(pn, '')}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # Meta info
                    meta_cols = st.columns(4)
                    meta_cols[0].markdown(f"**المدة:** {phase['duration']}")
                    meta_cols[1].markdown(f"**الحالة:** <span style='color:{status_color}'>{STATUS_AR.get(status, status)}</span>", unsafe_allow_html=True)
                    meta_cols[2].markdown(f"**التقدم:** {steps_done}/{steps_total} خطوة")
                    if phase["started_at"]:
                        meta_cols[3].markdown(f"**بدأ:** {phase['started_at']}")

                    # Steps
                    if not steps.empty:
                        st.markdown("**الخطوات:**")
                        for _, step in steps.iterrows():
                            s_status = step["status"]
                            if s_status == "COMPLETED":
                                st.markdown(f"<div class='step-done'>✅ {step['description']}</div>", unsafe_allow_html=True)
                            elif s_status == "IN_PROGRESS":
                                st.markdown(f"<div class='step-active'>🔶 {step['description']}</div>", unsafe_allow_html=True)
                            else:
                                st.markdown(f"<div class='step-pending'>⬜ {step['description']}</div>", unsafe_allow_html=True)

                    if phase.get("notes"):
                        st.caption(f"ملاحظة: {phase['notes']}")

        conn.close()
    except Exception as e:
        st.error(f"خطأ في تحميل المراحل: {e}")


# ══════════════════════════════════════════════════════════════
# TAB 2: حالة النظام
# ══════════════════════════════════════════════════════════════
with tab_state:
    st.markdown("""
    <div style="color:#888;font-size:13px;margin-bottom:16px">
        لوحة مراقبة حية لحالة النظام — الرصيد، الصفقات، الاستراتيجيات النشطة، ومؤشرات الأداء.
        يُحفظ snapshot يومي تلقائياً لتتبع التقدم عبر الزمن.
    </div>
    """, unsafe_allow_html=True)

    try:
        conn_t = get_conn(TRADING_DB)

        # ── Metrics row ──
        c1, c2, c3, c4, c5 = st.columns(5)
        try:
            acc = pd.read_sql("SELECT balance, equity FROM account_snapshots ORDER BY time DESC LIMIT 1", conn_t)
            if not acc.empty:
                c1.metric("الرصيد", f"${acc.iloc[0]['balance']:,.2f}")
                c2.metric("حقوق الملكية", f"${acc.iloc[0]['equity']:,.2f}")
        except Exception:
            pass

        try:
            trades_q = pd.read_sql("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins,
                       SUM(profit) as pnl
                FROM trades WHERE is_closed = 1
            """, conn_t)
            if not trades_q.empty and trades_q.iloc[0]["total"] > 0:
                t = trades_q.iloc[0]
                wr = (t["wins"] / t["total"] * 100) if t["total"] > 0 else 0
                c3.metric("إجمالي الربح/الخسارة", f"${t['pnl']:+,.2f}")
                c4.metric("نسبة الفوز", f"{wr:.1f}%")
                c5.metric("الصفقات المغلقة", f"{int(t['total'])}")
        except Exception:
            pass

        st.divider()

        # ── Strategy performance ──
        st.markdown("### أداء الاستراتيجيات")
        st.markdown("""
        <div style="color:#888;font-size:12px;margin-bottom:8px">
            تصنيف الاستراتيجيات حسب الربحية — الأعلى ربحاً في الأعلى. يساعد في تحديد أي استراتيجية يجب تعزيزها أو إيقافها.
        </div>
        """, unsafe_allow_html=True)

        try:
            strats = pd.read_sql("""
                SELECT strategy as 'الاستراتيجية',
                       symbol as 'الزوج',
                       COUNT(*) as 'الصفقات',
                       ROUND(SUM(CASE WHEN profit > 0 THEN 1.0 ELSE 0 END) / COUNT(*) * 100, 1) as 'نسبة الفوز%',
                       ROUND(SUM(profit), 2) as 'الربح/الخسارة'
                FROM trades WHERE is_closed = 1
                GROUP BY strategy, symbol
                ORDER BY SUM(profit) DESC
            """, conn_t)
            if not strats.empty:
                st.dataframe(strats, use_container_width=True, hide_index=True)
            else:
                st.info("لا توجد صفقات مغلقة بعد")
        except Exception:
            st.info("لا توجد بيانات صفقات")

        st.divider()

        # ── Open positions ──
        st.markdown("### الصفقات المفتوحة")
        try:
            opens = pd.read_sql("""
                SELECT symbol as 'الزوج',
                       order_type as 'النوع',
                       strategy as 'الاستراتيجية',
                       volume as 'اللوت',
                       ROUND(profit, 2) as 'الربح',
                       open_time as 'وقت الفتح'
                FROM trades WHERE is_closed = 0 ORDER BY open_time DESC
            """, conn_t)
            if not opens.empty:
                st.dataframe(opens, use_container_width=True, hide_index=True)
            else:
                st.info("لا توجد صفقات مفتوحة")
        except Exception:
            pass

        st.divider()

        # ── Historical state chart ──
        st.markdown("### تطور الرصيد والأداء")
        st.markdown("""
        <div style="color:#888;font-size:12px;margin-bottom:8px">
            يُسجَّل snapshot يومي تلقائياً — يساعد في رؤية اتجاه الحساب عبر الأيام.
        </div>
        """, unsafe_allow_html=True)

        try:
            conn_i = get_conn(IMP_DB)
            history = pd.read_sql("SELECT time, balance, total_pnl, win_rate, filter_accuracy, notes FROM system_state ORDER BY time", conn_i)
            conn_i.close()
            if not history.empty and len(history) > 1:
                history["time"] = pd.to_datetime(history["time"])
                st.line_chart(history.set_index("time")[["balance"]], use_container_width=True)
            else:
                st.info("بيانات غير كافية — ستظهر بعد يومين من التشغيل")
        except Exception:
            st.info("لا توجد بيانات تاريخية بعد")

        conn_t.close()

    except Exception as e:
        st.error(f"خطأ في تحميل حالة النظام: {e}")


# ══════════════════════════════════════════════════════════════
# TAB 3: تحليل الأنظمة (Regime Analysis)
# ══════════════════════════════════════════════════════════════
with tab_regime:
    st.markdown("""
    <div style="color:#888;font-size:13px;margin-bottom:16px">
        تحليل أداء كل استراتيجية حسب نظام السوق — يكشف إذا كانت الاستراتيجية تملك Edge حقيقية أم مجرد حظ مؤقت.
        <b style="color:#FF9800">النتيجة الرئيسية:</b> MACD و RSI تتفوقان في RANGING فقط. جميع الاستراتيجيات تفشل في TRENDING_BEAR.
    </div>
    """, unsafe_allow_html=True)

    try:
        conn_t = get_conn(TRADING_DB)

        # Regime distribution
        regime_dist = pd.read_sql("""
            SELECT detected_regime as 'النظام', COUNT(*) as 'الصفقات',
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as 'رابحة',
                   ROUND(SUM(CASE WHEN pnl > 0 THEN 1.0 ELSE 0 END) / COUNT(*) * 100, 1) as 'نسبة الفوز%',
                   ROUND(SUM(pnl), 2) as 'إجمالي الربح'
            FROM trade_results
            WHERE detected_regime IS NOT NULL
            GROUP BY detected_regime
            ORDER BY SUM(pnl) DESC
        """, conn_t)

        if not regime_dist.empty:
            st.markdown("### توزيع الأنظمة")
            st.markdown("""
            <div style="color:#888;font-size:12px;margin-bottom:8px">
                كيف توزعت الصفقات حسب نظام السوق — وأيها كان الأكثر ربحية.
            </div>
            """, unsafe_allow_html=True)

            # Metrics row
            for _, row in regime_dist.iterrows():
                regime_name = row["النظام"]
                wr = row["نسبة الفوز%"]
                pnl = row["إجمالي الربح"]
                color = "#4CAF50" if pnl > 0 else "#F44336"

                regime_ar = {
                    "RANGING": "نطاقي (Ranging)",
                    "TRENDING_BULL": "صاعد (Trending Bull)",
                    "TRENDING_BEAR": "هابط (Trending Bear)",
                    "TRANSITIONAL": "انتقالي (Transitional)",
                    "VOLATILE": "متقلب (Volatile)",
                }.get(regime_name, regime_name)

                st.markdown(f"""
                <div style="background:#12151C;border-radius:8px;padding:12px 16px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center">
                    <span style="color:#DDD;font-weight:600">{regime_ar}</span>
                    <span style="color:#888">{int(row['الصفقات'])} صفقة</span>
                    <span style="color:#888">WR: {wr}%</span>
                    <span style="color:{color};font-weight:700">${pnl:+,.2f}</span>
                </div>
                """, unsafe_allow_html=True)

            st.divider()

        # Strategy x Regime matrix
        st.markdown("### أداء الاستراتيجيات حسب النظام")
        st.markdown("""
        <div style="color:#888;font-size:12px;margin-bottom:8px">
            الجدول الأهم — يوضح أين تعمل كل استراتيجية وأين تفشل. الخلايا الخضراء = edge حقيقية، الحمراء = يجب تجنبها.
        </div>
        """, unsafe_allow_html=True)

        regime_matrix = pd.read_sql("""
            SELECT strategy as 'الاستراتيجية',
                   detected_regime as 'النظام',
                   COUNT(*) as 'الصفقات',
                   ROUND(SUM(CASE WHEN pnl > 0 THEN 1.0 ELSE 0 END) / COUNT(*) * 100, 1) as 'نسبة الفوز%',
                   ROUND(SUM(pnl), 2) as 'الربح/الخسارة',
                   ROUND(AVG(pnl), 2) as 'متوسط الصفقة'
            FROM trade_results
            WHERE detected_regime IS NOT NULL
            GROUP BY strategy, detected_regime
            ORDER BY strategy, detected_regime
        """, conn_t)

        if not regime_matrix.empty:
            st.dataframe(
                regime_matrix,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "الربح/الخسارة": st.column_config.NumberColumn(format="$%.2f"),
                    "متوسط الصفقة": st.column_config.NumberColumn(format="$%.2f"),
                },
            )

            st.divider()

            # Key insights
            st.markdown("### الاستنتاجات الرئيسية")

            # Best combos
            best = regime_matrix[regime_matrix["نسبة الفوز%"] >= 70].sort_values("نسبة الفوز%", ascending=False)
            if not best.empty:
                st.markdown("""
                <div style="background:#0D2818;border:1px solid #1B5E20;border-radius:8px;padding:14px 18px;margin-bottom:10px">
                    <div style="color:#4CAF50;font-weight:700;margin-bottom:8px">Edge مؤكدة (WR >= 70%)</div>
                """, unsafe_allow_html=True)
                for _, r in best.iterrows():
                    st.markdown(f"""
                    <div style="color:#CCC;font-size:13px;padding:2px 0">
                        {r['الاستراتيجية']} في {r['النظام']}: <b style="color:#4CAF50">{r['نسبة الفوز%']}% WR</b> — {int(r['الصفقات'])} صفقة — ${r['الربح/الخسارة']:+,.2f}
                    </div>
                    """, unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

            # Worst combos
            worst = regime_matrix[regime_matrix["نسبة الفوز%"] <= 35].sort_values("نسبة الفوز%")
            if not worst.empty:
                st.markdown("""
                <div style="background:#2D1111;border:1px solid #B71C1C;border-radius:8px;padding:14px 18px;margin-bottom:10px">
                    <div style="color:#F44336;font-weight:700;margin-bottom:8px">يجب تجنبها (WR <= 35%)</div>
                """, unsafe_allow_html=True)
                for _, r in worst.iterrows():
                    st.markdown(f"""
                    <div style="color:#CCC;font-size:13px;padding:2px 0">
                        {r['الاستراتيجية']} في {r['النظام']}: <b style="color:#F44336">{r['نسبة الفوز%']}% WR</b> — {int(r['الصفقات'])} صفقة — ${r['الربح/الخسارة']:+,.2f}
                    </div>
                    """, unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("لا توجد بيانات نظام — يجب تصنيف الصفقات أولاً")

        conn_t.close()

    except Exception as e:
        st.error(f"خطأ في تحميل تحليل الأنظمة: {e}")


# ══════════════════════════════════════════════════════════════
# TAB 4: سجل القرارات
# ══════════════════════════════════════════════════════════════
with tab_decisions:
    st.markdown("""
    <div style="color:#888;font-size:13px;margin-bottom:16px">
        كل قرار مهم في المشروع يُسجَّل هنا مع السبب والأثر — لفهم لماذا وصلنا لهذه النقطة وتجنب تكرار الأخطاء.
    </div>
    """, unsafe_allow_html=True)

    try:
        conn = get_conn(IMP_DB)
        decisions = pd.read_sql(
            "SELECT time, category, decision, reason, impact, phase FROM decisions_log ORDER BY time DESC",
            conn
        )
        conn.close()

        CAT_CONFIG = {
            "BACKTEST": ("#2196F3", "اختبار رجعي"),
            "OPTIMIZATION": ("#9C27B0", "تحسين"),
            "RISK": ("#F44336", "إدارة مخاطر"),
            "STRATEGY": ("#FF9800", "استراتيجية"),
            "DATA": ("#4CAF50", "بيانات"),
            "PROCESS": ("#00BCD4", "عملية"),
        }

        if not decisions.empty:
            for _, d in decisions.iterrows():
                color, cat_ar = CAT_CONFIG.get(d["category"], ("#666", d["category"]))

                st.markdown(f"""
                <div class="decision-card" style="border-right:4px solid {color}">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                        <span class="badge" style="background:{color}22;color:{color}">{cat_ar}</span>
                        <span style="color:#555;font-size:11px">المرحلة {d['phase']} &nbsp;|&nbsp; {d['time']}</span>
                    </div>
                    <div style="color:#EEE;font-size:14px;font-weight:600;margin-bottom:6px">{d['decision']}</div>
                    <div style="color:#999;font-size:12px;line-height:1.7">
                        <b style="color:#FF9800">السبب:</b> {d['reason']}
                    </div>
                    <div style="color:#999;font-size:12px;line-height:1.7">
                        <b style="color:#4CAF50">الأثر:</b> {d['impact']}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("لم تُسجَّل قرارات بعد")

    except Exception as e:
        st.error(f"خطأ في تحميل القرارات: {e}")


# ══════════════════════════════════════════════════════════════
# TAB 4: التحسينات
# ══════════════════════════════════════════════════════════════
with tab_improvements:
    st.markdown("""
    <div style="color:#888;font-size:13px;margin-bottom:16px">
        سجل جميع التحسينات من IMP-01 إلى IMP-76 — كل تحسين يُتتبع من الفكرة إلى التنفيذ.
        هذا يمنع فقدان الأفكار ويضمن تنفيذ الأولويات أولاً.
    </div>
    """, unsafe_allow_html=True)

    try:
        conn = get_conn(IMP_DB)
        imps = pd.read_sql(
            "SELECT code, title, category, priority, status FROM improvements ORDER BY id DESC",
            conn
        )
        conn.close()

        if not imps.empty:
            # Summary metrics
            c1, c2, c3, c4 = st.columns(4)
            done_count = len(imps[imps["status"] == "DONE"])
            skip_count = len(imps[imps["status"] == "SKIPPED"])
            pending_count = len(imps[imps["status"].isin(["PENDING", "TODO"])])

            c1.metric("الإجمالي", len(imps))
            c2.metric("مكتمل", done_count)
            c3.metric("تم تخطيه", skip_count)
            c4.metric("معلّق", pending_count)

            # Progress
            if len(imps) > 0:
                pct = done_count / len(imps)
                st.progress(pct, text=f"نسبة الإنجاز: {pct*100:.0f}%")

            st.divider()

            # Filter
            status_options = imps["status"].unique().tolist()
            STATUS_AR_MAP = {"DONE": "مكتمل", "SKIPPED": "تم تخطيه", "PENDING": "معلّق", "TODO": "للتنفيذ"}
            status_filter = st.multiselect(
                "تصفية حسب الحالة",
                status_options,
                default=["DONE"],
                format_func=lambda x: STATUS_AR_MAP.get(x, x),
            )
            filtered = imps[imps["status"].isin(status_filter)] if status_filter else imps

            st.dataframe(
                filtered.rename(columns={
                    "code": "الرمز", "title": "العنوان", "category": "الفئة",
                    "priority": "الأولوية", "status": "الحالة",
                }),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("لا توجد تحسينات مسجلة")

    except Exception as e:
        st.error(f"خطأ في تحميل التحسينات: {e}")


# ══════════════════════════════════════════════════════════════
# TAB 5: التداول الظلي
# ══════════════════════════════════════════════════════════════
with tab_shadow:
    st.markdown("""
    <div style="color:#888;font-size:13px;margin-bottom:16px">
        كل إشارة تُسجَّل سواء نُفذت أم رُفضت — ثم نتابع ماذا كان سيحدث لو نفذناها.
        هذا ينتج بيانات تدريب ML عالية الجودة ويقيس دقة الفلاتر.
    </div>
    """, unsafe_allow_html=True)

    try:
        conn_t = get_conn(TRADING_DB)

        # Summary metrics
        total = pd.read_sql("SELECT COUNT(*) as n FROM shadow_signals", conn_t).iloc[0]["n"]
        executed = pd.read_sql("SELECT COUNT(*) as n FROM shadow_signals WHERE executed = 1", conn_t).iloc[0]["n"]
        blocked = pd.read_sql("SELECT COUNT(*) as n FROM shadow_signals WHERE executed = 0", conn_t).iloc[0]["n"]
        open_s = pd.read_sql("SELECT COUNT(*) as n FROM shadow_signals WHERE sim_status = 'OPEN'", conn_t).iloc[0]["n"]
        resolved = pd.read_sql("SELECT COUNT(*) as n FROM shadow_signals WHERE sim_status != 'OPEN'", conn_t).iloc[0]["n"]

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("إجمالي الإشارات", total)
        c2.metric("نُفذت", executed)
        c3.metric("رُفضت", blocked)
        c4.metric("مفتوحة", open_s)
        c5.metric("محلولة", resolved)

        # Target progress
        target = 200
        if total > 0:
            pct = min(1.0, resolved / target)
            st.progress(pct, text=f"الهدف: {resolved}/{target} إشارة محلولة لتدريب ML")

        if resolved > 0:
            st.divider()
            st.markdown("### فعالية الفلاتر")
            st.markdown("""
            <div style="color:#888;font-size:12px;margin-bottom:8px">
                كلما ارتفعت دقة الفلتر، كان أفضل في حجب الإشارات الخاسرة. إذا انخفضت عن 50% فالفلتر يحجب إشارات رابحة أكثر من الخاسرة — يحتاج تعديل.
            </div>
            """, unsafe_allow_html=True)

            filter_stats = pd.read_sql("""
                SELECT rejection_reason as 'الفلتر',
                       COUNT(*) as 'المجموع',
                       SUM(CASE WHEN label = 1 THEN 1 ELSE 0 END) as 'كانت ستربح',
                       SUM(CASE WHEN label = 0 THEN 1 ELSE 0 END) as 'كانت ستخسر',
                       ROUND(CAST(SUM(CASE WHEN label = 0 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100, 1) as 'الدقة%'
                FROM shadow_signals
                WHERE executed = 0 AND sim_status != 'OPEN'
                GROUP BY rejection_reason
            """, conn_t)

            if not filter_stats.empty:
                st.dataframe(filter_stats, use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("### آخر الإشارات")
        st.markdown("""
        <div style="color:#888;font-size:12px;margin-bottom:8px">
            آخر 50 إشارة — لمراقبة ما يحدث الآن في الوقت الحقيقي.
        </div>
        """, unsafe_allow_html=True)

        recent = pd.read_sql("""
            SELECT time as 'الوقت',
                   symbol as 'الزوج',
                   action as 'الاتجاه',
                   strategy as 'الاستراتيجية',
                   CASE WHEN executed = 1 THEN 'نعم' ELSE 'لا' END as 'نُفذت',
                   COALESCE(rejection_reason, '-') as 'سبب الرفض',
                   COALESCE(regime, '-') as 'النظام',
                   sim_status as 'الحالة',
                   COALESCE(ROUND(sim_pnl_pips, 1), 0) as 'النتيجة (نقاط)',
                   CASE WHEN label = 1 THEN 'ربح' WHEN label = 0 THEN 'خسارة' ELSE 'مفتوح' END as 'النتيجة'
            FROM shadow_signals
            ORDER BY time DESC LIMIT 50
        """, conn_t)

        if not recent.empty:
            st.dataframe(recent, use_container_width=True, hide_index=True)
        else:
            st.info("لا توجد إشارات ظلية بعد — أعد تشغيل start.bat لبدء التجميع")

        conn_t.close()

    except Exception as e:
        st.error(f"خطأ في تحميل بيانات الظل: {e}")
