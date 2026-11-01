import os, json, re, requests
from .common import load
from .budget import check_budget, record

def _provider(model, S):
    for prefix, p in S["providers"].items():
        if model.startswith(prefix): return p
    raise ValueError(f"unknown model: {model}")

def _parse(text):
    m = re.search(r"\{.*\}", text, re.S)  # 前後に説明文が付いてもJSON部分だけ取り出す
    return json.loads(m.group(0) if m else text)

def _anthropic(model, prompt, temperature, max_tokens):
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=180, headers={
        "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
        "content-type": "application/json"}, json={
        "model": model, "max_tokens": max_tokens,
        "system": "出力は指定されたJSONだけにしてください。説明文やコードブロックは付けないでください。",
        "messages": [{"role": "user", "content": prompt}]})
    if r.status_code >= 400:  # 原因が分かるように、APIのエラー内容をログに出す
        print("Anthropic API error:", r.status_code, r.text[:1000])
    r.raise_for_status(); j = r.json()
    text = "".join(b.get("text", "") for b in j["content"] if b.get("type") == "text")
    u = j.get("usage", {})
    return text, u.get("input_tokens", len(prompt)), u.get("output_tokens", max_tokens)

def _google(model, prompt, temperature, max_tokens):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens,
                                 "responseMimeType": "application/json"}}
    r = requests.post(url, params={"key": os.environ["GEMINI_API_KEY"]}, json=body, timeout=180)
    r.raise_for_status(); j = r.json(); u = j.get("usageMetadata", {})
    return (j["candidates"][0]["content"]["parts"][0]["text"], u.get("promptTokenCount", len(prompt)),
            u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0))

def generate_json(prompt, temperature=0.8, role="light", max_tokens=8000):
    S = load("config/settings.yaml")
    model = S["models"][role]
    check_budget()  # 上限に達していたら例外で止める
    call = _anthropic if _provider(model, S) == "anthropic" else _google
    text, tin, tout = call(model, prompt, temperature, max_tokens)
    record(model, tin, tout)
    return _parse(text)
