# H3 短剧工具包（h3-drama-kit）

[English](README.md) · **简体中文**

> 从 60 集 AI 短剧《越线 · Crossing the Line》（MiniMax H3 + AutoDL，480 段、约 120 分钟）实战，以及约 150 条 RunningHub H3 对照测试里提炼的**可复用全流程**：剧本 → 资产（视觉/声线）→ 分镜提示词 → 编译自检 → AutoDL 云端出片 → 看片返工 → 后期交付。
> 既是一个 Claude Code / Codex skill，也是一套零门槛的 Python 工具。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Model](https://img.shields.io/badge/Video-MiniMax%20H3-brightgreen.svg)](#依赖)
[![Agents](https://img.shields.io/badge/Agent-Claude%20Code%20%7C%20Codex-orange.svg)](#作为-skill-安装)

---

## 为什么要做这个

一部 60 集的 AI 短剧，真正耗钱耗时间的不是"生成"，而是**返工**：人物前后不像、站位接不上、台词被剪半句、声线每段漂、打斗像慢动作、片尾话没说完就黑屏……这些坑《越线》全踩过一遍，并且都留下了数据。

工具包把这些经验变成三样东西：
- **playbook**：每个阶段怎么做、门禁是什么，每条写法规则都标了证据等级（量产验证 / RH 对照 / 第三方 / 测过无效）。
- **scripts**：把规则写进工具里：编译时自动拦截坏提示词，出片前预检和估价，看片时自动核对台词，后期一条龙出成片。
- **templates**：一个可以从头跑到尾的示例项目，零花费演练整套流程（自带模拟出片接口）。

## 全流程

| 阶段 | 做什么 | 工具 | 门禁 |
|---|---|---|---|
| S0 立项 | 画幅、语言、段数、平台交付标准、尺度 | `new_project.py` | 画幅和尺度已确认 |
| S1 剧本审计 + 台词锁定 | 逐字锁台词、估时长；设备声挪到后期 | `lock_dialogue.py`、`plans/move_post.py` | 无逻辑冲突 |
| S2 资产 | 角色/场景/道具拆 ID、写库条目、出参考图；声线定档 | `asset_gaps.py`、`blocking_diagram.py` | 缺图清零 |
| S3 分镜 | 每集一个 `plans/eNN.py`：镜头、时长、台词位置、站位、段缝 | `plans/pw.py` | 自查清单 |
| S4 编译自检 | 生成中英对照提示词并自动校验 | `compose_plan.py`、`build_episode.py`、`shot_lint.py`、`axis_lint.py` | ❌ 清零 |
| S5 出片 | 预检 → dry-run → 先锋段 → 夜间批量 | `h3_run.py`、`h3_batch.py` | **付费前明确同意** |
| S6 看片返工 | 台词核对、对照图、动作量检测；按层回退修 | `dialogue_check.py`、`episode_sheet.py`、`motion_check.py` | 每段保留由人确认 |
| S7 后期 | 声线统一、设备声、拼接、环境声底、字幕铭牌、片头尾、响度 | `voice_fix_ep.py`、`assemble_episode.py`、`subtitle_episode.py`、`finish_episode.py` | 成片完整看一遍 |

## 三分钟上手

```bash
git clone https://github.com/egguy886/h3-drama-kit.git
cd h3-drama-kit

# 1. 建项目（不会覆盖已有文件）
python3 scripts/new_project.py ~/my-drama --title-en "Night Shift" --title-cn "夜班" --aspect 9:16
cd ~/my-drama
python3 tools/kit_doctor.py                 # 环境自检

# 2. 跑通自带的 E01 示例（全程免费）
python3 tools/lock_dialogue.py scripts_fixed/E01_示例.md episodes/E01/02_dialogue_lock.json
python3 plans/e01.py && python3 tools/compose_plan.py E01
python3 tools/build_episode.py episodes/E01 --voices voices.json
python3 tools/asset_gaps.py                 # 缺哪些图 + 生图提示词
python3 tools/h3_run.py check E01           # 放好图之后预检
python3 tools/h3_run.py run E01 --seg 1 --dry-run

# 3. 想演练完整出片？起一个本地模拟接口（不花钱）
python3 tools/mock_autodl.py &              # 然后 export AUTODL_BASE_URL=http://127.0.0.1:8765 AUTODL_TOKEN=TEST
```

## 作为 skill 安装

```bash
ln -s "$(pwd)" ~/.claude/skills/h3-drama-kit     # Claude Code
ln -s "$(pwd)" ~/.agents/skills/h3-drama-kit     # Codex / 其他 Agent
```
然后在 Agent 里说"用 h3-drama-kit 开新剧 / 写 E05 分镜 / 出片"即可。

## 写镜头的十条（摘自 playbook/04，证据见 09）

1. 每段 15.0 秒、≤6 镜；最后一句台词 ≤13.5 秒；最后 1–1.5 秒是有内容的停留。【量产】
2. 同场景跨段硬切、新段换景别，写段缝动机（动作/视线/声音）；不尾帧接力；禁全景接全景。【量产】
3. 开场全景要**动**（运镜 + 持续动作）；少写 "static shot"；绝不写 slow motion。【量产 + RH】
4. 打斗每个打击单独一镜 0.8–1.4 秒、一镜一动作。【RH + 量产】
5. 肯定式；状态先行；视线写到具体落点；左右写 frame-left/right；多人动作写先后。【量产】
6. 对白镜只写台词，说完的动作放下一镜；画面里别人的正脸写 lips at rest。【量产 + 第三方】
7. 站位卡只写整段不动的东西；会移动的人写进镜头（否则一个人出现两次）。【量产】
8. ≥3 人静态戏：第一镜静默锁位首秒；要精确站位加灰度字母站位线稿图。【RH】
9. 前景失焦物（管道、后视镜、栏杆）加纵深；眼神写法（眼先于头）。【RH】
10. 参考图里可变物体画"动作之前"的状态；会变的状态单独一张图。【量产 + RH】

**测过没用或有害**：数量锁、"声线更高"描述、参考音频拉音高、用"静默"控制对白起点、去掉场景参考图、首帧锁、身高数字、对白段用精简提示词、TTS 整句重配。

## 目录

| 路径 | 内容 |
|---|---|
| `SKILL.md` | Skill 入口：流程、硬规则、写镜头十条 |
| `playbook/00–10` | 全流程总览、剧本审计、视觉资产、声线、**分镜与提示词（核心）**、编译自检、AutoDL 出片、看片返工、后期交付、规则证据表、踩坑清单 |
| `scripts/` | 全部工具（建项目时复制到项目的 `tools/`） |
| `templates/project/` | 新项目模板（配置、资产库示例、E01 示例剧本与分镜、站位线稿示例） |
| `templates/prompts/` | 资产参考图提示词模板、编译好的单段提示词示例 |

## 依赖

- **必需**：Python ≥ 3.9、ffmpeg/ffprobe、Pillow、numpy。
- **推荐**：openai-whisper（台词核对、字幕）、[seed-vc](https://github.com/Plachtaa/seed-vc) + demucs（声线统一，GPL-3.0，需自行安装，见 playbook/08）、VoxCPM2（设备声/候选声线）、macOS（OCR 检测 H3 自带字幕、字体）。
- **出片接口**：[AutoDL](https://www.autodl.art) 上的 MiniMax H3 工作流（`minimax_h3_zm_u24`）。令牌只放项目 `.env` 的 `AUTODL_TOKEN`，**不要提交到 git**（新项目自带的 `.gitignore` 已排除）。

## 安全与花费

- `h3_run.py` / `h3_batch.py` 在付费提交前会报任务数 × 分辨率 × 时长 × 预估费用；作为 skill 使用时，Agent 必须得到你明确同意才会提交。
- 网络异常不自动重提（先 `resume` 查状态），避免重复扣费。
- 768p 夜间空闲窗口约 ¥0.45/段（2026-10 价格，以平台为准）。

## 相关项目

- [write-screenplay-skill](https://github.com/egguy886/write-screenplay-skill)：前一步的剧本工具，把小说改成短剧剧本、生成制作圣经，并可直接导出本工具包的资产库格式。

## 说明

playbook 与 SKILL.md 正文为中文（规则来自中文生产记录）；用其他语言向 Agent 提问，它会用你的语言回答。

## 许可证

[MIT](LICENSE)。第三方模型与工具（MiniMax H3、AutoDL、seed-vc、VoxCPM、Whisper）遵循各自的许可与服务条款。
