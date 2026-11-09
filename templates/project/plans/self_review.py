"""每集拼好后的自检（autopilot 自动调用；第 N 集自检时 GPU 已经在出第 N+1 集）。
  python3 plans/self_review.py E05            出审片卡 + 让 Claude 看卡挑毛病
  python3 plans/self_review.py E05 --cards    只出审片卡（不调模型）
审片卡：review/自检/ENN/segNN.jpg —— 每个镜头取中间一帧，下面写这个镜头本来要拍什么。
看卡：本机 Codex（默认；SELF_REVIEW_MODEL=sonnet 改用 claude -p，需先登录；SELF_REVIEW=off 关掉），只挑"肉眼一看就错"的硬伤，结果 review/自检/ENN/review.json。
处理：
  random 类（换种子大概率就好：重影、多余的人、倒置、字幕、乱码、空镜）→ 自动进返工队列，每段只自动返一次
  prompt 类（提示词本身导致：道具状态、穿着、动作方向……）→ 记到 review/自检待办.md，由我改分镜后再返工
每条都记进 review/教训账本.jsonl（类别统计见 plans/lesson_report.py），同类问题多了就落成 plans/pw.py 的编译规则。"""
import json, os, re, subprocess, sys, time
from PIL import Image, ImageDraw, ImageFont
PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); os.chdir(PIPE)
FONT = '/System/Library/Fonts/STHeiti Medium.ttc'
ep = sys.argv[1]; only_cards = '--cards' in sys.argv
OUT = f'review/自检/{ep}'; os.makedirs(OUT, exist_ok=True)
asm = json.load(open(f'review/compare/{ep}_asm.json'))
src = {str(s['id']): s for s in json.load(open(f'episodes/{ep}/plan_src.json'))['segments']}
LOGF = 'autopilot.log'
def log(m): open(LOGF, 'a', encoding='utf-8').write(f'{time.strftime("%m-%d %H:%M:%S")} [自检] {m}\n')


def wrap(d, s, f, w):
    out, cur = [], ''
    for ch in s:
        if d.textlength(cur + ch, font=f) > w: out.append(cur); cur = ch
        else: cur += ch
    return out + [cur]


