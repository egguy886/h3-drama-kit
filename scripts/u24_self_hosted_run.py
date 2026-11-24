#!/usr/bin/env python3
"""《沉香如局》自建原生 ComfyUI 首要生产客户端（API-U24-文武双修T8版 · 16:9 1312×736 / 9:16 736×1312）

适配通过 `tools/deploy_self_hosted_u24.sh` 部署的任意标准原生 ComfyUI 实例（AutoDL / RunPod / 本地 4090D·5090·6000Ada / Colab 隧道），
无需第三方 zealman 面板封装，仅依赖原生 ComfyUI 核心节点 + `T8mars/comfyui-minimax-h3-audio-T8`。

用法（在 04_H3横版短剧工程 根目录运行）：
  python3 tools/u24_self_hosted_run.py status --url http://127.0.0.1:8188
  python3 tools/u24_self_hosted_run.py run E81 --all --url http://127.0.0.1:8188
  python3 tools/u24_self_hosted_run.py run E81 --seg 1 2 --url http://127.0.0.1:8188
  python3 tools/u24_self_hosted_run.py run-jobs episodes/E81_Exp2_PureDirector/jobs.json --out episodes/E81_Exp2_U24/07_clips --url http://127.0.0.1:8188
"""
import argparse, glob, hashlib, json, os, re, subprocess, sys, time, urllib.error, urllib.parse, urllib.request

PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_P = os.path.join(PIPE, "u24_self_upload_cache.json")

SECTIONS = [
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
]


def extract_en(md: str) -> str:
    parts = {}
    for key, text in re.findall(r"<!-- EN:(\w+) -->\n(.*?)\n<!-- /EN -->", md, re.S):
        parts.setdefault(key, []).append(text)
    if parts:
        return "\n\n".join(f"{k}:\n" + "\n".join(parts[k]) for k in SECTIONS if k in parts) + "\n"
    return md.strip() + "\n"


def h3_frames(sec: float) -> int:
    n = max(5, round(sec * 24))
    return n + (5 - (n % 17)) % 17


def find_asset(bid: str) -> str:
    if bid.startswith("VOICE-"):
        cands = sorted(glob.glob(os.path.join(PIPE, "assets", "voices", f"{bid}_h3_32k.wav")))
        if not cands:
            cands = sorted(glob.glob(os.path.join(PIPE, "assets", "voices", f"{bid}*.wav")))
        if not cands:
            raise SystemExit(f"缺少音色参考资产: {bid}")
        return cands[-1]
    cands = sorted(
        glob.glob(os.path.join(PIPE, "assets", "images", f"{bid}_*.png"))
        + glob.glob(os.path.join(PIPE, "assets", "images", f"{bid}.png"))
    )
    if not cands:
        raise SystemExit(f"缺少图片参考资产: {bid}")
    return cands[-1]


