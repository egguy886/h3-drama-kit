"""自我升级：经验 → 验证 → 同步进 h3-drama-kit skill（autopilot 每轮调用；也可手动 python3 plans/skill_sync.py [--dry]）。

1 验证（plans/lessons.json 里每条经验都有一组"试验段"）
  每个试验段重出后算一次：成 = 新片台词质检过 + 之后的自检没再报这段 + 不在返工队列里；败 = 质检 FAIL 或自检又报。
  人工判定优先：review/人工判定.jsonl 一行 {"ep":"E02","seg":5,"result":"败","lesson":"L04","note":"…"}（看片后由我记）。
  转正标准沿用 skill 09_规则证据表：成 ≥3 且 败 ≤1 → 已验证；败 ≥2 → 退回。样本不到 3 段的继续等。
2 升级（只对"已验证 / 退回"且还没同步过的经验动 skill，skill 里只进验证过的东西）
  rule/hypothesis → templates/project/plans/defect_rules.py（已验证的规则在 skill 里是 ❌，其余 ⚠；退回的关掉），首次会给 skill 的 pw.py 接上
  qc  → scripts/vision_qc.py、scripts/vqc.swift，并给 skill 的 qc_lib.py 接上画面质检
  tool → templates/project/plans/ 下的自检/返工/统计/升级脚本
  每条都写进 playbook/09_规则证据表.md 的"G. 看片返工自动升级"，然后在 skill 仓库 git commit 并推送到 GitHub（用户 2026-11-09 同意自动推送；SKILL_PUSH=0 或 --no-push 关掉）。
3 记录：review/技能升级记录.md"""
import glob, json, os, re, shutil, subprocess, sys, time
PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); os.chdir(PIPE)
SKILL = os.environ.get('SKILL_DIR') or os.path.expanduser('~/.claude/skills/h3-drama-kit')
LJ = os.environ.get('LESSONS_JSON', 'plans/lessons.json'); REC = os.environ.get('SYNC_RECORD', 'review/技能升级记录.md')
DRY = '--dry' in sys.argv; PUSH = os.environ.get('SKILL_PUSH', '1') != '0' and '--no-push' not in sys.argv   # 用户 2026-11-09 定：验证过的自动推送
L = json.load(open(LJ, encoding='utf-8'))
def jl(p): return [json.loads(x) for x in open(p, encoding='utf-8')] if os.path.exists(p) else []
def ts(s): return time.mktime(time.strptime(s, '%Y-%m-%d %H:%M' if len(s) > 11 else '%m-%d %H:%M'))
human = jl('review/人工判定.jsonl'); book = jl('review/教训账本.jsonl')
queue = {(x['ep'], x['seg']) for x in jl('plans/reroll_queue.jsonl')}


def outcome(lid, ep, seg, since):
    h = [x for x in human if x['ep'] == ep and int(x['seg']) == seg and x.get('lesson', lid) == lid]
    if h: return h[-1]['result']
    if (ep, seg) in queue: return None
    ch = json.load(open(f'episodes/{ep}/chosen.json')) if os.path.exists(f'episodes/{ep}/chosen.json') else {}
    clip = ch.get(f'u24:{seg}')
    if not clip or not os.path.exists(clip) or os.path.getmtime(clip) < since: return None          # 还没重出
    rel = os.path.relpath(clip, f'episodes/{ep}')
    rows = [r for r in jl(f'episodes/{ep}/06_jobs/qc.jsonl') if r['clip'] == rel]
    if not rows: return None
    if rows[-1]['status'] == 'FAIL': return '败'
    rv = f'review/自检/{ep}/review.json'
    if os.environ.get('SELF_REVIEW') != 'off':
        if not os.path.exists(rv) or os.path.getmtime(rv) < os.path.getmtime(clip): return None      # 等自检跑完
        if any(x['ep'] == ep and int(x.get('seg', 0)) == seg and ts(x['at']) > os.path.getmtime(clip) for x in book): return '败'
    return '成'


