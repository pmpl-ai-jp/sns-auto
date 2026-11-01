"""毎朝実行: リサーチ係 → 企画係 → 執筆係 → チェック係 の順に動き、当日分を queue/ に保存"""
import random, json
from .common import load, now, save_post, killed, ROOT, in_warmup, setting
from .llm import generate_json
from .guard import check, apply_pr, logic_check, design_check, G
from .render import render_carousel
from .budget import BudgetExceeded

S = load("config/settings.yaml"); PR = load("config/profile.yaml")
T = load("data/topics.yaml")["stages"]
FACTS = load("data/facts.yaml")["facts"] or []
AFF = [a for a in (load("data/affiliates.yaml")["affiliates"] or []) if a.get("active")]
FACTS_TEXT = "\n".join(f["text"].format(**f.get("value", {})) for f in FACTS)

def perf():
    p = ROOT / "data" / "performance.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"stage_score": {}, "top_posts": []}

def weights():
    """企画係: 基本の割合に、成績の良いテーマを最大1.5倍まで上乗せ（悪くても0.7倍まで）"""
    sc = perf()["stage_score"]; avg = (sum(sc.values()) / len(sc)) if sc else 0
    w = {}
    for k, v in T.items():
        r = v["ratio"]
        if v.get("affiliate") and (in_warmup() or not [a for a in AFF if a["stage"] == k]): r = 0  # 立ち上げ期間中・案件なしならPRテーマは出さない  # 提携案件がなければPRテーマは出さない
        if avg and k in sc: r *= min(1.5, max(0.7, sc[k] / avg))
        w[k] = r
    return w

def research():
    """リサーチ係: 今日のネタ候補を出す（外部取得はせず、テーマ例と過去の伸びた投稿から発想）"""
    p = perf()
    return generate_json(f"""次の人物がSNSで発信します。今日のネタ候補を8個出してください。
人物像: {S["persona"]}
この人の経歴（年数や順番はここに書かれたものだけを使う。推測で数字を作らない）:
{json.dumps(PR.get("profile", {}), ensure_ascii=False)}
各ネタは「誰の・どんな悩みに・何を持ち帰ってもらうか」が分かる1行にする。
テーマ一覧: {json.dumps({k: v["name"] for k, v in T.items()}, ensure_ascii=False)}
最近伸びた投稿（同じ型で切り口を変える参考に）: {p["top_posts"][:3]}
JSON: {{"ideas": [{{"stage": "テーマのキー", "idea": "1行"}}]}}""", 0.9)["ideas"]

BASE = """あなたは日本語のSNS発信者です。人物像: {persona}
テーマ: {stage}
ネタ: {idea}
ルール:
- 結論から書き、理由を2〜3個に分け、事実と意見を分ける（ロジカルシンキング）
- 結論は「〜することがある」のようにぼかさず、読者がとる行動で言い切る（例:「移る前に4つ確認する」）。不確かな点は結論ではなく本文で補足する
- 一般論で終わらせず、各ポイントに「具体例」か「すぐ使える質問・チェック項目」を必ず付ける
- 経歴の年数や順番は次の通り。これ以外の数字や順番を書かない: {career}
- 体験・具体的な手順ベース。煽らない。断定や収益の約束をしない
- 次の語は使わない: {ng}
- 数字は次の事実一覧にあるものだけ使う。なければ数字を書かない:
{facts}
- 体験談のルール（最重要）:
  - 一人称で語ってよい経験は次のリストだけ: {episodes}
  - テーマに合う経験がなければ、体験談は書かず手順・一般論で書く
  - 次は自分の経験として絶対に書かない: {not_me}
  - 架空の人物・架空の受講生の声・架空の実績を作らない
"""

def base(stage, idea):
    return BASE.format(persona=S["persona"], stage=T[stage]["name"], idea=idea, ng="、".join(G["ng_words"]),
                       facts=FACTS_TEXT or "（なし）", episodes=PR.get("episodes") or "（なし）",
                       not_me="、".join(PR.get("not_me") or []), career="／".join((PR.get("profile") or {}).get("career_history") or []))

def examples():
    """伸びた投稿を、お手本として執筆係に渡す（文体・構成の参考。内容はコピーしない）"""
    top = perf()["top_posts"][:3]
    return ("\n- 反応の良かった過去の投稿（構成と語り口の参考。内容や数字はコピーしない）:\n" +
            "\n---\n".join(top)) if top else ""

