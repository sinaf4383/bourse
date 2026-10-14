# -*- coding: utf-8 -*-
"""
بورس همه‌کاره - نسخه ۶ (میان‌مدت)

منو (۵ گزینه):
  ۱) تحلیل پورتفوی من: هر سهم جدا بررسی می‌شود و می‌گوید امروز چه کار کنید
  ۲) پیشنهاد سهم برای خرید (میان‌مدت، حدود ۲ ماه)
  ۳) بک‌تست میان‌مدت: آزمایش قاعده‌ها روی تاریخچه (هفته‌ای یک بار کافی است)
  ۴) ویرایش لیست سهام من (چند نماد را با فاصله بنویسید)
  ۵) دیده‌بان بازار: تحلیل هفته، پول حقیقی، گروه‌ها و هشدار داغی بازار

ثبت داده‌ی حقیقی/حقوقی و دفتر آزمون زنده خودکار انجام می‌شود (بعد از ۱۲:۴۵).
فقط به requests نیاز دارد.
"""
import csv
import difflib
import itertools
import json
import os
import random
import statistics
import time
import traceback
from datetime import datetime

import requests

# ======================= تنظیمات =======================
MODE = "menu"              # "menu" یا مستقیم یک عدد از "1" تا "5"

# لیست سهام شما در فایل my_stocks.txt (کنار برنامه) ذخیره می‌شود (گزینه‌ی ۴).
MY_STOCKS_FILE = "my_stocks.txt"
MY_STOCKS = {"فولاد": None, "شپنا": None}   # فقط برای بار اول

# --- تحلیل پورتفو ---
TRAIL_PCT = 12.0           # حد ضرر شناور: این‌قدر زیر بالاترین قیمت پایانی ۴۰ روز اخیر
FIXED_STOP_PCT = 10.0      # اگر قیمت خرید را بدهید: حداکثر ضرر از قیمت خرید
TAKE_PROFIT_PCT = 30.0     # از این سود به بعد، فروش بخشی از سهم پیشنهاد می‌شود
EXTENDED_PCT = 30.0        # اگر قیمت این‌قدر بالای میانگین ۵۰ روزه باشد (کشیده شده)

# --- پیشنهاد خرید میان‌مدت (بعد از اجرای گزینه‌ی ۳ تنظیمشان کنید) ---
LONG = {"val": 30,          # حداقل میانگین ارزش معاملات ۲۰ روز (میلیارد تومان)
        "trend": True,      # قیمت بالای میانگین ۵۰ روزه و میانگین ۲۰ روزه بالای ۵۰ روزه
        "r60": 0.0,         # حداقل بازده ۶۰ روز اخیر (٪)
        "r20max": 25.0}     # حداکثر بازده ۲۰ روز اخیر (٪) تا سهم کشیده نباشد
REGIME_MIN_BREADTH = 50.0  # حداقل ٪ نمادهای بالای میانگین ۱۰ روزه (وضعیت کل بازار)
LONG_EXIT = (40, "trail", 12.0)   # (حداکثر روز نگهداری، نوع حد ضرر، درصد)
CAPITAL_TOMAN = 0          # سرمایه‌ی کل (تومان). ۰ = محاسبه‌ی حجم خاموش
RISK_PER_TRADE_PCT = 2.0   # حداکثر ضرر قابل قبول از کل سرمایه در هر معامله

# --- هشدارهای پیشنهاد خرید و دیده‌بان (تست‌نشده) ---
OVERHEAT_RET10 = 8.0       # رشد ۱۰ جلسه‌ی اخیر شاخص هم‌وزن (٪) که بازار «داغ» حساب شود
OVERHEAT_BREADTH = 85.0    # یا درصد نمادهای بالای میانگین ۱۰ روزه
R60_FLAG = 60.0            # بازده ۶۰ روز بیشتر از این: سهم «خیلی کشیده» است
EXT50_FLAG = 20.0          # فاصله از میانگین ۵۰ روزه بیشتر از این (٪): کشیده
PE_RATIO_FLAG = 1.5        # P/E بیشتر از این برابر میانه‌ی گروه: هشدار گرانی

# --- بک‌تست میان‌مدت ---
# هر کدام: (حداکثر روز نگهداری، "fixed" ثابت یا "trail" شناور، درصد حد ضرر)
EXITS = [(20, "fixed", 8.0), (40, "trail", 12.0), (60, "trail", 15.0), (40, "fixed", 10.0)]
STEP = 3                   # هر چند روز یک نمونه (برای سرعت)
COST_PCT = 1.5             # کارمزد و مالیات رفت‌وبرگشت - با کارگزار خود چک کنید
TRAIN_FRAC = 0.7
MIN_TRAIN, MIN_TEST = 80, 30

# --- داده: بررسی مرحله‌ای تا مسدود نشوید ---
N_CORE = 120               # نمادهای پرمعامله برای وضعیت بازار و بک‌تست
BATCH_SIZE = 25            # بعد از هر چند نماد، استراحت
BATCH_PAUSE = 15           # ثانیه‌ی استراحت بین دسته‌ها
MAX_REQUESTS = 400         # حداکثر درخواست تاریخچه در هر بار اجرا
HISTORY_DAYS = 500
CACHE_FILE = "bourse_cache.json"
PICKS_LOG = "picks_log_mid.csv"   # دفتر آزمون زنده
# =========================================================

HOSTS = ["http://old.tsetmc.com", "https://old.tsetmc.com",
         "http://members.tsetmc.com"]
MW_PATH = "/tsev2/data/MarketWatchPlus.aspx?h=0&r=0"
CT_PATH = "/tsev2/data/ClientTypeAll.aspx"
HIST_PATH = "/tsev2/data/InstTradeHistory.aspx?i={}&Top={}&A=0"
HEADERS = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36"}
_dbg = {"n": 0}
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_NUM = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


# ======================= ابزارهای پایه =======================
def fnum(x):
    try:
        return float(x)
    except Exception:
        return 0.0


def fa(s):
    return s.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ").strip()


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def after_close():
    now = datetime.now()
    return now.hour * 60 + now.minute >= 12 * 60 + 45


def fetch(path, min_len):
    for host in HOSTS:
        try:
            r = requests.get(host + path, headers=HEADERS, timeout=25)
            if r.status_code == 200 and len(r.text) >= min_len:
                return r.text
        except Exception:
            pass
    return None


def fetch_hist(code):
    path = HIST_PATH.format(code, HISTORY_DAYS)
    for attempt in range(3):
        for host in HOSTS[:2]:
            try:
                r = requests.get(host + path, headers=HEADERS, timeout=30)
                if r.status_code == 200 and len(r.text) >= 20:
                    return r.text
                if _dbg["n"] < 3:
                    print("  [debug]", host, r.status_code, len(r.text))
                    _dbg["n"] += 1
            except Exception as e:
                if _dbg["n"] < 3:
                    print("  [debug] خطا:", str(e)[:100])
                    _dbg["n"] += 1
        time.sleep(1.0 * (attempt + 1))
    return None


def parse_market(text):
    best = []
    for part in text.split("@"):
        rows = [r.split(",") for r in part.split(";") if r]
        good = [r for r in rows if len(r) >= 22 and r[1].startswith("IR")]
        if len(good) > len(best):
            best = good
    return best


def parse_client(text):
    data = {}
    for row in text.replace("@", ";").split(";"):
        c = row.split(",")
        if len(c) >= 9:
            data[c[0]] = c
    return data


def client_info(c):
    if not c:
        return None
    bc, sc = fnum(c[1]), fnum(c[5])
    bi, bn, si, sn = fnum(c[3]), fnum(c[4]), fnum(c[7]), fnum(c[8])
    if bc <= 0 or sc <= 0 or si <= 0:
        return None
    return {"power": (bi / bc) / (si / sc), "net_vol": bi - si,
            "legal_buy": bn / (bi + bn) * 100 if (bi + bn) else 0,
            "legal_sell": sn / (si + sn) * 100 if (si + sn) else 0}


def parse_history(text):
    """0 تاریخ | 1 بیشترین | 2 کمترین | 3 پایانی | 4 آخرین قیمت
    5 اولین قیمت | 6 دیروز | 7 ارزش | 8 حجم | 9 تعداد معاملات"""
    out = []
    for line in text.split(";"):
        r = line.split("@")
        if len(r) < 10 or not (r[0].isdigit() and len(r[0]) == 8):
            continue
        d = {"date": r[0], "high": fnum(r[1]), "low": fnum(r[2]),
             "close": fnum(r[4]), "open": fnum(r[5]), "py": fnum(r[6]),
             "val": fnum(r[7]), "vol": fnum(r[8])}
        if min(d["high"], d["low"], d["close"], d["open"], d["py"]) <= 0:
            continue
        out.append(d)
    out.sort(key=lambda x: x["date"])
    return out


