#!/usr/bin/env python3
"""整集拼接（PIPELINE 第 5 节）：硬切、接力缝逐帧找切点、对白段 J-cut、音频短交叉淡化、集尾切黑。

用法：python tools/assemble_episode.py E01 [--out 08_edit/E01_full_v1.mp4] [--end-black 13.5]
- 每段取账本里最后一次 kept 的片子；同名的 *_vc-*.mp4（voice_fix 统一过声线）存在时优先用它。
- TAIL_RELAY 缝：在上一段尾帧位置前 1.0s 内、下一段开头 1.0s 内逐帧比对，取画面最接近的一对作切点；
  下一段入点限制在开头 12 帧内；下一段第一个镜头有对白时，它的声音从第 0 帧开始、提前压在上一段画面上（J-cut = 入点，≤12 帧）。
- HARD_CUT（换场）缝：上一段用满，下一段从第 0 帧开始，音频 120ms 交叉淡化。
- 集尾：最后一段在 --end-black 秒切黑，声音压着黑屏延续到片尾。
- 同场景接色（2026-10-15，E31 起，delivery.json color_match）：接力缝两侧、灯光设定相同的段为一组，每段取 9 帧的逐通道
  中位均值与离散度，向组内中位数拉近 strength（0.7），每通道一个增益 + 偏移（有上限）；换场缝与有意的光变不动。做法借鉴 zenstory-ai/drama-skills。
- 台词保护（2026-10-13）：用 Whisper 词级时间（缓存 08_edit/vc/words/）——上一段出点不早于最后一个词结束 +0.18s；
  下一段入点前有词时改用 J-cut 让声音从第 0 帧起；集尾切黑不早于最后一个词结束 +0.6s。此前只按画面选切点，全剧 16 处剪掉了半句话。
输出：mp4 + 同名 .json（每段入出点、切点、J-cut 时长），只用 ffmpeg / numpy。
"""
import argparse, glob, json, os, re, subprocess, tempfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); PIPE = os.path.dirname(HERE)
from delivery import profile
FPS = 24; W, H = 96, 170
SCENE_IDS = set(json.load(open(os.path.join(PIPE, "library", "scenes.json"), encoding="utf-8")))
MAX_IN = 12 / FPS


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, check=True)


def dur(p):
    return float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p]).stdout)


def frames(clip, start, length):
    raw = sh(["ffmpeg", "-loglevel", "error", "-ss", f"{max(0, start):.3f}", "-t", f"{length:.3f}", "-i", clip,
              "-vf", f"fps={FPS},scale={W}:{H},format=gray", "-f", "rawvideo", "-"]).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(float)


WH = (__import__("shutil").which("whisper") or "/opt/homebrew/bin/whisper")


def words_of(ep, clip):
    """该片子的 Whisper 词级时间（与 voice_fix_ep / pick_anchors 共用缓存），返回 [(start, end)]"""
    stem = os.path.splitext(os.path.basename(clip))[0]
    cache = os.path.join(ep, "08_edit", "vc", "words", stem + ".json")
    if not os.path.isfile(cache):
        tmp = tempfile.mkdtemp(); os.makedirs(os.path.dirname(cache), exist_ok=True)
        subprocess.run([WH, clip, "--model", "small", "--language", "en", "--word_timestamps", "True", "--output_format", "json",
                        "--output_dir", tmp, "--fp16", "False"], capture_output=True)
        os.replace(os.path.join(tmp, stem + ".json"), cache)
    js = json.load(open(cache, encoding="utf-8"))
    return [(w["start"], w["end"]) for sg in js["segments"] for w in sg.get("words", [])]


ap = argparse.ArgumentParser()
ap.add_argument("episode"); ap.add_argument("--out"); ap.add_argument("--end-black", type=float, default=13.5)
ap.add_argument("--no-bed", action="store_true", help="不铺分场景环境声底（E31 起默认铺）"); ap.add_argument("--bed-offset-db", type=float, default=0.0, help="环境声底整体电平偏移")
a = ap.parse_args()
ep = os.path.join(PIPE, "episodes", a.episode)
plan = json.load(open(os.path.join(ep, "plan.json"), encoding="utf-8"))
rows = [json.loads(l) for l in open(os.path.join(ep, "06_jobs", "ledger.jsonl"), encoding="utf-8") if l.strip()]

