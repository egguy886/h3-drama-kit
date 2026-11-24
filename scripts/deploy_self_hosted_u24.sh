#!/usr/bin/env bash
# ==============================================================================
# 《沉香如局》首要生产工作流：API-U24-文武双修T8版 一键自建 ComfyUI 部署脚本
# 适用环境：AutoDL / 自有 Ubuntu GPU 服务器 / RunPod / Colab（建议显存 ≥ 32GB，推荐 48–98GB）
# 用法：
#   COMFY_DIR=/root/autodl-tmp/ComfyUI bash tools/deploy_self_hosted_u24.sh
# ==============================================================================
set -euo pipefail

COMFY_DIR="${COMFY_DIR:-$HOME/ComfyUI}"
PORT="${PORT:-8188}"

echo "[1/5] 检查基础工具 (git / aria2c / ffmpeg) ..."
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -qq || apt-get update -qq || true
  sudo apt-get install -y -qq git aria2 ffmpeg || apt-get install -y -qq git aria2 ffmpeg
fi

echo "[2/5] 部署 ComfyUI 主程序 -> $COMFY_DIR ..."
if [ ! -d "$COMFY_DIR" ]; then
  git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git "$COMFY_DIR"
  pip install -r "$COMFY_DIR/requirements.txt"
fi

echo "[3/5] 安装 T8 核心双采音视频插件与 VHS 视频合成插件 ..."
mkdir -p "$COMFY_DIR/custom_nodes"
if [ ! -d "$COMFY_DIR/custom_nodes/minimax-h3-audio-T8" ]; then
  git clone --depth 1 https://github.com/T8mars/comfyui-minimax-h3-audio-T8.git "$COMFY_DIR/custom_nodes/minimax-h3-audio-T8"
fi
if [ ! -d "$COMFY_DIR/custom_nodes/ComfyUI-VideoHelperSuite" ]; then
  git clone --depth 1 https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git "$COMFY_DIR/custom_nodes/ComfyUI-VideoHelperSuite"
  pip install -r "$COMFY_DIR/custom_nodes/ComfyUI-VideoHelperSuite/requirements.txt"
fi

dl() {
  local rel="$1"
  local url="$2"
  local dst="$COMFY_DIR/models/$rel"
  mkdir -p "$(dirname "$dst")"
  if [ -f "$dst" ] && [ "$(stat -c%s "$dst" 2>/dev/null || stat -f%z "$dst")" -gt 5000000 ]; then
    echo "  [已存在跳过] $rel"
    return
  fi
  echo "  [16线程高速拉取] $rel ..."
  aria2c -x 16 -s 16 -k 16M --console-log-level=warn -d "$(dirname "$dst")" -o "$(basename "$dst")" "$url"
}

echo "[4/5] 拉取 U24 文武双修 T8 全部 11 个已核验模型权重 (~46 GB) ..."
dl "vae/minimax_h3_video_vae_fp16.safetensors" \
   "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_video_vae_fp16.safetensors"
dl "vae/minimax_h3_audio_vae_fp32.safetensors" \
   "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_audio_vae_fp32.safetensors"
dl "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors" \
   "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
dl "diffusion_models/minimax/minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors" \
   "https://huggingface.co/smhfacct/Minimax-H3-fl2va-ref2va-hybrid-models/resolve/main/minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors"
dl "latent_upscale_models/minimax_h3_latent_upscaler_3d_fp16.safetensors" \
   "https://huggingface.co/Konteni2/Minimax_h3_latent_Upscaler/resolve/main/minimax_h3_latent_upscaler_3d_fp16.safetensors"
dl "loras/minimax/minimax_h3_fl2v_turbo_4step_v1.2_768p_comfyui_bf16.safetensors" \
   "https://huggingface.co/lightx2v/MiniMax-H3-Turbo/resolve/main/minimax_h3_fl2v_turbo_4step_v1.2_768p_comfyui_bf16.safetensors"
dl "loras/minimax/H3_Combat_V2.safetensors" \
   "https://huggingface.co/JOKER141/MiniMax-H3-Combat-Base-V2/resolve/main/H3_Combat_V2.safetensors"
dl "loras/minimax/minimax_h3_turbo_v4_step600_ema_DasiwaREF2VAHybridV1_0_curveproj1025_compat_v001.safetensors" \
   "https://huggingface.co/t8star/minimax_h3_turbo_v4_step600_ema_DasiwaREF2VAHybridV1_0_curveproj1025_compat_v001/resolve/main/minimax_h3_turbo_v4_step600_ema_DasiwaREF2VAHybridV1_0_curveproj1025_compat_v001.safetensors"
dl "loras/minimax/minimax_h3_turbo_4step_10ErosMax_test4_pruned_curveproj1025_exp_v001-T8.safetensors" \
   "https://huggingface.co/t8star/minimax_h3_turbo_4step_10ErosMax_test4_pruned_curveproj1025_T8/resolve/main/minimax_h3_turbo_4step_10ErosMax_test4_pruned_curveproj1025_exp_v001-T8.safetensors"
dl "loras/minimax/Motion_Repair.safetensors" \
   "https://huggingface.co/JOKER141/MiniMax-H3-General-Motion-Continuity-Repair/resolve/main/Motion_Repair.safetensors"
# 同时保留原中文名与 ASCII 软链，确保画布版与 API 脚本版 100% 兼容
dl "loras/minimax/MinimaxH3真实电影质感V0.1.safetensors" \
   "https://huggingface.co/orangesouth/MinimaxH3CinematicRealism/resolve/main/Minimax%20H3%E7%9C%9F%E5%AE%9E%E7%94%B5%E5%BD%B1%E8%B4%A8%E6%84%9FV0.1.safetensors"
ln -sf "$COMFY_DIR/models/loras/minimax/MinimaxH3真实电影质感V0.1.safetensors" \
       "$COMFY_DIR/models/loras/minimax/MinimaxH3_CinematicRealism_V0.1.safetensors"

mkdir -p "$COMFY_DIR/models/upscale_models"
ln -sf "$COMFY_DIR/models/latent_upscale_models/minimax_h3_latent_upscaler_3d_fp16.safetensors" \
       "$COMFY_DIR/models/upscale_models/minimax_h3_latent_upscaler_3d_fp16.safetensors"

echo "[5/5] U24 文武双修 T8 环境部署完成！启动命令："
echo "  python3 $COMFY_DIR/main.py --listen 0.0.0.0 --port $PORT --preview-method none"
