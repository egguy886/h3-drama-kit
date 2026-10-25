#!/usr/bin/env python3
"""片尾 v5「复刻」：一比一复刻用户提供的范例视频（约 3.7 秒片段）的结尾。

范例逐帧测量（review/ref/1012_1_结尾逐帧.jpg）：
① 胶片烧光 0.53 秒：画面被金白光从上往下烧穿（上半屏先亮先暗），中段带紫/橙光斑，纯白约 0.17 秒；闪光盖住一个切镜，切进最后一个镜头。
② 余光 ~1.2 秒：最后一个镜头整体略提亮，左侧漏光呼吸两下，颜色由暖白转青。
③ 定格 1.9 秒：硬切到干净（无光效）的静止画面，声音淡出到静音。
④ 黑屏一闪：画面一糊一暗进黑（3 帧）→ 黑底 TO BE CONTINUED。
声音：闪光处一下明亮的「沙—」（高频为主），原声同时压低；没有低频撞击。

用法同 bumper_episode.py（bumpers.json 的 tail_style = "replica" 时由它自动转调）：
python3 tools/ending_replica.py E01 --video 08_edit/E01_v1_768p_subs.mp4 --report 08_edit/E01_v1_768p.json --out 08_edit/E01_v5_replica.mp4
"""
import argparse, json, os, re, shutil, subprocess, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__)); PIPE = os.path.dirname(HERE)
W, H, FPS = 1080, 1920, 24
SUP = "/System/Library/Fonts/Supplemental/"

# ① 闪光强度曲线（滤色强度 s：输出 = 1-(1-画面)(1-s)），由范例整屏亮度换算：s = (亮度-50)/205
FLASH = ([0, .033, .10, .133, .167, .30, .333, .367, .433, .467, .50, .533],
         [0, .54, .75, .96, 1.0, 1.0, .98, .88, .75, .32, .12, .06])
FLASH_D = 0.533
CUT_AT = 0.23                     # 切镜放在纯白平台中间
# ② 左侧漏光强度（相对闪光结束），由范例左三分之一亮度变化换算；之后按同样节奏循环
LEAK = ([0, .17, .33, .47, .53, .60, .80, .93, 1.0, 1.1, 1.2, 1.23, 1.4, 1.6, 1.8, 2.0],
        [.10, .12, .22, .40, .42, .36, .12, .10, .16, .30, .40, .42, .30, .14, .22, .36])
LIVE_MAX, LIVE_GOAL = 2.0, 1.25
HOLD = 1.9                        # ③ 定格
DIP = [(4, .82), (10, .58), (18, .32), (28, .10)]   # ④ 黑屏一闪：每帧（模糊半径, 亮度），范例 18.70 秒一糊一暗


def ease(x): x = max(0.0, min(1.0, x)); return x * x * (3 - 2 * x)
def snap(t): return round(t * FPS) / FPS


ap = argparse.ArgumentParser()
ap.add_argument("episode"); ap.add_argument("--video", required=True); ap.add_argument("--report", required=True)
ap.add_argument("--out"); ap.add_argument("--no-title", action="store_true")
ap.add_argument("--style"); ap.add_argument("--flash-mode")          # 与 bumper_episode.py 参数兼容，这里不用
a = ap.parse_args()
ep = os.path.join(PIPE, "episodes", a.episode)
video = os.path.join(ep, a.video); rep = json.load(open(os.path.join(ep, a.report), encoding="utf-8"))
cfg = {}
cp = os.path.join(ep, "bumpers.json")
if os.path.isfile(cp): cfg = json.load(open(cp, encoding="utf-8"))
T = float(rep["video_end"]); TL = T - 0.06          # 源片在 T 之前就已硬切黑
DUR = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                           capture_output=True, text=True).stdout)


def busy_end():
    """最后一次需要观众听/看清的时刻：最后一句台词、最后一条叠字、最后一条后期配音。"""
    seg = {s["id"]: s for s in rep["segments"]}
    tl = lambda sg, l: seg[sg]["t0"] + (l - seg[sg]["in"])
    ends = []
    wp = os.path.splitext(os.path.join(ep, a.report))[0] + "_words.json"
    if os.path.isfile(wp):
        ends += [w["end"] for sg in json.load(open(wp, encoding="utf-8"))["segments"] for w in sg.get("words", [])]
    op = os.path.join(ep, "overlays.json")
    if os.path.isfile(op):
        ends += [tl(o["seg"], o["l1"]) for o in json.load(open(op, encoding="utf-8"))["items"] if o["seg"] in seg]
    for l in json.load(open(os.path.join(PIPE, "post_audio.json"), encoding="utf-8"))["lines"]:
        pl = l.get("place")
        if l["episode"] != a.episode or not pl or pl["seg"] not in seg: continue
        wv = os.path.join(ep, "08_edit", "post_audio", l["id"] + ".wav")
        if os.path.isfile(wv):
            with wave.open(wv) as w: d = w.getnframes() / w.getframerate()
            ends.append(tl(pl["seg"], pl["local"]) + d / pl.get("tempo", 1.0))
    return max([e for e in ends if e <= T + 0.5] or [T - 3.0])


