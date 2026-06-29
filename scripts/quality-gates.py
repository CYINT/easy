"""Release quality gates for maintainability and cyclomatic complexity."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SOURCE_PATHS = ("boards", "easy_project")
MAX_COMPLEXITY_RANK = "B"
MIN_MI_RANK = "C"
RANKS = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6}
EXCLUDED_NAMES = {"tests.py", "asgi.py", "wsgi.py"}


def run_radon(*args: str) -> dict[str, Any]:
    command = [sys.executable, "-m", "radon", *args, *SOURCE_PATHS, "-j"]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def is_excluded(path: str) -> bool:
    normalized = Path(path)
    return "migrations" in normalized.parts or normalized.name in EXCLUDED_NAMES


def flatten_complexity_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for block in blocks:
        flattened.append(block)
        flattened.extend(flatten_complexity_blocks(block.get("closures", [])))
        flattened.extend(flatten_complexity_blocks(block.get("methods", [])))
    return flattened


def check_complexity() -> list[str]:
    failures: list[str] = []
    max_allowed = RANKS[MAX_COMPLEXITY_RANK]
    results = run_radon("cc")
    for path, blocks in results.items():
        if is_excluded(path):
            continue
        for block in flatten_complexity_blocks(blocks):
            rank = block["rank"]
            if RANKS[rank] > max_allowed:
                name = block.get("fullname") or block.get("name", "<unknown>")
                line = block.get("lineno", "?")
                failures.append(f"{path}:{line} {name} has cyclomatic complexity rank {rank}")
    return failures


def check_maintainability() -> list[str]:
    failures: list[str] = []
    min_allowed = RANKS[MIN_MI_RANK]
    results = run_radon("mi")
    for path, result in results.items():
        if is_excluded(path):
            continue
        rank = result["rank"]
        if RANKS[rank] > min_allowed:
            failures.append(f"{path} has maintainability index rank {rank}")
    return failures


def main() -> int:
    failures = [*check_complexity(), *check_maintainability()]
    if failures:
        print("Quality gates failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Quality gates passed: cyclomatic complexity <= B, maintainability index >= C.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
