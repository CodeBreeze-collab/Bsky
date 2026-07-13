import os
import random  # Added for generating random intervals
import sys
import time
from atproto import Client
from atproto.exceptions import AtProtocolError

# --- Configuration ---
BLUESKY_HANDLE = "veevasearch.com"
BLUESKY_APP_PASSWORD = "6xor-n2aa-rech-xl4b" # os.getenv("BLUESKY_APP_PASSWORD")

# Random sleep range configurations (in seconds)
MIN_DELAY = 2.0
MAX_DELAY = 6.0


def follow_users_from_file(file_path):
    # Security Check: Ensure the environment variable is actually set
    if not BLUESKY_APP_PASSWORD:
        print(
            "❌ Error: The 'BLUESKY_APP_PASSWORD' environment variable is not set."
        )
        print("Please set it in your terminal before running this script.")
        return

    # Initialize the AT Protocol client
    client = Client()

    print("🔑 Logging into Bluesky...")
    try:
        client.login(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)
        print("✅ Login successful!\n")
    except Exception as e:
        print(f"❌ Failed to log in. Check your handle and app password: {e}")
        return

    # Verify that the text file exists
    if not os.path.exists(file_path):
        print(f"❌ Error: The file at '{file_path}' does not exist.")
        return

    # Read and clean handles from the file
    with open(file_path, "r", encoding="utf-8") as f:
        handles = [line.strip().lstrip("@") for line in f if line.strip()]

    print(f"📚 Found {len(handles)} handles to process.\n")

    for handle in handles:
        try:
            print(f"🔄 Processing: {handle}")

            # Step 1: Resolve handle to DID
            resolution = client.com.atproto.identity.resolve_handle(
                params={"handle": handle}
            )
            user_did = resolution.did

            # Step 2: Send follow request
            client.follow(user_did)
            print(f"➕ Successfully followed: {handle}")

            # Step 3: Randomized Rate limit buffer
            sleep_time = random.uniform(MIN_DELAY, MAX_DELAY)
            print(f"⏱️ Sleeping for {sleep_time:.2f} seconds...")
            time.sleep(sleep_time)

        except AtProtocolError as e:
            print(f"⚠️ AT Protocol Error for {handle}: {e}")
        except Exception as e:
            print(f"❌ Unexpected error for {handle}: {e}")

        print("-" * 40)

    print("\n🎉 Process complete!")


if __name__ == "__main__":
    follow_users_from_file(
        "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/to_follow.txt"
    )