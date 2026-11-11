#!/bin/zsh
# 出片队列：先清返工队列（plans/reroll.py），再按 E02–E30 按集号顺序，只要某集已编译（episodes/Exx/plan.json）且还有段没出，就整集顺序出片（U24，一采 0.4MP × 二采 1.5，自动质检、FAIL 换种子重出）。
# 分镜写好一集就自动接上；服务器不空转。停掉：touch queue_stop 或 pkill -f queue_worker。
cd "$(dirname "$0")/.."; rm -f queue_stop
while pgrep -f "comfy_run.py batch" >/dev/null; do sleep 30; done   # 重启时先等正在跑的批次结束，免得同一集被两个进程同时出
while [[ ! -f queue_stop ]]; do
  work=0
  if python3 plans/reroll.py has; then              # 返工段优先（plans/reroll_queue.jsonl）
    python3 plans/reroll.py next; continue
  fi
  for n in $(seq 2 40); do
    ep=$(printf E%02d $n)
    [[ -f episodes/$ep/plan.json && -f episodes/$ep/READY ]] || continue
    todo=$(python3 - <<PY
import json,os
ep="$ep"; segs=len(json.load(open(f"episodes/{ep}/plan.json"))["segments"]); d=f"episodes/{ep}/07_clips"
have=[f for f in os.listdir(d) if f.startswith(f"{ep}_seg") and "_r1" in f] if os.path.isdir(d) else []
done={f.split("_")[1] for f in have}
try:
    ch=json.load(open(f"episodes/{ep}/chosen.json"))      # 已选定（返工替换过、原 r1 被清理）也算出过
    for k,v in ch.items():
        if os.path.exists(v): done.add("seg%02d"%int(k.split(":")[-1]))
except Exception: pass
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
