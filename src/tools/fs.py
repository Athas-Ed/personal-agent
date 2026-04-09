from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


@dataclass(frozen=True)
class SafePath:
    abs_path: Path
    rel_posix: str


def resolve_under(base_dir: Path, user_path: str) -> SafePath:
    """
    将 user_path 解析为 base_dir 下的安全路径。

    规则：
    - user_path 允许相对路径（相对 base_dir）
    - 若传入绝对路径，也必须位于 base_dir 内
    - 禁止路径穿越（..）到 base_dir 外
    """
    base = (base_dir or Path(".")).resolve()
    raw = (user_path or "").strip().replace("\\", "/")
    if not raw:
        raise ValueError("路径不能为空。")

    p = Path(raw)
    abs_p = p.resolve() if p.is_absolute() else (base / p).resolve()

    try:
        abs_p.relative_to(base)
    except Exception as e:
        raise ValueError(f"路径不允许（必须位于 {base} 下）：{user_path}") from e

    return SafePath(abs_path=abs_p, rel_posix=abs_p.relative_to(base).as_posix())


def read_text(path: Path, *, encoding: str = "utf-8") -> str:
    return Path(path).read_text(encoding=encoding)


def write_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    newline: str = "\n",
    overwrite: bool = False,
    mkdirs: bool = True,
) -> None:
    p = Path(path)
    if p.exists() and (not overwrite):
        raise FileExistsError(f"目标文件已存在：{p}")
    if mkdirs:
        p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding=encoding, newline=newline)


def delete_file(path: Path, *, missing_ok: bool = True) -> None:
    p = Path(path)
    if not p.exists():
        if missing_ok:
            return
        raise FileNotFoundError(str(p))
    if p.is_dir():
        raise IsADirectoryError(str(p))
    p.unlink()


def remove_dir(
    path: Path,
    *,
    allow_non_empty: bool = False,
    missing_ok: bool = True,
) -> None:
    """
    删除目录。
    - 默认不允许删除非空目录（避免误伤）
    - allow_non_empty=True 时递归删除
    """
    p = Path(path)
    if not p.exists():
        if missing_ok:
            return
        raise FileNotFoundError(str(p))
    if not p.is_dir():
        raise NotADirectoryError(str(p))

    if allow_non_empty:
        shutil.rmtree(p)
        return
    p.rmdir()


def safe_io_paths(
    *,
    base_dir: Path,
    input_path: str,
    output_path: Optional[str],
    default_output_rel: str,
) -> Tuple[SafePath, SafePath]:
    """
    常用模式：在同一 base_dir 约束下解析输入/输出路径。
    """
    src = resolve_under(base_dir, input_path)
    out_rel = (output_path or "").strip() or default_output_rel
    dst = resolve_under(base_dir, out_rel)
    return src, dst

