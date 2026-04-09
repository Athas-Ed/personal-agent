from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from langchain_core.tools import BaseTool, StructuredTool

from src.core.config import Settings
from src.services.file_expander import expand_markdown_file
from src.services.study_notes import build_export_note_runnable


def build_local_tools(settings: Settings) -> List[BaseTool]:
    """
    本地工具集合（不包含 MCP tools）。
    约定：这里负责“Tool schema”，实际业务逻辑尽量下沉到 services/utils。
    """

    # Optional plugin tools
    weather_tool: BaseTool | None = None
    try:
        # 插件是否启用由插件自身（环境变量）决定
        from src.plugins.weather import build_weather_tool

        weather_tool = build_weather_tool()
    except Exception:
        weather_tool = None

    def _merge_md(
        input_paths: List[str],
        output_path: str = "",
        overwrite: bool = False,
        delete_inputs: bool = False,
        confirm_delete: bool = False,
        scope: str = "study_files",
    ) -> dict:
        from src.services.markdown_merger import merge_markdown_files

        base_dir = (
            Path("study_files")
            if (scope or "").strip().lower() in {"study", "study_files", "study-files"}
            else Path(".")
        )
        res = merge_markdown_files(
            settings=settings,
            input_paths=input_paths,
            output_path=(output_path or "").strip() or None,
            base_dir=base_dir,
            overwrite=bool(overwrite),
            delete_inputs=bool(delete_inputs),
            confirm_delete=bool(confirm_delete),
        )
        return {"ok": True, "output_rel_path": res.output_rel_path, "deleted_inputs": res.deleted_inputs}

    merge_tool = StructuredTool.from_function(
        name="merge_markdown_files",
        description=(
            "合并多份同主题 Markdown 为一份“唯一版本”。默认在 study_files/ 范围内操作更安全。"
            "参数：input_paths(相对 scope 的路径列表)、output_path(可空)、overwrite、"
            "delete_inputs(可选)、confirm_delete(删除必须=true)、scope(study_files|repo)。"
        ),
        func=_merge_md,
    )

    def _search_files(
        query: str,
        scope: str = "study_files",
        max_results: int = 10,
        exts: List[str] | None = None,
    ) -> dict:
        """
        模糊搜索文件（按路径名），返回候选列表。
        """
        from src.tools.fuzzy_search import fuzzy_search_files

        base_dir = (
            Path("study_files")
            if (scope or "").strip().lower() in {"study", "study_files", "study-files"}
            else Path(".")
        )
        hits = fuzzy_search_files(
            base_dir=base_dir,
            query=query,
            exts=exts or [".md"],
            max_results=int(max_results),
        )
        return {"ok": True, "hits": [{"rel_path": h.rel_path, "score": h.score, "reason": h.reason} for h in hits]}

    search_tool = StructuredTool.from_function(
        name="fuzzy_search_files",
        description=(
            "在指定范围内按路径名模糊搜索文件，返回候选列表（不读文件内容）。"
            "参数：query、scope(study_files|repo)、max_results、exts(例如['.md'])。"
        ),
        func=_search_files,
    )

    def _expand_md(
        input_path: str,
        output_path: str = "",
        overwrite: bool = False,
        scope: str = "study_files",
    ) -> dict:
        base_dir = (
            Path("study_files")
            if (scope or "").strip().lower() in {"study", "study_files", "study-files"}
            else Path(".")
        )
        res = expand_markdown_file(
            settings=settings,
            input_path=input_path,
            output_path=(output_path or "").strip() or None,
            base_dir=base_dir,
            overwrite=bool(overwrite),
        )
        return {"ok": True, "input_rel_path": res.input_rel_path, "output_rel_path": res.output_rel_path}

    expand_tool = StructuredTool.from_function(
        name="expand_markdown_file",
        description=(
            "读取并扩充本地 Markdown 文件内容，补齐知识点/误区/场景/对比/下一步等，并保存为新文件或覆盖写回。"
            "参数：input_path(相对 scope)、output_path(可空)、overwrite、scope(study_files|repo)。"
        ),
        func=_expand_md,
    )

    out: List[BaseTool] = []
    if weather_tool is not None:
        out.append(weather_tool)
    out.extend([search_tool, merge_tool, expand_tool])
    return out


def build_export_tool_for_session(settings: Settings, *, session_messages: List[dict]) -> BaseTool:
    """
    绑定当前会话消息的“导出学习笔记”工具（闭包）。
    """

    def _export_study_note(
        indices_1based: List[int] | None = None,
        start_i: int = 1,
        end_i: int = 1,
        confirm_write: bool = False,
    ) -> dict:
        if not confirm_write:
            return {
                "ok": False,
                "error": "禁止写入：请在用户明确要求“保存/导出/写入study_files”时再调用，并把 confirm_write=true。",
            }
        if indices_1based:
            idx = [int(x) for x in indices_1based]
        else:
            idx = list(range(int(start_i), int(end_i) + 1))

        study_root = Path("study_files")
        runnable = build_export_note_runnable(settings, study_root=study_root)
        res = runnable.invoke({"all_messages": session_messages, "indices_1based": idx})
        return {"ok": True, "rel_path": res.rel_path}

    return StructuredTool.from_function(
        name="export_study_note",
        description=(
            "把当前对话整理为学习笔记并保存到 study_files/。"
            "参数：indices_1based(可选，消息序号列表)、start_i/end_i(可选，闭区间)、"
            "confirm_write(必须=true，且仅当用户明确要求保存/导出时才允许写入)。"
        ),
        func=_export_study_note,
    )