segs = []
for s in plan["segments"]:
    kept = [r for r in rows if r["seg"] == s["id"] and r["outcome"] == "kept"]
    if not kept:
        raise SystemExit(f"Seg{s['id']} 没有 kept 片子")
    clip = os.path.join(ep, kept[-1]["clip"])
    vc = sorted(glob.glob(os.path.splitext(clip)[0] + "_vc-*.mp4"), key=os.path.getmtime)
    tail = os.path.join(ep, "07_clips", f"seg{s['id']:02d}_tail_meta.json")
    off = json.load(open(tail, encoding="utf-8"))["tail_offset_from_end"] if os.path.isfile(tail) else None
    loc = next((r[2] for r in s.get("refs", []) if len(r) > 2 and r[2] in SCENE_IDS), None)     # 2026-10-17 修：原写法把接力首帧（None）和 X- 开头的角色也当成地点，接力段的 loc 变成 None，同场景接色和环境声底分不了组
    scene_key = (re.match(r"场\d+", s.get("scene", "")) or [s.get("scene")])[0], loc     # 场次编号 + 地点参考图（标题括号里每段不同）
    segs.append({"light": s.get("light"), "scene": scene_key, "loc": loc, "id": s["id"], "clip": clip, "audio": vc[-1] if vc else clip, "dur": dur(clip),
                 "next": s["connection_to_next"], "first_dialogue": bool(s["shots"][0]["dialogue"]), "tail_off": off,
                 "has_dialogue": any(sh.get("dialogue") for sh in s["shots"]), "last_shot": s["shots"][-1]["dur"]})
    ws = words_of(ep, clip) if any(sh.get("dialogue") for sh in s["shots"]) else []
    segs[-1]["w_first"] = min((w[0] for w in ws), default=None); segs[-1]["w_last"] = max((w[1] for w in ws), default=None)

# ---- 剪辑单（E41 起）：episodes/Exx/edit.json = {"drop":[段号], "trim_in":{段号:秒}, "trim_out":{段号:秒}}；没有这个文件时按默认规则 ----
EPN = 99          # 工具包：所有集都用最新剪辑规则（原项目 E41 起才启用《BREAK》法硬切剪辑）
EDIT = {}
_ep_edit = os.path.join(ep, "edit.json")
if EPN >= 41 and os.path.isfile(_ep_edit):
    EDIT = json.load(open(_ep_edit, encoding="utf-8"))
segs = [g for g in segs if g["id"] not in set(EDIT.get("drop", []))]
HEAD_TRIM, TAIL_PAD, LAST_SHOT_MIN, LCUT = 0.08, 1.0, 2.2, 0.25

# 入出点
for i, g in enumerate(segs):
    g.setdefault("in", 0.0); g["out"] = g["dur"]; g["j"] = 0.0
    if EPN >= 41 and i < len(segs) - 1:                      # 《BREAK》法硬切：去掉每段开头约 2 帧的起步帧，结尾去掉台词后的多余停留
        g["in"] = float(EDIT.get("trim_in", {}).get(str(g["id"]), HEAD_TRIM if i else 0.0))
        if str(g["id"]) in EDIT.get("trim_out", {}):
            g["out"] = min(g["dur"], float(EDIT["trim_out"][str(g["id"])]))
        elif g["has_dialogue"] and g["w_last"] is not None and g["next"] != "TAIL_RELAY":
            g["out"] = round(min(g["dur"], max(g["w_last"] + TAIL_PAD, g["dur"] - g["last_shot"] + min(g["last_shot"], LAST_SHOT_MIN))), 3)
        elif g["next"] != "TAIL_RELAY":
            g["out"] = round(g["dur"] - 0.15, 3)