# ======================= بارگذاری داده (مرحله‌ای) =======================
def entry_fresh(e):
    try:
        if datetime.fromtimestamp(e["ts"]).date() != datetime.now().date():
            return False
        return bool(e.get("final")) or (time.time() - e["ts"] < 1800)
    except Exception:
        return False


def load_cache():
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, encoding="utf-8") as f:
                c = json.load(f)
            if c.get("v") == 3:
                return {k: v for k, v in c.get("items", {}).items() if entry_fresh(v)}
    except Exception:
        pass
    return {}


def save_cache(items):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"v": 3, "items": items}, f, ensure_ascii=False)
    except Exception:
        pass


def log_clients(rows, clients, hist):
    """بعد از بسته شدن بازار، داده‌ی حقیقی/حقوقی را با «تاریخ واقعی داده» ذخیره می‌کند.
    برای اطمینان، حجم خرید حقیقی+حقوقی چند نماد بزرگ با حجم همان روز در تاریخچه مقایسه می‌شود."""
    if not after_close() or not hist:
        return
    latest = max(h[-1]["date"] for h in hist.values())
    ok = tot = 0
    for _, code, sym, _r in rows[:30]:
        c, h = clients.get(code), hist.get(sym)
        if c and h and h[-1]["date"] == latest and h[-1]["vol"] > 0:
            tot += 1
            if abs((fnum(c[3]) + fnum(c[4])) / h[-1]["vol"] - 1) < 0.02:
                ok += 1
    if tot < 5 or ok < tot * 0.7:
        print("(داده‌ی حقیقی/حقوقی ثبت نشد: هنوز با تاریخچه‌ی آخرین جلسه هم‌خوان نیست.)")
        return
    path = "client_log.csv"
    try:
        exists = os.path.exists(path)
        if exists:
            with open(path, encoding="utf-8") as f:
                if any(line.startswith(latest + ",") for line in f):
                    return
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(["date", "sym", "buy_cnt_i", "buy_cnt_n", "buy_vol_i",
                            "buy_vol_n", "sell_cnt_i", "sell_cnt_n",
                            "sell_vol_i", "sell_vol_n"])
            for _, code, sym, _r in rows:
                c = clients.get(code)
                if c:
                    w.writerow([latest, sym] + c[1:9])
        print(f"✅ داده‌ی حقیقی/حقوقی جلسه‌ی {latest} ذخیره شد.")
    except Exception:
        pass


def load_basic():
    """فقط لیست بازار و حقیقی/حقوقی (۲ درخواست)؛ برای وقتی که تاریخچه‌ها نیامدند."""
    mw = fetch(MW_PATH, 1000)
    if not mw:
        print("دریافت اطلاعات ناموفق بود. VPN را خاموش/روشن کنید.")
        return None
    ct = fetch(CT_PATH, 100)
    market, universe = {}, []
    for r in parse_market(mw):
        sym = fa(r[2])
        market[sym] = r
        if r[1].startswith("IRO1") and not sym.endswith("ح"):
            universe.append((fnum(r[10]), r[0], sym, r))
    universe.sort(key=lambda x: x[0], reverse=True)
    return market, universe, (parse_client(ct) if ct else {})


def load_data(want_survivors):
    """مرحله ۱: لیست کل بازار | مرحله ۲: پیش‌فیلتر با داده‌ی امروز |
    مرحله ۳: تاریخچه فقط برای نمادهای لازم، در دسته‌های کوچک با استراحت.
    پیشرفت ذخیره می‌شود؛ اگر سرور محدود کرد، بعداً دوباره اجرا کنید تا ادامه یابد."""
    print("مرحله ۱: دریافت لیست کل بازار ...")
    basic = load_basic()
    if not basic:
        return None
    market, universe, clients = basic
    print(f"  {len(market)} نماد در بازار | {len(universe)} سهم بررسی شد")

    core = universe[:N_CORE]
    core_syms = {x[2] for x in core}
    survivors = []
    if want_survivors:
        for tval, code, sym, r in universe:
            pl, py = fnum(r[7]), fnum(r[13])
            if pl <= 0 or py <= 0:
                continue
            if tval / 10 / 1e9 >= LONG["val"] * 0.5 and (pl / py - 1) * 100 < 2.7:
                survivors.append((tval, code, sym, r))
        print(f"مرحله ۲: {len(survivors)} نماد از پیش‌فیلتر امروز رد شد")

    surv_syms = {x[2] for x in survivors}
    order = survivors + [x for x in core if x[2] not in surv_syms]
    wanted = {x[2] for x in order}
    cache = load_cache()
    need = [x for x in order if x[2] not in cache]
    print(f"مرحله ۳: تاریخچه — {len(order) - len(need)} نماد آماده، {len(need)} نماد باید گرفته شود"
          + (" (چند دقیقه صبر کنید)" if need else ""))

    final = after_close()
    fails, reqs, blocked = 0, 0, False
    for k, (_, code, sym, _) in enumerate(need, 1):
        if reqs >= MAX_REQUESTS:
            print("به سقف درخواست این اجرا رسیدیم؛ بعداً دوباره اجرا کنید تا ادامه یابد.")
            break
        text = fetch_hist(code)
        reqs += 1
        if text is None:
            fails += 1
            if fails >= 5:
                blocked = True
                break
        else:
            fails = 0
            h = parse_history(text)
            cache[sym] = {"ts": time.time(), "final": final,
                          "h": h if len(h) >= 70 else []}
        if k % BATCH_SIZE == 0:
            save_cache(cache)
            print(f"  {k}/{len(need)} — استراحت {BATCH_PAUSE} ثانیه ...")
            time.sleep(BATCH_PAUSE)
        else:
            time.sleep(0.4 + random.random() * 0.3)
    save_cache(cache)

    hist = {sym: e["h"] for sym, e in cache.items()
            if sym in wanted and len(e.get("h", [])) >= 70}
    pending = len([x for x in order if x[2] not in cache])
    if blocked:
        print("\n⚠ سرور درخواست‌ها را محدود کرد. پیشرفت ذخیره شد؛ "
              "۱۰ تا ۱۵ دقیقه صبر کنید و دوباره اجرا کنید تا ادامه یابد.")
    print(f"نمادهای آماده‌ی تحلیل: {len(hist)}" + (f" | باقی‌مانده: {pending}" if pending else ""))
    if not hist:
        print("تاریخچه‌ای دریافت نشد.")
        return None
    log_clients(universe[:300], clients, hist)
    return hist, market, clients, core_syms, pending


# ======================= محاسبات =======================
def compute_breadth(hist):
    """برای هر تاریخ: درصد نمادهایی که قیمتشان بالای میانگین ۱۰ روزه است."""
    cnt = {}
    for h in hist.values():
        closes = [x["close"] for x in h]
        for i in range(9, len(h)):
            a = cnt.setdefault(h[i]["date"], [0, 0])
            a[1] += 1
            if closes[i] > mean(closes[i - 9:i + 1]):
                a[0] += 1
    return {d: a[0] / a[1] * 100 for d, a in cnt.items() if a[1] >= 30}


def regime_status(breadth):
    if not breadth:
        return None, None
    d = max(breadth)
    return d, breadth[d]


def print_regime(breadth):
    d, b = regime_status(breadth)
    if b is None:
        print("وضعیت بازار قابل محاسبه نبود.")
        return True
    strong = b >= REGIME_MIN_BREADTH
    print(f"\nوضعیت بازار ({d}): {b:.0f}٪ نمادها بالای میانگین ۱۰ روزه‌اند "
          f"(آستانه {REGIME_MIN_BREADTH:.0f}٪)")
    print("  ✅ بازار قوی؛ خرید جدید مجاز است" if strong
          else "  ⛔ بازار ضعیف؛ خرید جدید توصیه نمی‌شود")
    return strong


_WEEKDAYS = {5: "شنبه", 6: "یکشنبه", 0: "دوشنبه", 1: "سه‌شنبه", 2: "چهارشنبه",
             3: "پنجشنبه", 4: "جمعه"}


