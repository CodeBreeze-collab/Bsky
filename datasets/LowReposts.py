from datetime import datetime, timezone, timedelta
import json
import os
import requests

# Import the unified Google GenAI SDK
from google import genai


class BlueskyPostAuditor:

    def __init__(self):
        self.base_url = "https://public.api.bsky.app/xrpc"

        # Initialize the modern Gemini Client
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            self.gemini_client = genai.Client(api_key=api_key)
            self.gemini_enabled = True
            print("🤖 Modern Gemini GenAI Client initialized successfully.")
        else:
            self.gemini_enabled = False
            print("[Warning] GEMINI_API_KEY environment variable not found. Falling back to default categories.")

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

    def _extract_image_urls(self, post_info: dict) -> list:
        """Safely pulls image URLs from standard and quote/media post embeds."""
        image_urls = []
        embed = post_info.get("embed", {})
        images = []

        if embed.get("$type") == "app.bsky.embed.images#view":
            images = embed.get("images", [])
        elif embed.get("$type") == "app.bsky.embed.recordWithMedia#view":
            media = embed.get("media", {})
            if media.get("$type") == "app.bsky.embed.images#view":
                images = media.get("images", [])

        for img in images:
            url = img.get("fullsize") or img.get("thumb")
            if url:
                image_urls.append(url)

        return image_urls

    def _classify_with_gemini(self, text: str) -> dict:
        """Uses the modern google-genai client to categorize the rescue post."""
        if not self.gemini_enabled or not text.strip():
            return {"status": "General Update", "rescue_name": None}

        # Prompt updated to split donations into requested vs thanked
        prompt = f"""
        Analyze the following animal welfare / rescue social media post. 
        Categorize it into exactly ONE of these statuses:
        - Needs Foster
        - Needs Shelter Pull
        - Reserved for Rescue
        - Needs Donations
        - Donations Thanked
        - More Info about Animal
        - Group Summary
        - General Update

        Rules for classification (IMPORTANT: If a post fits 'Group Summary', that category takes precedence over others):
        1. "Group Summary": Collective daily updates, roundups, master lists, or tallies featuring multiple distinct animals at once (e.g., lists of daily pledge totals, multiple dogs remaining under kill command, or daily digests of multiple animals). Even if these animals individually need fosters or donations, a consolidated list or tally of them must be classified here.
        2. "Needs Foster": High priority request for a temporary foster home (typically focused on a single animal or single litter).
        3. "Needs Shelter Pull": Urgent plea asking an accredited rescue network to pull an animal from a high-kill/local shelter (typically focused on a single animal).
        4. "Reserved for Rescue": The animal has successfully secured placement, or is safe with a specific rescue. If a specific rescue's name is mentioned, extract it.
        5. "Needs Donations": Requests for financial help, sponsorships, medical funds, supplies, wishlists, GoFundMe links, or paid monthly subscriptions (e.g., support us for £1 a month) for a specific animal or sanctuary.
        6. "Donations Thanked": Acknowledging, thanking, or celebrating donations that have been received, pledges that have been paid, or fundraiser goals that have successfully been met.
        7. "More Info about Animal": Behavioral notes, medical updates, or bios expanding on a specific pet's personality.
        8. "General Update": Standard everyday content, generic sanctuary updates, heatwave warnings, or anything that doesn't cleanly fit the other options.

        Post text:
        \"\"\"{text}\"\"\"

        Return a JSON object matching this schema precisely:
        {{
          "status": "One of the exact strings listed above",
          "rescue_name": "String name of the rescue if status is 'Reserved for Rescue' and mentioned, otherwise null"
        }}
        """

        try:
            response = self.gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"[Warning] Gemini SDK classification failed: {e}")
            return {"status": "General Update", "rescue_name": None, "api_error": str(e)}

    def load_accounts(self, file_path: str) -> list:
        """Reads and cleans Bluesky handles from a .txt file."""
        if not os.path.exists(file_path):
            print(f"[Error] Accounts file not found: {file_path}")
            return []

        handles = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                clean_line = line.strip()
                if not clean_line or clean_line.startswith("#"):
                    continue
                if clean_line.startswith("@"):
                    clean_line = clean_line[1:]
                handles.append(clean_line)
        return handles

    def audit_and_export_posts(
            self,
            handle: str,
            output_file: str,
            target_reposts: int = 10,
            min_age_days: float = 1.0,
            max_age_days: float = 7.0,
            max_posts_to_scan: int = 50,
            filter_underperforming: bool = True,
    ) -> int:
        """Scans an account's feed and appends qualified posts to a JSONL file."""
        did = self._resolve_handle_to_did(handle)
        if not did:
            print(f"[Error] Could not resolve handle: {handle}")
            return 0

        cursor = None
        endpoint = f"{self.base_url}/app.bsky.feed.getAuthorFeed"
        now = datetime.now(timezone.utc)

        min_time_cutoff = timedelta(days=min_age_days)
        max_time_cutoff = timedelta(days=max_age_days) if max_age_days else None

        posts_scanned = 0
        posts_written = 0

        with open(output_file, "a", encoding="utf-8") as jsonl_file:
            while posts_scanned < max_posts_to_scan:
                chunk_limit = min(100, max_posts_to_scan - posts_scanned)
                params = {
                    "actor": did,
                    "filter": "posts_no_replies",
                    "limit": chunk_limit,
                }
                if cursor:
                    params["cursor"] = cursor

                try:
                    resp = requests.get(endpoint, params=params, timeout=10)
                    if resp.status_code != 200:
                        print(f"[API Error] Status {resp.status_code} for {handle}")
                        break

                    data = resp.json()
                    feed_items = data.get("feed", [])

                    if not feed_items:
                        break

                    for item in feed_items:
                        posts_scanned += 1
                        post_info = item.get("post", {})

                        is_repost = (
                                "reason" in item
                                and item["reason"].get("$type") == "app.bsky.feed.defs#reasonRepost"
                        )

                        embed = post_info.get("embed", {})
                        embed_type = embed.get("$type", "")
                        is_quote_repost = embed_type in [
                            "app.bsky.embed.record#view",
                            "app.bsky.embed.recordWithMedia#view"
                        ]

                        indexed_at_str = post_info.get("indexedAt")
                        if not indexed_at_str:
                            continue

                        post_time = datetime.fromisoformat(
                            indexed_at_str.replace("Z", "+00:00")
                        )
                        post_age = now - post_time

                        # Age & Performance Filters
                        if filter_underperforming:
                            if post_age < min_time_cutoff:
                                continue
                            if max_time_cutoff and post_age > max_time_cutoff:
                                continue

                            reposts = post_info.get("repostCount", 0)
                            if reposts >= target_reposts:
                                continue

                        author_info = post_info.get("author", {})
                        author_handle = author_info.get("handle", handle)

                        uri = post_info.get("uri", "")
                        rkey = uri.split("/")[-1] if uri else ""
                        post_url = (
                            f"https://bsky.app/profile/{author_handle}/post/{rkey}"
                            if rkey
                            else ""
                        )

                        record = post_info.get("record", {})
                        text = record.get("text", "")

                        # Process classification with the updated status list
                        gemini_res = self._classify_with_gemini(text)
                        category = gemini_res.get("status", "General Update")
                        cid = post_info.get("cid", "")

                        # Structure data matching requirements
                        post_data = {
                            "scanned_via": handle,
                            "author_handle": author_handle,
                            "post_url": post_url,
                            "uri": uri,
                            "cid": cid,
                            "is_repost": is_repost,
                            "is_quote_repost": is_quote_repost,
                            "category": category,
                            "text": text,
                            "image_urls": self._extract_image_urls(post_info),
                            "posted_at": record.get("createdAt"),
                            "indexedAt": indexed_at_str,
                            "gemini_response": gemini_res,
                        }

                        # Stream out straight to JSONL line
                        json_line = json.dumps(post_data, ensure_ascii=False)
                        jsonl_file.write(json_line + "\n")
                        posts_written += 1

                    cursor = data.get("cursor")
                    if not cursor:
                        break

                except Exception as e:
                    print(f"[Network Error] Error retrieving feed chunk for {handle}: {e}")
                    break

        return posts_written


