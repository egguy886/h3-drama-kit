"""画面缺陷与空间防穿帮写作规则 v2.1（编译前拦截：含单镜单形态 S04 与感官外化 S05）。pw.seg() 调用 defect_check。"""
import json, os, re
PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEVEL = {
    "L01": "err", "L02": "warn", "L03": "warn", "L04": "off", "L05": "warn",
    "L06": "warn", "L07": "err", "L08": "warn", "L10": "warn", "L11": "warn",
    "L12": "warn", "L13": "warn", "H01": "warn", "L04b": "err", "H02": "warn",
    "L14": "err", "W2": "warn", "W3": "warn",
    "S01": "err", "S02": "err", "S03": "err", "S04": "err", "S05": "warn",
}  # SKILL_SYNC_LEVEL

ERRS = []
_BLUSH_OK = re.compile(r"a shade pinker|faint warm pink", re.I)
_HIT_OK = re.compile(r"\b(punch\w*|strik\w*|kick\w*|slam\w*|smash\w*|tackl\w*|elbow\w*|headbutt\w*|throws? (?:him|her)|hurl\w*|swings?|sweeps? .* upward|drives? (?:her|his) knee|crash\w* (?:into|through)|lunges?)\b", re.I)
_LOCK_OR_RELAY = re.compile(r"silent one-second position-lock|position-lock frame|^The shot begins from <Picture 1>", re.I)
_STILL_LOCK = re.compile(r"completely frozen motionless,\s*zero breathing or swaying", re.I)

R = {
 "L01": re.compile(r"\b(?:ears?|neck|throat|collarbone|cheeks?|face|skin|hairline)\b[^.;]{0,40}\b(?:red|reddens?|reddening|crimson|scarlet|flush\w*|blush\w*|burn\w*)\b"
                   r"|\b(?:red|crimson|scarlet|flush\w*|blush\w*)\b[^.;]{0,30}\b(?:ears?|neck|throat|collarbone|cheeks?|hairline)\b", re.I),
 "L02": re.compile(r"\bthe sound of\b|\bknock(?:s|ing)? (?:on|at)\b|\bbang(?:s|ing)? on\b|\bpounding on\b|\bis heard\b|\brings? out\b|\bdoorbell\b|\bhammering on\b", re.I),
 "L03": re.compile(r"\beyes?\b[^.;]{0,30}\b(?:brighten\w*|lights? up|lit up|glow\w*|gleam\w*|shin(?:e|es|ing)|sparkl\w*|spark)\b|\b(?:light|spark|gleam|glint|fire)\s+in\s+(?:his|her|their)\s+eyes\b", re.I),
 "L04": re.compile(r"\b(?:flushed marks?|red marks?|marks? (?:on|at|down|above|under) (?:the |his |her )?(?:neck|jaw|throat|collar)|hickey|love bite|kiss mark|bite marks?|teeth marks?|tooth marks?|scratch(?:es|ed|marks?)?|welts?|claw marks?|bruis\w*)\b", re.I),
 "L05": re.compile(r"\bumbrellas?\b", re.I),
 "L06k": re.compile(r"\bkeyboard\b|\bkeys? (?:of|on) (?:the|a|her|his) (?:phone|laptop)\b|\bthumbs? (?:type|types|typing) on\b", re.I),
 "L06g": re.compile(r"\b(?:lens|lenses|glasses)\b[^.;]{0,50}\b(?:numbers?|digits?|figures?|text|letters?|words?)\b", re.I),
 "L06s": re.compile(r"\b(?:phone|laptop|monitor|tablet) screen\b|\btext message\b|\bmessage bubble\b|\bnotice\b|\binspection (?:tag|label)\b|\bspreadsheet\b", re.I),
 "L07z": re.compile(r"\bzip(?:per)?\b", re.I),
 "L07zs": re.compile(r"\b(?:closed|open|opened|half|down|up)\b", re.I),
 "L07rp": re.compile(r"\bring\b[^.]*\bpendant\b|\bpendant\b[^.]*\bring\b", re.I),
 "L08": re.compile(r"\b(?:slips?|slides?|trips?|falls?|lunges?|stumbles?|flies|fly|scatters?|catch(?:es)?|spins?|throws?|kicks?|flings?)\b", re.I),
 "L09": re.compile(r"\b(?:Ferrari|prancing horse|horse emblem|horse logo|logo|emblem|Columbia)\b", re.I),
 "L10": re.compile(r"\b(?:top|end|head) of the (?:iron |metal |fire )?(?:stairs?|staircase|steps)\b", re.I),
 "L11": re.compile(r"\blaptop\b", re.I),
 "L11ok": re.compile(r"from behind|over (?:her|his) shoulder|\blid\b|back of the laptop|screen glow on (?:her|his) face|faces away from the camera", re.I),
 "L13": re.compile(r"\bupside[- ]down\b|\binverted\b", re.I),
 "L14": re.compile(r"\b(?:face|lips?|mouth|skin|palms?|cheeks?)\b[^.;,]{0,30}\b(?:white|gray|grey|pale|ashen|colou?rless|blanch\w*|red lines?)\b"
                   r"|\b(?:go(?:es|ing)?|gone|turn(?:s|ing|ed)?) (?:white|gray|grey|pale|ashen) in the face\b|\bcolou?r (?:drain\w*|leav\w*) (?:from|out of) (?:his|her|their) face\b|\bdrained of colou?r\b", re.I),
 # v2.0 新增空间与状态防穿帮硬拦截
 "S01p": re.compile(r"\b(?:two|three|four|several|multiple)\s+(?:tall\s+|dark\s+|hooded\s+|black-clad\s+|shadowy\s+|hulking\s+|coarse-robed\s+)*(?:silhouettes?|figures?|human shadows?|strangers?|intruders?|guards?|bandits?|men)\b", re.I),
 "S01s": re.compile(r"\b(?:a|one|another)\s+(?:tall\s+|dark\s+|hooded\s+|black-clad\s+|shadowy\s+|mysterious\s+)+(?:silhouette|figure|stranger|intruder|black-clad man)\b", re.I),
 "S02e": re.compile(r"\b(?:headless(?:\s+[\w-]+){0,2}\s+(?:figures?|bodies|corpses?|bandits?|men|guards?|trunks?)|corpses?|dead\s+bod(?:y|ies)|lifeless\s+bod(?:y|ies)|feigning\s+(?:sleep|death|unconsciousness)|playing\s+dead)\b", re.I),
 "S02c": re.compile(r"(?:无头(?:尸|躯干|矿匪)|死尸|尸体|装昏|装睡|假寐)"),
 "S04w": re.compile(r"\b(?:suspended|hoisted|hanging|mid-air)\b[^.]{0,55}\b(?:net|bundle|sack)\b|\b(?:net|bundle|sack)\b[^.]{0,40}\b(?:suspended|hoisted|over the rail)\b", re.I),
 "S04o": re.compile(r"\b(?:drops? open|falls? open|spills? open|unfolds?|opens?)\b[^.]{0,65}\brevealing\b", re.I),
 "S05e": re.compile(r"\b(?:closed eyes|eyes closed)\b[^.]{0,80}\b(?:inhal\w*|smell\w*|scent|sniff\w*|listen\w*)|\b(?:inhal\w*|smell\w*|scent|sniff\w*)\b[^.]{0,80}\b(?:closed eyes|eyes closed)\b", re.I),
 "S05ok": re.compile(r"\b(?:fingertips?|two fingers|index finger|scrapes?|wipes?|dabs?|pinches?|brings? [^.]{0,25}to (?:her|his) (?:nose|nostrils))\b", re.I),
}
GARMENTS = re.compile(r"\b(white (?:dress )?shirt|navy suit|dark suit|suit jacket|T-shirt|t-shirt|tank top|sweater|sweatshirt|hoodie|turtleneck|pajamas|robe|dress|blazer|cardigan)\b", re.I)


