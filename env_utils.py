"""Simple .env file loader and updater without external dependencies."""

from __future__ import annotations

from pathlib import Path


def load_env(path: Path) -> dict[str, str]:
    """Read key=value pairs from a .env file while ignoring comments and blank lines."""
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")):
            val = val[1:-1]
        values[key] = val
    return values


def _format_env_value(value: str) -> str:
    if any(ch in value for ch in (" ", "#", '"', "'")):
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    return value


def update_env(path: Path, updates: dict[str, str]) -> None:
    """Update or append key=value entries in a .env file, preserving existing comments."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(updates)
    new_lines: list[str] = []

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(raw_line)
            continue
        key, _ = stripped.split("=", 1)
        key = key.strip()
        if key in remaining:
            new_lines.append(f"{key}={_format_env_value(remaining.pop(key))}")
        else:
            new_lines.append(raw_line)

    for key, val in remaining.items():
        new_lines.append(f"{key}={_format_env_value(val)}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
