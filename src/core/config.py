from __future__ import annotations

import os
from dataclasses import dataclass

from src.utils.env import apply_runtime_env


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_base_url: str
    chat_model: str
    embed_model: str
    embeddings_provider: str
    local_embeddings_model: str
    local_embeddings_device: str
    chroma_persist_dir: str
    collection_name: str
    mcp_enable: bool
    mcp_tools_ttl_s: int
    mcp_python: str


def get_settings() -> Settings:
    apply_runtime_env()

    # 支持两种命名（优先使用 DeepSeek 命名，避免系统里残留的 OPENAI_API_KEY 干扰）
    # - DeepSeek：DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL
    # - OpenAI兼容：OPENAI_API_KEY / OPENAI_BASE_URL
    openai_api_key = (os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    if not openai_api_key:
        raise RuntimeError("缺少 API Key。请在 .env 中配置 OPENAI_API_KEY 或 DEEPSEEK_API_KEY。")

    base_url = (os.getenv("DEEPSEEK_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "").strip()
    if not base_url:
        base_url = "https://api.deepseek.com/v1"

    return Settings(
        openai_api_key=openai_api_key,
        openai_base_url=base_url,
        chat_model=os.getenv("CHAT_MODEL", "deepseek-chat").strip(),
        embed_model=os.getenv("EMBED_MODEL", "deepseek-embedding").strip(),
        embeddings_provider=os.getenv("EMBEDDINGS_PROVIDER", "openai").strip(),
        local_embeddings_model=os.getenv("LOCAL_EMBEDDINGS_MODEL", "BAAI/bge-small-zh-v1.5").strip(),
        local_embeddings_device=os.getenv("LOCAL_EMBEDDINGS_DEVICE", "cpu").strip(),
        chroma_persist_dir=os.getenv("CHROMA_PERSIST_DIR", "./data/chroma").strip(),
        collection_name=os.getenv("COLLECTION_NAME", "personal_workbench").strip(),
        mcp_enable=(os.getenv("MCP_ENABLE", "1").strip() not in {"0", "false", "False", "no", "NO"}),
        mcp_tools_ttl_s=int(os.getenv("MCP_TOOLS_TTL_S", "60").strip() or "60"),
        mcp_python=os.getenv("MCP_PYTHON", "").strip(),
    )

