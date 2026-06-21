import requests
import json
import time
import logging
import os
import sys
from typing import List, Dict, Any, Optional
from datetime import datetime

# --- Configuration for this new module ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


# ------------------------------------------

class BlueskyFollowGraph:
    """
    Connects to the Bluesky API to fetch the social graph and write the results
    to date-stamped JSONL files.
    """

    API_BASE_URL = "https://bsky.social/xrpc"
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0
    PAGINATION_DELAY = 1.0

    def __init__(self, handle: str, password: str):
        self.handle = handle
        self.password = password
        self.token = None

    def _get_session(self) -> bool:
        """Authenticates and obtains an access token."""
        url = f"{self.API_BASE_URL}/com.atproto.server.createSession"
        payload = {"identifier": self.handle, "password": self.password}
        logging.info("Attempting authentication...")
        try:
            res = requests.post(url, json=payload)
            res.raise_for_status()
            self.token = res.json()["accessJwt"]
            logging.info("✅ Authentication successful.")
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"❌ FATAL AUTHENTICATION ERROR: {e}")
            logging.error("Please check the account handle and App Password (BLUESKY_APP_PASSWORD env var).")
            return False

    def _resolve_handle_to_did(self, handle: str) -> Optional[str]:
        """
        Looks up the permanent DID for a given human-readable handle.
        This uses the com.atproto.identity.resolveHandle endpoint.
        """
        if not self.token:
            # Try public access first, then fail if no session
            logging.warning("No authentication token. Attempting handle resolution publicly.")
            headers = {}
        else:
            headers = {"Authorization": f"Bearer {self.token}"}

        url = f"{self.API_BASE_URL}/com.atproto.identity.resolveHandle"
        params = {"handle": handle}

        logging.info(f"🔍 Resolving handle '{handle}' to DID...")

        try:
            res = requests.get(url, headers=headers, params=params)
            res.raise_for_status()

            # The DID is in the response body's 'did' field
            target_did = res.json().get("did")

            if target_did:
                logging.info(f"✅ Resolved DID: {target_did}")
                return target_did
            else:
                logging.error(f"❌ Resolution failed: API returned no DID for handle '{handle}'.")
                return None

        except requests.exceptions.RequestException as e:
            logging.error(f"❌ Error resolving handle '{handle}': {e}")
            return None

    def _fetch_paginated_list(self, endpoint: str, target_did: str, list_key: str) -> List[Dict[str, Any]]:
        """
        Generic function to paginate through followers or follows endpoints.
        """
        if not self.token:
            logging.error("Authentication token is missing. Cannot fetch data.")
            return []

        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.API_BASE_URL}/{endpoint}"
        all_profiles: List[Dict[str, Any]] = []
        cursor = None
        page_num = 1

        logging.info(f"Starting pagination for {list_key}...")

        while True:
            params = {"actor": target_did, "limit": 100}
            if cursor:
                params["cursor"] = cursor

            try:
                res = requests.get(url, headers=headers, params=params)
                res.raise_for_status()
                data = res.json()

                profiles = data.get(list_key, [])
                all_profiles.extend(profiles)

                logging.debug(f"Fetched page {page_num}: added {len(profiles)} records.")

                cursor = data.get('cursor')
                if not cursor:
                    break

                page_num += 1
                time.sleep(self.PAGINATION_DELAY)

            except requests.exceptions.RequestException as e:
                logging.error(f"❌ Error fetching {list_key} page {page_num}: {e}. Stopping pagination.")
                break

        logging.info(f"✅ Finished fetching. Total {list_key}: {len(all_profiles)}")
        return all_profiles

    def _write_results_to_jsonl(self, profiles: List[Dict[str, Any]], filename: str) -> None:
        """Writes a list of profiles (with handle/did) to a JSONL file."""
        if not profiles:
            logging.warning(f"No profiles to write to {filename}. Skipping file creation.")
            return

        data_to_write = []
        for profile in profiles:
            # Extract only the required fields: handle and did
            data_to_write.append({
                "handle": profile.get("handle", "N/A"),
                "did": profile.get("did", "N/A")
            })

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                for record in data_to_write:
                    json_line = json.dumps(record, ensure_ascii=False)
                    f.write(json_line + '\n')
            logging.info(f"🎉 Successfully wrote {len(data_to_write)} records to {filename}")
        except Exception as e:
            logging.error(f"❌ Error writing results to file {filename}: {e}")

    def run_analysis_and_output_files(self, target_did: str, target_handle_for_naming: str) -> None:
        """
        Main method to fetch the graph data and save it to date-stamped JSONL files.
        """
        # Note: Session should be obtained before calling this if using the new structure.

        # 1. Format the date for the filename
        date_str = datetime.now().strftime("%Y%m%d")

        # Clean the handle for use in the filename
        safe_handle = target_handle_for_naming.replace('.', '_').replace('@', '')

        # --- A. Fetch and write Followers ---
        logging.info(f"\n--- Processing Followers for {target_handle_for_naming} ---")
        followers = self._fetch_paginated_list(
            endpoint="app.bsky.graph.getFollowers",
            target_did=target_did,
            list_key="followers"
        )
        followers_filename = f"{date_str}_{safe_handle}_followers.jsonl"
        self._write_results_to_jsonl(followers, followers_filename)

        # Pause to respect rate limits
        time.sleep(2)

        # --- B. Fetch and write Follows (Following) ---
        logging.info(f"\n--- Processing Follows (Following) for {target_handle_for_naming} ---")
        follows = self._fetch_paginated_list(
            endpoint="app.bsky.graph.getFollows",
            target_did=target_did,
            list_key="follows"
        )
        follows_filename = f"{date_str}_{safe_handle}_following.jsonl"
        self._write_results_to_jsonl(follows, follows_filename)


# --- EXECUTION BLOCK ---
if __name__ == "__main__":

    # --- CONFIGURATION ---
    # Credentials to access the API (can be any valid Bluesky account)
    MY_HANDLE = "ethicalsearch.bsky.social"

    # The account whose graph you want to analyze - ONLY THE HANDLE IS NOW NEEDED
    TARGET_HANDLE_TO_ANALYZE = "joyfulgrowth.bsky.social"

    # --- SECURE CREDENTIAL RETRIEVAL ---
    APP_PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD")

    if not APP_PASSWORD:
        logging.error(
            "FATAL: Environment variable 'BLUESKY_APP_PASSWORD' not set. "
            "Please export it before running the script (e.g., export BLUESKY_APP_PASSWORD='your_app_pass')."
        )
        sys.exit(1)

    # --- RUN ANALYSIS ---
    try:
        logging.info(f"--- STARTING BLUESKY FOLLOW GRAPH ANALYSIS ---")
        graph_analyzer = BlueskyFollowGraph(
            handle=MY_HANDLE,
            password=APP_PASSWORD
        )

        # 1. Authenticate first
        if not graph_analyzer._get_session():
            sys.exit(1)

        # 2. Look up the DID using the handle
        TARGET_DID_TO_ANALYZE = graph_analyzer._resolve_handle_to_did(TARGET_HANDLE_TO_ANALYZE)

        if not TARGET_DID_TO_ANALYZE:
            logging.error(f"FATAL: Could not resolve DID for handle '{TARGET_HANDLE_TO_ANALYZE}'. Exiting.")
            sys.exit(1)

        # 3. Call the main method
        graph_analyzer.run_analysis_and_output_files(
            target_did=TARGET_DID_TO_ANALYZE,
            target_handle_for_naming=TARGET_HANDLE_TO_ANALYZE
        )

    except Exception as e:
        logging.error(f"A fatal error occurred during execution: {e}")