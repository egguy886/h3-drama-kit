#!/usr/bin/env python3
"""新建一部剧的项目目录（从工具包模板复制；不会覆盖已有文件）。

用法：
  python3 <工具包>/scripts/new_project.py <项目目录> --title-en "Night Shift" --title-cn "夜班" \
          [--aspect 9:16] [--genre-cn "写实电影感出海都市悬疑短剧，英文对白"] [--no-example]

建好后的目录：
  tools/        全部工具（从工具包 scripts/ 复制，可以随项目改）
  library/      角色/场景/道具/光色/表演/环境声/运镜词库（示例条目，换成本剧的）
  scripts_fixed/ 修订后的剧本（每集一个 .md）
  plans/        每集一个 eNN.py（写分镜的唯一地方）+ pw.py 写作助手
  episodes/Exx/ 生成物：台词锁定、plan.json、提示词、出片、剪辑
  assets/       参考图（images/）与参考音频（voices/），文件名以资产 ID 开头
  project.json  剧名、画幅、类型、出片规格
"""
import argparse, json, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__)); KIT = os.path.dirname(HERE)
TPL = os.path.join(KIT, "templates", "project")

ap = argparse.ArgumentParser()
ap.add_argument("dest")
ap.add_argument("--title-en", required=True); ap.add_argument("--title-cn", default="")
ap.add_argument("--aspect", default="9:16", choices=["9:16", "16:9", "1:1"])
ap.add_argument("--genre-cn", default="写实电影感出海短剧，英文对白")
ap.add_argument("--no-example", action="store_true", help="不带 E01 示例（剧本、分镜、示例角色）")
a = ap.parse_args()
dest = os.path.abspath(a.dest)
os.makedirs(dest, exist_ok=True)
copied, kept = 0, 0


def put(src, dst):
    global copied, kept
    if os.path.exists(dst):
        kept += 1; return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst); copied += 1


for root, dirs, files in os.walk(TPL):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    rel = os.path.relpath(root, TPL)
    os.makedirs(os.path.join(dest, rel), exist_ok=True)
    for f in files:
        if a.no_example and (f in ("E01_示例.md", "e01.py")):
            continue
        put(os.path.join(root, f), os.path.join(dest, rel, f))
for root, dirs, files in os.walk(os.path.join(KIT, "scripts")):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", ".venv", "seed-vc")]
    rel = os.path.relpath(root, os.path.join(KIT, "scripts"))
    for f in files:
        if f.endswith((".py", ".swift", ".sh")):
            put(os.path.join(root, f), os.path.join(dest, "tools", rel, f))

pj = os.path.join(dest, "project.json")
p = json.load(open(pj, encoding="utf-8"))
if p.get("series_title_en") in ("Night Shift", None) or not os.path.exists(os.path.join(dest, ".initialized")):
    p.update({"series_title_en": a.title_en, "series_title_cn": a.title_cn or a.title_en, "aspect": a.aspect, "genre_cn": a.genre_cn})
    json.dump(p, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
if a.aspect != "9:16":                                  # 光色风格句里的画幅
    sp = os.path.join(dest, "library", "styles.json")
    st = json.load(open(sp, encoding="utf-8"))
    for v in st.values():
        if isinstance(v, dict) and "en" in v:
            v["en"] = v["en"].replace("vertical short drama (9:16)", f"short drama ({a.aspect})")
    json.dump(st, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

docs = {
 "CLAUDE.md": f"""# {a.title_cn or a.title_en}（{a.title_en}）· H3 短剧项目

用 Claude 的 skill `h3-drama-kit`（工具包：{KIT}）。先读本目录 `STATUS.md`（进度与待办）和 `decisions.md`（已定的决定），流程与写法见工具包 `playbook/`。

硬规则：
- 付费出片（AutoDL）前先报 任务数 × 分辨率 × 时长 × 预估费用，等制片人明确同意。
- 令牌只在 `.env`（AUTODL_TOKEN），绝不读出、打印或写进任何文件。
- 英文台词逐字不改；中文潜台词只给人看，绝不进提示词。
- 改分镜只改 `plans/eNN.py`，再跑 compose → build；不要手改 `05_prompts/` 下的文件。
- 出问题回到最早出错的一层修（参考图 → 镜头设计 → 提示词 → 单段重出），一次只改一处。
""",
 "STATUS.md": f"""# {a.title_cn or a.title_en} · 进度

| 集 | 剧本 | 台词锁定 | 资产 | 分镜 | build/lint | 出片 | 看片 | 后期 | 交付 |
|---|---|---|---|---|---|---|---|---|---|
| E01 | | | | | | | | | |

## 待办
- [ ] S0 立项：画幅 {a.aspect}、语言、每集段数、平台交付标准（delivery.json）
- [ ] S1 剧本审计 → scripts_fixed/

## 资产缺口
（`python3 tools/asset_gaps.py` 生成 assets/00_资产清单与缺口.md）
""",
 "decisions.md": "# 已定的决定（日期｜决定｜理由｜谁定的）\n\n",
}
for name, text in docs.items():
    fp = os.path.join(dest, name)
    if not os.path.exists(fp):
        open(fp, "w", encoding="utf-8").write(text); copied += 1
gi = os.path.join(dest, ".gitignore")
if not os.path.exists(gi):
    open(gi, "w").write(".env\n*.mp4\n*.wav\n__pycache__/\ntools/voiceconv/.venv/\ntools/voiceconv/seed-vc/\nmodels/\n")
open(os.path.join(dest, ".initialized"), "w").write("h3-drama-kit\n")
print(f"项目已就绪：{dest}（新建 {copied} 个文件，已存在跳过 {kept} 个）")
print("下一步：cd 进去 → python3 tools/kit_doctor.py → 按 playbook/00_全流程总览.md 走" + ("" if a.no_example else "（E01 示例可先跑通再删）"))
