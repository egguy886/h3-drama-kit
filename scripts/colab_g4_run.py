#!/usr/bin/env python3
"""Colab G4 零人工值守 H3 批量出片器（NVMe 直拉权重版）：
彻底弃用 colab drivemount（免浏览器每次一次性 OAuth 授权卡死、免 Google Drive FUSE 慢速 I/O），
直接在全新 Colab G4（RTX PRO 6000 Blackwell 98GB）实例上用 aria2c 16 线程从 HuggingFace
约 2 分钟高速拉取 42GB H3 权重至本地 NVMe 固态盘，后台守护进程逐段渲染、定期保活心跳防 Colab 20 分钟空闲回收、
每完成一段立即增量回传本地 episodes/<EP>/07_clips/，全部完成后自动执行 colab stop 销毁实例避免空跑计费。

用法（在项目根目录）：
  python3 tools/colab_g4_run.py E01 --all --dry-run      # 仅打包预检并报任务规模，不启动 GPU
  python3 tools/colab_g4_run.py E01 --seg 1 2 3 --stitch # 渲染指定段并自动无损拼接预览片
  python3 tools/colab_g4_run.py E01 --all --stitch       # 渲染整集全部段、增量回传并自动停机
"""
import argparse, glob, json, os, re, shutil, subprocess, sys, tarfile, tempfile, time

PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLAB = shutil.which("colab") or os.path.expanduser("~/.local/bin/colab")

SECTIONS = [
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
]

HF_BASE = "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main"
HF_MODELS = [
    ("vae", "minimax_h3_video_vae_int8_convrot.safetensors"),
    ("vae", "minimax_h3_audio_vae_fp32.safetensors"),
    ("diffusion_models", "minimax_h3_ref2va_pruned_int8_convrot.safetensors"),
    ("loras", "pika_h3_flex_ref2va_v1_bf16.safetensors"),
    ("text_encoders", "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"),
]


def extract_en(md):
    parts = {}
    for key, text in re.findall(r"<!-- EN:(\w+) -->\n(.*?)\n<!-- /EN -->", md, re.S):
        parts.setdefault(key, []).append(text)
    return "\n\n".join(f"{k}:\n" + "\n".join(parts[k]) for k in SECTIONS if k in parts) + "\n"


def h3_frames(sec):
    n = max(5, round(sec * 24))
    return n + (5 - (n % 17)) % 17


def find_asset(bid):
    if bid.startswith("VOICE-"):
        cands = sorted(glob.glob(os.path.join(PIPE, "assets", "voices", f"{bid}_h3_32k.wav")))
        if not cands:
            cands = sorted(glob.glob(os.path.join(PIPE, "assets", "voices", f"{bid}*.wav")))
        if not cands:
            raise SystemExit(f"找不到声线资产：{bid}")
        return cands[-1]
    cands = sorted(
        glob.glob(os.path.join(PIPE, "assets", "images", f"{bid}_*.png"))
        + glob.glob(os.path.join(PIPE, "assets", "images", f"{bid}.png"))
    )
    if not cands:
        raise SystemExit(f"找不到视觉母图资产：{bid}")
    return cands[-1]


def run_retry(cmd, retries=8, delay=5, capture=False, allow_fail=False):
    for i in range(1, retries + 1):
        r = subprocess.run(cmd, text=True, capture_output=capture)
        if r.returncode == 0:
            return r.stdout if capture else ""
        if i == retries:
            if allow_fail:
                return None
            err_tail = (r.stderr or r.stdout or "")[-400:] if capture else ""
            raise SystemExit(f"命令重试 {retries} 次仍失败：{' '.join(cmd)}\n{err_tail}")
        time.sleep(delay)


