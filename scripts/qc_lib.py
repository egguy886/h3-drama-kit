#!/usr/bin/env python3
"""单段自动质检（出片后立刻跑，坏段自动重出）——把"返工原因"变成机器能抓的规则。

为什么（2026-10-29 复盘）：E03–E13 事后看片才发现 4 段台词有硬伤（开头词丢了 / 结尾被吞 / 说到一半换了词）；
旧的 dialogue_check 只看整句相似度，数字写法（"5 000" vs "five thousand"）和人名听错（Sincere/Sinclair）又会误报，
所以真问题被淹在 ⚠ 里。这里改成：
  1. 数字统一成英文单词、人名等近音词按相似度并到原文词上，再比；
  2. 单独查「开头 3 词」「结尾 3 词」——硬伤几乎都出在开头或结尾；
  3. 同时查技术项：时长 15±0.7 s、有音频轨、画幅；
  4. 结果写 episodes/Exx/06_jobs/qc.jsonl，comfy_run batch 据此自动换种子重出，auto_post 据此挑最佳版本。

状态：PASS（可用） / WARN（个别词有差，听一下） / FAIL（硬伤，自动重出）。
"""
import difflib, glob, json, os, re, shutil, subprocess, tempfile, time

PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WH = shutil.which("whisper") or "/opt/homebrew/bin/whisper"

