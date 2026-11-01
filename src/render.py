"""カルーセル画像をPillowで生成（画像生成AIは使わない）"""
from PIL import Image, ImageDraw, ImageFont
from .common import ROOT
import textwrap, os

FONT_CANDIDATES = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                   "C:/Windows/Fonts/meiryob.ttc", "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"]
def font(size):
    for f in FONT_CANDIDATES:
        if os.path.exists(f): return ImageFont.truetype(f, size)
    return ImageFont.load_default()

W = H = 1080
BG, FG, ACCENT = (250, 248, 243), (30, 30, 30), (37, 99, 235)

def render_carousel(post_id, slides, pr=False):
    out = ROOT / "media" / post_id; out.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, s in enumerate(slides):
        im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W, 16], fill=ACCENT)
        if pr and i == 0: d.text((60, 50), "PR", font=font(40), fill=ACCENT)
        y = 200 if i == 0 else 140
        for line in textwrap.wrap(s["title"], 12):
            d.text((60, y), line, font=font(84 if i == 0 else 64), fill=FG); y += 110
        y += 40
        for line in textwrap.wrap(s.get("body", ""), 20):
            d.text((60, y), line, font=font(44), fill=FG); y += 70
        d.text((W - 160, H - 90), f"{i+1}/{len(slides)}", font=font(36), fill=(120, 120, 120))
        p = out / f"{i+1}.jpg"; im.save(p, quality=90)
        paths.append(str(p.relative_to(ROOT)).replace("\\", "/"))
    return paths
