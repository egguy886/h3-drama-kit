#!/usr/bin/env python3
"""S1 对白锁定 + S3 时长预算：从剧本 Markdown 提取每句对白，逐字锁定并估算时长。

用法：python lock_dialogue.py <剧本.md> <输出 02_dialogue_lock.json> [--wps 2.5] [--digit-adj 0.5]
剧本格式：说话人单独一行 **Name**，下面依次是（表演提示）、"英文台词"（直引号或“弯引号”）、（中文潜台词：…）。
只用标准库。
"""
import argparse, json, os, re

ap = argparse.ArgumentParser()
ap.add_argument('script'); ap.add_argument('out')
ap.add_argument('--wps', type=float, default=2.5, help='英文语速（词/秒），待实测校准')
ap.add_argument('--digit-adj', type=float, default=0.5, help='含 . 或 : 的数字词额外加的秒数')
a = ap.parse_args()

lines = open(a.script, encoding='utf-8').read().split('\n')
lock, scene = [], 0
for i, ln in enumerate(lines):
    m = re.match(r'^###\s*场\s*(\d+)', ln)
    if m: scene = int(m.group(1))
    m = re.match(r'^\*\*([A-Za-z][A-Za-z0-9 .]*)\*\*\s*$', ln)
    if not m: continue
    block = lines[i + 1:i + 6]
    for k, b in enumerate(block):                             # 2026-10-19：只看到下一个说话人之前，免得把下一句的表演提示算到这句
        if re.match(r'^\*\*[A-Za-z]', b): block = block[:k]; break
    QRE = r'^["\u201c](.*)["\u201d]\s*$'                      # 直引号或中文弯引号
    quote = next((re.match(QRE, b.strip()).group(1) for b in block if re.match(QRE, b.strip())), None)
    if quote is None: continue
    delivery = next((b.strip() for b in block if b.startswith('（') and '中文潜台词' not in b), '')
    sub = next((b.strip() for b in block if '中文潜台词' in b), '')
    words = len(quote.split())
    adj = a.digit_adj * sum(1 for w in quote.split() if re.search(r'\d', w) and re.search(r'[.:]', w))
    lock.append({'id': f'L{len(lock) + 1}', 'scene': scene, 'speaker': m.group(1).strip(), 'text_en': quote,
                 'delivery_cn': delivery, 'subtext_cn_NOT_FOR_PROMPT': sub, 'words': words,
                 'est_sec': round(words / a.wps + adj, 1)})
ep = re.match(r'(E\d+)', os.path.basename(a.script))
json.dump({'episode': ep.group(1) if ep else '', 'source': a.script, 'words_per_sec': a.wps, 'lines': lock},
          open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
tot = {}
for x in lock: tot[x['scene']] = round(tot.get(x['scene'], 0) + x['est_sec'], 1)
print(f"{len(lock)} 句，{sum(x['words'] for x in lock)} 词，估 {round(sum(x['est_sec'] for x in lock), 1)} 秒；按场：{tot}")
for x in lock:
    flag = '  ← 长句，考虑长镜头' if x['est_sec'] >= 9 else ''
    print(f"  {x['id']} 场{x['scene']} {x['speaker']}: {x['words']} 词 / {x['est_sec']}s{flag}")
