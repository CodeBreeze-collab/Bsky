import requests
import datetime
import time

# Auth
def get_access_token():
    response = requests.post(
        "https://bsky.social/xrpc/com.atproto.server.createSession",
        json={
            "identifier": "realtimesearch.bsky.social",
            "password": "kj67-ouif-fllt-fcib"
        }
    )
    response.raise_for_status()
    print("✅ Access token acquired.")
    return response.json()["accessJwt"], response.json()["did"]

# Get latest posts
def get_latest_posts(actor, token, seen_uris):
    headers = {"Authorization": f"Bearer {token}"}
    params = {"actor": actor, "limit": 5}
    res = requests.get("https://bsky.social/xrpc/app.bsky.feed.getAuthorFeed", headers=headers, params=params)
    if res.status_code != 200:
        print("❌ Failed to fetch feed:", res.text)
        return []
    
    posts = res.json().get("feed", [])
    new_posts = []
    for item in posts:
        post = item.get("post")
        uri = post.get("uri")
        if uri not in seen_uris and not post.get("reason"):  # Skip replies/reposts
            seen_uris.add(uri)
            new_posts.append(post)
    return new_posts

# Reply to post
def reply_to_post(post, token, my_did, message="Cool post! 😎"):
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

    response = requests.post("https://bsky.social/xrpc/com.atproto.repo.createRecord",
                             headers=headers, json=payload)
    if response.status_code == 200:
        print(f"💬 Commented on {post['uri']}")
    else:
        print(f"❌ Failed to comment: {response.status_code} {response.text}")

# Main loop
def run_bot():
    token, my_did = get_access_token()
    seen_posts = set()
    watched_users = ["realtimesearch.bsky.social"]  # add more if you want!

    while True:
        for user in watched_users:
            print(f"🔎 Checking posts from {user}...")
            new_posts = get_latest_posts(user, token, seen_posts)
            for post in new_posts:
                reply_to_post(post, token, my_did, message="🤖 Hello from my bot!")
        time.sleep(60)  # Check every minute

if __name__ == "__main__":
    run_bot()

