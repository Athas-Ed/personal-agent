from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.tools import BaseTool


@dataclass(frozen=True)
class ToolEvent:
    tool_name: str
    tool_args: dict
    ok: bool
    result_preview: str


def tool_dict(tools: List[BaseTool]) -> Dict[str, BaseTool]:
    return {t.name: t for t in tools}


def normalize_tool_args(args: Any) -> dict:
    if args is None:
        return {}
    if isinstance(args, dict):
        return args
    if isinstance(args, str):
        s = args.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                v = json.loads(s)
                if isinstance(v, dict):
                    return v
            except Exception:
                return {"input": args}
        return {"input": args}
    return {"input": args}


def _preview_result(content: str, *, max_len: int = 400) -> str:
    preview = (content or "").replace("\n", " ").strip()
    if len(preview) > max_len:
        preview = preview[:max_len] + "…"
    return preview


def run_tool_calls_once(
    *,
    tool_calls: List[dict],
    tool_map: Dict[str, BaseTool],
) -> Tuple[List[ToolMessage], List[ToolEvent]]:
    msgs: List[ToolMessage] = []
    events: List[ToolEvent] = []
    for tc in tool_calls:
        name = str(tc.get("name") or "").strip()
        args = normalize_tool_args(tc.get("args"))
        tool = tool_map.get(name)
        call_id = str(tc.get("id") or name)

        if tool is None:
            msgs.append(ToolMessage(tool_call_id=call_id, content=f"ERROR: 未找到工具：{name}"))
            events.append(ToolEvent(tool_name=name, tool_args=args, ok=False, result_preview="未找到工具"))
            continue

        try:
            result = tool.invoke(args)
            content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            events.append(ToolEvent(tool_name=name, tool_args=args, ok=True, result_preview=_preview_result(content)))
        except Exception as e:
            content = f"ERROR: {e}"
            events.append(ToolEvent(tool_name=name, tool_args=args, ok=False, result_preview=_preview_result(str(e))))

        msgs.append(ToolMessage(tool_call_id=call_id, content=content))

    return msgs, events


@dataclass(frozen=True)
class ToolCallingLoopOutput:
    final_text: str
    messages: List[BaseMessage]
    events: List[ToolEvent]


def build_tool_calling_loop() -> Runnable[dict, ToolCallingLoopOutput]:
    """
    用 RunnableLambda 封装 tool-calling loop。
    目的：让“链路”成为可组合 Runnable（更贴近 LCEL 的表达方式），便于后续加 tracing/回放/测试。
    """

    def _run(inp: dict) -> ToolCallingLoopOutput:
        llm_with_tools: Runnable[List[BaseMessage], Any] = inp["llm_with_tools"]
        tools: List[BaseTool] = inp["tools"]
        msgs: List[BaseMessage] = list(inp["messages"])
        max_tool_iters: int = int(inp.get("max_tool_iters", 6) or 0)

        events: List[ToolEvent] = []
        tool_map = tool_dict(tools)
        last_text = ""

        for _ in range(max_tool_iters):
            ai = llm_with_tools.invoke(msgs)
            msgs.append(ai)

            last_text = str(getattr(ai, "content", "") or "").strip()
            tool_calls = getattr(ai, "tool_calls", None) or []
            if not tool_calls:
                break

            tool_msgs, ev = run_tool_calls_once(tool_calls=tool_calls, tool_map=tool_map)
            msgs.extend(tool_msgs)
            events.extend(ev)

        return ToolCallingLoopOutput(final_text=last_text, messages=msgs, events=events)

    return RunnableLambda(_run)

