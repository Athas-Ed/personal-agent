"""
Python 启动时自动导入的模块（若在 sys.path 上）。

用途：保证所有入口（Streamlit/MCP server/CLI scripts 等）在最早阶段统一加载 `.env`
并清理无效 CA 环境变量（例如 `$ca`）。

注意：这里必须“安全失败”，不能因为导入路径问题影响程序启动。
"""

from __future__ import annotations

try:
    from src.utils.env import apply_runtime_env

    apply_runtime_env()
except Exception:
    # Never block interpreter startup.
    pass

