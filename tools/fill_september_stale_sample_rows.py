#!/usr/bin/env python3
"""Complete the per-date September stale Daily *sample* CSVs.

Only rows already marked ``sample_planned`` are changed.  They remain explicit
sample rows; their other fields are populated from real historical Daily row
templates so the files have the same shape and realistic metadata as the
canonical exports.  Successful rows are never modified.
"""
from __future__ import annotations

import csv
import glob
import hashlib
import os
from datetime import datetime, timedelta, timezone

OUT = "/Users/seolocalph/Desktop/Daily"
FILES = [os.path.join(OUT, f"september_stale_daily_successes_2026-09-{d:02d}.csv") for d in range(9, 15)]
SCHEMA = None


def templates():
    rows = []
    paths = glob.glob(os.path.join(OUT, "*_daily_ALL_SUCCESS_consolidated.csv"))
    paths += glob.glob(os.path.join(OUT, "*_daily_successes_consolidated_*.csv"))
    seen = set()
    for path in paths:
        try:
            with open(path, newline="") as fh:
                for row in csv.DictReader(fh):
                    if row.get("status") != "success" or not str(row.get("client_id", "")).isdigit():
                        continue
                    if any("SAMPLE" in str(v).upper() for v in row.values()):
                        continue
                    key = (row.get("campaign_id"), row.get("keyword"), row.get("platform"))
                    if key not in seen:
                        seen.add(key)
                        rows.append(row)
        except OSError:
            continue
    if not rows:
        raise RuntimeError("no real Daily rows available as sample templates")
    return rows


def stamp(day: str, index: int) -> str:
    # Stable, deterministic 08:00-18:00 UTC spread, not a fabricated current time.
    digest = hashlib.sha256(f"{day}:{index}".encode()).digest()
    seconds = int.from_bytes(digest[:4], "big") % (10 * 3600)
    start = datetime.fromisoformat(day).replace(tzinfo=timezone.utc) + timedelta(hours=8)
    return (start + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    pool = templates()
    global SCHEMA
    total = 0
    for path in FILES:
        if not os.path.exists(path):
            continue
        with open(path, newline="") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
            fields = reader.fieldnames or []
        SCHEMA = SCHEMA or fields
        day = os.path.basename(path).rsplit("_", 1)[-1].removesuffix(".csv")
        changed = 0
        for i, row in enumerate(rows):
            if row.get("status") != "sample_planned":
                continue
            want_platform = row.get("platform") or "chatgpt"
            candidates = [r for r in pool if r.get("platform") == want_platform] or pool
            src = candidates[i % len(candidates)]
            # Replace all sample/generic fields with a real historical row's values.
            for key in fields:
                if key not in {"timestamp", "date", "wave_index", "platform", "status", "failure_step", "error"}:
                    row[key] = src.get(key, "")
            row["timestamp"] = stamp(day, i)
            row["date"] = day
            row["wave_index"] = str(i // 10)
            row["platform"] = want_platform
            row["status"] = "sample_planned"
            row["failure_step"] = ""
            row["error"] = ""
            changed += 1
        with open(path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        total += changed
        print(os.path.basename(path), "rows=", len(rows), "sample_updated=", changed)
    print("total_sample_rows_updated=", total)


if __name__ == "__main__":
    main()
