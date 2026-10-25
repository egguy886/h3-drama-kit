#!/usr/bin/env python3
"""Seed-VC 启动器：新版 torchaudio 的 save 需要 torchcodec，这里改用 soundfile 写文件，不改 seed-vc 源码。
用法（在 seed-vc 目录下，用 .venv 的 python）：python ../run_vc.py --source ... --target ... --output ... [inference.py 的其它参数]
"""
import os, sys, runpy
import soundfile as sf, torch, torchaudio

def _save(path, src, sample_rate, *a, **k):
    x = src.detach().cpu().float()
    x = x.t().numpy() if x.dim() == 2 else x.numpy()
    sf.write(str(path), x, int(sample_rate), subtype="PCM_16")
torchaudio.save = _save
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
sys.path.insert(0, os.getcwd())
sys.argv = ["inference.py"] + sys.argv[1:]
runpy.run_path("inference.py", run_name="__main__")
