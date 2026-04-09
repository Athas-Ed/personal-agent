from __future__ import annotations

from typing import Dict, List

from langchain_core.tools import BaseTool

from src.services.mcp_client import MCPClientService
from src.core.config import Settings


def load_mcp_tools(*, settings: Settings, force_refresh: bool = False) -> List[BaseTool]:
    """
    从 MCP server 拉取工具列表（内部带缓存）。
    用于后续注册到 Agent 的工具字典/工具列表中。
    """
    return MCPClientService.get_instance(settings=settings).get_tools(force_refresh=force_refresh)


def mcp_tools_dict(*, settings: Settings, force_refresh: bool = False) -> Dict[str, BaseTool]:
    return {t.name: t for t in load_mcp_tools(settings=settings, force_refresh=force_refresh)}

