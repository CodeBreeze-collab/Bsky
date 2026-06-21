from atproto import Client
import os

# --- Configuration ---
HANDLE = "vegansearchengine.bsky.social"
APP_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD")
REQUIRED_KEYWORD = "Python"  # The word that MUST be in their profile


def main():
    client = Client()
    client.login(HANDLE, APP_PASSWORD)

    print(f"Logged in as {HANDLE}. Fetching follows...")

    # Get the list of accounts you follow
    # 'limit' can be adjusted; the API returns 50 by default
    follows_response = client.get_follows(actor=HANDLE)

    unfollow_count = 1

    for user in follows_response.follows:
        # Fetch the full profile to see the 'description' (bio)
        profile = client.get_profile(actor=user.did)
        bio = profile.description or ""

        # Check for the keyword (case-insensitive)
        if REQUIRED_KEYWORD.lower() not in bio.lower():
            print(f"Unfollowing {user.handle}: Keyword '{REQUIRED_KEYWORD}' not found.")

            # The 'viewer.following' attribute contains the URI of the follow record
            # We delete this record to "unfollow"
            if user.viewer and user.viewer.following:
                client.delete_record(user.viewer.following)
                unfollow_count += 1
        else:
            print(f"Keeping {user.handle}: Matches criteria.")

    print(f"\nFinished! Total accounts unfollowed: {unfollow_count}")


if __name__ == "__main__":
    main()