"""
conftest.py — 测试目录共享的 pytest fixtures / sys.path 设置
"""

from __future__ import annotations

import os
import sys

# 把 lesson2/ 加入 sys.path，使 `import cot_demo` 等不依赖 pytest 的 rootdir
_LESSON2_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _LESSON2_DIR not in sys.path:
    sys.path.insert(0, _LESSON2_DIR)