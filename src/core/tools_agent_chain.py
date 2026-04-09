from __future__ import annotations

from typing import Any, List, Optional

from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.tools import BaseTool

from src.core.llm import build_chat_llm
from src.core.prompts import build_tools_agent_system_message
from src.core.message_chain import build_messages_runnable
from src.core.tool_calling_chain import ToolCallingLoopOutput, build_tool_calling_loop
from src.core.config import Settings
from src.tools.tool_registry import ToolsBundle, build_tools_bundle


def build_tools_agent_chain(settings: Settings) -> Runnable[dict, dict]:
    """
    构建 tools-agent 的 LCEL 链路（更标准的“输入驱动”形态）。

    约定：链路输入（invoke 的 dict）支持：
    - session_messages: List[dict]
    - user_input: str
    - extra_tools: Optional[List[BaseTool]]（例如 session export tool）
    - include_mcp_tools: bool
    - include_local_tools: bool
    - max_tool_iters: int

    链路输出（dict）包含：
    - output: ToolCallingLoopOutput
    - bundle: ToolsBundle（给上层读取 mcp_loaded/tool_names）
    """
    system = build_tools_agent_system_message()
    build_msgs = build_messages_runnable()
    loop = build_tool_calling_loop()

    def _chain_inp(inp: dict) -> dict:
        extra_tools: Optional[List[BaseTool]] = inp.get("extra_tools")
        include_mcp_tools: bool = bool(inp.get("include_mcp_tools", True))
        include_local_tools: bool = bool(inp.get("include_local_tools", True))
        max_tool_iters: int = int(inp.get("max_tool_iters", 6) or 0)

        bundle = build_tools_bundle(
            settings,
            extra_tools=extra_tools,
            include_mcp_tools=include_mcp_tools,
            include_local_tools=include_local_tools,
        )
        llm = build_chat_llm(settings)
        llm_t = llm.bind_tools(bundle.tools)

        msgs = build_msgs.invoke(
            {
                "system": system,
                "session_messages": inp.get("session_messages") or [],
                "user_input": inp.get("user_input") or "",
            }
        )
        return {
            "loop_input": {"llm_with_tools": llm_t, "messages": msgs, "tools": bundle.tools, "max_tool_iters": max_tool_iters},
            "bundle": bundle,
        }

    def _run(inp: dict) -> dict:
        packed = _chain_inp(inp)
        out: ToolCallingLoopOutput = loop.invoke(packed["loop_input"])
        return {"output": out, "bundle": packed["bundle"]}

    return RunnableLambda(_run)