def http_json(url: str, payload=None, timeout: int = 30):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def upload_input_file(base_url: str, local_path: str, remote_name: str) -> str:
    """使用标准 ComfyUI `/upload/image` 上传 PNG 或 WAV 到 ComfyUI `input/` 目录（按 base_url + sha256 去重缓存）。"""
    cache = json.load(open(CACHE_P, encoding="utf-8")) if os.path.isfile(CACHE_P) else {}
    ck = f"{base_url}::{sha256_file(local_path)}"
    if ck in cache:
        return cache[ck]
    r = subprocess.run(
        [
            "curl", "-sS", "-m", "180", "-X", "POST", f"{base_url}/upload/image",
            "-F", f"image=@{local_path};filename={remote_name}",
            "-F", "type=input",
            "-F", "overwrite=true",
        ],
        stdin=subprocess.DEVNULL, capture_output=True, text=True,
    )
    try:
        d = json.loads(r.stdout)
    except Exception:
        raise SystemExit(f"上传失败 {local_path}: {r.stdout[:200]} {r.stderr[:200]}")
    if "name" not in d:
        raise SystemExit(f"上传返回异常 {local_path}: {d}")
    name = d["name"] if not d.get("subfolder") else f"{d['subfolder']}/{d['name']}"
    cache[ck] = name
    json.dump(cache, open(CACHE_P, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return name


def resolve_upscaler_name(base_url: str) -> str:
    oi = http_json(f"{base_url}/object_info/MiniMaxH3LearnedLatentUpscaleT8Advanced", timeout=20)
    opts = oi["MiniMaxH3LearnedLatentUpscaleT8Advanced"]["input"]["required"]["model_name"][0]
    for opt in opts:
        if "minimax_h3_latent_upscaler_3d_fp16.safetensors" in opt:
            return opt
    return "minimax_h3_latent_upscaler_3d_fp16.safetensors"


def resolve_cinema_lora(base_url: str) -> str:
    oi = http_json(f"{base_url}/object_info/LoraLoaderModelOnly", timeout=20)
    opts = oi["LoraLoaderModelOnly"]["input"]["required"]["lora_name"][0]
    for cand in ("minimax/MinimaxH3真实电影质感V0.1.safetensors", "minimax/MinimaxH3_CinematicRealism_V0.1.safetensors"):
        if cand in opts:
            return cand
    for opt in opts:
        if "真实电影质感" in opt or "CinematicRealism" in opt:
            return opt
    return "minimax/MinimaxH3真实电影质感V0.1.safetensors"


def build_u24_graph(job: dict, upscaler_name: str, cinema_lora: str, aspect: str = "16:9", scale_by: float = 1.5) -> dict:
    low_w, low_h = (864, 480) if aspect == "16:9" else (480, 864)
    jid = job["job_id"]
    seed = int(job["seed"])
    frames = int(job["frames"])
    g = {
        "1": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
        "2": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "type": "minimax", "device": "default"}},
        "4": {"class_type": "UNETLoader", "inputs": {"unet_name": "minimax/minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors", "weight_dtype": "default"}},
        "5": {"class_type": "LoraLoaderBypassModelOnly", "inputs": {"lora_name": "minimax/minimax_h3_fl2v_turbo_4step_v1.2_768p_comfyui_bf16.safetensors", "strength_model": 1.0, "model": ["4", 0]}},
        "33": {"class_type": "ModelAttentionBackend", "inputs": {"attention": "pytorch attention", "model": ["5", 0]}},
        # PASS 1 (LOW 0.4MP, 4 steps) 5-LoRA branch
        "52": {"class_type": "LoraLoaderModelOnly", "inputs": {"lora_name": "minimax/H3_Combat_V2.safetensors", "strength_model": 0.70, "model": ["33", 0]}},
        "51": {"class_type": "LoraLoaderBypassModelOnly", "inputs": {"lora_name": "minimax/minimax_h3_turbo_v4_step600_ema_DasiwaREF2VAHybridV1_0_curveproj1025_compat_v001.safetensors", "strength_model": 0.90, "model": ["52", 0]}},
        "50": {"class_type": "LoraLoaderModelOnly", "inputs": {"lora_name": "minimax/minimax_h3_turbo_4step_10ErosMax_test4_pruned_curveproj1025_exp_v001-T8.safetensors", "strength_model": 0.50, "model": ["51", 0]}},
        "45": {"class_type": "LoraLoaderModelOnly", "inputs": {"lora_name": "minimax/Motion_Repair.safetensors", "strength_model": 0.70, "model": ["50", 0]}},
        "48": {"class_type": "LoraLoaderModelOnly", "inputs": {"lora_name": cinema_lora, "strength_model": 0.50, "model": ["45", 0]}},
        # PASS 2 (HIGH 1.5x -> 1312x736, 5 steps) 5-LoRA branch
        "53": {"class_type": "LoraLoaderModelOnly", "inputs": {"lora_name": "minimax/H3_Combat_V2.safetensors", "strength_model": 0.49, "model": ["33", 0]}},
        "47": {"class_type": "LoraLoaderBypassModelOnly", "inputs": {"lora_name": "minimax/minimax_h3_turbo_v4_step600_ema_DasiwaREF2VAHybridV1_0_curveproj1025_compat_v001.safetensors", "strength_model": 0.50, "model": ["53", 0]}},
        "44": {"class_type": "LoraLoaderModelOnly", "inputs": {"lora_name": "minimax/minimax_h3_turbo_4step_10ErosMax_test4_pruned_curveproj1025_exp_v001-T8.safetensors", "strength_model": 0.70, "model": ["47", 0]}},
        "46": {"class_type": "LoraLoaderModelOnly", "inputs": {"lora_name": "minimax/Motion_Repair.safetensors", "strength_model": 0.20, "model": ["44", 0]}},
        "49": {"class_type": "LoraLoaderModelOnly", "inputs": {"lora_name": cinema_lora, "strength_model": 0.20, "model": ["46", 0]}},
        # Dual-clock 2-pass T8 pipeline
        "8": {"class_type": "MiniMaxH3DualClockSamplerT8", "inputs": {
            "steps": 8, "shift_video": 12, "shift_audio": 3,
            "sampler_name": "dual_clock_euler", "scheduler": "native_flow",
            "model": ["48", 0], "av_latent": ["95", 1],
        }},
        "9": {"class_type": "MiniMaxH3LearnedTwoPassParityPlanT8Advanced", "inputs": {"base_steps": 9, "coarse_steps": 4, "refine_steps": 5, "model": ["8", 0]}},
        "10": {"class_type": "BasicGuider", "inputs": {"model": ["8", 0], "conditioning": ["95", 0]}},
        "11": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "12": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["11", 0], "guider": ["10", 0], "sampler": ["8", 1], "sigmas": ["9", 0], "latent_image": ["95", 1]}},
        "13": {"class_type": "MiniMaxH3LearnedLatentUpscaleT8Advanced", "inputs": {
            "model_name": upscaler_name, "size_mode": "scale_by", "scale_by": scale_by,
            "target_megapixels": 1, "target_width": 1280, "target_height": 704,
            "aspect_policy": "preserve_source", "max_anisotropy": 1.05,
            "precision": "fp16", "release_policy": "offload_after",
            "av_latent": ["12", 1],
        }},
        "15": {"class_type": "MiniMaxH3TwoPassLatentReconcileT8Advanced", "inputs": {
            "audio_policy": "auto", "second_pass_audio_source": "legacy_policy", "second_pass_audio_strength": 0,
            "learned_latent": ["13", 0], "highres_template": ["96", 1], "positive": ["96", 0],
        }},
        "16": {"class_type": "MiniMaxH3TwoPassDetailMixerT8Advanced", "inputs": {
            "shift_video": 12, "shift_audio": 3,
            "enable_tail": False, "extra_tail_steps": 1, "tail_spacing": "video_sigma_linear",
            "enable_model_time_bias": False, "bias": -0.025, "bias_start_progress": 0.7, "bias_end_progress": 0.95, "bias_domain": "video_sigma",
            "enable_stg": False, "stg_scale": 0.35, "stg_double_blocks": "25", "stg_start_progress": 0.25, "stg_end_progress": 0.85,
            "enable_restart": False, "restart_video_sigma": 0.15, "restart_steps": 3, "restart_seed": seed + 99999,
            "model": ["49", 0], "av_latent": ["15", 0], "refine_sigmas": ["9", 1],
        }},
        "17": {"class_type": "BasicGuider", "inputs": {"model": ["16", 0], "conditioning": ["15", 1]}},
        "19": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["11", 0], "guider": ["17", 0], "sampler": ["16", 1], "sigmas": ["16", 2], "latent_image": ["15", 0]}},
        "20": {"class_type": "MiniMaxH3AVDecodeT8", "inputs": {"av_latent": ["19", 0], "video_vae": ["1", 0], "audio_vae": ["2", 0]}},
        "21": {"class_type": "CreateVideo", "inputs": {"images": ["20", 0], "audio": ["20", 1], "fps": 24.0, "bit_depth": "auto", "color_space": "sRGB", "chroma_subsampling": "auto", "codec": "none"}},
        "92": {"class_type": "SaveVideo", "inputs": {"video": ["21", 0], "filename_prefix": f"video/{jid}", "format": "auto", "format.codec": "auto"}},
    }
    cond_low = {
        "prompt": job["prompt"],
        "width": low_w, "height": low_h, "length": frames,
        "task_type": "Ref2VA", "audio_mode": "native", "audio_denoise_strength": 1.0,
        "add_source_as_reference": False, "prompt_primary_audio_ordinal": 0,
        "strict_prompt_tags": False, "ref_image_size": "match",
        "reference_video_policy": "official_2_to_15s", "allow_above_reference_area": False,
        "clip": ["3", 0], "video_vae": ["1", 0], "audio_vae": ["2", 0],
    }
    cond_high = dict(cond_low, width=["13", 1], height=["13", 2])
    for i, im in enumerate(job["ref_images"][:9]):
        nid = str(200 + i)
        g[nid] = {"class_type": "LoadImage", "inputs": {"image": im["remote_name"]}}
        cond_low[f"ref_images.ref_image_{i}"] = [nid, 0]
        cond_high[f"ref_images.ref_image_{i}"] = [nid, 0]
    for i, au in enumerate(job["ref_audios"][:3]):
        nid = str(300 + i)
        g[nid] = {"class_type": "LoadAudio", "inputs": {"audio": au["remote_name"]}}
        cond_low[f"ref_audios.ref_audio_{i}"] = [nid, 0]
        cond_high[f"ref_audios.ref_audio_{i}"] = [nid, 0]
    g["95"] = {"class_type": "MiniMaxH3AudioConditioningT8", "inputs": cond_low}
    g["96"] = {"class_type": "MiniMaxH3AudioConditioningT8", "inputs": cond_high}
    return g


