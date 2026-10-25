"""BNM API probe: saves RAW responses so we can verify fields before building.
Endpoint paths and Accept header are UNVERIFIED (taken from third-party docs),
so every attempt and its HTTP status is recorded, including failures."""
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = "https://api.bnm.gov.my/public"
ENDPOINTS = ["opr", "base-rate"]
ACCEPTS = ["application/vnd.BNM.API.v1+json", "application/json"]


def get(url, accept):
    req = urllib.request.Request(
        url, headers={"Accept": accept, "User-Agent": "Mozilla/5.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # network error, timeout, DNS, etc.
        return None, str(e)


out = {"fetched_at": datetime.now(timezone.utc).isoformat(), "results": []}

for ep in ENDPOINTS:
    for accept in ACCEPTS:
        status, body = get(f"{BASE}/{ep}", accept)
        out["results"].append(
            {"endpoint": ep, "accept": accept, "status": status, "body": body[:200000]}
        )
        print(f"[{ep}] accept={accept} status={status}")
        print(body[:400].replace("\n", " "))
        print("-" * 40)
        if status == 200:
            break

os.makedirs("data", exist_ok=True)
with open("data/bnm_probe.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("saved data/bnm_probe.json")
