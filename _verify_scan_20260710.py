#!/usr/bin/env python3
"""Batch checker for the 2026-07-10 ranking run.

Two gates per success row:
  1. TOP-3 rows (rank 1-3): upload the screenshot to S3, call
     POST /api/screenshot-scan/verify (ad-hoc). PASS iff valid==true
     (exact business name is a real numbered-list entry at the claimed rank).
  2. ALL rows: text-scan response_text for leaked prompt instructions
     (the "[RANK: X/Y] FIRST" / "IMMEDIATELY after" echo bug).

Writes verify_report_2026-07-10.csv with a PASS/FAIL verdict + reason.
FAIL rows are the ones to delete from the audit CSV and re-run on the new prompt.

env: READ_API_TOKEN, SSL_CERT_FILE, AWS_PROFILE=aeo-admin
"""
import csv, os, re, ssl, json, subprocess, urllib.request
from concurrent.futures import ThreadPoolExecutor

CSV = "rabbitmq_audit_results_2026-07-10_2026-07-10.csv"
OUT = "verify_report_2026-07-10.csv"
API = "https://jjm59vpn3y.us-east-1.awsapprunner.com/api/screenshot-scan/verify"
BUCKET = "aeo-rank-screenshots"
TOKEN = os.environ["READ_API_TOKEN"]
CTX = ssl.create_default_context(cafile=os.environ["SSL_CERT_FILE"])
ROOTS = ["", "/Users/seolocalph/projects/aeo-appium/", "/Users/seolocalph/projects/device-agent/"]

# Prompt fragments that must never appear in a clean answer (instruction leak).
LEAK = ["immediately after", "before any summary", " own line", "do not pad",
        "2-4 word tag", "numbered 1-3", "[rank: x/y", "] first", "rank: x/y",
        "under 8 words", "verbatim name", "never abbreviated"]

# The captured response_text is a full-page scrape that INCLUDES the visible
# prompt bubble (ChatGPT "You said:…", Perplexity echoed-query). Scanning the
# whole page flags every ChatGPT/Perplexity row on the prompt text itself — a
# false positive. Only the model's answer counts, so split off the prompt first.
ANSWER_MARKER = {"chatgpt": "ChatGPT said:", "perplexity": "Show more"}

# gate 3 (consistency): the model must not list the target business in the top 3
# while [RANK: X/Y] claims a different position — e.g. listed #1 but [RANK: 4/4]
# (a fabricated bad rank, same class as the FABRICATED_BAD_RANK correction set).
# Match the business against each list item's NAME only (the text before the
# "— description"), never the whole line, so a generic name like "Air Duct
# Cleaning" doesn't match a competitor's description and false-positive.
_RANK_RE = re.compile(r"\[rank:\s*(\d+)\s*/\s*(\d+)\]", re.I)


def _norm(s):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s.lower()).split())


def _list_name(item):
    return _norm(re.split(r"\s[—–-]\s|\n", item.strip(), maxsplit=1)[0])


def rank_consistency(answer, biz):
    """FAIL reason when the target business's top-3 list position disagrees with
    the [RANK: X/Y] line; None if consistent or undeterminable. Text-based
    pre-check; a vision validator on the screenshot is the more robust upgrade."""
    m = _RANK_RE.search(answer)
    if not m:
        return None
    x = int(m.group(1))
    biz_core = _norm((biz or "").split(",")[0])
    if len(biz_core) < 3:
        return None
    region = answer[:m.start()]
    names = {}
    for n in (1, 2, 3):
        mm = re.search(rf"(?:^|\n)\s*{n}[.\)]\s*(.*?)(?=(?:\n\s*{n + 1}[.\)])|\Z)",
                       region, re.S)
        if mm:
            names[n] = _list_name(mm.group(1))
    listed = next((n for n in (1, 2, 3) if n in names and biz_core in names[n]), None)
    if listed is not None and (x > 3 or x != listed):
        return f"inconsistent(listed#{listed},RANK{x})"
    return None


def answer_text(txt, plat):
    """Return only the model's answer, stripping the echoed prompt bubble.

    Falls back to the full text when the marker is absent (better a false
    positive than a missed leak)."""
    marker = ANSWER_MARKER.get(plat)
    if marker and marker in txt:
        return txt.split(marker, 1)[1]
    return txt


def find(p):
    for r in ROOTS:
        f = r + p if r else p
        if p and os.path.isfile(f):
            return f
    return None


def verify(local, biz, rank, key):
    subprocess.run(["aws", "s3", "cp", local, f"s3://{BUCKET}/{key}",
                    "--profile", "aeo-admin", "--region", "us-east-1"],
                   capture_output=True, text=True)
    body = json.dumps({"screenshotUrl": f"s3://{BUCKET}/{key}",
                       "businessName": biz, "rankingPosition": rank}).encode()
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    for _ in range(3):
        try:
            return json.load(urllib.request.urlopen(req, timeout=90, context=CTX))
        except Exception:
            continue
    return None


def check(r):
    biz = r.get("biz_name", "")
    plat = (r.get("platform") or "").lower()
    resp = answer_text(r.get("response_text") or "", plat).lower()
    rank = r.get("rank_position", "")
    reasons = []
    # gate 2: leaked instructions (answer only — the prompt bubble is stripped)
    hit = [w for w in LEAK if w in resp]
    if hit:
        reasons.append("leak:" + "|".join(hit[:3]))
    # gate 3: list position vs [RANK] consistency (fabricated bad rank)
    incon = rank_consistency(resp, biz)
    if incon:
        reasons.append("consistency:" + incon)
    # gate 1: top-3 checker
    inlist = pos = None
    if rank in ("1", "2", "3"):
        local = find(r.get("screenshot"))
        if not local:
            reasons.append("no_screenshot_on_disk")
        else:
            v = verify(local, biz, int(rank),
                       f"verify-staging/kw{r.get('campaign_id')}_{plat}.png")
            if v is None:
                reasons.append("verify_error")
            else:
                inlist, pos = v.get("inList"), v.get("position")
                if not v.get("valid"):
                    reasons.append(f"checker_invalid(inList={inlist},pos={pos})")
    return {"campaign_id": r.get("campaign_id"), "platform": plat, "biz_name": biz,
            "rank_position": rank, "gate": "checker" if rank in ("1", "2", "3") else "text",
            "verdict": "FAIL" if reasons else "PASS", "reason": ";".join(reasons),
            "inList": inlist, "position": pos}


rows = [r for r in csv.DictReader(open(CSV)) if r.get("status") == "success"]
print(f"checking {len(rows)} success rows "
      f"({sum(1 for r in rows if r.get('rank_position') in ('1','2','3'))} top-3 via endpoint)…",
      flush=True)
results = []
with ThreadPoolExecutor(max_workers=8) as ex:
    for i, res in enumerate(ex.map(check, rows), 1):
        results.append(res)
        if i % 50 == 0:
            print(f"  {i}/{len(rows)}", flush=True)

with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
    w.writeheader()
    w.writerows(results)

fails = [r for r in results if r["verdict"] == "FAIL"]
top3_fail = [r for r in fails if r["gate"] == "checker"]
leak_fail = [r for r in fails if "leak:" in r["reason"]]
print(f"\n=== VERIFY REPORT -> {OUT} ===")
print(f"total: {len(results)} | PASS: {len(results)-len(fails)} | FAIL: {len(fails)}")
print(f"  top-3 checker FAIL: {len(top3_fail)} / 255")
print(f"  leaked-instruction FAIL: {len(leak_fail)}")
print(f"FAIL rows (delete + re-run) are in {OUT} (verdict=FAIL).")
