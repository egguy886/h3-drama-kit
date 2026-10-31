#!/usr/bin/env python3
"""全剧收尾盘点（只读，不花钱）：停服务器、交后期之前跑一次。
查：每集有没有成片和音轨、每段有没有采用版、成片是不是用的当前采用版、采用版还有没有质检 FAIL。
用法（项目根目录）：python3 tools/audit_final.py [E01 E02 …]
有问题退出码 1。质检 FAIL 要逐条核对转写：可能是真多念了话，也可能是误报。
"""
import glob, json, os, subprocess, sys

PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PIPE, "tools"))
import qc_lib as q


def main():
    os.chdir(PIPE)
    eps = sys.argv[1:] or sorted(os.path.basename(d) for d in glob.glob("episodes/E??") if os.path.isfile(f"{d}/plan.json"))
    total, secs, bad = 0, 0.0, []
    for ep in eps:
        d = f"episodes/{ep}"
        p = json.load(open(f"{d}/plan.json", encoding="utf-8"))
        segs = p.get("segments") or p.get("segs") or p
        total += len(segs)
        cuts = glob.glob(f"{d}/08_edit/{ep}_cut_*.mp4")
        if not cuts:
            bad.append(f"{ep}：没有成片"); continue
        last = max(cuts, key=os.path.getmtime)
        info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:format=duration", "-of", "json", last],
                                         capture_output=True, text=True).stdout)
        secs += float(info["format"]["duration"])
        if not any(s["codec_type"] == "audio" for s in info["streams"]):
            bad.append(f"{ep}：{os.path.basename(last)} 没有音轨")
        side = last[:-4] + ".json"
        used = open(side, encoding="utf-8").read() if os.path.isfile(side) else ""
        ledger = q.ledger_read(ep)
        for n in range(1, len(segs) + 1):
            a = f"{d}/07_clips/seg{n:02d}_accepted.mp4"
            if not os.path.exists(a):
                bad.append(f"{ep} Seg{n}：没有采用版（或链接已断）"); continue
            name = os.path.basename(os.path.realpath(a))
            if used and name[:-4] not in used:
                bad.append(f"{ep} Seg{n}：{os.path.basename(last)} 没用当前采用版 {name}，要重拼")
            rec = [r for r in ledger if os.path.basename(str(r.get("clip", ""))) == name]
            if rec and rec[-1].get("status") == "FAIL":
                bad.append(f"{ep} Seg{n}：采用版质检 FAIL {rec[-1].get('issues')}")
    print(f"{len(eps)} 集 {total} 段，最新成片共 {secs / 60:.1f} 分钟")
    print("\n".join(bad) if bad else "没有发现问题")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
