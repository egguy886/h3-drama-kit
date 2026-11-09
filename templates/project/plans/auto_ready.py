"""自动就绪：每隔 60 秒检查 E03–E30；某集的垫图和场景图都出齐、而分镜编译得比最新垫图旧，就重新编译（plans/eNN.py → compose → build），通过后写 episodes/Exx/READY，出片队列才会接这一集。
停掉：pkill -f auto_ready.py"""
import glob, importlib.util, json, os, subprocess, sys, time
PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = lambda i: os.path.join(PIPE, 'assets', 'images', i + '.png')
def log(m): open(os.path.join(PIPE, 'auto_ready.log'), 'a', encoding='utf-8').write(f'{time.strftime("%m-%d %H:%M:%S")} {m}\n')
def need(ep):
    kp = os.path.join(PIPE, 'plans', 'keys', ep.lower() + '.py'); keys = []
    if os.path.exists(kp):
        spec = importlib.util.spec_from_file_location('k', kp); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); keys = list(m.K)
    refs = []
    sp = os.path.join(PIPE, 'episodes', ep, 'plan_src.json')
    if os.path.exists(sp):
        d = json.load(open(sp, encoding='utf-8'))
        for s in d['segments']:
            refs += list(s.get('cast', [])) + ([s['scene_ref']] if s.get('scene_ref') else []) + list(s.get('props', []))
    return keys, sorted(set(refs))
def cycle():
    for n in range(3, 31):
        ep = f'E{n:02d}'; src = os.path.join(PIPE, 'plans', f'e{n:02d}.py'); pj = os.path.join(PIPE, 'episodes', ep, 'plan.json'); rd = os.path.join(PIPE, 'episodes', ep, 'READY')
        if not os.path.exists(src): continue
        if not os.path.exists(os.path.join(PIPE, 'episodes', ep, 'plan_src.json')): continue   # 分镜还没编译过：refs 读不到会被误判成‘图已齐’（E24 缺 D-COMPLIANCE 却被放行）
        keys, refs = need(ep)
        missing = [i for i in keys + refs if not os.path.exists(IMG(i)) and not i.startswith('T-') and not i.startswith('P') or (i.startswith(('T-', 'P')) and not os.path.exists(IMG(i)) and i in refs)]
        if [k for k in keys if not os.path.exists(IMG(k))] or [r for r in refs if not os.path.exists(IMG(r)) and not r.startswith('K-')]: continue
        newest = max([os.path.getmtime(IMG(i)) for i in keys + refs if os.path.exists(IMG(i))] or [0])
        if os.path.exists(rd) and os.path.exists(pj) and os.path.getmtime(pj) >= newest: continue
        log(f'{ep} 图已齐，重新编译')
        r1 = subprocess.run([sys.executable, src], cwd=os.path.join(PIPE, 'plans'), capture_output=True, text=True)
        r2 = subprocess.run([sys.executable, os.path.join(PIPE, 'tools', 'compose_plan.py'), ep], cwd=PIPE, capture_output=True, text=True)
        r3 = subprocess.run([sys.executable, os.path.join(PIPE, 'tools', 'build_episode.py'), os.path.join('episodes', ep), '--voices', 'voices.json'], cwd=PIPE, capture_output=True, text=True)
        out = (r1.stdout + r1.stderr + r2.stdout + r2.stderr + r3.stdout + r3.stderr)
        if r1.returncode or r2.returncode or '校验失败' in out or r3.returncode:
            log(f'{ep} 编译失败：' + out[-500:].replace('\n', ' | ')); continue
        open(rd, 'w').write('ok'); log(f'{ep} ✅ 就绪')
if __name__ == '__main__':
    while True:
        try: cycle()
        except Exception as e: log('ERR ' + str(e)[:200])
        time.sleep(60)
