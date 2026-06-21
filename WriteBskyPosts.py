import json
from atproto import Client

# --- Authentication (The "Actor" account) ---
MY_HANDLE = 'ethicalsearch.bsky.social'
MY_APP_PASSWORD = 'bilm-gvql-5toq-d434'

# --- Target (The account you want to scrape) ---
TARGET_HANDLE = 'vegansearchengine.bsky.social'# 'nycacckills.bsky.social' #'newenglandtopnews.bsky.social' #'the-epstein-class.bsky.social'


def fetch_external_posts():
    client = Client()

    try:
        # Log in as the "Actor"
        print(f"Logging in as {MY_HANDLE}... {MY_APP_PASSWORD}")
        client.login(MY_HANDLE, MY_APP_PASSWORD)

        params = {'actor': TARGET_HANDLE}
        cursor = None
        count = 0

        filename = f'/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/my_posts/{TARGET_HANDLE.replace(".", "_")}_posts_06-01-2026.jsonl'

        with open(filename, 'w', encoding='utf-8') as f:
            print(f"Fetching posts from {TARGET_HANDLE}...")

            while True:
                # Fetching the feed for the TARGET_HANDLE
                profile_feed = client.app.bsky.feed.get_author_feed(
                    params={**params, 'cursor': cursor}
                )

                for feed_view in profile_feed.feed:
                    post = feed_view.post

                    # Extract URLs from the rich text facets
                    urls = []
                    if post.record.facets:
                        for facet in post.record.facets:
                            for feature in facet.features:
                                if hasattr(feature, 'uri'):
                                    urls.append(feature.uri)

                    # Build the human-readable web URL
                    rkey = post.uri.split('/')[-1]
                    post_url = f"https://bsky.app/profile/{post.author.handle}/post/{rkey}"

                    # --- NEW: Check if it is a Reply ---
                    # If post.record has a 'reply' property, it's a reply
                    reply_metadata = getattr(post.record, 'reply', None)
                    is_reply = reply_metadata is not None

                    # Optional: Grab what it is replying to if you want to reconstruct threads later
                    parent_uri = reply_metadata.parent.uri if is_reply else None

                    # --- NEW: Check if it is a Repost ---
                    # If feed_view has a 'reason', the target user just reposted it
                    is_repost = getattr(feed_view, 'reason', None) is not None

                    # Construct the updated record payload
                    record = {
                        "url": post_url,
                        "date": post.record.created_at,
                        "text": post.record.text,
                        "urls": urls,
                        "is_reply": is_reply,
                        "is_repost": is_repost,
                        "parent_uri": parent_uri  # Handy to track down the parent post
                    }

                    f.write(json.dumps(record) + '\n')
                    count += 1

                # Pagination logic
                cursor = profile_feed.cursor
                if not cursor:
                    break

                print(f"Downloaded {count} posts so far...")

        print(f"Success! {count} posts saved to {filename}")

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    fetch_external_posts()