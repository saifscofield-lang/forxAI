"""Generate Arabic PDF report for ForexAI and send to Telegram."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from fpdf import FPDF
import sqlite3
from datetime import datetime


class ArabicPDF(FPDF):
    def __init__(self):
        super().__init__()
        # Use Amiri font for Arabic support
        self.add_font("Amiri", "", "C:/Windows/Fonts/Amiri-Regular.ttf", uni=True)
        self.add_font("Amiri", "B", "C:/Windows/Fonts/Amiri-Bold.ttf", uni=True)

    def rtl_cell(self, w, h, txt, border=0, ln=0, align="R", fill=False):
        """Write RTL Arabic text."""
        # Reshape Arabic text for correct display
        try:
            from arabic_reshaper import reshape
            from bidi.algorithm import get_display
            txt = get_display(reshape(txt))
        except ImportError:
            pass  # Use raw text if reshaper not available
        self.cell(w, h, txt, border=border, new_x="LMARGIN" if ln else "RIGHT",
                  new_y="NEXT" if ln else "TOP", align=align, fill=fill)

    def section_title(self, title):
        self.ln(5)
        self.set_font("Amiri", "B", 16)
        self.set_fill_color(30, 60, 120)
        self.set_text_color(255, 255, 255)
        self.rtl_cell(0, 12, f"  {title}  ", fill=True, ln=1)
        self.set_text_color(0, 0, 0)
        self.ln(3)

    def body_text(self, text, size=12):
        self.set_font("Amiri", "", size)
        for line in text.split("\n"):
            if line.strip():
                self.rtl_cell(0, 8, line.strip(), ln=1)

    def table_row(self, cols, widths, bold=False, fill=False):
        self.set_font("Amiri", "B" if bold else "", 10)
        if fill:
            self.set_fill_color(220, 230, 245)
        for i, (col, w) in enumerate(zip(cols, widths)):
            self.rtl_cell(w, 8, str(col), border=1, fill=fill)
        self.ln()


def get_stats():
    db = sqlite3.connect("data/trading.db")
    c = db.cursor()

    stats = {}
    stats["total"] = c.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    stats["closed"] = c.execute("SELECT COUNT(*) FROM trades WHERE is_closed=1").fetchone()[0]
    stats["open"] = c.execute("SELECT COUNT(*) FROM trades WHERE is_closed=0").fetchone()[0]
    stats["wins"] = c.execute("SELECT COUNT(*) FROM trades WHERE is_closed=1 AND profit>0").fetchone()[0]
    stats["losses"] = c.execute("SELECT COUNT(*) FROM trades WHERE is_closed=1 AND profit<0").fetchone()[0]
    stats["pnl"] = c.execute("SELECT COALESCE(SUM(profit),0) FROM trades WHERE is_closed=1").fetchone()[0]
    stats["balance"] = c.execute("SELECT balance FROM account_snapshots ORDER BY id DESC LIMIT 1").fetchone()[0]
    stats["win_rate"] = stats["wins"] / stats["closed"] * 100 if stats["closed"] > 0 else 0

    stats["strategies"] = c.execute("""
        SELECT strategy, COUNT(*), SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END),
        SUM(CASE WHEN profit<0 THEN 1 ELSE 0 END), COALESCE(SUM(profit),0)
        FROM trades WHERE is_closed=1 GROUP BY strategy ORDER BY COALESCE(SUM(profit),0) DESC
    """).fetchall()

    stats["symbols"] = c.execute("""
        SELECT symbol, COUNT(*), SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END),
        SUM(CASE WHEN profit<0 THEN 1 ELSE 0 END), COALESCE(SUM(profit),0)
        FROM trades WHERE is_closed=1 GROUP BY symbol ORDER BY COALESCE(SUM(profit),0) DESC
    """).fetchall()

    db.close()

    # Improvements
    db2 = sqlite3.connect("data/improvements.db")
    stats["total_imp"] = db2.execute("SELECT COUNT(*) FROM improvements").fetchone()[0]
    stats["done_imp"] = db2.execute("SELECT COUNT(*) FROM improvements WHERE status='DONE'").fetchone()[0]
    stats["pending_imp"] = db2.execute("SELECT COUNT(*) FROM improvements WHERE status='PENDING'").fetchone()[0]

    stats["recent_imps"] = db2.execute("""
        SELECT code, title, category, status FROM improvements
        WHERE code >= 'IMP-38' ORDER BY code
    """).fetchall()

    db2.close()
    return stats


def generate_report():
    stats = get_stats()
    pdf = ArabicPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    # === Page 1: Cover ===
    pdf.add_page()
    pdf.ln(30)
    pdf.set_font("Amiri", "B", 28)
    pdf.rtl_cell(0, 15, "ForexAI", align="C", ln=1)
    pdf.set_font("Amiri", "B", 20)
    pdf.rtl_cell(0, 12, "تقرير نظام التداول الآلي", align="C", ln=1)
    pdf.ln(10)
    pdf.set_font("Amiri", "", 14)
    pdf.rtl_cell(0, 10, f"التاريخ: {datetime.now().strftime('%Y-%m-%d')}", align="C", ln=1)
    pdf.rtl_cell(0, 10, f"الحساب: 5047751974 (MetaQuotes Demo)", align="C", ln=1)
    pdf.rtl_cell(0, 10, f"الرصيد: ${stats['balance']:,.2f}", align="C", ln=1)
    pdf.rtl_cell(0, 10, f"صافي الربح: ${stats['pnl']:+,.2f}", align="C", ln=1)
    pdf.ln(20)

    # Decorative line
    pdf.set_draw_color(30, 60, 120)
    pdf.set_line_width(1)
    pdf.line(30, pdf.get_y(), 180, pdf.get_y())

    # === Page 2: How the System Works ===
    pdf.add_page()
    pdf.section_title("آلية عمل النظام")

    pdf.body_text("""
