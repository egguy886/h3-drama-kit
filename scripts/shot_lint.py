#!/usr/bin/env python3
"""摄影检查（摄影指导的自动部分，只读、免费）：按 protocols/CINEMATOGRAPHY.md 检查 plan.json 的镜头语言。

用法：python3 tools/shot_lint.py E31            # 一集
      python3 tools/shot_lint.py E21-E30 --brief # 多集，只出统计
      python3 tools/shot_lint.py E31 --only group
❌（退出码 1，build_episode 会失败）：
  - 本剧禁用的运镜/转场（推拉变焦、子弹时间、H3 内甩镜/叠化、Shake Strongly…，见 library/techniques.json banned）
  - 带台词的镜头写了慢动作
⚠：
  - 多人动作没写先后/站位（E21 Seg6 Nia 站位接不上的教训）
  - 整段没有一个视觉冲击镜头（运镜 / 仰俯过肩 / 极特写 / 前景框 / 剪影 / 转焦…）
  - 连续 4 个以上"平镜头"（固定机位切近景/中景）
  - 运镜镜头太短，看不出动作；一个镜头写了两种运镜
  - 台词镜头画面里有别人正脸却没写听者闭嘴；一段推镜超过 2 次（模板化）
  - 相邻两镜景别、人物、角度都没变（无效切镜）；推断词（seems / as if / realizes…画不出来）
  - E31 起：换场缝（HARD_CUT）没写 transition；Seg1 没有开场钩子；反应镜点名情绪不足一半
"""
import json, os, re, sys

PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _cast_names():
    """角色名从 library/cast.json 的 name 字段读（工具包通用化：不再写死某部剧的人名）。"""
    names = set()
    for f in ("cast.json", "acting.json"):
        p = os.path.join(PIPE, "library", f)
        if os.path.isfile(p):
            for k, v in json.load(open(p, encoding="utf-8")).items():
                if k.startswith("_"):
                    continue
                if f == "acting.json":
                    names.add(k)
                elif isinstance(v, dict) and v.get("name"):
                    names.add(v["name"])
                    names.update(v.get("aliases", []))
    names = sorted((n for n in names if n), key=len, reverse=True) or ["Somebody"]
    return "|".join(re.escape(n) for n in names)


NAMES = _cast_names()

GROUP = re.compile(r"one after another|in turn|all three|the three|both (?:of )?(?:them|men|boys)|(?:walk|run|move|step|stand|duck|sprint)s? together|side by side|rush(?:es)? in|slip(?:s)? through|duck(?:s)? through|step(?:s)? through|file(?:s)? out|the two (?:of )?(?:them|stand|walk|run|turn|duck)|(?:the|all) (?:students|guards|officers)", re.I)
ORDER = re.compile(r"\b(first|then|second|last|behind|ahead|leads?|leading|follows?|following|trailing|(?:at|from) frame-left|(?:at|from) frame-right|nearest|farthest)\b", re.I)

