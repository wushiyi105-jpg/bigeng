"""Web UI:http.server 单文件,不依赖任何框架。"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import agent, llm
from .db import Database

PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>笔耕 · 这一句改不改</title>
<style>
:root{--bg:#faf7f2;--card:#fff;--ink:#2c2620;--dim:#7b7168;--accent:#b5651d;--line:#e8dfd3}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.7 "Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:880px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:26px;margin:0 0 6px}
.sub{color:var(--dim);margin:0 0 20px}
.badge{display:inline-block;padding:2px 10px;border-radius:99px;font-size:13px;margin-left:8px}
.tabs{display:flex;gap:8px;margin:18px 0}
.tab{padding:8px 16px;border:1px solid var(--line);background:var(--card);border-radius:8px;cursor:pointer}
.tab.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:16px}
label{display:block;font-size:14px;color:var(--dim);margin:10px 0 4px}
input,textarea,select{width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:8px;font:inherit;background:#fff}
textarea{min-height:160px;resize:vertical}
button{padding:9px 18px;border:0;border-radius:8px;background:var(--accent);color:#fff;font:inherit;cursor:pointer}
button:disabled{opacity:.55;cursor:wait}
.out{white-space:pre-wrap;font:14px/1.8 Consolas,"Microsoft YaHei",monospace;background:#fdfbf7;border:1px solid var(--line);border-radius:8px;padding:14px;margin-top:12px;min-height:40px}
.list div{padding:8px 0;border-bottom:1px dashed var(--line);display:flex;gap:12px;align-items:center}
.list div span{color:var(--dim);font-size:13px}
a{color:var(--accent);cursor:pointer;text-decoration:none}

h1{font-size:clamp(31px,5vw,39px);line-height:1.26}
.prod{display:block;font-size:11px;line-height:1.4;letter-spacing:.18em;font-weight:650;margin-bottom:8px;opacity:.72}
.lede,.sub{max-width:62ch;line-height:1.75}
.route{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;margin:0 0 20px;border:1px solid var(--line);background:var(--line)}
.route span{padding:11px 13px;background:var(--card);font-size:12px;line-height:1.5}
.route b{display:block;font-size:10px;letter-spacing:.1em;margin-bottom:3px;opacity:.66}
button{min-height:46px}
input,select{min-height:44px}
@media(max-width:680px){
  .wrap{padding:20px 16px 56px}
  .route{grid-template-columns:1fr}
  h1{font-size:30px!important}
  .row>div{min-width:100%!important}
  button{width:100%}
}

body{background:#f7f2e8;color:#1f2328;font-family:"Songti SC","SimSun",Georgia,serif}
.wrap{max-width:960px;position:relative}
.wrap::before{content:"";position:absolute;left:8px;top:0;bottom:0;width:1px;background:#d8b7b0}
header{padding:8px 0 20px;margin-bottom:20px;border-bottom:1px solid #cfc4b3}
header h1{font-size:38px;line-height:1.25}
header p{color:#6e675d;font-size:14px;font-family:"PingFang SC","Microsoft YaHei",sans-serif}
.card{background:#fffdf8;border:1px solid #d8d0c2;border-radius:2px;box-shadow:0 1px 0 #e9e1d4}
button{background:#2456a6;border-radius:2px;font-family:"PingFang SC","Microsoft YaHei",sans-serif;letter-spacing:.05em}
button:hover{background:#1d4789}
textarea,input,select{background:#fffefa;border-color:#d5caba;border-radius:2px}
textarea:focus,input:focus,select:focus{border-color:#2456a6;box-shadow:0 0 0 2px #d5e0f0}
.item{border-left:3px solid #2456a6}
h3{color:#2456a6;letter-spacing:.08em}


/* palette-normalized */
:root{--bg:#f7f2e8;--card:#fffdf8;--ink:#1f2328;--text:#1f2328;--dim:#6e675d;--line:#d8d0c2;--accent:#2456a6}

/* polish-batch1 */
button.ghost,button.secondary{background:transparent!important;color:#2456a6!important;border:1px solid #d8d0c2!important}

/* mobile-32 */

@media(max-width:760px){
  main{grid-template-columns:1fr!important}
  aside{border-right:0!important;border-bottom:1px solid #d8d0c2;width:auto!important}
  section{padding:16px!important}
  .row{flex-wrap:wrap!important}
  .row>div{min-width:100%!important}
  h1{font-size:30px!important}
  .route{grid-template-columns:1fr!important}
  button{min-height:48px}
  pre{overflow-x:auto}
}

/* mobile-height */
@media(max-width:760px){main{min-height:auto!important}aside{min-height:0!important}}
</style></head><body><div class="wrap">
<h1><span class="prod">笔耕</span>这一句，改还是不改 <span id="st" class="badge"></span></h1>
<p class="sub">给手里已有稿子的中文作者：锁住人名、术语、数字和直接引语，逐段看删改，点选采纳，随时退回保存版本。</p>
<div class="tabs">
  <div class="tab on" data-t="list">稿子</div>
  <div class="tab" data-t="new">新建</div>
  <div class="tab" data-t="run">改写</div>
</div>


  <div class="route" aria-label="任务步骤"><span><b>01</b>先锁事实</span><span><b>02</b>逐句看删改</span><span><b>03</b>导出干净稿</span></div>
<div class="card" id="p-list">
  <div class="list" id="drafts">加载中…</div>
</div>

<div class="card" id="p-new" style="display:none">
  <label>标题(留空自动起)</label><input id="nTitle" placeholder="例如:为什么我总在下午三点卡住">
  <label>正文</label><textarea id="nBody" placeholder="把草稿粘进来"></textarea>
  <div style="margin-top:12px"><button id="btnNew">建稿</button></div>
  <div class="out" id="newOut"></div>
</div>

<div class="card" id="p-run" style="display:none">
  <label>稿子</label><select id="rId"></select>
  <label>动作</label>
  <select id="rMode">
    <option value="polish">润色</option>
    <option value="rewrite">改写</option>
    <option value="expand">扩写</option>
    <option value="shrink">缩写</option>
    <option value="title">起标题</option>
  </select>
  <label>风格(仅改写)</label>
  <select id="rStyle"><option value="formal">正式</option><option value="oral">口语</option><option value="brief">简洁</option></select>
  <div style="margin-top:12px"><button id="btnRun">开始</button></div>
  <div class="out" id="runOut"></div>
</div>
</div>
<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s==null?'':s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function loading(btn,on){
  if(on){btn.dataset.label=btn.dataset.label||btn.textContent.trim();btn.disabled=true;btn.textContent='处理中…';}
  else{btn.disabled=false;btn.textContent=btn.dataset.label||btn.textContent;}
}
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
  document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===t));
  ['list','new','run'].forEach(k=>$('p-'+k).style.display = k===t.dataset.t?'block':'none');
});
async function api(path,body){
  const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});
  const j=await r.json();
  if(!r.ok) throw new Error(j.error||('HTTP '+r.status));
  return j;
}
async function loadDrafts(){
  const d=await api('/api/drafts');
  $('drafts').innerHTML = d.length? d.map(x=>`<div><b>${esc(x.title)}</b><span>${x.chars} 字</span><span>${esc(x.updated_at)}</span><a onclick="pick(${x.id})">选它</a></div>`).join('') : '<div>还没有稿子</div>';
  $('rId').innerHTML = d.map(x=>`<option value="${x.id}">[${x.id}] ${esc(x.title)}</option>`).join('');
}
window.pick=id=>{document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x.dataset.t==='run'));['list','new','run'].forEach(k=>$('p-'+k).style.display=k==='run'?'block':'none');$('rId').value=id;};
$('btnNew').onclick=async()=>{
  const btn=$('btnNew');loading(btn,true);
  try{const r=await api('/api/new',{title:$('nTitle').value,body:$('nBody').value});
    $('newOut').textContent=`已建稿 [${r.id}] ${r.title}  ${r.chars} 字`;await loadDrafts();}
  catch(e){$('newOut').textContent='❌ '+e.message;}finally{loading(btn,false);}
};
$('btnRun').onclick=async()=>{
  const btn=$('btnRun');loading(btn,true);
  try{const r=await api('/api/run',{id:+$('rId').value,mode:$('rMode').value,style:$('rStyle').value});
    let txt=(r.offline?'【离线模式】\\n':'')+(r.checks||[]).join('\\n')+'\\n\\n'+r.body;
    if(r.rejected) txt='! 校验没过,已保留原稿\\n'+ (r.checks||[]).join('\\n');
    if(r.saved && r.version_id) txt='已存为版本 v'+r.version_id+'\\n\\n'+r.body;
    $('runOut').textContent=txt;await loadDrafts();}
  catch(e){$('runOut').textContent='❌ '+e.message;}finally{loading(btn,false);}
};
(async()=>{try{const s=await api('/api/status');
  const b=$('st');b.textContent=s.mock?'离线模式':'模型模式';b.style.background=s.mock?'#f6e3d0':'#dff0e2';b.style.color=s.mock?'#8a4a12':'#245c31';
}catch(e){} await loadDrafts();})();
</script></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    db: Database
    cfg: dict
    force_mock: bool

    def log_message(self, fmt, *a):
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        raw = self.rfile.read(n)
        for enc in ("utf-8", "gbk"):
            try:
                return json.loads(raw.decode(enc))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        return {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/status":
            cfg = {**llm.default_config(), **self.cfg}
            self._json({"mock": self.force_mock or not cfg.get("api_key"), "model": cfg.get("model")})
            return
        if path == "/api/drafts":
            self._json(self.db.list_drafts())
            return
        if path == "/api/draft":
            q = parse_qs(urlparse(self.path).query)
            d = self.db.get_draft(q.get("id", ["0"])[0])
            if not d:
                self._json({"error": "稿子不存在"}, 404)
                return
            d["versions"] = self.db.list_versions(d["id"])
            self._json(d)
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self._read_json()
        except ValueError:
            self._json({"error": "请求体不是合法 JSON"}, 400)
            return
        if path == "/api/new":
            body = str(data.get("body", "")).strip()
            if not body:
                self._json({"error": "正文不能为空"}, 400)
                return
            from . import tools

            title = str(data.get("title", "")).strip()
            if not title:
                title = (tools.title_candidates(body) or ["未命名"])[0]
            did = self.db.create_draft(title, body)
            self.db.add_version(did, "original", body, "初稿")
            self._json({"id": did, "title": title, "chars": len(body)})
            return
        if path == "/api/run":
            d = self.db.get_draft(data.get("id"))
            if not d:
                self._json({"error": "稿子不存在"}, 404)
                return
            mode = str(data.get("mode", "polish"))
            if mode not in ("polish", "rewrite", "expand", "shrink", "title"):
                self._json({"error": f"不认识的模式:{mode}"}, 400)
                return
            kw = {"style": str(data.get("style", "formal"))} if mode == "rewrite" else {}
            try:
                r = agent.transform(d, mode, config=self.cfg, force_mock=self.force_mock, **kw)
            except Exception as e:  # noqa: BLE001 模型异常统一转给前端
                self._json({"error": str(e)}, 502)
                return
            if r.get("body") and not r.get("rejected") and mode != "title":
                vid = self.db.add_version(d["id"], r["mode"], r["body"], r.get("note", ""))
                self.db.update_body(d["id"], r["body"])
                r["version_id"] = vid
                r["saved"] = True
            self._json(r)
            return
        self._json({"error": "not found"}, 404)


def _make_handler(db: Database, cfg: dict, force_mock: bool):
    class Handler(_Handler):
        pass

    Handler.db, Handler.cfg, Handler.force_mock = db, cfg, force_mock
    return Handler


def serve(host: str = "127.0.0.1", port: int = 8000, db_path: str | None = None, force_mock: bool = False):
    db = Database(db_path or os.environ.get("BIGENG_DB"))
    cfg = llm.default_config()
    httpd = ThreadingHTTPServer((host, port), _make_handler(db, cfg, force_mock))
    print(f"✍️  笔耕已启动  http://{host}:{httpd.server_address[1]}")
    print("   Ctrl+C 结束")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        db.close()


if __name__ == "__main__":
    serve()
