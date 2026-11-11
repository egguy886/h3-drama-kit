"""无人值守收尾：每 10 分钟扫一遍，做三件事（日志 autopilot.log）。
1. Codex 补图：缺的新场景图 / 垫图，每 40 分钟试一次（额度没了就退出码非 0，下次再试）；图一到，auto_ready 会自动重编译并放行。
2. 已出齐的集：质检仍 FAIL 的段补出一轮（tag r2，每段只补一次）；全部有片后 make_ledger + assemble_episode → review/compare/ENN_asm.mp4，成功后删本集没选中的重出片段，
   再跑自检 plans/self_review.py（审片卡 + Codex 看卡，random 类硬伤自动进返工队列 plans/reroll.py，其余记 review/自检待办.md）。
3. 磁盘守门：< 2.5GB 记日志；< 1.5GB 暂停出片队列，> 4GB 自动恢复（disk_guard）。不删用户文件。
停掉：touch autopilot_stop
"""
import glob, importlib.util, json, os, subprocess, sys, time
PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); os.chdir(PIPE); sys.path.insert(0, os.path.join(PIPE, 'tools'))
import qc_lib as Q
LOGF = os.path.join(PIPE, 'autopilot.log')
def log(m): open(LOGF, 'a', encoding='utf-8').write(f'{time.strftime("%m-%d %H:%M:%S")} {m}\n')
def run(cmd, timeout=3600):
    return subprocess.run(cmd, cwd=PIPE, capture_output=True, text=True, timeout=timeout)
def running(pat): return subprocess.run(['pgrep', '-f', pat], capture_output=True).returncode == 0
def free_gb():
    s = os.statvfs(PIPE); return s.f_bavail * s.f_frsize / 1e9
def eps():
    return sorted(d for d in os.listdir('episodes') if d.startswith('E') and d[1:].isdigit() and int(d[1:]) >= 2 and os.path.exists(f'episodes/{d}/plan.json'))   # E01 已定稿，不动
def segs(ep): return len(json.load(open(f'episodes/{ep}/plan.json'))['segments'])
def have_clip(ep, s): return bool(glob.glob(f'episodes/{ep}/07_clips/{ep}_seg{s:02d}_*.mp4'))

def codex_fill():
    sp = importlib.util.spec_from_file_location('ns', 'plans/keys/new_scenes.py'); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
    miss = [i for i in m.S if not os.path.exists(f'assets/images/{i}.png')]
    keys_todo = []
    for kp in sorted(glob.glob('plans/keys/e[0-9]*.py')):
        ep = os.path.basename(kp)[:-3].upper()
        s = importlib.util.spec_from_file_location('k', kp); mk = importlib.util.module_from_spec(s); s.loader.exec_module(mk)
        if [k for k in mk.K if not os.path.exists(f'assets/images/{k}.png')]: keys_todo.append(ep)
    if not miss and not keys_todo: return
    if miss:
        r = run([sys.executable, 'plans/gen_scenes.py'] + miss, timeout=7200); log(f'Codex 场景图 {miss} → 退出码 {r.returncode}')
    for ep in keys_todo:
        r = run([sys.executable, 'plans/gen_keys.py', ep], timeout=7200); log(f'Codex 垫图 {ep} → 退出码 {r.returncode}')

