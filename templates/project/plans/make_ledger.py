"""ComfyUI 路线没有 h3_run 的 ledger：按 stitch_ep 同样的取片顺序（chosen.json → 质检最佳 → 最新）写 06_jobs/ledger.jsonl，让 tools/assemble_episode.py 能用。
用法：python3 plans/make_ledger.py E02 [E03 ...]"""
import glob, json, os, sys
PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); os.chdir(PIPE); sys.path.insert(0, 'tools')
import qc_lib as Q
for ep in sys.argv[1:]:
    d = f'episodes/{ep}'; n = len(json.load(open(f'{d}/plan.json'))['segments'])
    ch = json.load(open(f'{d}/chosen.json')) if os.path.exists(f'{d}/chosen.json') else {}
    rows = []
    for s in range(1, n + 1):
        f = ch.get(f'u24:{s}') if ch.get(f'u24:{s}') and os.path.exists(ch[f'u24:{s}']) else None
        f = f or Q.best_clip(ep, s)
        f = f or max(glob.glob(f'{d}/07_clips/{ep}_seg{s:02d}_*.mp4'), key=os.path.getmtime, default=None)
        if not f: sys.exit(f'{ep} 缺 Seg{s}')
        rows.append({'seg': s, 'outcome': 'kept', 'clip': os.path.relpath(f, d), 'note': 'comfyui'})
    os.makedirs(f'{d}/06_jobs', exist_ok=True)
    with open(f'{d}/06_jobs/ledger.jsonl', 'w', encoding='utf-8') as o:
        for r in rows: o.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'{ep}: {n} 段写入 06_jobs/ledger.jsonl')