def build_bundle(ep, seg_ids, seed_base, width, height):
    ep_dir = os.path.join(PIPE, "episodes", ep)
    plan = json.load(open(os.path.join(ep_dir, "plan.json"), encoding="utf-8"))
    sec = float(plan.get("segment_sec", 15.0))
    stage = tempfile.mkdtemp(prefix=f"h3_{ep.lower()}_stage_")
    os.makedirs(os.path.join(stage, "input"), exist_ok=True)
    jobs = []
    for seg in seg_ids:
        meta_p = os.path.join(ep_dir, "05_prompts", f"seg{seg:02d}.meta.json")
        md_p = os.path.join(ep_dir, "05_prompts", f"seg{seg:02d}.bilingual.md")
        meta = json.load(open(meta_p, encoding="utf-8"))
        prompt_en = extract_en(open(md_p, encoding="utf-8").read()).strip()
        ref_imgs, ref_auds = [], []
        for r in meta["refs_in_upload_order"]:
            bid = r["backend_id"]
            src = find_asset(bid)
            fn = f"{bid}{os.path.splitext(src)[1]}"
            shutil.copy2(src, os.path.join(stage, "input", fn))
            if r["label"].startswith("Picture"):
                ref_imgs.append({"label": r["label"], "backend_id": bid, "file": fn})
            else:
                ref_auds.append({"label": r["label"], "backend_id": bid, "file": fn})
        res_tag = f"{height}p" if width >= height else f"{width}p"
        jobs.append({
            "job_id": f"{ep}_Seg{seg:02d}_{res_tag}",
            "seg": seg,
            "seconds": sec,
            "frames": h3_frames(sec),
            "width": width,
            "height": height,
            "seed": seed_base + seg,
            "prompt": prompt_en,
            "ref_images": ref_imgs,
            "ref_audios": ref_auds,
        })
    json.dump(jobs, open(os.path.join(stage, "jobs.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    tar_path = os.path.join(tempfile.gettempdir(), f"h3_{ep.lower()}_nvme_bundle.tar.gz")
    with tarfile.open(tar_path, "w:gz") as tf:
        tf.add(stage, arcname="h3_stage")
    shutil.rmtree(stage, ignore_errors=True)
    return tar_path, jobs


REMOTE_SETUP = f"""import os, subprocess, tarfile, shutil, time, urllib.request
print('GPU:', subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader']).decode().strip(), flush=True)
subprocess.run(['apt-get', 'update', '-qq'], check=False)
subprocess.run(['apt-get', 'install', '-y', '-qq', 'aria2'], check=True)
if not os.path.exists('/content/ComfyUI'):
    subprocess.run(['git', 'clone', '--depth', '1', 'https://github.com/comfyanonymous/ComfyUI', '/content/ComfyUI'], check=True)
    subprocess.run(['pip', 'install', '-r', '/content/ComfyUI/requirements.txt', '-q'], check=True)
with tarfile.open('/content/h3_nvme_bundle.tar.gz') as tf:
    tf.extractall('/content')
os.makedirs('/content/ComfyUI/input', exist_ok=True)
for fn in os.listdir('/content/h3_stage/input'):
    shutil.copy2(f'/content/h3_stage/input/{{fn}}', f'/content/ComfyUI/input/{{fn}}')
for cat, fname in {HF_MODELS!r}:
    dst_dir = f'/content/ComfyUI/models/{{cat}}'
    os.makedirs(dst_dir, exist_ok=True)
    dst_p = f'{{dst_dir}}/{{fname}}'
    if not (os.path.exists(dst_p) and os.path.getsize(dst_p) > 10_000_000):
        t0 = time.time()
        print(f'[DL] {{cat}}/{{fname}} ...', flush=True)
        subprocess.run(['aria2c', '-x', '16', '-s', '16', '-k', '16M', '--console-log-level=warn', '-d', dst_dir, '-o', fname, f'{HF_BASE}/{{cat}}/{{fname}}'], check=True)
        print(f'[OK] {{cat}}/{{fname}} in {{time.time()-t0:.1f}}s', flush=True)
up = False
try:
    up = urllib.request.urlopen('http://127.0.0.1:8188/system_stats', timeout=2).status == 200
except Exception:
    pass
if not up:
    subprocess.Popen(['python3', '/content/ComfyUI/main.py', '--listen', '0.0.0.0', '--port', '8188', '--preview-method', 'auto'],
                     stdout=open('/content/comfyui.log', 'w'), stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(90):
        time.sleep(1)
        try:
            if urllib.request.urlopen('http://127.0.0.1:8188/system_stats', timeout=2).status == 200:
                up = True; break
        except Exception:
            pass
if not up:
    raise SystemExit('ComfyUI 启动超时')
print('COMFY_NVME_READY', flush=True)
"""

REMOTE_DAEMON = """import subprocess, time
code = '''import json, urllib.request, urllib.error, time, os, shutil

jobs = json.load(open('/content/h3_stage/jobs.json', encoding='utf-8'))
local_out = '/content/h3_done'
os.makedirs(local_out, exist_ok=True)
status_path = '/content/h3_render_status.json'

def save(d):
    with open(status_path + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(status_path + '.tmp', status_path)

state = {"started_at": time.time(), "total_jobs": len(jobs), "done_jobs": [], "current_job": None, "finished": False, "error": None}
save(state)

for job in jobs:
    jid = job["job_id"]
    state["current_job"] = jid; save(state)
    dst = os.path.join(local_out, f"{jid}.mp4")
    if os.path.exists(dst) and os.path.getsize(dst) > 500000:
        state["done_jobs"].append({"job_id": jid, "file": f"{jid}.mp4", "elapsed_s": 0}); save(state); continue
    g = {
        "151": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_int8_convrot.safetensors"}},
        "152": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
        "158": {"class_type": "UNETLoader", "inputs": {"unet_name": "minimax_h3_ref2va_pruned_int8_convrot.safetensors", "weight_dtype": "default"}},
        "165": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["158", 0], "lora_name": "pika_h3_flex_ref2va_v1_bf16.safetensors", "strength_model": 1.0}},
        "159": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "type": "minimax", "device": "default"}},
        "157": {"class_type": "BasicGuider", "inputs": {"model": ["165", 0], "conditioning": ["162", 0]}},
        "160": {"class_type": "RandomNoise", "inputs": {"noise_seed": job["seed"]}},
        "155": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "lcm"}},
        "166": {"class_type": "ManualSigmas", "inputs": {"sigmas": "1.0, 0.972973, 0.923077, 0.8, 0.571429, 0.333333, 0.0"}},
        "156": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["160", 0], "guider": ["157", 0], "sampler": ["155", 0], "sigmas": ["166", 0], "latent_image": ["162", 1]}},
        "154": {"class_type": "VAEDecode", "inputs": {"samples": ["156", 0], "vae": ["151", 0]}},
        "153": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["156", 0], "vae": ["152", 0]}},
        "161": {"class_type": "CreateVideo", "inputs": {"images": ["154", 0], "audio": ["153", 0], "fps": 24.0, "bit_depth": "auto", "color_space": "sRGB", "chroma_subsampling": "auto", "codec": "none"}},
        "92": {"class_type": "SaveVideo", "inputs": {"video": ["161", 0], "filename_prefix": f"video/{jid}", "format": "auto", "format.codec": "auto"}},
    }
    h3_in = {"clip": ["159", 0], "vae": ["151", 0], "audio_vae": ["152", 0], "prompt": job["prompt"], "width": job["width"], "height": job["height"], "length": int(job["frames"]), "ref_image_size": "match"}
    for i, im in enumerate(job["ref_images"]):
        nid = str(200 + i); g[nid] = {"class_type": "LoadImage", "inputs": {"image": im["file"]}}; h3_in[f"ref_images.ref_image_{i}"] = [nid, 0]
    for i, au in enumerate(job["ref_audios"]):
        nid = str(300 + i); g[nid] = {"class_type": "LoadAudio", "inputs": {"audio": au["file"]}}; h3_in[f"ref_audios.ref_audio_{i}"] = [nid, 0]
    g["162"] = {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": h3_in}
    req = urllib.request.Request("http://127.0.0.1:8188/prompt", data=json.dumps({"prompt": g, "client_id": jid}).encode(), headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        pid = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())["prompt_id"]
    except urllib.error.HTTPError as e:
        state["error"] = f"{jid}: HTTP {e.code} {e.read().decode()}"; save(state); raise SystemExit(1)
    while True:
        time.sleep(15)
        h = json.loads(urllib.request.urlopen(f"http://127.0.0.1:8188/history/{pid}", timeout=10).read().decode())
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("status_str") != "success":
                state["error"] = f"{jid}: {json.dumps(st)}"; save(state); raise SystemExit(1)
            outs = h[pid].get("outputs", {}).get("92", {})
            for it in outs.get("images", []) + outs.get("videos", []):
                src = os.path.join("/content/ComfyUI/output", it.get("subfolder", ""), it["filename"])
                shutil.copy2(src, dst)
                state["done_jobs"].append({"job_id": jid, "file": f"{jid}.mp4", "elapsed_s": int(time.time() - t0)}); save(state)
            break

state["current_job"] = None; state["finished"] = True; save(state)
'''
open('/content/daemon_h3.py', 'w', encoding='utf-8').write(code)
subprocess.Popen(['python3', '/content/daemon_h3.py'], stdout=open('/content/h3_render.log', 'w'), stderr=subprocess.STDOUT, start_new_session=True)
time.sleep(2)
print('DAEMON_STARTED', flush=True)
"""

REMOTE_CHECK = """import os
print(open('/content/h3_render_status.json').read())
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("episode", help="集号，如 E01")
    ap.add_argument("--seg", nargs="+", type=int, help="指定段号列表")
    ap.add_argument("--all", action="store_true", help="渲染整集全部段")
    ap.add_argument("--session", default="h3-g4-nvme", help="Colab 会话名")
    ap.add_argument("--seed-base", type=int, default=2026112200)
    ap.add_argument("--poll-sec", type=int, default=90, help="保活巡检与增量回传间隔秒数（必须 <600s 防 Colab 空闲回收）")
    ap.add_argument("--stitch", action="store_true", help="跑完后用 ffmpeg 自动无损拼接本批预览片")
    ap.add_argument("--keep-alive", action="store_true", help="调试用：跑完后保留实例不自动 stop（默认必自动销毁）")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    ep = a.episode.upper()
    plan = json.load(open(os.path.join(PIPE, "episodes", ep, "plan.json"), encoding="utf-8"))
    aspect = plan.get("aspect", "16:9")
    width, height = (1344, 768) if aspect == "16:9" else (768, 1344)
    seg_ids = [s["id"] for s in plan["segments"]] if a.all else (a.seg or [1])
    tar_path, jobs = build_bundle(ep, seg_ids, a.seed_base, width, height)
    est_min = round(len(jobs) * 7.8 + 2.5)
    print(f"已打包 {ep} 共 {len(jobs)} 段（{width}x{height}，每段 {jobs[0]['seconds']}s）→ {tar_path}（{os.path.getsize(tar_path)/1024/1024:.2f} MB），预估 G4 总耗时约 {est_min} 分钟。")
    if a.dry_run:
        return

    if not os.path.exists(COLAB):
        raise SystemExit(f"未找到 colab CLI：{COLAB}")

    tmp = tempfile.gettempdir()
    setup_f = os.path.join(tmp, f"setup_{ep.lower()}.py"); open(setup_f, "w", encoding="utf-8").write(REMOTE_SETUP)
    daemon_f = os.path.join(tmp, f"daemon_{ep.lower()}.py"); open(daemon_f, "w", encoding="utf-8").write(REMOTE_DAEMON)
    check_f = os.path.join(tmp, f"check_{ep.lower()}.py"); open(check_f, "w", encoding="utf-8").write(REMOTE_CHECK)
    out_dir = os.path.join(PIPE, "episodes", ep, "07_clips")
    os.makedirs(out_dir, exist_ok=True)
    downloaded = set()

    try:
        subprocess.run([COLAB, "stop", "-s", a.session], capture_output=True)
        run_retry([COLAB, "new", "-s", a.session, "--gpu", "G4"])
        run_retry([COLAB, "upload", "-s", a.session, tar_path, "/content/h3_nvme_bundle.tar.gz"])
        run_retry([COLAB, "exec", "-s", a.session, "-f", setup_f, "--timeout", "600"])
        run_retry([COLAB, "exec", "-s", a.session, "-f", daemon_f, "--timeout", "60"])

        miss_streak = 0
        while True:
            time.sleep(a.poll_sec)
            raw = run_retry([COLAB, "exec", "-s", a.session, "-f", check_f, "--timeout", "30"], retries=4, delay=4, capture=True, allow_fail=True)
            if not raw:
                miss_streak += 1
                print(f"[巡检网络抖动重试 {miss_streak}/6] 等待下一轮保活巡检...", flush=True)
                if miss_streak >= 6:
                    raise SystemExit("连续 6 轮无法连接 Colab 实例，终止并触发自动关机")
                continue
            miss_streak = 0
            m = re.search(r"\{.*\}", raw, re.S)
            if not m:
                continue
            st = json.loads(m.group(0))
            for d in st.get("done_jobs", []):
                fn = d["file"]
                if fn not in downloaded:
                    run_retry([COLAB, "download", "-s", a.session, f"/content/h3_done/{fn}", os.path.join(out_dir, fn)])
                    downloaded.add(fn)
                    print(f"[回传完成 {len(downloaded)}/{len(jobs)}] {os.path.join(out_dir, fn)}（耗时 {d['elapsed_s']}s）", flush=True)
            if st.get("error"):
                raise SystemExit(f"远端渲染报错：{st['error']}")
            if st.get("finished"):
                break
            print(f"[运行中 {len(downloaded)}/{len(jobs)}] 当前段：{st.get('current_job')}", flush=True)

        if a.stitch and len(jobs) > 1:
            lst = os.path.join(tmp, f"concat_{ep.lower()}.txt")
            with open(lst, "w", encoding="utf-8") as fh:
                for j in jobs:
                    fh.write(f"file '{os.path.join(out_dir, j['job_id'] + '.mp4')}'\n")
            prev = os.path.join(out_dir, f"{ep}_Seg{seg_ids[0]:02d}-{seg_ids[-1]:02d}_preview.mp4")
            subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", prev], check=True)
            print(f"[拼接完成] {prev}", flush=True)
    finally:
        if not a.keep_alive:
            for attempt in range(1, 11):
                subprocess.run([COLAB, "stop", "-s", a.session])
                chk = subprocess.run([COLAB, "sessions"], text=True, capture_output=True)
                out = (chk.stdout or "") + (chk.stderr or "")
                print(out.strip(), flush=True)
                if chk.returncode == 0 and ("No active sessions" in out or a.session not in out):
                    print(f"[安全停机已确认] 会话 {a.session} 已销毁。", flush=True)
                    break
                time.sleep(5)


if __name__ == "__main__":
    main()
