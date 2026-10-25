#!/usr/bin/env python3
"""逐段台词核对：用本机 Whisper 转写保留片，和 02_dialogue_lock.json 的原文逐句对比。
用法：python3 tools/dialogue_check.py E01-E10 [--model small]
输出：review/台词核对_<范围>.md
"""
import argparse, difflib, glob, json, os, re, subprocess, sys, tempfile

ap = argparse.ArgumentParser()
ap.add_argument("episodes", nargs="+"); ap.add_argument("--model", default="small")
a = ap.parse_args()
PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WH = (__import__("shutil").which("whisper") or "/opt/homebrew/bin/whisper")


def eps(spec):
    out = []
    for p in spec:
        m = re.fullmatch(r"E(\d+)-E?(\d+)", p.upper())
        out += [f"E{i:02d}" for i in range(int(m.group(1)), int(m.group(2)) + 1)] if m else [p.upper()]
    return out


def tok(s):
    s = s.lower().replace("’", "'").replace("—", " ").replace("-", " ")
    s = re.sub(r"(\d+)\.(\d+)", r"\1 point \2", s)
    return re.sub(r"[^a-z0-9' ]", " ", s).replace("'", "").split()


def best(line, hyp):
    """在转写词序列里找和该句最像的窗口，返回 (相似度, 命中文本)"""
    L = tok(line)
    if not L or not hyp: return 0.0, ""
    bestr, bt = 0.0, ""
    for w in range(max(1, len(L) - 3), len(L) + 4):
        for i in range(0, max(1, len(hyp) - w + 1)):
            seg = hyp[i:i + w]
            r = difflib.SequenceMatcher(None, L, seg).ratio()
            if r > bestr: bestr, bt = r, " ".join(seg)
    return bestr, bt


rows = []; lines_out = []
tmp = tempfile.mkdtemp()
for ep in eps(a.episodes):
    d = os.path.join(PIPE, "episodes", ep)
    plan = json.load(open(os.path.join(d, "plan.json"), encoding="utf-8"))
    lock = {l["id"]: l for l in json.load(open(os.path.join(d, "02_dialogue_lock.json"), encoding="utf-8"))["lines"]}
    for s in plan["segments"]:
        ids = [sh["dialogue"] for sh in s["shots"] if sh.get("dialogue")]
        if not ids: continue
        clip = os.path.join(d, "07_clips", f"seg{s['id']:02d}_accepted.mp4")
        if not os.path.isfile(clip): continue
        subprocess.run([WH, clip, "--model", a.model, "--language", "en", "--output_format", "txt", "--output_dir", tmp, "--fp16", "False"],
                       capture_output=True)
        txtp = os.path.join(tmp, f"seg{s['id']:02d}_accepted.txt")
        hyp_raw = open(txtp, encoding="utf-8").read().strip() if os.path.isfile(txtp) else ""
        if os.path.isfile(txtp): os.remove(txtp)
        hyp = tok(hyp_raw)
        for i in ids:
            r, bt = best(lock[i]["text_en"], hyp)
            rows.append((ep, s["id"], i, lock[i]["speaker"], r, lock[i]["text_en"], bt, hyp_raw))
        print(ep, "Seg", s["id"], ids, flush=True)

name = "-".join([eps(a.episodes)[0], eps(a.episodes)[-1]])
out = [f"# 台词核对 {name}（本机 Whisper {a.model}，逐段转写 vs 锁定原文）", "",
       "相似度 ≥0.9 基本逐字一致；0.75–0.9 有个别词差（多半是转写误差，听一下确认）；<0.75 要重点听（漏词、改词、串台或没说）。",
       "", "| 集 | 段 | 台词 | 说话人 | 相似度 | 原文 | 转写命中 |", "|---|---|---|---|---|---|---|"]
for ep, sg, i, sp, r, ref, bt, raw in rows:
    flag = "✅" if r >= 0.9 else ("⚠️" if r >= 0.75 else "❌")
    out.append(f"| {ep} | Seg{sg} | {i} | {sp} | {flag} {r:.2f} | {ref} | {bt} |")
n = len(rows)
out += ["", f"合计 {n} 句：✅ {sum(r[4] >= .9 for r in rows)}，⚠️ {sum(.75 <= r[4] < .9 for r in rows)}，❌ {sum(r[4] < .75 for r in rows)}"]
p = os.path.join(PIPE, "review", f"台词核对_{name}.md")
open(p, "w", encoding="utf-8").write("\n".join(out) + "\n")
print(out[-1], "→", p)
