import requests

# --- Constants ---
MY_DID = "did:plc:svaj55mwdq6oczerywmhiwop"  # Replace with your bot's DID
POST_URI = "at://did:plc:jag2kvikoewpjcq5dmr2nswb/app.bsky.feed.post/3lotohlhlbc2e"  # Replace with a post URI you have liked

# --- Get access token ---
def get_access_token():
    print("Getting access token...")
    response = requests.post(
        "https://bsky.social/xrpc/com.atproto.server.createSession",
        json={
            "identifier": "realtimesearch.bsky.social",  # Your bot's identifier
            "password": "kj67-ouif-fllt-fcib"  # Replace with your real App Password
        }
    )
    response.raise_for_status()
    print("✅ Access token acquired.")
    data = response.json()
    return data["accessJwt"]

# --- Check if post is liked by checking the post URI ---
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
            print(f"Liked post Actor DID: {liked_post.get('actor', {}).get('did')}")
            
            # Compare the actor's DID
            if liked_post.get("actor", {}).get("did") == my_did:
                return True
    else:
        print(f"❌ Failed to fetch liked posts: {res.status_code} {res.text}")
    
    return False

# --- Test the like check ---
def test_like_check():
    # Get a fresh access token
    token = get_access_token()
    
    print(f"Testing if post is liked: {POST_URI}")

    if is_post_liked(POST_URI, token, MY_DID):
        print("✅ The post has already been liked!")
    else:
        print("❌ The post has not been liked yet.")

if __name__ == "__main__":
    test_like_check()

