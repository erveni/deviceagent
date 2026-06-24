#!/usr/bin/env python3
"""Run orchestrator dashboard — pure-Python (stdlib http.server). Two modes:

  DAILY    : pick date -> Build/Randomize plan -> Run (auto-retry to 100%) -> watch
  RANKING  : pick date + scope -> Build due-set (never-ranked/stale) -> Run
             (residential audit path, inline OCR, retry errors to 0) -> watch

Wraps the existing engine (build_daily_plan.py / run_daily_auto.sh /
build_ranking_dueset.py / run_ranking_auto.sh / run_rolling_plan.py / run_ranking.py).
No external dependencies. State is derived from plan/dueset files, result CSVs,
and run logs on disk, so it survives reloads and shows runs started elsewhere.

    python3 dashboard.py            # http://127.0.0.1:8800
    PORT=8888 python3 dashboard.py
"""
from __future__ import annotations
import csv, glob, json, os, re, signal, subprocess, sys
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8800"))
DAILY_BUILDER = os.path.join(HERE, "build_daily_plan.py")
DAILY_WRAPPER = os.path.join(HERE, "run_daily_auto.sh")
RANK_BUILDER = os.path.join(HERE, "build_ranking_dueset.py")
RANK_WRAPPER = os.path.join(HERE, "run_ranking_auto.sh")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SCOPES = ("never_ranked", "stale", "all_due")


# ---------- shared helpers ----------
def pid_alive(pidfile):
    try:
        pid = int(open(pidfile).read().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError, FileNotFoundError):
        return None


def tail(path, n=40):
    try:
        return "".join(open(path, errors="replace").readlines()[-n:])
    except FileNotFoundError:
        return ""


def pgrep(pat):
    try:
        out = subprocess.run(["pgrep", "-f", pat], capture_output=True, text=True).stdout.strip()
        return int(out.split()[0]) if out else None
    except Exception:
        return None


def _executor_token():
    tok = subprocess.run(
        ["aws", "secretsmanager", "get-secret-value", "--secret-id", "aeo-admin/prod",
         "--profile", "aeo-admin", "--region", "us-east-1",
         "--query", "SecretString", "--output", "text"],
        capture_output=True, text=True).stdout.strip()
    try:
        return json.loads(tok).get("EXECUTOR_TOKEN", "")
    except Exception:
        return ""


def _certifi():
    return subprocess.run([sys.executable, "-c", "import certifi;print(certifi.where())"],
                          capture_output=True, text=True).stdout.strip()


def _norm(v):
    s = "" if v is None else str(v).strip()
    return "" if s.lower() in ("", "null", "none") else s


# ========== DAILY ==========
def d_plan(date): return os.path.join(HERE, f"daily_plan_{date}.json")
def d_blog(date): return f"/private/tmp/dash_build_{date}.log"
def d_bpid(date): return f"/private/tmp/dash_build_{date}.pid"
def d_rpid(date): return f"/private/tmp/dash_run_{date}.pid"


def d_runlog(date):
    g = f"/private/tmp/daily_auto_{date}.log"
    j = "/private/tmp/jun08_daily_auto.log"
    return g if os.path.exists(g) else (j if date == "2026-06-08" and os.path.exists(j) else g)


def d_results(date):
    return sorted(set(glob.glob(os.path.join(HERE, f"daily_plan_{date}*results*.csv"))))


def d_read_plan(date):
    try:
        return json.load(open(d_plan(date)))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _dkey(r):
    return (_norm(r.get("platform")).lower(), _norm(r.get("client_id")), _norm(r.get("campaign_id")),
            _norm(r.get("biz_name")).lower(), _norm(r.get("keyword") or r.get("keyword_text")).lower())


