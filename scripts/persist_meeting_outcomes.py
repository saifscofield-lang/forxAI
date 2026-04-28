"""Phase 1 of Post-meeting.md task — DB persistence (AI-015 + AI-016).
Inserts 8 rows into go_no_go_decisions and updates project_phases / phase_steps."""
import sqlite3

DB = "data/improvements.db"
DECIDED_BY = "meeting_2026_04_28"
TODAY = "2026-04-28"
TRANSITION = "2026-05-04"

VOTES = [
    # (vote, phase, verdict, gates_p, gates_t, next_action, en, ar)
    (1, 5, "GREEN", 6, 8,
     "AI-014, transition_date 2026-05-04",
     "[Vote 1] Approved Phase 5 closure and Phase 6/7 launch on 2026-05-04. Phase 5 deliverables complete: code freeze, H1 backfill, feature shortlist, primary signals dataset, meta-labeler validation, demo stability restored. Approval here is upstream of Phase 8 gating; does not commit Jun 8.",
     "[التصويت 1] تمت الموافقة على إغلاق المرحلة 5 وانطلاق المرحلتين 6/7 في 2026-05-04. مخرجات المرحلة 5 مكتملة: تجميد الكود، backfill لـ H1، اختيار الميزات، dataset الإشارات الأولية، التحقق من meta-labeler، استقرار الـ demo. هذه الموافقة سابقة لبوابة المرحلة 8 ولا تلتزم بـ 8 يونيو."),
    (2, 8, "YELLOW", 0, 5,
     "June 1 gate review; 5 blockers OPEN",
     "[Vote 2] Phase 8 (paper trading) DEFERRED from Jun 8 to a 2026-06-01 gate review. Five blockers must clear: AI-001 zero-BUY, AI-002 retirements/blocks merged, AI-003 migration system, AI-005 OOS holdout, AI-006/7 OVERLAP shadow-validation. Capability gates over calendar gates. 'Phase 8 indefinitely deferred' is acceptable if blockers persist — alternative would invalidate the dataset.",
     "[التصويت 2] تأجيل المرحلة 8 (التداول الورقي) من 8 يونيو إلى مراجعة بوابة في 2026-06-01. يجب إنهاء 5 معوقات: AI-001 zero-BUY، AI-002 الإيقافات/الحجوب المدمجة، AI-003 نظام الترحيل، AI-005 OOS holdout، AI-006/7 التحقق من فلتر OVERLAP. بوابات القدرة فوق بوابات التقويم. \"تأجيل المرحلة 8 إلى أجل غير مسمى\" مقبول إذا استمرت المعوقات."),
    (3, 5, "YELLOW", None, None,
     "AI-006 + AI-007 shadow-mode May 4 - May 25",
     "[Vote 3] OVERLAP filter for XAUUSD goes shadow-only for 14+ days. Post-hoc hypothesis (generated and tested on the same dataset) disqualifies p=0.006 from carrying nominal weight. Likely confounded with ATR. Require persistence on n>=20 new OVERLAP trades + ATR-controlled analysis (AI-007) before any paper.yaml installation.",
     "[التصويت 3] فلتر OVERLAP لـ XAUUSD سيعمل في وضع shadow فقط لمدة 14+ يوم. الفرضية post-hoc (تم توليدها واختبارها على نفس الـ dataset) تُسقط الوزن الاسمي لـ p=0.006. مرشح للتداخل مع ATR. يتطلب استمرار النمط على 20+ صفقة OVERLAP جديدة + تحليل مضبوط بـ ATR (AI-007) قبل أي تركيب في paper.yaml."),
    (4, 5, "GREEN", None, None,
     "AI-002a retire bollinger_bounce before May 4",
     "[Vote 4] Retire bollinger_bounce entirely from active rotation before Phase 7 starts (2026-05-04). Structural pathology: WR 68%, R:R 0.12, PF 0.26 over 25 v3 trades. Restructure path costs Phase 8 timeline; design-level issue not parameter-level. Future bounded-mean-reversion strategies must be built with TP >= 2*SL as design constraint, not as patch.",
     "[التصويت 4] إلغاء استراتيجية bollinger_bounce بالكامل من الدوران النشط قبل بدء المرحلة 7 (2026-05-04). علة بنيوية: WR 68%، R:R 0.12، PF 0.26 على 25 صفقة في v3. مسار إعادة الهيكلة يكلّف الجدول الزمني للمرحلة 8؛ المشكلة على مستوى التصميم لا المعاملات. الاستراتيجيات المستقبلية يجب أن تُبنى بقيد TP >= 2*SL كقيد تصميم، لا كرقعة."),
    (5, 5, "GREEN", None, None,
     "AI-002b retire ml_filtered_sma before May 4",
     "[Vote 5] Retire ml_filtered_sma entirely before Phase 7. Same structural pathology as bollinger_bounce (R:R 0.11, PF 0.23 — actually worse). Second strategy with this exact pattern. Flagged AI-017 (meeting-emergent): audit remaining strategies for system-wide TP/SL design tendency before Phase 7.",
     "[التصويت 5] إلغاء ml_filtered_sma بالكامل قبل المرحلة 7. نفس العلة البنيوية مثل bollinger_bounce (R:R 0.11، PF 0.23 — أسوأ في الواقع). ثاني استراتيجية بنفس النمط بالضبط. تم رفع AI-017 (ناشئ من الاجتماع): فحص الاستراتيجيات المتبقية لميل تصميم TP/SL على مستوى النظام قبل المرحلة 7."),
    (6, 5, "GREEN", None, None,
     "AI-002c block ml_direct/XAUUSD in both configs",
     "[Vote 6] Block ml_direct/XAUUSD in BOTH base.yaml AND paper.yaml until zero-BUY structural issue is resolved. The +$21k profit is data we are choosing to set aside, not data validating the design. Honors the same methodological standard applied to v4 closure. Forward risk in BOTH regimes (rising and falling gold) requires blocking until structural issue resolved.",
     "[التصويت 6] حجب ml_direct/XAUUSD في كلٍ من base.yaml و paper.yaml حتى يتم حل مشكلة zero-BUY البنيوية. الأرباح بمقدار +21,000$ هي بيانات نختار وضعها جانباً، وليست بيانات تثبت صحة التصميم. هذا يحترم نفس المعيار المنهجي المطبَّق على إغلاق v4. المخاطر المستقبلية في كلا النظامين (الذهب الصاعد والهابط) تتطلب الحجب حتى حل المشكلة البنيوية."),
    (7, 8, "RED", 0, 1,
     "AI-001 BLOCKING; June 1 gate cannot GREEN without it",
     "[Vote 7] Zero-BUY on XAUUSD elevated from Phase 7 deliverable to BLOCKING for Phase 8. Consistent with Vote 6. AI-001 must land before June 1 gate. If 5-week window insufficient, Phase 8 slips — that is the correct outcome, not a problem to be routed around. A zero-BUY system in a projected reversal regime cannot be paper-traded responsibly.",
     "[التصويت 7] رفع مشكلة zero-BUY على XAUUSD من مخرجات المرحلة 7 إلى معوّق للمرحلة 8. متسق مع التصويت 6. يجب إنجاز AI-001 قبل بوابة 1 يونيو. إذا كانت نافذة الـ 5 أسابيع غير كافية، تتأجل المرحلة 8 — هذه هي النتيجة الصحيحة، لا مشكلة يجب التحايل عليها. نظام zero-BUY في نظام انعكاس متوقع لا يمكن تشغيله ورقياً بمسؤولية."),
    (8, 9, "YELLOW", None, None,
     "AI-018 watchdog implementation; July re-eval (AI-019)",
     "[Vote 8] Phase 9 hosting decided NOW: keep on local Windows workstation. Operational simplicity during May-June structural fixes. Snapshot gaps are restart-discipline issues, not infrastructure issues — addressable via AI-018 watchdog (boot-on-startup + auto-restart on log-staleness). July re-evaluation (AI-019) conditional on Phase 8 GREEN.",
     "[التصويت 8] قرار استضافة المرحلة 9 الآن: البقاء على محطة Windows المحلية. بساطة تشغيلية خلال إصلاحات مايو-يونيو البنيوية. فجوات اللقطات هي مشكلات انضباط إعادة التشغيل، وليست مشكلات بنية تحتية — يمكن معالجتها عبر AI-018 watchdog (التشغيل عند الإقلاع + إعادة التشغيل التلقائي عند تأخر السجل). إعادة تقييم في يوليو (AI-019) مشروطة بأن تكون المرحلة 8 GREEN."),
]

