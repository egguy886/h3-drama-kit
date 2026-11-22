#!/usr/bin/env python3
"""摄影与空间防穿帮检查 v2.0（只读、免费）：检查 plan.json 的镜头语言与空间/资产严谨度。

用法：python3 tools/shot_lint.py E31            # 一集
      python3 tools/shot_lint.py E21-E30 --brief # 多集，只出统计
      python3 tools/shot_lint.py E31 --only group
❌（退出码 1，build_episode 会失败）：
  - 本剧禁用的运镜/转场（推拉变焦、子弹时间、H3 内甩镜/叠化、Shake Strongly…）
  - 带台词的镜头写了慢动作
  - [v2.0 新增] 常规叙事/动作镜时长 <2.0s（纯单次打击镜与首秒静默锁位帧除外）
  - [v2.0 新增] 未挂载对应人物母图却写了额外人影/黑影（silhouette / dark figure 等）
  - [v2.0 新增] 同一集内不同物理子空间共用同一张固定构图场景母图（未标 same_room_ok=True）
  - [v2.0 新增] 尸体/无头躯干/装昏状态未在镜头内写死 'completely frozen motionless, zero breathing or swaying'
  - [v2.0 新增] 同处铁栅/隔断外侧的双人正反打把铁栅夹在两人中间（一镜前景隔栏、一镜抓栏杆，导致内外错位）
"""
import json, os, re, sys

PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _cast_names():
    names = set()
    for f in ("cast.json", "acting.json"):
        p = os.path.join(PIPE, "library", f)
        if os.path.isfile(p):
            for k, v in json.load(open(p, encoding="utf-8")).items():
                if k.startswith("_"):
                    continue
                if f == "acting.json":
                    names.add(k)
                elif isinstance(v, dict) and v.get("kind") != "creature":
                    if v.get("name"):
                        names.add(v["name"])
                    if v.get("name_en"):
                        names.add(v["name_en"])
                    names.update(v.get("aliases", []))
    names = sorted((n for n in names if n), key=len, reverse=True) or ["Somebody"]
    return "|".join(re.escape(n) for n in names)


NAMES = _cast_names()

GROUP = re.compile(r"one after another|in turn|all three|the three|both (?:of )?(?:them|men|boys)|(?:walk|run|move|step|stand|duck|sprint)s? together|side by side|rush(?:es)? in|slip(?:s)? through|duck(?:s)? through|step(?:s)? through|file(?:s)? out|the two (?:of )?(?:them|stand|walk|run|turn|duck)|(?:the|all) (?:students|guards|officers)", re.I)
ORDER = re.compile(r"\b(first|then|second|last|behind|ahead|leads?|leading|follows?|following|trailing|(?:at|from) frame-left|(?:at|from) frame-right|nearest|farthest)\b", re.I)