MOVES = {  # 运镜类型 → 正则（H3 官方运镜词的自然写法）
    "推": r"\bpush(?:es)? in\b|\bpushes slowly\b",
    "拉": r"\bpulls? (?:out|back)\b",
    "摇": r"\bpans? (?:left|right)\b|\btilts? (?:up|down)\b",
    "移": r"\btrucks? (?:left|right)\b|\bpedestals? (?:up|down)\b|\b(?:rising|rises) slowly\b|\bslowly (?:rising|rises)\b",
    "环绕": r"\barcs? (?:with|around|slowly)\b|\barc shot\b",
    "跟": r"\btracks? (?:alongside|behind|with|beside)\b|\btracking (?:shot|medium|close-up|wide)\b|\bfollow(?:s|ing)? (?:him|her|them|closely|" + NAMES + r")\b",
    "晃": r"\bshakes? slightly\b|\bhandheld\b",
    "主观": r"\bPOV\b|point of view",
    "转焦": r"\bfocus shifts\b|\brack(?:s)? focus\b|\bfocus pulls\b",
}
MIN_DUR = {"推": 2.2, "拉": 2.4, "摇": 2.0, "移": 2.2, "环绕": 3.0, "转焦": 2.2, "跟": 1.6, "晃": 1.2, "主观": 1.4}
LOOK = {  # 角度 / 构图 / 光 / 景别里的冲击手段
    "仰拍": r"low-angle|low angle|from near the ground",
    "俯拍": r"high-angle|high angle|high wide shot|top-down|overhead shot",
    "过肩": r"over-the-shoulder|over (?:his|her|the) shoulder",
    "极特写": r"extreme close-up",
    "前景框": r"framed through|soft in the foreground|fills the lower third",
    "剪影": r"silhouett|backlit",
    "半脸光": r"half of (?:his|her|\w+'s) face in (?:deep )?shadow",
    "负空间": r"small at frame-(?:left|right|\{SIDE\})|\bsmall (?:in|at) the (?:lower|upper|edge)",
    "慢动作": r"slow motion|slow-motion",
}
BANNED = re.compile(r"dolly zoom|vertigo effect|bullet time|360-degree|\borbits?\b|\bFPV\b|drone shot|whip[- ]pans?|crash zoom|zooms? in (?:with \w+ amplitude )?at fast speed|cross-dissolve|the shot dissolves|dissolves? into the next|fades? (?:to|from) black|the shot fades|wipe transition|shakes? strongly|double exposure|glitch", re.I)
EMO = re.compile(r"\b(shock|stun|startl|furi|fury|anger|angr|afraid|fear|terrif|smug|grief|horror|disbelie|dread|rage|relie|triumph|panic|guilt|hurt|resolv|resolute|defian|despair|contempt|suspici|alarm|confus|hope|humiliat|betray|devastat|moved|vulnerab|wary|at ease|tender|asham|shame|desperat|sorrow|joy|elat|stricken|haunt|broken|exhaust|determin|wonder|awe|fierce|exult|uneas|unflinch|calm)", re.I)   # 情绪词词干
LIPS = re.compile(r"lips (?:at rest|stay closed|remain(?:s)? (?:completely )?closed|pressed shut)|back (?:turned )?to (?:the )?camera|from behind|silhouett", re.I)
WIDE_TALK = re.compile(r"two-shot|medium shot|medium-wide|wide shot|over-the-shoulder|full-body", re.I)
REACT = re.compile(r"close-up of (?:" + NAMES + r")(?!'s (?:right |left )?(?:fist|hands?|boots?|foot|feet|fingers?|fingertips?|shoes?|spikes?|knuckles?|wrists?|thumb|palm|ankle|heel))|close-up of \w+'s (?:face|eyes)", re.I)   # 手/脚/鞋等插入镜不算反应镜
SIZE = [("极特写", r"extreme close-up"), ("近景", r"medium close-up|close-up|close shot"), ("中景", r"medium shot|waist up|medium-wide"),
        ("全身", r"full-body|full body"), ("全景", r"wide shot|wide static shot|long shot|establishing")]
WHO = re.compile(r"\b(" + NAMES + r")\b(?:'s (?:\w+ )?(hands?|fist|fingers?|boots?|foot|feet|wrists?|palm|shoes?|spikes?|ankle|heel|knuckles?))?")
PART = lambda m: (m.group(1) + ("·" + m.group(2) if m.group(2) else "")) if m else None   # 手、脚等插入镜算不同主体
INFER = re.compile(r"\b(seems? to|as if|as though|realizes?|suddenly understands|senses?|appears to)\b", re.I)   # 推断词：画不出来（drama-skills 可生成性）
CAMLINE = re.compile(r"\bthe camera (?:holds|pushes|pulls|pans|tilts|trucks|tracks|arcs|pedestals|rises|follows|shakes|stays)|static shot|locked|\bPOV\b|focus shifts", re.I)
RELAY = re.compile(r"^The shot begins from <Picture 1>")
ESTAB = re.compile(r"^A wide static shot fixes")


def eps(spec):
    out = []
    for p in spec:
        m = re.fullmatch(r"E(\d+)-E?(\d+)", p.upper())
        out += [f"E{i:02d}" for i in range(int(m.group(1)), int(m.group(2)) + 1)] if m else [p.upper()]
    return out


def tags(en):
    mv = [k for k, p in MOVES.items() if re.search(p, en, re.I)]
    lk = [k for k, p in LOOK.items() if re.search(p, en, re.I)]
    return mv, lk


