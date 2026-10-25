#!/usr/bin/env python3
"""用新阈值重新评估已保留段的 ⚠ 标记（只改 flag 字段，不动片子）。
必须在批量进程退出之后运行（否则会被进程内存里的状态覆盖）。
用法：python3 tools/batch_relabel.py [tag]   # 默认 768p-v1
"""
import glob, json, os, re, sys
PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PIPE, "tools"))
import h3_batch as B
tag = sys.argv[1] if len(sys.argv) > 1 else "768p-v1"
cleared = kept = 0
for p in sorted(glob.glob(os.path.join(PIPE, "episodes", "E*", "06_jobs", "batch_state.json"))):
    st = json.load(open(p, encoding="utf-8"))
    if st.get("tag") != tag: continue
    ch = False
    for k, r in st["segs"].items():
        if not r.get("flag"): continue
        remain = []
        for w in r["flag"].split("；"):
            m = re.search(r"（([\d.]+)）", w)
            v = float(m.group(1)) if m else None
            if w.startswith("首帧接不上") and v is not None and v <= B.GATE["first_diff_max"]: continue
            if w.startswith("片尾不稳") and v is not None and v <= B.GATE["tail_motion_max"]: continue
            remain.append(w)
        if remain:
            kept += 1
            if "；".join(remain) != r["flag"]: r["flag"] = "；".join(remain); ch = True
        else:
            r["flag_cleared"] = r.pop("flag"); cleared += 1; ch = True
    if ch: json.dump(st, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"⚠ 仍保留 {kept} 个，按新阈值清除 {cleared} 个")
