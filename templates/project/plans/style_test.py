"""风格试样：用 library/style_lock.json 的母提示词 + 已定稿的场景/人物图，出 9:16 剧照，判断全剧基调。只用于定风格，不当资产。
用法：python3 plans/style_test.py [F1 F2 ...]   输出 review/style_tests/<ID>_<场景>.png（已有则另存 _vN）"""
import json, os, subprocess, sys, time
PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.argv = [sys.argv[0], '/dev/null'] + sys.argv[1:]          # 借用 gen_refs 的 codex 定位与模型默认值
import importlib.util
spec = importlib.util.spec_from_file_location('g', os.path.join(PIPE, 'plans', 'gen_refs.py'))
src = open(spec.origin, encoding='utf-8').read().split('\nargs = sys.argv[1:]')[0]
g = {'__file__': spec.origin}; exec(compile(src, spec.origin, 'exec'), g)
BIN, MODEL, FALLBACK = g['CODEX_BIN'], g['MODEL'], g['FALLBACK_MODEL']
LOCK = json.load(open(os.path.join(PIPE, 'library', 'style_lock.json'), encoding='utf-8'))
OUT = os.path.join(PIPE, 'review', 'style_tests'); os.makedirs(OUT, exist_ok=True)
IMG = lambda i: os.path.join(PIPE, 'assets', 'images', i + '.png')

CORE = ("A single still frame from a live-action American romantic comedy series, vertical 9:16 composition, the kind of "
        "polished frame a streaming romance would use as its key art. " + LOCK['reference_prompt_suffix_en'] +
        " Shallow depth of field: the people are sharp and the background melts into soft readable shapes.")
V = "Vivian, a slim 24-year-old Chinese American woman with black hair pinned back, straight brows, thin lips and a still, deadpan face"
J = "Julian, a 31-year-old man with a long jaw, gray eyes, short dark hair graying at the temples and a boxer's shoulders"

F = {
 'F1': ('kitchen', ['D-KITCHEN', 'C01-FLANNEL', 'C02-TEE'],
   f"Picture 1 is the location, Picture 2 is Vivian, Picture 3 is Julian; keep their faces, hair and clothes exactly. "
   f"Morning in the long Franklin Street loft kitchen: low warm sun pours through the tall factory windows at frame-left across the butcher-block island and dark oak shelves, aged red brick behind. "
   f"{V}, in her buttoned sheep-print flannel pajamas, sits on a steel stool at the island in the foreground at frame-right with a laptop and a mug, reading the screen. "
   f"{J}, in a white tank top and flannel trousers, stands at the black range in the midground at frame-left, half turned toward her, a pan in his hand, the corner of his mouth almost smiling. "
   "Palette: charcoal, brick and dark oak warmed by gold sunlight."),
 'F2': ('office50', ['D-OFFICE50', 'C01-OFFICE', 'C02-SUIT'],
   f"Picture 1 is the location, Picture 2 is Vivian, Picture 3 is Julian; keep their faces, hair and clothes exactly. "
   f"Day in the vast fiftieth-floor corner office: cool, clean daylight from the full-height window over Central Park falls from frame-left, the room steel grey and glass white with one long dark walnut desk. "
   f"{J}, in his dark navy suit, sits behind the desk in the midground, level and unreadable, looking up at her. "
   f"{V}, in her gray suit and white shirt, stands in the foreground at frame-right holding a thin folder against her chest, chin up, eyes on him. "
   "Palette: steel grey and glass white, the navy suit and walnut as the only depth of colour."),
 'F3': ('perry', ['N-PERRY', 'C01-TURTLE'],
   f"Picture 1 is the location, Picture 2 is Vivian; keep her face, hair and clothes exactly. "
   f"Early morning in the small Perry Street studio under the sloped ceiling: soft daylight through the one narrow window, cream walls, faded denim-blue bedding, a small butter-yellow lamp still on. "
   f"{V}, in her camel turtleneck and gray skirt with an ID lanyard, stands at the window with a chipped mug in both hands, tortoiseshell glasses on, looking out at the street, the light soft on one side of her face. "
   "Palette: cream, faded blue and butter yellow, tortoiseshell brown as the accent."),
 'F4': ('grounds', ['M-GROUNDS', 'C01-WHITE', 'C02-SUIT'],
   f"Picture 1 is the location, Picture 2 is Vivian, Picture 3 is Julian; keep their faces, hair and clothes exactly. "
   f"Late golden afternoon on the Thorne Manor stone terrace in the Hamptons: the sun low behind them puts a warm golden rim on hair and shoulders, the long sea-grass-green lawn slopes to a bright blue bay. "
   f"{V}, in her high-necked white silk gown and tortoiseshell glasses, stands at the balustrade in the foreground at frame-left, looking out at the bay. "
   f"{J}, in his dark navy suit, stands two steps below her in the midground at frame-right, looking up at her, not at the view. "
   "Palette: sun-bleached white, sea-grass green and bay blue, airy and bright."),
 'F5': ('manor', ['N-MANOR', 'C01-BLACK', 'P01'],
   f"Picture 1 is the location, Picture 2 is Vivian, Picture 3 is the emerald pendant; keep her face, hair and dress exactly and the pendant's shape exactly. "
   f"Night in the Thorne Manor great hall: firelight from the stone fireplace and one brass lamp, dark walnut panelling, deep burgundy curtains, black-and-white marble floor falling into shadow. "
   f"{V}, in the short black dress, stands by the fireplace in a medium close-up from the waist up, the pear-shaped emerald pendant on its fine chain at her collarbone catching the firelight, her fingers just touching it, her eyes toward someone off frame-right. "
   "Palette: walnut, burgundy and brass; the emerald is the only green in the frame."),
}

ids = sys.argv[2:] or list(F)
for i in ids:
    name, refs, body = F[i]
    out = os.path.join(OUT, f'{i}_{name}.png'); n = 2
    while os.path.exists(out): out = os.path.join(OUT, f'{i}_{name}_v{n}.png'); n += 1
    rel = os.path.relpath(out, PIPE)
    ask = ('Use your built-in image generation tool to generate exactly one image, portrait 2:3 (1024x1536), from the prompt below, '
           'using the attached reference images as described. Do not change the prompt. '
           f'Save the resulting PNG into this workspace as {rel}. Do nothing else and edit no other files. '
           'When done, reply with only the saved path.\n\nPROMPT:\n' + CORE + '\n\n' + body)
    cmd = [BIN, 'exec', '-m', MODEL, '-c', 'model_reasoning_effort="low"', '--skip-git-repo-check', '-s', 'workspace-write', '-C', PIPE]
    for r in refs: cmd += ['-i', IMG(r)]
    cmd += ['--', ask]
    t = time.time()
    r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0 and 'not supported' in (r.stdout + r.stderr):
        cmd[cmd.index('-m') + 1] = FALLBACK
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if not os.path.exists(out):   # Codex 生成了图但没存进项目（如参数过长）：从它自己的缓存里取本次最新的一张
        import glob
        c = [f for f in glob.glob(os.path.expanduser('~/.codex/generated_images/*/*.png')) if os.path.getmtime(f) > t]
        if c: import shutil; shutil.copy(max(c, key=os.path.getmtime), out)
    ok = os.path.exists(out)
    print(f'{time.strftime("%H:%M")} {i} {"✅ " + rel if ok else "❌ " + (r.stdout + r.stderr)[-600:]} {time.time() - t:.0f}s', flush=True)
