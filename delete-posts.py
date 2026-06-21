import json
from atproto import Client

# --- Authentication ---
# CRITICAL: You must log in as the account that actually owns these posts!
MY_HANDLE = 'the-epstein-class.bsky.social'
MY_APP_PASSWORD = 'kpbo-vrvi-uyww-br2r'

# Path to the JSONL file you generated
JSONL_FILE_PATH = '/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/IG_posts/the-epstein-class_bsky_social_posts_06-01-2026_reposts.jsonl'


def delete_posts_from_file():
    client = Client()

    try:
        # Log in as the owner of the posts
        print(f"Logging in as {MY_HANDLE}...")
        client.login(MY_HANDLE, MY_APP_PASSWORD)

        deleted_count = 0
        skipped_reposts = 0

        print(f"Opening data file: {JSONL_FILE_PATH}")
        with open(JSONL_FILE_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue

                # Parse the JSON line
                record = json.loads(line)
                url = record.get("url")
                is_repost = record.get("is_repost", False)

                # Extract the unique record key (rkey) from the web URL
                # e.g., "3moit47tppc2b" from "https://bsky.app/profile/.../post/3moit47tppc2b"
                rkey = url.split('/')[-1]

                # --- Handling Reposts ---
                if is_repost:
                    # To "un-repost" something, the API requires the unique URI of the
                    # *repost action record* itself, which wasn't saved in the JSONL.
                    # We skip it here to avoid errors.
                    print(f"Skipping repost entry: {url}")
                    skipped_reposts += 1
                    continue

                # --- Reconstructing the AT Protocol URI for Posts/Replies ---
                # Format required by SDK: at://{did_or_handle}/app.bsky.feed.post/{rkey}
                post_uri = f"at://{MY_HANDLE}/app.bsky.feed.post/{rkey}"

                print(f"Deleting: {url} -> ({post_uri})")
                try:
                    client.delete_post(post_uri)
                    deleted_count += 1
                except Exception as post_err:
                    print(f"Could not delete {url}. Error: {post_err}")

        print(f"\n--- Run Complete ---")
        print(f"Successfully deleted {deleted_count} posts/replies.")
        if skipped_reposts > 0:
            print(f"Skipped {skipped_reposts} repost entries (requires an un-repost tracking URI).")

    except Exception as e:
        print(f"An authentication or system error occurred: {e}")


if __name__ == "__main__":
    delete_posts_from_file()