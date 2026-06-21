import requests
import json
import time
import csv
from datetime import datetime, timezone

# Configuration
API_BASE_URL = "https://bsky.social/xrpc"
USERNAME = "realtimesearch.bsky.social"  # Replace with your Bluesky username
APP_PASSWORD = "kj67-ouif-fllt-fcib"  # Replace with your app password
NON_FOLLOWERS_FILE = "non_followers.json"
OUTPUT_TSV_FILE = "prospects/active_non_followers.tsv"

# Authenticate and obtain access token
def get_access_token():
    print("Authenticating and obtaining access token...")

    try:
        # Make the POST request to authenticate
        response = requests.post(
            f"{API_BASE_URL}/com.atproto.server.createSession",
            json={
                "identifier": USERNAME,
                "password": APP_PASSWORD
            }
        )

        # Check the status code and response content
        print(f"Authentication response status code: {response.status_code}")

        if response.status_code != 200:
            print(f"Authentication failed with status code {response.status_code}")
            print(f"Response content: {response.text}")
            response.raise_for_status()

        # Parse and return the access token
        data = response.json()
        print(f"Access token obtained: {data['accessJwt'][:10]}...")  # Show part of the token for verification
        return data["accessJwt"]

    except requests.exceptions.RequestException as e:
        print(f"Error during authentication: {e}")
        raise

# Fetch latest posts for a user
def get_latest_posts(did, token, limit=5):
    print(f"Fetching latest posts for DID: {did}...")
    headers = {"Authorization": f"Bearer {token}"}
    params = {"actor": did, "limit": limit}
    response = requests.get(f"{API_BASE_URL}/app.bsky.feed.getAuthorFeed", headers=headers, params=params)
    if response.status_code != 200:
        print(f"Failed to fetch posts for {did}: {response.status_code}")
        return []
    feed = response.json().get("feed", [])
    posts = []
    for item in feed:
        post = item.get("post")
        if post and not post.get("reason"):  # Skip reposts
            posts.append(post)
    print(f"Found {len(posts)} posts for DID: {did}")
    return posts

# Calculate average posting frequency
def calculate_posting_frequency(posts):
    if len(posts) < 2:
        print("Not enough posts to calculate average posting frequency.")
        return None
    timestamps = [datetime.fromisoformat(post["record"]["createdAt"].replace("Z", "+00:00")) for post in posts]
    timestamps.sort()
    intervals = [(timestamps[i] - timestamps[i - 1]).total_seconds() for i in range(1, len(timestamps))]
    average_interval = sum(intervals) / len(intervals)
    print(f"Calculated average posting interval: {average_interval} seconds")
    return average_interval

# Fetch follower and following counts
def get_follow_counts(did, token):
    print(f"Fetching follower and following counts for DID: {did}...")
    headers = {"Authorization": f"Bearer {token}"}
    params = {"actor": did}
    response = requests.get(f"{API_BASE_URL}/app.bsky.actor.getProfile", headers=headers, params=params)
    if response.status_code != 200:
        print(f"Failed to fetch profile for {did}: {response.status_code}")
        return None, None
    profile = response.json()
    followers_count = profile.get("followersCount", 0)
    following_count = profile.get("followsCount", 0)
    print(f"Followers: {followers_count}, Following: {following_count}")
    return followers_count, following_count

# Read already processed accounts from the existing output file
def read_processed_accounts():
    processed_dids = set()
    try:
        with open(OUTPUT_TSV_FILE, "r", newline='', encoding='utf-8') as tsvfile:
            reader = csv.reader(tsvfile, delimiter='\t')
            next(reader)  # Skip the header row
            for row in reader:
                processed_dids.add(row[0])  # Assuming DID is the first column
        print(f"Found {len(processed_dids)} already processed accounts in the output file.")
    except FileNotFoundError:
        print(f"{OUTPUT_TSV_FILE} not found, starting fresh.")
    return processed_dids

# Main function
def main():
    token = get_access_token()
    processed_dids = read_processed_accounts()  # Get the DIDs already processed

    with open(NON_FOLLOWERS_FILE, "r") as f:
        users = json.load(f)

    with open(OUTPUT_TSV_FILE, "a", newline='', encoding='utf-8') as tsvfile:
        writer = csv.writer(tsvfile, delimiter='\t')

        # Write the header if the file is empty
        if tsvfile.tell() == 0:
            writer.writerow(["DID", "Handle", "Display Name", "Average Posting Interval (seconds)", "Followers Count", "Following Count"])
            print("Created new output file with header.")

        for user in users:
            did = user.get("did")
            handle = user.get("handle")
            display_name = user.get("displayName", "")

            if did in processed_dids:
                print(f"[DEBUG] Skipping already processed user: {handle} ({did})")
                continue

            print(f"[DEBUG] Processing user: {handle} ({did})")

            posts = get_latest_posts(did, token)
            if not posts:
                print(f"[DEBUG] No posts found for {did}, skipping user.")
                continue

            # Check if the latest post is within the last week
            latest_post_time = datetime.fromisoformat(posts[0]["record"]["createdAt"].replace("Z", "+00:00"))
            now_utc = datetime.now(timezone.utc)

            # Debug print for time comparison
            print(f"[DEBUG] Latest post time: {latest_post_time}, Current UTC time: {now_utc}")
            
            if (now_utc - latest_post_time).days > 7:
                print(f"[DEBUG] Latest post for {handle} is older than 7 days, skipping user.")
                continue

            avg_interval = calculate_posting_frequency(posts)
            followers_count, following_count = get_follow_counts(did, token)

            # Write the user's data to the file
            writer.writerow([did, handle, display_name, avg_interval, followers_count, following_count])
            processed_dids.add(did)  # Mark this DID as processed
            print(f"[DEBUG] Written data for {handle} to the file.")
            time.sleep(1)  # To respect API rate limits

if __name__ == "__main__":
    main()