def cuts(t0, t1):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-ss", f"{t0:.3f}", "-to", f"{t1:.3f}", "-i", video,
                        "-vf", "scale=270:480,select='gt(scene,0.28)',showinfo", "-f", "null", "-"], capture_output=True, text=True)
    return [t0 + float(m) for m in re.findall(r"pts_time:([\d.]+)", r.stderr)]


# ---------------- 时间轴 ----------------
BUSY = busy_end()
lo = max(BUSY + 0.05, T - 4.5)
cands = [c for c in cuts(max(0, T - 4.8), TL) if c - CUT_AT >= lo and TL - (c - CUT_AT + FLASH_D) >= 0.6]
if cfg.get("flash_at") is not None:
    FS = float(cfg["flash_at"]); how = "手动指定"
elif cands:
    c = min(cands, key=lambda c: abs(TL - (c - CUT_AT + FLASH_D) - 1.5))
    FS = c - CUT_AT; how = f"盖住 {c:.2f}s 的切镜"
else:
    FS = max(BUSY + 0.05, TL - FLASH_D - 1.5); how = "镜头内（最后一句话之后）"
FS = snap(FS); FE = FS + FLASH_D
LIVE = max(0.0, min(LIVE_MAX, TL - FE))
TZ = snap(FE + LIVE) if LIVE > 0 else snap(min(FE, TL))
BLACK0 = TZ + HOLD + len(DIP) / FPS
CARD0 = BLACK0 + 0.45
TOTAL = CARD0 + 2.1
print(f"[{a.episode}] 最后需要看清 {BUSY:.2f}s；闪光 {FS:.2f}s（{how}）；余光 {LIVE:.2f}s；定格 {TZ:.2f}s；黑 {BLACK0:.2f}s；片尾卡 {CARD0:.2f}s", flush=True)

work = os.path.join(ep, "08_edit", "replica_layers"); shutil.rmtree(work, ignore_errors=True)
for k in ("leak", "dip", "card"): os.makedirs(os.path.join(work, k))

# ---------------- ①② 光层（滤色叠加用，黑 = 无光）----------------
w, h = 270, 480                                     # 光场都很柔，低分辨率算再放大
yy, xx = np.mgrid[0:h, 0:w].astype(np.float32); yn, xn = yy / h, xx / w


def blob(cx, cy, rx, ry): return np.exp(-(((xn - cx) / rx) ** 2 + ((yn - cy) / ry) ** 2))


n_leak = int(round((TZ - FS) * FPS))
for i in range(n_leak):
    t = i / FPS; L = np.zeros((h, w, 3), np.float32)
    if t < FLASH_D + 0.5 / FPS:
        s = np.interp(t - 0.035 * (yn - 0.5), *FLASH)                   # 上半屏先亮先暗
        k = np.clip(4 * s * (1 - s), 0, 1)                               # 中段带颜色，平台纯白
        dr = 0.12 * t / FLASH_D
        g1 = blob(0.80 + dr, 0.15, 0.60, 0.40); g2 = blob(0.05 + dr, 0.85, 0.45, 0.30); g3 = blob(0.55 - dr, 0.95, 0.50, 0.28)
        base = np.array([1.0, 0.80, 0.55])
        col = (base * 0.5 + g1[..., None] * [1.0, 0.95, 0.85] + g2[..., None] * [0.78, 0.40, 1.0] + g3[..., None] * [1.0, 0.48, 0.12])
        col = col / (0.5 + g1 + g2 + g3)[..., None]
        L = s[..., None] * ((1 - k[..., None]) + k[..., None] * col)
    else:
        u = t - FLASH_D
        p = float(np.interp(u, *LEAK))
        mix = ease((u - 0.55) / 0.5)                                     # 暖白 → 青
        col = np.array([1.0, 0.95, 0.88]) * (1 - mix) + np.array([0.62, 0.92, 0.95]) * mix
        L = blob(0.0, 0.38, 0.32, 0.40)[..., None] * col * min(1.0, p * 1.7) + np.array([1.0, 0.90, 0.78]) * 0.05
    im = Image.fromarray((np.clip(L, 0, 1) * 255).astype(np.uint8), "RGB").resize((W, H), Image.BILINEAR)
    im.save(os.path.join(work, "leak", f"{i:03d}.png"))

# ---------------- ③④ 定格 + 黑屏一闪 ----------------
fz = os.path.join(work, "freeze.png")
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{TZ - 0.5 / FPS:.4f}", "-i", video, "-frames:v", "1", fz], check=True)
F0 = Image.open(fz).convert("RGB")
for i, (rad, br) in enumerate(DIP):
    im = F0.filter(ImageFilter.GaussianBlur(rad)).point(lambda v, b=br: int(v * b)); im.save(os.path.join(work, "dip", f"{i:03d}.png"))

# ---------------- 片尾卡 ----------------
def copper(size): return ImageFont.truetype(SUP + "Copperplate.ttc", size, index=1)


