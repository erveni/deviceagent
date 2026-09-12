#!/usr/bin/env python3
"""Build an isolated, read-only ranking catalog for priority clients 331-334."""
from __future__ import annotations

import json
import ssl
import subprocess
import urllib.request
from pathlib import Path

import certifi


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "ranking_priority_clients_331_334_20260911"
CLIENT_IDS = (331, 332, 333, 334)
BUSINESS_IDS = (365, 366, 367, 368)
KEYWORD_IDS = tuple(range(5231, 5251))
HARKER_ADDRESS = "305 Miller's Crossing, Harker Heights, TX 76548"


def main() -> None:
    secret = json.loads(subprocess.check_output([
        "aws", "secretsmanager", "get-secret-value", "--secret-id", "aeo-admin/prod",
        "--profile", "aeo-admin", "--region", "us-east-1", "--query", "SecretString",
        "--output", "text",
    ], text=True))
    context = ssl.create_default_context(cafile=certifi.where())

    def get(path: str, *, bearer: bool = False):
        headers = ({"Authorization": "Bearer " + secret["READ_API_TOKEN"]} if bearer
                   else {"X-Executor-Token": secret["EXECUTOR_TOKEN"]})
        request = urllib.request.Request(
            "https://jjm59vpn3y.us-east-1.awsapprunner.com" + path, headers=headers)
        with urllib.request.urlopen(request, timeout=120, context=context) as response:
            return json.load(response)

    clients = [get(f"/api/clients/{client_id}") for client_id in CLIENT_IDS]
    all_businesses = get("/api/businesses")
    businesses = [business for business in all_businesses if business.get("id") in BUSINESS_IDS]
    keywords = []
    history = []
    for business in businesses:
        keywords.extend(get(
            f"/api/keywords?businessId={business['id']}&includeLocked=true"))
        report = get(
            f"/api/ranking-reports?businessId={business['id']}&limit=1000", bearer=True)
        if report.get("meta", {}).get("total") != len(report.get("data", [])):
            raise RuntimeError(f"Incomplete ranking history for business {business['id']}")
        history.extend(report["data"])

    if tuple(sorted(client["id"] for client in clients)) != CLIENT_IDS:
        raise RuntimeError("Priority client set changed")
    if tuple(sorted(business["id"] for business in businesses)) != BUSINESS_IDS:
        raise RuntimeError("Priority business set changed")
    if tuple(sorted(keyword["id"] for keyword in keywords)) != KEYWORD_IDS:
        raise RuntimeError("Priority keyword set changed")
    if history:
        raise RuntimeError("Priority clients already have ranking history")
    if not all(keyword.get("isActive") and keyword.get("keywordText") for keyword in keywords):
        raise RuntimeError("Priority keyword is inactive or missing text")

    # Admin currently contains a four-digit ZIP. The City of Harker Heights
    # publishes this exact street address as 76548. Correct only this isolated
    # run snapshot; do not mutate the admin record.
    business_366 = next(b for b in businesses if b["id"] == 366)
    if business_366.get("publishedAddress") != "305 Miller's Crossing, Harker Heights, TX 7654":
        raise RuntimeError("Unexpected client 332 source address; review before running")
    business_366["publishedAddress"] = HARKER_ADDRESS

    campaign_addr = {}
    for keyword in keywords:
        business = next(b for b in businesses if b["id"] == keyword["businessId"])
        campaign_addr[str(keyword["aeoPlanId"])] = business["publishedAddress"]

    OUT.mkdir(exist_ok=False)
    catalog = OUT / "catalog"
    catalog.mkdir()
    payloads = {
        "clients_admin.json": clients,
        "biz_admin.json": businesses,
        "kw_admin.json": keywords,
        "rr_admin.json": history,
        "campaign_addr.json": campaign_addr,
    }
    for name, payload in payloads.items():
        (catalog / name).write_text(json.dumps(payload, indent=2) + "\n")
    (OUT / "keyword_ids.json").write_text(json.dumps(KEYWORD_IDS, indent=2) + "\n")
    (OUT / "scope.json").write_text(json.dumps({
        "client_ids": CLIENT_IDS,
        "business_ids": BUSINESS_IDS,
        "keyword_ids": KEYWORD_IDS,
        "platforms": ["chatgpt", "gemini", "copilot"],
        "pair_count": len(KEYWORD_IDS) * 3,
        "target_date": "2026-09-11",
        "admin_writes": False,
        "client_332_snapshot_address": HARKER_ADDRESS,
    }, indent=2) + "\n")
    print(json.dumps({"clients": len(clients), "businesses": len(businesses),
                      "keywords": len(keywords), "pairs": len(KEYWORD_IDS) * 3,
                      "output": str(OUT)}))


if __name__ == "__main__":
    main()
