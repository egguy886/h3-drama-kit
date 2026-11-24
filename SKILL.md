---
name: h3-drama-kit
description: |-
  AI 电影级短剧/中长剧全流程引擎 v3.0（U24-文武双修T8 首要底座 · 纯导演官方 MiniMax H3 原生声画 · Cinema Studio 4.0 / Hell Grind 光学运镜 · 仅留 3 项轻量硬护栏）：
  全面解绑旧版厚规则紧箍咒（废除 600 词重复布局八股、废除强制静音室音、解禁 orbit 环绕与对白动作合流、取消闭唇木偶锁），以“厚资产、薄规则、强导演”驱动 MiniMax H3 音画联合扩散满血发挥。
  全画幅/全题材/全文化自由定制（横屏 16:9 & 2.39:1 / 竖屏 9:16、中式/美式/日韩、短剧/中长剧无 8 段上限）；默认锁定 API-U24-文武双修T8版 为自建原生 ComfyUI 与 Colab G4 首要生产工作流。
---

# H3 导演级影视工具包 v3.0（Director-First · U24-T8 Primary · Native A/V Engine）

> **v3.0 底层信条（经实拍对照实验验证）**：
> 旧版 40+ 条防御式微规则会制造“全景引力”“跨模态声画打架”与“合规税”，把强底座（`U24-T8`）和强编导模型捆成木偶。
> **v3.0 彻底瘦身为“厚资产 + 强导演 + 3 项轻量硬护栏”**：把编剧、运镜、表演与声场创作权 100% 归还给顶级导演思维，用脚本只守真正能省钱防翻车的 3 条底线。

---

## 一、 首要出片引擎锁定：`API-U24-文武双修T8版`

经全集 A（Pika H3）/ B（Cobijada + 3 LoRA）/ C（`API-U24-文武双修T8版`）同种子实拍评测，**正式将 `API-U24-文武双修T8版` 锁定为自建 ComfyUI 与云端出片的首要默认引擎**：
- **核心架构**：`minimax_h3_hybrid_fl2va_ref2va_b25-49-int8` 底模 + 两阶段采样（`PASS 1` 4 步 `0.4MP` 构图运动 → `1.5×` 3D 潜空间放大 → `PASS 2` 5 步 `1312×736` 16:9 或 `736×1312` 9:16 电影精修）+ 双分支 6 LoRA（`FL2V Turbo v1.2` + `H3_Combat_V2` + `Dasiwa` + `10ErosMax_T8` + `Motion_Repair` + `MinimaxH3真实电影质感V0.1`）。
- **开箱即用三件套**：
  - 一键部署自建原生 ComfyUI（Linux GPU / AutoDL / RunPod，建议显存 ≥32GB）：`bash scripts/deploy_self_hosted_u24.sh`
  - 自建原生 ComfyUI 直连客户端（支持 `episodes/<EP>` 或纯导演 `jobs.json`，自动去重上传图/音并回传成片）：`python3 scripts/u24_self_hosted_run.py run-jobs <jobs.json> --out <out_dir> --url http://<IP>:8188`
  - 完整 API 工作流模板：`templates/workflows/u24_wenwu_t8_primary.api.json`

---

## 二、 全适配立项参数（S0 · 由用户自由定调）

新项目启动前只确认 5 个制片开关，**绝不强套旧默认**：
1. **画幅**：`16:9`（`1312×736`）/ `2.39:1` / `9:16`（`736×1312`）；
2. **语言与文化语境**：中文（按 `3.8 字/秒`）/ 英文美式（按 `2.5 词/秒`）；
3. **体量与节奏**：竖屏短剧（参考 8–10 段，按戏核伸缩）/ 横屏短剧（**无 8 段上限**）/ 中长剧分幕；
4. **声音模式（`audio_mode`）**：
   - **`native-cinema`（默认推荐）**：全面释放 MiniMax H3 原生音画联合扩散——写满持续环境声底（Audio Bed）、逐切镜动作材质音效与电影配乐情绪弧线；
   - **`dry-stem`（仅当用户明确要求后期换配音/独立混音时启用）**：干声对白 + 轻环境底噪 + `non_diegetic_music: N/A`。
5. **视觉介质与导演参考系**：真人电影写实 / 国风 2D 厚涂 / 3D 电影级国漫 + 明确摄影指导参考系（如 *Deakins / Lubezki / 徐克暗黑光影*），写入 `library/style_lock.json`。

---

## 三、 官方精简 H3 语法 × `Cinema Studio 4.0 / Hell Grind` 五大导演法则

无论是直接生成 `jobs.json`（推荐纯导演直写模式），还是通过 `compose_plan.py -> build_episode.py` 编译，每段 15 秒提示词严格遵循 **MiniMax H3 官方 6 段式（`550–850` 英文词黄金甜区）**：
`subject_definitions` → `summary` → `retention_analysis` → `detailed_description` → `overall_soundscape` → `non_diegetic_music`