# --- Execution Sandbox ---
if __name__ == "__main__":
    auditor = BlueskyPostAuditor()

    ACCOUNTS_FILE = "accounts.txt"
    OUTPUT_FILE = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help/07-16-2026/low-reposts-3.jsonl"

    REPOST_THRESHOLD = 25
    MIN_AGE_DAYS = 1.0
    MAX_AGE_DAYS = 2.0
    MAX_POSTS_TO_CHECK = 50
    FILTER_UNDERPERFORMING = True

    if not os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            f.write("# Put your Bluesky handles below, one per line:\n")
            f.write("minisanctuary.bsky.social\n")
            f.write("crits4cats.org\n")
        print(f"Created sample '{ACCOUNTS_FILE}'. Populating config...")

    target_accounts = auditor.load_accounts(ACCOUNTS_FILE)

    if target_accounts:
        print(f"Loaded {len(target_accounts)} handles from {ACCOUNTS_FILE}.")
        print(f"Auditing posts between {MIN_AGE_DAYS} and {MAX_AGE_DAYS} days old.")
        print(f"Writing matching entries to: {OUTPUT_FILE}\n")

        if os.path.exists(OUTPUT_FILE):
            os.remove(OUTPUT_FILE)

        total_saved = 0
        for handle in target_accounts:
            saved_count = auditor.audit_and_export_posts(
                handle=handle,
                output_file=OUTPUT_FILE,
                target_reposts=REPOST_THRESHOLD,
                min_age_days=MIN_AGE_DAYS,
                max_age_days=MAX_AGE_DAYS,
                max_posts_to_scan=MAX_POSTS_TO_CHECK,
                filter_underperforming=FILTER_UNDERPERFORMING,
            )
            print(f"✅ Saved {saved_count} classified posts for @{handle}")
            total_saved += saved_count

        print("\n" + "=" * 50)
        print(f"Run complete! Total of {total_saved} records written to {OUTPUT_FILE}.")
        print("=" * 50)