#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TikTok Drama Center "黑边" 检查与修复。

平台提示：`黑边：不能有边缘连续黑像素>20px 且连续出现>5秒`。AI 短剧的电影感暗调镜头（夜景、暗角、压黑）
即使没有真正的黑条，边缘也会被压成近纯黑而被判黑边。修法：把暗部整体抬高一点（黑位 → TV 范围 ~36），
片尾切黑/To Be Continued 卡之前淡出抬亮，片尾保持纯黑。

  python3 tools/tiktok_edge.py check  <视频或 episodes 目录里的 Exx> [...]   # 量边缘近黑持续时间（代理指标，不等于平台判定）
  python3 tools/tiktok_edge.py fix    <输入.mp4> [-o 输出.mp4] [--floor 36] [--tail 4.5]
  python3 tools/tiktok_edge.py fix-all <成片目录> -o <输出目录> [--pattern "*/08_edit/*_final.mp4"] [-j 4]

原片不会被覆盖。需要 ffmpeg/ffprobe + numpy。
"""
import argparse, glob, json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

W, H, FPS = 270, 480, 2        # 检测用小图：1080 宽的 20px = 5px
SC = 1080 / W
THR, FRAC = 20, 0.9            # 灰度阈值（0–255）、该行/列近黑像素占比


def _run(a):
    n = 0
    for v in a:
        if v:
            n += 1
        else:
            break
    return n


def measure(path):
    """返回 (最长连续秒数 [任一边缘近黑 >20px], 起点秒, 片长秒)。整屏全黑帧也计入。"""
    import numpy as np
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', path, '-vf', f'fps={FPS},scale={W}:{H},format=gray',
                          '-f', 'rawvideo', '-'], stdout=subprocess.PIPE)
    best = cur = start = bs = 0
    i = 0
    while True:
        b = p.stdout.read(W * H)
        if len(b) < W * H:
            break
        g = np.frombuffer(b, dtype=np.uint8).reshape(H, W)
        bl = g < THR
        rb = bl.mean(axis=1) >= FRAC
        cb = bl.mean(axis=0) >= FRAC
        m = max(_run(rb), _run(rb[::-1]), _run(cb), _run(cb[::-1])) * SC
        if m > 20:
            if cur == 0:
                start = i
            cur += 1
            if cur > best:
                best, bs = cur, start
        else:
            cur = 0
        i += 1
    p.wait()
    return best / FPS, bs / FPS, i / FPS


def duration(path):
    out = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path])
    return float(out.decode().strip())


def black_start(path, win=12.0):
    """片尾"切黑"的起点秒（最后一段连续整屏近黑的开始）；找不到返回 None。"""
    import numpy as np
    d = duration(path)
    st = max(0.0, d - win)
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-ss', f'{st:.2f}', '-i', path, '-vf', 'fps=10,scale=108:192,format=gray',
                          '-f', 'rawvideo', '-'], stdout=subprocess.PIPE)
    means = []
    while True:
        b = p.stdout.read(108 * 192)
        if len(b) < 108 * 192:
            break
        means.append(float(np.frombuffer(b, dtype=np.uint8).mean()))
    p.wait()
    i = len(means)
    while i > 0 and means[i - 1] < 8:      # 近黑（含 TO BE CONTINUED 卡：黑底小字）
        i -= 1
    return None if i == len(means) else st + i / 10.0


def fix(src, dst, floor=36, tail=4.5, crf=17):
    """抬黑位：Y' = floor + (Y-16)*(235-floor)/219；到片尾切黑前 0.4 秒淡出，片尾黑场/To Be Continued 保持原样。
    找不到切黑点时退回"片尾前 tail 秒"。"""
    d = duration(src)
    sc = (235 - floor) / 219
    bs = black_start(src)
    st = max(0.0, (bs - 0.4) if bs else d - tail)
    fc = (f"[0:v]split[o][a];"
          f"[a]lutyuv=y='clip((val-16)*{sc:.5f}+{floor},16,235)',format=yuva420p,fade=t=out:st={st:.2f}:d=0.4:alpha=1[l];"
          f"[o][l]overlay=format=auto,format=yuv420p[v]")
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    cmd = ['ffmpeg', '-v', 'error', '-y', '-i', src, '-filter_complex', fc, '-map', '[v]', '-map', '0:a?',
           '-c:v', 'libx264', '-crf', str(crf), '-preset', 'medium', '-profile:v', 'high',
           '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
           '-c:a', 'copy', '-movflags', '+faststart', dst]
    subprocess.check_call(cmd)
    return dst


def resolve(arg):
    if os.path.isfile(arg):
        return arg
    hits = glob.glob(f'episodes/{arg}/08_edit/{arg}_v1_768p_final.mp4')
    if not hits:
        sys.exit(f'找不到 {arg}')
    return hits[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('check'); c.add_argument('videos', nargs='+')
    f = sub.add_parser('fix'); f.add_argument('video'); f.add_argument('-o'); f.add_argument('--floor', type=int, default=36)
    f.add_argument('--tail', type=float, default=4.5)
    fa = sub.add_parser('fix-all'); fa.add_argument('root'); fa.add_argument('-o', required=True)
    fa.add_argument('--pattern', default='*/08_edit/*_final.mp4'); fa.add_argument('--floor', type=int, default=36)
    fa.add_argument('--tail', type=float, default=4.5); fa.add_argument('-j', type=int, default=4)
    a = ap.parse_args()

    if a.cmd == 'check':
        for v in a.videos:
            p = resolve(v)
            s, at, d = measure(p)
            flag = '⚠ 可能被判黑边' if s >= 4.0 else 'ok'
            print(f'{os.path.basename(p):40s} 边缘近黑最长 {s:4.1f}s（起于 {at:5.1f}s / 全长 {d:.0f}s） {flag}')
    elif a.cmd == 'fix':
        src = resolve(a.video)
        dst = a.o or os.path.splitext(src)[0] + f'_edgefix{a.floor}.mp4'
        print('→', fix(src, dst, a.floor, a.tail))
    else:
        files = sorted(glob.glob(os.path.join(a.root, a.pattern)))
        if not files:
            sys.exit('没找到成片')

        def job(p):
            ep = os.path.basename(p).split('_')[0]
            dst = os.path.join(a.o, os.path.basename(p).replace('.mp4', '_tt.mp4'))
            if os.path.exists(dst):
                return ep, 'skip'
            fix(p, dst, a.floor, a.tail)
            return ep, 'ok'
        with ThreadPoolExecutor(max_workers=a.j) as ex:
            for ep, st in ex.map(job, files):
                print(ep, st, flush=True)


if __name__ == '__main__':
    main()
