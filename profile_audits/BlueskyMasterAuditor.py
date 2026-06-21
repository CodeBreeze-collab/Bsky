import os
import time
import re
from datetime import datetime, timezone
from atproto import Client, models


class BlueskyMasterAuditor:
    def __init__(self, handle, password, keywords):
        self.client = Client()
        self.client.login(handle, password)
        self.handle = handle.lower()
        self.keywords = keywords
        print(f"✅ Logged in as {self.handle}")

    def get_days_since_active(self, did):
        """Checks the last post date for a specific DID."""
        try:
            feed = self.client.app.bsky.feed.get_author_feed(actor=did, limit=1)
            if not feed.feed:
                return 9999  # No posts found

            last_post = feed.feed[0].post.indexed_at
            last_dt = datetime.fromisoformat(last_post.replace('Z', '+00:00'))
            delta = datetime.now(timezone.utc) - last_dt
            return delta.days
        except Exception:
            return -1

    def matches_blacklist(self, bio):
        """Checks bio for keywords while respecting 'no' negations."""
        if not bio: return []
        bio_lower = bio.lower()
        matches = []
        for kw in self.keywords:
            # Matches keyword NOT preceded by 'no '
            pattern = rf"(?<!\bno\s){re.escape(kw.lower())}"
            if re.search(pattern, bio_lower):
                matches.append(kw)
        return matches

    def run_audit(self, output_file, inactivity_threshold=30):
        print(f"🔍 Starting full audit of accounts followed by {self.handle}...")

        cursor = None
        with open(output_file, "w", encoding="utf-8") as f:
            # Header
            f.write("handle\tdays_inactive\tflagged_keywords\tfollow_uri\taction_recommended\n")

            while True:
                # 1. Fetch Follows
                response = self.client.app.bsky.graph.get_follows(actor=self.handle, cursor=cursor)

                for follow in response.follows:
                    handle = follow.handle
                    did = follow.did
                    bio = follow.description or ""
                    # The follow_uri is stored in the 'viewer' field
                    follow_uri = follow.viewer.following if follow.viewer else None

                    # 2. Analyze Activity & Content
                    days = self.get_days_since_active(did)
                    flags = self.matches_blacklist(bio)

                    # 3. Decision Logic
                    reason = []
                    if days >= inactivity_threshold: reason.append(f"Inactive ({days}d)")
                    if flags: reason.append(f"Flagged: {', '.join(flags)}")

                    action = "UNFOLLOW" if reason else "KEEP"

                    print(f"[{action}] @{handle:.<30} | {days} days | Flags: {flags}")

                    # 4. Save to TSV
                    f.write(f"{handle}\t{days}\t{','.join(flags)}\t{follow_uri}\t{action}\n")

                    time.sleep(0.5)  # Gentle rate limiting

                cursor = response.cursor
                if not cursor: break

        print(f"\n✨ Audit complete. Report saved to: {output_file}")


# --- Execute ---
if __name__ == "__main__":
    KEYWORDS = ["porn", "onlyfans", "nsfw", "hunting", "fishing"]
    # Be sure to set your env vars!
    AUDITOR = BlueskyMasterAuditor(
        handle="vegansearchengine.bsky.social",
        password=os.environ.get("BLUESKY_APP_PASSWORD"),
        keywords=KEYWORDS
    )

    REPORT_PATH = f"master_audit_{datetime.now().strftime('%Y%m%d')}.tsv"
    AUDITOR.run_audit(REPORT_PATH, inactivity_threshold=30)