def card(seg):
    s = src[str(seg['id'])]; clip = f"episodes/{ep}/{seg['clip']}"
    tiles, t = [], 0.0
    f_big = ImageFont.truetype(FONT, 22); f_small = ImageFont.truetype(FONT, 17)
    for k, x in enumerate(s['shots'], 1):
        mid = t + x['dur'] / 2; t += x['dur']
        fp = f'{OUT}/_t.jpg'
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', f'{mid:.2f}', '-i', clip, '-frames:v', '1', '-vf', 'scale=300:-1', fp])
        im = Image.open(fp).convert('RGB'); W, H = im.size
        tile = Image.new('RGB', (W, H + 150), 'white'); tile.paste(im, (0, 0)); d = ImageDraw.Draw(tile)
        d.text((6, H + 4), f'镜{k} {mid:.1f}s', fill='black', font=f_big)
        for i, line in enumerate(wrap(d, re.sub(r'\s+', ' ', x['cn']), f_small, W - 10)[:6]):
            d.text((6, H + 32 + i * 19), line, fill='black', font=f_small)
        tiles.append(tile)
    W, H = tiles[0].size; cols = 3; rows = (len(tiles) + 2) // 3
    sheet = Image.new('RGB', (W * cols, H * rows), 'white')
    for i, tl in enumerate(tiles): sheet.paste(tl, ((i % cols) * W, (i // cols) * H))
    p = f"{OUT}/seg{int(seg['id']):02d}.jpg"; sheet.save(p, quality=82)
    if os.path.exists(f'{OUT}/_t.jpg'): os.remove(f'{OUT}/_t.jpg')
    return p


cards = [card(s) for s in asm['segments']]
print(ep, '审片卡', len(cards), '张 →', OUT)
if only_cards or os.environ.get('SELF_REVIEW') == 'off': sys.exit(0)

model = os.environ.get('SELF_REVIEW_MODEL', 'codex')
PROMPT = f"""你是短剧审片员。下面是 {ep} 每一段的审片卡（一张卡 = 一段 15 秒，每格 = 一个镜头的中间帧，格子下面的中文是这个镜头本来要拍的内容）。
用 Read 工具逐张看完这些图：
{chr(10).join(os.path.abspath(c) for c in cards)}

只挑"观众一眼就会觉得错"的硬伤，不要挑审美、构图、表演细节。检查清单：
1 同一个人在一个画面里出现两次，或者多出描述里没有的人
2 画面倒置；描述里有人，画面却是空场景
3 道具错：戒指/项链/吊坠数量或位置不对，物件状态和描述相反（拉链、门、鞋、杯子）
4 穿着和描述不符，或和同一段其他镜头不一致
5 画面上有字幕、乱码文字、不该有的品牌标志
6 皮肤：发红像烫伤、伤痕像溃烂/缝线/纹身
7 动作方向和描述相反（拉高写成拉低等）
8 肢体：多余的手、重影、畸形
9 场景跳：同一场戏背景明显变成另一个地方

每个问题给一个类别：random = 换个随机种子大概率就好（重影、多余的人、倒置、字幕、乱码、空镜、畸形）；prompt = 描述本身就会导致或描述和参考冲突（道具状态、穿着、动作方向、场景）。
只输出一个 JSON 数组，不要别的文字。每项：{{"seg": 段号整数, "shot": 镜号整数, "check": 清单编号, "category": "random"或"prompt", "problem": "一句中文，说清楚画面里看到什么", "severity": "high"或"medium"}}。
没有问题就输出 []。拿不准的不要报。"""
if model == 'codex':                                      # 默认：本机已登录的 Codex（无头 claude 需要另外登录）
    src_ = open('plans/gen_refs.py', encoding='utf-8').read().split('\nargs = sys.argv[1:]')[0]; g_ = {'__file__': 'plans/gen_refs.py'}; exec(src_, g_)
    cmd = [g_['CODEX_BIN'], 'exec', '--skip-git-repo-check', '-s', 'read-only', '-c', 'model_reasoning_effort="medium"', '-o', f'{OUT}/_last.txt']
    for c in cards: cmd += ['-i', c]
    r = subprocess.run(cmd + ['--', PROMPT.replace('用 Read 工具逐张看完这些图', '附件里的图按顺序就是这些审片卡')], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=1800)
    txt = open(f'{OUT}/_last.txt', encoding='utf-8').read() if os.path.exists(f'{OUT}/_last.txt') else r.stdout
else:
    r = subprocess.run(['claude', '-p', PROMPT, '--model', model, '--allowedTools', 'Read', '--output-format', 'text'], capture_output=True, text=True, timeout=1800)
    txt = r.stdout.strip()
if not re.search(r'\[', txt or ''): log(f'{ep} 自检没拿到结果：{(txt or r.stderr)[-200:]}')
m = re.search(r'\[.*\]', txt or '', re.S)
try:
    items = json.loads(m.group(0)) if m else []
except ValueError:
    items = []; log(f'{ep} 自检输出解析失败：{txt[:200]}')
json.dump(items, open(f'{OUT}/review.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
log(f'{ep} 自检完成（{model}）：{len(items)} 处')
if os.environ.get('SELF_REVIEW_DRY'):
    for it in items: print(it)
    sys.exit(0)

todo = open('review/自检待办.md', 'a', encoding='utf-8')
auto = set()
for it in items:
    open('review/教训账本.jsonl', 'a', encoding='utf-8').write(json.dumps({'ep': ep, **it, 'at': time.strftime('%Y-%m-%d %H:%M')}, ensure_ascii=False) + '\n')
    seg = int(it.get('seg', 0)); mark = f'episodes/{ep}/.selfreview_{seg}'
    if it.get('category') == 'random' and it.get('severity') == 'high' and not os.path.exists(mark):
        auto.add(seg); open(mark, 'w').write(it['problem'])
    else:
        todo.write(f"- [ ] {ep} Seg{seg} 镜{it.get('shot')}（{it.get('category')}/{it.get('severity')}）：{it.get('problem')}  卡：{OUT}/seg{seg:02d}.jpg\n")
if auto:
    subprocess.run([sys.executable, 'plans/reroll.py', 'add', ep] + [str(s) for s in sorted(auto)] + ['--reason', '自检 random 类硬伤'])
    log(f'{ep} 自动返工 {sorted(auto)}')
print(f'{ep} 自检 {len(items)} 处；自动返工 {sorted(auto)}')
