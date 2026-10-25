#!/usr/bin/env python3
"""多人动作顺序检查（已并入 tools/shot_lint.py，这里保留旧入口）。
用法：python3 tools/group_lint.py E21-E30
"""
import os, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.exit(subprocess.call([sys.executable, os.path.join(here, "shot_lint.py"), *sys.argv[1:], "--only", "group"]))
