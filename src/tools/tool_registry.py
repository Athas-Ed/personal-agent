from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from langchain_core.tools import BaseTool

from src.core.config import Settings
from src.tools.local_tools import build_local_tools


@dataclass(frozen=True)
class ToolsBundle:
    tools: List[BaseTool]
    mcp_loaded: bool


def _dedupe_tools(tools: List[BaseTool]) -> List[BaseTool]:
    seen: set[str] = set()
    out: List[BaseTool] = []
    for t in tools:
        n = getattr(t, "name", "") or ""
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(t)
    return out


def build_tools_bundle(
    settings: Settings,
    *,
    extra_tools: Optional[List[BaseTool]] = None,
    include_mcp_tools: bool = True,
    include_local_tools: bool = True,
) -> ToolsBundle:
    """
    统一的 tools 注册入口（注册表模式）：
    - extra_tools：业务侧临时注入（例如基于 session 的 export tool）
    - include_mcp_tools：是否加载 MCP tools（可由 settings/env 控制）
    - include_local_tools：是否加载本地工具（merge/expand/可选插件等）
    """

    all_tools: List[BaseTool] = []
    if extra_tools:
        all_tools.extend(extra_tools)

    mcp_loaded = False
    if include_mcp_tools and bool(getattr(settings, "mcp_enable", True)):
        try:
            from src.tools.mcp_tools import load_mcp_tools

            all_tools.extend(load_mcp_tools(settings=settings, force_refresh=False))
            mcp_loaded = True
        except Exception:
            mcp_loaded = False

    if include_local_tools:
        all_tools.extend(build_local_tools(settings))

    all_tools = _dedupe_tools(all_tools)
    return ToolsBundle(tools=all_tools, mcp_loaded=mcp_loaded)