def finish(ep):
    n = segs(ep)
    if not all(have_clip(ep, s) for s in range(1, n + 1)): return
    if running(f'comfy_run.py batch {ep}'): return
    asm = os.path.join(PIPE, 'review', 'compare', f'{ep}_asm.mp4')
    # 先补 FAIL 段一轮
    for s in range(1, n + 1):
        mark = f'episodes/{ep}/.rerolled_{s}'
        rows = [r for r in Q.ledger_read(ep) if r['seg'] == s]
        if rows and not any(r['status'] in ('PASS', 'WARN') for r in rows) and not os.path.exists(mark):
            open(mark, 'w').write('1'); log(f'{ep} Seg{s} 质检仍 FAIL，补出一轮 r2')
            run([sys.executable, 'tools/comfy_run.py', 'batch', ep, '--only', f'{ep}:{s}', '--tag', 'r2', '--attempts', '3'], timeout=7200)
            return                                  # 一次只处理一段，下一轮再来
    if os.path.exists(asm) or os.path.exists(f'episodes/{ep}/.asm_failed'): return
    if run([sys.executable, 'plans/make_ledger.py', ep]).returncode:
        log(f'{ep} make_ledger 失败'); return
    r = run([sys.executable, 'tools/assemble_episode.py', ep, '--out', asm], timeout=1800)
    if r.returncode or not os.path.exists(asm):
        open(f'episodes/{ep}/.asm_failed', 'w').write(r.stdout[-300:] + r.stderr[-300:]); log(f'{ep} 拼接失败：' + (r.stderr or r.stdout)[-200:].replace('\n', ' | ')); return
    kept = {os.path.basename(json.loads(l)['clip']) for l in open(f'episodes/{ep}/06_jobs/ledger.jsonl')}
    gone = 0
    for f in glob.glob(f'episodes/{ep}/07_clips/*.mp4'):
        if os.path.basename(f) not in kept: os.remove(f); gone += 1
    log(f'{ep} ✅ 已拼接 {os.path.basename(asm)}，清理未选中重出片段 {gone} 个')
    r = run([sys.executable, 'plans/self_review.py', ep], timeout=3600)          # 自检：审片卡 + Codex 看卡；random 硬伤自动返工
    log(f'{ep} 自检 → ' + (r.stdout.strip().splitlines() or ['(无输出)'])[-1])

def disk_guard():
    """磁盘守门（Tangled 11-10：剩 2GB 只记日志、没人看，差点写满）。
    < 2.5GB 记 ⚠；< 1.5GB 让出片队列在当前段出完后停（touch queue_stop，记 .disk_paused），写满会把正在下载的片子写坏；
    回到 > 4GB 且是磁盘暂停的 → 自动重启队列。不删任何用户文件。"""
    g = free_gb()
    if g < 1.5 and not os.path.exists('.disk_paused'):
        open('queue_stop', 'w').write('disk'); open('.disk_paused', 'w').write(f'{g:.1f}')
        log(f'⛔ 磁盘只剩 {g:.1f}GB：出片队列出完当前段后暂停，腾出空间（>4GB）后自动恢复')
    elif g > 4 and os.path.exists('.disk_paused') and not running('queue_worker.sh'):
        os.remove('.disk_paused')
        if os.path.exists('queue_stop'): os.remove('queue_stop')
        subprocess.Popen(['zsh', 'plans/queue_worker.sh'], cwd=PIPE, stdout=open('queue_worker.log', 'a'), stderr=subprocess.STDOUT, start_new_session=True)
        log(f'磁盘回到 {g:.1f}GB，出片队列已恢复')
    elif g < 2.5:
        log(f'⚠ 磁盘只剩 {g:.1f}GB')

last_codex = 0
while not os.path.exists('autopilot_stop'):
    try:
        if time.time() - last_codex > 2400 and time.time() >= time.mktime((2026, 11, 9, 0, 55, 0, 0, 0, -1)):   # Codex 额度 11-09 0:50 重置
            last_codex = time.time(); codex_fill()
        for ep in eps(): finish(ep)
        for ep in eps():                                   # 自检补跑：拼好了但没有有效自检结果（额度用完等）→ 每轮补一集
            a, rv = f'review/compare/{ep}_asm.mp4', f'review/自检/{ep}/review.json'
            if os.path.exists(a) and (not os.path.exists(rv) or os.path.getmtime(rv) < os.path.getmtime(a)) and os.environ.get('SELF_REVIEW') != 'off':
                r = run([sys.executable, 'plans/self_review.py', ep], timeout=3600); log(f'{ep} 自检补跑 → 退出码 {r.returncode}'); break
        run([sys.executable, 'plans/make_watchlist.py']); run([sys.executable, 'plans/lesson_report.py'])
        r = run([sys.executable, 'plans/skill_sync.py'])                    # 自我升级：验证过的经验同步进 skill（提交并推送 GitHub）
        if '同步进' in r.stdout or 'skill ' in r.stdout.split('同步')[-1]: log('[升级] ' + r.stdout.strip()[-300:])
        disk_guard()
    except Exception as e:
        log('ERR ' + str(e)[:300])
    time.sleep(600)
log('autopilot 停止')
