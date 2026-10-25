#!/usr/bin/env python3
"""成片英文字幕 + 人物铭牌（欧美短剧风格），烧录进画面。定稿样式见 protocols/TITLE_STYLE.md。

本机 ffmpeg 不带 libass / drawtext，所以用 Pillow 把每条字幕、每块铭牌画成 1080×1920 透明图层，
再用 ffmpeg overlay 叠加（淡入淡出、铭牌滑入）。

用法：python3 tools/subtitle_episode.py E01 --video 08_edit/E01_full_v3.1.mp4 --words <whisper 词级 json>
- 字幕文字一律取 02_dialogue_lock.json（逐字），只借 Whisper 的词级时间点对齐；
- 铭牌读 episodes/Exx/titles.json；
- 输出 <video>_subs.mp4（1080×1920）+ <video>_subs.srt（同步的纯文本字幕，平台上传用）。
"""
import argparse, difflib, json, os, re, shutil, subprocess
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__)); PIPE = os.path.dirname(HERE)
W, H = 1080, 1920
# ===== 定稿样式（2026-10-10 用户确认，见 protocols/TITLE_STYLE.md）=====
# 字幕：圆体粗字（SF Rounded Heavy）+ 黄字黑边 + 柔和投影
# 铭牌：电影衬线（Didot，参考欧美 AI 短剧"Callie"式）：大号首字母大写、半透明白、柔光投影，下配细线 + 小号大写身份行（Copperplate Light）
SUP = "/System/Library/Fonts/Supplemental/"
def _rounded(size):
    f = ImageFont.truetype("/System/Library/Fonts/SFNSRounded.ttf", size)
    try: f.set_variation_by_name("Heavy")
    except Exception: f = ImageFont.truetype(SUP + "Arial Rounded Bold.ttf", size)
    return f
F_SUB = _rounded(54)
SUB_FILL, SUB_STROKE, SUB_STROKE_W = (255, 205, 40, 255), (16, 16, 16, 255), 7
DIDOT = SUP + "Didot.ttc"; COPPER = SUP + "Copperplate.ttc"
NAME_SIZE, NAME_ALPHA, NAME_MAXW = 190, 0.86, 0.60     # 名字字号 / 不透明度 / 最大宽度（占画面宽）
ROLE_SIZE, ROLE_TRACK = 30, 7
TAG_NAME_SIZE, TAG_ROLE_SIZE = 96, 27                  # 远景人物的指示线小标签
SUB_Y = 0.80                                           # 字幕块中心高度（避开平台底部按钮区）
MAX_CH = 30                                            # 每行字符上限


def norm(w):
    return re.sub(r"[^a-z0-9]", "", w.lower())


def tracked(draw, xy, text, font, fill, track=0, **kw):
    """带字距的文字；返回宽度。"""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill, **kw)
        x += draw.textlength(ch, font=font) + track
    return x - xy[0] - track


def text_w(text, font, track=0):
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    return sum(d.textlength(c, font=font) for c in text) + track * (len(text) - 1)


