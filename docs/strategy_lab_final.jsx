import { useState } from "react";

// ============================================================
// FORXAI — STRATEGY LAB MASTER DOCUMENT v3.0
// النسخة النهائية المعدّلة بعد مراجعة جميع المخاطر
// ============================================================

const C = {
  bg: "#07080a",
  surface: "#0d0f12",
  border: "#1c2028",
  borderHover: "#2e3540",
  gold: "#c9a84c",
  goldDim: "#7a6330",
  goldBright: "#f0c968",
  amber: "#e07b39",
  green: "#3d9e6e",
  red: "#b84040",
  blue: "#3a7fc1",
  purple: "#7c5cbf",
  text: "#c8cdd6",
  textDim: "#5a6270",
  textBright: "#edf0f4",
};

const tag = (label, color = C.goldDim) => (
  <span style={{
    background: color + "18", border: `1px solid ${color}50`,
    color, padding: "2px 10px", fontSize: 10, letterSpacing: "0.12em",
    fontFamily: "monospace", whiteSpace: "nowrap",
  }}>{label}</span>
);

const Section = ({ title, sub, children, accent = C.gold }) => (
  <div style={{ marginBottom: 32 }}>
    <div style={{ borderBottom: `1px solid ${accent}30`, paddingBottom: 10, marginBottom: 20 }}>
      <div style={{ color: accent, fontSize: 11, letterSpacing: "0.3em", fontFamily: "monospace" }}>{title}</div>
      {sub && <div style={{ color: C.textDim, fontSize: 12, marginTop: 4 }}>{sub}</div>}
    </div>
    {children}
  </div>
);

const Row = ({ label, value, note, accent = C.text }) => (
  <div style={{
    display: "grid", gridTemplateColumns: "220px 1fr auto",
    gap: 16, padding: "10px 14px", borderBottom: `1px solid ${C.border}`,
    alignItems: "start",
  }}>
    <div style={{ color: C.textDim, fontSize: 12 }}>{label}</div>
    <div style={{ color: accent, fontSize: 12, lineHeight: 1.7 }}>{value}</div>
    {note && <div style={{ color: C.textDim, fontSize: 10, textAlign: "right" }}>{note}</div>}
  </div>
);

const Pill = ({ children, color = C.goldDim, size = 11 }) => (
  <span style={{
    background: color + "15", border: `1px solid ${color}40`,
    color, padding: "3px 10px", fontSize: size, fontFamily: "monospace",
    display: "inline-block",
  }}>{children}</span>
);

const Alert = ({ type, children }) => {
  const map = { warn: [C.amber, "⚠"], info: [C.blue, "◈"], ok: [C.green, "✓"], danger: [C.red, "✖"] };
  const [color, icon] = map[type] || map.info;
  return (
    <div style={{
      background: color + "0c", border: `1px solid ${color}30`,
      padding: "12px 16px", marginBottom: 10, display: "flex", gap: 12,
    }}>
      <span style={{ color, flexShrink: 0 }}>{icon}</span>
      <div style={{ color: C.text, fontSize: 12, lineHeight: 1.8 }}>{children}</div>
    </div>
  );
};

// ──────────────────────────────────────────
// DATA
// ──────────────────────────────────────────
const TABS = [
  { id: "philosophy", label: "01 — الفلسفة" },
  { id: "hypotheses", label: "02 — مكتبة الفرضيات" },
  { id: "funnel",     label: "03 — القمع والأعداد" },
  { id: "selection",  label: "04 — الانتقاء والتحسين" },
  { id: "scoring",    label: "05 — التقييم والقبول" },
  { id: "engine",     label: "06 — محرك القرار" },
  { id: "naming",     label: "07 — التسمية والتخزين" },
  { id: "risks",      label: "08 — إدارة المخاطر" },
  { id: "roadmap",    label: "09 — خارطة الطريق" },
];

const SOURCES = [
  {
    id: "S1", title: "الهيكل الميكانيكي للسوق", color: C.gold,
    why: "آلية مطابقة الأوامر ثابتة لا تتغير — ليست نظرية بل فيزياء السوق",
    examples: ["Stop Hunt: السيولة موجودة دائماً عند القمم والقيعان الواضحة",
      "Fair Value Gap: الفجوات تُملأ لأن المؤسسات تحتاج التنفيذ عند هذه الأسعار",
      "Round Numbers: تجمّع الأوامر عند الأرقام المستديرة حتمي"],
    stability: "دائم", source: "بنية السوق",
  },
  {
    id: "S2", title: "علم النفس البشري الثابت", color: C.amber,
    why: "الخوف والجشع والقطيع لم تتغير منذ آلاف السنين — قابلة للقياس والاستغلال",
    examples: ["Fear Spike Fade: ردود الفعل المبالغ بها تُصحَّح دائماً",
      "Retail Trap: الاختراقات الواضحة للجميع هي فخ",
      "News Trap: الحشد يشتري الخبر بعد أن باع المحترفون"],
    stability: "دائم", source: "علم النفس",
  },
  {
    id: "S3", title: "الالتزامات الهيكلية للمؤسسات", color: C.blue,
    why: "الصناديق الكبيرة ملزمة قانونياً بأفعال متوقعة — هذه ليست أسراراً",
    examples: ["Month-End Rebalancing: إعادة التوازن الإلزامية في آخر الشهر",
      "Quarter-End Flows: تدفقات نهاية الربع ضخمة ومتوقعة الاتجاه",
      "Fix Orders: أوامر WM/Reuters Fix في 4 PM لندن يومياً"],
    stability: "شبه دائم", source: "اللوائح المالية",
  },
  {
    id: "S4", title: "الإيقاعات الزمنية للجلسات", color: C.purple,
    why: "ساعات عمل البنوك والصناديق تخلق أنماطاً يومية وأسبوعية متكررة",
    examples: ["Asia Range: آسيا تبني النطاق، لندن تكسره في 70% من الأيام",
      "London Killzone: 8-10 AM GMT هي ذروة النشاط المؤسسي",
      "Dead Zone: 12-13 GMT انخفاض السيولة = حركات مزيفة"],
    stability: "مستقر", source: "هيكل الجلسات",
  },
  {
    id: "S5", title: "بياناتك التاريخية الخاصة", color: C.green,
    why: "الأقوى لأنها واقعية وليست نظرية — 119 صفقة من مشروعك تحمل فرضيات جاهزة",
    examples: ["MACD تفوق في ATR عالٍ ← فرضية: ATR filter إلزامي",
      "RSI < 35 يخسر ← فرضية: تجنب الإشارات الحدية",
      "Bollinger خسر لأن R:R=1:1 ← فرضية: R:R > 2 شرط قبول"],
    stability: "حي ومتجدد", source: "data/reports في مشروعك",
  },
  {
    id: "S6", title: "البحث الأكاديمي الموثق", color: C.textDim,
    why: "آلاف الأوراق البحثية عن Forex Market Microstructure — موثقة ومحكّمة",
    examples: ["Day-of-Week Effect: الثلاثاء/الأربعاء أقوى أيام الاتجاه (Eugene Fama 1965+)",
      "Monday Gap Fill: 72% fill rate — موثق في عشرات الدراسات",
      "Volatility Clustering: هدوء السوق يتبعه انفجار — GARCH models"],
    stability: "موثق", source: "Literature Review",
  },
];