MOVES = {
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
LOOK = {
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
BANNED = re.compile(r"bullet time|360-degree|\borbits?\b|\bFPV\b|drone shot|whip[- ]pans?|crash zoom|zooms? in (?:with \w+ amplitude )?at fast speed|cross-dissolve|the shot dissolves|dissolves? into the next|fades? (?:to|from) black|the shot fades|wipe transition|shakes? strongly|double exposure|glitch", re.I)
EMO = re.compile(r"\b(shock|stun|startl|furi|fury|anger|angr|afraid|fear|terrif|smug|grief|horror|disbelie|dread|rage|relie|triumph|panic|guilt|hurt|resolv|resolute|defian|despair|contempt|suspici|alarm|confus|hope|humiliat|betray|devastat|moved|vulnerab|wary|at ease|tender|asham|shame|desperat|sorrow|joy|elat|stricken|haunt|broken|exhaust|determin|wonder|awe|fierce|exult|uneas|unflinch|calm)", re.I)
LIPS = re.compile(r"lips (?:at rest|stay closed|remain(?:s)? (?:completely )?closed|pressed shut)|back (?:turned )?to (?:the )?camera|from behind|silhouett", re.I)
WIDE_TALK = re.compile(r"two-shot|medium shot|medium-wide|wide shot|over-the-shoulder|full-body", re.I)
REACT = re.compile(r"close-up of (?:" + NAMES + r")(?!'s (?:right |left )?(?:fist|hands?|boots?|foot|feet|fingers?|fingertips?|shoes?|spikes?|knuckles?|wrists?|thumb|palm|ankle|heel))|close-up of \w+'s (?:face|eyes)", re.I)
SIZE = [("极特写", r"extreme close-up"), ("近景", r"medium close-up|close-up|close shot"), ("中景", r"medium shot|waist up|medium-wide"),
        ("全身", r"full-body|full body"), ("全景", r"wide shot|wide static shot|long shot|establishing")]
WHO = re.compile(r"\b(" + NAMES + r")\b(?:'s (?:\w+ )?(hands?|fist|fingers?|boots?|foot|feet|wrists?|palm|shoes?|spikes?|ankle|heel|knuckles?))?")
PART = lambda m: (m.group(1) + ("·" + m.group(2) if m.group(2) else "")) if m else None
INFER = re.compile(r"\b(seems? to|as if|as though|realizes?|suddenly understands|senses?|appears to)\b", re.I)
CAMLINE = re.compile(r"\bthe camera (?:holds|pushes|pulls|pans|tilts|trucks|tracks|arcs|pedestals|rises|follows|shakes|stays)|static shot|locked|\bPOV\b|focus shifts", re.I)
RELAY = re.compile(r"^The shot begins from <Picture 1>")
ESTAB = re.compile(r"^A wide static shot fixes")


def eps(spec):
    out = []
    for p in spec:
        m = re.fullmatch(r"E(\d+)-E?(\d+)", p.upper())
        out += [f"E{i:03d}" if len(m.group(1)) == 3 else f"E{i:02d}" for i in range(int(m.group(1)), int(m.group(2)) + 1)] if m else [p.upper()]
    return out


def tags(en):
    mv = [k for k, p in MOVES.items() if re.search(p, en, re.I)]
    lk = [k for k, p in LOOK.items() if re.search(p, en, re.I)]
    return mv, lk


SPEAKCLAUSE = re.compile(r"<Subject \d+> \(S\d+\),.*?\{\{d:[^}]*\}\}", re.S)
SAYVERB = re.compile(r"\b(says?|said|speaks?|spoke|tells?|told|talks?|whispers?|shouts?|yells?|asks?|replies|calls? out|murmurs?|mutters?)\b", re.I)
LIPSPART = re.compile(r"\b(lips? part(?:s|ed)?|mouth (?:opens|falls open|hangs open)|opens? (?:his|her) mouth)\b", re.I)
AFTERSPEAK = re.compile(r"\b(swallows?|closes? (?:his|her) mouth|lips close|mouth closes|exhales after)\b", re.I)
COLLIDE = re.compile(r"\b(collid\w*|crash(?:es|ed|ing)? (?:into|through)|smash(?:es|ed|ing)? (?:into|through)|slam(?:s|med|ming)? into|spill(?:s|ed|ing)? (?:over|onto|across)|pours? (?:onto|over|into)|hurtl\w* into)\b", re.I)
UNITS = re.compile(r"\b\d+(?:\.\d+)?\s?(?:cm|mm|m|km|meters?|metres?|feet|foot|ft|inch(?:es)?|yards?)\b|\b(?:a|one) (?:hand|palm|finger)(?:'s)? (?:width|breadth|span)\b|\bhandspan\b", re.I)
ATOB = re.compile(r"\b(?:turns? into|changes? (?:from|into)|shifts? from [^.]{0,40} to|from (?:shock|fear|anger|calm|rage|relief|grief|hope|doubt|surprise|worry)[^.]{0,20} to)\b", re.I)
HANDSIDE = re.compile(r"\b(?:on|to|at|from) (?:his|her|their|\w+'s) (?:left|right)(?: side| hand)?\b(?!-)", re.I)
VAGUE = re.compile(r"\b(nearby|somewhere|around (?:him|her|them|the room)|next to|close to)\b", re.I)
LEAVE = re.compile(r"\b(walks? away|leaves?|exits?|steps? out|disappears?|recedes?|fades? into the (?:crowd|dark|distance)|moves? off|heads? (?:off|out))\b", re.I)
PROCESS = re.compile(r"\b(reaches (?:into|for|out)|pulls? out|takes? out|draws?|winds? up|then|and then|before (?:he|she|they))\b", re.I)


def extra_lint(ep, plan, warns, errs):
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
                for j in (k - 2, k):
                    if 0 <= j < len(shots) and LEAVE.search(shots[j]["en"]) and not RELAY.search(shots[j]["en"]):
                        warns.append(f"{where}：相邻镜头 {j + 1} 里有人离场/背景人物，台词镜会压缩它的帧数；换位置或把台词镜挪远")
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
    sf = os.path.join(PIPE, "episodes", ep, "stale_terms.txt")
    if os.path.isfile(sf):
        pats = [x.strip() for x in open(sf, encoding="utf-8") if x.strip() and not x.startswith("#")]
        blob = json.dumps(plan, ensure_ascii=False)
        for pt in pats:
            hits = re.findall(pt, blob, re.I)
            if hits:
                errs.append(f"{ep}：淘汰词 “{pt}” 还出现 {len(hits)} 次（改设定后旧词没清干净）")


FACE = re.compile(r"\b(?:extreme close-up|close-up|close shot|medium close-up) of <Subject \d+>(?!'s (?:hands?|thumbs?|fingers?|feet|foot|knees?|wrists?|shoes?|sneakers?|ears?|back|shoulders?))|<Subject \d+>'s (?:face|mouth|lips)\b", re.I)
SHUT = re.compile(r"\b(?:lips? (?:at rest|closed|pressed|press|stay closed|together)|mouth (?:closed|shut|at rest|stays closed)|presses? (?:his|her) lips|jaw (?:set|clenched)|bites? (?:his|her) lip)\b", re.I)
SEEN = re.compile(r"\b(?:looks?|looking|glances?|stares?|staring|gazes?|eyes (?:on|drop|fall|go|land|lock)|sees?|notices?|spots?|reads?|reading|watch(?:es|ing)?|turns? (?:to|toward)|insert|close-up of (?:a|an|the) )", re.I)
DEIXIS = re.compile(r"\b(?:this|that|these|those|what is|what's|whose|why is|is that)\b", re.I)


def causal_lint(ep, plan, warns):
    lines = {}
    lk = os.path.join(PIPE, "episodes", ep, "02_dialogue_lock.json")
    if os.path.isfile(lk):
        for x in json.load(open(lk, encoding="utf-8")).get("lines", []):
            lines[x.get("id")] = x.get("text_en", "")
    for s in plan["segments"]:
        shots = s["shots"]
        if not any(sh.get("dialogue") for sh in shots):
            continue
        for k, sh in enumerate(shots, 1):
            en = sh["en"]; where = f"{ep} Seg{s['id']} 镜{k}（{sh['storyboard_cn'][:24]}）"
            if RELAY.search(en):
                continue
            if not sh.get("dialogue"):
                if FACE.search(en) and not SHUT.search(en):
                    warns.append(f"{where}：对白段里拍到脸的无台词镜头没写闭嘴，H3 容易让这张脸也动嘴；加 lips at rest / lips pressed together")
                continue
            t = lines.get(sh["dialogue"], "")
            if t.rstrip().endswith("?") and DEIXIS.search(t):
                prev = shots[k - 2]["en"] if k > 1 else ""
                if not SEEN.search(SPEAKCLAUSE.sub(" ", en)) and not SEEN.search(prev):
                    warns.append(f"{where}：指着东西发问（{t[:30]}），本镜和上一镜都没写先看见它；先给视线落点或那件东西的特写，再发问")


FROZEN = re.compile(r"\b(frozen|freezes|freeze|completely still|motionless|perfectly still|rigid(?:ly)?|holds one pose)\b", re.I)
CORPSE_OR_STILL = re.compile(
    r"\b(?:headless|corpses?|dead\s+bod(?:y|ies)|lifeless|unconscious|feigning\s+(?:sleep|death|unconsciousness)|playing\s+dead|completely frozen motionless)\b",
    re.I,
)
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
    n_ep = 99; segs = plan["segments"]; rolls = 0; relays = 0
    for i, s in enumerate(segs):
        sid = s["id"]; shots = s["shots"]
        for k, sh in enumerate(shots, 1):
            en = sh["en"]; where = f"{ep} Seg{sid} 镜{k}（{sh['storyboard_cn'][:24]}）"
            if RELAY.search(en):
                continue
            # v2.0 豁免尸体/无头躯干/装昏镜头的静止锁，只对活人误用 frozen 告警
            if FROZEN.search(en) and WHO.search(en) and not CORPSE_OR_STILL.search(en):
                warns.append(f"{where}：活人角色写了 “{FROZEN.search(en).group(0)}”，H3 会把运镜拖掉约 80%；活人改成站着、呼吸、眨眼、轻微换重心（仅尸体/装昏用 completely frozen motionless）")
            if re.search(MOVES["推"], en, re.I) and TOCU.search(en) and size_of(en.split("push", 1)[0]) == "极特写":
                warns.append(f"{where}：开头已经是极特写还要推，没有推的空间；以特写结束的推镜要从中景或远景开始")
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
                    errs.append(f"{ep} Seg{sid}→{sid + 1}：同场景不用尾帧接力，改硬切、新段换景别开场；确需接力时在该段写 relay_reason 说明理由")
                if last.get("dialogue"):
                    warns.append(f"{ep} Seg{sid}→{sid + 1}：接力缝落在台词镜上；接缝放在换气、视线转开或一记重音之后")
                elif ACTIONV.search(last["en"]) or any(re.search(MOVES[m], last["en"], re.I) for m in ("推", "拉", "摇", "移", "环绕", "跟")):
                    warns.append(f"{ep} Seg{sid}→{sid + 1}：接力缝落在动作或运镜中段（{last['storyboard_cn'][:20]}）；改成硬切换景别，或让上一段停在静止的一拍")
            elif same and n_ep >= 51 and size_of(last["en"]) == "全景" and size_of(first["en"]) == "全景":
                (errs if errs is not None else warns).append(f"{ep} Seg{sid}→{sid + 1}：同场景硬切，全景接全景（跳帧感）；新段改用中景/近景/过肩开场")
            elif same and size_of(last["en"]) and size_of(last["en"]) == size_of(first["en"]):
                warns.append(f"{ep} Seg{sid}→{sid + 1}：同场景硬切，但新段开场景别和上一段结尾一样（{size_of(first['en'])}）；新段换景别开场（远景↔近景↔过肩）")
            if same and n_ep >= 51 and s["connection_to_next"] == "HARD_CUT" and s.get("seam_motive") not in ("action", "gaze", "sound"):
                (errs if errs is not None else warns).append(f"{ep} Seg{sid}→{sid + 1}：同场景每条硬切缝要有动机——在该段写 seam_motive：action / gaze / sound")
            if not same and not any(WIDE.search(x["en"]) for x in nxt["shots"][:3]):
                warns.append(f"{ep} Seg{sid + 1}：换了场景，前三镜没有地点标点远景（wide / aerial / establishing）")
    if relays > 2:
        warns.append(f"{ep}：{relays} 条接力缝（同场景一律硬切换景别；带理由的接力也建议一集 ≤2 条）")
    if rolls > 1:
        warns.append(f"{ep}：荷兰角/翻滚用了 {rolls} 次，试用期一集最多一次")


STATIC = re.compile(r"holds a static shot|wide static shot|locked-off|stays (?:completely )?still", re.I)
HIT = re.compile(r"\b(punch\w*|strik\w*|kick\w*|slam\w*|smash\w*|tackl\w*|elbow\w*|headbutt\w*|throws? (?:him|her)|hurl\w*|swings? (?:the|his|her|<Subject \d+>)|sweeps? <Subject \d+> upward|drives? (?:her|his) knee|crash\w* (?:into|through)|lunges?)\b", re.I)
LOCK1 = re.compile(r"silent one-second position-lock|position-lock frame", re.I)
DIAGLOCK = re.compile(r"staging diagram|positions-only map", re.I)

# ---- v2.0 新增：空间站位、单镜 2.5–5.0s 硬门禁与防穿帮四大规则 ----
_UNMOUNTED_PLURAL_RX = re.compile(
    r"\b(?:two|three|four|several|multiple)\s+(?:tall\s+|dark\s+|hooded\s+|black-clad\s+|shadowy\s+|hulking\s+|coarse-robed\s+)*(?:silhouettes?|figures?|human shadows?|strangers?|intruders?|guards?|bandits?|men)\b",
    re.I,
)
_UNMOUNTED_SINGLE_RX = re.compile(
    r"\b(?:a|one|another)\s+(?:tall\s+|dark\s+|hooded\s+|black-clad\s+|shadowy\s+|mysterious\s+)+(?:silhouette|figure|stranger|intruder|black-clad man)\b",
    re.I,
)
_CORPSE_EN_RX = re.compile(
    r"\b(?:headless(?:\s+[\w-]+){0,2}\s+(?:figures?|bodies|corpses?|bandits?|men|guards?|trunks?)|corpses?|dead\s+bod(?:y|ies)|lifeless\s+bod(?:y|ies)|feigning\s+(?:sleep|death|unconsciousness)|playing\s+dead)\b",
    re.I,
)
_CORPSE_CN_RX = re.compile(r"(?:无头(?:尸|躯干|矿匪)|死尸|尸体|装昏|装睡|假寐)")
_STILL_LOCK_RX = re.compile(r"completely frozen motionless,\s*zero breathing or swaying", re.I)
_THRU_BARS_RX = re.compile(r"framed through[^.]{0,35}\bbars\b", re.I)
_GRIP_BARS_RX = re.compile(r"gripping the (?:iron |wooden )?bars?\b", re.I)
_LOOT_RX = re.compile(r"\b(?:pulls?|takes?|draws?|snatches?)\b[^.]{0,45}\b(?:key|dagger|knife|pouch|packet|bun)\b", re.I)


def _subspace_key(seg):
    if seg.get("subspace"):
        return str(seg["subspace"]).strip()
    sc = str(seg.get("scene", "")).strip()
    sc = re.sub(r"^场\s*\d+\s*[.、·\-]?\s*", "", sc)
    sc = re.split(r"[：:]", sc, 1)[0].strip()
    sc = re.sub(r"\s*·\s*(?:内|外).*$", "", sc).strip()
    sc = re.sub(r"^(?:重返|回到)", "", sc).strip()
    return sc


def staging_and_rigor_lint(ep, plan, warns, errs, allow_legacy=False):
    sink = warns if (allow_legacy or plan.get("legacy_spatial_exempt")) else errs
    # 1) 异地子空间共用同一张固定构图场景母图拦截
    subspaces_by_ref = {}
    for s in plan["segments"]:
        sref = scene_id(s)
        subk = _subspace_key(s)
        if sref and str(sref).startswith("N-") and subk and not s.get("same_room_ok") and not plan.get("allow_shared_scene_ref"):
            subspaces_by_ref.setdefault(sref, {}).setdefault(subk, []).append(f"Seg{s['id']}")
    for sref, mp in subspaces_by_ref.items():
        if len(mp) > 1:
            detail = " / ".join(f"「{k}」({','.join(v)})" for k, v in mp.items())
            sink.append(f"{ep} [子空间混图拦截] 不同物理子空间共用了同一张固定构图场景母图 {sref}：{detail} → 请拆分为独立子空间母图（如走廊/隔壁牢/赌桌），重返同一房间请标 same_room_ok=True")

    for s in plan["segments"]:
        sid = s["id"]; shots = s["shots"]
        subjs = (s.get("en") or {}).get("subjects", [])
        subj_blob = " ".join(subjs)
        n_char_subj = sum(
            1 for x in subjs
            if re.match(r"<Subject \d+> is ", x)
            and "is the location shown in" not in x
            and "is the prop shown in" not in x
            and "the scene." not in x
            and "the prop." not in x
        )
        fight_hits = sum(1 for sh in shots if HIT.search(sh["en"]))
        real_shots = [sh for sh in shots if not LOCK1.search(sh["en"]) and not RELAY.search(sh["en"])]
        if len(real_shots) >= 5 and fight_hits == 0:
            warns.append(f"{ep} Seg{sid}：非打斗段切了 {len(shots)} 镜，建议收敛至 3–4 镜（每镜 2.5–5.0s）把动作与空间因果演透")

        both_outside_bars = bool(re.search(r"outside the (?:iron |wooden )?bars[^.]*<Subject \d+>[^.]*<Subject \d+>|<Subject \d+> and <Subject \d+> stand[^.]*outside the (?:iron |wooden )?bars", subj_blob, re.I))
        thru_bar_shots, grip_bar_shots = [], []

        for k, sh in enumerate(shots, 1):
            en = sh["en"]; cn = sh.get("wenwu", ""); dur = float(sh["dur"])
            where = f"{ep} Seg{sid} 镜{k}（{sh['storyboard_cn'][:24]}）"
            if RELAY.search(en) or LOCK1.search(en) or ESTAB.search(en):
                continue

            en_nodlg = re.sub(r"\{\{d:[^}]*\}\}", "", en)
            cn_nodlg = re.sub(r"\{\{q:[^}]*\}\}|[“\"].*?[”\"]", "", cn)

            # 2) 单镜时长硬门禁（常规镜 2.5–5.0s；<2.0s 非纯打击镜 ❌）
            is_hit = bool(HIT.search(en_nodlg))
            if is_hit and _LOOT_RX.search(en_nodlg):
                sink.append(f"{where}：在同一镜里既做打击又摸尸/取物，动作会被模型跳过变魔术；请拆成独立 ≥2.5s 搜身取物镜并先交代道具出处")
            elif not is_hit:
                if dur < 2.0 - 1e-6:
                    sink.append(f"{where}：[碎切门禁] 常规叙事/动作镜仅 {dur}s（<2.0s），动作来不及演完即硬切瞬移；请合并镜头或拉长至 2.5–5.0s")
                elif dur < 2.5 - 1e-6:
                    warns.append(f"{where}：镜头时长 {dur}s 偏短（常规镜建议 2.5–5.0s，每段 3–4 镜为主，演清起手→过程→结果）")
                elif dur > 5.5 + 1e-6 and not sh.get("dialogue"):
                    warns.append(f"{where}：无台词单镜长达 {dur}s（建议控制在 2.5–5.0s 以免后半段漂移）")

            # 3) 未挂母图禁写人影
            mp_u = _UNMOUNTED_PLURAL_RX.search(en_nodlg)
            if mp_u and n_char_subj <= 1 and "headless" not in mp_u.group(0).lower():
                sink.append(f"{where}：[未挂母图禁写人影] 本段仅挂载 {n_char_subj} 名角色，却写了多人黑影/人物「{mp_u.group(0)}」（H3 会凭空捏造黑衣人）")
            ms_u = _UNMOUNTED_SINGLE_RX.search(en_nodlg)
            if ms_u and (n_char_subj == 0 or (n_char_subj == 1 and re.search(r"\b(?:stranger|intruder|black-clad|hooded)\b", ms_u.group(0), re.I))):
                sink.append(f"{where}：[未挂母图禁写人影] 写了未挂载的陌生人影「{ms_u.group(0)}」")

            # 4) 尸体/无头躯干/装昏静止死锁
            if (_CORPSE_EN_RX.search(en_nodlg) or _CORPSE_CN_RX.search(cn_nodlg)) and not _STILL_LOCK_RX.search(en_nodlg):
                sink.append(f"{where}：[静止死锁缺失] 含尸体/无头躯干/装昏状态，必须在镜头英文内写死 'completely frozen motionless, zero breathing or swaying'")

            # 5) 隔断物同侧正反打反切检测
            if _THRU_BARS_RX.search(en_nodlg):
                thru_bar_shots.append(k)
            if _GRIP_BARS_RX.search(en_nodlg) and not re.search(r"\b(?:corridor side|both outside|outside the bars)\b", en_nodlg, re.I):
                grip_bar_shots.append(k)

        if both_outside_bars and thru_bar_shots and grip_bar_shots:
            sink.append(
                f"{ep} Seg{sid} [隔断内外错位拦截] 站位声明双人同在铁栅外侧，但镜{thru_bar_shots}隔着前景铁栅拍一人、镜{grip_bar_shots}拍另一人抓铁栅，会把同伙视觉关进牢内；请统一在走廊同侧取景"
            )


def rh_lint(ep, plan, warns):
    for s in plan["segments"]:
        sid = s["id"]; shots = s["shots"]
        n_static = sum(1 for sh in shots if STATIC.search(sh["en"]))
        if len(shots) >= 3 and n_static / len(shots) >= 0.6:
            warns.append(f"{ep} Seg{sid}：{n_static}/{len(shots)} 个镜头写了 static/固定机位——H3 会整段偏慢偏僵。除了对白特写，给镜头一个有动机的运镜（push in / tracks / tilts / handheld）")
        for k, sh in enumerate(shots, 1):
            en = sh["en"]
            if HIT.search(en) and sh["dur"] > 1.6 and not sh.get("dialogue"):
                warns.append(f"{ep} Seg{sid} 镜{k}：纯打击/冲撞动作镜头 {sh['dur']}s——每个打击单独一镜 0.8–1.4 s、一镜一动作（搜身取物等后续动作拆到下一镜 ≥2.5s）")
            if re.search(r"slow motion|slow-motion", en, re.I) and HIT.search(en):
                warns.append(f"{ep} Seg{sid} 镜{k}：打斗镜头写了慢动作；一段最多在最关键一击用一次，其余写 full real-time speed")
        _cast_p = os.path.join(PIPE, "library", "cast.json")
        _cast_lib = json.load(open(_cast_p, encoding="utf-8")) if os.path.isfile(_cast_p) else {}
        cast_n = len([r for r in s.get("refs", []) if len(r) > 2 and r[2] and str(r[2]).startswith(("C", "X")) and _cast_lib.get(str(r[2]), {}).get("kind") != "creature"])
        has_talk = any(sh.get("dialogue") for sh in shots)
        if cast_n >= 3 and has_talk and shots and not LOCK1.search(shots[0]["en"]) and not RELAY.search(shots[0]["en"]):
            warns.append(f"{ep} Seg{sid}：{cast_n} 人同场对话、开头不是「静默锁位首秒」——写 lock1 拿到 1 秒站位全景再切")


def lint(ep, only=None, allow_legacy=False):
    f = os.path.join(PIPE, "episodes", ep, "plan.json")
    if not os.path.isfile(f):
        return None
    plan = json.load(open(f, encoding="utf-8")); n_ep = 99; ep_no = int(ep[1:])
    errs, warns, stat = [], [], {"shots": 0, "hero": 0, "use": {}, "react": 0, "react_emo": 0, "camline": 0}
    for s in plan["segments"]:
        sid = s["id"]; run = []; hero_in_seg = 0; prev_key = None
        for k, sh in enumerate(s["shots"], 1):
            en = sh["en"]; where = f"{ep} Seg{sid} 镜{k}（{sh['storyboard_cn'][:28]}）"
            if GROUP.search(en) and WHO.search(en) and not RELAY.search(en) and not ORDER.search(GROUP.sub(" ", en)):
                warns.append(f"{where}：多人动作没写先后顺序或画面站位")
            if only == "group":
                continue
            m = BANNED.search(en)
            if m:
                errs.append(f"{where}：本剧禁用的写法 “{m.group(0)}”（见 techniques.json banned）")
            mv, lk = tags(en)
            if RELAY.search(en):
                mv = []
            if "慢动作" in lk and sh.get("dialogue"):
                errs.append(f"{where}：带台词的镜头写了慢动作")
            if len(mv) > 1 and not set(mv) <= {"跟", "晃"}:
                warns.append(f"{where}：一个镜头写了 {len(mv)} 种运镜（{'+'.join(mv)}），H3 一镜一运动")
            for x in mv:
                if sh["dur"] < MIN_DUR[x] - 1e-6:
                    warns.append(f"{where}：{x}镜只有 {sh['dur']}s，至少 {MIN_DUR[x]}s 才看得出来")
            if sh.get("dialogue") and WIDE_TALK.search(en) and not LIPS.search(en):
                warns.append(f"{where}：台词镜头画面里可能有别人的正脸，写明听者 lips at rest 或让他背身/出画")
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
    if only != "group":
        segs = plan["segments"]
        POS = re.compile(r"frame-left|frame-right|centred|centered|centre of the frame|middle of the frame|upper frame|lower third", re.I)
        SLOW = re.compile(r"slow motion|slow-motion", re.I)
        for i, s in enumerate(segs):
            sid = s["id"]; en = s.get("en", {})
            ff = en.get("first_frame") or ""
            if ff:
                cnt = en.get("count", "")
                miss = sorted({m.group(1) for m in WHO.finditer(ff)} - {m.group(1) for m in WHO.finditer(cnt)})
                if miss:
                    warns.append(f"{ep} Seg{sid}：接力首帧里有 {'、'.join(miss)}，人数句里没写（人物会消失或漂移）")
            tr = s.get("transition") or {}
            if tr.get("type") == "match_cut" and i + 1 < len(segs):
                a_, b_ = segs[i]["shots"][-1]["en"], segs[i + 1]["shots"][0]["en"]
                pa = {x.lower() for x in POS.findall(a_)}; pb = {x.lower() for x in POS.findall(b_)}
                if not (pa & pb):
                    warns.append(f"{ep} Seg{sid}→{sid + 1}：写了 match_cut，但两边镜头没有共同的画面位置词，等于普通硬切")
            slows = [sh for sh in s["shots"] if SLOW.search(sh["en"]) and not RELAY.search(sh["en"])]
            if len(slows) > 1:
                warns.append(f"{ep} Seg{sid}：一段用了 {len(slows)} 次慢动作（建议一段一次）")
            for sh in slows:
                if sh["dur"] > 2.6 and not re.search(r"the moment[^.]*plays in slow motion|slow-motion beat", sh["en"], re.I):
                    warns.append(f"{ep} Seg{sid}（{sh['storyboard_cn'][:20]}）：整镜慢动作 {sh['dur']}s，超过约 2.6 秒 H3 常常不慢；只让关键一刻慢下来")
        def scene_of(sg):
            return next((r[2] for r in sg.get("refs", []) if len(r) > 2 and r[2] and not str(r[2]).startswith(("C", "P", "X", "VOICE"))), None)
        prev_ep = f"E{ep_no - 1:03d}" if len(ep) == 4 else f"E{ep_no - 1:02d}"
        prevf = os.path.join(PIPE, "episodes", prev_ep, "plan.json")
        cont = os.path.isfile(prevf) and scene_of(json.load(open(prevf, encoding="utf-8"))["segments"][-1]) == scene_of(segs[0]) if segs else False
        MOVEC = re.compile(r"\b(pushes|pulls|tracks|tracking|trucks|arcs|cranes|tilts|pans|dollies|glides|rises|descends)\b", re.I)
        ACTV = re.compile(r"\b(walk|walks|run|runs|sprint|sprints|burst|bursts|swing|swings|rolls|roll|step|steps|stride|strides|charge|charges|rush|rushes|slam|slams|spin|spins|lift|lifts|swirl|swirls|flap|flaps|wave|waves|rain|rains|surge|surges|stream|streams|pour|pours|erupt|erupts|rotate|rotates|spins|flicker|flickers|flash|flashes)\b", re.I)
        for sg in segs:
            f0 = sg["shots"][0]["en"]
            if WIDE.search(f0) and not MOVEC.search(f0) and sg["shots"][0]["dur"] >= 1.8:
                warns.append(f"{ep} Seg{sg['id']} 镜1：开场全景镜头不动（{sg['shots'][0]['dur']}s 的 static wide）——改成镜头缓推/拉/横移/升降，并写一个持续的动作")
            elif WIDE.search(f0) and not ACTV.search(f0) and sg["shots"][0]["dur"] >= 1.8:
                warns.append(f"{ep} Seg{sg['id']} 镜1：开场全景里没有持续的动作词；写一个连续动作，让画面从第 0 秒就在动")
        if segs and not cont:
            first = segs[0]["shots"]
            if not ESTAB.search(first[0]["en"]) and not any(re.search(r"wide (?:static |tracking )?shot|position-lock", x["en"], re.I) for x in first[:3]):
                warns.append(f"{ep} Seg1：前三镜里没有交代空间的全景（要会动的全景，或多人静态戏用「静默锁位首秒」）")
    if only != "group":
        extra_lint(ep, plan, warns, errs)
        break_lint(ep, plan, warns, errs)
        causal_lint(ep, plan, warns)
        rh_lint(ep, plan, warns)
        staging_and_rigor_lint(ep, plan, warns, errs, allow_legacy=allow_legacy)
    if only != "group" and stat["react"] and stat["react_emo"] / stat["react"] < 0.5:
        warns.append(f"{ep}：反应镜只有 {stat['react_emo']}/{stat['react']} 点名了情绪；H3 反应镜写法＝情绪词 + 两处可见泄露 + 1.5 秒内落下定住")
    if only != "group" and stat["shots"] and stat["hero"] / stat["shots"] < 0.30:
        warns.append(f"{ep}：冲击镜头只占 {round(100 * stat['hero'] / stat['shots'])}%，目标 ≥30%（每段 2–3 个）")
    return errs, warns, stat


def main():
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    only = "group" if "--only" in sys.argv and "group" in sys.argv else None
    brief = "--brief" in sys.argv
    allow_legacy = "--allow-legacy-spatial" in sys.argv
    if only:
        args = [x for x in args if x != "group"]
    bad = 0; rows = []
    for ep in eps(args or ["E21-E30"]):
        r = lint(ep, only, allow_legacy=allow_legacy)
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
