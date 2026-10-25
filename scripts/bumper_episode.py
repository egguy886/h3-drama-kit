#!/usr/bin/env python3
"""片头标题 + 片尾特效 + 片尾卡（全剧统一系统，protocols/BUMPER.md）。

输入：已烧录字幕/铭牌的成片（1080×1920）+ 拼接报告（取画面结束时间）。输出：<video>_final.mp4（比输入长 END_EXTRA 秒）。
- 片头：不加前置卡（保护前 3 秒钩子）。0.6–3.0 秒在画面上叠剧名 + 集数 + 集名（上部暗角保证可读），配一下低频撞击。
- 片尾（v3「余晖」，tail_style=glow，默认）：最后一句话/叠字/配音结束后 0.2 秒起 —— 0.5 秒白闪（亮度曲线取自参考片）→ 画面带着柔光回来（高光溢出 + 左上漏光），
  慢推、轻微去饱和，停约 1.4 秒 → 0.7 秒渐隐到黑 → 黑底 TO BE CONTINUED。画面不够长时把最后一帧冻住补足。
- 旧版：tail_style=dark（黑色暗角 + 白闪 + 硬切黑）、red（红色警戒，已弃用）。
用法：python3 tools/bumper_episode.py E01 --video 08_edit/E01_v1_768p_subs.mp4 --report 08_edit/E01_v1_768p.json
配置：episodes/Exx/bumpers.json（可选）；缺省从 plan.json 的标题自动生成。
"""
import argparse, json, math, os, shutil, subprocess, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__)); PIPE = os.path.dirname(HERE)
W, H, FPS = 1080, 1920, 24
SUP = "/System/Library/Fonts/Supplemental/"
RED = (222, 38, 38)
END_EXTRA = 1.5          # 片尾卡需要的额外黑场（秒）


def didot(size): return ImageFont.truetype(SUP + "Didot.ttc", size, index=0)
def copper(size): return ImageFont.truetype(SUP + "Copperplate.ttc", size, index=1)


def tw(text, font, track):
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    return sum(d.textlength(c, font=font) for c in text) + track * (len(text) - 1)


def tracked(d, x, y, text, font, fill, track):
    for c in text:
        d.text((x, y), c, font=font, fill=fill); x += d.textlength(c, font=font) + track


def centered(d, cy, text, font, fill, track):
    w = tw(text, font, track); tracked(d, (W - w) / 2, cy, text, font, fill, track)


def ease(x): x = max(0.0, min(1.0, x)); return x * x * (3 - 2 * x)


def title_name(t):
    return (t or "").split("｜")[0].strip()


ap = argparse.ArgumentParser()
ap.add_argument("episode"); ap.add_argument("--video", required=True); ap.add_argument("--report", required=True)
ap.add_argument("--out"); ap.add_argument("--no-title", action="store_true")
ap.add_argument("--style"); ap.add_argument("--flash-mode")   # 临时覆盖 tail_style / freeze_flash，不写回配置
a = ap.parse_args()
ep = os.path.join(PIPE, "episodes", a.episode)
video = os.path.join(ep, a.video); rep = json.load(open(os.path.join(ep, a.report), encoding="utf-8"))
plan = json.load(open(os.path.join(ep, "plan.json"), encoding="utf-8"))
num = int(a.episode[1:])
_pj = os.path.join(PIPE, "project.json")
_series = (json.load(open(_pj, encoding="utf-8")).get("series_title_en") if os.path.isfile(_pj) else None) or "UNTITLED SERIES"
cfg = {"series": _series.upper(), "episode": num, "title": title_name(plan.get("title")),
       "lockup": None,            # 片头剧名叠加：None = 不加（2026-10-12 用户决定：片头不用效果）
       "tail_style": "dark",      # 片尾：dark = 黑色暗角 + 白闪 + 硬切黑（v2，用户最终定稿，全剧标准）；glow/freeze/replica = 试过未采用；red = 已弃用
       "flash_at": None,          # 手动指定白闪时刻（成片秒）；None = 自动（最后一句话/叠字之后）
       "freeze_flash": "image",   # freeze 样式的「黑屏一闪」：image = 黑屏上闪一下定格画面；text = 黑屏后片尾字闪一下
       "accent": None,            # 强调色（线上的小竖标）：None = 白色，不用红
       "show_next": False,        # 片尾卡是否显示下一集
       "next_episode": None, "next_title": None, "flash": True}
