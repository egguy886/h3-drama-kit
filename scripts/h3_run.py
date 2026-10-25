#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""h3_run.py — 云端 H3（AutoDL.Art 无服务器工作流 minimax_h3_zm_u24）出片执行器

流程：本地资产读取 ➔ 编码上传 ➔ 云端等待 ➔ 下载本地 ➔ 尾帧抽帧接力
只用 Python 标准库（Pillow 可选：缩图与尾帧清晰度评分）；需要 ffmpeg / ffprobe 在 PATH 里。

用法（在项目根目录运行；参考图/声线默认在 assets/ 下找，见 project.json 的 asset_root；--root 可另指素材所在目录）：
  python tools/h3_run.py check  E01                                    # 离线预检：每段的参考图/音频/提示词是否齐全
  python tools/h3_run.py probe                                         # 最小付费探测（约 2 秒、480p）：确认认证与编码方式
  python tools/h3_run.py run    E01 --seg 1 4 7 --fmt both --dry-run  # 只构建请求，不发送
  python tools/h3_run.py run    E01 --seg 1 4 7 --fmt both            # 第 1 轮：三个链头并行，英/中各一次（同 seed）
  python tools/h3_run.py run    E01 --chain A --fmt en                # 沿 A 链逐段生成，每段后询问 保留/淘汰
  python tools/h3_run.py accept E01 1 --fmt en                        # 保留：写账、抽尾帧给下一段
  python tools/h3_run.py reject E01 1 --reason identity-drift
  python tools/h3_run.py tail   E01 1 --tail-offset 1.0               # 重新抽尾帧（默认自动挑最清晰的）
  python tools/h3_run.py resume E01                                    # 断线后继续等待/下载未完成的任务
  python tools/h3_run.py run    E01 --seg 2 5 8 --takes 2             # 抽卡：每段同时出 2 张，自动排序
  python tools/h3_run.py review E01 --seg 1                           # 重新审片：切点对比 + 尾段稳定 + 首帧承接 → 08_review/

环境变量（也可写在流水线根目录或 --root 下的 .env 文件里，不要提交到仓库）：
  AUTODL_TOKEN        必填（也认 AUTODL_API_KEY）。令牌绝不会被打印或写入任何记录文件
  AUTODL_BASE_URL     默认 https://www.autodl.art（接口域名，若文档不同请改）
  AUTODL_AUTH_HEADER  默认 Authorization
  AUTODL_AUTH_PREFIX  默认 "Bearer "（已由真实调用记录确认）
  PROJECT_ROOT        同 --root