changed = []
for lid, x in L.items():
    since = ts(x['since'])
    if x['kind'] == 'tool':
        log = open('autopilot.log', encoding='utf-8').read() if os.path.exists('autopilot.log') else ''
        ok = len(re.findall(r'\[自检\] E\d+ 自检完成（codex）', log)) - 1          # 第一次是 E02 校准，不算
        bad = len(re.findall(r'自检没拿到结果', log)); res = {}
    else:
        res = {f'{e}:{s}': outcome(lid, e, s, since) for e, s in x['tests']}
        ok = sum(v == '成' for v in res.values()); bad = sum(v == '败' for v in res.values())
    st = x['status']
    if st in ('验证中',):
        st = '已验证' if ok >= 3 and bad <= 1 else '退回' if bad >= 2 else '验证中'
    if (ok, bad, st) != (x['ok'], x['bad'], x['status']):
        changed.append(f"{lid} {x['title']}：成 {ok} 败 {bad} → {st}")
    x.update(ok=ok, bad=bad, status=st, results=res)

# ---------- 升级进 skill ----------
def cp(src, dst):
    d = os.path.join(SKILL, dst); os.makedirs(os.path.dirname(d), exist_ok=True); shutil.copy(src, d)

def ensure(path, marker, snippet, after):
    p = os.path.join(SKILL, path); s = open(p, encoding='utf-8').read()
    if marker in s: return
    i = s.index(after) + len(after); open(p, 'w', encoding='utf-8').write(s[:i] + snippet + s[i:])

def sync_rules():
    lv = {k: ('err' if v['status'] == '已验证' else 'off' if v['status'] == '退回' else 'warn') for k, v in L.items() if v['kind'] in ('rule', 'hypothesis')}
    src = open('plans/defect_rules.py', encoding='utf-8').read()
    src = re.sub(r'LEVEL = \{.*?\}   # SKILL_SYNC_LEVEL', 'LEVEL = ' + json.dumps(lv, ensure_ascii=False) + '   # SKILL_SYNC_LEVEL', src)
    src = src.replace('        if LEVEL.get(code) != "err": return warn(code, k, msg)', '        if LEVEL.get(code) == "off": return\n        if LEVEL.get(code) != "err": return warn(code, k, msg)')
    src = src.replace('    def warn(code, k, msg): print(', '    def warn(code, k, msg):\n        if LEVEL.get(code) == "off": return\n        print(')
    open(os.path.join(SKILL, 'templates/project/plans/defect_rules.py'), 'w', encoding='utf-8').write(src)
    pw = 'templates/project/plans/pw.py'
    ensure(pw, 'from defect_rules import', '\n\ntry:                                   # 画面缺陷规则（自动升级同步，见 playbook/09 G 节）\n    from defect_rules import ERRS, defect_check\nexcept ImportError:\n    ERRS = []\n    def defect_check(*a, **k): pass\n', 'import json, os, re\n')
    s = open(os.path.join(SKILL, pw), encoding='utf-8').read()
    if 'defect_check(id, shots' not in s:
        s = re.sub(r'(\n(\s+)look_check\(id, shots[^\n]*\n)', r'\1\2defect_check(id, shots, (props or []) + ([ref] if ref else []), cast)\n', s, count=1)
        s = s.replace('def write(ep, title, header, notes, segs, wear=None, per_episode=8):\n', 'def write(ep, title, header, notes, segs, wear=None, per_episode=8):\n    if ERRS and not os.environ.get("LINT_OK"):\n        raise SystemExit(f"{ep}：{len(ERRS)} 处 ❌（规则见 playbook/09 G 节），plan_src 未写出；确认无误可 LINT_OK=1")\n', 1)
        open(os.path.join(SKILL, pw), 'w', encoding='utf-8').write(s)