nxt = os.path.join(PIPE, "episodes", f"E{num + 1:02d}", "plan.json")
if os.path.isfile(nxt):
    cfg["next_episode"] = num + 1; cfg["next_title"] = title_name(json.load(open(nxt, encoding="utf-8")).get("title"))
cp = os.path.join(ep, "bumpers.json")
if os.path.isfile(cp): cfg.update(json.load(open(cp, encoding="utf-8")))
else: json.dump(cfg, open(cp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
if a.style: cfg["tail_style"] = a.style
if a.flash_mode: cfg["freeze_flash"] = a.flash_mode
if cfg.get("tail_style") == "replica":            # v5：一比一复刻范例结尾，见 tools/ending_replica.py
    import sys
    os.execv(sys.executable, [sys.executable, os.path.join(HERE, "ending_replica.py"), *sys.argv[1:]])

T = float(rep["video_end"])                 # 画面结束（之后是黑场 + 脚步声）
DUR = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                           capture_output=True, text=True).stdout)
GLOW = cfg.get("tail_style") == "glow"
G, FLASH_D, FADE_D = 3.2, 0.5, 0.8          # 余晖总长 / 白闪长度 / 末尾渐隐长度


def busy_end():
    """最后一次「需要观众听/看清」的时刻：最后一句台词、最后一条叠字、最后一条后期配音。"""
    seg = {s["id"]: s for s in rep["segments"]}
    tl = lambda sg, l: seg[sg]["t0"] + (l - seg[sg]["in"])
    ends = []
    wp = os.path.splitext(os.path.join(ep, a.report))[0] + "_words.json"
    if os.path.isfile(wp):
        ends += [w["end"] for sg in json.load(open(wp, encoding="utf-8"))["segments"] for w in sg.get("words", [])]
    op = os.path.join(ep, "overlays.json")
    if os.path.isfile(op):
        ends += [tl(o["seg"], o["l1"]) for o in json.load(open(op, encoding="utf-8"))["items"] if o["seg"] in seg]
    pa = json.load(open(os.path.join(PIPE, "post_audio.json"), encoding="utf-8"))["lines"]
    for l in pa:
        pl = l.get("place")
        if l["episode"] != a.episode or not pl or pl["seg"] not in seg: continue
        wv = os.path.join(ep, "08_edit", "post_audio", l["id"] + ".wav")
        if os.path.isfile(wv):
            with wave.open(wv) as w: dur = w.getnframes() / w.getframerate()
            ends.append(tl(pl["seg"], pl["local"]) + dur / pl.get("tempo", 1.0))
    return max([e for e in ends if e <= T + 0.5] or [T - 3.0])


FREEZE = cfg.get("tail_style") == "freeze"
FZ, BLACK1, FLD, BLACK2 = 0.85, 0.28, 3 / FPS, 0.40     # 定格 / 黑屏 / 闪 3 帧 / 黑屏
IMG = cfg.get("freeze_flash", "image") == "image"
if FREEZE:
    TL = T - 0.06                           # 源片在 T 之前就已硬切黑，取最后一个有内容的帧
    HIT_FLASH = TL + FZ + BLACK1
    CARD0 = HIT_FLASH + (FLD + BLACK2 if IMG else 0.0)
    FX, T0 = FZ, TL
    TOTAL = CARD0 + 1.9
elif GLOW:
    TF = float(cfg["flash_at"]) if cfg.get("flash_at") is not None else max(busy_end() + 0.2, T - 2.0)
    TL = T - 0.06                           # 源片在 T 之前就已硬切黑，取最后一个有内容的帧
    EXT = max(0.0, TF + G - TL)             # 画面不够长时，冻结最后一帧补足
    FX, T0 = G, TF
    T_PIC = TF + G                          # 画面（含渐隐）结束
    CARD0 = T_PIC + 0.3
    TOTAL = max(DUR, TL + EXT) + END_EXTRA
    TOTAL = max(TOTAL, CARD0 + 1.9)
