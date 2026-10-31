#!/usr/bin/env python3
"""提前备好字幕：给每集最新成片做 Whisper 词级转写，再出 SRT 和铭牌预览（不烧录，不花钱）。
已有 _words.json 且比成片新的集跳过转写。某集重拼后再跑一次，只重做这一集。
用法（项目根目录）：python3 tools/prep_subs.py [E01 E02 …] [-j 3]
"""
import glob, json, os, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WH = shutil.which("whisper") or "/opt/homebrew/bin/whisper"


def collapsed(path, n=5):
    run, last = 0, None
    for seg in json.load(open(path, encoding="utf-8"))["segments"]:
        for w in seg["words"]:
            run = run + 1 if w["start"] == last else 1; last = w["start"]
            if run >= n: return True
    return False


def one(ep):
    ed = os.path.join(PIPE, "episodes", ep, "08_edit")
    cut = max((c for c in glob.glob(f"{ed}/{ep}_cut_*.mp4") if not c.endswith("_subs.mp4")), key=os.path.getmtime)
    base = os.path.basename(cut)[:-4]; words = f"{ed}/{base}_words.json"
    if not os.path.isfile(words) or os.path.getmtime(words) < os.path.getmtime(cut):
        with tempfile.TemporaryDirectory() as td:
            subprocess.run([WH, cut, "--model", "small", "--language", "en", "--word_timestamps", "True", "--output_format", "json",
                            "--output_dir", td, "--fp16", "False", "--threads", "3"], check=True, capture_output=True)
            shutil.move(f"{td}/{base}.json", words)
        if collapsed(words):                     # Whisper 偶尔把一串词压到同一时间点（E38），关掉上下文重转
            with tempfile.TemporaryDirectory() as td:
                subprocess.run([WH, cut, "--model", "small", "--language", "en", "--word_timestamps", "True", "--output_format", "json",
                                "--output_dir", td, "--fp16", "False", "--threads", "3", "--condition_on_previous_text", "False"], check=True, capture_output=True)
                shutil.move(f"{td}/{base}.json", words)
    r = subprocess.run([sys.executable, "tools/subtitle_episode.py", ep, "--video", f"08_edit/{base}.mp4", "--words", words, "--prep"],
                       cwd=PIPE, capture_output=True, text=True)
    print(r.stdout.strip().splitlines()[-1] if r.returncode == 0 and r.stdout.strip() else f"{ep} ❌ {r.stderr.strip()[-300:]}", flush=True)


args = sys.argv[1:]; j = 3
if "-j" in args:
    k = args.index("-j"); j = int(args[k + 1]); del args[k:k + 2]
eps = args or [f"E{n:02d}" for n in range(1, 61)]
with ThreadPoolExecutor(j) as ex:
    list(ex.map(one, eps))
print("字幕准备结束")
