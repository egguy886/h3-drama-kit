#!/usr/bin/env python3
"""单集收尾一条龙（全剧标准流程）：拼接 → Whisper 词级转写 → 字幕/铭牌/叠字 → 片尾特效与片尾卡 → 检查图。
前置：该集已做过声线统一（voice_fix_ep.py）；episodes/Exx/titles.json、overlays.json（可选）已就绪。
用法：python3 tools/finish_episode.py E02
输出：episodes/Exx/08_edit/Exx_v1_768p_final.mp4（以及中间文件）+ review/final_check/Exx.jpg
"""
import json, os, shutil, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__)); PIPE = os.path.dirname(HERE)
ep = sys.argv[1]; d = os.path.join(PIPE, "episodes", ep); ed = os.path.join(d, "08_edit")
FROM_SUBS = "--from-subs" in sys.argv        # 跳过拼接/转写/后期配音，沿用已有中间文件，只重做字幕、叠字、片尾
base = f"{ep}_v1_768p"


def run(cmd, label):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=PIPE)
    if r.returncode:
        sys.exit(f"[{ep}] {label} 失败：\n{(r.stderr or r.stdout)[-1500:]}")
    return r.stdout


os.makedirs(ed, exist_ok=True)
if not FROM_SUBS:
    print(f"[{ep}] 拼接…", flush=True)
    run([sys.executable, "tools/assemble_episode.py", ep, "--out", f"08_edit/{base}.mp4"], "拼接")
rep = json.load(open(os.path.join(ed, base + ".json"), encoding="utf-8"))
vc = sum(1 for s in rep["segments"] if s["audio"] != s["clip"])
print(f"[{ep}] 拼接完成 {rep['duration']}s，声线统一版 {vc}/8 段", flush=True)

# ---- 后期配音（设备里的声音：录音笔回放、终端合成声等，post_audio.json 的 place）----
def timeline(sg, local):
    g = next(s for s in rep["segments"] if s["id"] == sg)
    return g["t0"] + (local - g["in"])


PA = json.load(open(os.path.join(PIPE, "post_audio.json"), encoding="utf-8"))["lines"]
mine = [l for l in PA if l["episode"] == ep and l.get("place")]
vid = base + ".mp4"
if mine and FROM_SUBS:
    vid = base + "_mixed.mp4"
