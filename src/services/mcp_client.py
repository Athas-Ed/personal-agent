from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import json

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from src.utils.sync import run_sync


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    command: str
    args: List[str]
    transport: str = "stdio"


class MCPClientService:
    """
    MCP 客户端服务（单例）：
    - 管理到 MCP Server 的连接（MultiServerMCPClient）
    - 缓存服务器提供的工具列表，减少 list_tools 频率
    """

    _instance: "MCPClientService | None" = None

    def __init__(self, server: MCPServerConfig, tools_ttl_s: int = 60):
        self._server = server
        self._tools_ttl_s = tools_ttl_s
        self._client: MultiServerMCPClient | None = None
        self._tools_cache: List[BaseTool] | None = None
        self._tools_cached_at: float | None = None

    @classmethod
    def get_instance(cls, *, settings: "Optional[object]" = None) -> "MCPClientService":
        if cls._instance is None:
            repo_root = Path(__file__).resolve().parents[2]
            # MCP server 入口（优先 src/ 下的主入口；root/mcp/server.py 仅为兼容转发）
            server_py = repo_root / "src" / "mcp" / "server.py"

            python_exe = ""
            tools_ttl_s = 60
            try:
                # Avoid hard dependency on Settings type here; keep mcp_client service reusable.
                python_exe = str(getattr(settings, "mcp_python", "") or "").strip()
                tools_ttl_s = int(getattr(settings, "mcp_tools_ttl_s", 60) or 60)
            except Exception:
                python_exe = ""
                tools_ttl_s = 60

            if not python_exe:
                python_exe = os.getenv("MCP_PYTHON", "").strip()
            if not python_exe:
                # 默认显式使用当前项目 venv 的 python，避免子进程找不到依赖
                candidate = repo_root / "venv" / "Scripts" / "python.exe"
                python_exe = str(candidate) if candidate.exists() else "python"

            server = MCPServerConfig(
                name="personal-workbench-mcp",
                command=python_exe,
                args=[str(server_py)],
                transport="stdio",
            )
            cls._instance = MCPClientService(server=server, tools_ttl_s=tools_ttl_s)
        return cls._instance

    def _ensure_client(self) -> MultiServerMCPClient:
        if self._client is None:
            cfg: Dict[str, Dict[str, Any]] = {
                self._server.name: {
                    "command": self._server.command,
                    "args": self._server.args,
                    "transport": self._server.transport,
                }
            }
            self._client = MultiServerMCPClient(cfg)
        return self._client

    async def aget_tools(self, force_refresh: bool = False) -> List[BaseTool]:
        now = time.time()
        if (
            (not force_refresh)
            and self._tools_cache is not None
            and self._tools_cached_at is not None
            and (now - self._tools_cached_at) < self._tools_ttl_s
        ):
            return self._tools_cache

        client = self._ensure_client()
        tools = await client.get_tools()
        self._tools_cache = list(tools)
        self._tools_cached_at = now
        return self._tools_cache

    def get_tools(self, force_refresh: bool = False) -> List[BaseTool]:
        return run_sync(self.aget_tools(force_refresh=force_refresh))

    async def acall_tool(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> Any:
        tools = await self.aget_tools()
        for t in tools:
            if t.name == tool_name:
                result = await t.ainvoke(args or {})
                # langchain-mcp-adapters often returns a list of message blocks like:
                # [{"type":"text","text":"{...json...}", ...}]
                if isinstance(result, list) and result:
                    first = result[0]
                    if isinstance(first, dict) and first.get("type") == "text" and isinstance(first.get("text"), str):
                        text = first["text"].strip()
                        if text.startswith("{") and text.endswith("}"):
                            try:
                                return json.loads(text)
                            except Exception:
                                return result
                return result
        raise KeyError(f"未找到 MCP 工具：{tool_name}")

    def call_tool(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> Any:
        return run_sync(self.acall_tool(tool_name=tool_name, args=args))