def write(kind, stage, idea):
    """執筆係"""
    if kind == "threads":
        return base(stage, idea) + examples() + "\nThreads用の投稿を1つ。400字以内、最後は読者への質問で終える。JSON: {\"text\": \"...\"}"
    return base(stage, idea) + examples() + ("""
Instagramの保存されるカルーセルを作る。読み終えたら行動できるだけの中身を入れる。
構成（8〜10枚）:
1枚目: 表紙。結論を行動で言い切る（title 16字以内, body 40字以内で「誰向けか」）
2枚目: なぜ大事か（読者の悩み・よくある失敗）
3〜(n-2)枚目: ポイントを1枚に1つ。title に要点、body に「具体例」か「確認する質問」を入れる
(n-1)枚目: まとめのチェックリスト（3〜5項目を「・」で並べる）
n枚目: 保存とフォローを促す（次に何を発信するか一言）
文字数: title 16字以内, body 60〜110字。体言止めと短い文を混ぜ、硬い「です・ます」の連続を避ける
キャプション: 500〜800字。1行目で結論、続けて各ポイントの補足（スライドの丸写しにしない）、最後に問いかけ。ハッシュタグは5個まで
各スライドに type を付ける: cover（表紙）/ why（なぜ大事か）/ point（ポイント）/ checklist（まとめ。body は「・」区切り）/ cta（最後）
JSON: {"slides": [{"type": "cover", "title": "...", "body": "..."}], "caption": "..."}""")

def design_loop(post_id, out, prompt, pr):
    """画像を作り、機械チェック→デザインのレビュー。問題があれば文字を直して作り直す（最大2回）"""
    for attempt in range(3):
        paths, warns = render_carousel(post_id, out["slides"], pr=pr)
        issues = warns or design_check(paths)
        if not issues: return paths, []
        if attempt == 2: break
        fix = generate_json(prompt + f"""
前回のカルーセルを画像にしたところ、デザイン上の問題がありました。内容は保ったまま、文字量や言い回しを直したslidesだけを返してください。
前回のslides: {json.dumps(out["slides"], ensure_ascii=False)}
問題点: {issues}
JSON: {{"slides": [...]}}""", role="writer")
        out["slides"] = fix.get("slides", out["slides"])
        print("デザインを直して作り直し:", issues)
    return paths, issues

def make(kind, idx, idea):
    stage = idea["stage"]
    cands = [] if in_warmup() else [a for a in AFF if a["stage"] == stage]
    aff = random.choice(cands) if cands else None
    prompt = write(kind, stage, idea["idea"])
    issues = ["未生成"]
    for attempt in range(G["max_rewrite"] + 1):
        out = generate_json(prompt, role="writer")
        text = out["text"] if kind == "threads" else out["caption"] + " " + " ".join(s["title"] + s["body"] for s in out["slides"])
        issues = check(text, FACTS_TEXT)
        if not issues: issues = logic_check(text)  # 機械チェックを通ったものだけAIで論理チェック
        if not issues: break
        prompt += f"\n前回の出力に問題がありました。修正してください: {issues}"
    post = {"id": f"{now():%Y%m%d}-{kind}-{idx}", "kind": kind, "stage": stage, "idea": idea["idea"],
            "created": now().isoformat(), "issues": issues, "affiliate": aff["id"] if aff else None}
    if kind == "threads":
        post["text"] = apply_pr(out["text"] + ("\n詳しくはプロフィールのリンクから" if aff else ""), bool(aff))
    else:
        post["caption"] = apply_pr(out["caption"] + ("\n詳しくはプロフィールのリンクから" if aff else ""), bool(aff))
        if not issues:
            post["images"], issues = design_loop(post["id"], out, prompt, bool(aff))
            post["issues"] = issues; post["slides"] = out["slides"]
    if issues:
        post["status"] = "rejected"          # 全自動: 問題が残った投稿は出さずに捨てる
    elif aff and not aff.get("auto_ok"):
        post["status"] = "rejected"; post["issues"] = ["案件の自動公開が未許可（affiliates.yaml の auto_ok）"]
    else:
        post["status"] = "approved"
    save_post(post); print(post["id"], post["status"], post["issues"])

def main():
    if killed(): print("KILL_SWITCH ON: skip"); return
    print("立ち上げ期間中" if in_warmup() else "通常運用")
    try:
        w = weights(); ideas = research()
        ideas = [i for i in ideas if i.get("stage") in T and w.get(i["stage"], 0) > 0]
        def pick():
            ks = list(w); st = random.choices(ks, weights=[w[k] for k in ks])[0]
            m = [i for i in ideas if i["stage"] == st]
            return random.choice(m) if m else {"stage": st, "idea": random.choice(T[st]["examples"])}
        for i in range(setting("threads_per_day")): make("threads", i, pick())
        for i in range(S["instagram_per_day"]): make("instagram", i, pick())
    except BudgetExceeded as e:
        print(e)

if __name__ == "__main__":
    main()
