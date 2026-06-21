import argparse
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Set

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

class ApifyInstagramProfileScraper:
    BASE_URL = "https://api.apify.com/v2"

    def __init__(self, api_token: str, actor_id: str, output_file: str):
        self.api_token = api_token
        self.actor_id = actor_id
        self.output_file = Path(output_file)
        self.output_file.touch(exist_ok=True)
        self.existing_post_ids = self._load_existing_post_ids()

    def _load_existing_post_ids(self) -> Set[str]:
        seen_ids = set()
        if not self.output_file.exists(): return seen_ids
        try:
            with open(self.output_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            data = json.loads(line)
                            post_id = data.get("result", {}).get("id")
                            if post_id: seen_ids.add(str(post_id))
                        except:
                            continue
        except Exception as e:
            logging.warning("Duplicate check failed to load: %s", e)
        return seen_ids

    def run_actor_batch(self, profile_urls, results_limit=100):
        url = f"{self.BASE_URL}/acts/{self.actor_id}/run-sync-get-dataset-items"
        payload = {
            "directUrls": profile_urls,
            "resultsType": "posts",
            "resultsLimit": results_limit,
        }

        logging.info("📡 Requesting batch of %d profiles...", len(profile_urls))
        try:
            # 600s timeout to allow Apify enough time to scrape the batch
            response = requests.post(
                url,
                params={"token": self.api_token},
                json=payload,
                timeout=600,
            )
            if response.status_code != 200:
                logging.error("API Error %d: %s", response.status_code, response.text)
                return []

            return response.json()
        except Exception as e:
            logging.error("Batch request failed: %s", str(e))
            return []

    def save_jsonl(self, results: List[Dict[str, Any]]):
        new_count = 0
        with open(self.output_file, "a", encoding="utf-8") as f:
            for item in results:
                post_id = item.get("id")
                if post_id and str(post_id) in self.existing_post_ids:
                    continue

                line = {
                    "instagram_url": item.get("url") or item.get("postUrl"),
                    "result": item
                }
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
                if post_id: self.existing_post_ids.add(str(post_id))
                new_count += 1
        return new_count

    def scrape(self, profile_urls: List[str], chunk_size: int = 15):
        """Processes profiles in small batches to avoid 400 Bad Request errors."""
        total = len(profile_urls)
        for i in range(0, total, chunk_size):
            batch = profile_urls[i:i + chunk_size]
            current_chunk = (i // chunk_size) + 1
            total_chunks = (total + chunk_size - 1) // chunk_size

            logging.info("🚀 Processing chunk %d/%d", current_chunk, total_chunks)

            # --- Added Logging for Individual URLs ---
            for profile_url in batch:
                logging.info("📝 Processing profile: %s", profile_url)
            # -----------------------------------------

            results = self.run_actor_batch(batch)
            if results:
                saved = self.save_jsonl(results)
                logging.info("✅ Saved %d new posts from batch.", saved)

            # Optional sleep to avoid hitting Apify rate limits too hard
            if i + chunk_size < total:
                time.sleep(2)


def load_urls(path: str) -> List[str]:
    return [line.strip() for line in Path(path).read_text().splitlines() if line.strip()]


def get_already_scraped_usernames(output_path: Path) -> Set[str]:
    finished = set()
    if not output_path.exists(): return finished
    with open(output_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line)
                username = data.get("result", {}).get("ownerUsername")
                if username: finished.add(username.lower())
            except:
                continue
    return finished


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--api-key", required=True)
    p.add_argument("--input-file", required=True)
    p.add_argument("--output-file", default="instagram_post_results.jsonl")
    p.add_argument("--chunk-size", type=int, default=15, help="Number of profiles per API request")
    return p.parse_args()


def main():
    args = parse_args()
    output_path = Path(args.output_file)

    all_urls = load_urls(args.input_file)
    finished_users = get_already_scraped_usernames(output_path)

    to_scrape = [u for u in all_urls if u.rstrip('/').split('/')[-1].lower() not in finished_users]

    logging.info("Summary: %d total | %d already done | %d remaining",
                 len(all_urls), len(finished_users), len(to_scrape))

    if not to_scrape:
        logging.info("All profiles done!")
        return

    scraper = ApifyInstagramProfileScraper(
        api_token=args.api_key,
        actor_id="apify~instagram-scraper",
        output_file=args.output_file,
    )

    scraper.scrape(to_scrape, chunk_size=args.chunk_size)


if __name__ == "__main__":
    main()