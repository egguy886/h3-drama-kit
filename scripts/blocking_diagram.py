#!/usr/bin/env python3
"""站位线稿图生成器（多人静态戏锁站位用，免费）。灰色火柴人 + 头上字母 A/B/C，不用颜色绑定角色（彩色线稿 1/3 会把颜色漏进服装）。

用法：python3 tools/blocking_diagram.py plans/diagrams/E05S3.json        → assets/images/D-E05S3.png
规格 JSON：
{
  "id": "D-E05S3",                      # 资产 ID（也是输出文件名）
  "size": [720, 1280],                  # 9:16；横屏写 [1280, 720]
  "landmarks": [{"box": [30, 140, 250, 570], "grid": [2, 4]},          # 墙/窗：矩形，可加格子
                {"box": [540, 200, 690, 820], "lines": 8},              # 机柜/门：矩形 + 横线
                {"poly": [[30, 820], [470, 820], [500, 900], [30, 900]]}], # 桌子/车：多边形
  "figures":   [{"letter": "A", "x": 360, "y": 330, "pose": "stand", "scale": 1.0},
                {"letter": "B", "x": 285, "y": 790, "pose": "crouch"},
                {"letter": "C", "x": 600, "y": 920, "pose": "stand", "scale": 1.3},
                {"letter": "D", "x": 420, "y": 1000, "pose": "lie"}]
}
x, y 是头部中心（画面像素）；scale 大＝离镜头近。站在远处的人画小、画高。

然后在 library/props.json 登记（把线稿当一个"道具"放进该段 props，排在最后）：
  "D-E05S3": {"name_cn": "E05 Seg3 站位线稿", "en": "the staging diagram shown in {P}: a positions-only map seen from the camera's side, drawn in plain grey lines; each figure carries a letter",
              "keep": "reference - positions only; the diagram itself never appears in the video", "match": []}
并在镜头/站位卡里写："The figure marked A = {C01} Mia, standing …; the figure marked B = … The diagram defines positions only; it has no colors, and faces, wardrobe, light and materials come exclusively from the character and location references."
效果（RunningHub H3 Enhanced 实测）：开场站位与计划一致 6/6；约 1/6 概率线稿叠进成片第一秒要重抽；图里的人会提前出场，人物陆续进场的段不要用。
"""
import json, os, sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__)); PIPE = os.path.dirname(HERE)
spec = json.load(open(sys.argv[1], encoding="utf-8"))
W, H = spec.get("size", [720, 1280])
im = Image.new("RGB", (W, H), (255, 255, 255)); d = ImageDraw.Draw(im)
GRID, LINE, FIG = (232, 232, 232), (120, 120, 120), (70, 70, 70)
for x in range(0, W, 80):
    d.line([(x, 0), (x, H)], fill=GRID)
for y in range(0, H, 80):
    d.line([(0, y), (W, y)], fill=GRID)
for lm in spec.get("landmarks", []):
    if "box" in lm:
        x0, y0, x1, y1 = lm["box"]; d.rectangle([x0, y0, x1, y1], outline=LINE, width=2)
        if "grid" in lm:
            cx, cy = lm["grid"]
            for i in range(1, cx):
                d.line([(x0 + (x1 - x0) * i / cx, y0), (x0 + (x1 - x0) * i / cx, y1)], fill=LINE, width=2)
            for j in range(1, cy):
                d.line([(x0, y0 + (y1 - y0) * j / cy), (x1, y0 + (y1 - y0) * j / cy)], fill=LINE, width=2)
        for j in range(1, lm.get("lines", 0) + 1):
            yy = y0 + (y1 - y0) * j / (lm["lines"] + 1); d.line([(x0 + 10, yy), (x1 - 10, yy)], fill=LINE, width=1)
    if "poly" in lm:
        d.polygon([tuple(p) for p in lm["poly"]], outline=LINE, width=2)
def font_of(px):
    for f in ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, px)
        except Exception:
            pass
    return ImageFont.load_default()


def figure(f):
    s = f.get("scale", 1.0); x, y = f["x"], f["y"]; r = max(16, int(28 * s)); w = 4
    pose = f.get("pose", "stand")
    if pose == "lie":                                   # 横躺：头在左，身体向右
        d.line([(x + r, y), (x + int(260 * s), y)], fill=FIG, width=w)
        d.line([(x + int(260 * s), y), (x + int(330 * s), y - int(20 * s))], fill=FIG, width=w)
        d.line([(x + int(260 * s), y), (x + int(330 * s), y + int(20 * s))], fill=FIG, width=w)
        d.line([(x + int(80 * s), y), (x + int(150 * s), y - int(40 * s))], fill=FIG, width=w)
    elif pose == "crouch":
        d.line([(x, y + r), (x - int(30 * s), y + int(150 * s))], fill=FIG, width=w)
        d.line([(x - int(30 * s), y + int(150 * s)), (x + int(40 * s), y + int(200 * s))], fill=FIG, width=w)
        d.line([(x + int(40 * s), y + int(200 * s)), (x + int(20 * s), y + int(260 * s))], fill=FIG, width=w)
        d.line([(x - int(10 * s), y + int(70 * s)), (x + int(50 * s), y + int(130 * s))], fill=FIG, width=w)
    else:                                               # 站立：梯形躯干 + 两腿 + 一臂
        sh, hip = int(55 * s), int(40 * s)
        top, waist, foot = y + r + int(20 * s), y + int(260 * s), y + int(670 * s)
        d.polygon([(x - sh, top), (x + sh, top), (x + hip, waist), (x - hip, waist)], outline=FIG, width=w)
        d.line([(x - hip + 5, waist), (x - hip, foot)], fill=FIG, width=w)
        d.line([(x + hip - 5, waist), (x + hip, foot)], fill=FIG, width=w)
        d.line([(x - sh, top), (x - sh - int(15 * s), top + int(160 * s))], fill=FIG, width=w)
    d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255), outline=FIG, width=w)
    font = font_of(int(r * 1.3)); t = f["letter"]; tw = d.textlength(t, font=font)
    d.text((x - tw / 2, y - r * 0.85), t, fill=(30, 30, 30), font=font)


for f in spec.get("figures", []):
    figure(f)
out_dir = os.path.join(PIPE, json.load(open(os.path.join(PIPE, "project.json"), encoding="utf-8")).get("asset_root", "assets") if os.path.isfile(os.path.join(PIPE, "project.json")) else "assets", "images")
os.makedirs(out_dir, exist_ok=True)
out = os.path.join(out_dir, spec["id"] + ".png")
im.save(out)
print("→", os.path.relpath(out, PIPE))
