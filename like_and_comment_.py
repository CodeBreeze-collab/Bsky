import requests
import datetime
import time
import google.generativeai as genai
import os

# --- Constants ---
TOKEN = "57my-eid7-otze-g2n2" #"dl4q-gze6-zidj-apgh"
MY_DID = "did:plc:svaj55mwdq6oczerywmhiwop"
CHECK_INTERVAL_MINUTES = 1
WATCHED_USERS = ["veganmealnews.bsky.social"]# [ "compassionnews.bsky.social", "veganmealnews.bsky.social"] # "vegansearchengine.bsky.social",
LOG_FILE_PATH = "bot_activity_log.tsv"
# 57my-eid7-otze-g2n2
# Configure Gemini API
genai.configure(api_key="AIzaSyCtamdG_cAV_K--idpt80RuX7vAQxkeUx8")
gemini_model = genai.GenerativeModel("gemini-2.0-flash")

# --- Get access token ---
def get_access_token():
    response = requests.post(
        "https://bsky.social/xrpc/com.atproto.server.createSession",
        json={
            "identifier": "compassionnews.bsky.social",
            "password": TOKEN
        }
    )
    response.raise_for_status()
    return response.json()["accessJwt"]

def is_post_liked(post_uri, token, my_did):
    headers = {"Authorization": f"Bearer {token}"}
    # Fetch liked posts from the post URI
    params = {"uri": post_uri}
    res = requests.get("https://bsky.social/xrpc/app.bsky.feed.getLikes", headers=headers, params=params)

    print(f"Response from getLikes: {res.status_code} {res.text}")  # Added print to show the response

    if res.status_code == 200:
        liked_posts = res.json().get("likes", [])

        # Check if the bot's DID is in the list of likes for this post
        for liked_post in liked_posts:
            # Debugging: Print the URI and actor DID for each like
            # print(f"Liked post Actor DID: {liked_post.get('actor', {}).get('did')}")

            # Compare the actor's DID
            if liked_post.get("actor", {}).get("did") == my_did:
                print('Already liked')
                return True
    else:
        print(f"❌ Failed to fetch liked posts: {res.status_code} {res.text}")

    return False

# --- Check if post is already in log ---
def is_post_logged(post_uri, action):
    if not os.path.exists(LOG_FILE_PATH):
        return False
    with open(LOG_FILE_PATH, "r") as log_file:
        for line in log_file:
            if post_uri in line and action in line:
                return True
    return False

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

# --- Get latest posts ---
def get_latest_posts(actor, token):
    headers = {"Authorization": f"Bearer {token}"}
    params = {"actor": actor, "limit": 5}
    res = requests.get("https://bsky.social/xrpc/app.bsky.feed.getAuthorFeed", headers=headers, params=params)
    if res.status_code != 200:
        print(f"❌ Failed to fetch feed: {res.status_code}")
        return []
    return [item["post"] for item in res.json().get("feed", []) if "post" in item]

# --- Like a post ---
def like_post(post, token, my_did):
    post_uri = post["uri"]
    """ if is_post_logged(post_uri, "liked"):
        print(f"⏩ Already logged as liked: {human_readable_url(post_uri)}")
        return """
    if is_post_liked(post_uri, token, my_did):
        print(f"⏩ Already liked (confirmed): {human_readable_url(post_uri)}")
        return

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
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
        print(f"❤️ Liked: {human_readable_url(post_uri)}")
        log_activity(post, "liked", "")
    else:
        print(f"❌ Failed to like: {res.status_code} {res.text}")

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
        # print(f"💬 Commented on: {human_readable_url(post_uri)}")
        log_activity(post, "commented", message)
    else:
        print(f"❌ Failed to comment: {res.status_code} {res.text}")

# --- Convert URI to readable URL ---
def human_readable_url(post_uri):
    if post_uri.startswith("at://"):
        parts = post_uri[5:].split("/app.bsky.feed.post/")
        if len(parts) == 2:
            did = parts[0]
            post_id = parts[1]
            return f"https://bsky.app/profile/{did}/post/{post_id}"
    return post_uri

