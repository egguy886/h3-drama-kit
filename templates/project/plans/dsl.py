"""分镜速写助手（E41 起用）：把"镜头句式""段落包装"写成函数，只留每个镜头的画面和台词。
  dl(dur, 说话人ID, 'L3', 画面en, 画面cn, 语气en, 语气cn)       # 台词镜头（近景）
  sd(dur, 景别, 画面en, 画面cn)                                   # 无台词镜头；景别 'wide shot' 'medium shot' 'close-up' 'extreme close-up' ...
  sg(id, 标题, 场景ID, 风格, [角色ID], 人数句, 总述en, 音效en, 总述cn, 一句钩子, 声音cn, 关键画面cn, [镜头], props=, nxt=, end=True)
镜头 en 句式固定：第一镜 "the camera opens on …"，其余 "the camera cuts to …"；台词 "{SAY:ID} 语气, says: {{d:Lk}}"。"""
from pw import *

KC = {"extreme close-up": "极特写", "medium close-up": "近景", "close-up": "近景", "medium shot": "中景", "wide shot": "全景",
      "high-angle shot": "俯拍", "over-the-shoulder shot": "过肩", "low-angle shot": "仰拍", "tracking shot": "跟拍", "overhead shot": "俯拍"}


def _kc(kind):
    for k in sorted(KC, key=len, reverse=True):
        if kind.startswith(k): return KC[k]
    return "近景"


def _a(kind): return "an" if kind[0] in "aeiou" else "a"


def sd(dur, kind, en, cn, kc=None):
    kc = kc or _kc(kind)
    e = f"the camera cuts to {_a(kind)} {kind} of {en}."
    c = f"{kc}：{cn}。"
    return sh(dur, c, e, c)


def dl(dur, cid, L, en, cn, tone_en, tone_cn, kind="close-up", kc=None, name=""):
    kc = kc or _kc(kind)
    e = f"the camera cuts to {_a(kind)} {kind} of {en}. {{SAY:{cid}}} {tone_en}, says: {{{{d:{L}}}}}"
    c = f"{kc}：{cn}，{tone_cn}地说：{{{{q:{L}}}}}"
    return sh(dur, f"{name}{kc}：{cn}，说 {L}", e, c, L)


def sg(i, head, scene, style, cast, cl, en, snd, cn, hook, sndcn, key, shots, props=None, nxt="HARD_CUT", end=False,
       blocking=None, mood=None, seam="gaze", trans=None, typ="对白段。"):
    for k, x in enumerate(shots):
        if k == 0: x["en"] = x["en"].replace("the camera cuts to", "the camera opens on", 1)
    a = dict(props=props or [], blocking=blocking, mood=mood)
    if not end:
        a["seam_motive"] = seam
        a["transition"] = trans if isinstance(trans, dict) else {"type": "cut", "note": trans or "接下一段"}
    return seg(i, head, scene, style, "A", "（集尾）" if end else nxt, cast, cl, en, snd, (typ, cn, hook, sndcn, key), shots, **a)
