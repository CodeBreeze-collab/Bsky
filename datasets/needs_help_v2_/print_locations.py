import os
import json


ROOT_DIR = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help"


cities = set()
states = set()
countries = set()


for root, _, files in os.walk(ROOT_DIR):
    for filename in files:
        if filename == "animal_centric_posts-w-loc-2.jsonl":
            filepath = os.path.join(root, filename)
            print(f"Reading: {filepath}")

            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        record = json.loads(line)

                        city = record.get("city", "").strip()
                        state = record.get("state", "").strip()
                        country = record.get("country", "").strip()

                        if city:
                            cities.add(city)

                        if state:
                            states.add(state)

                        if country:
                            countries.add(country)

                    except json.JSONDecodeError:
                        print(f"Skipping malformed JSON: {filepath}")


print("\n=== Cities ===")
for city in sorted(cities):
    print(city)

print(f"\nTotal cities: {len(cities)}")


print("\n=== States / Regions ===")
for state in sorted(states):
    print(state)

print(f"\nTotal states/regions: {len(states)}")


print("\n=== Countries ===")
for country in sorted(countries):
    print(country)

print(f"\nTotal countries: {len(countries)}")