# ---- 2026-10-17 新增（学自 h3-storyboard-skill 与 Higgsfield HELL GRIND 项目 Brief；见 protocols/LEARNINGS_*.md）----
SPEAKCLAUSE = re.compile(r"<Subject \d+> \(S\d+\),.*?\{\{d:[^}]*\}\}", re.S)               # 说话句本身（含 says:）不检查
SAYVERB = re.compile(r"\b(says?|said|speaks?|spoke|tells?|told|talks?|whispers?|shouts?|yells?|asks?|replies|calls? out|murmurs?|mutters?)\b", re.I)
LIPSPART = re.compile(r"\b(lips? part(?:s|ed)?|mouth (?:opens|falls open|hangs open)|opens? (?:his|her) mouth)\b", re.I)   # 嘴型：会变成真的开口说话
AFTERSPEAK = re.compile(r"\b(swallows?|closes? (?:his|her) mouth|lips close|mouth closes|exhales after)\b", re.I)
COLLIDE = re.compile(r"\b(collid\w*|crash(?:es|ed|ing)? (?:into|through)|smash(?:es|ed|ing)? (?:into|through)|slam(?:s|med|ming)? into|spill(?:s|ed|ing)? (?:over|onto|across)|pours? (?:onto|over|into)|hurtl\w* into)\b", re.I)
UNITS = re.compile(r"\b\d+(?:\.\d+)?\s?(?:cm|mm|m|km|meters?|metres?|feet|foot|ft|inch(?:es)?|yards?)\b|\b(?:a|one) (?:hand|palm|finger)(?:'s)? (?:width|breadth|span)\b|\bhandspan\b", re.I)
ATOB = re.compile(r"\b(?:turns? into|changes? (?:from|into)|shifts? from [^.]{0,40} to|from (?:shock|fear|anger|calm|rage|relief|grief|hope|doubt|surprise|worry)[^.]{0,20} to)\b", re.I)
HANDSIDE = re.compile(r"\b(?:on|to|at|from) (?:his|her|their|\w+'s) (?:left|right)(?: side| hand)?\b(?!-)", re.I)   # 左右只从摄影机出发，写 frame-left / frame-right
VAGUE = re.compile(r"\b(nearby|somewhere|around (?:him|her|them|the room)|next to|close to)\b", re.I)   # 位置要靠地标/距离锚定
LEAVE = re.compile(r"\b(walks? away|leaves?|exits?|steps? out|disappears?|recedes?|fades? into the (?:crowd|dark|distance)|moves? off|heads? (?:off|out))\b", re.I)
PROCESS = re.compile(r"\b(reaches (?:into|for|out)|pulls? out|takes? out|draws?|winds? up|then|and then|before (?:he|she|they))\b", re.I)   # 连续过程（H3 擅长状态，不擅长过程）


def extra_lint(ep, plan, warns, errs):
    n_ep = 99                     # 工具包：所有集都按最新规则检查（原项目按集号分批启用）
    if n_ep < 31:
        return
    for s in plan["segments"]:
        sid = s["id"]; shots = s["shots"]
        for k, sh in enumerate(shots, 1):
            en = sh["en"]; where = f"{ep} Seg{sid} 镜{k}（{sh['storyboard_cn'][:24]}）"
            if RELAY.search(en):
                continue
            body = SPEAKCLAUSE.sub(" ", en)
            emo = {m.group(1).lower() for m in EMO.finditer(body)}
            if len(emo) > 2:
                warns.append(f"{where}：一镜里有 {len(emo)} 个情绪词（{'、'.join(sorted(emo))}），H3 一镜表情节拍超过 2–3 个会被抹平，拆镜")
            m_ab = next((m for m in ATOB.finditer(body) if "focus" not in body[max(0, m.start() - 40):m.end()].lower()), None)
            if m_ab and sh["dur"] < 3.0:
                warns.append(f"{where}：一镜里写了 A→B 的表情转折，H3 会交叉淡化成橡皮脸；把转折藏进闭眼/低头/切镜")
            if sh.get("dialogue"):
                if SAYVERB.search(body):
                    warns.append(f"{where}：说话句之外还出现 “{SAYVERB.search(body).group(0)}”，会被念出来或自带多余台词")
                if LIPSPART.search(body):
                    warns.append(f"{where}：写了 “{LIPSPART.search(body).group(0)}”，会变成真的开口说话；改成抿紧嘴唇或吞咽")
                if AFTERSPEAK.search(body):
                    warns.append(f"{where}：说话镜头里放了“说完之后”的动作（吞咽/收嘴），这些放到下一镜")
                for j in (k - 2, k):                      # 台词镜会抢相邻镜头的帧：旁边有离场/背景人物的镜头容易消失
                    if 0 <= j < len(shots) and LEAVE.search(shots[j]["en"]) and not RELAY.search(shots[j]["en"]):
                        warns.append(f"{where}：相邻镜头 {j + 1} 里有人离场/背景人物，台词镜会压缩它的帧数（E36 人物消失的嫌疑原因）；换位置或把台词镜挪远")
                        break
            elif SAYVERB.search(body) and not re.search(r"\bsay(?:s)? (?:nothing|no)\b", body):
                warns.append(f"{where}：无台词镜头里出现 “{SAYVERB.search(body).group(0)}”，会被念出来")
            if COLLIDE.search(en):
                warns.append(f"{where}：写了接触/碰撞/液体 “{COLLIDE.search(en).group(0)}”，H3 画不出接触因果；拍扫过画面→切→已发生的结果")
            if UNITS.search(en):
                warns.append(f"{where}：写了带单位的距离 “{UNITS.search(en).group(0)}”，会被忽略甚至渲染成接触；改成相对关系或画面内参照物")
            if HANDSIDE.search(en):
                warns.append(f"{where}：左右用法 “{HANDSIDE.search(en).group(0)}”，改成画面左/右（frame-left / frame-right）")
            if len(PROCESS.findall(en)) >= 3:
                warns.append(f"{where}：连续 {len(PROCESS.findall(en))} 个过程词，写成已处于中段的状态，过程另拍一镜")
            if sh["dur"] > 3.5 and not sh.get("dialogue") and re.search(r"holds a static shot|static shot", en) and len(re.findall(r"\b(?:then|as|while|the moment|until)\b", en)) < 2:
                warns.append(f"{where}：{sh['dur']}s 的静态镜头里没有 ≥2 个带先后的小事件（只写“很安静”只能撑 1.8 秒）")
        sub_vague = [sh for sh in shots if VAGUE.search(sh["en"]) and WHO.search(sh["en"]) and not RELAY.search(sh["en"])]
        if len(sub_vague) >= 3:
            warns.append(f"{ep} Seg{sid}：{len(sub_vague)} 个镜头用了 nearby/next to/around 这类模糊位置词，位置用地标或距离锚定（背贴墙、站在灯下）")
    # 淘汰词：该集 stale_terms.txt（一行一个正则）命中即 ❌（改了设定但旧词还留在摘要/声音/镜头里）
    sf = os.path.join(PIPE, "episodes", ep, "stale_terms.txt")
    if os.path.isfile(sf):
        pats = [x.strip() for x in open(sf, encoding="utf-8") if x.strip() and not x.startswith("#")]
        blob = json.dumps(plan, ensure_ascii=False)
        for pt in pats:
            hits = re.findall(pt, blob, re.I)
            if hits:
                errs.append(f"{ep}：淘汰词 “{pt}” 还出现 {len(hits)} 次（改设定后旧词没清干净）")



