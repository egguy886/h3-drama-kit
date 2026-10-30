#!/usr/bin/env python3
"""简写源 → 完整 plan.json。

用法：python3 tools/compose_plan.py E01            # 读 episodes/E01/plan_src.json + library/*.json，写 episodes/E01/plan.json
之后照常：python3 tools/build_episode.py episodes/E01 --voices voices.json
（plan_src.json 一般由 plans/eNN.py 用 plans/pw.py 的 seg()/sh() 写出来，见工具包 playbook/04_分镜与提示词.md）

为什么要有它：同一个角色/场景/道具在全剧用同一段经参考图核对过的描述（library/），
每集只写镜头本身；参考顺序、Subject/Picture/Audio 编号、说话人 (S1)(S2)、保留分析、中文总述全部自动生成，避免手工错号。

源文件里镜头文字可用的记号（英文 en 字段）：
  {C01}        → 该资产在本段的 <Subject N>
  {SAY:C01}    → "<Subject N> (S1), in <固定声线>, with the timbre of <Audio M>,"（有声音资产的角色）
                 或 "<Subject N> (S1), <提示词固定声控制词>,"（次要角色，控制词取自 voices.json prompt_voices）
  {VO:Name}    → 画外声（如 Board Relay），只写控制词，不绑定画面主体
  {{d:L3}}     → 台词原文（build_episode.py 展开）
中文 cn 字段用 {{q:L3}} 放台词；中文里不要用 <Subject> 标签，直接写名字。

plan_src.json 字段：
  顶层：episode, title, version, header[], notes[], state_locks[], dialogue_headroom_min（可选）, wear{ID:[en,cn]}（全集服装，可选）
  每段：id, scene, scene_ref, light（styles.json 的键）, chain, next（TAIL_RELAY / HARD_CUT / （集尾））,
        cast[], props[], wear{ID:[en,cn]}, extra{ID:[en,cn]}, prop_state{ID:[en,cn]}, keep{ID:文字}, count（人数句）,
        ff_en / ff_cn（接力段首帧描述，接力段必填）, mood（[en,cn] 本段氛围，可放顶层作全集默认，见 protocols/TONE.md）, summary, sound, cn{kind, dev, perf, sound, visual},
        shots[{dur, sb, en, cn, d（本镜台词 ID，可选）}]
  {ACT:Cade:jaw}：取 library/acting.json 里 Cade 的 jaw 习惯（英文短句）；每镜最多取一个。
  blocking [en, cn]（可选）：站位卡，写进每段 subject_definitions 末尾 "Blocking, fixed in every shot: …"，长对话/多人同场戏用，固定谁坐哪、谁在画面哪侧（E32 起）。
  library 条目标 "noref": true 表示还没有参考图（只按文字），补图后在 local_paths.json 指向图片并去掉 noref。
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__)); PIPE = os.path.dirname(HERE)
LIB = os.path.join(PIPE, "library")


def load(name):
    return json.load(open(os.path.join(LIB, name), encoding="utf-8"))


cast, scenes, props, styles = load("cast.json"), load("scenes.json"), load("props.json"), load("styles.json")
ACT = {k: v for k, v in load("acting.json").items() if not k.startswith("_")}   # 表演档案：{ACT:名字:键} → 一个习惯的英文短句
voices = json.load(open(os.path.join(PIPE, "voices.json"), encoding="utf-8"))
_pj = os.path.join(PIPE, "project.json")
PROJ = json.load(open(_pj, encoding="utf-8")) if os.path.isfile(_pj) else {}
ASPECT = PROJ.get("aspect", "9:16")
GENRE_CN = PROJ.get("genre_cn", "写实电影感短剧，英文对白")
PROMPT_V = {v["character"]: v for v in voices.get("prompt_voices", [])}

ep = sys.argv[1]
epdir = os.path.join(PIPE, "episodes", ep)
src = json.load(open(os.path.join(epdir, "plan_src.json"), encoding="utf-8"))
lock = {x["id"]: x for x in json.load(open(os.path.join(epdir, "02_dialogue_lock.json"), encoding="utf-8"))["lines"]}

def lib_item(aid):
    for kind, table in (("character", cast), ("scene", scenes), ("prop", props)):
        if aid in table:
            return kind, table[aid]
    raise SystemExit(f"{ep}：资产 {aid} 不在 library/ 里")

def names_list(xs):
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]

CN_NUM = "零一二三四五六七八九十"
plan = {"episode": src["episode"], "title": src["title"], "version": src.get("version", "v1"),
        "segment_sec": 15.0, "segments_per_episode": src.get("segments_per_episode", 8),   # 台词过密的集可在 plan_src 里放宽（E33 起，需用户确认）
        "aspect": ASPECT,
        "styles": {k: v["en"] for k, v in styles.items()},
        "storyboard_header": src.get("header", []), "review_notes": src.get("notes", []),
        "dialogue_headroom_min": src.get("dialogue_headroom_min", 0.3),
        "state_locks": src.get("state_locks", []), "segments": []}

prev = None
for s in src["segments"]:
    n = s["id"]; relay = prev is not None and prev.get("next") == "TAIL_RELAY"
    refs, subj_lines, sub_of, pic_of = [], [], {}, {}
    pic = 0
    if relay:
        pic += 1; refs.append([f"Picture {pic}", f"上一段尾帧（Seg{prev['id']}）", None])
    order = list(s.get("cast", [])) + ([s["scene_ref"]] if s.get("scene_ref") else []) + list(s.get("props", []))
    for k, aid in enumerate(order, 1):
        kind, it = lib_item(aid)
        sub_of[aid] = k
        if it.get("noref"):                                  # 无参考图：只用文字定义（出片前补资产，或出片后截图补参考）
            if kind == "character":
                wear = s.get("wear", {}).get(aid) or [it["wear_en"], it["wear_cn"]]
                subj_lines.append(f"<Subject {k}> is {it['name']}, {it['base_en'].replace(' shown in {P}', '').replace('{P}', 'the description')}; {wear[0]}.")
            elif kind == "scene":
                subj_lines.append(f"<Subject {k}> is {it['en'].replace(' shown in {P}', '').replace('{P}', 'the scene')}. {it['layout_en']}")
            else:
                subj_lines.append(f"<Subject {k}> is {it['en'].replace(' shown in {P}', '').replace('{P}', 'the prop')}.")
            continue
        pic += 1; pic_of[aid] = pic
        refs.append([f"Picture {pic}", it["name_cn"], aid])
        P = f"<Picture {pic}>"
        if kind == "character":
            wear = s.get("wear", {}).get(aid) or src.get("wear", {}).get(aid) or [it["wear_en"], it["wear_cn"]]
            extra = s.get("extra", {}).get(aid)
            line = f"<Subject {k}> is {it['name']}, {it['base_en'].replace('{P}', P)}; {wear[0]}" + (f"; {extra[0]}" if extra else "") + "."
        elif kind == "scene":
            # 学自 Higgsfield 双人同场指南：场景图只定空间，机位要新找，否则会照搬参考图构图（E21 电梯厅人物进出方向反了）
            line = f"<Subject {k}> is {it['en'].replace('{P}', P)}. {it['layout_en']} {P} supplies only the geography, furniture, materials and light of this place; frame every shot from fresh camera positions instead of copying the reference composition."
        else:
            state = s.get("prop_state", {}).get(aid)
            line = f"<Subject {k}> is {it['en'].replace('{P}', P)}" + (f"; {state[0]}" if state else "") + "."
        subj_lines.append(line)

    # 说话人编号与音频
    speakers, audios = [], []
    alltxt = " ".join(sh["en"] for sh in s["shots"])
    for m in re.finditer(r"\{SAY:([\w-]+)\}", alltxt):
        if m.group(1) not in speakers: speakers.append(m.group(1))
    aud_of = {}
    for aid in speakers:
        it = lib_item(aid)[1]
        if it.get("voice_id"):
            a = len(audios) + 1; aud_of[aid] = a
            audios.append(f"<Audio {a}> is the voice-timbre reference for <Subject {sub_of[aid]}> (S{speakers.index(aid) + 1}).")
            refs.append([f"Audio {a}", f"{it['name']} 声线参考", it["voice_id"]])

    def expand(t):
        def act(m):
            who, key = m.group(1), m.group(2)
            ent = ACT.get(who)
            if not ent or key not in ent["tics"]:
                raise SystemExit(f"{ep} Seg{n}：{{ACT:{who}:{key}}} 不在 library/acting.json")
            return ent["tics"][key]["en"]
        t = re.sub(r"\{ACT:(\w+):(\w+)\}", act, t)
        def say(m):
            aid = m.group(1); it = lib_item(aid)[1]; S = f"(S{speakers.index(aid) + 1})"
            if aid in aud_of:
                return f"<Subject {sub_of[aid]}> {S}, in {it['voice_en']}, with the timbre of <Audio {aud_of[aid]}>,"
            if it["name"] in PROMPT_V:                       # 次要角色：控制词逐字原样（decisions.md）
                return f"<Subject {sub_of[aid]}> {S}, with the fixed voice \"{PROMPT_V[it['name']]['control_prompt']}\","
            return f"<Subject {sub_of[aid]}> {S}, in {it['voice_en']},"
        t = re.sub(r"\{SAY:([\w-]+)\}", say, t)
        t = re.sub(r"\{VO:([^}]+)\}", lambda m: f"the fixed voice \"{PROMPT_V[m.group(1)]['control_prompt']}\"" if m.group(1) in PROMPT_V else m.group(1), t)
        # 资产记号 → <Subject N>。2026-10-13 修：原正则只认 C01/S13/P15 式编号，N-xxx / X-xxx / C12F-xxx 会原样留在提示词里（E06、E10–E18 共 85 处）
        def subj(m):
            k = m.group(1)
            if k not in sub_of: raise SystemExit(f"{ep} Seg{n}：记号 {{{k}}} 不是本段的 cast/scene_ref/props")
            return f"<Subject {sub_of[k]}>"
        t = re.sub(r"\{([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)\}", subj, t)
        if re.search(r"\{[A-Z][A-Z0-9-]*\}", t): raise SystemExit(f"{ep} Seg{n}：提示词里还有未替换的记号：{t[:120]}")
        # 说话句清理：<Subject N> (Sx), ..., he/she says: → ..., says:；", and, <Subject" → ". <Subject"
        t = re.sub(r"(<Subject \d+> \(S\d+\),[^:]*?),? (?:he|she|they) (says|asks|answers|replies|adds)", r"\1, \2", t)
        t = re.sub(r",? and, (<Subject \d+> \(S\d+\))", r". \1", t)
        return t

    shots = []
    for sh in s["shots"]:
        shots.append({"dur": sh["dur"], "storyboard_cn": sh["sb"], "en": expand(sh["en"]), "wenwu": sh["cn"], "dialogue": sh.get("d")})

    # 保留分析
    ret = []
    if relay:
        ret.append(f"<Picture 1> ([Shot 1] first frame): fully_preserved - {s.get('ff_keep', 'composition, positions, light and the established state')}.")
    def appears(aid, it, kind):
        if kind == "scene": return list(range(1, len(shots) + 1))
        keys = [f"<Subject {sub_of[aid]}>"] + ([it["name"].split()[-1]] if kind == "character" else it.get("match", []))
        return [k for k, sh in enumerate(shots, 1) if any(x in sh["en"] for x in keys)]
    def span(ks):
        if not ks: return "[Shot 1]"
        if len(ks) > 2 and ks == list(range(ks[0], ks[-1] + 1)): return f"[Shot {ks[0]}] to [Shot {ks[-1]}]"
        return ", ".join(f"[Shot {k}]" for k in ks)
    for aid in order:
        kind, it = lib_item(aid)
        keep = s.get("keep", {}).get(aid) or it.get("keep") or ("fully_preserved - layout, light and materials" if kind == "scene" else "fully_preserved - shape, material and state")
        ret.append(f"<Subject {sub_of[aid]}> (appears in {span(appears(aid, it, kind))}): {keep}.")
    for aid in aud_of:
        it = lib_item(aid)[1]
        ret.append(f"<Audio {aud_of[aid]}>: reference - its timbre guides {it['name']}'s voice without copying the original signal.")

    people = [lib_item(a)[1]["name"] for a in s.get("cast", [])]
    count = s.get("count") or (f"{people[0]} is the only person in this video." if len(people) == 1 else
                               f"Exactly {['zero','one','two','three','four','five','six'][len(people)]} people appear in this video: {names_list(people)}.")
    mood = s.get("mood") or src.get("mood")          # [en, cn]：本段氛围（protocols/TONE.md）
    # 氛围句（剧情概括整句）会被模型当台词念出来：E21/E24/E34 实测 4 段"多说了词"全是它，标成"无声注记"后 E34 Seg2 仍被念（10-30 小试）
    # → 英文提示词里不再放氛围句，只留中文给人看（下面 wenwu 的"氛围："）
    # 只念引号里的台词（Higgsfield："Speak only the quoted lines"）：其余句子都是无声说明，堵住氛围句/总述被念出来
    if speakers: count = f"{count} Speak only the quoted dialogue lines with accurate lip sync; every other sentence in this prompt is silent direction."
    tag = "[" + " + ".join((["keyframe completion"] if relay else []) + ["reference generation"] + (["audio reference"] if audios else [])) + "]"

    # 中文总述
    cn = s.get("cn", {})
    parts = [f"15秒，{ASPECT}，{GENRE_CN}。" + cn.get("kind", "")]
    if relay:
        parts.append(f"<Picture 1> 是本段 0.0 秒的首帧（上一段最后一帧）：{s['ff_cn']}")
    if s.get("blocking"):
        parts.append(f"站位（每个镜头固定，不互换）：{s['blocking'][1]}")
    if s.get("start"):
        parts.append(f"首帧站位（接上一段）：{s['start'][1]}")
    life = []
    for aid in s.get("cast", []):
        it = cast[aid]; wear = s.get("wear", {}).get(aid) or src.get("wear", {}).get(aid) or [it["wear_en"], it["wear_cn"]]
        extra = s.get("extra", {}).get(aid)
        if it.get("noref"):
            life.append(f"{it['name']}（无参考图，按文字）：{it['base_cn']}，{wear[1]}")
        else:
            life.append(f"{it['name']} 以 <Picture {pic_of[aid]}> 为准，{it['base_cn'].replace('{P}', '参考图')}，{wear[1]}" + (f"，{extra[1]}" if extra else ""))
    if life: parts.append("生命核：" + "；".join(life) + "。")
    if s.get("scene_ref"):
        sc = scenes[s["scene_ref"]]
        if sc.get("noref"):
            parts.append(f"场景（暂无参考图，按文字）：{sc['cn']}。布局：{sc['layout_cn']}")
        else:
            parts.append(f"场景以 <Picture {pic_of[s['scene_ref']]}> 为准：{sc['cn']}。布局：{sc['layout_cn']}")
    if s.get("props"):
        parts.append("道具：" + "；".join((f"{props[a]['cn']}（暂无参考图）" if props[a].get("noref") else f"<Picture {pic_of[a]}> {props[a]['cn']}") + (f"（{s['prop_state'][a][1]}）" if a in s.get("prop_state", {}) else "") for a in s["props"]) + "。")
    parts.append("光：" + styles[s["light"]]["cn"])
    if mood: parts.append("氛围：" + mood[1])
    vs = []
    for aid in speakers:
        it = lib_item(aid)[1]
        vs.append(f"{it['name']} 用 <Audio {aud_of[aid]}> 的音色，{it['voice_cn']}" if aid in aud_of else f"{it['name']} 用固定提示词声线，{it['voice_cn']}")
    if vs: parts.append("声线：" + "；".join(vs) + "。")
    if people:
        parts.append(f"画面里只有这{CN_NUM[len(people)] if len(people) <= 10 else len(people)}个人" + ("，每人只说引号里的台词。" if speakers else "。") if len(people) > 1 else f"画面里只有 {people[0]} 一个人。")
    parts.append("最终发展线：" + cn.get("dev", ""))
    wenwu = {"open": "".join(parts), "perf": cn.get("perf", ""), "sound": cn.get("sound", "") + "本段只有环境声与动作声，配乐留给后期。",
             "visual": cn.get("visual", "")}

    plan["segments"].append({
        "id": n, "scene": s["scene"], "scene_ref": s.get("scene_ref"), "light": s["light"], "connection_to_next": s["next"], "chain": s["chain"],
        "en": {"tag": tag, "first_frame": s.get("ff_en") if relay else None, "count": count,
               "subjects": subj_lines + ([f"Blocking, fixed in every shot: {expand(s['blocking'][0])}"] if s.get("blocking") else [])
                           # 首帧站位（Higgsfield 的 LOCATION AND FIRST FRAME）：每段单独生成、看不到上一段，必须写明 0 秒时谁在哪、什么姿势、手里拿什么、机位在哪（E34 Seg2 床上→站着）
                           + ([f"First frame{'' if (s.get('transition') or {}).get('type') in ('establish', 'time_cut') else ', continuous with the previous moment'} (positions and postures only; the framing of every shot follows its own shot description): {expand(s['start'][0])}"] if s.get("start") else []), "audios": audios,
               "summary": expand(s["summary"]), "retention": ret, "soundscape": s["sound"]},
        "refs": refs, "wenwu": wenwu, "shots": shots, **({"transition": s["transition"]} if s.get("transition") else {}), **({"relay_reason": s["relay_reason"]} if s.get("relay_reason") else {}), **({"seam_motive": s["seam_motive"]} if s.get("seam_motive") else {})})
    if relay and not s.get("ff_en"):
        raise SystemExit(f"{ep} Seg{n} 是接力段，缺 ff_en / ff_cn（首帧描述）")
    prev = s

json.dump(plan, open(os.path.join(epdir, "plan.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{ep}: plan.json 已生成（{len(plan['segments'])} 段）")
