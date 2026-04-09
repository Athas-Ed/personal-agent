from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool

from src.core.config import Settings
from src.core.tools_agent_chain import build_tools_agent_chain


@dataclass(frozen=True)
class ToolEvent:
    tool_name: str
    tool_args: dict
    ok: bool
    result_preview: str


@dataclass(frozen=True)
class AgentRunResult:
    output: str
    tool_events: List[ToolEvent]
    mcp_tools_loaded: bool
    tool_names: List[str]


def _to_chat_history(messages: List[dict]) -> List[BaseMessage]:
    """
    将 Streamlit session 中的 {"role","content"} 转成 LangChain messages。
    仅保留 user/assistant；工具消息由 AgentExecutor 内部处理。
    """
    out: List[BaseMessage] = []
    for m in messages or []:
        role = (m.get("role") or "").strip()
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            out.append(HumanMessage(content=content))
        elif role == "assistant":
            out.append(AIMessage(content=content))
    return out


def run_with_tools_agent(
    settings: Settings,
    user_input: str,
    *,
    session_messages: Optional[List[dict]] = None,
    tools: Optional[List[BaseTool]] = None,
    include_mcp_tools: bool = True,
    include_local_tools: bool = True,
    max_tool_iters: int = 6,
    runnable_config: Any | None = None,
) -> AgentRunResult:
    """
    轻量工具调用循环（Tool-Calling）：
    - 使用 LangChain Tools schema 绑定到 Chat 模型
    - 若模型返回 tool_calls，则逐个执行工具并回填 ToolMessage
    - 直到模型不再请求工具或达到 max_tool_iters

    说明：
    - 这不是 LangChain 旧版 AgentExecutor（你当前安装的 langchain 1.x 已移除/重构相关接口）
    - 但仍然是标准的 LangChain Tool 体系：BaseTool + bind_tools + ToolMessage
    """
    chain = build_tools_agent_chain(settings)
    res = chain.invoke(
        {
            "session_messages": session_messages or [],
            "user_input": user_input,
            "extra_tools": tools,
            "include_mcp_tools": include_mcp_tools,
            "include_local_tools": include_local_tools,
            "max_tool_iters": max_tool_iters,
        },
        config=runnable_config,
    )
    out = res["output"]
    bundle = res["bundle"]
    last_text = out.final_text
    events: List[ToolEvent] = [
        ToolEvent(tool_name=e.tool_name, tool_args=e.tool_args, ok=e.ok, result_preview=e.result_preview)
        for e in out.events
    ]

    return AgentRunResult(
        output=last_text,
        tool_events=events,
        mcp_tools_loaded=bundle.mcp_loaded,
        tool_names=[t.name for t in bundle.tools],
    )


def answer_with_tools_agent(
    settings: Settings,
    user_input: str,
    *,
    session_messages: Optional[List[dict]] = None,
    tools: Optional[List[BaseTool]] = None,
    include_mcp_tools: bool = True,
    include_local_tools: bool = True,
    max_tool_iters: int = 6,
    runnable_config: Any | None = None,
) -> str:
    return run_with_tools_agent(
        settings,
        user_input,
        session_messages=session_messages,
        tools=tools,
        include_mcp_tools=include_mcp_tools,
        include_local_tools=include_local_tools,
        max_tool_iters=max_tool_iters,
        runnable_config=runnable_config,
    ).output