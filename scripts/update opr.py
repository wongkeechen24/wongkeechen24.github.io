import json
from datetime import datetime, timezone
from pathlib import Path

import requests


API_URL = "https://api.bnm.gov.my/public/opr"

headers = {
    "Accept": "application/vnd.BNM.API.v1+json",
    "User-Agent": "Malaysia-OPR-Personal-App/1.0"
}

response = requests.get(API_URL, headers=headers, timeout=30)
response.raise_for_status()

payload = response.json()

records = payload.get("data", payload)

if isinstance(records, dict):
    records = [records]

if not records:
    raise RuntimeError("BNM API 没有返回 OPR 数据")

latest = records[0]

opr = (
    latest.get("opr")
    or latest.get("new_opr_level")
    or latest.get("value")
    or latest.get("rate")
)

date = (
    latest.get("date")
    or latest.get("effective_date")
    or latest.get("effectiveDate")
)

change = (
    latest.get("change_in_opr")
    or latest.get("change")
    or latest.get("changeInOPR")
)

if opr is None:
    raise RuntimeError(f"找不到 OPR 字段，实际资料：{latest}")

output = {
    "indicator": "OPR",
    "country": "Malaysia",
    "rate": float(opr),
    "date": date,
    "change": float(change) if change is not None else None,
    "source": "Bank Negara Malaysia",
    "source_url": API_URL,
    "updated_at": datetime.now(timezone.utc).isoformat(),
}

output_path = Path("data/opr.json")
output_path.parent.mkdir(parents=True, exist_ok=True)

output_path.write_text(
    json.dumps(output, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print(json.dumps(output, ensure_ascii=False, indent=2))
