import os
import sys
import time
import random
from urllib.parse import urlparse
from atproto import Client, models
from atproto.exceptions import AtProtocolError

# --- Configuration ---
BLUESKY_HANDLE = "newenglandtopnews.bsky.social"
BLUESKY_APP_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD")

# Adjust the delay range here (in seconds)
MIN_DELAY = 1.0
MAX_DELAY = 2.0


def parse_post_url(url):
    """Parses a Bluesky post URL to extract the handle/DID and the rkey."""
    parsed = urlparse(url.strip())
    parts = [part for part in parsed.path.split('/') if part]

    if len(parts) >= 4 and parts[0] == "profile" and parts[2] == "post":
        return parts[1], parts[3]

    raise ValueError(
        f"Invalid Bluesky post URL format: {url}"
    )


def bulk_gate_posts(file_path):
    # Ensure environment credentials are set
    if not BLUESKY_HANDLE or not BLUESKY_APP_PASSWORD:
        print("❌ Error: Both 'BLUESKY_HANDLE' and 'BLUESKY_APP_PASSWORD' environment variables must be set.")
        return

    # Ensure the input text file exists
    if not os.path.exists(file_path):
        print(f"❌ Error: The file at '{file_path}' does not exist.")
        return

    # Read and clean URLs from the file
    with open(file_path, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print("❌ Error: No URLs found in the text file.")
        return

    print(f"📚 Loaded {len(urls)} post URLs from file.")

    # Step 1: Log in once
    client = Client()
    print("🔑 Logging into Bluesky...")
    try:
        client.login(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)
        print("✅ Login successful!\n")
    except Exception as e:
        print(f"❌ Failed to log in: {e}")
        return

    # Tracking metrics
    success_count = 0
    fail_count = 0

    # Step 2: Loop through each URL
    for index, url in enumerate(urls):
        print(f"👉 [{index + 1}/{len(urls)}] Processing: {url}")

        try:
            handle_or_did, rkey = parse_post_url(url)
        except ValueError as e:
            print(f"   ⚠️ {e} - Skipping.")
            fail_count += 1
            print("-" * 40)
            continue

        # Resolve handle to DID if it's not a DID already
        author_did = handle_or_did
        if not author_did.startswith("did:"):
            try:
                resolution = client.com.atproto.identity.resolve_handle(params={'handle': handle_or_did})
                author_did = resolution.did
            except Exception as e:
                print(f"   ⚠️ Could not resolve handle '{handle_or_did}' to a DID: {e} - Skipping.")
                fail_count += 1
                print("-" * 40)
                continue

        # Double check that we actually own the post before trying to gate it
        if author_did != client.me.did:
            print("   ⚠️ Error: You cannot modify interaction settings on someone else's post! Skipping.")
            fail_count += 1
            print("-" * 40)
            continue

        post_uri = f"at://{author_did}/app.bsky.feed.post/{rkey}"
        post_success = True

        # Apply Reply Rules (Thread Gate - Mention Only)
        try:
            thread_rules = [models.AppBskyFeedThreadgate.MentionRule()]
            threadgate_record = models.AppBskyFeedThreadgate.Record(
                post=post_uri,
                allow=thread_rules,
                created_at=client.get_current_time_iso()
            )
            client.com.atproto.repo.put_record(
                models.ComAtprotoRepoPutRecord.Data(
                    repo=client.me.did,
                    collection='app.bsky.feed.threadgate',
                    rkey=rkey,
                    record=threadgate_record
                )
            )
            print("   ✅ Replies restricted to mentions only.")
        except AtProtocolError as e:
            print(f"   ⚠️ Failed to apply Thread Gate: {e}")
            post_success = False

        # Apply Quote Rules (Post Gate - Disable Quotes)
        try:
            post_rules = [models.AppBskyFeedPostgate.DisableRule()]
            postgate_record = models.AppBskyFeedPostgate.Record(
                post=post_uri,
                embedding_rules=post_rules,
                created_at=client.get_current_time_iso()
            )
            client.com.atproto.repo.put_record(
                models.ComAtprotoRepoPutRecord.Data(
                    repo=client.me.did,
                    collection='app.bsky.feed.postgate',
                    rkey=rkey,
                    record=postgate_record
                )
            )
            print("   ✅ Quotes disabled completely.")
        except AtProtocolError as e:
            print(f"   ⚠️ Failed to apply Post Gate: {e}")
            post_success = False

        if post_success:
            success_count += 1
        else:
            fail_count += 1

        # Step 3: Random delay (don't sleep after the final item)
        if index < len(urls) - 1:
            sleep_time = round(random.uniform(MIN_DELAY, MAX_DELAY), 2)
            print(f"⏳ Sleeping for {sleep_time} seconds before the next post...")
            time.sleep(sleep_time)

        print("-" * 40)

    # Summary
    print("\n🏁 Process complete!")
    print(f"📊 Summary: {success_count} succeeded, {fail_count} failed/skipped.")


if __name__ == "__main__":
    path = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/my_posts/newenglandtopnews_com_posts_07-16-2026-2_posts.txt"

    bulk_gate_posts(path)