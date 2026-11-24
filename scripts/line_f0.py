"""逐句音高：whisper 分句时间 → 对齐台词 → 截出该句 → numpy 自相关估 F0 中位数。
用法：python3 f0.py <clip> <ep> <seg>   或 import line_f0(clip, lines)"""
import json, os, subprocess, sys, tempfile
import numpy as np
PIPE = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, os.path.join(PIPE, "tools")); import qc_lib

_W = {}
def words(clip):
    if clip in _W: return _W[clip]
    d = tempfile.mkdtemp()
    subprocess.run(["whisper", clip, "--model", "small", "--language", "en", "--output_format", "json", "--word_timestamps", "True", "--output_dir", d, "--fp16", "False"], capture_output=True)
    j = json.load(open(os.path.join(d, os.path.splitext(os.path.basename(clip))[0] + ".json")))
    _W[clip] = [(w["start"], w["end"], w["word"]) for s in j["segments"] for w in s.get("words", [])]
    return _W[clip]

def segs(clip):
    W = words(clip); return [(W[0][0], W[-1][1], " ".join(w[2] for w in W))] if W else []

def span(clip, text):
    """台词在转写词序列里的最佳窗口 → (起, 止, 相似度)。"""
    W = words(clip); n = len(qc_lib.tok(text)); best = (None, None, 0)
    for w in range(max(1, n - 2), n + 3):
        for i in range(0, max(1, len(W) - w + 1)):
            r = qc_lib.score_line(text, " ".join(x[2] for x in W[i:i + w]))["ratio"]
            if r > best[2]: best = (W[i][0], W[min(i + w, len(W)) - 1][1], r)
    return best

def pcm(clip, t0, t1, sr=16000):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t0), "-to", str(t1), "-i", clip, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.float32), sr

def f0_median(x, sr, fmin=70, fmax=400):
    fr, hop = int(0.04 * sr), int(0.01 * sr); out = []
    rms_all = np.sqrt(np.mean(x ** 2)) + 1e-9
    for i in range(0, len(x) - fr, hop):
        w = x[i:i + fr] * np.hanning(fr)
        if np.sqrt(np.mean(w ** 2)) < 0.3 * rms_all: continue
        ac = np.correlate(w, w, "full")[fr - 1:]
        lo, hi = int(sr / fmax), int(sr / fmin)
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] / (ac[0] + 1e-9) > 0.45: out.append(sr / k)
    return (float(np.median(out)), len(out)) if out else (None, 0)

def line_f0(clip, lines):
    res = []
    for lid, sp, text in lines:
        t0, t1, r = span(clip, text)
        if t0 is None or r < 0.5: res.append((lid, sp, None, 0)); continue
        x, sr = pcm(clip, t0, t1); f, n = f0_median(x, sr); res.append((lid, sp, round(f, 1) if f else None, n, round(t0, 2), round(t1, 2)))
    return res

if __name__ == "__main__":
    clip, ep, seg = sys.argv[1], sys.argv[2], int(sys.argv[3])
    for r in line_f0(clip, qc_lib.seg_lines(ep, seg)): print(r)
