"""分析係: 公開済み投稿の反応を取得し、テーマごとの成績を data/performance.json に書く"""
import os, json, requests
from collections import defaultdict
from .common import iter_posts, save_post, ROOT, now
TH = "https://graph.threads.net/v1.0"; IG = "https://graph.instagram.com/v21.0"

def threads_metrics(mid):
    r = requests.get(f"{TH}/{mid}/insights", params={"metric": "views,likes,replies,reposts,quotes",
                     "access_token": os.environ["THREADS_TOKEN"]}, timeout=30)
    r.raise_for_status()
    return {d["name"]: d["values"][0]["value"] for d in r.json()["data"]}

def ig_metrics(mid):
    r = requests.get(f"{IG}/{mid}/insights", params={"metric": "reach,saved,shares,likes,comments",
                     "access_token": os.environ["IG_TOKEN"]}, timeout=30)
    r.raise_for_status()
    return {d["name"]: d["values"][0]["value"] for d in r.json()["data"]}

def score(kind, m):
    if kind == "threads":  # 会話を重視
        v = max(m.get("views", 0), 1)
        return (m.get("replies", 0) * 3 + m.get("reposts", 0) * 2 + m.get("quotes", 0) * 2 + m.get("likes", 0)) / v
    v = max(m.get("reach", 0), 1)  # 保存・シェアを重視
    return (m.get("saved", 0) * 3 + m.get("shares", 0) * 3 + m.get("comments", 0) * 2 + m.get("likes", 0)) / v

def main():
    agg = defaultdict(list); top = []
    for _, p in iter_posts():
        if p.get("status") != "published": continue
        try:
            m = threads_metrics(p["published_id"]) if p["kind"] == "threads" else ig_metrics(p["published_id"])
        except Exception as e:
            print("skip", p["id"], e); continue
        p["metrics"] = m; p["score"] = score(p["kind"], m); save_post(p)
        agg[p["stage"]].append(p["score"])
        top.append((p["score"], p.get("text") or p.get("caption", "")))
    perf = {k: sum(v) / len(v) for k, v in agg.items()}
    top = [t for _, t in sorted(top, reverse=True)[:5]]
    (ROOT / "data" / "performance.json").write_text(json.dumps(
        {"updated": now().isoformat(), "stage_score": perf, "top_posts": top}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(perf)

if __name__ == "__main__":
    main()