const HYPOTHESES = [
  {
    cat: "🩸 السيولة وهيكل السوق", color: C.gold, source: "S1",
    sourceLabel: "هيكل السوق",
    items: [
      { id:"LIQ-001", name:"Stop Hunt Reversal", ar:"اصطياد الأوامر وعكسها",
        thesis:"كسر قمة/قاع واضح بـ 3-10 pips ثم عودة = اصطياد سيولة، الاتجاه الحقيقي عكسي",
        edge:"صنّاع السوق يحتاجون السيولة المتراكمة عند المستويات الواضحة",
        entry:"كسر + حجم مرتفع + شمعة عكسية خلال شمعتين",
        invalidation:"إذا أغلق السعر بعيداً عن نقطة الكسر > 15 دقيقة",
        pairs:["EURUSD","GBPUSD","XAUUSD"], tf:["M15","H1"], regime:"Ranging" },
      { id:"LIQ-002", name:"Fair Value Gap Fill", ar:"ملء فجوة القيمة العادلة",
        thesis:"الفجوات السعرية (3 شمعات بلا تداخل) تجذب السعر للعودة قبل استمرار الاتجاه",
        edge:"المؤسسات تملأ أوامرها في المناطق غير المتداوَلة لتحسين متوسط السعر",
        entry:"FVG > 10 pips + عودة السعر + شمعة تأكيد",
        invalidation:"خبر قوي جداً أثناء الفجوة — قد لا تُملأ",
        pairs:["XAUUSD","EURUSD","GBPUSD"], tf:["M15","H1","H4"], regime:"Trending" },
      { id:"LIQ-003", name:"Order Block Reaction", ar:"رد فعل على بلوك الأوامر",
        thesis:"المنطقة التي انطلقت منها حركة قوية = تجمع أوامر مؤسسي، السعر يعود إليها",
        edge:"المؤسسات لم تنفذ كل أوامرها، تنتظر العودة",
        entry:"آخر شمعة عكسية قبل الحركة + عودة السعر + تأكيد H1",
        invalidation:"إذا تجاوز السعر البلوك بأكثر من 50% في جسم الشمعة",
        pairs:["EURUSD","USDJPY","GBPUSD","XAUUSD"], tf:["H1","H4"], regime:"Trending" },
      { id:"LIQ-004", name:"Equal Highs/Lows Sweep", ar:"اختراق القمم/القيعان المتساوية",
        thesis:"قمتان+ بنفس المستوى = تجمع أوامر Stop Loss. السعر سيصطادها ثم ينعكس",
        edge:"التجمعات الظاهرة هي أهداف لصنّاع السوق بالتعريف",
        entry:"3+ قمم متساوية ± 5 pips + اختراق سريع + شمعة ابتلاع",
        invalidation:"إذا استمر السعر > قمم آسيا 15 دقيقة",
        pairs:["EURUSD","USDJPY","GBPUSD"], tf:["H1","H4"], regime:"Any" },
    ]
  },
  {
    cat: "🕐 ميكانيكا الجلسات", color: C.amber, source: "S4",
    sourceLabel: "هيكل الجلسات",
    items: [
      { id:"SES-001", name:"Asia Range Breakout", ar:"اختراق نطاق آسيا",
        thesis:"آسيا (22:00-08:00 GMT) تبني نطاقاً، لندن تكسره في 70% من الأيام والزخم يستمر",
        edge:"لندن تحتاج سيولة آسيا لبدء اتجاهها — هذا هيكلي لا اختياري",
        entry:"كسر أعلى/أدنى آسيا في أول ساعتين من لندن + حجم > متوسط",
        invalidation:"أيام الجمعة + قبل NFP + أيام العطل",
        pairs:["GBPUSD","EURUSD","USDJPY"], tf:["M15","H1"], regime:"Any" },
      { id:"SES-002", name:"London Kill Zone Reversal", ar:"عكس منطقة قتل لندن",
        thesis:"8:00-10:00 GMT — لندن تصطاد سيولة آسيا ثم تعكس في 60% من الحالات",
        edge:"أكبر تجمع مؤسسي يبدأ هنا ويحتاج السيولة قبل التحرك الحقيقي",
        entry:"Spike واضح + عكس سريع + شمعة M5 ابتلاع",
        invalidation:"إذا كان D1 trending قوياً جداً في نفس اتجاه الـ Spike",
        pairs:["EURUSD","GBPUSD"], tf:["M5","M15"], regime:"Ranging على اليومي" },
      { id:"SES-003", name:"Dead Zone Fade", ar:"تلاشي المنطقة الميتة",
        thesis:"12:00-13:00 GMT (فجوة لندن-نيويورك) — الحركات مزيفة وتُعكس في 65% من الحالات",
        edge:"انخفاض السيولة يسبب تذبذباً بلا مشارك مؤسسي حقيقي",
        entry:"حركة > 20 pips في Dead Zone بدون خبر = فرصة عكس",
        invalidation:"إذا ظهر خبر فجائي غير مجدوَل",
        pairs:["EURUSD","GBPUSD"], tf:["M15"], regime:"Low Volatility" },
    ]
  },
  {
    cat: "🧠 علم النفس السوقي", color: C.purple, source: "S2",
    sourceLabel: "علم النفس",
    items: [
      { id:"PSY-001", name:"News Trap Reversal", ar:"فخ الخبر وعكسه",
        thesis:"خبر إيجابي جداً + ارتفاع أولي + انهيار = المحترفون باعوا على الخبر قبل الحشد",
        edge:"المحترفون يبنون مراكزهم قبل الخبر، الحشد يدخل بعده — اتجاهان عكسيان",
        entry:"خبر > توقعات + ارتفاع أولي + شمعة انعكاسية خلال 15 دقيقة",
        invalidation:"أرقام صادمة جداً (> 3x توقعات) — الزخم يتجاوز الفخ",
        pairs:["EURUSD","GBPUSD","USDJPY"], tf:["M5","M15"], regime:"News Day" },
      { id:"PSY-002", name:"Fear Spike Fade", ar:"تلاشي ذعر الخوف",
        thesis:"حركات > 50 pips في 5 دقائق بدون خبر مجدوَل = ذعر مبالَغ فيه، العكس قادم",
        edge:"ردود الفعل العاطفية المبالغ بها تُصحَّح — العواطف ليست اقتصاداً",
        entry:"حركة > 50 pips في M5 + غياب في التقويم + حجم ضخم",
        invalidation:"خبر غير مجدوَل حقيقي (حرب، كارثة، قرار مفاجئ)",
        pairs:["XAUUSD","USDJPY","GBPUSD"], tf:["M5","M15"], regime:"Spike Event" },
    ]
  },
  {
    cat: "🔗 الترابطات بين الأسواق", color: C.blue, source: "S3",
    sourceLabel: "العلاقات الهيكلية",
    items: [
      { id:"COR-001", name:"DXY Divergence Play", ar:"تباين الدولار",
        thesis:"DXY يرتفع لكن EURUSD لا ينزل بالمقابل = EURUSD سيتأخر ويلحق",
        edge:"الارتباط السلبي DXY/EUR هيكلي — أي تباين مؤقت يُصحَّح",
        entry:"DXY +0.3% في ساعة + EURUSD تحرك < 0.1% في نفس الوقت",
        invalidation:"خبر خاص بالـ EUR يكسر الارتباط بشكل مستقل",
        pairs:["EURUSD"], tf:["H1"], regime:"Normal Correlation" },
      { id:"COR-002", name:"Gold-JPY Safe Haven Sync", ar:"تزامن الذهب والين",
        thesis:"في أوقات الخوف كلاهما يرتفع. عندما يرتفع أحدهما دون الآخر = فرصة",
        edge:"أموال الملاذ الآمن تتدفق لكليهما — التأخر بين السوقين فرصة",
        entry:"XAUUSD +0.5% + USDJPY لم ينزل بشكل كافٍ بعد",
        invalidation:"أزمة تخص اليابان تحديداً — الين يتحرك مستقلاً",
        pairs:["USDJPY","XAUUSD"], tf:["H1","H4"], regime:"Risk-Off" },
    ]
  },
  {
    cat: "📊 الإيقاعات الإحصائية", color: C.green, source: "S5+S6",
    sourceLabel: "بياناتك + أكاديمي",
    items: [
      { id:"STAT-001", name:"Day-of-Week Bias", ar:"تحيز يوم الأسبوع",
        thesis:"الثلاثاء والأربعاء أكثر أيام الاتجاه الصافي. الجمعة تعكس الاتجاه قبيل الإغلاق",
        edge:"أنماط إعادة التوازن المؤسسي الأسبوعية متكررة وموثقة أكاديمياً",
        entry:"اتجاه واضح صباح الثلاثاء بعد فتح لندن",
        invalidation:"أسبوع NFP — الأنماط الأسبوعية تُكسر",
        pairs:["EURUSD","GBPUSD"], tf:["H1","H4"], regime:"Normal Week" },
      { id:"STAT-002", name:"Monday Gap Fill", ar:"ملء فجوة الاثنين",
        thesis:"72% من فجوات افتتاح الاثنين تُملأ قبل نهاية اليوم",
        edge:"السيولة المتراكمة في عطلة نهاية الأسبوع تُفرج عنها بالملء",
        entry:"فجوة افتتاح > 15 pips يوم الاثنين + اتجاه العكس",
        invalidation:"أخبار صادمة في عطلة نهاية الأسبوع — الفجوة تستمر",
        pairs:["EURUSD","GBPUSD","XAUUSD"], tf:["M15","H1"], regime:"Normal Open" },
      { id:"STAT-003", name:"ATR Regime Filter (من بياناتك)", ar:"فلتر التقلب من بياناتك",
        thesis:"MACD تفوّق فقط في ATR عالٍ (winners ATR=3.59 vs losers ATR=1.18) — مكتشف من 119 صفقة",
        edge:"هذه ليست نظرية — هي نتيجة مباشرة من بيانات مشروعك الحقيقية",
        entry:"أي استراتيجية اتجاهية + ATR الحالي > 1.5x المتوسط 20 شمعة",
        invalidation:"ATR ينهار فجأة أثناء الصفقة المفتوحة",
        pairs:["All"], tf:["H1","H4"], regime:"High Volatility" },
    ]
  },
  {
    cat: "🌊 أنظمة السوق (Regime First)", color: C.textDim, source: "S1+S6",
    sourceLabel: "أساسي — يسبق كل شيء",
    items: [
      { id:"REG-001", name:"Volatility Compression Breakout", ar:"اختراق ضغط التقلب",
        thesis:"ATR ينضغط لأدنى مستوياته في 20 شمعة = انفجار وشيك في أي اتجاه",
        edge:"الأسواق الهادئة تتراكم طاقة — الانفجار حتمي إحصائياً (GARCH)",
        entry:"ATR < 30% من متوسط 20 + Bollinger Squeeze + أول شمعة كبيرة كتأكيد",
        invalidation:"الانفجار في الاتجاهين ممكن — بحاجة لتأكيد قبل الدخول",
        pairs:["XAUUSD","EURUSD","GBPUSD"], tf:["H1","H4"], regime:"Pre-Breakout" },
      { id:"REG-002", name:"Regime Detector (Meta)", ar:"كاشف النظام — يعمل دائماً",
        thesis:"لا تدخل أي صفقة قبل تشخيص النظام: Trending / Ranging / Volatile",
        edge:"معظم الاستراتيجيات تفشل لأنها تُطبَّق في النظام الخاطئ",
        entry:"ADX > 25 = Trending | ADX < 20 = Ranging | ATR > 2x = Volatile",
        invalidation:"انتقالات النظام (أول 2-3 أيام) — قلّل الحجم وانتظر",
        pairs:["All"], tf:["H4","D1"], regime:"Meta — يسبق كل استراتيجية" },
    ]
  },
];

