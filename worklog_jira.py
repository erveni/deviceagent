#!/usr/bin/env python3
"""Create a Jira worklog for one day, with evidence gathered from the machine.

Two steps, so the narrative stays human-written and the facts stay machine-checked:

    worklog_jira.py gather --date 2026-09-01
        Prints JSON: commits authored that day across every local repo, deliverable
        files on disk with real row counts, and run logs. Nothing is written.

    worklog_jira.py create --date 2026-09-01 --hours 8h --issue DVFRM-162 \
                   --heading "..." --body-file body.txt [--apply]
        Builds the ADF comment (your body + an Evidence section built from `gather`)
        and posts it. Dry-run unless --apply is passed.

Auth comes from the environment, never from this file:
    JIRA_EMAIL      (default erven.i@appstango.com)
    JIRA_API_TOKEN  (required)
    JIRA_SITE       (default https://devicefarmseolocal.atlassian.net)
"""
import argparse, base64, collections, datetime as dt, glob, json, os, re, subprocess, sys, urllib.request

SITE  = os.environ.get("JIRA_SITE", "https://devicefarmseolocal.atlassian.net")
EMAIL = os.environ.get("JIRA_EMAIL", "erven.i@appstango.com")
PROJECTS = os.path.expanduser("~/projects")
DESKTOP  = os.path.expanduser("~/Desktop")
SKIP_REPOS = {"everything-claude-code"}


def _token():
    """Resolve the API token without ever requiring an export, in this order:

      1. JIRA_API_TOKEN in the environment (wins, so CI or a one-off can override)
      2. macOS Keychain, service `jira-devicefarmseolocal` — the recommended home;
         nothing lands on disk in plaintext. Store it once with:
             security add-generic-password -a "$USER" -s jira-devicefarmseolocal \
                 -w '<token>' -U
      3. JIRA_API_TOKEN= in .env.dev next to this script (gitignored)
    """
    tok = os.environ.get("JIRA_API_TOKEN")
    if tok:
        return tok
    try:
        cp = subprocess.run(["security", "find-generic-password",
                             "-s", "jira-devicefarmseolocal", "-w"],
                            capture_output=True, text=True, timeout=10)
        if cp.returncode == 0 and cp.stdout.strip():
            return cp.stdout.strip()
    except Exception:
        pass
    envf = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.dev")
    if os.path.exists(envf):
        for line in open(envf):
            k, _, v = line.strip().partition("=")
            if k.strip() == "JIRA_API_TOKEN" and v.strip():
                return v.strip().strip("'\"")
    sys.exit("No Jira token found. Store one in the Keychain:\n"
             "  security add-generic-password -a \"$USER\" "
             "-s jira-devicefarmseolocal -w '<token>' -U")


def _auth():
    return "Basic " + base64.b64encode(f"{EMAIL}:{_token()}".encode()).decode()


def _api(path, data=None, method="GET"):
    req = urllib.request.Request(
        SITE + path,
        data=json.dumps(data).encode() if data is not None else None,
        method=method,
        headers={"Authorization": _auth(), "Accept": "application/json",
                 "Content-Type": "application/json"})
    body = urllib.request.urlopen(req, timeout=40).read()
    return json.loads(body) if body else {}


def repos():
    """Repos by NAME order, so a commit shared with a worktree is credited to the
    canonical checkout (device-agent) rather than device-agent-citedlogic."""
    found = []
    for p in glob.glob(f"{PROJECTS}/*/.git"):
        name = os.path.basename(os.path.dirname(p))
        if name not in SKIP_REPOS:
            found.append((name, os.path.dirname(p)))
    return sorted(found, key=lambda t: (len(t[0]), t[0]))


def commits_on(date, author="erven"):
    """Commits authored on `date`, across every local repo (all branches, so work
    pushed to devicefarm1 counts even when it is not on the current branch).

    Deduped by SHA: worktrees and clones share git objects, so the same commit
    would otherwise be reported once per checkout."""
    out, seen = [], set()
    for name, path in repos():
        cp = subprocess.run(
            ["git", "-C", path, "log", "--all", f"--author={author}",
             f"--since={date} 00:00", f"--until={date} 23:59",
             "--date=short", "--format=%h|%s"],
            capture_output=True, text=True)
        for line in cp.stdout.splitlines():
            sha, _, subj = line.partition("|")
            if sha and sha not in seen:
                seen.add(sha)
                out.append({"repo": name, "sha": sha, "subject": subj})
    return out


