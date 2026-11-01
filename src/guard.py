import re
from .common import load

G = load("config/guardrails.yaml")
P = load("config/profile.yaml")
EPISODES = P.get("episodes") or []
NOT_ME = P.get("not_me") or []

def check(text, facts_text=""):
    """問題点のリストを返す。空ならOK。"""
    issues = [f"NGワード: {w}" for w in G["ng_words"] if w in text]
    for m in re.finditer(G["number_pattern"], text):
        if m.group(0) not in facts_text:
            issues.append(f"出典のない数字: {m.group(0)}")
    issues += experience_issues(text)
    return issues

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
    """デザインのレビュー係: 画像を見て、読みやすさ・はみ出し・詰め込みすぎを確認する"""
    from .llm import generate_json
    from .common import ROOT
    r = generate_json("""Instagramのカルーセル画像をレビューしてください。スマホで見る前提で、厳しめに判定します。
観点:
(1) 文字が切れている・重なっている・枠からはみ出している
(2) 文字が小さすぎる、1枚の情報量が多すぎて読む気がしない
(3) 不自然な改行（言葉の途中での改行、1〜2文字だけの行、句読点や開き括弧の位置、行の長さが極端にバラバラ）
(3b) ラベルと文の重複（「保存版」ラベルの下の文にも「保存版」がある等）、本文に「例：」「質問：」のようなラベルが残っている
(4) 1枚目の表紙が、スクロール中に目に止まる強さがあるか。タイトルが問いかけで終わらず、行動で言い切っているか
(5) 全体のデザインがそろっているか
写真やイラストがないことは、このアカウントの方針なので問題にしない。
問題がなければ ok=true。直すべき点は、何枚目の何をどう直すか（文字を減らす、言い換える等）を具体的に書く。
JSON: {"ok": true/false, "issues": ["..."]}""", 0.1, role="checker", images=[str(ROOT / p) for p in image_paths])
    return [] if r.get("ok") else [f"デザイン: {i}" for i in r.get("issues", [])]

def apply_pr(text, has_affiliate):
    if not has_affiliate:
        return text
    if not text.startswith(G["pr_label"]):
        text = f"{G['pr_label']}{text}"
    if G["pr_footer"] not in text:
        text += "\n\n" + G["pr_footer"]
    return text
