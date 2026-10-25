#!/usr/bin/env python3
"""生成记账本：每次生成一行，之后统计"每个通过片段平均要生成几次"。只用标准库。

用法：
  python gen_ledger.py log   <ledger.jsonl> --seg 3 --outcome rejected --reason identity-drift [--seed 123] [--version seg03-v2.1] [--note ...]
  python gen_ledger.py ratio <ledger.jsonl>
outcome：kept | rejected | filtered
reason（rejected/filtered 时填，可多个，逗号分隔）：
  identity-drift  prop-error  space-error  gate-opened  extra-cuts  tail-collapse
  garbled-text  lip-sync  audio-jump  motion-artifact  weapon-flag  other
"""
import argparse, collections, datetime, json, sys

REASONS = {"identity-drift", "prop-error", "space-error", "gate-opened", "extra-cuts", "tail-collapse",
           "garbled-text", "lip-sync", "audio-jump", "motion-artifact", "weapon-flag", "other"}

ap = argparse.ArgumentParser()
ap.add_argument("cmd", choices=["log", "ratio"])
ap.add_argument("ledger")
ap.add_argument("--seg", type=int)
ap.add_argument("--outcome", choices=["kept", "rejected", "filtered"])
ap.add_argument("--reason", default="")
ap.add_argument("--seed")
ap.add_argument("--version", default="", help="提示词版本，如 seg03-v2.1；每次迭代只改一行")
ap.add_argument("--note", default="")
a = ap.parse_args()

if a.cmd == "log":
    if a.seg is None or a.outcome is None:
        sys.exit("log 需要 --seg 和 --outcome")
    reasons = [r for r in a.reason.split(",") if r]
    bad = [r for r in reasons if r not in REASONS]
    if bad:
        sys.exit(f"未知原因：{bad}；可用：{sorted(REASONS)}")
    row = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), "seg": a.seg, "outcome": a.outcome,
           "reasons": reasons, "seed": a.seed, "prompt_version": a.version, "note": a.note}
    with open(a.ledger, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("logged", row)
else:
    rows = [json.loads(x) for x in open(a.ledger, encoding="utf-8") if x.strip()]
    per = collections.defaultdict(lambda: collections.Counter())
    why = collections.Counter()
    for r in rows:
        per[r["seg"]][r["outcome"]] += 1
        for x in r["reasons"]:
            why[x] += 1
    print("| 段 | 生成次数 | 通过 | 每个通过需生成 |\n|---|---|---|---|")
    for seg in sorted(per):
        n = sum(per[seg].values()); k = per[seg]["kept"]
        print(f"| Seg{seg} | {n} | {k} | {n / k:.1f} |" if k else f"| Seg{seg} | {n} | 0 | — |")
    tot = sum(sum(c.values()) for c in per.values()); kept = sum(c["kept"] for c in per.values())
    print(f"\n合计 {tot} 次，通过 {kept} 次" + (f"，通过率 {kept / tot:.0%}" if tot else ""))
    if rows and len(rows) < 30:
        print("（样本少于 30 行，比例仅供参考）")
    print("失败原因排行：", ", ".join(f"{k}×{v}" for k, v in why.most_common()) or "—")
