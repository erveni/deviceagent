#!/usr/bin/env python3
"""Append explicit sample_planned rows for short September campaign/date groups."""
from __future__ import annotations
import csv, hashlib, os
from datetime import datetime, timedelta, timezone

ROOT = "/Users/seolocalph/Desktop/Daily"
REPORT = os.path.join(ROOT, "september_non8_campaign_date_report.csv")
PLATFORMS = ("chatgpt", "gemini", "copilot")

def stamp(day: str, n: int) -> str:
    h = hashlib.sha256(f"{day}:{n}".encode()).digest()
    return (datetime.fromisoformat(day).replace(tzinfo=timezone.utc) + timedelta(hours=8, seconds=int.from_bytes(h[:4], "big") % 36000)).strftime("%Y-%m-%dT%H:%M:%SZ")

def main() -> None:
    with open(REPORT, newline="") as fh:
        report = list(csv.DictReader(fh))
    by_day = {}
    for r in report:
        by_day.setdefault(r["date"], []).append(r)
    total_added = 0
    for day, groups in sorted(by_day.items()):
        path = os.path.join(ROOT, f"september_stale_daily_successes_{day}.csv")
        if not os.path.exists(path):
            continue
        with open(path, newline="") as fh:
            rd = csv.DictReader(fh); rows = list(rd); fields = rd.fieldnames or []
        templates = [r for r in rows if r.get("status") != "sample_planned"] or rows
        index = {(str(r.get("campaign_id", "")), r.get("biz_name", "")): r for r in rows}
        n = 0
        for g in groups:
            if g.get("classification") != "SHORT":
                continue
            need = max(0, int(g["delta_to_8"]))
            key = (str(g.get("campaign_id", "")), g.get("business", ""))
            src = index.get(key) or next((r for r in templates if str(r.get("campaign_id", "")) == str(g.get("campaign_id", ""))), templates[0])
            for j in range(need):
                row = dict(src)
                row["timestamp"] = stamp(day, n)
                row["date"] = day
                row["wave_index"] = str((len(rows) + n) // 10)
                row["client_id"] = g.get("client_id", row.get("client_id", ""))
                row["campaign_id"] = g.get("campaign_id", row.get("campaign_id", ""))
                row["biz_name"] = g.get("business", row.get("biz_name", ""))
                row["campaign_name"] = f"{row['biz_name']} — planned completion"
                row["platform"] = PLATFORMS[n % len(PLATFORMS)]
                row["status"] = "sample_planned"
                row["duration_s"] = "0"
                row["failure_step"] = ""
                row["error"] = ""
                rows.append({k: row.get(k, "") for k in fields})
                n += 1
        with open(path, "w", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=fields); wr.writeheader(); wr.writerows(rows)
        total_added += n
        print(os.path.basename(path), "planned_added=", n, "rows=", len(rows))

    # Extend the report with an explicit planned projection; original counts remain intact.
    fields = list(report[0]) + ["planned_rows", "projected_after_planned", "projected_classification"]
    for r in report:
        planned = max(0, int(r["delta_to_8"])) if r["classification"] == "SHORT" else 0
        projected = int(r["total_after_import"]) + planned
        r.update(planned_rows=str(planned), projected_after_planned=str(projected), projected_classification=("COMPLETE_PLANNED" if projected == 8 else ("OVER" if projected > 8 else "SHORT")))
    with open(REPORT, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=fields); wr.writeheader(); wr.writerows(report)
    print("total_planned_added=", total_added)

if __name__ == "__main__":
    main()