# ---------------- 字幕 ----------------
def align(lock_lines, words):
    """把台词原文的每个词对到 Whisper 的词级时间。"""
    lw = []                                            # (line_idx, word)
    for i, L in enumerate(lock_lines):
        lw += [(i, w) for w in L["text_en"].split()]
    hw = [(x["word"].strip(), x["start"], x["end"]) for x in words]
    a = [norm(w) for _, w in lw]; b = [norm(w) for w, _, _ in hw]
    t = [None] * len(lw)
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            for k in range(i2 - i1): t[i1 + k] = (hw[j1 + k][1], hw[j1 + k][2])
        elif op == "replace" and j2 > j1:              # 如 rubber, Cade → rubbercade：按词数均分时间
            s, e = hw[j1][1], hw[j2 - 1][2]; n = i2 - i1
            for k in range(n): t[i1 + k] = (s + (e - s) * k / n, s + (e - s) * (k + 1) / n)
    # 1) 离群词：小词（the / is / of）会在整集转写里对到很远的位置；同一句里偏离中位数太远的时间当作没对上
    import statistics
    for i in sorted({x[0] for x in lw}):
        ks = [k for k in range(len(lw)) if lw[k][0] == i and t[k]]
        if len(ks) >= 2:
            med = statistics.median(t[k][0] for k in ks); lim = max(6.0, 0.7 * len(ks) + 3)
            for k in ks:
                if abs(t[k][0] - med) > lim: t[k] = None
    # 2) 没对上的词：只在同一句内用相邻词推算（每词约 0.4 s），不跨句借用时间，避免字幕挂到前面很远的位置
    for k in range(len(t)):
        if t[k] is None:
            ln = lw[k][0]
            pk = next((j for j in range(k - 1, -1, -1) if lw[j][0] == ln and t[j]), None)
            nk = next((j for j in range(k + 1, len(t)) if lw[j][0] == ln and t[j]), None)
            if pk is not None and nk is not None:
                s = max(t[pk][1], t[nk][0] - 0.4 * (nk - k)); e = min(t[nk][0], s + 0.4)
            elif nk is not None:
                s = t[nk][0] - 0.4 * (nk - k); e = s + 0.4
            elif pk is not None:
                s = t[pk][1] + 0.05 + 0.4 * (k - pk - 1); e = s + 0.4
            else:                                      # 整句都没对上：接在前一句之后
                pj = next((j for j in range(k - 1, -1, -1) if t[j]), None)
                s = (t[pj][1] + 0.3 if pj is not None else 0.0) + 0.4 * sum(1 for j in range(k) if lw[j][0] == ln and t[j] is None)
                e = s + 0.4
            t[k] = (s, max(e, s + 0.15))
    t = [(s, min(e, s + 1.2)) for s, e in t]            # 词级时间偶尔把句尾词拉得很长（话被打断、后面是静音/混响），字幕会挂几十秒；单词最长 1.2 s
    return [(i, w, ts) for (i, w), ts in zip(lw, t)]


def chunks(aligned):
    """先按整句（. ? !）切；超过两行的句子从最靠近中间的逗号切，没有逗号再从中间的词切。"""
    sents, cur = [], []
    for k, item in enumerate(aligned):
        if cur and cur[-1][0] != item[0]:
            sents.append(cur); cur = []
        cur.append(item)
        if re.search(r"[.?!]$", item[1]):
            sents.append(cur); cur = []
    if cur: sents.append(cur)

    def split(c):
        txt = " ".join(x[1] for x in c)
        if len(txt) <= 2 * MAX_CH - 4: return [c]
        mid = len(txt) / 2; pos, best = 0, None
        for k, x in enumerate(c[:-1]):
            pos += len(x[1]) + 1
            score = abs(pos - mid) - (40 if x[1].endswith(",") else 0)
            if best is None or score < best[0]: best = (score, k)
        k = best[1]
        return split(c[:k + 1]) + split(c[k + 1:])
    out = [p for c in sents for p in split(c)]
    subs = []
    for c in out:
        subs.append({"text": " ".join(x[1] for x in c), "start": c[0][2][0] - 0.08, "end": c[-1][2][1] + 0.3})
    for a, b in zip(subs, subs[1:]):                   # 不重叠，最短 0.9s
        a["end"] = min(a["end"], b["start"] - 0.04)
    # 极短的单句（"Father."）延长到 0.9s 时会和下一条重叠、两条字幕叠在一起：能并进下一条就并（≤两行），否则只延长到下一条开始前
    merged = []
    for x in subs:
        if merged and (x["start"] - merged[-1]["start"] < 0.9) and len(merged[-1]["text"] + " " + x["text"]) <= 2 * MAX_CH - 4:
            merged[-1] = {"text": merged[-1]["text"] + " " + x["text"], "start": merged[-1]["start"], "end": x["end"]}
        else:
            merged.append(dict(x))
    subs = merged
    for i, x in enumerate(subs):
        x["end"] = max(x["end"], x["start"] + 0.9)
        if i + 1 < len(subs): x["end"] = min(x["end"], subs[i + 1]["start"] - 0.04)
    for x in subs:                                     # 兜底：短句不会说几十秒
        nw = len(x["text"].split())
        if x["end"] - x["start"] > 6 and nw <= 10: x["end"] = x["start"] + 0.6 + 0.45 * nw
    return subs


