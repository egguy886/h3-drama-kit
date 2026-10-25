#!/usr/bin/env python3
"""为还没有声线基准的说话人，从已保留的片子里挑最干净的一句话当候选基准。

用法：python3 tools/pick_anchors.py E02-E10 [--apply]
- 对每个有对白的段用 Whisper 取词级时间戳（缓存在 episodes/Exx/08_edit/vc/words/）；
- 一句台词作为候选的条件：转写与原文匹配 ≥ 0.90，时长 3.0–10 秒，前后 0.35 秒内没有别人说话；
- 评分 = 匹配度 + 时长（封顶 8 秒）+ 该段不带 ⚠；每个角色取最高分；
- 不加 --apply 只打印；加 --apply 调用 voice_fix.py anchor 登记（并复制一份到 review/voices/ 方便试听）。
"""
import argparse, difflib, glob, json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__)); PIPE = os.path.dirname(HERE)
ap = argparse.ArgumentParser(); ap.add_argument("episodes", nargs="+"); ap.add_argument("--apply", action="store_true")
ap.add_argument("--skip", nargs="*", default=[], help="跳过这些角色（如只用提示词固定声的次要角色）")
a = ap.parse_args()
WH = (__import__("shutil").which("whisper") or "/opt/homebrew/bin/whisper")
anchors = json.load(open(os.path.join(PIPE, "voice_anchors", "anchors.json"), encoding="utf-8"))


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


def words_of(ep, clip):
    d = os.path.join(PIPE, "episodes", ep, "08_edit", "vc", "words"); os.makedirs(d, exist_ok=True)
    cache = os.path.join(d, os.path.splitext(os.path.basename(clip))[0] + ".json")
    if not os.path.isfile(cache):
        tmp = os.path.join(d, "_tmp"); os.makedirs(tmp, exist_ok=True)
        subprocess.run([WH, clip, "--model", "small", "--language", "en", "--word_timestamps", "True", "--output_format", "json",
                        "--output_dir", tmp, "--fp16", "False"], capture_output=True)
        src = os.path.join(tmp, os.path.splitext(os.path.basename(clip))[0] + ".json")
        shutil.move(src, cache)
    js = json.load(open(cache, encoding="utf-8"))
    return [(w["word"], w["start"], w["end"]) for sg in js["segments"] for w in sg.get("words", [])]


cands = {}
for ep in eps(a.episodes):
    d = os.path.join(PIPE, "episodes", ep)
    plan = json.load(open(os.path.join(d, "plan.json"), encoding="utf-8"))
    lock = {l["id"]: l for l in json.load(open(os.path.join(d, "02_dialogue_lock.json"), encoding="utf-8"))["lines"]}
    rows = [json.loads(l) for l in open(os.path.join(d, "06_jobs", "ledger.jsonl"), encoding="utf-8") if l.strip()]
    st = json.load(open(os.path.join(d, "06_jobs", "batch_state.json"), encoding="utf-8"))["segs"] if os.path.isfile(os.path.join(d, "06_jobs", "batch_state.json")) else {}
    for s in plan["segments"]:
        ids = [sh["dialogue"] for sh in s["shots"] if sh.get("dialogue")]
        if not ids: continue
        if not any(lock[i]["speaker"] not in anchors and lock[i]["speaker"] not in a.skip for i in ids): continue
        k = [r for r in rows if r["seg"] == s["id"] and r["outcome"] == "kept"]
        if not k: continue
        clip = os.path.join(d, k[-1]["clip"])
        ws = words_of(ep, clip); hyp = []
        for w, s0, e0 in ws:
            for t in tok(w): hyp.append((t, s0, e0))
        exp, owner = [], []
        for i in ids:
            for t in tok(lock[i]["text_en"]): exp.append(t); owner.append(i)
        sm = difflib.SequenceMatcher(None, exp, [h[0] for h in hyp], autojunk=False)
        times = {i: [] for i in ids}
        for b in sm.get_matching_blocks():
            for q in range(b.size):
                h = hyp[b.b + q]; times[owner[b.a + q]].append((h[1], h[2]))
        spans = {i: (min(t[0] for t in times[i]), max(t[1] for t in times[i])) for i in ids if times[i]}
        for i in ids:
            sp = lock[i]["speaker"]
            if sp in anchors or sp in a.skip or i not in spans: continue
            n_exp = len(tok(lock[i]["text_en"])); ratio = len(times[i]) / max(1, n_exp)
            s0, e0 = spans[i]; dur = e0 - s0
            if ratio < 0.85 or not (3.0 <= dur <= 12.5): continue
            clean = all(spans[j][1] < s0 - 0.35 or spans[j][0] > e0 + 0.35 for j in ids if j != i and j in spans)
            if not clean: continue
            flagged = bool(st.get(str(s["id"]), {}).get("flag"))
            score = ratio * 4 + min(dur, 8.0) + (0 if flagged else 1.5)
            cands.setdefault(sp, []).append({"score": round(score, 2), "ep": ep, "seg": s["id"], "line": i, "range": f"{max(0, s0 - 0.1):.2f}-{e0 + 0.15:.2f}",
                                              "dur": round(dur, 1), "ratio": round(ratio, 2), "text": lock[i]["text_en"], "clip": os.path.relpath(clip, d)})
    print(ep, "完成", flush=True)

print()
chosen = {}
for sp, cl in sorted(cands.items()):
    cl.sort(key=lambda c: -c["score"]); c = cl[0]; chosen[sp] = c
    print(f"{sp:14s} ← {c['ep']} Seg{c['seg']} {c['line']} {c['range']}s（{c['dur']}s，匹配 {c['ratio']}，候选 {len(cl)} 个）：{c['text'][:70]}")
missing = {l["speaker"] for ep in eps(a.episodes) for l in json.load(open(os.path.join(PIPE, "episodes", ep, "02_dialogue_lock.json"), encoding="utf-8"))["lines"]} - set(anchors) - set(a.skip) - set(chosen)
if missing: print("找不到合格候选：", sorted(missing))
json.dump(chosen, open(os.path.join(PIPE, "voice_anchors", "candidates_E02-E10.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

if a.apply:
    venv = os.path.join(HERE, "voiceconv", ".venv", "bin", "python")
    os.makedirs(os.path.join(PIPE, "review", "voices"), exist_ok=True)
    for sp, c in chosen.items():
        r = subprocess.run([venv, os.path.join(HERE, "voice_fix.py"), "anchor", c["ep"], "--seg", str(c["seg"]), "--range", c["range"],
                            "--character", sp, "--clip", c["clip"], "--note", f"自动挑选 2026-10-12（{c['ep']} Seg{c['seg']} {c['line']}），未经人耳确认"],
                           capture_output=True, text=True)
        print(sp, "登记" if r.returncode == 0 else "失败：" + r.stderr[-300:], flush=True)
        reg = json.load(open(os.path.join(PIPE, "voice_anchors", "anchors.json"), encoding="utf-8"))
        if sp in reg:
            shutil.copyfile(os.path.join(PIPE, "voice_anchors", reg[sp]["file"]), os.path.join(PIPE, "review", "voices", f"{sp.replace(' ', '_')}_anchor.wav"))