def sync_qc():
    cp('tools/vision_qc.py', 'scripts/vision_qc.py'); cp('tools/vqc.swift', 'scripts/vqc.swift')
    ensure('scripts/qc_lib.py', 'import vision_qc', '''    try:                                                       # 画面自动质检：模型自带字幕 / 片头空镜（scripts/vision_qc.py，需先 swiftc -O scripts/vqc.swift -o tools/bin/vqc）
        import vision_qc
        vi = vision_qc.check(ep, seg, clip)
        if vi: issues += vi; status = "FAIL"
    except ImportError:
        pass
''', '            issues.append(f"多说了词：转写 {got} 词，台词共 {total} 词（疑似在停顿处插入了台词之外的话）"); status = "FAIL"\n')

def sync_tools():
    for f in ('self_review.py', 'reroll.py', 'lesson_report.py', 'skill_sync.py'):
        cp(f'plans/{f}', f'templates/project/plans/{f}')
    cp('plans/autopilot.py', 'templates/project/plans/autopilot.py'); cp('plans/queue_worker.sh', 'templates/project/plans/queue_worker.sh')

def table_row(lid, x):
    t = os.path.join(SKILL, 'playbook/09_规则证据表.md'); s = open(t, encoding='utf-8').read()
    if '## G. 看片返工自动升级' not in s:
        s += ('\n## G. 看片返工自动升级（plans/skill_sync.py 写入；样本＝返工后重出的段，成＝质检过且自检/人工没再报）\n'
              '| 规则 | 等级 | 证据 | 日期 |\n|---|---|---|---|\n')
    samples = '、'.join(k for k, v in x.get('results', {}).items() if v) or '自检运行记录'
    lvl = '量产' if x['status'] == '已验证' else '无效'
    row = f"| {lid} {x['title']} | {lvl} | 成 {x['ok']} 败 {x['bad']}（{samples}，《Tangled》） | {time.strftime('%Y-%m-%d')} |\n"
    s = re.sub(rf'\| {re.escape(lid)} [^\n]*\n', '', s); s += row
    open(t, 'w', encoding='utf-8').write(s)

todo = [k for k, v in L.items() if v['status'] in ('已验证', '退回') and not v.get('synced')]
done = []
if todo and not DRY:
    kinds = {L[k]['kind'] for k in todo}
    if kinds & {'rule', 'hypothesis'}: sync_rules()
    if 'qc' in kinds: sync_qc()
    if 'tool' in kinds: sync_tools()
    for k in todo: table_row(k, L[k])
    msg = 'auto-upgrade: ' + '; '.join(f"{k} {L[k]['status']} (ok {L[k]['ok']}/bad {L[k]['bad']})" for k in todo)
    g = lambda *a: subprocess.run(['git', '-C', SKILL] + list(a), capture_output=True, text=True)
    g('add', '-A', 'playbook/09_规则证据表.md', 'templates/project/plans', 'scripts/vision_qc.py', 'scripts/vqc.swift', 'scripts/qc_lib.py')
    r = g('commit', '-m', msg + '\n\nVerified on Tangled in His Bed reworks; evidence in playbook/09 section G.\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>')
    h = g('rev-parse', '--short', 'HEAD').stdout.strip()
    if PUSH:
        pr = g('push')
        if pr.returncode: open('autopilot.log', 'a', encoding='utf-8').write(f"{time.strftime('%m-%d %H:%M:%S')} [升级] 推送失败：{pr.stderr[-200:]}\n")
    for k in todo: L[k].update(synced=time.strftime('%Y-%m-%d %H:%M'), commit=h); done.append(f"{k} {L[k]['status']} → skill {h}")
if not DRY: json.dump(L, open(LJ, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

if changed or done:
    with open(REC, 'a', encoding='utf-8') as f:
        f.write(f"\n## {time.strftime('%Y-%m-%d %H:%M')}\n" + ''.join(f'- {c}\n' for c in changed) + ''.join(f'- 同步进 skill：{d}\n' for d in done))
summary = {s: sum(v['status'] == s for v in L.values()) for s in ('验证中', '已验证', '退回')}
print('经验', summary, '| 本轮变化', len(changed), '| 同步', done or '无')
