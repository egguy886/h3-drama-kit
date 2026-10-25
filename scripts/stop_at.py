#!/usr/bin/env python3
"""到点优雅停止批量进程，然后只恢复（下载/质检/保留）云端已提交的任务，不再提交任何新任务。

用法：python3 tools/stop_at.py --pid 49357 --at 07:40 --log batch_run.log
步骤：
1. 睡到 --at；
2. 等到「没有正在提交的请求」的空档（日志里 提交中… 的次数 == 任务/✗ 的次数）再发 SIGINT，避免请求发出但任务号没记下；
3. 等进程退出；
4. 运行 `h3_batch.py run --recover-only`：等云端任务完成 → 下载 → 质检 → 保留；
5. 运行 batch_relabel.py 按新阈值清理 ⚠；写 status。
全程日志写到 stop_at.log。
"""
import argparse, datetime, os, re, signal, subprocess, sys, time

ap = argparse.ArgumentParser()
ap.add_argument("--pid", type=int, required=True)
ap.add_argument("--at", required=True)
ap.add_argument("--log", default="batch_run.log")
ap.add_argument("--tag", default="768p-v1")
ap.add_argument("--eps", default="E01-E20", help="集范围，恢复/状态阶段用（原先写死 E01-E20，E21 起必须传）")
a = ap.parse_args()
PIPE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PIPE)


def say(m):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {m}", flush=True)


def alive(pid):
    try:
        os.kill(pid, 0); return True
    except OSError:
        return False


hh, mm = map(int, a.at.split(":"))
go = datetime.datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0)
if go <= datetime.datetime.now():                     # 已过今天的这个点 → 取下一次（明早）
    go += datetime.timedelta(days=1)
say(f"等到 {go:%H:%M} 停止进程 {a.pid}")
while datetime.datetime.now() < go:
    if not alive(a.pid):
        say("进程已提前退出"); break
    time.sleep(10)

if alive(a.pid):
    t0 = time.time()
    while time.time() - t0 < 180:                       # 最多等 3 分钟的空档
        txt = open(a.log, encoding="utf-8", errors="replace").read()
        starts = len(re.findall(r"提交中…", txt)); done = len(re.findall(r"/en 任务 ", txt)) + len(re.findall(r"提交被拒绝|提交时连接异常", txt))
        if starts == done:
            break
        time.sleep(0.3)
    say(f"发送停止信号（提交中 {starts} / 已记任务 {done}）")
    os.kill(a.pid, signal.SIGTERM)                      # 新版批量进程会优雅停止；旧版（忽略 SIGINT 的后台进程）也会被终止，在途任务由恢复模式接手
    for _ in range(600):                                # 优雅停止要等在途任务下载完，最多 10 分钟
        if not alive(a.pid): break
        time.sleep(1)
    say("进程已退出" if not alive(a.pid) else "进程仍在运行！未能停止")
    if alive(a.pid): sys.exit(2)

say("开始只恢复模式：等云端任务完成并下载质检")
r = subprocess.run([sys.executable, "tools/h3_batch.py", "run", a.eps, "--root", "..", "--tag", a.tag, "--recover-only", "--yes", "--timeout", "2400"],
                   capture_output=True, text=True)
open("recover_run.log", "w", encoding="utf-8").write(r.stdout + "\n" + r.stderr)
say(f"恢复完成（退出码 {r.returncode}）：" + (r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""))
r = subprocess.run([sys.executable, "tools/batch_relabel.py", a.tag], capture_output=True, text=True)
say("重新标注：" + r.stdout.strip())
r = subprocess.run([sys.executable, "tools/h3_batch.py", "status", a.eps, "--tag", a.tag], capture_output=True, text=True)
say("最终状态：" + (r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""))
say("全部完成")
