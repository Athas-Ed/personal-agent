from __future__ import annotations

from dataclasses import dataclass
from typing import List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda


@dataclass(frozen=True)
class BuildMessagesInput:
    system: SystemMessage
    session_messages: List[dict]
    user_input: str


def to_chat_history(messages: List[dict]) -> List[BaseMessage]:
    """
    将 Streamlit session 中的 {"role","content"} 转成 LangChain messages。
    仅保留 user/assistant；工具消息由 tool-calling loop 内部处理。
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


def build_messages_runnable() -> Runnable[dict, List[BaseMessage]]:
    """
    LCEL 风格：把 messages 构建封装为 Runnable。
    输入是 dict，便于后续在 chain 中组合。
    """

    def _run(inp: dict) -> List[BaseMessage]:
        system: SystemMessage = inp["system"]
        session_messages: List[dict] = inp.get("session_messages") or []
        user_input: str = str(inp.get("user_input") or "")
        msgs: List[BaseMessage] = [system]
        msgs.extend(to_chat_history(session_messages))
        msgs.append(HumanMessage(content=user_input))
        return msgs

    return RunnableLambda(_run)