def print_data_date(latest):
    """تاریخ آخرین جلسه‌ی موجود در داده را نشان می‌دهد؛ اگر کهنه باشد هشدار می‌دهد."""
    try:
        dt = datetime.strptime(latest, "%Y%m%d")
    except Exception:
        return
    print(f"داده‌ی آخرین جلسه: {dt:%Y-%m-%d} ({_WEEKDAYS[dt.weekday()]})")
    now = datetime.now()
    if now.date() > dt.date() and now.weekday() in (5, 6, 0, 1, 2) and after_close():
        print("  ⚠ امروز روز معاملاتی است ولی داده‌ی امروز هنوز نیامده: یا بازار امروز بسته"
              " بوده یا سرور هنوز به‌روز نشده. «فردا» یعنی جلسه‌ی بعد از همین تاریخ.")


def market_series(hist):
    """شاخص هم‌وزن ساده از میانگین بازده روزانه‌ی نمادها (پایه ۱۰۰)."""
    rets = {}
    for h in hist.values():
        for k in range(1, len(h)):
            x = h[k]
            r = x["close"] / x["py"] - 1
            if abs(r) > 0.12:
                continue
            a = rets.setdefault(x["date"], [0.0, 0])
            a[0] += r
            a[1] += 1
    level, series = 100.0, []
    for d in sorted(rets):
        if rets[d][1] >= 30:
            level *= 1 + rets[d][0] / rets[d][1]
            series.append((d, level))
    return series


def period_return(series, n):
    if len(series) <= n:
        return None
    return (series[-1][1] / series[-1 - n][1] - 1) * 100


def market_hot(series, breadth):
    d, b = regime_status(breadth)
    r10 = period_return(series, 10)
    hot = (r10 is not None and r10 >= OVERHEAT_RET10) or (b is not None and b >= OVERHEAT_BREADTH)
    msg = ""
    if hot:
        parts = []
        if r10 is not None:
            parts.append(f"شاخص هم‌وزن در ۱۰ جلسه‌ی اخیر {r10:+.1f}٪")
        if b is not None:
            parts.append(f"{b:.0f}٪ نمادها بالای میانگین ۱۰ روزه")
        msg = "بازار داغ است (" + "؛ ".join(parts) + "). ورود تازه در چنین شرایطی ریسک بالاتری دارد (در بک‌تست تأیید نشده)."
    return hot, msg


def stock_rows(market):
    return [r for sym, r in market.items() if r[1].startswith("IRO1") and not sym.endswith("ح")]


def sector_groups(rows):
    """گروه‌بندی بر اساس کد صنعت؛ اگر ساختار داده معقول نبود None می‌دهد."""
    sec = {}
    for r in rows:
        sec.setdefault(r[18].strip(), []).append(r)
    ok = all(c.isdigit() and len(c) <= 3 for c in sec) and 12 <= len(sec) <= 90
    return sec if ok else None


def pe_table(rows):
    """P/E تقریبی = آخرین قیمت ÷ EPS؛ اگر داده معقول نبود None می‌دهد."""
    pes = {}
    for r in rows:
        eps, pl = fnum(r[14]), fnum(r[7])
        if eps > 0 and pl > 0:
            pes[fa(r[2])] = pl / eps
    if len(pes) < 100:
        return None
    return pes if 3 <= statistics.median(pes.values()) <= 40 else None


def pe_for(sym, r, pes, secs):
    if not pes or sym not in pes:
        return None, None
    med = None
    if secs and r:
        vals = [pes[fa(x[2])] for x in secs.get(r[18].strip(), [])
                if fa(x[2]) in pes and 0 < pes[fa(x[2])] < 200]
        if len(vals) >= 4:
            med = statistics.median(vals)
    return pes[sym], med


def weekly_returns(hist, n=5):
    """بازده n جلسه‌ی اخیر هر نماد (٪)، بدون روزهای غیرعادی."""
    out = {}
    for sym, h in hist.items():
        if len(h) < n + 3:
            continue
        w = h[-(n + 1):]
        if any(abs(w[k]["close"] / w[k]["py"] - 1) > 0.12 for k in range(1, len(w))):
            continue
        out[sym] = (w[-1]["close"] / w[0]["close"] - 1) * 100
    return out


def group_info(sym, market, secs, wk):
    """وضعیت گروه یک سهم: میانگین تغییر امروز (وزن‌دار با ارزش معاملات) و بازده ۵ جلسه."""
    r = market.get(sym)
    if not secs or not r:
        return None
    members = secs.get(r[18].strip(), [])
    if len(members) < 3:
        return None
    chg, wts = [], []
    for x in members:
        pl, py, tv = fnum(x[7]), fnum(x[13]), fnum(x[10])
        if pl > 0 and py > 0 and tv > 0:
            chg.append((pl / py - 1) * 100)
            wts.append(tv)
    if len(chg) < 3:
        return None
    day = sum(c * w for c, w in zip(chg, wts)) / sum(wts)
    rets = [wk[fa(x[2])] for x in members if fa(x[2]) in wk]
    big = sorted(members, key=lambda x: fnum(x[10]), reverse=True)[:3]
    return {"code": r[18].strip(), "day": day,
            "week": mean(rets) if len(rets) >= 3 else None,
            "label": "، ".join(fa(x[2]) for x in big)}


def group_line(g):
    return (f"  گروه ({g['label']}): امروز {g['day']:+.1f}٪"
            + (f" | ۵ جلسه {g['week']:+.1f}٪" if g["week"] is not None else ""))