const FUNNEL = [
  { stage:"مكتبة الفرضيات", count:71, pct:100, color:C.textDim,
    desc:"71 فرضية موثقة من 6 مصادر هيكلية — كل فرضية تحمل Edge واضحاً وشرط إخفاق" },
  { stage:"اختبار سريع — 90 يوم", count:30, pct:42, color:C.gold,
    desc:"Backtest 90 يوم فقط. الهدف: الإقصاء السريع. الفاشل يُرفض فوراً بدون وقت إضافي" },
  { stage:"اختبار كامل — 3 سنوات", count:15, pct:21, color:C.amber,
    desc:"Walk-Forward حقيقي + Out-of-Sample محجوز 20% لا يُلمس إلا الآن" },
  { stage:"تحسين Optuna — 50 trial", count:10, pct:14, color:C.purple,
    desc:"50 trial فقط (لا 500) لتجنب Overfitting. تحسين المعاملات فقط — لا تغيير المنطق" },
  { stage:"Paper Trading — 30 يوم", count:6, pct:8, color:C.blue,
    desc:"Demo account حقيقي. أي انحراف > 15% عن الـ Backtest = رفض فوري" },
  { stage:"Live — حجم صغير أولاً", count:3, pct:4, color:C.green,
    desc:"0.01 lot لأول شهر. توسع تدريجي كل شهر بشرط الاستمرارية" },
  { stage:"نخبة — مدمجة ومحسّنة", count:"2-3", pct:3, color:C.goldBright,
    desc:"الهدف النهائي: 2-3 استراتيجيات مفهومة وموثوقة تعمل في ظروف محددة معروفة مسبقاً" },
];

const SCORING = {
  primary: [
    { m:"Expected Value", formula:"(WR×AvgWin) − (LR×AvgLoss)", pass:"> $0", fail:"< $0", w:"35%", fatal:true,
      why:"إذا كانت سالبة — المنطق خاطئ، المعاملات لن تصلحه" },
    { m:"Profit Factor", formula:"Gross Profit / Gross Loss", pass:"> 1.4", fail:"< 1.0", w:"25%", fatal:true,
      why:"أقل من 1.0 يعني خسارة مضمونة على المدى الطويل" },
    { m:"Max Drawdown", formula:"Peak-to-Trough", pass:"< 8%", fail:"> 15%", w:"20%", fatal:true,
      why:"Drawdown كبير يُخرجك نفسياً قبل أن تنجح الاستراتيجية" },
    { m:"عدد الصفقات", formula:"Total Trades in Backtest", pass:"> 150", fail:"< 50", w:"10%", fatal:true,
      why:"أقل من 50 صفقة = عينة إحصائية غير موثوقة" },
    { m:"Win Rate", formula:"Wins / Total", pass:"> 35%", fail:"< 25%", w:"10%", fatal:false,
      why:"غير قاتل منفرداً — مع R:R جيد يمكن أن تربح بـ 30% WR" },
  ],
  secondary: [
    { m:"Sharpe Ratio", bench:"> 1.0", desc:"العائد المعدَّل للمخاطرة" },
    { m:"Calmar Ratio", bench:"> 2.0", desc:"صافي الربح / Max Drawdown" },
    { m:"Out-of-Sample PF", bench:"> 1.2", desc:"Profit Factor على البيانات المحجوزة فقط — الأهم" },
    { m:"Consistency Score", bench:"> 65%", desc:"نسبة الأشهر المربحة" },
    { m:"Regime Accuracy", bench:"> 60%", desc:"هل الاستراتيجية تعمل فعلاً في النظام المستهدف؟" },
    { m:"Paper vs Backtest", bench:"< 15% انحراف", desc:"أي انحراف أكبر = رفض فوري" },
  ],
  grades: [
    { g:"S", range:"90-100", action:"تُفعَّل فوراً + Paper Trading بدء فوري", c:C.goldBright },
    { g:"A", range:"75-89", action:"Paper Trading أسبوعان ثم Live", c:C.green },
    { g:"B", range:"60-74", action:"Optuna تحسين ثم إعادة اختبار", c:C.blue },
    { g:"C", range:"40-59", action:"مراجعة الفرضية + تعديل المنطق", c:C.amber },
    { g:"F", range:"< 40", action:"رفض نهائي — حفظ في أرشيف التعلم", c:C.red },
  ]
};

const DECISION_ENGINE = [
  { step:"1", title:"تشخيص النظام", color:C.gold,
    logic:"كل ساعة: ADX (H4) + ATR ratio + Bollinger Width → تصنيف: Trending / Ranging / Volatile / Transitional",
    output:"نظام_الساعة = [Trending_Bull | Trending_Bear | Ranging | Volatile]",
    risk:"في Transitional: لا تشغيل أي استراتيجية — انتظر التأكيد" },
  { step:"2", title:"فلترة الاستراتيجيات المؤهلة", color:C.amber,
    logic:"من قائمة الاستراتيجيات Active: اعرض فقط التي regime_target == النظام الحالي",
    output:"قائمة_المؤهلة = [STR-A, STR-B, STR-C]",
    risk:"لا تشغّل استراتيجية في نظام مختلف عن نظامها المثبَت — هذا القاعدة الأهم" },
  { step:"3", title:"فحص Circuit Breaker", color:C.red,
    logic:"كل استراتيجية مؤهلة: فحص 5 خسائر متتالية | EV سلبي على آخر 20 | Drawdown > 3%",
    output:"قائمة_نشطة = المؤهلة ناقص المجمَّدة",
    risk:"Auto-freeze خلال 5 ثواني من اكتشاف الشرط" },
  { step:"4", title:"تحديد الأولوية وحجم المركز", color:C.purple,
    logic:"ترتيب بـ Score × Regime_Accuracy × Days_Since_Last_Loss. الأعلى score يحصل على حجم أكبر",
    output:"priority_list = [(STR-A, 0.02 lot), (STR-B, 0.01 lot)]",
    risk:"لا تشغّل أكثر من 3 استراتيجيات في نفس الوقت — Correlation Risk" },
  { step:"5", title:"التحقق من الارتباط", color:C.blue,
    logic:"إذا كانت استراتيجيتان تشتريان نفس الزوج في نفس الوقت = حجم مزدوج غير مقصود",
    output:"تقليص الحجم أو انتظار إغلاق المركز الأول",
    risk:"Correlation > 0.7 بين استراتيجيتين = تشغيل واحدة فقط" },
];