# ---- 2026-10-17 新增（E41 起）：学自成片《BREAK》、loopforge 14 种 H3 运镜、God-minmax-H3（protocols/LEARNINGS_break-case_h3-shots.md）----
FROZEN = re.compile(r"\b(frozen|freezes|freeze|completely still|motionless|perfectly still|rigid(?:ly)?|holds one pose)\b", re.I)
CAMSOUND = re.compile(r"\b(camera|lens|drone|rig|gimbal|tripod|dolly|crane)\b", re.I)
TOCU = re.compile(r"\b(?:to|into|until|onto)\b[^.]{0,50}\b(?:extreme close-up|close-up|fills the frame)", re.I)
ACTIONV = re.compile(r"\b(sprints?|runs?|running|races?|charges?|leaps?|jumps?|lunges?|swings?|throws?|falls?|dives?|skids?|crash\w*)\b", re.I)
WIDE = re.compile(r"\b(wide shot|wide static shot|extreme wide|high wide|aerial|establishing|long shot|top-down wide)\b", re.I)
ROLL = re.compile(r"\brolls? (?:clockwise|counterclockwise)|dutch (?:angle|tilt)", re.I)


def size_of(en):
    return next((n for n, p in SIZE if re.search(p, en, re.I)), None)


def scene_id(sg):
    if sg.get("scene_ref"): return sg["scene_ref"]
    return next((r[2] for r in sg.get("refs", []) if len(r) > 2 and r[2] and str(r[2]).startswith("N-")), sg.get("scene"))


