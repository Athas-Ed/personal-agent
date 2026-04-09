from __future__ import annotations

from pathlib import Path

from dotenv import dotenv_values


def escape_cmd_value(v: str) -> str:
    # Escape for: set "KEY=VALUE"
    # Keep it simple but safe for common special chars in cmd.
    v = v.replace("^", "^^")
    v = v.replace("&", "^&")
    v = v.replace("|", "^|")
    v = v.replace("<", "^<")
    v = v.replace(">", "^>")
    v = v.replace('"', '\\"')
    return v


def write_env_as_cmd(env_path: Path, out_cmd_path: Path) -> None:
    values = dotenv_values(env_path)
    out_cmd_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for k, val in values.items():
        if not k or val is None:
            continue
        lines.append(f'set "{k}={escape_cmd_value(str(val))}"')
    out_cmd_path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")

