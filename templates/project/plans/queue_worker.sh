#!/bin/zsh
# 出片队列：E02–E20 按集号顺序，只要某集已编译（episodes/Exx/plan.json）且还有段没出，就整集顺序出片（U24，一采 0.4MP × 二采 1.5，自动质检、FAIL 换种子重出）。
# 分镜写好一集就自动接上；服务器不空转。停掉：touch queue_stop 或 pkill -f queue_worker。
cd "$(dirname "$0")/.."; rm -f queue_stop
while [[ ! -f queue_stop ]]; do
  work=0
  for n in $(seq 2 20); do
    ep=$(printf E%02d $n)
    [[ -f episodes/$ep/plan.json ]] || continue
    todo=$(python3 - <<PY
import json,os
ep="$ep"; segs=len(json.load(open(f"episodes/{ep}/plan.json"))["segments"]); d=f"episodes/{ep}/07_clips"
have=[f for f in os.listdir(d) if f.startswith(f"{ep}_seg") and "_r1" in f] if os.path.isdir(d) else []
done={f.split("_")[1] for f in have}
print(segs-len(done))
PY
)
    if [[ $todo -gt 0 ]]; then
      echo "=== $(date '+%m-%d %H:%M:%S') $ep 出片（还差 $todo 段）"
      python3 tools/comfy_run.py batch $ep --tag r1
      work=1; break
    fi
  done
  [[ $work -eq 0 ]] && sleep 60
done
echo "=== QUEUE_STOP $(date '+%m-%d %H:%M:%S')"
