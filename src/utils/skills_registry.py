from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_simple_yaml(frontmatter: str) -> Dict[str, Any]:
    """
    极简 YAML 解析器（只支持 key: value 以及 key: a, b, c）。
    避免引入额外依赖；如后续需要完整 YAML，再引入 PyYAML。
    """
    out: Dict[str, Any] = {}
    for raw in frontmatter.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip()
        if "," in v:
            out[k] = [x.strip() for x in v.split(",") if x.strip()]
        else:
            out[k] = v
    return out


def _read_skill_meta(skill_dir: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None, "missing SKILL.md"
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, "missing YAML frontmatter"
    meta = _parse_simple_yaml(m.group(1))
    if not meta.get("name"):
        return None, "missing frontmatter.name"
    if not meta.get("description"):
        return None, "missing frontmatter.description"
    return meta, None


def _list_skill_dirs(skills_root: Path) -> List[Path]:
    if not skills_root.exists():
        return []
    return sorted([p for p in skills_root.iterdir() if p.is_dir() and not p.name.startswith(".")])


def build_registry(skills_root: Path) -> Dict[str, Any]:
    skills: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for d in _list_skill_dirs(skills_root):
        if d.name.lower() == "__pycache__":
            continue
        meta, err = _read_skill_meta(d)
        if err:
            errors.append({"dir": d.name, "error": err})
            continue

        scripts_dir = d / "scripts"
        scripts: List[str] = []
        if scripts_dir.exists() and scripts_dir.is_dir():
            for f in sorted(scripts_dir.rglob("*.py")):
                scripts.append(str(f.relative_to(skills_root)).replace("\\", "/"))

        skills.append(
            {
                "dir": d.name,
                "name": meta.get("name"),
                "aliases": meta.get("aliases", []),
                "description": meta.get("description"),
                "has_scripts": scripts_dir.exists(),
                "scripts": scripts,
                "skill_md": str((d / "SKILL.md").relative_to(skills_root)).replace("\\", "/"),
            }
        )

    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "skills": skills,
        "errors": errors,
    }

