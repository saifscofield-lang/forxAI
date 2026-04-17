"""
متتبع المشروع — مراحل Strategy Lab وحالة النظام وسجل التحسينات
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timezone, timedelta
from pathlib import Path

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

    # Current phase — dynamic from DB, prefers highest-numbered IN_PROGRESS phase
    # (so v3.0 phase 5 shows over legacy phases if both active)
    phase_row = pd.read_sql(
        "SELECT phase_number, name, duration, started_at FROM project_phases "
        "WHERE status = 'IN_PROGRESS' ORDER BY phase_number DESC LIMIT 1", conn_i)
    if not phase_row.empty:
        current_phase = int(phase_row.iloc[0]["phase_number"])
        phase_name = phase_row.iloc[0]["name"]
        phase_duration = phase_row.iloc[0]["duration"] or ""
        phase_started = phase_row.iloc[0]["started_at"]
    else:
        current_phase = 0; phase_name = "---"; phase_duration = ""; phase_started = None

    # Day counter — dynamic: days since current phase started
    if phase_started:
        try:
            started_dt = datetime.fromisoformat(phase_started).replace(tzinfo=timezone.utc)
            phase_day = max(1, (datetime.now(timezone.utc) - started_dt).days + 1)
        except Exception:
            phase_day = 1
    else:
        phase_day = 1

    # Balance
    acc = pd.read_sql("SELECT balance FROM account_snapshots ORDER BY time DESC LIMIT 1", conn_t)
    balance = acc.iloc[0]["balance"] if not acc.empty else 0

    # Shadow signals + STABLE stats
    shadow_total = pd.read_sql("SELECT COUNT(*) as n FROM shadow_signals", conn_t).iloc[0]["n"]
    stable_count = pd.read_sql("SELECT COUNT(*) as n FROM shadow_signals WHERE data_group = 'STABLE'", conn_t).iloc[0]["n"]

    # Delta from baseline
    baseline_balance = 87580.0
    delta = balance - baseline_balance

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("المرحلة الحالية", f"Phase {current_phase}", phase_name)
    c2.metric("الرصيد", f"${balance:,.0f}", f"${delta:+,.0f} من خط الأساس")
    c3.metric("إشارات الظل", f"{shadow_total}", f"{stable_count} مستقرة")
    c4.metric("نافذة المرحلة", f"يوم {phase_day}", phase_duration or "—")
    c5.metric("الهدف", "150+ مستقرة", f"{stable_count}/150")

    conn_t.close()
    conn_i.close()
except Exception:
    pass

st.divider()

# ══════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════
tab_phases, tab_state, tab_weekly, tab_data, tab_regime, tab_metalabel, tab_decisions, tab_improvements, tab_shadow = st.tabs([
    "📊 المراحل",
    "⚡ حالة النظام",
    "📈 راقب الأداء",
    "📦 تقسيم البيانات",
    "🎯 تحليل الأنظمة",
    "🧠 Meta-Labeler",
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
                5: "v3.0 Pre-Build (Apr 17 - May 3) — تجميد ممتد + قراءة Lopez de Prado + بناء dataset الإشارات الأولية + Go/No-Go meeting",
                6: "TSMOM Layer (May 4 - Jun 30) — استراتيجية موازية بدون ML، 12-month lookback، إعادة توازن شهرية، 140 سنة من الأدلة",
                7: "Meta-Labeler Rebuild (May 4 - Jun 8) — Triple Barrier + Purged K-Fold + LightGBM filter. ML يصفّي بدلاً من التنبؤ",
                8: "v3.0 Paper Trading (Jun 8 - Jul 20) — 6 أسابيع على demo، تجميد كود في آخر 14 يوم، gate صارم قبل live",
                9: "v3.0 Live Trading (Sep 1+) — تخطّي أغسطس (سيولة منخفضة)، بدء $2,000 فقط، 0.3% risk → 0.5% تدريجياً",
            }

            PHASE_WHY = {
                0: "لا يمكن بناء نظام تداول بدون بنية تحتية صلبة — كاشف النظام يمنع التداول في الظروف الخاطئة، والتقييم يفرز الاستراتيجيات الضعيفة",
                1: "الهدف ليس الربح بل جمع بيانات حقيقية — التداول الظلي يسجل كل إشارة بنتيجتها المحاكاة لتدريب ML لاحقاً",
                2: "بعد إثبات المفهوم، نوسّع بحذر — كل فرضية جديدة تمر بنفس القمع الصارم قبل التفعيل",
                3: "الذكاء الاصطناعي يبدأ بتوليد أفكار جديدة بناءً على ما نجح وما فشل — تطور ذاتي محكوم",
                4: "النظام يدير نفسه — أفضل الاستراتيجيات تستمر، الأضعف تتقاعد، النماذج تُحدَّث دورياً",
                5: "البدء بدون pre-build dataset (3000+ إشارة) أو قراءة Lopez de Prado = architecture mistakes حتمية. التجميد للقراءة والتخطيط، ليس للراحة",
                6: "TSMOM أبسط مكوّن في v3.0 ولديه أقوى دليل علمي (140 سنة). تشغيله بالتوازي = طبقة عاملة insurance إذا فشل Meta-Labeler",
                7: "ML الحالي يتنبأ بالاتجاه (دقة 34-46% = أقل من تعادل). Meta-Labeling يحوّله إلى مصفّي ثنائي (trade/skip) يرفع Sharpe بـ 30-50%",
                8: "اختبار حقيقي على demo قبل live. الـ 13 تغيير في 10 أيام درس مكلف — تجميد كود لأسبوعين شرط لازم قبل أي ship",
                9: "أغسطس أسوأ شهر سيولة في السنة. بدء $2,000 حقيقي في widest spreads = خسارة نفسية قد تنهي المشروع. Sep 1 = سيولة طبيعية",
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
# TAB 3: راقب الأداء الأسبوعي (Weekly Performance Monitor)
# ══════════════════════════════════════════════════════════════
with tab_weekly:
    import numpy as np

    st.markdown("""
    <div style="color:#888;font-size:13px;margin-bottom:16px">
        مقارنة أداء كل نسخة من المحرك — كل نسخة كانت كود مختلف، النتائج لا تُخلط.
        يساعد في فهم هل التغييرات حسّنت الأداء أم أضرّت به.
    </div>
    """, unsafe_allow_html=True)

    try:
        conn_t = get_conn(TRADING_DB)

        # ─── ملخص النسخ (Version Summary) ───
        st.markdown("### 📊 ملخص النسخ")
        st.markdown("""
        <div style="color:#888;font-size:12px;margin-bottom:8px">
            كل نسخة من المحرك لها كود وفلاتر مختلفة — مقارنتها توضح أثر كل تغيير.
        </div>
        """, unsafe_allow_html=True)

        versions = pd.read_sql("""
            SELECT COALESCE(engine_version, '?') as 'النسخة',
                   data_group as 'المجموعة',
                   COUNT(*) as 'الصفقات',
                   SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as 'رابحة',
                   ROUND(SUM(CASE WHEN profit > 0 THEN 1.0 ELSE 0 END) / COUNT(*) * 100, 1) as 'WR%',
                   ROUND(SUM(profit), 2) as 'الربح',
                   ROUND(AVG(profit), 2) as 'متوسط الصفقة',
                   ROUND(MIN(profit), 2) as 'أسوأ صفقة',
                   ROUND(MAX(profit), 2) as 'أفضل صفقة',
                   MIN(open_time) as 'من',
                   MAX(open_time) as 'إلى'
            FROM trades WHERE is_closed = 1
            GROUP BY engine_version, data_group
            ORDER BY MIN(open_time)
        """, conn_t)

        if not versions.empty:
            for _, v in versions.iterrows():
                pnl = v["الربح"]
                color = "#4CAF50" if pnl > 0 else "#F44336"
                group_badge = {"OLD": "📁 قديمة", "TRANSITION": "🔄 انتقالية", "STABLE": "✅ مستقرة"}.get(v["المجموعة"], "❓")

                st.markdown(f"""
                <div style="background:#12151C;border-left:3px solid {color};border-radius:6px;padding:14px 18px;margin-bottom:8px">
                    <div style="display:flex;justify-content:space-between;align-items:center">
                        <span style="color:#EEE;font-weight:700;font-size:15px">v{v['النسخة']}</span>
                        <span style="color:#888;font-size:11px">{group_badge} | {v['من'][:10] if v['من'] else '?'} ← {v['إلى'][:10] if v['إلى'] else '?'}</span>
                    </div>
                    <div style="display:flex;gap:24px;margin-top:8px;font-size:13px">
                        <span style="color:#888">{int(v['الصفقات'])} صفقة</span>
                        <span style="color:#888">WR: {v['WR%']}%</span>
                        <span style="color:{color};font-weight:700">${pnl:+,.2f}</span>
                        <span style="color:#888">متوسط: ${v['متوسط الصفقة']:+,.2f}</span>
                        <span style="color:#F44336">أسوأ: ${v['أسوأ صفقة']:+,.2f}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        st.divider()

        # ─── أداء النسخة الحالية (Current Version Performance) ───
        st.markdown("### 🎯 أداء النسخة الحالية (STABLE)")
        st.markdown("""
        <div style="color:#888;font-size:12px;margin-bottom:8px">
            فقط الصفقات من فترة الاستقرار (بعد 10 أبريل) — الكود ثابت والفلاتر لم تتغير.
        </div>
        """, unsafe_allow_html=True)

        stable_trades = pd.read_sql("""
            SELECT strategy as 'الاستراتيجية',
                   symbol as 'الزوج',
                   COUNT(*) as 'الصفقات',
                   ROUND(SUM(CASE WHEN profit > 0 THEN 1.0 ELSE 0 END) / COUNT(*) * 100, 1) as 'WR%',
                   ROUND(SUM(profit), 2) as 'الربح',
                   ROUND(AVG(profit), 2) as 'المتوسط'
            FROM trades WHERE is_closed = 1 AND data_group = 'STABLE'
            GROUP BY strategy, symbol
            ORDER BY SUM(profit) DESC
        """, conn_t)

        if not stable_trades.empty:
            # Summary metrics
            total_stable = pd.read_sql("""
                SELECT COUNT(*) as n,
                       SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as w,
                       ROUND(SUM(profit), 2) as pnl
                FROM trades WHERE is_closed = 1 AND data_group = 'STABLE'
            """, conn_t).iloc[0]

            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("صفقات مستقرة", int(total_stable["n"]))
            wr = (total_stable["w"] / total_stable["n"] * 100) if total_stable["n"] > 0 else 0
            sc2.metric("نسبة الفوز", f"{wr:.1f}%")
            sc3.metric("الربح", f"${total_stable['pnl']:+,.2f}")
            sc4.metric("من خط الأساس", f"${total_stable['pnl']:+,.2f}")

            st.dataframe(
                stable_trades,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "الربح": st.column_config.NumberColumn(format="$%.2f"),
                    "المتوسط": st.column_config.NumberColumn(format="$%.2f"),
                },
            )

            # Weekly breakdown
            st.divider()
            st.markdown("### 📅 الأداء الأسبوعي")

            weekly = pd.read_sql("""
                SELECT strftime('%Y-W%W', open_time) as 'الأسبوع',
                       COUNT(*) as 'الصفقات',
                       SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as 'رابحة',
                       ROUND(SUM(CASE WHEN profit > 0 THEN 1.0 ELSE 0 END) / COUNT(*) * 100, 1) as 'WR%',
                       ROUND(SUM(profit), 2) as 'الربح',
                       ROUND(AVG(profit), 2) as 'المتوسط'
                FROM trades WHERE is_closed = 1
                GROUP BY strftime('%Y-W%W', open_time)
                ORDER BY strftime('%Y-W%W', open_time)
            """, conn_t)

            if not weekly.empty:
                # Chart
                chart_data = weekly.set_index("الأسبوع")[["الربح"]].copy()
                st.bar_chart(chart_data, use_container_width=True)
                st.dataframe(weekly, use_container_width=True, hide_index=True)

        else:
            st.info("لا توجد صفقات مستقرة بعد")

        st.divider()

        # ─── مونت كارلو (Monte Carlo Simulation) ───
        st.markdown("### 🎲 اختبار مونت كارلو")
        st.markdown("""
        <div style="color:#888;font-size:12px;margin-bottom:8px">
            يأخذ نتائج الصفقات المستقرة ويعيد ترتيبها عشوائياً 1000 مرة — يظهر أسوأ وأفضل سيناريو ممكن بنفس الصفقات.
            إذا كان أسوأ سيناريو خسارة كارثية = النظام هش. إذا كان الفارق صغير = النظام مستقر.
        </div>
        """, unsafe_allow_html=True)

        mc_trades = pd.read_sql("""
            SELECT profit FROM trades WHERE is_closed = 1 AND data_group = 'STABLE'
        """, conn_t)

        if len(mc_trades) >= 10:
            profits = mc_trades["profit"].values
            n_simulations = 1000
            n_trades = len(profits)

            # Run Monte Carlo
            final_pnls = []
            max_dds = []
            for _ in range(n_simulations):
                shuffled = np.random.choice(profits, size=n_trades, replace=True)
                equity = np.cumsum(shuffled)
                final_pnls.append(equity[-1])
                # Max drawdown
                peak = np.maximum.accumulate(equity)
                dd = peak - equity
                max_dds.append(dd.max())

            final_pnls = np.array(final_pnls)
            max_dds = np.array(max_dds)

            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("أفضل سيناريو", f"${np.percentile(final_pnls, 95):+,.0f}")
            mc2.metric("الوسيط", f"${np.median(final_pnls):+,.0f}")
            mc3.metric("أسوأ سيناريو", f"${np.percentile(final_pnls, 5):+,.0f}")
            mc4.metric("أقصى تراجع متوقع", f"${np.median(max_dds):,.0f}")

            # Distribution chart
            mc_df = pd.DataFrame({"P&L": final_pnls})
            st.bar_chart(mc_df["P&L"].value_counts(bins=30).sort_index(), use_container_width=True)

            # Risk metrics
            prob_profit = (final_pnls > 0).mean() * 100
            prob_big_loss = (final_pnls < -5000).mean() * 100

            st.markdown(f"""
            <div style="background:#12151C;border-radius:8px;padding:14px 18px;margin-top:8px">
                <div style="display:flex;gap:32px;font-size:13px">
                    <span style="color:#4CAF50">احتمال الربح: <b>{prob_profit:.0f}%</b></span>
                    <span style="color:#F44336">احتمال خسارة > $5K: <b>{prob_big_loss:.0f}%</b></span>
                    <span style="color:#888">عدد المحاكاة: {n_simulations}</span>
                    <span style="color:#888">حجم العينة: {n_trades} صفقة</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        else:
            st.info(f"تحتاج 10+ صفقات مستقرة للمحاكاة (لديك {len(mc_trades)})")

        st.divider()

        # ─── الشرح (Explanation) ───
        st.markdown("### ❓ الشرح")
        st.markdown("""
        <div style="background:#0D1117;border:1px solid #2D3748;border-radius:8px;padding:16px 20px">
            <div style="color:#CCC;font-size:13px;line-height:2">
                <b style="color:#1E88E5">لماذا نفصل النسخ؟</b><br>
                كل نسخة من المحرك كانت كود مختلف — فلاتر مختلفة، حجم لوت مختلف، إعدادات مختلفة.
                خلط نتائج نسخة قديمة (لوت 10) مع الحالية (لوت 1) يعطي صورة مضللة تماماً.
                <br><br>
                <b style="color:#FF9800">لماذا مونت كارلو؟</b><br>
                ترتيب الصفقات مهم — 5 خسائر متتالية في البداية تختلف عن 5 خسائر في النهاية.
                المحاكاة تعيد الترتيب 1000 مرة لتظهر كل السيناريوهات الممكنة بنفس الصفقات.
                إذا كان أغلب السيناريوهات رابحة = النظام لديه Edge حقيقية.
                <br><br>
                <b style="color:#4CAF50">كيف نستخدم هذا؟</b><br>
                ● إذا احتمال الربح > 60% = النظام يعمل<br>
                ● إذا أقصى تراجع > 20% من الرصيد = المخاطرة عالية جداً<br>
                ● إذا أسوأ سيناريو > -$10K = يجب تقليل حجم اللوت<br>
                ● فقط بيانات STABLE تُستخدم — القديمة للأرشيف فقط
            </div>
        </div>
        """, unsafe_allow_html=True)

        conn_t.close()

    except Exception as e:
        st.error(f"خطأ في تحميل الأداء الأسبوعي: {e}")


# ══════════════════════════════════════════════════════════════
# TAB 4: تقسيم البيانات (Data Segmentation)
# ══════════════════════════════════════════════════════════════
with tab_data:
    st.markdown("""
    <div style="color:#888;font-size:13px;margin-bottom:16px">
        البيانات مقسمة لثلاث مجموعات حسب استقرار الكود — لأن خلط بيانات من إصدارات مختلفة يؤدي لنتائج مضللة.
        <b style="color:#FF9800">القاعدة:</b> فقط مجموعة STABLE تُستخدم لتدريب ML وتقييم الأداء.
    </div>
    """, unsafe_allow_html=True)

    try:
        conn_i = get_conn(IMP_DB)
        conn_t = get_conn(TRADING_DB)

        # Load segmentation log
        segments = pd.read_sql("SELECT * FROM data_segmentation_log ORDER BY id", conn_i)

        if not segments.empty:
            GROUP_COLORS = {"OLD": "#666", "TRANSITION": "#FF9800", "STABLE": "#4CAF50"}
            GROUP_AR = {"OLD": "قديمة (أرشيف)", "TRANSITION": "انتقالية (تعلم)", "STABLE": "مستقرة (تدريب ML)"}
            GROUP_ICONS = {"OLD": "📁", "TRANSITION": "🔄", "STABLE": "✅"}

            # Summary metrics
            c1, c2, c3 = st.columns(3)
            for i, (_, seg) in enumerate(segments.iterrows()):
                g = seg["group_name"]
                col = [c1, c2, c3][i]
                col.metric(
                    f"{GROUP_ICONS.get(g, '')} {GROUP_AR.get(g, g)}",
                    f"{int(seg['trade_count'])} صفقة",
                    f"${seg['total_pnl']:+,.0f} | WR {seg['win_rate']}%",
                )

            st.divider()

            # Live count from trading.db
            for _, seg in segments.iterrows():
                g = seg["group_name"]
                color = GROUP_COLORS.get(g, "#666")
                ar_name = GROUP_AR.get(g, g)

                # Get current count from DB
                try:
                    live = pd.read_sql(
                        f"SELECT COUNT(*) as n, ROUND(SUM(profit),2) as pnl FROM trades WHERE is_closed=1 AND data_group='{g}'",
                        conn_t,
                    )
                    live_count = int(live.iloc[0]["n"]) if not live.empty else 0
                    live_pnl = live.iloc[0]["pnl"] or 0 if not live.empty else 0
                except Exception:
                    live_count = int(seg["trade_count"])
                    live_pnl = seg["total_pnl"]

                with st.expander(f"{GROUP_ICONS.get(g, '')} {g} — {ar_name} ({live_count} صفقة | ${live_pnl:+,.0f})", expanded=(g == "STABLE")):
                    st.markdown(f"""
                    <div style="background:#0D1117;border-left:3px solid {color};border-radius:6px;padding:14px 18px;margin-bottom:10px">
                        <div style="color:#CCC;font-size:13px;line-height:1.8;margin-bottom:8px">{seg['description']}</div>
                        <div style="color:#888;font-size:12px">
                            <b>الفترة:</b> {seg['date_from']} ← {seg['date_to']}  |
                            <b>الإصدارات:</b> {seg['engine_versions']}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.markdown(f"""
                        <div style="background:#0D2818;border:1px solid #1B5E20;border-radius:6px;padding:12px 16px">
                            <div style="color:#4CAF50;font-weight:700;font-size:12px;margin-bottom:6px">صالحة لـ</div>
                            <div style="color:#CCC;font-size:12px;line-height:1.8">{seg['valid_for']}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    with col_b:
                        st.markdown(f"""
                        <div style="background:#2D1111;border:1px solid #B71C1C;border-radius:6px;padding:12px 16px">
                            <div style="color:#F44336;font-weight:700;font-size:12px;margin-bottom:6px">غير صالحة لـ</div>
                            <div style="color:#CCC;font-size:12px;line-height:1.8">{seg['not_valid_for']}</div>
                        </div>
                        """, unsafe_allow_html=True)

                    st.markdown(f"""
                    <div style="background:#12151C;border-radius:6px;padding:10px 16px;margin-top:8px">
                        <div style="color:#888;font-size:11px;margin-bottom:4px">الإعدادات النشطة في هذه الفترة:</div>
                        <div style="color:#7dd3fc;font-size:11px;font-family:monospace">{seg['config_changes']}</div>
                    </div>
                    """, unsafe_allow_html=True)

            st.divider()

            # Baseline info
            st.markdown("""
            <div style="background:#0D1117;border:1px solid #2D3748;border-radius:8px;padding:16px 20px">
                <div style="color:#1E88E5;font-weight:700;margin-bottom:8px">خط الأساس الجديد</div>
                <div style="color:#CCC;font-size:13px;line-height:1.8">
                    <b>التاريخ:</b> 14 أبريل 2026<br>
                    <b>الرصيد:</b> $87,580<br>
                    <b>القاعدة:</b> كل التقييمات تُقاس من هذا التاريخ فقط<br>
                    <b>تجميد الكود:</b> لا تغييرات حتى 28 أبريل — لجمع 200+ إشارة مستقرة
                </div>
            </div>
            """, unsafe_allow_html=True)

        else:
            st.info("لم يتم تقسيم البيانات بعد — شغّل scripts/segment_data.py")

        conn_i.close()
        conn_t.close()

    except Exception as e:
        st.error(f"خطأ في تحميل تقسيم البيانات: {e}")


# ══════════════════════════════════════════════════════════════
# TAB 4: تحليل الأنظمة (Regime Analysis)
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
# TAB: Meta-Labeler Prototype Results
# ══════════════════════════════════════════════════════════════
with tab_metalabel:
    st.markdown("""
    <div style="color:#888;font-size:13px;margin-bottom:16px">
        نتائج prototype الـ Meta-Labeler على 1,144 إشارة أولية. كل تشغيل يختبر architecture مختلف (global / per-strategy / per-combo).
        <br/><b style="color:#FF9800">كيف تقرأ:</b> AUC ≥ 0.55 = model له إشارة حقيقية. WR lift ≥ 5 نقاط = يستحق التعقيد.
    </div>
    """, unsafe_allow_html=True)

    try:
        conn = get_conn(IMP_DB)
        runs = pd.read_sql("""
            SELECT run_time, architecture, scope, n_signals, n_features,
                   auc_mean, auc_std, baseline_wr, lifted_wr, wr_lift_points,
                   precision_mean, recall_mean, f1_mean, verdict, notes
            FROM meta_labeler_runs
            ORDER BY run_time DESC, architecture, scope
        """, conn)
        conn.close()

        if runs.empty:
            st.info("لم تُشغَّل نماذج meta-labeler بعد. شغّل scripts/research_meta_labeler_prototype.py")
        else:
            # Latest run summary
            latest_time = runs["run_time"].max()
            latest = runs[runs["run_time"] == latest_time]

            st.markdown(f"**آخر تشغيل:** {latest_time} — {len(latest)} نموذج")

            # Top-line metrics
            best = latest.loc[latest["wr_lift_points"].idxmax()]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("أفضل Architecture", best["architecture"])
            c2.metric("أفضل Scope", best["scope"])
            c3.metric("AUC", f"{best['auc_mean']:.3f}" if pd.notna(best['auc_mean']) else "—")
            c4.metric("WR Lift", f"{best['wr_lift_points']:+.1f}pp",
                      f"{best['baseline_wr']:.1f}% → {best['lifted_wr']:.1f}%")

            st.divider()

            # Results by architecture
            for arch in ["GLOBAL", "PER_STRATEGY", "PER_COMBO"]:
                arch_rows = latest[latest["architecture"] == arch]
                if arch_rows.empty:
                    continue

                arch_desc = {
                    "GLOBAL": "نموذج واحد لكل الإشارات",
                    "PER_STRATEGY": "نموذج منفصل لكل استراتيجية (MACD / RSI)",
                    "PER_COMBO": "نموذج لكل (استراتيجية × زوج) — يتطلب ≥80 عينة",
                }.get(arch, "")
                st.markdown(f"### {arch}")
                st.caption(arch_desc)

                display = arch_rows[[
                    "scope", "n_signals", "auc_mean", "auc_std",
                    "baseline_wr", "lifted_wr", "wr_lift_points", "verdict",
                ]].copy()
                display.columns = [
                    "Scope", "N", "AUC", "AUC std",
                    "Raw WR", "Filtered WR", "Lift (pp)", "Verdict",
                ]
                display["AUC"] = display["AUC"].apply(lambda x: f"{x:.3f}" if pd.notna(x) else "—")
                display["AUC std"] = display["AUC std"].apply(lambda x: f"{x:.3f}" if pd.notna(x) else "—")
                display["Raw WR"] = display["Raw WR"].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "—")
                display["Filtered WR"] = display["Filtered WR"].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "—")
                display["Lift (pp)"] = display["Lift (pp)"].apply(lambda x: f"{x:+.1f}" if pd.notna(x) else "—")

                st.dataframe(display, use_container_width=True, hide_index=True)

            st.divider()

            # Historical runs expander (if more than one run)
            all_times = runs["run_time"].unique()
            if len(all_times) > 1:
                with st.expander(f"📜 كل التشغيلات السابقة ({len(all_times)} runs)"):
                    st.dataframe(
                        runs[["run_time", "architecture", "scope", "auc_mean",
                              "wr_lift_points", "verdict"]],
                        use_container_width=True, hide_index=True,
                    )

            # Interpretation box
            strong = (latest["verdict"].str.contains("STRONG", na=False)).sum()
            weak = (latest["verdict"].str.contains("WEAK", na=False)).sum()
            marginal = (latest["verdict"].str.contains("MARGINAL", na=False)).sum()
            none_n = (latest["verdict"].str.contains("NONE", na=False)).sum()

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("✅ Strong", strong)
            c2.metric("⚠️ Weak", weak)
            c3.metric("❌ Marginal", marginal)
            c4.metric("❌ None", none_n)

            if strong > 0:
                st.success(
                    f"**الخلاصة**: {strong} architecture ناجح. هذا هو نقطة انطلاق Phase 7. "
                    f"التقرير الكامل: `docs/research/meta_labeler_prototype.md`"
                )
            elif weak > 0:
                st.warning(
                    f"**الخلاصة**: فقط {weak} architecture ضعيف. يمكن المتابعة لكن مع توقعات أقل "
                    f"(Sharpe lift 5-10% بدلاً من 30%)."
                )
            else:
                st.error(
                    "**الخلاصة**: لا يوجد architecture ناجح. راجع feature set أو labels قبل Phase 7."
                )

    except Exception as e:
        st.error(f"خطأ في تحميل نتائج meta-labeler: {e}")

    # ─── Expectancy section (same tab) ───
    st.divider()
    st.markdown("### 💰 Expectancy per صفقة")
    st.markdown("""
    <div style="color:#888;font-size:12px;margin-bottom:8px">
        Expectancy = (WR × متوسط الربح) − ((1−WR) × متوسط الخسارة) — الرقم الحقيقي الذي يحدد إذا كانت الاستراتيجية تكسب أو تخسر.
        <br/>WR عالية لا تكفي. ml_direct كان WR=75.7% وخسر $33,907.
    </div>
    """, unsafe_allow_html=True)

    try:
        conn = get_conn(IMP_DB)
        exp = pd.read_sql("""
            SELECT run_time, source, strategy, symbol, scope_label,
                   n_signals, wr_pct, avg_win, avg_loss, rr_ratio,
                   expectancy_per_signal, unit, extras
            FROM expectancy_analysis
            ORDER BY run_time DESC
        """, conn)
        conn.close()

        if exp.empty:
            st.info("لم تُشغَّل تحليل expectancy بعد. شغّل scripts/research_expectancy.py")
        else:
            latest_exp_time = exp["run_time"].max()
            latest_exp = exp[exp["run_time"] == latest_exp_time]

            st.caption(f"آخر تشغيل: {latest_exp_time}  ·  {len(latest_exp)} سجل")

            # Backtest per-pair
            bt_per_pair = latest_exp[
                (latest_exp["source"] == "backtest") & latest_exp["symbol"].notna()
            ].copy()
            if not bt_per_pair.empty:
                bt_per_pair = bt_per_pair.sort_values("expectancy_per_signal", ascending=False)
                st.markdown("**Backtest — (strategy × pair)** · وحدة: pips per signal")
                disp = bt_per_pair[[
                    "strategy", "symbol", "n_signals", "wr_pct", "rr_ratio",
                    "expectancy_per_signal",
                ]].copy()
                disp.columns = ["Strategy", "Pair", "N", "WR", "RR", "Exp (pips/signal)"]
                disp["WR"] = disp["WR"].apply(lambda x: f"{x:.1f}%")
                disp["RR"] = disp["RR"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
                disp["Exp (pips/signal)"] = disp["Exp (pips/signal)"].apply(lambda x: f"{x:+.1f}")
                st.dataframe(disp, use_container_width=True, hide_index=True)

            # Live expectancy — top winners + bottom losers
            live_exp = latest_exp[latest_exp["source"] == "live"].copy()
            if not live_exp.empty:
                live_exp = live_exp.sort_values("expectancy_per_signal", ascending=False)
                st.markdown("**Live trades — Top 10 رابحة**  ($ per trade)")
                top = live_exp.head(10)[[
                    "strategy", "symbol", "n_signals", "wr_pct", "rr_ratio",
                    "expectancy_per_signal",
                ]].copy()
                top.columns = ["Strategy", "Pair", "N", "WR", "RR", "$/trade"]
                top["WR"] = top["WR"].apply(lambda x: f"{x:.0f}%")
                top["RR"] = top["RR"].apply(lambda x: f"{x:.2f}" if pd.notna(x) and x < 100 else "∞")
                top["$/trade"] = top["$/trade"].apply(lambda x: f"${x:+,.0f}")
                st.dataframe(top, use_container_width=True, hide_index=True)

                st.markdown("**Live trades — Bottom 10 خاسرة**")
                bot = live_exp.tail(10)[[
                    "strategy", "symbol", "n_signals", "wr_pct", "rr_ratio",
                    "expectancy_per_signal",
                ]].copy()
                bot.columns = ["Strategy", "Pair", "N", "WR", "RR", "$/trade"]
                bot["WR"] = bot["WR"].apply(lambda x: f"{x:.0f}%")
                bot["RR"] = bot["RR"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
                bot["$/trade"] = bot["$/trade"].apply(lambda x: f"${x:+,.0f}")
                st.dataframe(bot, use_container_width=True, hide_index=True)

            # Meta-filtered row
            meta = latest_exp[latest_exp["source"] == "meta_filtered"]
            if not meta.empty:
                row = meta.iloc[0]
                st.markdown("**Meta-filtered RSI impact**")
                c1, c2, c3 = st.columns(3)
                c1.metric("Keep-rate", row["extras"].split("keep_rate=")[1].split(",")[0] if "keep_rate" in str(row["extras"]) else "—")
                c2.metric("Filtered WR", f"{row['wr_pct']:.1f}%")
                c3.metric("Filtered Exp", f"{row['expectancy_per_signal']:+.1f} pips")

            # Sobering takeaway
            n_positive = (bt_per_pair["expectancy_per_signal"] > 0).sum() if not bt_per_pair.empty else 0
            n_combos = len(bt_per_pair) if not bt_per_pair.empty else 0
            if n_positive < n_combos / 2:
                st.error(
                    f"⚠️ **تحذير**: فقط {n_positive}/{n_combos} combo لها expectancy موجبة في backtest. "
                    "النظام هش أكثر مما تبدو metrics الفوز. راجع docs/research/expectancy_report.md"
                )

    except Exception as e:
        st.error(f"خطأ في تحميل expectancy: {e}")

    # ─── TSMOM section (same tab) ───
    st.divider()
    st.markdown("### 📈 TSMOM Prototype — Layer 3")
    st.markdown("""
    <div style="color:#888;font-size:12px;margin-bottom:8px">
        استراتيجية Time-Series Momentum (Moskowitz/Ooi/Pedersen 2012, AQR 2017). شهرية، لا ML.
        <br/>القاعدة: إذا السعر الحالي > السعر قبل 12 شهراً → LONG. حجم الصفقة = target_vol / realized_vol. AQR benchmark: Sharpe ~0.7، عائد سنوي ~10%.
    </div>
    """, unsafe_allow_html=True)

    try:
        conn = get_conn(IMP_DB)
        tsmom = pd.read_sql("""
            SELECT run_time, scope, n_months, start_date, end_date,
                   annual_return, annual_vol, sharpe, sortino, max_drawdown,
                   hit_rate_monthly, cagr, verdict
            FROM tsmom_runs
            ORDER BY run_time DESC
        """, conn)
        conn.close()

        if tsmom.empty:
            st.info("لم تُشغَّل TSMOM prototype بعد. شغّل scripts/research_tsmom_prototype.py")
        else:
            latest_tsmom_time = tsmom["run_time"].max()
            latest_tsmom = tsmom[tsmom["run_time"] == latest_tsmom_time]

            # Portfolio row first
            port = latest_tsmom[latest_tsmom["scope"] == "portfolio_equal_weight"]
            pairs_rows = latest_tsmom[latest_tsmom["scope"] != "portfolio_equal_weight"]

            if not port.empty:
                p = port.iloc[0]
                st.markdown(f"**محفظة (equal-weight) — {p['verdict']}**")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Sharpe", f"{p['sharpe']:.2f}", f"AQR: ~0.70")
                c2.metric("عائد سنوي", f"{p['annual_return']*100:+.1f}%", f"AQR: ~10%")
                c3.metric("Max DD", f"{p['max_drawdown']*100:.1f}%", f"AQR: ~-25%")
                c4.metric("CAGR", f"{p['cagr']*100:.2f}%")
                st.caption(f"{p['start_date']} → {p['end_date']} · {p['n_months']} شهر · hit rate {p['hit_rate_monthly']*100:.1f}%")

            if not pairs_rows.empty:
                st.markdown("**نتائج كل زوج على حدة:**")
                disp = pairs_rows[[
                    "scope", "n_months", "annual_return", "annual_vol",
                    "sharpe", "max_drawdown", "hit_rate_monthly", "verdict",
                ]].copy()
                disp.columns = ["Pair", "Months", "Ann Ret", "Ann Vol",
                                "Sharpe", "Max DD", "Hit%", "Verdict"]
                disp["Ann Ret"] = disp["Ann Ret"].apply(lambda x: f"{x*100:+.1f}%")
                disp["Ann Vol"] = disp["Ann Vol"].apply(lambda x: f"{x*100:.1f}%")
                disp["Sharpe"] = disp["Sharpe"].apply(lambda x: f"{x:+.2f}")
                disp["Max DD"] = disp["Max DD"].apply(lambda x: f"{x*100:.1f}%")
                disp["Hit%"] = disp["Hit%"].apply(lambda x: f"{x*100:.0f}%")
                st.dataframe(disp, use_container_width=True, hide_index=True)

            # Equity curve chart
            chart_path = Path("docs/research/tsmom_equity_curve.png")
            if chart_path.exists():
                st.markdown("**Equity curve:**")
                st.image(str(chart_path))

            # Auto-interpretation
            if not port.empty:
                sharpe = port.iloc[0]["sharpe"]
                if sharpe >= 0.5:
                    st.success(
                        f"**TSMOM قابلة للاستخدام** (Sharpe {sharpe:.2f}). "
                        "يستحق البناء كطبقة موازية في Phase 6."
                    )
                elif sharpe >= 0.3:
                    st.warning(
                        f"**TSMOM ضعيفة** (Sharpe {sharpe:.2f}) — لكن بعض الأزواج فردياً "
                        "لها Sharpe أعلى. راجع per-pair جدول أعلاه."
                    )
                else:
                    st.error(
                        f"**TSMOM فاشلة** على هذه البيانات (Sharpe {sharpe:.2f} ضد AQR 0.7). "
                        "السبب المحتمل: 7 أزواج USD-centric لا توفّر diversification كافي "
                        "مقارنة بـ 67 سوق في أبحاث AQR. **Option C (TSMOM-only) خارج الطاولة.**"
                    )

    except Exception as e:
        st.error(f"خطأ في تحميل TSMOM: {e}")


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
