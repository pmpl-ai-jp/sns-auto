"""1時間ごとに実行: 投稿時刻が来た approved の投稿を1件ずつ公開"""
import os, time, requests
from .common import load, now, iter_posts, save_post, killed

S = load("config/settings.yaml")
TH = "https://graph.threads.net/v1.0"
IG = __import__("src.common", fromlist=["load"]).load("config/settings.yaml")["ig_graph_base"]
from .common import in_warmup
SLOTS = {"threads": [7, 12, 18, 22], "instagram": [20]}  # Threadsは1日4本
if in_warmup(): SLOTS["threads"] = [7, 12, 18, 22]  # 立ち上げ期間中は1日4回  # JSTの投稿時刻

def post_threads(text, topic=""):
    """Threadsに投稿する。トピックを付けて失敗したときは、付けずにもう一度試す"""
    uid, tok = os.environ["THREADS_USER_ID"], os.environ["THREADS_TOKEN"]
    def create(with_topic):
        params = {"media_type": "TEXT", "text": text, "access_token": tok}
        if with_topic and topic: params["topic_tag"] = topic
        return requests.post(f"{TH}/{uid}/threads", params=params, timeout=60)
    c = create(True)
    if c.status_code >= 400 and topic:
        print("トピック付きで失敗したため、トピックなしで再試行:", c.text[:200]); c = create(False)
    c.raise_for_status(); time.sleep(5)
    r = requests.post(f"{TH}/{uid}/threads_publish", params={"creation_id": c.json()["id"], "access_token": tok}, timeout=60)
    r.raise_for_status(); return r.json()["id"]

def _wait(cid, tok):
    for _ in range(20):
        s = requests.get(f"{IG}/{cid}", params={"fields": "status_code", "access_token": tok}, timeout=30).json()
        if s.get("status_code") == "FINISHED": return
        time.sleep(5)
    raise RuntimeError(f"container not ready: {cid}")

def post_instagram(images, caption):
    uid, tok = os.environ["IG_USER_ID"], os.environ["IG_TOKEN"]
    base = S["public_base_url"].rstrip("/")
    children = []
    for img in images:
        for k in range(3):                     # 画像の読み込みに失敗することがあるので、間をあけて3回まで試す
            r = requests.post(f"{IG}/{uid}/media", params={"image_url": f"{base}/{img}", "is_carousel_item": "true", "access_token": tok}, timeout=60)
            if r.status_code < 400: break
            print(f"画像の登録に失敗（{img}、{k+1}回目）:", r.status_code, r.text[:400])   # Instagramが返した理由をログに出す
            time.sleep(20)
        r.raise_for_status(); children.append(r.json()["id"])
    for c in children: _wait(c, tok)
    r = requests.post(f"{IG}/{uid}/media", params={"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption, "access_token": tok}, timeout=60)
    r.raise_for_status(); cid = r.json()["id"]; _wait(cid, tok)
    r = requests.post(f"{IG}/{uid}/media_publish", params={"creation_id": cid, "access_token": tok}, timeout=60)
    r.raise_for_status(); return r.json()["id"]

def trip_if_failing():
    """直近3件が連続でエラーなら、自動でKILL_SWITCHをONにして止める"""
    from .common import ROOT
    errs = [p for _, p in iter_posts() if p["status"] in ("published", "error")]
    errs.sort(key=lambda p: p.get("published_at") or p["created"])
    if len(errs) >= 2 and all(p["status"] == "error" for p in errs[-2:]):  # 今回の分を含めて3連続
        (ROOT / "config/KILL_SWITCH").write_text("ON\n"); print("連続エラーのため停止")

def main():
    """その日の公開時刻を過ぎていて、まだ公開していない枠があれば1件公開する。
    GitHubの自動実行が遅れたり飛ばされたりしても、次に動いたときに追いつく"""
    if killed(): print("KILL_SWITCH ON: skip"); return
    t = now(); today = t.date().isoformat()
    for kind, slots in SLOTS.items():
        due = [h for h in slots if h <= t.hour]                 # もう時刻を過ぎた枠の数
        posts = [p for _, p in iter_posts() if p["kind"] == kind]
        done = sum(1 for p in posts if p.get("status") == "published" and str(p.get("published_at", "")).startswith(today))
        if done >= len(due): continue
        for path, post in iter_posts():
            if post["kind"] == kind and post["status"] == "approved" and post["created"][:10] <= today:
                try:
                    pid = post_threads(post["text"], post.get("topic", "")) if kind == "threads" else post_instagram(post["images"], post["caption"])
                    post.update(status="published", published_id=pid, published_at=now().isoformat())
                except Exception as e:
                    post.update(status="error", error=str(e)[:500])
                    trip_if_failing()
                save_post(post); print(post["id"], post["status"]); break

if __name__ == "__main__":
    main()
