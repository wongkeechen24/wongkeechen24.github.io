import csv
import io
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

FRED_KEY = os.environ.get("FRED_API_KEY", "")
COT_URL = "https://publicreporting.cftc.gov/resource/gpe5-46if.json?"


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
    return [(o["date"], float(o["value"])) for o in data["observations"]
            if o["value"] not in (".", "")]  # newest first


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


def latest(series):
    cur = series[0]
    prev = series[1] if len(series) > 1 else None
    return {"value": round(cur[1], 2),
            "prev": round(prev[1], 2) if prev else None,
            "asof": cur[0]}


def yoy(series):
    d = dict(series)

    def at(date):
        year, rest = date.split("-", 1)
        ago = "%d-%s" % (int(year) - 1, rest)
        if ago in d:
            return round((d[date] / d[ago] - 1) * 100, 2)
        return None

    dates = [s[0] for s in series]
    return {"value": at(dates[0]),
            "prev": at(dates[1]) if len(dates) > 1 else None,
            "asof": dates[0]}


def cot():
    q = urllib.parse.urlencode({
        "$where": "market_and_exchange_names like 'EURO FX - CHICAGO%'",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": 52,
    })
    rows = json.loads(get(COT_URL + q))
    if not rows:
        raise ValueError("no COT rows returned")

    def num(r, *names):
        for n in names:
            if n in r:
                return float(r[n])
        raise KeyError("missing field, available: " + ",".join(sorted(r)))

    lev = [num(r, "lev_money_positions_long", "lev_money_positions_long_all")
           - num(r, "lev_money_positions_short", "lev_money_positions_short_all") for r in rows]
    am = [num(r, "asset_mgr_positions_long", "asset_mgr_positions_long_all")
          - num(r, "asset_mgr_positions_short", "asset_mgr_positions_short_all") for r in rows]
    oi = num(rows[0], "open_interest_all")

    def block(vals):
        pct = round(100.0 * sum(1 for x in vals if x < vals[0]) / len(vals))
        return {"net": int(vals[0]),
                "change": int(vals[0] - vals[1]) if len(vals) > 1 else None,
                "pct_of_oi": round(100.0 * vals[0] / oi, 1),
                "percentile_1y": pct}

    return {"asof": rows[0]["report_date_as_yyyy_mm_dd"][:10],
            "open_interest": int(oi), "weeks": len(rows),
            "leveraged_funds": block(lev), "asset_managers": block(am)}


result = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds")}

# 1. Market direction
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

# 2. Macro data
macro = {}
try:
    macro["usd"] = {
        "unemployment": latest(fred("UNRATE", 3)),
        "cpi_yoy": yoy(fred("CPIAUCSL", 30)),
        "core_cpi_yoy": yoy(fred("CPILFESL", 30)),
    }
except Exception as e:
    macro["usd"] = {"error": str(e)}
try:
    macro["eur"] = {
        "unemployment": latest(ecb("LFSI", "M.U2.S.UNEHRT.TOTAL0.15_74.T", 3)),
        "cpi_yoy": latest(ecb("ICP", "M.U2.N.000000.4.ANR", 3)),
        "core_cpi_yoy": latest(ecb("ICP", "M.U2.N.XEF000.4.ANR", 3)),
    }
except Exception as e:
    macro["eur"] = {"error": str(e)}
result["macro"] = macro

# 4. Big money (COT, weekly)
try:
    result["cot"] = cot()
except Exception as e:
    result["cot"] = {"error": str(e)}

os.makedirs("data", exist_ok=True)
with open("data/lean.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(json.dumps(result, ensure_ascii=False, indent=2))
