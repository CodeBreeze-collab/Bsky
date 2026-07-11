import os
import requests
import json
import time
from datetime import datetime, timezone


class BlueskyAuditor:
    API_BASE_URL = "https://bsky.social/xrpc"

    def __init__(self, handle: str, password: str):
        self.handle = handle.lower().lstrip('@')
        self.password = password
        self.token = None
        self.headers = {}
        self._authenticate()

    def _authenticate(self):
        """Initializes the session and stores the JWT."""
        url = f"{self.API_BASE_URL}/com.atproto.server.createSession"
        res = requests.post(url, json={"identifier": self.handle, "password": self.password})
        res.raise_for_status()
        self.token = res.json()["accessJwt"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def _paginate(self, endpoint, params, total_needed=None):
        """Helper to handle cursor-based pagination while respecting API limits."""
        items = []
        cursor = None

        while True:
            if cursor:
                params['cursor'] = cursor

            params['limit'] = 100
            if total_needed:
                remaining = total_needed - len(items)
                params['limit'] = min(remaining, 100)

            res = requests.get(f"{self.API_BASE_URL}/{endpoint}", headers=self.headers, params=params)

            if res.status_code == 429:
                print("⚠️ Rate limit hit! Sleeping for 30 seconds...")
                time.sleep(30)
                continue

            res.raise_for_status()
            data = res.json()

            # Identify the data key based on the endpoint
            batch = data.get('feed') or data.get('likes') or data.get('repostedBy') or []
            if not batch:
                break

            items.extend(batch)

            if total_needed and len(items) >= total_needed:
                items = items[:total_needed]
                break

            cursor = data.get('cursor')
            if not cursor:
                break

            time.sleep(0.4)  # Small safety delay for rate limits
        return items

    def get_post_interactions(self, post_uri: str):
        """Gathers unique DIDs and handles from likes, reposts, and replies."""
        interactors = {}

        # 1. Get Likes
        try:
            likes = self._paginate("app.bsky.feed.getLikes", {"uri": post_uri})
            for l in likes:
                actor = l['actor']
                interactors[actor['did']] = actor['handle']
        except Exception as e:
            print(f"      ⚠️ Error fetching likes: {e}")

        # 2. Get Reposts
        try:
            reposts = self._paginate("app.bsky.feed.getRepostedBy", {"uri": post_uri})
            for r in reposts:
                interactors[r['did']] = r['handle']
        except Exception as e:
            print(f"      ⚠️ Error fetching reposts: {e}")

        # 3. Get Replies
        try:
            res = requests.get(
                f"{self.API_BASE_URL}/app.bsky.feed.getPostThread",
                headers=self.headers,
                params={"uri": post_uri, "depth": 10}
            )
            if res.status_code == 200:
                self._extract_repliers(res.json().get('thread', {}), interactors)
        except Exception as e:
            print(f"      ⚠️ Error fetching thread: {e}")

        return interactors

    def _extract_repliers(self, thread_node, interactor_map):
        """Recursively traverses a thread to find all repliers."""
        replies = thread_node.get('replies', [])
        for reply in replies:
            post = reply.get('post')
            if post:
                author = post['author']
                interactor_map[author['did']] = author['handle']
            if 'replies' in reply:
                self._extract_repliers(reply, interactor_map)

    def export_interaction_report(self, target_handle: str, output_file: str, post_limit=1000):
        """Main execution flow: fetches feed and audits every post."""
        processed_ids = set()
        if os.path.exists(output_file):
            with open(output_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        processed_ids.add(json.loads(line)['post_id'])
                    except:
                        continue
            print(f"✅ Already processed {len(processed_ids)} posts. Skipping...")

        # Resolve Handle to DID
        print(f"🔍 Resolving @{target_handle}...")
        resolve_url = f"{self.API_BASE_URL}/com.atproto.identity.resolveHandle"
        res = requests.get(resolve_url, params={"handle": target_handle})
        res.raise_for_status()
        target_did = res.json().get("did")

        # Fetch the feed
        print(f"📡 Fetching feed for {target_handle}...")
        feed_items = self._paginate(
            "app.bsky.feed.getAuthorFeed",
            {"actor": target_did, "filter": "posts_with_replies"},
            total_needed=post_limit
        )

        print(f"🚀 Found {len(feed_items)} posts. Deep scanning interactions...")

        with open(output_file, 'a', encoding='utf-8') as f:
            for item in feed_items:
                post = item['post']
                post_uri = post['uri']
                post_id = post_uri.split('/')[-1]

                if post_id in processed_ids:
                    continue

                print(f"  🧵 Scoping: {post_id}")
                try:
                    interactors = self.get_post_interactions(post_uri)
                    user_list = [{"handle": h, "did": d} for d, h in interactors.items()]

                    record = {
                        "post_id": post_id,
                        "post_uri": post_uri,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "interactor_count": len(user_list),
                        "interactors": user_list
                    }
                    f.write(json.dumps(record) + '\n')
                    f.flush()
                except Exception as e:
                    print(f"  ❌ Error processing post {post_id}: {e}")
                    continue

        print(f"🏁 Audit complete for @{target_handle}")


# --- Execution ---
if __name__ == "__main__":
    # Ensure you set this in your terminal: export BLUESKY_APP_PASSWORD='your-pw'
    MY_HANDLE = "vegansearchengine.bsky.social"
    MY_PWD = os.environ.get("BLUESKY_APP_PASSWORD")

    if not MY_PWD:
        print("🚨 Set your BLUESKY_APP_PASSWORD environment variable!")
    else:
        auditor = BlueskyAuditor(MY_HANDLE, MY_PWD)
        auditor.export_interaction_report(
            target_handle="atproto.com",
            output_file="interactions.jsonl",
            post_limit=2000
        )