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
    code = _run(["poetry", "run", "ruff", "format", "."])
    code = code or _run(["npm", "run", "format"])
    sys.exit(code)
