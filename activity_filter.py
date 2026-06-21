import requests
import json
import time
import logging
import os
import sys
from typing import Set, List, Dict, Any, Optional
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class ActivityFilter:
    """
    Reads an activity stream, filters out users in the follow graph, fetches profile info
    AND the author's recent activity feed, and writes results in real-time to a JSONL file,
    resuming work if the file exists.
    """

    API_BASE_URL = "https://bsky.social/xrpc"
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0
    API_CALL_DELAY = 0.5  # Delay after fetching profile and feed
    FEED_LIMIT = 10  # Number of recent activities to fetch

    def __init__(self, activity_filepath: str, followers_filepath: str, following_filepath: str,
                 auth_handle: str, auth_password: str, output_filepath: str):

        self.activity_filepath = activity_filepath
        self.followers_filepath = followers_filepath
        self.following_filepath = following_filepath
        self.output_filepath = output_filepath

        self.auth_handle = auth_handle
        self.auth_password = auth_password
        self.token = None

        self.exclusion_handles: Set[str] = set()
        self.unfiltered_activities: List[Dict[str, Any]] = []
        self.processed_handles: Set[str] = set()

    def _get_session(self) -> bool:
        # ... (Authentication logic remains unchanged) ...
        url = f"{self.API_BASE_URL}/com.atproto.server.createSession"
        payload = {"identifier": self.auth_handle, "password": self.auth_password}
        logging.info("Attempting API authentication...")
        try:
            res = requests.post(url, json=payload)
            res.raise_for_status()
            self.token = res.json()["accessJwt"]
            logging.info("✅ Authentication successful.")
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"❌ FATAL AUTHENTICATION ERROR: {e}")
            logging.error("Please check the Auth Handle and App Password.")
            return False

    def _get_profile_description(self, actor_handle: str) -> Optional[Dict[str, Any]]:
        # ... (Profile fetch logic remains unchanged) ...
        if not self.token:
            return None

        headers = {"Authorization": f"Bearer {self.token}"}

        for retries in range(self.MAX_RETRIES):
            try:
                profile_params = {"actor": actor_handle}
                profile_url = f"{self.API_BASE_URL}/app.bsky.actor.getProfile"

                profile_res = requests.get(profile_url, headers=headers, params=profile_params)
                profile_res.raise_for_status()
                return profile_res.json()

            except requests.exceptions.RequestException as e:
                time.sleep(self.RETRY_DELAY * (2 ** retries))

        logging.error(f"❌ Failed to fetch profile for {actor_handle} after {self.MAX_RETRIES} attempts.")
        return None

    def _get_author_feed(self, actor_handle: str) -> List[Dict[str, Any]]:
        """Fetches the last N posts, replies, or reposts for a given handle."""
        if not self.token:
            return []

        headers = {"Authorization": f"Bearer {self.token}"}

        for retries in range(self.MAX_RETRIES):
            try:
                # Use the 'actor' parameter which accepts a handle
                feed_params = {"actor": actor_handle, "limit": self.FEED_LIMIT}
                feed_url = f"{self.API_BASE_URL}/app.bsky.feed.getAuthorFeed"

                feed_res = requests.get(feed_url, headers=headers, params=feed_params)
                feed_res.raise_for_status()

                # Extract relevant information from the feed items
                cleaned_feed = []
                for item in feed_res.json().get('feed', []):
                    post = item.get('post', {})
                    record = post.get('record', {})

                    # Determine activity type (Post, Repost, Reply)
                    activity_type = "POST"
                    if item.get('reason', {}).get('$type') == 'app.bsky.feed.defs#reasonRepost':
                        activity_type = "REPOST"
                    elif record.get('reply'):
                        activity_type = "REPLY"

                    cleaned_feed.append({
                        "activity_type": activity_type,
                        "uri": post.get('uri'),
                        "text": record.get('text', ''),
                        "timestamp": record.get('createdAt', ''),
                        "repostCount": post.get('repostCount', 0),
                        "likeCount": post.get('likeCount', 0),
                    })

                return cleaned_feed

            except requests.exceptions.RequestException as e:
                logging.warning(
                    f"⚠️ Error fetching feed for {actor_handle} (try {retries + 1}/{self.MAX_RETRIES}): {e}")
                time.sleep(self.RETRY_DELAY * (2 ** retries))

        logging.error(f"❌ Failed to fetch feed for {actor_handle} after {self.MAX_RETRIES} attempts.")
        return []

    # --- File Loading Methods (Omitted for brevity - Unchanged) ---
    def _load_handles_from_jsonl(self, filepath: str) -> Set[str]:
        # ... (Exclusion handle loading remains unchanged) ...
        handles: Set[str] = set()
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        record = json.loads(line.strip())
                        handle = record.get("handle")
                        if handle:
                            handles.add(handle.lower())
                    except json.JSONDecodeError:
                        logging.warning(f"Skipping malformed JSON line in {filepath}.")
            logging.info(f"✅ Loaded {len(handles)} unique handles from {filepath}.")
            return handles
        except FileNotFoundError:
            logging.error(f"❌ FATAL: Input file not found: {filepath}")
            sys.exit(1)
        except Exception as e:
            logging.error(f"❌ Error reading file {filepath}: {e}")
            sys.exit(1)

    def _load_activities_from_jsonl(self) -> None:
        # ... (Activity loading remains unchanged) ...
        try:
            with open(self.activity_filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        self.unfiltered_activities.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        logging.warning(f"Skipping malformed JSON line in {self.activity_filepath}.")
            logging.info(f"✅ Loaded {len(self.unfiltered_activities)} total activities from stream.")
        except FileNotFoundError:
            logging.error(f"❌ FATAL: Activity file not found: {self.activity_filepath}")
            sys.exit(1)

    def _load_processed_handles(self) -> None:
        # ... (Resume logic remains unchanged) ...
        if not os.path.exists(self.output_filepath):
            logging.info("Output file not found. Starting analysis from scratch.")
            return

        initial_count = 0
        try:
            with open(self.output_filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        record = json.loads(line.strip())
                        handle = record.get("handle")
                        if handle:
                            self.processed_handles.add(handle.lower())
                            initial_count += 1
                    except json.JSONDecodeError:
                        logging.warning("Skipping malformed JSON line in existing output file.")
            logging.info(
                f"🔁 RESUMING: Loaded {initial_count} handles from {self.output_filepath}. These will be skipped.")
        except Exception as e:
            logging.error(f"❌ Error reading existing output file for resume: {e}")

    def _write_result_to_file(self, record: Dict[str, Any]) -> None:
        """Writes a single record immediately to the output JSONL file."""
        try:
            with open(self.output_filepath, 'a', encoding='utf-8') as f:
                # The record already contains the structured profile and activity list
                json_line = json.dumps(record, ensure_ascii=False)
                f.write(json_line + '\n')

            self.processed_handles.add(record['handle'].lower())
        except Exception as e:
            logging.error(f"❌ Error writing record to output file {self.output_filepath}: {e}")

    # --- Main Run Method (Updated) ---

    def run_filter(self) -> None:
        """
        Main method to handle setup, filtering, profile/feed fetching, and real-time output.
        """
        if not self._get_session():
            return

        self._load_processed_handles()

        logging.info("--- STEP 1: Building Exclusion Set ---")
        followers = self._load_handles_from_jsonl(self.followers_filepath)
        following = self._load_handles_from_jsonl(self.following_filepath)
        self.exclusion_handles = followers.union(following)
        logging.info(f"Total handles to exclude (Follows/Followers): {len(self.exclusion_handles)}")

        logging.info("\n--- STEP 2: Loading Activity Stream ---")
        self._load_activities_from_jsonl()

        logging.info("\n--- STEP 3: Filtering, Fetching Profiles/Feeds, and Writing in Real-Time ---")

        matches_found = 0
        handles_to_process = set()

        for activity in self.unfiltered_activities:
            handle = activity.get("handle")
            activity_type = activity.get("activity_type")

            if not handle or activity_type != "POST":
                continue

            # Check if handle is NOT excluded AND NOT already processed
            if handle.lower() not in self.exclusion_handles and handle.lower() not in self.processed_handles:
                handles_to_process.add(handle)

        logging.info(f"Found {len(handles_to_process)} unique, unseen prospects to process.")

        # Iterate only through the unique handles we need to fetch profiles for
        for handle in sorted(list(handles_to_process)):

            matches_found += 1

            # 3A. Fetch Profile Information
            profile = self._get_profile_description(handle)

            # 3B. Fetch Recent Activity Feed
            recent_activities = self._get_author_feed(handle)

            # 3C. Structure the output record and write immediately
            if profile:
                # Use a combined record structure
                record = {
                    "handle": handle,
                    "did": profile.get('did'),
                    "displayName": profile.get('displayName', ''),
                    "bio": profile.get('description', ''),
                    "followersCount": profile.get('followersCount', 0),
                    "followingCount": profile.get('followsCount', 0),
                    "recentActivities": recent_activities  # List of JSON objects
                }

                # Find the initial post that triggered the match and add it to the record
                # Note: We prioritize the latest post from the API call for "Latest Post"
                # but we can grab the URI from the original activity stream for reference.
                original_post_uri = next(
                    (a.get("post_uri") for a in self.unfiltered_activities if a.get("handle") == handle),
                    "N/A"
                )
                record["matchSourcePostUri"] = original_post_uri

                self._write_result_to_file(record)
                logging.info(
                    f"✅ Wrote Prospect #{matches_found} (@{handle}) to file with {len(recent_activities)} activities.")
            else:
                logging.warning(
                    f"⚠️ Failed to write Prospect #{matches_found} (@{handle}) due to profile fetch failure. Skipping.")

            # Rate-limit pause after a full API cycle (Profile + Feed)
            time.sleep(self.API_CALL_DELAY)

        print("\n" + "=" * 70)
        print(f"🎉 Analysis Complete. Attempted to process {len(handles_to_process)} unique unseen prospects.")
        print(f"Final output written to: {self.output_filepath}")
        print("=" * 70)


if __name__ == "__main__":

    # --- CONFIGURATION ---
    AUTH_HANDLE = "vegansearchengine.bsky.social" #"ethicalsearch.bsky.social"
    APP_PASSWORD = "rxba-yxai-3pno-hjqp" # os.environ.get("BLUESKY_APP_PASSWORD")

    # File paths
    ACTIVITY_FILE = "activity/latest_activity_report_recent_only.jsonl"
    FOLLOWERS_FILE = "followers_n_followed_vegansearchengine/20251211_bsky_app_followers.jsonl"
    FOLLOWING_FILE = "followers_n_followed_vegansearchengine/20251211_bsky_app_following.jsonl"

    # Define the output filename here
    # Use a fixed name for the run to enable easy restarting/resuming
    OUTPUT_FILE = "prospects/unseen_prospects_12-12-2025.jsonl"

    # Ensure you are running this from a context where the env var is set
    if not APP_PASSWORD:
        logging.error("FATAL: Environment variable 'BLUESKY_APP_PASSWORD' not set.")
        sys.exit(1)

    try:
        if not all(os.path.exists(f) for f in [ACTIVITY_FILE, FOLLOWERS_FILE, FOLLOWING_FILE]):
            logging.error("FATAL: One or more required input files are missing. Check file paths.")
            sys.exit(1)

        activity_filter = ActivityFilter(
            activity_filepath=ACTIVITY_FILE,
            followers_filepath=FOLLOWERS_FILE,
            following_filepath=FOLLOWING_FILE,
            auth_handle=AUTH_HANDLE,
            auth_password=APP_PASSWORD,
            output_filepath=OUTPUT_FILE
        )

        activity_filter.run_filter()

    except Exception as e:
        logging.error(f"A fatal error occurred during execution: {e}")