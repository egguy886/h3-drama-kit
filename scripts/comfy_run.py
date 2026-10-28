#!/usr/bin/env python3
"""自有 ComfyUI（zealman 面板）出片：把已编译好的分镜（05_prompts + 参考图）提交到面板的工作流 API，轮询并把成片落到 07_clips。
和 h3_run.py（AutoDL.art 云端按次计费）的区别：无令牌、无单次费用；一次只跑一段（单卡），段间自动清显存。

用法（在项目根目录）：
  python3 tools/comfy_run.py status                         # 面板 / GPU / 队列 / 工作流是否在线
  python3 tools/comfy_run.py run E01 --seg 1 2 3            # 逐段提交并等结果，成片 → episodes/E01/07_clips/
  python3 tools/comfy_run.py run E01 --all                  # 整集
  python3 tools/comfy_run.py run E01 --seg 1 --dry-run      # 只构建输入，不上传不提交
  python3 tools/comfy_run.py run E01 --seg 1 --seed 123 --mp 0.4 --tag t1

设置（comfy_settings.json，可用环境变量 COMFY_BASE_URL 覆盖地址）：base_url / workflow_id / aspect_ratio / megapixels / second_scale。
每次成功的结果立刻落盘并写 episodes/Exx/comfy_runs.jsonl（prompt_id 只在 ComfyUI 内存里，重启即失效）。
"""
import argparse, json, os, re, subprocess, sys, time, urllib.parse, urllib.request

PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SET_P = os.path.join(PIPE, "comfy_settings.json")
DEFAULTS = {
    "base_url": "",            # 你的 ComfyUI 面板地址，写进项目根的 comfy_settings.json 或环境变量 COMFY_BASE_URL
    "workflow_id": "API-U24-文武双修T8版",
    "aspect_ratio": "9:16 (Portrait Widescreen)",
    "megapixels": 0.4,          # 一采分辨率（U24 标签：默认 0.4，太高会失败）
    "second_scale": 1.5,        # 二采倍率（节点 54）
    "duration": 15,
    "poll_sec": 3,
    "timeout_min": 40,
}


def settings():
    s = dict(DEFAULTS)
    if os.path.isfile(SET_P):
        s.update(json.load(open(SET_P, encoding="utf-8")))
    if os.environ.get("COMFY_BASE_URL"):
        s["base_url"] = os.environ["COMFY_BASE_URL"]
    s["base_url"] = s["base_url"].rstrip("/")
    if not s["base_url"]:
        raise SystemExit("先在项目根建 comfy_settings.json：{\"base_url\": \"https://你的面板地址\"}（或设环境变量 COMFY_BASE_URL）")
    return s


def http(method, url, body=None, timeout=60):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"} if body is not None else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    try:
        return json.loads(raw)
    except Exception:
        return {"_raw": raw[:300].decode("utf-8", "replace")}


CACHE_P = os.path.join(PIPE, "comfy_upload_cache.json")


