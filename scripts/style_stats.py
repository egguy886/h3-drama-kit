#!/usr/bin/env python3
"""全剧色调基准：量片子的亮度、饱和度、暖度、黑位，和基准（E01 定稿）比，偏太多就报警。只读、免费。
用法：python3 tools/style_stats.py make <视频> [--out review/style_baseline/e01_stats.json]    # 建基准（每 15 秒一段）
      python3 tools/style_stats.py check <视频> [--seg-sec 15]                              # 逐段对比基准
指标（0–1）：luma 平均亮度；sat 平均饱和度；warm 平均 红/(红+蓝)；black 第 5 百分位亮度（黑位）。
局限（实测）：E01 是夜戏，基准偏暗偏暖；旧 720p 版和新风格版的这四个数几乎一样，所以它分不出“风格对不对”，只能抓离群：
饱和度掉了（灰蒙蒙）、黑位被抬起或压死。亮度和暖度只做参考（白天戏、冷色办公室本来就该不同），不报警。"""
import json, os, subprocess, sys
import numpy as np
PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(PIPE, 'review', 'style_baseline', 'e01_stats.json')
TOL = {'luma': 0.08, 'sat': 0.10, 'warm': 0.06, 'black': 0.05}
GUARD = ('sat', 'black')     # 只有这两项超容差才报警
W, H = 72, 128

def frames(path):
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-vf', f'fps=2,scale={W}:{H}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True)
    a = np.frombuffer(r.stdout, np.uint8); n = len(a) // (W * H * 3)
    return a[:n * W * H * 3].reshape(n, H, W, 3).astype(np.float32) / 255

def stat(fr):
    r, g, b = fr[..., 0], fr[..., 1], fr[..., 2]
    mx, mn = fr.max(-1), fr.min(-1); y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return {'luma': float(y.mean()), 'sat': float(((mx - mn) / np.maximum(mx, 1e-3)).mean()),
            'warm': float((r / np.maximum(r + b, 1e-3)).mean()), 'black': float(np.percentile(y, 5))}

def per_seg(path, sec):
    fr = frames(path); k = int(sec * 2)
    return [stat(fr[i:i + k]) for i in range(0, len(fr), k) if len(fr[i:i + k]) >= k // 2], stat(fr)

if __name__ == '__main__':
    cmd, path = sys.argv[1], sys.argv[2]
    sec = float(sys.argv[sys.argv.index('--seg-sec') + 1]) if '--seg-sec' in sys.argv else 15
    segs, whole = per_seg(path, sec)
    if cmd == 'make':
        out = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else BASE
        json.dump({'source': os.path.relpath(path, PIPE), 'seg_sec': sec, 'tolerance': TOL, 'whole': whole, 'segments': segs}, open(out, 'w'), indent=1)
        print('基准已写', out, {k: round(v, 3) for k, v in whole.items()})
    else:
        base = json.load(open(BASE))['whole']; bad = 0
        for k, v in whole.items():
            d = v - base[k]; flag = ('⚠' if abs(d) > TOL[k] else '✓') if k in GUARD else 'ℹ'; bad += flag == '⚠'
            print(f'{flag} {k:5s} 本集 {v:.3f}  基准 {base[k]:.3f}  差 {d:+.3f}（容差 ±{TOL[k]}）')
        for i, s in enumerate(segs, 1):
            print(f'  段{i:2d} ' + '  '.join(f'{k} {v:.2f}' for k, v in s.items()))
        sys.exit(1 if bad else 0)
