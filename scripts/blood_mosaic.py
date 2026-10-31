#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
血腥画面局部马赛克（不重新出片）。

TikTok 对"逼真血腥/血液特写"会判"分发受限"。本工具在你指定的时间段里，自动找出画面中的血迹颜色区域
（红色、饱和、偏暗），只对这些区域打马赛克；其余画面、音频原样保留。

  python3 tools/blood_mosaic.py preview <成片.mp4> --plan plan.json [--out-dir 预览目录]   # 抽帧看效果（不转码）
  python3 tools/blood_mosaic.py apply   <成片.mp4> --plan plan.json -o <输出.mp4>

plan.json：
{
  "block": 30,                 # 马赛克块大小（像素，按 1080 宽）
  "dilate": 36,                # 把血迹区域向外扩多少像素再打码
  "desat": 0.85, "dark": 0.25, # 马赛克区域去色/压暗比例（血不再是红色）
  "snap": 0.5,                 # 窗口起止点吸附到 ±0.5 秒内最近的真实切镜点（0=关闭）
  "windows": [
    {"a": 74.6, "b": 76.6,     # 起止秒（成片时间）
     "smin": 0.40, "vmin": 0.10, "vmax": 0.85,   # 可选：饱和度/明度阈值
     "min_frac": 0.004,        # 可选：血迹占画面比例低于它就不打码（避免误伤）
     "roi": [0.0, 0.2, 1.0, 0.9],   # 可选：只在画面这块区域找（x0,y0,x1,y1，0–1）
     "boxes": [[0,0.2,0.5,0.7],[0.5,0.5,1,0.9]],   # 可选：多个框（优先于 roi）
     "dilate": 50, "block": 30,    # 可选：覆盖全局设置
     "mode": "auto"}           # auto=按颜色（限定在框内）；box=整个框都打码
  ]
}
依赖：ffmpeg/ffprobe、numpy、Pillow。输出 1080x1920 H.264 CRF17、音频直拷。
"""
import argparse, json, os, subprocess, sys
import numpy as np


def probe(path):
    o = subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                                 'stream=width,height,r_frame_rate', '-of', 'json', path])
    s = json.loads(o)['streams'][0]
    n, d = s['r_frame_rate'].split('/')
    return int(s['width']), int(s['height']), float(n) / float(d)


def box_sum(a, r):
    """a: 2D 数组；返回每个像素 (2r+1)^2 邻域内的和（积分图）。"""
    k = 2 * r + 1
    p = np.pad(a.astype(np.int32), ((r + 1, r), (r + 1, r)), mode='constant')
    c = p.cumsum(0).cumsum(1)
    return c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]


def dilate(m, r):
    return box_sum(m, r) > 0 if r > 0 else m


def erode(m, r):
    k = (2 * r + 1) ** 2
    return box_sum(m, r) >= k if r > 0 else m


def blood_mask(rgb, w):
    """rgb: HxWx3 uint8（已降采样）；w: window 参数。返回 bool 掩码。"""
    f = rgb.astype(np.float32) / 255.0
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    mx = f.max(-1)
    mn = f.min(-1)
    d = mx - mn + 1e-6
    s = d / (mx + 1e-6)
    red = (r >= g) & (r >= b) & ((b - g) / d <= 0.33) & ((g - b) / d <= 0.23)
    return red & (s > w.get('smin', 0.40)) & (mx > w.get('vmin', 0.10)) & (mx < w.get('vmax', 0.85))


def process_frame(frame, w, cfg):
    H, W, _ = frame.shape
    ds = 2
    small = frame[::ds, ::ds]
    h, ww = small.shape[:2]
    boxes = w.get('boxes') or [w.get('roi', [0, 0, 1, 1])]
    roi = np.zeros((h, ww), bool)
    for x0, y0, x1, y1 in boxes:
        roi[int(y0 * h):int(y1 * h), int(x0 * ww):int(x1 * ww)] = True
    if w.get('mode', 'auto') == 'box':
        m = roi
    else:
        m = blood_mask(small, w) & roi
        m = dilate(erode(m, 1), 1)                      # 去掉零星噪点
        if m.mean() < w.get('min_frac', 0.004):
            return frame, 0.0
        m = dilate(m, max(1, int(w.get('dilate', cfg.get('dilate', 36)) / ds)))   # 外扩
        m &= dilate(roi, 0)                            # 不超出 roi
    frac = float(m.mean())
    full = np.repeat(np.repeat(m, ds, 0), ds, 1)[:H, :W]
    b = int(w.get('block', cfg.get('block', 30)))
    hb, wb = H // b, W // b
    crop = frame[:hb * b, :wb * b].reshape(hb, b, wb, b, 3).mean((1, 3))
    mosaic = np.repeat(np.repeat(crop, b, 0), b, 1).astype(np.uint8)
    ds_ = float(w.get('desat', cfg.get('desat', 0.85)))
    dk_ = float(w.get('dark', cfg.get('dark', 0.25)))
    if ds_ > 0 or dk_ > 0:
        gray = mosaic.astype(np.float32).mean(-1, keepdims=True)
        mosaic = ((mosaic.astype(np.float32) * (1 - ds_) + gray * ds_) * (1 - dk_)).astype(np.uint8)
    out = frame.copy()
    mm = full[:hb * b, :wb * b]
    sel = out[:hb * b, :wb * b]
    sel[mm] = mosaic[mm]
    return out, frac


def detect_cuts(path, thr=0.35):
    """返回镜头切换时间点（秒）。"""
    p = subprocess.run(['ffmpeg', '-v', 'info', '-i', path, '-vf', f"scale=270:480,select='gt(scene,{thr})',showinfo",
                        '-an', '-f', 'null', '-'], capture_output=True, text=True)
    cuts = []
    for ln in p.stderr.splitlines():
        if 'pts_time:' in ln:
            try:
                cuts.append(float(ln.split('pts_time:')[1].split()[0]))
            except ValueError:
                pass
    return cuts


def snap_windows(plan, src):
    tol = float(plan.get('snap', 0))
    if tol <= 0:
        return plan
    cuts = detect_cuts(src)
    def near(t):
        c = [x for x in cuts if abs(x - t) <= tol]
        return min(c, key=lambda x: abs(x - t)) if c else t
    for w in plan['windows']:
        if w.get('snap', True):
            w['a'], w['b'] = near(w['a']), near(w['b'])
    return plan


def which_window(t, wins):
    for w in wins:
        if w['a'] <= t < w['b']:
            return w
    return None


def run(src, plan, dst):
    W, H, fps = probe(src)
    cfg = snap_windows(plan, src)
    wins = plan['windows']
    rd = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', src, '-vf',
                           'scale=in_color_matrix=bt709:in_range=tv:out_range=full,format=rgb24',
                           '-f', 'rawvideo', '-'], stdout=subprocess.PIPE, bufsize=W * H * 3 * 2)
    wr = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
                           '-r', f'{fps}', '-i', '-', '-i', src, '-map', '0:v', '-map', '1:a?',
                           '-vf', 'scale=out_color_matrix=bt709:out_range=tv,format=yuv420p',
                           '-c:v', 'libx264', '-crf', '17', '-preset', 'medium', '-profile:v', 'high',
                           '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
                           '-c:a', 'copy', '-movflags', '+faststart', '-shortest', dst], stdin=subprocess.PIPE)
    n = hit = 0
    size = W * H * 3
    while True:
        buf = rd.stdout.read(size)
        if len(buf) < size:
            break
        t = n / fps
        w = which_window(t, wins)
        if w is not None:
            frame = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
            out, frac = process_frame(frame, w, cfg)
            if frac > 0:
                hit += 1
            wr.stdin.write(out.tobytes())
        else:
            wr.stdin.write(buf)
        n += 1
    wr.stdin.close()
    rd.wait()
    wr.wait()
    return n, hit


def preview(src, plan, out_dir, step=0.5):
    from PIL import Image, ImageDraw
    W, H, fps = probe(src)
    os.makedirs(out_dir, exist_ok=True)
    plan = snap_windows(plan, src)
    wins = plan['windows']
    for w in wins:
        print(f"  窗口 {w['a']:.2f}–{w['b']:.2f}s")
    tiles = []
    for wi, w in enumerate(wins):
        t = w['a'] + step / 2
        while t < w['b']:
            raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-ss', f'{t:.3f}', '-i', src, '-frames:v', '1',
                                           '-vf', 'scale=in_color_matrix=bt709:in_range=tv:out_range=full,format=rgb24',
                                           '-f', 'rawvideo', '-'])
            fr = np.frombuffer(raw, np.uint8).reshape(H, W, 3)
            out, frac = process_frame(fr, w, plan)
            a = Image.fromarray(fr).resize((216, 384))
            b = Image.fromarray(out).resize((216, 384))
            tiles.append((a, b, f'{t:.1f}s win{wi + 1} {frac * 100:.1f}%'))
            t += step
    cols = 4
    rows = (len(tiles) + cols - 1) // cols
    sheets = []
    per = 12  # 每张预览图最多 12 对（4 列 x 3 行，每对左原图右效果）
    for s in range(0, len(tiles), per):
        chunk = tiles[s:s + per]
        r = (len(chunk) + cols - 1) // cols
        sh = Image.new('RGB', (cols * 440, r * 404), (80, 80, 80))
        d = ImageDraw.Draw(sh)
        for i, (a, b, lab) in enumerate(chunk):
            x, y = (i % cols) * 440, (i // cols) * 404
            sh.paste(a, (x, y + 16)); sh.paste(b, (x + 220, y + 16)); d.text((x + 3, y + 2), lab, fill=(255, 255, 255))
        p = os.path.join(out_dir, f'preview_{s // per + 1}.png')
        sh.save(p); sheets.append(p)
    return sheets


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=['preview', 'apply'])
    ap.add_argument('video')
    ap.add_argument('--plan', required=True)
    ap.add_argument('-o')
    ap.add_argument('--out-dir', default='blood_preview')
    ap.add_argument('--step', type=float, default=0.5)
    a = ap.parse_args()
    plan = json.load(open(a.plan, encoding='utf-8'))
    if a.cmd == 'preview':
        for p in preview(a.video, plan, a.out_dir, a.step):
            print(p)
    else:
        if not a.o:
            sys.exit('apply 需要 -o 输出文件')
        n, hit = run(a.video, plan, a.o)
        print(f'完成：{n} 帧，其中 {hit} 帧打了马赛克 → {a.o}')


if __name__ == '__main__':
    main()
