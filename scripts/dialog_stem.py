#!/usr/bin/env python3
"""只留人声：用 Demucs（htdemucs，two-stems=vocals）把每段 H3 原声拆成"人声 / 其余"，丢掉 H3 自带的环境声与音乐，
把人声和原画面合成 <片名>_vc-dlg.mp4（assemble_episode.py 会优先用 *_vc-*.mp4 的声音）。环境声底、音效、配乐在拼接/后期统一铺。

为什么（2026-10-28，用户看 E01 粗剪）：每段 15 秒各自生成的背景声不一样，段缝处一段有背景、下一段没有，衔接生硬；
做法学自 HELL GRIND / ONEIRIC（生成只留安静底噪，声音在后期统一）和《越线》的 voice_fix（Demucs 分离对白）。

用法：python3 tools/dialog_stem.py E01 [E02 ...]   （处理 episodes/Exx/07_clips/segNN_accepted.mp4，已处理过的跳过；--force 重做）
同时写 episodes/Exx/06_jobs/ledger.jsonl 的 kept 记录（assemble_episode.py 按它取片）。
Demucs 环境：环境变量 DEMUCS_PY，默认用《越线》项目里已装好的 tools/voiceconv/.venv（不重复下载模型）。
"""
import argparse, glob, json, os, shutil, subprocess, sys, tempfile

PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMUCS_PY = os.environ.get("DEMUCS_PY", os.path.join(PIPE, "tools", "voiceconv", ".venv", "bin", "python"))


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def stem(clip, force):
    out = os.path.splitext(clip)[0] + "_vc-dlg.mp4"
    if os.path.exists(out) and not force:
        return out, "跳过"
    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "in.wav")
        run(["ffmpeg", "-loglevel", "error", "-y", "-i", clip, "-vn", "-ac", "2", "-ar", "44100", wav])
        r = run([DEMUCS_PY, "-m", "demucs.separate", "-n", "htdemucs", "--two-stems", "vocals", "-d", "cpu", "-o", td, wav])
        voc = glob.glob(os.path.join(td, "htdemucs", "*", "vocals.wav"))
        if not voc:
            raise SystemExit(f"Demucs 失败 {clip}：{r.stderr[-600:]}")
        # 人声轨：去掉 60 Hz 以下低频闷响；原画面直接复制
        r = run(["ffmpeg", "-loglevel", "error", "-y", "-i", clip, "-i", voc[0], "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                 "-af", "highpass=f=60", "-c:a", "aac", "-b:a", "192k", "-shortest", out])
        if r.returncode:
            raise SystemExit(f"合成失败 {clip}：{r.stderr[-400:]}")
    return out, "完成"


def ledger(ep_dir):
    """为 assemble_episode.py 写 kept 记录：每段取 segNN_accepted.mp4 指向的片子。"""
    rows = []
    for link in sorted(glob.glob(os.path.join(ep_dir, "07_clips", "seg??_accepted.mp4"))):
        n = int(os.path.basename(link)[3:5])
        real = os.path.realpath(link)
        rows.append({"seg": n, "outcome": "kept", "clip": os.path.relpath(real, ep_dir), "source": "comfy_run"})
    os.makedirs(os.path.join(ep_dir, "06_jobs"), exist_ok=True)
    with open(os.path.join(ep_dir, "06_jobs", "ledger.jsonl"), "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("episodes", nargs="+"); ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if not os.path.exists(DEMUCS_PY):
        sys.exit(f"找不到 Demucs 环境：{DEMUCS_PY}（设 DEMUCS_PY 指向装了 demucs 的 python）")
    for ep in a.episodes:
        d = os.path.join(PIPE, "episodes", ep)
        rows = ledger(d)
        for r in rows:
            out, st = stem(os.path.join(d, r["clip"]), a.force)
            print(f"{ep} Seg{r['seg']}：{st} → {os.path.relpath(out, PIPE)}", flush=True)
