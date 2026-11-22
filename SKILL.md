---
name: h3-drama-kit
description: AI 短剧全流程工具包 v2.0（MiniMax H3 + AutoDL 云端出片 / 自有 ComfyUI 服务器出片）：剧本审计与中英双语台词锁定 -> 场次站位与子空间母图映射（STAGING_MAP） -> 拆视觉/声线资产 -> 写分镜与 H3 提示词（常规镜 2.5–5.0s 硬门禁） -> 编译硬拦截（禁未挂母图写黑影/禁异地子空间共用场景图/禁尸体与装昏漏写静止锁/禁隔断物内外反切） -> 批量出片 -> 看片返工 -> 声线统一/拼接/字幕/响度交付。新开一部剧、写某一集分镜或提示词、拆资产、锁导演视觉风格（style_lock.json）、出片、审片、后期时使用。
---
# H3 短剧工具包 v2.0（h3-drama-kit · 空间站位与防穿帮硬门禁版）

工具包目录：`playbook/` 写法与流程、`scripts/` 全部工具、`templates/` 新项目模板与提示词模板。
**所有对用户的说明用中文。** 证据标记：【量产】AutoDL/ComfyUI 正式生产验证；【RH】RunningHub 对照验证；详见 `playbook/09_规则证据表.md`。

## 开新项目

```bash
python3 <工具包>/scripts/new_project.py <项目目录> --title-en "Night Shift" --title-cn "夜班" --aspect 9:16 --genre-cn "写实电影感出海都市悬疑短剧，英文对白"
cd <项目目录> && python3 tools/kit_doctor.py
```

先问清（S0）：画幅（9:16 / 16:9 / 1:1）、视觉介质风格（真人实拍院线感 vs 国风 2D 厚涂动漫 vs 3D 电影级国漫渲染）、主色调与导演影调宪法（`library/style_lock.json`）、语言（`zh` 中文按 3.8 字/秒、`en` 英文按 2.5 词/秒）、每集段数、发布平台（`delivery.json` 从第 1 集统一）、内容尺度、配乐与出片方案（AutoDL 云端 vs 自有 ComfyUI 服务器）。写进 `project.json` / `decisions.md` / `library/style_lock.json`。

## 一集的流程（在项目根目录）

| 步 | 命令 | 门禁 | 写法 |
|---|---|---|---|
| 1 剧本审计 + 台词锁定 | `python3 tools/lock_dialogue.py scripts_fixed/E05_x.md episodes/E05/02_dialogue_lock.json`（兼容中英文说话人与 `**开场站位**`）；设备声/V.O. `plans/post_moves.json` -> `python3 plans/move_post.py` | 单一子空间分场、无逻辑冲突；台词逐字 | playbook/01 |
| 2 站位与子空间映射 + 资产锁 | **写分镜前先定 `STAGING_MAP`**：每个物理子空间（如女牢/走廊/隔壁牢/赌桌）必须对应独立 `scene_ref` 母图，严禁异地共用同一张固定构图图；锁死 `library/style_lock.json`；`python3 tools/asset_gaps.py E05` | 缺图清零、子空间零混图 | playbook/02、04、14 |
| 3 分镜与站位写入 | 在 `plans/starts.py` 写首帧站位；在 `plans/e05.py` 先声明 `STAGING_MAP` 再写 `seg / sh / lock1`（常规镜 **2.5–5.0s**，每段推荐 **3–4 镜**） | 自查清单 + `defect_rules` | **playbook/04（核心）** |
| 4 编译硬拦截自检 | `python3 plans/e05.py && python3 tools/compose_plan.py E05 && python3 tools/build_episode.py episodes/E05 --voices voices.json`；`python3 tools/axis_lint.py E05` | **❌ 零容忍拦截**（含空间/人影/静止锁/碎切门禁） | playbook/05 |
| 5 出片 | `h3_run.py check` -> `run --dry-run` -> `h3_batch.py plan` -> **问制片人** -> `h3_batch.py run E05-E08 --window 00:00-08:00` | 付费前明确同意 | playbook/06 |
| 5′ 自有 ComfyUI | `preflight.py E05-E08` -> `comfy_run.py batch E05-E08 --tag r1` -> `auto_post.py E05-E08` | 服务器常开才走这条 | **playbook/11** |
| 6 看片返工 | `h3_run.py accept/reject`、`dialogue_check.py`、`episode_sheet.py`、`motion_check.py` | 每段保留由人确认 | playbook/07 |
| 7 后期 | `voice_fix_ep.py` -> `post_voice.py` -> `assemble_episode.py` -> `finish_episode.py` | 成片完整看一遍 | playbook/08 |
| 7′ 高潮点声音 | `python3 tools/post_additives.py 成片.mp4 out.mp4 --beat 上升始:上升止:落地:冻结 --report` | 手机外放能听到落地；谢帕德 -14 dB | playbook/16 |

## 硬规则（含 v2.0 四大防穿帮编译铁律 ★）

