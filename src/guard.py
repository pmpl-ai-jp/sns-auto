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
    """チェック係: 結論と理由のつながり・誇張・作り話をAIで確認する"""
    from .llm import generate_json
    r = generate_json(f"""次のSNS投稿をレビューしてください。問題があれば具体的に指摘。
観点: (1)結論が先にあり、理由とつながっているか (2)誇張・断定・収益の約束がないか
(3)事実と意見が混ざっていないか (4)誰かを傷つけたり、他社を批判したりしていないか
投稿:
{text}
JSON: {{"ok": true/false, "issues": ["..."]}}""", 0.1, role="checker")
    return [] if r.get("ok") else [f"論理チェック: {i}" for i in r.get("issues", [])]

def apply_pr(text, has_affiliate):
    if not has_affiliate:
        return text
    if not text.startswith(G["pr_label"]):
        text = f"{G['pr_label']}{text}"
    if G["pr_footer"] not in text:
        text += "\n\n" + G["pr_footer"]
    return text