def download_output_video(base_url: str, hist_entry: dict, dst_path: str):
    outputs = hist_entry.get("outputs", {})
    for nid, out in outputs.items():
        for key in ("images", "videos", "gifs"):
            for item in out.get(key, []):
                fn = item.get("filename", "")
                if fn.endswith((".mp4", ".webm", ".mov")):
                    qs = urllib.parse.urlencode({
                        "filename": fn,
                        "subfolder": item.get("subfolder", ""),
                        "type": item.get("type", "output"),
                    })
                    urllib.request.urlretrieve(f"{base_url}/view?{qs}", dst_path + ".tmp")
                    os.replace(dst_path + ".tmp", dst_path)
                    return
    raise RuntimeError(f"未在 ComfyUI history outputs 中找到视频文件: {outputs}")


def execute_jobs(base_url: str, jobs: list, out_dir: str, aspect: str, scale_by: float):
    os.makedirs(out_dir, exist_ok=True)
    upscaler_name = resolve_upscaler_name(base_url)
    cinema_lora = resolve_cinema_lora(base_url)
    print(f"[U24] 连接就绪: {base_url} | upscaler={upscaler_name} | cinema_lora={cinema_lora}")
    for idx, job in enumerate(jobs, 1):
        jid = job["job_id"]
        dst = os.path.join(out_dir, f"{jid}.mp4")
        if os.path.exists(dst) and os.path.getsize(dst) > 500_000:
            print(f"[{idx}/{len(jobs)}] 已存在跳过: {dst}")
            continue
        for im in job["ref_images"]:
            src = find_asset(im["backend_id"])
            im["remote_name"] = upload_input_file(base_url, src, f"{im['backend_id']}{os.path.splitext(src)[1]}")
        for au in job["ref_audios"]:
            src = find_asset(au["backend_id"])
            au["remote_name"] = upload_input_file(base_url, src, f"{au['backend_id']}{os.path.splitext(src)[1]}")
        g = build_u24_graph(job, upscaler_name, cinema_lora, aspect=aspect, scale_by=scale_by)
        t0 = time.time()
        resp = http_json(f"{base_url}/prompt", {"prompt": g, "client_id": jid}, timeout=30)
        pid = resp["prompt_id"]
        print(f"[{idx}/{len(jobs)}] 已提交 {jid} -> prompt_id={pid}，等待二采 1312x736 完成 ...")
        while True:
            time.sleep(8)
            h = http_json(f"{base_url}/history/{pid}", timeout=20)
            if pid in h:
                st = h[pid].get("status", {})
                if st.get("status_str") == "error":
                    raise SystemExit(f"[ERROR] {jid} 渲染报错: {st}")
                download_output_video(base_url, h[pid], dst)
                print(f"  [DONE] {dst} ({os.path.getsize(dst)/1e6:.1f} MB, {time.time()-t0:.0f}s)")
                break


