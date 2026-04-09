from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.config import Settings
from src.core.llm import build_chat_llm
from src.tools.fs import SafePath, read_text, safe_io_paths, write_text


@dataclass(frozen=True)
class ExpandFileResult:
    input_rel_path: str
    input_abs_path: str
    output_rel_path: str
    output_abs_path: str
    markdown: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]

def _default_output_rel(input_rel: str, *, suffix: str = ".expanded.md") -> str:
    p = Path(input_rel)
    if p.suffix.lower() != ".md":
        return input_rel + suffix
    return p.with_suffix("").as_posix() + suffix


def expand_markdown_file(
    settings: Settings,
    input_path: str,
    *,
    output_path: Optional[str] = None,
    base_dir: Optional[Path] = None,
    overwrite: bool = False,
    max_chars: int = 14000,
) -> ExpandFileResult:
    """
    读取本地 Markdown，并在尽量保持原意与结构的前提下扩充内容。

    约束：
    - 默认只允许在仓库根目录下读写（base_dir 可指定为 study_files 等子目录）
    - 输入必须是 .md
    - 输出默认写到同目录 `<name>.expanded.md`，或由 output_path 指定
    """
    base = (base_dir or _repo_root()).resolve()

    # 先解析输入路径，拿到输入相对路径再计算默认输出路径
    src_only: SafePath
    dst_only: SafePath
    src_only, _tmp = safe_io_paths(
        base_dir=base,
        input_path=input_path,
        output_path=None,
        default_output_rel="__unused__.md",
    )

    if src_only.abs_path.suffix.lower() != ".md":
        raise ValueError("仅支持扩充 .md 文件。")
    if not src_only.abs_path.exists():
        raise FileNotFoundError(f"找不到输入文件：{src_only.rel_posix}")

    out_user = (output_path or "").strip()
    out_default = _default_output_rel(src_only.rel_posix)
    src, dst = safe_io_paths(
        base_dir=base,
        input_path=input_path,
        output_path=out_user or None,
        default_output_rel=out_default,
    )

    original = read_text(src.abs_path, encoding="utf-8")
    if not original.strip():
        raise ValueError("输入文件为空，无法扩充。")
    if dst.abs_path.exists() and (not overwrite) and (dst.abs_path != src.abs_path):
        raise FileExistsError(f"输出文件已存在（可开启 overwrite）：{dst.rel_posix}")

    # 对过长内容做截断，避免超时；保留头尾更利于模型保持结构
    text = original
    if len(text) > max_chars:
        head = text[: int(max_chars * 0.75)]
        tail = text[-int(max_chars * 0.25) :]
        text = head + "\n\n<!-- …内容过长已截断… -->\n\n" + tail

    llm = build_chat_llm(settings)
    system = (
        "你是中文技术学习笔记编辑器。你的任务是：在不改变原文核心含义的前提下，扩充并完善给定的 Markdown 笔记。"
        "输出必须是完整 Markdown（不要输出解释、不要输出 JSON、不要加多余前后缀）。"
        "要求："
        "1) 保留原有标题与主要结构；若结构缺失，可补齐合理小节。"
        "2) 若存在“（待补充）/TODO/空小节”，要补齐为具体内容。"
        "3) 适当增加：定义/直观类比/关键要点/典型场景/常见误区/与相近概念对比/延伸阅读。"
        "4) 内容要可复用：条理清晰，避免空话；可加入简短代码示例（如适用）。"
        "5) 不要编造具体链接；如需引用，给出可搜索的关键词或官方文档名称即可。"
    )
    user = (
        f"当前时间：{datetime.now():%Y-%m-%d %H:%M}\n\n"
        "请扩充并重写下面这份 Markdown（保留其主题与意图）：\n\n"
        f"{text}"
    )

    msg = llm.invoke(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )
    md = str(getattr(msg, "content", "")).strip()
    if not md:
        raise RuntimeError("模型未返回任何内容。")
    if not md.endswith("\n"):
        md += "\n"

    if dst.abs_path == src.abs_path:
        if not overwrite:
            raise ValueError("输出路径与输入路径相同，且 overwrite=False，已阻止覆盖写入。")
        write_text(dst.abs_path, md, encoding="utf-8", newline="\n", overwrite=True, mkdirs=True)
    else:
        write_text(dst.abs_path, md, encoding="utf-8", newline="\n", overwrite=bool(overwrite), mkdirs=True)

    return ExpandFileResult(
        input_rel_path=src.rel_posix,
        input_abs_path=str(src.abs_path),
        output_rel_path=dst.rel_posix,
        output_abs_path=str(dst.abs_path),
        markdown=md,
    )

