"""参考图提示词生成器：从 library 读资产，按工具包规范（角色三栏表 / 场景 45° 俯拍空镜 / 道具 2x2 产品照）写出可直接生图的英文提示词。
用法：python3 plans/ref_prompts.py <输出.md> ID [ID ...]
look_en（cast）只用于参考图，不进视频提示词。"""
import json, os, sys
PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
lib = lambda n: json.load(open(os.path.join(PIPE, 'library', n), encoding='utf-8'))
CAST, SCN, PROP = lib('cast.json'), lib('scenes.json'), lib('props.json')
TITLE = json.load(open(os.path.join(PIPE, 'project.json'), encoding='utf-8'))['series_title_en']
HEAD = (f'Create a clean production reference image sheet for the live-action short drama "{TITLE}". Use premium grounded live-action realism, '
        'natural skin and fabric texture with visible pores, physically plausible materials, and a neutral professional art-department presentation. '
        'This is a static reference sheet, not a video frame. Do not invent a logo, brand, readable text, readable number, signature, watermark or graphic interface; '
        'leave documents, screens, labels and signs blank.')
NEG = ('Negative constraints: no readable text, no random letters or numbers, no logos, no watermark, no subtitles, no duplicated limbs, no extra fingers, '
       'no mirrored geography, no glamour fashion styling, no film grain or cinematic colour grade, no unexplained prop, no extra people.')
def wear(v):
    w = v['wear_en']
    return w.split(' wears ', 1)[1] if ' wears ' in w else w
def char(cid, v):
    return (f'{HEAD}\n\nLayout: three panels side by side on a flat neutral mid-grey studio backdrop with soft even light. LEFT: a large three-quarter close-up '
            'portrait of the face and shoulders, eyes with small natural catchlights. MIDDLE: a full-body front view with the head cropped out at the top edge '
            '(frame from the neck down). RIGHT: a full-body back view. Same real person and identical outfit in all three panels; plain and unstyled.\n\n'
            f'Character: {v["look_en"]}. Skin is clean, smooth and evenly toned. Outfit: {wear(v)}. This is an adult.\n\n{NEG}')
def scene(sid, v):
    body = v['en'].split(' shown in {P}: ', 1)[1]
    return (f'{HEAD}\n\nLayout: one single image, a high-angle three-quarter wide view of the empty location, camera high in one corner looking diagonally down '
            'at about 45 degrees; one light logic with one consistent shadow direction; no people. Every door is closed, every screen is dark, every curtain is still.\n\n'
            f'Location: {body}. {v["layout_en"]} Light: {v.get("light_en", "")}.\n\n{NEG}')
def prop(pid, v):
    body = v['en'].split(' shown in {P}: ', 1)[1]
    # 车辆等大件俯视图容易画出结构错误（P04 踏板车大灯朝天、坐垫横贴），可在 props.json 用 views 换掉
    views = v.get('views', 'hero three-quarter view, side view, top view, and a close detail')
    if v.get('image_text'):
        # 画面里要出现可读文字的道具（手机屏幕、便签、合同、牌面、书脊）：文字逐字写进参考图，分镜里引用这张图，不靠后期叠字（2026-10-29 用户定）。
        # 文字只出现在这张图的提示词里，不进 props.json 的 en（en 会进视频提示词，且不能含否定词）。
        neg = NEG.replace('no readable text, no random letters or numbers, ', 'no misspelled words, no extra text beyond the exact text given, ')
        head = HEAD.replace('Do not invent a logo, brand, readable text, readable number, signature, watermark or graphic interface; leave documents, screens, labels and signs blank.', 'Do not invent a logo, brand, watermark or any text other than the exact text given below.')
        return (f'{head}\n\nLayout: a 2x2 product-photo sheet on a neutral warm-grey surface with soft directional light from one side and a small contact shadow: '
                f'{views}; identical object and identical text in all four panels, every view physically correct and consistent with the others.\n\n'
                f'Prop: {body}.\n\nExact text, spelled letter for letter, large and sharp and fully legible, in the same wording in every panel: {v["image_text"]}\n\n{neg}')
    return (f'{HEAD}\n\nLayout: a 2x2 product-photo sheet on a neutral warm-grey surface with soft directional light from one side and a small contact shadow: '
            f'{views}; identical object, scale and wear in all four panels, every view physically correct and consistent with the others.\n\n'
            f'Prop: {body}. Any screen or label is blank.\n\n{NEG}')
out, ids = sys.argv[1], sys.argv[2:]
parts = [f'# 参考图提示词 · {TITLE}\n\n生成后存为 assets/images/<ID>.png（多版本 <ID>_v2.png，取最大者）。\n']
for i in ids:
    if i in CAST: parts.append(f'## {i} {CAST[i]["name_cn"]}\n```\n{char(i, CAST[i])}\n```\n')
    elif i in SCN: parts.append(f'## {i} {SCN[i]["name_cn"]}\n```\n{scene(i, SCN[i])}\n```\n')
    elif i in PROP: parts.append(f'## {i} {PROP[i]["name_cn"]}\n```\n{prop(i, PROP[i])}\n```\n')
    else: sys.exit(f'未知 ID：{i}')
os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
open(out, 'w', encoding='utf-8').write('\n'.join(parts))
print(f'{len(ids)} 条 → {out}')
