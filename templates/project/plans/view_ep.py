#!/usr/bin/env python3
"""紧凑看一集：场景头、动作行、台词（带 Lk 与估时）。用法：python3 plans/view_ep.py 41"""
import glob, json, re, sys
n = sys.argv[1]
f = glob.glob(f"scripts_fixed/E{n}_*.md")[0]
lock = json.load(open(f"episodes/E{n}/02_dialogue_lock.json", encoding="utf-8"))["lines"]
txt = open(f, encoding="utf-8").read().split("---", 2)[-1]
q = iter(lock); cur = None; last = None; scr = False
for ln in txt.splitlines():
    ln = ln.strip()
    if ln.startswith("### 场"): print("\n" + ln); continue
    if ln.startswith("**核心道具") or ln.startswith("**出场") or ln.startswith("**造型") or "中文潜台词" in ln or not ln or ln.startswith("**【"): continue
    if ln.startswith("【"): scr = True; print(ln[:200]); continue
    if ln.startswith("△") or ln.startswith("**"): scr = False
    if ln.startswith("△") or ln.startswith("> ") or (scr and ln.startswith('"')): print(ln[:200]); continue
    if re.match(r"^\*\*[^*]+\*\*$", ln): cur = ln.strip("*"); cur = None if "(V.O.)" in cur or "(O.S.)" in cur else cur; continue
    if ln.startswith("（") and cur: last = ln[:40]; continue
    if ln.startswith('"') and cur:
        l = next(q); print(f"  {l['id']} {l['speaker']} {l['est_sec']}s {last or ''} \"{ln.strip(chr(34))}\""); last = None
