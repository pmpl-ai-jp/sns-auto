"""週1回: 運用ログ（note下書き用Markdown）を自動生成。公開は人が行う"""
from collections import Counter
from .common import iter_posts, now, ROOT
from .llm import generate_json

def main():
    posts = [p for _, p in iter_posts()]
    from .budget import spent
    st = Counter(p["status"] for p in posts); kinds = Counter(p["kind"] for p in posts if p["status"] == "published")
    errors = [p["error"] for p in posts if p["status"] == "error"][-5:]
    stats = f"公開: {dict(kinds)} / 状態: {dict(st)} / 直近のエラー: {errors} / 今月のAI費用: {round(spent())}円"
    out = generate_json(f"""SNS自動運用の週次ログをnote用に書く。煽らず、事実と失敗を正直に。数字は次のデータのみ使う:
{stats}
JSON: {{"title": "...", "markdown": "見出し付き本文。最後に『本記事はAIを使って作成し、筆者が確認しています』と書く"}}""", 0.5)
    d = ROOT / "note_drafts"; d.mkdir(exist_ok=True)
    p = d / f"{now():%Y%m%d}_weekly.md"
    p.write_text(f"# {out['title']}\n\n{out['markdown']}\n", encoding="utf-8"); print(p)

if __name__ == "__main__":
    main()
