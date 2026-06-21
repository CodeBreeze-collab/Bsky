import json
import requests
import datetime
import time
import google.generativeai as genai
import os

# --- Constants ---
USERNAME = "realtimesearch.bsky.social"
PASSWORD = "kj67-ouif-fllt-fcib"
DAYS_LIMIT = 7
JSON_FILE = "vegan_accounts.json"
MY_DID = "did:plc:svaj55mwdq6oczerywmhiwop"
LOG_FILE_PATH = "activity_log.txt"

# Configure Gemini API
genai.configure(api_key="AIzaSyATp4Tq02TW11zIuZTeRTdPZHCVef9uBzw")
gemini_model = genai.GenerativeModel("gemini-2.0-flash")

# --- Get Gemini response ---
def get_gemini_response(post_text):
    prompt = (
        "Is the following post about vegan food, recipe, or product? "
        "If the post is positive or complimenting, respond with one of the following emojis: "
        "raised hands (🙌), happy face (😊), clapping hands (👏), thumbs up (👍), or green heart (💚). "
        "If the post is about veganism and positive, include the plant emoji (🌱). "
        "If the post expresses dissatisfaction, disapproval, or recommends against vegan food, respond with 'No'. "
        "If the post is not positive or related to veganism, just respond with 'No'.\n\n"
        f"Post: \"{post_text}\""
    )
    try:
        response = gemini_model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"❌ Gemini API error: {e}")
        return "No"

# --- Get access token ---
def get_access_token():
    response = requests.post(
        "https://bsky.social/xrpc/com.atproto.server.createSession",
        json={
            "identifier": USERNAME,
            "password": PASSWORD
        }
    )
    response.raise_for_status()
    return response.json()["accessJwt"]

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

# --- Convert URI to readable URL ---
def human_readable_url(post_uri):
    if post_uri.startswith("at://"):
        parts = post_uri[5:].split("/app.bsky.feed.post/")
        if len(parts) == 2:
            did = parts[0]
            post_id = parts[1]
            return f"https://bsky.app/profile/{did}/post/{post_id}"
    return post_uri

# --- Comment on post ---
def reply_to_post(post, token, my_did, message):
    post_uri = post["uri"]

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    payload = {
        "repo": my_did,
        "collection": "app.bsky.feed.post",
        "record": {
            "text": message,
            "createdAt": now,
            "reply": {
                "root": {"cid": post["cid"], "uri": post["uri"]},
                "parent": {"cid": post["cid"], "uri": post["uri"]}
            }
        }
    }
    res = requests.post("https://bsky.social/xrpc/com.atproto.repo.createRecord", headers=headers, json=payload)
    if res.status_code == 200:
        print(f"💬 Commented on: {human_readable_url(post_uri)}")
        log_activity(post, "commented", message)
    else:
        print(f"❌ Failed to comment: {res.status_code} {res.text}")

def log_activity(post, action, message):
    post_url = human_readable_url(post["uri"])
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE_PATH, "a") as log_file:
        log_file.write(f"{timestamp}\t{post_url}\t{action}\t{message}\n")


# --- Load user handles and fetch posts ---
def fetch_recent_posts_from_json(json_path):
    token = get_access_token()

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
                    resp = get_gemini_response(text)
                    if resp != 'No':
                        print(resp)
                        reply_to_post(post, token, MY_DID, resp)
                        break

                    timestamp = post.get("indexedAt", "unknown time")
                    print(f"  {i}. [{timestamp}] {text}")
            else:
                print(f"⏳ No recent posts in the last {DAYS_LIMIT} days.")
        else:
            print("🛑 No posts returned at all.")

# --- Run it ---
fetch_recent_posts_from_json(JSON_FILE)

