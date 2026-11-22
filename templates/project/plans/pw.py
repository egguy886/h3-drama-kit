"""plan_src 写作助手 v2.0：支持 STAGING_MAP 场次站位与子空间母图映射 + 单镜时长/人影/静止锁前置校验。

每集一个脚本 plans/eNN.py：
    from pw import *
    STAGING_MAP = [
        {"subspace": "场01 女囚室", "scene_ref": "N-MINE-CELL", "camera_side": "机位在牢内，画左生锈铁栅紧锁", "blocking": "桑晚仰卧画右湿石壁干草堆"},
        {"subspace": "场02 牢外走廊", "scene_ref": "N-MINE-CORRIDOR", "camera_side": "机位统一在走廊侧，画右为女囚室铁栅门", "blocking": "矿匪甲与疤脸老四同处画左石桌旁"},
    ]
    S = []
    S.append(seg(1, "场01 女囚室：…", "N-MINE-CELL", "mine_lamp", "A", "HARD_CUT", ["C01-MINE"], None, summary, sound, cn, [sh(...)], subspace="女囚室"))
    write("E01", "标题", header=[], notes=[], segs=S, staging_map=STAGING_MAP)
"""
import json, os, re


try:
    from defect_rules import ERRS, defect_check
except ImportError:
    ERRS = []
    def defect_check(*a, **k): pass

NEG_EN = re.compile(r"\b(not|no|never|without|nothing|none|cannot)\b|n't", re.I)
NEG_CN = ["不要", "禁止", "不得", "不能", "没有", "不会", "不出现", "避免"]


def neg_check(sid, summary, shots, cn, mood=None):
    def clean(t): return re.sub(r"\{\{d:[^}]*\}\}|\{SAY:[^}]*\}", "", t)
    def clean_cn(t): return re.sub(r"\{\{q:[^}]*\}\}|[“\"].*?[”\"]", "", t)
    for where, t in ([("mood", mood[0])] if mood else []) + [("总述 en", summary)] + [(f"镜{k}", x["en"]) for k, x in enumerate(shots, 1)]:
        m = NEG_EN.findall(clean(t))
        if m: print(f"  ⚠ Seg{sid} {where} 英文含否定词 {m}（改肯定式，例：'stays closed' 而不是 'does not open'）")
    for where, t in [("中文说明", " ".join(cn))] + [(f"镜{k}", x["cn"]) for k, x in enumerate(shots, 1)]:
        m = [w for w in NEG_CN if w in clean_cn(t)]
        if m: print(f"  ⚠ Seg{sid} {where} 含否定表达 {m}（改肯定式）")


SKIN_BAD = re.compile(r"\b(?:her|his|Wren's|Lucien's)?\s*(?:cheeks?|face|neck|skin)\b[^.,;]{0,18}\b(?:flush\w*|burn\w*|flam\w*|crimson|red|pink|blush\w*)\b|\b(?:flushed|blushing|rosy)\b[^.,;]{0,12}\b(?:cheeks?|face)\b|\bblush\w*\b", re.I)
PEOPLE = re.compile(r"\{C\d|Wren|Lucien|Sloane|Beckett|Tyler|Graham|Owen|Evelyn|Diane|Grandma|Hastings|hand|finger|figure|silhouette|man\b|woman|girl|boy|guest|crowd|people|reporter|student", re.I)

LOCO = re.compile(r"\b(?:walk|walks|walking|step|steps|stepping|strides?|striding|runs? (?:to|toward|across|down|up|into|out)|running (?:to|toward|across|down|up|into|out)|dash(?:es)?|approach(?:es)?|crosses|moves? toward)\b", re.I)
THRU = re.compile(r"\b(?:into|out of|through)\b[^.;]{0,40}\b(?:elevator|lift|door|doorway|car|room|corridor|hallway|hall|gate)\b", re.I)
DIRWORD = re.compile(r"toward the camera|away from the camera|from behind|back to the camera|facing the camera|seen from|camera (?:inside|behind|in front)", re.I)
AGENTLESS = re.compile(r"\b(?:already|left)\s+(?:swung\s+|standing\s+|wide\s+)?open\b|\bdoors?\s+(?:opens|swings open|slides open)\b", re.I)
MOVES = re.compile(r"\b(?:pushes in|push(?:es)? in|pulls? back|pulls? out|pans?|tilts?|tracks?|orbits?|cranes?|dollies|dolly|whip-pans?|zooms?)\b", re.I)
CHAOS = re.compile(r"\b(?:recoil\w*|scatter\w*|leap\w*|jump\w*|explod\w*|stampede\w*|bursting across|guests? (?:flee|duck|dive))\b", re.I)
CAR = re.compile(r"\b(?:rear seat|back seat|backseat|inside the (?:car|Bentley|SUV)|in the (?:car|Bentley|SUV)|car interior|passenger seat|open (?:car|rear) door)\b", re.I)
CARCAM = re.compile(r"camera (?:sits|is placed|is mounted|stays|holds) (?:in|on|at|outside)|from the (?:front|passenger|driver)|through the (?:windshield|window|side window)|from outside the", re.I)