else:                                       # v2 dark（全剧标准）+ 2026-10-13 结尾定格：话说完 → 定格停顿 → 白闪 → 切黑
    BUSY = busy_end()
    TL = T - 0.06                           # 源片在 T 之前就已硬切黑，取最后一个有内容的帧
    HOLD = min(2.0, max(0.6, BUSY + 1.0 - TL))   # 定格至少 0.6 秒；最后一句说完到切黑至少 1 秒
    TE = TL + HOLD                          # 白闪 + 切黑的时刻
    FX = 2.2                                # 片尾特效时长（慢推、去饱和、暗角收紧，跨过定格一直推到切黑）
    T0 = TE - FX
    TOTAL = TE + 0.35 + 2.4
work = os.path.join(ep, "08_edit", "bumper_layers"); shutil.rmtree(work, ignore_errors=True)
for k in ("lock", "tail", "card"): os.makedirs(os.path.join(work, k))


def save(im, k, i): im.save(os.path.join(work, k, f"{i:03d}.png"))


# ---------------- 片头：剧名 + 集数 ----------------
END_TEXT = cfg.get("end_text", "TO BE CONTINUED")      # 大结局用 bumpers.json 的 "end_text": "THE END"
LOCK = cfg.get("lockup")
l0, l1 = LOCK if LOCK else (0.0, 0.0); n_l = int((l1 - l0) * FPS) if LOCK else 0
ACC = tuple(cfg["accent"]) if cfg.get("accent") else (255, 255, 255)
name = cfg["series"]; sub = f"EPISODE {cfg['episode']:02d}  ·  {cfg['title'].upper()}"
scrim = np.zeros((H, W, 4), np.uint8)
g = np.clip(1 - np.arange(H) / 620.0, 0, 1) ** 1.6
scrim[:, :, 3] = (g[:, None] * 150).astype(np.uint8)
scrim_im = Image.fromarray(scrim, "RGBA")
for i in range(n_l):
    t = i / FPS; dur = l1 - l0
    a_in = ease(t / 0.35); a_out = ease((dur - t) / 0.35); al = min(a_in, a_out)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if not a.no_title:
        sc = scrim_im.copy(); sc.putalpha(sc.getchannel("A").point(lambda v: int(v * al))); im.alpha_composite(sc)
        d = ImageDraw.Draw(im)
        f1 = didot(68); y0 = 230
        trk = 6 + 6 * ease(t / 1.6)                       # 字距缓慢拉开，宽度始终限制在画面 82% 以内
        while tw(name, f1, trk) > W * 0.82 and trk > 2: trk -= 0.5
        w1 = tw(name, f1, trk)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        tracked(ld, (W - w1) / 2, y0, name, f1, (255, 255, 255, int(235 * al)), trk)
        glow = lay.filter(ImageFilter.GaussianBlur(10)); ga = glow.getchannel("A").point(lambda v: int(v * 0.5))
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0)); shadow.putalpha(ga); im.alpha_composite(shadow, (0, 6)); im.alpha_composite(lay)
        # 横线从中间向两边画开，中点一根红色竖标（「线被越过」）
        ly = y0 + 112; half = int(300 * ease((t - 0.15) / 0.55))
        d.line([(W / 2 - half, ly), (W / 2 + half, ly)], fill=(255, 255, 255, int(210 * al)), width=2)
        if t > 0.6:
            ra = ease((t - 0.6) / 0.15); flash = 1.0 if t < 0.72 else 0.0
            col = (255, 255, 255, int(255 * al)) if flash else (*ACC, int(255 * ra * al))
            d.rectangle([W / 2 - 3, ly - 22, W / 2 + 3, ly + 22], fill=col)
        sa = ease((t - 0.45) / 0.45) * al
        centered(d, ly + 34, sub, copper(32), (255, 255, 255, int(235 * sa)), 7)
    save(im, "lock", i)
