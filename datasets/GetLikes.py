import os
import re
import requests


class BlueskyEngagementTracker:

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
        """Returns a list of clean handles (usernames) who liked the target post."""
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

    def get_reposters(self, target_url_or_uri: str, max_results: int = 100) -> list:
        """Returns a list of clean handles (usernames) who reposted the target post."""
        try:
            at_uri = self._normalize_to_at_uri(target_url_or_uri)
        except ValueError as err:
            print(f"[Error] {err}")
            return []

        reposters = []
        cursor = None
        endpoint = f"{self.base_url}/app.bsky.feed.getRepostedBy"

        while len(reposters) < max_results:
            chunk_limit = min(100, max_results - len(reposters))
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
                repost_chunk = data.get("repostedBy", [])

                for profile in repost_chunk:
                    handle = profile.get("handle")
                    if handle:
                        reposters.append(handle)

                cursor = data.get("cursor")
                if not cursor or not repost_chunk:
                    break

            except Exception as e:
                print(
                    f"[Network Error] Connection interrupted during cursor retrieval: {e}"
                )
                break

        return reposters

    def get_engagement_from_file(
            self, file_path: str, max_results_per_post: int = 100
    ) -> dict:
        """Reads Bluesky post links from a text file and collects both likers and reposters."""
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

        for index, url in enumerate(urls, 1):
            print(f"\n[{index}/{len(urls)}] Scraping: {url}")

            likers = self.get_likers(url, max_results=max_results_per_post)
            reposters = self.get_reposters(url, max_results=max_results_per_post)

            print(f" -> Found {len(likers)} likes and {len(reposters)} reposts.")

            results[url] = {
                "likers": likers,
                "reposters": reposters
            }

        return results


# --- Batch Execution ---
if __name__ == "__main__":
    tracker = BlueskyEngagementTracker()

    input_file = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/bsky_posts.txt"

    # Batch retrieval initialization (will print extraction live)
    batch_results = tracker.get_engagement_from_file(
        input_file, max_results_per_post=50
    )

    if batch_results:
        common_likers = None
        common_reposters = None
        common_any_engagement = None
        all_unique_users = set()

        # Step through the posts sequentially to run set intersections
        for url, engagement in batch_results.items():
            post_likers = set(engagement["likers"])
            post_reposters = set(engagement["reposters"])
            post_any = post_likers.union(post_reposters)

            # Accumulate overall unique users
            all_unique_users.update(post_any)

            if common_likers is None:
                common_likers = post_likers
                common_reposters = post_reposters
                common_any_engagement = post_any
            else:
                common_likers.intersection_update(post_likers)
                common_reposters.intersection_update(post_reposters)
                common_any_engagement.intersection_update(post_any)

        # Fallbacks in case collections were completely empty
        common_likers = common_likers or set()
        common_reposters = common_reposters or set()
        common_any_engagement = common_any_engagement or set()

        # --- Statistics Output Summary ---
        print("\n" + "=" * 60)
        print(f"BATCH COMPLETE: Tracked {len(all_unique_users)} unique dynamic users overall.")
        print("=" * 60)

        print(f"\n[1] Users who LIKED every single post ({len(common_likers)}):")
        if common_likers:
            for handle in sorted(common_likers):
                print(f"  -> {handle}")
        else:
            print("  -> None")

        print(f"\n[2] Users who REPOSTED every single post ({len(common_reposters)}):")
        if common_reposters:
            for handle in sorted(common_reposters):
                print(f"  -> {handle}")
        else:
            print("  -> None")

        print(f"\n[3] Users who ENGAGED (Like OR Repost) with every single post ({len(common_any_engagement)}):")
        if common_any_engagement:
            for handle in sorted(common_any_engagement):
                print(f"  -> {handle}")
        else:
            print("  -> None")