def _subspace_key(seg):
    if seg.get("subspace"):
        return str(seg["subspace"]).strip()
    sc = str(seg.get("scene", "")).strip()
    sc = re.sub(r"^场\s*\d+\s*[.、·\-]?\s*", "", sc)
    sc = re.split(r"[：:]", sc, 1)[0].strip()
    sc = re.sub(r"\s*·\s*(?:内|外).*$", "", sc).strip()
    sc = re.sub(r"^(?:重返|回到)", "", sc).strip()
    return sc


def start_check(ep, segs, starts):
    for sg_ in segs:
        st = starts.get(sg_["id"])
        if st:
            m = NEG_EN.findall(st[0])
            if m: print(f"  ⚠ {ep} Seg{sg_['id']} 首帧站位英文含否定词 {m}")
        elif sg_.get("cast"):
            print(f"  ⚠ {ep} Seg{sg_['id']} 缺首帧站位（plans/starts.py）：每段单独生成、看不到上一段，要写 0 秒时谁在哪、什么姿势、手里拿什么、机位在哪")


def staging_map_check(ep, segs, staging_map):
    """v2.0 强制站位与子空间映射检查：核对是否声明 STAGING_MAP，并拦截异地子空间复用同一张固定构图场景母图。"""
    if not staging_map:
        print(f"  ⚠ {ep} 未在 plans/{ep.lower()}.py 中传入 staging_map=[...]（建议先声明每场子空间母图、隔断物机位同侧锁与开场站位）")
    by_ref = {}
    for sg_ in segs:
        sref = sg_.get("scene_ref")
        subk = _subspace_key(sg_)
        if sref and subk and not sg_.get("same_room_ok"):
            by_ref.setdefault(sref, {}).setdefault(subk, []).append(f"Seg{sg_['id']}")
    for sref, mp in by_ref.items():
        if len(mp) > 1:
            detail = " / ".join(f"「{k}」({','.join(v)})" for k, v in mp.items())
            msg = f"{ep} [S00 子空间混图] 不同物理子空间共用了同一场景母图 {sref}：{detail}（请拆独立子空间图，确系重返同屋标 same_room_ok=True）"
            ERRS.append(msg); print(f"  ❌ {msg}")


def look_check(sid, shots, summary="", establish=False):
    for k, x in enumerate(shots, 1):
        t = re.sub(r"\{\{d:[^}]*\}\}|\{SAY:[^}]*\}", "", x["en"])
        if SKIN_BAD.search(t): print(f"  ⚠ Seg{sid} 镜{k} 脸/颈/皮肤写了发红（{SKIN_BAD.search(t).group(0).strip()}）：模型会画成皮炎红斑，情绪靠眼神和表情写")
        if re.search(r"\bmole\b", t, re.I) and "rice" not in t.lower(): print(f"  ⚠ Seg{sid} 镜{k} 朱砂痣没写成 one single rice-grain-sized")
        if k > 1 and not PEOPLE.search(t) and re.match(r"the camera (?:opens on|cuts to) an? (?:wide|medium|close-up|high-angle|low-angle|still wide)", t, re.I): print(f"  ⚠ Seg{sid} 镜{k} 镜头里没有人/手：容易被渲染成空场景")
        if re.search(r"\bmole\b", t, re.I) and "flat" not in t.lower(): print(f"  ⚠ Seg{sid} 镜{k} 痣没写 flat")
        if k == 1 and not establish and LOCO.search(t): print(f"  ⚠ Seg{sid} 镜1 首镜里人在走动（{LOCO.search(t).group(0)}）：首镜让人定在上一段结尾的位置，走动放到后面镜头")
        if THRU.search(t) and not DIRWORD.search(t): print(f"  ⚠ Seg{sid} 镜{k} 进出（{THRU.search(t).group(0)}）没写相对机位的方向：写 'away from the camera' / 'toward the camera' / 'seen from behind'")
        if AGENTLESS.search(t): print(f"  ⚠ Seg{sid} 镜{k} 门/车门自己开着或自己打开（{AGENTLESS.search(t).group(0)}）：让开门的人入画")
        if len(MOVES.findall(t)) >= 2: print(f"  ⚠ Seg{sid} 镜{k} 一个镜头里有 {len(MOVES.findall(t))} 个运镜 {MOVES.findall(t)}：一镜只一个运镜")
        if re.search(r"\bwide\b", t, re.I) and CHAOS.search(t): print(f"  ⚠ Seg{sid} 镜{k} 全景里写了群体剧烈动作（{CHAOS.search(t).group(0)}）：全景只让一个人动")
        if CAR.search(t) and not CARCAM.search(t): print(f"  ⚠ Seg{sid} 镜{k} 车内戏没写机位")


PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = []
FULL_SPEED = "All action plays at full real-time speed."
QUIET_SOUND = ("Only a quiet, even room tone and the soft natural sounds of the characters' own visible movements; "
               "each spoken line is clean, dry and close.")
