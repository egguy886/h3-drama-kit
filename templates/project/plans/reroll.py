"""返工队列（GPU 串行：返工段优先于新集）。queue_worker.sh 每轮先清这个队列，再出新集。
  python3 plans/reroll.py add E02 2 3 --reason "看片意见1：站位/拉链" [--retire]   入队；--retire = 提示词已改，旧片段移到 07_clips/_old/ 不再参与选片
  python3 plans/reroll.py list                                                    看队列
  python3 plans/reroll.py next                                                    出队首（worker 调用）：comfy_run --only，自动用新 tag
  python3 plans/reroll.py has                                                     队列非空返回 0
出完后删掉该集拼接成片，autopilot 会重新选片、拼接、自检。"""
import glob, json, os, re, shutil, subprocess, sys, time
PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); os.chdir(PIPE)
QF = 'plans/reroll_queue.jsonl'; LOG = 'autopilot.log'
def log(m): open(LOG, 'a', encoding='utf-8').write(f'{time.strftime("%m-%d %H:%M:%S")} [返工] {m}\n')
def load(): return [json.loads(l) for l in open(QF, encoding='utf-8')] if os.path.exists(QF) else []
def save(q): open(QF, 'w', encoding='utf-8').write(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in q))
def next_tag(ep, seg):
    tags = [int(m.group(1)) for f in glob.glob(f'episodes/{ep}/07_clips/**/{ep}_seg{seg:02d}_r*', recursive=True) for m in [re.search(r'_r(\d+)', os.path.basename(f))] if m]
    return f'r{max(tags + [2]) + 1}'
def retire(ep, seg):
    d = f'episodes/{ep}/07_clips'; os.makedirs(f'{d}/_old', exist_ok=True); n = 0
    for f in glob.glob(f'{d}/{ep}_seg{seg:02d}_*'): shutil.move(f, f'{d}/_old/'); n += 1
    ch = f'episodes/{ep}/chosen.json'
    if os.path.exists(ch):
        c = json.load(open(ch)); c.pop(f'u24:{seg}', None); json.dump(c, open(ch, 'w'), indent=1)
    for f in (f'review/compare/{ep}_asm.mp4', f'review/compare/{ep}_asm.json', f'episodes/{ep}/.asm_failed', f'episodes/{ep}/.rerolled_{seg}'):
        if os.path.exists(f): os.remove(f)
    return n
a = sys.argv[1:]
if not a or a[0] == 'list':
    for x in load(): print(x)
elif a[0] == 'has':
    sys.exit(0 if load() else 1)
elif a[0] == 'add':
    ep = a[1]; segs = [int(x) for x in a[2:] if x.isdigit()]
    reason = a[a.index('--reason') + 1] if '--reason' in a else ''
    q = load(); have = {(x['ep'], x['seg']) for x in q}
    for s in segs:
        if '--retire' in a: log(f'{ep} Seg{s} 提示词已改，旧片段 {retire(ep, s)} 个移到 _old')
        open('review/返工记录.jsonl', 'a', encoding='utf-8').write(json.dumps({'ep': ep, 'seg': s, 'reason': reason, 'at': time.strftime('%Y-%m-%d %H:%M')}, ensure_ascii=False) + '\n')
        if (ep, s) not in have: q.append({'ep': ep, 'seg': s, 'reason': reason, 'at': time.strftime('%m-%d %H:%M')})
    save(q); print(f'队列 {len(q)} 段')
elif a[0] == 'next':
    q = load()
    if not q: sys.exit(1)
    def missing(x):
        try:
            sg = next(y for y in json.load(open(f"episodes/{x['ep']}/plan.json"))['segments'] if int(y['id']) == x['seg'])
        except Exception:
            return []
        return [r[2] for r in sg.get('refs', []) if not glob.glob(f'assets/*/{r[2]}.png')]
    ready = [y for y in q if not missing(y)]
    if not ready:
        log(f'队列里 {len(q)} 段都在等参考图（如 {q[0]["ep"]} Seg{q[0]["seg"]} 缺 {missing(q[0])}）'); time.sleep(120); sys.exit(0)
    x = ready[0]; ep, s = x['ep'], x['seg']; tag = next_tag(ep, s)
    log(f'{ep} Seg{s} 开始重出 {tag}（{x["reason"]}）')
    r = subprocess.run([sys.executable, 'tools/comfy_run.py', 'batch', ep, '--only', f'{ep}:{s}', '--tag', tag, '--attempts', '3'])
    q = [y for y in load() if (y['ep'], y['seg']) != (ep, s)]; save(q)
    sys.path.insert(0, 'tools'); import qc_lib as Q
    best = Q.best_clip(ep, s, tag=tag)                          # 钉住这一轮的新片（旧片质检分可能更高，但画面有毛病）
    if best:
        ch = f'episodes/{ep}/chosen.json'; c = json.load(open(ch)) if os.path.exists(ch) else {}
        c[f'u24:{s}'] = os.path.relpath(best, PIPE); json.dump(c, open(ch, 'w'), indent=1)
    for f in (f'review/compare/{ep}_asm.mp4', f'review/compare/{ep}_asm.json', f'episodes/{ep}/.asm_failed'):
        if os.path.exists(f): os.remove(f)
    log(f'{ep} Seg{s} 重出结束（退出码 {r.returncode}），等 autopilot 重新拼接')
