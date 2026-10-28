---
name: h3-drama-kit
description: AI 短剧全流程工具包（MiniMax H3 + AutoDL 云端出片 / 自有 ComfyUI 服务器出片）：剧本审计与台词锁定 → 拆视觉/声线资产并写参考图提示词 → 写分镜与 H3 提示词 → 编译自检 → AutoDL 批量出片 → 看片返工 → 声线统一/拼接/字幕/响度交付。新开一部剧、写某一集分镜或提示词、拆资产、出片、审片、后期时使用。来源：《越线》60 集实战 + RunningHub H3 对照测试。
---

# H3 短剧工具包（h3-drama-kit）

工具包目录（本文件所在处）：`playbook/` 写法与流程、`scripts/` 全部工具、`templates/` 新项目模板与提示词模板。
**所有对用户的说明用中文。** 证据标记：【量产】AutoDL 正式生产验证；【RH】RunningHub 对照验证、AutoDL 待小样；详见 `playbook/09_规则证据表.md`。

## 开新项目
```bash
python3 <工具包>/scripts/new_project.py <项目目录> --title-en "Night Shift" --title-cn "夜班" --aspect 9:16 --genre-cn "写实电影感出海都市悬疑短剧，英文对白"
cd <项目目录> && python3 tools/kit_doctor.py
```
先问清（S0）：画幅、语言、每集段数、发布平台（delivery.json 从第 1 集统一）、内容尺度、配乐方案。写进 project.json / decisions.md。
模板带一个可跑通的 E01 示例（2 段），用来对照格式，跑通后删掉。

## 一集的流程（在项目根目录）
| 步 | 命令 | 门禁 | 写法 |
|---|---|---|---|
| 1 剧本审计 + 台词锁定 | `python3 tools/lock_dialogue.py scripts_fixed/E05_x.md episodes/E05/02_dialogue_lock.json`；设备声 `plans/post_moves.json` → `python3 plans/move_post.py` | 无逻辑冲突；台词逐字 | playbook/01 |
| 2 资产 | 写 library/*.json；`python3 tools/asset_gaps.py E05` → assets/00_资产清单与缺口.md（含生图提示词） | 缺图清零或明确 noref | playbook/02、03 |
| 3 分镜 | 写 `plans/e05.py`（`from pw import *`：seg / sh / lock1） | 自查清单 | **playbook/04（核心）** |
| 4 编译自检 | `python3 plans/e05.py && python3 tools/compose_plan.py E05 && python3 tools/build_episode.py episodes/E05 --voices voices.json`；`python3 tools/axis_lint.py E05` | ❌ 清零，⚠ 逐条看 | playbook/05 |
| 5 出片 | `h3_run.py check` → `run --dry-run` → `h3_batch.py plan` → **问制片人** → `h3_batch.py run E05-E08 --window 00:00-08:00` | 付费前明确同意 | playbook/06 |
| 5′ 自有 ComfyUI | `comfy_run.py batch E05-E08 --tag r1`（无单次费用，单卡串行）→ `auto_post.py E05-E08`（只留人声 + 铺环境底 + 拼接） | 服务器常开才走这条 | **playbook/11** |
| 6 看片返工 | `h3_run.py accept/reject`、`dialogue_check.py`、`episode_sheet.py`、`motion_check.py` | 每段保留由人确认 | playbook/07 |
| 7 后期 | `voice_fix_ep.py` → `post_voice.py` → `assemble_episode.py` → `finish_episode.py` | 成片完整看一遍 | playbook/08 |

## 硬规则
1. **付费出片前**报 任务数 × 分辨率 × 时长 × 预估费用（768p 空闲 ¥0.45/段），等明确同意；网络异常不自动重提（先 `resume`）。
2. **令牌只在项目 .env（AUTODL_TOKEN）**，绝不读出、打印、写进文件或发给别人。
3. 英文台词逐字不改；中文潜台词绝不进提示词；设备里的声音（广播/电话/电视）不进 H3，后期配。
4. 改分镜只改 `plans/eNN.py` 再 compose → build；不手改 `05_prompts/`。
5. 参考图优先于文字：冲突就改文字或补状态图（asset_locks.json 锁住）。
6. 回到最早出错的一层修（参考图 → 镜头设计 → 提示词 → 单段重出），一次只改一处；同段 10 次不过就拆镜头。
7. 片子在人看过之前都是"候选"；自动分不管表演、台词、人脸。
8. **生成时不要环境声/音乐**：提示词声音行全集统一 `QUIET_SOUND`，环境底、音效、配乐一律后期统一铺（段缝才不跳声）。【量产，playbook/11】

## 写镜头的十条（详见 playbook/04）
1. 每段 15.0 秒、≤6 镜；最后一句台词 ≤13.5 秒；最后 1–1.5 秒是有内容的停留。【量产】
2. 同场景跨段硬切、新段换景别，写 `seam_motive`（action/gaze/sound）；不尾帧接力；禁全景接全景。【量产】
3. 开场全景要**动**（运镜 + 持续动作）；少写 "holds a static shot"，给镜头有动机的运镜；绝不写 slow motion。【量产 + RH】
4. 打斗每个打击单独一镜 0.8–1.4 秒、一镜一动作。【RH + 量产】
5. 肯定式；状态先行（写成已在进行中）；视线写到具体落点；左右写 frame-left/right；多人动作写先后。【量产】
6. 对白镜只写台词，说完的动作放下一镜；画面里别人的正脸写 lips at rest。【量产 + 第三方】
7. 站位卡只写整段不动的东西；会移动的人写进镜头（否则一个人出现两次）。【量产】
8. ≥3 人同场静态戏：第一镜用 `lock1()` 静默锁位首秒；要精确站位加站位线稿图（`tools/blocking_diagram.py`，灰度字母版）。【RH】
9. 前景失焦物（管道、后视镜、栏杆）加纵深；眼神写法（眼先于头、读对方的眼睛）。【RH】
10. 参考图里可变物体画"动作之前"的状态；会变的状态单独一张图；需要时写状态追踪句。【量产 + RH】

## 不要做（测过没用或有害）
数量锁、"声线更高"描述、参考音频拉音高、用"静默"控制对白起点、地点图"只取空间"职责句、去掉场景参考图、首帧锁、风格锚点前置、身高数字、对白段用精简提示词、TTS 整句重配。

## 状态与交接
每个项目根目录有 `STATUS.md`（进度/待办/缺口）、`decisions.md`（已定的决定）、`CLAUDE.md`（指向本工具包）。换会话先读这三个。
