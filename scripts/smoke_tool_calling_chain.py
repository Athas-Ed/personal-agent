from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is on sys.path so `import src.*` works
_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from langchain_core.messages import HumanMessage

from src.core.config import get_settings
from src.core.tools_agent_chain import build_tools_agent_chain


def main() -> int:
    s = get_settings()
    chain = build_tools_agent_chain(s)
    res = chain.invoke(
        {
            "session_messages": [],
            "user_input": "你好，简要介绍你能做什么。",
            "extra_tools": None,
            "include_mcp_tools": False,
            "include_local_tools": True,
            "max_tool_iters": 2,
        }
    )
    out = res["output"]
    # Windows 控制台可能是 GBK；这里用 backslashreplace 避免因 emoji 等字符导致崩溃
    safe = (out.final_text or "").strip()[:200].encode("ascii", errors="backslashreplace").decode("ascii")
    print("final_text:", safe)
    print("n_events:", len(out.events))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

