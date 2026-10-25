#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""h3_batch.py — 多集批量出片（在 h3_run.py 之上：按集顺序排队、空闲时段窗口、自动质检把关、断点续跑）

  python3 tools/h3_batch.py plan   E01-E20                                 # 列计划 + 费用估算（不花钱）
  python3 tools/h3_batch.py run    E01-E20 --dry-run                       # 构建请求，不发送
  python3 tools/h3_batch.py run    E01-E20 --window 00:00-08:00            # 只在空闲时段提交；现在不在窗口内就等到窗口开始
  python3 tools/h3_batch.py status E01-E20                                 # 看进度，写 BATCH_REPORT.md

调度：
- 一条链 = 一串 TAIL_RELAY 段，链内必须按顺序（下一段要用上一段尾帧）。每条链同一时刻最多 1 个任务在云端。
- 同时开跑的链数 = --parallel（默认 4）。链按「集号、链号」顺序启动，所以前面的集会先完整出完。
- 接口提示并发/限流（HTTP 429、"并发"、"concurrent"、"too many" 等）时，自动把并发数减 1（最低 1），不算重试。
- --window HH:MM-HH:MM：只在这个时段提交新任务（空闲时段 00:00–08:00 单价更低）。启动时不在窗口内就等待；
  窗口关闭前 --window-margin 分钟（默认 15）停止提交新任务，已提交的任务照常跑完；没出完的下次用同一个命令续批。

质检与保护：
- 每段下载后自动质检：画幅（768p竖=768×1344）、时长 15±0.6s、有音频；规划切点命中率；多余切点；接力段片尾稳定度；
  接续段首帧与上一段尾帧差异。通过 → 自动保留并抽尾帧，记为 auto_kept（待人工看片）；不通过 → 换 seed 重出，最多 --retries 次；
  仍不过：只有软指标（切点/片尾/首帧）不过 → 取分最高的一次继续，标注 ⚠ 需优先人工看；有硬伤（画幅/时长/音频）→ 该链停下（needs_review），其他链照常。
  自动质检只管技术和时间结构，表演、台词、逻辑仍要人看。阈值用 E01 v3.1 已接受的 8 段校准（7/8 通过，另一段是已知的提前切镜）。
