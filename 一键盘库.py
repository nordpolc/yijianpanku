# -*- coding: utf-8 -*-
"""一键盘库 —— 入口。

双击运行，或：
    python 一键盘库.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from panku.ui import main  # noqa: E402

if __name__ == "__main__":
    main()