if n_l == 0:
    save(Image.new("RGBA", (W, H), (0, 0, 0, 0)), "lock", 0)

# ---------------- 片尾特效（最后 FX 秒）----------------
n_t = int(FX * FPS)
if FREEZE:
    save(Image.new("RGBA", (W, H), (0, 0, 0, 0)), "tail", 0); n_t = 0
elif GLOW:
    # 白闪亮度曲线取自参考片（0.1 秒冲顶、约 0.3 秒平台、0.15 秒回落）：叠加不透明度
    FL = ([0, .04, .10, .20, .30, .40, .46, FLASH_D], [0, .53, .93, .97, .95, .74, .25, 0])
    yy, xx = np.mgrid[0:H, 0:W]
    d2 = ((xx - W * 0.08) / (W * 0.85)) ** 2 + ((yy - H * 0.30) / (H * 0.55)) ** 2     # 漏光：从左上角漫出
    leak = np.exp(-d2 * 2.2).astype(np.float32)
    for i in range(n_t):
        t = i / FPS
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        amp = 0.30 * ease((t - 0.30) / 0.30) * (1 - 0.65 * ease((t - 1.1) / 1.0))
        if amp > 0.003:
            arr = np.zeros((H, W, 4), np.uint8); arr[:, :, 0] = 255; arr[:, :, 1] = 238; arr[:, :, 2] = 210
            arr[:, :, 3] = (leak * amp * 255).astype(np.uint8); im.alpha_composite(Image.fromarray(arr, "RGBA"))
        fa = float(np.interp(t, *FL))
        if fa > 0.004:
            im.alpha_composite(Image.new("RGBA", (W, H), (255, 253, 250, int(255 * fa))))
        ba = ease((t - (G - FADE_D)) / FADE_D)
        if ba > 0.004:
            im.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(255 * ba))))
        save(im, "tail", i)
    n_t = 0                                  # 旧版循环不再执行
vig = np.zeros((H, W), np.float32)
yy, xx = np.mgrid[0:H, 0:W]
r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
vig = np.clip((r - 0.45) / 0.85, 0, 1) ** 1.7
for i in range(n_t):
    t = i / FPS; p = t / FX
    pulse = 0.5 + 0.5 * math.sin(2 * math.pi * 1.45 * t - 1.2)          # ≈ 脚步节拍
    amp = ease(p * 1.3) * (0.35 + 0.65 * pulse) * 0.85
    arr = np.zeros((H, W, 4), np.uint8)
    if cfg.get("tail_style") == "red":
        arr[:, :, 0] = 230; arr[:, :, 1] = 20; arr[:, :, 2] = 25
    else:                                                      # 黑色暗角，随推进缓慢收紧，没有脉冲
        amp = ease(p * 1.1) * 0.72
    arr[:, :, 3] = (vig * amp * 255).astype(np.uint8)
    im = Image.fromarray(arr, "RGBA")
    if cfg.get("flash", True) and t > FX - 0.17:   # 切黑前 4 帧白闪
        k = (t - (FX - 0.17)) / 0.17
        im = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * ease(0.4 + 0.6 * k))))
    save(im, "tail", i)

