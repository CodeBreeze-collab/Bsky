import os
import sys
from atproto import Client, models
from typing import List, Dict, Any

# --- Configuration ---
TARGET_HANDLE = "geofhuth.bsky.social"
# >>> 1. Define your search keyword here <<<
SEARCH_KEYWORD = "pets"


# --- Core Functions ---

def retrieve_author_posts(client: Client, actor_handle: str, limit: int = 20, query: str = None) -> List[
    Dict[str, Any]]:
    """
    Retrieves posts from a specified Bluesky account, filtered by a search keyword.

    If 'query' is provided, it uses searchPosts. Otherwise, it defaults to getAuthorFeed.
    """

    if not query:
        print("⚠️ No search query provided. Defaulting to chronological feed retrieval (getAuthorFeed).")
        # Reuse the old logic if no search term is present (optional, but robust)
        return retrieve_author_feed(client, actor_handle, limit)

    # --- NEW SEARCH LOGIC ---
    print(f"📡 Searching up to {limit} posts by @{actor_handle} for keyword: '{query}'...")

    all_posts = []
    cursor = None

    while len(all_posts) < limit:
        page_limit = min(limit - len(all_posts), 100)

        try:
            # 1. Create the explicit Params object for searchPosts
            params = models.AppBskyFeedSearchPosts.Params(
                # The search term goes in the 'q' parameter
                q=query,
                # The author filter ensures results are from the target account
                author=actor_handle,
                limit=page_limit,
                cursor=cursor
            )

            # 2. Call the searchPosts endpoint
            response = client.app.bsky.feed.search_posts(params)

            # The structure of the response is slightly different for search
            all_posts.extend(response.posts)

            cursor = response.cursor
            if not cursor:
                print("✅ Reached the end of search results.")
                break

            if len(all_posts) >= limit:
                break

        except Exception as e:
            print(f"🚨 An error occurred while fetching posts: {e}")
            break

    return all_posts[:limit]


# --- Helper function for non-search (renamed for clarity) ---
def retrieve_author_feed(client: Client, actor_handle: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Retrieves the chronological author feed without searching."""
    print(f"📡 Fetching up to {limit} items from @{actor_handle}'s chronological feed...")
    all_posts = []
    cursor = None
    while len(all_posts) < limit:
        page_limit = min(limit - len(all_posts), 100)
        try:
            params = models.AppBskyFeedGetAuthorFeed.Params(
                actor=actor_handle,
                limit=page_limit,
                cursor=cursor
            )
            response = client.app.bsky.feed.get_author_feed(params)
            all_posts.extend(response.feed)
            cursor = response.cursor
            if not cursor: break
            if len(all_posts) >= limit: break
        except Exception as e:
            print(f"🚨 An error occurred while fetching the chronological feed: {e}")
            break
    return all_posts[:limit]


def display_posts(posts: List[Dict[str, Any]]):
    """
    Formats and prints the post details to the console (now with no text truncation).
    """
    print(f"\n--- Found {len(posts)} Post(s) for @{TARGET_HANDLE} ---")

    for i, post_item in enumerate(posts):
        post_obj = post_item.post if hasattr(post_item, 'post') else post_item

        if not hasattr(post_obj, 'record'):
            print(f"\n{i + 1}. [ITEM SKIPPED] Missing post record data.")
            continue

        post_record = post_obj.record

        # 1. Get and clean the content text (removes newlines)
        content_text = getattr(post_record, 'text', "[No Text Content]").replace('\n', ' ')
        author_handle = post_obj.author.handle

        # 2. Determine post type
        is_post_record = getattr(post_record, 'type', None) == 'app.bsky.feed.post'
        is_a_reply = getattr(post_record, 'reply', None) is not None

        post_type = 'POST'  # Initialize to a safe default
        if not is_post_record:
            post_type = 'UNKNOWN'
        elif is_a_reply:
            post_type = 'REPLY'

        # 3. Construct the display string (uses the full content_text)
        # FIX: This line is now correctly placed AFTER post_type is set.
        display_str = f"[{post_type}] Content: \"{content_text}\""

        print(f"\n{i + 1}. Author: @{author_handle}")
        print(f"   URI: {post_obj.uri}")
        print(f"   {display_str}")
        print("-" * 20)


def main():
    """
    Main execution function: authenticates and retrieves the posts.
    """

    client = Client()

    # 1. Login Logic
    try:
        username = os.environ.get("BS_USERNAME")
        password = os.environ.get("BS_PASSWORD")

        if username and password:
            client.login(username, password)
        # else, proceed unauthenticated
    except Exception:
        # If login fails, proceed unauthenticated
        pass

    # 2. Retrieve and display the posts using the search term
    post_limit = 15
    author_posts = retrieve_author_posts(client, TARGET_HANDLE, limit=post_limit, query=SEARCH_KEYWORD)

    if author_posts:
        display_posts(author_posts)
    else:
        print(f"\nNo posts found for @{TARGET_HANDLE} containing the keyword '{SEARCH_KEYWORD}'.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nFATAL UNHANDLED ERROR: {e}")
        sys.exit(1)