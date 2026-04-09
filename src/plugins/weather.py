from __future__ import annotations

import os
from typing import Any, Dict, Optional

from langchain_core.tools import BaseTool, StructuredTool


def _amap_key_present() -> bool:
    key = (os.getenv("AMAP_KEY") or "").strip()
    return bool(key and key != "your_amap_key_here")


def get_weather_forecast(city: str = "太原") -> Dict[str, Any]:
    """
    可插拔天气能力（高德 MCP）。

    说明：
    - 这是“额外功能”，不应成为 core 的硬依赖
    - 这里统一对外暴露稳定返回结构（尽量 dict）；失败返回 error 字段
    """
    city = (city or "太原").strip()
    try:
        from src.integrations.amap_weather_mcp import AMapWeatherMCPService

        amap = AMapWeatherMCPService.get_instance()
        tool_name = amap.guess_weather_tool_name()
        data = amap.call_tool(tool_name, {"city": city})
        return data if isinstance(data, dict) else {"raw": data, "city": city, "source": "amap_mcp"}
    except Exception as e:
        return {"error": str(e), "city": city, "source": "amap_mcp"}


def build_weather_tool() -> Optional[BaseTool]:
    """
    返回可选的天气工具：
    - 环境缺少 AMAP_KEY 时直接返回 None（实现“可插拔”）
    - 有 key 时返回 StructuredTool（供 Agent 本地工具列表使用）
    """
    if not _amap_key_present():
        return None

    return StructuredTool.from_function(
        name="get_weather",
        description="查询天气（高德 MCP）。参数：city（城市名，默认太原）。返回未来预报。",
        func=get_weather_forecast,
    )