def follow_user(did_to_follow, token, my_did):
    """
    Follows the given DID using the authenticated user's DID.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    payload = {
        "repo": my_did,
        "collection": "app.bsky.graph.follow",
        "record": {
            "subject": did_to_follow,
            "createdAt": now
        }
    }

    res = requests.post("https://bsky.social/xrpc/com.atproto.repo.createRecord", headers=headers, json=payload)

    if res.status_code == 200:
        print(f"✅ Successfully followed: {did_to_follow}")
    else:
        print(f"❌ Failed to follow {did_to_follow}: {res.status_code} {res.text}")


# --- Log activity ---
def log_activity(post, action, message):
    post_url = human_readable_url(post["uri"])
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE_PATH, "a") as log_file:
        log_file.write(f"{timestamp}\t{post_url}\t{action}\t{message}\n")

def resolve_handle(handle):
    res = requests.get(f"https://bsky.social/xrpc/com.atproto.identity.resolveHandle", params={"handle": handle})
    if res.status_code == 200:
        return res.json().get("did")
    else:
        print(f"❌ Failed to resolve handle: {res.status_code} {res.text}")
        return None

def like_and_comment_from_list():
    token = get_access_token()

    for user in WATCHED_USERS:
        print(f"\n🔍 Checking posts from: {user}")
        posts = get_latest_posts(user, token)
        did = resolve_handle(user)

        if(is_followed_by(did, MY_DID, token)):
            print(did + ' is already following us')
            if not is_following(did, MY_DID, token):
                follow_user(did, token, MY_DID)
            break

        for post in posts:
            post_uri = post.get("uri")
            print(post_uri)

            if is_post_liked(post_uri, token, MY_DID):
                log_activity(post, 'like', '')
                continue

            post_text = post.get("record", {}).get("text", "")
            gemini_response = get_gemini_response(post_text.strip())

            if gemini_response == "No":
                print(f"⏩ Skipping non-vegan post: {human_readable_url(post_uri)}")
                continue

            response = '🌱'

            like_post(post, token, MY_DID)
            reply_to_post(post, token, MY_DID, response)

            log_activity(post, 'comment', response)

            # Stop checking further posts for this user
            break

    print(f"⏳ Sleeping for {CHECK_INTERVAL_MINUTES} minute(s)...")
    time.sleep(CHECK_INTERVAL_MINUTES * 2)

def is_following(target_did, my_did, token):
    headers = {"Authorization": f"Bearer {token}"}
    cursor = None

    while True:
        params = {"actor": my_did, "limit": 100}
        if cursor:
            params["cursor"] = cursor

        res = requests.get("https://bsky.social/xrpc/app.bsky.graph.getFollows", headers=headers, params=params)

        if res.status_code != 200:
            print(f"❌ Failed to fetch follows: {res.status_code} {res.text}")
            return False

        follows = res.json().get("follows", [])
        for follow in follows:
            if follow.get("did") == target_did:
                return True

        cursor = res.json().get("cursor")
        if not cursor:
            break

    return False

def is_followed_by(target_did, my_did, token):
    headers = {"Authorization": f"Bearer {token}"}
    cursor = None

    while True:
        params = {"actor": my_did, "limit": 100}
        if cursor:
            params["cursor"] = cursor

        res = requests.get("https://bsky.social/xrpc/app.bsky.graph.getFollowers", headers=headers, params=params)

        if res.status_code != 200:
            print(f"❌ Failed to fetch followers: {res.status_code} {res.text}")
            return False

        followers = res.json().get("followers", [])
        for follower in followers:
            if follower.get("did") == target_did:
                return True

        cursor = res.json().get("cursor")
        if not cursor:
            break

    return False


# --- Run the bot ---
def run_bot():
    token = get_access_token()
    if not os.path.exists(LOG_FILE_PATH):
        with open(LOG_FILE_PATH, "w") as f:
            f.write("Timestamp\tPost URL\tAction\tComment\n")

    while True:
        for user in WATCHED_USERS:

            print(f"\n🔍 Checking posts from: {user}")
            posts = get_latest_posts(user, token)
            handle = resolve_handle()

            for post in posts:
                post_uri = post.get("uri")

                if(is_post_liked(post_uri, token, MY_DID)):
                    continue

                post_text = post.get("record", {}).get("text", "")
                gemini_response = get_gemini_response(post_text.strip())
                if gemini_response == "No":
                    print(f"⏩ Skipping non-vegan post: {human_readable_url(post_uri)}")
                    continue
                like_post(post, token, MY_DID)
                reply_to_post(post, token, MY_DID, gemini_response)
                log_activity(post, 'comment', gemini_response)
        print(f"⏳ Sleeping for {CHECK_INTERVAL_MINUTES} minute(s)...")
        time.sleep(CHECK_INTERVAL_MINUTES * 2)


import json

def resolve_handle_to_did(handle):
    res = requests.get(f"https://bsky.social/xrpc/com.atproto.identity.resolveHandle", params={"handle": handle})
    if res.status_code == 200:
        return res.json().get("did")
    else:
        print(f"❌ Failed to resolve handle: {handle} - {res.status_code}")
        return None

def follow_vegan_accounts_from_file(file_path, token, my_did):
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return

    with open(file_path, "r") as f:
        accounts = json.load(f)

    i = 0
    for account in accounts:
        print(i)
        if i >= 10:  # Check here to break the loop after 10 follows
            break

        handle = account.get("handle")
        if not handle:
            continue

        did = resolve_handle_to_did(handle)
        if not did:
            continue

        if is_following(did, my_did, token):
            print(f"⏩ Already following {handle} ({did})")
            continue

        # follow_user(did, token, my_did)
        i += 1  # Increment the counter only when following
        time.sleep(CHECK_INTERVAL_MINUTES * 10)



def follow_vegan_accounts_from_file(file_path, token, my_did):
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return

    with open(file_path, "r") as f:
        accounts = json.load(f)

    for account in accounts:
        handle = account.get("handle")
        if not handle:
            continue

        did = resolve_handle_to_did(handle)
        if not did:
            continue

        if is_following(did, my_did, token):
            print(f"⏩ Already following {handle} ({did})")
            continue

        follow_user(did, token, my_did)

if __name__ == "__main__":
    #run_bot()
    #like_and_comment_from_list()
    path = '/bsky/vegan_accounts.json'
    token = get_access_token()
    follow_vegan_accounts_from_file(path, token, MY_DID)
