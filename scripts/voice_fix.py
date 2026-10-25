#!/usr/bin/env python3
"""对白声线统一（后期，本地免费）：分离 → 变声 → 门限 → 回混 → 自动校验。

保留 H3 原片的表演、口型和环境声，只把指定说话人的音色换成「声线基准」。
用 tools/voiceconv/.venv 运行（含 demucs / soundfile / librosa）；变声调用 tools/voiceconv/seed-vc（Seed-VC，GPL-3.0）。

子命令：
  anchor  从某段已保留片子的对白轨里截一段，登记为角色的声线基准（voice_anchors/<角色>.wav + anchors.json）
      python tools/voice_fix.py anchor E01 --seg 2 --range 0-4.15 --character "Coach Draper" --note "用户确认 Seg2 声线正常"
  fix     把某段里某个说话人的对白变成基准音色，输出新音轨 + 换好声音的片子（不覆盖原片）
      python tools/voice_fix.py fix E01 --seg 3 --character "Coach Draper" [--range 0-8] [--clip 07_clips/...mp4]

校验（任何一项不过，结果标为 FAIL，片子仍然输出以便人工复听）：
  1. 静音污染：原对白轨无人声处，变声结果必须被门限压到 -60 dB 以下（Seed-VC 会在静音上凭空生成声音）
  2. 逐字：回混后的音轨用 Whisper 转写，与 02_dialogue_lock.json 中本段台词逐词比对
  3. 电平：变声对白与原对白的有声部分电平差 ≤ 1.5 dB
  4. 时长：输出与原片时长一致
"""
import argparse, difflib, glob, json, os, re, shutil, subprocess, sys

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.path.dirname(HERE)
VC_DIR = os.path.join(HERE, "voiceconv")
SEEDVC = os.path.join(VC_DIR, "seed-vc")
VENV_PY = os.path.join(VC_DIR, ".venv", "bin", "python")
ANCHOR_DIR = os.path.join(PIPE, "voice_anchors")
GATE_DB, GATE_PAD, GATE_SMOOTH = -48.0, 0.08, 0.04


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode:
        sys.exit(f"命令失败：{' '.join(map(str, cmd[:3]))} …\n{r.stderr[-1500:]}")
    return r


def ep_dir(ep):
    return os.path.join(PIPE, "episodes", ep)


def kept_clip(ep, n):
    """账本里该段最后一次 kept 的片子。"""
    rows = [json.loads(l) for l in open(os.path.join(ep_dir(ep), "06_jobs", "ledger.jsonl"), encoding="utf-8") if l.strip()]
    rows = [r for r in rows if r.get("seg") == n and r.get("outcome") == "kept"]
    if not rows:
        sys.exit(f"Seg{n} 在账本里没有 kept 记录；用 --clip 指定片子")
    return os.path.join(ep_dir(ep), rows[-1]["clip"])


def parse_range(s, dur):
    if not s:
        return 0.0, dur
    a, b = s.split("-")
    return float(a), float(b)


def separate(ep, n, clip):
    """demucs 两轨分离，结果缓存在 08_edit/vc/sep/<片名>/。"""
    work = os.path.join(ep_dir(ep), "08_edit", "vc")
    name = os.path.splitext(os.path.basename(clip))[0]
    out = os.path.join(work, "sep", name)
    if os.path.isfile(os.path.join(out, "vocals.wav")):
        return out
    os.makedirs(os.path.join(work, "src"), exist_ok=True)
    wav = os.path.join(work, "src", name + ".wav")
    run(["ffmpeg", "-loglevel", "error", "-y", "-i", clip, "-vn", "-ac", "2", "-ar", "44100", wav])
    tmp = os.path.join(work, "sep_tmp")
    run([os.path.join(VC_DIR, ".venv", "bin", "demucs"), "--two-stems=vocals", "-n", "htdemucs", "-d", "mps", "-o", tmp, wav])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    shutil.move(os.path.join(tmp, "htdemucs", name), out)
    shutil.rmtree(tmp, ignore_errors=True)
    return out


def mono(x):
    return x.mean(1) if x.ndim > 1 else x


def activity_mask(v, sr):
    from scipy.ndimage import maximum_filter1d, uniform_filter1d
    win = int(0.02 * sr); n = len(v) // win
    rms = np.sqrt((v[:n * win].reshape(n, win) ** 2).mean(1)) + 1e-9
    act = (20 * np.log10(rms) > GATE_DB).astype(float)
    act = maximum_filter1d(act, size=2 * int(GATE_PAD / 0.02) + 1)
    m = np.pad(np.repeat(act, win), (0, len(v) - n * win))
    return uniform_filter1d(m, size=int(GATE_SMOOTH * sr))


