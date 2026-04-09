from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_project_env() -> None:
    """
    统一加载项目根目录 `.env`。
    - override=True：避免被系统环境变量（例如残留 OPENAI_API_KEY）污染
    """
    load_dotenv(dotenv_path=repo_root() / ".env", override=True)


def sanitize_ca_env() -> None:
    """
    清理无效 CA 环境变量（例如被代理工具注入 `$ca` 或指向不存在文件）。
    避免 requests/httpx 初始化时报 FileNotFoundError。
    """
    for key in ("SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        v = (os.getenv(key) or "").strip()
        if not v:
            continue
        if v.startswith("$") or (not os.path.exists(v)):
            os.environ.pop(key, None)


def apply_runtime_env() -> None:
    """
    建议在任何“入口点”最早调用：
    - Streamlit app
    - MCP server
    - CLI scripts
    """
    load_project_env()
    sanitize_ca_env()

