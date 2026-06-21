import requests
import json
import time
import csv
from datetime import datetime, timezone
import os
import re

# Configuration
API_BASE_URL = "https://bsky.social/xrpc"
USERNAME = "ethicalsearch.bsky.social"  # Replace with your Bluesky username
APP_PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD")
# Set the input file path to the one requested by the user
NON_FOLLOWERS_INPUT_FILE = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/prospects/20251211_joyfulgrowth_bsky_social_following.jsonl"
OUTPUT_TSV_FILE = "prospects/active_non_followers.tsv"


# Authenticate and obtain access token
def get_access_token():
    print("Authenticating and obtaining access token...")

    # --- START DEBUGGING LINES (REMOVE ONCE AUTH IS WORKING) ---
    if not APP_PASSWORD:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("ERROR: BLUESKY_APP_PASSWORD is not set or is empty.")
        print("Please ensure you run 'export BLUESKY_APP_PASSWORD=...' before execution.")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        raise ValueError("BLUESKY_APP_PASSWORD environment variable is missing.")

    print(f"DEBUG: Using Username: {USERNAME}")
    print(f"DEBUG: Using Password (first 3 chars): {APP_PASSWORD[:3]}...")
    # --- END DEBUGGING LINES ---

    response = requests.post(
        f"{API_BASE_URL}/com.atproto.server.createSession",
        json={
            "identifier": USERNAME,
            "password": APP_PASSWORD
        }
    )
    # This will raise HTTPError for 401 Unauthorized or other failure codes
    response.raise_for_status()

    data = response.json()
    print(f"Access token obtained: {data['accessJwt'][:10]}...")
    return data["accessJwt"]


# Fetch latest posts for a user
def get_latest_posts(did, token, limit=5):
    print(f"Fetching latest posts for DID: {did}...")
    headers = {"Authorization": f"Bearer {token}"}
    params = {"actor": did, "limit": limit}
    response = requests.get(f"{API_BASE_URL}/app.bsky.feed.getAuthorFeed", headers=headers, params=params)
    if response.status_code != 200:
        print(f"Failed to fetch posts for {did}: {response.status_code}")
        # Raise HTTPError here so the main try/except block catches it
        response.raise_for_status()
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

    # Helper to clean up the timestamp string for Python's datetime.fromisoformat
    def clean_timestamp(iso_string):
        # Python's fromisoformat is limited to six decimal places (microseconds).
        # We use a regex to find the fractional seconds and truncate them if necessary.

        # Regex to capture: (Year-Month-DayTHour:Min:Sec.)(fractional seconds)(Timezone)
        match = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.)(\d+)([\+\-Z].*)", iso_string)
        if match:
            # Group 2 is the fractional seconds part
            fractional = match.group(2)
            if len(fractional) > 6:
                # Truncate to 6 digits (microseconds)
                return match.group(1) + fractional[:6] + match.group(3)
        return iso_string

    timestamps = [
        datetime.fromisoformat(
            clean_timestamp(post["record"]["createdAt"].replace("Z", "+00:00"))
        )
        for post in posts
    ]

    timestamps.sort()
    intervals = [(timestamps[i] - timestamps[i - 1]).total_seconds() for i in range(1, len(timestamps))]

    if not intervals:
        return None  # Should not happen if len(posts) >= 2, but for safety

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
        # Raise HTTPError here so the main try/except block catches it
        response.raise_for_status()
        return None, None

    profile = response.json()
    followers_count = profile.get("followersCount", 0)
    following_count = profile.get("followsCount", 0)
    print(f"Followers: {followers_count}, Following: {following_count}")
    return followers_count, following_count