WEAK_END = {"the", "a", "an", "in", "to", "of", "or", "and", "my", "your", "with", "at", "on", "into"}


def wrap(text):
    """两行尽量等长；优先在逗号后换行，行尾不停在冠词/介词上，数字不和前一个词拆开。"""
    words = text.split(); best = None
    if len(text) <= MAX_CH: return [text]
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        score = abs(len(a) - len(b))
        if len(a) > MAX_CH + 4 or len(b) > MAX_CH + 4: score += 100
        if words[k - 1].endswith(","): score -= 12
        if words[k - 1].lower().strip(",.") in WEAK_END: score += 15
        if re.match(r"\d", words[k]): score += 30
        if best is None or score < best[0]: best = (score, [a, b])
    return best[1]


def render_sub(text, path):
    lines = wrap(text)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    f = F_SUB
    while f.size > 44 and max(d.textlength(ln, font=f) for ln in lines) + 2 * SUB_STROKE_W > 2 * HALF - 20:   # 右侧按钮区：长行缩字号
        f = _rounded(f.size - 2)
    lh = int(f.size * 1.3); y0 = int(SUB_Y * H - lh * len(lines) / 2)
    y0 = min(y0, SY1 - lh * len(lines) - 8)                                                            # 底边不进平台文案区
    for i, ln in enumerate(lines):
        x = (W - d.textlength(ln, font=f)) / 2
        d.text((x, y0 + i * lh), ln, font=f, fill=SUB_FILL, stroke_width=SUB_STROKE_W, stroke_fill=SUB_STROKE)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img.alpha_composite(soft(lay, 6, (0, 0, 0), 0.45), (0, 4))
    img.alpha_composite(lay)
    img.save(path)


def soft(layer, radius, color, alpha):
    """用图层的透明度做柔光/投影。"""
    a_ = layer.split()[-1].filter(ImageFilter.GaussianBlur(radius)).point(lambda v: int(v * alpha))
    g = Image.new("RGBA", layer.size, color + (0,)); g.putalpha(a_); return g


def name_mask(text, font, track=2, pad=40):
    w = int(text_w(text, font, track)) + 2 * pad; asc, desc = font.getmetrics()
    m = Image.new("L", (w, asc + desc + 2 * pad), 0)
    tracked(ImageDraw.Draw(m), (pad, pad), text, font, 255, track)
    return m


