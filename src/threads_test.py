"""Threadsに1本だけテスト投稿する（Claudeは使わない。queue/ や連載には影響しない）"""
import os, time, requests
TH = "https://graph.threads.net/v1.0"

def main():
    uid, tok = os.environ.get("THREADS_USER_ID"), os.environ.get("THREADS_TOKEN")
    if not uid or not tok:
        raise SystemExit("THREADS_USER_ID または THREADS_TOKEN がSecretsに登録されていません")
    text = (os.environ.get("TEXT") or "").strip()
    if not text: raise SystemExit("投稿する文が空です")
    # 1) トークンとユーザーIDの確認
    me = requests.get(f"{TH}/me", params={"fields": "id,username", "access_token": tok}, timeout=30)
    print("アカウント確認:", me.status_code, me.text[:300])
    me.raise_for_status()
    if me.json().get("id") != uid:
        print("注意: THREADS_USER_ID とトークンのアカウントIDが違います:", me.json().get("id"))
    # 2) 投稿（コンテナ作成 → 公開）
    c = requests.post(f"{TH}/{uid}/threads", params={"media_type": "TEXT", "text": text, "access_token": tok}, timeout=60)
    print("下書き作成:", c.status_code, c.text[:300]); c.raise_for_status()
    time.sleep(5)
    r = requests.post(f"{TH}/{uid}/threads_publish", params={"creation_id": c.json()["id"], "access_token": tok}, timeout=60)
    print("公開:", r.status_code, r.text[:300]); r.raise_for_status()
    print("成功: 投稿ID", r.json().get("id"))

if __name__ == "__main__":
    main()
