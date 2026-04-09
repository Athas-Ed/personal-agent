from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path so `import src.*` works
_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.core.config import get_settings
from src.services.mcp_client import MCPClientService


def main() -> int:
    """
    CLI: 调用本地 stdio MCP server 的 list_study_files 工具并打印结果。

    用法：
      venv\\Scripts\\python scripts\\mcp_list_study_files.py
    """
    s = get_settings()
    mcp = MCPClientService.get_instance(settings=s)
    res = mcp.call_tool(
        "list_study_files",
        {
            "exts": [".md", ".txt", ".pdf"],
            "limit": 200,
            "contains": "",
        },
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

