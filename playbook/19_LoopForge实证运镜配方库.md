# 19｜MiniMax H3 实证运镜配方库与五大同种子 A/B 铁律（v3.1 · 融合 LoopForge 实测）

> 本手册每一条均经《沉香如局》EP01 `E83` **U24-文武双修T8 同种子单变量 A/B 实拍验证**（5 组对照实片亲眼检验，绝非纸上谈兵），只沉淀经实拍 100% 胜出的有效杠杆。

---

## 一、 经同种子 A/B 实拍验证的五大核心铁律

| 铁律 | 实拍对照依据 | 必须执行的新规范 |
| :--- | :--- | :--- |
| **① 官方 12 运镜原语 + 显式开场景别完胜焦段度数** | **AB1 完胜 10:0**（同种子 `2026112484`：`CINEDANCE` 度数卡死在空绳与无头躯干；LoopForge 原语扫出完整绕背环绕双人贴脸） | 在 MiniMax H3 中**不依赖 `84°/29°/18°` 或 `Cooke/Zeiss` 镜头品牌词**，改用 **官方 12 运镜原语动词 + 显式开场景别（要推紧就先开宽）+ 前景物体擦镜视差 + 表情动态演变弧线**。 |
| **② 静态双景深 + 回眸动机拉焦配方（D-03）** | **AB5 绝杀 10:0**（同种子 `2026112491`：同时框死前景老赵与后景高台姜无音，回眸瞬间单调拉焦丝滑切换，尾镜铁栓水花暴溅） | 双景深拉焦必须显式写 **`holds two distinct depth planes at once` + `holds a Static Shot` + 前景人物转头/回眸触发动机 + `focus racks smoothly from A to B`**。 |
| **③ 废除 `completely frozen motionless` 绝对静止死锁** | **AB2 完胜 9:1**（同种子 `2026112483`：去静止词后前 3 秒运动能量 `+17%`，镜头从血腕一路上摇到闭眼俊脸，阿奴全程零误动） | 昏迷/尸体严禁再写 `completely frozen motionless, zero breathing or swaying`（会拖死运镜行程）；改为自然垂卧描述（`lies limp and unconscious with eyelids shut and jaw slack while rainwater streams off his pale cheek`）+ 显式 `Tilt Up / Push In`。 |
| **④ ComfyUI 节点 `ref_image_size = "max"`** | **AB3 胜出**（同种子 `2026112481`：零三视图首帧泄露，纵深光影更立体，全段运动活力 `+8.4%`） | `MiniMaxH3AudioConditioningT8` 的 `ref_image_size` 默认锁死 **`"max"`**（已同步至 `scripts/u24_self_hosted_run.py`）。 |
| **⑤ 场景母图“分场精准挂载”法则（拒绝一刀切）** | **AB4 双面实证**（同种子 `2026112481`：大场卸掉 `S01-DECK-WIDE` 后，明代卧式木辘轳漂移成了西洋圆船舵！） | **定场全景/含独特历史器物与建筑结构的段 → 必挂干净无字场景母图**锁死结构；**纯双人对峙、贴身搏杀、大幅环绕 `Arc Shot`、单人情绪特写段 → 坚决不挂全景场景图**释放运镜与构图自由度。 |

---

## 二、 MiniMax H3 官方 12 运镜原语速查表（直接写进动词句中）

不要把标签堆在句尾，直接写成自然英文动作句：

| 类别 | 精确原语词 | 实测黄金用法（避坑要点） |
| :--- | :--- | :--- |
| **纵深位移** | `Push In` / `Pull Out` | **必须放前景物体在画边擦过**（如麻缆、风灯、门框、人物肩背），否则会退化成扁平 `Zoom In`；要推到极紧，开场必须开宽！ |
| **焦距缩放** | `Zoom In` / `Zoom Out` | 机位不动、画面纯放大缩小；做极速 `Crash Zoom` 时若需 3 帧瞬切，后期变速剪辑最稳。 |
| **环绕运镜** | `Arc Shot` | **高燃对峙王牌！** 普通弧线不加修饰词；需要绕背切到正面贴脸或 360° 环绕时，精准加上 **`with large amplitude`**（或 **`with large amplitude at fast speed`**）。 |
| **跟拍与平移** | `Tracking Shot` / `Truck Left·Right` | 配合奔跑、抢步拔刀、冲锋使用；手持压迫感可叠加 `Shake Slightly`。 |
| **升降与摇镜** | `Pedestal Up·Down` / `Tilt Up·Down` / `Pan Left·Right` | 做甩镜（Whip Pan）时必须写明 **`FROM 起点 → TO 明确落点主体`**，有落点才有速度与自然运动模糊。 |
| **轴向倾斜** | `Roll Counterclockwise` / `Roll Clockwise` | 荷兰角压迫感（如被按在主桅上锁喉），单集克制使用 1 次效果最炸。 |
| **双景深拉焦** | `Static Shot` + `focus racks smoothly from A to B` | **必须先稳定开在包含前后两个清晰景深平面的中全景**，让前景人物一个转头或眼神动作“带动”焦点滑向后景动作中的主体。 |
| **主视角** | `POV` | 仅展示观察者伸入画面的手与目标互动，严禁写出会被画进画面的穿戴式摄影机支架名（如 `body rig`）。 |

---

## 三、 高级表演与构图句式（经实拍验证）

1. **表情演变弧线（绝不写静态死脸）**：
   - ❌ `looks furious` / `open-faced`（容易 8 秒定格成僵硬表情）
   - ✅ `expression shifts from wary calculation into furious desperation as his brow tightens and jaw locks`
2. **纵向起身 / 登梯防切头顶（Headroom Lock）**：
   - 凡角色起身、踏上楼梯、纵深冲向高台，必补：`the camera tilts smoothly upward and tracks slightly wider to maintain clear headroom framing above her entire head`。
3. **声音槽位零硬件污染 + 严禁原生 BGM（`non_diegetic_music: N/A`）**：
   - `overall_soundscape` 满血写现场环境声底与动作音效，**严禁出现 `camera / lens / drone / rig / dolly`** 等硬件词；`non_diegetic_music` 一律写 `N/A`（避免每 15 秒曲风不同难以拼接，BGM 成片后统一配）。
4. **跨 15 秒段无缝连戏三铁律（v3.2 必守）**：
   - **180° 银幕左右轴线死锁**：同场内固定双方左右侧（如甲板戏姜无音锁 `screen-left` 朝右，老赵锁 `screen-right` 朝左）；拍画左人物的过肩镜（OTS），虚化前景肩影必须在 **`right foreground edge`**（写反必越轴翻转！）；
   - **段尾定姿 = 下段起姿 0.1s 咬合**：连续时间相邻段，上一段尾镜结束的高低姿态（站/单膝跪/平躺/登顶立定）、手持物与贴靠物（如背贴主桅、刀鞘顶胸），下一段首镜第 0 秒必须 1:1 承接，仅换景别/角度；
   - **说话人必入画露脸**：凡有 `<d>` 台词的镜头，说话角色本人必须在焦点内清晰露脸张口。