def db(x):
    return 20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-12) if len(x) else -200.0


def words(s):
    s = s.lower().replace("’", "'")
    return re.findall(r"[a-z0-9']+(?:\.[0-9]+)?", s)


def whisper_text(wav, tmpdir):
    os.makedirs(tmpdir, exist_ok=True)
    run(["whisper", wav, "--model", "small", "--language", "en", "--output_format", "txt", "--output_dir", tmpdir, "--fp16", "False"])
    return open(os.path.join(tmpdir, os.path.splitext(os.path.basename(wav))[0] + ".txt"), encoding="utf-8").read()


def seg_lines(ep, n):
    plan = json.load(open(os.path.join(ep_dir(ep), "plan.json"), encoding="utf-8"))
    lock = {x["id"]: x for x in json.load(open(os.path.join(ep_dir(ep), "02_dialogue_lock.json"), encoding="utf-8"))["lines"]}
    s = next(x for x in plan["segments"] if x["id"] == n)
    return [lock[sh["dialogue"]] for sh in s["shots"] if sh["dialogue"]]


def cmd_anchor(a):
    clip = a.clip and os.path.join(ep_dir(a.episode), a.clip) or kept_clip(a.episode, a.seg)
    sep = separate(a.episode, a.seg, clip)
    v, sr = sf.read(os.path.join(sep, "vocals.wav")); v = mono(v)
    t0, t1 = parse_range(a.range, len(v) / sr)
    piece = v[int(t0 * sr):int(t1 * sr)]
    os.makedirs(ANCHOR_DIR, exist_ok=True)
    key = a.character.replace(" ", "_").replace(".", "")
    out = os.path.join(ANCHOR_DIR, f"{key}.wav")
    sf.write(out, piece, sr, subtype="PCM_16")
    reg_p = os.path.join(ANCHOR_DIR, "anchors.json")
    reg = json.load(open(reg_p, encoding="utf-8")) if os.path.isfile(reg_p) else {}
    reg[a.character] = {"file": os.path.basename(out), "source_clip": os.path.relpath(clip, PIPE), "range": [t0, t1],
                        "dur_sec": round(len(piece) / sr, 2), "note": a.note}
    json.dump(reg, open(reg_p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    warn = "（短于 6 秒，Seed-VC 建议 6–20 秒；可以之后用更多已确认的台词追加）" if len(piece) / sr < 6 else ""
    print(f"声线基准 {a.character} → {os.path.relpath(out, PIPE)}，{len(piece)/sr:.2f}s{warn}")


def cmd_fix(a):
    ep = a.episode; n = a.seg
    reg = json.load(open(os.path.join(ANCHOR_DIR, "anchors.json"), encoding="utf-8"))
    if a.character not in reg:
        sys.exit(f"{a.character} 还没有声线基准，先运行 anchor")
    target = os.path.join(ANCHOR_DIR, reg[a.character]["file"])
    clip = a.clip and os.path.join(ep_dir(ep), a.clip) or kept_clip(ep, n)
    name = os.path.splitext(os.path.basename(clip))[0]
    sep = separate(ep, n, clip)
    work = os.path.join(ep_dir(ep), "08_edit", "vc", f"seg{n:02d}_{a.character.replace(' ', '_')}")
    os.makedirs(work, exist_ok=True)

    v, sr = sf.read(os.path.join(sep, "vocals.wav")); v = mono(v)
    bg, _ = sf.read(os.path.join(sep, "no_vocals.wav"))
    dur = len(v) / sr
    t0, t1 = parse_range(a.range, dur)
    src_wav = os.path.join(work, "source_vocals.wav")
    sf.write(src_wav, v, sr, subtype="PCM_16")

    # 变声（整条对白轨送入，之后只取指定区间）
    outdir = os.path.join(work, "seedvc")
    shutil.rmtree(outdir, ignore_errors=True)
    run([VENV_PY, os.path.join(VC_DIR, "run_vc.py"), "--source", src_wav, "--target", target, "--output", outdir,
         "--diffusion-steps", str(a.steps), "--fp16", "False"], cwd=SEEDVC)
    c, csr = sf.read(glob.glob(os.path.join(outdir, "*.wav"))[0]); c = mono(c)
    if csr != sr:
        import librosa
        c = librosa.resample(c, orig_sr=csr, target_sr=sr)
    c = np.pad(c, (0, max(0, len(v) - len(c))))[:len(v)]

    act = activity_mask(v, sr)
    rng = np.zeros(len(v)); rng[int(t0 * sr):int(t1 * sr)] = 1.0
    keep = act * rng                                   # 变声生效区域
    raw_leak = db(c[(act < 0.5) & (rng > 0.5)])        # 门限前：静音处 Seed-VC 生成了多少
    c = c * keep
    on = keep > 0.5
    gain = np.sqrt((v[on] ** 2).mean()) / (np.sqrt((c[on] ** 2).mean()) + 1e-12)
    c *= gain
    new_v = v * (1 - rng) + c                          # 区间外保留原对白（其他说话人不动）
    mix = np.clip(bg[:len(v)] + np.stack([new_v, new_v], 1), -0.98, 0.98)
    mix_wav = os.path.join(work, "mix.wav")
    sf.write(mix_wav, mix, sr, subtype="PCM_16")

    out_clip = os.path.join(ep_dir(ep), "07_clips", f"{name}_vc-{a.character.replace(' ', '_')}.mp4")
    run(["ffmpeg", "-loglevel", "error", "-y", "-i", clip, "-i", mix_wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-shortest", out_clip])

    # ---------- 校验 ----------
    checks = {}
    leak = db(c[(act < 0.5) & (rng > 0.5)])
    checks["静音污染"] = {"ok": bool(leak < -60), "门限前_dB": round(float(raw_leak), 1), "门限后_dB": round(float(leak), 1)}
    lvl = db(new_v[on]) - db(v[on])
    checks["电平差"] = {"ok": bool(abs(lvl) <= 1.5), "dB": round(float(lvl), 2)}
    d_out = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out_clip]).stdout)
    d_in = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", clip]).stdout)
    checks["时长"] = {"ok": bool(abs(d_out - d_in) < 0.1), "原片": round(d_in, 3), "输出": round(d_out, 3)}
    m16 = os.path.join(work, "mix16k.wav")
    run(["ffmpeg", "-loglevel", "error", "-y", "-i", mix_wav, "-ac", "1", "-ar", "16000", m16])
    heard = whisper_text(m16, os.path.join(work, "whisper"))
    expect = " ".join(L["text_en"] for L in seg_lines(ep, n))
    hw, ew = words(heard), words(expect)
    sm = difflib.SequenceMatcher(None, ew, hw)
    diffs = [f"{op}: {' '.join(ew[i1:i2])} → {' '.join(hw[j1:j2])}" for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal"]
    checks["逐字"] = {"ok": bool(sm.ratio() >= 0.95), "相似度": round(sm.ratio(), 3), "转写": heard.strip(), "差异": diffs}

    ok = all(x["ok"] for x in checks.values())
    report = {"episode": ep, "seg": n, "character": a.character, "target": os.path.relpath(target, PIPE), "range": [t0, t1],
              "source_clip": os.path.relpath(clip, PIPE), "output_clip": os.path.relpath(out_clip, PIPE),
              "seedvc_steps": a.steps, "gate": {"db": GATE_DB, "pad_s": GATE_PAD, "smooth_s": GATE_SMOOTH},
              "result": "PASS" if ok else "FAIL", "checks": checks}
    json.dump(report, open(os.path.join(work, "report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Seg{n} {a.character} → {os.path.relpath(out_clip, PIPE)}  【{report['result']}】")
    for k, v_ in checks.items():
        extra = {kk: vv for kk, vv in v_.items() if kk not in ("ok", "转写")}
        print(f"  {'✓' if v_['ok'] else '✗'} {k}：{extra}")
    print("  台词仍需人耳复听：音色是否自然、有无电子味。")


ap = argparse.ArgumentParser()
sp = ap.add_subparsers(dest="cmd", required=True)
p = sp.add_parser("anchor"); p.add_argument("episode"); p.add_argument("--seg", type=int, required=True)
p.add_argument("--range", required=True); p.add_argument("--character", required=True); p.add_argument("--clip"); p.add_argument("--note", default="")
p.set_defaults(f=cmd_anchor)
p = sp.add_parser("fix"); p.add_argument("episode"); p.add_argument("--seg", type=int, required=True)
p.add_argument("--character", required=True); p.add_argument("--range"); p.add_argument("--clip"); p.add_argument("--steps", type=int, default=30)
p.set_defaults(f=cmd_fix)
a = ap.parse_args(); a.f(a)
