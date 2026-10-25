"""plan_src 写作助手：只负责固定格式，镜头内容逐条手写（写法见工具包 playbook/04_分镜与提示词.md）。

每集一个脚本 plans/eNN.py：
    from pw import *
    S = []
    S.append(seg(1, "场01 …", "N-ROOFTOP", "night_neon", "A", "HARD_CUT", ["C01", "C02"], None, summary, sound, cn, [sh(...), ...], blocking=..., seam_motive="gaze"))
    write("E01", "标题", header=[], notes=[], segs=S)
然后：python3 plans/e01.py && python3 tools/compose_plan.py E01 && python3 tools/build_episode.py episodes/E01 --voices voices.json
"""
import json, os

PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # 项目根（plans/ 的上一级）

# 状态锁：剧情里某个资产状态变了（手环被剪、换装、受伤），之后的段只能用新参考，并禁止旧描述出现。
# 例：{"from_seg": 1, "ref_old": "C01", "ref_new": "C01-NOBAND", "forbid_en": ["band on his left wrist"], "why": "E01 手环被剪"}
STATE = []

FULL_SPEED = "All action plays at full real-time speed."


def sh(dur, sb, en, cn, d=None):
    """一个镜头：dur 秒；sb 中文分镜名；en 英文镜头文字（不写 [Shot N]/At 00:0x，生成器自动加）；cn 中文对照；d 本镜台词 ID（如 "L3"）。
    en 里可用：{C01} → <Subject N>；{SAY:C01} → 说话句头（含声线）；{{d:L3}} → 台词原文；{ACT:名字:键} → 表演习惯。"""
    x = {"dur": dur, "sb": sb, "en": en, "cn": cn}
    if d:
        x["d"] = d
    return x


def lock1(where_en, where_cn, dur=1.0):
    """静默锁位首秒（多人同场静态戏的第一镜；RH 实测人物一开始不说话时 7/7 得到 1 秒站位全景再硬切）。
    where_en 写每个人的位置，例如 "Reeve stands over the bound Julian, Cade is crouched at frame-left and Nia stands by the car at the far end"。"""
    return sh(dur, "静默锁位首秒：全景，站位", f"a silent one-second position-lock frame: every mouth stays closed and the room is silent; {where_en}, the camera steady.",
              f"静默锁位的一秒全景：所有人闭嘴、没有声音；{where_cn}，镜头稳住。")


def relay(en_short, cn_short):
    """尾帧接力首镜（只在必须一镜连续时用，并在 seg() 里写 relay_reason）。"""
    return sh(1.0, f"承接尾帧 {cn_short}", f"The shot begins from <Picture 1>, {en_short}.", f"承接首帧，{cn_short}。")


def seg(id, scene, ref, light, chain, nxt, cast, count, summary, sound, cn, shots, props=None, wear=None, ff=None, mood=None, extra=None,
        prop_state=None, transition=None, blocking=None, relay_reason=None, seam_motive=None):
    """一段 15 秒。
    nxt：HARD_CUT（默认，同场景也硬切换景别）/ TAIL_RELAY（尾帧接力，必须写 relay_reason）/ "（集尾）"。
    count：人数句，None 时自动生成 "Exactly N people appear in this video: …"；有群众时手写。
    cn：(kind, dev, perf, sound, visual) 五项中文说明（只给人看，不上传）。
    blocking：(en, cn) 站位卡——只写整段都不动的东西和人；会移动的人写进镜头，否则同一个人会出现两次。
    seam_motive：同场景硬切缝的动机 action / gaze / sound（写在缝前那一段），缺了 shot_lint ❌。"""
    s = {"light": light, "id": id, "scene": scene, "scene_ref": ref, "chain": chain, "next": nxt, "cast": cast}
    if props: s["props"] = props
    if wear: s["wear"] = wear
    if extra: s["extra"] = extra
    if prop_state: s["prop_state"] = prop_state
    if count: s["count"] = count
    if ff: s["ff_en"], s["ff_cn"] = ff
    s["summary"] = summary; s["sound"] = sound
    s["cn"] = dict(zip(("kind", "dev", "perf", "sound", "visual"), cn))
    s["shots"] = shots
    if mood: s["mood"] = list(mood)
    if blocking: s["blocking"] = list(blocking)
    if seam_motive: s["seam_motive"] = seam_motive
    if relay_reason: s["relay_reason"] = relay_reason
    if transition: s["transition"] = transition          # 换场缝设计：{"type": "cut" / "match_cut" / "foreground_wipe" …, "note": "…"}
    tot = round(sum(x["dur"] for x in shots), 2)
    assert abs(tot - 15.0) < 0.01, f"Seg{id} 镜头总长 {tot}（必须正好 15.0 秒）"
    assert len(shots) <= 6 or os.environ.get("ALLOW_7"), f"Seg{id} 有 {len(shots)} 个镜头：每段 ≤6 个（7 个起切点命中率下降）"
    t = 0
    for x in shots:                                   # 台词留余量：最后一句在 13.5 s 前说完（接缝要用最后 1 秒）
        t += x["dur"]
        if x.get("d") and t > 13.51 and not x.get("_ok"):
            print(f"  ⚠ Seg{id} 台词镜头结束在 {t:.1f}s（>13.5）")
    return s


def write(ep, title, header, notes, segs, wear=None, per_episode=8):
    d = {"episode": ep, "title": title, "version": "v1", "state_locks": STATE, "header": header, "notes": notes, "segments": segs}
    if wear: d["wear"] = wear
    if len(segs) != per_episode: d["segments_per_episode"] = len(segs)   # 台词过密时放宽段数（先和制片人确认）
    os.makedirs(os.path.join(PIPE, "episodes", ep), exist_ok=True)
    p = os.path.join(PIPE, "episodes", ep, "plan_src.json")
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(ep, "写入", len(segs), "段 →", os.path.relpath(p, PIPE))
