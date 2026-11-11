"""出片后的画面自动质检（macOS Vision，本地，不花钱）。qc_lib.qc_segment 会自动调用；也可单独跑：
    python3 tools/vision_qc.py E06 8 episodes/E06/07_clips/xxx.mp4
检查项（都是"换种子重出就能好"的随机毛病，FAIL 会触发自动重出）：
  V1 模型自带字幕：画面下半部 OCR 出的字和本段台词对上 ≥2 帧（E05 S8 / E06 S8 / E28 S6）
  V2 片头多出空镜：片段开头 0.3 秒后、第一镜计划结束前出现硬切（E04 S7 等 10 处，片头先给 0.7–1.6 秒空场景）
源码 tools/vqc.swift，编译：swiftc -O tools/vqc.swift -o tools/bin/vqc"""
import glob, json, os, re, shutil, subprocess, sys, tempfile
PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(PIPE, "tools", "bin", "vqc")


def _toks(s): return re.findall(r"[a-z']+", s.lower())


def _dialog(ep, seg):
    p = os.path.join(PIPE, "episodes", ep, "05_prompts", f"seg{seg:02d}.bilingual.md")
    return [_toks(x) for x in re.findall(r"<d>\[English\] (.*?)</d>", open(p, encoding="utf-8").read(), re.S)] if os.path.exists(p) else []


def _shot1(ep, seg):
    try:
        src = json.load(open(os.path.join(PIPE, "episodes", ep, "plan_src.json"), encoding="utf-8"))
        s = next(x for x in src["segments"] if str(x["id"]) == str(seg))
        return float(s["shots"][0]["dur"]), (s.get("transition") or {}).get("type")
    except Exception:
        return 0.0, None


def _prop_text(ep, seg):
    """本段挂的带字道具（props.json 的 image_text）里的词：画面上这张纸/屏幕本来就该有字，台词又恰好念到它时别当成字幕
    （E42 Seg3：她举着"SUPERVISORY RELATIONSHIP DISCLOSURE"表格说出表名，3 个种子全被判 V1）。"""
    try:
        src = json.load(open(os.path.join(PIPE, "episodes", ep, "plan_src.json"), encoding="utf-8"))
        s = next(x for x in src["segments"] if str(x["id"]) == str(seg))
        props = json.load(open(os.path.join(PIPE, "library", "props.json"), encoding="utf-8"))
        return set(_toks(" ".join(str(props.get(i, {}).get("image_text", "")) for i in s.get("props") or [])))
    except Exception:
        return set()


def subtitles(ep, seg, clip):
    lines = _dialog(ep, seg)
    on_prop = _prop_text(ep, seg)
    if not lines or not os.path.exists(BIN): return []
    td = tempfile.mkdtemp()
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", clip, "-vf", "fps=1,crop=iw:ih*0.45:0:ih*0.55,scale=720:-1", "-q:v", "4", f"{td}/%02d.jpg"])
        fs = sorted(glob.glob(f"{td}/*.jpg"))
        out = subprocess.run([BIN] + fs, capture_output=True, text=True).stdout
        hits = []
        for l in out.splitlines():
            d = json.loads(l); t = int(os.path.basename(d["f"])[:2]) - 1
            for x in d["t"]:
                w = _toks(x["s"])
                if on_prop and sum(any(q.startswith(t) for q in on_prop) for t in set(w)) >= max(2, 0.8 * len(set(w))): continue   # 字在道具上（参考图本来就有）
                for L in lines:
                    ov = len(set(w) & set(L))
                    if (len(w) >= 3 and ov >= max(2, 0.6 * len(w))) or (len(w) >= 2 and ov == len(w) and len(L) <= 6):
                        hits.append((t, x["s"])); break
        return [f"V1 画面里有模型自带字幕（{len(hits)} 帧，如 {hits[0][0]}s「{hits[0][1]}」）"] if len({h[0] for h in hits}) >= 2 else []
    finally:
        shutil.rmtree(td, ignore_errors=True)


def headcut(ep, seg, clip):
    d1, kind = _shot1(ep, seg)
    if d1 < 1.6: return []
    r = subprocess.run(["ffmpeg", "-t", str(min(d1, 2.4)), "-i", clip, "-vf", "select='gt(scene,0.30)',showinfo", "-f", "null", "-"], capture_output=True, text=True)
    ts = [float(x) for x in re.findall(r"pts_time:([\d.]+)", r.stderr)]
    ts = [t for t in ts if 0.3 < t < d1 - 0.5]
    return [f"V2 片头多了一个计划外镜头（{ts[0]:.1f}s 处硬切，第一镜本该 {d1:.1f}s）"] if ts else []


def check(ep, seg, clip):
    issues = []
    for f in (subtitles, headcut):
        try: issues += f(ep, seg, clip)
        except Exception as e: print("vision_qc", f.__name__, "跳过：", e)
    return issues


if __name__ == "__main__":
    print(check(sys.argv[1], int(sys.argv[2]), sys.argv[3]) or "OK")
