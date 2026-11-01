"""週1回: 60日トークンを更新し、GitHub Secretsを上書き（gh CLIを使用）
Secretsが未登録のトークンはスキップする（Threadsを後から始める場合など）"""
import os, subprocess, requests

def refresh(url, grant, token):
    r = requests.get(url, params={"grant_type": grant, "access_token": token}, timeout=30)
    r.raise_for_status(); return r.json()["access_token"]

def set_secret(name, value):
    subprocess.run(["gh", "secret", "set", name, "--body", value], check=True)

TARGETS = [
    # IG_TOKEN はシステムユーザートークン（無期限）なので更新しない
    ("THREADS_TOKEN", "https://graph.threads.net/refresh_access_token", "th_refresh_token"),
]

if __name__ == "__main__":
    for name, url, grant in TARGETS:
        tok = os.environ.get(name)
        if not tok:
            print(f"{name}: 未登録のためスキップ"); continue
        set_secret(name, refresh(url, grant, tok)); print(f"{name}: 更新しました")
