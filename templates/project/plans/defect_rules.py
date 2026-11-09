"""画面缺陷写作规则（编译前拦截）。每条规则编号见 plans/lessons.md / lessons.json；pw.seg() 调用 defect_check。
LEVEL：每条规则的级别。项目里按 lessons.json 的状态；同步进 skill 时由 plans/skill_sync.py 改写——已验证的保留 ❌，未验证的降为 ⚠。"""
import json, os, re
PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEVEL = {"L01": "err", "L02": "warn", "L03": "warn", "L04": "off", "L05": "warn", "L06": "warn", "L07": "warn", "L08": "warn", "L10": "warn", "L11": "warn", "L12": "warn", "L13": "warn", "H01": "warn"}   # SKILL_SYNC_LEVEL


# ---- 看片意见 1（2026-11-09，E02–E17 共 40 条，报告 review/问题核实_看片意见1.md）落成的机器规则 ----
# ❌ = 编译拦下（plan_src 不写出；确认无误可 LINT_OK=1 放行）；⚠ = 提示。每条规则编号对应 plans/lessons.md。
ERRS = []
_BLUSH_OK = re.compile(r"a shade pinker|faint warm pink", re.I)
R = {
 "L01": re.compile(r"\b(?:ears?|neck|throat|collarbone|cheeks?|face|skin|hairline)\b[^.;]{0,40}\b(?:red|reddens?|reddening|crimson|scarlet|flush\w*|blush\w*|burn\w*)\b"
                   r"|\b(?:red|crimson|scarlet|flush\w*|blush\w*)\b[^.;]{0,30}\b(?:ears?|neck|throat|collarbone|cheeks?|hairline)\b", re.I),
 "L02": re.compile(r"\bthe sound of\b|\bknock(?:s|ing)? (?:on|at)\b|\bbang(?:s|ing)? on\b|\bpounding on\b|\bis heard\b|\brings? out\b|\bdoorbell\b|\bhammering on\b", re.I),
 "L03": re.compile(r"\beyes?\b[^.;]{0,30}\b(?:brighten\w*|lights? up|lit up|glow\w*|gleam\w*|shin(?:e|es|ing)|sparkl\w*|spark)\b|\b(?:light|spark|gleam|glint|fire)\s+in\s+(?:his|her|their)\s+eyes\b", re.I),
 "L04": re.compile(r"\b(?:hickey|love bite|kiss mark|bite marks?|teeth marks?|tooth marks?|scratch(?:es|ed|marks?)?|welts?|claw marks?|bruis\w*)\b", re.I),
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
    has_mark = any(str(p).startswith("T-MARK") for p in props)
    has_text = any(str(p).startswith(("T-", "K-")) for p in props)
    wear = ""
    try:
        CAST = json.load(open(os.path.join(PIPE, "library", "cast.json"), encoding="utf-8"))
        wear = " ".join(CAST.get(c, {}).get("wear_en", "") for c in (cast or []))
    except (OSError, ValueError):
        pass
    for k, x in enumerate(shots, 1):
        t = re.sub(r"\{\{d:[^}]*\}\}|\{SAY:[^}]*\}", "", x["en"])
        m = R["L01"].search(t)
        if m and not _BLUSH_OK.search(t): err("L01", k, f"皮肤发红写法「{m.group(0)}」：模型会画成饱和红/烫伤（E08/E15/E17）。写 'a faint warm pink, only a shade pinker than the surrounding skin'，或干脆用表情写情绪")
        m = R["L02"].search(t)
        if m: err("L02", k, f"声音写进了画面「{m.group(0)}」：模型会让画面里的人去制造这个声音（E02 Julian 自己敲门）。画面只写看得到的反应，声音后期配")
        m = R["L03"].search(t)
        if m and " on the " not in m.group(0): err("L03", k, f"眼睛发光写法「{m.group(0)}」：会画出火苗/发光眼（E10 杯子着火）。写 'the corners of his eyes crinkle'")
        m = R["L04"].search(t)
        if m and not has_mark: err("L04", k, f"身体痕迹「{m.group(0)}」没有挂 T-MARK-* 参考图：会画成伤口/缝合线/溃烂（E03/E10/E11）")
        if R["L05"].search(t) and re.search(r"\b(?:lobby|elevator|hall|office|inside|indoors|room|corridor|turnstiles?)\b", re.sub(r"\{[^}]*\}", "", t), re.I) and not re.search(r"\b(?:closed|folded|furled)\b", t, re.I): err("L05", k, "室内雨伞没写 closed/folded：会全部撑开（E03 大堂）")
        m = R["L06k"].search(t)
        if m: err("L06", k, f"键盘/打字特写「{m.group(0)}」：键帽和输入框的字会是乱码（E06）。拍拇指和屏幕边缘、或拍脸")
        m = R["L06g"].search(t)
        if m: err("L06", k, f"镜片上写字/数字「{m.group(0)}」：会被画成手写在镜片上（E14）。镜片只写 'cool screen light on her lenses'")
        if R["L06s"].search(t) and not has_text: warn("L06", k, f"屏幕/告示上要有字「{R['L06s'].search(t).group(0)}」但本段没挂 T-/K- 带字参考图：字会是乱码")
        if R["L07z"].search(t) and not R["L07zs"].search(t): err("L07", k, "拉链没写当前状态（closed / open to mid-back / pulled down）：模型会自己定开合方向（E02 拉上拉链）")
        if R["L07rp"].search(t): err("L07", k, "戒指和吊坠写在同一个镜头：戒指会被画成第二条吊坠（E02 2:25）。拆两镜")
        acts = {w.lower() for w in R["L08"].findall(t)}
        if len(acts) >= 3: warn("L08", k, f"一镜里动作太多 {sorted(acts)}：模型会摆姿势、不真实（E03 滑倒）。一镜一个动作")
        m = R["L09"].search(t)
        if m: warn("L09", k, f"品牌/标志「{m.group(0)}」：会出现真实商标或串到别的道具上（E07 刀刃上的 Columbia、E08 马标）")
        if R["L10"].search(t) and re.search(r"\b(?:stands?|standing|alone)\b", t, re.I): warn("L10", k, "同一镜写了楼梯/通道和终点位置：模型会把'走上来的她'和'站着的她'画在同一画面（E10 两个女主）")
        if R["L11"].search(t) and not R["L11ok"].search(t): warn("L11", k, "笔记本没写机位朝向：屏幕会朝向镜头、键盘朝向人（E05 反的笔记本）。写 'seen over her shoulder' 或只拍屏幕光照在脸上")
        if R["L13"].search(t): err("L13", k, "画面倒置：模型会把整个画面旋转 180°（E15）。摄影机正放，写人的头倒挂")
        for g in {g.lower() for g in GARMENTS.findall(t)}:
            if wear and g.split()[-1] not in wear.lower(): warn("L12", k, f"镜头里写了「{g}」，但本段人物造型是：{wear[:80]}…（E10 白衬衫/西装来回变）")
