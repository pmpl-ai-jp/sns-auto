"""API費用を記録し、月の上限を超えたら止める"""
import json
from .common import ROOT, load, now

class BudgetExceeded(Exception):
    pass

def _path():
    d = ROOT / "data" / "cost"; d.mkdir(parents=True, exist_ok=True)
    return d / f"{now():%Y-%m}.json"

def spent():
    p = _path()
    return json.loads(p.read_text())["jpy"] if p.exists() else 0.0

def check_budget():
    S = load("config/settings.yaml")
    if spent() >= S["monthly_budget_jpy"]:
        raise BudgetExceeded(f"今月の上限 {S['monthly_budget_jpy']}円 に達したため停止")

def record(model, tin, tout, searches=0):
    S = load("config/settings.yaml"); pr = S["prices"][model]
    usd = (tin * pr["in"] + tout * pr["out"]) / 1e6 + searches * S.get("web_search_usd", 0.01)
    jpy = usd * S["usd_jpy"]
    p = _path(); d = json.loads(p.read_text()) if p.exists() else {"jpy": 0.0, "calls": 0}
    d["jpy"] = round(d["jpy"] + jpy, 4); d["calls"] += 1
    p.write_text(json.dumps(d))