for i in range(len(segs) - 1):
    g, n = segs[i], segs[i + 1]
    if g["next"] != "TAIL_RELAY":
        continue
    tail_t = g["dur"] - (g["tail_off"] or 0.5)
    a0 = tail_t - 1.0; a1 = tail_t
    if g["w_last"] is not None and g["w_last"] + 0.18 > a0:          # 台词保护：切点只能落在最后一个词之后
        a0 = min(g["w_last"] + 0.18, g["dur"] - 2 / FPS); a1 = max(a1, min(g["dur"] - 1 / FPS, a0 + 0.5))
    A = frames(g["clip"], a0, a1 - a0 + 1 / FPS); B = frames(n["clip"], 0, MAX_IN)   # 入点最多 12 帧，保证 J-cut 不超 0.5s
    D = np.array([[np.abs(x - y).mean() for y in B] for x in A])
    ia, ib = np.unravel_index(D.argmin(), D.shape)
    g["out"] = round(a0 + (ia + 1) / FPS, 3); n["in"] = round(ib / FPS, 3)
    if g["w_last"] is not None and g["out"] < g["w_last"] + 0.18:
        g["out"] = round(min(g["dur"], g["w_last"] + 0.18), 3)
    g["seam_diff"] = round(float(D[ia, ib]), 2); g["seam_diff_at_tail"] = round(float(D[-1, 0]), 2)
    if n["first_dialogue"] or (n["w_first"] is not None and n["w_first"] < n["in"] + 0.05):
        n["j"] = n["in"]                    # 下一段声音从它的第 0 帧起，提前量 = 入点（入点前有词时也这样，避免吞掉第一个词）
if EPN >= 41:
    for g in segs:
        if g["in"] > 0 and g["j"] == 0 and g["w_first"] is not None and g["w_first"] < g["in"] + 0.05:
            g["j"] = g["in"]
lw = segs[-1]["w_last"]
segs[-1]["vout"] = min(max(a.end_black, (lw or 0) + 0.6), segs[-1]["dur"] - 1 / FPS)   # 集尾：话说完 0.6s 后才切黑

# 同场景接色
CM = profile(a.episode).get("color_match")


def rgb_stats(g):
    """该段可用区间内均匀取 9 帧，返回逐通道（均值、离散度）的帧间中位数，0–1。"""
    t0 = g["in"]; t1 = g.get("vout", g["out"]); n = 9
    raw = sh(["ffmpeg", "-loglevel", "error", "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}", "-i", g["clip"],
              "-vf", f"fps={n / max(0.5, t1 - t0):.4f},scale=96:170,format=rgb24", "-f", "rawvideo", "-"]).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 170 * 96, 3).astype(float) / 255
    return np.median(fr.mean(1), 0), np.median(fr.std(1), 0)


if CM:
    groups, cur = [], [segs[0]]
    for prev, g in zip(segs, segs[1:]):
        if (prev["next"] == "TAIL_RELAY" or EPN >= 41) and prev["light"] == g["light"] and prev["scene"] == g["scene"]:
            cur.append(g)
        else:
            groups.append(cur); cur = [g]
    groups.append(cur)
    for grp in groups:
        if len(grp) < 2:
            continue
        st = [rgb_stats(g) for g in grp]
        gm = np.median([x[0] for x in st], 0); gs = np.median([x[1] for x in st], 0)
        for g, (m, sd) in zip(grp, st):
            k = CM["strength"]; lo, hi = CM["gain_range"]
            gain = (sd + k * (gs - sd)) / np.maximum(sd, 1e-3)
            off = m + k * (gm - m) - gain * m
            if gain.min() < lo or gain.max() > hi or np.abs(off).max() > CM["offset_max"]:   # 差得太多＝有意的光变（强光、闪电、警报），不校
                g["color_skip"] = "差异超出校正范围，视为有意光变"; continue
            if np.abs(gain - 1).max() > 0.01 or np.abs(off).max() > 0.004:
                g["color"] = {"gain": [round(float(x), 3) for x in gain], "offset": [round(float(x), 4) for x in off],
                              "group": [x["id"] for x in grp]}

# 时间线
t = 0.0
for g in segs:
    g["vlen"] = (g.get("vout", g["out"])) - g["in"]
    g["t0"] = t; t += g["vlen"]