# ---------------- 铭牌 ----------------
def render_plate(p, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    name, role = p["name"], p["role"].upper()
    big = p["style"] in ("left", "right")
    size = NAME_SIZE if big else TAG_NAME_SIZE
    fn = ImageFont.truetype(DIDOT, size, index=0)
    while big and text_w(name, fn, 2) > NAME_MAXW * W and size > 96:      # 长名字自动缩小
        size -= 6; fn = ImageFont.truetype(DIDOT, size, index=0)
    fr = ImageFont.truetype(COPPER, ROLE_SIZE if big else TAG_ROLE_SIZE, index=1)
    m = name_mask(name, fn)
    white = Image.new("RGBA", m.size, (255, 255, 255, 0)); white.putalpha(m.point(lambda v: int(v * NAME_ALPHA)))
    layer = Image.new("RGBA", m.size, (0, 0, 0, 0))
    layer.alpha_composite(soft(white, 18 if big else 10, (0, 0, 0), 0.55), (4, 8))
    layer.alpha_composite(soft(white, 10 if big else 6, (255, 255, 255), 0.25))
    layer.alpha_composite(white)
    bbox = m.getbbox(); nw = bbox[2] - bbox[0]; rw = text_w(role, fr, ROLE_TRACK)
    margin = 70; y = int(p["y"] * H)
    if p["style"] == "right": margin = max(70, W - SX1 + 24)                 # 右侧按钮区
    elif p["style"] == "left": margin = max(70, SX0 + 24)
    if PROF.get("safe") and big and not (SY0 <= y - 40 and y + 120 <= SY1):
        SAFE_WARN.append(f"铭牌 {name} y={p['y']} 超出 TikTok 安全框（{SY0 / H:.2f}–{SY1 / H:.2f}）")
    if p["style"] == "left":
        nx = margin - bbox[0]; lx0 = margin + 6
    elif p["style"] == "right":
        nx = W - margin - bbox[2]; lx0 = W - margin - max(rw, 90) - 2
    else:                                               # 指示线小标签：放在目标人物左上方
        tx, ty = p["target"][0] * W, p["target"][1] * H
        right = tx - 36; nx = int(right - bbox[2])
        lx0 = right - rw
    img.alpha_composite(layer, (int(nx), y - 40))
    d = ImageDraw.Draw(img)
    ry = y - 40 + bbox[3] + (18 if big else 10)
    if p["style"] == "right":
        rx = W - margin - rw; d.line([(W - margin - 90, ry - 10), (W - margin - 2, ry - 10)], fill=(255, 255, 255, 200), width=2)
    elif p["style"] == "left":
        rx = margin + 8; d.line([(margin + 6, ry - 10), (margin + 90, ry - 10)], fill=(255, 255, 255, 200), width=2)
    else:
        rx = lx0; d.line([(right - 60, ry - 7), (right, ry - 7)], fill=(255, 255, 255, 200), width=2)
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0)); tracked(ImageDraw.Draw(sh), (rx, ry), role, fr, (0, 0, 0, 255), ROLE_TRACK)
    img.alpha_composite(soft(sh, 4, (0, 0, 0), 0.6), (1, 2))
    tracked(d, (rx, ry), role, fr, (255, 255, 255, 220), ROLE_TRACK)
    if p["style"] == "pointer":                         # 细引线 + 小圆点指向远景人物
        d.line([(right + 6, ry + 14), (tx, ty - 28)], fill=(255, 255, 255, 210), width=2)
        d.ellipse([tx - 7, ty - 35, tx + 7, ty - 21], outline=(255, 255, 255, 230), width=2)
    img.save(path)


def srt_time(t):
    h, r = divmod(max(0, t), 3600); m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"


ap = argparse.ArgumentParser()
ap.add_argument("episode"); ap.add_argument("--video", required=True); ap.add_argument("--words", required=True)
ap.add_argument("--report", help="assemble_episode 的切点报告 json（默认与 --video 同名 .json）；铭牌/插入文字用段内时间时需要")
ap.add_argument("--overlays", help="屏幕文字插入配置（默认 episodes/Exx/overlays.json，存在才用）")
a = ap.parse_args()
ep = os.path.join(PIPE, "episodes", a.episode)
from delivery import profile, safe_box                 # 交付标准（delivery.json）：E31 起 TikTok 安全区 + 字幕位置
PROF = profile(a.episode); SX0, SY0, SX1, SY1 = safe_box(PROF, W, H); SUB_Y = PROF["sub_y"]
HALF = min(W / 2 - SX0, SX1 - W / 2)                   # 居中元素在安全框内可用的半宽
SAFE_WARN = []
video = os.path.join(ep, a.video)
lock = json.load(open(os.path.join(ep, "02_dialogue_lock.json"), encoding="utf-8"))["lines"]
words = [x for s in json.load(open(a.words, encoding="utf-8"))["segments"] for x in s["words"]]
titles = json.load(open(os.path.join(ep, "titles.json"), encoding="utf-8"))["plates"]
rep_path = a.report and os.path.join(ep, a.report) or os.path.splitext(video)[0] + ".json"
rep = json.load(open(rep_path, encoding="utf-8")) if os.path.isfile(rep_path) else None
def T(seg, local):
    """段内时间（该段原片里的秒）→ 成片时间轴"""
    g = next(s for s in rep["segments"] if s["id"] == seg)
    return round(g["t0"] + (local - g["in"]), 3)
