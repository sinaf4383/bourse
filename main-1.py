# -*- coding: utf-8 -*-
"""
نسخه‌ی اندروید «بورس همه‌کاره».
یک سرور محلی کوچک (فقط روی خود گوشی) اجرا می‌شود و صفحه‌ی برنامه را داخل WebView نشان می‌دهد؛
منطق تحلیل همان bourse_all.py است. هیچ داده‌ای از گوشی بیرون نمی‌رود، جز درخواست به TSETMC.
"""
import json
import os
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
BASE = os.environ.get("ANDROID_PRIVATE") or HERE
try:
    os.chdir(BASE)          # فایل‌های ذخیره‌شده (لیست سهام، حافظه، دفتر آزمون زنده) اینجا می‌مانند
except Exception:
    pass

import bourse_all as core  # noqa: E402

PORT = int(os.environ.get("BOURSE_PORT", "5000"))
LOCK = threading.Lock()
LINES = []
STATE = {"running": False}


class Tee:
    """هر چیزی که برنامه print می‌کند را خط‌به‌خط ذخیره می‌کند تا صفحه نشان دهد."""

    def __init__(self):
        self.buf = ""

    def write(self, s):
        if not s:
            return 0
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            with LOCK:
                LINES.append(line)
        return len(s)

    def flush(self):
        pass


def job(mode):
    old, tee = sys.stdout, Tee()
    sys.stdout = tee
    try:
        core.run_mode(mode)
    except Exception:
        traceback.print_exc(file=tee)
    finally:
        sys.stdout = old
        with LOCK:
            if tee.buf:
                LINES.append(tee.buf)
            STATE["running"] = False


def start_job(mode):
    if mode not in ("1", "2", "3", "5"):
        return {"ok": False, "msg": "گزینه‌ی نامعتبر"}
    with LOCK:
        if STATE["running"]:
            return {"ok": False, "msg": "یک کار در حال اجراست؛ صبر کنید."}
        STATE["running"] = True
        del LINES[:]
    threading.Thread(target=job, args=(mode,), daemon=True).start()
    return {"ok": True}


def stocks_payload(stocks, extra=None):
    out = {"stocks": [{"name": k, "price": v} for k, v in stocks.items()]}
    if extra:
        out.update(extra)
    return out


def apply_stocks(text):
    stocks = core.load_my_stocks()
    adds, removes = core.parse_names(text)
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
    core.save_my_stocks(stocks)
    return stocks_payload(stocks, {"added": added, "updated": updated,
                                   "deleted": deleted, "missing": missing})


HTML = """<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>بورس</title>
<style>
body{font-family:sans-serif;margin:0;background:#111;color:#eee}
header{padding:12px;background:#1f3b57;font-weight:bold;font-size:17px}
.btns{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:8px}
button{padding:13px 6px;font-size:15px;border:0;border-radius:8px;background:#2d6cdf;color:#fff}
button.alt{background:#46586b}
button:disabled{opacity:.45}
#status{padding:4px 10px;color:#9ab;font-size:13px}
#out{padding:8px 10px;font-size:14px;line-height:1.75}
#out div{white-space:pre-wrap;min-height:1em}
.box{padding:10px;background:#1b1b1b;margin:8px;border-radius:8px}
input{width:100%;box-sizing:border-box;padding:11px;font-size:16px;border-radius:6px;
border:1px solid #555;background:#222;color:#fff;margin:6px 0}
.hint{font-size:12px;color:#9ab;margin-bottom:6px}
</style></head><body>
<header>بورس همه‌کاره</header>
<div class="btns">
<button id="b1" onclick="run('1')">تحلیل پورتفوی من</button>
<button id="b2" onclick="run('2')">پیشنهاد خرید</button>
<button id="b5" onclick="run('5')">دیده‌بان بازار</button>
<button id="b3" onclick="run('3')">بک‌تست</button>
<button class="alt" style="grid-column:1/3" onclick="toggleStocks()">لیست سهام من</button>
</div>
<div class="box" id="stocksBox" style="display:none">
<div id="stockList"></div>
<input id="stockText" placeholder="نام سهم‌ها با فاصله؛ مثلاً: فولاد فملی شپنا">
<div class="hint">قیمت خرید (اختیاری): فولاد 3400 &nbsp;|&nbsp; حذف: -شپنا</div>
<div class="btns" style="padding:0">
<button onclick="saveStocks(false)">ثبت</button>
<button onclick="saveStocks(true)">ثبت و تحلیل پورتفو</button></div>
<div id="stockMsg" class="hint"></div>
</div>
<div id="status"></div>
<div id="out"></div>
<script>
let pos=0;
function $(i){return document.getElementById(i)}
function busy(b){for(const i of ['b1','b2','b5','b3'])$(i).disabled=b}
function say(t){$('status').textContent=t}
async function run(mode){
  busy(true);$('out').innerHTML='';pos=0;say('در حال اجرا ... برنامه را نبندید');
  $('stocksBox').style.display='none';
  const r=await fetch('/api/run',{method:'POST',body:JSON.stringify({mode})});
  const j=await r.json();
  if(!j.ok){say(j.msg);busy(false);return}
  poll();
}
async function poll(){
  const r=await fetch('/api/out?since='+pos);const j=await r.json();
  const out=$('out');
  for(const l of j.lines){const d=document.createElement('div');d.dir='auto';d.textContent=l||'\\u00a0';out.appendChild(d)}
  pos=j.total;
  if(j.lines.length)window.scrollTo(0,document.body.scrollHeight);
  if(j.running)setTimeout(poll,800);else{busy(false);say('تمام شد')}
}
function showList(s){
  $('stockList').textContent='لیست فعلی: '+(s.length?s.map(x=>x.name+(x.price?' ('+x.price+')':'')).join('، '):'(خالی)');
}
async function toggleStocks(){
  const b=$('stocksBox');
  if(b.style.display==='none'){b.style.display='block';const j=await (await fetch('/api/stocks')).json();showList(j.stocks)}
  else b.style.display='none';
}
async function saveStocks(analyze){
  const text=$('stockText').value;
  const r=await fetch('/api/stocks',{method:'POST',body:JSON.stringify({text})});
  const j=await r.json();showList(j.stocks);
  const m=[];
  if(j.added&&j.added.length)m.push('اضافه شد: '+j.added.join('، '));
  if(j.updated&&j.updated.length)m.push('به‌روز شد: '+j.updated.join('، '));
  if(j.deleted&&j.deleted.length)m.push('حذف شد: '+j.deleted.join('، '));
  if(j.missing&&j.missing.length)m.push('در لیست نبود: '+j.missing.join('، '));
  $('stockMsg').textContent=m.join(' | ');$('stockText').value='';
  if(analyze)run('1');
}
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            return self._send(200, HTML, "text/html; charset=utf-8")
        if u.path == "/api/out":
            try:
                since = int(parse_qs(u.query).get("since", ["0"])[0])
            except Exception:
                since = 0
            with LOCK:
                return self._json({"lines": LINES[since:], "total": len(LINES),
                                   "running": STATE["running"]})
        if u.path == "/api/stocks":
            return self._json(stocks_payload(core.load_my_stocks()))
        self._json({}, 404)

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n) or b"{}") if n else {}
        except Exception:
            data = {}
        u = urlparse(self.path)
        if u.path == "/api/run":
            return self._json(start_job(str(data.get("mode", ""))))
        if u.path == "/api/stocks":
            return self._json(apply_stocks(str(data.get("text", ""))))
        self._json({}, 404)


def serve():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    srv.serve_forever()


if os.environ.get("BOURSE_NO_SERVE") != "1":
    serve()
