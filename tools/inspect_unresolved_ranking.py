#!/usr/bin/env python3
"""List attempted keyword/platform pairs that still lack a terminal result."""
import argparse
import csv
import glob
import json
from collections import Counter, defaultdict


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_glob")
    parser.add_argument("keyword_ids")
    parser.add_argument("--platform", default="")
    args = parser.parse_args()
    keyword_ids = set(json.load(open(args.keyword_ids)))
    rows = []
    for path in glob.glob(args.source_glob):
        with open(path, newline="", encoding="utf-8-sig") as stream:
            rows.extend(csv.DictReader(stream))
    relevant = []
    for row in rows:
        try:
            keyword_id = int(row.get("campaign_id") or 0) % 10000
        except ValueError:
            continue
        platform = (row.get("platform") or "").lower().strip()
        if keyword_id in keyword_ids and (not args.platform or platform == args.platform):
            relevant.append(row)
    terminal = {
        ((row.get("campaign_id") or "").strip(), (row.get("platform") or "").lower().strip())
        for row in relevant if (row.get("status") or "").lower() in {"success", "no_rank"}
    }
    attempts = defaultdict(list)
    for row in relevant:
        key = ((row.get("campaign_id") or "").strip(), (row.get("platform") or "").lower().strip())
        if key not in terminal:
            attempts[key].append(row)
    for key, values in sorted(attempts.items()):
        values.sort(key=lambda row: row.get("timestamp") or "")
        latest = values[-1]
        print(json.dumps({
            "campaign_id": key[0], "platform": key[1], "keyword": latest.get("keyword"),
            "biz_name": latest.get("biz_name"), "attempts": len(values),
            "statuses": dict(Counter((row.get("status") or "").lower() for row in values)),
            "latest_timestamp": latest.get("timestamp"), "latest_status": latest.get("status"),
            "latest_error": latest.get("error"), "latest_screenshot": latest.get("screenshot"),
            "latest_response_text": latest.get("response_text"),
        }, ensure_ascii=False))
    print(json.dumps({"unresolved_attempted_pairs": len(attempts)}))


if __name__ == "__main__":
    main()