def centered(d, cy, text, font, fill, track):
    tw = sum(d.textlength(c, font=font) for c in text) + track * (len(text) - 1); x = (W - tw) / 2
    for c in text: d.text((x, cy), c, font=font, fill=fill); x += d.textlength(c, font=font) + track


for i in range(int((TOTAL - CARD0) * FPS) + 1):
    t = i / FPS; al = ease(t / 0.3)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im); cy = 820
    centered(d, cy, "TO BE CONTINUED", copper(50), (255, 255, 255, int(240 * al)), 14)
    ly = cy + 86; half = int(210 * ease((t - 0.1) / 0.4))
    d.line([(W / 2 - half, ly), (W / 2 + half, ly)], fill=(255, 255, 255, int(200 * al)), width=2)
    if t > 0.45: d.rectangle([W / 2 - 3, ly - 20, W / 2 + 3, ly + 20], fill=(255, 255, 255, int(255 * ease((t - 0.45) / 0.15))))
    im.save(os.path.join(work, "card", f"{i:03d}.png"))

# ---------------- 声音：闪光处明亮的「沙—」+ 细碎闪粒 ----------------
SR = 48000; total_n = int(TOTAL * SR) + SR; mix = np.zeros(total_n)
rng = np.random.default_rng(21)
n = int(1.3 * SR); tt = np.arange(n) / SR
nz = rng.standard_normal(n + 2); nz = np.diff(np.diff(nz))                       # 二阶差分 = 强高通
pk = 0.38
env = np.where(tt < pk, (tt / pk) ** 2, np.exp(-(tt - pk) / 0.28))
mix[int(FS * SR):int(FS * SR) + n] += nz * env * 0.075
for _ in range(26):                                                              # 闪粒
    f = rng.uniform(3000, 9000); at = FS + rng.uniform(0.12, 0.95); m = int(0.05 * SR); q = np.arange(m) / SR
    mix[int(at * SR):int(at * SR) + m] += np.sin(2 * np.pi * f * q) * np.exp(-q / 0.012) * rng.uniform(0.01, 0.035)
wav = os.path.join(work, "hits.wav")
with wave.open(wav, "wb") as wv:
    wv.setnchannels(1); wv.setsampwidth(2); wv.setframerate(SR)
    wv.writeframes((np.clip(mix, -0.95, 0.95) * 32767).astype(np.int16).tobytes())

# ---------------- 合成 ----------------
out = os.path.join(ep, a.out) if a.out else os.path.splitext(video)[0] + "_final.mp4"
nb = TOTAL - BLACK0 + 0.5
duck = f"if(between(t,{FS:.3f},{FE + 0.3:.3f}),0.5,1)"
fc = [
    "[0:v]split=2[va][vb]",
    f"[va]trim=0:{FS:.4f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[v1]",
    f"[vb]trim={FS:.4f}:{TZ:.4f},setpts=PTS-STARTPTS,format=gbrp[vb2]",
    "[1:v]setpts=PTS-STARTPTS,format=gbrp[lk]",
    "[vb2][lk]blend=all_expr='255-(255-min(255,A*(1+2.2*B/255)))*(255-B)/255':shortest=1,setsar=1,format=yuv420p[v2]",
    f"[2:v]trim=0:{HOLD:.3f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[v3]",
    "[3:v]setpts=PTS-STARTPTS,setsar=1,format=yuv420p[v4]",
    f"[6:v]trim=0:{nb:.3f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[v5]",
    "[v1][v2][v3][v4][v5]concat=n=5:v=1:a=0[vc]",
    f"[4:v]format=rgba,setpts=PTS-STARTPTS+{CARD0:.3f}/TB[o3]",
    "[vc][o3]overlay=eof_action=pass[vo]",
    f"[vo]trim=0:{TOTAL:.3f},setpts=PTS-STARTPTS[vout]",
    f"[0:a]volume='{duck}':eval=frame,afade=t=out:st={TZ:.3f}:d={HOLD - 0.15:.3f},apad=pad_dur={TOTAL:.1f},atrim=0:{TOTAL:.3f}[a0]",
    "[5:a]aformat=sample_rates=48000:channel_layouts=stereo[a1]",
    "[a0][a1]amix=inputs=2:normalize=0:duration=first[aout]",
]
cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", video,
       "-framerate", str(FPS), "-i", os.path.join(work, "leak", "%03d.png"),
       "-loop", "1", "-framerate", str(FPS), "-t", f"{HOLD + 0.2:.2f}", "-i", fz,
       "-framerate", str(FPS), "-i", os.path.join(work, "dip", "%03d.png"),
       "-framerate", str(FPS), "-i", os.path.join(work, "card", "%03d.png"),
       "-i", wav, "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}:d={nb + 0.5:.2f}",
       "-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]",
       "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", out]
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode:
    raise SystemExit("ffmpeg 失败：\n" + r.stderr[-1800:])
d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out], capture_output=True, text=True).stdout)
print(f"→ {os.path.relpath(out, ep)}  {d:.2f}s（闪光 {FS:.2f}s，定格 {TZ:.2f}s，片尾卡 {CARD0:.2f}s 起）")