def defect_check(sid, shots, props, cast):
    def err(code, k, msg):
        if LEVEL.get(code) == "off": return
        if LEVEL.get(code) != "err": return warn(code, k, msg)
        ERRS.append(f"Seg{sid} 镜{k} [{code}] {msg}"); print(f"  ❌ Seg{sid} 镜{k} [{code}] {msg}")
    def warn(code, k, msg):
        if LEVEL.get(code) == "off": return
        print(f"  ⚠ Seg{sid} 镜{k} [{code}] {msg}")
    props = props or []
    n_cast = len(cast or [])
    has_mark = any(str(p).startswith(("T-MARK", "T-FACE")) for p in props)
    has_text = any(str(p).startswith(("T-", "K-")) for p in props)
    wear = ""
    try:
        CAST = json.load(open(os.path.join(PIPE, "library", "cast.json"), encoding="utf-8"))
        wear = " ".join(CAST.get(c, {}).get("wear_en", "") for c in (cast or []))
    except (OSError, ValueError):
        pass
    for k, x in enumerate(shots, 1):
        t = re.sub(r"\{\{d:[^}]*\}\}|\{SAY:[^}]*\}", "", x["en"])
        c_txt = re.sub(r"\{\{q:[^}]*\}\}|[“\"].*?[”\"]", "", x.get("cn", ""))
        dur = float(x.get("dur", 0))
        m = R["L01"].search(t)
        if m and not _BLUSH_OK.search(t): err("L01", k, f"皮肤发红写法「{m.group(0)}」：写 'a faint warm pink' 或用眼神表情写情绪")
        m = R["L14"].search(t)
        if m: err("L14", k, f"皮肤/嘴唇变色写法「{m.group(0)}」：改写成动作和表情")
        m = R["L02"].search(t)
        if m: err("L02", k, f"声音写进了画面「{m.group(0)}」：画面只写看得到的反应，声音后期配")
        m = R["L03"].search(t)
        if m and " on the " not in m.group(0): err("L03", k, f"眼睛发光写法「{m.group(0)}」：写 'the corners of his eyes crinkle'")
        m = R["L04"].search(t)
        if m and not has_mark: err("L04", k, f"身体痕迹「{m.group(0)}」没有挂 T-MARK-* 微距参考图")
        if m and has_mark and not re.search(r"\bmacro\b|extreme close-up", t, re.I): warn("L04", k, f"痕迹「{m.group(0)}」出现在非微距镜头")
        if R["L05"].search(t) and re.search(r"\b(?:lobby|elevator|hall|office|inside|indoors|room|corridor|turnstiles?)\b", re.sub(r"\{[^}]*\}", "", t), re.I) and not re.search(r"\b(?:closed|folded|furled)\b", t, re.I): err("L05", k, "室内雨伞没写 closed/folded")
        m = R["L06k"].search(t)
        if m: err("L06", k, f"键盘/打字特写「{m.group(0)}」：拍拇指和屏幕边缘、或拍脸")
        m = R["L06g"].search(t)
        if m: err("L06", k, f"镜片上写字/数字「{m.group(0)}」：镜片只写反光")
        if R["L06s"].search(t) and not has_text: warn("L06", k, f"屏幕/告示上要有字「{R['L06s'].search(t).group(0)}」但没挂 T-/K- 带字参考图")
        if R["L07z"].search(t) and not R["L07zs"].search(t): err("L07", k, "拉链没写当前状态")
        if R["L07rp"].search(t): err("L07", k, "戒指和吊坠写在同一个镜头：拆两镜")
        acts = {w.lower() for w in R["L08"].findall(t)}
        if len(acts) >= 3: warn("L08", k, f"一镜里动作太多 {sorted(acts)}：一镜一个动作")
        m = R["L09"].search(t)
        if m: warn("L09", k, f"品牌/标志「{m.group(0)}」")
        if R["L10"].search(t) and re.search(r"\b(?:stands?|standing|alone)\b", t, re.I): warn("L10", k, "同一镜写了楼梯/通道和终点位置")
        if R["L11"].search(t) and not R["L11ok"].search(t): warn("L11", k, "笔记本没写机位朝向")
        if R["L13"].search(t): err("L13", k, "画面倒置：摄影机正放，写人的头倒挂")
        for g in {g.lower() for g in GARMENTS.findall(t)}:
            if wear and g.split()[-1] not in wear.lower(): warn("L12", k, f"镜头里写了「{g}」，但本段人物造型是：{wear[:80]}…")
        # v2.0 S01: 未挂母图禁写人影
        mp = R["S01p"].search(t)
        if mp and n_cast <= 1 and "headless" not in mp.group(0).lower():
            err("S01", k, f"本段仅挂载 {n_cast} 名角色，却写了多人影/人物「{mp.group(0)}」（H3 会凭空造黑衣人；挂角色母图或改纯光影扫墙）")
        ms = R["S01s"].search(t)
        if ms and (n_cast == 0 or (n_cast == 1 and re.search(r"\b(?:stranger|intruder|black-clad|hooded)\b", ms.group(0), re.I))):
            err("S01", k, f"写了未挂载的陌生黑衣人影「{ms.group(0)}」")
        # v2.0 S02: 尸体/无头躯干/装昏静止死锁
        if (R["S02e"].search(t) or R["S02c"].search(c_txt)) and not _STILL_LOCK.search(t):
            err("S02", k, "含尸体/无头躯干/装昏状态，英文必须显式写死 'completely frozen motionless, zero breathing or swaying'")
        # v2.0 S03: 常规镜 <2.0s 碎切拦截
        if not _LOCK_OR_RELAY.search(t) and not _HIT_OK.search(t) and dur < 2.0 - 1e-6:
            err("S03", k, f"常规叙事/动作镜仅 {dur}s（<2.0s），动作来不及演完即切；请合并或拉长至 2.5–5.0s")
        # v2.1 S04: 单镜跨拓扑形态硬变拦截（悬空闭网兜→掉落散开露活人）
        if R["S04w"].search(t) and R["S04o"].search(t):
            err("S04", k, "同一镜既悬空吊着闭合网兜/包裹又直接散开露人体，模型会在半空提前长出双腿变形；请配 P-NET-BUNDLE 拆为闭合砸水遮挡切 + 下一镜已摊开挑网揭示")
        # v2.1 S05: 活人无媒介闭眼闻香/听风谜语人告警
        if not R["S02e"].search(t) and "unconscious" not in t.lower() and R["S05e"].search(t) and not R["S05ok"].search(t):
            warn("S05", k, "活人无物理媒介原地闭眼闻香/听风易像犯困发呆；请改为睁眼警觉 + 手指刮缆绳水渍/捻物凑鼻等可见物理媒介")
