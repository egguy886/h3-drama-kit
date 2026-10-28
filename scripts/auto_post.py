#!/usr/bin/env python3
"""每集出齐后自动后期（2026-10-28 用户定"全剧用这套"）：
  1. 每段把最新的成片链接为 segNN_accepted.mp4（已经手动指定过的不动，例如 E01 Seg3 的 r2）
  2. tools/dialog_stem.py：Demucs 只留人声，丢掉 H3 自带的环境声
  3. tools/assemble_episode.py：按场景铺连续环境底声、段头去起步帧、L-cut、同场景接色 → 08_edit/Exx_cut_v1.mp4
用法：python3 tools/auto_post.py E02-E10 [--tag r1] [--poll 60]   （一直等到范围内每集都处理完；已有 cut 的集跳过）
日志：auto_post.log
"""
import argparse, glob, os, re, subprocess, sys, time

PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(PIPE, "auto_post.log")


def say(m):
    line = f"{time.strftime('%m-%d %H:%M:%S')} {m}"
    print(line, flush=True); open(LOG, "a", encoding="utf-8").write(line + "\n")


def expand(spec):
    out = []
    for p in spec:
        m = re.fullmatch(r"E(\d+)-E?(\d+)", p.upper())
        out += [f"E{i:02d}" for i in range(int(m.group(1)), int(m.group(2)) + 1)] if m else [p.upper()]
    return out


def segs_of(ep):
    d = os.path.join(PIPE, "episodes", ep, "05_prompts")
    return sorted(int(re.search(r"seg(\d+)", f).group(1)) for f in os.listdir(d) if f.endswith(".meta.json")) if os.path.isdir(d) else []


def clip_for(ep, n, tag):
    c = [f for f in glob.glob(os.path.join(PIPE, "episodes", ep, "07_clips", f"{ep}_seg{n:02d}_*.mp4")) if "_vc-" not in f and f"_{tag}_" in os.path.basename(f)]
    return max(c, key=os.path.getmtime) if c else None


def ready(ep, tag):
    return bool(segs_of(ep)) and all(clip_for(ep, n, tag) for n in segs_of(ep))


def process(ep, tag):
    d = os.path.join(PIPE, "episodes", ep, "07_clips")
    for n in segs_of(ep):
        link = os.path.join(d, f"seg{n:02d}_accepted.mp4")
        if not os.path.islink(link) and not os.path.exists(link):
            os.symlink(os.path.basename(clip_for(ep, n, tag)), link)
    say(f"{ep} 出齐，开始只留人声")
    r = subprocess.run([sys.executable, os.path.join(PIPE, "tools", "dialog_stem.py"), ep], cwd=PIPE, capture_output=True, text=True)
    if r.returncode:
        say(f"{ep} 人声分离失败：{r.stdout[-300:]} {r.stderr[-300:]}"); return False
    out = f"08_edit/{ep}_cut_v1.mp4"
    r = subprocess.run([sys.executable, os.path.join(PIPE, "tools", "assemble_episode.py"), ep, "--out", out], cwd=PIPE, capture_output=True, text=True)
    if r.returncode:
        say(f"{ep} 拼接失败：{r.stdout[-300:]} {r.stderr[-300:]}"); return False
    line = next((l for l in r.stdout.splitlines() if l.startswith("→")), "")
    say(f"{ep} ✅ episodes/{ep}/{out.lstrip('→ ')} {line}")
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("episodes", nargs="+"); ap.add_argument("--tag", default="r1"); ap.add_argument("--poll", type=int, default=60)
    a = ap.parse_args()
    todo = [ep for ep in expand(a.episodes) if not glob.glob(os.path.join(PIPE, "episodes", ep, "08_edit", f"{ep}_cut_v*.mp4"))]
    say(f"自动后期开始：{todo}")
    while todo:
        for ep in list(todo):
            if ready(ep, a.tag):
                process(ep, a.tag); todo.remove(ep)
        if todo:
            time.sleep(a.poll)
    say("自动后期全部完成")
