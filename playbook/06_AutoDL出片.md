# 06 AutoDL 出片（S5）

> **任何付费提交之前**：告诉制片人 任务数 × 分辨率 × 时长 × 预估费用，等明确同意。提交时网络异常**不自动重提**（可能已扣费），先 `resume` 查。

## 1. 准备（一次性）
- 令牌：项目根目录建 `.env`，写 `AUTODL_TOKEN=…`（不提交、不打印、不发给任何人）。
- 接口：`https://www.autodl.art/api/v1/comfyui/comfyui_workflow/minimax_h3_zm_u24`；`Authorization: Bearer <令牌>`；参考图/音频用 data-URI Base64；返回 `data.status` / `data.results[].url`。模板里的 `h3_settings.json` 已按《越线》实测写好；新账号可跑一次 `python3 tools/h3_run.py probe`（约 2 秒 480p，花几分钱）确认。
- 工作流只开放：prompt / duration / resolution / seed / ref_image_0..8 / ref_audio_0..2。**没有首帧/尾帧参数、采样步数不可设**（尾帧接力＝把上一段尾帧当 Picture 1）。
- 环境自检：`python3 tools/kit_doctor.py`。

## 2. 免费的三道检查
```bash
python3 tools/h3_run.py check E05                       # 每段的参考图/音频/提示词是否齐（找不到图会告诉你放哪）
python3 tools/h3_run.py run E05 --seg 1 2 3 --dry-run   # 只构建请求体 → 06_jobs/dryrun_segNN_en.json，核对参考顺序
python3 tools/h3_batch.py plan E05-E08                  # 链、段数、费用、用时
```

## 3. 单段试拍（480p，看写法是否成立）
```bash
python3 tools/h3_run.py run E05 --seg 3 --resolution 480p竖
python3 tools/h3_run.py run E05 --seg 3 --takes 2       # 抽卡：同时 2 张不同 seed，自动排序（费用 ×2，只用于难段）
python3 tools/h3_run.py accept E05 3 --clip 07_clips/<文件>.mp4      # 保留：记账 + 抽尾帧
python3 tools/h3_run.py reject E05 3 --clip 07_clips/<文件>.mp4 --reason identity-drift
python3 tools/h3_run.py resume E05                      # 断线后继续等待/下载
```
reject 原因词表：identity-drift / prop-error / space-error / gate-opened / extra-cuts / tail-collapse / garbled-text / lip-sync / audio-jump / motion-artifact / weapon-flag / other。

## 4. 夜间批量（768p 正式版）
```bash
python3 tools/h3_batch.py run E05-E08 --resolution 768p竖 --window 00:00-08:00 --parallel 4
python3 tools/h3_batch.py status E05-E08                # 写 BATCH_REPORT.md
```
- **空闲窗口 00:00–08:00 单价低 25%**；不在窗口内会等到 0 点；窗口关前 15 分钟停止提交，已提交的跑完；没出完下次同一命令续批。
- **先锋段**（默认 2 段）合格才放行全部；**熔断**：连续 6 次接口错误停；**限流**自动降并发；磁盘 <2.5 GB 停。
- 每段下载后自动质检：画幅、时长 15±0.6 s、有音频、切点命中、首帧承接、H3 自带字幕（OCR）。**只对看得见的硬伤自动重出**（技术参数 / 分辨率 / 首帧接不上 / 自带字幕），切点类、片尾抖动只标 ⚠ 不重出【量产：切点类重出改善率只有 29%，片尾不稳重出 4 次 0 次变好】。
- 通过的段记为 auto_kept（待人工看片）；硬伤两次不过，该链停下等人。
- 防休眠：macOS 自动 caffeinate；笔记本接电源别合盖。到点要停可用 `tools/stop_at.py --pid <批量进程> --at 07:40`（优雅停 + 只恢复已提交的任务）。
- 同一 `--tag` 断点续跑；换 tag 时旧保留片移到 `07_clips/_pre_<tag>/`。

## 5. 数字（《越线》实测）
| 项 | 值 |
|---|---|
| 单段云端用时 | 中位 13 分钟，最长 18 分钟 |
| 一晚产能 | 并发 4，约 85 段（≈10 集） |
| 费用 | 768p 空闲 ¥0.45/段；一晚约 ¥40；E31–E40 重出率 7% |
| 文件 | 每段约 11 MB；768p 竖 = 768×1344，24fps，15.1 s，带音轨 |

## 6. 链与并行
- HARD_CUT 段互不依赖，可以并行（段缝 v2 的附带好处：出片更快）。
- TAIL_RELAY 段必须等上一段 accept（要用它的尾帧）。
- 新集先跑链头和难段（打斗、多人、长对白），通过后再放量。

## 7. 在 RunningHub 上测试（可选）
RunningHub 网页画布（rhtv.runninghub.ai）的 "MiniMax H3 RH Enhanced" 会员 00:00–10:00 免费（界面"预计消耗 0"），适合做写法对照；注意：只认 6 张参考图、5 图 + 2 音频时音频不附上、提示词里的 `<Picture N>` 要换成输入框 `@` 选出的"图片N"芯片、必须确认网址是 `model=476` 且预计消耗 0。正式出片仍走 AutoDL。