def break_lint(ep, plan, warns, errs=None):
    if False:                     # 工具包：所有集都按最新规则（原为 E41 起）
        return
    n_ep = 99; segs = plan["segments"]; rolls = 0; relays = 0
    for i, s in enumerate(segs):
        sid = s["id"]; shots = s["shots"]
        for k, sh in enumerate(shots, 1):
            en = sh["en"]; where = f"{ep} Seg{sid} 镜{k}（{sh['storyboard_cn'][:24]}）"
            if RELAY.search(en):
                continue
            if FROZEN.search(en) and WHO.search(en):
                warns.append(f"{where}：人物写了 “{FROZEN.search(en).group(0)}”，H3 会把运镜拖掉约 80%；改成站着、呼吸、眨眼、轻微换重心")
            if re.search(MOVES["推"], en, re.I) and TOCU.search(en) and size_of(en.split("push", 1)[0]) == "极特写":
                warns.append(f"{where}：开头已经是极特写还要推，没有推的空间；以特写结束的推镜要从中景或远景开始")
            if re.search(MOVES["推"], en, re.I) and not re.search(r"foreground|past (?:the|a)|frame edge|in the near", en, re.I) and sh["dur"] >= 2.4:
                pass                                                     # 推镜加前景是 trial（push_foreground），先不报，避免噪音
            rolls += bool(ROLL.search(en))
        snd = (s.get("en") or {}).get("soundscape", "")
        if CAMSOUND.search(snd):
            warns.append(f"{ep} Seg{sid}：声音描述里出现 “{CAMSOUND.search(snd).group(0)}”，会被画进画面或拖掉运镜；声音段只写场内声音")
        if i + 1 < len(segs):
            nxt = segs[i + 1]; last = shots[-1]; first = next((x for x in nxt["shots"] if not RELAY.search(x["en"])), nxt["shots"][0])
            same = scene_id(s) == scene_id(nxt)
            if s["connection_to_next"] == "TAIL_RELAY":
                relays += 1
                if errs is not None and not s.get("relay_reason"):
                    errs.append(f"{ep} Seg{sid}→{sid + 1}：E41 起同场景不用尾帧接力，改《BREAK》法——硬切、新段换景别开场（scene_recut）；确需接力时在该段写 relay_reason 说明理由")
                if last.get("dialogue"):
                    warns.append(f"{ep} Seg{sid}→{sid + 1}：接力缝落在台词镜上；接缝放在换气、视线转开或一记重音之后")
                elif ACTIONV.search(last["en"]) or any(re.search(MOVES[m], last["en"], re.I) for m in ("推", "拉", "摇", "移", "环绕", "跟")):
                    warns.append(f"{ep} Seg{sid}→{sid + 1}：接力缝落在动作或运镜中段（{last['storyboard_cn'][:20]}）；改成硬切换景别，或让上一段停在静止的一拍")
            elif same and n_ep >= 51 and size_of(last["en"]) == "全景" and size_of(first["en"]) == "全景":
                (errs if errs is not None else warns).append(f"{ep} Seg{sid}→{sid + 1}：同场景硬切，全景接全景（跳帧感）；新段改用中景/近景/过肩开场")
            elif same and size_of(last["en"]) and size_of(last["en"]) == size_of(first["en"]):
                warns.append(f"{ep} Seg{sid}→{sid + 1}：同场景硬切，但新段开场景别和上一段结尾一样（{size_of(first['en'])}）；新段换景别开场（远景↔近景↔过肩）")
            if same and n_ep >= 51 and s["connection_to_next"] == "HARD_CUT" and s.get("seam_motive") not in ("action", "gaze", "sound"):
                (errs if errs is not None else warns).append(f"{ep} Seg{sid}→{sid + 1}：E51 起同场景每条硬切缝要有动机——在该段写 seam_motive：action（上一镜动作在下一镜完成）/ gaze（上一镜人物看向的东西就是下一镜）/ sound（声音先于画面或压过切点）")
            if not same and not any(WIDE.search(x["en"]) for x in nxt["shots"][:3]):
                warns.append(f"{ep} Seg{sid + 1}：换了场景，前三镜没有地点标点远景（wide / aerial / establishing）")
    if relays > 2:
        warns.append(f"{ep}：{relays} 条接力缝（E41 起同场景一律《BREAK》法硬切换景别；带理由的接力也建议一集 ≤2 条）")
    if rolls > 1:
        warns.append(f"{ep}：荷兰角/翻滚用了 {rolls} 次，试用期一集最多一次")

# ---- 工具包新增（2026-10-24，RunningHub H3 Enhanced 三晚约 150 条对照 + E41–E60 动作量实测；见 playbook/09_规则证据表.md）----
STATIC = re.compile(r"holds a static shot|wide static shot|locked-off|stays (?:completely )?still", re.I)
HIT = re.compile(r"\b(punch\w*|strik\w*|kick\w*|slam\w*|smash\w*|tackl\w*|elbow\w*|headbutt\w*|throws? (?:him|her)|hurl\w*|swings? (?:the|his|her)|crash\w* (?:into|through)|lunges?)\b", re.I)
LOCK1 = re.compile(r"silent one-second position-lock|position-lock frame", re.I)
DIAGLOCK = re.compile(r"staging diagram|positions-only map", re.I)


