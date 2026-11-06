#!/bin/zsh
# 把一集的各段拼成一条看片用的片子（统一 1080×1920 Lanczos、响度 -16、48kHz）。还没加 V.O.、叠字、字幕、配乐。
# 用法：plans/stitch_ep.sh E02 [输出路径]    每段取 episodes/E02/chosen.json 的 "u24:N"，没有就取质检账本里的最佳版本，再没有就取最新的一条。
# 注意：zsh 里 $i:a 会被当成路径修饰符，下标一律写 ${i}。
cd "$(dirname "$0")/.."; ep=$1; out=${2:-review/compare/${ep}_raw.mp4}; n=$(python3 -c "import json;print(len(json.load(open('episodes/$ep/plan.json'))['segments']))")
inputs=(); chain=""; i=0
for ((s=1; s<=n; s++)); do
  sx=$(printf %02d $s)
  f=$(python3 -c "import sys;sys.path.insert(0,'tools');import qc_lib as Q;print(Q.best_clip('$ep',$s) or '')" 2>/dev/null)
  [[ -z $f || ! -f $f ]] && f=$(ls -t episodes/$ep/07_clips/${ep}_seg${sx}_*.mp4 2>/dev/null | head -1)
  c=$(python3 -c "import json,os;p='episodes/$ep/chosen.json';d=json.load(open(p)) if os.path.exists(p) else {};print(d.get('u24:$s',''))"); [[ -n $c && -f $c ]] && f=$c
  [[ -z $f ]] && { echo "缺 Seg$sx"; exit 1; }
  inputs+=(-i "$f"); chain+="[${i}:v]scale=1080:1920:flags=lanczos,setsar=1,fps=24[v$i];[${i}:a]aresample=48000,aformat=channel_layouts=stereo[a$i];"; i=$((i+1))
done
pairs=""; for ((k=0;k<i;k++)); do pairs+="[v$k][a$k]"; done
ffmpeg -y -loglevel error "${inputs[@]}" -filter_complex "${chain}${pairs}concat=n=$i:v=1:a=1[v][a0];[a0]loudnorm=I=-16:TP=-1.5,aresample=48000[a]" -map "[v]" -map "[a]" -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p -c:a aac -b:a 192k "$out"
echo "拼好 $out $(ffprobe -v error -show_entries format=duration -of csv=p=0 $out)s"
