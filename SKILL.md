---
name: h3-drama-kit
description: |-
  AI 电影级短剧/中长剧全流程引擎 v3.1（U24-文武双修T8 首要底座 · ref_image_size=max · 纯导演官方 MiniMax H3 原生声画 · LoopForge 12 实证运镜原语 × 双景深回眸拉焦 · 仅留 3 项轻量硬护栏）：
  经 5 组同种子单变量 A/B 实拍全面验证，废除旧版 600 词重复布局八股、强制静音室音、闭唇木偶锁与 completely frozen 静止死锁；确立“官方 12 运镜原语 + 显式开场景别 + 场景母图分场精准挂载 + 表情演变弧线”实证铁律，驱动 MiniMax H3 音画联合扩散满血发挥。
  全画幅/全题材/全文化自由定制（横屏 16:9 & 2.39:1 / 竖屏 9:16、中式/美式/日韩、短剧/中长剧无 8 段上限）；默认锁定 API-U24-文武双修T8版 为自建原生 ComfyUI 与 Colab G4 首要生产工作流。
---

# H3 导演级影视工具包 v3.1（Director-First · U24-T8 Primary · Empirical Camera Grammar）

> **v3.1 底层信条（经全集多轴实拍 + 5 组同种子单变量 A/B 实验验证）**：
> 旧版 40+ 条防御式微规则会制造“全景引力”“跨模态声画打架”与“合规税”，把强底座（`U24-T8`）和强编导模型捆成木偶。
> **v3.1 彻底聚焦“厚资产 + 强导演 + 实证运镜原语 + 3 项轻量硬护栏”**：只保留经肉眼同种子实拍 100% 胜出的有效杠杆。

---

## 一、 首要出片引擎锁定：`API-U24-文武双修T8版`

经全集 A（Pika H3）/ B（Cobijada + 3 LoRA）/ C（`API-U24-文武双修T8版`）同种子实拍评测，**正式将 `API-U24-文武双修T8版` 锁定为自建 ComfyUI 与云端出片的首要默认引擎**：
- **核心架构**：`minimax_h3_hybrid_fl2va_ref2va_b25-49-int8` 底模 + 两阶段采样（`PASS 1` 4 步 `0.4MP` 构图运动 → `1.5×` 3D 潜空间放大 → `PASS 2` 5 步 `1312×736` 16:9 或 `736×1312` 9:16 电影精修）+ 双分支 6 LoRA（`FL2V Turbo v1.2` + `H3_Combat_V2` + `Dasiwa` + `10ErosMax_T8` + `Motion_Repair` + `MinimaxH3真实电影质感V0.1`），节点 `ref_image_size` 默认锁 **`"max"`**（经 AB3 同种子验证）。
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

## 三、 官方精简 H3 语法 × 五大实拍验证导演法则（v3.1）

无论是直接生成 `jobs.json`（推荐纯导演直写模式），还是通过 `compose_plan.py -> build_episode.py` 编译，每段 15 秒提示词严格遵循 **MiniMax H3 官方 6 段式（`550–850` 英文词黄金甜区）**：
`subject_definitions` → `summary` → `retention_analysis` → `detailed_description` → `overall_soundscape` → `non_diegetic_music`

详见必读手册：**[playbook/18_U24首要工作流与纯导演官方H3编译规范.md](playbook/18_U24首要工作流与纯导演官方H3编译规范.md)** 与 **[playbook/19_LoopForge实证运镜配方库.md](playbook/19_LoopForge实证运镜配方库.md)**，经 5 组同种子 A/B 实拍验证的核心五条铁律：
1. **场景母图“分场精准挂载”法则（AB4 实证）**：**含独特历史器物/关键建筑拓扑的定场全景段必挂干净场景母图**（锁死结构不漂移）；**纯双人对峙、贴身搏杀、大幅环绕 `Arc Shot`、单人情绪特写段坚决卸掉全景背景图**（解放运镜且无杂景抢戏）。本镜不入画的元素绝不挂图、绝不复读 600 词全局布局。
2. **用“官方 12 运镜原语 + 显式开场景别”控镜（AB1 & AB5 实证完胜 10:0）**：
   - 不依赖对 H3 几乎无效的焦段度数（`84°/29°`）或镜头品牌词，直接写 **官方 12 原语动词**（`Push In / Pull Out / Arc Shot with large amplitude / Tracking Shot / Tilt Up / Pedestal / Static Shot / Roll`）；
   - **开场景别反着留余量**：要推紧/大幅环绕，开头必须显式开宽；`Push In` 必放前景实物在画边擦过以区别于扁平 `Zoom In`；
   - **双景深拉焦（D-03 绝杀配方）**：`holds two distinct depth planes at once` + `holds a Static Shot` + 前景人物回眸/转头触发拉焦动机 + `focus racks smoothly from A to B`。