def _sha(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_REMOTE = {"names": None}


def remote_names(base):
    """面板 input 目录里现有的文件名（缓存命中后核对文件还在，防止面板清过 input）。"""
    if _REMOTE["names"] is None:
        try:
            _REMOTE["names"] = {a["name"] for a in http("GET", base + "/api/input-assets", timeout=60)}
        except Exception:
            _REMOTE["names"] = set()
    return _REMOTE["names"]


def upload(base, path, remote_name):
    """同一张参考图只传一次（按内容 sha256 缓存），后面的段直接复用面板里的文件名。"""
    cache = json.load(open(CACHE_P, encoding="utf-8")) if os.path.isfile(CACHE_P) else {}
    key = _sha(path)
    if key in cache and cache[key] in remote_names(base):
        return cache[key]
    name = _upload_raw(base, path, remote_name)
    cache[key] = name
    json.dump(cache, open(CACHE_P, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    remote_names(base).add(name)
    return name


def _upload_raw(base, path, remote_name):
    """multipart 上传到 ComfyUI input（用 curl，避免手写 multipart）；返回面板给的 name。"""
    r = subprocess.run(["curl", "-s", "-m", "180", "-X", "POST", f"{base}/api/comfy/upload/file", "-F", f"file=@{path};filename={remote_name}", "-F", "overwrite=true"],
                       capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
    except Exception:
        raise SystemExit(f"上传失败 {path}：{r.stdout[:200]} {r.stderr[:200]}")
    if "name" not in d:
        raise SystemExit(f"上传失败 {path}：{d}")
    return d["name"] if not d.get("subfolder") else f"{d['subfolder']}/{d['name']}"


def cmd_status(a):
    s = settings(); b = s["base_url"]
    for p in ("/api/health", "/api/gpu/info", "/api/comfy/status", "/api/comfy/queue-status"):
        try:
            print(p, "→", json.dumps(http("GET", b + p, timeout=20), ensure_ascii=False)[:240])
        except Exception as e:
            print(p, "→ 失败", e)
    wl = http("GET", b + "/api/workflow/list", timeout=30).get("workflows", [])
    ok = any(w["id"] == s["workflow_id"] for w in wl)
    print(f"工作流 {s['workflow_id']}：{'在' if ok else '不在'}（共 {len(wl)} 个）")


def build(ep, seg, a, s):
    """读 h3_run 的 dry-run 产物拿提示词 + 参考图清单（不需要任何令牌）。"""
    jp = os.path.join(PIPE, "episodes", ep, "06_jobs", f"dryrun_seg{seg:02d}_en.json")
    subprocess.run([sys.executable, os.path.join(PIPE, "tools", "h3_run.py"), "run", ep, "--seg", str(seg), "--dry-run"], cwd=PIPE, capture_output=True, text=True)
    if not os.path.isfile(jp):
        raise SystemExit(f"没有 {jp}：先 compose + build 这一集")
    d = json.load(open(jp, encoding="utf-8"))
    pay = d["payload"]
    files = [(f["field"], os.path.join(PIPE, f["file"]) if not os.path.isabs(f["file"]) else f["file"]) for f in d["files"]]
    return pay["prompt"], files, int(a.seed if a.seed is not None else pay.get("seed", int(time.time()) % 10**9))


def run_seg(ep, seg, a, s):
    base = s["base_url"]
    prompt, files, seed = build(ep, seg, a, s)
    mp = a.mp if a.mp is not None else s["megapixels"]
    tag = a.tag or "c1"
    iv = {"prompt": prompt, "27:value": s["duration"], "29:aspect_ratio": s["aspect_ratio"], "29:megapixels": mp,
          "54:value": a.scale if a.scale is not None else s["second_scale"], "11:noise_seed": seed}
    print(f"== {ep} Seg{seg}：{len(files)} 个参考，seed {seed}，一采 {mp}MP × 二采 {iv['54:value']}，提示词 {len(prompt)} 字符")
    if a.dry_run:
        for fld, p in files:
            print("   ", fld, "←", os.path.relpath(p, PIPE))
        return None
    for fld, p in files:
        iv[fld] = upload(base, p, f"{ep}_s{seg:02d}_{fld}_{os.path.basename(p)}")
    try:
        http("POST", base + "/api/comfy/proxy/free", {"unload_models": True, "free_memory": True}, timeout=30)   # 连续跑重模型前清显存
    except Exception as e:
        print("   清显存失败（不阻断）：", e)
    t0 = time.time()
    for k in range(3):                               # 提交前确认队列空，避免网络报错后重复提交同一段
        try:
            if not http("GET", base + "/api/comfy/queue-status", timeout=20).get("busy"):
                break
        except Exception:
            pass
        time.sleep(15)
    r = http("POST", base + "/api/workflow/generate", {"workflow_id": s["workflow_id"], "input_values": iv, "client_id": f"{ep}-s{seg:02d}"}, timeout=60)
    if not r.get("success"):
        raise RuntimeError(f"提交失败：{json.dumps(r, ensure_ascii=False)[:600]}")
    pid = r["prompt_id"]
    print(f"   已提交 prompt_id={pid}；resolved_inputs={json.dumps(r.get('resolved_inputs'), ensure_ascii=False)[:300]}")
    deadline = time.time() + 60 * s["timeout_min"]
    while time.time() < deadline:
        time.sleep(s["poll_sec"])
        try:
            q = http("GET", f"{base}/api/workflow/result?prompt_id={pid}", timeout=30)
        except Exception as e:                       # 网络抖动（SSL EOF / 超时）不判失败：任务还在服务器上跑，继续轮询
            print(f"   轮询出错（继续）：{str(e)[:120]}", flush=True); time.sleep(10); continue
        if q.get("error"):
            raise RuntimeError(f"工作流报错：{str(q['error'])[:800]}")
        if q.get("pending") is False:
            vids = [x for x in q.get("results", []) if x.get("type") == "video"]
            if not vids:
                raise RuntimeError(f"完成但没有视频：{json.dumps(q, ensure_ascii=False)[:600]}")
            out_dir = os.path.join(PIPE, "episodes", ep, "07_clips"); os.makedirs(out_dir, exist_ok=True)
            dst = os.path.join(out_dir, f"{ep}_seg{seg:02d}_{tag}_s{seed}.mp4")
            for k in range(5):                       # 下载也重试
                try:
                    urllib.request.urlretrieve(base + vids[0]["url"], dst); break
                except Exception as e:
                    print(f"   下载出错（第 {k+1} 次）：{str(e)[:120]}", flush=True); time.sleep(10)
            else:
                raise RuntimeError("成片下载 5 次都失败")
            sec = time.time() - t0
            rec = {"ep": ep, "seg": seg, "tag": tag, "seed": seed, "megapixels": mp, "scale": iv["54:value"], "prompt_id": pid, "file": os.path.relpath(dst, PIPE),
                   "remote": vids[0]["url"], "seconds": round(sec), "workflow": s["workflow_id"], "at": time.strftime("%Y-%m-%d %H:%M:%S")}
            open(os.path.join(PIPE, "episodes", ep, "comfy_runs.jsonl"), "a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"   ✅ {rec['file']}（{sec/60:.1f} 分钟）")
            return dst
    raise RuntimeError("等待超时（面板里可能还在跑，用 status 看队列）")


def cmd_run(a):
    s = settings()
    segs = a.seg
    if a.all:
        meta = [f for f in os.listdir(os.path.join(PIPE, "episodes", a.episode, "05_prompts")) if f.endswith(".meta.json")]
        segs = sorted(int(re.search(r"seg(\d+)", f).group(1)) for f in meta)
    if not segs:
        raise SystemExit("用 --seg N [N ...] 或 --all")
    for n in segs:
        run_seg(a.episode, n, a, s)


def seg_list(ep):
    d = os.path.join(PIPE, "episodes", ep, "05_prompts")
    return sorted(int(re.search(r"seg(\d+)", f).group(1)) for f in os.listdir(d) if f.endswith(".meta.json")) if os.path.isdir(d) else []


def expand(spec):
    out = []
    for part in spec:
        m = re.fullmatch(r"E(\d+)-E(\d+)", part)
        if m:
            out += [f"E{n:02d}" for n in range(int(m.group(1)), int(m.group(2)) + 1)]
        else:
            out.append(part)
    return out


def cmd_batch(a):
    """整批顺序出片：按集、按段依次跑；已有同 tag 成片的跳过；失败重试 --retries 次，仍失败就记下继续下一段。"""
    s = settings(); tag = a.tag or "r1"
    log = os.path.join(PIPE, "comfy_batch.log")

    def say(m):
        line = f"{time.strftime('%m-%d %H:%M:%S')} {m}"
        print(line, flush=True); open(log, "a", encoding="utf-8").write(line + "\n")

    todo = []
    for ep in expand(a.episodes):
        for n in seg_list(ep):
            clip_dir = os.path.join(PIPE, "episodes", ep, "07_clips")
            have = os.path.isdir(clip_dir) and any(f.startswith(f"{ep}_seg{n:02d}_{tag}_") for f in os.listdir(clip_dir))
            if not have:
                todo.append((ep, n))
    say(f"批量开始：待出 {len(todo)} 段（tag {tag}，工作流 {s['workflow_id']}）")
    failed, t0 = [], time.time()
    for i, (ep, n) in enumerate(todo, 1):
        ns = argparse.Namespace(seed=None, mp=a.mp, scale=a.scale, tag=tag, dry_run=False)
        for attempt in range(a.retries + 1):
            try:
                st = time.time(); run_seg(ep, n, ns, s)
                say(f"[{i}/{len(todo)}] ✅ {ep} Seg{n}（{(time.time()-st)/60:.1f} 分钟）")
                break
            except Exception as e:
                say(f"[{i}/{len(todo)}] ❌ {ep} Seg{n} 第 {attempt+1} 次失败：{str(e)[:300]}")
                time.sleep(20)
        else:
            failed.append(f"{ep}-S{n}")
    say(f"批量结束：成功 {len(todo)-len(failed)}/{len(todo)}，失败 {failed or '无'}，共 {(time.time()-t0)/3600:.1f} 小时")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="自有 ComfyUI 面板出片")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    r = sub.add_parser("run"); r.add_argument("episode"); r.add_argument("--seg", type=int, nargs="*"); r.add_argument("--all", action="store_true")
    r.add_argument("--dry-run", action="store_true"); r.add_argument("--seed", type=int); r.add_argument("--mp", type=float)
    r.add_argument("--scale", type=float); r.add_argument("--tag")
    b = sub.add_parser("batch"); b.add_argument("episodes", nargs="+", help="如 E01-E10 或 E01 E03"); b.add_argument("--tag"); b.add_argument("--retries", type=int, default=1)
    b.add_argument("--mp", type=float); b.add_argument("--scale", type=float)
    a = ap.parse_args()
    {"status": cmd_status, "run": cmd_run, "batch": cmd_batch}[a.cmd](a)
