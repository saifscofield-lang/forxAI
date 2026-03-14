# متطلبات غير Python
# Non-Python Requirements

---

## 1. MetaTrader 5 Terminal (إلزامي الآن)

**ما هو؟** تطبيق سطح المكتب الذي يعمل كجسر بين Python والوسيط.

**التثبيت:**
1. اذهب إلى موقع أي وسيط يدعم MT5، مثل:
   - [XM](https://www.xm.com) — موصى به
   - [ICMarkets](https://www.icmarkets.com)
   - [Pepperstone](https://www.pepperstone.com)
   - أو مباشرة: https://www.metatrader5.com/en/download
2. ثبّت التطبيق
3. افتح حساب **Demo** مجاني من داخل البرنامج
4. تأكد أن المنصة **مفتوحة وموصولة** عند تشغيل Python

> ⚠️ مهم: مكتبة `MetaTrader5` في Python تتصل بالتطبيق المفتوح على جهازك.
> إذا كان MT5 مغلقاً، لن يعمل الكود.

---

## 2. Python 3.11+ (إلزامي)

**التحقق من الإصدار:**
```bash
python --version
```

**التثبيت إذا لم يكن موجوداً:**
- https://www.python.org/downloads/
- اختر Python 3.11 أو 3.12
- ✅ تأكد من تفعيل خيار "Add Python to PATH" أثناء التثبيت

---

## 3. pip (يأتي مع Python تلقائياً)

**التحقق:**
```bash
pip --version
```

**التحديث:**
```bash
python -m pip install --upgrade pip
```

---

## 4. Git (موصى به)

لتتبع التغييرات في الكود.

**التثبيت:**
- https://git-scm.com/download/win

**الإعداد الأساسي:**
```bash
git config --global user.name "اسمك"
git config --global user.email "بريدك@example.com"
```

---

## 5. Visual Studio Code (موصى به كمحرر)

**التثبيت:**
- https://code.visualstudio.com/

**الإضافات الموصى بها:**
- Python (من Microsoft)
- Pylance
- Black Formatter
- GitLens

---

## 6. TA-Lib (اختياري — للمرحلة 2)

مكتبة C للمؤشرات التقنية — أسرع من pandas-ta لكن تثبيتها أصعب على Windows.

**التثبيت على Windows:**
```bash
# خيار 1: من ملف wheel جاهز
pip install TA-Lib

# إذا فشل، حمّل الملف من:
# https://github.com/cgohlke/talib-build/releases
# ثم:
pip install TA_Lib-0.4.xx-cpXXX-win_amd64.whl
```

> 💡 يمكن الاستغناء عنه في البداية باستخدام pandas-ta بدلاً منه

---

## ملخص الأولويات

| المتطلب | الأولوية | الوقت التقريبي للتثبيت |
|---|---|---|
| Python 3.11+ | **إلزامي الآن** | 5 دقائق |
| MT5 Terminal + Demo Account | **إلزامي الآن** | 10 دقائق |
| Git | موصى به | 5 دقائق |
| VS Code | موصى به | 5 دقائق |
| TA-Lib | اختياري (المرحلة 2) | لاحقاً |

---

## بعد تثبيت المتطلبات، ابدأ بـ:

```bash
cd d:/forexAI
python -m venv venv
venv\Scripts\activate
pip install -r requirements/requirements_phase0.txt
```
