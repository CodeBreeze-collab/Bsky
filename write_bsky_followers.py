import requests
import csv
import time
import os

def get_session(handle: str, password: str) -> str:
    url = "https://bsky.social/xrpc/com.atproto.server.createSession"
    payload = {"identifier": handle, "password": password}
    res = requests.post(url, json=payload)
    res.raise_for_status()
    return res.json()["accessJwt"]

def get_all_followers(handle: str, token: str, limit: int = 100):
    headers = {"Authorization": f"Bearer {token}"}
    followers = []
    cursor = None

    while True:
        params = {"actor": handle, "limit": limit}
        if cursor:
            params["cursor"] = cursor

        res = requests.get(
            "https://bsky.social/xrpc/app.bsky.graph.getFollowers",
            headers=headers,
            params=params
        )

        if res.status_code != 200:
            print(f"❌ Error fetching followers: {res.status_code} - {res.text}")
            break

        data = res.json()
        followers.extend(data.get("followers", []))

        cursor = data.get("cursor")
        if not cursor:
            break

        time.sleep(0.2)  # Be polite to the API

    return followers

def get_all_followers2(handle: str, token: str, limit: int = 100, max_retries: int = 3, retry_delay: float = 1.0):
    headers = {"Authorization": f"Bearer {token}"}
    followers = []
    cursor = None
    page = 1

    while True:
        params = {"actor": handle, "limit": limit}
        if cursor:
            params["cursor"] = cursor

        retries = 0
        while retries < max_retries:
            res = requests.get(
                "https://bsky.social/xrpc/app.bsky.graph.getFollowers",
                headers=headers,
                params=params
            )

            if res.status_code == 200:
                data = res.json()
                followers.extend(data.get("followers", []))
                print(f"📦 Page {page}: Fetched {len(data.get('followers', []))} followers")
                page += 1
                cursor = data.get("cursor")
                time.sleep(0.3)  # polite throttling
                break
            else:
                retries += 1
                print(f"⚠️ Error (try {retries}/{max_retries}): {res.status_code} - {res.text}")
                time.sleep(retry_delay * (2 ** retries))

        else:
            print("❌ Max retries reached. Exiting early.")
            break

        if not cursor:
            break

    return followers

def save_followers_to_csv(followers, filename="followers.csv"):
    # Create directories if they don't exist
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    with open(filename, mode="w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["handle", "displayName", "did", "avatar"])
        writer.writeheader()
        for f in followers:
            writer.writerow({
                "handle": f.get("handle"),
                "displayName": f.get("displayName"),
                "did": f.get("did"),
                "avatar": f.get("avatar")
            })

    print(f"✅ Saved {len(followers)} followers to {filename}")

# Example usage
if __name__ == "__main__":
    your_handle = "realtimesearch.bsky.social"
    app_password = "6zjl-ohr5-impf-r7f7"  # updated app password
    target_handle = "animalagreality.bsky.social"

    token = get_session(your_handle, app_password)
    followers = get_all_followers2(target_handle, token)
    save_followers_to_csv(followers, filename=f"profiles/{target_handle}/{target_handle}_followers.csv")

