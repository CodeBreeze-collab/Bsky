from datetime import datetime, timezone, timedelta
import requests


class BlueskyPostAuditor:

    def __init__(self):
        self.base_url = "https://public.api.bsky.app/xrpc"

    def _resolve_handle_to_did(self, handle: str) -> str:
        """Resolves a human-readable handle to its permanent DID."""
        try:
            endpoint = f"{self.base_url}/com.atproto.identity.resolveHandle"
            resp = requests.get(endpoint, params={"handle": handle}, timeout=5)
            if resp.status_code == 200:
                return resp.json().get("did")
        except Exception as e:
            print(f"[Warning] Failed to resolve handle {handle}: {e}")
        return None

    def audit_posts(
        self,
        handle: str,
        target_reposts: int = 10,
        age_threshold_days: float = 1.0,
        max_posts_to_scan: int = 50,
    ) -> list:
        """Scans an account's feed and returns posts that have failed to hit the

        repost threshold after the given time window has passed.
        """
        did = self._resolve_handle_to_did(handle)
        if not did:
            print(f"[Error] Could not resolve handle: {handle}")
            return []

        underperforming_posts = []
        cursor = None
        endpoint = f"{self.base_url}/app.bsky.feed.getAuthorFeed"
        now = datetime.now(timezone.utc)
        time_cutoff = timedelta(days=age_threshold_days)

        print(
            f"🔍 Auditing @{handle}... (Looking for posts older than {age_threshold_days} days with < {target_reposts} reposts)"
        )

        posts_scanned = 0

        while posts_scanned < max_posts_to_scan:
            # Fetch up to 100 items per chunk (or remaining count needed)
            chunk_limit = min(100, max_posts_to_scan - posts_scanned)
            params = {
                "actor": did,
                "filter": "posts_no_replies",  # Focus purely on their organic top-level posts
                "limit": chunk_limit,
            }
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
                    break  # Reached the end of their historical timeline

                for item in feed_items:
                    posts_scanned += 1

                    # Skip if this item is a third-party repost amplified by the target account
                    if "reason" in item:
                        continue

                    post_info = item.get("post", {})
                    indexed_at_str = post_info.get("indexedAt")

                    if not indexed_at_str:
                        continue

                    # Parse Bluesky's standard ISO timestamp (replacing 'Z' for Python datetime compatibility)
                    post_time = datetime.fromisoformat(
                        indexed_at_str.replace("Z", "+00:00")
                    )
                    post_age = now - post_time

                    # EVALUATION LOGIC:
                    # Is the post older than our timeframe window?
                    if post_age >= time_cutoff:
                        reposts = post_info.get("repostCount", 0)

                        # Did it fail to hit the target repost count?
                        if reposts < target_reposts:
                            uri = post_info.get("uri", "")
                            rkey = uri.split("/")[-1]
                            web_url = f"https://bsky.app/profile/{handle}/post/{rkey}"

                            underperforming_posts.append(
                                {
                                    "url": web_url,
                                    "reposts": reposts,
                                    "likes": post_info.get("likeCount", 0),
                                    "age_days": round(post_age.days + (post_age.seconds / 86400), 2),
                                }
                            )

                cursor = data.get("cursor")
                if not cursor:
                    break

            except Exception as e:
                print(f"[Network Error] Error retrieving feed chunk: {e}")
                break

        return underperforming_posts


# --- Execution Sandbox ---
if __name__ == "__main__":
    auditor = BlueskyPostAuditor()

    # --- Change parameters here ---
    TARGET_ACCOUNT = "morgfairsdogs.bsky.social"
    REPOST_THRESHOLD = 25  # Flag if it has less than this many reposts...
    AGE_THRESHOLD_DAYS = 1  # ...after being live for this many days (can use decimals like 0.5 for 12 hours)
    MAX_POSTS_TO_CHECK = 40  # How far back into their history to look

    flagged_posts = auditor.audit_posts(
        handle=TARGET_ACCOUNT,
        target_reposts=REPOST_THRESHOLD,
        age_threshold_days=AGE_THRESHOLD_DAYS,
        max_posts_to_scan=MAX_POSTS_TO_CHECK,
    )

    print("\n" + "=" * 50)
    print(f"AUDIT COMPLETE: Found {len(flagged_posts)} flagged posts.")
    print("=" * 50)

    for i, post in enumerate(flagged_posts, 1):
        print(f"\n📌 Flagged Post #{i}")
        print(f"🔗 URL: {post['url']}")
        print(f"⏱️ Age: {post['age_days']} days old")
        print(f"📊 Stats: {post['reposts']} Reposts | {post['likes']} Likes")
        print("-" * 30)