def rh_lint(ep, plan, warns):
    for s in plan["segments"]:
        sid = s["id"]; shots = s["shots"]
        n_static = sum(1 for sh in shots if STATIC.search(sh["en"]))
        if len(shots) >= 3 and n_static / len(shots) >= 0.6:
            warns.append(f"{ep} Seg{sid}：{n_static}/{len(shots)} 个镜头写了 static/固定机位——H3 会整段偏慢偏僵（E41–E60 实测固定全景开场首秒动作量 2.9，推/跟开场 19.6；RH 实测删掉 static、换有动机的运镜后后 5 秒动作量 4→8）。除了对白特写，给镜头一个有动机的运镜（push in / tracks / tilts / handheld）")
        for k, sh in enumerate(shots, 1):
            en = sh["en"]
            if HIT.search(en) and sh["dur"] > 1.6 and not sh.get("dialogue"):
                warns.append(f"{ep} Seg{sid} 镜{k}：打击/冲撞动作镜头 {sh['dur']}s——H3 会把一个动作摊满整镜像慢动作；每个打击单独一镜 0.8–1.4 s、一镜一动作（RH 实测 1 秒一镜前 5 秒动作量最高）")
            if re.search(r"slow motion|slow-motion", en, re.I) and HIT.search(en):
                warns.append(f"{ep} Seg{sid} 镜{k}：打斗镜头写了慢动作；一段最多在最关键一击用一次，其余写 full real-time speed")
        cast_n = len([r for r in s.get("refs", []) if len(r) > 2 and r[2] and str(r[2]).startswith(("C", "X"))])
        has_talk = any(sh.get("dialogue") for sh in shots)
        if cast_n >= 3 and has_talk and shots and not LOCK1.search(shots[0]["en"]) and not RELAY.search(shots[0]["en"]):
            warns.append(f"{ep} Seg{sid}：{cast_n} 人同场对话、开头不是「静默锁位首秒」——RH 实测（人物一开始不说话时 7/7）写 ‘a silent one-second position-lock frame: every mouth stays closed and the room is silent; <站位>, the camera steady’ 能稳定拿到 1 秒站位全景；站位要精确再加站位线稿图")


