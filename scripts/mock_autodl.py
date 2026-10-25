#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mock_autodl.py — 本地模拟 AutoDL.Art 的 minimax_h3_zm_u24 接口，用来演练 h3_run.py（不花钱、不联网）

两个用途：
  1) 造一棵假的素材目录（和真实目录同结构，图是占位 PNG，音频是静音 WAV）：
       python tools/mock_autodl.py fixture <目录>
  2) 起一个假服务器（默认 127.0.0.1:8765）：
       python tools/mock_autodl.py serve --accept both --token TEST

      然后另开终端：
       set AUTODL_BASE_URL=http://127.0.0.1:8765   (Linux/mac 用 export)
       set AUTODL_TOKEN=TEST
       python tools/h3_run.py run E01 --seg 1 --root <假素材目录> --yes --poll 1

注意：这只是**按文档字段**写的模拟（提交字段、分辨率枚举、参考数量上限、编码三选一），
返回 JSON 的外形是我猜的。真实接口返回什么，以第一次 `probe` 的原始返回为准。
"""
import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RES = {"480p竖": (480, 848), "768p竖": (768, 1360), "480p横": (848, 480), "768p横": (1360, 768),
       "480p(1:1)": (480, 480), "768p(1:1)": (768, 768)}
TASKS, LOCK = {}, threading.Lock()
CFG = {}


# ------------------------------------------------------------------ fixture
def make_fixture(dst):
    from PIL import Image, ImageDraw
    here = os.path.dirname(os.path.abspath(__file__))
    pipe = os.path.dirname(here)
    man = json.load(open(os.path.join(pipe, "assets_manifest.json"), encoding="utf-8"))
    n = 0
    for i, a in enumerate(man["assets"]):
        p = os.path.join(dst, a["resolved_path"])
        os.makedirs(os.path.dirname(p), exist_ok=True)
        big = a["type"] != "prop"                          # 人物/场景做大图，测缩图；道具小图
        im = Image.new("RGB", (1536, 2048) if big else (512, 512), ((i * 37) % 255, (i * 91) % 255, (i * 53) % 255))
        ImageDraw.Draw(im).text((20, 20), a["id"] + " " + a.get("name", ""), fill=(255, 255, 255))
        im.save(p)
        n += 1
    vd = os.path.join(dst, "13_短剧生产", "声音参考")
    os.makedirs(vd, exist_ok=True)
    vm = json.load(open(os.path.join(pipe, "voices.json"), encoding="utf-8"))
    for v in vm["voices"]:
        name = v.get("ref_audio") or ("VOICE_%s_%s_h3_32k.wav" % (v["character"].upper().replace(" ", "_").replace(".", ""), v["voice_id"].split("-")[2].lower()))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=5", "-ar", "32000", "-ac", "1",
                        os.path.join(vd, name)], check=True)
    print(f"假素材已生成：{n} 张图 + {len(vm['voices'])} 条音频 → {dst}")


# ------------------------------------------------------------------ video
def make_video(path, seconds, w, h):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate=24:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", path], check=True)


# ------------------------------------------------------------------ server
def decode(v, field):
    """返回 (字节, 编码方式)；不合法抛 ValueError"""
    if not isinstance(v, str) or not v:
        raise ValueError(f"{field} 为空")
    if v.startswith("data:"):
        m = re.match(r"data:([\w/+.-]+);base64,(.*)$", v, re.S)
        if not m:
            raise ValueError(f"{field} data-URI 格式错误")
        return base64.b64decode(m.group(2)), "data_uri"
    if v.startswith(("http://", "https://")):
        raise ValueError(f"{field} 是 URL（模拟器不抓取）")
    return base64.b64decode(v, validate=True), "raw_base64"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def authed(self):
        got = self.headers.get(CFG["auth_header"], "")
        return got == CFG["auth_prefix"] + CFG["token"]

    def do_POST(self):
        ln = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(ln)
        if not self.path.endswith("/comfyui_workflow/minimax_h3_zm_u24"):
            return self.send(404, {"code": 404, "msg": "no such workflow"})
        if not self.authed():
            return self.send(401, {"code": 401, "msg": "invalid token"})
        try:
            js = json.loads(body)
        except ValueError:
            return self.send(400, {"code": 400, "msg": "bad json"})
        err = []
        p = js.get("prompt")
        if not isinstance(p, str) or not 1 <= len(p) <= 10000:
            err.append("prompt 必填，1–10000 字符")
        d = js.get("duration", 5)
        if not isinstance(d, int) or not 1 <= d <= 15:
            err.append("duration 1–15 整数")
        res = js.get("resolution", "768p竖")
        if res not in RES:
            err.append(f"resolution 必须是 {list(RES)}")
        if "seed" in js and not isinstance(js["seed"], int):
            err.append("seed 必须是整数")
        fields = {}
        for k, v in js.items():
            m = re.match(r"ref_(image|audio)_(\d)$", k)
            if not m:
                if k not in ("prompt", "duration", "resolution", "seed"):
                    err.append(f"未知字段 {k}")
                continue
            kind, i = m.group(1), int(m.group(2))
            if (kind == "image" and i > 8) or (kind == "audio" and i > 2):
                err.append(f"{k} 超出编号范围")
                continue
            try:
                raw, enc = decode(v, k)
            except Exception as e:
                err.append(str(e))
                continue
            if enc not in (CFG["accept"], "both") and CFG["accept"] != "both":
                err.append(f"{k}：模拟器只接受 {CFG['accept']}，收到 {enc}")
                continue
            if kind == "image" and not (raw[:8] == b"\x89PNG\r\n\x1a\n" or raw[:2] == b"\xff\xd8" or raw[:4] == b"RIFF"):
                err.append(f"{k} 不是 JPG/PNG/WebP")
            if kind == "audio" and not (raw[:4] == b"RIFF" or raw[:3] == b"ID3" or raw[:4] == b"fLaC" or raw[4:8] == b"ftyp" or raw[:2] == b"\xff\xfb"):
                err.append(f"{k} 不是 MP3/WAV/MP4/FLAC")
            fields[k] = {"enc": enc, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        if "ref_image_0" not in js:
            err.append("ref_image_0 必填")
        if err:
            return self.send(400, {"code": 400, "msg": "; ".join(err)})
        with LOCK:
            tid = "T%04d" % (len(TASKS) + 1)
            TASKS[tid] = {"polls": 0, "dur": d, "res": res}
        with open(CFG["log"], "a", encoding="utf-8") as f:
            f.write(json.dumps({"task": tid, "duration": d, "resolution": res, "seed": js.get("seed"), "prompt_head": p[:60], "fields": fields,
                                "body_mb": round(len(body) / 1e6, 2)}, ensure_ascii=False) + "\n")
        self.send(200, {"code": 0, "msg": "ok", "data": {"task_id": tid}})

    def do_GET(self):
        if self.path.startswith("/files/"):
            fp = os.path.join(CFG["out"], os.path.basename(self.path))
            if not os.path.isfile(fp):
                return self.send(404, {"msg": "nf"})
            b = open(fp, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        m = re.search(r"/comfyui_workflow/result/(\w+)$", self.path)
        if not m:
            return self.send(404, {"msg": "nf"})
        if not self.authed():
            return self.send(401, {"code": 401, "msg": "invalid token"})
        t = TASKS.get(m.group(1))
        if not t:
            return self.send(404, {"code": 404, "msg": "task not found"})
        t["polls"] += 1
        if CFG["fail_task"] == m.group(1):
            return self.send(200, {"code": 0, "data": {"task_id": m.group(1), "status": "FAILED", "error": "mock failure"}})
        if t["polls"] <= CFG["running_polls"]:
            return self.send(200, {"code": 0, "data": {"task_id": m.group(1), "status": "RUNNING"}})
        w, h = RES[t["res"]]
        fp = os.path.join(CFG["out"], f"{m.group(1)}.mp4")
        if not os.path.isfile(fp):
            make_video(fp, t["dur"], w, h)
        return self.send(200, {"code": 0, "data": {"task_id": m.group(1), "status": "SUCCESS", "results": [{"type": "video", "url": f"/files/{m.group(1)}.mp4"}]}})


def serve(a):
    CFG.update(accept=a.accept, token=a.token, auth_header=a.auth_header, auth_prefix=a.auth_prefix, running_polls=a.running_polls,
               fail_task=a.fail_task, out=os.path.abspath(a.out), log=os.path.abspath(a.log))
    os.makedirs(CFG["out"], exist_ok=True)
    print(f"mock AutoDL @ http://{a.host}:{a.port}  accept={a.accept} token={a.token} log={CFG['log']}", flush=True)
    ThreadingHTTPServer((a.host, a.port), H).serve_forever()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("fixture"); p.add_argument("dst"); p.set_defaults(f=lambda a: make_fixture(a.dst))
    p = sp.add_parser("serve")
    p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=8765)
    p.add_argument("--accept", choices=["data_uri", "raw_base64", "both"], default="both")
    p.add_argument("--token", default="TEST"); p.add_argument("--auth-header", default="Authorization"); p.add_argument("--auth-prefix", default="Bearer ")
    p.add_argument("--running-polls", type=int, default=2); p.add_argument("--fail-task", default="")
    p.add_argument("--out", default="mock_out"); p.add_argument("--log", default="mock_requests.jsonl")
    p.set_defaults(f=serve)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
