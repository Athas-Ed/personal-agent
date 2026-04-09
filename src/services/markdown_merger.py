from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.core.config import Settings
from src.core.llm import build_chat_llm
from src.tools.fs import SafePath, delete_file, read_text, resolve_under, write_text


@dataclass(frozen=True)
class MergeMarkdownResult:
    output_rel_path: str
    output_abs_path: str
    deleted_inputs: List[str]
    markdown: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def merge_markdown_files(
    settings: Settings,
    input_paths: List[str],
    *,
    output_path: Optional[str] = None,
    base_dir: Optional[Path] = None,
    overwrite: bool = False,
    delete_inputs: bool = False,
    confirm_delete: bool = False,
    max_chars_per_file: int = 12000,
    max_total_chars: int = 26000,
) -> MergeMarkdownResult:
    """
    合并多个 Markdown 文件为一个“唯一版本”。

    安全约束：
    - 默认 base_dir=study_files/，输入/输出都必须在 base_dir 下
    - delete_inputs 需要 confirm_delete=True 才会执行删除
    """
    if not input_paths or len([p for p in input_paths if (p or "").strip()]) < 2:
        raise ValueError("请至少提供 2 个 input_paths。")

    base = (base_dir or Path("study_files")).resolve()
    if not base.exists():
        # allow auto-create study_files
        base.mkdir(parents=True, exist_ok=True)

    # Resolve and read inputs safely
    srcs: List[SafePath] = []
    texts: List[str] = []
    for raw in input_paths:
        sp = resolve_under(base, raw)
        if sp.abs_path.suffix.lower() != ".md":
            raise ValueError(f"仅支持 .md：{sp.rel_posix}")
        if not sp.abs_path.exists():
            raise FileNotFoundError(f"找不到输入文件：{sp.rel_posix}")
        t = read_text(sp.abs_path, encoding="utf-8").strip()
        if not t:
            raise ValueError(f"输入文件为空：{sp.rel_posix}")
        if len(t) > max_chars_per_file:
            head = t[: int(max_chars_per_file * 0.7)]
            tail = t[-int(max_chars_per_file * 0.3) :]
            t = head + "\n\n<!-- …该文件内容过长，已截断… -->\n\n" + tail
        srcs.append(sp)
        texts.append(t)

    # Decide output path
    if output_path and output_path.strip():
        out_rel = output_path.strip().replace("\\", "/")
    else:
        # default: place next to first file, suffix ".merged.md"
        p0 = Path(srcs[0].rel_posix)
        out_rel = (p0.with_suffix("").as_posix() + ".merged.md") if p0.suffix.lower() == ".md" else (p0.as_posix() + ".merged.md")

    dst = resolve_under(base, out_rel)
    if dst.abs_path.exists() and (not overwrite):
        raise FileExistsError(f"输出文件已存在（可开启 overwrite）：{dst.rel_posix}")

    # Build merged prompt with a global cap
    blocks: List[str] = []
    used = 0
    for sp, t in zip(srcs, texts):
        chunk = f"### 来源：{sp.rel_posix}\n\n{t}\n"
        remaining = max_total_chars - used
        if remaining <= 0:
            break
        if len(chunk) > remaining:
            chunk = chunk[: max(0, remaining - 40)] + "\n\n<!-- …总输入过长，后续来源已截断… -->\n"
        blocks.append(chunk)
        used += len(chunk)

    llm = build_chat_llm(settings)
    system = (
        "你是中文技术笔记编辑器。你的任务是把多份同主题 Markdown 笔记合并为一份“唯一版本”。"
        "输出必须是完整 Markdown（不要输出解释、不要输出 JSON、不要加多余前后缀）。"
        "要求："
        "1) 去重：同义重复内容只保留一份，取更准确、更完整、更可操作的表述。"
        "2) 融合：把各来源的细节融合到同一结构中，避免碎片化。"
        "3) 结构：建议包含：概览/定义、核心要点、实践步骤/示例（如适用）、常见误区、排错、延伸阅读。"
        "4) 不要编造具体链接；如需引用，给出可搜索关键词或官方文档名称。"
        "5) 在文末追加“## 来源文件”列出所有来源相对路径（逐行）。"
    )
    user = (
        f"当前时间：{datetime.now():%Y-%m-%d %H:%M}\n\n"
        f"请合并以下 {len(srcs)} 份 Markdown：\n\n"
        + "\n\n".join(blocks)
    )

    msg = llm.invoke([{"role": "system", "content": system}, {"role": "user", "content": user}])
    md = str(getattr(msg, "content", "")).strip()
    if not md:
        raise RuntimeError("模型未返回任何内容。")
    if not md.endswith("\n"):
        md += "\n"

    write_text(dst.abs_path, md, encoding="utf-8", newline="\n", overwrite=bool(overwrite), mkdirs=True)

    deleted: List[str] = []
    if delete_inputs:
        if not confirm_delete:
            raise ValueError("delete_inputs=True 需要 confirm_delete=True 才会执行删除。")
        for sp in srcs:
            # Don't delete the output file if user mistakenly included it
            if sp.abs_path == dst.abs_path:
                continue
            delete_file(sp.abs_path, missing_ok=False)
            deleted.append(sp.rel_posix)

    return MergeMarkdownResult(
        output_rel_path=dst.rel_posix,
        output_abs_path=str(dst.abs_path),
        deleted_inputs=deleted,
        markdown=md,
    )

