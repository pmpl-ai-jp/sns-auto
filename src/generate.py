"""毎朝実行: リサーチ係 → 企画係 → 執筆係 → チェック係 の順に動き、当日分を queue/ に保存"""
import random, json, datetime, os, yaml, copy, re
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

def knowledge(stage):
    """AI仕事術のテーマでは、data/knowledge/ の資料を背景知識として渡す（Threads・Instagram共通。note/ の中は読まない）"""
    if stage != "ai_work": return ""
    kd = ROOT / "data/knowledge"
    docs = [p.read_text(encoding="utf-8") for p in sorted(kd.glob("*.md"))] if kd.exists() else []
    if not docs: return ""
    return ("\n- 背景知識（内容の正しさの土台にする。出典名や原文は書かず自分の言葉で書く。"
            "例文はそのまま使わず別の場面の例に変える。資料内の数字は例であり、実績や統計として書かない）:\n" + "\n".join(docs))

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

def history(n=40):
    """過去の投稿のネタ一覧（同じ切り口を繰り返さないため）"""
    from .common import iter_posts
    xs = [p for _, p in iter_posts() if p.get("idea")]
    return [p["idea"] for p in xs[-n:]]

def _grams(t, n=3):
    t = re.sub(r"[\s・、。！？!?「」『』（）()\n]", "", t or "")
    return {t[i:i + n] for i in range(len(t) - n + 1)}

def similarity(a, b):
    """2つの文章の言葉の重なり（0〜1）。文字3つ組の共通部分で測る"""
    A, B = _grams(a), _grams(b)
    return len(A & B) / max(1, min(len(A), len(B)))

def recent_texts(kind, n=20):
    """直近に作った同じ媒体の投稿の本文（似すぎを防ぐため）。却下された投稿は含めない"""
    from .common import iter_posts
    xs = [p for _, p in iter_posts() if p.get("kind") == kind and p.get("status") in ("approved", "published")]
    xs = sorted(xs, key=lambda p: p["created"])[-n:]
    return [(p.get("text") or p.get("caption", "")) for p in xs]

def recent_openings(kind, n=20):
    """直近の投稿の1行目（書く役に「同じ場面・主張は避ける」と伝えるため）"""
    return [t.strip().splitlines()[0][:60] for t in recent_texts(kind, n) if t.strip()]

def too_similar(text, kind):
    """過去の投稿とほぼ同じ文章になっていないか。同じ日の分は少し厳しくする"""
    from .common import iter_posts
    today = f"{now():%Y%m%d}"
    for _, p in iter_posts():
        if p.get("kind") != kind or p.get("status") not in ("approved", "published"): continue
        old = p.get("text") or p.get("caption", "")
        th = 0.45 if p["id"].startswith(today) else 0.55   # ほぼ同じ文章だけ止める
        v = similarity(text, old)
        if v >= th:
            return [f"過去の投稿「{old.strip().splitlines()[0][:25]}」とほぼ同じ文章になっている（重なり{v:.2f}）。場面・主張・言い回しを変えて、別の切り口で書き直す"]
    return []

def teaser():
    """直近に公開した投稿の最後のスライドにある「次回予告」（題名と本文）を取り出す。
    次の投稿はこの約束を果たす内容にする"""
    from .common import iter_posts
    xs = [p for _, p in iter_posts() if p.get("kind") == "instagram" and p.get("slides")
          and p.get("status") == "published"]      # 読者が実際に見た（公開済みの）投稿の予告だけを引き継ぐ
    if not xs: return ""
    last = sorted(xs, key=lambda p: p.get("published_at") or p["created"])[-1]
    cta = next((s for s in reversed(last["slides"]) if s.get("type") == "cta"), None)
    if not cta: return ""
    return f"直近の投稿「{last['slides'][0]['title']}」の最後で、読者に次のように予告した: {cta['title']}。{cta['body']}"