# ---------------- 片尾卡（黑底）----------------
card0 = CARD0 if (GLOW or FREEZE) else TE + 0.35
n_c = int((TOTAL - card0) * FPS)
for i in range(n_c):
    t = i / FPS; al = ease(t / (0.8 if GLOW else 0.5))
    if FREEZE:                                # 干脆：直接切入，不淡入
        al = 1.0
        if not IMG and 3 / FPS <= t < 4 / FPS: al = 0.0       # text 变体：字闪一下（亮—灭—亮）
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    cy = 820
    if GLOW:                                  # 字距从 24 慢慢收到 14，带一圈柔光，像「余晖」落定
        trk = 14 + 10 * (1 - ease(t / 1.6))
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        centered(ld, cy, END_TEXT, copper(50), (255, 255, 255, int(240 * al)), trk)
        halo = lay.filter(ImageFilter.GaussianBlur(14)); halo.putalpha(halo.getchannel("A").point(lambda v: int(v * 0.55)))
        im.alpha_composite(halo); im.alpha_composite(lay)
    else:
        centered(d, cy, END_TEXT, copper(50), (255, 255, 255, int(240 * al)), 14)
    ly = cy + 86; half = int(210 * ease((t - 0.1) / (0.2 if FREEZE else 0.5)))
    d.line([(W / 2 - half, ly), (W / 2 + half, ly)], fill=(255, 255, 255, int(200 * al)), width=2)
    if t > (0.25 if FREEZE else 0.5):
        d.rectangle([W / 2 - 3, ly - 20, W / 2 + 3, ly + 20], fill=(*ACC, int(255 * (al if FREEZE else ease((t - 0.5) / 0.15)))))
    if cfg.get("show_next") and cfg.get("next_episode"):
        na = ease((t - 0.6) / 0.5)
        centered(d, ly + 74, f"NEXT  ·  EPISODE {cfg['next_episode']:02d}", copper(32), (255, 255, 255, int(205 * na)), 8)
        centered(d, ly + 128, cfg["next_title"], didot(64), (255, 255, 255, int(240 * na)), 3)
    save(im, "card", i)

# ---------------- 声音：开场撞击 + 切黑下沉 ----------------
SR = 48000
def tone(ts, dur, f0, f1=None, decay=0.3, noise=0.0, seed=1):
    n = int(dur * SR); t = np.arange(n) / SR; f1 = f1 or f0
    f = f0 + (f1 - f0) * (t / dur); ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) * np.exp(-t / decay)
    if noise:
        rng = np.random.default_rng(seed); nz = rng.standard_normal(n)
        k = np.ones(40) / 40; nz = np.convolve(nz, k, "same")
        s += noise * nz * np.exp(-t / (decay * 0.5))
    return s
total_n = int(TOTAL * SR); mix = np.zeros(total_n)
def put(sig, at, gain):
    i0 = int(at * SR); sig = sig * gain
    mix[i0:i0 + len(sig)] += sig[:max(0, total_n - i0)]
if LOCK:
    put(tone(0, 1.4, 62, 38, 0.45, 0.35, 3), l0, 0.55)                    # 片头：低频撞击
    put(tone(0, 0.5, 2400, 1800, 0.05, 0.0, 4), l0 + 0.6, 0.10)           # 标出现的细微金属点
if FREEZE:
    put(tone(0, 0.30, 78, 40, 0.09, 0.10, 11), TL, 0.85)                       # 定格：短促低击，原声同时掐断
    hit = HIT_FLASH if IMG else CARD0
    put(tone(0, 0.10, 3600, 700, 0.025, 0.7, 12), hit, 0.45)                   # 一闪：脆响
    put(tone(0, 0.55, 46, 30, 0.22, 0.05, 13), hit, 0.80)                      # 一闪：低频
elif GLOW:
    n_sw = int(0.55 * SR); env = (np.arange(n_sw) / n_sw) ** 2.2
    air = np.diff(np.random.default_rng(8).standard_normal(n_sw + 1))        # 差分 = 高通，白噪变「气声」
    put(air * env, TF - 0.55, 0.16)                                          # 白闪前：气声上扬
    put(tone(0, 1.8, 58, 32, 0.55, 0.14, 7), TF, 0.80)                       # 白闪：低频一击
    ring = sum(tone(0, 1.8, f, f, 0.55) * g for f, g in ((1760, .05), (2349, .035), (3520, .02)))
    put(ring, TF + 0.02, 1.0)                                                # 玻璃般的余响
else:
    put(tone(0, 0.18, 3200, 600, 0.04, 0.6, 5), TE - 0.17, 0.35)              # 白闪：快门咔哒
    put(tone(0, 2.2, 52, 30, 0.7, 0.18, 6), TE, 0.75)                         # 切黑：低频下沉