const NAMING = {
  format: "CAT — HYP — vMAJOR.MINOR — REGIME",
  example: "LIQ — SHS — v2.1 — RANGING",
  parts: [
    { p:"CAT", d:"فئة الفرضية (3 أحرف)", ex:"LIQ / SES / PSY / COR / STAT / REG" },
    { p:"HYP", d:"اختصار الفرضية (3 أحرف)", ex:"SHS / FVG / OBR / ARB / NTR" },
    { p:"vX.Y", d:"نسخة رقمية", ex:"v1.0 أصلية | v1.3 معاملات | v2.0 منطق" },
    { p:"REGIME", d:"النظام المستهدف", ex:"TRENDING / RANGING / VOLATILE / ANY" },
  ],
  versioning: [
    { bump:"v2.0 (Major)", trigger:"تغيير منطق الدخول أو الخروج الأساسي" },
    { bump:"v1.3 (Minor)", trigger:"تعديل معاملات أو إضافة فلتر" },
    { bump:"v1.0.2 (Patch)", trigger:"إصلاح خطأ حسابي" },
  ],
  tables: [
    { name:"strategies", fields:["id (CAT-HYP-vX.Y-REGIME)","hypothesis_id","code TEXT","parameters JSON","status","regime_target","score REAL","grade TEXT","author (HUMAN|AI|EVOLVED)","parent_id","generation INT","created_at","updated_at"] },
    { name:"backtest_results", fields:["id","strategy_id","period_start / end","symbol","timeframe","total_trades","win_rate","profit_factor","expected_value","max_drawdown","sharpe","out_of_sample_pf ← الأهم","paper_vs_backtest_delta","regime_accuracy","grade","run_at"] },
    { name:"strategy_lineage", fields:["parent_id","child_id","evolution_type (OPTIMIZE|MUTATE|MERGE|REDESIGN)","score_before / score_after","created_at"] },
    { name:"rejected_archive", fields:["strategy_id","rejection_reason","failure_mode","lesson_learned (Claude يستخلصه)","archived_at"] },
    { name:"regime_log", fields:["timestamp","detected_regime","adx_value","atr_ratio","bb_width","active_strategies JSON","action_taken"] },
  ]
};

const RISKS = [
  { risk:"Over-Engineering", severity:"عالي", fix:"MVP أولاً: فرضيتان فقط + backtest بسيط + لا Optuna في البداية. أثبت المفهوم ثم وسّع.", status:"محلول" },
  { risk:"Overfitting", severity:"عالي جداً — الأخطر", fix:"20% من البيانات محجوز مقدساً. 50 trial Optuna لا 500. Out-of-Sample PF > 1.2 شرط قبول لا تفاوض عليه.", status:"محلول" },
  { risk:"جودة Tick Volume", severity:"متوسط", fix:"لا تبنِ فرضيات تعتمد على Volume بشكل حرفي. استخدمه كمؤشر نسبي فقط (أعلى/أقل من المتوسط).", status:"محلول" },
  { risk:"Regime Shift المفاجئ", severity:"عالي", fix:"Circuit Breaker فوري + حجم صغير لأول شهر + Regime Detector يعمل كل ساعة + Transitional state لا تشغيل فيه.", status:"محلول" },
  { risk:"Decision Engine غامض", severity:"عالي", fix:"5 خطوات محددة بالترتيب: تشخيص النظام → فلترة → Circuit Breaker → أولوية → ارتباط. لا غموض.", status:"محلول" },
  { risk:"Strategy Explosion", severity:"متوسط", fix:"سقف صارم: لا أكثر من 20 في المرحلة الأولى. Funnel: 71 → 15 → 6 → 2-3 نخبة. الجودة لا الكمية.", status:"محلول" },
  { risk:"ML Black Box", severity:"متوسط", fix:"LightGBM/XGBoost أولاً (قابل للتفسير). LSTM و Autoencoder للمرحلة الثالثة فقط بعد ثبات النظام.", status:"مؤجل" },
  { risk:"تأخر التقييم الحقيقي", severity:"منخفض — لا حل سحري", fix:"30 يوم Paper Trading هو الحد الأدنى. من يقول أقل يكذب. الصبر جزء من النظام.", status:"مقبول" },
  { risk:"فرضيات غير مؤكدة", severity:"منخفض", fix:"هذه طبيعة البحث — الخطر الحقيقي هو تشغيلها بدون اختبار. النظام يمنع ذلك بالتعريف.", status:"مُعالج هيكلياً" },
  { risk:"الإفراط في الثقة بالنظام", severity:"متوسط", fix:"لا تشغيل تلقائي بالكامل في البداية. الإنسان يراجع كل استراتيجية جديدة قبل Paper Trading.", status:"إجراء إلزامي" },
  { risk:"تكلفة الحساب", severity:"منخفض", fix:"50 trial Optuna + Backtest 90 يوم للفحص السريع + 8 اختبارات بالتوازي = طاقة معقولة.", status:"محلول" },
  { risk:"أخطاء كود = خسائر", severity:"عالي", fix:"Paper Trading إلزامي. حجم 0.01 lot في أول شهر Live. Circuit Breaker يوقف كل شيء عند الشذوذ.", status:"محلول" },
  { risk:"ضعف التعميم", severity:"متوسط", fix:"Walk-Forward حقيقي (لا Walk-Forward زائف). اختبار على أزواج لم تُدرَّب عليها. Out-of-sample يكشف ذلك.", status:"محلول" },
];

const ROADMAP = [
  { phase:"Phase 0 — الأساس", dur:"أسبوع 1", color:C.gold,
    steps:["استخراج الفرضيات من 119 صفقة الحالية (بياناتك = المنجم الأول)",
      "بناء Regime Detector (ADX + ATR + BB Width) — يعمل كل ساعة",
      "تجهيز Out-of-Sample: حجز آخر 20% من البيانات في ملف مقفل",
      "قاعدة البيانات: إنشاء 5 جداول بالـ Schema المحدد"] },
  { phase:"Phase 1 — MVP حقيقي", dur:"أسبوع 2-3", color:C.amber,
    steps:["فرضيتان فقط: LIQ-001 (Stop Hunt) + SES-001 (Asia Breakout)",
      "Backtest 90 يوم سريع — إذا فشلتا، عُد لمكتبة الفرضيات",
      "Backtest 3 سنوات + Out-of-Sample إذا نجحتا",
      "لا Optuna الآن — المعاملات الأصلية فقط"] },
  { phase:"Phase 2 — التوسع المحكوم", dur:"شهر 2", color:C.purple,
    steps:["إضافة 6 فرضيات جديدة (واحدة من كل فئة)",
      "Optuna بـ 50 trial فقط للناجحات",
      "Paper Trading لأفضل 4 استراتيجيات بالتوازي",
      "Decision Engine يعمل تلقائياً لاختيار الاستراتيجية بالنظام"] },
  { phase:"Phase 3 — التطور الذكي", dur:"شهر 3", color:C.blue,
    steps:["Claude API يولّد فرضيات جديدة بناءً على نتائج Phase 1+2",
      "دمج أفضل استراتيجيتين ناجحتين (Merge Evolution)",
      "ML Regime Detector: LightGBM يستبدل ADX البسيط",
      "Live Trading: أفضل 3 استراتيجيات بـ 0.01 lot"] },
  { phase:"Phase 4 — النخبة", dur:"مستمر", color:C.green,
    steps:["Weekly Tournament: 10 استراتيجيات تتنافس على نفس الفترة",
      "التقاعد التلقائي: فشل في موسمين = تقاعد نهائي",
      "Hall of Fame: أفضل 5 استراتيجيات في التاريخ محفوظة أبداً",
      "Retraining شهري للنماذج على أحدث البيانات"] },
];