النظام يعمل كمنصة تداول آلية متصلة بـ MetaTrader 5 عبر Python.
يقوم بمسح 8 أزواج عملات كل ساعة باستخدام 3 استراتيجيات.
""")

    pdf.set_font("Amiri", "B", 13)
    pdf.rtl_cell(0, 10, "خط سير البيانات:", ln=1)
    pdf.body_text("""
MT5 → المؤشرات الفنية → الاستراتيجية → إدارة المخاطر → التنفيذ → قاعدة البيانات
""")

    pdf.set_font("Amiri", "B", 13)
    pdf.rtl_cell(0, 10, "الاستراتيجيات النشطة:", ln=1)
    pdf.body_text("""
1. RSI Reversal - شراء عند التشبع البيعي / بيع عند التشبع الشرائي
2. MACD Crossover - تقاطع خط MACD مع خط الإشارة
3. Bollinger Bounce - ارتداد السعر من حدود بولينجر
* SMA Crossover - معطّل (نسبة فوز 35% فقط)
""")

    pdf.set_font("Amiri", "B", 13)
    pdf.rtl_cell(0, 10, "نظام المراقبة الهجين (4 مراحل):", ln=1)
    pdf.body_text("""
المرحلة 1: نقل وقف الخسارة لنقطة التعادل عند +0.3x ATR
المرحلة 1.5: تتبع وقف الخسارة عند 0.5x ATR بعد التعادل
المرحلة 2: إغلاق 50% عند TP الأصلي، نقل SL لمنتصف الربح
المرحلة 3: تتبع عند 0.5x ATR بعد الإغلاق الجزئي
المرحلة 4: تضييق التتبع إلى 0.7x ATR بعد +3x ATR
""")

    pdf.set_font("Amiri", "B", 13)
    pdf.rtl_cell(0, 10, "فلاتر الحماية:", ln=1)
    pdf.body_text("""
- فلتر H4: منع التداول عكس الاتجاه العام (ذكي حسب الاستراتيجية)
- فلتر الأخبار: إيقاف التداول 30 دقيقة قبل/بعد الأخبار المهمة
- فلتر الجلسة: منع التداول في ساعات السيولة المنخفضة
- حد المخاطرة: 1% لكل صفقة، صفقة واحدة لكل زوج
- حد الارتباط: أقصى 3 صفقات متشابهة الاتجاه
""")

    # === Page 3: Results ===
    pdf.add_page()
    pdf.section_title("النتائج")

    # Overall metrics
    pdf.set_font("Amiri", "B", 13)
    pdf.rtl_cell(0, 10, "الأداء العام:", ln=1)

    metrics = [
        ["المؤشر", "القيمة"],
        ["الرصيد الحالي", f"${stats['balance']:,.2f}"],
        ["رأس المال الأولي", "$100,000.00"],
        ["صافي الربح", f"${stats['pnl']:+,.2f}"],
        ["العائد", f"{stats['pnl']/1000:.1f}%"],
        ["إجمالي الصفقات", f"{stats['total']}"],
        ["رابحة", f"{stats['wins']}"],
        ["خاسرة", f"{stats['losses']}"],
        ["نسبة الفوز", f"{stats['win_rate']:.1f}%"],
    ]
    widths = [80, 80]
    for i, row in enumerate(metrics):
        pdf.table_row(row, widths, bold=(i == 0), fill=(i == 0))

    pdf.ln(5)
    pdf.set_font("Amiri", "B", 13)
    pdf.rtl_cell(0, 10, "أداء الاستراتيجيات:", ln=1)

    header = ["الاستراتيجية", "صفقات", "فوز", "خسارة", "الربح"]
    widths = [50, 25, 25, 25, 40]
    pdf.table_row(header, widths, bold=True, fill=True)
    for s in stats["strategies"]:
        row = [s[0], str(s[1]), str(s[2] or 0), str(s[3] or 0), f"${s[4]:+,.2f}"]
        pdf.table_row(row, widths)

    pdf.ln(5)
    pdf.set_font("Amiri", "B", 13)
    pdf.rtl_cell(0, 10, "أداء الأزواج:", ln=1)

    header = ["الزوج", "صفقات", "فوز", "خسارة", "الربح"]
    pdf.table_row(header, widths, bold=True, fill=True)
    for s in stats["symbols"]:
        row = [s[0], str(s[1]), str(s[2] or 0), str(s[3] or 0), f"${s[4]:+,.2f}"]
        pdf.table_row(row, widths)

    # === Page 4: Enhancements ===
    pdf.add_page()
    pdf.section_title("التحسينات المنجزة")

    pdf.body_text(f"""
