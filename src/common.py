import os, yaml, json, pathlib, datetime
ROOT = pathlib.Path(__file__).resolve().parent.parent
JST = datetime.timezone(datetime.timedelta(hours=9))

def load(path):
    with open(ROOT / path, encoding="utf-8") as f:
        return yaml.safe_load(f)

def now():
    return datetime.datetime.now(JST)

def killed():
    return (ROOT / "config/KILL_SWITCH").read_text().strip().upper() == "ON"

def queue_dir():
    d = ROOT / "queue"; d.mkdir(exist_ok=True); return d

def save_post(post):
    p = queue_dir() / f"{post['id']}.json"
    p.write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8")
    return p

def iter_posts():
    for p in sorted(queue_dir().glob("*.json")):
        yield p, json.loads(p.read_text(encoding="utf-8"))

def launch_date():
    """最初に生成した日を data/launch.json に記録して返す"""
    p = ROOT / "data" / "launch.json"
    if not p.exists():
        p.parent.mkdir(exist_ok=True)
        p.write_text(json.dumps({"launch": now().date().isoformat()}))
    return datetime.date.fromisoformat(json.loads(p.read_text())["launch"])

def in_warmup():
    w = load("config/settings.yaml").get("warmup") or {}
    return (now().date() - launch_date()).days < w.get("days", 0)

def setting(key):
    """立ち上げ期間中は warmup の値を優先して返す"""
    S = load("config/settings.yaml"); w = S.get("warmup") or {}
    return w[key] if in_warmup() and key in w else S[key]