// ──────────────────────────────────────────
// COMPONENT
// ──────────────────────────────────────────
export default function StrategyLabFinal() {
  const [tab, setTab] = useState("philosophy");
  const [openHyp, setOpenHyp] = useState(null);
  const [openCat, setOpenCat] = useState(0);
  const [openTable, setOpenTable] = useState(null);

  return (
    <div style={{
      background: C.bg, minHeight: "100vh", color: C.text,
      fontFamily: "'Courier New', monospace",
      direction: "rtl", fontSize: 13,
    }}>
      {/* TOP BAR */}
      <div style={{
        background: "#05060a", borderBottom: `1px solid ${C.gold}40`,
        padding: "18px 28px 0", position: "sticky", top: 0, zIndex: 100,
      }}>
        <div style={{ display:"flex", alignItems:"baseline", gap:16, marginBottom:14, flexWrap:"wrap" }}>
          <div style={{ color: C.gold, fontSize: 15, fontWeight: 700, letterSpacing:"0.08em" }}>
            ◈ FORXAI — STRATEGY LAB
          </div>
          <div style={{ color: C.textDim, fontSize: 10, letterSpacing:"0.2em" }}>
            MASTER DOCUMENT v3.0 — النسخة النهائية المعدّلة
          </div>
          <div style={{ marginRight:"auto", display:"flex", gap:8 }}>
            {tag("71 فرضية", C.gold)}
            {tag("6 مصادر هيكلية", C.amber)}
            {tag("13 مخاطرة محسوبة", C.red)}
          </div>
        </div>
        <div style={{ display:"flex", gap:2, flexWrap:"wrap" }}>
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} style={{
              background: tab===t.id ? "#12151c" : "transparent",
              border: "none",
              borderBottom: tab===t.id ? `2px solid ${C.gold}` : "2px solid transparent",
              color: tab===t.id ? C.goldBright : C.textDim,
              padding: "8px 14px", cursor:"pointer", fontSize:11,
              fontFamily:"inherit", letterSpacing:"0.05em",
              transition:"all 0.15s",
            }}>{t.label}</button>
          ))}
        </div>
      </div>

      {/* CONTENT */}
      <div style={{ padding:"28px 28px 60px", maxWidth:960, margin:"0 auto" }}>

        {/* ── 01 PHILOSOPHY ── */}
        {tab==="philosophy" && (
          <div>
            <Section title="01 — PHILOSOPHY — من أين تأتي الأفكار ولماذا؟"
              sub="الفلسفة الأساسية التي يقوم عليها كل شيء">
              <Alert type="ok">
                الفرضية الجيدة لا تُخترع — <strong>تُستخرج</strong> من مصادر هيكلية ثابتة.
                السؤال الأساسي لكل فرضية: <strong>"لماذا يجب أن أكون على الجانب الصحيح؟"</strong>
                إذا لم تستطع الإجابة — الفرضية ضعيفة بغض النظر عن نتائج الـ Backtest.
              </Alert>
              <div style={{ display:"grid", gap:12, marginTop:16 }}>
                {SOURCES.map(s => (
                  <div key={s.id} style={{
                    background: C.surface, border:`1px solid ${C.border}`,
                    borderRight:`3px solid ${s.color}`,
                    padding:16,
                  }}>
                    <div style={{ display:"flex", gap:12, alignItems:"center", marginBottom:10, flexWrap:"wrap" }}>
                      <Pill>{s.id}</Pill>
                      <span style={{ color: s.color, fontWeight:700 }}>{s.title}</span>
                      <Pill color={C.textDim}>{s.stability}</Pill>
                      <Pill color={C.textDim}>{s.source}</Pill>
                    </div>
                    <div style={{ color: C.textDim, fontSize:12, marginBottom:10, lineHeight:1.7 }}>{s.why}</div>
                    <div style={{ display:"grid", gap:4 }}>
                      {s.examples.map((e,i) => (
                        <div key={i} style={{ display:"flex", gap:10, color: C.text, fontSize:12, lineHeight:1.7 }}>
                          <span style={{ color: s.color, flexShrink:0 }}>→</span>
                          <span>{e}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </Section>

            <Section title="القاعدة الذهبية" accent={C.goldBright}>
              <div style={{
                background:"#0a0a05", border:`1px solid ${C.gold}50`,
                padding:20, fontSize:13, lineHeight:2, color: C.text,
              }}>
                <div style={{ color: C.goldBright, marginBottom:12, fontWeight:700 }}>الفرق بين فرضية قوية وضعيفة:</div>
                <div style={{ marginBottom:8 }}>
                  <span style={{ color: C.red }}>✖ ضعيفة:</span>
                  <span style={{ color: C.textDim, marginRight:8 }}>"RSI أقل من 30 = شراء"</span>
                  <span style={{ color: C.textDim, fontSize:11 }}>← لماذا؟ لا إجابة.</span>
                </div>
                <div>
                  <span style={{ color: C.green }}>✓ قوية:</span>
                  <span style={{ color: C.text, marginRight:8 }}>"RSI أقل من 30 + عند Order Block مؤسسي + في نهاية جلسة لندن = شراء"</span>
                </div>
                <div style={{ color: C.textDim, fontSize:11, marginTop:8, marginRight:20 }}>
                  ← لأن هناك مشترين مؤسسيين مجبَرين على الشراء عند هذا المستوى قبل إغلاق لندن — وهذا هيكلي لا عشوائي.
                </div>
              </div>
            </Section>
          </div>
        )}

        {/* ── 02 HYPOTHESES ── */}
        {tab==="hypotheses" && (
          <div>
            <Section title="02 — HYPOTHESIS LIBRARY — مكتبة الفرضيات الكاملة"
              sub="71 فرضية من 6 مصادر هيكلية — كل فرضية تحمل Edge + إشارة + شرط إلغاء">
              <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:12, marginBottom:20 }}>
                {[
                  { l:"إجمالي الفرضيات", v:71, c:C.gold },
                  { l:"الفئات الرئيسية", v:6, c:C.amber },
                  { l:"استراتيجية قابلة للتوليد", v:"~30-40", c:C.green },
                ].map((s,i)=>(
                  <div key={i} style={{ background:C.surface, border:`1px solid ${C.border}`, padding:16, textAlign:"center" }}>
                    <div style={{ color:s.c, fontSize:30, fontWeight:700 }}>{s.v}</div>
                    <div style={{ color:C.textDim, fontSize:11, marginTop:4 }}>{s.l}</div>
                  </div>
                ))}
              </div>

              {/* Category tabs */}
              <div style={{ display:"flex", gap:6, marginBottom:16, flexWrap:"wrap" }}>
                {HYPOTHESES.map((cat,ci)=>(
                  <button key={ci} onClick={()=>{setOpenCat(ci);setOpenHyp(null);}} style={{
                    background: openCat===ci ? "#12151c" : "transparent",
                    border: `1px solid ${openCat===ci ? cat.color : C.border}`,
                    color: openCat===ci ? cat.color : C.textDim,
                    padding:"6px 14px", cursor:"pointer", fontSize:11,
                    fontFamily:"inherit", transition:"all 0.15s",
                  }}>{cat.cat} <span style={{opacity:0.5}}>({cat.items.length})</span></button>
                ))}
              </div>

              {(() => {
                const cat = HYPOTHESES[openCat];
                return (
                  <div>
                    <div style={{
                      background: C.surface, borderRight:`3px solid ${cat.color}`,
                      border:`1px solid ${C.border}`, padding:14, marginBottom:12,
                      display:"flex", gap:12, alignItems:"center", flexWrap:"wrap",
                    }}>
                      <Pill color={cat.color}>{cat.sourceLabel}</Pill>
                      <span style={{ color:C.textDim, fontSize:12 }}>
                        كل فرضية في هذه الفئة مشتقة من: <span style={{color:cat.color}}>{cat.sourceLabel}</span>
                      </span>
                    </div>
                    <div style={{ display:"grid", gap:8 }}>
                      {cat.items.map((hyp,hi)=>(
                        <div key={hi}
                          style={{
                            background: openHyp===hi ? "#0f1218" : C.surface,
                            border:`1px solid ${openHyp===hi ? cat.color+"60" : C.border}`,
                            transition:"all 0.15s",
                          }}>
                          <div onClick={()=>setOpenHyp(openHyp===hi?null:hi)}
                            style={{ padding:"14px 16px", cursor:"pointer",
                              display:"flex", gap:12, alignItems:"center", flexWrap:"wrap" }}>
                            <span style={{ color:cat.color, fontSize:10, fontFamily:"monospace" }}>{hyp.id}</span>
                            <span style={{ color:C.textBright, fontWeight:700 }}>{hyp.ar}</span>
                            <span style={{ color:C.textDim, fontSize:11 }}>({hyp.name})</span>
                            <div style={{ marginRight:"auto", display:"flex", gap:6, flexWrap:"wrap" }}>
                              {hyp.pairs.map((p,pi)=><Pill key={pi} size={10}>{p}</Pill>)}
                              {hyp.tf.map((t,ti)=><Pill key={ti} color={C.purple} size={10}>{t}</Pill>)}
                            </div>
                            <span style={{ color:C.textDim, fontSize:12 }}>{openHyp===hi?"▲":"▼"}</span>
                          </div>
                          {openHyp===hi && (
                            <div style={{ borderTop:`1px solid ${C.border}`, padding:16 }}>
                              {[
                                { l:"📐 الفرضية", v:hyp.thesis, c:C.text },
                                { l:"⚡ الحافة (Edge)", v:hyp.edge, c:C.green },
                                { l:"🎯 إشارة الدخول", v:hyp.entry, c:C.gold },
                                { l:"🚫 شرط الإلغاء", v:hyp.invalidation, c:C.red },
                                { l:"🌊 النظام المناسب", v:hyp.regime, c:C.amber },
                              ].map((r,ri)=>(
                                <div key={ri} style={{
                                  display:"flex", gap:14, padding:"9px 0",
                                  borderBottom: ri<4 ? `1px solid ${C.border}` : "none",
                                }}>
                                  <div style={{ color:C.textDim, fontSize:11, minWidth:140, flexShrink:0 }}>{r.l}</div>
                                  <div style={{ color:r.c, fontSize:12, lineHeight:1.7 }}>{r.v}</div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })()}
            </Section>
          </div>
        )}

        {/* ── 03 FUNNEL ── */}
        {tab==="funnel" && (
          <div>
            <Section title="03 — THE FUNNEL — القمع والأعداد الحقيقية"
              sub="71 فرضية في القمة، 2-3 استراتيجيات نخبة في القاع — هذا هو الهدف">
              <Alert type="warn">
                الهدف النهائي ليس <strong>كثرة الاستراتيجيات</strong> — بل الوصول لـ <strong>2-3 استراتيجيات مفهومة وموثوقة</strong> تعمل في ظروف محددة معروفة مسبقاً.
                القمع الصارم هو الضمان ضد الضوضاء.
              </Alert>
              <div style={{ display:"grid", gap:6, marginTop:16 }}>
                {FUNNEL.map((f,fi)=>(
                  <div key={fi} style={{
                    background: C.surface, border:`1px solid ${C.border}`,
                    borderRight:`3px solid ${f.color}`,
                    padding:"16px 20px",
                    display:"grid", gridTemplateColumns:"180px 80px 1fr",
                    gap:16, alignItems:"center",
                  }}>
                    <div>
                      <div style={{ color:f.color, fontWeight:700, fontSize:12 }}>{f.stage}</div>
                      <div style={{ color:C.textDim, fontSize:10, marginTop:2 }}>معدل النجاح: {f.pct}%</div>
                    </div>
                    <div style={{
                      color:f.color, fontSize:28, fontWeight:900, textAlign:"center",
                      fontFamily:"monospace",
                    }}>{f.count}</div>
                    <div style={{ color:C.textDim, fontSize:12, lineHeight:1.7 }}>{f.desc}</div>
                  </div>
                ))}
              </div>
              <div style={{ marginTop:20 }}>
                <Section title="عدد الاستراتيجيات القابلة للتوليد — الحساب الحقيقي" accent={C.amber}>
                  <Alert type="info">
                    <strong>نظرياً:</strong> 71 فرضية × متوسط 3 أزواج × متوسط 2 إطار زمني = <strong>~426</strong> استراتيجية ممكنة<br/>
                    <strong>واقعياً في المرحلة الأولى:</strong> <strong>15-20</strong> استراتيجية — أفضل فرضية من كل فئة على الزوج الأنسب<br/>
                    <strong>في التشغيل الحي:</strong> لا أكثر من <strong>6-8</strong> في نفس الوقت — للتحكم والمراقبة الفعلية
                  </Alert>
                </Section>
                <Section title="التحسين أم الانتقاء؟ — الإجابة الصادقة" accent={C.green}>
                  <div style={{ display:"grid", gap:10 }}>
                    <Alert type="ok">
                      <strong>الانتقاء أولاً:</strong> "هل هذه الفرضية لها حق الوجود؟" — إذا فشلت في المقاييس الأساسية، لا تحسين ولا إنقاذ.
                      إذا كانت الفرضية خاطئة، Optuna لن يصلحها — ستكون Overfitting على الفشل.
                    </Alert>
                    <Alert type="ok">
                      <strong>التحسين للناجحين فقط:</strong> اجتازت الانتقاء لكن نتائجها جيدة وليست ممتازة → Optuna بـ 50 trial لتحسين المعاملات فقط — لا تغيير المنطق.
                    </Alert>
                    <Alert type="ok">
                      <strong>الدمج (الأقوى):</strong> استراتيجيتان ناجحتان في نفس الفئة → تُدمجان في استراتيجية أقوى.
                      مثال: Stop Hunt + Fair Value Gap = إشارة أعلى جودة من كل منهما منفرداً.
                    </Alert>
                  </div>
                </Section>
              </div>
            </Section>
          </div>
        )}

        {/* ── 04 SELECTION ── */}
        {tab==="selection" && (
          <div>
            <Section title="04 — SELECTION + IMPROVEMENT — الانتقاء والتحسين"
              sub="الاثنان معاً لكن بترتيب صارم">
              <div style={{ display:"grid", gap:10, marginBottom:24 }}>
                {[
                  { phase:"المرحلة 1 — الانتقاء الصارم", color:C.gold,
                    q:"هل هذه الفرضية لها حق الوجود أصلاً؟",
                    steps:["Backtest سريع 90 يوم — الهدف الإقصاء لا الإثبات",
                      "فحص المقاييس الأساسية الخمس (fatal metrics)",
                      "فشل أي منها = رفض فوري — بدون نقاش أو تحسين",
                      "الرفض يُحفظ في أرشيف التعلم مع سبب الفشل"] },
                  { phase:"المرحلة 2 — الاختبار العميق", color:C.amber,
                    q:"هل تصمد على البيانات التي لم ترَها؟",
                    steps:["Walk-Forward حقيقي على 3 سنوات",
                      "Out-of-Sample (20% محجوز مسبقاً) — هذا الاختبار الحقيقي الوحيد",
                      "Out-of-Sample PF > 1.2 شرط لا تفاوض عليه",
                      "أي انهيار في Out-of-Sample = Overfitting = رفض"] },
                  { phase:"المرحلة 3 — التحسين للناجحين", color:C.purple,
                    q:"كيف نجعل الناجح أفضل؟",
                    steps:["Optuna 50 trial فقط — لا 500 (تجنب Overfitting)",
                      "تحسين المعاملات فقط — لا تغيير منطق الدخول/الخروج",
                      "التحسين على training set فقط — ثم التحقق على Out-of-Sample",
                      "إذا ارتفع Train score لكن انخفض OOS score = Overfitting، أوقف"] },
                  { phase:"المرحلة 4 — الدمج والتطور", color:C.green,
                    q:"هل يمكن الجمع بين الناجحين؟",
                    steps:["Merge: استراتيجيتان ناجحتان في نفس الفئة → دمج فلاتر كلتيهما",
                      "Crossover: فرضيتان من فئتين مختلفتين → استراتيجية هجينة",
                      "Mutation: تعديل عشوائي صغير في المعاملات → اختبار",
                      "Evolution يُقيَّم كالأصل — نفس funnel، لا استثناءات"] },
                ].map((p,pi)=>(
                  <div key={pi} style={{
                    background: C.surface, border:`1px solid ${C.border}`,
                    borderRight:`3px solid ${p.color}`, padding:16,
                  }}>
                    <div style={{ marginBottom:12 }}>
                      <div style={{ color:p.color, fontWeight:700, marginBottom:4 }}>{p.phase}</div>
                      <div style={{ color:C.textDim, fontSize:12, fontStyle:"italic" }}>"{p.q}"</div>
                    </div>
                    <div style={{ display:"grid", gap:6 }}>
                      {p.steps.map((s,si)=>(
                        <div key={si} style={{ display:"flex", gap:10, fontSize:12, lineHeight:1.7 }}>
                          <span style={{ color:p.color, flexShrink:0 }}>◈</span>
                          <span style={{ color:C.text }}>{s}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </Section>
          </div>
        )}

        {/* ── 05 SCORING ── */}
        {tab==="scoring" && (
          <div>
            <Section title="05 — SCORING SYSTEM — نظام التقييم والقبول والرفض"
              sub="5 مقاييس أساسية قاتلة + 6 ثانوية + درجة S/A/B/C/F">
              <Alert type="danger">
                فشل أي مقياس أساسي واحد = <strong>رفض فوري</strong> — بغض النظر عن باقي المقاييس.
                لا يوجد "متوسط" أو "تعويض". هذه ليست قواعد صارمة — هي منطق رياضي.
              </Alert>
              <div style={{ marginTop:16, marginBottom:24 }}>
                <div style={{ color:C.textDim, fontSize:11, letterSpacing:"0.15em", marginBottom:10 }}>المقاييس الأساسية — FATAL</div>
                <div style={{ display:"grid", gap:1 }}>
                  <div style={{ display:"grid", gridTemplateColumns:"1fr 1.5fr 100px 100px 60px 50px", gap:8, padding:"8px 14px", background:"#05060a", color:C.textDim, fontSize:10 }}>
                    <span>المقياس</span><span>السبب</span><span>قبول</span><span>رفض</span><span>وزن</span><span>قاتل</span>
                  </div>
                  {SCORING.primary.map((m,mi)=>(
                    <div key={mi} style={{
                      display:"grid", gridTemplateColumns:"1fr 1.5fr 100px 100px 60px 50px",
                      gap:8, padding:"13px 14px", background: C.surface,
                      border:`1px solid ${C.border}`, alignItems:"start",
                    }}>
                      <span style={{ color:C.textBright, fontWeight:700, fontSize:12 }}>{m.m}</span>
                      <span style={{ color:C.textDim, fontSize:11, lineHeight:1.6 }}>{m.why}</span>
                      <span style={{ color:C.green }}>{m.pass}</span>
                      <span style={{ color:C.red }}>{m.fail}</span>
                      <span style={{ color:C.gold }}>{m.w}</span>
                      <span style={{ color: m.fatal ? C.red : C.textDim }}>{m.fatal?"✖ نعم":"لا"}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div style={{ marginBottom:24 }}>
                <div style={{ color:C.textDim, fontSize:11, letterSpacing:"0.15em", marginBottom:10 }}>المقاييس الثانوية — للتحليل والفهم</div>
                <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8 }}>
                  {SCORING.secondary.map((m,mi)=>(
                    <div key={mi} style={{ background:C.surface, border:`1px solid ${C.border}`, padding:"12px 14px" }}>
                      <div style={{ display:"flex", justifyContent:"space-between", marginBottom:4 }}>
                        <span style={{ color:C.textBright, fontWeight:700, fontSize:12 }}>{m.m}</span>
                        <span style={{ color:C.amber, fontSize:11 }}>{m.bench}</span>
                      </div>
                      <div style={{ color:C.textDim, fontSize:11 }}>{m.desc}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <div style={{ color:C.textDim, fontSize:11, letterSpacing:"0.15em", marginBottom:10 }}>التقدير والإجراء</div>
                <div style={{ display:"grid", gap:6 }}>
                  {SCORING.grades.map((g,gi)=>(
                    <div key={gi} style={{
                      background: g.c+"08", border:`1px solid ${g.c}30`,
                      padding:"14px 18px", display:"flex", gap:16, alignItems:"center",
                    }}>
                      <div style={{ color:g.c, fontWeight:900, fontSize:26, minWidth:36, textAlign:"center" }}>{g.g}</div>
                      <Pill color={g.c}>{g.range}</Pill>
                      <div style={{ color:C.text, fontSize:12 }}>{g.action}</div>
                    </div>
                  ))}
                </div>
              </div>
            </Section>
          </div>
        )}

        {/* ── 06 ENGINE ── */}
        {tab==="engine" && (
          <div>
            <Section title="06 — DECISION ENGINE — محرك القرار"
              sub="5 خطوات محددة بالترتيب — لا غموض، لا اجتهاد">
              <Alert type="warn">
                هذا أكثر ما كان غامضاً في الخطة الأولى.
                الآن: <strong>5 خطوات بترتيب صارم</strong>، كل خطوة تعطي output محدد يدخل للخطوة التالية.
              </Alert>
              <div style={{ display:"grid", gap:10, marginTop:16 }}>
                {DECISION_ENGINE.map((d,di)=>(
                  <div key={di} style={{
                    background: C.surface, border:`1px solid ${C.border}`,
                    borderRight:`3px solid ${d.color}`, padding:18,
                  }}>
                    <div style={{ display:"flex", gap:14, alignItems:"flex-start" }}>
                      <div style={{
                        width:32, height:32, borderRadius:"50%",
                        background:d.color+"20", border:`1px solid ${d.color}`,
                        color:d.color, display:"flex", alignItems:"center", justifyContent:"center",
                        fontWeight:900, flexShrink:0, fontSize:14,
                      }}>{d.step}</div>
                      <div style={{ flex:1 }}>
                        <div style={{ color:d.color, fontWeight:700, marginBottom:8 }}>{d.title}</div>
                        <Row label="المنطق" value={d.logic} accent={C.text} />
                        <Row label="المخرج" value={d.output} accent={C.green} note="output" />
                        <Row label="خطر / حماية" value={d.risk} accent={C.amber} note="guard" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </Section>
          </div>
        )}

        {/* ── 07 NAMING ── */}
        {tab==="naming" && (
          <div>
            <Section title="07 — NAMING + STORAGE — التسمية والتخزين">
              <div style={{ marginBottom:24 }}>
                <div style={{ color:C.textDim, fontSize:11, letterSpacing:"0.15em", marginBottom:12 }}>نظام التسمية</div>
                <div style={{
                  background:"#050508", border:`1px solid ${C.gold}50`,
                  padding:20, textAlign:"center", marginBottom:16,
                }}>
                  <div style={{ color:C.gold, fontSize:20, fontWeight:700, letterSpacing:"0.15em", fontFamily:"monospace" }}>
                    {NAMING.format}
                  </div>
                  <div style={{ color:C.textDim, fontSize:12, marginTop:8 }}>
                    مثال: <span style={{color:C.goldBright}}>{NAMING.example}</span>
                  </div>
                </div>
                <div style={{ display:"grid", gap:6 }}>
                  {NAMING.parts.map((p,pi)=>(
                    <div key={pi} style={{
                      background:C.surface, border:`1px solid ${C.border}`,
                      padding:"12px 16px", display:"flex", gap:16, alignItems:"center",
                    }}>
                      <span style={{ color:C.gold, fontFamily:"monospace", fontWeight:700, minWidth:60 }}>{p.p}</span>
                      <span style={{ color:C.text, fontSize:12 }}>{p.d}</span>
                      <span style={{ color:C.textDim, fontSize:11, marginRight:"auto" }}>{p.ex}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div style={{ marginBottom:24 }}>
                <div style={{ color:C.textDim, fontSize:11, letterSpacing:"0.15em", marginBottom:12 }}>نظام الإصدارات</div>
                {NAMING.versioning.map((v,vi)=>(
                  <div key={vi} style={{
                    background:C.surface, border:`1px solid ${C.border}`,
                    padding:"11px 16px", display:"flex", gap:16, alignItems:"center", marginBottom:4,
                  }}>
                    <Pill color={C.amber}>{v.bump}</Pill>
                    <span style={{ color:C.text, fontSize:12 }}>{v.trigger}</span>
                  </div>
                ))}
              </div>

              <div>
                <div style={{ color:C.textDim, fontSize:11, letterSpacing:"0.15em", marginBottom:12 }}>مخطط قاعدة البيانات — 5 جداول</div>
                <div style={{ display:"grid", gap:10 }}>
                  {NAMING.tables.map((t,ti)=>(
                    <div key={ti} style={{ background:C.surface, border:`1px solid ${C.border}` }}>
                      <div onClick={()=>setOpenTable(openTable===ti?null:ti)}
                        style={{
                          padding:"12px 16px", cursor:"pointer",
                          display:"flex", gap:12, alignItems:"center",
                          borderBottom: openTable===ti ? `1px solid ${C.border}` : "none",
                        }}>
                        <span style={{ color:C.gold, fontSize:10, fontFamily:"monospace" }}>TABLE</span>
                        <span style={{ color:C.textBright, fontWeight:700 }}>{t.name}</span>
                        <span style={{ color:C.textDim, fontSize:11, marginRight:"auto" }}>{t.fields.length} حقل</span>
                        <span style={{ color:C.textDim }}>{openTable===ti?"▲":"▼"}</span>
                      </div>
                      {openTable===ti && (
                        <div style={{ padding:"8px 0" }}>
                          {t.fields.map((f,fi)=>{
                            const isSpecial = f.includes("←") || f.includes("أهم");
                            return (
                              <div key={fi} style={{
                                padding:"6px 20px", fontSize:11, fontFamily:"monospace",
                                color: isSpecial ? C.gold : C.textDim,
                                background: fi%2===0 ? "#0a0b0e" : C.surface,
                                borderRight: isSpecial ? `2px solid ${C.gold}` : "none",
                              }}>{f}</div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </Section>
          </div>
        )}

        {/* ── 08 RISKS ── */}
        {tab==="risks" && (
          <div>
            <Section title="08 — RISK REGISTER — سجل المخاطر الكامل"
              sub="13 مخاطرة محددة، كل منها بحل محدد أو قرار واضح">
              <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:10, marginBottom:20 }}>
                {[
                  { l:"محلول", v:RISKS.filter(r=>r.status==="محلول").length, c:C.green },
                  { l:"مؤجل/مقبول", v:RISKS.filter(r=>r.status!=="محلول"&&r.status!=="إجراء إلزامي").length, c:C.amber },
                  { l:"إجراء إلزامي", v:RISKS.filter(r=>r.status==="إجراء إلزامي").length, c:C.gold },
                ].map((s,i)=>(
                  <div key={i} style={{ background:C.surface, border:`1px solid ${C.border}`, padding:14, textAlign:"center" }}>
                    <div style={{ color:s.c, fontSize:26, fontWeight:700 }}>{s.v}</div>
                    <div style={{ color:C.textDim, fontSize:11 }}>{s.l}</div>
                  </div>
                ))}
              </div>
              <div style={{ display:"grid", gap:8 }}>
                {RISKS.map((r,ri)=>{
                  const sc = { "محلول":C.green, "مؤجل":C.amber, "مقبول":C.amber, "مُعالج هيكلياً":C.blue, "إجراء إلزامي":C.gold }[r.status] || C.textDim;
                  const sev = { "عالي جداً — الأخطر":C.red, "عالي":C.amber, "متوسط":C.gold, "منخفض":C.textDim, "منخفض — لا حل سحري":C.textDim }[r.severity] || C.textDim;
                  return (
                    <div key={ri} style={{
                      background:C.surface, border:`1px solid ${C.border}`,
                      borderRight:`3px solid ${sc}`, padding:"14px 18px",
                    }}>
                      <div style={{ display:"flex", gap:12, alignItems:"center", marginBottom:8, flexWrap:"wrap" }}>
                        <span style={{ color:C.textDim, fontSize:10, minWidth:20 }}>{String(ri+1).padStart(2,"0")}</span>
                        <span style={{ color:C.textBright, fontWeight:700 }}>{r.risk}</span>
                        <Pill color={sev} size={10}>{r.severity}</Pill>
                        <Pill color={sc} size={10}>{r.status}</Pill>
                      </div>
                      <div style={{ display:"flex", gap:10, fontSize:12, lineHeight:1.7 }}>
                        <span style={{ color:C.green, flexShrink:0 }}>→</span>
                        <span style={{ color:C.text }}>{r.fix}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </Section>
          </div>
        )}

        {/* ── 09 ROADMAP ── */}
        {tab==="roadmap" && (
          <div>
            <Section title="09 — ROADMAP — خارطة الطريق التنفيذية"
              sub="من MVP إلى النخبة — بخطوات واقعية لا نظرية">
              <Alert type="ok">
                المبدأ: <strong>أثبت المفهوم أولاً بأبسط شكل ممكن</strong>، ثم وسّع بشكل تدريجي محكوم.
                Phase 0 و Phase 1 لا تبدآن في نفس الوقت — كل phase تنتظر نجاح ما قبلها.
              </Alert>
              <div style={{ display:"grid", gap:16, marginTop:16 }}>
                {ROADMAP.map((p,pi)=>(
                  <div key={pi} style={{
                    background:C.surface, border:`1px solid ${C.border}`,
                    borderRight:`3px solid ${p.color}`,
                  }}>
                    <div style={{
                      padding:"14px 20px", borderBottom:`1px solid ${C.border}`,
                      display:"flex", gap:12, alignItems:"center",
                    }}>
                      <span style={{ color:p.color, fontWeight:700, fontSize:13 }}>{p.phase}</span>
                      <Pill color={p.color}>{p.dur}</Pill>
                    </div>
                    <div style={{ padding:"12px 20px", display:"grid", gap:8 }}>
                      {p.steps.map((s,si)=>(
                        <div key={si} style={{ display:"flex", gap:12, fontSize:12, lineHeight:1.8 }}>
                          <span style={{ color:p.color, flexShrink:0, marginTop:1 }}>◈</span>
                          <span style={{ color:C.text }}>{s}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              <div style={{ marginTop:24 }}>
                <Section title="الهدف النهائي — ليس رقماً بل نوعية" accent={C.goldBright}>
                  <div style={{
                    background:"#050508", border:`1px solid ${C.gold}50`,
                    padding:24, lineHeight:2.2, color:C.text, fontSize:13,
                  }}>
                    <div style={{ color:C.goldBright, fontWeight:700, marginBottom:12 }}>
                      2-3 استراتيجيات نخبة تحقق:
                    </div>
                    {[
                      "مفهومة: نعرف لماذا تربح وفي أي ظروف",
                      "موثوقة: أثبتت نفسها في Out-of-Sample وفي Paper Trading",
                      "محدودة المخاطر: Circuit Breaker يحميها وحجم متحكم فيه",
                      "قابلة للتطور: كل شهر تُحدَّث نماذجها على أحدث البيانات",
                      "قابلة للاستبدال: إذا تقاعدت، الـ Funnel جاهز لتوليد خلفائها",
                    ].map((item,i)=>(
                      <div key={i} style={{ display:"flex", gap:12 }}>
                        <span style={{ color:C.gold }}>✓</span>
                        <span>{item}</span>
                      </div>
                    ))}
                  </div>
                </Section>
              </div>
            </Section>
          </div>
        )}

      </div>

      {/* FOOTER */}
      <div style={{
        borderTop:`1px solid ${C.border}`, padding:"12px 28px",
        display:"flex", justifyContent:"space-between", alignItems:"center",
        color:C.textDim, fontSize:10, letterSpacing:"0.1em",
      }}>
        <span>FORXAI STRATEGY LAB — MASTER DOCUMENT v3.0</span>
        <span>بُني على أساس: ميكانيكا السوق + علم النفس + الالتزامات الهيكلية + بياناتك الحقيقية</span>
        <span>CONFIDENTIAL — 2026</span>
      </div>
    </div>
  );
}
