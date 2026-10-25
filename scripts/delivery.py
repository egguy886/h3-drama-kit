"""交付标准（delivery.json）：按集号返回该集用的标准。E31 起 TikTok 海外 v1，之前沿用旧标准。"""
import json, os, re
PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def profile(ep):
    d = json.load(open(os.path.join(PIPE, "delivery.json"), encoding="utf-8"))
    n = int(re.sub(r"\D", "", os.path.basename(str(ep))) or 0)
    return dict(d["legacy"], **(d["standard"] if n >= d["from_episode"] else {}))


def safe_box(prof, W, H):
    """可放关键信息的区域 (x0, y0, x1, y1)；旧标准返回整幅画面。"""
    s = prof.get("safe")
    if not s:
        return 0, 0, W, H
    return int(s["left"] * W), int(s["top"] * H), int((1 - s["right"]) * W), int((1 - s["bottom"]) * H)
