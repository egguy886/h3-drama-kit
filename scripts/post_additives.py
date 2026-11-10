#!/usr/bin/env python3
"""后期声音“添加剂”：在拼好的成片上，对指定的高潮点加三样（只改声音，画面原样拷贝）。

  1) 谢帕德–里塞上升音（--rise 段）：8 个八度叠加，持续上升（每 7 秒升一个八度），音量缓慢爬升；
  2) 骤停留白（0.5 秒全静音，紧贴在落地点前）；
  3) 重低音落地（手机版：能量在 110–440 Hz + 轻度饱和，手机喇叭也听得到；--no-phone 才是纯 55 Hz）；
  4) 冻结段压低（落地后 --duck 秒，原音压低 14 dB，最后 0.4 秒淡回）；落地后 1 秒原片动作声 +5 dB。

用法（时间都是成片里的秒）：
  python3 tools/post_additives.py IN.mp4 OUT.mp4 --beat 92.0:106.2:106.7:8.0
    beat = 上升开始:上升结束:落地:冻结时长 ；可重复多个 --beat
  --shepard-db -14   谢帕德音量相对基准（基准最响约 −20 dBFS；用户听感定稿：−14，即最响约 −34 dBFS）
  --no-phone         重低音只用 55 Hz 基音（手机上几乎听不见，只适合耳机/电视）
  --report           打印每个落地点 0.6 秒的响度：全频 / 手机外放模拟（200 Hz 高通×2）

规则（《Tangled》2026-11-10 试验，用户听感定稿）：
  · 一集最多 1–2 个落地点，只放在剧情真正的“砸下来”的一刻（受伤、反转、揭牌），不要每场都用；
  · 落地点必须对准画面里的动作瞬间（看一遍成片、记下秒数），上升段从该场戏开头起；
  · 手机观众占大头：默认手机版；谢帕德音只做“垫底的紧张”，−14 dB 起步，别盖过环境底和对白；
  · 上升段里如果有对白，谢帕德音在对白处不要再响（用 --shepard-db 再降，或把 rise 起点后移到对白之后）。
"""
import argparse, os, subprocess, sys
import numpy as np

SR = 48000


def probe_channels(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=channels", "-of", "csv=p=0", p], capture_output=True, text=True)
    return max(1, int(r.stdout.strip() or 1))


def read_audio(p, ch):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-vn", "-f", "f32le", "-ac", str(ch), "-ar", str(SR), "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.float32).reshape(-1, ch).copy()


def shepard(n_t, rise_s, db):
    L = n_t[-1] - n_t[0] + 1 / SR
    tt = n_t - n_t[0]; out = np.zeros(len(tt), np.float32); rate = 1.0 / 7.0
    for k in range(8):
        pos = (k + tt * rate) % 8; f0 = 55 * 2 ** pos
        out += np.exp(-0.5 * ((pos - 4) / 1.3) ** 2) * np.sin(2 * np.pi * np.cumsum(f0) / SR)
    out /= np.abs(out).max()
    return out * 0.10 * 10 ** (db / 20) * (tt / L) ** 1.5


def boom(t_len, phone):
    tt = np.arange(int(2.2 * SR)) / SR
    ph = 2 * np.pi * np.cumsum(55 * (1 + 0.6 * np.exp(-tt * 12))) / SR; env = np.exp(-tt * 2.2)
    H = [1, .8, .7, .6, .45, .3, .2, .12] if phone else [1, .45, .25]
    b = env * sum(h * np.sin((i + 1) * ph) for i, h in enumerate(H))
    if phone: b = np.tanh(b * 1.6)
    click = np.exp(-tt * 180) * np.random.default_rng(1).standard_normal(len(tt)) * 0.5
    return 0.55 * b / np.abs(b).max() + click * 0.25


def apply_beat(a, beat, db, phone):
    r0, r1, hit, duck = beat
    n = a.shape[0]; t = np.arange(n) / SR; src = a.copy()
    m = (t >= r0) & (t < r1)
    if m.any(): a[m] += shepard(t[m], (r0, r1), db)[:, None]
    a[(t >= hit - 0.5) & (t < hit)] = 0                                   # 0.5 秒真空
    g = np.ones(n, np.float32); d = (t >= hit) & (t < hit + duck); g[d] = 0.2
    f = (t >= hit + duck - 0.4) & (t < hit + duck); g[f] = np.linspace(0.2, 1, f.sum())
    a *= g[:, None]
    i0 = int(hit * SR); b = boom(0, phone); k = min(len(b), n - i0)
    if k > 0: a[i0:i0 + k] += b[:k, None]
    hm = (t >= hit) & (t < hit + 1.0); a[hm] += src[hm] * (1.78 - 0.2)    # 落地后 1 秒动作声 +5 dB
    return a


def loud(x, t0, t1, hp=False):
    s = x[int(t0 * SR):int(t1 * SR)].mean(axis=1)
    if hp:                                                                  # 简易 200 Hz 高通×2（FFT）
        F = np.fft.rfft(s); f = np.fft.rfftfreq(len(s), 1 / SR); F *= (1 / (1 + (200 / np.maximum(f, 1)) ** 4)); s = np.fft.irfft(F, len(s))
    return 20 * np.log10(np.sqrt((s ** 2).mean()) + 1e-9)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inp"); ap.add_argument("out")
    ap.add_argument("--beat", action="append", required=True, help="上升开始:上升结束:落地:冻结时长（秒）")
    ap.add_argument("--shepard-db", type=float, default=-14.0); ap.add_argument("--no-phone", action="store_true"); ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    ch = probe_channels(a.inp); x = read_audio(a.inp, ch); phone = not a.no_phone
    for b in a.beat:
        r0, r1, hit, duck = [float(v) for v in b.split(":")]
        assert r0 < r1 <= hit - 0.5 + 1e-6 and duck >= 1.0, f"beat {b}：要求 上升开始 < 上升结束 ≤ 落地−0.5，冻结 ≥ 1 秒"
        x = apply_beat(x, (r0, r1, hit, duck), a.shepard_db, phone)
        if a.report: print(f"落地 {hit:.1f}s：全频 {loud(x, hit, hit + .6):.1f} dBFS，手机外放模拟 {loud(x, hit, hit + .6, True):.1f} dBFS")
    x = np.clip(x, -0.99, 0.99)
    tmp = a.out + ".tmp.f32"; x.astype(np.float32).tofile(tmp)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", a.inp, "-f", "f32le", "-ar", str(SR), "-ac", str(ch), "-i", tmp, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", a.out], check=True)
    os.remove(tmp); print("写入", a.out)


if __name__ == "__main__":
    main()
