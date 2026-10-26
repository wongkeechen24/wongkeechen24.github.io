"""Fetch the latest OPR from the BNM Open API and save it to data/opr.json.
Field names (date, change_in_opr, new_opr_level) were verified on 2026-10-25
from a real response. On any failure the old file is kept and the job fails."""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

URL = "https://api.bnm.gov.my/public/opr"

req = urllib.request.Request(
    URL,
    headers={"Accept": "application/vnd.BNM.API.v1+json", "User-Agent": "Mozilla/5.0"},
)

try:
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.loads(r.read().decode("utf-8"))
    d = payload["data"]
    out = {
        "opr": float(d["new_opr_level"]),
        "decision_date": d["date"],
        "change_in_opr": d["change_in_opr"],
        "bnm_last_updated": payload.get("meta", {}).get("last_updated"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": URL,
    }
except Exception as e:
    print("FAILED:", repr(e))
    sys.exit(1)

os.makedirs("data", exist_ok=True)
with open("data/opr.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("saved data/opr.json:", out)
