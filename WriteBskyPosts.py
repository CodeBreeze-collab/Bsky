import json
from atproto import Client

# --- Authentication (The "Actor" account) ---
MY_HANDLE = 'ethicalsearch.bsky.social'
MY_APP_PASSWORD = 'bilm-gvql-5toq-d434'

# --- Target (The account you want to scrape) ---
TARGET_HANDLE = 'newenglandtopnews.bsky.social'


def fetch_external_posts():
    client = Client()

    try:
        # Log in as the "Actor"
        print(f"Logging in as {MY_HANDLE}...")
        client.login(MY_HANDLE, MY_APP_PASSWORD)

        params = {'actor': TARGET_HANDLE}
        cursor = None
        count = 0

        filename = f'{TARGET_HANDLE.replace(".", "_")}_posts_07-16-2026-2.jsonl'

        with open(filename, 'w', encoding='utf-8') as f:
            print(f"Fetching posts from {TARGET_HANDLE}...")

            while True:
                # Fetching the feed for the TARGET_HANDLE
                profile_feed = client.app.bsky.feed.get_author_feed(
                    params={**params, 'cursor': cursor}
                )

                for feed_view in profile_feed.feed:
                    post = feed_view.post

                    # Identify the embed type dynamically (if any)
                    embed_type = None
                    if post.embed:
                        embed_type = getattr(post.embed, 'py_type', None) or getattr(post.embed, '$type', None)

                    # 1. Extract text URLs from the rich text facets
                    urls = []
                    if post.record.facets:
                        for facet in post.record.facets:
                            for feature in facet.features:
                                if hasattr(feature, 'uri'):
                                    urls.append(feature.uri)

                    # 2. Extract Embedded Media Image URLs
                    image_urls = []
                    if embed_type:
                        # Handle standard images or the 5-10 image galleries
                        if embed_type in ['app.bsky.embed.images#view', 'app.bsky.embed.gallery#view']:
                            images_list = getattr(post.embed, 'images', None) or getattr(post.embed, 'items', None)
                            if images_list:
                                for img in images_list:
                                    image_urls.append(img.fullsize)

                        # Handle images inside quote tweets (Record with Media)
                        elif embed_type == 'app.bsky.embed.recordWithMedia#view':
                            media = getattr(post.embed, 'media', None)
                            if media:
                                media_type = getattr(media, 'py_type', None) or getattr(media, '$type', None)
                                if media_type in ['app.bsky.embed.images#view', 'app.bsky.embed.gallery#view']:
                                    images_list = getattr(media, 'images', None) or getattr(media, 'items', None)
                                    if images_list:
                                        for img in images_list:
                                            image_urls.append(img.fullsize)

                    # Build the human-readable web URL
                    rkey = post.uri.split('/')[-1]
                    post_url = f"https://bsky.app/profile/{post.author.handle}/post/{rkey}"

                    # Check if it is a Reply
                    reply_metadata = getattr(post.record, 'reply', None)
                    is_reply = reply_metadata is not None
                    parent_uri = reply_metadata.parent.uri if is_reply else None

                    # Check if it is a Repost
                    # In get_author_feed, a repost is indicated by a 'reason' object (ReasonRepost)
                    is_repost = False
                    reason = getattr(feed_view, 'reason', None)
                    if reason:
                        reason_type = getattr(reason, 'py_type', None) or getattr(reason, '$type', None) or ""
                        if "reasonRepost" in reason_type:
                            is_repost = True

                    # Check if it is a Quote Repost
                    # Quotes embed other records (with or without media)
                    is_quote_repost = False
                    if embed_type:
                        is_quote_repost = any(
                            t in embed_type
                            for t in ['app.bsky.embed.record', 'app.bsky.embed.recordWithMedia']
                        )

                    # Construct the final record payload
                    record = {
                        "url": post_url,
                        "date": post.record.created_at,
                        "text": post.record.text,
                        "urls": urls,
                        "image_urls": image_urls,
                        "is_reply": is_reply,
                        "is_repost": is_repost,
                        "is_quote_repost": is_quote_repost,  # <-- Added flag
                        "parent_uri": parent_uri
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