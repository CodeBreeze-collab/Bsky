#!/usr/bin/env python3

import json
from pathlib import Path

# Set your top-level directory here
TOP_DIR = Path("/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help")


def scan_file(path):
    found = False

    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                print(f"[BAD JSON] {path}:{lineno}")
                continue

            city = str(row.get("city", "")).strip()
            state = str(row.get("state", "")).strip()

            if city or state:
                if not found:
                    print(f"\n=== {path} ===")
                    found = True

                print(f"line {lineno}: city={city!r}, state={state!r}")


def main():
    for path in sorted(TOP_DIR.rglob("*.jsonl")):
        if "animal_centric" not in path.name:
            continue
        scan_file(path)


if __name__ == "__main__":
    main()