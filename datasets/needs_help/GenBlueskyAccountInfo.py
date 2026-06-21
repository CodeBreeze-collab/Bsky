import os
import json
from datetime import datetime
from atproto import Client


def generate_rescue_list(handles: list, output_file: str):
    client = Client()
    # You generally don't need to login just to view public profiles,
    # but logging in helps with rate limits.
    handle = "ethicalsearch.bsky.social"
    password = os.environ.get("BLUESKY_APP_PASSWORD")

    try:
        client.login(handle, password)
    except Exception as e:
        print(f"Login failed, attempting as public: {e}")

    # Keywords to check for in the description/display name
    keywords = ["sanctuary", "rescue", "animal", "shelter", "foster"]

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "a", encoding="utf-8") as f:
        for h in handles:
            try:
                print(f"Processing: {h}")
                # Fetch profile data from Bluesky
                profile = client.get_profile(actor=h)

                # Determine which keywords matched
                text_to_scan = f"{profile.display_name} {profile.description}".lower()
                matched = [kw for kw in keywords if kw in text_to_scan]

                # Construct the exact record format
                record = {
                    "handle": profile.handle,
                    "did": profile.did,
                    "display_name": profile.display_name,
                    "description": profile.description,
                    "matched_keywords": matched,
                    "source_account": "manual_input",
                    "written_at": datetime.utcnow().isoformat() + "Z"
                }

                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                print(f"  [SAVED] {h}")

            except Exception as e:
                print(f"  [ERROR] Could not process {h}: {e}")


if __name__ == "__main__":
    # Your list of handles
    my_handles = [
        "nycacckills.bsky.social",
        "thescoopnewyork.com",
        "nyshelterreform.bsky.social",
        "tammyfeabakker.bsky.social"
    ]

    # Path to your existing dataset
    FILE_PATH = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/rescue_repost_handles/bluesky_rescue_accounts-03-31-2026-handle-title.jsonl"

    generate_rescue_list(my_handles, FILE_PATH)