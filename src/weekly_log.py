"""週1回: 運用ログ（note下書き用Markdown）を自動生成。公開は人が行う"""
import json, datetime
from collections import Counter
from .common import iter_posts, now, ROOT, load
from .llm import generate_json

def main():
    S = load("config/settings.yaml"); P = load("config/profile.yaml")
    from .budget import spent
    posts = [p for _, p in iter_posts()]
    week_ago = now() - datetime.timedelta(days=7)
    recent = [p for p in posts if datetime.datetime.fromisoformat(p["created"]) >= week_ago]
    st = Counter(p["status"] for p in recent)
    pub = [p for p in recent if p["status"] == "published"]
    # 投稿ごとの反応（分析係が取得した数字だけを使う）
    rows = [{"日付": p["created"][:10], "媒体": p["kind"], "テーマ": p.get("stage"), "ネタ": p.get("idea"),
             "反応": p.get("metrics"), "スコア": round(p.get("score", 0), 4)} for p in pub]
    rejected = [{"ネタ": p.get("idea"), "止まった理由": (p.get("issues") or [])[:2]} for p in recent if p["status"] == "rejected"]
    errors = [p.get("error") for p in recent if p["status"] == "error"][-5:]
    data = {"期間": f"{week_ago:%m/%d}〜{now():%m/%d}", "状態の内訳": dict(st), "公開した投稿": rows,
            "チェックで止めた投稿": rejected, "エラー": errors, "今月のAI費用(円)": round(spent())}
    out = generate_json(f"""AIエージェントでSNS運用を自動化している人の、週1回の運用ログをnote用に書いてください。
筆者: {S["persona"]}
筆者が一人称で語ってよい経験: {P.get("episodes")}
今週のデータ（数字はここにあるものだけを使う。ない数字は書かない）:
{json.dumps(data, ensure_ascii=False)}

書き方:
- 冒頭で今週の結論を1〜2文で言い切る（ロジカルシンキング：結論→理由→具体例）
- 構成: 今週の数字 / 伸びた投稿と、その理由の仮説 / 止まった投稿と、仕組みで直したこと / 来週試すこと / 今週の費用
- 「理由」はデータからの仮説として書き、断定しない。投稿が少ない週は「まだ判断できない」と正直に書く
- 読者（AIで仕事を自動化したい会社員）が自分でも使える学びを、1つ以上入れる
- 煽らない。「必ず」「稼げる」は使わない。収益の数字は書かない
- 最後に『本記事はAIを使って作成し、筆者が確認しています』と書く
JSON: {{"title": "...", "markdown": "見出し付き本文"}}""", 0.5, role="planner", max_tokens=8000)
    d = ROOT / "note_drafts"; d.mkdir(exist_ok=True)
    p = d / f"{now():%Y%m%d}_weekly.md"
    p.write_text(f"# {out['title']}\n\n{out['markdown']}\n", encoding="utf-8"); print(p)

if __name__ == "__main__":
    main()
