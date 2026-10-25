#!/usr/bin/env python3
"""设备声后期配音：录音笔、终端、Board Relay 广播、录音、电话（本地 VoxCPM2，不调用 H3，不花钱）。

用法（用 VoxCPM 的虚拟环境运行；模型路径见 project.json 的 voxcpm_model 或环境变量 VOXCPM_MODEL）：
  .venv-voxcpm/bin/python tools/post_voice.py [--only E15-BR E16-BR] [--redesign]
  .venv-voxcpm/bin/python tools/post_voice.py --candidates "Pit Master" --n 3

台词与声线登记在 post_audio.json（台词逐字取自剧本）。
- 声音资产角色：用 voices.json 里该角色的 master（母版 48k 音频）+ ref_text（母版里说的话）续写式克隆。
- 设计声（designed_voices）：先按描述生成一条基准声 voice_anchors/designed/<名字>.wav（固定 seed），
  之后每句都克隆这条基准，保证同一个声音前后一致。改描述或加 --redesign 才会重做基准。
输出：episodes/Exx/08_edit/post_audio/<id>_dry.wav（干声）和 <id>.wav（加设备音色），日志 post_audio_log.jsonl。
--candidates：按 voices.json prompt_voices 的描述生成 N 条候选声线（台词取该角色在台词锁定里的第一句），
  写到 voice_candidates/，供人试听选定后再升级为声音资产。
"""
import argparse, glob, json, os, subprocess, sys

ap = argparse.ArgumentParser()
ap.add_argument("--root", help="项目根（默认：tools/ 的上一级）")
ap.add_argument("--only", nargs="*")
ap.add_argument("--redesign", action="store_true")
ap.add_argument("--candidates"); ap.add_argument("--n", type=int, default=3)
ap.add_argument("--cfg", type=float, default=2.0); ap.add_argument("--steps", type=int, default=10)
ap.add_argument("--device", default="mps")
ap.add_argument("--seed", type=int, default=20261011, help="台词生成的随机种子（某句读错时换一个重出）")
a = ap.parse_args()

here = os.path.dirname(os.path.abspath(__file__)); pipe = os.path.dirname(here); root = os.path.abspath(a.root or pipe)
reg = json.load(open(os.path.join(pipe, "post_audio.json"), encoding="utf-8"))
_pj = os.path.join(pipe, "project.json")
PROJ = json.load(open(_pj, encoding="utf-8")) if os.path.isfile(_pj) else {}
vdir = os.path.join(root, PROJ.get("voice_dir", "assets/voices"))
VOICES = json.load(open(os.path.join(pipe, "voices.json"), encoding="utf-8")).get("voices", [])

FX = {  # ffmpeg 滤镜：设备音色
    "pa": "highpass=f=250,lowpass=f=4000,acompressor=threshold=-18dB:ratio=4:attack=5:release=80,aecho=0.8:0.6:45|90:0.22|0.12",
    "pa_stadium": "highpass=f=300,lowpass=f=3800,acompressor=threshold=-18dB:ratio=4:attack=5:release=80,aecho=0.8:0.75:140|300:0.35|0.22",
    "terminal": "asetrate=48000*0.94,aresample=48000,atempo=1.0638,highpass=f=140,lowpass=f=5200,acrusher=bits=10:mode=log:aa=1:mix=0.3,acompressor=threshold=-20dB:ratio=3",
    "recorder": "highpass=f=180,lowpass=f=3600,acompressor=threshold=-22dB:ratio=3",
    "phone": "highpass=f=320,lowpass=f=3300,acompressor=threshold=-20dB:ratio=6,acrusher=bits=12:mode=log:aa=1:mix=0.18",
    "tv": "highpass=f=200,lowpass=f=6000,acompressor=threshold=-20dB:ratio=3,aecho=0.6:0.3:25:0.12",   # 墙上电视直播（E44）
    "vo": "acompressor=threshold=-22dB:ratio=2,aecho=0.5:0.25:60:0.1",   # 内心独白式画外音（E46）
    "crowd": "highpass=f=150,lowpass=f=6500,acompressor=threshold=-16dB:ratio=3,aecho=0.8:0.55:70|160:0.25|0.15",   # 人群中远处的一声喊（E35 起）
}
HISS = {"recorder": 0.006, "phone": 0.003}


def pick_voice(character):
    """voices.json 里该角色的 master（相对 voice_dir 或项目根）+ ref_text。"""
    v = next((x for x in VOICES if x.get("character") == character), None)
    if not v or not v.get("master") or not v.get("ref_text"):
        sys.exit(f"voices.json 里 {character} 缺 master（母版音频）或 ref_text（母版里说的原话）")
    for base in (vdir, root):
        p = os.path.join(base, v["master"])
        if os.path.isfile(p):
            return p, v["ref_text"], os.path.basename(p)
    sys.exit(f"找不到 {character} 的母版音频：{v['master']}")


