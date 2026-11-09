"""成功率与教训统计 → review/教训报告.md（autopilot 每轮会刷新）。
看三件事：①首次出片通过率（r1 第一次就 PASS）有没有在涨 ②自动重出主要因为什么 ③自检/看片问题按类别的分布。"""
import collections, glob, json, os, re
PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); os.chdir(PIPE)
rows = []
for p in sorted(glob.glob('episodes/E*/06_jobs/qc.jsonl')):
    ep = p.split('/')[1]
    for l in open(p, encoding='utf-8'):
        r = json.loads(l); r['ep'] = ep; rows.append(r)
first = {}
for r in rows:
    k = (r['ep'], r['seg'])
    if r['tag'].startswith('r1') and k not in first: first[k] = r['status']
by_ep = collections.defaultdict(lambda: [0, 0])
for (ep, s), st in first.items():
    by_ep[ep][1] += 1; by_ep[ep][0] += st != 'FAIL'
cause = collections.Counter()
for r in rows:
    if r['status'] == 'FAIL':
        for i in r['issues']:
            cause[('V1 自带字幕' if i.startswith('V1') else 'V2 片头空镜' if i.startswith('V2') else '多说了词' if '多说' in i
                   else '台词相似度低' if '相似度' in i else '开头/结尾' if ('开头' in i or '结尾' in i) else '其他')] += 1
sr = [json.loads(l) for l in open('review/教训账本.jsonl', encoding='utf-8')] if os.path.exists('review/教训账本.jsonl') else []
CHK = {1: '重复/多余的人', 2: '倒置/空镜', 3: '道具错', 4: '穿着不一致', 5: '字幕/乱码/品牌', 6: '皮肤/伤痕', 7: '动作方向反', 8: '肢体畸形', 9: '场景跳'}
chk = collections.Counter(CHK.get(int(x.get('check', 0)), '其他') for x in sr)
rq = [json.loads(l) for l in open('plans/reroll_queue.jsonl', encoding='utf-8')] if os.path.exists('plans/reroll_queue.jsonl') else []
out = ['# 教训报告（自动生成：python3 plans/lesson_report.py）', '',
       '## 台词质检一次通过率（r1 第一次质检就过；只管台词和字幕/空镜，不管画面内容）', '', '| 集 | 通过 | 段数 | 通过率 |', '|---|---|---|---|']
for ep in sorted(by_ep):
    a, n = by_ep[ep]; out.append(f'| {ep} | {a} | {n} | {a / n:.0%} |')
hist = [json.loads(l) for l in open('review/返工记录.jsonl', encoding='utf-8')] if os.path.exists('review/返工记录.jsonl') else []
bad = collections.defaultdict(set)
for x in hist: bad[x['ep']].add(x['seg'])
out += ['', '## 画面返工（看片 + 自检发现问题的段）', '', '| 集 | 返工段 | 段数 | 画面一次通过率 |', '|---|---|---|---|'] + [f"| {ep} | {len(bad[ep])} | {by_ep[ep][1]} | {1 - len(bad[ep]) / max(1, by_ep[ep][1]):.0%} |" for ep in sorted(bad)]
out += ['', '## 自动重出的原因（质检 FAIL 次数）', ''] + [f'- {k}：{v}' for k, v in cause.most_common()]
out += ['', '## 自检挑出的问题（按清单类别）', ''] + ([f'- {k}：{v}' for k, v in chk.most_common()] or ['- 暂无'])
out += ['', f'## 返工队列：{len(rq)} 段待出', ''] + [f"- {x['ep']} Seg{x['seg']}：{x['reason']}" for x in rq[:40]]
open('review/教训报告.md', 'w', encoding='utf-8').write('\n'.join(out) + '\n')
print('写入 review/教训报告.md')
