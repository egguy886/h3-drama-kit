# 17 · Colab G4 零人工值守 NVMe 直拉出片（免 Drive 授权版）

【量产验证】除了 AutoDL 云端（`playbook/06`）与常开自有 ComfyUI 服务器（`playbook/11`）之外，工具包原生提供第 3 条出片通道：**Google Colab G4（NVIDIA RTX PRO 6000 Blackwell · 98GB VRAM）本地 NVMe 直拉权重零值守出片**（`scripts/colab_g4_run.py`）。

---

## 一、 为什么严禁在 Agent 自动化中使用 `colab drivemount`？

踩坑实证（2026-11）：
1. **每次新建虚拟机都会卡死在浏览器一次性授权**：`colab drivemount` 采用 `authorize-for-drive-credentials-ephem` 临时端点鉴权，每次 `colab new` 分配新机器都会弹出浏览器 OAuth 页面并阻塞标准输入等待人工回车，一旦无人点击，20 分钟后实例即被空闲回收。
2. **Google Drive FUSE 读取 42GB 权重极慢**：通过网络虚拟文件系统首次把 `Qwen3-VL-32B` 与 `MiniMax-H3` 读入显存常卡顿 3–5 分钟。
3. **NVMe 直拉快 5–10 倍且全程零人工点击**：在 Colab 机房内用 `aria2c -x 16 -s 16` 直接从 HuggingFace 官方仓库（`Comfy-Org/MiniMax-H3`）拉取全部 5 个核心权重（共 `42.04 GB`）到本地 NVMe 固态盘，**实测仅需约 130 秒（持续 310+ MB/s）**，随后秒级载入 98GB 显存。

---

## 二、 三大必守铁律（Agent 执行红线）

1. **付费开机前先 `--dry-run` 报账等制片人同意**：
   - 先跑 `python3 tools/colab_g4_run.py E01 --all --dry-run`，向用户汇报 `段数 × 分辨率（1344×768 / 768×1344）× 单段时长 × 预估 G4 时长`（768p 约 `7.5–8 分钟/段` + 环境拉取 `2.5 分钟`），获得明确许可后再开机。
2. **防 Colab 20 分钟空闲回收（Anti-Idle Reaper）**：
   - 远端渲染采用后台守护进程（`start_new_session=True`）防本地代理 WebSocket 断连中断采样；**同时本地或调度器必须每 ≤7–8 分钟发送一次 `colab exec` 状态巡检心跳**，绝不能让远端 Jupyter Kernel 连续空闲超过 15 分钟！
   - 每渲染完一段，立即用 `colab download` 增量回传至本地 `episodes/<EP>/07_clips/`，确保任何网络波动下已出成片零丢失。
3. **跑完必销毁实例并核验零残留**：
   - 下载完成后**立即执行 `colab stop -s <session>`**，并跑 `colab sessions` 确认输出 `[colab] No active sessions found on server.`，严禁留空转 GPU 消耗算力配额。

---

## 三、 标准命令速查

```bash
# 1. 打包预检（免费，检查所有母图与 .wav 声线齐全并估算耗时）
python3 tools/colab_g4_run.py E01 --all --dry-run

# 2. 先锋测试前 3 段并自动无损拼接预览片（跑完自动关机）
python3 tools/colab_g4_run.py E01 --seg 1 2 3 --stitch

# 3. 整集无人值守批量出片（若本机走代理，先导出 HTTP_PROXY / HTTPS_PROXY）
export HTTP_PROXY=http://127.0.0.1:7897 HTTPS_PROXY=http://127.0.0.1:7897
python3 tools/colab_g4_run.py E01 --all --stitch
```

---

## 四、 自动直拉的 5 个官方权重清单（`Comfy-Org/MiniMax-H3`）

| 目录 | 权重文件 | 体积 |
|---|---|---|
| `vae/` | `minimax_h3_video_vae_int8_convrot.safetensors` | 2.81 GB |
| `vae/` | `minimax_h3_audio_vae_fp32.safetensors` | 0.61 GB |
| `diffusion_models/` | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | 20.97 GB |
| `loras/` | `pika_h3_flex_ref2va_v1_bf16.safetensors` | 1.96 GB |
| `text_encoders/` | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | 15.69 GB |