sig = np.clip(mix, -0.95, 0.95)
wav = os.path.join(work, "hits.wav")
with wave.open(wav, "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((sig * 32767).astype(np.int16).tobytes())

# ---------------- 合成 ----------------
out = a.out and os.path.join(ep, a.out) or os.path.splitext(video)[0] + "_final.mp4"
Z = 0.065
if FREEZE:
    lastf = f"trim=start={TL - 1.5 / FPS:.4f}:end={TL:.4f},setpts=PTS-STARTPTS"
    fc = [
        "[0:v]split=3[va][vb][vc]" if IMG else "[0:v]split=2[va][vb]",
        f"[va]trim=0:{TL:.3f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[v1]",
        f"[vb]{lastf},tpad=stop_mode=clone:stop_duration={FZ + 0.1:.3f},trim=0:{FZ:.3f},"
        f"scale=1112:1976,crop=1080:1920,eq=saturation=0.85,setsar=1,format=yuv420p,setpts=PTS-STARTPTS[vh]",
        f"[5:v]trim=0:{BLACK1:.3f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[bk]",
    ]
    if IMG:
        fc += [f"[vc]{lastf},tpad=stop_mode=clone:stop_duration=0.3,trim=0:{FLD:.3f},"
               f"eq=contrast=1.15:brightness=0.20:saturation=0.5,setsar=1,format=yuv420p,setpts=PTS-STARTPTS[vf]",
               "[v1][vh][bk][vf]concat=n=4:v=1:a=0[vc2]"]
    else:
        fc += ["[v1][vh][bk]concat=n=3:v=1:a=0[vc2]"]
    fc += [
        f"[vc2]tpad=stop_mode=add:stop_duration=5:color=black[vp]",
        f"[1:v]format=rgba,setpts=PTS-STARTPTS+{l0:.3f}/TB[o1]",
        f"[3:v]format=rgba,setpts=PTS-STARTPTS+{card0:.3f}/TB[o3]",
        "[vp][o1]overlay=eof_action=pass[x1]", "[x1][o3]overlay=eof_action=pass[vout0]",
        f"[vout0]trim=0:{TOTAL:.3f},setpts=PTS-STARTPTS[vout]",
        f"[0:a]atrim=0:{TL:.3f},afade=t=out:st={TL - 0.05:.3f}:d=0.05,apad=pad_dur=6,atrim=0:{TOTAL:.3f}[a0]",
        "[4:a]aformat=sample_rates=48000:channel_layouts=stereo[a1]",
        "[a0][a1]amix=inputs=2:normalize=0:duration=longest[aout]",
    ]
elif GLOW:
    Zg = 0.045
    tail = TL + EXT < DUR - 0.05
    fc = [
        f"[0:v]split={3 if tail else 2}[va][vb]" + ("[vc]" if tail else ""),
        f"[va]trim=0:{TF:.3f},setpts=PTS-STARTPTS[v1]",
        f"[vb]trim={TF:.3f}:{TL:.3f},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={EXT:.3f},"
        f"scale=w='trunc(1080*(1+{Zg}*min(t/{G},1))/2)*2':h='trunc(1920*(1+{Zg}*min(t/{G},1))/2)*2':eval=frame,crop=1080:1920,"
        f"eq=saturation='1-0.22*min(t/{G},1)':eval=frame,format=gbrp,split[g1][g2]",
        f"[g2]gblur=sigma=26:steps=2[gb]",
        f"[g1][gb]blend=all_expr='A+(255-A)*B/255*0.55*min(1,T/0.35)',format=yuv420p[v2]",
    ]
    if tail:
        fc += [f"[vc]trim={TL + EXT:.3f}:{DUR:.3f},setpts=PTS-STARTPTS[v4]", "[v1][v2][v4]concat=n=3:v=1:a=0[vc2]"]
    else:
        fc += ["[v1][v2]concat=n=2:v=1:a=0[vc2]"]
    fc += [
        f"[vc2]tpad=stop_mode=add:stop_duration={END_EXTRA + 2:.3f}:color=black[vp]",
        f"[1:v]format=rgba,setpts=PTS-STARTPTS+{l0:.3f}/TB[o1]",
        f"[2:v]format=rgba,setpts=PTS-STARTPTS+{TF:.3f}/TB[o2]",
        f"[3:v]format=rgba,setpts=PTS-STARTPTS+{card0:.3f}/TB[o3]",
        f"[vp][o1]overlay=eof_action=pass[x1]", f"[x1][o2]overlay=eof_action=pass[x2]", f"[x2][o3]overlay=eof_action=pass[vout0]",
        f"[vout0]trim=0:{TOTAL:.3f},setpts=PTS-STARTPTS[vout]",
        f"[0:a]volume='if(lt(t,{TF + 0.3:.3f}),1,max(0.3,1-0.7*(t-{TF + 0.3:.3f})/{G - 0.3:.3f}))':eval=frame,"
        f"apad=pad_dur={END_EXTRA + 2:.3f},atrim=0:{TOTAL:.3f}[a0]",
        f"[4:a]aformat=sample_rates=48000:channel_layouts=stereo[a1]",
        f"[a0][a1]amix=inputs=2:normalize=0:duration=longest[aout]",
    ]
else:
  fc = [
    f"[0:v]split=2[va][vb]",
    f"[va]trim=0:{T0:.3f},setpts=PTS-STARTPTS[v1]",
    f"[vb]trim={T0:.3f}:{TL:.3f},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={HOLD:.3f},"
    f"scale=w='trunc(1080*(1+{Z}*min(t/{FX:.3f},1))/2)*2':h='trunc(1920*(1+{Z}*min(t/{FX:.3f},1))/2)*2':eval=frame,crop=1080:1920,"
    f"eq=saturation='1-0.30*min(t/{FX:.3f},1)':eval=frame,"
    f"rgbashift=rh=-9:bh=9:enable='between(t,{FX - 0.30:.3f},{FX - 0.17:.3f})'[v2]",
    f"[v1][v2]concat=n=2:v=1:a=0[vc]",
    f"[vc]tpad=stop_mode=add:stop_duration=6:color=black[vp]",
    f"[1:v]format=rgba,setpts=PTS-STARTPTS+{l0:.3f}/TB[o1]",
    f"[2:v]format=rgba,setpts=PTS-STARTPTS+{T0:.3f}/TB[o2]",
    f"[3:v]format=rgba,setpts=PTS-STARTPTS+{card0:.3f}/TB[o3]",
    f"[vp][o1]overlay=eof_action=pass[x1]",
    f"[x1][o2]overlay=eof_action=pass[x2]",
    f"[x2][o3]overlay=eof_action=pass[vo]",
    f"[vo]trim=0:{TOTAL:.3f},setpts=PTS-STARTPTS[vout]",
    f"[0:a]apad=pad_dur=6,atrim=0:{TOTAL:.3f}[a0]",
    f"[4:a]aformat=sample_rates=48000:channel_layouts=stereo[a1]",
    f"[a0][a1]amix=inputs=2:normalize=0:duration=longest[aout]",
]
cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", video,
       "-framerate", str(FPS), "-i", os.path.join(work, "lock", "%03d.png"),
       "-framerate", str(FPS), "-i", os.path.join(work, "tail", "%03d.png"),
       "-framerate", str(FPS), "-i", os.path.join(work, "card", "%03d.png"),
       "-i", wav, *(["-f", "lavfi", "-i", f"color=c=black:s=1080x1920:r=24:d={BLACK1 + 0.5}"] if FREEZE else []),
       "-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]",
       "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", out]
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode:
    raise SystemExit("ffmpeg 失败：\n" + r.stderr[-1800:])
d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out], capture_output=True, text=True).stdout)
print(f"→ {os.path.relpath(out, ep)}  {d:.2f}s（画面特效 {T0:.2f}s 起" + (f"，定格 {TL:.2f}–{TE:.2f}s" if not (GLOW or FREEZE) else "") + f"，片尾卡 {card0:.2f}s 起）")