def cmd_status(args):
    base = args.url.rstrip("/")
    stats = http_json(f"{base}/system_stats")
    q = http_json(f"{base}/queue")
    up_name = resolve_upscaler_name(base)
    lora_name = resolve_cinema_lora(base)
    print(json.dumps({
        "devices": stats.get("devices", []),
        "queue_running": len(q.get("queue_running", [])),
        "queue_pending": len(q.get("queue_pending", [])),
        "u24_upscaler": up_name,
        "u24_cinema_lora": lora_name,
    }, ensure_ascii=False, indent=2))


def cmd_run_episode(args):
    base = args.url.rstrip("/")
    ep_dir = os.path.join(PIPE, "episodes", args.ep)
    plan = json.load(open(os.path.join(ep_dir, "plan.json"), encoding="utf-8"))
    segs = [int(s["id"]) for s in plan["segments"]] if args.all else args.seg
    jobs = []
    for seg in segs:
        meta = json.load(open(os.path.join(ep_dir, "05_prompts", f"seg{seg:02d}.meta.json"), encoding="utf-8"))
        prompt_en = extract_en(open(os.path.join(ep_dir, "05_prompts", f"seg{seg:02d}.bilingual.md"), encoding="utf-8").read()).strip()
        imgs = [{"label": r["label"], "backend_id": r["backend_id"]} for r in meta["refs_in_upload_order"] if r["label"].startswith("Picture")]
        auds = [{"label": r["label"], "backend_id": r["backend_id"]} for r in meta["refs_in_upload_order"] if not r["label"].startswith("Picture")]
        jobs.append({
            "job_id": f"{args.ep}_U24_Seg{seg:02d}_768p",
            "seg": seg,
            "frames": h3_frames(float(meta.get("duration", 15.0))),
            "seed": args.seed_base + seg,
            "prompt": prompt_en,
            "ref_images": imgs,
            "ref_audios": auds,
        })
    out_dir = args.out or os.path.join(ep_dir, "07_clips")
    execute_jobs(base, jobs, out_dir, args.aspect, args.scale)


