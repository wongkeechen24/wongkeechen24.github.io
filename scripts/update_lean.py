import csv
import io
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

FRED_KEY = os.environ.get("FRED_API_KEY", "")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "lean-bot"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def fred(series, n=12):
    q = urllib.parse.urlencode({
        "series_id": series, "api_key": FRED_KEY, "file_type": "json",
        "sort_order": "desc", "limit": n,
    })
    data = json.loads(get("https://api.stlouisfed.org/fred/series/observations?" + q))
    out = [(o["date"], float(o["value"])) for o in data["observations"]
           if o["value"] not in (".", "")]
    return out  # newest first


def ecb(flow, key, n=12):
    url = ("https://data-api.ecb.europa.eu/service/data/%s/%s"
           "?lastNObservations=%d&format=csvdata" % (flow, key, n))
    rows = csv.DictReader(io.StringIO(get(url)))
    out = [(r["TIME_PERIOD"], float(r["OBS_VALUE"])) for r in rows if r.get("OBS_VALUE")]
    out.sort(reverse=True)
    return out  # newest first


def lean(bp):
    if bp >= 25:
        return "hawkish"
    if bp <= -25:
        return "dovish"
    return "neutral"


def side(policy_series, yield_series):
    policy = policy_series[0][1]
    now = [s[0][1] for s in yield_series]
    prev = [s[min(5, len(s) - 1)][1] for s in yield_series]
    score_now = (sum(now) / len(now) - policy) * 100
    score_prev = (sum(prev) / len(prev) - policy) * 100
    return {
        "asof": max(s[0][0] for s in yield_series),
        "policy_rate": round(policy, 3),
        "short_yield_6m": round(now[0], 3),
        "yield_2y": round(now[1], 3),
        "score_bp": round(score_now, 1),
        "score_5d_ago_bp": round(score_prev, 1),
        "change_bp": round(score_now - score_prev, 1),
        "lean": lean(score_now),
    }


result = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds")}

try:
    result["usd"] = side(fred("DFF"), [fred("DGS6MO"), fred("DGS2")])
except Exception as e:
    result["usd"] = {"error": str(e)}

try:
    result["eur"] = side(
        ecb("FM", "B.U2.EUR.4F.KR.DFR.LEV"),
        [ecb("YC", "B.U2.EUR.4F.G_N_C.SV_C_YM.SR_6M"),
         ecb("YC", "B.U2.EUR.4F.G_N_C.SV_C_YM.SR_2Y")],
    )
except Exception as e:
    result["eur"] = {"error": str(e)}

if "score_bp" in result["usd"] and "score_bp" in result["eur"]:
    diff = result["usd"]["score_bp"] - result["eur"]["score_bp"]
    result["relative"] = {
        "usd_minus_eur_bp": round(diff, 1),
        "reading": ("USD more hawkish than EUR" if diff >= 15 else
                    "USD more dovish than EUR" if diff <= -15 else "about balanced"),
    }

os.makedirs("data", exist_ok=True)
with open("data/lean.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(json.dumps(result, ensure_ascii
