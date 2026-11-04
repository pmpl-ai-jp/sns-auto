import re
from .common import load

G = load("config/guardrails.yaml")
P = load("config/profile.yaml")
EPISODES = P.get("episodes") or []
NOT_ME = P.get("not_me") or []

def check(text, facts_text=""):
    """問題点のリストを返す。空ならOK。
    NGワードは「約束・断定」の形のときだけ止める。「保証しません」のような注意書きの言い回しは通す"""
    t = text
    for ok in G.get("allowed_phrases", []):       # 許可する言い回しを取り除いてから判定する
        t = t.replace(ok, "")
    issues = [f"NGワード: {w}" for w in G["ng_words"] if w in t]
    for pat in G.get("promise_patterns", []):     # 約束の形は、許可した言い回しの中でも止める
        m = re.search(pat, text)
        if m: issues.append(f"約束・断定の表現: {m.group(0)}")
    for m in re.finditer(G["number_pattern"], text):
        if m.group(0) not in facts_text:
            issues.append(f"出典のない数字: {m.group(0)}")
    issues += experience_issues(text)
    return list(dict.fromkeys(issues))

def experience_issues(text):
    """体験談らしい表現があり、episodes のどれとも結びつかなければ指摘する"""
    out = []
    for pat in G.get("experience_patterns", []):
        for m in re.finditer(pat, text):
            frag = m.group(0)
            if not any(_overlap(text, e) for e in EPISODES):
                out.append(f"根拠のない体験談の可能性: 「{frag}」")
    return out

def _overlap(text, episode, n=4):
    """episode の4文字以上の断片が本文にあれば、その体験に基づくとみなす"""
    e = re.sub(r"[（）()、。\s0-9年月〜]", "", episode)
    return any(e[i:i+n] in text for i in range(max(0, len(e) - n + 1)))

def logic_check(text):
    """チェック係: 公開を止めるべき重大な問題だけを返す。細かい改善点は止めない（書き直しの参考にだけ使う）"""
    from .llm import generate_json
    P = load("config/profile.yaml")
    r = generate_json(f"""次のSNS投稿をレビューしてください。
筆者の経歴（ここにある経験は事実として確認済み。根拠不足として扱わない）:
{P.get("episodes")}

【公開を止める問題（blocking）】次に当てはまるものだけ:
(a) 誇張・断定的な効果の約束・収益の約束（「必ず」「誰でも」等）
(b) 事実として誤っている内容、または上の経歴にない体験を筆者の経験として書いている
(c) 結論がない、または結論と本文が矛盾している
(d) 特定の企業・個人・職種を見下す、批判する
(e) 法令や規約に反するおそれ（ステマ、個人情報の扱いを勧める等）
【改善点（suggestions）】上に当てはまらない細かい点（言い回し、意見表明の明示、補足不足など）。公開は止めない。

一般的に知られた考え方（例:「バッチ処理は抽出・変換・格納で組む」）に出典は要らない。
筆者の考えであることが文脈から分かれば、毎文に「私の見方では」を付ける必要はない。

投稿:
{text}
JSON: {{"blocking": ["..."], "suggestions": ["..."]}}""", 0.1, role="checker")
    return [f"論理チェック: {i}" for i in r.get("blocking", [])], r.get("suggestions", [])

def design_check(image_paths):
    """デザインのレビュー係: 公開を止める見た目の問題(blocking)と、細かい改善点(suggestions)を分けて返す"""
    from .llm import generate_json
    from .common import ROOT
    r = generate_json("""Instagramのカルーセル画像をレビューしてください。スマホで見る前提です。
【公開を止める問題（blocking）】見た目が壊れているものだけ:
(a) 文字が切れている・重なっている・枠や下の帯からはみ出している
(b) 文字が小さすぎて読めない、または1枚に文字が詰まりすぎて読む気がしない
(c) 単語の途中での改行（例:「自／動化」）、句読点や開き括弧が行頭に来ている
(d) ラベルと本文の重複（「保存版」ラベルの下に「保存版：」がある等）、本文に「例：」のようなラベルが残っている
【改善点（suggestions）】上に当てはまらないもの（言い回し、表現の統一、表紙の訴求力、細かい位置のずれ、文節単位の改行の好み など）。公開は止めない。
写真やイラストがないことは、このアカウントの方針なので指摘しない。文章の内容の正しさは別の係が確認済みなので、見た目に集中する。
JSON: {"blocking": ["何枚目の何をどう直すか"], "suggestions": ["..."]}""", 0.1, role="checker", images=[str(ROOT / p) for p in image_paths])
    return [f"デザイン: {i}" for i in r.get("blocking", [])], r.get("suggestions", [])

def apply_pr(text, has_affiliate):
    if not has_affiliate:
        return text
    if not text.startswith(G["pr_label"]):
        text = f"{G['pr_label']}{text}"
    if G["pr_footer"] not in text:
        text += "\n\n" + G["pr_footer"]
    return text