con = sqlite3.connect(DB)
cur = con.cursor()
try:
    con.execute("BEGIN")

    # ─── 1.1 Insert 8 vote rows ────────────────────────────────────────
    for v_num, phase, verdict, gp, gt, na, en, ar in VOTES:
        cur.execute("""
            INSERT INTO go_no_go_decisions
              (phase_number, decision_date, verdict, gates_passed, gates_total,
               rationale_en, rationale_ar, decided_by, next_action)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (phase, TODAY, verdict, gp, gt, en, ar, DECIDED_BY, na))

    # ─── 1.2 project_phases updates ────────────────────────────────────
    # Phase 5: COMPLETED today
    cur.execute(
        "UPDATE project_phases SET status='COMPLETED', completed_at=?, notes=? WHERE phase_number=5",
        (TODAY,
         "Phase 5 closed 2026-04-28 by go/no-go meeting (Vote 1). All major deliverables done: code freeze (v2.4-frozen), H1 backfill, feature shortlist (82->20), primary signals dataset (1,144 signals), meta-labeler validation (RSI valid / MACD rejected), demo stability restored 2026-04-22. Phases 6+7 launch 2026-05-04."))

    # Phase 6: IN_PROGRESS starting May 4
    cur.execute(
        "UPDATE project_phases SET status='IN_PROGRESS', started_at=?, notes=? WHERE phase_number=6",
        (TRANSITION,
         "Phase 6 (TSMOM Layer build) started 2026-05-04 per 04-28 meeting Vote 1. Parallel with Phase 7. Operates on existing v3 trade rotation; not blocked by Phase 8 gate."))

    # Phase 7: IN_PROGRESS starting May 4
    cur.execute(
        "UPDATE project_phases SET status='IN_PROGRESS', started_at=?, notes=? WHERE phase_number=7",
        (TRANSITION,
         "Phase 7 (Meta-Labeler Rebuild) started 2026-05-04 per 04-28 meeting Vote 1. AI-017 (R:R pathology audit) is a Phase 7 prerequisite — must complete before training-set composition is finalized. AI-002 (retire bollinger_bounce + ml_filtered_sma) is also a Phase 7 prerequisite."))

    # Phase 8: DEFERRED with gate review June 1
    cur.execute(
        "UPDATE project_phases SET status='DEFERRED', notes=? WHERE phase_number=8",
        ("Phase 8 (paper trading) DEFERRED per 04-28 meeting Vote 2. Gate review 2026-06-01. 5 blockers: AI-001 (zero-BUY), AI-002 (retirements/blocks), AI-003 (migration system), AI-005 (OOS holdout), AI-006/007 (OVERLAP shadow). All five must clear; any RED extends deferral.",))

    # ─── 1.2b phase_steps: mark Phase 5 step 9 (the meeting itself) COMPLETE ──
    cur.execute(
        "UPDATE phase_steps SET status='COMPLETED', completed_at=?, notes=? WHERE phase_number=5 AND step_order=9",
        (TODAY,
         "v3 go/no-go meeting held 2026-04-28. 8 votes decided (7 aligned with external review, 1 deviation on Vote 8 with mitigation). See docs/research/decision_log.md and docs/research/external_review_2026_04_28.md."))

    # Add tracking step to Phase 6 (insert if missing)
    cnt6 = cur.execute("SELECT COUNT(*) FROM phase_steps WHERE phase_number=6").fetchone()[0]
    if cnt6 == 0:
        cur.execute(
            "INSERT INTO phase_steps (phase_number, step_order, description, description_ar, status, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (6, 1,
             "TSMOM Layer build — operational on v3 trade rotation, May 4 - Jun 8",
             "بناء طبقة TSMOM — تشغيلي على دوران تداول v3، 4 مايو - 8 يونيو",
             "IN_PROGRESS",
             "Started 2026-05-04 per 04-28 meeting Vote 1."))

    # Add tracking step to Phase 7 (insert if missing)
    cnt7 = cur.execute("SELECT COUNT(*) FROM phase_steps WHERE phase_number=7").fetchone()[0]
    if cnt7 == 0:
        cur.execute(
            "INSERT INTO phase_steps (phase_number, step_order, description, description_ar, status, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (7, 1,
             "Meta-Labeler Rebuild — Triple Barrier + Purged K-Fold + LightGBM",
             "إعادة بناء Meta-Labeler — Triple Barrier + Purged K-Fold + LightGBM",
             "IN_PROGRESS",
             "Started 2026-05-04 per 04-28 meeting Vote 1. Prerequisites: AI-017 R:R audit + AI-002 retirements/blocks must complete first."))

    con.commit()
    print("[OK] all writes committed")
except Exception as e:
    con.rollback()
    print(f"[FAIL] rolled back: {e}")
    raise
finally:
    con.close()

# ─── Verification ────────────────────────────────────────────────────
con = sqlite3.connect(DB)
print()
print("=" * 78)
print("VERIFICATION")
print("=" * 78)

n_meeting = con.execute(f"SELECT COUNT(*) FROM go_no_go_decisions WHERE decided_by=?", (DECIDED_BY,)).fetchone()[0]
print(f"go_no_go_decisions WHERE decided_by='{DECIDED_BY}': {n_meeting}  [expected 8]")

print()
print("Verdict distribution (this meeting):")
for r in con.execute(
    "SELECT phase_number, verdict, COUNT(*) FROM go_no_go_decisions WHERE decided_by=? GROUP BY phase_number, verdict ORDER BY phase_number, verdict",
    (DECIDED_BY,)).fetchall():
    print(f"  phase {r[0]}: {r[1]:8s} count={r[2]}")

print()
print("Phase status updates:")
for r in con.execute(
    "SELECT phase_number, name, status, started_at, completed_at FROM project_phases WHERE phase_number IN (5,6,7,8) ORDER BY phase_number"
).fetchall():
    print(f"  Phase {r[0]}: {r[2]:14s} started={r[3]} completed={r[4]} | {r[1][:60]}")

print()
print("phase_steps activity since 2026-04-28:")
for r in con.execute(
    "SELECT phase_number, step_order, status, completed_at, substr(description,1,55) FROM phase_steps "
    "WHERE completed_at >= '2026-04-28' OR (status='IN_PROGRESS' AND phase_number IN (6,7)) ORDER BY phase_number, step_order"
).fetchall():
    print(f"  P{r[0]} step{r[1]} [{r[2]:11s}] done={r[3]} | {r[4]}")

con.close()
