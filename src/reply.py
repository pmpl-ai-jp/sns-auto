"""返信係: 自分の投稿に付いた返信・コメントに、公式APIで返事をする（1日の上限つき）"""
import os, json, time, requests, datetime
from .common import iter_posts, ROOT, now, killed, load, setting
from .llm import generate_json
from .guard import check
from .budget import BudgetExceeded
TH = "https://graph.threads.net/v1.0"; IG = __import__("src.common", fromlist=["load"]).load("config/settings.yaml")["ig_graph_base"]
S = load("config/settings.yaml"); PR = load("config/profile.yaml")
# 自動で返さず、そのまま残す内容（お金・個別相談・攻撃的な内容など）
SKIP = ["いくら", "稼げ", "年収", "紹介して", "DM", "詐欺", "怪しい", "嘘", "ステマ", "訴"]

def state():
    p = ROOT / "data" / "replied.json"
    d = json.loads(p.read_text()) if p.exists() else {"ids": [], "count": {}}
    return p, d

def draft(post_text, comment):
    r = generate_json(f"""SNSの自分の投稿に付いた返信へ、短くお礼と補足を返します。
人物像: {S["persona"]}
自分の経験として話してよいのは次だけ: {PR.get("episodes")}
ルール: 120字以内。丁寧でフラット。宣伝・リンク・DMへの誘導・断定・数字の創作はしない。
答えられない質問なら、分からないと正直に書く。
自分の投稿: {post_text}
相手の返信: {comment}
JSON: {{"reply": "...", "should_reply": true/false}}""", 0.5)
    return r["reply"] if r.get("should_reply") and not check(r["reply"]) else None

def threads_replies(mid, tok):
    r = requests.get(f"{TH}/{mid}/replies", params={"fields": "id,text,username,is_reply_owned_by_me", "access_token": tok}, timeout=30)
    r.raise_for_status(); return r.json().get("data", [])

def threads_reply(to_id, text, uid, tok):
    """Threadsで返信する。下書きを作ってから少し待ち、公開する。公開に失敗したら間をあけて数回やり直す"""
    c = requests.post(f"{TH}/{uid}/threads", params={"media_type": "TEXT", "text": text, "reply_to_id": to_id, "access_token": tok}, timeout=60)
    if c.status_code >= 400: print("返信の下書き作成に失敗:", c.status_code, c.text[:400])
    c.raise_for_status()
    cid = c.json()["id"]
    last = None
    for wait in (6, 10, 20):                       # 下書きの準備ができるまで待つ（公開が早すぎると400になる）
        time.sleep(wait)
        r = requests.post(f"{TH}/{uid}/threads_publish", params={"creation_id": cid, "access_token": tok}, timeout=60)
        if r.status_code < 400: return r.json().get("id")
        last = r; print(f"返信の公開に失敗（{wait}秒待ったあと）:", r.status_code, r.text[:400])
    last.raise_for_status()

def ig_comments(mid, tok):
    r = requests.get(f"{IG}/{mid}/comments", params={"fields": "id,text,username", "access_token": tok}, timeout=30)
    r.raise_for_status(); return r.json().get("data", [])

def ig_reply(cid, text, tok):
    requests.post(f"{IG}/{cid}/replies", params={"message": text, "access_token": tok}, timeout=60).raise_for_status()

def main():
    if killed(): print("KILL_SWITCH ON: skip"); return
    p, st = state(); today = f"{now():%Y-%m-%d}"
    n = st["count"].get(today, 0)
    cutoff = now() - datetime.timedelta(days=7)
    try:
        for _, post in iter_posts():
            if post.get("status") != "published" or datetime.datetime.fromisoformat(post["published_at"]) < cutoff: continue
            body = post.get("text") or post.get("caption", "")
            if post["kind"] == "threads":
                items = [c for c in threads_replies(post["published_id"], os.environ["THREADS_TOKEN"]) if not c.get("is_reply_owned_by_me")]
            else:
                items = ig_comments(post["published_id"], os.environ["IG_TOKEN"])
            for c in items:
                if n >= setting("reply_per_day"): break
                if c["id"] in st["ids"]: continue
                st["ids"].append(c["id"])
                t = c.get("text", "")
                if not t or any(w in t for w in SKIP): continue
                rep = draft(body, t)
                if not rep: continue
                try:
                    if post["kind"] == "threads": threads_reply(c["id"], rep, os.environ["THREADS_USER_ID"], os.environ["THREADS_TOKEN"])
                    else: ig_reply(c["id"], rep, os.environ["IG_TOKEN"])
                    n += 1; print("replied", c["id"])
                except Exception as e:                       # 1件の失敗で全体を止めない。次の実行でもう一度試す
                    print("返信に失敗（次の実行で再試行）:", c["id"], str(e)[:200])
                    if c["id"] in st["ids"]: st["ids"].remove(c["id"])
    except BudgetExceeded as e:
        print(e)
    finally:
        st["count"] = {today: n}; st["ids"] = st["ids"][-3000:]
        p.write_text(json.dumps(st))

if __name__ == "__main__":
    main()