video_end = t
total = video_end + (segs[-1]["dur"] - segs[-1]["vout"])   # 集尾声音延续

inputs, fv, fa = [], [], []
for k, g in enumerate(segs):
    inputs += ["-i", g["clip"], "-i", g["audio"]]
    vi, ai = 2 * k, 2 * k + 1
    cm = ""
    if g.get("color"):
        gn, of = g["color"]["gain"], g["color"]["offset"]
        cm = ",lutrgb=" + ":".join(f"{c}='clip(val*{gn[i]}+{of[i] * 255:.2f},0,255)'" for i, c in enumerate("rgb"))
    fv.append(f"[{vi}:v]trim={g['in']:.3f}:{g['in'] + g['vlen']:.3f},setpts=PTS-STARTPTS,fps={FPS}{cm}[v{k}]")
    a_start = g["in"] - g["j"]                      # J-cut：声音比画面早
    a_end = g["out"] if k < len(segs) - 1 else g["dur"]
    nxt_j = segs[k + 1]["j"] if k < len(segs) - 1 else 0.0
    fo = max(0.12, nxt_j)
    if EPN >= 41 and k < len(segs) - 1 and g["next"] != "TAIL_RELAY":      # L-cut：上一段的声音多留 0.25s 压在下一镜头上，和下一段声音交叉
        ext = min(LCUT, g["dur"] - g["out"]); a_end = g["out"] + ext; fo = max(fo, ext + 0.12)
    alen = a_end - a_start
    fa.append(f"[{ai}:a]atrim={max(0, a_start):.3f}:{a_end:.3f},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,"
              f"afade=t=in:st=0:d=0.06" + (f",afade=t=out:st={alen - fo:.3f}:d={fo:.3f}" if k < len(segs) - 1 else "") +
              f",adelay={int((g['t0'] - g['j']) * 1000)}|{int((g['t0'] - g['j']) * 1000)}[a{k}]")
