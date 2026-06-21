import requests
import datetime
import json
import google.generativeai as genai

# --- Gemini setup ---
genai.configure(api_key="AIzaSyCtamdG_cAV_K--idpt80RuX7vAQxkeUx8")
gemini_model = genai.GenerativeModel("gemini-2.0-flash")

# --- Constants ---
ACCOUNTS_FILE = "vegan_accounts.json"
ONE_WEEK_AGO = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)

# --- Gemini analysis ---
def analyze_post(post_text):
    vegan_prompt = (
        "Is the following post about vegan food, recipe, or product? "
        "If the post is positive or complimenting, respond with one of the following emojis: "
        "🙌 😊 👏 👍 💚. "
        "If the post is about veganism and positive, include 🌱. "
        "If the post is negative or unrelated to veganism, respond with 'No'.\n\n"
        f"Post: \"{post_text}\""
    )

    try:
        response = gemini_model.generate_content(vegan_prompt)
        answer = response.text.strip()

        if answer == "No":
            emoji_prompt = (
                f"This post is not about veganism: \"{post_text}\".\n"
                "Suggest an appropriate emoji that represents the tone or emotion of the post."
            )
            emoji_response = gemini_model.generate_content(emoji_prompt)
            return answer, emoji_response.text.strip()
        else:
            return answer, None
    except Exception as e:
        print(f"❌ Gemini API error: {e}")
        return "Error", None

# --- Auth ---
def get_access_token():
    response = requests.post(
        "https://bsky.social/xrpc/com.atproto.server.createSession",
        json={
            "identifier": "realtimesearch.bsky.social",
            "password": "kj67-ouif-fllt-fcib"  # Replace with your real password
        }
    )
    response.raise_for_status()
    data = response.json()
    return data["accessJwt"]

# --- Fetch recent posts ---
def get_recent_posts(actor_handle, token, limit=5):
    headers = {"Authorization": f"Bearer {token}"}
    params = {"actor": actor_handle, "limit": limit}
    res = requests.get("https://bsky.social/xrpc/app.bsky.feed.getAuthorFeed", headers=headers, params=params)

    if res.status_code != 200:
        print(f"❌ Failed to fetch feed for {actor_handle}: {res.status_code} {res.text}")
        return []

    feed_items = res.json().get("feed", [])
    posts = []

    for item in feed_items:
        post = item.get("post")
        if not post or item.get("reason"):
            continue

        record = post.get("record", {})
        created_str = record.get("createdAt", "")
        if not created_str or "reply" in record:
            continue  # Skip replies

        created_at = datetime.datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        if created_at >= ONE_WEEK_AGO:
            posts.append(post)

    return posts

# --- Main logic ---
def main():
    # Load account list
    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
        accounts = json.load(f)

    # Auth
    token = get_access_token()

    for account in accounts:
        handle = account["handle"]
        print(f"\n🔍 Checking posts from {handle}...")

        posts = get_recent_posts(handle, token)
        if not posts:
            print("ℹ️ No recent posts in the last week.")
            continue

        for post in posts:
            post_text = post.get("record", {}).get("text", "").strip()
            created_str = post.get("record", {}).get("createdAt", "")
            uri = post.get("uri", "")

            print(f"\n🕒 Created: {created_str}")
            print(f"📄 Text: {post_text}")

            # If it includes an image, print URL
            embed = post.get("record", {}).get("embed", {})
            if embed and "images" in embed:
                print(f"🖼️ Post contains image. URL: https://bsky.app/profile/{handle}/post/{uri.split('/')[-1]}")

            vegan_response, alt_emoji = analyze_post(post_text)
            print(f"🤖 Gemini response: {vegan_response}")
            if alt_emoji:
                print(f"✨ Suggested emoji (non-vegan): {alt_emoji}")

if __name__ == "__main__":
    main()

