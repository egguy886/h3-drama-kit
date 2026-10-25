#!/usr/bin/env python3
"""整集声线统一：对每个对白段，用 Whisper 词级时间戳找出每个说话人的时间区间，再逐人调用 voice_fix.py fix。

用法：tools/voiceconv/.venv/bin/python tools/voice_fix_ep.py E01 [--segs 2 3 4 5 6] [--dry-run]
- 只处理声线基准（voice_anchors/anchors.json）里已有的角色；没有基准的说话人跳过并列出。
- 同一段有多个说话人时，按顺序链式处理（第二个人在第一个人的输出上继续），assemble 取最新的 *_vc-*.mp4。
- 区间 = 该说话人台词的首词起点 −0.15s 到末词终点 +0.25s；两人区间重叠时取两句之间空隙的中点。
"""
import argparse, difflib, glob, json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); PIPE = os.path.dirname(HERE)
ap = argparse.ArgumentParser()
ap.add_argument("episode"); ap.add_argument("--segs", type=int, nargs="*"); ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--steps", type=int, default=30)
a = ap.parse_args()
ep = os.path.join(PIPE, "episodes", a.episode)
plan = json.load(open(os.path.join(ep, "plan.json"), encoding="utf-8"))
lock = {l["id"]: l for l in json.load(open(os.path.join(ep, "02_dialogue_lock.json"), encoding="utf-8"))["lines"]}
anchors = json.load(open(os.path.join(PIPE, "voice_anchors", "anchors.json"), encoding="utf-8"))
rows = [json.loads(l) for l in open(os.path.join(ep, "06_jobs", "ledger.jsonl"), encoding="utf-8") if l.strip()]
WH = (__import__("shutil").which("whisper") or "/opt/homebrew/bin/whisper")


def tok(s):
    s = s.lower().replace("’", "'").replace("—", " ").replace("-", " ")
    s = re.sub(r"(\d+)\.(\d+)", r"\1 point \2", s)
    return re.sub(r"[^a-z0-9' ]", " ", s).replace("'", "").split()


def kept(n):
    k = [r for r in rows if r["seg"] == n and r["outcome"] == "kept"]
    return os.path.join(ep, k[-1]["clip"]) if k else None


for s in plan["segments"]:
    n = s["id"]
    if a.segs and n not in a.segs: continue
    ids = [sh["dialogue"] for sh in s["shots"] if sh.get("dialogue")]
    if not ids: continue
    clip = kept(n)
    stem = os.path.splitext(os.path.basename(clip))[0]
    cache = os.path.join(ep, "08_edit", "vc", "words", stem + ".json")        # 与 pick_anchors.py 共用缓存
    if not os.path.isfile(cache):
        tmp = tempfile.mkdtemp(); os.makedirs(os.path.dirname(cache), exist_ok=True)
        subprocess.run([WH, clip, "--model", "small", "--language", "en", "--word_timestamps", "True", "--output_format", "json",
                        "--output_dir", tmp, "--fp16", "False"], capture_output=True)
        os.replace(os.path.join(tmp, stem + ".json"), cache)
    js = json.load(open(cache, encoding="utf-8"))
    words = [(w["word"], w["start"], w["end"]) for sg in js["segments"] for w in sg.get("words", [])]
    hyp = []                                            # 每个转写词可能展开成多个归一化 token
    for w, st, en in words:
        for t in tok(w): hyp.append((t, st, en))
    exp = []; owner = []
    for i in ids:
        for t in tok(lock[i]["text_en"]): exp.append(t); owner.append(i)
    sm = difflib.SequenceMatcher(None, exp, [h[0] for h in hyp], autojunk=False)
    times = {i: [] for i in ids}
    for b in sm.get_matching_blocks():
        for k in range(b.size):
            h = hyp[b.b + k]; times[owner[b.a + k]].append((h[1], h[2]))
    spans = {}
    for i in ids:
        if not times[i]: print(f"Seg{n} {i}：没有对上转写，跳过"); continue
        spans[i] = (min(t[0] for t in times[i]), max(t[1] for t in times[i]))
    order = []                                          # 按说话顺序合并相邻同一说话人
    for i in ids:
        if i not in spans: continue
        sp = lock[i]["speaker"]
        if order and order[-1][0] == sp:
            order[-1][1] = min(order[-1][1], spans[i][0]); order[-1][2] = max(order[-1][2], spans[i][1])
        else:
            order.append([sp, spans[i][0], spans[i][1]])
    rng = []
    for k, (sp, t0, t1) in enumerate(order):
        lo = t0 - 0.15; hi = t1 + 0.25
        if k > 0: lo = max(lo, (order[k - 1][2] + t0) / 2)
        if k < len(order) - 1: hi = min(hi, (t1 + order[k + 1][1]) / 2)
        rng.append((sp, max(0.0, lo), hi))
    print(f"Seg{n}：" + "；".join(f"{sp} {lo:.2f}–{hi:.2f}s" for sp, lo, hi in rng), flush=True)
    cur = None
    for sp, lo, hi in rng:
        if sp not in anchors:
            print(f"  {sp} 没有声线基准，跳过"); continue
        if a.dry_run: continue
        cmd = [sys.executable, os.path.join(HERE, "voice_fix.py"), "fix", a.episode, "--seg", str(n), "--character", sp,
               "--range", f"{lo:.2f}-{hi:.2f}", "--steps", str(a.steps)]
        if cur: cmd += ["--clip", os.path.relpath(cur, ep)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        print(r.stdout.strip() or r.stderr.strip()[-400:], flush=True)
        m = re.search(r"→ (.+?\.mp4)", r.stdout)
        if m: cur = os.path.join(PIPE, m.group(1))
