from __future__ import annotations

from langchain_core.messages import SystemMessage


def build_tools_agent_system_message() -> SystemMessage:
    """
    Tool-calling agent 的系统提示词。
    约定：集中管理，避免散落在 core 逻辑中，便于后续做 A/B 与版本化。
    """
    return SystemMessage(
        content=(
            "你是个人工作台助手。你可以在需要时调用工具来完成任务。"
            "文件操作优先使用 scope=study_files，除非用户明确要求 scope=repo。"
            "任何写入文件的工具都必须在用户明确要求“保存/导出/写入”时才调用，并遵守工具的 confirm_write 约束。"
            "回答要简洁、可执行、中文。"
        )
    )

