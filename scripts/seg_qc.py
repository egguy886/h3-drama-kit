#!/usr/bin/env python3
"""单段/整集质检（qc_lib 的命令行）。出片后马上看这一段有没有硬伤；comfy_run batch 默认自动调用，这里用来补查历史片或手工复核。
用法：
  python3 tools/seg_qc.py E04 --seg 5                 # 查 segNN_accepted（没有就查最新成片）
  python3 tools/seg_qc.py E03-E13                     # 整批补查，写 06_jobs/qc.jsonl，汇总到 review/质检_<范围>.md
  python3 tools/seg_qc.py E04 --seg 5 --clip episodes/E04/07_clips/xxx.mp4
"""
import argparse, glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qc_lib as Q


def eps(spec):
    out = []
    for p in spec:
        m = re.fullmatch(r"E(\d+)-E?(\d+)", p.upper())
        out += [f"E{i:02d}" for i in range(int(m.group(1)), int(m.group(2)) + 1)] if m else [p.upper()]
    return out


def segs_of(ep):
    d = os.path.join(Q.PIPE, "episodes", ep, "05_prompts")
    return sorted(int(re.search(r"seg(\d+)", f).group(1)) for f in os.listdir(d) if f.endswith(".meta.json")) if os.path.isdir(d) else []


def find_clip(ep, n):
    d = os.path.join(Q.PIPE, "episodes", ep, "07_clips")
    acc = os.path.join(d, f"seg{n:02d}_accepted.mp4")
    if os.path.exists(acc): return os.path.realpath(acc)
    c = [f for f in glob.glob(os.path.join(d, f"{ep}_seg{n:02d}_*.mp4")) if "_vc-" not in f]
    return max(c, key=os.path.getmtime) if c else None


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("episodes", nargs="+"); ap.add_argument("--seg", type=int, nargs="*"); ap.add_argument("--clip")
    ap.add_argument("--model", default="small"); ap.add_argument("--no-ledger", action="store_true")
    a = ap.parse_args()
    rows = []
    for ep in eps(a.episodes):
        for n in (a.seg or segs_of(ep)):
            clip = a.clip or find_clip(ep, n)
            if not clip: continue
            res = Q.qc_segment(ep, n, clip, a.model)
            if not a.no_ledger: Q.ledger_add(ep, n, clip, res, tag="qc")
            rows.append((ep, n, os.path.basename(clip), res))
            print(f"{ep} Seg{n}: {res['status']} {res['score']:.2f} {'; '.join(res['issues'])}", flush=True)
    name = f"{eps(a.episodes)[0]}-{eps(a.episodes)[-1]}"
    out = [f"# 单段质检 {name}", "", "| 集 | 段 | 状态 | 最低相似度 | 问题 | 文件 |", "|---|---|---|---|---|---|"]
    for ep, n, f, r in rows:
        out.append(f"| {ep} | Seg{n} | {r['status']} | {r['score']:.2f} | {'；'.join(r['issues']) or '—'} | {f} |")
    out += ["", f"合计 {len(rows)} 段：PASS {sum(r['status']=='PASS' for *_, r in rows)}，WARN {sum(r['status']=='WARN' for *_, r in rows)}，FAIL {sum(r['status']=='FAIL' for *_, r in rows)}"]
    os.makedirs(os.path.join(Q.PIPE, "review"), exist_ok=True)
    p = os.path.join(Q.PIPE, "review", f"质检_{name}.md"); open(p, "w", encoding="utf-8").write("\n".join(out) + "\n")
    print(out[-1], "→", p)
