from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path so `import src.*` works
_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.utils.skills_registry import build_registry


def main() -> int:
    repo_root = _repo_root
    skills_root = repo_root / "skills"
    registry_path = skills_root / "registry.json"

    reg = build_registry(skills_root)
    skills_root.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK: registry written -> {registry_path}")
    if reg.get("errors"):
        print("WARN: some skills have issues:")
        for e in reg["errors"]:
            print(f"- {e['dir']}: {e['error']}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

