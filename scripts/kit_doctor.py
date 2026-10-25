#!/usr/bin/env python3
"""环境自检（只读、免费）：python 版本、ffmpeg/ffprobe、Pillow/numpy、Whisper、声线统一环境、AutoDL 令牌是否就位（不打印令牌）。

用法：python3 tools/kit_doctor.py
"""
import importlib.util, json, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__)); PIPE = os.path.dirname(HERE)
ok = lambda b: "✅" if b else "❌"
rows = []


def have_mod(m):
    return importlib.util.find_spec(m) is not None


rows.append(("Python ≥ 3.9", sys.version_info >= (3, 9), sys.version.split()[0], "必需"))
for b in ("ffmpeg", "ffprobe"):
    rows.append((b, bool(shutil.which(b)), shutil.which(b) or "brew install ffmpeg", "必需（出片质检、拼接、字幕）"))
rows.append(("Pillow", have_mod("PIL"), "pip3 install pillow", "必需（缩图、对照图、字幕铭牌）"))
rows.append(("numpy", have_mod("numpy"), "pip3 install numpy", "必需（拼接、动作量、声线）"))
rows.append(("whisper（openai-whisper）", bool(shutil.which("whisper")), "pip3 install -U openai-whisper", "台词核对、字幕时间轴"))
vc = os.path.join(HERE, "voiceconv")
rows.append(("声线统一环境 tools/voiceconv/.venv + seed-vc", os.path.isfile(os.path.join(vc, ".venv", "bin", "python")) and os.path.isdir(os.path.join(vc, "seed-vc")),
             "见 playbook/08_后期合成与交付.md §声线统一", "后期统一声线（可选，但推荐）"))
ocr = os.path.join(HERE, "ocr", "ocr")
rows.append(("OCR（H3 自带字幕检测）", os.path.isfile(ocr), "swiftc -O tools/ocr/ocr.swift -o tools/ocr/ocr", "批量出片质检（macOS，可选）"))
tok = any(os.environ.get(k) for k in ("AUTODL_TOKEN", "AUTODL_API_KEY"))
envf = os.path.join(PIPE, ".env")
if not tok and os.path.isfile(envf):
    tok = any(l.strip().startswith(("AUTODL_TOKEN=", "AUTODL_API_KEY=")) and l.split("=", 1)[1].strip() for l in open(envf, encoding="utf-8"))
rows.append(("AutoDL 令牌（环境变量或 .env）", tok, "在 .env 写 AUTODL_TOKEN=…（不要提交、不要发给别人）", "付费出片必需"))
pj = os.path.join(PIPE, "project.json")
rows.append(("project.json", os.path.isfile(pj), "用 new_project.py 建项目会自动生成", "必需"))
for f in ("library/cast.json", "library/scenes.json", "library/styles.json", "voices.json"):
    rows.append((f, os.path.isfile(os.path.join(PIPE, f)), "模板里有示例", "必需"))
free = shutil.disk_usage(PIPE).free / 2**30
rows.append((f"磁盘可用 {free:.1f} GB", free >= 5, "每段约 11 MB + 尾帧/对照图；低于 2.5 GB 批量出片会自动停", "建议 ≥5 GB"))

w = max(len(r[0]) for r in rows)
for name, good, hint, why in rows:
    print(f"{ok(good)} {name.ljust(w)}  {'' if good else '→ ' + hint}  （{why}）")
bad = [r for r in rows if not r[1] and r[3].startswith("必需")]
print("\n" + ("全部必需项就绪。" if not bad else f"有 {len(bad)} 个必需项没就绪。"))
sys.exit(1 if bad else 0)
