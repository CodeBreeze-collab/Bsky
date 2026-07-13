import os
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

        # Strips out query strings (?key=val), hashes (#anchor), and extra trailing slashes
        match = re.search(
            r"https://bsky\.app/profile/([^/?#\s]+)/post/([^/?#\s]+)", target
        )
        if not match:
            raise ValueError(
                "Target string is neither a valid AT URI nor a recognized Bluesky web URL."
            )

        handle_or_did, rkey = match.groups()

        if not handle_or_did.startswith("did:"):
            did = self._resolve_handle_to_did(handle_or_did)
            if not did:
                raise ValueError(
                    f"Could not resolve the handle '{handle_or_did}' extracted from the URL."
                )
        else:
            did = handle_or_did

        return f"at://{did}/app.bsky.feed.post/{rkey}"

    def get_likers(self, target_url_or_uri: str, max_results: int = 100) -> list:
        """Returns a list of clean handles (usernames) who liked the target comment/post."""
        try:
            at_uri = self._normalize_to_at_uri(target_url_or_uri)
        except ValueError as err:
            print(f"[Error] {err}")
            return []

        likers = []
        cursor = None
        endpoint = f"{self.base_url}/app.bsky.feed.getLikes"

        while len(likers) < max_results:
            chunk_limit = min(100, max_results - len(likers))
            params = {"uri": at_uri, "limit": chunk_limit}
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
                likes_chunk = data.get("likes", [])

                for item in likes_chunk:
                    actor_info = item.get("actor", {})
                    handle = actor_info.get("handle")
                    if handle:
                        likers.append(handle)

                cursor = data.get("cursor")
                if not cursor or not likes_chunk:
                    break

            except Exception as e:
                print(
                    f"[Network Error] Connection interrupted during cursor retrieval: {e}"
                )
                break

        return likers

    def get_likers_from_file(
        self, file_path: str, max_results_per_post: int = 100
    ) -> dict:
        """Reads Bluesky post links from a text file and collects likers for each."""
        results = {}

        if not os.path.exists(file_path):
            print(f"[Error] The file '{file_path}' does not exist.")
            return results

        with open(file_path, "r", encoding="utf-8") as f:
            urls = [
                line.strip()
                for line in f
                if line.strip() and not line.strip().startswith("#")
            ]

        if not urls:
            print(f"[Warning] No valid URLs found in '{file_path}'.")
            return results

        # print(f"Found {len(urls)} target posts in '{file_path}'. Processing queue... ")

        for index, url in enumerate(urls, 1):
            # print(f"\n[{index}/{len(urls)}] Target: {url}")
            likers = self.get_likers(url, max_results=max_results_per_post)
            # print(f" -> Found {len(likers)} likers:")

            # Print handles right now instead of waiting for the file to finish
            for handle in likers:
                print(f"{handle}")

            results[url] = likers

        return results


# --- Batch Execution ---
if __name__ == "__main__":
    fetcher = BlueskyCommentLikes()

    input_file = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/bsky_posts.txt"

    # Batch retrieval initialization (will print handles live)
    batch_results = fetcher.get_likers_from_file(
        input_file, max_results_per_post=50
    )

    # Compilation stat summary at the absolute end
    all_unique_handles = set()
    for handles in batch_results.values():
        all_unique_handles.update(handles)

    print("\n" + "=" * 40)
    print(f"BATCH COMPLETE: Collected {len(all_unique_handles)} unique users.")
    print("=" * 40)