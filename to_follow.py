import requests
import json
import time
import os
import logging
import csv
from typing import List, Dict, Any, Tuple

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class BlueskyFollowerAnalyzer:
    """
    Analyzes follower lists on the Bluesky Social network (AT Protocol)
    to find users who follow a set of source accounts but do not follow
    a specified target account, outputting results in JSONL and two TSV formats.
    """

    API_BASE_URL = "https://bsky.social/xrpc"
    LIMIT = 100
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0

    # Constants for output files and filtering
    TSV_HEADER = ["did", "handle", "description", "createdAt", "indexedAt"]
    VEGAN_KEYWORD = "vegan"
    VEGAN_SYMBOLS = ["Ⓥ", "🌱"]
    SPAM_LABEL = "spam"

    def __init__(self, handle: str, password: str, target_account: str, source_accounts: List[str]):
        """
        Initializes the analyzer with account details and targets.
        """
        self.handle = handle
        self.password = password
        self.target_account = target_account
        self.source_accounts = source_accounts
        self.token = None
        self.target_dids = set()
        self.output_jsonl_filepath = None
        self.output_tsv_filepath = None
        self.output_vegan_tsv_filepath = None  # New path for the filtered TSV

    def _get_session(self) -> str:
        """Authenticates and obtains an access token."""
        url = f"{self.API_BASE_URL}/com.atproto.server.createSession"
        payload = {"identifier": self.handle, "password": self.password}

        try:
            res = requests.post(url, json=payload)
            res.raise_for_status()
            self.token = res.json()["accessJwt"]
            logging.info("✅ Access token acquired.")
            return self.token
        except requests.exceptions.RequestException as e:
            logging.error(f"❌ Error during authentication: {e}")
            raise

    def get_all_followers(self, actor_handle: str) -> List[Dict[str, Any]]:
        """Fetches all followers for a given handle, handling pagination and retries."""

        if not self.token:
            raise RuntimeError("Authentication token is missing. Call _get_session() first.")

        headers = {"Authorization": f"Bearer {self.token}"}
        followers = []
        cursor = None

        while True:
            params = {"actor": actor_handle, "limit": self.LIMIT}
            if cursor:
                params["cursor"] = cursor

            retries = 0
            while retries < self.MAX_RETRIES:
                logging.debug(f"Sending request for followers with params: {params}")
                res = requests.get(
                    f"{self.API_BASE_URL}/app.bsky.graph.getFollowers",
                    headers=headers,
                    params=params
                )

                if res.status_code == 200:
                    data = res.json()
                    fetched = data.get("followers", [])
                    followers.extend(fetched)
                    logging.debug(f"Fetched {len(fetched)} followers from current page")

                    cursor = data.get("cursor")
                    time.sleep(0.3)
                    break
                else:
                    retries += 1
                    logging.warning(f"⚠️ Error (try {retries}/{self.MAX_RETRIES}): {res.status_code} - {res.text}")
                    time.sleep(self.RETRY_DELAY * (2 ** retries))
            else:
                logging.error("❌ Max retries reached. Exiting follower fetch early.")
                break

            if not cursor:
                logging.debug("No more pages of followers. Stopping.")
                break

        logging.debug(f"Total followers fetched for {actor_handle}: {len(followers)}")
        return followers

    def _extract_tsv_row(self, follower: Dict[str, Any]) -> List[str]:
        """Extracts the specific fields for the TSV output."""
        # Ensure description is cleaned of tabs/newlines to prevent breaking TSV structure
        description = follower.get("description", "").replace('\t', ' ').replace('\n', ' ')

        return [
            follower.get("did", ""),
            follower.get("handle", ""),
            description,
            follower.get("createdAt", ""),
            follower.get("indexedAt", "")
        ]

    def run_analysis(self) -> Tuple[int, str, str, str]:
        """
        Executes the full follower comparison analysis.

        :returns: A tuple containing the count of non-followers found, and the
                  absolute paths to the JSONL, All TSV, and Vegan TSV files.
        """

        # 1. Authenticate
        self._get_session()

        # 2. Setup output paths
        output_dir = f"non_followers_{self.target_account.split('.')[0]}"
        os.makedirs(output_dir, exist_ok=True)
        self.output_jsonl_filepath = os.path.join(output_dir, "non_followers.jsonl")
        self.output_tsv_filepath = os.path.join(output_dir, "non_followers_all.tsv")
        self.output_vegan_tsv_filepath = os.path.join(output_dir, "non_followers_vegan_nonspam_11-30-2025.tsv")  # New path

        # 3. Fetch followers of target account
        logging.info(f"Fetching followers for target account: {self.target_account}")
        target_followers = self.get_all_followers(self.target_account)
        self.target_dids = set(f["did"] for f in target_followers)
        logging.info(f"Target account has {len(self.target_dids)} unique followers.")

        found_count = 0
        vegan_count = 0
        logging.info(f"Starting comparison. Results will be written to three files.")

        # 4. Process source accounts and write to ALL three files
        try:
            with open(self.output_jsonl_filepath, "w", encoding="utf-8") as jsonl_f, \
                    open(self.output_tsv_filepath, "w", newline='', encoding="utf-8") as tsv_f, \
                    open(self.output_vegan_tsv_filepath, "w", newline='', encoding="utf-8") as vegan_tsv_f:

                # Set up writers
                tsv_writer = csv.writer(tsv_f, delimiter='\t')
                vegan_tsv_writer = csv.writer(vegan_tsv_f, delimiter='\t')

                # Write Headers
                tsv_writer.writerow(self.TSV_HEADER)
                vegan_tsv_writer.writerow(self.TSV_HEADER)
                logging.info(f"Wrote TSV headers to both TSV files.")

                for account in self.source_accounts:
                    logging.info(f"🔍 Fetching followers of {account}")
                    source_followers = self.get_all_followers(account)

                    for follower in source_followers:
                        did = follower.get("did")

                        if did and did not in self.target_dids:
                            # --- 4a. Write to JSONL file (full record) ---
                            json_line = json.dumps(follower)
                            jsonl_f.write(json_line + "\n")

                            # Get the subset data for TSV files
                            tsv_row = self._extract_tsv_row(follower)

                            # --- 4b. Write to ALL TSV file ---
                            tsv_writer.writerow(tsv_row)

                            found_count += 1
                            logging.debug(f"Wrote ALL non-follower: {did}")

                            # --- 4c. Filter for Non-Spam and Vegan Interest ---

                            # 1. Check for spam label
                            is_spam = any(label.get("val") == self.SPAM_LABEL for label in follower.get("labels", []))

                            if not is_spam:
                                # 2. Check for vegan interest in handle or description
                                description_lower = follower.get("description", "").lower()
                                handle_lower = follower.get("handle", "").lower()

                                is_vegan_interest = self.VEGAN_KEYWORD in description_lower or \
                                                    self.VEGAN_KEYWORD in handle_lower

                                # Check symbols
                                if not is_vegan_interest:
                                    if any(symbol in description_lower or symbol in handle_lower for symbol in
                                           self.VEGAN_SYMBOLS):
                                        is_vegan_interest = True

                                if is_vegan_interest:
                                    # --- Write to the filtered VEGAN TSV file ---
                                    vegan_tsv_writer.writerow(tsv_row)
                                    vegan_count += 1
                                    logging.debug(f"Wrote VEGAN non-spam follower: {did}")

                return found_count, os.path.abspath(self.output_jsonl_filepath), os.path.abspath(
                    self.output_tsv_filepath), os.path.abspath(self.output_vegan_tsv_filepath)

        except Exception as e:
            logging.error(f"❌ An error occurred during file writing: {e}")
            # Re-raise the exception after logging to ensure execution stops cleanly
            raise


if __name__ == "__main__":

    MY_HANDLE = "ethicalsearch.bsky.social"
    APP_PASSWORD = "iegl-23ir-rmi5-g3qk"
    TARGET = "vegansearchengine.bsky.social"
    SOURCES = ["tonytheauthor.bsky.social"]

    try:
        analyzer = BlueskyFollowerAnalyzer(
            handle=MY_HANDLE,
            password=APP_PASSWORD,
            target_account=TARGET,
            source_accounts=SOURCES
        )

        non_followers_count, final_jsonl_path, final_tsv_path, final_vegan_tsv_path = analyzer.run_analysis()

        logging.info(f"✅ Processing complete. {non_followers_count} non-followers found in total.")
        logging.info(f"💾 Results saved to:")
        logging.info(f"   JSONL (Full Data): {final_jsonl_path}")
        logging.info(f"   TSV (All Non-Followers): {final_tsv_path}")
        logging.info(f"   TSV (Vegan, Non-Spam Filtered): {final_vegan_tsv_path}")

    except Exception as e:
        # This catches errors not handled within the class methods
        logging.error(f"A fatal error occurred during execution: {e}")