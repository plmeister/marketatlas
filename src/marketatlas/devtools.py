"""Dev tooling entry points (wired into `poetry run lint` / `poetry run fmt`).

Runs the Python (ruff/mypy) and JS (eslint/prettier) toolchains and
propagates the first non-zero exit code.
"""

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def _run(cmd: list[str]) -> int:
    print("$", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=_ROOT)
    return result.returncode


def _changed_files() -> list[str]:
    """Files modified in the working tree vs HEAD, restricted to tool targets."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACM", "HEAD"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [ln for ln in result.stdout.splitlines() if ln]


def lint() -> None:
    commands = [
        ["poetry", "run", "ruff", "check", "."],
        ["poetry", "run", "mypy", "src"],
        ["npm", "run", "lint"],
    ]
    code = 0
    for cmd in commands:
        code = code or _run(cmd)
    sys.exit(code)


def fmt() -> None:
    changed = _changed_files()
    py_files = [f for f in changed if f.endswith(".py")]
    js_files = [f for f in changed if f.endswith(".js")]
    if not py_files and not js_files:
        print("No changed files to format.")
        return
    code = 0
    if py_files:
        code = code or _run(["poetry", "run", "ruff", "format"] + py_files)
    if js_files:
        code = code or _run(["npx", "prettier", "--write"] + js_files)
    sys.exit(code)
