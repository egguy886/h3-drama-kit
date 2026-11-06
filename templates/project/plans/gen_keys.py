"""开场构图垫图：每段 0.0 秒的首帧，由 Codex 用已定稿的人物造型 / 场景 / 道具图合成，作为额外参考图送进 H3，
固定“谁站哪、机位多高、穿什么、光怎样”，并把全剧统一的风格（library/style_lock.json）带进画面。
用法：python3 plans/gen_keys.py E02            生成 plans/keys/e02.py 里还没有图的垫图（已有跳过）
      python3 plans/gen_keys.py E02 K-E02-S03 --force   重出（另存 _vN，不覆盖）
规格文件 plans/keys/eNN.py：K = {"K-E02-S01": dict(refs=["C01-PARTY","C02-SHIRT","N-BEDROOM"], body="英文构图描述（先说各图职责）", cn="中文说明")}
出图后写进 library/props.json（id 同名），分镜里把它放进该段 props 即可，编译时自动编成 <Picture N>。"""
import importlib.util, json, os, subprocess, sys, time, glob, shutil
PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ep = sys.argv[1]; force = '--force' in sys.argv; only = [a for a in sys.argv[2:] if a.startswith('K-')]
spec = importlib.util.spec_from_file_location('k', os.path.join(PIPE, 'plans', 'keys', ep.lower() + '.py')); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
sys.argv = [sys.argv[0], '/dev/null']
gsrc = open(os.path.join(PIPE, 'plans', 'gen_refs.py'), encoding='utf-8').read().split('\nargs = sys.argv[1:]')[0]
g = {'__file__': os.path.join(PIPE, 'plans', 'gen_refs.py')}; exec(compile(gsrc, 'gen_refs', 'exec'), g)
BIN, MODEL, FALLBACK = g['CODEX_BIN'], g['MODEL'], g['FALLBACK_MODEL']
LOCK = json.load(open(os.path.join(PIPE, 'library', 'style_lock.json'), encoding='utf-8'))
IMG = os.path.join(PIPE, 'assets', 'images'); LIBP = os.path.join(PIPE, 'library', 'props.json')
CORE = ("A single still frame from a live-action American romantic comedy series, vertical 9:16 composition, the opening frame of a scene. "
        + LOCK['reference_prompt_suffix_en'] + " Shallow depth of field: the people are sharp and the background melts into soft readable shapes. "
        "No readable text, no logos, no watermark, no subtitles.")
for kid, d in m.K.items():
    if only and kid not in only: continue
    out = os.path.join(IMG, kid + '.png'); n = 2
    if os.path.exists(out):
        if not force: print(kid, '已有，跳过'); continue
        while os.path.exists(os.path.join(IMG, f'{kid}_v{n}.png')): n += 1
        out = os.path.join(IMG, f'{kid}_v{n}.png')
    rel = os.path.relpath(out, PIPE)
    ask = ('Use your built-in image generation tool to generate exactly one image, portrait 2:3 (1024x1536), from the prompt below, using the attached reference images as described. '
           f'Do not change the prompt. Save the resulting PNG into this workspace as {rel}. Do nothing else and edit no other files. When done, reply with only the saved path.\n\nPROMPT:\n' + CORE + '\n\n' + d['body'])
    cmd = [BIN, 'exec', '-m', MODEL, '-c', 'model_reasoning_effort="low"', '--skip-git-repo-check', '-s', 'workspace-write', '-C', PIPE]
    for r in d['refs']:
        p = os.path.join(IMG, r + '.png')
        if not os.path.exists(p): sys.exit(f'{kid}：参考图 {r} 不存在')
        cmd += ['-i', p]
    cmd += ['--', ask]; t = time.time()
    run = lambda: subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8', errors='replace')
    r = run()
    if r.returncode != 0 and 'not supported' in (r.stdout + r.stderr):
        cmd[cmd.index('-m') + 1] = FALLBACK; r = run()
    if os.path.exists(out) and os.path.getsize(out) < 50000: os.remove(out)   # 0 字节占位
    if not os.path.exists(out):      # Codex 生成了图但没存进项目：从它的缓存里取本次最新一张
        c = [f for f in glob.glob(os.path.expanduser('~/.codex/generated_images/*/*.png')) if os.path.getmtime(f) > t]
        if c: shutil.copy(max(c, key=os.path.getmtime), out)
    ok = os.path.exists(out)
    print(f'{time.strftime("%H:%M")} {kid} {"✅ " + rel if ok else "❌ " + (r.stdout + r.stderr)[-400:]} {time.time() - t:.0f}s', flush=True)
    if ok and n == 2 and not os.path.basename(out).count('_v'):
        lib = json.load(open(LIBP, encoding='utf-8'))
        lib[kid] = {"name_cn": "开场构图垫图 " + kid, "cn": d['cn'], "match": [],
                    "en": ("the opening-composition reference shown in {P}: " + d.get('en_note', "it fixes who stands where, how high the camera is, what everyone wears and the light of this segment's first moment; "
                           "it is a starting layout only, and the camera then moves and cuts freely through the shots")),
                    "views": "single opening frame"}
        json.dump(lib, open(LIBP, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
