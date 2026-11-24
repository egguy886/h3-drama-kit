#!/usr/bin/env python3
"""首尾帧防漂移微裁 + 贴图泄露质检 + 音频接缝柔化拼接门禁 (clip_qc_trim.py v3.3)：
融合《Hell Grind》戛纳实战后期剪辑律与 H3 实拍质检：
1. 逐帧扫描前 1.8 秒（0..43 帧）：检出三栏设定图泄露或静态母图闪现跳变，若跳变前无语音对白则自动裁至稳定帧；
2. 边缘防漂移智能微裁：AI 视频首尾最易出现构图微晃与收尾拖沓，在非语音安全区默认微裁段首 `0.12–0.25s` 与段尾 `0.20–0.35s`（若边缘检测到强人声则自动收缩至 `0.04s / 0.08s` 绝不切字）；
3. 零延迟唇音同步音频接缝柔化：每段首尾施加 `0.08s` 极短音频微淡入/淡出（`afade`），彻底消除 15s 节点底噪断层与咔哒声，同时保持 100% 逐帧唇音同步零漂移。
"""
import argparse, json, os, subprocess, tempfile
import numpy as np

FPS = 24
W, H = 192, 108


def decode_rgb(mp4, t0=0.0, dur=2.2):
    raw = subprocess.check_output([
        "ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", mp4,
        "-vf", f"fps={FPS},scale={W}:{H},format=rgb24", "-f", "rawvideo", "-"
    ])
    return np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3).astype(np.float32)


def audio_rms_window(mp4, t0, t1):
    dur = max(0.0, t1 - t0)
    if dur <= 0.04:
        return -99.0
    raw = subprocess.check_output([
        "ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", mp4,
        "-vn", "-f", "f32le", "-ac", "1", "-ar", "16000", "-"
    ])
    x = np.frombuffer(raw, np.float32)
    if len(x) == 0:
        return -99.0
    return float(20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9))


def is_turnaround_grey(frame):
    sat = frame.max(axis=2) - frame.min(axis=2)
    lum = frame.mean(axis=2)
    strip1 = (sat[:, int(W * 0.30):int(W * 0.38)] < 14) & (lum[:, int(W * 0.30):int(W * 0.38)] > 24) & (lum[:, int(W * 0.30):int(W * 0.38)] < 88)
    strip2 = (sat[:, int(W * 0.64):int(W * 0.72)] < 14) & (lum[:, int(W * 0.64):int(W * 0.72)] > 24) & (lum[:, int(W * 0.64):int(W * 0.72)] < 88)
    return float(strip1.mean()) > 0.65 and float(strip2.mean()) > 0.65


def smart_stitch_clips(clip_paths, out_mp4, width=1344, height=768):
    report = []
    trimmed_files = []
    tmp_dir = tempfile.mkdtemp(prefix="qc_trim_v33_")

    for idx, src in enumerate(clip_paths, 1):
        dur = float(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src
        ]).decode().strip())
        fr = decode_rgb(src, 0.0, min(2.0, dur))
        diffs = np.abs(fr[1:] - fr[:-1]).mean(axis=(1, 2, 3)) if len(fr) > 1 else np.array([])

        # Speech-safe edge-drift trim defaults (Hell Grind edge-drift rule adapted for H3)
        head_rms = audio_rms_window(src, 0.0, 0.25)
        tail_rms = audio_rms_window(src, max(0.0, dur - 0.35), dur)
        trim_in = 0.20 if head_rms < -22.0 else 0.04
        trim_out = round(dur - (0.30 if tail_rms < -22.0 else 0.08), 3)
        reason = "edge_drift_trimmed" if (trim_in >= 0.15 or (dur - trim_out) >= 0.25) else "speech_protected_edge"

        # 1) Turnaround studio sheet leak check across first 40 frames
        leak_frames = [i for i in range(min(40, len(fr))) if is_turnaround_grey(fr[i])]
        if leak_frames:
            cut_idx = max(leak_frames) + 2
            trim_in = max(trim_in, round(cut_idx / FPS, 3))
            reason = f"turnaround_leak_trimmed@{trim_in:.2f}s"
        else:
            # 2) Early hard reference-plate flash jump in [0.25s .. 1.45s]
            for j in range(5, min(35, len(diffs))):
                pre_motion = float(diffs[:j].mean()) if j > 0 else 0.0
                if diffs[j] > 26.0 and pre_motion < 5.2:
                    cand_t = round((j + 2) / FPS, 3)
                    if audio_rms_window(src, 0.0, cand_t) < -23.0:
                        trim_in = max(trim_in, cand_t)
                        reason = f"static_plate_flash_trimmed@{trim_in:.2f}s(jump={diffs[j]:.1f})"
                        break

        eff_dur = max(1.0, round(trim_out - trim_in, 3))
        fade_out_st = max(0.0, round(eff_dur - 0.08, 3))
        vf = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps={FPS}"
        af = f"afade=t=in:st=0:d=0.08,afade=t=out:st={fade_out_st:.3f}:d=0.08"
        dst = os.path.join(tmp_dir, f"seg{idx:02d}_clean.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-v", "error",
            "-ss", f"{trim_in:.3f}", "-t", f"{eff_dur:.3f}", "-i", src,
            "-vf", vf, "-af", af,
            "-c:v", "libx264", "-preset", "fast", "-crf", "16", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", dst
        ], check=True)
        trimmed_files.append(dst)
        report.append({
            "seg": idx, "src": os.path.basename(src),
            "trim_in": trim_in, "trim_out": trim_out, "eff_dur": eff_dur,
            "head_rms": round(head_rms, 1), "tail_rms": round(tail_rms, 1), "status": reason
        })
        print(f"  Seg{idx:02d}: in={trim_in:5.2f}s out={trim_out:5.2f}s ({eff_dur:5.2f}s) | {reason}")

    os.makedirs(os.path.dirname(os.path.abspath(out_mp4)), exist_ok=True)
    lst = os.path.join(tmp_dir, "concat.txt")
    with open(lst, "w", encoding="utf-8") as fh:
        for p in trimmed_files:
            fh.write(f"file '{p}'\n")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out_mp4], check=True)
    rep_path = os.path.splitext(out_mp4)[0] + "_qc_report.json"
    json.dump(report, open(rep_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[QC STITCH v3.3 DONE] {out_mp4} ({os.path.getsize(out_mp4)/1e6:.1f} MB) -> {rep_path}")
    return report


def inspect_and_stitch(clip_dir, ep, seg_ids, out_mp4):
    paths = [os.path.join(clip_dir, f"{ep}_Seg{s:02d}_768p.mp4") for s in seg_ids]
    return smart_stitch_clips(paths, out_mp4)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", default=None, help="Optional jobs.json path (for v3.x episodes)")
    a = ap.parse_args()
    pipe = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cdir = os.path.join(pipe, "episodes", a.episode, "07_clips")
    if a.jobs and os.path.exists(a.jobs):
        jobs = json.load(open(a.jobs, encoding="utf-8"))
        paths = [os.path.join(cdir, f"{j['job_id']}.mp4") for j in jobs]
        smart_stitch_clips(paths, a.out)
    else:
        plan = json.load(open(os.path.join(pipe, "episodes", a.episode.upper(), "plan.json"), encoding="utf-8"))
        sids = [s["id"] for s in plan["segments"]]
        inspect_and_stitch(os.path.join(pipe, "episodes", a.episode.upper(), "07_clips"), a.episode.upper(), sids, a.out)