STILL_CORPSE = "completely frozen motionless, zero breathing or swaying"


def sh(dur, sb, en, cn, d=None):
    x = {"dur": dur, "sb": sb, "en": en, "cn": cn}
    if d:
        x["d"] = d
    return x


def lock1(where_en, where_cn, dur=1.0):
    return sh(dur, "静默锁位首秒：全景，站位", f"a silent one-second position-lock frame: every mouth stays closed and the room is silent; {where_en}, the camera steady.",
              f"静默锁位的一秒全景：所有人闭嘴、没有声音；{where_cn}，镜头稳住。")


def relay(en_short, cn_short):
    return sh(1.0, f"承接尾帧 {cn_short}", f"The shot begins from <Picture 1>, {en_short}.", f"承接首帧，{cn_short}。")


def seg(id, scene, ref, light, chain, nxt, cast, count, summary, sound, cn, shots, props=None, wear=None, ff=None, mood=None, extra=None,
        prop_state=None, transition=None, blocking=None, relay_reason=None, seam_motive=None, subspace=None, same_room_ok=False):
    s = {"light": light, "id": id, "scene": scene, "scene_ref": ref, "chain": chain, "next": nxt, "cast": cast}
    if subspace: s["subspace"] = subspace
    if same_room_ok: s["same_room_ok"] = True
    if props: s["props"] = props
    if wear: s["wear"] = wear
    if extra: s["extra"] = extra
    if prop_state: s["prop_state"] = prop_state
    if count: s["count"] = count
    if ff: s["ff_en"], s["ff_cn"] = ff
    s["summary"] = summary; s["sound"] = QUIET_SOUND; s["sound_post"] = sound
    s["cn"] = dict(zip(("kind", "dev", "perf", "sound", "visual"), cn))
    neg_check(id, summary, shots, cn, mood)
    look_check(id, shots, establish=(transition or {}).get("type") in ("establish", "time_cut"))
    defect_check(id, shots, (props or []) + ([ref] if ref else []), cast)
    s["shots"] = shots
    if mood: s["mood"] = list(mood)
    if blocking: s["blocking"] = list(blocking)
    if seam_motive: s["seam_motive"] = seam_motive
    if relay_reason: s["relay_reason"] = relay_reason
    if transition: s["transition"] = transition
    tot = round(sum(x["dur"] for x in shots), 2)
    assert abs(tot - 15.0) < 0.01, f"Seg{id} 镜头总长 {tot}（必须正好 15.0 秒）"
    assert len(shots) <= 6 or os.environ.get("ALLOW_7"), f"Seg{id} 有 {len(shots)} 个镜头：每段 ≤6 个（常规段建议 3–4 个，每镜 2.5–5.0s）"
    t = 0
    for x in shots:
        t += x["dur"]
        if x.get("d") and t > 13.51 and not x.get("_ok"):
            print(f"  ⚠ Seg{id} 台词镜头结束在 {t:.1f}s（>13.5）")
    return s


INDOOR_LIGHT = re.compile(r"\b(windows?|lamps?|tungsten|indoors?|interior|fireplace|chandelier|oak)\b", re.I)


def light_check(ep, segs):
    try:
        lib = os.path.join(PIPE, "library")
        LT = json.load(open(os.path.join(lib, "styles.json"), encoding="utf-8"))
        SC = json.load(open(os.path.join(lib, "scenes.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return
    for sg_ in segs:
        sc = SC.get(sg_.get("scene_ref") or "", {}); lt = LT.get(sg_.get("light") or "", {}).get("en", "")
        if "外/" in sc.get("name_cn", "") and INDOOR_LIGHT.search(lt):
            print(f"⚠️ {ep} Seg{sg_['id']}：室外场景 {sg_['scene_ref']} 配了室内光 {sg_['light']}——换成室外光预设")


def write(ep, title, header, notes, segs, wear=None, per_episode=8, staging_map=None):
    staging_map_check(ep, segs, staging_map)
    if ERRS and not os.environ.get("LINT_OK"):
        raise SystemExit(f"{ep}：{len(ERRS)} 处 ❌（规则见 playbook/04 与 defect_rules.py），plan_src 未写出；确认无误可 LINT_OK=1")
    try:
        import importlib, starts as _st; importlib.reload(_st); ST = _st.STARTS.get(ep, {})
    except ImportError:
        ST = {}
    for sg_ in segs:
        if sg_["id"] in ST: sg_["start"] = list(ST[sg_["id"]])
    start_check(ep, segs, ST)
    light_check(ep, segs)
    d = {"episode": ep, "title": title, "version": "v1", "state_locks": STATE, "header": header, "notes": notes, "segments": segs}
    if staging_map: d["staging_map"] = staging_map
    if wear: d["wear"] = wear
    if len(segs) != per_episode: d["segments_per_episode"] = len(segs)
    os.makedirs(os.path.join(PIPE, "episodes", ep), exist_ok=True)
    p = os.path.join(PIPE, "episodes", ep, "plan_src.json")
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(ep, "写入", len(segs), "段 →", os.path.relpath(p, PIPE))
