#!/usr/bin/env python3
"""轴线（越轴）检查：不用 Blender，直接读分镜文字里的画左/画右，找正反打方向矛盾。

规则：同一场景里 A 看向 B（B 在画外 frame-left），紧接着切到 B 看向 A 时，A 应在画外 frame-right；
若两个镜头写成同一个方向，观众会感觉两人在看向同一侧——越轴。
用法：python3 tools/axis_lint.py E02-E20        （只读，不改文件）
"""
import json, os, re, sys

PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cast = json.load(open(os.path.join(PIPE, "library", "cast.json"), encoding="utf-8"))
NAME = {}
for k, v in cast.items():
    if isinstance(v, dict) and v.get("name"):
        NAME["{%s}" % k] = v["name"]
ALIAS = {}                                    # 别名 → 名字：在 cast.json 条目里写 "aliases": ["Coach Draper", "the coach"]
for k, v in cast.items():
    if isinstance(v, dict) and v.get("name"):
        for al in v.get("aliases", []):
            ALIAS[al] = v["name"]
TOK = sorted({v["name"] for k, v in cast.items() if isinstance(v, dict) and v.get("name")}, key=len, reverse=True)
DIR = re.compile(r"(" + "|".join(re.escape(t) for t in TOK or ["Somebody"]) + r")\b[^.;,]{0,25}?off-camera at (?:upper |lower )?frame-(left|right)")


def norm(t):
    for k, v in NAME.items():
        t = t.replace(k, v)
    for k, v in ALIAS.items():
        t = t.replace(k, v)
    return t


def canon(s):
    for t in TOK:
        if t.split()[-1].lower() in s.lower():
            return t
    return s


def subject(t):
    best = None
    for tok in TOK:
        i = t.find(tok)
        if i >= 0 and (best is None or i < best[0]): best = (i, tok)
    return best[1] if best else None


def eps(spec):
    out = []
    for p in spec:
        m = re.fullmatch(r"E(\d+)-E?(\d+)", p.upper())
        out += [f"E{i:02d}" for i in range(int(m.group(1)), int(m.group(2)) + 1)] if m else [p.upper()]
    return out


hits = 0
for ep in eps(sys.argv[1:] or ["E02-E20"]):
    p = os.path.join(PIPE, "episodes", ep, "plan_src.json")
    if not os.path.isfile(p): continue
    d = json.load(open(p, encoding="utf-8"))
    for s in d["segments"]:
        prev = None   # (idx, subject, target, dir)
        for i, sh in enumerate(s["shots"], 1):
            t = norm(sh["en"])
            m = DIR.search(t)
            if not m: prev = None; continue
            subj, tgt, dr = subject(t), canon(m.group(1)), m.group(2)
            if subj and tgt and subj != tgt:
                if prev and prev[1] == tgt and prev[2] == subj and prev[3] == dr:
                    hits += 1
                    print(f"{ep} Seg{s['id']} 镜头{prev[0]}→{i}：{prev[1]} 与 {subj} 的视线都指向画外 frame-{dr}（正反打应相反）")
                prev = (i, subj, tgt, dr)
print(f"\n共发现 {hits} 处疑似越轴")

# ---- 第二项：跑步方向（全剧约定：选手一律从画左跑向画右）----
RUN = re.compile(r"sprint|\bruns?\b|running|explode[sd]? (?:off|out)|drives? off|surges?|bursts? across|crossing the line|driving (?:at|from)", re.I)
DIRW = re.compile(r"frame-left to frame-right|from frame-left|toward frame-right|towards frame-right|facing frame-right|finish[^.]{0,40}frame-right|frame-right[^.]{0,60}finish", re.I)
SKIP_STATIC_CLOSE = re.compile(r"close-up of (?:the )?(?:[A-Z][a-z]+'s) (?:face|hand|spikes)|face, his eyes|\bbreathing\b.*\bface\b", re.I)
missing = 0
for ep in eps(sys.argv[1:] or ["E02-E20"]):
    p = os.path.join(PIPE, "episodes", ep, "plan_src.json")
    if not os.path.isfile(p): continue
    d = json.load(open(p, encoding="utf-8"))
    for s in d["segments"]:
        for i, sh in enumerate(s["shots"], 1):
            t = norm(sh["en"])
            if RUN.search(t) and not DIRW.search(t) and not re.search(r"(?:head-on|from behind|toward the camera|trailing)", t):
                missing += 1
                print(f"{ep} Seg{s['id']} 镜头{i}：写了跑步但没写方向（应写 toward frame-right / from frame-left）：{sh['en'][:90]}")
print(f"\n跑步方向缺失 {missing} 处")
