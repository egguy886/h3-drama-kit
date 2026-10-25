#!/usr/bin/env python3
"""每集一张总览联系表：8 段 × 每个镜头中点一帧（竖向排列），左侧标段号与质检数据，带 ⚠ 的段标橙色。
用法：python3 tools/episode_sheet.py E01-E10      输出 review/sheets/Exx_总览.jpg
"""
import json, os, re, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont

PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(PIPE, "review", "sheets"); os.makedirs(OUT, exist_ok=True)
FONT = ImageFont.truetype("/System/Library/Fonts/STHeiti Medium.ttc", 17)
FS = ImageFont.truetype("/System/Library/Fonts/STHeiti Medium.ttc", 13)
TW, TH, MAXC = 100, 178, 10


def eps(spec):
    out = []
    for p in spec:
        m = re.fullmatch(r"E(\d+)-E?(\d+)", p.upper())
        out += [f"E{i:02d}" for i in range(int(m.group(1)), int(m.group(2)) + 1)] if m else [p.upper()]
    return out


def grab(clip, t, path):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", clip, "-frames:v", "1", "-vf", f"scale={TW}:{TH}", path], check=False)
    return Image.open(path).convert("RGB") if os.path.isfile(path) else Image.new("RGB", (TW, TH), (60, 0, 0))


for ep in eps(sys.argv[1:] or ["E01-E10"]):
    d = os.path.join(PIPE, "episodes", ep)
    plan = json.load(open(os.path.join(d, "plan.json"), encoding="utf-8"))
    sp = os.path.join(d, "06_jobs", "batch_state.json")
    st = json.load(open(sp, encoding="utf-8"))["segs"] if os.path.isfile(sp) else {}
    LW = 150
    W = LW + MAXC * (TW + 2); H = 40 + len(plan["segments"]) * (TH + 4)
    im = Image.new("RGB", (W, H), (18, 18, 18)); dr = ImageDraw.Draw(im)
    dr.text((8, 8), f"{ep}  {plan.get('title', '')}   （每格 = 该镜头中点一帧；橙色 = 需优先看）", font=FONT, fill=(255, 255, 255))
    tmp = tempfile.mkdtemp()
    for r, s in enumerate(plan["segments"]):
        y = 40 + r * (TH + 4)
        rec = st.get(str(s["id"]), {}); flag = rec.get("flag")
        clip = os.path.join(d, "07_clips", f"seg{s['id']:02d}_accepted.mp4")
        col = (255, 160, 40) if flag else (120, 220, 120)
        dr.text((8, y + 2), f"Seg{s['id']}", font=FONT, fill=col)
        dr.text((8, y + 24), s["scene"][:9], font=FS, fill=(200, 200, 200))
        dr.text((8, y + 42), f"链 {s['chain']} → {'接力' if s['connection_to_next'] == 'TAIL_RELAY' else ('硬切' if s['connection_to_next'] == 'HARD_CUT' else '集尾')}", font=FS, fill=(160, 160, 160))
        if rec.get("tries"): dr.text((8, y + 60), f"出片 {rec['tries']} 次", font=FS, fill=(160, 160, 160))
        if rec.get("last_score") is not None: dr.text((8, y + 78), f"自动分 {rec['last_score']}", font=FS, fill=(160, 160, 160))
        if flag:
            for k, ln in enumerate([flag[i:i + 9] for i in range(0, min(len(flag), 36), 9)]):
                dr.text((8, y + 98 + k * 15), ln, font=FS, fill=(255, 160, 40))
        if not os.path.isfile(clip):
            dr.text((LW + 10, y + 70), "（暂无保留片）", font=FONT, fill=(150, 80, 80)); continue
        t = 0.0
        for c, sh in enumerate(s["shots"][:MAXC]):
            mid = t + sh["dur"] / 2; t += sh["dur"]
            f = grab(clip, min(mid, 14.8), os.path.join(tmp, f"{s['id']}_{c}.png"))
            im.paste(f, (LW + c * (TW + 2), y))
            dr.rectangle([LW + c * (TW + 2), y, LW + c * (TW + 2) + 34, y + 14], fill=(0, 0, 0))
            dr.text((LW + c * (TW + 2) + 2, y), f"{c + 1}", font=FS, fill=(255, 255, 0))
    p = os.path.join(OUT, f"{ep}_总览.jpg"); im.save(p, quality=86); print(ep, "→", p, flush=True)