- 先锋段 --canary（默认 2）：先只跑这几条链的第一段，全部合格才放行其余；不合格整批停止。
- 熔断 --max-errors（默认 6）：接口连续出错这么多次就停止提交。
- 可能已扣费的异常（提交时连接中断、等待超时）不会自动重提：任务记为 pending，下次运行先恢复下载再质检。
- 防休眠：macOS 上自动 caffeinate；笔记本请接电源、别合盖。
- 断点续跑：同一个 --tag 下已保留的段自动跳过。换新 tag 时，07_clips 里旧的保留片与尾帧先移到 07_clips/_pre_<tag>/，不覆盖。
- 状态：episodes/Exx/06_jobs/batch_state.json；汇总：BATCH_REPORT.md。
"""
import argparse, datetime, json, os, re, shutil, signal, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__)); PIPE = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import h3_run as H  # noqa: E402

GATE = {"cut_hit_min": 0.6, "extra_cuts_max": 2, "tail_motion_max": 15.0, "first_diff_max": 60.0}
# 2026-10-12 用 768p 首夜 120 个样本重新校准：首帧差中位 39（>30 的占 43%，景别被模型挪动是常态，目视同场景同人物），
# 只有 >60 的才是真断（如 E02 Seg7→8 差值 95）；片尾抖动中位 5，>15 占 5%。原阈值 30/10 来自 E01 v3.1 的 480p 旧片，偏紧。


# 2026-10-15：这几类是看得见的缺陷，值得花钱重出；切点命中/多余切点只是"和分镜的时间对不对"，重出的改善率只有 29%（E21–E30：45 次重出只有 13 次变好），改为只标 ⚠ 不重出。
RETRY_PAT = re.compile(r"技术参数|分辨率|首帧接不上|H3 自带字幕")   # 片尾不稳也去掉了：E31–E40 重出 4 次 0 次变好（多是火花/闪电本身在闪）


def is_hard(w):
    """硬伤：画幅/时长/音频。其余是软指标（切点、片尾、首帧承接）。"""
    return "技术参数" in w or "分辨率" in w
DIMS = {"768p竖": (768, 1344), "480p竖": (480, 864)}            # 实测规格
PRICE = {"768p竖": (0.040, 0.030), "480p竖": (0.030, 0.020)}     # 元/秒：(高峰 08–24, 空闲 00–08)，AutoDL 页面
THROTTLE = re.compile(r"429|并发|concurr|too many|rate.?limit|queue (?:is )?full|busy|限流|上限|超过.{0,6}(?:数量|个数)", re.I)
AMBIGUOUS = re.compile(r"提交时连接异常|等待超过|不要自动重试")
# 上传请求体途中被对方断开（服务器没收到完整请求，不会建任务）：可以退避后安全重试；读超时等"请求已发出、没拿到回应"仍按"可能已扣费"处理
SEND_FAIL = re.compile(r"Errno 32|Broken pipe|Errno 54|Errno 104|Connection reset", re.I)
MIN_FREE_GB = 2.5                                              # 低于这个可用空间就停止提交（每段约 11 MB，另有尾帧候选与对照图）
SLOCK = threading.Lock()
RT = {"stop": False, "why": "", "errs": 0, "throttled": 0, "window_closed": False}


# ------------------------------------------------------------------ 基础
def episodes(spec):
    out = []
    for part in spec:
        m = re.fullmatch(r"E(\d+)-E?(\d+)", part.upper())
        out += [f"E{i:02d}" for i in range(int(m.group(1)), int(m.group(2)) + 1)] if m else [part.upper()]
    return [e for e in out if os.path.isdir(os.path.join(PIPE, "episodes", e))]


def chains(ep_dir):
    """按真实依赖拆链：只有上一段 TAIL_RELAY 到下一段才算同一条链；硬切处断开（可并行）。"""
    out, cur, prev = [], [], None
    for n in H.all_segs(ep_dir):
        meta = H.load_meta(ep_dir, n)
        if cur and (prev or "").upper() != "TAIL_RELAY":
            out.append(cur); cur = []
        cur.append(n); prev = meta.get("connection_to_next")
    if cur: out.append(cur)
    names = {}
    res = []
    for segs in out:
        base = H.load_meta(ep_dir, segs[0]).get("chain") or "S"
        k = names.get(base, 0); names[base] = k + 1
        res.append((base if k == 0 else f"{base}{k + 1}", segs))
    return res


def is_relay_out(ep_dir, n):
    return (H.load_meta(ep_dir, n).get("connection_to_next") or "").upper() == "TAIL_RELAY"


def state_path(ep_dir):
    return os.path.join(ep_dir, "06_jobs", "batch_state.json")


def load_state(ep_dir, tag):
    p = state_path(ep_dir)
    st = json.load(open(p, encoding="utf-8")) if os.path.isfile(p) else {}
    if st.get("tag") != tag:
        st = {"tag": tag, "started": datetime.datetime.now().isoformat(timespec="seconds"), "segs": {}, "archived_old": False}
    return st


def save_state(ep_dir, st):
    with SLOCK:
        os.makedirs(os.path.dirname(state_path(ep_dir)), exist_ok=True)
        json.dump(st, open(state_path(ep_dir), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def archive_old(ep_dir, st):
    """换 tag 前，把旧的保留片和尾帧移走（不删除）。"""
    if st.get("archived_old"):
        return
    d = os.path.join(ep_dir, "07_clips")
    old = [f for f in (os.listdir(d) if os.path.isdir(d) else []) if re.match(r"seg\d\d_(accepted\.mp4|tail.*\.(png|json))$", f)]
    if old:
        dst = os.path.join(d, f"_pre_{st['tag']}")
        os.makedirs(dst, exist_ok=True)
        for f in old:
            shutil.move(os.path.join(d, f), os.path.join(dst, f))
        H.say(f"  {os.path.basename(ep_dir)}：旧的保留片/尾帧 {len(old)} 个已移到 07_clips/_pre_{st['tag']}/")
    st["archived_old"] = True
    save_state(ep_dir, st)


def done_status(rec):
    return rec.get("status") in ("auto_kept", "kept")


# ------------------------------------------------------------------ 窗口
def parse_window(s):
    m = re.fullmatch(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})", s or "")
    if not m: return None
    a, b, c, d = map(int, m.groups())
    return a * 60 + b, c * 60 + d


def window_open(now, w, margin=0):
    if w is None: return True
    s, e = w; m = now.hour * 60 + now.minute + now.second / 60
    if s <= e:
        return s <= m < e - margin
    return m >= s or m < e - margin


def next_open(now, w):
    s, _ = w
    go = now.replace(hour=s // 60, minute=s % 60, second=0, microsecond=0)
    return go if go > now else go + datetime.timedelta(days=1)


# ------------------------------------------------------------------ 质检
OCR_BIN = os.path.join(PIPE, "tools", "ocr", "ocr")


def caption_check(ep_dir, n, clip):
    """H3 自带字幕检测（LESSONS_E11-E20 D1，用 E01–E20 共 160 段校准）：
    A 画面下方居中的成行文字与本段台词重合 ≥2 个词（E11 Seg6 型）→ 软指标，触发重出；
    B 像句子的居中文字（2–9 词、句号/叹号/问号结尾）出现 ≥3 帧（E12 Seg5 乱码型）→ 只标 ⚠ 给人看，不重出（旧数据里一半是手机弹幕/文件误报）。
    返回 (A 原因或 None, B 原因或 None)。识别工具缺失时跳过。"""
    import tempfile, glob as _g
    src = OCR_BIN + ".swift"
    if not os.path.isfile(OCR_BIN) and os.path.isfile(src) and shutil.which("swiftc"):
        subprocess.run(["swiftc", "-O", src, "-o", OCR_BIN], capture_output=True)
    if not os.path.isfile(OCR_BIN): return None, None
    tmp = tempfile.mkdtemp()
    try:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-i", clip, "-vf", "fps=2,scale=432:-2", os.path.join(tmp, "%03d.png")], check=True)
        out = subprocess.run([OCR_BIN, tmp], capture_output=True, text=True, timeout=300).stdout
    except Exception:
        return None, None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    tok = lambda t: {w for w in re.sub(r"[^a-z' ]", " ", t.lower()).split() if len(w) > 2}
    plan = json.load(open(os.path.join(ep_dir, "plan.json"), encoding="utf-8"))
    lock = {l["id"]: l for l in json.load(open(os.path.join(ep_dir, "02_dialogue_lock.json"), encoding="utf-8"))["lines"]}
    seg = next(x for x in plan["segments"] if x["id"] == n)
    words = set().union(*[tok(lock[sh["dialogue"]]["text_en"]) for sh in seg["shots"] if sh.get("dialogue") in lock] or [set()])
    a_hits, b_frames = [], set()
    for ln in out.splitlines():
        try: r = json.loads(ln)
        except ValueError: continue
        if not (0.08 <= r["y"] <= 0.42 and 0.3 <= r["x"] + r["w"] / 2 <= 0.7 and r["w"] >= 0.2 and r["h"] <= 0.07): continue
        t = r["t"].strip()
        if len(tok(t) & words) >= 2: a_hits.append(t)
        if 2 <= len(t.split()) <= 9 and re.search(r"[.!?]$", t) and sum(c.isalpha() for c in t) / max(1, len(t)) > 0.6 and not re.search(r"[:/|\d]{2,}", t):
            b_frames.add(r["f"])
    A = f"画面里有 H3 自带字幕（{a_hits[0][:30]}）" if len(a_hits) >= 2 else None
    B = f"疑似 H3 自带字幕 {len(b_frames)} 帧" if len(b_frames) >= 3 else None
    return A, B


def gate(ep_dir, n, rv, info, resolution):
    why = []
    if not rv.get("tech_ok"): why.append("技术参数（画幅/时长/音频）不合格")
    h, t = (rv.get("cut_hits") or "0/0").split("/")
    if int(t) and int(h) / int(t) < GATE["cut_hit_min"]: why.append(f"切点命中 {h}/{t}")
    if len(rv.get("extra_cuts") or []) > GATE["extra_cuts_max"]: why.append(f"多余切点 {len(rv['extra_cuts'])} 个")
    if is_relay_out(ep_dir, n) and (rv.get("tail_motion") or 0) > GATE["tail_motion_max"]: why.append(f"片尾不稳（{rv['tail_motion']}）")
    if rv.get("first_frame_diff") is not None and rv["first_frame_diff"] > GATE["first_diff_max"]: why.append(f"首帧接不上（{rv['first_frame_diff']}）")
    want = DIMS.get(resolution)
    if want and (info.get("w"), info.get("h")) != want:
        why.append(f"分辨率 {info.get('w')}×{info.get('h')}，应为 {want[0]}×{want[1]}")
    return why


def pending_task(ep_dir, n):
    """已提交但没有下载完成的最新任务（可能已扣费，不能重复提交）。"""
    p = os.path.join(ep_dir, "06_jobs", "jobs.jsonl")
    if not os.path.isfile(p): return None
    last = {}
    for ln in open(p, encoding="utf-8").read().splitlines():
        try: j = json.loads(ln)
        except ValueError: continue
        if j.get("seg") == n and j.get("fmt") == "en": last[j["task_id"]] = j
    sub = [j for j in last.values() if j.get("state") == "submitted"]
    return sub[-1] if sub else None


# ------------------------------------------------------------------ 一条链
def run_chain(ctx, ep, ep_dir, chain, segs, a, st, win, limit=None):
    """返回 done / stopped / throttled / window / halt。"""
    for n in segs[:limit]:
        rec = st["segs"].get(str(n), {})
        if done_status(rec): continue
        tries = rec.get("tries", 0)
        while True:
            if RT["stop"]: return "halt"
            if tries > a.retries:
                soft = [x for x in rec.get("attempts", []) if not any(is_hard(w) for w in x["why"])]
                if soft:                                   # 只有软指标不过：挑分最高的一次继续，标注需优先人工看
                    b = max(soft, key=lambda x: x.get("score") or 0)
                    H.do_accept(ep_dir, n, os.path.join(ep_dir, b["clip"]), "en", b.get("seed"), b.get("version", ""), b.get("task_id"),
                                note=f"batch {st['tag']} 软指标未过，取分最高的一次：{'；'.join(b['why'])}")
                    rec.update(status="auto_kept", flag="；".join(b["why"]), last_clip=b["clip"], last_score=b.get("score"))
                    st["segs"][str(n)] = rec; save_state(ep_dir, st)
                    H.say(f"⚠ {ep} 链{chain} Seg{n}：{a.retries + 1} 次软指标都没过（{'；'.join(b['why'])}），取分最高的一次继续，标注为需优先人工看。")
                    break
                rec["status"] = "needs_review"; st["segs"][str(n)] = rec; save_state(ep_dir, st)
                H.say(f"■ {ep} 链{chain} Seg{n}：{a.retries + 1} 次都有硬伤（画幅/时长/音频），本链停下等人看。")
                return "stopped"
            r, err = None, None
            pend = pending_task(ep_dir, n)
            try:
                if pend:                                   # 先恢复上次没下完的任务，不重复提交
                    H.say(f"  {ep} Seg{n}：恢复未完成的任务 {pend['task_id']}（不重新提交）")
                    clip = H.wait_and_download(ctx, ep_dir, n, "en", pend["task_id"], pend.get("version", ""), pend.get("seed"), a.poll, a.timeout)
                    r = {"seg": n, "fmt": "en", "clip": clip, "seed": pend.get("seed"), "version": pend.get("version", ""), "task_id": pend["task_id"]}
                else:
                    if getattr(a, "recover_only", False):      # 只恢复未完成任务，不提交新的
                        return "done"
                    if not window_open(datetime.datetime.now(), win, a.window_margin):
                        RT["window_closed"] = True
                        return "window"
                    free_gb = shutil.disk_usage(PIPE).free / 1e9          # 磁盘空间保护（2026-10-15）：不足就不再提交新任务，已在途的照常收完
                    if free_gb < MIN_FREE_GB:
                        with SLOCK:
                            if not RT["stop"]:
                                RT.update(stop=True, why=f"磁盘可用空间只剩 {free_gb:.1f} GB（低于 {MIN_FREE_GB} GB），停止提交新任务")
                                H.say(f"■ {RT['why']}")
                        return "halt"
                    seed = H.new_seed(); tries += 1
                    r = H.run_one(ctx, ep_dir, n, "en", seed, a)
                with SLOCK: RT["errs"] = 0
            except Exception as e:
                err = str(e)
            if err:
                if SEND_FAIL.search(err) and not pending_task(ep_dir, n) and rec.get("send_retries", 0) < 2:
                    rec["send_retries"] = rec.get("send_retries", 0) + 1; tries -= 1
                    st["segs"][str(n)] = rec; save_state(ep_dir, st)
                    H.say(f"  ↺ {ep} Seg{n}：上传途中被断开（服务器没收到完整请求），45 秒后重试（第 {rec['send_retries']} 次）")
                    time.sleep(45); continue
                rec.update(tries=tries, last_error=err[:300]); st["segs"][str(n)] = rec; save_state(ep_dir, st)
                H.say(f"  ✗ {ep} Seg{n}：{err.splitlines()[0][:180]}")
                if AMBIGUOUS.search(err) or pending_task(ep_dir, n):
                    rec["status"] = "pending"; st["segs"][str(n)] = rec; save_state(ep_dir, st)
                    H.say(f"■ {ep} 链{chain} Seg{n}：任务可能已建立并扣费，不自动重提；下次运行会先恢复下载。")
                    with SLOCK: RT["errs"] += 1
                    return "stopped"
                if THROTTLE.search(err):
                    return "throttled"
                with SLOCK:
                    RT["errs"] += 1
                    if RT["errs"] >= a.max_errors:
                        RT.update(stop=True, why=f"接口连续出错 {RT['errs']} 次，熔断停止提交（最后一次：{err[:120]}）")
                        H.say("■ " + RT["why"])
                continue
            if r is None:                                  # dry-run
                rec.update(status="dry_run"); st["segs"][str(n)] = rec; save_state(ep_dir, st)
                return "done"
            try:
                rv = H.review_clip(ep_dir, n, r["clip"])
            except Exception as e:
                rv = {"tech_ok": True, "cut_hits": "0/0", "note": f"审片失败：{e}"}
            why = gate(ep_dir, n, rv, H.ffprobe(r["clip"]), a.resolution)
            cap_a, cap_b = caption_check(ep_dir, n, r["clip"])
            if cap_a: why.append(cap_a)
            if cap_b: rec["caption_flag"] = cap_b
            flag_only = [w for w in why if not RETRY_PAT.search(w)]            # 切点类：只标记
            why = [w for w in why if RETRY_PAT.search(w)]
            if flag_only: rec["gate_flag"] = "；".join(flag_only)
            else: rec.pop("gate_flag", None)
            rec.update(tries=tries, last_clip=os.path.relpath(r["clip"], ep_dir), last_score=rv.get("score"), last_gate=why, seed=r.get("seed"),
                       task_id=r["task_id"], resolution=a.resolution)
            rec.pop("last_error", None)
            if not why:
                H.do_accept(ep_dir, n, r["clip"], "en", r.get("seed"), r["version"], r["task_id"], note=f"batch {st['tag']} 自动质检通过，待人工看片")
                rec["status"] = "auto_kept"
                fl = [x for x in (rec.get("gate_flag"), rec.get("caption_flag")) if x]
                if fl: rec["flag"] = "；".join(fl)
                st["segs"][str(n)] = rec; save_state(ep_dir, st)
                H.say(f"✓ {ep} 链{chain} Seg{n} 自动保留（分 {rv.get('score')}，第 {tries} 次）")
                break
            H.ledger_row(ep_dir, {"seg": n, "outcome": "rejected", "reasons": ["other"], "seed": r.get("seed"), "prompt_version": r["version"],
                                  "format": "en", "task_id": r["task_id"], "clip": os.path.relpath(r["clip"], ep_dir), "note": "batch 自动质检：" + "；".join(why)})
            rec.setdefault("attempts", []).append({"clip": os.path.relpath(r["clip"], ep_dir), "score": rv.get("score"), "why": why,
                                                   "seed": r.get("seed"), "version": r["version"], "task_id": r["task_id"]})
            rec["status"] = "retry"; st["segs"][str(n)] = rec; save_state(ep_dir, st)
            H.say(f"  ↻ {ep} Seg{n} 未过自动质检：{'；'.join(why)}")
    return "done"


# ------------------------------------------------------------------ 计划与调度
def todo_rows(eps, tag):
    rows = []
    for ep in eps:
        ep_dir = os.path.join(PIPE, "episodes", ep)
        st = load_state(ep_dir, tag)
        for c, segs in chains(ep_dir):
            rows.append((ep, c, segs, [n for n in segs if not done_status(st["segs"].get(str(n), {}))]))
    return rows


def cost_text(n_segs, a, retries):
    po, pl = PRICE.get(a.resolution, (0, 0))
    sec = n_segs * a.duration
    lo, hi = sec * pl, sec * po
    return (f"{n_segs} 段 × {a.duration}s = {sec}s；{a.resolution} 空闲时段 ¥{lo:.0f}（高峰时段 ¥{hi:.0f}）；"
            f"若每段都多重出 {retries} 次，空闲时段最多 ¥{lo * (1 + retries):.0f}")


def cmd_plan(a):
    rows = todo_rows(episodes(a.episodes), a.tag)
    tot = sum(len(x[3]) for x in rows)
    for ep in sorted({r[0] for r in rows}):
        H.say(f"{ep}：" + "  ".join(f"链{c}={s}" + (f"(余{len(l)})" if len(l) != len(s) else "") for e_, c, s, l in rows if e_ == ep))
    longest = max((len(r[3]) for r in rows), default=0)
    H.say(f"\n共 {len(rows)} 条链、待出 {tot} 段；最长的链 {longest} 段。")
    H.say("费用：" + cost_text(tot, a, a.retries))
    H.say(f"用时参考（每段按 13 分钟估（E31–E40 实测中位 13 分、最长 18 分））：并行 1 → {tot * 13 / 60:.0f} 小时；并行 2 → {tot * 13 / 120:.0f} 小时；"
          f"并行 4 → {tot * 8 / 240:.1f} 小时（最长的链至少 {longest * 8} 分钟）；一个空闲窗口 8 小时。")
    return 0


def run_scheduler(ctx, jobs, a, win):
    """按顺序启动链，同时运行数 ≤ limit；被限流就降并发并把链放回队首。"""
    limit = a.parallel
    queue = list(jobs); running = []
    while queue or running:
        for item in list(running):
            t, job, box = item
            if t.is_alive(): continue
            running.remove(item)
            if box.get("r") == "throttled":
                limit = max(1, limit - 1); RT["throttled"] += 1
                H.say(f"■ 接口提示并发/限流，同时运行数降为 {limit}；{job[1]} 链{job[3]} 稍后重试")
                queue.insert(0, job); time.sleep(30)
                if RT["throttled"] >= 10:
                    RT.update(stop=True, why="被限流 10 次，停止提交")
        if RT["stop"] or RT["window_closed"]:
            queue = []
        while queue and len(running) < limit:
            job = queue.pop(0)
            todo = [n for n in job[4] if not done_status(job[7]["segs"].get(str(n), {}))]
            if not todo: continue
            box = {}
            j = job[:4] + (todo,) + job[5:]
            t = threading.Thread(target=lambda j=j, b=box: b.__setitem__("r", run_chain(ctx, j[1], j[2], j[3], j[4], a, j[7], win)), daemon=True)
            t.start(); running.append((t, j, box))
        time.sleep(2)


def _graceful(signum, frame):
    """SIGINT/SIGTERM：不再提交新任务，在途任务照常下载、质检、保留，然后正常退出。"""
    if not RT["stop"]:
        RT.update(stop=True, why="收到停止信号，优雅停止（在途任务会跑完）")
        H.say("■ 收到停止信号：不再提交新任务，等在途任务下载、质检完成后退出。")


def cmd_run(a):
    signal.signal(signal.SIGINT, _graceful); signal.signal(signal.SIGTERM, _graceful)   # 后台进程默认忽略 SIGINT，这里显式接管
    eps = episodes(a.episodes)
    win = parse_window(a.window) if a.window else None
    if a.window and win is None:
        raise H.Err("--window 格式应为 HH:MM-HH:MM，例如 00:00-08:00")
    ctx = H.Ctx(a, need_token=not a.dry_run)
    a.enc = a.enc or ctx.settings.get("enc", "data_uri")
    rows = todo_rows(eps, a.tag)
    tot = sum(len(x[3]) for x in rows)
    pend = sum(1 for ep in eps for n in H.all_segs(ctx.ep_dir(ep)) if pending_task(ctx.ep_dir(ep), n))
    if getattr(a, "recover_only", False):
        H.say(f"只恢复模式：{pend} 个未完成任务，下载、质检、保留；不提交任何新任务。")
        if not pend: return cmd_status(a)
        jobs = []
        for ep in eps:
            ep_dir = ctx.ep_dir(ep); st = load_state(ep_dir, a.tag)
            for c, segs in chains(ep_dir):
                if any(pending_task(ep_dir, n) for n in segs) and any(not done_status(st["segs"].get(str(n), {})) for n in segs):
                    jobs.append((ctx, ep, ep_dir, c, [n for n in segs if not done_status(st["segs"].get(str(n), {}))], a, None, st))
        run_scheduler(ctx, jobs, a, None)
        return cmd_status(a)
    if not tot:
        H.say("没有待出的段（这个 tag 下都已保留）。"); return 0
    now = datetime.datetime.now()
    if not a.dry_run and not a.yes:
        H.say(f"\n即将批量提交：{len(eps)} 集、{tot} 段（其中 {pend} 段有未下完的任务，会先恢复下载，不重复计费），{a.resolution}。")
        H.say("费用估算：" + cost_text(tot, a, a.retries))
        if win:
            inside = window_open(now, win, a.window_margin)
            H.say(f"同时最多 {a.parallel} 条链并行；只在 {a.window} 提交，现在" + ("在窗口内。" if inside else f"不在窗口内，将等到 {next_open(now, win):%m-%d %H:%M} 再开始。"))
        else:
            H.say(f"同时最多 {a.parallel} 条链并行；未设时段限制（高峰时段单价更高）。")
        if not sys.stdin.isatty():
            raise H.Err("非交互环境请加 --yes 确认（付费前必须先征得用户同意）")
        if input("确认提交？输入 y 继续 > ").strip().lower() != "y":
            raise H.Err("已取消")
    if not a.dry_run and sys.platform == "darwin" and shutil.which("caffeinate"):
        subprocess.Popen(["caffeinate", "-i", "-s", "-w", str(os.getpid())])
        H.say("已开启防休眠（caffeinate），本进程结束后自动解除；笔记本请接电源、别合盖。")
    if win and not a.dry_run:
        while not window_open(datetime.datetime.now(), win, a.window_margin):
            go = next_open(datetime.datetime.now(), win)
            H.say(f"等待空闲时段：{go:%m-%d %H:%M} 开始提交（现在 {datetime.datetime.now():%H:%M}）。可以离开了。")
            time.sleep(min(600, max(5, (go - datetime.datetime.now()).total_seconds())))
    jobs = []
    for ep in eps:
        ep_dir = ctx.ep_dir(ep)
        st = load_state(ep_dir, a.tag)
        if not a.dry_run: archive_old(ep_dir, st)
        for c, segs in chains(ep_dir):
            todo = [n for n in segs if not done_status(st["segs"].get(str(n), {}))]
            if todo: jobs.append((ctx, ep, ep_dir, c, todo, a, None, st))
    if a.canary and not a.dry_run and jobs:
        can = jobs[:a.canary]
        H.say(f"先锋段：先跑 {len(can)} 段（" + "、".join(f"{j[1]} Seg{j[4][0]}" for j in can) + "），全部合格才放行其余各段")
        ts = [threading.Thread(target=run_chain, args=(j[0], j[1], j[2], j[3], j[4], a, j[7], win), kwargs={"limit": 1}, daemon=True) for j in can]
        for t in ts: t.start()
        for t in ts: t.join()
        bad = [f"{j[1]} Seg{j[4][0]}" for j in can if not done_status(j[7]["segs"].get(str(j[4][0]), {}))]
        if RT["window_closed"]:
            H.say("■ 空闲时段已结束，先锋段尚未完成；下次同一命令续批。")
            return cmd_status(a)
        if bad or RT["stop"]:
            H.say("■ 先锋段没有通过（" + "、".join(bad) + "），整批停止。看 BATCH_REPORT.md 和各集 06_jobs/batch_state.json 找原因。")
            cmd_status(a); return 2
        H.say("先锋段通过，放行全部。")
    run_scheduler(ctx, jobs, a, win)
    if RT["stop"]:
        H.say("■ 本批因熔断提前停止：" + RT["why"] + "；排除问题后用同一个 --tag 重跑即可续批。")
    if RT["window_closed"]:
        H.say("■ 空闲时段已结束，已提交的任务都跑完了；没出完的下次用同一个命令续批（同一个 --tag）。")
    return cmd_status(a)


def cmd_status(a):
    eps = episodes(a.episodes)
    lines = [f"# 批量出片进度（tag={a.tag}，{datetime.datetime.now():%Y-%m-%d %H:%M}）", "",
             "已保留 = 自动质检通过、已接力，**待人工看片**（带 ⚠ 的是软指标没过、取了分最高的一次，请优先看）；停住 = 链停在这里等人看（有硬伤 / 任务异常）；未出 = 还没提交。", "",
             "| 集 | 已保留 | 停住 | 未出 | 停住的段 |", "|---|---|---|---|---|"]
    T = [0, 0, 0]
    for ep in eps:
        ep_dir = os.path.join(PIPE, "episodes", ep)
        st = load_state(ep_dir, a.tag)
        segs = H.all_segs(ep_dir)
        k = [n for n in segs if done_status(st["segs"].get(str(n), {}))]
        nr = [n for n in segs if st["segs"].get(str(n), {}).get("status") in ("needs_review", "pending")]
        rest = len(segs) - len(k) - len(nr)
        T[0] += len(k); T[1] += len(nr); T[2] += rest
        detail = "；".join(f"Seg{n}：{'、'.join(st['segs'][str(n)].get('last_gate') or [st['segs'][str(n)].get('last_error', st['segs'][str(n)].get('status', ''))])}" for n in nr)
        flagged = [f"Seg{n}（{st['segs'][str(n)]['flag']}）" for n in k if st['segs'][str(n)].get("flag")]
        if flagged: detail = (detail + "；" if detail else "") + "⚠需优先人工看：" + "、".join(flagged)
        lines.append(f"| {ep} | {len(k)} | {len(nr)} | {rest} | {detail} |")
    lines += ["", f"合计：已保留 {T[0]}，停住 {T[1]}，未出 {T[2]}。"]
    open(os.path.join(PIPE, "BATCH_REPORT.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    H.say("\n".join(lines[6:]))
    return 0


def main():
    ap = argparse.ArgumentParser(description="多集批量出片", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("plan", cmd_plan), ("run", cmd_run), ("status", cmd_status)):
        p = sp.add_parser(name); p.add_argument("episodes", nargs="+")
        p.add_argument("--pipeline", default=PIPE); p.add_argument("--root")
        p.add_argument("--tag", default="768p-v1", help="批次名；同一 tag 内断点续跑")
        p.add_argument("--retries", type=int, default=1, help="自动质检不过时每段最多重出几次")
        p.add_argument("--resolution", default="768p竖", choices=H.RESOLUTIONS)
        p.add_argument("--duration", type=int, default=15)
        if name == "run":
            p.add_argument("--parallel", type=int, default=4, help="同时运行的链数（接口提示限流时会自动减少）")
            p.add_argument("--window", help="只在该时段提交，HH:MM-HH:MM，例如 00:00-08:00（空闲时段）")
            p.add_argument("--window-margin", type=int, default=15, help="窗口关闭前多少分钟不再提交新任务")
            p.add_argument("--canary", type=int, default=2, help="先锋段数：先跑这几段，全部合格才放行其余（0=不用）")
            p.add_argument("--max-errors", type=int, default=6, help="接口连续出错多少次就熔断停止提交")
            p.add_argument("--enc", choices=["data_uri", "raw_base64"])
            p.add_argument("--max-side", type=int, default=1280)
            p.add_argument("--poll", type=float, default=10); p.add_argument("--timeout", type=int, default=1800)
            p.add_argument("--dry-run", action="store_true"); p.add_argument("--yes", action="store_true")
            p.add_argument("--version")
            p.add_argument("--recover-only", action="store_true", help="只恢复未完成的任务（下载/质检/保留），不提交任何新任务")
        p.set_defaults(f=fn)
    a = ap.parse_args()
    try:
        sys.exit(a.f(a) or 0)
    except H.Err as e:
        print("✗ " + str(e), file=sys.stderr); sys.exit(1)
    except KeyboardInterrupt:
        print("\n已中断。已提交的任务不会丢：用同一个命令再跑一次，会先恢复下载再续批。", file=sys.stderr); sys.exit(130)


if __name__ == "__main__":
    main()
