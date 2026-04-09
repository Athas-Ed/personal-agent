from __future__ import annotations

from pathlib import Path


def list_study_files_impl(
    *,
    repo_root: Path,
    exts: list[str] | None = None,
    limit: int = 200,
    contains: str = "",
) -> dict:
    """
    业务实现：列出 study_files/ 下的资料文件（默认：.md/.txt/.pdf）。

    说明：
    - 这里放在 plugins/，便于复用（UI、本地工具、MCP server 都可调用同一实现）
    - MCP server 侧只负责注册为 @mcp.tool() 并传入 repo_root
    """
    try:
        study_root = (repo_root / "study_files").resolve()
        if not study_root.exists():
            return {"ok": True, "root": "study_files", "count": 0, "files": [], "note": "study_files/ 不存在"}

        exts = exts or [".md", ".txt", ".pdf"]
        exts_n = {e.lower() if str(e).startswith(".") else f".{str(e).lower()}" for e in exts}

        q = (contains or "").strip().lower()
        files: list[str] = []
        for p in sorted(study_root.rglob("*")):
            if not p.is_file():
                continue
            if p.suffix.lower() not in exts_n:
                continue
            rel = p.relative_to(study_root).as_posix()
            if q and (q not in rel.lower()):
                continue
            files.append(rel)
            if len(files) >= max(1, int(limit)):
                break

        return {"ok": True, "root": "study_files", "count": len(files), "files": files}
    except Exception as e:
        return {"ok": False, "error": str(e)}

