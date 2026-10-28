# 11 自有 ComfyUI 服务器出片 + "生成不带环境声、后期统一铺"

> 来源：《I Texted the Wrong Billionaire》2026-10 实战（E01 全集拼接验证，用户确认"顺了，全剧用这套"）。AutoDL 路线（playbook/06）仍然可用；本章是**服务器常开、无单次费用**时的路线。

## 1. 什么时候走这条路
- 你有一台常开的 ComfyUI 实例（zealman 面板，带 `/api/workflow/generate`），工作流 `API-U24-文武双修T8版`（同一个 H3 U24 工作流）。无令牌、无单次费用 → 可以放开试提示词、返工。
- **单卡只能一次跑一段**：整集串行，不要并发。一段约 6 分钟（0.4MP 一采 × 1.5 二采 → 736×1312、24 fps、15.08 s）；一集 8–10 段 ≈ 1 小时。**0.6MP 会爆显存**，别升。

## 2. 命令（项目根目录）
```bash
echo '{"base_url": "https://你的面板地址"}' > comfy_settings.json     # 或环境变量 COMFY_BASE_URL
python3 tools/comfy_run.py status                      # 面板 / GPU / 队列 / 工作流是否在线
python3 tools/comfy_run.py run E01 --seg 1 2 --tag t1  # 单段试拍
python3 tools/comfy_run.py batch E01-E10 --tag r1 --retries 1   # 整批顺序出；已有同 tag 成片的跳过
```
- 提示词和参考图清单来自 `h3_run.py run --dry-run`（先 compose + build）；参考图按内容 sha256 只传一次（`comfy_upload_cache.json`），每段提交前先清显存、确认队列空。
- 成片 → `episodes/Exx/07_clips/Exx_segNN_<tag>_s<seed>.mp4`，记 `comfy_runs.jsonl`；批量日志 `comfy_batch.log`。网络抖动（SSL EOF）只会继续轮询、下载重试 5 次，不会重复提交。
- 注意：**待办列表在 batch 启动那一刻展开**。后面才编译的集要另起一个 batch（或写链式脚本等上一批结束再起）。

## 3. 声音策略：生成时只留安静底噪，环境声/音效/配乐全部后期
- 问题（E01 实测）：每段 15 秒各自生成的背景声不同，段缝处这段有背景声、下一段没有 → 听感一跳。
- 做法（学自 HELL GRIND / ONEIRIC / 《越线》voice_fix）：
  1. `plans/pw.py` 里 `QUIET_SOUND`：提示词的声音行**全集统一一句**——只要安静均匀的房间底噪 + 人物自身动作声 + 干净贴近的人声。分镜里写的 `sound` 保留为 `sound_post`（后期音效清单），不进提示词。
  2. `tools/dialog_stem.py Exx`：Demucs（htdemucs two-stems=vocals，CPU）只留人声 → `<clip>_vc-dlg.mp4`。需要 `DEMUCS_PY` 指向装了 demucs 的 python（默认 `tools/voiceconv/.venv`）。
  3. `tools/assemble_episode.py`：按场景从 `library/ambience.json` 铺一条**连续**环境底（雨窗、会所、瓷砖间、车库、校园、湖边、海夜、日间车内…），段头去 0.08 s 起步帧、L-cut、同场景段做颜色匹配。
  4. 一键：`python3 tools/auto_post.py E02-E10 --tag r1`——等一集的每段出齐，自动链接 `segNN_accepted.mp4`、分离人声、拼接成 `08_edit/Exx_cut_v1.mp4`（日志 `auto_post.log`）。
- 代价：**画面内的写实音效（碰杯、关门、手机震动）被 Demucs 当作非人声去掉了**，要在后期按 `sound_post` 加；环境底是合成占位，正式版换实录。

## 4. 已知问题（E01 实测，后期处理）
手机屏幕/便签/账单上的字被生成成乱码 → 一律后期叠字；Seg1 画外音（V.O.）不进 H3，后期配；暗绿裙子在俱乐部灯光下偏黑（服装颜色写足、冷暖光别压）；未带参考图的有色衣物别在文字里点名（会被画成别的颜色）。

## 5. 参考图（Codex CLI 生图）
- `codex exec -m gpt-5.6-luna -i <参考图> -- "<提示词>"`（`-i` 后要加 `--`，否则会吞掉提示词；ChatGPT 登录下默认模型不支持，要指定 -m）。
- `plans/ref_prompts.py` 按库里的 ID 出提示词，`plans/gen_refs.py` 逐个 ID 调 Codex（支持 `--ref`、`--force`）。人物＝3 联图（脸特写 / 无头正面 / 背面），场景＝3/4 俯角空景，道具＝2×2；**状态单独一个 ID**。
- **被否决的图必须搬出 assets/**（放 `_rejected_refs/`）：资产查找器取"每个 ID 在 assets/ 下文件名最大的那张"。
- 道具的视角别套通用模板（踏板车俯视图会画错）；道具支持 `views` 覆盖。
