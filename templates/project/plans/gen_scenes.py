"""新增一次性场景：从 plans/keys/new_scenes.py 的 S 登记到 library/scenes.json，并用 Codex 出四格场景参考图（和 22 个主场景同一模板）。
用法：python3 plans/gen_scenes.py [ID ...]   不写 ID = 全部还没有图的"""
import json, os, subprocess, sys, importlib.util
PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location('ns', os.path.join(PIPE, 'plans', 'keys', 'new_scenes.py')); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ids = sys.argv[1:] or [i for i in m.S if not os.path.exists(os.path.join(PIPE, 'assets', 'images', i + '.png'))]
LP = os.path.join(PIPE, 'library', 'scenes.json'); lib = json.load(open(LP, encoding='utf-8'))
TPL = open(os.path.join(PIPE, 'assets', 'prompts', 'scene_prop_prompts.md'), encoding='utf-8').read()
head = TPL[TPL.index('## D-DUANE'):]; head = head[head.index('```\n') + 4:]
pre, rest = head.split('Location: ', 1); neg = rest[rest.index('Negative constraints:'):].split('\n```')[0]
md = []
for i in ids:
    d = m.S[i]
    lib[i] = {"name": i, "name_cn": d['cn'], "en": f"the {d['name_en']} shown in {{P}}: " + d['en'], "layout_en": d['layout'], "layout_cn": d['layout'], "cn": d['cn'], "light_en": d['light']}
    md.append(f"## {i} {d['cn']}\n```\n{pre}Location: {d['en']}. {d['layout']} Light: {d['light']}.\n\n{neg}\n```\n")
json.dump(lib, open(LP, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
out = os.path.join(PIPE, 'assets', 'prompts', 'extra_scene_prompts.md')
old = open(out, encoding='utf-8').read() if os.path.exists(out) else ''
open(out, 'w', encoding='utf-8').write(old + '\n'.join(md))
if ids: subprocess.run([sys.executable, os.path.join(PIPE, 'plans', 'gen_refs.py'), out] + ids)