def lint(ep, only=None):
    f = os.path.join(PIPE, "episodes", ep, "plan.json")
    if not os.path.isfile(f):
        return None
    plan = json.load(open(f, encoding="utf-8")); n_ep = 99; ep_no = int(ep[1:])   # n_ep=99：按最新规则
    errs, warns, stat = [], [], {"shots": 0, "hero": 0, "use": {}, "react": 0, "react_emo": 0, "camline": 0}
    for s in plan["segments"]:
        sid = s["id"]; run = []; hero_in_seg = 0; prev_key = None
        for k, sh in enumerate(s["shots"], 1):
            en = sh["en"]; where = f"{ep} Seg{sid} 镜{k}（{sh['storyboard_cn'][:28]}）"
            if GROUP.search(en) and WHO.search(en) and not RELAY.search(en) and not ORDER.search(GROUP.sub(" ", en)):   # 只查写到人物的镜头
                warns.append(f"{where}：多人动作没写先后顺序或画面站位")
            if only == "group":
                continue
            m = BANNED.search(en)
            if m:
                errs.append(f"{where}：本剧禁用的写法 “{m.group(0)}”（见 techniques.json banned）")
            mv, lk = tags(en)
            if RELAY.search(en):
                mv = []                                  # 接力首镜是固定 1 秒，描述里的"跟拍/主观"只是复述上一段
            if "慢动作" in lk and sh.get("dialogue"):
                errs.append(f"{where}：带台词的镜头写了慢动作")
            if len(mv) > 1 and not set(mv) <= {"跟", "晃"}:
                warns.append(f"{where}：一个镜头写了 {len(mv)} 种运镜（{'+'.join(mv)}），H3 一镜一运动")
            for x in mv:
                if sh["dur"] < MIN_DUR[x] - 1e-6:
                    warns.append(f"{where}：{x}镜只有 {sh['dur']}s，至少 {MIN_DUR[x]}s 才看得出来")
            if sh.get("dialogue") and WIDE_TALK.search(en) and not LIPS.search(en):
                warns.append(f"{where}：台词镜头画面里可能有别人的正脸，写明听者 lips at rest 或让他背身/出画（drama-skills H3 实测：口型会落到最显眼的正脸）")
            m2 = INFER.search(en)
            if m2:
                warns.append(f"{where}：推断词 “{m2.group(0)}” 画不出来，改成看得见的动作或表情")
            size = next((n for n, p in SIZE if re.search(p, en, re.I)), None)
            who = PART(WHO.search(en.split("cuts to", 1)[-1]))
            key = (size, who, bool(mv or lk))
            if prev_key and size and who and key == prev_key and not (mv or lk):
                warns.append(f"{where}：和上一镜景别、人物、角度都一样，这个切镜没有带来变化（改景别 / 换角度 / 并成一镜）")
            prev_key = key
            if RELAY.search(en) or ESTAB.search(en):
                continue
            stat["camline"] += bool(CAMLINE.search(en))
            if not sh.get("dialogue") and REACT.search(en):
                stat["react"] += 1; stat["react_emo"] += bool(EMO.search(en))
            stat["shots"] += 1
            for x in mv + lk:
                stat["use"][x] = stat["use"].get(x, 0) + 1
            if mv or lk:
                stat["hero"] += 1; hero_in_seg += 1
                if len(run) >= 4:
                    warns.append(f"{ep} Seg{sid} 镜{run[0]}–{run[-1]}：连续 {len(run)} 个平镜头（固定机位切近景/中景）")
                run = []
            else:
                run.append(k)
        if only == "group":
            continue
        if len(run) >= 4:
            warns.append(f"{ep} Seg{sid} 镜{run[0]}–{run[-1]}：连续 {len(run)} 个平镜头（固定机位切近景/中景）")
        pushes = sum(1 for sh in s["shots"] if re.search(MOVES["推"], sh["en"], re.I))
        if pushes > 2:
            warns.append(f"{ep} Seg{sid}：一段用了 {pushes} 次推镜，情绪点都用同一招会显得模板化")
        if hero_in_seg == 0:
            warns.append(f"{ep} Seg{sid}：整段没有一个视觉冲击镜头")
        if n_ep >= 31 and s["connection_to_next"] == "HARD_CUT" and not s.get("transition"):
            warns.append(f"{ep} Seg{sid}→{sid + 1}：换场缝没写 transition（match_cut / smash_cut / sound_bridge / cut）")
    if only != "group" and 31 <= n_ep < 51:          # E51 起开场钩子可选（用户 2026-10-19：每集同一套"极特写→大全景"开头成了套路）
        sh0 = plan["segments"][0]["shots"][0]["en"]
        if ESTAB.search(sh0) and "extreme close-up" not in sh0:
            warns.append(f"{ep} Seg1：开场直接是定位全景，没有开场钩子镜头（hook_open）")
    if only != "group":
        segs = plan["segments"]
        POS = re.compile(r"frame-left|frame-right|centred|centered|centre of the frame|middle of the frame|upper frame|lower third", re.I)
        SLOW = re.compile(r"slow motion|slow-motion", re.I)
        for i, s in enumerate(segs):
            sid = s["id"]; en = s.get("en", {})
            ff = en.get("first_frame") or ""
            if ff:                                                    # 1) 接力首帧里的人必须写进人数句
                cnt = en.get("count", "")
                miss = sorted({m.group(1) for m in WHO.finditer(ff)} - {m.group(1) for m in WHO.finditer(cnt)})
                if miss:
                    warns.append(f"{ep} Seg{sid}：接力首帧里有 {'、'.join(miss)}，人数句里没写（人物会消失或漂移）")
            tr = s.get("transition") or {}
            if tr.get("type") == "match_cut" and i + 1 < len(segs):   # 2) 匹配剪辑两边要有同一个位置词
                a_, b_ = segs[i]["shots"][-1]["en"], segs[i + 1]["shots"][0]["en"]
                pa = {x.lower() for x in POS.findall(a_)}; pb = {x.lower() for x in POS.findall(b_)}
                if not (pa & pb):
                    warns.append(f"{ep} Seg{sid}→{sid + 1}：写了 match_cut，但两边镜头没有共同的画面位置词，等于普通硬切")
            slows = [sh for sh in s["shots"] if SLOW.search(sh["en"]) and not RELAY.search(sh["en"])]
            if len(slows) > 1:                                        # 4) 慢动作一段一次、整镜不超过约 2.6 秒
                warns.append(f"{ep} Seg{sid}：一段用了 {len(slows)} 次慢动作（建议一段一次）")
            for sh in slows:
                if sh["dur"] > 2.6 and not re.search(r"the moment[^.]*plays in slow motion|slow-motion beat", sh["en"], re.I):
                    warns.append(f"{ep} Seg{sid}（{sh['storyboard_cn'][:20]}）：整镜慢动作 {sh['dur']}s，超过约 2.6 秒 H3 常常不慢；只让关键一刻慢下来")
        def scene_of(sg):
            return next((r[2] for r in sg.get("refs", []) if len(r) > 2 and r[2] and not str(r[2]).startswith(("C", "P", "X", "VOICE"))), None)
        prevf = os.path.join(PIPE, "episodes", f"E{ep_no - 1:02d}", "plan.json")
        cont = os.path.isfile(prevf) and scene_of(json.load(open(prevf, encoding="utf-8"))["segments"][-1]) == scene_of(segs[0]) if segs else False
        if n_ep >= 41:                                               # 4) E41–E60 复盘（用户 2026-10-20）：每段开头的全景如果"镜头不动 + 人物站着/坐着"，H3 会渲成静帧，看起来像慢动作
            MOVEC = re.compile(r"\b(pushes|pulls|tracks|tracking|trucks|arcs|cranes|tilts|pans|dollies|glides|rises|descends)\b", re.I)
            ACTV = re.compile(r"\b(walk|walks|run|runs|sprint|sprints|burst|bursts|swing|swings|rolls|roll|step|steps|stride|strides|charge|charges|rush|rushes|slam|slams|spin|spins|lift|lifts|swirl|swirls|flap|flaps|wave|waves|rain|rains|surge|surges|stream|streams|pour|pours|erupt|erupts|rotate|rotates|spins|flicker|flickers|flash|flashes)\b", re.I)
            for sg in segs:
                f0 = sg["shots"][0]["en"]
                if WIDE.search(f0) and not MOVEC.search(f0) and sg["shots"][0]["dur"] >= 1.8:
                    warns.append(f"{ep} Seg{sg['id']} 镜1：开场全景镜头不动（{sg['shots'][0]['dur']}s 的 static wide）——H3 会把站着不动的人渲成静帧、像慢动作；改成镜头缓推/拉/横移/升降，并写一个持续的动作（人走进画面、车驶过、门打开、人群挥旗）")
                elif WIDE.search(f0) and not ACTV.search(f0) and sg["shots"][0]["dur"] >= 1.8:
                    warns.append(f"{ep} Seg{sg['id']} 镜1：开场全景里没有持续的动作词（只有站着/坐着/看着）；写一个连续动作，让画面从第 0 秒就在动")
        if n_ep >= 31 and segs and not cont:                          # 3) 第一段：钩子之后要有定位全景（紧接上一集同场景时不要求）
            first = segs[0]["shots"]
            if not ESTAB.search(first[0]["en"]) and not any(re.search(r"wide (?:static |tracking )?shot|position-lock", x["en"], re.I) for x in first[:3]):
                warns.append(f"{ep} Seg1：前三镜里没有交代空间的全景（要会动的全景，或多人静态戏用「静默锁位首秒」）")
    if only != "group":
        extra_lint(ep, plan, warns, errs)
        break_lint(ep, plan, warns, errs)
        rh_lint(ep, plan, warns)
    if only != "group" and n_ep >= 31 and stat["react"] and stat["react_emo"] / stat["react"] < 0.5:
        warns.append(f"{ep}：反应镜只有 {stat['react_emo']}/{stat['react']} 点名了情绪；H3 反应镜写法＝情绪词 + 两处可见泄露 + 1.5 秒内落下定住（CINEMATOGRAPHY §9）")
    if only != "group" and n_ep >= 31 and stat["shots"] and stat["hero"] / stat["shots"] < 0.30:
        warns.append(f"{ep}：冲击镜头只占 {round(100 * stat['hero'] / stat['shots'])}%，目标 ≥30%（每段 2–3 个）")
    return errs, warns, stat


def main():
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    only = "group" if "--only" in sys.argv and "group" in sys.argv else None
    brief = "--brief" in sys.argv
    if only:
        args = [x for x in args if x != "group"]
    bad = 0; rows = []
    for ep in eps(args or ["E21-E30"]):
        r = lint(ep, only)
        if r is None:
            continue
        errs, warns, st = r; bad += len(errs)
        if not brief:
            for e in errs: print("❌", e)
            for w in warns: print("⚠ ", w)
        if not only:
            pct = round(100 * st["hero"] / max(1, st["shots"]))
            top = "、".join(f"{k}{v}" for k, v in sorted(st["use"].items(), key=lambda x: -x[1])[:6]) or "—"
            rows.append(f"{ep}  冲击镜头 {st['hero']:3d}/{st['shots']:3d}（{pct:2d}%）  反应镜点名情绪 {st['react_emo']:2d}/{st['react']:2d}  写了机位句 {st['camline']:2d}/{st['shots']:2d}  ❌{len(errs)} ⚠{len(warns):2d}  手段：{top}")
        else:
            print(f"{ep} 站位问题 {len(warns)} 个")
    if rows:
        print("\n".join(["", "摄影统计（不含接力首帧和首秒定位全景）："] + rows))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