def group_strength(hist, sector_of, win=5, min_members=3):
    """برای هر تاریخ: مجموعه‌ی گروه‌های «قوی» (ثلث بالای بازده win جلسه‌ی اخیر).
    فقط با داده‌ی تا همان تاریخ محاسبه می‌شود (بدون نگاه به آینده)."""
    by_date = {}
    for sym, h in hist.items():
        code = sector_of.get(sym)
        if code is None:
            continue
        for i in range(win, len(h)):
            r = h[i]["close"] / h[i - win]["close"] - 1
            if abs(r) > 0.6:
                continue
            by_date.setdefault(h[i]["date"], {}).setdefault(code, []).append(r)
    strong = {}
    for d, groups in by_date.items():
        vals = [(mean(v), c) for c, v in groups.items() if len(v) >= min_members]
        if len(vals) < 6:
            continue
        vals.sort(reverse=True)
        strong[d] = {c for _, c in vals[:max(1, len(vals) // 3)]}
    return strong


def swings(highs, lows, i, price):
    res = [highs[j] for j in range(max(2, i - 60), i - 1)
           if highs[j] == max(highs[j - 2:j + 3]) and highs[j] > price * 1.001]
    sup = [lows[j] for j in range(max(2, i - 60), i - 1)
           if lows[j] == min(lows[j - 2:j + 3]) and lows[j] < price * 0.999]
    resistance = min(res) if res else None
    support = max(sup) if sup else min(lows[max(0, i - 30):i + 1])
    return resistance, support


def features_long(h, i):
    """ویژگی‌های میان‌مدت در روز i (فقط با داده‌ی تا همان روز)."""
    if i < 60:
        return None
    c = h[i]["close"]
    closes = [x["close"] for x in h[i - 59:i + 1]]
    ma20, ma50 = mean(closes[-20:]), mean(closes[-50:])
    return {"val": mean(x["val"] for x in h[i - 19:i + 1]) / 10 / 1e9,
            "chg": (c / h[i]["py"] - 1) * 100,
            "trend": c > ma50 and ma20 > ma50,
            "r20": (c / h[i - 20]["close"] - 1) * 100,
            "r60": (c / h[i - 60]["close"] - 1) * 100,
            "ma20": ma20, "ma50": ma50}


def passes_long(f, p):
    return (f["val"] >= p["val"] and (f["trend"] or not p["trend"])
            and f["r60"] >= p["r60"] and f["r20"] <= p["r20max"])


def bad_prefix(h):
    """روزهای غیرعادی (افزایش سرمایه، تقسیم سود و ...) را علامت می‌زند."""
    pre = [0]
    for k, x in enumerate(h):
        bad = (abs(x["close"] / x["py"] - 1) > 0.12
               or (k > 0 and abs(x["open"] / h[k - 1]["close"] - 1) > 0.10))
        pre.append(pre[-1] + (1 if bad else 0))
    return pre


def outcome_long(h, e, entry_p, hold, mode, pct, allow_open=False):
    """معامله‌ی میان‌مدت: ورود در روز e با قیمت entry_p.
    mode="fixed": حد ضرر ثابت | "trail": حد ضرر شناور زیر بالاترین قیمت پایانی.
    خروجی: (درصد سود بعد از کارمزد، روز نگهداری، تمام‌شده؟، حد ضرر فعلی) یا None."""
    n = len(h)
    last = e + hold
    stop = entry_p * (1 - pct / 100)
    top = entry_p
    for d in range(e + 1, min(last, n - 1) + 1):
        o, lo = h[d]["open"], h[d]["low"]
        if o <= stop:
            return (o / entry_p - 1) * 100 - COST_PCT, d - e, True, stop
        if lo <= stop:
            return (stop / entry_p - 1) * 100 - COST_PCT, d - e, True, stop
        if mode == "trail":
            top = max(top, h[d]["close"])
            stop = max(stop, top * (1 - pct / 100))
    if last <= n - 1:
        return (h[last]["close"] / entry_p - 1) * 100 - COST_PCT, hold, True, stop
    if allow_open:
        return (h[n - 1]["close"] / entry_p - 1) * 100, n - 1 - e, False, stop
    return None


# ======================= ۱) تحلیل پورتفو =======================
def run_portfolio(hist, market, clients, breadth):
    my = load_my_stocks()
    d, b = regime_status(breadth)
    weak = b is not None and b < 40
    print(f"\n===== تحلیل پورتفوی من - {datetime.now():%Y-%m-%d %H:%M} =====")
    if not my:
        print("لیست خالی است. گزینه‌ی ۴ را بزنید و نام سهم‌ها را با فاصله بنویسید.")
        return
    if d:
        print_data_date(d)
    if b is not None:
        print(f"وضعیت کل بازار: {b:.0f}٪ نمادها بالای میانگین ۱۰ روزه "
              + ("⛔ ضعیف" if b < REGIME_MIN_BREADTH else "✅"))
    summary = []
    rows_all = stock_rows(market)
    secs = sector_groups(rows_all)
    wk = weekly_returns(hist) if hist else {}
    holding_groups = {}
    for name, buy in my.items():
        key = fa(name)
        print("\n" + "=" * 30)
        r = market.get(key)
        if not r:
            print(f"{key}: در بازار پیدا نشد.")
            sug = difflib.get_close_matches(key, list(market), n=3, cutoff=0.6)
            if sug:
                print("  شاید منظورتان این بود:", "، ".join(sug))
            continue
        h = hist.get(key)
        if not h:
            text = fetch_hist(r[0])
            h = parse_history(text) if text else []
        price, py = fnum(r[7]), fnum(r[13])
        if price <= 0 or py <= 0 or len(h) < 25:
            print(f"{key}: داده‌ی کافی برای تحلیل نیست (نماد جدید یا بسته).")
            continue
        change = (price / py - 1) * 100
        closes = [x["close"] for x in h]
        n = len(h)
        ma20 = mean(closes[-20:])
        ma50 = mean(closes[-50:]) if n >= 50 else None
        top40 = max(closes[-40:])
        stop = top40 * (1 - TRAIL_PCT / 100)
        if buy:
            stop = max(stop, buy * (1 - FIXED_STOP_PCT / 100))
        highs = [x["high"] for x in h]
        lows = [x["low"] for x in h]
        resistance, support = swings(highs, lows, n - 1, price)
        ci = client_info(clients.get(r[0]))
        avgv = mean(x["vol"] for x in h[-21:-1]) or 1
        red = closes[-1] < closes[-2]
        pnl = (price / buy - 1) * 100 if buy else None
        ext = (price / ma50 - 1) * 100 if ma50 else 0

        s, bad, good = 0, [], []
        if price <= stop:
            s += 5; bad.append("قیمت به حد ضرر پیشنهادی رسیده یا از آن پایین‌تر است")
        broken = bool(ma50) and price < ma50 * 0.97 and ma20 < ma50
        if broken:
            s += 4; bad.append("روند میان‌مدت شکسته (زیر میانگین ۵۰ روزه و ۲۰ روزه پایین‌تر)")
        elif ma50 and price < ma50:
            s += 2; bad.append("قیمت زیر میانگین ۵۰ روزه است")
        elif ma50:
            good.append("بالای میانگین ۵۰ روزه")
        if price < ma20:
            s += 1; bad.append("قیمت زیر میانگین ۲۰ روزه")
        if red and h[-1]["vol"] > 2 * avgv:
            s += 2; bad.append("حجم بالا در روز قرمز")
        if ci:
            if ci["legal_sell"] >= 50:
                s += 1; bad.append(f"فروش سنگین حقوقی ({ci['legal_sell']:.0f}٪ فروش امروز)")
            if ci["power"] < 0.8:
                s += 1; bad.append(f"قدرت خریدار ضعیف ({ci['power']:.2f})")
        if weak:
            s += 1; bad.append("کل بازار ضعیف شده")
        take = (pnl is not None and pnl >= TAKE_PROFIT_PCT) or ext >= EXTENDED_PCT

        if s >= 5:
            verdict, todo = "🔴 خروج", "امروز: بخش عمده یا کل سهم را بفروشید."
            kind = "exit"
        elif s >= 3:
            verdict = "🟡 احتیاط"
            todo = ("امروز: چیزی اضافه نکنید؛ حد ضرر را بالا ببرید و اگر ریسک‌پذیر نیستید "
                    "۳۰ تا ۵۰٪ را کم کنید.")
            kind = "caution"
        elif take:
            verdict = "🟢 نگه دارید + برداشت سود"
            todo = "امروز: ۳۰ تا ۵۰٪ از سهم را بفروشید و بقیه را با حد ضرر شناور نگه دارید."
            kind = "take"
        else:
            verdict, todo = "🟢 نگه دارید", "امروز: نگه دارید و فقط حد ضرر را به‌روز کنید."
            kind = "hold"
        summary.append((key, kind))
        grp = group_info(key, market, secs, wk)
        if grp:
            holding_groups.setdefault(grp["code"], []).append((key, grp["label"]))

        print(f"{key} | قیمت {price:.0f} | امروز {change:+.2f}٪")
        print(verdict, f"(امتیاز خطر {s})")
        if pnl is not None:
            print(f"  سود/ضرر شما: {pnl:+.1f}٪")
        if ma50:
            print(f"  میانگین ۲۰ روزه {ma20:.0f} | ۵۰ روزه {ma50:.0f}")
        print(f"  حد ضرر پیشنهادی: {stop:.0f} ({(stop / price - 1) * 100:.1f}٪ از قیمت فعلی)")
        print(f"  حمایت {support:.0f}" + (f" | مقاومت {resistance:.0f}" if resistance
                                         else " | مقاومتی بالاتر نیست"))
        if grp:
            print(group_line(grp))
            if abs(grp["day"]) >= 1.5 and change * grp["day"] > 0:
                print("  ℹ حرکت امروز بیشتر مال کل گروه است، نه فقط این سهم.")
        for x in bad:
            print("  ⚠", x)
        for x in good:
            print("  ✓", x)
        if take and kind in ("hold", "take") and ext >= EXTENDED_PCT:
            print(f"  ⚠ قیمت {ext:.0f}٪ بالای میانگین ۵۰ روزه است؛ اضافه نکنید.")
        print("  " + todo)

    if summary:
        cnt = {k: sum(1 for _, x in summary if x == k) for k in ("exit", "caution", "take", "hold")}
        print("\n" + "=" * 30)
        print(f"خلاصه: خروج {cnt['exit']} | احتیاط {cnt['caution']} | "
              f"برداشت سود {cnt['take']} | نگه‌داری {cnt['hold']}")
        urgent = [k for k, x in summary if x in ("exit", "caution")]
        if urgent:
            print("نیازمند توجه امروز:", "، ".join(urgent))
        for code, items in holding_groups.items():
            if len(items) >= 2 and len(items) / len(summary) >= 0.5:
                print(f"⚠ تمرکز گروهی: {len(items)} از {len(summary)} سهم شما در یک گروه‌اند "
                      f"({'، '.join(k for k, _ in items)}). این‌ها معمولاً با هم بالا و پایین می‌روند.")
    print("\nاین تحلیل بر پایه‌ی قاعده‌ی روند است، نه پیش‌بینی. کدال و خبر را هم ببینید.")
    print("در صف فروش ممکن است حد ضرر اجرا نشود.")


# ======================= ۲) پیشنهاد خرید میان‌مدت =======================
def run_pick(hist, market, clients, breadth, series):
    strong = print_regime(breadth)
    latest = max(breadth)
    print_data_date(latest)
    hot, hot_msg = market_hot(series, breadth)
    print(f"\n===== پیشنهاد خرید میان‌مدت - {datetime.now():%Y-%m-%d %H:%M} =====")
    if hot:
        print("🔥", hot_msg)
    if not strong:
        print("چون بازار ضعیف است، امروز سهمی پیشنهاد نمی‌شود.")
        live_summary(market)
        return
    rows = stock_rows(market)
    pes, secs = pe_table(rows), sector_groups(rows)
    wk_all = weekly_returns(hist)
    cands = []
    for sym, h in hist.items():
        if h[-1]["date"] != latest:
            continue
        f = features_long(h, len(h) - 1)
        if not f or not passes_long(f, LONG) or f["chg"] >= 2.7:
            continue
        price = h[-1]["close"]
        ext50 = (price / f["ma50"] - 1) * 100
        r = market.get(sym)
        ci = client_info(clients.get(r[0])) if r else None
        pe, pe_med = pe_for(sym, r, pes, secs)
        flags = []
        if ci:
            if ci["legal_sell"] >= 50:
                flags.append(f"فروش سنگین حقوقی: {ci['legal_sell']:.0f}٪ فروش امروز دست حقوقی‌هاست")
            if ci["power"] < 1:
                flags.append(f"قدرت خریدار حقیقی {ci['power']:.2f} (زیر ۱)")
        if f["r60"] > R60_FLAG:
            flags.append(f"۶۰ روز اخیر {f['r60']:.0f}٪ رشد کرده (خیلی کشیده)")
        elif f["r20"] > 15:
            flags.append(f"۲۰ روز اخیر {f['r20']:.0f}٪ رشد کرده (احتمال کشیدگی)")
        if ext50 > EXT50_FLAG:
            flags.append(f"قیمت {ext50:.0f}٪ بالای میانگین ۵۰ روزه است")
        if price < f["ma20"]:
            flags.append("قیمت زیر میانگین ۲۰ روزه است (ضعف کوتاه‌مدت)")
        if pe and pe_med and pe > PE_RATIO_FLAG * pe_med:
            flags.append(f"P/E تقریبی {pe:.1f} نسبت به میانه‌ی گروه ({pe_med:.1f}) گران است")
        cands.append((-len(flags), -ext50, sym, h, f, ci, flags, ext50, pe, pe_med))
    if not cands:
        print("امروز سهمی پیدا نشد که شرایط را داشته باشد. نخریدن هم یک تصمیم است.")
        live_summary(market)
        return
    # انتخاب: کمترین هشدار؛ بعد نزدیک‌ترین به میانگین ۵۰ روزه (حد ضرر منطقی‌تر)
    cands.sort(key=lambda x: (x[0], x[1]), reverse=True)
    _, _, sym, h, f, ci, flags, ext50, pe, pe_med = cands[0]
    price = h[-1]["close"]
    hold, mode, pct = LONG_EXIT
    stop0 = price * (1 - pct / 100)
    highs = [x["high"] for x in h]
    lows = [x["low"] for x in h]
    resistance, support = swings(highs, lows, len(h) - 1, price)

    print("\n" + "=" * 30)
    print("📌 خلاصه")
    print(f"  نماد: {sym}")
    print(f"  خرید: جلسه‌ی بعد با اولین قیمت (حدود {price:.0f})")
    print(f"  حد ضرر اولیه: {stop0:.0f} (−{pct:g}٪) و هر روز بالا می‌رود")
    print(f"  نگهداری: تا {hold} روز؛ حد سود ثابت ندارد")
    print("  هشدار سهم: " + (f"{len(flags)} مورد 🚩" if flags else "ندارد"))
    print("  هشدار بازار: " + ("داغ 🔥" if hot else "ندارد"))
    print("=" * 30)
    print("⚠ در بک‌تست این فیلترها از «خرید هر سهم بدون فیلتر» بهتر نبودند؛ این فقط")
    print("  یک ایده برای بررسی است، نه برتری اثبات‌شده.")
    print(f"\n⭐ {sym} | قیمت {price:.0f} | امروز {f['chg']:+.1f}٪")
    print(f"  بازده ۲۰ روز {f['r20']:+.0f}٪ | ۶۰ روز {f['r60']:+.0f}٪")
    print(f"  میانگین ۲۰ روزه {f['ma20']:.0f} | ۵۰ روزه {f['ma50']:.0f} "
          f"(قیمت {ext50:+.0f}٪ نسبت به ۵۰ روزه)")
    print(f"  میانگین ارزش معاملات ۲۰ روز: {f['val']:.0f} میلیارد تومان")
    if pe:
        print(f"  P/E تقریبی {pe:.1f}" + (f" | میانه‌ی گروه {pe_med:.1f}" if pe_med else ""))
    grp = group_info(sym, market, secs, wk_all)
    if grp:
        print(group_line(grp))
    print(f"  حمایت {support:.0f}" + (f" | مقاومت {resistance:.0f}" if resistance
                                     else " | مقاومتی بالاتر نیست"))
    if flags:
        print("\n  🚩 هشدارهای سهم (در بک‌تست نیستند):")
        for x in flags:
            print("   ⚠", x)
    print("\n  برنامه‌ی معامله:")
    print("   • جلسه‌ی بعد با اولین قیمت بخرید")
    print(f"   • حد ضرر اولیه {stop0:.0f}؛ بعد هر روز حد ضرر را {pct:g}٪ زیر بالاترین")
    print("     قیمت پایانی از زمان خرید بگذارید (حد ضرر شناور)")
    print(f"   • اگر حد ضرر فعال نشد، حداکثر بعد از {hold} روز بفروشید")
    if CAPITAL_TOMAN > 0:
        max_loss = CAPITAL_TOMAN * RISK_PER_TRADE_PCT / 100
        risk_toman = price * pct / 100 / 10
        shares = int(max_loss / risk_toman)
        amount = shares * price / 10
        if amount > CAPITAL_TOMAN:
            shares = int(CAPITAL_TOMAN * 10 / price)
            amount = shares * price / 10
        print(f"   • حجم پیشنهادی: {shares:,} سهم (حدود {amount:,.0f} تومان)")
    if ci:
        print(f"\n  (اطلاعات، تست‌نشده) قدرت خریدار {ci['power']:.2f} | "
              f"حقوقی: {ci['legal_buy']:.0f}٪ از خرید، {ci['legal_sell']:.0f}٪ از فروش")
    if len(cands) > 1:
        print("\n  دیگر نمادهای رد‌شده:", "، ".join(c[2] for c in cands[1:4]))
    print("\n  چک‌لیست دستی قبل از خرید (برنامه این‌ها را نمی‌بیند):")
    print("   ۱) کدال: مجمع/تقسیم سود نزدیک؟ افزایش سرمایه؟ گزارش ماهانه؟ توقف نماد؟")
    print("   ۲) صف خرید/فروش و حجم سفارش‌ها")
    print("   ۳) اخبار شرکت و صنعت این هفته")
    log_pick(latest, sym, price, len(flags))
    live_summary(market)


# ======================= ۵) دیده‌بان بازار =======================
def run_watch(hist, market, clients, breadth, series):
    d, b = regime_status(breadth)
    print(f"\n===== دیده‌بان بازار - {datetime.now():%Y-%m-%d %H:%M} =====")
    if d:
        print_data_date(d)
    rows = stock_rows(market)

    print("\n۱) روند بازار (شاخص هم‌وزن؛ محاسبه‌ی خودمان از نمادهای پرمعامله)")
    if len(series) > 21:
        last5 = []
        for k in range(len(series) - 5, len(series)):
            dd = series[k][0]
            last5.append(f"{dd[4:6]}/{dd[6:]} {(series[k][1] / series[k - 1][1] - 1) * 100:+.1f}٪")
        print("  ۵ جلسه‌ی اخیر:", " | ".join(last5))
        print(f"  بازده ۵ جلسه {period_return(series, 5):+.1f}٪ | ۱۰ جلسه "
              f"{period_return(series, 10):+.1f}٪ | ۲۰ جلسه {period_return(series, 20):+.1f}٪")
    if b is not None:
        ds = sorted(breadth)
        b5 = breadth.get(ds[-6]) if len(ds) > 6 else None
        print(f"  گستردگی: {b:.0f}٪ نمادها بالای میانگین ۱۰ روزه"
              + (f" (۵ جلسه قبل: {b5:.0f}٪)" if b5 is not None else ""))
    hot, hot_msg = market_hot(series, breadth)
    if hot:
        print("  🔥", hot_msg)

    up = down = flat = lim_up = lim_dn = 0
    tot_val = real_net = buy_legal = buy_all = sell_legal = sell_all = 0.0
    flows = []
    for r in rows:
        pl, py, tv = fnum(r[7]), fnum(r[13]), fnum(r[10])
        if pl <= 0 or py <= 0 or tv <= 0:
            continue
        ch = pl / py - 1
        if ch > 0.0005:
            up += 1
        elif ch < -0.0005:
            down += 1
        else:
            flat += 1
        if ch >= 0.027:
            lim_up += 1
        if ch <= -0.027:
            lim_dn += 1
        tot_val += tv
        c = clients.get(r[0])
        if c:
            bi, bn, si, sn = fnum(c[3]), fnum(c[4]), fnum(c[7]), fnum(c[8])
            net = (bi - si) * pl
            real_net += net
            buy_legal += bn * pl
            buy_all += (bi + bn) * pl
            sell_legal += sn * pl
            sell_all += (si + sn) * pl
            flows.append((net, fa(r[2])))
    print("\n۲) آخرین جلسه (همه‌ی سهام)")
    print(f"  مثبت {up} | منفی {down} | بدون تغییر {flat}")
    print(f"  رشد ۲.۷٪ یا بیشتر (نزدیک سقف/صف خرید احتمالی) {lim_up} | افت ۲.۷٪ یا بیشتر {lim_dn}")
    print(f"  ارزش معاملات سهام: {tot_val / 1e13:.1f} همت")
    print(f"  پول حقیقی خالص: {real_net / 1e13:+.1f} همت ({'ورود' if real_net > 0 else 'خروج'})")
    if buy_all and sell_all:
        print(f"  حقوقی‌ها {buy_legal / buy_all * 100:.0f}٪ از خرید و "
              f"{sell_legal / sell_all * 100:.0f}٪ از فروش را دارند")

    wk = weekly_returns(hist)
    secs = sector_groups(rows)
    if secs and wk:
        grp = []
        for code, members in secs.items():
            rets = [wk[fa(x[2])] for x in members if fa(x[2]) in wk]
            if len(rets) < 3:
                continue
            big = sorted(members, key=lambda x: fnum(x[10]), reverse=True)[:3]
            net = sum((fnum(clients[x[0]][3]) - fnum(clients[x[0]][7])) * fnum(x[7])
                      for x in members if x[0] in clients)
            grp.append((mean(rets), net, "، ".join(fa(x[2]) for x in big)))
        grp.sort(reverse=True)
        if len(grp) >= 6:
            print("\n۳) گروه‌ها (با نام چند سهم بزرگ هر گروه؛ بازده ۵ جلسه)")
            print("  قوی‌ترین:")
            for ret, net, label in grp[:5]:
                print(f"   {ret:+.1f}٪ | {label} | پول حقیقی {net / 1e13:+.2f} همت")
            print("  ضعیف‌ترین:")
            for ret, net, label in grp[-3:][::-1]:
                print(f"   {ret:+.1f}٪ | {label} | پول حقیقی {net / 1e13:+.2f} همت")

    if wk:
        order = sorted(wk.items(), key=lambda x: x[1], reverse=True)
        print("\n۴) نمادها (۵ جلسه‌ی اخیر، پرمعامله‌ها)")
        print("  بیشترین رشد:", " | ".join(f"{k} {v:+.0f}٪" for k, v in order[:8]))
        print("  بیشترین افت:", " | ".join(f"{k} {v:+.0f}٪" for k, v in order[-5:][::-1]))
    if flows:
        flows.sort(reverse=True)
        print("  بیشترین ورود پول حقیقی امروز:",
              " | ".join(f"{n} {v / 1e10:+.0f}" for v, n in flows[:5]), "(میلیارد تومان)")
        print("  بیشترین خروج پول حقیقی امروز:",
              " | ".join(f"{n} {v / 1e10:+.0f}" for v, n in flows[-5:][::-1]), "(میلیارد تومان)")
    surge = []
    near_high = 0
    for sym, h in hist.items():
        avgv = mean(x["vol"] for x in h[-21:-1])
        if avgv > 0 and h[-1]["vol"] / avgv >= 3 and h[-1]["close"] > h[-1]["py"]:
            surge.append((h[-1]["vol"] / avgv, sym))
        if len(h) >= 120 and h[-1]["close"] >= max(x["close"] for x in h[-250:]) * 0.995:
            near_high += 1
    if surge:
        surge.sort(reverse=True)
        print("  جهش حجم همراه با رشد:", " | ".join(f"{n} {v:.1f}×" for v, n in surge[:5]))
    if hist:
        print(f"  نزدیک سقف یک‌ساله: {near_high} از {len(hist)} نماد پرمعامله")

    alerts = []
    if hot:
        alerts.append("بازار داغ است؛ سقف‌های تاریخی و صف‌های گسترده معمولاً اشتیاق شدید را نشان می‌دهند.")
    if len(series) > 1 and series[-1][1] > series[-2][1] and real_net < 0:
        alerts.append("شاخص مثبت بود ولی پول حقیقی خالص خارج شد (احتمال فروش نهادی).")
    if lim_up > 300:
        alerts.append(f"{lim_up} نماد با رشد نزدیک سقف مجاز بسته شدند؛ خرید در چنین روزی سخت است.")
    if lim_dn > 50:
        alerts.append(f"{lim_dn} نماد با افت نزدیک کف مجاز بسته شدند؛ فشار فروش گسترده.")
    if alerts:
        print("\n۵) هشدارها")
        for x in alerts:
            print("  ⚠", x)
    print("\nخبر و رویداد: برنامه نمی‌تواند خبر بخواند. برای خلاصه‌ی اخبار هفته، کدال و رویدادها")
    print("(مجامع، افزایش سرمایه، عرضه اولیه) از Claude در چت بخواهید.")
    print("این اعداد توصیفی‌اند و پیش‌بینی نیستند.")


# ======================= آزمون زنده =======================
def log_pick(date, sym, price, n_flags):
    if not after_close():
        print("(در دفتر آزمون زنده ثبت نشد: بازار هنوز باز است؛ بعد از ۱۲:۴۵ اجرا کنید.)")
        return
    hold, mode, pct = LONG_EXIT
    try:
        exists = os.path.exists(PICKS_LOG)
        if exists:
            with open(PICKS_LOG, encoding="utf-8") as f:
                if any(r["date"] == date for r in csv.DictReader(f)):
                    print("(پیشنهاد امروز قبلاً در دفتر آزمون زنده ثبت شده است.)")
                    return
        with open(PICKS_LOG, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(["date", "sym", "price", "hold", "mode", "pct", "flags"])
            w.writerow([date, sym, round(price), hold, mode, pct, n_flags])
        print("✅ این پیشنهاد در دفتر آزمون زنده ثبت شد.")
    except Exception:
        pass


def live_summary(market):
    """نتیجه‌ی واقعی پیشنهادهای قبلی (باز یا بسته)."""
    if not os.path.exists(PICKS_LOG):
        return
    try:
        with open(PICKS_LOG, encoding="utf-8") as f:
            picks = list(csv.DictReader(f))
    except Exception:
        return
    if not picks:
        return
    cache = load_cache()
    done, openp, skipped = [], [], []
    for p in picks:
        sym, hold = p["sym"], int(p["hold"])
        mode, pct, ref = p["mode"], float(p["pct"]), fnum(p["price"])
        r = market.get(sym)
        res = None
        for attempt in (0, 1):
            h = cache.get(sym, {}).get("h") or []
            if attempt == 1:
                if not r:
                    break
                text = fetch_hist(r[0])
                h = parse_history(text) if text else []
                time.sleep(0.5)
            e = next((k for k, x in enumerate(h) if x["date"] > p["date"]), None)
            if e is None:
                continue
            entry_p = h[e]["open"]
            if ref and entry_p >= ref * 1.028:
                res = ("gap", entry_p)
                break
            o = outcome_long(h, e, entry_p, hold, mode, pct, allow_open=True)
            if o and o[2]:
                res = ("done", entry_p, o)
                break
            if o:
                res = ("open", entry_p, o)
                if attempt == 1:
                    break
        if not res:
            continue
        if res[0] == "gap":
            skipped.append(p)
        elif res[0] == "done":
            done.append((p, res[1], res[2]))
        else:
            openp.append((p, res[1], res[2]))
    print(f"\n----- آزمون زنده ({len(picks)} پیشنهاد ثبت‌شده) -----")
    for p, ep, o in done:
        print(f"  {p['date']} {p['sym']} | بسته‌شده {o[0]:+.1f}٪ در {o[1]} روز"
              + (" 🚩" if int(p["flags"]) > 0 else ""))
    for p, ep, o in openp:
        print(f"  {p['date']} {p['sym']} | باز: {o[0]:+.1f}٪ تا الان ({o[1]} روز) | حد ضرر فعلی {o[3]:.0f}")
    for p in skipped:
        print(f"  {p['date']} {p['sym']} | روز بعد با گپ به سقف باز شد؛ خرید ممکن نبود")
    if done:
        rets = [o[0] for _, _, o in done]
        print(f"  جمع بسته‌شده‌ها: {len(done)} معامله | میانگین {mean(rets):+.1f}٪ | "
              f"وین‌ریت {sum(1 for x in rets if x > 0) / len(rets) * 100:.0f}٪")
    if len(done) < 30:
        print("  ⚠ هنوز کمتر از ۳۰ معامله‌ی بسته‌شده؛ این عددها را جدی نگیرید.")


# ======================= ۳) بک‌تست میان‌مدت =======================
def stats_long(items):
    """items: لیست (درصد سود، روز نگهداری)"""
    n = len(items)
    if n == 0:
        return None
    rets = [x[0] for x in items]
    wins = [r for r in rets if r > 0]
    gl = abs(sum(r for r in rets if r <= 0))
    return {"n": n, "wr": len(wins) / n * 100, "avg": mean(rets),
            "med": statistics.median(rets),
            "pf": (sum(wins) / gl) if gl > 0 else 99.0, "worst": min(rets),
            "days": mean(x[1] for x in items)}


def fmt_long(s):
    if not s:
        return "بدون معامله"
    return (f"n={s['n']} | وین‌ریت {s['wr']:.0f}٪ | میانگین {s['avg']:+.1f}٪ | "
            f"میانه {s['med']:+.1f}٪ | PF {s['pf']:.2f} | بدترین {s['worst']:.0f}٪ | "
            f"نگهداری {s['days']:.0f} روز")


def build_rows_long(hist, breadth, sector_of=None, strong=None):
    rows, max_hold = [], max(x[0] for x in EXITS)
    for sym, h in hist.items():
        n = len(h)
        if n < 100:
            continue
        pre = bad_prefix(h)
        for i in range(60, n - 2, STEP):
            if pre[min(n, i + max_hold + 2)] - pre[i - 60] > 0:
                continue
            f = features_long(h, i)
            if not f:
                continue
            e, entry_p = i + 1, h[i + 1]["open"]
            if entry_p >= h[i]["close"] * 1.028:
                continue
            outs = {}
            for k, (hold, mode, pct) in enumerate(EXITS):
                o = outcome_long(h, e, entry_p, hold, mode, pct)
                outs[k] = (o[0], o[1]) if o else None
            if all(v is None for v in outs.values()):
                continue
            f["date"], f["sym"], f["out"] = h[i]["date"], sym, outs
            f["breadth"] = breadth.get(h[i]["date"])
            if sector_of and strong is not None and sector_of.get(sym) is not None \
                    and h[i]["date"] in strong:
                f["grp_strong"] = sector_of[sym] in strong[h[i]["date"]]
            else:
                f["grp_strong"] = None
            rows.append(f)
    return rows


def passes_row(r, p):
    return passes_long(r, p) and (p["regime"] == 0 or
                                  (r["breadth"] is not None and r["breadth"] >= p["regime"]))


def desc_long(p):
    return (f"ارزش≥{p['val']}م.ت | روند={'بله' if p['trend'] else 'خیر'} | "
            f"بازده۶۰روز≥{p['r60']}٪ | بازده۲۰روز≤{p['r20max']}٪ | "
            f"بازار≥{p['regime']}٪")


def run_backtest(hist, breadth, market):
    print("\nساخت داده‌ی بک‌تست (ممکن است ۱ تا ۲ دقیقه طول بکشد) ...")
    secs = sector_groups(stock_rows(market))
    sector_of = ({fa(x[2]): x[18].strip() for g in secs.values() for x in g} if secs else None)
    strong = group_strength(hist, sector_of) if sector_of else None
    rows = build_rows_long(hist, breadth, sector_of, strong)
    print("تعداد نمونه (نماد-روز):", len(rows))
    if len(rows) < 800:
        print("نمونه کم است؛ نتیجه قابل اتکا نیست.")
        return
    dates = sorted({r["date"] for r in rows})
    split = dates[int(len(dates) * TRAIN_FRAC)]
    print(f"بازه: {dates[0]} تا {dates[-1]} | مرز آموزش/تست: {split}")
    cur = {"val": LONG["val"], "trend": LONG["trend"], "r60": LONG["r60"],
           "r20max": LONG["r20max"], "regime": REGIME_MIN_BREADTH}
    grid = list(itertools.product([30, 80], [False, True], [-100, 0, 15], [99, 25], [0, 50, 60]))
    for k, (hold, mode, pct) in enumerate(EXITS):
        print("\n" + "=" * 34)
        print(f"نگهداری تا {hold} روز | حد ضرر {'شناور' if mode == 'trail' else 'ثابت'} "
              f"{pct:g}٪ | کارمزد {COST_PCT}٪")
        rk = [r for r in rows if r["out"].get(k) is not None]
        tr_all = [r["out"][k] for r in rk if r["date"] < split]
        te_all = [r["out"][k] for r in rk if r["date"] >= split]
        print("پایه (خرید هر سهم، بدون فیلتر):")
        print("  آموزش:", fmt_long(stats_long(tr_all)))
        base_te = stats_long(te_all)
        print("  تست  :", fmt_long(base_te))
        p = dict(cur)
        tr = [r["out"][k] for r in rk if r["date"] < split and passes_row(r, p)]
        te = [r["out"][k] for r in rk if r["date"] >= split and passes_row(r, p)]
        print("تنظیم فعلی برنامه:", desc_long(p))
        print("  آموزش:", fmt_long(stats_long(tr)))
        print("  تست  :", fmt_long(stats_long(te)))
        results = []
        for val, trend, r60, r20m, reg in grid:
            p = {"val": val, "trend": trend, "r60": r60, "r20max": r20m, "regime": reg}
            tr = [r["out"][k] for r in rk if r["date"] < split and passes_row(r, p)]
            if len(tr) < MIN_TRAIN:
                continue
            te = [r["out"][k] for r in rk if r["date"] >= split and passes_row(r, p)]
            results.append((stats_long(tr), stats_long(te), p))
        results.sort(key=lambda x: x[0]["avg"], reverse=True)
        if not results:
            print("هیچ ترکیبی به حداقل تعداد معامله نرسید.")
            continue
        print("\nبهترین ترکیب‌ها بر اساس بخش آموزش:")
        for j, (s_tr, s_te, p) in enumerate(results[:3], 1):
            ok = (s_tr["avg"] > 0 and s_te and s_te["n"] >= MIN_TEST and s_te["avg"] > 0
                  and base_te and s_te["avg"] > base_te["avg"])
            print(f"\n#{j} {'✅ در تست هم از پایه بهتر' if ok else '⚠ در تست از پایه بهتر نبود'}")
            print("  " + desc_long(p))
            print("  آموزش:", fmt_long(s_tr))
            print("  تست  :", fmt_long(s_te))
    print("\n" + "=" * 34)
    print("اثر داغی بازار (خرید بدون فیلتر؛ بر اساس درصد نمادهای بالای میانگین ۱۰ روزه)")
    buckets = [("زیر ۴۰٪", 0, 40), ("۴۰ تا ۶۰٪", 40, 60), ("۶۰ تا ۸۰٪", 60, 80), ("۸۰٪ و بالاتر", 80, 101)]

    def short(items):
        st = stats_long(items)
        return "بدون نمونه" if not st else f"n={st['n']} میانگین {st['avg']:+.1f}٪ وین‌ریت {st['wr']:.0f}٪"

    for k, (hold, mode, pct) in enumerate(EXITS):
        print(f"\n نگهداری تا {hold} روز | حد ضرر {'شناور' if mode == 'trail' else 'ثابت'} {pct:g}٪")
        for label, lo, hi in buckets:
            sel = [r for r in rows if r["out"].get(k) is not None
                   and r["breadth"] is not None and lo <= r["breadth"] < hi]
            print(f"  بازار {label}: آموزش {short([r['out'][k] for r in sel if r['date'] < split])}"
                  f" | تست {short([r['out'][k] for r in sel if r['date'] >= split])}")
    print("اگر نتیجه‌ی آموزش و تست یک جهت نداشتند، از آن نتیجه‌ای نگیرید.")

    print("\n" + "=" * 34)
    print("اثر قدرت گروه (خرید بدون فیلتر؛ گروه «قوی» = ثلث بالای بازده ۵ جلسه‌ی اخیر)")
    print("قاعده از قبل ثابت شده و تنظیم نشده؛ فقط یک بار آزمایش می‌شود.")
    if not any(r.get("grp_strong") is not None for r in rows):
        print("داده‌ی گروه‌بندی معتبر نبود؛ این آزمون انجام نشد.")
    else:
        wins = 0
        for k, (hold, mode, pct) in enumerate(EXITS):
            print(f"\n نگهداری تا {hold} روز | حد ضرر {'شناور' if mode == 'trail' else 'ثابت'} {pct:g}٪")
            res = {}
            for label, flag in (("گروه قوی", True), ("سایر گروه‌ها", False)):
                sel = [r for r in rows if r["out"].get(k) is not None and r.get("grp_strong") is flag]
                tr = [r["out"][k] for r in sel if r["date"] < split]
                te = [r["out"][k] for r in sel if r["date"] >= split]
                res[flag] = (stats_long(tr), stats_long(te))
                print(f"  {label}: آموزش {short(tr)} | تست {short(te)}")
            ok = all(res[True][j] and res[False][j] and res[True][j]["avg"] > res[False][j]["avg"]
                     for j in (0, 1))
            wins += 1 if ok else 0
            print("  " + ("✅ هم در آموزش و هم در تست بهتر بود" if ok else "⚠ در هر دو بخش بهتر نبود"))
        print(f"\nنتیجه: در {wins} از {len(EXITS)} حالت، قدرت گروه در هر دو بخش مزیت داشت.")
        print("فقط اگر در همه یا تقریباً همه‌ی حالت‌ها ✅ بود، ارزش جدی گرفتن دارد.")
    print("\nراهنما: فقط ترکیبی که در تست هم از «پایه» بهتر بود (✅) ارزش بررسی دارد؛ آن را در")
    print("LONG و REGIME_MIN_BREADTH بگذارید. تفاوت‌های کوچک را جدی نگیرید.")
    print("هشدار: داده‌ی محدود و شاید یک دوره‌ی صعودی؛ فقط نمادهای فعلی؛ بدون صف خرید/فروش.")
    print("در بازار صعودی تقریباً هر خریدی سود می‌دهد؛ مهم این است که فیلتر از «پایه» بهتر باشد.")


# ======================= ۴) لیست سهام من =======================
def save_my_stocks(stocks):
    try:
        with open(MY_STOCKS_FILE, "w", encoding="utf-8") as f:
            f.write("# هر خط یک نماد: نام نماد و (اختیاری) قیمت خرید. مثال: فولاد 3400\n")
            for k, v in stocks.items():
                f.write(f"{k} {v:g}\n" if v else f"{k}\n")
    except Exception as e:
        print("ذخیره‌ی لیست ناموفق بود:", str(e)[:80])


def load_my_stocks():
    if not os.path.exists(MY_STOCKS_FILE):
        stocks = {fa(k): v for k, v in MY_STOCKS.items()}
        save_my_stocks(stocks)
        return stocks
    stocks = {}
    try:
        with open(MY_STOCKS_FILE, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                price = None
                if len(parts) > 1:
                    t = parts[-1].translate(_DIGITS).replace(",", "")
                    if fnum(t) > 0:
                        price = fnum(t)
                        parts = parts[:-1]
                name = fa(" ".join(parts))
                if name:
                    stocks[name] = price
    except Exception:
        pass
    return stocks


def parse_names(line):
    """'فولاد 3400 فملی شپنا' -> اضافه: [(فولاد،3400)، (فملی،None)، (شپنا،None)]
    '-شپنا -فولاد' -> حذف: [شپنا، فولاد]"""
    adds, removes = [], []
    for tok in line.split():
        t = tok.translate(_DIGITS).replace(",", "")
        if tok.startswith("-") and len(tok) > 1:
            removes.append(fa(tok[1:]))
        elif t.replace(".", "", 1).isdigit() and adds:
            adds[-1] = (adds[-1][0], fnum(t))
        elif not t.replace(".", "", 1).isdigit():
            adds.append((fa(tok), None))
    return adds, removes


def manage_stocks():
    """خروجی True یعنی کاربر خواست همین حالا پورتفو تحلیل شود."""
    stocks = load_my_stocks()
    print("\nویرایش لیست سهام من")
    print("  اضافه: نام چند سهم را با فاصله بنویسید و Enter بزنید. مثال:  فولاد فملی شپنا")
    print("  قیمت خرید (اختیاری) را بعد از نام بنویسید. مثال:  فولاد 3400 فملی")
    print("  حذف: یک خط تیره قبل از نام. مثال:  -شپنا -فولاد")
    while True:
        print("\nلیست فعلی:", "، ".join(
            f"{k}" + (f" ({v:g})" if v else "") for k, v in stocks.items()) or "(خالی)")
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            return False
        cmd = line.strip().translate(_NUM)
        if cmd == "1":
            return True
        if cmd in ("2", ""):
            return False
        adds, removes = parse_names(line)
        added, updated, deleted, missing = [], [], [], []
        for name, price in adds:
            if name in stocks:
                if price:
                    stocks[name] = price
                updated.append(name)
            else:
                stocks[name] = price
                added.append(name)
        for name in removes:
            if name in stocks:
                del stocks[name]
                deleted.append(name)
            else:
                missing.append(name)
        save_my_stocks(stocks)
        if added:
            print("✅ اضافه شد:", "، ".join(added))
        if updated:
            print("به‌روز شد (قبلاً در لیست بود):", "، ".join(updated))
        if deleted:
            print("🗑 حذف شد:", "، ".join(deleted))
        if missing:
            print("در لیست نبود:", "، ".join(missing))
        print("۱) تحلیل پورتفو همین حالا   ۲) برگشت به منوی اصلی   (یا نام‌های بیشتر را بنویسید)")


# ======================= منو =======================
def run_mode(mode):
    if mode == "4":
        if not manage_stocks():
            return
        mode = "1"
    if mode == "1":
        data = load_data(want_survivors=False)
        if data:
            hist, market, clients, core_syms, pending = data
            hist_core = {k: v for k, v in hist.items() if k in core_syms}
        else:
            print("\nتاریخچه‌ی بازار کامل نشد؛ تحلیل بدون وضعیت کل بازار انجام می‌شود.")
            basic = load_basic()
            if not basic:
                return
            market, _, clients = basic
            hist, hist_core, pending = {}, {}, 0
        breadth = compute_breadth(hist_core) if hist_core else {}
        if pending:
            print(f"⚠ {pending} نماد هنوز بررسی نشده؛ وضعیت کل بازار تقریبی است.")
        run_portfolio(hist, market, clients, breadth)
        return
    data = load_data(want_survivors=(mode == "2"))
    if not data:
        return
    hist, market, clients, core_syms, pending = data
    hist_core = {k: v for k, v in hist.items() if k in core_syms}
    breadth = compute_breadth(hist_core)
    if not breadth:
        print("داده‌ی کافی برای وضعیت بازار نیست؛ چند دقیقه بعد دوباره اجرا کنید.")
        return
    if pending:
        print(f"⚠ {pending} نماد هنوز بررسی نشده؛ نتیجه کامل نیست. دوباره اجرا کنید تا ادامه یابد.")
    series = market_series(hist_core)
    if mode == "2":
        run_pick(hist, market, clients, breadth, series)
    elif mode == "3":
        run_backtest(hist_core, breadth, market)
    elif mode == "5":
        run_watch(hist_core, market, clients, breadth, series)


def main():
    if MODE != "menu":
        run_mode(MODE.translate(_NUM))
        return
    while True:
        print("\n" + "=" * 34)
        print("منوی اصلی")
        print("۱) تحلیل پورتفوی من (هر روز)")
        print("۲) پیشنهاد سهم برای خرید (میان‌مدت)")
        print("۳) بک‌تست میان‌مدت")
        print("۴) ویرایش لیست سهام من")
        print("۵) دیده‌بان بازار (تحلیل هفته)")
        print("۰) خروج از برنامه")
        try:
            choice = input("عدد را وارد کنید: ").strip().translate(_NUM)
        except (EOFError, KeyboardInterrupt):
            break
        if choice == "0":
            print("پایان.")
            break
        if choice not in ("1", "2", "3", "4", "5"):
            print("گزینه‌ی نامعتبر.")
            continue
        try:
            run_mode(choice)
        except KeyboardInterrupt:
            print("\nمتوقف شد.")
        except Exception:
            print("\nخطا رخ داد (عکس این پیام را بفرستید):")
            traceback.print_exc()
        try:
            input("\nبرای برگشت به منوی اصلی Enter بزنید ...")
        except (EOFError, KeyboardInterrupt):
            break


if __name__ == "__main__":
    main()
