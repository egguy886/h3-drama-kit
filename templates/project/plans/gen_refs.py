"""用本机 Codex CLI 内置生图批量出参考图：从 ref_prompts.py 写好的提示词文件里取对应 ID 的提示词，逐张生成到 assets/images/<ID>.png。
用法：python3 plans/gen_refs.py <提示词.md> ID [ID ...] [--force] [--ref 参考图.png] [--model gpt-6-luna]
- 已有 <ID>.png 默认跳过（--force 时另存 <ID>_vN.png，不覆盖）
- 角色 3:2 横版三栏；场景 3:2 横版；道具 1:1（2x2 产品照）
- 默认模型 gpt-6-luna（支持通过 --model 或环境变量 CODEX_MODEL 覆盖）
- 自动优先定位本机 Codex 桌面端最新内核 codex.exe，并通过 stdin=DEVNULL 防止 Windows 子进程阻塞
- --ref：附一张参考图（如已定稿的脸），让 Codex 在它基础上改，保住同一张脸"""
import glob, os, re, shutil, subprocess, sys, time

PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(PIPE, 'assets', 'images')
LOG = os.path.join(PIPE, 'assets', 'prompts', 'gen_log.txt')
MODEL = os.environ.get('CODEX_MODEL', 'gpt-6-luna')


def resolve_codex_bin():
    if os.environ.get('CODEX_BIN') and os.path.exists(os.environ['CODEX_BIN']):
        return os.environ['CODEX_BIN']
    cfg = os.path.expanduser(r'~\.codex\config.toml')
    if os.path.exists(cfg):
        txt = open(cfg, encoding='utf-8', errors='ignore').read()
        m = re.search(r"CODEX_CLI_PATH\s*=\s*['\"]([^'\"]+)['\"]", txt)
        if m and os.path.exists(m.group(1)):
            return m.group(1)
    candidates = glob.glob(os.path.expanduser(r'~\AppData\Local\OpenAI\Codex\bin\*\codex.exe'))
    if candidates:
        candidates.sort(key=os.path.getmtime, reverse=True)
        return candidates[0]
    return shutil.which('codex') or 'codex'


CODEX_BIN = resolve_codex_bin()

args = sys.argv[1:]
force = '--force' in args
ref = None
if '--ref' in args:
    i = args.index('--ref'); ref = os.path.abspath(args[i + 1]); del args[i:i + 2]
if '--model' in args:
    i = args.index('--model'); MODEL = args[i + 1]; del args[i:i + 2]
args = [a for a in args if a != '--force']
src, ids = args[0], args[1:]
text = open(src, encoding='utf-8').read()

def prompt_of(i):
    m = re.search(rf'^## {re.escape(i)} .*?\n```\n(.*?)\n```', text, re.S | re.M)
    if not m: sys.exit(f'提示词文件里没有 {i}')
    return m.group(1)

def target(i):
    p = os.path.join(IMG, f'{i}.png')
    if not os.path.exists(p): return p
    if not force: return None
    n = 2
    while os.path.exists(os.path.join(IMG, f'{i}_v{n}.png')): n += 1
    return os.path.join(IMG, f'{i}_v{n}.png')

os.makedirs(IMG, exist_ok=True)
os.makedirs(os.path.dirname(LOG), exist_ok=True)
for i in ids:
    out = target(i)
    if out is None:
        print(f'{i} 已有，跳过', flush=True); continue
    size = 'square 1:1 (1024x1024)' if i.startswith('P') else 'landscape 3:2 (1536x1024)'
    rel = os.path.relpath(out, PIPE)
    ask = (f'Use your built-in image generation tool to generate exactly one image, {size}, from the prompt below. '
           + (('Use the attached reference image: keep the same real person, face and hair exactly, and change only what the prompt describes. '
               if i.startswith('C') else
               'Use the attached reference image: it is the same place or object; keep its design, layout, materials and camera angle exactly, and change only what the prompt describes. ')
              if ref else '')
           + f'Do not change the prompt. Save the resulting PNG into this workspace as {rel}. '
           'Do nothing else and edit no other files. When done, reply with only the saved path.\n\nPROMPT:\n' + prompt_of(i))
    cmd = [CODEX_BIN, 'exec', '-m', MODEL, '-c', 'model_reasoning_effort="low"', '--skip-git-repo-check',
           '-s', 'workspace-write', '-C', PIPE]
    if ref: cmd += ['-i', ref]
    cmd += ['--', ask]   # -i 接受多个文件，不加 -- 会把提示词也当成图片吃掉
    t = time.time()
    r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8', errors='replace')
    ok = r.returncode == 0 and os.path.exists(out)
    line = f'{time.strftime("%m-%d %H:%M")} {i} {"✅ " + rel if ok else "❌ exit " + str(r.returncode)} {time.time() - t:.0f}s'
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')
        if not ok: f.write(((r.stdout or '') + (r.stderr or ''))[-1500:] + '\n')