for pl in titles:
    if "seg" in pl:
        pl["t0"], pl["t1"] = T(pl["seg"], pl["l0"]), T(pl["seg"], pl["l1"])
ov_path = a.overlays and os.path.join(ep, a.overlays) or os.path.join(ep, "overlays.json")
overlays = json.load(open(ov_path, encoding="utf-8"))["items"] if os.path.isfile(ov_path) else []
masks = [o for o in overlays if o.get("style") == "mask"]          # H3 自己烧进画面的字幕：box = [x, y, w, h]（成片 1080×1920 的比例，左上为原点）
overlays = [o for o in overlays if o.get("style") != "mask"]

subs = chunks(align(lock, words))
# 画外/广播/电视/电话（post_audio.json 里有 place 的台词）：Whisper 听不到（它们是后期混进去的），按 place 的起点和实际时长给字幕（E51 起）。
try:
    _pa = [l for l in json.load(open(os.path.join(PIPE, "post_audio.json"), encoding="utf-8"))["lines"] if l["episode"] == a.episode and l.get("place")]
except Exception:
    _pa = []
if _pa and rep:                                   # 设备声字幕（原项目 E51 起，工具包默认开启）
    import wave
    for l in _pa:
        pl = l["place"]; wp = os.path.join(ep, "08_edit", "post_audio", l["id"] + ".wav")
        try:
            with wave.open(wp) as w: dur = w.getnframes() / w.getframerate() / pl.get("tempo", 1.0)
        except Exception:
            continue
        t0 = T(pl["seg"], pl["local"]); words_ = l["text"].split(); k0 = 0
        sents = []; cur = []                                 # 按句号/问号/感叹号切（省略号 ... 不算），一条 ≤ 约 52 个字符，太短的尾巴并回前一条
        for wd in words_:
            cur.append(wd)
            if (re.search(r"(?<!\.)[.?!]+[\"”']?$", wd) and not wd.endswith("...")) or len(" ".join(cur)) >= 52:
                sents.append(cur); cur = []
        if cur: sents.append(cur)
        merged = []
        for s in sents:
            if merged and (len(s) < 3 or len(" ".join(s)) < 14): merged[-1] = merged[-1] + s
            else: merged.append(s)
        sents = merged
        tot = sum(len(" ".join(s)) for s in sents)
        for s in sents:
            seg_d = dur * len(" ".join(s)) / tot
            subs.append({"text": " ".join(s), "start": t0 + k0, "end": t0 + k0 + seg_d - 0.04}); k0 += seg_d
    subs.sort(key=lambda x: x["start"])
    for x1, x2 in zip(subs, subs[1:]):
        if x1["end"] > x2["start"] - 0.04: x1["end"] = max(x1["start"] + 0.5, x2["start"] - 0.04)