3. **废除死锁词、释放演变弧线表演（AB2 实证完胜 9:1）**：
   - **彻底废除 `completely frozen motionless` 与 `lips pressed shut`**：昏迷/躺卧改写为自然垂卧（`lies limp and unconscious with eyelids shut and jaw slack`）+ 显式 `Tilt Up`，既不误动又能拉满 100% 运镜行程；
   - **表情写“演变弧线（Shift from A to B）”**（如从警惕转为阴鸷冷笑），且允许对白与肢体动作同步进行。
4. **节点参数锁 `ref_image_size = "max"`（AB3 实证）**：U24 ComfyUI 节点统一用 `ref_image_size="max"` 替代 `"match"`，光影纵深更立体、动态更强且零首帧三联卡残留。
5. **持续声底 + 逐切镜材质爆点 + 配乐弧线**：在 `overall_soundscape`（严禁混入 `camera / drone / rig` 硬件词）与 `non_diegetic_music` 中写出贯穿环境声底、精准踩在切点上的材质音效与配乐起落——用声音节拍牵引 H3 画面剪辑。

---

## 四、 仅保留的 3 项轻量硬护栏（真正防翻车，绝不绑架创意）

1. **护栏 ① · 资产状态机（厚资产是一切一致性的基石）**：
   - 角色母图用干净无字的暗底定妆卡锁死灵魂视觉符号；可变物体（闭合麻网 vs 挑开麻网、完好信封 vs 撕碎残片）必须拆独立分态母图跨镜过渡，**禁单镜硬变形**；主力说话角色配纯净 `32kHz` 声线 WAV。
2. **护栏 ② · 15 秒语速与节拍容量算账器**：
   - 使用 `lock_dialogue.py`（中文 `3.8 字/秒`、英文 `2.5 词/秒`）核对容量，给核心收尾视觉爆点留足最后 `2.5–3.5s` 独立一镜，绝不塞爆挤出画外。
3. **护栏 ③ · 3 条极简物理与构图底线**：
   - **全肯定式描述**：提示词中不写 `no / not / never / without`；
   - **未挂母图不凭空写陌生黑影**；
   - **起身/登梯/纵深大位移镜头**顺手补 `camera tilts smoothly upward to maintain clear headroom framing`（实拍验证 100% 根治切头顶）。

---

## 五、 标准作业流（双轨任选）

| 轨道 | 适用场景 | 执行链路 |
| :--- | :--- | :--- |
| **轨道 A：纯导演直写 `jobs.json`（推荐 · 最高上限）** | 精品横屏/竖屏短剧、电影感强运镜试拍、追求极致流畅度与原创镜头语言 | 导演剧本 → `lock_dialogue.py` 核对台词时长 → 备齐角色/分态道具/声线母图 → 直接按官方 6 段式 + 12 运镜原语写 `05_prompts/segXX.txt` + `jobs.json` → `u24_self_hosted_run.py run-jobs` 或 Colab G4 `U24` 出片 |
| **轨道 B：工程化编译 `plan.json`（长篇批量量产）** | 20–80 集长篇批量生产，需要统一资产表复用与台词防漏检 | `lock_dialogue.py` → `plans/eNN.py`（默认 `compact_prompt=True`、`audio_mode="native-cinema"`、近景可 `scene_ref=None`）→ `compose_plan.py` → `build_episode.py`（已解绑全部旧紧箍咒）→ `u24_self_hosted_run.py run` |

### 付费 / 上云硬纪律（不变）
- 任何云端计费或 Colab GPU 运行前清晰汇报任务数与预计耗时/消耗；
- Colab 出片完毕后必须核验 `colab sessions` 返回 `No active sessions found on server.` 确认零算力残留；
- 令牌仅存 `.env`，绝不打印或外泄。
