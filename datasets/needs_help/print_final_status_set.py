import os
import json

ROOT_DIR = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help/"  # change this

statuses = set()

for root, _, files in os.walk(ROOT_DIR):
    for file in files:
        if file == "animal_centric_posts-w-loc-2.jsonl":
            filepath = os.path.join(root, file)
            print(f"Reading: {filepath}")

            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        record = json.loads(line)
                        if "final_status" in record:
                            statuses.add(record["final_status"])
                    except json.JSONDecodeError as e:
                        print(f"Skipping malformed JSON in {filepath}: {e}")

print("\nUnique final_status values:")
for status in sorted(statuses):
    print(status)

print(f"\nTotal unique statuses: {len(statuses)}")