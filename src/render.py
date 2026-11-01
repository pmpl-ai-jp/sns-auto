"""カルーセル画像をPillowで生成（画像生成AIは使わない）
デザイン: 濃紺ベースの近未来テイスト（グリッド・光のにじみ・シアンのアクセント）"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from .common import ROOT
from .vendor.phrase import phrases
import os, math, re

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")
# 日本語: Zen Kaku Gothic New（上品で落ち着いた印象）／英字・数字: Inter。どちらも無料・商用可（SIL OFL）
FONT_BOLD = [os.path.join(FONT_DIR, "ZenKakuGothicNew-Bold.ttf"), "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "C:/Windows/Fonts/meiryob.ttc",
             "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"]
FONT_REG = [os.path.join(FONT_DIR, "ZenKakuGothicNew-Medium.ttf"), "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "C:/Windows/Fonts/meiryo.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"]
EXTRA_FONTS = []  # テスト用に差し込めるようにしておく

def _font(cands, size):
    for f in EXTRA_FONTS + cands:
        if os.path.exists(f): return ImageFont.truetype(f, size)
    return ImageFont.load_default()
FONT_LATIN = [os.path.join(FONT_DIR, "Inter.ttf")]

class Mix:
    """日本語はZen Kaku、英数字はInterで描くための組み合わせフォント"""
    def __init__(self, jp, lat, size): self.jp, self.lat, self.size = jp, lat, size

def _runs(text):
    out = []
    for ch in text:
        is_lat = ord(ch) < 0x2E80 and ch not in "・。、"
        if out and out[-1][0] == is_lat: out[-1][1] += ch
        else: out.append([is_lat, ch])
    return out

def mlen(d, text, f):
    if not isinstance(f, Mix): return d.textlength(text, font=f)
    return sum(d.textlength(t, font=f.lat if l else f.jp) for l, t in _runs(text))

def mtext(d, xy, text, f, fill):
    if not isinstance(f, Mix): d.text(xy, text, font=f, fill=fill); return
    x, y = xy
    for l, t in _runs(text):
        ft = f.lat if l else f.jp
        # 英字のベースライン（文字の底の線）を日本語のベースラインにそろえる
        dy = (f.jp.getmetrics()[0] - f.lat.getmetrics()[0]) if l else 0
        kw = {"features": ["cv08"]} if l else {}       # Interの「I」をセリフ付きにして「l」と見分ける
        try: d.text((x, y + dy), t, font=ft, fill=fill, **kw)
        except Exception: d.text((x, y + dy), t, font=ft, fill=fill)
        x += d.textlength(t, font=ft)

def _bold_raw(size): return _font(FONT_BOLD, size)
def latin(size, weight=700):
    """英字・数字用（Inter）。可変フォントなので太さを指定する"""
    for f in FONT_LATIN:
        if os.path.exists(f):
            ft = ImageFont.truetype(f, size)
            try: ft.set_variation_by_axes([size if size < 32 else 32, weight])
            except Exception:
                try: ft.set_variation_by_axes([weight])
                except Exception: pass
            return ft
    return _bold_raw(size)
def bold(size): return Mix(_bold_raw(size), latin(size, 700), size)
def reg(size): return Mix(_font(FONT_REG, size), latin(size, 500), size)

W = H = 1080
M = 84                                   # 左右の余白
BG1, BG2 = (8, 16, 40), (14, 40, 92)     # 濃紺のグラデーション
CYAN, BLUE = (56, 189, 248), (59, 130, 246)
WHITE, SOFT, MUTED = (241, 245, 255), (191, 208, 240), (120, 145, 190)
CARD = (255, 255, 255, 18)
NO_HEAD = set("。、，．・：；！？）」』】〉》ー…ぁぃぅぇぉっゃゅょァィゥェォッャュョ")
WEAK_HEAD = set("てでたにをはがのもと")  # 助詞・接続の文字は、行頭に来ないよう前の語ごと送る
NO_TAIL = set("（「『【〈《")

def _units(para):
    """改行してよい単位（文節）に分ける。行頭禁則の文字は前に、開き括弧は後ろにくっつける"""
    merged = []
    for u in phrases(para):
        if merged and (u[0] in NO_HEAD or merged[-1][-1] in NO_TAIL):
            merged[-1] += u
        else:
            merged.append(u)
    return merged

def _greedy(d, units, f, max_w):
    """文節単位で詰める。文節が1行に入らないときだけ文字で切る（そのときは split=True）"""
    lines, line, split = [], "", False
    for u in units:
        if mlen(d, line + u, f) <= max_w or not line:
            if mlen(d, line + u, f) > max_w and not line:   # 1つの文節が長すぎる
                split = True; buf = ""
                for ch in u:
                    if mlen(d, buf + ch, f) <= max_w or not buf or ch in NO_HEAD: buf += ch
                    else: lines.append(buf); buf = ch
                line = buf
            else:
                line += u
            continue
        lines.append(line); line = u
        if mlen(d, line, f) > max_w:
            split = True; buf = ""
            for ch in u:
                if mlen(d, buf + ch, f) <= max_w or not buf or ch in NO_HEAD: buf += ch
                else: lines.append(buf); buf = ch
            line = buf
    lines.append(line)
    return [l for l in lines if l], split

def wrap(d, text, f, max_w, info=None):
    """言葉の途中で改行しない。「。」の後ろはなるべく改行する。最後の行が極端に短いときだけ整える"""
    lines, split_any = [], False
    paras = []
    for para in str(text).split("\n"):
        parts = [x for x in re.split(r"(?<=。)", para) if x]
        if len(parts) > 1 and all(mlen(d, x, f) <= max_w for x in parts): paras += parts
        else: paras.append(para)
    for para in paras:
        units = _units(para)
        ls, sp = _greedy(d, units, f, max_w); split_any |= sp
        # 最後の行が4文字以下なら、前の行の最後の文節を1つ送る（言葉の途中では切らない）
        if len(ls) >= 2 and len(ls[-1]) <= 4 and not sp:
            ph = _units(ls[-2])
            if len(ph) >= 2 and mlen(d, ph[-1] + ls[-1], f) <= max_w:
                ls[-2] = "".join(ph[:-1]); ls[-1] = ph[-1] + ls[-1]
        lines += ls
    if info is not None: info["split"] = split_any
    return lines

def _clean(text, ls):
    """「。」が行の途中に来ていない（文の区切りで改行できている）か"""
    return all(l.endswith("。") or "。" not in l for l in ls)

def fit(d, text, mk, max_w, max_lines, start, min_size):
    """max_lines 行に収まる最大の文字サイズを探す。
    言葉の途中で切れない＞文の区切りで改行できる＞大きい、の順で優先する"""
    size, cands = start, []
    while size >= min_size:
        f = mk(size); info = {}; ls = wrap(d, text, f, max_w, info)
        if len(ls) <= max_lines:
            score = (0 if not info["split"] else 2) + (0 if _clean(text, ls) else 1)
            cands.append((score, -size, f, ls, size))
            if score == 0: break
        size -= 4
    if cands:
        cands.sort(key=lambda c: (c[0], c[1])); _, _, f, ls, size = cands[0]
        return f, ls, size, cands[0][0] < 2
    f = mk(min_size); return f, wrap(d, text, f, max_w), min_size, False

def background(seed):
    im = Image.new("RGB", (W, H))
    px = im.load()
    for y in range(H):                              # 斜めのグラデーション
        for x in range(0, W, 4):
            t = (x * 0.4 + y * 0.6) / (W * 0.4 + H * 0.6)
            c = tuple(int(BG1[i] + (BG2[i] - BG1[i]) * t) for i in range(3))
            for dx in range(4): px[x + dx, y] = c
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0)); g = ImageDraw.Draw(glow)
    cx, cy = (W - 160, 160) if seed % 2 == 0 else (180, H - 200)
    g.ellipse([cx - 320, cy - 320, cx + 320, cy + 320], fill=(56, 189, 248, 70))
    glow = glow.filter(ImageFilter.GaussianBlur(140))
    im = Image.alpha_composite(im.convert("RGBA"), glow)
    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0)); gd = ImageDraw.Draw(grid)
    for v in range(0, W, 60):
        gd.line([(v, 0), (v, H)], fill=(120, 170, 255, 14)); gd.line([(0, v), (W, v)], fill=(120, 170, 255, 14))
    return Image.alpha_composite(im, grid)

def header_footer(im, i, n):
    d = ImageDraw.Draw(im)
    d.rectangle([M, 60, M + 56, 66], fill=CYAN)
    d.text((M + 72, 44), "PM/PL × AI", font=latin(26, 600), fill=SOFT)
    for k in range(n):                              # 進捗ドット
        x = W - M - (n - k) * 22
        d.ellipse([x, 52, x + 10, 62], fill=CYAN if k == i else (70, 95, 150))
    d.line([(M, H - 104), (W - M, H - 104)], fill=(90, 120, 180), width=1)
    d.text((M, H - 84), "@pmpl_ai", font=latin(28, 600), fill=SOFT)
    d.text((W - M - 86, H - 84), f"{i+1:02d}/{n:02d}", font=latin(28, 500), fill=MUTED)

def card(im, box):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); od = ImageDraw.Draw(ov)
    od.rounded_rectangle(box, radius=28, fill=CARD, outline=(120, 170, 255, 70), width=2)
    return Image.alpha_composite(im, ov)

def slide_type(i, n, s):
    t = s.get("type")
    if t: return t
    if i == 0: return "cover"
    if i == n - 1: return "cta"
    if i == n - 2 and ("・" in s.get("body", "") or "\n" in s.get("body", "")): return "checklist"
    if i == 1: return "why"
    return "point"

def draw_slide(i, n, s, pr, point_no):
    im = background(i); d = ImageDraw.Draw(im); warn = []
    kind = slide_type(i, n, s); max_w = W - M * 2
    if kind == "cover":
        tf0, tl0, ts0, _ = fit(d, s["title"], bold, max_w, 3, 96, 60)
        bf0, bl0, bs0, _ = fit(d, s.get("body", ""), reg, max_w, 3, 40, 32)
        total = 100 + len(tl0) * int(ts0 * 1.28) + 30 + 58 + len(bl0) * int(bs0 * 1.55)
        y = max(130, (H - 104 - total) // 2 + 20)      # 表紙は上下中央に置く
        tag = "PR" if pr else "保存版"
        tw = mlen(d, tag, bold(30)) + 44
        d.rounded_rectangle([M, y, M + tw, y + 52], radius=26, outline=CYAN, width=2)
        mtext(d, (M + 22, y + 8), tag, bold(30), CYAN); y += 100
        tf, tl, ts, ok = fit(d, s["title"], bold, max_w, 3, 96, 60)
        if not ok: warn.append("表紙のタイトルが長すぎて、言葉の途中で改行される。16字以内に短くする")
        if s["title"].rstrip().endswith(("？", "?")): warn.append("表紙のタイトルが問いかけで終わっている。読者がとる行動で言い切る形にする")
        if any(w in s.get("body", "") for w in ("保存版", "PR")): warn.append("表紙の補足に「保存版」「PR」が入っていてラベルと重複している。補足からは消す")
        for line in tl:
            mtext(d, (M, y), line, tf, WHITE); y += int(ts * 1.28)
        y += 30; d.rectangle([M, y, M + 120, y + 8], fill=CYAN); y += 50
        bf, bl, bs, ok = fit(d, s.get("body", ""), reg, max_w, 3, 40, 32)
        if not ok: warn.append("表紙の補足が長すぎる")
        for line in bl:
            mtext(d, (M, y), line, bf, SOFT); y += int(bs * 1.55)
        bottom = y
    elif kind == "cta":
        tf, tl, ts, ok = fit(d, s["title"], bold, max_w, 2, 76, 52)
        bf, bl, bs, ok2 = fit(d, s.get("body", ""), reg, max_w - 80, 5, 40, 30)
        card_h = len(bl) * int(bs * 1.55) + 80
        total = len(tl) * int(ts * 1.3) + 40 + card_h + 50 + 76
        y = max(150, (H - 104 - total) // 2 + 20)       # 上下の余白をそろえて中央に置く
        for line in tl:
            mtext(d, (M, y), line, tf, WHITE); y += int(ts * 1.3)
        y += 40
        im = card(im, [M, y, W - M, y + card_h]); d = ImageDraw.Draw(im)
        if not ok2: warn.append("最後のスライドの文が長すぎる")
        yy = y + 40
        for line in bl:
            mtext(d, (M + 40, yy), line, bf, SOFT); yy += int(bs * 1.55)
        y += card_h + 50
        d.rounded_rectangle([M, y, M + 420, y + 76], radius=38, fill=CYAN)
        mtext(d, (M + 40, y + 16), "保存して、あとで使う", bold(34), BG1)
        bottom = y + 76
    else:
        y = 140
        if kind == "point":
            d.text((M, y - 16), f"{point_no:02d}", font=latin(120, 300), fill=CYAN); y += 150
        elif kind == "checklist":
            d.text((M, y), "CHECK LIST", font=latin(34, 600), fill=CYAN); y += 70
        else:
            d.text((M, y), "WHY", font=latin(34, 600), fill=CYAN); y += 70
        tf, tl, ts, ok = fit(d, s["title"], bold, max_w, 2, 66, 48)
        if not ok: warn.append(f"{i+1}枚目のタイトルが長すぎる")
        for line in tl:
            mtext(d, (M, y), line, tf, WHITE); y += int(ts * 1.3)
        y += 36
        top = y; inner = max_w - 80
        if kind == "checklist":
            body = s.get("body", "")
            # 改行があれば改行で区切る（「抽出・変換」のような語中の「・」では区切らない）。なければ行頭の「・」で区切る
            raw = body.split("\n") if "\n" in body.strip() else re.split(r"(?:^|(?<=[^\s・]))・(?=[^・])", body) if body.startswith("・") else [body]
            items = [x.strip(" ・-□") for x in raw if x.strip(" ・-□")]
            if len(items) > 6: warn.append(f"{i+1}枚目のチェックリストが6項目を超えている。6項目以内にまとめる")
            f = reg(40); rows = []
            for it in items[:6]: rows.append(wrap(d, it, f, inner - 70))
            h = sum(len(r) * 60 + 30 for r in rows) + 50
            im = card(im, [M, top, W - M, top + h]); d = ImageDraw.Draw(im); yy = top + 40
            for r in rows:
                d.rounded_rectangle([M + 40, yy + 6, M + 78, yy + 44], radius=8, outline=CYAN, width=3)
                for k, line in enumerate(r):
                    mtext(d, (M + 100, yy + k * 60), line, f, WHITE)
                yy += len(r) * 60 + 30
            bottom = top + h
        else:
            bf, bl, bs, ok = fit(d, s.get("body", ""), reg, inner, 7, 42, 32)
            if not ok: warn.append(f"{i+1}枚目の本文が長すぎて、言葉の途中で改行される。短くする")
            if re.search(r"(^|\n)(悩み|例|質問|ポイント)：", s.get("body", "")): warn.append(f"{i+1}枚目の本文に「例：」「質問：」のようなラベルが入っている。ラベルを付けず自然な文にする")
            h = len(bl) * int(bs * 1.6) + 80
            im = card(im, [M, top, W - M, top + h]); d = ImageDraw.Draw(im); yy = top + 40
            d.rectangle([M, top + 30, M + 6, top + h - 30], fill=CYAN)
            for line in bl:
                mtext(d, (M + 40, yy), line, bf, SOFT); yy += int(bs * 1.6)
            bottom = top + h
    if bottom > H - 124: warn.append(f"{i+1}枚目の文字が下の帯にはみ出している")
    header_footer(im, i, n)
    return im.convert("RGB"), warn

def render_carousel(post_id, slides, pr=False):
    """画像を作り、(パスの一覧, 機械チェックで見つかった問題) を返す"""
    out = ROOT / "media" / post_id; out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.jpg"): old.unlink()
    paths, warns, n, pno = [], [], len(slides), 0
    for i, s in enumerate(slides):
        if slide_type(i, n, s) == "point": pno += 1
        im, w = draw_slide(i, n, s, pr, pno); warns += w
        p = out / f"{i+1}.jpg"; im.save(p, quality=92)
        paths.append(str(p.relative_to(ROOT)).replace("\\", "/"))
    return paths, warns


def render_note_header(title, out_path, label="運用ログ"):
    """noteの見出し画像（1280×670）を、Instagramと同じデザインで作る"""
    global W, H
    w0, h0 = W, H
    W, H = 1280, 670
    try:
        im = background(0); d = ImageDraw.Draw(im); max_w = W - M * 2
        d.rectangle([M, 70, M + 56, 76], fill=CYAN)
        d.text((M + 72, 54), "PM/PL × AI", font=latin(28, 600), fill=SOFT)
        tw = mlen(d, label, bold(30)) + 44
        d.rounded_rectangle([M, 140, M + tw, 192], radius=26, outline=CYAN, width=2)
        mtext(d, (M + 22, 148), label, bold(30), CYAN)
        tf, tl, ts, _ = fit(d, title, bold, max_w, 3, 76, 48)
        y = 230
        for line in tl:
            mtext(d, (M, y), line, tf, WHITE); y += int(ts * 1.3)
        d.text((M, H - 80), "@pmpl_ai", font=latin(28, 600), fill=SOFT)
        im.convert("RGB").save(out_path, quality=92)
    finally:
        W, H = w0, h0
    return out_path
