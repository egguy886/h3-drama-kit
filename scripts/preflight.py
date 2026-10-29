#!/usr/bin/env python3
"""出片前总预检——把这个项目踩过的坑都变成自动检查（2026-10-29 复盘）。出片 / 开夜班批量前跑一遍：
  python3 tools/preflight.py E15-E20          # 有 ❌ 退出码 1，⚠ 只提示
检查项（括号里是当时踩的坑）：
  1. 资源：磁盘剩余 ≥ 每段 0.15 GB × 待出段数；ComfyUI 面板在线、队列空闲（单卡，别两个任务同时跑）
  2. 参考图：计划里引用的每个 ID（角色/场景/道具）图片都在 assets/ 下；noref=false 的必须有图；assets/ 里不能混进 _rejected（废图会被"取最大文件名"误选）
  3. 资料库字段：cast 要有 look_en/voice_cn/wear_en，scene 要有 layout_cn，prop 要有 en/cn；这些英文里不能有否定词（compose 会 KeyError / build 会 ❌）
  4. 画面里的可读文字：分镜近景提到屏幕/便签/合同/书/牌面且没挂"带文字的道具参考图"（props.json 的 image_text）→ ⚠（不靠后期叠字）
  5. 环境声配方：library/ambience.json 每个滤镜参数合法（tremolo f≥0.1 之类，拼接才不会炸）
  6. 造型一致：剧本"造型"标签 vs 分镜里实际用的造型 ID，不一致的列出来给人确认（剧本写 STU 描写是毛衣牛仔裤）
"""
import argparse, json, os, re, shutil, subprocess, sys, urllib.request

PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEG_EN = re.compile(r"\b(not|no|never|without|nothing|none|cannot)\b|n't", re.I)
TEXT_WORDS = re.compile(r"\b(screen|message|messages|note|sticky|card|contract|page|pages|book|textbook|label|sign|headline|ledger|folder|bill|receipt|letter|paper|poster)\b", re.I)
errs, warns = [], []


def E(m): errs.append(m); print("❌", m)
def W(m): warns.append(m); print("⚠ ", m)


def eps(spec):
    out = []
    for p in spec:
        m = re.fullmatch(r"E(\d+)-E?(\d+)", p.upper())
        out += [f"E{i:02d}" for i in range(int(m.group(1)), int(m.group(2)) + 1)] if m else [p.upper()]
    return out


def load(name):
    return json.load(open(os.path.join(PIPE, "library", name), encoding="utf-8"))


