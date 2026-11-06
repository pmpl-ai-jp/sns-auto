"""週1回: 運用ログ（note下書き用Markdown）を自動生成。公開は人が行う"""
import json, datetime, os, re, requests
from collections import Counter
from .common import iter_posts, now, ROOT, load
from .llm import generate_json

def main():
    S = load("config/settings.yaml"); P = load("config/profile.yaml")
    from .budget import spent, cost_summary
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
            "チェックで止めた投稿": rejected, "エラー": errors, "AI費用": cost_summary()}
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
- 「今週の費用」では、AI費用の今週の合計（ドルと円）と今月の合計を書く。日別の記録があれば、多かった日と理由の仮説を1つ書く。円は目安であることを一言添える
- 煽らない。「必ず」「稼げる」は使わない。収益の数字は書かない
- 最後に『本記事はAIを使って作成し、筆者が確認しています』と書く
JSON: {{"title": "...", "markdown": "見出し付き本文"}}""", 0.5, role="planner", max_tokens=8000)
    d = ROOT / "note_drafts"; d.mkdir(exist_ok=True)
    stem = f"{now():%Y%m%d}_weekly"
    (d / f"{stem}.md").write_text(f"# {out['title']}\n\n{out['markdown']}\n", encoding="utf-8")
    text = to_note_text(out["markdown"])
    (d / f"{stem}.txt").write_text(text, encoding="utf-8")
    from .render import render_note_header
    img = d / f"{stem}_header.jpg"; render_note_header(out["title"], img)
    notify(out["title"], text, f"note_drafts/{stem}_header.jpg")
    print(d / f"{stem}.txt")

def to_note_text(md):
    """noteにそのまま貼れる形にする（Markdownの記号を外し、表は箇条書きにする）"""
    lines = []
    for line in md.splitlines():
        s = line.strip()
        if re.match(r"^\|?\s*:?-{3,}", s): continue                    # 表の区切り行
        if s.startswith("|") and s.endswith("|"):                       # 表の行 → 箇条書き
            cells = [c.strip() for c in s.strip("|").split("|")]
            lines.append("・" + "：".join(c for c in cells if c)); continue
        m = re.match(r"^(#{1,6})\s+(.*)", s)
        if m: lines += ["", "■ " + m.group(2), ""]; continue             # 見出し → ■
        s = re.sub(r"^[-*]\s+", "・", s)                                 # 箇条書き
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)                          # 太字の記号を外す
        s = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1（\2）", s)                 # リンク
        lines.append(s)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"

def notify(title, text, img_path):
    """GitHubのIssueを作って知らせる（GitHubからメール通知が届く）。失敗しても止めない"""
    repo, tok = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not (repo and tok): return
    S = load("config/settings.yaml"); base = S["public_base_url"].rstrip("/")
    body = (f"今週の運用ログの下書きができました。\n\n"
            f"**公開の手順（5分）**\n1. 下の本文を読んで、気になるところを直す\n"
            f"2. noteの「投稿」→「テキスト」に、タイトルと本文を貼る（「■」の行は見出しにする）\n"
            f"3. 見出し画像をダウンロードして設定する：{base}/{img_path}\n4. 公開したら、このIssueを閉じる\n\n"
            f"![見出し画像]({base}/{img_path})\n\n---\n**タイトル**\n```\n{title}\n```\n**本文**\n```\n{text}\n```")
    try:
        requests.post(f"https://api.github.com/repos/{repo}/issues", timeout=30,
                      headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"},
                      json={"title": f"【note下書き】{title}", "body": body, "labels": ["note"]}).raise_for_status()
        print("Issueで通知しました")
    except Exception as e:
        print("通知をスキップ:", e)

if __name__ == "__main__":
    main()