elif mine:
    print(f"[{ep}] 后期配音 {len(mine)} 条…", flush=True)
    ins = ["-i", os.path.join(ed, base + ".mp4")]; fc = []; labels = ["[a0]"]
    chain = "[0:a]"
    for k, l in enumerate(mine, 1):
        pl = l["place"]; wav = os.path.join(d, "08_edit", "post_audio", l["id"] + ".wav")
        t_on = timeline(pl["seg"], pl["local"])
        da, db = timeline(*pl["duck"][0]), timeline(*pl["duck"][1])
        vol = 10 ** (pl.get("duck_db", -18) / 20)
        fc.append(f"{chain}volume={vol:.4f}:enable='between(t,{da:.3f},{db:.3f})'[d{k}]"); chain = f"[d{k}]"
        ins += ["-i", wav]
        fc.append(f"[{k}:a]atempo={pl.get('tempo', 1.0)},aformat=sample_rates=48000:channel_layouts=stereo,volume={10 ** (pl.get('gain_db', 0) / 20):.3f},"
                  f"adelay={int(t_on * 1000)}|{int(t_on * 1000)}[p{k}]")
    mixin = chain + "".join(f"[p{k}]" for k in range(1, len(mine) + 1))
    fc.append(f"{mixin}amix=inputs={len(mine) + 1}:normalize=0:duration=first[aout]")
    vid = base + "_mixed.mp4"
    run(["ffmpeg", "-loglevel", "error", "-y", *ins, "-filter_complex", ";".join(fc), "-map", "0:v", "-map", "[aout]",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", os.path.join(ed, vid)], "后期配音")

words = os.path.join(ed, base + "_words.json")
if not FROM_SUBS:
    print(f"[{ep}] 转写词级时间戳…", flush=True)
    tmp = tempfile.mkdtemp()
    run([(__import__("shutil").which("whisper") or "/opt/homebrew/bin/whisper"), os.path.join(ed, base + ".mp4"), "--model", "small", "--language", "en", "--word_timestamps", "True",
         "--output_format", "json", "--output_dir", tmp, "--fp16", "False"], "转写")
    shutil.move(os.path.join(tmp, base + ".json"), words)

print(f"[{ep}] 字幕 / 铭牌 / 叠字…", flush=True)
out = run([sys.executable, "tools/subtitle_episode.py", ep, "--video", f"08_edit/{vid}", "--words", words, "--report", f"08_edit/{base}.json"], "字幕")
print(out.splitlines()[0], flush=True)

print(f"[{ep}] 片尾特效 + 片尾卡…", flush=True)
out = run([sys.executable, "tools/bumper_episode.py", ep, "--video", f"08_edit/{os.path.splitext(vid)[0]}_subs.mp4", "--report", f"08_edit/{base}.json",
           "--out", f"08_edit/{base}_final.mp4"], "片尾")
print(out.strip().splitlines()[-1], flush=True)
import re
m = re.search(r"闪光 ([\d.]+)s，定格 ([\d.]+)s，片尾卡 ([\d.]+)s", out)

# ---- 响度标准化（delivery.json loudnorm；E31 起 TikTok：-14 LUFS、真峰 ≤ -1 dBTP，两遍测量）----
sys.path.insert(0, HERE)
from delivery import profile
LN = profile(ep).get("loudnorm")
if LN:
    fin = os.path.join(ed, base + "_final.mp4"); tmpf = os.path.join(ed, base + "_final_ln.mp4")
    tgt = f"I={LN['I']}:TP={LN['TP']}:LRA={LN['LRA']}"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", fin, "-af", f"loudnorm={tgt}:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    js = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
    run(["ffmpeg", "-loglevel", "error", "-y", "-i", fin, "-af",
         f"loudnorm={tgt}:measured_I={js['input_i']}:measured_TP={js['input_tp']}:measured_LRA={js['input_lra']}:"
         f"measured_thresh={js['input_thresh']}:offset={js['target_offset']}:linear=true,aresample=48000,"
         f"alimiter=limit={10 ** ((LN['TP'] - 0.8) / 20):.4f}:attack=2:release=60:level=disabled",   # AAC 编码会让真峰反弹约 0.5 dB，先限到 TP-0.8
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", tmpf], "响度标准化")
    os.replace(tmpf, fin)
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", fin, "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    I = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr); P = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r.stderr)
    print(f"[{ep}] 响度标准化：{js['input_i']} LUFS / 峰值 {js['input_tp']} dB → {I[-1] if I else '?'} LUFS / 峰值 {P[-1] if P else '?'} dB", flush=True)

# ---- 检查图：每个叠字 / 铭牌 / 片尾各一帧 ----
final = os.path.join(ed, base + "_final.mp4")
seg = {s["id"]: s for s in rep["segments"]}
T = lambda sg, l: seg[sg]["t0"] + (l - seg[sg]["in"])
spots = []
tp = os.path.join(d, "titles.json")
if os.path.isfile(tp):
    for pl in json.load(open(tp, encoding="utf-8")).get("plates", []):
        if "seg" in pl: spots.append((f"铭牌 {pl['name']}", T(pl["seg"], (pl["l0"] + pl["l1"]) / 2)))
op = os.path.join(d, "overlays.json")
if os.path.isfile(op):
    for k, o in enumerate(json.load(open(op, encoding="utf-8"))["items"], 1):
        spots.append((f"叠字{k} Seg{o['seg']}", T(o["seg"], (o["l0"] + o["l1"]) / 2)))
if m:                                       # v5 复刻片尾：烧光闪 / 余光 / 定格 / 片尾卡
    fs, tz, c0 = map(float, m.groups())
    spots += [("烧光闪", fs + 0.06), ("余光", fs + 0.9), ("定格", tz + 0.4), ("片尾卡", c0 + 0.8)]
else:
    spots += [("片尾暗角", rep["video_end"] - 1.0), ("片尾卡", rep["video_end"] + 1.2)]
F = ImageFont.truetype("/System/Library/Fonts/STHeiti Medium.ttc", 18)
tiles = []
for lab, t in spots[:16]:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", final, "-ss", f"{t:.2f}", "-frames:v", "1", "-vf", "scale=288:512", "/tmp/_fe.png"], check=True)
    im = Image.open("/tmp/_fe.png").convert("RGB"); ImageDraw.Draw(im).text((6, 4), f"{lab} {t:.0f}s", font=F, fill=(0, 255, 255)); tiles.append(im)
cols = min(8, max(1, len(tiles))); rows = (len(tiles) + cols - 1) // cols
sh = Image.new("RGB", (288 * cols, 512 * rows), (10, 10, 10))
for i, t in enumerate(tiles): sh.paste(t, ((i % cols) * 288, (i // cols) * 512))
os.makedirs(os.path.join(PIPE, "review", "final_check"), exist_ok=True)
cp = os.path.join(PIPE, "review", "final_check", f"{ep}.jpg"); sh.save(cp, quality=86)
dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", final], capture_output=True, text=True).stdout)
print(f"[{ep}] 完成 → {os.path.relpath(final, PIPE)}（{dur:.1f}s）；检查图 {os.path.relpath(cp, PIPE)}", flush=True)
