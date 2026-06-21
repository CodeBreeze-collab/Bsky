import re
import sys
from pathlib import Path

def main():
    # 👉 Set the path to your .txt file here
    file_path = Path("/Users/hdon/Desktop/bluesky-accts-audit.txt")

    if not file_path.exists():
        print(f"File not found: {file_path}")
        sys.exit(1)

    # Regex:
    # - Capture the handle
    # - Capture the number of days inside (Xd)
    pattern = re.compile(r'^(@\S+)\s+\|.*\((\d+)d\)')

    with file_path.open(encoding="utf-8") as f:
        for line in f:
            match = pattern.search(line)
            if not match:
                continue

            handle, days = match.groups()
            days = int(days)

            if days > 30:
                print(handle)


if __name__ == "__main__":
    main()
