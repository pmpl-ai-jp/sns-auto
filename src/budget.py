"""API費用を記録する（noteの運用ログ用）。月の上限での自動停止は、設定で止めるか選べる"""
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
    """budget_stop が true のときだけ、上限で止める（今は false: 止めずに記録だけ）"""
    S = load("config/settings.yaml")
    if S.get("budget_stop", False) and spent() >= S["monthly_budget_jpy"]:
        raise BudgetExceeded(f"今月の上限 {S['monthly_budget_jpy']}円 に達したため停止")

def record(model, tin, tout, searches=0):
    """月の合計に加えて、日別・モデル別の金額（ドルと円）と回数を残す"""
    S = load("config/settings.yaml"); pr = S["prices"][model]
    usd = (tin * pr["in"] + tout * pr["out"]) / 1e6 + searches * S.get("web_search_usd", 0.01)
    jpy = usd * S["usd_jpy"]
    p = _path(); d = json.loads(p.read_text()) if p.exists() else {"jpy": 0.0, "calls": 0}
    d["jpy"] = round(d["jpy"] + jpy, 4); d["calls"] += 1
    d["usd"] = round(d.get("usd", 0.0) + usd, 6)
    day = f"{now():%Y-%m-%d}"
    dd = d.setdefault("days", {}).setdefault(day, {"usd": 0.0, "jpy": 0.0, "calls": 0})
    dd["usd"] = round(dd["usd"] + usd, 6); dd["jpy"] = round(dd["jpy"] + jpy, 2); dd["calls"] += 1
    md = d.setdefault("models", {}).setdefault(model, {"usd": 0.0, "calls": 0})
    md["usd"] = round(md["usd"] + usd, 6); md["calls"] += 1
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1))

def cost_summary(days=7):
    """noteの運用ログ用: 直近 days 日の金額（日別）と、今月の合計・モデル別"""
    import datetime
    S = load("config/settings.yaml"); rate = S["usd_jpy"]
    out_days, week_usd, week_calls = {}, 0.0, 0
    for i in range(days - 1, -1, -1):
        dt = now() - datetime.timedelta(days=i)
        p = ROOT / "data" / "cost" / f"{dt:%Y-%m}.json"
        d = json.loads(p.read_text()) if p.exists() else {}
        v = d.get("days", {}).get(f"{dt:%Y-%m-%d}")
        if v:
            out_days[f"{dt:%m/%d}"] = {"ドル": round(v["usd"], 3), "円": round(v["jpy"]), "AI呼び出し回数": v["calls"]}
            week_usd += v["usd"]; week_calls += v["calls"]
    p = _path(); m = json.loads(p.read_text()) if p.exists() else {}
    return {"今週の合計": {"ドル": round(week_usd, 2), "円": round(week_usd * rate), "AI呼び出し回数": week_calls},
            "日別": out_days or "日別の記録は今週から開始（まだなし）",
            "今月の合計": {"ドル": round(m.get("usd", 0), 2), "円": round(m.get("jpy", 0))},
            "モデル別（今月）": {k: round(v["usd"], 3) for k, v in m.get("models", {}).items()},
            "円の計算": f"1ドル={rate}円（為替・消費税・カード手数料込みの実際の請求に合わせた目安）"}