def apply_fx(dry, wet, fx):
    if fx in HISS:
        cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", dry, "-filter_complex",
               f"[0:a]{FX[fx]}[v];anoisesrc=color=pink:amplitude={HISS[fx]}:sample_rate=48000[n];[v][n]amix=inputs=2:duration=first:normalize=0[o]",
               "-map", "[o]", "-ar", "48000", "-ac", "1", wet]
    else:
        cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", dry, "-af", FX[fx], "-ar", "48000", "-ac", "1", wet]
    subprocess.run(cmd, check=True)


import soundfile as sf
from voxcpm import VoxCPM

model_path = os.environ.get("VOXCPM_MODEL") or os.path.join(root, PROJ.get("voxcpm_model", "models/VoxCPM2"))
print(f"加载 VoxCPM2（{a.device}）…", flush=True)
model = VoxCPM.from_pretrained(model_path, load_denoiser=False, optimize=False, device=a.device)
sr = int(model.tts_model.sample_rate)


def gen(text, seed, ref=None, prompt=None):
    kw = dict(text=text, cfg_value=a.cfg, inference_timesteps=a.steps, seed=seed, denoise=False)
    if ref: kw["reference_wav_path"] = ref
    if prompt: kw["prompt_wav_path"], kw["prompt_text"] = prompt
    return model.generate(**kw)


if a.candidates:
    voices = json.load(open(os.path.join(pipe, "voices.json"), encoding="utf-8"))
    pv = next(v for v in voices["prompt_voices"] if v["character"] == a.candidates)
    line = None
    for p in sorted(glob.glob(os.path.join(pipe, "episodes", "E*", "02_dialogue_lock.json"))):
        for L in json.load(open(p, encoding="utf-8"))["lines"]:
            if L["speaker"] == a.candidates: line = L; break
        if line: break
    out = os.path.join(pipe, "voice_candidates"); os.makedirs(out, exist_ok=True)
    tag = a.candidates.replace(" ", "")
    for k in range(1, a.n + 1):
        seed = 8000 + k
        wav = gen(f"({pv['control_prompt']}){line['text_en']}", seed)
        p = os.path.join(out, f"{tag}_cand{k}_seed{seed}.wav"); sf.write(p, wav, sr, subtype="PCM_16")
        print(f"候选 {k}：{os.path.relpath(p, pipe)}（{len(wav)/sr:.1f}s，台词 {line['id']}）", flush=True)
    sys.exit(0)

anc_dir = os.path.join(pipe, "voice_anchors", "designed"); os.makedirs(anc_dir, exist_ok=True)
anchors = {}
for name, d in reg["designed_voices"].items():
    p = os.path.join(anc_dir, name.replace(" ", "_") + ".wav")
    meta = p[:-4] + ".json"
    old = json.load(open(meta, encoding="utf-8")) if os.path.isfile(meta) else None
    if a.redesign or old is None or old.get("design") != d["design"] or not os.path.isfile(p):
        print(f"设计基准声：{name}", flush=True)
        wav = gen(f"({d['design']}){d['anchor_text']}", d["seed"])
        sf.write(p, wav, sr, subtype="PCM_16")
        json.dump({"design": d["design"], "anchor_text": d["anchor_text"], "seed": d["seed"]}, open(meta, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    anchors[name] = (p, d["anchor_text"])

for L in reg["lines"]:
    if a.only and L["id"] not in a.only: continue
    out = os.path.join(pipe, "episodes", L["episode"], "08_edit", "post_audio"); os.makedirs(out, exist_ok=True)
    if L["voice"] in anchors:
        ref, txt = anchors[L["voice"]]; src = os.path.basename(ref)
    else:
        ref, txt, src = pick_voice(L["voice"])
    wav = gen(L.get("tts_text") or L["text"], a.seed, ref=ref, prompt=(ref, txt))   # tts_text：只改合成用的拼写，台词原文（text）不动
    dry = os.path.join(out, f"{L['id']}_dry.wav"); wet = os.path.join(out, f"{L['id']}.wav")
    sf.write(dry, wav, sr, subtype="PCM_16"); apply_fx(dry, wet, L["fx"])
    rec = {"id": L["id"], "seed": a.seed, "voice": L["voice"], "ref": src, "fx": L["fx"], "dur": round(len(wav) / sr, 2), "text": L["text"]}
    open(os.path.join(out, "post_audio_log.jsonl"), "a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"{L['id']} {L['voice']} ← {src}  {rec['dur']}s → {os.path.relpath(wet, pipe)}", flush=True)