def cmd_run_jobs(args):
    base = args.url.rstrip("/")
    raw = json.load(open(args.jobs_json, encoding="utf-8"))
    jobs = []
    for item in raw:
        seg = int(item.get("seg", len(jobs) + 1))
        jobs.append({
            "job_id": item.get("job_id", f"U24_Seg{seg:02d}_768p"),
            "seg": seg,
            "frames": int(item.get("frames", h3_frames(float(item.get("duration", 15.0))))),
            "seed": int(item.get("seed", args.seed_base + seg)),
            "prompt": item["prompt"].strip(),
            "ref_images": [{"label": x["label"], "backend_id": x["backend_id"]} for x in item.get("ref_images", [])],
            "ref_audios": [{"label": x["label"], "backend_id": x["backend_id"]} for x in item.get("ref_audios", [])],
        })
    execute_jobs(base, jobs, args.out, args.aspect, args.scale)


def main():
    default_url = os.environ.get("COMFY_BASE_URL", "http://127.0.0.1:8188")
    ap = argparse.ArgumentParser(description="U24 文武双修 T8 自建原生 ComfyUI 首要工作流客户端")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_st = sub.add_parser("status", help="检查自建 ComfyUI 节点与 U24 模型就绪状态")
    p_st.add_argument("--url", default=default_url)
    p_st.set_defaults(fn=cmd_status)

    p_ep = sub.add_parser("run", help="按 episodes/<EP> 分镜目录批量渲染 U24 成片")
    p_ep.add_argument("ep", help="例如 E81 / E82")
    p_ep.add_argument("--seg", type=int, nargs="+", default=[])
    p_ep.add_argument("--all", action="store_true")
    p_ep.add_argument("--url", default=default_url)
    p_ep.add_argument("--out", default="")
    p_ep.add_argument("--aspect", choices=["16:9", "9:16"], default="16:9")
    p_ep.add_argument("--scale", type=float, default=1.5)
    p_ep.add_argument("--seed-base", type=int, default=2026112400)
    p_ep.set_defaults(fn=cmd_run_episode)

    p_jb = sub.add_parser("run-jobs", help="按纯导演 jobs.json 批量渲染 U24 成片")
    p_jb.add_argument("jobs_json")
    p_jb.add_argument("--out", required=True)
    p_jb.add_argument("--url", default=default_url)
    p_jb.add_argument("--aspect", choices=["16:9", "9:16"], default="16:9")
    p_jb.add_argument("--scale", type=float, default=1.5)
    p_jb.add_argument("--seed-base", type=int, default=2026112500)
    p_jb.set_defaults(fn=cmd_run_jobs)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
