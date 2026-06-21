import json
import requests
import datetime

# --- Constants ---
TOKEN = "kj67-ouif-fllt-fcib"
DAYS_LIMIT = 7
JSON_FILE = "vegan_accounts.json"

# --- Get latest posts ---
def get_latest_posts(actor, token):
    headers = {"Authorization": f"Bearer {token}"}
    params = {"actor": actor, "limit": 5}
    res = requests.get("https://bsky.social/xrpc/app.bsky.feed.getAuthorFeed", headers=headers, params=params)

    if res.status_code != 200:
        print(f"❌ Failed to fetch feed for {actor}: {res.status_code}")
        print(f"📦 Response: {res.text}")
        return []

    feed_items = res.json().get("feed", [])
    posts = [item["post"] for item in feed_items if "post" in item]
    return posts

# --- Check if latest post is within a week ---
def is_recent(post):
    if not post or "indexedAt" not in post:
        return False
    post_time = datetime.datetime.fromisoformat(post["indexedAt"].replace("Z", "+00:00"))
    return (datetime.datetime.now(datetime.timezone.utc) - post_time).days <= DAYS_LIMIT

# --- Load user handles and fetch posts ---
def fetch_recent_posts_from_json(json_path, token):
    with open(json_path, "r", encoding="utf-8") as f:
        users = json.load(f)

    for user in users:
        handle = user.get("handle")
        print(f"\n🔍 Checking {handle}...")
        posts = get_latest_posts(handle, token)

        if posts:
            first_post_time = posts[0].get("indexedAt")
            print(f"📅 First post time: {first_post_time}")
            if is_recent(posts[0]):
                print(f"✅ Recent posts from {handle}:")
                for i, post in enumerate(posts, 1):
                    text = post.get("record", {}).get("text", "(no text)")
                    timestamp = post.get("indexedAt", "unknown time")
                    print(f"  {i}. [{timestamp}] {text}")
            else:
                print(f"⏳ No recent posts in the last {DAYS_LIMIT} days.")
        else:
            print("🛑 No posts returned at all.")

# --- Run it ---
fetch_recent_posts_from_json(JSON_FILE, TOKEN)

