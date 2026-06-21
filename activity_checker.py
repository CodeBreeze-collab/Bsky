import requests
import json
import time
import logging
import csv
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple
import os  # Added for os.path.exists in the __main__ block

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class BlueskyActivityChecker:
    """
    Reads a list of DIDs/handles from a TSV file and retrieves the latest public
    activity (posts, replies, quotes, reposts) for each user using the Bluesky API.
    The results are printed to the console and saved to a JSON Lines (.jsonl) file.

    This updated version filters the output to include only users whose latest
    activity was within the last 7 days.
    """

    API_BASE_URL = "https://bsky.social/xrpc"
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0

    def __init__(self, handle: str, password: str, tsv_filepath: str):
        """
        Initializes the activity checker.

        :param handle: Your Bluesky handle.
        :param password: Your Bluesky app password.
        :param tsv_filepath: Path to the TSV file containing the target list.
        """
        self.handle = handle
        self.password = password
        self.tsv_filepath = tsv_filepath
        self.token = None

    def _get_session(self) -> None:
        """Authenticates and obtains an access token. Includes debug logging."""
        url = f"{self.API_BASE_URL}/com.atproto.server.createSession"
        payload = {"identifier": self.handle, "password": self.password}

        logging.info("Attempting authentication...")  # ADDED DEBUG LOG
        try:
            res = requests.post(url, json=payload)
            res.raise_for_status()
            self.token = res.json()["accessJwt"]
            logging.info("✅ Authentication successful. Token obtained.")
        except requests.exceptions.RequestException as e:
            # Enhanced Error Logging for better visibility
            logging.error(f"❌ FATAL AUTHENTICATION ERROR: {e}")
            logging.error("Please check your Bluesky handle and App Password (MY_HANDLE and APP_PASSWORD).")
            raise

    def _read_handles_from_tsv(self) -> List[str]:
        """Reads DIDs or handles from the first column of the TSV file. Includes debug logging."""
        handles = []
        logging.info(f"Attempting to read handles from {self.tsv_filepath}...")  # ADDED DEBUG LOG
        try:
            with open(self.tsv_filepath, 'r', encoding='utf-8') as f:
                # Use csv.reader for robust TSV parsing
                reader = csv.reader(f, delimiter='\t')
                next(reader)  # Skip the header row

                for row in reader:
                    # The first column is the DID, which is the most reliable identifier
                    if row:
                        handles.append(row[0])
            logging.info(f"✅ Successfully loaded {len(handles)} users from TSV.")
            return handles
        except FileNotFoundError:
            logging.error(f"❌ Error: TSV file not found at {self.tsv_filepath}")
            return []
        except Exception as e:
            logging.error(f"❌ Error reading TSV file: {e}")
            return []

    def _fetch_latest_activity(self, actor_identifier: str) -> Optional[Dict[str, Any]]:
        """
        Fetches the single latest activity (post, reply, or quote) for a user.

        :param actor_identifier: The DID of the user.
        :returns: The feed item dictionary or None if no activity is found.
        """
        if not self.token:
            return None

        headers = {"Authorization": f"Bearer {self.token}"}
        # Limit to 1 post to minimize API load and maximize speed, as we only need the *latest* activity
        params = {"actor": actor_identifier, "limit": 1}

        for retries in range(self.MAX_RETRIES):
            try:
                res = requests.get(
                    f"{self.API_BASE_URL}/app.bsky.feed.getAuthorFeed",
                    headers=headers,
                    params=params
                )
                res.raise_for_status()
                data = res.json()

                feed = data.get("feed", [])
                if feed:
                    return feed[0]  # Return the latest (first) item
                else:
                    return None  # No activity found

            except requests.exceptions.RequestException as e:
                logging.warning(
                    f"⚠️ Error fetching activity for {actor_identifier} (try {retries + 1}/{self.MAX_RETRIES}): {e}")
                time.sleep(self.RETRY_DELAY * (2 ** retries))

        logging.error(f"❌ Failed to fetch activity for {actor_identifier} after {self.MAX_RETRIES} attempts.")
        return None

    def _parse_activity_type(self, feed_item: Dict[str, Any]) -> Tuple[str, str]:
        """
        Determines the type of activity and extracts the relevant text.

        :returns: A tuple (ActivityType: str, Content: str)
        """
        post = feed_item.get("post", {})
        record = post.get("record", {})

        # Get the full text. This text is what might contain newlines.
        text = record.get("text", "No content text available.")

        # 1. Repost Check
        if feed_item.get("reason", {}).get("$type") == "app.bsky.feed.defs#reasonRepost":
            original_post_author = feed_item.get("reason", {}).get("repost", {}).get("author", {})
            reposter_handle = original_post_author.get("handle", "Unknown")
            return "REPOST", f"Reposted a post by @{reposter_handle}."

        # 2. Quote Post Check (Uses app.bsky.embed.record)
        embed = record.get("embed", {})
        if embed and embed.get("$type") == "app.bsky.embed.record":
            return "QUOTE POST", text

        # 3. Reply Check
        if record.get("reply"):
            return "REPLY", text

        # 4. Standard Post (The default)
        return "POST", text

    def _write_results_to_jsonl(self, results: List[Dict[str, str]], output_filepath: str) -> None:
        """
        Writes the collected activity results to a JSON Lines (.jsonl) file.

        :param results: List of dictionaries containing activity data.
        :param output_filepath: Path to the output JSONL file.
        """
        try:
            with open(output_filepath, 'w', encoding='utf-8') as f:
                for record in results:
                    json_line = json.dumps(record, ensure_ascii=False)
                    f.write(json_line + '\n')
            logging.info(f"✅ Successfully wrote activity report to {output_filepath}")
        except Exception as e:
            logging.error(f"❌ Error writing results to JSONL file {output_filepath}: {e}")

    def run_activity_check(self) -> None:
        """
        Main method to run the analysis, print results, and save to JSONL,
        filtering to only include activity from the last 7 days.
        """
        try:
            self._get_session()
        except Exception:  # Catch any exception raised by _get_session
            return  # Exit if auth fails

        user_dids = self._read_handles_from_tsv()

        if not user_dids:
            logging.info("No DIDs found in the TSV file. Exiting.")
            return

        # 1. Define the time threshold (7 days ago)
        # Bluesky timestamps are in UTC (Z suffix), so we use timezone.utc for comparison
        checked_timestamp_dt = datetime.now(timezone.utc)
        one_week_ago = checked_timestamp_dt - timedelta(days=7)

        # Get the current timestamp in ISO format for the 'checked_timestamp' column
        checked_timestamp = checked_timestamp_dt.isoformat()
        results_data = []  # List to hold all the results for JSONL output
        recent_activity_count = 0

        print("\n" + "=" * 80)
        print("          LATEST ACTIVITY REPORT (FILTERED TO LAST 7 DAYS)")
        print("=" * 80)

        for did in user_dids:
            latest_activity = self._fetch_latest_activity(did)

            # Rate limit avoidance
            time.sleep(0.5)

            if latest_activity:
                post = latest_activity.get("post", {})

                # --- Time Check Logic ---
                created_at_str = post.get("record", {}).get("createdAt", "N/A")

                is_recent = False
                try:
                    # Parse ISO 8601 string, replacing 'Z' with a proper UTC offset
                    activity_dt = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))

                    # Compare the activity timestamp to the 7-day threshold
                    if activity_dt >= one_week_ago:  # Note: >= ensures activity on the 7th day is included
                        is_recent = True
                    else:
                        # Skip activity older than 7 days
                        print(f"| User: {did}")
                        print(f"| -> Status: Activity found, but older than 7 days ({created_at_str}). Skipping.")
                        print("-" * 80)
                        continue  # Skip to the next user

                except ValueError:
                    logging.warning(f"Could not parse timestamp '{created_at_str}' for DID {did}. Skipping this entry.")
                    continue  # If the timestamp is unreadable, skip

                # If execution reaches here, the activity IS recent
                recent_activity_count += 1

                # Extraction and Data Collection
                handle = post.get("author", {}).get("handle", did)
                post_uri = post.get("uri", "N/A")
                post_cid = post.get("cid", "N/A")

                activity_type, full_content = self._parse_activity_type(latest_activity)

                # Use a truncated summary for console printing only
                content_summary_for_print = full_content.replace('\n', ' ')[:80] + '...' if len(
                    full_content) > 80 else full_content.replace('\n', ' ')

                # Print output to console
                print(f"| User: @{handle} (DID: {did})")
                print(f"| -> Activity: {activity_type} **(RECENT)**")
                print(f"| -> Timestamp: {created_at_str}")
                print(f"| -> Content (Value): {content_summary_for_print}")
                print("-" * 80)

                # Collect data for JSONL
                results_data.append({
                    "handle": handle,
                    "activity_type": activity_type,
                    "value": full_content,
                    "checked_timestamp": checked_timestamp,
                    "activity_timestamp": created_at_str,
                    "post_uri": post_uri,
                    "post_cid": post_cid
                })
            else:
                # If no activity is found (empty feed)
                print(f"| User: {did}")
                print("| -> Status: No recent posts found in author feed.")
                print("-" * 80)

        output_filepath = "activity/latest_activity_report_recent_only.jsonl"
        self._write_results_to_jsonl(results_data, output_filepath)

        logging.info(
            f"✅ Activity check complete. Found {recent_activity_count} accounts with activity in the last 7 days.")
        logging.info("NOTE: 'Likes' are not included as they require a separate, much slower API call per user.")


if __name__ == "__main__":

    MY_HANDLE = "ethicalsearch.bsky.social"
    APP_PASSWORD = "iegl-23ir-rmi5-g3qk"# os.environ.get("BLUESKY_APP_PASSWORD")
    TSV_FILEPATH = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/prospects/active_non_followers-12-12-2025.tsv"

    logging.info(f"--- STARTING BLUESKY ACTIVITY CHECKER ---")
    logging.info(f"Configured TSV File Path: {TSV_FILEPATH}")

    if not os.path.exists(TSV_FILEPATH):
        # FATAL error log for visibility
        logging.error(
            f"FATAL: The required TSV file was not found at '{TSV_FILEPATH}'.")
    else:
        logging.info("✅ TSV file found. Beginning execution flow.")
        try:
            checker = BlueskyActivityChecker(
                handle=MY_HANDLE,
                password=APP_PASSWORD,
                tsv_filepath=TSV_FILEPATH
            )
            checker.run_activity_check()

        except Exception as e:
            # Catching general errors outside the class to ensure a clean exit message
            logging.error(f"A fatal error occurred during execution: {e}")