_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def _words(n):
    if n < 20: return [_ONES[n]]
    if n < 100: return [_TENS[n // 10]] + ([_ONES[n % 10]] if n % 10 else [])
    if n < 1000: return [_ONES[n // 100], "hundred"] + (_words(n % 100) if n % 100 else [])
    for div, name in ((10**9, "billion"), (10**6, "million"), (1000, "thousand")):
        if n >= div:
            return _words(n // div) + [name] + (_words(n % div) if n % div else [])
    return [str(n)]


def _num(n):
    if 1100 <= n <= 2099 and n % 100:                    # 1982 → nineteen eighty two（年份）
        return _words(n // 100) + _words(n % 100)
    return _words(n)


def tok(s):
    """文本 → 词序列：小写、去标点、数字转英文词、连字符拆开、数字间的 and 去掉。"""
    s = s.lower().replace("’", "'").replace("—", " ").replace("-", " ").replace("$", " ")
    s = re.sub(r"(\d) ?,(\d{3})", r"\1\2", s)
    s = re.sub(r"(?<=\d) (?=\d{3}\b)", "", s)            # "5 000" → 5000
    s = re.sub(r"(\d+)\.(\d+)", r"\1 point \2", s)
    s = re.sub(r"(\d+)%", r"\1 percent", s)
    s = re.sub(r"[^a-z0-9' ]", " ", s).replace("'", "")
    out = []
    for w in s.split():
        out += _num(int(w)) if w.isdigit() else [w]
    res = []
    for i, w in enumerate(out):                          # "eight hundred and twelve thousand" 的 and
        if w == "and" and res and res[-1] in set(_ONES) | set(_TENS) | {"hundred", "thousand", "million"} and i + 1 < len(out) and out[i + 1] in set(_ONES) | set(_TENS):
            continue
        res.append(w)
    return res


def _snap(hyp, ref):
    """把转写里和原文某个词近音/近形的词（Sincere→Sinclair、cane→kane）换成原文词，避免人名误报。"""
    vocab = set(ref)
    out = []
    for w in hyp:
        if w in vocab or len(w) < 4:
            out.append(w); continue
        c = difflib.get_close_matches(w, vocab, n=1, cutoff=0.72)
        out.append(c[0] if c else w)
    return out


def score_line(ref_text, hyp_text):
    """返回 dict：ratio（整句相似度）、head_ok、tail_ok、matched（命中的转写片段）。"""
    R, H0 = tok(ref_text), tok(hyp_text)
    if not R or not H0:
        return {"ratio": 0.0, "head_ok": False, "tail_ok": False, "matched": ""}
    H = _snap(H0, R)
    best, bw = 0.0, (0, 0)
    for w in range(max(1, len(R) - 4), len(R) + 5):
        for i in range(0, max(1, len(H) - w + 1)):
            r = difflib.SequenceMatcher(None, R, H[i:i + w]).ratio()
            if r > best: best, bw = r, (i, i + w)
    win = H[bw[0]:bw[1]]
    # 开头/结尾 3 词：按顺序对齐后，原文头/尾各 3 个词至少 2 个被转写覆盖（短句不查）。
    # 用有序匹配块而不是"出现过就算"：否则 "You staged the entire…" 丢了 "You staged" 会因为后文也有 you/the 而漏报。
    cov = set()
    for blk in difflib.SequenceMatcher(None, R, win).get_matching_blocks():
        cov.update(range(blk.a, blk.a + blk.size))
    def ends_ok(idx):
        if len(R) <= 4: return True
        return sum(1 for i in idx if i in cov) >= min(2, len(idx))
    head_ok = ends_ok(range(0, min(3, len(R))))
    tail_ok = ends_ok(range(max(0, len(R) - 3), len(R)))
    return {"ratio": round(best, 3), "head_ok": head_ok, "tail_ok": tail_ok, "matched": " ".join(win)}


def probe(clip):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration", "-of", "json", clip],
                       capture_output=True, text=True)
    try:
        j = json.loads(r.stdout)
        st = j.get("streams", [])
        return {"dur": float(j["format"]["duration"]), "audio": any(s["codec_type"] == "audio" for s in st),
                "size": next(((s["width"], s["height"]) for s in st if s["codec_type"] == "video"), None)}
    except Exception:
        return {"dur": 0.0, "audio": False, "size": None}


def transcribe(clip, model="small", words=True):
    """Whisper 转写。默认带 word_timestamps：实测普通模式会丢句首/句尾的词（E06 Seg8 "Lumen is my narrative internship"、
    E04 Seg5 "in his Bentley" 在普通转写里消失，逐词模式里都在），导致把好片误判成"开头丢词/结尾被吞"。"""
    with tempfile.TemporaryDirectory() as td:
        cmd = [WH, clip, "--model", model, "--language", "en", "--fp16", "False", "--output_dir", td,
               "--output_format", "json" if words else "txt"] + (["--word_timestamps", "True"] if words else [])
        subprocess.run(cmd, capture_output=True)
        base = os.path.splitext(os.path.basename(clip))[0]
        if words:
            p = os.path.join(td, base + ".json")
            if not os.path.isfile(p): return ""
            j = json.load(open(p, encoding="utf-8"))
            ws = [w["word"].strip() for sg in j.get("segments", []) for w in sg.get("words", [])]
            return " ".join(ws) if ws else j.get("text", "").strip()
        p = os.path.join(td, base + ".txt")
        return open(p, encoding="utf-8").read().strip() if os.path.isfile(p) else ""


def seg_lines(ep, seg):
    """该段要说的锁定台词 [(id, speaker, text)]。"""
    d = os.path.join(PIPE, "episodes", ep)
    plan = json.load(open(os.path.join(d, "plan.json"), encoding="utf-8"))
    lock = {l["id"]: l for l in json.load(open(os.path.join(d, "02_dialogue_lock.json"), encoding="utf-8"))["lines"]}
    for s in plan["segments"]:
        if s["id"] == seg:
            return [(sh["dialogue"], lock[sh["dialogue"]]["speaker"], lock[sh["dialogue"]]["text_en"]) for sh in s["shots"] if sh.get("dialogue")]
    return []


def _has_device_voice(ep, seg):
    """该段是否有"设备里的声音"（电话/外放/隔门喊话，台词已移到后期 post_audio）：这类段 H3 会自己说出一点对方的话，不算插词。"""
    d = os.path.join(PIPE, "episodes", ep)
    try:
        moved = json.load(open(os.path.join(d, "02_dialogue_lock.json"), encoding="utf-8")).get("post_audio_moved")
        if not moved: return False
        plan = json.load(open(os.path.join(d, "plan.json"), encoding="utf-8"))
        for sg in plan["segments"]:
            if sg["id"] == seg:
                txt = " ".join(sh["en"] for sh in sg["shots"]) + " " + sg.get("summary", "")
                return bool(re.search(r"\b(speaker|phone|call|voice|through the door)\b", txt, re.I))
    except Exception:
        return False
    return False


def qc_segment(ep, seg, clip, model="small"):
    """单段质检。返回 dict(status, score, issues, lines, tech)。"""
    tech = probe(clip)
    issues = []
    if not tech["audio"]: issues.append("无音频轨")
    if not (14.3 <= tech["dur"] <= 15.8): issues.append(f"时长 {tech['dur']:.2f}s 偏离 15 秒")
    if tech["size"] and tech["size"][0] > tech["size"][1]: issues.append("画幅是横屏")
    lines_out, worst = [], 1.0
    status = "PASS"
    hyp = ""
    lines = seg_lines(ep, seg)
    if lines and tech["audio"]:
        hyp = transcribe(clip, model)
        for lid, sp, text in lines:
            sc = score_line(text, hyp)
            lines_out.append({"id": lid, "speaker": sp, **sc})
            worst = min(worst, sc["ratio"])
            if sc["ratio"] < 0.72:
                issues.append(f"{lid}（{sp}）整句相似度 {sc['ratio']:.2f}"); status = "FAIL"
            elif (not sc["head_ok"] or not sc["tail_ok"]) and sc["ratio"] < 0.95:
                issues.append(f"{lid}（{sp}）{'开头词丢了' if not sc['head_ok'] else '结尾被吞'}（相似度 {sc['ratio']:.2f}）"); status = "FAIL"
            elif sc["ratio"] < 0.88 and status == "PASS":
                issues.append(f"{lid}（{sp}）个别词有差（{sc['ratio']:.2f}）"); status = "WARN"
    # 插词：转写词数明显多于该段台词总词数 → 模型在台词里塞了没写的话（E04/E06/E09 的"..."处）
    if lines and tech["audio"] and not _has_device_voice(ep, seg):
        total = sum(len(tok(t)) for _, _, t in lines)
        got = len(tok(hyp))
        if got > total * 1.15 + 2:
            issues.append(f"多说了词：转写 {got} 词，台词共 {total} 词（疑似在停顿处插入了台词之外的话）"); status = "FAIL"
    if any(i for i in issues if i.startswith(("无音频", "时长", "画幅"))): status = "FAIL"
    return {"status": status, "score": round(worst, 3), "issues": issues, "lines": lines_out, "tech": tech}


# ---- 账本：episodes/Exx/06_jobs/qc.jsonl（每次出片一行）----
def ledger_path(ep):
    return os.path.join(PIPE, "episodes", ep, "06_jobs", "qc.jsonl")


def ledger_read(ep):
    p = ledger_path(ep)
    return [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.isfile(p) else []


def ledger_add(ep, seg, clip, res, tag=""):
    os.makedirs(os.path.dirname(ledger_path(ep)), exist_ok=True)
    row = {"seg": seg, "clip": os.path.relpath(clip, os.path.join(PIPE, "episodes", ep)), "tag": tag, "status": res["status"], "score": res["score"],
           "issues": res["issues"], "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    open(ledger_path(ep), "a", encoding="utf-8").write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def attempts(ep, seg, tag):
    return [r for r in ledger_read(ep) if r["seg"] == seg and (r["tag"] == tag or r["tag"].startswith(tag + "x"))]


def best_clip(ep, seg):
    """账本里这一段的最佳成片（先取 PASS/WARN 里分最高的，全 FAIL 则取分最高的）；没有记录返回 None。"""
    rows = [r for r in ledger_read(ep) if r["seg"] == seg and os.path.isfile(os.path.join(PIPE, "episodes", ep, r["clip"]))]
    if not rows: return None
    rank = {"PASS": 2, "WARN": 1, "FAIL": 0}
    rows.sort(key=lambda r: (rank[r["status"]], r["score"], r["at"]))
    return os.path.join(PIPE, "episodes", ep, rows[-1]["clip"])
