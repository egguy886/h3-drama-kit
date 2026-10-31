"""成片超分到 1080×1920（服务器上的 RTX VSR Ultra）。一集一集处理，切 15 秒一块，避免整集帧一次进内存。
用法：python3 tools/rtx_upscale.py E50 [--src 08_edit/E50_cut_v2.mp4] [--limit 30]
  --src    要放大的成片（默认 08_edit/<EP>_cut_v2.mp4，没有就用 _cut_v1.mp4）
  --limit  只处理前 N 秒（试跑用）
输出：episodes/<EP>/08_edit/<EP>_rtx1080.mp4（视频是放大后的，声音原样取自 --src），字幕步骤再往上烧。
服务器上的输入块和输出块不会自动删：文件名记在 review/rtx/<EP>_server_files.txt，等制片人确认后再清。
"""
import json, os, subprocess, sys, time, urllib.parse, urllib.request

PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = json.load(open(os.path.join(PIPE, "comfy_settings.json")))["base_url"].rstrip("/")
COMFY = PANEL.replace("//uu", "//u", 1)                    # ComfyUI 本体地址：和面板只差域名前缀
UA = {"User-Agent": "Mozilla/5.0"}
CHUNK = 15


def http(url, body=None, timeout=60):
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), headers={**UA, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def sh(*a):
    subprocess.run(a, check=True)


def probe(f, entry):
    return subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", f"stream={entry}", "-of", "csv=p=0", f],
                          capture_output=True, text=True).stdout.strip()


def upload(path, name):
    for _ in range(4):                                      # 面板上传偶发 curl 55，重试；它会给文件名加哈希后缀，要用返回的名字
        r = subprocess.run(["curl", "-s", "-m", "300", "-X", "POST", f"{PANEL}/api/comfy/upload/file", "-F", f"file=@{path};filename={name}", "-F", "overwrite=true"],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip().startswith("{"): return json.loads(r.stdout)["name"]
        time.sleep(10)
    raise SystemExit(f"上传 {name} 失败 curl {r.returncode}")


def graph(name, prefix, fps):
    return {"1": {"class_type": "VHS_LoadVideo", "inputs": {"video": name, "force_rate": 0, "custom_width": 0, "custom_height": 0,
                                                         "frame_load_cap": 0, "skip_first_frames": 0, "select_every_nth": 1}},
            "2": {"class_type": "DenoRTXVFXEasyUpscale", "inputs": {"images": ["1", 0], "mode": "VSR Ultra", "resize_type": "Manual", "scale": 2.0,
                  "megapixels": 2.0, "width": 1080, "height": 1920, "divisible_by": "1", "device": 0, "ratio_preset": "9:16",
                  "resize_method": "Center Crop (Fill)"}},
            "4": {"class_type": "VHS_VideoCombine", "inputs": {"images": ["2", 0], "frame_rate": fps, "loop_count": 0, "filename_prefix": prefix,
                  "format": "video/h264-mp4", "pingpong": False, "save_output": True, "pix_fmt": "yuv420p", "crf": 14, "save_metadata": False}}}


def run_chunk(path, ep, i, fps, out):
    t0 = time.time()
    name = upload(path, f"rtx_{ep}_{i:02d}.mp4"); t_up = time.time() - t0
    pid = http(COMFY + "/prompt", {"prompt": graph(name, f"rtx_{ep}_{i:02d}", fps), "client_id": "rtx-upscale"})["prompt_id"]
    while True:
        time.sleep(5)
        h = http(f"{COMFY}/history/{pid}").get(pid)
        if h and h.get("status", {}).get("completed") is not None: break
        if time.time() - t0 > 1200: raise SystemExit(f"块 {i} 超过 20 分钟")
    if h["status"].get("status_str") == "error": raise SystemExit(json.dumps(h["status"]["messages"][-1], ensure_ascii=False)[:300])
    f = [x for o in h["outputs"].values() for x in o.get("gifs", [])][0]
    url = f"{COMFY}/view?" + urllib.parse.urlencode({"filename": f["filename"], "subfolder": f.get("subfolder", ""), "type": f.get("type", "output")})
    t1 = time.time(); open(out, "wb").write(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=600).read())
    return name, f["filename"], t_up, time.time() - t1, time.time() - t0


def main():
    ep = sys.argv[1]
    args = sys.argv[2:]
    ed = os.path.join(PIPE, "episodes", ep, "08_edit")
    src = args[args.index("--src") + 1] if "--src" in args else next(p for p in (f"{ed}/{ep}_cut_v2.mp4", f"{ed}/{ep}_cut_v1.mp4") if os.path.isfile(p))
    limit = float(args[args.index("--limit") + 1]) if "--limit" in args else None
    work = os.path.join(PIPE, "review", "rtx", ep); os.makedirs(work, exist_ok=True)
    fr = probe(src, "r_frame_rate"); fps = float(fr.split("/")[0]) / float(fr.split("/")[1]) if "/" in fr else float(fr)
    for f in os.listdir(work):
        if f.startswith(("in_", "out_")): os.remove(os.path.join(work, f))
    cut = ["ffmpeg", "-v", "error", "-y", "-i", src] + (["-t", str(limit)] if limit else []) + ["-an", "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p",   # crf 17：块小一半，上传是整集用时的大头
          
           "-force_key_frames", f"expr:gte(t,n_forced*{CHUNK})", "-f", "segment", "-segment_time", str(CHUNK), "-reset_timestamps", "1", os.path.join(work, "in_%02d.mp4")]
    sh(*cut)
    ins = sorted(f for f in os.listdir(work) if f.startswith("in_"))
    server, T = [], time.time()
    for i, f in enumerate(ins):
        out = os.path.join(work, f"out_{i:02d}.mp4")
        n_in, n_out, t_up, t_dn, t_all = run_chunk(os.path.join(work, f), ep, i, fps, out)
        server += [f"input/{n_in}", f"output/{n_out}"]
        print(f"{ep} 块 {i + 1}/{len(ins)} ✅ 上传 {t_up:.0f}s 下载 {t_dn:.0f}s 共 {t_all:.0f}s", flush=True)
    open(os.path.join(work, "list.txt"), "w").write("".join(f"file 'out_{i:02d}.mp4'\n" for i in range(len(ins))))
    dst = os.path.join(ed, f"{ep}_rtx1080.mp4")
    sh("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", os.path.join(work, "list.txt"), "-i", src, "-map", "0:v", "-map", "1:a?",
       "-c:v", "copy", "-c:a", "copy", "-shortest", dst)
    open(os.path.join(PIPE, "review", "rtx", f"{ep}_server_files.txt"), "w").write("\n".join(server) + "\n")
    print(f"{ep} 完成 → {dst}  {probe(dst, 'width')}×{probe(dst, 'height')}  总用时 {time.time() - T:.0f}s（服务器上的 {len(server)} 个文件待确认后清理）")


main()