work = os.path.join(ep, "08_edit", "subs_layers"); shutil.rmtree(work, ignore_errors=True); os.makedirs(work)
def render_insert(it, path):
    """屏幕文字插入：alert = 红色警报大字；doc = 等宽文件/标签文字，半透明黑底 + 橙色竖线。"""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    lines = it["lines"]; y0 = int(it.get("y", 0.6) * H)
    if it["style"] == "alert":
        def fit(ln, size, trk):                      # 每行自动缩字号，保证不超出画面（原先 118 号对 ≥14 个字符的警报会溢出）
            while size > 40 and text_w(ln, ImageFont.truetype(SUP + "Impact.ttf", size), trk) > min(940, 2 * HALF - 20): size -= 4
            return ImageFont.truetype(SUP + "Impact.ttf", size)
        y = y0
        for i, ln in enumerate(lines):
            f = fit(ln, 118 if i == 0 else 52, 3 if i == 0 else 6); tw = text_w(ln, f, 6 if i else 3)
            x = (W - tw) / 2
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
            tracked(ld, (x, y), ln, f, (232, 36, 36, 255), 6 if i else 3)
            glow = lay.filter(ImageFilter.GaussianBlur(14)); im.alpha_composite(glow); im.alpha_composite(lay)
            y += f.getmetrics()[0] + (14 if i == 0 else 8)
        if PROF.get("safe") and not (SY0 <= y0 and y <= SY1):
            SAFE_WARN.append(f"警报叠字 “{lines[0][:24]}” y={it.get('y', 0.6)} 超出 TikTok 安全框（{SY0 / H:.2f}–{SY1 / H:.2f}）")
    else:
        size = 44
        while size > 26 and max(text_w(l, ImageFont.truetype(SUP + "Courier New Bold.ttf", size), 1) for l in lines) > min(880, 2 * HALF - 110): size -= 2   # 最长一行不超出画面
        f = ImageFont.truetype(SUP + "Courier New Bold.ttf", size); lh = int(size * 1.5)
        wmax = max(text_w(l, f, 1) for l in lines); bw = int(wmax) + 90; bh = lh * len(lines) + 56
        x0 = (W - bw) // 2
        box = Image.new("RGBA", (bw, bh), (8, 8, 8, 168)); im.alpha_composite(box, (x0, y0))
        if PROF.get("safe") and not (SY0 <= y0 and y0 + bh <= SY1):
            SAFE_WARN.append(f"叠字 “{lines[0][:24]}” y={it.get('y', 0.6)} 超出 TikTok 安全框（{SY0 / H:.2f}–{SY1 / H:.2f}）")
        d.rectangle([x0, y0, x0 + 7, y0 + bh], fill=(255, 150, 40, 255))
        for i, ln in enumerate(lines):
            tracked(d, (x0 + 40, y0 + 28 + i * lh), ln, f, (255, 255, 255, 255) if i else (255, 190, 90, 255), 1)
    im.save(path)


items = []
for k, s in enumerate(subs):
    p = os.path.join(work, f"sub{k:02d}.png"); render_sub(s["text"], p)
    items.append({"png": p, "t0": s["start"], "t1": s["end"], "fade": 0.08, "slide": 0})
for k, pl in enumerate(titles):
    p = os.path.join(work, f"plate{k:02d}.png"); render_plate(pl, p)
    items.append({"png": p, "t0": pl["t0"], "t1": pl["t1"], "fade": 0.4,
                  "slide": {"left": -24, "right": 24, "pointer": 0}[pl["style"]]})

for k, o in enumerate(overlays):
    p = os.path.join(work, f"ins{k:02d}.png"); render_insert(o, p)
    t0, t1 = T(o["seg"], o["l0"]), T(o["seg"], o["l1"])
    items.append({"png": p, "t0": t0, "t1": t1, "fade": 0.12, "slide": 0})