详见必读手册：**[playbook/18_U24首要工作流与纯导演官方H3编译规范.md](playbook/18_U24首要工作流与纯导演官方H3编译规范.md)**，核心五条法则：
1. **D1 去污染与零“全景引力”**：**本镜不入画的元素绝不挂图、绝不写词！** 近景对峙、特写搏杀、微距插切**不要强行挂载全景空景母图**，也不要把全局建筑/家具布局重复写三遍；已挂参考图的人物只用 1–2 句锚定核心辨识特征，把 80% 词数留给 `[Shot 1..N]` 的表演、光影与镜头运动。
2. **用“物理光学结果”控景别（吸收 `CINEDANCE V4`）**：
   - 沉浸大景/贴身动作（`84° / 107°` 广角感）：写明物理贴近、空间扩张、直线平直、前后景皆清晰；
   - 情感孤立/压迫特写（`29° / 18°` 长焦压缩感）：写明长焦压缩背景、奶油虚化、锐利锁定眼眸、前景暗部失焦遮挡占底边 1/3；
   - 同一镜内不混装“广角大景 + 微距特写”，换景别用明确内部硬切（`HARD CUT / SMASH CUT / INSERT CUT`）。
3. **操作员级摄影机与自然微表演**：
   - **完全解禁 `orbit`（环绕）、肩扛跟拍、低机位滑轨、焦点接力**，并写明物理机位高度（`deck level / hip height`）、暗部侧（`shadow side`）与手持呼吸惯性（`shoulder-mounted mass, operator breath`）；
   - **允许边说边演**：对白与拔刀、逼近、转身融为一体，不再强拆成“先站桩念完再切镜动”；
   - **彻底取消 `lips pressed shut` 闭唇木偶锁**：非说话人物用真实的生理微表情（冷笑、下颌收紧、呼吸起伏、眼神偏移）演活戏剧张力。
4. **实体物理与材质惯性**：兵器挥动写重量惯性与停顿反震，雨水/血花写抛物线飞溅，衣摆与长发写运动延迟，避免飘浮 CG 感。
5. **持续声底 + 逐切镜声效爆点 + 配乐弧线**：在 `overall_soundscape` 与 `non_diegetic_music` 中写出贯穿全段的风浪/环境声底（Audio Bed）、精准踩在碰撞/拔刀切点上的材质音效，以及随情绪起落或骤停留白的电影配乐——用声音节拍牵引 H3 画面剪辑。

---

## 四、 仅保留的 3 项轻量硬护栏（真正防翻车，绝不绑架创意）

1. **护栏 ① · 资产状态机（厚资产是一切一致性的基石）**：
   - 角色母图死锁灵魂视觉符号（发饰/伤疤/标志配饰），**严禁把未裁切的“三视图设定表”直接当单人母图塞给视频模型**；
   - 物理形态剧变道具（闭合麻网 vs 挑开麻网、完好信封 vs 撕碎残片）必须拆成独立分态母图，跨两镜过渡，**禁单镜硬变形**；
   - 音色资产用纯净 `32kHz` 单人声 WAV 锚定 `<Audio N>`。
2. **护栏 ② · 15 秒语速与节拍容量算账器**：
   - 使用 `lock_dialogue.py`（或手动硬算：中文 `3.8 字/秒`、英文 `2.5 词/秒` + 动作切换余量）核对每段总耗时，防止自由导演“贪心塞太满”把关键收尾动作（如刀刃落布、门栓震颤）挤出 15 秒边界。
3. **护栏 ③ · 4 条极简物理与构图底线（D2 内部静默自检，有风险才补一句短锁）**：
   - **全肯定式描述**：提示词中不写 `no / not / never / without`（改写正面可见物理状态）；
   - **未挂母图不凭空写陌生黑影**；
   - **死尸/装昏/昏迷不动**写明 `completely frozen motionless, zero breathing or swaying`；
   - **起身/登梯/纵深大位移镜头**顺手补一句 `maintain clear headroom framing`（防止头顶出画）。

---

## 五、 标准作业流（双轨任选）

| 轨道 | 适用场景 | 执行链路 |
| :--- | :--- | :--- |
| **轨道 A：纯导演直写 `jobs.json`（推荐 · 最高上限）** | 精品横屏/竖屏短剧、电影感强运镜试拍、追求极致流畅度与原创镜头语言 | 导演剧本 → `lock_dialogue.py` 核对台词时长 → 备齐角色/分态道具/声线母图 → 直接按官方 6 段式写 `05_prompts/segXX.txt` + `jobs.json` → `u24_self_hosted_run.py run-jobs` 或 Colab G4 `U24` 出片 |
| **轨道 B：工程化编译 `plan.json`（长篇批量量产）** | 20–80 集长篇批量生产，需要统一资产表复用与台词防漏检 | `lock_dialogue.py` → `plans/eNN.py`（默认 `compact_prompt=True`、`audio_mode="native-cinema"`、近景可 `scene_ref=None`）→ `compose_plan.py` → `build_episode.py`（已解绑四大紧箍咒）→ `u24_self_hosted_run.py run` |

### 付费 / 上云硬纪律（不变）
- 任何云端计费或 Colab GPU 运行前清晰汇报任务数与预计耗时/消耗；
- Colab 出片完毕后必须核验 `colab sessions` 返回 `No active sessions found on server.` 确认零算力残留；
- 令牌仅存 `.env`，绝不打印或外泄。
