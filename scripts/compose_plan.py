#!/usr/bin/env python3
"""简写源 → 完整 plan.json v2.0（支持双语角色名 name_en、creature 非人类资产、STAGING_MAP 与子空间标记）。

用法：python3 tools/compose_plan.py E01            # 读 episodes/E01/plan_src.json + library/*.json，写 episodes/E01/plan.json
之后照常：python3 tools/build_episode.py episodes/E01 --voices voices.json
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__)); PIPE = os.path.dirname(HERE)
LIB = os.path.join(PIPE, "library")


def load(name):
    return json.load(open(os.path.join(LIB, name), encoding="utf-8"))


cast, scenes, props, styles = load("cast.json"), load("scenes.json"), load("props.json"), load("styles.json")
ACT = {k: v for k, v in load("acting.json").items() if not k.startswith("_")}
voices = json.load(open(os.path.join(PIPE, "voices.json"), encoding="utf-8"))
_pj = os.path.join(PIPE, "project.json")
PROJ = json.load(open(_pj, encoding="utf-8")) if os.path.isfile(_pj) else {}
ASPECT = PROJ.get("aspect", "9:16")
GENRE_CN = PROJ.get("genre_cn", "写实电影感短剧，英文对白")
PROMPT_V = {v["character"]: v for v in voices.get("prompt_voices", [])}

ep = sys.argv[1]
epdir = os.path.join(PIPE, "episodes", ep)
for sw in PROJ.get("style_swaps", []):
    if int(ep[1:]) >= int(sw["from_ep"]):
        for v in styles.values():
            for lang in ("en", "cn"):
                if isinstance(v, dict) and isinstance(v.get(lang), str):
                    v[lang] = v[lang].replace(sw["from"], sw["to"])
src = json.load(open(os.path.join(epdir, "plan_src.json"), encoding="utf-8"))
lock = {x["id"]: x for x in json.load(open(os.path.join(epdir, "02_dialogue_lock.json"), encoding="utf-8"))["lines"]}


def lib_item(aid):
    for kind, table in (("character", cast), ("scene", scenes), ("prop", props)):
        if aid in table:
            return ("creature" if table[aid].get("kind") == "creature" else kind), table[aid]
    raise SystemExit(f"{ep}：资产 {aid} 不在 library/ 里")


def names_list(xs):
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


CN_NUM = "零一二三四五六七八九十"
plan = {"episode": src["episode"], "title": src["title"], "version": src.get("version", "v1"),
        "segment_sec": 15.0, "segments_per_episode": src.get("segments_per_episode", len(src.get("segments", [])) or 8),
        "aspect": ASPECT,
        "styles": {k: v["en"] for k, v in styles.items()},
        "storyboard_header": src.get("header", []), "review_notes": src.get("notes", []),
        "dialogue_headroom_min": src.get("dialogue_headroom_min", 0.3),
        "state_locks": src.get("state_locks", []),
        **({"staging_map": src["staging_map"]} if src.get("staging_map") else {}),
        **({"allow_shared_scene_ref": src["allow_shared_scene_ref"]} if src.get("allow_shared_scene_ref") else {}),
        **({"legacy_spatial_exempt": src["legacy_spatial_exempt"]} if src.get("legacy_spatial_exempt") else {}),
        "segments": []}

prev = None
for s in src["segments"]:
    n = s["id"]; relay = prev is not None and prev.get("next") == "TAIL_RELAY"
    refs, subj_lines, sub_of, pic_of = [], [], {}, {}
    pic = 0
    if relay:
        pic += 1; refs.append([f"Picture {pic}", f"上一段尾帧（Seg{prev['id']}）", None])
    _kp = [a for a in s.get("props", []) if a.startswith("K-") and not any(a in t for t in (cast, scenes, props))]
    if _kp: print(f"  ⚠ {ep} Seg{n} 垫图 {_kp} 还没有，先不带（出图后重新 compose + build）")
    order = list(s.get("cast", [])) + ([s["scene_ref"]] if s.get("scene_ref") else []) + [a for a in s.get("props", []) if a not in _kp]
    for k, aid in enumerate(order, 1):
        kind, it = lib_item(aid)
        sub_of[aid] = k
        en_name = it.get("name_en") or it.get("name", "")
        if it.get("noref"):
            if kind == "character":
                wear = s.get("wear", {}).get(aid) or [it["wear_en"], it["wear_cn"]]
                subj_lines.append(f"<Subject {k}> is {en_name}, {it['base_en'].replace(' shown in {P}', '').replace('{P}', 'the description')}; {wear[0]}.")
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
            line = f"<Subject {k}> is {en_name}, {it['base_en'].replace('{P}', P)}; {wear[0]}" + (f"; {extra[0]}" if extra else "") + "."
        elif kind == "creature":
            extra = s.get("extra", {}).get(aid)
            line = f"<Subject {k}> is {en_name}, {it['base_en'].replace('{P}', P)}" + (f"; {extra[0]}" if extra else "") + "."
        elif kind == "scene":
            line = f"<Subject {k}> is {it['en'].replace('{P}', P)}. {it['layout_en']} {P} supplies only the geography, furniture, materials and light of this place; frame every shot from fresh camera positions instead of copying the reference composition."
        else:
            state = s.get("prop_state", {}).get(aid)
            line = f"<Subject {k}> is {it['en'].replace('{P}', P)}" + (f"; {state[0]}" if state else "") + "."
        subj_lines.append(line)

    speakers, audios = [], []
    alltxt = " ".join(sh["en"] for sh in s["shots"])
    for m in re.finditer(r"\{SAY:([\w-]+)!?\}", alltxt):
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
            if it["name"] in PROMPT_V:
                cp = PROMPT_V[it['name']]['control_prompt']
                if m.group(2): cp = re.sub(r"^[^:]*:\s*", "", cp)
                return f"<Subject {sub_of[aid]}> {S}, with the fixed voice \"{cp}\","
            return f"<Subject {sub_of[aid]}> {S}, in {it['voice_en']},"
        t = re.sub(r"\{SAY:([\w-]+)(!?)\}", say, t)
        t = re.sub(r"\{VO:([^}]+)\}", lambda m: f"the fixed voice \"{PROMPT_V[m.group(1)]['control_prompt']}\"" if m.group(1) in PROMPT_V else m.group(1), t)
        def subj(m):
            k = m.group(1)
            if k not in sub_of: raise SystemExit(f"{ep} Seg{n}：记号 {{{k}}} 不是本段的 cast/scene_ref/props")
            return f"<Subject {sub_of[k]}>"
        t = re.sub(r"\{([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)\}", subj, t)
        if re.search(r"\{[A-Z][A-Z0-9-]*\}", t): raise SystemExit(f"{ep} Seg{n}：提示词里还有未替换的记号：{t[:120]}")
        t = re.sub(r"(<Subject \d+> \(S\d+\),[^:]*?),? (?:he|she|they) (says|asks|answers|replies|adds)", r"\1, \2", t)
        t = re.sub(r",? and, (<Subject \d+> \(S\d+\))", r". \1", t)
        return t

    shots = []
    for sh in s["shots"]:
        shots.append({"dur": sh["dur"], "storyboard_cn": sh["sb"], "en": expand(sh["en"]), "wenwu": sh["cn"], "dialogue": sh.get("d")})

    ret = []
    if relay:
        ret.append(f"<Picture 1> ([Shot 1] first frame): fully_preserved - {s.get('ff_keep', 'composition, positions, light and the established state')}.")
    def appears(aid, it, kind):
        if kind == "scene": return list(range(1, len(shots) + 1))
        en_nm = it.get("name_en") or it.get("name", "")
        keys = [f"<Subject {sub_of[aid]}>"] + ([en_nm.split()[-1]] if (kind == "character" and en_nm) else it.get("match", []))
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
        en_nm = it.get("name_en") or it["name"]
        ret.append(f"<Audio {aud_of[aid]}>: reference - its timbre guides {en_nm}'s voice without copying the original signal.")

    people_en = [lib_item(a)[1].get("name_en") or lib_item(a)[1]["name"] for a in s.get("cast", []) if lib_item(a)[0] != "creature"]
    people_cn = [lib_item(a)[1]["name"] for a in s.get("cast", []) if lib_item(a)[0] != "creature"]
    count = s.get("count") or (f"{people_en[0]} is the only person in this video." if len(people_en) == 1 else
                               f"Exactly {['zero','one','two','three','four','five','six','seven','eight'][len(people_en)]} people appear in this video: {names_list(people_en)}.")
    mood = s.get("mood") or src.get("mood")
    if speakers: count = f"{count} Speak only the quoted dialogue lines with accurate lip sync; every other sentence in this prompt is silent direction."
    tag = "[" + " + ".join((["keyframe completion"] if relay else []) + ["reference generation"] + (["audio reference"] if audios else [])) + "]"

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
        elif it.get("kind") == "creature":
            life.append(f"{it['name']} 以 <Picture {pic_of[aid]}> 为准，{it['base_cn'].replace('{P}', '参考图')}" + (f"，{extra[1]}" if extra else ""))
        else:
            life.append(f"{it['name']} 以 <Picture {pic_of[aid]}> 为准，{it['base_cn'].replace('{P}', '参考图')}，{wear[1]}" + (f"，{extra[1]}" if extra else ""))
    if life: parts.append("生命核：" + "；".join(life) + "。")
    if s.get("scene_ref"):
        sc = scenes[s["scene_ref"]]
        lcn = sc.get("layout_cn") or sc.get("cn", "")
        if sc.get("noref"):
            parts.append(f"场景（暂无参考图，按文字）：{sc['cn']}。布局：{lcn}")
        else:
            parts.append(f"场景以 <Picture {pic_of[s['scene_ref']]}> 为准：{sc['cn']}。布局：{lcn}")
    if s.get("props"):
        parts.append("道具：" + "；".join((f"{lib_item(a)[1]['cn']}（暂无参考图）" if lib_item(a)[1].get("noref") else f"<Picture {pic_of[a]}> {lib_item(a)[1]['cn']}") + (f"（{s['prop_state'][a][1]}）" if a in s.get("prop_state", {}) else "") for a in s["props"] if a not in _kp) + "。")
    parts.append("光：" + styles[s["light"]]["cn"])
    if mood: parts.append("氛围：" + mood[1])
    vs = []
    for aid in speakers:
        it = lib_item(aid)[1]
        vcn = it.get("voice_cn") or "自然人声"
        vs.append(f"{it['name']} 用 <Audio {aud_of[aid]}> 的音色，{vcn}" if aid in aud_of else f"{it['name']} 用固定提示词声线，{vcn}")
    if vs: parts.append("声线：" + "；".join(vs) + "。")
    if people_cn:
        parts.append(f"画面里只有这{CN_NUM[len(people_cn)] if len(people_cn) <= 10 else len(people_cn)}个人" + ("，每人只说引号里的台词。" if speakers else "。") if len(people_cn) > 1 else f"画面里只有 {people_cn[0]} 一个人。")
    parts.append("最终发展线：" + cn.get("dev", ""))
    wenwu = {"open": "".join(parts), "perf": cn.get("perf", ""), "sound": cn.get("sound", "") + "本段只有环境声与动作声，配乐留给后期。",
             "visual": cn.get("visual", "")}

    plan["segments"].append({
        "id": n, "scene": s["scene"], "scene_ref": s.get("scene_ref"), "light": s["light"], "connection_to_next": s["next"], "chain": s["chain"],
        "en": {"tag": tag, "first_frame": s.get("ff_en") if relay else None, "count": count,
               "subjects": subj_lines + ([f"Blocking, fixed in every shot: {expand(s['blocking'][0])}"] if s.get("blocking") else [])
                           + ([f"First frame{'' if (s.get('transition') or {}).get('type') in ('establish', 'time_cut') else ', continuous with the previous moment'} (positions and postures only; the framing of every shot follows its own shot description): {expand(s['start'][0])}"] if s.get("start") else []), "audios": audios,
               "summary": expand(s["summary"]), "retention": ret, "soundscape": s["sound"]},
        "refs": refs, "wenwu": wenwu, "shots": shots,
        **({"subspace": s["subspace"]} if s.get("subspace") else {}),
        **({"same_room_ok": s["same_room_ok"]} if s.get("same_room_ok") else {}),
        **({"transition": s["transition"]} if s.get("transition") else {}),
        **({"relay_reason": s["relay_reason"]} if s.get("relay_reason") else {}),
        **({"seam_motive": s["seam_motive"]} if s.get("seam_motive") else {})})
    if relay and not s.get("ff_en"):
        raise SystemExit(f"{ep} Seg{n} 是接力段，缺 ff_en / ff_cn（首帧描述）")
    prev = s

json.dump(plan, open(os.path.join(epdir, "plan.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{ep}: plan.json 已生成（{len(plan['segments'])} 段）")