"""
import argparse
import base64
import datetime
import glob
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urljoin

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SUBMIT_PATH = "/api/v1/comfyui/comfyui_workflow/minimax_h3_zm_u24"
RESULT_PATH = "/api/v1/comfyui/comfyui_workflow/result/{task_id}"
DEFAULT_BASE = "https://www.autodl.art"
RESOLUTIONS = ["480p竖", "768p竖", "480p横", "768p横", "480p(1:1)", "768p(1:1)"]
REASONS = {"identity-drift", "prop-error", "space-error", "gate-opened", "extra-cuts", "tail-collapse",
           "garbled-text", "lip-sync", "audio-jump", "motion-artifact", "weapon-flag", "other"}
OK_ST = {"success", "succeeded", "succeed", "completed", "complete", "done", "finished", "finish", "ok"}
BAD_ST = {"failed", "fail", "failure", "error", "cancelled", "canceled", "timeout", "timed_out"}
RUN_ST = {"pending", "running", "queued", "queue", "processing", "waiting", "in_progress", "started",
          "submitted", "created", "0", "1"}
VIDEO_EXT = (".mp4", ".mov", ".webm", ".mkv")
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
TAIL_OFFSETS = (2.0, 1.5, 1.0, 0.5, 0.2)

LOCK = threading.Lock()


class Err(Exception):
    pass


def say(*a):
    with LOCK:
        print(*a, flush=True)


# ------------------------------------------------------------------ config
def load_env(*dirs):
    for d in dirs:
        p = os.path.join(d, ".env")
        if os.path.isfile(p):
            for ln in open(p, encoding="utf-8"):
                ln = ln.strip()
                if not ln or ln.startswith("#") or "=" not in ln:
                    continue
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class Ctx:
    def __init__(self, a, need_root=True, need_token=False):
        self.pipe = os.path.abspath(a.pipeline)
        root_arg = getattr(a, "root", None)
        load_env(self.pipe, root_arg or "", os.getcwd())
        lp = os.path.join(self.pipe, "local_paths.json")
        self.local = json.load(open(lp, encoding="utf-8")) if os.path.isfile(lp) else {}
        self.root = root_arg or os.environ.get("PROJECT_ROOT") or self.local.get("root") or self.pipe   # 默认：素材就在项目里
        self.root = os.path.abspath(self.root)
        pj = os.path.join(self.pipe, "project.json")
        self.project = json.load(open(pj, encoding="utf-8")) if os.path.isfile(pj) else {}
        sp_ = os.path.join(self.pipe, "h3_settings.json")          # probe 探测成功后写入（不含令牌）
        self.settings = json.load(open(sp_, encoding="utf-8")) if os.path.isfile(sp_) else {}
        self.base = (os.environ.get("AUTODL_BASE_URL") or self.settings.get("base_url") or DEFAULT_BASE).rstrip("/")
        self.token = ""
        for nm in ("AUTODL_TOKEN", "AUTODL_API_KEY"):
            self.token = os.environ.get(nm, "").strip()
            if not self.token and sys.platform == "darwin" and need_token:       # macOS：launchctl setenv 设的变量
                try:
                    self.token = subprocess.run(["launchctl", "getenv", nm], capture_output=True, text=True, timeout=5).stdout.strip()
                except Exception:
                    self.token = ""
            if self.token:
                break
        if need_token and not self.token:
            raise Err("缺少令牌：设置环境变量 AUTODL_TOKEN（或 AUTODL_API_KEY），或写进项目根目录的 .env 文件")
        self.auth_header = os.environ.get("AUTODL_AUTH_HEADER") or self.settings.get("auth_header") or "Authorization"
        self.auth_prefix = os.environ["AUTODL_AUTH_PREFIX"] if "AUTODL_AUTH_PREFIX" in os.environ else self.settings.get("auth_prefix", "Bearer ")
        mp = os.path.join(self.pipe, "assets_manifest.json")
        self.by_id = {x["id"]: x for x in json.load(open(mp, encoding="utf-8"))["assets"]} if os.path.isfile(mp) else {}
        vp = os.path.join(self.pipe, "voices.json")
        self.voices = json.load(open(vp, encoding="utf-8")) if os.path.isfile(vp) else {"voices": []}

    def ep_dir(self, ep):
        d = os.path.join(self.pipe, "episodes", ep)
        if not os.path.isdir(d):
            raise Err(f"找不到集目录 {d}")
        return d


# ------------------------------------------------------------------ assets
def search_base(ctx):
    """素材搜索目录：project.json 的 asset_root（默认 assets/，相对项目根）→ 旧布局 13_短剧生产/ → --root 本身。"""
    for base in (ctx.pipe, ctx.root):
        p = os.path.join(base, ctx.project.get("asset_root", "assets"))
        if os.path.isdir(p):
            return p
    p = os.path.join(ctx.root, "13_短剧生产")
    return p if os.path.isdir(p) else ctx.root


def find_by_id(ctx, xid, exts):
    """按文件名找素材：<ID>.png / <ID>_v2.png / <ID>__说明.png（同 ID 多版本取文件名最大者）。"""
    base = search_base(ctx)
    cands = []
    for pat in (xid + ".*", xid + "_*"):
        cands += [c for c in glob.glob(os.path.join(base, "**", pat), recursive=True) if c.lower().endswith(exts)]
    return sorted(set(cands))


def resolve_asset(ctx, bid):
    """返回 (绝对路径, 备注或 None)"""
    ov = ctx.local.get("images", {}).get(bid)
    if ov:
        p = ov if os.path.isabs(ov) else os.path.join(ctx.root, ov)
        if os.path.isfile(p):
            return p, None
        raise Err(f"local_paths.json 里 {bid} 指向的文件不存在：{p}")
    a = ctx.by_id.get(bid)
    if not a:                                                   # 新项目不需要注册表：按文件名找
        cands = find_by_id(ctx, bid, IMG_EXT)
        if cands:
            note = f"同 ID 有 {len(cands)} 个文件，取 {os.path.basename(cands[-1])}" if len(cands) > 1 else None
            return cands[-1], note
        raise Err(f"找不到 {bid} 的参考图：把图放进 {os.path.relpath(search_base(ctx), ctx.pipe)}/ 并命名为 {bid}.png（或 {bid}_v1.png），或在 local_paths.json 的 images 里指定")
    p = os.path.join(ctx.root, a["resolved_path"])
    if os.path.isfile(p):
        return p, None
    pat = bid.replace("-", "_") + "_*"
    cands = [c for c in glob.glob(os.path.join(search_base(ctx), "**", pat), recursive=True)
             if c.lower().endswith(IMG_EXT)]
    if cands:
        pick = sorted(cands)[-1]
        return pick, f"注册表路径不存在，改用 {os.path.relpath(pick, ctx.root)}（共 {len(cands)} 个候选，取文件名最大者）"
    raise Err(f"找不到 {bid} 的图片：{a['resolved_path']}")


def resolve_voice(ctx, vid):
    ov = ctx.local.get("voices", {}).get(vid)
    if ov:
        p = ov if os.path.isabs(ov) else os.path.join(ctx.root, ov)
        if os.path.isfile(p):
            return p, None
        raise Err(f"local_paths.json 里 {vid} 指向的文件不存在：{p}")
    direct = [c for c in find_by_id(ctx, vid, (".wav", ".mp3", ".flac", ".m4a")) if "master" not in os.path.basename(c).lower()]
    if direct:                                  # 优先 <voice_id>_h3_32k.wav（单声道 32k，H3 用），其次 <voice_id>.wav；母版 *_master_48k 只给后期用
        direct.sort(key=lambda c: ("h3_32k" in c.lower(), os.path.basename(c)))
        return direct[-1], None
    ch = next((x for x in ctx.voices.get("voices", []) if x["voice_id"] == vid), None)
    if not ch:
        raise Err(f"声线 {vid} 不在 voices.json 里，也没有名为 {vid}.wav 的文件")
    tokens = {t.upper() for t in re.split(r"[\s_\-]+", ch["character"]) if t}
    ver = {t.upper() for t in re.split(r"[\s_\-]+", vid)[2:]}          # 例如 V2 / AGE18
    cands = []
    for d in [search_base(ctx)] + glob.glob(os.path.join(search_base(ctx), "**", "声音参考"), recursive=True):
        for f in os.listdir(d):
            u = f.upper()
            if not u.endswith((".WAV", ".MP3", ".FLAC", ".MP4")) or "H3_32K" not in u:
                continue
            parts = set(re.split(r"[\s_\-\.]+", u))
            hit = len(tokens & parts)
            if hit:
                cands.append((hit * 10 + len(ver & parts), os.path.join(d, f)))
    if not cands:
        raise Err(f"找不到 {vid} 的 H3 参考音频（*_h3_32k.wav，名字里要有 {sorted(tokens)}）；可在 local_paths.json 的 voices 里手动指定")
    cands.sort(reverse=True)
    if len(cands) > 1 and cands[0][0] == cands[1][0]:
        raise Err(f"{vid} 有多个同分候选，请在 local_paths.json 的 voices 里指定：" + "；".join(os.path.relpath(c[1], ctx.root) for c in cands[:4]))
    return cands[0][1], None


def enc_image(path, max_side, mode):
    raw = open(path, "rb").read()
    mime = "image/png" if path.lower().endswith(".png") else "image/webp" if path.lower().endswith(".webp") else "image/jpeg"
    try:
        from PIL import Image
        im = Image.open(path)
        if max_side > 0 and (max(im.size) > max_side or len(raw) > 1_500_000):
            im = im.convert("RGB")
            im.thumbnail((max_side, max_side))
            import io
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=92)
            raw, mime = buf.getvalue(), "image/jpeg"
    except ImportError:
        pass
    return wrap(raw, mime, mode)


def enc_audio(path, mode):
    ext = os.path.splitext(path)[1].lower()
    mime = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac", ".mp4": "video/mp4"}.get(ext, "audio/wav")
    return wrap(open(path, "rb").read(), mime, mode)


def wrap(raw, mime, mode):
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}" if mode == "data_uri" else b64


# ------------------------------------------------------------------ episode files
def load_meta(ep_dir, n):
    p = os.path.join(ep_dir, "05_prompts", f"seg{n:02d}.meta.json")
    if not os.path.isfile(p):
        raise Err(f"没有 {p}（先运行 build_episode.py）")
    return json.load(open(p, encoding="utf-8"))


SECTIONS = ["subject_definitions", "summary", "retention_analysis", "detailed_description", "overall_soundscape", "non_diegetic_music"]


def extract_en(md):
    """从中英对照文件里只取英文块，按官方六段式顺序拼回。中文块一个字都不上传。"""
    parts = {}
    for key, text in re.findall(r"<!-- EN:(\w+) -->\n(.*?)\n<!-- /EN -->", md, re.S):
        parts.setdefault(key, []).append(text)
    return "\n\n".join(f"{k}:\n" + "\n".join(parts[k]) for k in SECTIONS if k in parts) + "\n"


def load_prompt(ep_dir, n, fmt, notes=None):
    if fmt == "en":
        bp = os.path.join(ep_dir, "05_prompts", f"seg{n:02d}.bilingual.md")
        if os.path.isfile(bp):
            md = open(bp, encoding="utf-8").read()
            want = load_meta(ep_dir, n).get("bilingual_sha256")
            if want and hashlib.sha256(md.encode("utf-8")).hexdigest() != want and notes is not None:
                notes.append("双语提示词被手工改过（与 plan.json 生成的版本不同）；本次按改过的英文上传，记得把改动移回 plan.json")
            txt = extract_en(md).strip()
            missing = [k for k in SECTIONS if f"{k}:" not in txt]
            if missing:
                raise Err(f"Seg{n} 双语文件缺少英文段：{missing}")
            return txt
        p = os.path.join(ep_dir, "05_prompts", f"seg{n:02d}.md")
    else:
        p = next((c for c in (os.path.join(ep_dir, "05_prompts_wenwu", f"seg{n:02d}.txt"),
                              os.path.join(ep_dir, "_archive", "05_prompts_wenwu_v2", f"seg{n:02d}.txt")) if os.path.isfile(c)),
                 os.path.join(ep_dir, "05_prompts_wenwu", f"seg{n:02d}.txt"))
    if not os.path.isfile(p):
        raise Err(f"没有提示词文件 {p}" + ("（中文分镜版已改为对照阅读，不再单独生成；需要时用 build_episode.py --legacy-wenwu）" if fmt == "cn" else ""))
    return open(p, encoding="utf-8").read().strip()


def tail_path(ep_dir, n):
    return os.path.join(ep_dir, "07_clips", f"seg{n:02d}_tail.png")


def all_segs(ep_dir):
    return sorted(int(m.group(1)) for f in os.listdir(os.path.join(ep_dir, "05_prompts"))
                  if (m := re.match(r"seg(\d+)\.meta\.json$", f)))


def chain_segs(ep_dir, letter):
    return [n for n in all_segs(ep_dir) if load_meta(ep_dir, n).get("chain") == letter.upper()]


def build_payload(ctx, ep_dir, n, fmt, seed, resolution, duration, mode, max_side, encode=True):
    meta = load_meta(ep_dir, n)
    imgs, auds, report, notes, pending_tail = {}, {}, [], [], []
    prompt = load_prompt(ep_dir, n, fmt, notes)
    for r in meta["refs_in_upload_order"]:
        m = re.match(r"(Picture|Audio) (\d+)$", r["label"])
        if not m:
            raise Err(f"Seg{n} 参考标签格式不认识：{r['label']}")
        kind, k = m.group(1), int(m.group(2))
        if kind == "Picture":
            if r.get("backend_id") is None:
                mm = re.search(r"Seg(\d+)", r["name"])
                prev = int(mm.group(1)) if mm else n - 1
                tp = tail_path(ep_dir, prev)
                if not os.path.isfile(tp) and not encode:
                    path, note = None, f"（待 Seg{prev} accept 后生成尾帧）"
                    imgs[k - 1] = (r, path)
                    pending_tail.append(prev)
                    continue
                if not os.path.isfile(tp):
                    raise Err(f"Seg{n} 需要 Seg{prev} 的尾帧，但 {os.path.relpath(tp, ctx.pipe)} 不存在——先对 Seg{prev} 执行 accept")
                path, note = tp, None
            else:
                path, note = resolve_asset(ctx, r["backend_id"])
            imgs[k - 1] = (r, path)
        else:
            path, note = resolve_voice(ctx, r["backend_id"])
            auds[k - 1] = (r, path)
        if note:
            notes.append(f"{r['label']}：{note}")
    for name, d in (("ref_image", imgs), ("ref_audio", auds)):
        if sorted(d) != list(range(len(d))):
            raise Err(f"Seg{n} 的 {name} 编号不连续：{sorted(d)}")
    if not imgs:
        raise Err(f"Seg{n} 没有参考图（ref_image_0 必填）")
    if len(imgs) > 9 or len(auds) > 3:
        raise Err(f"Seg{n} 参考数超限：图 {len(imgs)}（≤9），音频 {len(auds)}（≤3）")
    if not (1 <= len(prompt) <= 10000):
        raise Err(f"Seg{n} 提示词长度 {len(prompt)}，接口要求 1–10000 字符")
    payload = {"prompt": prompt, "duration": int(duration), "resolution": resolution, "seed": int(seed)}
    for k, (r, p) in sorted(imgs.items()):
        v = enc_image(p, max_side, mode) if (encode and p) else ""
        payload[f"ref_image_{k}"] = v
        report.append((f"ref_image_{k}", r["label"], r["name"], p, len(v)))
    for k, (r, p) in sorted(auds.items()):
        v = enc_audio(p, mode) if encode else ""
        payload[f"ref_audio_{k}"] = v
        report.append((f"ref_audio_{k}", r["label"], r["name"], p, len(v)))
    if pending_tail:
        notes.append(f"尾帧未就绪：Seg{pending_tail[0]} 还没 accept（预检模式，其余参考已检查）")
    return meta, payload, report, notes


# ------------------------------------------------------------------ http
def http(ctx, method, target, body=None, timeout=60):
    url = target if target.startswith("http") else ctx.base + target
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if ctx.token:
        headers[ctx.auth_header] = ctx.auth_prefix + ctx.token
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw, code = r.read(), r.status
    except urllib.error.HTTPError as e:
        raw, code = e.read(), e.code
    except (urllib.error.URLError, OSError) as e:
        raise ConnectionError(str(e))
    txt = raw.decode("utf-8", "replace")
    try:
        js = json.loads(txt)
    except ValueError:
        js = None
    return code, js, txt


def walk(o, path=()):
    if isinstance(o, dict):
        for k, v in o.items():
            yield path + (str(k),), v
            yield from walk(v, path + (str(k),))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield path + (str(i),), v
            yield from walk(v, path + (str(i),))


def first_key(o, keys):
    for p, v in walk(o):
        if p[-1] in keys and isinstance(v, (str, int)) and not isinstance(v, bool):
            return v
    return None


def video_urls(o):
    out = []
    data = o.get("data") if isinstance(o, dict) else None
    res = data.get("results") if isinstance(data, dict) else None
    if isinstance(res, list):                                  # 已确认的返回结构：data.results[{type:"video", url}]
        out += [str(x["url"]) for x in res if isinstance(x, dict) and x.get("type") == "video" and x.get("url")]
        if out:
            return out
    for p, v in walk(o):
        if isinstance(v, str) and v.startswith(("http://", "https://", "/")):
            base = v.split("?")[0].lower()
            if base.endswith(VIDEO_EXT) or ("video" in ".".join(p).lower() and not base.endswith(IMG_EXT + (".gif",))):
                out.append(v)
    return list(dict.fromkeys(out))


def status_of(js):
    d = js.get("data") if isinstance(js, dict) else None
    if isinstance(d, dict) and d.get("status") is not None:
        return str(d["status"]).strip().lower()
    v = first_key(js, {"status", "state", "task_status", "taskStatus"}) if js is not None else None
    return None if v is None else str(v).strip().lower()


def body_mb(payload):
    return len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) / 1e6


def redact(payload):
    return {k: (f"<{len(v)} chars>" if k.startswith("ref_") else v) for k, v in payload.items()}


def jobs_append(ep_dir, row):
    os.makedirs(os.path.join(ep_dir, "06_jobs"), exist_ok=True)
    row = dict(row, ts=datetime.datetime.now().isoformat(timespec="seconds"))
    with LOCK, open(os.path.join(ep_dir, "06_jobs", "jobs.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def save_raw(ep_dir, name, text):
    d = os.path.join(ep_dir, "06_jobs", "raw")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        f.write(text)


def ffprobe(path):
    if not shutil.which("ffprobe"):
        raise Err("找不到 ffprobe/ffmpeg，请先安装并加入 PATH")
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path],
                         capture_output=True, text=True)
    if out.returncode:
        raise Err(f"ffprobe 失败：{out.stderr.strip()[:300]}")
    j = json.loads(out.stdout)
    v = next((s for s in j["streams"] if s["codec_type"] == "video"), {})
    return {"w": v.get("width"), "h": v.get("height"), "dur": float(j["format"].get("duration", 0)),
            "audio": any(s["codec_type"] == "audio" for s in j["streams"])}


# ------------------------------------------------------------------ submit / wait / download
def submit(ctx, ep_dir, n, fmt, payload, version, resolution):
    say(f"  Seg{n}/{fmt} 提交中…（请求体 {body_mb(payload):.1f} MB）")
    try:
        code, js, txt = http(ctx, "POST", SUBMIT_PATH, payload, timeout=600)
    except ConnectionError as e:
        raise Err(f"Seg{n}/{fmt} 提交时连接异常：{e}。**不要自动重试**——请先在控制台确认是否已扣费/已建任务，再决定重提")
    if code >= 400:
        raise Err(f"Seg{n}/{fmt} 提交被拒绝（HTTP {code}）：{txt[:800]}")
    tid = first_key(js, {"task_id", "taskId", "id", "job_id", "jobId"}) if js is not None else None
    save_raw(ep_dir, f"seg{n:02d}_{fmt}_submit_{int(time.time())}.json", txt)
    if tid is None:
        raise Err(f"Seg{n}/{fmt} 提交返回里找不到 task_id，原始返回：{txt[:800]}")
    jobs_append(ep_dir, {"episode": os.path.basename(ep_dir), "seg": n, "fmt": fmt, "version": version, "seed": payload["seed"],
                         "task_id": str(tid), "state": "submitted", "resolution": resolution, "duration": payload["duration"]})
    return str(tid)


def wait_and_download(ctx, ep_dir, n, fmt, tid, version, seed, interval, timeout):
    t0, seen_raw, last_st, tries_unknown = time.time(), False, object(), 0
    while True:
        try:
            code, js, txt = http(ctx, "GET", RESULT_PATH.format(task_id=tid), timeout=60)
        except ConnectionError as e:
            say(f"  Seg{n}/{fmt} 查询连接异常，稍后重试：{e}")
            time.sleep(interval)
            continue
        if code == 429 or code >= 500:
            say(f"  Seg{n}/{fmt} 查询 HTTP {code}，稍后重试")
        elif code >= 400:
            raise Err(f"Seg{n}/{fmt} 查询失败（HTTP {code}）：{txt[:500]}")
        else:
            st, urls = status_of(js), video_urls(js)
            if st != last_st:
                say(f"  Seg{n}/{fmt} [{int(time.time() - t0)}s] 状态：{st if st is not None else '（返回里没有 status 字段）'}")
                last_st = st
            if st in BAD_ST:
                save_raw(ep_dir, f"seg{n:02d}_{fmt}_{tid}_result.json", txt)
                jobs_append(ep_dir, {"seg": n, "fmt": fmt, "task_id": tid, "state": "failed", "reason": txt[:300]})
                raise Err(f"Seg{n}/{fmt} 云端任务失败：{txt[:500]}")
            if urls and (st in OK_ST or (st is not None and st not in RUN_ST) or st is None):
                save_raw(ep_dir, f"seg{n:02d}_{fmt}_{tid}_result.json", txt)
                return download(ctx, ep_dir, n, fmt, tid, version, seed, urls[0])
            if st is None and not urls:
                tries_unknown += 1
                if tries_unknown == 4 and not seen_raw:
                    seen_raw = True
                    say(f"  Seg{n}/{fmt} 返回结构我不认识，原始内容（请发给我适配）：{txt[:600]}")
        if time.time() - t0 > timeout:
            raise Err(f"Seg{n}/{fmt} 等待超过 {timeout}s，任务 {tid} 仍未完成；稍后用 `resume` 继续")
        time.sleep(interval)


def download(ctx, ep_dir, n, fmt, tid, version, seed, url):
    url = url if url.startswith("http") else urljoin(ctx.base + "/", url)
    d = os.path.join(ep_dir, "07_clips")
    os.makedirs(d, exist_ok=True)
    base = f"seg{n:02d}_{fmt}_{version}_s{seed}"
    path, i = os.path.join(d, base + ".mp4"), 1
    while os.path.exists(path):
        i += 1
        path = os.path.join(d, f"{base}_{i}.mp4")
    say(f"  Seg{n}/{fmt} 下载 → {os.path.relpath(path, ep_dir)}")
    tmp = path + ".part"
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=300) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
    except (urllib.error.URLError, OSError) as e:
        raise Err(f"Seg{n}/{fmt} 下载失败：{e}；链接 {url}")
    os.replace(tmp, path)
    info = ffprobe(path)
    warns = []
    if info["h"] and info["w"] and info["h"] <= info["w"]:
        warns.append(f"不是竖屏（{info['w']}x{info['h']}）")
    if fmt != "probe" and abs(info["dur"] - 15) > 0.6:
        warns.append(f"时长 {info['dur']:.1f}s，与预期 15s 不符")
    if not info["audio"]:
        warns.append("没有音轨")
    jobs_append(ep_dir, {"seg": n, "fmt": fmt, "task_id": tid, "state": "done", "clip": os.path.relpath(path, ep_dir),
                         "seed": seed, "version": version, "info": info, "warnings": warns})
    say(f"  Seg{n}/{fmt} 完成：{info['w']}x{info['h']}，{info['dur']:.1f}s，{'有' if info['audio'] else '无'}音轨" + (f"；⚠ {'；'.join(warns)}" if warns else ""))
    return path


# ------------------------------------------------------------------ tail frame
def sharp(path):
    try:
        from PIL import Image, ImageFilter, ImageStat
    except ImportError:
        return 0.0
    g = Image.open(path).convert("L")
    g.thumbnail((480, 480))
    return ImageStat.Stat(g.filter(ImageFilter.FIND_EDGES)).var[0]


def grab(clip, t, out):
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(t, 0):.3f}", "-i", clip, "-frames:v", "1", out],
                       capture_output=True, text=True)
    if r.returncode or not os.path.isfile(out):
        raise Err(f"ffmpeg 抽帧失败：{r.stderr.strip()[:300]}")


def extract_tail(clip, out_png, offset=None):
    dur = ffprobe(clip)["dur"]
    cdir = os.path.splitext(clip)[0] + "_tailcands"
    os.makedirs(cdir, exist_ok=True)
    files = {}
    for o in TAIL_OFFSETS:
        f = os.path.join(cdir, f"m{o:.1f}.png")
        grab(clip, dur - o, f)
        files[o] = f
    if offset is None:
        pool = [o for o in TAIL_OFFSETS if 0.5 <= o <= 1.5]
        pick = max(pool, key=lambda o: sharp(files[o])) if shutil.which("ffmpeg") else 1.0
        why = "自动：0.5–1.5s 内最清晰的一帧"
        src = files[pick]
    else:
        pick, why = offset, "手动指定"
        src = os.path.join(cdir, f"manual_{offset:.2f}.png")
        grab(clip, dur - offset, src)
    shutil.copyfile(src, out_png)
    try:
        from PIL import Image, ImageDraw
        ims = []
        for o in TAIL_OFFSETS:
            im = Image.open(files[o]).convert("RGB")
            im.thumbnail((360, 640))
            ImageDraw.Draw(im).text((8, 8), f"-{o:.1f}s" + ("  <== PICK" if o == pick else ""), fill=(255, 255, 0))
            ims.append(im)
        sheet = Image.new("RGB", (sum(i.width for i in ims), max(i.height for i in ims)))
        x = 0
        for im in ims:
            sheet.paste(im, (x, 0))
            x += im.width
        sheet.save(os.path.splitext(clip)[0] + "_tail_candidates.jpg", quality=88)
    except ImportError:
        pass
    return pick, why, dur


def ledger_row(ep_dir, row):
    os.makedirs(os.path.join(ep_dir, "06_jobs"), exist_ok=True)
    row = dict({"ts": datetime.datetime.now().isoformat(timespec="seconds"), "reasons": [], "seed": None,
                "prompt_version": "", "note": ""}, **row)
    with LOCK, open(os.path.join(ep_dir, "06_jobs", "ledger.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def latest_job(ep_dir, n, fmt=None):
    p = os.path.join(ep_dir, "06_jobs", "jobs.jsonl")
    if not os.path.isfile(p):
        return None
    for ln in reversed(open(p, encoding="utf-8").read().splitlines()):
        j = json.loads(ln)
        if j.get("seg") == n and j.get("state") == "done" and (fmt is None or j.get("fmt") == fmt):
            return j
    return None


def do_accept(ep_dir, n, clip, fmt, seed, version, tid, offset=None, note=""):
    d = os.path.join(ep_dir, "07_clips")
    shutil.copyfile(clip, os.path.join(d, f"seg{n:02d}_accepted.mp4"))
    pick, why, dur = extract_tail(clip, tail_path(ep_dir, n), offset)
    json.dump({"seg": n, "source_clip": os.path.relpath(clip, ep_dir), "clip_duration": dur, "tail_offset_from_end": pick, "how": why},
              open(os.path.join(d, f"seg{n:02d}_tail_meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    ledger_row(ep_dir, {"seg": n, "outcome": "kept", "seed": seed, "prompt_version": version, "note": note, "format": fmt, "task_id": tid,
                        "clip": os.path.relpath(clip, ep_dir)})
    say(f"  Seg{n} 已保留；尾帧取自片尾前 {pick}s（{why}）→ {os.path.relpath(tail_path(ep_dir, n), ep_dir)}")


# ------------------------------------------------------------------ auto review（抽卡排序用）
def detect_cuts(clip, thr=0.18):
    # 2026-10-15：0.28 → 0.18。E21–E30 全是暗场景（锅炉房/管廊/暴雨夜），0.28 在暗场里几乎看不见切点：
    # 80 段保留片重测，命中率 63% → 92%（暗场景 56% → 90%），命中<0.6 的段 34% → 2%，平均多余切点 0.3 → 0.7。
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", clip, "-vf", f"select='gt(scene,{thr})',metadata=print:file=-",
                        "-an", "-f", "null", "-"], capture_output=True, text=True)
    return [round(float(x), 2) for x in re.findall(r"pts_time:([0-9.]+)", r.stdout + r.stderr)]


def _gray_frames(clip, start, dur, fps=8, size=(96, 170)):
    """抽一小段的灰度小图（用于尾段稳定度）。"""
    from PIL import Image
    import tempfile
    d = tempfile.mkdtemp(prefix="h3rv_")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(start, 0):.3f}", "-t", f"{dur:.3f}", "-i", clip,
                    "-vf", f"fps={fps},scale={size[0]}:{size[1]}", os.path.join(d, "f%03d.png")], check=False)
    ims = [Image.open(os.path.join(d, f)).convert("L") for f in sorted(os.listdir(d))]
    shutil.rmtree(d, ignore_errors=True)
    return ims


def _diff(a, b):
    from PIL import ImageChops, ImageStat
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0]


def review_clip(ep_dir, n, clip, write=True):
    """自动审片：切点与规划对比、尾段稳定度、首帧承接（接力段）、技术参数 → 排序分 + 对照图。
    只衡量技术与时间结构，表演、台词、人脸是否像，仍要人看。"""
    meta = load_meta(ep_dir, n) if n else {}
    info = ffprobe(clip)
    starts = meta.get("shot_starts") or []
    planned = [x for x in starts[1:]]
    cuts = detect_cuts(clip)
    hits, errs, used = 0, [], set()
    for p in planned:
        cand = [(abs(c - p), i) for i, c in enumerate(cuts) if i not in used and abs(c - p) <= 1.2]
        if cand:
            e, i = min(cand)
            used.add(i); hits += 1; errs.append(e)
    extra = [c for i, c in enumerate(cuts) if i not in used and 0.3 < c < info["dur"] - 0.3]
    if planned:
        timing = 45 * (hits / len(planned)) * max(0.0, 1 - (sum(errs) / len(errs) if errs else 0) / 1.2)
    else:
        timing = 45.0
    timing = max(0.0, timing - 5 * len(extra))
    tail_motion = first_diff = None
    tail_s = cont_s = 0.0
    try:
        fr = _gray_frames(clip, info["dur"] - 1.5, 1.5)
        tail_motion = sum(_diff(a, b) for a, b in zip(fr, fr[1:])) / max(1, len(fr) - 1)
        tail_s = 25 * max(0.0, 1 - tail_motion / 12)
        first_ref = meta.get("refs_in_upload_order", [{}])[0] if meta else {}
        if meta and first_ref.get("backend_id") is None and first_ref.get("label") == "Picture 1":
            mm = re.search(r"Seg(\d+)", first_ref.get("name", ""))
            tp = tail_path(ep_dir, int(mm.group(1)) if mm else n - 1)
            if os.path.isfile(tp):
                from PIL import Image
                f0 = _gray_frames(clip, 0.0, 0.2)[0]
                ref = Image.open(tp).convert("L").resize(f0.size)
                first_diff = _diff(f0, ref)
                cont_s = 20 * max(0.0, 1 - first_diff / 40)
        else:
            cont_s = 20.0
    except Exception as e:                                   # Pillow 缺失等：只降级，不中断
        say(f"  （审片指标部分跳过：{e}）")
    tech_ok = bool(info["h"] and info["w"] and info["h"] > info["w"] and abs(info["dur"] - 15) <= 0.6 and info["audio"])
    score = round(timing + tail_s + cont_s + (10 if tech_ok else 0), 1)
    res = {"seg": n, "clip": os.path.relpath(clip, ep_dir), "score": score, "planned_cuts": planned, "detected_cuts": cuts,
           "cut_hits": f"{hits}/{len(planned)}", "cut_mean_err": round(sum(errs) / len(errs), 2) if errs else None,
           "extra_cuts": extra, "tail_motion": None if tail_motion is None else round(tail_motion, 2),
           "first_frame_diff": None if first_diff is None else round(first_diff, 2), "tech_ok": tech_ok,
           "parts": {"timing": round(timing, 1), "tail": round(tail_s, 1), "continuity": round(cont_s, 1), "tech": 10 if tech_ok else 0}}
    if write:
        d = os.path.join(ep_dir, "08_review")
        os.makedirs(d, exist_ok=True)
        res["sheet"] = os.path.relpath(make_sheet(clip, starts, info["dur"], os.path.join(d, os.path.splitext(os.path.basename(clip))[0] + "_sheet.jpg"), res), ep_dir)
        with LOCK, open(os.path.join(d, "review.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(res, ts=datetime.datetime.now().isoformat(timespec="seconds")), ensure_ascii=False) + "\n")
    return res


def make_sheet(clip, starts, dur, out, res):
    """对照图：每个规划镜头的中点各一帧 + 片尾一帧，标注镜头号与时间。"""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return out
    bounds = list(starts) + [dur]
    ts_ = [(f"S{i + 1} {((bounds[i] + bounds[i + 1]) / 2):.1f}s", (bounds[i] + bounds[i + 1]) / 2) for i in range(len(starts))] or \
          [(f"{t:.1f}s", t) for t in (1, 4, 7, 10, 13)]
    ts_.append((f"END {dur - 0.15:.1f}s", dur - 0.15))
    ims = []
    import tempfile
    tmp = tempfile.mkdtemp(prefix="h3sh_")
    for lab, t in ts_:
        f = os.path.join(tmp, f"{len(ims)}.png")
        grab(clip, t, f)
        im = Image.open(f).convert("RGB")
        im.thumbnail((240, 430))
        ImageDraw.Draw(im).text((6, 6), lab, fill=(255, 255, 0))
        ims.append(im)
    head = 26
    sheet = Image.new("RGB", (sum(i.width for i in ims), max(i.height for i in ims) + head), (20, 20, 20))
    ImageDraw.Draw(sheet).text((6, 6), f"{os.path.basename(clip)}  score {res['score']}  cuts {res['cut_hits']}  extra {len(res['extra_cuts'])}  "
                                       f"tail {res['tail_motion']}  first {res['first_frame_diff']}", fill=(255, 255, 255))
    x = 0
    for im in ims:
        sheet.paste(im, (x, head))
        x += im.width
    sheet.save(out, quality=88)
    shutil.rmtree(tmp, ignore_errors=True)
    return out


def print_ranking(rows):
    say("\n  自动排序（只看时间结构/尾段稳定/首帧承接/技术；表演和台词要你看）：")
    for k, r in enumerate(sorted(rows, key=lambda x: -x["score"]), 1):
        say(f"   {k}. {r['clip']}  分 {r['score']}  切点命中 {r['cut_hits']}  多余切 {len(r['extra_cuts'])}  "
            f"尾段晃动 {r['tail_motion']}  首帧差 {r['first_frame_diff']}  → {r.get('sheet', '')}")


def cmd_review(a):
    ctx = Ctx(a, need_root=False)
    ep_dir = ctx.ep_dir(a.episode)
    d = os.path.join(ep_dir, "07_clips")
    segs = a.seg or sorted({int(m.group(1)) for f in os.listdir(d) if (m := re.match(r"seg(\d+)_(en|cn)_.*\.mp4$", f))})
    for n in segs:
        clips = sorted(glob.glob(os.path.join(d, f"seg{n:02d}_*_*.mp4")))
        clips = [c for c in clips if not re.search(r"_(accepted|probe)", c)]
        if not clips:
            continue
        say(f"\nSeg{n}：{len(clips)} 条")
        print_ranking([review_clip(ep_dir, n, c) for c in clips])
    return 0


# ------------------------------------------------------------------ commands
def cmd_check(a):
    ctx = Ctx(a)
    ep_dir = ctx.ep_dir(a.episode)
    bad = 0
    say(f"根目录：{ctx.root}\n接口：{ctx.base}{SUBMIT_PATH}\n令牌：{'已设置' if ctx.token else '未设置（check 不需要，run 需要）'}")
    say("ffmpeg：" + ("OK" if shutil.which("ffmpeg") and shutil.which("ffprobe") else "找不到（抽尾帧需要）"))
    for n in all_segs(ep_dir):
        for fmt in ("en",):                    # 只检查英文（中文分镜版已停用，只作对照阅读）
            try:
                _, payload, rep, notes = build_payload(ctx, ep_dir, n, fmt, 0, RESOLUTIONS[0], 15, "data_uri", 1280, encode=False)
                imgs = sum(r[0].startswith("ref_image") for r in rep)
                auds = len(rep) - imgs
                say(f"  Seg{n} {fmt}：OK  图 {imgs}、音频 {auds}、提示词 {len(payload['prompt'])} 字符")
                for x in notes:
                    say(f"      注意 {x}")
            except Err as e:
                msg = str(e)
                if "需要 Seg" in msg and "尾帧" in msg:
                    say(f"  Seg{n} {fmt}：待上一段 accept 后才有尾帧（正常）")
                else:
                    bad += 1
                    say(f"  Seg{n} {fmt}：✗ {msg}")
    say("预检通过（尾帧类除外）" if not bad else f"有 {bad} 处问题，先解决再 run")
    return 1 if bad else 0


def new_seed():
    return random.randint(1, 2_000_000_000)


def run_one(ctx, ep_dir, n, fmt, seed, a):
    version = a.version or f"seg{n:02d}-{(load_meta(ep_dir, n).get('version') or 'v2')}-{fmt}"
    meta, payload, rep, notes = build_payload(ctx, ep_dir, n, fmt, seed, a.resolution, a.duration, a.enc, a.max_side)
    for x in notes:
        say(f"  Seg{n} 注意 {x}")
    if a.dry_run:
        d = os.path.join(ep_dir, "06_jobs")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, f"dryrun_seg{n:02d}_{fmt}.json")
        json.dump({"submit": ctx.base + SUBMIT_PATH, "payload": redact(payload),
                   "files": [{"field": r[0], "label": r[1], "name": r[2], "file": os.path.relpath(r[3], ctx.root) if r[3].startswith(ctx.root) else r[3],
                              "encoded_chars": r[4]} for r in rep]}, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        say(f"  Seg{n}/{fmt} dry-run：{len(rep)} 个参考，请求体 {body_mb(payload):.1f} MB → {os.path.relpath(p, ctx.pipe)}")
        return None
    tid = submit(ctx, ep_dir, n, fmt, payload, version, a.resolution)
    say(f"  Seg{n}/{fmt} 任务 {tid}")
    clip = wait_and_download(ctx, ep_dir, n, fmt, tid, version, seed, a.poll, a.timeout)
    return {"seg": n, "fmt": fmt, "clip": clip, "seed": seed, "version": version, "task_id": tid}


def confirm(a, count, ctx):
    if a.dry_run or a.yes:
        return
    say(f"\n即将提交 {count} 个付费任务：{a.resolution}、{a.duration}s、接口 {ctx.base}")
    if not sys.stdin.isatty():
        raise Err("非交互环境请加 --yes 确认")
    if input("确认提交？输入 y 继续 > ").strip().lower() != "y":
        raise Err("已取消")


def run_batch(ctx, ep_dir, jobs, a):
    """并行跑一批 (seg, fmt, seed)；返回 (结果列表, 错误列表)。下载后自动审片。"""
    results, errors = [], []

    def work(n, f, seed):
        try:
            r = run_one(ctx, ep_dir, n, f, seed, a)
            if r:
                try:
                    r["review"] = review_clip(ep_dir, n, r["clip"])
                except Exception as e:
                    say(f"  Seg{n}/{f} 自动审片失败（不影响片子）：{e}")
                results.append(r)
        except Err as e:
            errors.append(str(e))
            say(f"  ✗ {e}")
        except Exception as e:                      # 任何意外也要记下来，不让线程悄悄死掉
            errors.append(f"Seg{n}/{f} 意外错误：{type(e).__name__}: {e}")
            say(f"  ✗ Seg{n}/{f} 意外错误：{type(e).__name__}: {e}")
    threads = [threading.Thread(target=work, args=j) for j in jobs]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results, errors


def cmd_run(a):
    ctx = Ctx(a, need_token=not a.dry_run)
    if a.enc is None:
        a.enc = ctx.settings.get("enc", "data_uri")
        say(f"参考编码：{a.enc}" + ("（来自 probe 探测结果）" if "enc" in ctx.settings else "（默认；先跑一次 probe 可确认）"))
    if not a.dry_run and not shutil.which("ffprobe"):
        raise Err("找不到 ffmpeg/ffprobe，请先安装并加入 PATH")
    ep_dir = ctx.ep_dir(a.episode)
    fmts = ["en", "cn"] if a.fmt == "both" else [a.fmt]
    takes = max(1, a.takes)
    if a.chain:
        if a.fmt == "both":
            raise Err("链式生成只能选一种格式（--fmt en 或 cn）")
        segs = chain_segs(ep_dir, a.chain)
        if not segs:
            raise Err(f"没有链 {a.chain}")
        confirm(a, f"最多 {len(segs) * a.max_tries * takes}（链 {a.chain}：{segs}，每段每轮抽 {takes} 张、最多 {a.max_tries} 轮）", ctx)
        for n in segs:
            for rnd in range(1, a.max_tries + 1):
                seeds = [a.seed if (a.seed and rnd == 1 and k == 0) else new_seed() for k in range(takes)]
                say(f"\n=== 链 {a.chain} · Seg{n} · 第 {rnd} 轮 · 抽 {takes} 张 · seed {seeds} ===")
                res, errs = run_batch(ctx, ep_dir, [(n, a.fmt, sd) for sd in seeds], a)
                if a.dry_run:
                    say("（dry-run：后续段需要上一段尾帧，只演示第一段）")
                    return 0
                if not res:
                    say(f"Seg{n} 本轮全部失败：{errs[:1]}")
                    if rnd >= a.max_tries:
                        return 2
                    continue
                ranked = sorted(res, key=lambda r: -(r.get("review", {}).get("score", 0)))
                print_ranking([dict(r["review"]) for r in ranked if "review" in r])
                if a.auto_accept or not sys.stdin.isatty():
                    pick, reasons, ans = ranked[0], [], "a"
                else:
                    ans, reasons, idx = decide_take(len(ranked))
                    pick = ranked[idx] if ans == "a" else None
                for r in ranked:
                    if r is not pick and ans in ("a", "r", "x"):
                        ledger_row(ep_dir, {"seg": n, "outcome": "rejected", "reasons": reasons or ["other"], "seed": r["seed"],
                                            "prompt_version": r["version"], "format": a.fmt, "task_id": r["task_id"],
                                            "clip": os.path.relpath(r["clip"], ep_dir), "note": "抽卡未选中" if ans == "a" else ""})
                if ans == "a":
                    do_accept(ep_dir, n, pick["clip"], a.fmt, pick["seed"], pick["version"], pick["task_id"],
                              note=f"抽卡 {takes} 选 1，自动分 {pick.get('review', {}).get('score')}")
                    break
                if ans == "s":
                    say("已暂停，稍后用 accept / reject 决定，再继续。")
                    return 0
                if ans == "x" or rnd >= a.max_tries:
                    say(f"Seg{n} 未通过，链 {a.chain} 在此停止。")
                    return 2
        return 0
    if not a.seg:
        raise Err("请指定 --seg 或 --chain")
    seeds = {(n, k): (a.seed if (a.seed and k == 0) else new_seed()) for n in a.seg for k in range(takes)}  # 同一段同一张卡的 en / cn 共用 seed
    jobs = [(n, f, seeds[(n, k)]) for n in a.seg for k in range(takes) for f in fmts]
    confirm(a, len(jobs), ctx)
    results, errors = run_batch(ctx, ep_dir, jobs, a)
    say("\n本轮结果：")
    for n in sorted({r["seg"] for r in results}):
        rows = [r["review"] for r in results if r["seg"] == n and "review" in r]
        say(f"\nSeg{n}")
        if rows:
            print_ranking(rows)
        else:
            for r in results:
                if r["seg"] == n:
                    say(f"  {os.path.relpath(r['clip'], ep_dir)}  seed {r['seed']}")
    for e in errors:
        say("  ✗ " + e.splitlines()[0][:200])
    if results:
        say("\n看片后：python tools/h3_run.py accept <集> <段> --clip <片子路径>   或   reject <集> <段> --clip <片子路径> --reason <原因>")
    return 2 if errors else 0


def decide_take(k):
    tip = f"[1-{k}]保留第几名" if k > 1 else "[a]保留"
    ans = input(f"  {tip}  [r]全部淘汰并重抽  [x]全部淘汰并停止  [s]稍后决定 > ").strip().lower() or "s"
    idx = 0
    if ans.isdigit() and 1 <= int(ans) <= k:
        idx, ans = int(ans) - 1, "a"
    ans = ans[:1]
    reasons = []
    if ans in ("r", "x"):
        raw = input(f"  失败原因（逗号分隔，可选：{', '.join(sorted(REASONS))}；回车=other）> ").strip()
        reasons = [x.strip() for x in raw.split(",") if x.strip() in REASONS] or ["other"]
    return ans, reasons, idx


def decide():
    ans = input("  [a]保留  [r]淘汰并重做  [x]淘汰并停止  [s]稍后决定并停止 > ").strip().lower()[:1] or "s"
    reasons = []
    if ans in ("r", "x"):
        raw = input(f"  失败原因（逗号分隔，可选：{', '.join(sorted(REASONS))}；回车=other）> ").strip()
        reasons = [x.strip() for x in raw.split(",") if x.strip() in REASONS] or ["other"]
    return ans, reasons


def pick_clip(ep_dir, n, fmt, clip):
    if clip:
        for c in (clip, os.path.join(ep_dir, clip), os.path.join(ep_dir, "07_clips", os.path.basename(clip))):
            if os.path.isfile(c):
                rel = os.path.relpath(os.path.abspath(c), ep_dir)
                p = os.path.join(ep_dir, "06_jobs", "jobs.jsonl")
                rows = [json.loads(x) for x in open(p, encoding="utf-8").read().splitlines()] if os.path.isfile(p) else []
                j = next((r for r in reversed(rows) if r.get("state") == "done" and r.get("clip") == rel), {})
                return os.path.abspath(c), j
        raise Err(f"找不到片子 {clip}")
    j = latest_job(ep_dir, n, fmt)
    if not j:
        raise Err(f"Seg{n} 没有已下载的片段（先 run）")
    return os.path.join(ep_dir, j["clip"]), j


def cmd_accept(a):
    ctx = Ctx(a, need_root=False)
    ep_dir = ctx.ep_dir(a.episode)
    clip, j = pick_clip(ep_dir, a.seg, a.fmt, a.clip)
    do_accept(ep_dir, a.seg, clip, j.get("fmt", a.fmt or ""), j.get("seed"), j.get("version", ""), j.get("task_id"), a.tail_offset, a.note)
    return 0


def cmd_reject(a):
    ctx = Ctx(a, need_root=False)
    ep_dir = ctx.ep_dir(a.episode)
    reasons = [x.strip() for x in a.reason.split(",") if x.strip()]
    bad = [x for x in reasons if x not in REASONS]
    if bad or not reasons:
        raise Err(f"原因必须来自：{sorted(REASONS)}")
    clip, j = pick_clip(ep_dir, a.seg, a.fmt, a.clip)
    ledger_row(ep_dir, {"seg": a.seg, "outcome": "rejected", "reasons": reasons, "seed": j.get("seed"), "prompt_version": j.get("version", ""),
                        "format": j.get("fmt", ""), "task_id": j.get("task_id"), "clip": os.path.relpath(clip, ep_dir), "note": a.note})
    say(f"Seg{a.seg} 已记为淘汰：{reasons}")
    return 0


def cmd_tail(a):
    ctx = Ctx(a, need_root=False)
    ep_dir = ctx.ep_dir(a.episode)
    clip, _ = pick_clip(ep_dir, a.seg, a.fmt, a.clip)
    pick, why, dur = extract_tail(clip, tail_path(ep_dir, a.seg), a.tail_offset)
    say(f"尾帧 → {os.path.relpath(tail_path(ep_dir, a.seg), ep_dir)}（片尾前 {pick}s，{why}）；候选对照图：{os.path.splitext(clip)[0]}_tail_candidates.jpg")
    return 0


def cmd_resume(a):
    ctx = Ctx(a, need_root=False, need_token=True)
    ep_dir = ctx.ep_dir(a.episode)
    p = os.path.join(ep_dir, "06_jobs", "jobs.jsonl")
    if not os.path.isfile(p):
        raise Err("没有 jobs.jsonl")
    state, sub = {}, {}
    for ln in open(p, encoding="utf-8").read().splitlines():
        j = json.loads(ln)
        state[j["task_id"]] = j["state"]
        if j["state"] == "submitted":
            sub[j["task_id"]] = j
    todo = [(tid, sub[tid]) for tid, s in state.items() if s == "submitted" and tid in sub]
    if not todo:
        say("没有未完成的任务")
        return 0
    errs = []

    def work(tid, j):
        try:
            wait_and_download(ctx, ep_dir, j["seg"], j["fmt"], tid, j["version"], j["seed"], a.poll, a.timeout)
        except Err as e:
            errs.append(str(e))
            say("  ✗ " + str(e))
    ts = [threading.Thread(target=work, args=t) for t in todo]
    [t.start() for t in ts]
    [t.join() for t in ts]
    return 2 if errs else 0


def cmd_probe(a):
    """最小付费探测：1 张图、2 秒、480p；依次尝试 data_uri / raw_base64 两种编码。"""
    ctx = Ctx(a, need_token=True)
    ep_dir = ctx.ep_dir(a.episode)
    img, _ = resolve_asset(ctx, "C01")
    aud = None
    if a.with_audio:
        aud, _ = resolve_voice(ctx, "VOICE-CADE-v2-age18")
    if not a.yes:
        say(f"将提交 1–2 个最小付费任务（2 秒、{RESOLUTIONS[0]}），用来确认认证与参考编码方式。")
        if sys.stdin.isatty() and input("继续？输入 y > ").strip().lower() != "y":
            raise Err("已取消")
    for mode in ("data_uri", "raw_base64"):
        payload = {"prompt": "A young male sprinter runs along a misty track at dawn, cold blue-grey light, vertical cinematic shot.",
                   "duration": 2, "resolution": RESOLUTIONS[0], "seed": 1, "ref_image_0": enc_image(img, 1024, mode)}
        if aud:
            payload["ref_audio_0"] = enc_audio(aud, mode)
        say(f"\n— 尝试编码：{mode}")
        try:
            code, js, txt = http(ctx, "POST", SUBMIT_PATH, payload, timeout=300)
        except ConnectionError as e:
            raise Err(f"连接失败：{e}（检查 AUTODL_BASE_URL / 网络 / 代理）")
        say(f"  HTTP {code}：{txt[:500]}")
        if code in (401, 403):
            raise Err("认证失败：检查 AUTODL_TOKEN，以及 AUTODL_AUTH_HEADER / AUTODL_AUTH_PREFIX 是否与文档一致")
        tid = first_key(js, {"task_id", "taskId", "id", "job_id", "jobId"}) if js is not None else None
        if code < 400 and tid is not None:
            say(f"  ✓ {mode} 被接受，任务 {tid}，开始等待…")
            os.makedirs(os.path.join(ep_dir, "06_jobs"), exist_ok=True)
            clip = wait_and_download(ctx, ep_dir, 0, "probe", str(tid), f"probe-{mode}", 1, a.poll, a.timeout)
            st = {"enc": mode, "audio_ok": bool(aud), "base_url": ctx.base, "auth_header": ctx.auth_header, "auth_prefix": ctx.auth_prefix,
                  "probed_at": datetime.datetime.now().isoformat(timespec="seconds")}
            json.dump(st, open(os.path.join(ctx.pipe, "h3_settings.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            say(f"\n探测成功：编码方式 = {mode}；样片 {clip}\n已写入 h3_settings.json（不含令牌），之后 run 自动使用" + ("；音频字段也被接受" if aud else "；音频字段没测（加 --with-audio 再测一次）"))
            return 0
    raise Err("两种 Base64 写法都被拒绝。如果接口只收 URL，需要先把参考图/音频传到可访问的地址——把上面的返回内容发给我，我加上传步骤")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="云端 H3 出片执行器", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--pipeline", default=os.path.dirname(here), help="流水线根目录（默认：tools/ 的上一级）")
    ap.add_argument("--root", help="素材所在目录（默认：项目根，素材在 assets/ 下）")
    sp = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--pipeline", default=argparse.SUPPRESS)
        p.add_argument("--root", default=argparse.SUPPRESS)

    p = sp.add_parser("check"); common(p); p.add_argument("episode"); p.set_defaults(f=cmd_check)
    p = sp.add_parser("probe"); common(p); p.add_argument("--episode", default="E01"); p.add_argument("--with-audio", action="store_true")
    p.add_argument("--yes", action="store_true"); p.add_argument("--poll", type=float, default=8); p.add_argument("--timeout", type=int, default=900); p.set_defaults(f=cmd_probe)
    p = sp.add_parser("run"); common(p); p.add_argument("episode")
    p.add_argument("--seg", type=int, nargs="+"); p.add_argument("--chain")
    p.add_argument("--fmt", choices=["en", "cn", "both"], default="en")
    p.add_argument("--seed", type=int); p.add_argument("--version")
    p.add_argument("--resolution", default=RESOLUTIONS[0], choices=RESOLUTIONS)
    p.add_argument("--duration", type=int, default=15)
    p.add_argument("--enc", choices=["data_uri", "raw_base64"], default=None, help="参考编码；默认用 probe 探测出的写法，没有则 data_uri")
    p.add_argument("--max-side", type=int, default=1280, help="参考图长边上限（0=不缩）")
    p.add_argument("--poll", type=float, default=10); p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--dry-run", action="store_true"); p.add_argument("--yes", action="store_true")
    p.add_argument("--auto-accept", action="store_true", help="链式生成时不询问，自动保留（只用于无人值守的流程测试）")
    p.add_argument("--max-tries", type=int, default=3, help="链式生成时每段最多抽几轮")
    p.add_argument("--takes", type=int, default=1, help="抽卡：每段同时生成几张（不同 seed），自动排序后由你挑；费用 ×N")
    p.set_defaults(f=cmd_run)
    for name, fn in (("accept", cmd_accept), ("reject", cmd_reject), ("tail", cmd_tail)):
        p = sp.add_parser(name); common(p); p.add_argument("episode"); p.add_argument("seg", type=int)
        p.add_argument("--fmt", choices=["en", "cn"]); p.add_argument("--clip")
        p.add_argument("--tail-offset", type=float, help="尾帧取自片尾前多少秒（默认自动）")
        p.add_argument("--note", default="")
        if name == "reject":
            p.add_argument("--reason", required=True)
        p.set_defaults(f=fn)
    p = sp.add_parser("review"); common(p); p.add_argument("episode"); p.add_argument("--seg", type=int, nargs="+"); p.set_defaults(f=cmd_review)
    p = sp.add_parser("resume"); common(p); p.add_argument("episode"); p.add_argument("--poll", type=float, default=10); p.add_argument("--timeout", type=int, default=1800); p.set_defaults(f=cmd_resume)
    a = ap.parse_args()
    try:
        sys.exit(a.f(a) or 0)
    except Err as e:
        print("✗ " + str(e), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n已中断。已提交的任务不会丢，可用 resume 继续。", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
