from __future__ import annotations

import re
from pathlib import Path

PEM_RE = re.compile(
    r"-----BEGIN CERTIFICATE-----\s+.*?\s+-----END CERTIFICATE-----",
    re.DOTALL,
)


def extract_pem_blocks(text: str) -> str | None:
    blocks = PEM_RE.findall(text)
    if not blocks:
        return None
    normalized: list[str] = []
    for b in blocks:
        b = b.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"
        normalized.append(b)
    return "\n".join(normalized).strip() + "\n"


def prepare_ca_bundle(src: Path, dst: Path) -> bool:
    """
    尝试从输入证书文件中提取 PEM blocks，并写入 dst。
    - 成功写出返回 True
    - 输入不是 PEM/无法提取时返回 False（调用方可 fallback 到 certutil）
    """
    data = src.read_bytes()

    # Fast path: already contains ASCII PEM markers (UTF-8/ASCII).
    if b"BEGIN CERTIFICATE" not in data:
        return False

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        # Some tools store PEM as UTF-16LE; try that.
        text = data.decode("utf-16le", errors="ignore")

    pem = extract_pem_blocks(text)
    if pem is None:
        # Might still be UTF-16 with NULs in between; remove NULs and retry.
        pem = extract_pem_blocks(text.replace("\x00", ""))

    if pem is None:
        return False

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(pem, encoding="utf-8", newline="\n")
    return True