def _rows(path):
    try:
        with open(path, errors="ignore") as f:
            return sum(1 for _ in f) - 1
    except Exception:
        return None


def artifacts_on(date):
    """Deliverables relevant to `date`, matched two independent ways.

    A nightly starts in the evening and lands after midnight, so the file NAMED for
    a date is usually written the following morning, and the file written ON a date
    is usually the previous date's deliverable. Reporting only one of those hides
    real work (e.g. shipping a backfill of an earlier date). Both are returned,
    labelled, so the narrative can tell "named for this date" from "produced on it".
    """
    d = dt.date.fromisoformat(date)
    short = d.strftime("%b").lower() + d.strftime("%d")          # 'sep01'
    named, produced = [], []
    for base in ("Daily", "Rankings"):
        for p in glob.glob(f"{DESKTOP}/{base}/*"):
            b = os.path.basename(p)
            if not os.path.isfile(p):
                continue
            rec = {"file": b, "rows": _rows(p) if b.endswith(".csv") else None,
                   "modified": dt.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")}
            if b.lower().startswith(short) or date in b:
                named.append(rec)
            elif rec["modified"][:10] == date:
                produced.append(rec)
    return {"named_for_date": named, "modified_on_date": produced}


def runlogs_on(date):
    out = []
    for pat in (f"/private/tmp/daily_auto_{date}.log", f"/private/tmp/dailyfull_{date}.log",
                f"/private/tmp/ranking_auto_{date}.log"):
        if os.path.exists(pat):
            txt = open(pat, errors="ignore").read()
            out.append({"log": os.path.basename(pat),
                        "ok": len(re.findall(r"\] OK ", txt)),
                        "err": len(re.findall(r"\] ERR ", txt)),
                        "done": (re.findall(r"ALL SUCCESS[^\n]*", txt) or [""])[-1].strip()})
    return out


def gather(date):
    return {"date": date, "commits": commits_on(date),
            "artifacts": artifacts_on(date), "runs": runlogs_on(date)}


# ---------- ADF ----------
def _t(s):  return {"type": "text", "text": s}
def _code(s): return {"type": "text", "text": s, "marks": [{"type": "code"}]}
def _b(s):  return {"type": "text", "text": s, "marks": [{"type": "strong"}]}
def _p(*c): return {"type": "paragraph", "content": list(c)}
def _h(l, s): return {"type": "heading", "attrs": {"level": l}, "content": [_t(s)]}
def _li(nodes, sub=None):
    body = [_p(*nodes)]
    if sub:
        body.append({"type": "bulletList",
                     "content": [{"type": "listItem", "content": [_p(*s)]} for s in sub]})
    return {"type": "listItem", "content": body}
def _ul(items): return {"type": "bulletList", "content": items}


def build_adf(heading, body_text, ev):
    content = [_h(3, heading)]
    paras = [b.strip() for b in body_text.split("\n\n") if b.strip()]
    if paras:
        content.append(_p(_t(paras[0])))
        rest = []
        for blk in paras[1:]:
            for line in blk.split("\n"):
                line = line.strip().lstrip("-•").strip()
                if line:
                    rest.append(_li([_t(line)]))
        if rest:
            content += [_h(4, "Detail"), _ul(rest)]
    if ev["commits"]:
        byrepo = collections.defaultdict(list)
        for c in ev["commits"]:
            byrepo[c["repo"]].append(c)
        content.append(_h(4, f"Commits verified ({len(ev['commits'])} across {len(byrepo)} repo(s))"))
        items = []
        for repo in sorted(byrepo, key=lambda r: -len(byrepo[r])):
            subs = [[_code(c["sha"]), _t(" " + c["subject"])] for c in byrepo[repo][:10]]
            if len(byrepo[repo]) > 10:
                subs.append([_t(f"…and {len(byrepo[repo]) - 10} more in this repo")])
            items.append(_li([_b(repo), _t(f" — {len(byrepo[repo])} commit(s)")], subs))
        content.append(_ul(items))
    arts = ev["artifacts"]
    named, produced = arts["named_for_date"], arts["modified_on_date"]
    if named or produced:
        content.append(_h(4, "Artifacts confirmed on disk"))
        items = []
        for a in sorted(named, key=lambda a: a["file"]):
            items.append(_li([_code(a["file"])]
                             + ([_t(f" — {a['rows']:,} rows")] if a["rows"] else [])
                             + [_t(f" (written {a['modified']})")]))
        for a in sorted(produced, key=lambda a: a["file"]):
            items.append(_li([_code(a["file"])]
                             + ([_t(f" — {a['rows']:,} rows")] if a["rows"] else [])
                             + [_t(f" — shipped this day ({a['modified']})")]))
        content.append(_ul(items))
    if ev["runs"]:
        content.append(_h(4, "Run logs"))
        content.append(_ul([
            _li([_code(r["log"]), _t(f" — ok={r['ok']}, err={r['err']}"
                                     + (f" — {r['done']}" if r["done"] else ""))])
            for r in ev["runs"]]))
    return {"type": "doc", "version": 1, "content": content}


def suggest_issue(date):
    """The issue whose existing worklogs sit closest to this date."""
    q = ("worklogAuthor = currentUser() ORDER BY key ASC")
    issues = _api("/rest/api/3/search/jql?jql=" + urllib.parse.quote(q)
                  + "&fields=key,summary&maxResults=200")["issues"]
    best, gap = None, 10**9
    target = dt.date.fromisoformat(date)
    for i in issues:
        for w in _api(f"/rest/api/3/issue/{i['key']}/worklog?maxResults=200").get("worklogs", []):
            d = abs((dt.date.fromisoformat(w["started"][:10]) - target).days)
            if d < gap:
                best, gap = (i["key"], i["fields"]["summary"]), d
    return best, gap


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gather"); g.add_argument("--date", required=True)
    s = sub.add_parser("suggest"); s.add_argument("--date", required=True)
    c = sub.add_parser("create")
    c.add_argument("--date", required=True, help="date the worklog is LOGGED against")
    c.add_argument("--evidence-date", help="date the work actually describes; "
                                           "defaults to --date. Use when a Sunday's "
                                           "work is logged on the Monday.")
    c.add_argument("--hours", required=True, help="Jira format: 8h, 1d, 1d 1h, 2h30m")
    c.add_argument("--issue", required=True)
    c.add_argument("--heading", required=True)
    c.add_argument("--body-file", required=True)
    c.add_argument("--start-time", default="06:00", help="clock time, default 06:00")
    c.add_argument("--tz-offset", default="-0600",
                   help="UTC offset stamped on the worklog. Default -0600 to match "
                        "every existing DVFRM worklog; this Mac's own clock reports a "
                        "different offset, which would shift the displayed date.")
    c.add_argument("--apply", action="store_true", help="actually POST (otherwise dry-run)")
    a = ap.parse_args()

    if a.cmd == "gather":
        print(json.dumps(gather(a.date), indent=1)); return
    if a.cmd == "suggest":
        (key, summary), gap = suggest_issue(a.date)
        print(f"{key}  ({summary}) — nearest existing worklog is {gap} day(s) away"); return

    ev = gather(a.evidence_date or a.date)
    adf = build_adf(a.heading, open(a.body_file).read(), ev)
    started = f"{a.date}T{a.start_time}:00.000{a.tz_offset}"
    payload = {"started": started, "timeSpent": a.hours, "comment": adf}
    if not a.apply:
        print("DRY RUN — nothing written. Payload:")
        print(f"  issue   {a.issue}")
        print(f"  started {started}")
        print(f"  time    {a.hours}")
        na = len(ev["artifacts"]["named_for_date"]); pa = len(ev["artifacts"]["modified_on_date"])
        print(f"  evidence for {ev['date']}: {len(ev['commits'])} commits, "
              f"{na} named for that date, {pa} shipped that day, {len(ev['runs'])} run log(s)")
        print(json.dumps(adf)[:600] + " …")
        return
    r = _api(f"/rest/api/3/issue/{a.issue}/worklog?adjustEstimate=leave&notifyUsers=false",
             payload, "POST")
    print(f"created worklog {r['id']} on {a.issue}: started={r['started']} timeSpent={r['timeSpent']}")


if __name__ == "__main__":
    import urllib.parse
    main()