inputs = ["-i", video]; fc = ["[0:v]scale=1080:1920:flags=lanczos:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1" + ("[m0]" if masks else "[b0]")]   # 768×1344 不是严格 9:16：铺满后居中裁切，不拉伸
# 抹除 H3 自带字幕：该区域外扩后强虚化，四周 28px 羽化，贴回原处（delogo 会留竖条纹，不用）
for k, m in enumerate(masks):
    x, y, w, h = m["box"]; F = 28
    X, Y = max(0, int(x * W) - F), max(0, int(y * H) - F); Wd, Hd = min(W - X, int(w * W) + 2 * F), min(H - Y, int(h * H) + 2 * F)
    Wd -= Wd % 2; Hd -= Hd % 2
    t0, t1 = T(m["seg"], m["l0"]), T(m["seg"], m["l1"]); nxt = f"[m{k + 1}]" if k < len(masks) - 1 else "[b0]"
    fc.append(f"[m{k}]split[mp{k}][mq{k}]")
    fc.append(f"[mq{k}]crop={Wd}:{Hd}:{X}:{Y},gblur=sigma=48:steps=3,eq=brightness=-0.10:contrast=0.85,format=rgba,"
              f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='255*min(1,min(min(X,W-1-X),min(Y,H-1-Y))/{F})'[mb{k}]")
    fc.append(f"[mp{k}][mb{k}]overlay={X}:{Y}:enable='between(t,{t0:.3f},{t1:.3f})'{nxt}")
# 聚焦拉动：带 "blur": true 的叠字出现时，背景轻虚焦 + 压暗（把画面里生成的乱码文字退成质感），淡入淡出 0.15 秒
blurs = [(T(o["seg"], o["l0"]), T(o["seg"], o["l1"])) for o in overlays if o.get("blur")]
for k, (b0_, b1_) in enumerate(blurs):
    s0 = max(0.0, b0_ - 0.2); s1 = b1_ + 0.2
    fc.append(f"[b{k}]split[bp{k}][bq{k}]")
    fc.append(f"[bq{k}]trim=start={s0:.3f}:end={s1:.3f},setpts=PTS-STARTPTS+{s0:.3f}/TB,gblur=sigma=14,eq=brightness=-0.14,format=rgba,"
              f"fade=t=in:st={b0_:.3f}:d=0.15:alpha=1,fade=t=out:st={b1_ - 0.15:.3f}:d=0.15:alpha=1[bl{k}]")
    fc.append(f"[bp{k}][bl{k}]overlay=eof_action=pass:repeatlast=0[b{k + 1}]")
base_idx = len(blurs)

for k, it in enumerate(items, start=1):
    dur = it["t1"] - it["t0"]
    inputs += ["-loop", "1", "-framerate", "24", "-t", f"{dur:.3f}", "-i", it["png"]]
    fc.append(f"[{k}:v]format=rgba,fade=t=in:st=0:d={it['fade']}:alpha=1,fade=t=out:st={dur - it['fade']:.3f}:d={it['fade']}:alpha=1,"
              f"setpts=PTS-STARTPTS+{it['t0']:.3f}/TB[o{k}]")
    x = "0" if not it["slide"] else f"'{it['slide']}*(1-min(1,(t-{it['t0']:.3f})/0.35))'"
    fc.append(f"[b{base_idx + k - 1}][o{k}]overlay=x={x}:y=0:eof_action=pass[b{base_idx + k}]")
out = os.path.splitext(video)[0] + "_subs.mp4"
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", f"[b{base_idx + len(items)}]", "-map", "0:a",
                "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "copy", out], check=True)
with open(os.path.splitext(video)[0] + "_subs.srt", "w", encoding="utf-8") as f:
    for k, s in enumerate(subs, 1):
        f.write(f"{k}\n{srt_time(s['start'])} --> {srt_time(s['end'])}\n{chr(10).join(wrap(s['text']))}\n\n")
print(f"→ {os.path.relpath(out, ep)}（字幕 {len(subs)} 条，铭牌 {len(titles)} 块，插入文字 {len(overlays)} 处，抹除 H3 自带字幕 {len(masks)} 处；交付标准 {PROF['name']}，安全区提示 {len(SAFE_WARN)} 条）")
for w in SAFE_WARN: print("  ⚠ " + w)
for s in subs: print(f"  {s['start']:6.2f}-{s['end']:6.2f}  {' / '.join(wrap(s['text']))}")
