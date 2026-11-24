# 20｜《Hell Grind》跨段无缝衔接 × 工业级视听资产生产规范（v3.3 适配 MiniMax H3）

> 本手册提炼自 2026 戛纳电影市场展映 AI 电影长片 **《Hell Grind》**（Higgsfield Cinema Studio 4.0）官方制作白皮书、连续 15 秒原片逐帧接缝实测与我们的 MiniMax H3 / U24 对比实验，并将其彻底转译为 **MiniMax H3 100% 肯定式语法 + `550–850` 词黄金甜区** 可直接落地的生产规范。

---

## 一、 破除迷思：15 秒跨段无缝衔接不是靠“尾帧接首帧”，而是 6 招电影工程组合拳

AI 视频模型每次生成都是无记忆的封闭过程。强行用两段完全相同的中景构图硬接“尾帧→首帧”，一旦人物偏差 20 厘米或手势错半拍，观众立刻觉得穿帮；真正让 15 秒切片像院线电影一样丝滑的，是下面 6 招：

### 1. 段边界「景别大跳切（Hard-Cut Scale Jump）」藏住接缝
- **原则**：相邻 15 秒段（`Seg N` 尾镜 → `Seg N+1` 首镜）**绝不用相同的平庸中景机位硬拼**！刻意设计大景别或大角度反差硬切：
  - `Wide Standoff（双人宽景对峙收尾）` → `Extreme Close-Up / Tight Reaction（极端特写或贴脸反应起幅）`
  - `Medium Action Climax（动作爆点中景收尾）` → `Low-Angle Ground / Insert Cutaway（贴地仰拍或手部/器物微距起幅）`
  - `Tight Dialogue Close-Up（近景台词收尾）` → `Wide Re-Establishing Shot（宽景重定空间站位起幅）`
- **同步要求**：景别跳切的同时，**人物伤痕、血迹、湿干度、持物、高矮姿态（站/跪/躺）与 180° 左右方位必须 100% 物理连贯**。

### 2. 每场固化 4 行「纯地标空间地图（`GEO SPATIAL LAYOUT`）」常量
- **痛点**：早期最常见穿帮是人物跨段互换左右、机位突然越轴、光源左右乱跑。
- **解法**：每场戏在编剧/编译阶段定死 **4 行极简纯地标地图**（**不写人物、不写动作，只写镜头视角下的 `screen-left / center / screen-right` 地标 + 大致间距 + 180° 机位永留哪一侧 + 单一主光方向**），在同场所有段落的 `detailed_description` 开头原样复现：
  ```text
  Spatial lock (screen-left to screen-right): port timber rail and iron salvage pulley stand at screen-left, flooded plank deck spans center, horizontal wooden windlass roller and thick main mast with twin amber whale-oil lanterns anchor center-right; camera remains strictly on the forward deck side along the 180-degree axis; warm lantern key glows from center-right against cold indigo storm rain from above.
  ```
- **铁律**：一律使用镜头坐标系（`screen-left / screen-right`），绝不写“主角的左边”；静态对话戏把演员收束在**房间的一个角落**，缩小空间自由度。

### 3. 累计物理状态增量（Cumulative State Delta）+ 情绪生理余震（Emotional Tail）
- **自洽原则**：每段提示词都是完全独立的封闭文本，严禁写 `continues from previous shot / same as before` 等模型无法理解的相对词。
- **显式重写累计状态**：一旦上一段发生物理变化（如第 4 集右肩被抓出五道血爪印、刀身沾血、手腕缠粗麻布、衣袖撕裂），后续每一段的 `subject_definitions` 与 `[Shot 1]` 必须显式继承该累积状态。
- **情绪余震跨段**：切段瞬间情绪不会一键归零！上段刚经历剧痛、惊骇或窒息，下段第 0 秒必须描写残余生理态（胸口仍在急促起伏、指节紧攥发白、喉结干吞、血汗未拭），让情绪惯性牵引观众滑过剪辑点。

### 4. 跨空间转场「门槛冷暖对比法（Threshold Rule）」
- 人物跨过门洞、舱盖、拱门或拐角进入新空间时，把**门框/舱口前景与内外强冷暖光对比**写在同一段内（例如：冷靛暴雨甲板向下俯拍，下方敞开的舱口透出暖琥珀鲸油灯光），色温反差既立刻交代了空间转移，又自然吸收了局部几何差异。

