#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""兼容入口：分发逻辑已迁移到 skill-distributor 插件，保留此路径引用不失效。"""

import os
import runpy
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_target = os.path.join(
    _here, "..", "plugins", "skill-distributor",
    "skills", "skill-distributor", "scripts", "skill_distributor.py")

if not os.path.isfile(_target):
    print(f"找不到 skill_distributor.py：{_target}")
    sys.exit(2)

sys.argv[0] = _target
runpy.run_path(_target, run_name="__main__")
