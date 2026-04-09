from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is on sys.path so `import src.*` works
_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.utils.cert_bundle import prepare_ca_bundle


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: prepare_ca_bundle.py <input_cert_path> <output_pem_path>", file=sys.stderr)
        return 2

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])

    ok = prepare_ca_bundle(src=src, dst=dst)
    if not ok:
        print("Input does not look like PEM; fallback required.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

