import requests


class BlueskyAuthorFeed:

    def __init__(self):
        self.base_url = "https://public.api.bsky.app/xrpc"

    def _resolve_handle_to_did(self, handle: str) -> str:
        """Resolves a human-readable handle (like user.bsky.social) to its permanent DID."""
        try:
            endpoint = f"{self.base_url}/com.atproto.identity.resolveHandle"
            resp = requests.get(endpoint, params={"handle": handle}, timeout=5)
            if resp.status_code == 200:
                return resp.json().get("did")
        except Exception as e:
            print(f"[Warning] Failed to resolve handle {handle}: {e}")
        return None

    def get_latest_post_urls(
        self,
        handle: str,
        max_results: int = 20,
        include_replies: bool = False,
        include_reposts: bool = False,
    ) -> list:
        """Fetches the latest `n` post URLs for a given handle.

        Allows filtering out replies and amplified reposts.
        """
        # Resolve to DID first to verify the account exists
        did = self._resolve_handle_to_did(handle)
        if not did:
            print(f"[Error] Could not resolve handle: {handle}")
            return []

        # Bluesky API filter options: 'posts_with_replies' or 'posts_no_replies'
        api_filter = "posts_with_replies" if include_replies else "posts_no_replies"

        post_urls = []
        cursor = None
        endpoint = f"{self.base_url}/app.bsky.feed.getAuthorFeed"

        print(f"Fetching feed for {handle} (Filter: {api_filter})...")

        # Keep paginating until we reach our max target length or run out of feed
        while len(post_urls) < max_results:
            # Request chunks up to the API ceiling of 100 items per call
            params = {"actor": did, "filter": api_filter, "limit": 100}
            if cursor:
                params["cursor"] = cursor

            try:
                resp = requests.get(endpoint, params=params, timeout=10)
                if resp.status_code != 200:
                    print(
                        f"[API Error] Server returned status code {resp.status_code}"
                    )
                    break

                data = resp.json()
                feed_items = data.get("feed", [])

                if not feed_items:
                    break  # End of the timeline reached

                for item in feed_items:
                    if len(post_urls) >= max_results:
                        break

                    # Strip out third-party reposts if the user only wants original content
                    if not include_reposts and "reason" in item:
                        # Reposts contain a 'reason' object detailing who reposted it
                        continue

                    post_info = item.get("post", {})
                    uri = post_info.get("uri")  # Format: at://did:.../app.bsky.feed.post/rkey

                    if uri:
                        # Extract the unique record key (rkey) from the end of the AT-URI
                        rkey = uri.split("/")[-1]

                        # Pull actual author handle to handle custom domains/vanity updates accurately
                        author_handle = post_info.get("author", {}).get(
                            "handle", handle
                        )

                        # Construct clean browser URL
                        web_url = f"https://bsky.app/profile/{author_handle}/post/{rkey}"
                        post_urls.append(web_url)

                # Paginate using the server's cursor point
                cursor = data.get("cursor")
                if not cursor:
                    break

            except Exception as e:
                print(f"[Network Error] Error retrieving feed chunks: {e}")
                break

        return post_urls[:max_results]


# --- Verification Sandbox ---
if __name__ == "__main__":
    scraper = BlueskyAuthorFeed()

    # Configuration Parameters
    target_handle = "morgfairsdogs.bsky.social"
    count_to_fetch = 15

    # Fetch URLs
    urls = scraper.get_latest_post_urls(
        handle=target_handle,
        max_results=count_to_fetch,
        include_replies=False,  # Set True to grab comments they left on other threads
        include_reposts=False,  # Set True to include items they hit the "Repost" button on
    )

    # Print out results
    print(f"\n--- Latest {len(urls)} Posts for @{target_handle} ---")
    for i, url in enumerate(urls, 1):
        print(f"{url}")