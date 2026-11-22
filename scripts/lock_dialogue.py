#!/usr/bin/env python3
"""S1 对白锁定 + S3 时长预算：兼容中英文剧本（**桑晚** / **桑晚 (V.O.)** / **Name**），逐字锁定并估算时长。"""
import argparse, json, os, re

ap = argparse.ArgumentParser()
ap.add_argument('script'); ap.add_argument('out')
ap.add_argument('--cps', type=float, default=3.8, help='中文语速（字/秒）')
ap.add_argument('--wps', type=float, default=2.5, help='英文语速（词/秒）')
ap.add_argument('--digit-adj', type=float, default=0.5, help='含 . 或 : 的数字词额外加的秒数')
a = ap.parse_args()

lines = open(a.script, encoding='utf-8').read().split('\n')
lock, scene = [], 0
SPK_RE = re.compile(r'^\*\*([^*【】\n]+?)\*\*\s*$')
FIELD_SKIP = {'出场人物', '造型', '核心道具', '开场站位', '场景站位'}
QRE = re.compile(r'^["\u201c](.*)["\u201d]\s*$')

for i, ln in enumerate(lines):
    m = re.match(r'^###\s*场\s*(\d+)', ln)
    if m:
        scene = int(m.group(1))
        continue
    m = SPK_RE.match(ln.strip())
    if not m:
        continue
    raw_spk = m.group(1).strip()
    if any(raw_spk.startswith(k) for k in FIELD_SKIP) or raw_spk.startswith('【Episode') or raw_spk.startswith('【第'):
        continue
    mode = 'VO' if ('V.O.' in raw_spk or 'VO' in raw_spk) else ('OS' if ('O.S.' in raw_spk or 'OS' in raw_spk) else 'ON')
    clean_spk = re.sub(r'\s*[\(（]\s*(?:V\.?O\.?|O\.?S\.?|O\.?C\.?)\s*[\)）]\s*', '', raw_spk).strip()
    block = lines[i + 1:i + 7]
    for k, b in enumerate(block):
        if SPK_RE.match(b.strip()) or b.strip().startswith('△') or b.strip().startswith('###'):
            block = block[:k]
            break
    quote = next((QRE.match(b.strip()).group(1) for b in block if QRE.match(b.strip())), None)
    if quote is None:
        continue
    delivery = next((b.strip() for b in block if (b.strip().startswith('（') or b.strip().startswith('(')) and '潜台词' not in b), '')
    sub = next((b.strip() for b in block if '潜台词' in b), '')
    cjk_chars = len(re.findall(r'[\u4e00-\u9fff]', quote))
    if cjk_chars > 0:
        units = cjk_chars
        est = max(1.2, round(cjk_chars / a.cps + 0.3, 1))
    else:
        units = len(quote.split())
        adj = a.digit_adj * sum(1 for w in quote.split() if re.search(r'\d', w) and re.search(r'[.:]', w))
        est = round(units / a.wps + adj, 1)
    lock.append({
        'id': f'L{len(lock) + 1}',
        'scene': scene,
        'speaker': clean_spk,
        'mode': mode,
        'text': quote,
        'text_en': quote,
        'delivery_cn': delivery,
        'subtext_cn_NOT_FOR_PROMPT': sub,
        'words': units,
        'est_sec': est,
    })

ep = re.match(r'(E\d+|ep\d+)', os.path.basename(a.script), re.I)
ep_id = ep.group(1).upper() if ep else ''
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
meta = {'episode': ep_id, 'source': os.path.basename(a.script), 'chars_per_sec': a.cps, 'words_per_sec': a.wps, 'lines': lock}
json.dump(meta, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
tot = {}
for x in lock:
    tot[x['scene']] = round(tot.get(x['scene'], 0) + x['est_sec'], 1)
print(f"{ep_id or os.path.basename(a.script)}: {len(lock)} 句，{sum(x['words'] for x in lock)} 字/词，估 {round(sum(x['est_sec'] for x in lock), 1)} 秒；按场：{tot}")
for x in lock:
    flag = '  ← 长句，考虑长镜头' if x['est_sec'] >= 9 else ''
    print(f"  {x['id']} 场{x['scene']} {x['speaker']} ({x['mode']}): {x['words']} 字/词 / {x['est_sec']}s{flag}")
