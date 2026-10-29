#!/usr/bin/env python3
"""S4/S5 构建与校验：从 plan.json + 对白锁定文件生成一集的全部产出，并做自动校验。

用法：python build_episode.py <集目录> [--voices voices.json] [--check-only]
读取：<集目录>/plan.json、<集目录>/02_dialogue_lock.json
生成：04_storyboard.md、03_budget.json、05_prompts/segXX.md + segXX.meta.json（官方 Ref2VA 英文）、
      05_prompts/segXX.bilingual.md（中英对照单文件：英文上传，中文给编辑看）；
      加 --legacy-wenwu 才另外输出旧的 05_prompts_wenwu/segXX.txt；09_qc.md 只在不存在时创建（不覆盖已填内容）。
任何校验失败都以非零退出码结束，且不写文件。只用标准库。
"""
import argparse, hashlib, json, os, re, sys

ap = argparse.ArgumentParser()
ap.add_argument('epdir'); ap.add_argument('--voices'); ap.add_argument('--check-only', action='store_true')
ap.add_argument('--locks', help='资产文字锁 asset_locks.json（默认自动找流水线根目录下的）')
ap.add_argument('--force', action='store_true', help='覆盖被手工改过的双语提示词文件')
ap.add_argument('--legacy-wenwu', action='store_true', help='额外输出旧的 05_prompts_wenwu/（默认不再输出）')
a = ap.parse_args()
P = lambda *x: os.path.join(a.epdir, *x)
plan = json.load(open(P('plan.json'), encoding='utf-8'))
lock = json.load(open(P('02_dialogue_lock.json'), encoding='utf-8'))['lines']
L = {x['id']: x for x in lock}
errors, warnings = [], []
def err(msg): errors.append(msg)
def warn(msg): warnings.append(msg)
HEAD_MIN = plan.get('dialogue_headroom_min', 0.3)
GAZE = re.compile(r"\b(eyes?|looks?|looking|gaze|glances?|stares?|staring|watch(?:es|ing)?|studying|studies)\b", re.I)
HOLD = re.compile(r"\b(holds?|settles?|stays?|to the end|final second|freezes)\b", re.I)

