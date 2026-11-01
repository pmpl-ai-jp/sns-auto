"""日本語を文節（意味のかたまり）に区切る。
Google の BudouX（Apache License 2.0, Copyright 2021 Google LLC）の解析ロジックと日本語モデルを同梱したもの。
https://github.com/google/budoux"""
import json, os
_MODEL = json.load(open(os.path.join(os.path.dirname(__file__), "budoux_ja.json"), encoding="utf-8"))
_BASE = -sum(sum(g.values()) for g in _MODEL.values()) * 0.5

def phrases(s):
    if not s: return []
    m = _MODEL; out = [s[0]]
    for i in range(1, len(s)):
        sc = _BASE
        if i > 2: sc += m.get("UW1", {}).get(s[i-3], 0)
        if i > 1: sc += m.get("UW2", {}).get(s[i-2], 0)
        sc += m.get("UW3", {}).get(s[i-1], 0)
        sc += m.get("UW4", {}).get(s[i], 0)
        if i + 1 < len(s): sc += m.get("UW5", {}).get(s[i+1], 0)
        if i + 2 < len(s): sc += m.get("UW6", {}).get(s[i+2], 0)
        if i > 1: sc += m.get("BW1", {}).get(s[i-2:i], 0)
        sc += m.get("BW2", {}).get(s[i-1:i+1], 0)
        if i + 1 < len(s): sc += m.get("BW3", {}).get(s[i:i+2], 0)
        if i > 2: sc += m.get("TW1", {}).get(s[i-3:i], 0)
        if i > 1: sc += m.get("TW2", {}).get(s[i-2:i+1], 0)
        if i + 1 < len(s): sc += m.get("TW3", {}).get(s[i-1:i+2], 0)
        if i + 2 < len(s): sc += m.get("TW4", {}).get(s[i:i+3], 0)
        if sc > 0: out.append(s[i])
        else: out[-1] += s[i]
    return out
