"""把"设备里的声音"（广播、电视、电话、耳麦、画外 O.S.）从台词锁定移到 post_audio.json（后期配音，不进 H3 对白），剩下的台词重新编号。
登记表：plans/post_moves.json = {"E01": {"L2": ["E01-PA1", "Announcer", "pa_stadium", "场2 广播"]}, …}
   值 = [post_id, 声音（角色名或 designed_voices 里的名字）, 设备音色（pa / pa_stadium / terminal / recorder / phone / tv / vo / crowd）, 位置说明]
注意：重跑 lock_dialogue.py 会把这些台词放回来，之后要再跑本脚本。可重复运行。"""
import json, os, shutil

PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOVES = json.load(open(os.path.join(PIPE, "plans", "post_moves.json"), encoding="utf-8"))
pa_p = os.path.join(PIPE, "post_audio.json"); pa = json.load(open(pa_p, encoding="utf-8"))
have = {l["id"] for l in pa["lines"]}
os.makedirs(os.path.join(PIPE, "_archive"), exist_ok=True)
shutil.copy(pa_p, os.path.join(PIPE, "_archive", "post_audio_before_move.json"))
for ep, table in sorted(MOVES.items()):
    p = os.path.join(PIPE, "episodes", ep, "02_dialogue_lock.json"); d = json.load(open(p, encoding="utf-8"))
    if d.get("post_audio_moved"):
        print(ep, "已移过，跳过"); continue
    keep, moved = [], []
    for x in d["lines"]:
        m = table.get(x["id"])
        if m:
            moved.append({"old_id": x["id"], "post_id": m[0], "speaker": x["speaker"], "text_en": x["text_en"]})
            if m[0] not in have:
                pa["lines"].append({"id": m[0], "episode": ep, "voice": m[1], "fx": m[2], "where": m[3], "text": x["text_en"]}); have.add(m[0])
        else:
            keep.append(x)
    for i, x in enumerate(keep, 1):
        x["id"] = f"L{i}"
    d["lines"] = keep; d["post_audio_moved"] = moved
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(ep, "移出", len(moved), "句，剩", len(keep), "句")
json.dump(pa, open(pa_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
