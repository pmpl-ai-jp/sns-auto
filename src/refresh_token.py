"""週1回: 60日トークンを更新し、GitHub Secretsを上書き（gh CLIを使用）"""
import os, subprocess, requests

def refresh(url, grant, token):
    r = requests.get(url, params={"grant_type": grant, "access_token": token}, timeout=30)
    r.raise_for_status(); return r.json()["access_token"]

def set_secret(name, value):
    subprocess.run(["gh", "secret", "set", name, "--body", value], check=True)

if __name__ == "__main__":
    set_secret("THREADS_TOKEN", refresh("https://graph.threads.net/refresh_access_token", "th_refresh_token", os.environ["THREADS_TOKEN"]))
    set_secret("IG_TOKEN", refresh("https://graph.instagram.com/refresh_access_token", "ig_refresh_token", os.environ["IG_TOKEN"]))
    print("tokens refreshed")