def d_progress(date, plan):
    total = plan.get("total_jobs", 0) if plan else 0
    pk, plat_total = set(), Counter()
    for w in (plan or {}).get("waves", []):
        for j in w:
            pk.add(_dkey(j)); plat_total[j.get("platform")] += 1
    done, plat_done, seen = set(), Counter(), set()
    for f in d_results(date):
        try:
            for r in csv.DictReader(open(f)):
                k = _dkey(r); seen.add(k)
                if (r.get("status") or "").strip() == "success":
                    done.add(k); plat_done[r.get("platform")] += 1
        except FileNotFoundError:
            pass
    succ = len(done & pk) if pk else len(done)
    # currently failing = attempted (seen) but not yet succeeded, still in plan
    errored = len((seen & pk) - done)
    plats = sorted({p for p in (set(plat_total) | set(plat_done)) if p})
    return {"total": total, "success": succ, "errored": errored, "no_rank": None,
            "remaining": max(0, total - succ),
            "by_platform": [{"platform": p, "done": plat_done.get(p, 0), "total": plat_total.get(p, 0)}
                            for p in plats]}


def d_campaigns(plan, limit=25):
    if not plan:
        return []
    c = Counter()
    for w in plan["waves"]:
        for j in w:
            c[j.get("campaign_name") or j.get("biz_name") or "?"] += 1
    return [{"label": k, "n": v} for k, v in c.most_common(limit)]


def d_parse_buildlog(date):
    txt = tail(d_blog(date), 200)
    out = {"planned": None, "split": None, "active": None}
    if (m := re.search(r"TOTAL sessions planned:\s*(\d+)", txt)):
        out["planned"] = int(m.group(1))
    if (m := re.search(r"platform split:\s*(\{[^}]*\})", txt)):
        out["split"] = m.group(1)
    if (m := re.search(r"active keywords:\s*(\d+)\s+across\s+(\d+)", txt)):
        out["active"] = f"{m.group(1)} kw / {m.group(2)} campaigns"
    return out


def d_state(date):
    plan = d_read_plan(date)
    bpid, rpid = pid_alive(d_bpid(date)), pid_alive(d_rpid(date))
    if not rpid:
        rpid = pgrep(f"run_.*daily_auto.*{date}|run_jun08_daily_auto")
    rlog = tail(d_runlog(date), 40)
    terminal = "done" if re.search(r"ALL SUCCESS", rlog) else ("stalled" if re.search(r"NO PROGRESS", rlog) else None)
    phase = ("building" if bpid else "running" if rpid else
             terminal if (plan and terminal) else "ready" if plan else "idle")
    return {"mode": "daily", "date": date, "phase": phase,
            "build_pid": bpid, "run_pid": rpid, "plan_exists": bool(plan),
            "plan": {"total_jobs": plan.get("total_jobs"), "waves": len(plan.get("waves", []))} if plan else None,
            "build": d_parse_buildlog(date),
            "progress": d_progress(date, plan) if plan else None,
            "rows": d_campaigns(plan), "rows_title": "Campaign / location",
            "run_log_tail": tail(d_runlog(date), 30)}


# ========== RANKING ==========
def r_kwids(date): return f"/tmp/ranking_kw_ids_{date}.json"
def r_csvs(date):  # append_row date-splits into <base>_<rowdate>.csv — match all
    return sorted(glob.glob(os.path.join(HERE, f"rabbitmq_audit_results_{date}_ranking*.csv")))
def r_blog(date):  return f"/private/tmp/dash_rankbuild_{date}.log"
def r_bpid(date):  return f"/private/tmp/dash_rankbuild_{date}.pid"
def r_rpid(date):  return f"/private/tmp/dash_rankrun_{date}.pid"
def r_runlog(date): return f"/private/tmp/ranking_auto_{date}.log"


