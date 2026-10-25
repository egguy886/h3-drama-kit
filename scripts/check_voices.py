#!/usr/bin/env python3
"""S3 说话人核对：剧本里每个开口的角色，是否在声音清单里有固定声线，或被明确允许使用临时声。

用法：python check_voices.py <剧本目录> <voices.json>
输出 Markdown 表格；有"缺失"说话人时退出码为 1。只用标准库。
"""
import glob
import json
import os
import re
import sys

scripts, vpath = sys.argv[1], sys.argv[2]
v = json.load(open(vpath, encoding="utf-8"))
fixed = {x["character"].lower(): x for x in v["voices"]}
prompt = {x["character"].lower(): x for x in v.get("prompt_voices", [])}
temp = {n.lower() for n in v.get("temp_voice_roles", [])}
bad = 0
print("| 集 | 说话人 | 句数 | 词数 | 声音 |\n|---|---|---|---|---|")
for f in sorted(glob.glob(os.path.join(scripts, "E*.md"))):
    ep = os.path.basename(f)[:3]
    lines = open(f, encoding="utf-8").read().split("\n")
    stats = {}
    for i, ln in enumerate(lines):
        m = re.match(r"^\*\*([A-Za-z][A-Za-z .]*)\*\*\s*$", ln)
        if not m:
            continue
        for nxt in lines[i + 1:i + 5]:
            q = re.match(r'^"(.*)"\s*$', nxt.strip())
            if q:
                s = stats.setdefault(m.group(1).strip(), [0, 0])
                s[0] += 1
                s[1] += len(q.group(1).split())
                break
    for name, (n, w) in stats.items():
        k = name.lower()
        if k in fixed:
            st = f"固定 {fixed[k]['voice_id']}（{fixed[k]['status']}）"
        elif k in prompt:
            st = f"提示词固定声（{prompt[k]['status']}）"
        elif k in temp:
            st = "临时声"
        else:
            st = "**缺失**"
            bad += 1
        print(f"| {ep} | {name} | {n} | {w} | {st} |")
sys.exit(1 if bad else 0)
