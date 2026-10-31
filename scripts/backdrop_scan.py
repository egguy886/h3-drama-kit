#!/usr/bin/env python3
"""扫采用片段里疑似"灰棚背景"：角色参考图的灰底串进成片，场景没出来（只读，不花钱）。
做法：每段抽 5 帧，看上半部分有多少 16×16 小块低饱和、几乎没纹理、亮度中等；超过 22% 算命中，≥2 帧命中就列出来。
只查灰底这一类，白墙等会误报，列出来的段要人看帧确认。阈值在《错撩》E07 Seg2 上校准过，换剧先用一段已知灰底的片子试。
用法（项目根目录）：python3 tools/backdrop_scan.py [E07 E42 …]
"""
import glob, io, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def frame(clip, t):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", clip, "-frames:v", "1", "-vf", "scale=184:328", "-f", "image2pipe", "-c:v", "png", "-"], capture_output=True)
    return Image.open(io.BytesIO(r.stdout)).convert("RGB") if r.stdout else None


def check(clip):
    fracs = []
    for t in (1, 4, 7, 10, 13):
        im = frame(clip, t)
        if im is None: continue
        a = np.asarray(im).astype(float)
        blocks = [a[y:y + 16, x:x + 16] for y in range(0, 160, 16) for x in range(0, 176, 16)]
        flat = [b for b in blocks if (b.max(2) - b.min(2)).mean() < 12 and b.mean(2).std() < 4 and 50 < b.mean() < 175]
        fracs.append(round(len(flat) / len(blocks), 2))
    return clip, fracs


def main():
    os.chdir(PIPE)
    eps = sys.argv[1:] or ["E??"]
    clips = sorted(c for e in eps for c in glob.glob(f"episodes/{e}/07_clips/seg??_accepted.mp4"))
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(check, clips))
    hits = [(c, f) for c, f in res if sum(x > 0.22 for x in f) >= 2]
    print(f"共 {len(clips)} 段，疑似灰底 {len(hits)} 段")
    for c, f in hits:
        print(c.split("/")[1], os.path.basename(c)[:5], f)


if __name__ == "__main__":
    main()
