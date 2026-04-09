from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is on sys.path so `import src.*` works
_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.utils.env_cmd import write_env_as_cmd


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: env_to_cmd.py <env_path> <out_cmd_path>", file=sys.stderr)
        return 2

    env_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    write_env_as_cmd(env_path=env_path, out_cmd_path=out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