1. **付费出片前**报 任务数 x 分辨率 x 时长 x 预估费用（768p 空闲 ¥0.45/段），等明确同意；网络异常不自动重提（先 `resume`）。
2. **令牌只在项目 .env（AUTODL_TOKEN）**，绝不读出、打印、写进文件或发给别人。
3. 台词逐字不改；中文潜台词绝不进提示词；设备里的声音与内心独白 V.O. 不进 H3，后期配（且画面内必须有独立视觉因果，做到**静音也能看懂**）。
4. 改分镜只改 `plans/eNN.py` 再 compose -> build；不手改 `05_prompts/`。
5. 参考图优先于文字：冲突就改文字或补状态图（`asset_locks.json` 锁住）。
6. **【编译硬拦截 ① · 未挂母图禁写人影】**：当前段未挂载对应角色母图（或 `noref` 角色条目）时，英文提示词**严禁出现 `silhouette / dark figure / shadowy figure / two figures`** 等额外人影词（否则 H3 会凭空捏造黑衣人）；走廊有人靠近但未挂图时，一律改写为纯暖黄灯光扫过岩壁或铁锁轻晃。（`build_episode.py` & `shot_lint.py` ❌）
7. **【编译硬拦截 ② · 异地子空间禁共用同一固定构图场景图】**：写 `plans/eNN.py` 前强制填写 `STAGING_MAP`；同一集内不同物理子空间（如`寒山矿牢` vs `牢外走廊` vs `隔壁木牢` vs `矿洞赌桌`）**严禁复用同一个 `scene_ref`**（否则切段像原地刷出人物），缺子空间图必须先补图；确系稍后重返同一间屋子才可显式标 `same_room_ok=True`。（`build_episode.py` & `shot_lint.py` ❌）
8. **【编译硬拦截 ③ · 尸体 / 无头躯干 / 装昏不动强制写死静止锁】**：凡镜头出现死尸、无头躯干、昏迷或装睡不动，当前镜头的英文描述**必须显式写死 `completely frozen motionless, zero breathing or swaying`**（肯定式写法，不触发否定词拦截，且自动豁免活人 `FROZEN` 告警），漏写编译直接报错。（`build_episode.py` & `shot_lint.py` ❌）
9. **【编译硬拦截 ④ · 隔断物同侧锁与单镜时长硬门禁】**：
   - 两人同处铁栅/门框外侧交谈时，严禁一镜隔着前景铁栅拍 A、下一镜拍 B 抓铁栅（会把同伙视觉关进牢内），必须统一锁死在走廊同侧取景。（`shot_lint.py` ❌）
   - **收紧单镜时长**：除 `lock1` 首秒锁位帧与纯单次打击镜（`0.8–1.6s`，严禁混入摸尸/掏道具过程）外，**常规叙事与连贯动作镜强制 `2.5–5.0s`**（`<2.0s` 编译 ❌ 拦截，`2.0–2.4s` ⚠ 提示），单段 15 秒以 **3–4 镜**（至多 5 镜）为主，必须演透“起手→过程→结果”与道具物理来源。
10. **生成时不要环境声/音乐**：提示词声音行统一用干净室内底噪与可见动作声，连续环境底、音效、配乐一律后期统一铺。

## 写镜头的十条（详见 playbook/04 与 playbook/15）

1. 每段正好 15.0 秒；**常规段 3–4 镜（至多 5 镜），常规单镜 `2.5–5.0s`**；最后一句台词 ≤13.5 秒；最后 1–1.5 秒是有内容的停留。【量产 + v2.0】
2. **先写 `STAGING_MAP` 与 `starts.py` 首帧站位**，核对子空间独立母图与隔断物（铁栅/门框）机位同侧关系；跨子空间必给物理动线过渡镜。【v2.0】
3. 同场景跨段硬切、新段换景别，写 `seam_motive`（action/gaze/sound）；不尾帧接力；禁全景接全景。【量产】
4. 开场全景要**动**（运镜 + 持续动作）；少写 "holds a static shot"，给镜头有动机的运镜；绝不写 slow motion。【量产 + RH】
5. 打斗每个纯打击单独一镜 0.8–1.4 秒、一镜一动作；**搜身/拔刀/取物等过程动作必须独立给足 ≥2.5 秒并先交代道具出处**。【RH + v2.0】
6. 肯定式；状态先行；视线写到具体落点；左右写 frame-left/right；多人动作写先后。【量产】
7. 对白镜只写台词，说完的动作放下一镜；画面里别人的正脸写 lips at rest。【量产 + 第三方】
8. 活人不写 frozen/motionless（会拖慢运镜）；**死尸/无头躯干/装昏必须写死 `completely frozen motionless, zero breathing or swaying`**。【v2.0】
9. 站位卡只写整段不动的东西；会移动的人写进镜头；≥3 人同场静态戏用 `lock1` 首秒锁位或站位线稿图。【量产 + RH】
10. 未挂人物参考图绝不写 `silhouette / dark figure`；可变物体画"动作之前"的状态，状态改变换新图。【量产 + v2.0】

## 不要做（测过没用或有害）

未挂母图写黑影、四个子空间共用一张场景图、1.2 秒碎切塞反杀+摸尸、漏锁尸体静止词、把同侧双人拍到铁栅两侧、数量锁、身高数字、对白段用精简提示词、TTS 整句重配。