_wh = sh(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", segs[0]["clip"]]).stdout.decode().strip()
black = f"color=c=black:s={_wh}:r={FPS}:d={total - video_end:.3f}[vb]"          # 集尾黑屏取成片真实尺寸（480p / 768p 通用）
vcat = "".join(f"[v{k}]" for k in range(len(segs))) + f"[vb]concat=n={len(segs) + 1}:v=1:a=0[v]"
def layer_rms(layer, _cache={}):
    """这一层噪声（滤波后）的实测 RMS（dBFS），用来把 layer.db 校准成真实电平。"""
    key = json.dumps(layer, sort_keys=True)
    if key not in _cache:
        if "sine" in layer:
            src, fl = f"sine=f={layer['sine']}:sample_rate=48000:duration=4", "anull"
        else:
            src = f"anoisesrc=color={layer['noise']}:sample_rate=48000:amplitude=0.5:duration=4:seed=3"
            fl = f"highpass=f={layer['hp']},lowpass=f={layer['lp']}" if layer.get("hp") else "anull"
        err = subprocess.run(["ffmpeg", "-hide_banner", "-f", "lavfi", "-i", src, "-af", fl + ",volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
        m = re.search(r"mean_volume: (-?[\d.]+) dB", err)
        _cache[key] = float(m.group(1)) if m else -25.0
    return _cache[key]


# ---- 分场景连续环境声底（library/ambience.json；E31 起）----
bed_inputs, bed_fa, bed_labels, bed_report = [], [], [], []
AMB = json.load(open(os.path.join(PIPE, "library", "ambience.json"), encoding="utf-8"))
if not a.no_bed and profile(a.episode).get("color_match") and AMB["scenes"]:
    runs, cur = [], []
    for g in segs:
        if cur and cur[-1]["loc"] == g["loc"]:
            cur.append(g)
        else:
            if cur: runs.append(cur)
            cur = [g]
    runs.append(cur)
    XF = 0.5                                                    # 相邻两段底声各延伸 0.5s 互相交叉淡化
    n_in = 2 * len(segs); li = 0
    for ri, run in enumerate(runs):
        rec = AMB["recipes"].get(AMB["scenes"].get(run[0]["loc"] or ""))
        if not rec:
            bed_report.append({"segs": [g["id"] for g in run], "loc": run[0]["loc"], "bed": None}); continue
        t_a = max(0.0, run[0]["t0"] - (XF if ri else 0.0)); t_b = (total if ri == len(runs) - 1 else run[-1]["t0"] + run[-1]["vlen"] + XF)
        L = t_b - t_a; mix = []
        for layer in rec["layers"]:
            if "sine" in layer:
                src = f"sine=f={layer['sine']}:sample_rate=48000:duration={L:.3f}"; fl = ""
            else:
                src = f"anoisesrc=color={layer['noise']}:sample_rate=48000:amplitude=0.5:duration={L:.3f}:seed={7 + li}"
                fl = f"highpass=f={layer['hp']},lowpass=f={layer['lp']}," if layer.get("hp") else ""
            bed_inputs += ["-f", "lavfi", "-i", src]
            tr = f"tremolo=f={layer['trem'][0]}:d={layer['trem'][1]}," if layer.get("trem") else ""
            lab = f"b{li}"; li += 1
            # anoisesrc 满幅 0.5 的 RMS 约 -12 dBFS（pink）/ 更低（brown），统一用 volume 定电平：先用 loudnorm 无意义，这里按经验补偿 -9 dB 后加上 layer.db
            bed_fa.append(f"[{n_in}:a]aformat=sample_rates=48000:channel_layouts=stereo,{fl}{tr}volume={layer['db'] + a.bed_offset_db - layer_rms(layer):.1f}dB[{lab}]")
            n_in += 1; mix.append(f"[{lab}]")
        fi = XF if ri else 0.4; fo = XF if ri < len(runs) - 1 else 1.2
        bed_fa.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:duration=longest,afade=t=in:st=0:d={fi},afade=t=out:st={max(0.0, L - fo):.3f}:d={fo},"
                      f"adelay={int(t_a * 1000)}|{int(t_a * 1000)}[bed{ri}]")
        bed_labels.append(f"[bed{ri}]")
        bed_report.append({"segs": [g["id"] for g in run], "loc": run[0]["loc"], "bed": AMB["scenes"].get(run[0]["loc"]), "t": [round(t_a, 2), round(t_b, 2)]})
amix = "".join(f"[a{k}]" for k in range(len(segs))) + "".join(bed_labels) + f"amix=inputs={len(segs) + len(bed_labels)}:normalize=0:duration=longest,atrim=0:{total:.3f}[a]"
out = a.out and os.path.join(ep, a.out) or os.path.join(ep, "08_edit", f"{a.episode}_full_{plan['version']}.mp4")
fc = ";".join(fv + [black, vcat] + fa + bed_fa + [amix])
sh(["ffmpeg", "-loglevel", "error", "-y", *inputs, *bed_inputs, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
    "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", out])
rep = {"episode": a.episode, "output": os.path.relpath(out, ep), "duration": round(dur(out), 2), "video_end": round(video_end, 2),
       "ambience_bed": bed_report,
       "segments": [{k: (os.path.relpath(v, ep) if k in ("clip", "audio") else v) for k, v in g.items()} for g in segs]}
json.dump(rep, open(os.path.splitext(out)[0] + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"→ {os.path.relpath(out, ep)}  {rep['duration']}s（画面到 {video_end:.2f}s，之后黑屏压声）")
for g in segs:
    seam = f"  缝差 {g['seam_diff']}（尾帧处 {g['seam_diff_at_tail']}）" if "seam_diff" in g else ""
    print(f"  Seg{g['id']}  {g['t0']:6.2f}s 起  入 {g['in']:.3f} 出 {g.get('vout', g['out']):.3f}  J-cut {g['j']:.3f}s"
          f"  声音{'(声线统一版)' if g['audio'] != g['clip'] else ''}{seam}"
          + (f"  接色 增益{g['color']['gain']} 偏移{g['color']['offset']}" if g.get("color") else "")
          + (f"  不接色（{g['color_skip']}）" if g.get("color_skip") else ""))
