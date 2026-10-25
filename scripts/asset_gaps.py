#!/usr/bin/env python3
"""资产清单与缺口（只读、免费）：统计各集用到的角色/场景/道具/声线，查参考图和参考音频在不在，并给缺图的资产写好"参考图生成提示词"。

用法：python3 tools/asset_gaps.py              # 全部集
      python3 tools/asset_gaps.py E01-E10      # 指定集
输出：assets/00_资产清单与缺口.md（表格 + 每个缺图资产一段可直接粘贴到生图工具的提示词）

找图规则与 h3_run.py 相同：local_paths.json 指定 → assets/**/<ID>.png 或 <ID>_*.png（取文件名最大者）。
声线：assets/voices/<voice_id>_h3_32k.wav（或 <voice_id>.wav）给 H3；<voice_id>_master_48k.wav 给后期。
"""
import glob, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__)); PIPE = os.path.dirname(HERE)
J = lambda *p: json.load(open(os.path.join(PIPE, *p), encoding="utf-8"))
PROJ = J("project.json") if os.path.isfile(os.path.join(PIPE, "project.json")) else {}
LOCAL = J("local_paths.json") if os.path.isfile(os.path.join(PIPE, "local_paths.json")) else {}
ASSET_ROOT = os.path.join(PIPE, PROJ.get("asset_root", "assets"))
cast, scenes, props = J("library", "cast.json"), J("library", "scenes.json"), J("library", "props.json")
voices = J("voices.json") if os.path.isfile(os.path.join(PIPE, "voices.json")) else {"voices": [], "prompt_voices": []}
SERIES = PROJ.get("series_title_en", "this series")
ASPECT = PROJ.get("aspect", "9:16")
IMG = (".png", ".jpg", ".jpeg", ".webp")

# ---- 参考图提示词模板（《越线》资产图写法 v2：三栏人物表去头、场景 3/4 高机位 + 锚点 + 单光源、道具 2x2 产品照；用户用生图工具生成）----
PRE = (f'Create a clean production reference image sheet for the live-action short drama "{SERIES}". Use premium grounded live-action realism, natural skin and fabric texture with visible pores, '
       "physically plausible materials, and a neutral professional art-department presentation. This is a static reference sheet, not a video frame: no motion blur, no dialogue, no subtitles, no story action, no camera movement.\n\n"
       "Preserve the exact identity, age, proportions, wardrobe logic, spatial topology, material and state described below. Do not invent a logo, brand, readable text, readable number, signature, watermark or graphic interface. Leave documents, screens, labels and signs blank for post-production.")
CHAR = ("Layout (three panels side by side on a flat neutral mid-grey studio backdrop with soft even light): LEFT, a large three-quarter close-up portrait of the face and shoulders, the face turned slightly to one side, eyes with small natural catchlights; "
        "MIDDLE, a full-body front view with the head cropped out of frame at the top edge so only the neck down shows; RIGHT, a full-body back view. Same real person and identical wardrobe in all three panels. Plain and unstyled: no cinematic lighting, no colour grade.")
SCENE = ("Layout: one single image, a high-angle three-quarter wide view of the empty location, camera high in one corner looking diagonally down at about 45 degrees so the depth of the space and its main landmark are readable; "
         "one single light source with one consistent shadow direction; no people. Every door, lamp, screen and curtain is shown in its state BEFORE any story action (doors closed, lamps off, screens dark) unless stated otherwise.")
PROP = "Layout: 2x2 product-photo sheet on a neutral warm-grey surface with soft directional light from one side and a small contact shadow: hero three-quarter view, side view, top view, and a close detail; identical object, scale and wear in all four panels."
NEG = ("Negative constraints: no readable text, no random letters or numbers, no logos, no watermark, no subtitles, no duplicated limbs, no extra fingers, no mirrored geography, no identity drift, no age drift, no costume change, "
       "no glamour fashion styling, no film grain or cinematic colour grade on character sheets, no unexplained prop, no extra people.")
EDIT = ("Edit the attached reference image: {goal}. CHANGE: {change}. PRESERVE EXACTLY: the face, identity, age, hair, body proportions, pose, panel layout, camera angle, background, lighting and every detail not named in CHANGE. "
        "ONLY CHANGE: {change}. 100% identical otherwise.")


def eps(spec):
    allx = sorted(d for d in os.listdir(os.path.join(PIPE, "episodes")) if re.fullmatch(r"E\d+", d))
    if not spec:
        return allx
    out = []
    for p in spec:
        m = re.fullmatch(r"E(\d+)-E?(\d+)", p.upper())
        out += [f"E{i:02d}" for i in range(int(m.group(1)), int(m.group(2)) + 1)] if m else [p.upper()]
    return [e for e in out if e in allx]


def find(xid, exts):
    ov = LOCAL.get("images" if exts == IMG else "voices", {}).get(xid)
    if ov:
        p = ov if os.path.isabs(ov) else os.path.join(PIPE, ov)
        return [p] if os.path.isfile(p) else []
    c = []
    for pat in (xid + ".*", xid + "_*"):
        c += [x for x in glob.glob(os.path.join(ASSET_ROOT, "**", pat), recursive=True) if x.lower().endswith(exts)]
    return sorted(set(c))


def used_ids(ep):
    p = os.path.join(PIPE, "episodes", ep, "plan_src.json")
    if not os.path.isfile(p):
        return []
    src = json.load(open(p, encoding="utf-8"))
    out = []
    for s in src["segments"]:
        out += list(s.get("cast", [])) + ([s["scene_ref"]] if s.get("scene_ref") else []) + list(s.get("props", []))
    return out


