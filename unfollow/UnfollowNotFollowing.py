import argparse
import random
import time
import traceback
from atproto import Client, Request
from atproto.exceptions import AtProtocolError
from httpx import Timeout


def unfollow_non_followers(handle, password, dry_run, min_delay, max_delay):
    request_config = Request(timeout=Timeout(timeout=30.0))
    client = Client(request=request_config)

    try:
        print(f"Logging in as {handle}...")
        client.login(handle, password)
        print("✅ Login successful!")

        cursor = None
        unfollow_count = 0
        checked_count = 0

        print("\nScanning the accounts you follow...")
        if dry_run:
            print("⚠️ DRY RUN ENABLED: No accounts will actually be altered.")

        while True:
            response = client.app.bsky.graph.get_follows(
                params={'actor': handle, 'cursor': cursor}
            )

            for user in response.follows:
                checked_count += 1
                target_handle = user.handle

                is_following_me_back = getattr(user.viewer, 'followed_by', None) is not None

                if not is_following_me_back:
                    unfollow_count += 1
                    print(f"[{unfollow_count}] ❌ {target_handle} is NOT following you back.")

                    if not dry_run:
                        try:
                            client.delete_follow(user.viewer.following)
                            print(f"    Successfully unfollowed {target_handle}")

                            sleep_time = random.uniform(min_delay, max_delay)
                            print(f"    Pausing for {sleep_time:.2f} seconds...")
                            time.sleep(sleep_time)

                        except Exception as unfollow_err:
                            print(f"    Failed to unfollow {target_handle}: {unfollow_err}")

            cursor = response.cursor
            if not cursor:
                break

        print(f"\n--- Run Complete ---")
        print(f"Total accounts checked: {checked_count}")
        if dry_run:
            print(f"Would have unfollowed {unfollow_count} accounts.")
        else:
            print(f"Successfully unfollowed {unfollow_count} accounts.")

    except AtProtocolError as at_err:
        print(f"\n❌ Bluesky API Error occurred!")
        print(f"Error Details: {at_err}")
        print("\n--- Full API Traceback ---")
        traceback.print_exc()

    except Exception as e:
        print(f"\n❌ General System Error occurred!")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Message: {e}")
        print("\n--- Full Code Traceback ---")
        traceback.print_exc()


if __name__ == "__main__":
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description="Unfollow Bluesky accounts that don't follow you back.")

    # Required Arguments
    parser.add_argument('--handle', required=True, type=str, help="Your Bluesky handle (e.g., my-account.bsky.social)")
    parser.add_argument('--password', required=True, type=str, help="Your Bluesky App Password")

    # Optional Flags
    parser.add_argument('--execute', action='store_true',
                        help="Actually perform unfollows. Without this, it defaults to a safe dry run.")
    parser.add_argument('--min-delay', type=float, default=1.0,
                        help="Minimum random delay in seconds between actions (Default: 1.0)")
    parser.add_argument('--max-delay', type=float, default=3.5,
                        help="Maximum random delay in seconds between actions (Default: 3.5)")

    args = parser.parse_args()

    # The script runs as a dry run UNLESS the user explicitly includes '--execute'
    dry_run_flag = not args.execute

    unfollow_non_followers(
        handle=args.handle,
        password=args.password,
        dry_run=dry_run_flag,
        min_delay=args.min_delay,
        max_delay=args.max_delay
    )