def r_dueset(date):
    try:
        return len(json.load(open(r_kwids(date))))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def r_progress(date):
    kw = r_dueset(date)
    total = kw * 3 if kw else 0
    by_status, plat = Counter(), Counter()
    seen = {}
    for f in r_csvs(date):
        try:
            for r in csv.DictReader(open(f)):
                k = (_norm(r.get("campaign_id")), _norm(r.get("platform")).lower())
                seen[k] = (r.get("status") or "").strip().lower()
        except FileNotFoundError:
            pass
    for k, s in seen.items():
        by_status[s] += 1
        if s in ("success", "no_rank"):
            plat[k[1]] += 1
    succ, nr = by_status.get("success", 0), by_status.get("no_rank", 0)
    err = sum(v for s, v in by_status.items() if s not in ("success", "no_rank"))
    return {"total": total, "success": succ, "no_rank": nr, "errored": err,
            "remaining": max(0, total - succ - nr),
            "by_platform": [{"platform": p, "done": plat.get(p, 0), "total": (total // 3 if total else 0)}
                            for p in ("chatgpt", "gemini", "perplexity")]}


def r_parse_buildlog(date):
    txt = tail(r_blog(date), 80)
    out = {"selected": None, "never": None, "jobs": None}
    if (m := re.search(r"SELECTED \([^)]*\)\s*:\s*(\d+)", txt)):
        out["selected"] = int(m.group(1))
    if (m := re.search(r"never-ranked keywords\s*:\s*(\d+)", txt)):
        out["never"] = int(m.group(1))
    if (m := re.search(r"TOTAL JOBS[^:]*:\s*(\d+)", txt)):
        out["jobs"] = int(m.group(1))
    return out


def r_state(date):
    bpid, rpid = pid_alive(r_bpid(date)), pid_alive(r_rpid(date))
    if not rpid:
        rpid = pgrep(f"run_ranking_auto.sh {date}")
    kw = r_dueset(date)
    rlog = tail(r_runlog(date), 40)
    terminal = "done" if re.search(r"ALL DONE", rlog) else ("stalled" if re.search(r"NO PROGRESS", rlog) else None)
    phase = ("building" if bpid else "running" if rpid else
             terminal if (kw and terminal) else "ready" if kw else "idle")
    return {"mode": "ranking", "date": date, "phase": phase,
            "build_pid": bpid, "run_pid": rpid, "plan_exists": bool(kw),
            "plan": {"total_jobs": kw * 3, "keywords": kw} if kw else None,
            "build": r_parse_buildlog(date),
            "progress": r_progress(date) if kw else None,
            "rows": [], "rows_title": "Ranking",
            "run_log_tail": tail(r_runlog(date), 30)}


# ---------- actions ----------
def _popen(cmd, env, logfile):
    lf = open(logfile, "w")
    p = subprocess.Popen(cmd, cwd=HERE, env=env, stdout=lf, stderr=lf, start_new_session=True)
    return p.pid


def daily_build(date, scope=None):
    if pid_alive(d_bpid(date)) or d_read_plan(date):
        return False, "plan already built or building"
    tok = _executor_token()
    if not tok:
        return False, "could not load EXECUTOR_TOKEN"
    env = dict(os.environ, DATE=date, DRY_RUN="0", PLAN_PATH=d_plan(date),
               SSL_CERT_FILE=_certifi(), EXECUTOR_TOKEN=tok)
    pid = _popen([sys.executable, "-u", DAILY_BUILDER], env, d_blog(date))
    open(d_bpid(date), "w").write(str(pid))
    return True, f"daily build started pid {pid}"


def daily_run(date, scope=None):
    if pid_alive(d_rpid(date)) or pgrep(f"run_.*daily_auto.*{date}|run_jun08_daily_auto"):
        return False, "run already in progress"
    if not d_read_plan(date):
        return False, "build the plan first"
    pid = _popen(["/bin/bash", DAILY_WRAPPER, date], dict(os.environ), f"/private/tmp/dash_run_launch_{date}.log")
    open(d_rpid(date), "w").write(str(pid))
    return True, f"daily run started pid {pid}"


def ranking_build(date, scope="never_ranked"):
    if scope not in SCOPES:
        scope = "never_ranked"
    if pid_alive(r_bpid(date)):
        return False, "due-set already building"
    tok = _executor_token()
    if not tok:
        return False, "could not load EXECUTOR_TOKEN"
    env = dict(os.environ, DATE=date, SCOPE=scope, SSL_CERT_FILE=_certifi(), EXECUTOR_TOKEN=tok)
    pid = _popen([sys.executable, "-u", RANK_BUILDER], env, r_blog(date))
    open(r_bpid(date), "w").write(str(pid))
    return True, f"ranking due-set ({scope}) building pid {pid}"


def ranking_run(date, scope="never_ranked"):
    if pid_alive(r_rpid(date)) or pgrep(f"run_ranking_auto.sh {date}"):
        return False, "ranking run already in progress"
    if r_dueset(date) is None:
        return False, "build the due-set first"
    pid = _popen(["/bin/bash", RANK_WRAPPER, date, scope], dict(os.environ),
                 f"/private/tmp/dash_rankrun_launch_{date}.log")
    open(r_rpid(date), "w").write(str(pid))
    return True, f"ranking run started pid {pid}"


def stop_all(date, scope=None):
    killed = []
    for pf in (d_rpid(date), d_bpid(date), r_rpid(date), r_bpid(date)):
        pid = pid_alive(pf)
        if pid:
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM); killed.append(pid)
            except Exception:
                pass
    for pat in ("run_jun08_daily_auto", f"run_daily_auto.sh {date}", f"run_ranking_auto.sh {date}",
                "run_rolling_plan.py", "run_ranking.py", "gost -C", "sni_relay.py"):
        subprocess.run(["pkill", "-f", pat], capture_output=True)
    return True, f"stopped {killed} + child runners/proxies"


# ---------- http ----------
ROUTES = {"/api/build": daily_build, "/api/run": daily_run, "/api/stop": stop_all,
          "/api/ranking_build": ranking_build, "/api/ranking_run": ranking_run}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            return self._send(200, HTML, "text/html; charset=utf-8")
        if u.path == "/api/state":
            q = parse_qs(u.query)
            date = (q.get("date") or [""])[0]
            mode = (q.get("mode") or ["daily"])[0]
            if not DATE_RE.match(date):
                return self._send(400, json.dumps({"error": "bad date"}))
            return self._send(200, json.dumps(r_state(date) if mode == "ranking" else d_state(date)))
        return self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        date, scope = body.get("date", ""), body.get("scope", "never_ranked")
        if not DATE_RE.match(date):
            return self._send(400, json.dumps({"error": "bad date"}))
        fn = ROUTES.get(u.path)
        if not fn:
            return self._send(404, json.dumps({"error": "not found"}))
        ok, msg = fn(date, scope)
        return self._send(200, json.dumps({"ok": ok, "msg": msg}))


HTML = r"""<!doctype html><html><head><meta charset="utf-8">
<title>Run Orchestrator</title>
<style>
 :root{--bg:#0f1115;--card:#181b22;--mut:#8b93a7;--fg:#e6e9ef;--ac:#4f8cff;--ok:#2ecc71;--err:#ff5d5d;--warn:#ffb020;--nr:#a0a8bd;}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
 header{padding:16px 22px;border-bottom:1px solid #232733;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
 h1{font-size:17px;margin:0;font-weight:650} .sp{flex:1}
 input,select,button{font:inherit;color:var(--fg);background:#222632;border:1px solid #313747;border-radius:8px;padding:8px 12px}
 button{cursor:pointer;background:var(--ac);border:0;font-weight:600} button:hover{filter:brightness(1.08)}
 button.sec{background:#2a2f3c} button.danger{background:var(--err)} button:disabled{opacity:.4;cursor:not-allowed}
 .wrap{padding:22px;display:grid;grid-template-columns:1fr 1fr;gap:18px;max-width:1200px}
 .card{background:var(--card);border:1px solid #232733;border-radius:14px;padding:18px}
 .card h2{font-size:13px;margin:0 0 12px;color:var(--mut);text-transform:uppercase;letter-spacing:.5px}
 .metrics{display:flex;gap:10px;flex-wrap:wrap} .metric{flex:1;min-width:80px;background:#12151c;border-radius:10px;padding:12px}
 .metric .v{font-size:24px;font-weight:700} .metric .l{color:var(--mut);font-size:12px}
 .bar{height:14px;background:#12151c;border-radius:8px;overflow:hidden;margin:10px 0;display:flex}
 .bar i{display:block;height:100%} .bar .s{background:var(--ok)} .bar .n{background:var(--nr)} .bar .e{background:var(--err)}
 .pill{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600}
 .pill.idle{background:#2a2f3c;color:var(--mut)} .pill.building{background:#3a2f12;color:var(--warn)}
 .pill.ready{background:#13314a;color:var(--ac)} .pill.running{background:#13314a;color:var(--ac)}
 .pill.done{background:#11331f;color:var(--ok)} .pill.stalled{background:#3a1414;color:var(--err)}
 table{width:100%;border-collapse:collapse} td,th{text-align:left;padding:5px 8px;border-bottom:1px solid #1f2430;font-size:13px}
 th{color:var(--mut);font-weight:600} pre{background:#0b0d12;border-radius:10px;padding:12px;max-height:300px;overflow:auto;font-size:12px;color:#b9c0d0}
 .muted{color:var(--mut)} .spin{display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--warn);animation:p 1s infinite}
 @keyframes p{50%{opacity:.3}}
</style></head><body>
<header>
 <h1>📡 Run Orchestrator</h1>
 <span id="phase" class="pill idle">idle</span>
 <span class="sp"></span>
 <label class="muted">Mode</label>
 <select id="mode"><option value="daily">Daily sessions</option><option value="ranking">Ranking</option></select>
 <label class="muted" id="scopeLbl" style="display:none">Scope</label>
 <select id="scope" style="display:none">
   <option value="never_ranked">Never-ranked (initial)</option>
   <option value="stale">Stale &gt;14d</option>
   <option value="all_due">All due</option>
 </select>
 <label class="muted">Date</label><input type="date" id="date">
 <button id="btnBuild" class="sec">① Build</button>
 <button id="btnRun">② Run</button>
 <button id="btnStop" class="danger">■ Stop</button>
</header>
<div class="wrap">
 <div class="card"><h2 id="planTitle">Plan</h2>
  <div id="planBox" class="muted">Pick a date and click <b>Build</b>.</div>
  <div class="metrics" id="planMetrics" style="margin-top:12px"></div></div>
 <div class="card"><h2>Progress</h2>
  <div id="progBox" class="muted">No run yet.</div>
  <div class="bar" id="bar" style="display:none"></div>
  <div class="metrics" id="progMetrics"></div>
  <div id="platBox" style="margin-top:10px"></div></div>
 <div class="card"><h2 id="rowsTitle">Breakdown</h2><div id="rowsBox" class="muted">—</div></div>
 <div class="card"><h2>Live log</h2><pre id="log">—</pre></div>
</div>
<script>
const $=id=>document.getElementById(id);
$("date").value=new Date().toISOString().slice(0,10);
function mode(){return $("mode").value;}
function ep(a){return mode()=="ranking"?{build:"/api/ranking_build",run:"/api/ranking_run"}[a]:{build:"/api/build",run:"/api/run"}[a];}
async function post(path){const b={date:$("date").value,scope:$("scope").value};
 const r=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)});return r.json();}
$("mode").onchange=()=>{const r=mode()=="ranking";$("scope").style.display=$("scopeLbl").style.display=r?"":"none";
 $("btnBuild").textContent=r?"① Build due-set":"① Build / Randomize";$("planTitle").textContent=r?"Due-set":"Plan";refresh();};
$("scope").onchange=refresh; $("date").onchange=refresh;
$("btnBuild").onclick=async()=>{$("btnBuild").disabled=true;flash((await post(ep("build"))).msg);};
$("btnRun").onclick=async()=>{flash((await post(ep("run"))).msg);};
$("btnStop").onclick=async()=>{if(!confirm("Stop run + child runners?"))return;flash((await post("/api/stop")).msg);};
function flash(m){$("phase").textContent=m;setTimeout(refresh,900);}
function metric(v,l){return `<div class="metric"><div class="v">${v}</div><div class="l">${l}</div></div>`;}
async function refresh(){
 const d=$("date").value;if(!/^\d{4}-\d{2}-\d{2}$/.test(d))return;
 let s;try{s=await(await fetch(`/api/state?date=${d}&mode=${mode()}`)).json();}catch(e){return;}
 const ph=$("phase");ph.className="pill "+s.phase;
 ph.innerHTML=(s.phase=="building"||s.phase=="running")?s.phase+' <span class="spin"></span>':s.phase;
 $("btnBuild").disabled=s.phase=="building"||s.plan_exists;
 $("btnRun").disabled=!s.plan_exists||s.phase=="running"||s.phase=="building";
 const b=s.build||{},rk=mode()=="ranking";
 if(s.plan_exists){
   $("planBox").innerHTML=rk?`<b>${s.plan.keywords}</b> keywords · <b>${s.plan.total_jobs}</b> jobs (×3 platforms)`
     :`<b>${s.plan.total_jobs}</b> sessions · ${s.plan.waves} waves · <span class="muted">${b.active||""}</span>`;
 }else if(s.phase=="building"){
   $("planBox").innerHTML=`<span class="spin"></span> Building… `+(rk?(b.selected?`selected <b>${b.selected}</b> kw`:"fetching catalog…")
     :(b.planned?`planned <b>${b.planned}</b>, enriching…`:"fetching catalog…"));
 }else $("planBox").innerHTML='Pick a date and click <b>Build</b>.';
 $("planMetrics").innerHTML="";
 if(!rk&&b.split){try{const sp=JSON.parse(b.split.replace(/'/g,'"'));$("planMetrics").innerHTML=Object.entries(sp).map(([k,v])=>metric(v,k)).join("");}catch(e){}}
 if(rk&&b.never!=null)$("planMetrics").innerHTML=metric(b.never,"never-ranked")+(b.jobs?metric(b.jobs,"jobs"):"");
 const pr=s.progress;
 if(pr){
   const pct=pr.total?Math.round(pr.success/pr.total*100):0;
   const npct=pr.total&&pr.no_rank?Math.round(pr.no_rank/pr.total*100):0;
   const epct=pr.total?Math.round(pr.errored/pr.total*100):0;
   $("progBox").innerHTML="";$("bar").style.display="flex";
   $("bar").innerHTML=`<i class="s" style="width:${pct}%"></i><i class="n" style="width:${npct}%"></i><i class="e" style="width:${epct}%"></i>`;
   let m=metric(pr.success,"success");
   if(pr.no_rank!=null)m+=metric(pr.no_rank,"no_rank");
   m+=metric(pr.remaining,"remaining")+metric(pr.errored,"errored")+metric(pct+"%","complete");
   $("progMetrics").innerHTML=m;
   $("platBox").innerHTML='<table><tr><th>platform</th><th>done</th><th>planned</th></tr>'+
     pr.by_platform.map(p=>`<tr><td>${p.platform}</td><td>${p.done}</td><td>${p.total}</td></tr>`).join("")+'</table>';
 }else{$("progBox").innerHTML='<span class="muted">No run yet.</span>';$("bar").style.display="none";$("progMetrics").innerHTML="";$("platBox").innerHTML="";}
 $("rowsTitle").textContent=s.rows_title||"Breakdown";
 $("rowsBox").innerHTML=(s.rows&&s.rows.length)
   ?'<table><tr><th>'+(s.rows_title||"")+'</th><th>n</th></tr>'+s.rows.map(c=>`<tr><td>${(c.label||"").slice(0,52)}</td><td>${c.n}</td></tr>`).join("")+'</table>'
   :'<span class="muted">—</span>';
 $("log").textContent=s.run_log_tail||"—";
}
setInterval(refresh,3000);refresh();
</script></body></html>"""


def main():
    print(f"Run Orchestrator → http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
