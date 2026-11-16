"""Interactive prompts shared by the CLI and the setup wizard."""

from __future__ import annotations


def ask(prompt: str, default: str = "") -> str:
    """Ask for a value, returning ``default`` on empty input or EOF."""
    try:
        answer = input(f"{prompt} [{default}]: ").strip()
    except EOFError:
        return default
    return answer or default


def confirm(prompt: str) -> bool:
    """Ask a yes/no question; EOF and non-yes answers mean no."""
    try:
        answer = input(f"{prompt} ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")
