import os, json, re, base64, io, requests
from .common import load
from .budget import check_budget, record

def _provider(model, S):
    for prefix, p in S["providers"].items():
        if model.startswith(prefix): return p
    raise ValueError(f"unknown model: {model}")

def _escape_inner(t):
    """文字列の中の生の改行・タブを \\n などに直す（JSONでは文字列内の改行が許されないため）"""
    out, ins, esc = [], False, False
    for ch in t:
        if ins:
            if esc: out.append(ch); esc = False
            elif ch == "\\": out.append(ch); esc = True
            elif ch == '"': out.append(ch); ins = False
            elif ch == "\n": out.append("\\n")
            elif ch == "\r": pass
            elif ch == "\t": out.append("\\t")
            else: out.append(ch)
        else:
            out.append(ch)
            if ch == '"': ins = True
    return "".join(out)

def _parse(text):
    m = re.search(r"\{.*\}", text, re.S)  # 前後に説明文が付いてもJSON部分だけ取り出す
    raw = m.group(0) if m else text
    try: return json.loads(raw)
    except json.JSONDecodeError: pass
    fixed = _escape_inner(raw)
    fixed = re.sub(r",\s*([}\]])", r"\1", fixed)          # 末尾の余計なカンマ
    try: return json.loads(fixed)
    except json.JSONDecodeError: pass
    fixed2 = re.sub(r'"\s*\n\s*"', '",\n"', fixed)         # 項目間のカンマ抜け
    return json.loads(fixed2)

def _anthropic(model, prompt, temperature, max_tokens, images=None, web=0):
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=180, headers={
        "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
        "content-type": "application/json"}, json={
        "model": model, "max_tokens": max_tokens,
        "system": "出力は指定されたJSONだけにしてください。説明文やコードブロックは付けないでください。",
        "messages": [{"role": "user", "content": _content(prompt, images)}],
        **({"tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": web}]} if web else {})})
    if r.status_code >= 400:  # 原因が分かるように、APIのエラー内容をログに出す
        print("Anthropic API error:", r.status_code, r.text[:1000])
    r.raise_for_status(); j = r.json()
    text = "".join(b.get("text", "") for b in j["content"] if b.get("type") == "text")
    u = j.get("usage", {})
    searches = (u.get("server_tool_use") or {}).get("web_search_requests", 0)
    return text, u.get("input_tokens", len(prompt)), u.get("output_tokens", max_tokens), searches

def _content(prompt, images):
    """画像があれば、縮小してプロンプトと一緒に送る（トークン節約のため540px）"""
    if not images: return prompt
    from PIL import Image
    parts = []
    for i, path in enumerate(images):
        im = Image.open(path).convert("RGB"); im.thumbnail((540, 540))
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=80)
        parts.append({"type": "text", "text": f"{i+1}枚目"})
        parts.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                      "data": base64.b64encode(buf.getvalue()).decode()}})
    return parts + [{"type": "text", "text": prompt}]

def _google(model, prompt, temperature, max_tokens, images=None, web=0):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens,
                                 "responseMimeType": "application/json"}}
    r = requests.post(url, params={"key": os.environ["GEMINI_API_KEY"]}, json=body, timeout=180)
    r.raise_for_status(); j = r.json(); u = j.get("usageMetadata", {})
    return (j["candidates"][0]["content"]["parts"][0]["text"], u.get("promptTokenCount", len(prompt)),
            u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0), 0)

def generate_json(prompt, temperature=0.8, role="light", max_tokens=8000, images=None, web=0):
    S = load("config/settings.yaml")
    model = S["models"][role]
    check_budget()  # 上限に達していたら例外で止める
    call = _anthropic if _provider(model, S) == "anthropic" else _google
    last = None
    for attempt in range(3):                 # JSONが壊れていたら、同じ指示でもう一度書かせる（最大3回）
        if attempt: check_budget()
        text, tin, tout, searches = call(model, prompt, temperature, max_tokens, images, web)
        record(model, tin, tout, searches)
        try: return _parse(text)
        except json.JSONDecodeError as e:
            last = e
            print(f"JSONが壊れていた（{attempt+1}回目）: {e} | 返事の一部: {text[max(0,e.pos-60):e.pos+60]!r}")
    raise last