def base_of(aid):
    """C01-RAIN → C01（同一人换装/状态的派生图，用局部修图从母图改）。"""
    parts = aid.split("-")
    for k in range(len(parts) - 1, 0, -1):
        b = "-".join(parts[:k])
        if b in cast:
            return b
    return None


def strip_p(t):
    return t.replace(" shown in {P}", "").replace("{P}", "the reference")


def prompt_for(aid):
    if aid in cast:
        it = cast[aid]; b = base_of(aid)
        desc = f"{it['name']}, {strip_p(it['base_en'])}. Wardrobe: {it.get('wear_en', '')}."
        if b and find(b, IMG):
            return ("局部修图（从母图 " + b + " 改，保住脸和皮肤纹理）", EDIT.format(goal=f"show {it['name']} in a new outfit/state", change=it.get("wear_en", "")) + "\n\n" + desc)
        return ("角色三栏表", f"{PRE}\n\n{CHAR}\n\nCharacter: {desc} All characters are adults unless stated otherwise.\n\n{NEG}")
    if aid in scenes:
        it = scenes[aid]
        return ("场景 3/4 高机位", f"{PRE}\n\n{SCENE}\n\nLocation: {strip_p(it['en'])}. {it.get('layout_en', '')}\n\n{NEG}")
    if aid in props:
        it = props[aid]
        return ("道具 2x2 产品照", f"{PRE}\n\n{PROP}\n\nProp: {strip_p(it['en'])}.\n\n{NEG}")
    return ("未知", "")


def main():
    E = eps(sys.argv[1:])
    use = {}
    for ep in E:
        for aid in used_ids(ep):
            use.setdefault(aid, [])
            if ep not in use[aid]:
                use[aid].append(ep)
    rows, missing = [], []
    for aid in sorted(use):
        it = cast.get(aid) or scenes.get(aid) or props.get(aid)
        kind = "角色" if aid in cast else "场景" if aid in scenes else "道具" if aid in props else "？"
        if it is None:
            rows.append(f"| {aid} | ？ | — | ❌ 不在 library 里 | {'、'.join(use[aid])} |"); continue
        f = find(aid, IMG)
        st = ("✅ " + os.path.relpath(f[-1], PIPE)) if f else ("⚠ noref（只按文字）" if it.get("noref") else "❌ 缺图")
        if not f:
            missing.append(aid)
        rows.append(f"| {aid} | {kind} | {it.get('name_cn', '')} | {st} | {'、'.join(use[aid])} |")
    vrows = []
    for aid in sorted(a for a in use if a in cast):
        it = cast[aid]
        if it.get("voice_id"):
            h3 = [x for x in find(it["voice_id"], (".wav", ".mp3", ".flac", ".m4a")) if "master" not in x.lower()]
            ms = [x for x in find(it["voice_id"], (".wav", ".flac")) if "master" in x.lower()]
            vrows.append(f"| {it['name']} | {it['voice_id']} | {'✅' if h3 else '❌ 缺 H3 参考音频'} | {'✅' if ms else '⚠ 缺母版（后期设备声克隆要用）'} |")
        else:
            pv = {x['character'] for x in voices.get("prompt_voices", [])}
            vrows.append(f"| {it['name']} | （提示词固定声） | {'✅ 已登记控制词' if it['name'] in pv else '⚠ voices.json prompt_voices 里没登记'} | — |")
    speakers = set()
    for ep in E:
        p = os.path.join(PIPE, "episodes", ep, "02_dialogue_lock.json")
        if os.path.isfile(p):
            speakers |= {x["speaker"] for x in json.load(open(p, encoding="utf-8"))["lines"]}
    known = {x["character"] for x in voices.get("voices", [])} | {x["character"] for x in voices.get("prompt_voices", [])}
    unk = sorted(speakers - known)

    md = [f"# 资产清单与缺口（{E[0] if E else ''}–{E[-1] if E else ''}，{len(use)} 个资产）", "",
          "由 `tools/asset_gaps.py` 生成，可反复重跑。图放进 `assets/` 任意子目录、文件名以 ID 开头（如 `C01.png`、`C01_v2.png`）即可被找到。", "",
          "## 参考图", "", "| ID | 类型 | 名称 | 状态 | 用到的集 |", "|---|---|---|---|---|"] + rows
    md += ["", "## 声线", "", "| 角色 | voice_id | H3 参考（32k 单声道） | 母版（48k） |", "|---|---|---|---|"] + vrows
    if unk:
        md += ["", f"⚠ 台词里有说话人不在 voices.json：{'、'.join(unk)}（主要角色登记 voices，次要角色登记 prompt_voices）"]
    if missing:
        md += ["", "## 缺图资产的生成提示词（复制到生图工具；生成后命名为 <ID>.png 放进 assets/images/）", "",
               "挑图标准：挑最可信的脸，不挑最漂亮的；眼睛要有细小眼神光；场景只有一个光源方向；可变物体是动作之前的状态。修图一次只改一处（CHANGE 写小、PRESERVE 写全）。", ""]
        for aid in missing:
            kind, text = prompt_for(aid)
            md += [f"### {aid}｜{(cast.get(aid) or scenes.get(aid) or props.get(aid) or {}).get('name_cn', '')}｜{kind}", "", "```", text, "```", ""]
    out = os.path.join(ASSET_ROOT, "00_资产清单与缺口.md")
    os.makedirs(ASSET_ROOT, exist_ok=True)
    open(out, "w", encoding="utf-8").write("\n".join(md) + "\n")
    print(f"{len(use)} 个资产，缺图 {len(missing)} 个，声线 {len(vrows)} 条" + (f"，未登记说话人 {len(unk)} 个" if unk else "") + f" → {os.path.relpath(out, PIPE)}")
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