def last_promise():
    """直近に作った（公開済み、または公開待ち）連載の回の予告。次の回で必ず果たす中身として渡す"""
    from .common import iter_posts
    xs = [p for _, p in iter_posts() if p.get("kind") == "instagram" and p.get("slides") and p.get("series")
          and p.get("status") in ("published", "approved")]
    if not xs: return ""
    last = sorted(xs, key=lambda p: p["created"])[-1]
    cta = next((s for s in reversed(last["slides"]) if s.get("type") == "cta"), None)
    return f"{cta['title']}。{cta['body']}" if cta else ""

def trend():
    """トレンド調査係: ウェブ検索で、今話題になっていることを集める（失敗しても投稿づくりは止めない）"""
    tc = S.get("trend") or {}
    if not tc.get("enabled"): return []
    cache = ROOT / "data" / "trend.json"
    if cache.exists():                                  # 保存した結果がまだ新しければ、検索せずにそれを使う
        c = json.loads(cache.read_text(encoding="utf-8"))
        age = (now().date() - datetime.date.fromisoformat(c["date"])).days
        if age < tc.get("every_days", 7):
            print(f"トレンド: {c['date']} の調査結果を使用"); return c["topics"]
    try:
        r = generate_json(f"""日本のSNS（Instagram・Threads・note）で、次の分野について、直近1〜2週間に話題になっていることを調べてください。
分野: 仕事でのAI活用（ChatGPT・Claude・Copilot等の新機能や使い方）、IT業界のキャリア・転職、SIerと事業会社、プロジェクトマネジメント
発信者: {S["persona"]}
この発信者が自分の経験と結びつけて語れる話題を優先する。噂や真偽が不確かな話は除く。
JSON: {{"topics": [{{"topic": "1行", "why": "なぜ今話題か1行", "source": "参照したURL"}}]}}（5〜8個）""",
            0.5, role="planner", web=tc.get("max_searches", 4), max_tokens=6000)
        topics = r.get("topics", [])
        if topics:
            cache.parent.mkdir(exist_ok=True)
            cache.write_text(json.dumps({"date": now().date().isoformat(), "topics": topics}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"トレンド: 新しく調査（{len(topics)}件）"); return topics
    except Exception as e:
        print("トレンド調査をスキップ:", e)
        if cache.exists(): return json.loads(cache.read_text(encoding="utf-8"))["topics"]   # 失敗したら前回の結果で続ける
        return []

def research():
    """ネタ出し係: トレンド・経歴・過去の投稿・伸びた投稿をもとに、今日のネタ候補を出す"""
    p = perf(); tr = trend()
    return generate_json(f"""次の人物がSNSで発信します。今日のネタ候補を8個出してください。
人物像: {S["persona"]}
この人の経歴（年数や順番はここに書かれたものだけを使う。推測で数字を作らない）:
{json.dumps(PR.get("profile", {}), ensure_ascii=False)}
今話題になっていること（使えるものだけ使う。無理に入れない）:
{json.dumps(tr, ensure_ascii=False)}
最近伸びた投稿（同じ型で切り口を変える参考に）: {p["top_posts"][:3]}
これまでに出したネタ（同じ切り口は出さない）: {history()}
直近の予告（最優先）: {teaser() or "なし"}
  → 予告がある場合、8個のうち最初の1個は、その予告に答えるネタにする（stage はそのテーマに合うものを選ぶ）。予告したことを、次の投稿で必ず果たす
各ネタは「誰の・どんな悩みに・何を持ち帰ってもらうか」が分かる1行にする。
フォローしたくなる理由を作るため、8個のうち2個は、続きものにできる（シリーズ化できる）ネタにする。
テーマ一覧: {json.dumps({k: v["name"] for k, v in T.items()}, ensure_ascii=False)}
JSON: {{"ideas": [{{"stage": "テーマのキー", "idea": "1行"}}]}}""", 0.9, role="planner")["ideas"]


# ---------------- 連載（シリーズ） ----------------
SERIES_PATH = "data/series.yaml"

def load_series():
    p = ROOT / SERIES_PATH
    if not p.exists(): return {"current": None, "upcoming": [], "history": []}
    d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    d.setdefault("current", None); d.setdefault("upcoming", []); d.setdefault("history", [])
    return d

def save_series(d):
    (ROOT / SERIES_PATH).write_text(
        "# 連載の計画。upcoming に {theme: \"...\", stage: \"テーマのキー\"} を足すと、次の連載として使われる\n"
        + yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")

def next_stage(d):
    """テーマの割合に沿って、次の連載のテーマ（stage）を選ぶ。直前と同じテーマは避ける"""
    w = {k: v["ratio"] for k, v in T.items() if not v.get("affiliate") and k != "log" and v["ratio"] > 0}
    last = d["history"][-1]["stage"] if d["history"] else None
    if last in w and len(w) > 1: w.pop(last)
    ks = list(w); return random.choices(ks, weights=[w[k] for k in ks])[0]

def plan_series(d):
    """連載の計画係: テーマと各回の構成（3〜7回）を決める"""
    req = d["upcoming"].pop(0) if d["upcoming"] else {}
    tz = teaser()                                   # 直前に公開した投稿の予告（読者への約束）
    stage = req.get("stage") or next_stage(d)
    past = [s["theme"] for s in d["history"]][-10:]
    r = generate_json(f"""次の人物が、Instagramで平日に連載をします。次の連載の計画を立ててください。
人物像: {S["persona"]}
経歴（ここにある経験だけを使う）: {json.dumps(PR.get("profile", {}), ensure_ascii=False)}
語ってよい体験: {PR.get("episodes")}
テーマの分類: {T[stage]["name"]}
{"指定されたテーマ: " + req["theme"] if req.get("theme") else "テーマはこの分類の中から、読者が保存したくなるものを1つ選ぶ"}
過去の連載（同じテーマは避ける）: {past}
直前に公開した投稿の予告: {tz or "なし"}
  → 予告がある場合、指定されたテーマがあってもなくても、第1回はその予告に答える内容にする（読者への約束を守る）。予告の内容が連載のテーマになじまなければ、予告をテーマにした連載にする
今話題になっていること（使えるなら）: {json.dumps(trend(), ensure_ascii=False)}
ルール:
- 回数は内容に合わせて3〜7回。1回で1つのことだけを扱い、回を追うごとに理解が深まる順番にする
- 第1回は全体像、最終回はまとめ（チェックリストなど）にする
- 各回のtitleは、その回の内容が分かる具体的な見出し（16字以内が目安）
JSON: {{"theme": "連載の名前", "goal": "読者が最後に持ち帰るもの", "episodes": [{{"title": "...", "point": "その回で書くことを1〜2文"}}]}}""",
        0.7, role="planner", max_tokens=4000)
    eps = r.get("episodes", [])[:7]
    return {"theme": r.get("theme", ""), "stage": stage, "goal": r.get("goal", ""),
            "episodes": eps, "done": 0, "started": now().date().isoformat()}

def current_series():
    """今の連載を返す。なければ新しく計画する"""
    d = load_series()
    if not d["current"] or d["current"]["done"] >= len(d["current"]["episodes"]):
        if d["current"]: d["history"].append({k: d["current"][k] for k in ("theme", "stage", "started")})
        d["current"] = plan_series(d); save_series(d)
        print("新しい連載:", d["current"]["theme"], len(d["current"]["episodes"]), "回")
    return d

def series_idea(d):
    """今日書く回のネタと、最後のスライドで予告する内容"""
    c = d["current"]; n = c["done"]; ep = c["episodes"][n]; total = len(c["episodes"])
    promise = last_promise() if n > 0 else ""
    idea = (f"連載「{c['theme']}」第{n+1}回（全{total}回）:{ep['title']}。この回で書くこと: {ep['point']}。"
            f"連載のゴール: {c['goal']}。前の回までの内容: {[e['title'] for e in c['episodes'][:n]]}"
            + (f"。前の回の最後で読者に約束した内容（この回で必ず扱う。題名だけでなく本文の中身も入れる）: {promise}" if promise else ""))
    if n + 1 < total:
        nxt = f"次回:{c['episodes'][n+1]['title']}（連載「{c['theme']}」第{n+2}回）"
    else:
        nxt = "連載の最終回。最後のスライドでは、連載全体のまとめとして保存をすすめ、次の連載が始まることを一言だけ予告する"
    return {"stage": c["stage"], "idea": idea, "next": nxt}

def skip_if_stuck(d):
    """同じ回が3回続けて公開できなかったときは、その回を飛ばして次へ進む（連載が止まり続けないように）"""
    c = d["current"]
    if not c: return
    tries = c.setdefault("tries", {}); k = str(c["done"])
    tries[k] = tries.get(k, 0) + 1
    if tries[k] > 3 and c["done"] + 1 < len(c["episodes"]):
        print(f"第{c['done']+1}回が3回続けて通らなかったため、次の回へ進む"); c["done"] += 1
    save_series(d)

def mark_done():
    d = load_series()
    if d["current"]: d["current"]["done"] += 1; save_series(d)

STRUCTURES = [
    "具体的な場面から入り、何が起きたか→どうしたか→学んだこと、の順で書く",
    "よくある失敗から入り、なぜそうなるか→避け方、の順で書く",
    "結論を一言で言い切ってから、理由を1〜2つだけ書く",
    "2つのやり方（または立場）を比べて、違いを書く",
    "コツを1つだけに絞り、それを深く具体的に書く",
]

def style_rules():
    """文体のルール（AIっぽさを減らす）。文体メモがあれば、それに寄せる"""
    st = load("config/style.yaml") if (ROOT / "config/style.yaml").exists() else {}
    rules = (
        "\n- 構成は次の型で書く（毎回同じ型にしない）: " + random.choice(STRUCTURES) +
        "\n- 次の言い回しは使わない: " + "、".join(G.get("ai_phrases", [])) +
        "\n- 「〜と思います」「〜と考えます」は1投稿に2回まで。事実は言い切り、意見だけを意見として書く"
        "\n- 同じ語尾を3文続けない。「です・ます」の中に、短い言い切りや体言止めを少し混ぜる。ただし決めぜりふのような体言止めで締めない"
        "\n- 「まず」「次に」「最後に」のような段取りの言葉や、「〜について説明します」のような前置きを書かない"
        "\n- 文の長さに変化をつける（短い文と長めの文を混ぜる）")
    if st.get("notes"): rules += "\n- 筆者の文体の特徴（これに寄せる。中身はまねしない）: " + "／".join(st["notes"])
    if st.get("phrases"): rules += "\n- 筆者がよく使う言い回し（自然に使える場面なら使う）: " + "、".join(st["phrases"])
    if st.get("avoid"): rules += "\n- 筆者が使わない言い回し: " + "、".join(st["avoid"])
    return rules

def ai_tone_issues(text):
    """AIっぽい決まり文句や、ぼかし表現の多用を見つける（書き直しの参考にするだけで、公開は止めない）"""
    out = [f"AIっぽい言い回し「{p}」" for p in G.get("ai_phrases", []) if p.replace("〜", "") in text]
    n = sum(text.count(h) for h in G.get("hedge_words", []))
    if n > G.get("hedge_max", 2): out.append(f"「〜と思います」「〜と考えます」が{n}回ある。2回までにする")
    return out

BASE = """あなたは日本語のSNS発信者です。人物像: {persona}
テーマ: {stage}
ネタ: {idea}
ルール:
- 結論から書き、理由を2〜3個に分け、事実と意見を分ける（ロジカルシンキング）
- 結論は「〜することがある」のようにぼかさず、読者がとる行動で言い切る（例:「移る前に4つ確認する」）。不確かな点は結論ではなく本文で補足する
- 一般論で終わらせず、各ポイントに「具体例」か「すぐ使える質問・チェック項目」を必ず付ける
- 経歴の年数や順番は次の通り。これ以外の数字や順番を書かない: {career}
- 自己紹介は1〜2文に短くまとめ（例:「IT業界25年。SIerから事業会社のSEを経て、いまは外資系SIerでPMとPLをしています」）、年数の内訳や括弧書きの補足を並べない
- 体験・具体的な手順ベース。煽らない。断定や収益の約束をしない
- 次の語は、約束や断定の形では使わない: {ng}
  - 「保証しません」「必ずしも〜ではない」のような注意書きでも、機械チェックで止まることがある。迷ったら「確かではない」「限らない」など別の言い方にする
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
                       not_me="、".join(PR.get("not_me") or []), career="／".join((PR.get("profile") or {}).get("career_history") or [])) + style_rules() + knowledge(stage)

def examples():
    """伸びた投稿を、お手本として執筆係に渡す（文体・構成の参考。内容はコピーしない）"""
    top = perf()["top_posts"][:3]
    return ("\n- 反応の良かった過去の投稿（構成と語り口の参考。内容や数字はコピーしない）:\n" +
            "\n---\n".join(top)) if top else ""

def write(kind, stage, idea, nxt=None):
    """執筆係"""
    extra = f"\n最後のスライド(cta)の予告はこれにする（変えない）: {nxt}" if nxt else ""
    if kind == "threads":
        op = recent_openings("threads", 20)
        avoid = ("\n最近の投稿の1行目（これと同じ場面・同じ主張・似た言い回しは使わない。別の場面、別の切り口で書く）:\n- " + "\n- ".join(op)) if op else ""
        return base(stage, idea) + examples() + extra + avoid + "\nThreads用の投稿を1つ。「オフィスあるある」の形で書く。1行目は、読んだ人が「あるある」と思う具体的な場面にする（例:「ご確認ください」だけのメール）。続けて、なぜ困るかを1〜2文、直し方のコツを2〜3点（「・」の箇条書き）を示し、最後は言い切りの一文で締める（質問や問いかけで終えない。例:「結論から言うだけで、会議は短くなります。」）。150〜300字。短い文で、会話するような口調。箇条書きは「・」で項目だけを並べ、例や説明は箇条書きの中に入れず、箇条書きのあとの文にまとめる。括弧書きの補足は書かない（意味を足したいときは、本文の文にする）。読者への呼びかけを入れる場合は「あなた」にそろえ、「みなさん」「皆さん」は使わない。文末は「？」「?」「でしょうか」「ですか」で終えない。Instagramや他の媒体への案内、URL、ハッシュタグは書かない。数字は事実の表にあるものだけ、体験は経歴にあるものだけ（なければ体験は書かない）。「実体験型」の役割のときは、経歴の episodes から場面を1つ選んで書く。episodes にない場面や、細かい状況の作り話は足さない。1行目に「PMとして」「事業会社のSE時代」など、筆者の立場や時期を一言入れる。topic には、この投稿を探す人が使いそうな短い言葉を1つ（例: AI活用、仕事術、転職、ロジカルシンキング）。JSON: {\"text\": \"...\", \"topic\": \"...\"}"
    return base(stage, idea) + examples() + extra + ("""
Instagramの保存されるカルーセルを作る。読み終えたら行動できるだけの中身を入れる。
構成（8〜10枚）:
1枚目: 表紙。結論を行動で言い切る（title 16字以内, body 40字以内で「誰向けか」）
2枚目: なぜ大事か（読者の悩み・よくある失敗）
3〜(n-2)枚目: ポイントを1枚に1つ。title に要点、body に「具体例」か「確認する質問」を入れる
(n-1)枚目: まとめのチェックリスト（3〜5項目を「・」で並べる）
n枚目: 保存とフォローを促す（次に何を発信するか一言）
文字数: title 16字以内, body 60〜110字。体言止めと短い文を混ぜ、硬い「です・ます」の連続を避ける
禁止: 表紙のtitleを「？」で終わらせない（行動で言い切る）。表紙のtitleには「誰が・何を」が分かる言葉を入れる（例:「SIerから移る前に4つ確認する」）。
      最後のスライドのtitleに「NEXT」などの英字ラベルを付けない。最後のスライドのbodyに「保存して」を書かない（保存ボタンはデザイン側で付く）。
      最後のスライド(cta)のtitleは「次回:〇〇」の形で、次の投稿で実際に書ける具体的な予告にする。予告は、アカウントの軸（AI仕事術、キャリア、伝え方）に沿った内容にする。最後のスライドのbodyは、titleで予告した中身を具体的に説明する（titleと違う話を書かない）。予告の本文には、次の回で必ず書く内容を1〜2点、具体的に書く（次の回はこの約束を果たす）。
      同じものを指す言葉は全スライドで統一する。社内用語（例:「脱ホスト」）は一般の人にも分かる言葉に言い換える。表紙のbodyに「保存版」「PR」を書かない（ラベルはデザイン側で付く）。
      bodyに「悩み：」「例：」「質問：」のようなラベルを付けない（「たとえば〜」「〜と聞いてみる」など自然な文にする）
checklist の body は、項目ごとに改行（\n）で区切る
AIやツールに業務データを入れる手順を勧めるときは、「社内ルールを確認し、機密情報・個人情報は入れない」と一言添える
キャプション: 500〜800字。1行目で結論、続けて各ポイントの補足（スライドの丸写しにしない）、最後に問いかけ。ハッシュタグは5個まで
各スライドに type を付ける: cover（表紙）/ why（なぜ大事か）/ point（ポイント）/ checklist（まとめ。body は「・」区切り）/ cta（最後）
JSON: {"slides": [{"type": "cover", "title": "...", "body": "..."}], "caption": "..."}""")

def design_loop(post_id, out, prompt, pr):
    """画像を作り、機械チェック→デザインのレビュー。
    見た目が壊れている問題(blocking)は直して作り直す（最大2回）。
    細かい改善点(suggestions)は1回だけ反映するが、反映して悪くなったら、通っていた版に戻して公開する"""
    best = None                                   # 公開できる状態（blockingなし）の最新の版
    polished = False
    for attempt in range(4):
        paths, warns = render_carousel(post_id, out["slides"], pr=pr)
        if warns: issues, sugg = warns, []
        else: issues, sugg = design_check(paths)
        if not issues:
            best = (list(paths), copy.deepcopy(out["slides"]))
            if not sugg or polished: return paths, []
        elif best:                                # 磨いた結果、新しい問題が出た → 通っていた版に戻す
            print("磨き直しで問題が出たため、前の版に戻す:", issues)
            out["slides"] = best[1]
            paths, _ = render_carousel(post_id, out["slides"], pr=pr)
            return paths, []
        if attempt >= 3 or (issues and attempt >= 2): break
        todo = issues if issues else sugg
        if not issues: polished = True
        fix = generate_json(prompt + f"""
前回のカルーセルを画像にしたところ、直したい点がありました。内容は保ったまま、文字量や言い回しを直したslidesだけを返してください。文字は増やさず、減らす方向で直す。
前回のslides: {json.dumps(out["slides"], ensure_ascii=False)}
直す点: {todo}
JSON: {{"slides": [...]}}""", role="writer")
        out["slides"] = fix.get("slides", out["slides"])
        print("デザインを直して作り直し:", todo)
    return paths, issues

def make(kind, idx, idea):
    stage = idea["stage"]
    cands = [] if in_warmup() else [a for a in AFF if a["stage"] == stage]
    aff = random.choice(cands) if cands else None
    prompt = write(kind, stage, idea["idea"], idea.get("next"))
    issues = ["未生成"]
    tries = G["max_rewrite"] + (2 if kind == "threads" else 1)   # Threadsは書き直しを1回多くする
    for attempt in range(tries):
        out = generate_json(prompt, role="writer")
        text = out["text"] if kind == "threads" else out["caption"] + " " + " ".join(s["title"] + s["body"] for s in out["slides"])
        issues = check(text, FACTS_TEXT)
        if kind == "threads" and not issues: issues = threads_format_issues(out["text"])   # 形の崩れは書き直しで直す
        if kind == "threads" and not issues: issues = too_similar(out["text"], "threads")   # 過去の投稿・同じ日の投稿と似すぎていたら書き直し
        suggestions = []
        if not issues: issues, suggestions = logic_check(text)  # 機械チェックを通ったものだけAIで論理チェック
        if not issues: suggestions = list(suggestions) + ai_tone_issues(text)   # AIっぽさは止めずに1回だけ直す
        if not issues:
            if suggestions and attempt == 0:   # 重大な問題はないが改善点がある → 1回だけ磨く（失敗扱いにはしない）
                prompt += f"\n内容は良いので、次の改善点だけ反映して全体を書き直してください: {suggestions}"
                continue
            break
        prompt += f"\n前回の出力に問題がありました。修正してください: {issues}"
    post = {"id": f"{now():%Y%m%d}-{kind}-{idx}", "kind": kind, "stage": stage, "idea": idea["idea"],
            "created": now().isoformat(), "issues": issues, "affiliate": aff["id"] if aff else None}
    if kind == "threads":
        post["text"] = apply_pr(out["text"] + ("\n詳しくはプロフィールのリンクから" if aff else ""), bool(aff))
        post["topic"] = (out.get("topic") or "").replace("#", "").strip()[:50]
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
    if idea.get("series"): post["series"] = idea["series"]
    save_post(post); print(post["id"], post["status"], post["issues"])
    if idea.get("series") and post["status"] == "approved": mark_done()   # 連載は、公開できる回ができたときだけ次へ進める
    return post



def threads_format_issues(text):
    """Threadsの文章の形の崩れを見つける（箇条書きの途中の例・括弧書きの補足・呼びかけの不統一）"""
    out = []
    lines = text.split("\n")
    bullets = [i for i, l in enumerate(lines) if l.strip().startswith("・")]
    if bullets:
        first, last = bullets[0], bullets[-1]
        for i in range(first, last + 1):             # 箇条書きの範囲に、箇条書きでない行が挟まっていないか
            s = lines[i].strip()
            if s and not s.startswith("・"):
                out.append(f"箇条書きの途中に説明や例が入っている:「{s[:20]}」。例は箇条書きのあとにまとめる")
                break
    if re.search(r"[（(][^）)]{3,}[）)]", text):
        out.append("括弧書きの補足が入っている。補足は本文の文にする")
    tail = text.strip().splitlines()[-1].strip() if text.strip() else ""
    if re.search(r"[？?]\s*$|(でしょうか|ですか|ませんか|ますか|でしょう)[。]?\s*$", tail):
        out.append("最後の一文が疑問文（問いかけ）になっている。言い切りの一文で締める")
    if re.search(r"みなさん|皆さん|皆様", text):
        out.append("呼びかけが「あなた」にそろっていない（「みなさん」を使っている）")
    return out

THREADS_ROLES = [
    # 1本目: 経歴の実体験にもとづく型（反応が出た「議事録とレビュー」「SIerと事業会社」の系統）
    "実体験型。経歴にある実際の経験（事業会社のSE時代のレビュー、ベンダーとのやり取り、計画づくり、障害対応、SIerと事業会社の違いなど）から1つ選び、その場面を1行目に置く。「そのとき何に気づいたか」を短く示し、読者がすぐ使えるコツを2〜3点添える。AIの話は、その経験につながるときだけ入れる",
    # 2本目: 一般的なあるある（共感）
    "ロジカルシンキング・伝え方のオフィスあるある（会議、報告、メール、依頼など）。よくある失敗の場面から入り、直し方を短く示す。1行目に筆者の立場（PMとして見てきた、など）を一言添える",
    # 3本目: キャリアの実体験型
    "キャリアの実体験型。SIerと事業会社、受注側と発注側の両方を経験した立場から、「入る前に知りたかったこと」を1つ取り上げる。経歴にある事実だけを使い、確認するとよいことを2〜3点示す",
    # 4本目: AI活用のあるある（実体験を一言添える）
    "AI活用のあるある。仕事でAIを使う人が「自分もそうだ」と思う場面から入り、解決のコツを2〜3点示す。レビューや計画づくりなど、経歴にある経験を一言だけ添える",
]


def threads_ideas(ig):
    """Threadsの4本のネタ。Instagramには誘導せず、1本で完結する「あるある」形式にする。
    その日のInstagramのテーマは、重ならないよう参考として渡すだけ"""
    sl = (ig or {}).get("slides") or []
    avoid = f"（今日のInstagramは「{sl[0]['title']}」。同じ内容の言い換えにはしない）" if sl else ""
    stages = ["career_exp", "logic", "career_exp", "ai_work"]
    return [{"stage": stages[k], "idea": f"この投稿の役割: {r}{avoid}"} for k, r in enumerate(THREADS_ROLES)]

def main():
    if killed(): print("KILL_SWITCH ON: skip"); return
    print("立ち上げ期間中" if in_warmup() else "通常運用")
    try:
        w = weights(); ideas = research()
        ov = (os.environ.get("IDEA_OVERRIDE") or "").strip()      # 手動実行でネタを指定したとき
        if ov: ideas = [{"stage": "career_exp", "idea": ov}] + ideas
        ideas = [i for i in ideas if i.get("stage") in T and w.get(i["stage"], 0) > 0]
        first = [True]
        def pick():
            if first[0] and (ov or teaser()) and ideas:   # ネタの指定か予告がある日は、最初の1本をそのネタにする
                first[0] = False
                return ideas[0]
            first[0] = False
            ks = list(w); st = random.choices(ks, weights=[w[k] for k in ks])[0]
            m = [i for i in ideas if i["stage"] == st]
            return random.choice(m) if m else {"stage": st, "idea": random.choice(T[st]["examples"])}
        weekday = now().weekday() < 5
        ig_posts = []
        for i in range(S["instagram_per_day"]):
            if ov or not weekday:                 # ネタの指定がある日・週末は単発
                it = pick()
                if not weekday:                   # 週末の単発は、月曜から再開する連載の回を予告する
                    d = current_series(); sx = series_idea(d)
                    it = dict(it, next=f"月曜から連載「{d['current']['theme']}」の続き:{d['current']['episodes'][d['current']['done']]['title']}")
                ig_posts.append(make("instagram", i, it))
            else:                                 # 平日は連載の次の回
                d = current_series(); skip_if_stuck(d); d = load_series(); sx = series_idea(d)
                print(f"連載「{d['current']['theme']}」第{d['current']['done']+1}回")
                if now().weekday() == 4 and "連載の最終回" not in sx["next"]:
                    # 金曜は、週末が単発であること・連載の続きが月曜からであることを、最後のスライドで伝える
                    sx = dict(sx, next=sx["next"].replace("次回:", "月曜から連載の続き:", 1)
                              + "。最後のスライドのbodyには「週末は単発ネタをお届けします。連載の続きは月曜から」と一言入れる")
                ig_posts.append(make("instagram", i, dict(sx, series=d["current"]["theme"])))
        # Threads: Instagramが通っていれば、その内容とつなげる。通らなかった日は単発のネタで作る
        ig_ok = next((p for p in ig_posts if p and p.get("status") == "approved"), None)
        linked = threads_ideas(ig_ok)                           # Instagramが止まった日も、あるある形式で4本作る
        for i in range(setting("threads_per_day")):
            it = linked[i] if i < len(linked) else pick()
            p = make("threads", i, it)
            if p.get("status") != "approved":                  # 止まったら、別のネタで1回だけ作り直す
                print(f"Threads {i+1}本目が止まったため、作り直す:", p.get("issues"))
                make("threads", i, linked[(i + 1) % len(linked)])   # 別の役割（あるあるの種類）で作り直す
    except BudgetExceeded as e:
        print(e)

if __name__ == "__main__":
    main()