# Main function (UPDATED with robust try...except and timestamp fix)
def main():
    try:
        token = get_access_token()
    except Exception as e:
        print(f"FATAL ERROR: Failed to get access token. Check credentials. {e}")
        return  # Cannot proceed without a token

    users = []

    print(f"Attempting to load users from {NON_FOLLOWERS_INPUT_FILE}...")

    # --- INPUT LOADING LOGIC ---
    try:
        # Determine format based on extension
        file_path_lower = NON_FOLLOWERS_INPUT_FILE.lower()

        with open(NON_FOLLOWERS_INPUT_FILE, "r") as f:
            if file_path_lower.endswith('.json'):
                # Load as a single JSON array
                users = json.load(f)
                print(f"Successfully loaded {len(users)} users from JSON array (.json).")

            elif file_path_lower.endswith('.jsonl'):
                # Load line-by-line (JSON Lines format)
                for line in f:
                    stripped_line = line.strip()
                    if stripped_line:
                        try:
                            users.append(json.loads(stripped_line))
                        except json.JSONDecodeError as e:
                            print(f"Error decoding JSON line: '{stripped_line}'. Error: {e}")
                            continue
                print(f"Successfully loaded {len(users)} users from JSON Lines (.jsonl).")
            else:
                print(
                    f"Unsupported file format for {NON_FOLLOWERS_INPUT_FILE}. Please use a file ending in .json or .jsonl")
                return

    except FileNotFoundError:
        print(f"FATAL ERROR: Input file not found at path: {NON_FOLLOWERS_INPUT_FILE}")
        return
    except Exception as e:
        print(f"FATAL ERROR: An unexpected error occurred during file loading: {e}")
        return
    # --- END INPUT LOADING LOGIC ---

    if not users:
        print("No users were loaded. Exiting.")
        return

    # Use 'a' (append) mode if you want to resume a run, but 'w' (write)
    # is used here to overwrite, as per the original script's intention.
    with open(OUTPUT_TSV_FILE, "w", newline='', encoding='utf-8') as tsvfile:
        writer = csv.writer(tsvfile, delimiter='\t')
        writer.writerow(["DID", "Handle", "Display Name", "Average Posting Interval (seconds)", "Followers Count",
                         "Following Count"])

        # Loop through each user with individual error handling
        for user in users:
            try:
                did = user.get("did")
                handle = user.get("handle")
                display_name = user.get("displayName", "")

                if not did or not handle:
                    print(f"Skipping user due to missing DID or Handle: {user}")
                    continue

                print(f"Processing user: {handle} ({did})")

                # Fetch posts (can raise HTTPError)
                posts = get_latest_posts(did, token)

                if not posts:
                    print(f"No posts found for {handle}, skipping user.")
                    time.sleep(1)
                    continue

                # The clean_timestamp logic is now safely inside calculate_posting_frequency
                # But we need to use it here for the 7-day check

                # Use the helper function from calculate_posting_frequency to clean the string
                cleaned_post_time = calculate_posting_frequency.clean_timestamp(
                    posts[0]["record"]["createdAt"].replace("Z", "+00:00")
                )
                latest_post_time = datetime.fromisoformat(cleaned_post_time)

                now_utc = datetime.now(timezone.utc)

                if (now_utc - latest_post_time).days > 7:
                    print(f"Latest post for {handle} is older than 7 days, skipping user.")
                    time.sleep(1)
                    continue

                # Calculate frequency and fetch counts (can raise HTTPError or ValueError)
                avg_interval = calculate_posting_frequency(posts)
                followers_count, following_count = get_follow_counts(did, token)

                # Write data to file (only if all previous steps succeeded)
                writer.writerow([did, handle, display_name, avg_interval, followers_count, following_count])
                print(f"Written data for {handle} to the file.")

            except requests.exceptions.HTTPError as e:
                # Catch API-specific errors (e.g., 404, 429) and log them
                print(f"WARNING: HTTP error processing {handle} ({did}): {e}. Skipping to next user.")
            except Exception as e:
                # Catch all other general errors (e.g., the original ValueError)
                print(f"ERROR: General error processing {handle} ({did}): {e}. Skipping to next user.")

            # Rate limit wait time is executed regardless of success/failure
            time.sleep(1)


if __name__ == "__main__":
    # To properly use the regex fix in calculate_posting_frequency, we must define it
    # as an attribute of the function, or pass it directly. Redefining the function here.
    def clean_timestamp(iso_string):
        match = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.)(\d+)([\+\-Z].*)", iso_string)
        if match:
            fractional = match.group(2)
            if len(fractional) > 6:
                return match.group(1) + fractional[:6] + match.group(3)
        return iso_string


    def calculate_posting_frequency(posts):
        if len(posts) < 2:
            print("Not enough posts to calculate average posting frequency.")
            return None

        timestamps = [
            datetime.fromisoformat(
                clean_timestamp(post["record"]["createdAt"].replace("Z", "+00:00"))
            )
            for post in posts
        ]

        timestamps.sort()
        intervals = [(timestamps[i] - timestamps[i - 1]).total_seconds() for i in range(1, len(timestamps))]

        if not intervals: return None

        average_interval = sum(intervals) / len(intervals)
        print(f"Calculated average posting interval: {average_interval} seconds")
        return average_interval


    # Attach the helper function to the main function for use in main() logic
    calculate_posting_frequency.clean_timestamp = clean_timestamp

    # Run the main process
    main()