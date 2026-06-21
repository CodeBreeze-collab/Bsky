import requests
import datetime
import time

import google.generativeai as genai

# Configure Gemini API
genai.configure(api_key="AIzaSyCtamdG_cAV_K--idpt80RuX7vAQxkeUx8")
gemini_model = genai.GenerativeModel("gemini-2.0-flash")

# CONFIGURABLES
CHECK_INTERVAL_MINUTES = 1
WATCHED_USERS = ["vegansearchengine.bsky.social"]
BOT_MESSAGE = "🤖 Hello from my bot!"

def get_gemini_response(post_text):
    prompt = (
        "Is the following post about vegan food, recipe, or product? "
        "If the post is positive or complimenting, respond with one of the following emojis: "
        "raised hands (🙌), happy face (😊), clapping hands (👏), thumbs up (👍), or green heart (💚). "
        "If the post is about veganism and positive, include the plant emoji (🌱). "
        "If the post expresses dissatisfaction, disapproval, or recommends against vegan food, respond with 'No'. "
        "If the post has a negative sentiment toward vegan food, such as saying it's bad or not recommended, also respond with 'No'. "
        "If the post is not positive or related to veganism, just respond with 'No'.\n\n"
        f"Post: \"{post_text}\""
    )

    try:
        response = gemini_model.generate_content(prompt)
        response_text = response.text.strip()
        print(f"🤖 Gemini response: {response_text}")
        return response_text
    except Exception as e:
        print(f"❌ Gemini API error: {e}")
        return "No"


# Auth
def get_access_token():
    print("Getting access token")
    response = requests.post(
        "https://bsky.social/xrpc/com.atproto.server.createSession",
        json={
            "identifier": "realtimesearch.bsky.social",
            "password": "kj67-ouif-fllt-fcib"  # Replace with your real App Password
        }
    )
    response.raise_for_status()
    print("✅ Access token acquired.")
    data = response.json()
    return data["accessJwt"], data["did"]

# Get latest posts
def get_latest_posts(actor, token):
    headers = {"Authorization": f"Bearer {token}"}
    params = {"actor": actor, "limit": 5}
    res = requests.get("https://bsky.social/xrpc/app.bsky.feed.getAuthorFeed", headers=headers, params=params)

    print(f"📡 Fetching posts for {actor} - Status: {res.status_code}")
    if res.status_code != 200:
        print("❌ Failed to fetch feed:", res.status_code, res.text)
        return []

    feed_items = res.json().get("feed", [])
    print(f"📥 Received {len(feed_items)} items from feed")

    posts = []
    for item in feed_items:
        post = item.get("post")
        if post:
            print(f"🔎 Found post: {post.get('uri')} | Has reason: {'reason' in item}")
            if not item.get("reason"):
                posts.append(post)
    return posts

# Like a post
def like_post(post, token, my_did):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    payload = {
        "repo": my_did,
        "collection": "app.bsky.feed.like",
        "record": {
            "subject": {
                "uri": post["uri"],
                "cid": post["cid"]
            },
            "createdAt": now
        }
    }
    res = requests.post("https://bsky.social/xrpc/com.atproto.repo.createRecord", headers=headers, json=payload)
    if res.status_code == 200:
        print(f"❤️ Liked post {post['uri']}")
    else:
        print(f"❌ Failed to like post: {res.status_code} {res.text}")

# Reply to post
def reply_to_post(post, token, my_did, message):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    payload = {
        "repo": my_did,
        "collection": "app.bsky.feed.post",
        "record": {
            "text": message,
            "createdAt": now,
            "reply": {
                "root": {
                    "cid": post["cid"],
                    "uri": post["uri"]
                },
                "parent": {
                    "cid": post["cid"],
                    "uri": post["uri"]
                }
            }
        }
    }

    print("📝 Reply payload:", payload)

    res = requests.post("https://bsky.social/xrpc/com.atproto.repo.createRecord", headers=headers, json=payload)

    print(f"🔁 Reply response: {res.status_code} {res.text}")

    if res.status_code == 200:
        print(f"💬 Commented on {post['uri']}")
    else:
        print(f"❌ Failed to comment: {res.status_code} {res.text}")

# Main loop
def run_bot():
    token, my_did = get_access_token()
    last_checked = {user: None for user in WATCHED_USERS}

    while True:
        for user in WATCHED_USERS:
            print(f"\n🔍 Checking posts from: {user}")
            try:
                posts = get_latest_posts(user, token)
            except requests.exceptions.RequestException as e:
                print(f"❌ Network error while fetching posts: {e}")
                continue

            if not posts:
                print("ℹ️ No posts returned.")
                continue

            for post in posts:
                post_author = post.get("author", {}).get("did", "")
                post_uri = post.get("uri", "")
                post_text = post.get("record", {}).get("text", "")
                post_time_str = post.get("record", {}).get("createdAt", "")
                post_time = datetime.datetime.fromisoformat(post_time_str.replace("Z", "+00:00")) if post_time_str else None

                print(f"\n🔎 Post URI: {post_uri}")
                print(f"✍️ Author DID: {post_author}")
                print(f"🕒 Created at: {post_time_str}")
                print(f"📄 Text: {post_text.strip()!r}")

                if post_author == my_did:
                    print(f"⏩ Skipping bot's own post: {post_uri}")
                    continue

                if "reply" in post.get("record", {}):
                    print(f"⏩ Skipping reply post: {post_uri}")
                    continue

                if not post_text.strip():
                    print(f"⏩ Skipping empty/deleted post: {post_uri}")
                    continue

                last_seen = last_checked.get(user)
                print(f"🆚 Post time: {post_time} | Last seen: {last_seen}")

                if not post_time or (last_seen and post_time <= last_seen):
                    print("⏩ Post already seen or time invalid.")
                    continue

                resp = get_gemini_response(post_text.strip())
                print(resp)

                try:
                    like_post(post, token, my_did)
                    reply_to_post(post, token, my_did, BOT_MESSAGE)
                    last_checked[user] = post_time
                except requests.exceptions.RequestException as e:
                    print(f"❌ Error while interacting with post: {e}")

        print(f"⏳ Sleeping {CHECK_INTERVAL_MINUTES} minute(s)...")
        time.sleep(CHECK_INTERVAL_MINUTES * 60)

if __name__ == "__main__":
    run_bot()
