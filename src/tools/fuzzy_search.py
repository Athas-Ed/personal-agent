from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from src.tools.fs import resolve_under


@dataclass(frozen=True)
class SearchHit:
    rel_path: str
    score: float
    reason: str


def _normalize(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _score(query: str, rel_path: str) -> SearchHit:
    q = _normalize(query)
    p = _normalize(rel_path)
    if not q:
        return SearchHit(rel_path=rel_path, score=0.0, reason="empty query")

    # Strong signals first
    if q in p:
        return SearchHit(rel_path=rel_path, score=1.0, reason="substring match")

    # Token overlap (very cheap fuzzy)
    q_tokens = [t for t in re.split(r"[\\s/_\\-\\.]+", q) if t]
    p_tokens = [t for t in re.split(r"[\\s/_\\-\\.]+", p) if t]
    if not q_tokens:
        return SearchHit(rel_path=rel_path, score=0.0, reason="no tokens")

    hit = 0
    for t in q_tokens:
        if any(t in pt for pt in p_tokens):
            hit += 1
    ratio = hit / max(1, len(q_tokens))

    # Prefer closer path depth
    depth_penalty = min(0.25, (p.count("/") * 0.02))
    score = max(0.0, ratio - depth_penalty)
    reason = f"token_hit={hit}/{len(q_tokens)} depth={p.count('/')}"
    return SearchHit(rel_path=rel_path, score=score, reason=reason)


def fuzzy_search_files(
    *,
    base_dir: Path,
    query: str,
    exts: Optional[List[str]] = None,
    max_results: int = 10,
) -> List[SearchHit]:
    """
    在 base_dir 下做轻量模糊搜索（按相对路径名）。
    - 不读文件内容，速度快
    - 默认只搜 .md
    """
    base = (base_dir or Path(".")).resolve()
    exts = exts or [".md"]
    exts_n = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in exts}

    hits: List[SearchHit] = []
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in exts_n:
            continue
        rel = p.relative_to(base).as_posix()
        h = _score(query, rel)
        if h.score > 0:
            hits.append(h)

    hits.sort(key=lambda x: x.score, reverse=True)
    return hits[: max(1, int(max_results))]


def resolve_hits_under(base_dir: Path, rel_paths: Iterable[str]) -> List[str]:
    """
    用 resolve_under 做安全校验并标准化相对路径（posix）。
    """
    out: List[str] = []
    for rp in rel_paths:
        sp = resolve_under(base_dir, str(rp))
        out.append(sp.rel_posix)
    return out

