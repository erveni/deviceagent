#!/usr/bin/env python3
"""Write rows from a completed consolidation that were not in an earlier import."""
import argparse
import csv
from pathlib import Path


def key(row):
    return ((row.get("campaign_id") or "").strip(),
            (row.get("platform") or "").strip().lower())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prior", type=Path)
    parser.add_argument("completed", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    with args.prior.open(newline="", encoding="utf-8-sig") as stream:
        prior_rows = list(csv.DictReader(stream))
    with args.completed.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        completed_rows = list(reader)

    prior_keys = {key(row) for row in prior_rows}
    supplemental = [row for row in completed_rows if key(row) not in prior_keys]
    supplemental_keys = [key(row) for row in supplemental]
    if len(supplemental_keys) != len(set(supplemental_keys)):
        raise SystemExit("duplicate campaign/platform key in supplemental output")
    if prior_keys.intersection(supplemental_keys):
        raise SystemExit("supplemental output overlaps the prior import")
    if any((row.get("status") or "").lower() != "success" for row in supplemental):
        raise SystemExit("supplemental output contains a non-success row")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(supplemental)
    print(f"prior={len(prior_rows)} completed={len(completed_rows)} supplemental={len(supplemental)}")
    print(f"zero_overlap={not bool(prior_keys.intersection(supplemental_keys))} output={args.output}")


if __name__ == "__main__":
    main()