def has_image(i):
    return any(os.path.exists(os.path.join(PIPE, "assets", d, f"{i}{suf}.png")) for d in ("images",) for suf in ("",)) or \
        bool([f for f in os.listdir(os.path.join(PIPE, "assets", "images")) if f.startswith(i + "_v") and f.endswith(".png")])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("episodes", nargs="+"); ap.add_argument("--no-net", action="store_true")
    a = ap.parse_args()
    EPS = eps(a.episodes)
    cast, scenes, props = load("cast.json"), load("scenes.json"), load("props.json")
    # 1 资源
    nseg = 0
    for ep in EPS:
        d = os.path.join(PIPE, "episodes", ep, "05_prompts")
        nseg += len([f for f in os.listdir(d) if f.endswith(".meta.json")]) if os.path.isdir(d) else 0
    free = shutil.disk_usage(PIPE).free / 1e9
    need = nseg * 0.15
    (E if free < need else (W if free < need * 1.5 else print))(f"磁盘剩余 {free:.1f} GB，{nseg} 段约需 {need:.1f} GB") if free < need * 1.5 else print(f"✅ 磁盘剩余 {free:.1f} GB，{nseg} 段约需 {need:.1f} GB")
    if not a.no_net:
        try:
            sys.path.insert(0, os.path.join(PIPE, "tools"))
            import comfy_run as C
            s = C.settings()
            q = C.http("GET", s["base_url"] + "/api/comfy/queue-status", timeout=15)
            print(f"✅ ComfyUI 在线，队列 {'忙' if q.get('busy') else '空闲'}")
            if q.get("busy"): W("ComfyUI 队列有任务在跑：单卡只能串行，别再起第二个出片进程（会互相打断）")
        except SystemExit as e:
            W(f"ComfyUI 未配置：{e}")
        except Exception as e:
            E(f"ComfyUI 面板连不上：{str(e)[:100]}")
    # 2 参考图
    if os.path.isdir(os.path.join(PIPE, "assets", "_rejected")): E("assets/_rejected 在 assets 里面：废图会被资产查找器当成最大文件名误选，搬到 _rejected_refs/")
    for ep in EPS:
        pp = os.path.join(PIPE, "episodes", ep, "plan.json")
        if not os.path.isfile(pp): W(f"{ep} 还没编译（没有 plan.json）"); continue
        plan = json.load(open(pp, encoding="utf-8"))
        used = set()
        for s in plan["segments"]:
            for r in s.get("refs", []):
                if len(r) > 2 and r[2]: used.add(r[2])
        for i in sorted(used):
            lib = cast.get(i) or scenes.get(i) or props.get(i)
            if lib is None: E(f"{ep} 引用了库里没有的 ID：{i}"); continue
            if not has_image(i):
                (W if lib.get("noref") else E)(f"{ep} 参考图缺失：{i}（noref={lib.get('noref')}）")
            elif lib.get("noref"): W(f"{ep} {i} 图已有但库里还是 noref:true，确认后改成 false")
        # 4 可读文字
        for s in plan["segments"]:
            has_text_prop = any(props.get(r[2], {}).get("image_text") for r in s.get("refs", []) if len(r) > 2 and r[2])
            for k, sh in enumerate(s["shots"], 1):
                en = sh["en"]
                if re.search(r"close-up", en, re.I) and TEXT_WORDS.search(en) and not re.search(r"\bblank\b", en, re.I) and not has_text_prop:
                    W(f"{ep} Seg{s['id']} 镜{k}：近景里提到『{TEXT_WORDS.search(en).group(0)}』，若画面要拍清上面的字，请做带文字的道具参考图（props.json image_text），别靠后期叠字")
    # 3 库字段
    for k, v in cast.items():
        if not isinstance(v, dict) or "name" not in v: continue
        for f in ("look_en", "voice_cn", "wear_en"):
            if f not in v and not v.get("noref") is None and f != "look_en": E(f"cast {k} 缺字段 {f}（compose 会 KeyError）") if f == "voice_cn" else None
        for f in ("wear_en", "base_en", "look_en", "keep"):
            if f in v and isinstance(v[f], str) and NEG_EN.search(v[f]): W(f"cast {k}.{f} 含否定词 {NEG_EN.search(v[f]).group(0)}（会进视频提示词，build 报 ❌）")
    for k, v in scenes.items():
        if isinstance(v, dict) and "name_cn" in v and "layout_cn" not in v: E(f"scene {k} 缺 layout_cn")
    for k, v in props.items():
        if isinstance(v, dict) and "name_cn" in v:
            for f in ("en", "cn"):
                if f not in v: E(f"prop {k} 缺 {f}")
            if NEG_EN.search(v.get("en", "")): E(f"prop {k}.en 含否定词 {NEG_EN.search(v['en']).group(0)}（精确文字只放 image_text，别放 en）")
    # 5 环境声配方
    ap_ = os.path.join(PIPE, "library", "ambience.json")
    if os.path.isfile(ap_):
        def walk(o, path=""):
            if isinstance(o, dict):
                for kk, vv in o.items(): walk(vv, f"{path}.{kk}")
            elif isinstance(o, list) and path.endswith(".trem") and o and o[0] < 0.1:
                W(f"ambience{path} 的 tremolo 频率 {o[0]} < 0.1（ffmpeg 下限；assemble 已钳位，但配方最好改正）")
        walk(json.load(open(ap_, encoding="utf-8")))
    # 6 造型一致
    for ep in EPS:
        sd = [f for f in os.listdir(os.path.join(PIPE, "scripts_fixed")) if f.startswith(ep + "_")] if os.path.isdir(os.path.join(PIPE, "scripts_fixed")) else []
        pp = os.path.join(PIPE, "episodes", ep, "plan.json")
        if not sd or not os.path.isfile(pp): continue
        tags = set(re.findall(r"(?:Wren|Lucien|Owen|Tyler|Beckett|Sloane)=(C\d\d-[A-Z\-]+)", open(os.path.join(PIPE, "scripts_fixed", sd[0]), encoding="utf-8").read()))
        plan = json.load(open(pp, encoding="utf-8"))
        usedc = {r[2] for s in plan["segments"] for r in s.get("refs", []) if len(r) > 2 and r[2] and r[2].startswith("C")}
        miss = tags - usedc
        if miss: W(f"{ep} 剧本造型标签 {sorted(miss)} 分镜里没用到（实际用 {sorted(usedc)}）——确认是有意改的（以描写为准）")
    print(f"\n预检完成：❌ {len(errs)}  ⚠ {len(warns)}")
    sys.exit(1 if errs else 0)