def ts(t):
    m = int(t // 60); s = t - 60 * m
    return f"{m:02d}:{s:06.3f}"

_SPEECH_V = (r"says?|said|tells|told|asks|asked|demands|demanded|protests|protested|shrieks|snaps|whispers|murmurs|mutters|wails|declares|orders|warns|"
             r"exclaims|cries out|shouts|yells|answers|replies|insists|explains|admits|confesses|announces|stammers|mumbles|moans|sobs|pleads|begs|reads out|notes")
_SPEECH_RX = re.compile(rf"\b(?:{_SPEECH_V})\b[^;.]*", re.I)


def scrub_speech(t):
    """总述（summary）里不写台词内容的转述。
    2026-10-29 实测：总述里 "tells him to release her, the door was unlocked…" 这类转述会被 H3 当台词念出来——
    E12 Seg7 / E13 Seg5 / E11 Seg7 都是先含糊地复述一遍转述、再说真正的台词（12/90 段被质检抓到"多说了词"）。
    这里把总述里"说话动词 + 内容"的整段（到下一个分号/句号）换成 speaks，台词只留在镜头里的 {{d:Lx}}。"""
    return re.sub(r"\s+", " ", _SPEECH_RX.sub("speaks", t)).replace("speaks speaks", "speaks")

def pace(t):
    """台词里的省略号（...）在提示词里换成逗号：用词一字不改，只改停顿记号。
    2026-10-29 实测：E04 Seg5 / E06 Seg8 / E09 Seg6 三段的台词在"..."处被模型塞进乱码插词（"Aflac DuVarek tangles her line on us"），
    重出 2 次都一样；14 句含省略号的台词里 4 句 <0.85，74 句不含的只有 5 句。质检仍按锁定原文（含 "..."）比对。"""
    t = re.sub(r"\s*(?:\.{3,}|…)\s*$", ".", t.strip())
    return re.sub(r"\s*(?:\.{3,}|…)\s*", ", ", t).replace(", ?", "?").replace(", !", "!").replace(",,", ",")
def r_en(s):  return re.sub(r'\{\{d:(L\d+)\}\}', lambda m: f"<d>[English] {pace(L[m.group(1)]['text_en'])}</d>", s)
def r_cn(s):  return re.sub(r'\{\{q:(L\d+)\}\}', lambda m: f"\"{pace(L[m.group(1)]['text_en'])}\"", s)

SECTIONS = ['subject_definitions', 'summary', 'retention_analysis', 'detailed_description', 'overall_soundscape', 'non_diegetic_music']
def blk(key, text): return f"<!-- EN:{key} -->\n{text}\n<!-- /EN -->"
def cnb(text): return f"<!-- CN -->\n{text}\n<!-- /CN -->"
def extract_en(md):
    parts = {}
    for key, text in re.findall(r'<!-- EN:(\w+) -->\n(.*?)\n<!-- /EN -->', md, re.S):
        parts.setdefault(key, []).append(text)
    return '\n\n'.join(f"{k}:\n" + '\n'.join(parts[k]) for k in SECTIONS if k in parts) + '\n'
def bilingual(s, e, w, sd, shot_pairs, intro):
    n = s['id']
    md = [f"# {plan['episode']} · Seg{n:02d}｜{s['scene']}｜{plan['segment_sec']:.0f}s｜链 {s['chain']}｜接下一段 {s['connection_to_next']}｜{plan['version']}", '',
          '> 只有 `<!-- EN:… -->` 与 `<!-- /EN -->` 之间的英文会上传给 H3；`<!-- CN -->` 中文只供编辑阅读。',
          '> 本文件由 `plan.json` 生成。要改内容请改 `plan.json` 后重新运行 build_episode.py（手工改动会被检测到并提示）。', '',
          '## 参考（上传顺序）', '', '| 槽位 | 标签 | 内容 |', '|---|---|---|']
    ki = ka = 0
    for r in s['refs']:
        if r[0].startswith('Picture'): slot = f'ref_image_{ki}'; ki += 1
        else: slot = f'ref_audio_{ka}'; ka += 1
        md.append(f"| {slot} | {r[0]} | {r[1]} |")
    md += ['', '## 总述', '', cnb(r_cn(w['open'])), '', blk('subject_definitions', '\n'.join(sd)), '',
           blk('summary', f"{e['tag']} {scrub_speech(e['summary'])}"), '', blk('retention_analysis', '\n'.join(e['retention'])), '',
           '## 镜头', '', blk('detailed_description', r_en('\n'.join(intro))), '']
    for k, t0, t1, sh, en_line in shot_pairs:
        md += [f"### 镜头 {k} · {t0:.1f}–{t1:.1f}s" + (f"｜对白 {sh['dialogue']}" if sh['dialogue'] else ''), '',
               cnb(r_cn(sh['wenwu'])), '', blk('detailed_description', r_en(en_line)), '']
    md += ['## 表演与视觉母题（仅中文）', '', cnb('表演肌理：' + r_cn(w['perf']) + '\n视觉母题：' + w['visual']), '',
           '## 声音', '', cnb(w['sound']), '', blk('overall_soundscape', e['soundscape']), '', blk('non_diegetic_music', 'N/A'), '']
    return '\n'.join(md)

ID_RE = re.compile(r'\b[CSP]\d{2}\b|\bP\d{2}-[A-Z]+\b')
NEG_EN = re.compile(r"\b(not|no|never|without|nothing|none|cannot)\b|n't", re.I)
NEG_CN = ['不要', '禁止', '不得', '不能', '没有', '不会', '不出现', '避免']
LABEL = re.compile(r'<(Picture|Audio) (\d+)>')
subtexts = [re.sub(r'[A-Za-z0-9 .\-:/$,]+', '', x['subtext_cn_NOT_FOR_PROMPT'].replace('（中文潜台词：', '').rstrip('）'))[:10] for x in lock if x['subtext_cn_NOT_FOR_PROMPT']]   # 只比对中文部分（英文名/代码会与台词原文撞车）

segs = plan['segments']
if len(segs) != plan['segments_per_episode']:
    err(f"段数 {len(segs)} ≠ {plan['segments_per_episode']}")

voices = None
if a.voices:
    v = json.load(open(a.voices, encoding='utf-8'))
    voices = {x['character'].lower() for x in v.get('voices', [])} | {x['character'].lower() for x in v.get('prompt_voices', [])}

out_en, out_cn, metas, used_en, used_cn, out_bi = {}, {}, {}, [], [], {}
locks_path = a.locks or next((c for c in (os.path.join(a.epdir, '..', '..', 'asset_locks.json'),) if os.path.isfile(c)), None)
LOCKS = json.load(open(locks_path, encoding='utf-8'))['locks'] if locks_path else {}
for s in segs:
    n = s['id']; e = s['en']
    total = round(sum(x['dur'] for x in s['shots']), 3)
    if abs(total - plan['segment_sec']) > 1e-6: err(f"Seg{n} 镜头时长合计 {total} ≠ {plan['segment_sec']}")
    t, body, wl, starts, shot_pairs = 0.0, [plan['styles'][s['light']], e['count']], [], [], []
    for k, sh in enumerate(s['shots'], 1):
        if sh['dialogue']:
            d = sh['dialogue']
            if d not in L: err(f"Seg{n} 引用了不存在的台词 {d}"); continue
            head = sh['dur'] - L[d]['est_sec']
            if head < HEAD_MIN - 1e-6: err(f"Seg{n} 镜头{k} 时长 {sh['dur']}s 给 {d}（估 {L[d]['est_sec']}s）的余量只有 {head:.1f}s，至少 {HEAD_MIN}s（RETRO L4）")
            elif head > 1.5: warn(f"Seg{n} 镜头{k} 给 {d} 的余量 {head:.1f}s 偏大，模型可能提前切镜；台词后补一个可见的停留动作（RETRO L4）")
            if '{{d:%s}}' % d not in sh['en']: err(f"Seg{n} 镜头{k} 英文未包含 {d}")
            if '{{q:%s}}' % d not in sh['wenwu']: err(f"Seg{n} 镜头{k} 中文未包含 {d}")
            if voices is not None and L[d]['speaker'].lower() not in voices: err(f"Seg{n} 说话人 {L[d]['speaker']} 不在声音清单里")
        body.append(f"[Shot {k}] " + (sh['en'] if k == 1 else f"At {ts(t)}, {sh['en']}"))
        wl.append(f"镜头 {k:02d}。{t:.1f}–{t + sh['dur']:.1f}秒。{sh['wenwu']}")
        starts.append(t); shot_pairs.append((k, t, t + sh['dur'], sh, body[-1]))
        t = round(t + sh['dur'], 3)
    used_en += re.findall(r'\{\{d:(L\d+)\}\}', '\n'.join(body)); used_cn += re.findall(r'\{\{q:(L\d+)\}\}', '\n'.join(wl) + s['wenwu']['open'] + s['wenwu']['perf'])
    sd = ([e['first_frame']] if e['first_frame'] else []) + e['subjects'] + e['audios']
    en = '\n\n'.join(['subject_definitions:\n' + '\n'.join(sd), f"summary:\n{e['tag']} {scrub_speech(e['summary'])}",
                      'retention_analysis:\n' + '\n'.join(e['retention']), 'detailed_description:\n' + r_en('\n'.join(body)),
                      'overall_soundscape:\n' + e['soundscape'], 'non_diegetic_music:\nN/A']) + '\n'
    w = s['wenwu']
    cn = (r_cn(w['open']) + "\n\n时间线：\n" + r_cn('\n'.join(wl)) + "\n\n表演肌理：" + r_cn(w['perf']) +
          "\n\n声音脉络：" + w['sound'] + "\n\n视觉母题：" + w['visual'] + "\n")
    out_bi[n] = bilingual(s, e, w, sd, shot_pairs, body[:2])
    # --- RETRO 检查 ---
    subj_people = [(m.group(1), m.group(2)) for m in (re.match(r"<Subject (\d+)> is ([A-Z][\w.]*(?: [A-Z][\w.]*)?)", x) for x in e['subjects']) if m]
    who = [re.escape(nm) for _, nm in subj_people] + [re.escape(nm.split()[-1]) for _, nm in subj_people] + [f"<Subject {k}>" for k, _ in subj_people]
    PERSON_CU = re.compile(r"close-up (?:of|on) (?:" + "|".join(who or ["@@"]) + r")(?!['’]s (?:left |right |gloved |wet |open |shaking )?(?:hands?|wrists?|fingers?|thumb\w*|palm|feet|foot|shoes?|loafers?|knuckles|fist|heels?|trainers?|[\w-]*\s?pocket|track-bottoms pocket))", re.I) if who else None
    for k, sh in enumerate(s['shots'], 1):
        txt = sh['en']
        person = (PERSON_CU and PERSON_CU.search(txt)) or re.search(r"close-up of [\w'’ ]{0,24}\bface\b", txt, re.I)
        if person and not GAZE.search(txt):
            warn(f"Seg{n} 镜头{k} 是人物近景但没写视线落点（RETRO L5）")
    if s['connection_to_next'] == 'TAIL_RELAY' and not HOLD.search(s['shots'][-1]['en']):
        warn(f"Seg{n} 是接力段，最后一镜没写停留/保持（尾帧可能不稳，RETRO L6）")
    for st in plan.get('state_locks', []):
        if n >= st['from_seg']:
            for r in s['refs']:
                if r[2] == st['ref_old']: err(f"Seg{n} 仍引用状态改变前的参考 {st['ref_old']}，应改用 {st['ref_new']}（{st.get('why','')}，RETRO L1）")
            for ph in st.get('forbid_en', []):
                if ph.lower() in json.dumps(e, ensure_ascii=False).lower() + ' '.join(x['en'] for x in s['shots']).lower():
                    err(f"Seg{n} 出现状态改变前的描述『{ph}』（{st.get('why','')}，RETRO L1）")
    # --- asset text locks ---
    for r in s['refs']:
        lk = LOCKS.get(r[2] or '', {})
        for word in lk.get('forbid_en', []):
            if re.search(r'\b' + re.escape(word) + r'\b', en, re.I): err(f"Seg{n} 英文与参考图 {r[2]} 冲突：出现了『{word}』（{lk.get('why', '')}）")
        for word in lk.get('forbid_cn', []):
            if word in cn: err(f"Seg{n} 中文与参考图 {r[2]} 冲突：出现了『{word}』（{lk.get('why', '')}）")
        for word in lk.get('require_en', []):
            if word.lower() not in en.lower(): err(f"Seg{n} 英文缺少参考图 {r[2]} 的锁定描述『{word}』")
    if extract_en(out_bi[n]) != en: err(f"Seg{n} 双语文件抽取出的英文与六段式不一致（内部错误）")
    # --- checks ---
    for name, txt in (('英文', en), ('中文', cn)):
        if ID_RE.search(txt): err(f"Seg{n} {name}提示词里出现了后台编号：{ID_RE.search(txt).group(0)}")
        for st in subtexts:
            if len(st) >= 6 and st in re.sub(r'[A-Za-z0-9 .\-:/$,]+', '', txt): err(f"Seg{n} {name}提示词混入了中文潜台词")
        labels = {f"{k} {i}" for k, i in LABEL.findall(txt)}
        reflabels = {r[0] for r in s['refs']}
        if labels != reflabels: err(f"Seg{n} {name}标签与参考清单不一致：多 {sorted(labels - reflabels)}，少 {sorted(reflabels - labels)}")
    scan = re.sub(r'<d>.*?</d>', '', r_en('\n'.join(body)) + '\n' + e['soundscape'])
    if NEG_EN.findall(scan): err(f"Seg{n} 英文描述含否定词 {NEG_EN.findall(scan)}（请改肯定式）")
    hits = [x for x in NEG_CN if x in cn]
    if hits: err(f"Seg{n} 中文含否定表达 {hits}（请改肯定式）")
    out_en[n], out_cn[n] = en, cn
    metas[n] = {'segment': n, 'version': plan['version'], 'mode': 'Ref2VA', 'duration_sec': f"{plan['segment_sec']:.2f}",
                'aspect': plan['aspect'], 'summary_tag': e['tag'], 'chain': s['chain'], 'connection_to_next': s['connection_to_next'],
                'detailed_words': len(r_en('\n'.join(body)).split()),
                'refs_in_upload_order': [{'label': r[0], 'name': r[1], 'backend_id': r[2]} for r in s['refs']],
                'dialogue_ids': [x['dialogue'] for x in s['shots'] if x['dialogue']],
                'shot_starts': [round(x, 3) for x in starts],
                'prompt_file': f'seg{n:02d}.bilingual.md',
                'bilingual_sha256': hashlib.sha256(out_bi[n].encode('utf-8')).hexdigest(),
                'en_sha256': hashlib.sha256(en.encode('utf-8')).hexdigest(),
                'notes': '编号只用于后台绑定；上传顺序必须与 Picture/Audio 编号一致'}

for a_, b_ in zip(segs, segs[1:]):
    if a_['connection_to_next'] == 'TAIL_RELAY' and b_['shots'][0]['dialogue'] and '双人' in a_['shots'][-1]['storyboard_cn'] \
       and ('双人' in b_['shots'][0]['storyboard_cn'] or '承接' in b_['shots'][0]['storyboard_cn']):
        warn(f"Seg{a_['id']}→Seg{b_['id']} 是双人画面接力且下一段开口即对白，容易跳切；建议下一段首镜换景别（RETRO L3）")

for i in L:
    if used_en.count(i) != 1: err(f"台词 {i} 在英文版出现 {used_en.count(i)} 次（应为 1）")
    if used_cn.count(i) != 1: err(f"台词 {i} 在中文版出现 {used_cn.count(i)} 次（应为 1）")

if warnings:
    print(f'警告 {len(warnings)} 条（不阻止生成）：'); [print('  ·', x) for x in warnings]
if errors:
    print('校验失败：'); [print('  -', x) for x in errors]; sys.exit(1)
print(f"校验通过：{len(segs)} 段 × {plan['segment_sec']} 秒，{len(L)} 句台词逐字各出现一次（英/中），无编号、无潜台词、标签一致、肯定式。")
if a.check_only: sys.exit(0)

os.makedirs(P('05_prompts'), exist_ok=True)
edited = []
for n in out_en:
    bp, mp = P('05_prompts', f'seg{n:02d}.bilingual.md'), P('05_prompts', f'seg{n:02d}.meta.json')
    if os.path.isfile(bp) and os.path.isfile(mp) and not a.force:
        old = json.load(open(mp, encoding='utf-8')).get('bilingual_sha256')
        cur = hashlib.sha256(open(bp, encoding='utf-8').read().encode('utf-8')).hexdigest()
        if old and cur != old: edited.append(bp)
if edited:
    print('以下双语文件被手工改过，未覆盖（把改动移进 plan.json 后加 --force 重新生成）：'); [print('  -', x) for x in edited]; sys.exit(3)
for n in out_en:
    open(P('05_prompts', f'seg{n:02d}.bilingual.md'), 'w', encoding='utf-8').write(out_bi[n])
    json.dump(metas[n], open(P('05_prompts', f'seg{n:02d}.meta.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    old_en = P('05_prompts', f'seg{n:02d}.md')
    if os.path.isfile(old_en): os.remove(old_en)            # 旧的纯英文文件已由双语文件取代
    if a.legacy_wenwu:
        os.makedirs(P('05_prompts_wenwu'), exist_ok=True)
        open(P('05_prompts_wenwu', f'seg{n:02d}.txt'), 'w', encoding='utf-8').write(out_cn[n])

ep = plan['episode']; sec = plan['segment_sec']
md = [f"# {ep}《{plan['title']}》{len(segs)} 段衔接分镜 {plan['version']}", '']
md += [f"> {h}" for h in plan['storyboard_header']]
md += ['> 台词一字不改（来自 `02_dialogue_lock.json`）；中文潜台词不进入提示词；编号只用于后台绑定。', '',
       '## 总览', '', '| 段 | 时间 | 场景 | 对白 | 接下一段 | 生成链 | 参考数 |', '|---|---|---|---|---|---|---|']
for s in segs:
    dl = ' '.join(x['dialogue'] for x in s['shots'] if x['dialogue']) or '—'
    st = int((s['id'] - 1) * sec); en_ = int(st + sec)
    md.append(f"| Seg{s['id']} | {st//60}:{st%60:02d}–{en_//60}:{en_%60:02d} | {s['scene']} | {dl} | {s['connection_to_next']} | {s['chain']} | {len(s['refs'])} |")
chains = {}
for s in segs: chains.setdefault(s['chain'], []).append(f"Seg{s['id']}")
md += ['', '生成链（链内用 TAIL_RELAY，前一段先过尾帧 QC；不同链互不依赖、可并行）：' + '；'.join(f"**{c}** = {'→'.join(v)}" for c, v in chains.items()) + '。', '']
for s in segs:
    md += [f"## Seg{s['id']}｜{s['scene']}｜链 {s['chain']}｜接下一段：{s['connection_to_next']}", '', '| 时间 | 镜头 |', '|---|---|']
    t = 0.0
    for sh in s['shots']:
        md.append(f"| {t:.1f}–{t + sh['dur']:.1f} | {sh['storyboard_cn']} |"); t += sh['dur']
    dls = [x['dialogue'] for x in s['shots'] if x['dialogue']]
    if dls:
        md += ['', '**对白（逐字）**', '']
        for i in dls:
            md += [f"- **{L[i]['speaker']}**（{L[i]['words']} 词，估 {L[i]['est_sec']}s）{L[i]['delivery_cn']}", f'  "{L[i]["text_en"]}"']
    md += ['', '**参考（上传顺序）**：' + ' → '.join(f"{r[0]} {r[1]}" + (f"〔{r[2]}〕" if r[2] else '') for r in s['refs']), '']
if plan.get('review_notes'):
    md += ['## 与剧本的差异（请确认）', ''] + [f"{k}. {x}" for k, x in enumerate(plan['review_notes'], 1)]
open(P('04_storyboard.md'), 'w', encoding='utf-8').write('\n'.join(md) + '\n')

budget = {'episode': ep, 'words_per_sec': json.load(open(P('02_dialogue_lock.json'), encoding='utf-8')).get('words_per_sec', 2.5),
          'segment_sec': sec, 'total_sec': sec * len(segs),
          'dialogue_total_words': sum(x['words'] for x in lock), 'dialogue_total_est_sec': round(sum(x['est_sec'] for x in lock), 1),
          'segments': [{'seg': s['id'], 'dialogue_ids': [x['dialogue'] for x in s['shots'] if x['dialogue']],
                        'dialogue_est_sec': round(sum(L[x['dialogue']]['est_sec'] for x in s['shots'] if x['dialogue']), 1),
                        'shots': len(s['shots']), 'chain': s['chain'], 'connection_to_next': s['connection_to_next']} for s in segs]}
json.dump(budget, open(P('03_budget.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

if not os.path.exists(P('09_qc.md')):
    rows = '\n'.join(f"| Seg{s['id']} | | A / B | | | | | | | | | 保留 / 改进 | |" for s in segs)
    open(P('09_qc.md'), 'w', encoding='utf-8').write(
        f"# {ep} 片段质检表\n\n格式：A = 官方英文六段式，B = WenWu 中文。每项填 ✓ 或 ✗，失败原因用账本里的词。\n\n"
        "| 段 | 版本 | 格式 | seed | ① 人脸/服装与参考一致 | ② 站位/方向正确 | ③ 道具与状态正确 | ④ 台词逐字清楚 | ⑤ 无乱码文字 | ⑥ 片尾稳定 | ⑦ 首尾状态与分镜一致 | 结论 | 失败原因 / 备注 |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|\n" + rows + "\n")
import subprocess as _sp                                  # 摄影检查（protocols/CINEMATOGRAPHY.md）：❌ 时构建失败，⚠ 只提示
_r = _sp.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shot_lint.py'), ep], capture_output=True, text=True)
print(_r.stdout.rstrip())
if _r.returncode:
    raise SystemExit('摄影检查有 ❌，先改分镜（见上）')
print('已生成：04_storyboard.md、03_budget.json、05_prompts/segXX.bilingual.md + segXX.meta.json' + ('、05_prompts_wenwu/' if a.legacy_wenwu else ''))
