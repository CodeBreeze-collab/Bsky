import requests
import json

def get_access_token():
    response = requests.post(
        "https://bsky.social/xrpc/com.atproto.server.createSession",
        json={
            "identifier": "realtimesearch.bsky.social",
            "password": "kj67-ouif-fllt-fcib"  # Replace with your real App Password
        }
    )
    response.raise_for_status()
    print("✅ Access token acquired.")
    return response.json()["accessJwt"], response.json()["did"]

def make_post_request(access_token, did, post_content):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    data = {
        "text": post_content,
        "createdAt": "2025-05-10T00:00:00Z",  # You can modify the timestamp as needed
        "createdBy": did,
    }

    response = requests.post(
        "https://bsky.social/xrpc/com.atproto.social.createPost",
        headers=headers,
        json=data
    )

    if response.status_code == 200:
        print("✅ Post created successfully!")
        return response.json()  # Optionally, return the response for further processing
    else:
        print(f"❌ Failed to create post: {response.status_code}")
        print(response.text)

# Main execution
if __name__ == "__main__":
    try:
        access_token, did = get_access_token()
        post_content = "Your post content goes here."  # Modify this as needed
        make_post_request(access_token, did, post_content)
    except requests.exceptions.RequestException as e:
        print(f"❌ Error occurred: {e}")