إجمالي التحسينات: {stats['total_imp']}
المنجز: {stats['done_imp']}
قيد الانتظار: {stats['pending_imp']}
""")

    pdf.set_font("Amiri", "B", 13)
    pdf.rtl_cell(0, 10, "أبرز التحسينات الأخيرة:", ln=1)

    header = ["الكود", "الوصف", "الفئة", "الحالة"]
    widths = [25, 75, 35, 30]
    pdf.table_row(header, widths, bold=True, fill=True)
    for imp in stats["recent_imps"]:
        pdf.table_row(list(imp), widths)

    pdf.ln(5)
    pdf.set_font("Amiri", "B", 13)
    pdf.rtl_cell(0, 10, "التحسينات الرئيسية:", ln=1)
    pdf.body_text("""
1. نظام مراقبة هجين 4 مراحل (تعادل، إغلاق جزئي، تتبع، تضييق)
2. فلتر H4 ذكي حسب الاستراتيجية (RSI مسموح عكس الاتجاه)
3. إيقاف المسح في عطلة نهاية الأسبوع تلقائياً
4. فحص صحة النظام قبل البدء مع إشعار تليجرام
5. دعم تشغيل أكثر من منصة MT5 بنفس الوقت
6. لوحة تحكم متكاملة مع رسوم بيانية وشات ذكي
7. تحديث الربح المباشر في قاعدة البيانات كل ساعة
8. إشعارات تليجرام مفصّلة للصفقات والمراقبة
""")

    # === Page 5: Next Steps ===
    pdf.add_page()
    pdf.section_title("الخطوات القادمة")

    pdf.body_text("""
المرحلة 1: جمع البيانات (الآن)
- الهدف: 200 صفقة مغلقة (حالياً 112)
- المتوقع: 1-2 أسبوع
- البوت يعمل 24/5 مع 3 استراتيجيات على 8 أزواج

المرحلة 2: تدريب نماذج الذكاء الاصطناعي
- استخدام LightGBM لتصنيف الإشارات
- تدريب نموذج لكل زوج عملات
- Walk-forward validation لمنع الـ overfitting

المرحلة 3: تفعيل فلتر ML
- فقط الإشارات عالية الثقة تُنفّذ
- المتوقع: تحسين نسبة الفوز من 45% إلى 55%+
- تقليل الخسائر بنسبة 30-40%

المرحلة 4: الاختبار الخلفي والتحسين
- اختبار على بيانات تاريخية
- تحسين المعلمات بـ Optuna
- مقارنة الأداء قبل وبعد ML

المرحلة 5: التداول الحقيقي (اختياري)
- التحويل من الحساب التجريبي للحقيقي
- البدء بحجم صغير (0.01 لوت)
- زيادة الحجم تدريجياً مع الثقة
""")

    pdf.section_title("الخلاصة")
    pdf.body_text(f"""
النظام يعمل بشكل جيد مع ربح ${stats['pnl']:+,.2f} (+{stats['pnl']/1000:.1f}%).
أفضل استراتيجية: MACD Crossover (+${stats['strategies'][0][4]:,.2f}).
أفضل زوج: {stats['symbols'][0][0]} (+${stats['symbols'][0][4]:,.2f}).
تم تنفيذ {stats['done_imp']} تحسين من أصل {stats['total_imp']}.
النظام جاهز للمرحلة القادمة: تدريب نماذج ML بعد جمع 200 صفقة.
""")

    # Save PDF
    output_path = "data/reports/ForexAI_Report_AR.pdf"
    os.makedirs("data/reports", exist_ok=True)
    pdf.output(output_path)
    print(f"PDF saved: {output_path}")
    return output_path


def send_to_telegram(file_path):
    """Send PDF file to Telegram."""
    import urllib.request
    import json

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        print("Telegram not configured")
        return False

    url = f"https://api.telegram.org/bot{token}/sendDocument"

    # Build multipart form data
    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    filename = os.path.basename(file_path)

    with open(file_path, "rb") as f:
        file_data = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
        f"{chat_id}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="caption"\r\n\r\n'
        f"تقرير نظام ForexAI - {datetime.now().strftime('%Y-%m-%d')}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode("utf-8") + file_data + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                print("PDF sent to Telegram!")
                return True
            else:
                print(f"Telegram error: {result}")
                return False
    except Exception as e:
        print(f"Send failed: {e}")
        return False


if __name__ == "__main__":
    path = generate_report()
    send_to_telegram(path)
