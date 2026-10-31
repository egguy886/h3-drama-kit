#!/usr/bin/env python3
"""按质检账本把每段的 segNN_accepted 切到最佳成片，然后重做人声分离并另拼新版 cut（不覆盖旧版）。
用法：python3 tools/accept_best.py E11:1 E11:9 E13:6 ...   （段列表）
      python3 tools/accept_best.py --all E11-E20            （整批：每段都取账本最佳）
只改"账本里有记录且最佳版本与当前链接不同"的段；没有变化的集不重拼。
"""
import argparse, glob, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qc_lib as Q

PIPE = Q.PIPE


def eps(spec):
    out = []
    for p in spec:
        m = re.fullmatch(r"E(\d+)-E?(\d+)", p.upper())
        out += [f"E{i:02d}" for i in range(int(m.group(1)), int(m.group(2)) + 1)] if m else [p.upper()]
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("items", nargs="+"); ap.add_argument("--all", action="store_true"); ap.add_argument("--no-rebuild", action="store_true"); ap.add_argument("--tag", help="只在这一轮返工的成片里挑（画面返工用）")
    a = ap.parse_args()
    todo = []
    if a.all:
        for ep in eps(a.items):
            d = os.path.join(PIPE, "episodes", ep, "05_prompts")
            for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
                m = re.match(r"seg(\d+)\.meta\.json", f)
                if m: todo.append((ep, int(m.group(1))))
    else:
        todo = [(x.split(":")[0].upper(), int(x.split(":")[1])) for x in a.items]
    changed = {}
    for ep, n in todo:
        best = Q.best_clip(ep, n, a.tag)
        if not best: continue
        link = os.path.join(PIPE, "episodes", ep, "07_clips", f"seg{n:02d}_accepted.mp4")
        cur = os.path.realpath(link) if os.path.exists(link) else None
        if cur == os.path.realpath(best): continue
        os.symlink(os.path.basename(best), link + ".tmp"); os.replace(link + ".tmp", link)
        changed.setdefault(ep, []).append(n)
        print(f"{ep} Seg{n} → {os.path.basename(best)}", flush=True)
    if a.no_rebuild: sys.exit(0)
    for ep in changed:
        r = subprocess.run([sys.executable, os.path.join(PIPE, "tools", "dialog_stem.py"), ep], cwd=PIPE, capture_output=True, text=True)
        v = 1 + max([int(re.search(r"_cut_v(\d+)", f).group(1)) for f in glob.glob(os.path.join(PIPE, "episodes", ep, "08_edit", f"{ep}_cut_v*.mp4"))] or [0])
        out = f"08_edit/{ep}_cut_v{v}.mp4"
        r = subprocess.run([sys.executable, os.path.join(PIPE, "tools", "assemble_episode.py"), ep, "--out", out], cwd=PIPE, capture_output=True, text=True)
        print(f"{ep} 重拼 → {out} {'✅' if r.returncode == 0 else '❌ ' + r.stdout[-200:] + r.stderr[-200:]}", flush=True)