### 5. 活表演三原则（消除“木偶念台词”）
1. **手上有活（Busy Hands）**：对话角色手上保持具体动作（擦刀、系绷带、捻药叶、拨灯芯、攥紧船舷），在听到关键句的瞬间**手上的活骤然停住**——这是最强戏剧重音。
2. **话尾前预反应（Pre-Lap Reaction）**：听话者在对方台词尚未落音时，眼神、眉峰或呼吸节奏已经开始转变。
3. **写肌肉物理，不写抽象情绪词**：将空洞的 `shocked / angry / sad` 替换为可见的生理动作（`jaw muscles clench once, nostrils flare on a sharp silent inhale, wet knuckles whiten around the hilt, gaze snaps sideways before her head turns`）。

### 6. 后期防漂移微裁 + `0.15s` 音频平滑交叉淡化
- AI 视频模型（Seedance 2.0 与 MiniMax H3 均同）在每段 **最前 `0.15–0.4s`（起幅稳定期）** 与 **最后 `0.25–0.5s`（收尾漂移期）** 最易出现构图微晃或边缘拖沓。
- 拼接时除自动切除贴图泄露帧与空镜闪现帧外，对首尾无对白的安全静默区默认裁剪 `0.15–0.35s` 边缘漂移帧，并在段与段之间施加 **`0.15s` 音频平滑交叉淡化（Audio Crossfade）**，配合 `non_diegetic_music: N/A` 的统一环境声底与后期整轨配乐，实现真正影院级无痕衔接。

---

## 二、 工业级视觉与声音资产生产铁律（资产先行，绝不边拍边修）

### 1. 角色母图（Character Turnaround Sheet）
- **故意“平淡无电影感”**：使用中性深灰/炭灰平光棚拍背景（`#1A1B1D`），均匀平光、真实皮肤毛孔、清晰眼珠高光（`catch-lights` — 无高光的眼睛像死眼，视频模型演不出神采）；**绝不在角色母图里烘烤强电影滤镜、暗部压黑或霓虹打光**，电影光影完全留给场景母图与视频提示词控制！
- **构图布局**：16:9 横幅三栏（左：大比例 **3/4 微侧面胸像特写**，比纯死正面更容易被视频模型理解三维骨相；中：正面全身；右：背面全身）。如远景全景镜头反复出现小脸模糊，可按《Hell Grind》进阶方案生成“全身无头 + 独立大头像”变体，强迫模型只从高清特写采样面部。
- **严禁整图反复过模**：给同一角色加伤痕、血迹或换装时，保持同一演员骨相与原始毛孔质感，**按物理状态严格拆分为独立资产**（如 `C01-SEA-WET` vs `C01-SEA-BAND`、`C02-WET` vs `C02-DRY`），绝不靠一段文字同时硬压两种服化状态。

### 2. 场景空镜母图（Location Plate）
- **必须拍 3/4 纵深透视视角**：严禁把房间/船舱拍成扁平的正视对称壁纸！3/4 纵深构图能为视频模型提供真实三维空间纵深，支撑环绕、推进与过肩反打。
- **内置固定地标 + 单一主光逻辑**：每张场景母图必带清晰空间锚点（立柱、油灯、矮案、木梯、铁笼）与唯一主光方向，绝不出现互相打架的双太阳/双主光；画面内**零人物、零文字水印**。
- **反打视角高级取图法**：若需同一空间的严格 180° 反打空镜，可先用当前场景图生成一段无人的缓慢漫游推拉视频，截取目标反打帧再做单次高清写实精修。

### 3. 道具微距母图（Prop Macro Plate）
- **35mm 单主体 3/4 微距实拍**：中性深炭灰台面实拍，展现真实木纹、铸铁锈蚀、铜绿包浆与羊皮纤维，**严禁使用 2D 纸本厚涂或带网格边框的四宫格插画**。
- **拓扑剧变道具强制拆态**：闭合麻网 vs 挑开露链麻网、空白羊皮 vs 血指印契约、完整沉香 vs 劈开露白芯假沉香，必须独立建图。

### 4. 声音资产双层锁（Voice Continuity Lock）
- **Layer 1（主力 + 所有跨集/多句配角）**：全部配备 `32kHz mono PCM16` 神经声纹锚点 WAV（`3.5–8.5s` 干声，`-16 LUFS` 归一化，如 `VoxCPM2` 生成并登记 `library/cast.json` + `voices.json`），在 H3 中挂载 `<Audio N>` 锁死音色。
- **Layer 2（单句龙套群演）**：在 `voices.json` 中固化永不更改的英文声线控制常量（`register + tempo + texture + manner`），每次发声逐字粘贴，杜绝跨镜变声。
