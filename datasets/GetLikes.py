import re
import requests


class BlueskyCommentLikes:
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

    def _normalize_to_at_uri(self, target: str) -> str:
        """Normalizes either a web URL or an existing AT URI into a DID-based AT URI."""
        if target.startswith("at://"):
            return target

        # Parse standard browser post link
        match = re.search(r"https://bsky\.app/profile/([^/]+)/post/([^/]+)", target)
        if not match:
            raise ValueError("Target string is neither a valid AT URI nor a recognized Bluesky web URL.")

        handle_or_did, rkey = match.groups()

        # Resolve to DID if it's a vanity/human handle
        if not handle_or_did.startswith("did:"):
            did = self._resolve_handle_to_did(handle_or_did)
            if not did:
                raise ValueError(f"Could not resolve the handle '{handle_or_did}' extracted from the URL.")
        else:
            did = handle_or_did

        return f"at://{did}/app.bsky.feed.post/{rkey}"

    def get_likers(self, target_url_or_uri: str, max_results: int = 100) -> list:
        """
        Returns a list of clean handles (usernames) who liked the target comment/post.
        Handles full pagination loops automatically up to your designated max_results limit.
        """
        try:
            at_uri = self._normalize_to_at_uri(target_url_or_uri)
        except ValueError as err:
            print(f"[Error] {err}")
            return []

        likers = []
        cursor = None
        endpoint = f"{self.base_url}/app.bsky.feed.getLikes"

        # Loop until we run out of likes or hit our target cap
        while len(likers) < max_results:
            # Calculate next chunk size (API max is 100 items per request)
            chunk_limit = min(100, max_results - len(likers))

            params = {"uri": at_uri, "limit": chunk_limit}
            if cursor:
                params["cursor"] = cursor

            try:
                resp = requests.get(endpoint, params=params, timeout=10)
                if resp.status_code != 200:
                    print(f"[API Error] Server returned status code {resp.status_code}")
                    break

                data = resp.json()
                likes_chunk = data.get("likes", [])

                for item in likes_chunk:
                    actor_info = item.get("actor", {})
                    handle = actor_info.get("handle")
                    if handle:
                        likers.append(handle)

                # Paginate using the server cursor token
                cursor = data.get("cursor")
                if not cursor or not likes_chunk:
                    break  # No more records left on the server thread

            except Exception as e:
                print(f"[Network Error] Connection interrupted during cursor retrieval: {e}")
                break

        return likers


# --- Verification Sandbox ---
if __name__ == "__main__":
    fetcher = BlueskyCommentLikes()

    # Test link (Can be a top-level post or a nested comment link)
    sample_post = "https://bsky.app/profile/stlcatfishmike.bsky.social/post/3mqge4mupyc2u"

    print("Connecting to Bluesky ecosystem...")
    usernames = fetcher.get_likers(sample_post, max_results=50)

    print(f"\nFound {len(usernames)} account profiles:")
    for username in usernames:
        print(f"👉 @{username}")