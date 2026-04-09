from __future__ import annotations

"""
本地 MCP Server（stdio 模式）入口。

说明：
- 这里放在 src/ 下，便于按“可 import 的应用代码”来管理
- 仓库根目录的 mcp/server.py 仅保留为兼容启动器（薄转发）
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path so `import src.*` works
_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.utils.env import apply_runtime_env

apply_runtime_env()

from datetime import datetime, timezone
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("personal-workbench-mcp")


@mcp.tool()
def ping(text: str = "pong") -> str:
    return text


@mcp.tool()
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@mcp.tool()
def list_study_files(
    exts: list[str] | None = None,
    limit: int = 200,
    contains: str = "",
) -> dict:
    from src.plugins.study_files_mcp_tools import list_study_files_impl

    return list_study_files_impl(
        repo_root=_repo_root,
        exts=exts,
        limit=limit,
        contains=contains,
    )


@mcp.tool()
def expand_local_markdown(
    input_path: str,
    output_path: str = "",
    overwrite: bool = False,
    scope: str = "repo",
) -> dict:
    """
    读取本地 Markdown 并扩充内容（写回或写到新文件）。

    参数：
    - input_path：输入文件路径（相对 scope 目录，或绝对路径但必须位于 scope 内）
    - output_path：输出路径（留空则默认同目录生成 .expanded.md）
    - overwrite：是否允许覆盖输出文件（若 output_path 与 input_path 相同则必须为 True）
    - scope：读写范围，默认 repo；可选 study_files（更安全，限制在 study_files/ 下）
    """
    try:
        from src.core.config import get_settings
        from src.services.file_expander import expand_markdown_file

        settings = get_settings()
        base_dir = _repo_root
        if (scope or "").strip().lower() in {"study", "study_files", "study-files"}:
            base_dir = _repo_root / "study_files"

        res = expand_markdown_file(
            settings=settings,
            input_path=input_path,
            output_path=(output_path or "").strip() or None,
            base_dir=base_dir,
            overwrite=bool(overwrite),
        )
        return {
            "ok": True,
            "input_rel_path": res.input_rel_path,
            "output_rel_path": res.output_rel_path,
            "output_abs_path": res.output_abs_path,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

