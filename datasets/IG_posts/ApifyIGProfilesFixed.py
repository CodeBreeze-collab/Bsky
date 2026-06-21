import argparse
import json
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Set

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


class ApifyInstagramProfileScraper:
    BASE_URL = "https://api.apify.com/v2"

    def __init__(self, api_token: str, actor_id: str, output_file: str, scanned_via: str, category: str):
        self.api_token = api_token
        self.actor_id = actor_id
        self.output_file = Path(output_file)
        self.output_file.touch(exist_ok=True)
        self.scanned_via = scanned_via
        self.category = category

    def _extract_images(self, item: dict) -> List[str]:
        """Flattens all possible image URLs from an Instagram post into a single array."""
        images = []

        # Grab main display URL if it looks like an image link
        display_url = item.get("displayUrl")
        if display_url and "cdninstagram.com" in display_url:
            images.append(display_url)

        # Check explicit images array if present
        for img in item.get("images", []):
            if img and img not in images:
                images.append(img)

        # Dig into carousel child posts if they exist
        for child in item.get("childPosts", []):
            child_url = child.get("displayUrl")
            if child_url and child_url not in images:
                images.append(child_url)

        return images

    def scrape_all(self, profile_urls: List[str]):
        """Kicks off a single Apify run, monitors it, transforms data to target schema, and saves."""

        # 1. Start the Actor Run
        run_url = f"{self.BASE_URL}/acts/{self.actor_id}/runs"
        payload = {
            "directUrls": profile_urls,
            "resultsType": "posts",
            "resultsLimit": 100,
        }

        logging.info("📡 Kicking off a single Apify run for all %d profiles...", len(profile_urls))
        try:
            response = requests.post(run_url, params={"token": self.api_token}, json=payload, timeout=30)
            response.raise_for_status()
            run_data = response.json().get("data", {})
            run_id = run_data.get("id")
            default_dataset_id = run_data.get("defaultDatasetId")

            logging.info("🚀 Run started successfully! Run ID: %s", run_id)
        except Exception as e:
            logging.error("Failed to start Apify actor run: %s", e)
            return

        # 2. Poll the Run status until it completes
        status_url = f"{self.BASE_URL}/acts/{self.actor_id}/runs/{run_id}"
        while True:
            try:
                status_res = requests.get(status_url, params={"token": self.api_token}, timeout=30)
                status_res.raise_for_status()
                current_status = status_res.json().get("data", {}).get("status")

                logging.info("⏳ Current Apify worker status: %s", current_status)

                if current_status in ["SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"]:
                    if current_status != "SUCCEEDED":
                        logging.error("Apify run finished with an error status: %s", current_status)
                        return
                    break
            except Exception as e:
                logging.warning("Failed to check status (will retry): %s", e)

            time.sleep(15)

        # 3. Stream dataset items and transform them in real-time
        logging.info("✅ Apify job finished! Streaming items and transforming to target schema...")
        dataset_url = f"{self.BASE_URL}/datasets/{default_dataset_id}/items"

        try:
            dataset_res = requests.get(
                dataset_url,
                params={"token": self.api_token, "format": "jsonl"},
                stream=True,
                timeout=60
            )
            dataset_res.raise_for_status()

            new_count = 0
            with open(self.output_file, "a", encoding="utf-8") as f:
                for line in dataset_res.iter_lines():
                    if line:
                        item = json.loads(line.decode('utf-8'))

                        # Fix: Safely handle if Apify wraps the entire content block inside a "result" object
                        data_source = item.get("result") if "result" in item else item
                        if not data_source:
                            data_source = item

                        # Generate current timestamps for indexing
                        now_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

                        # Extract the profile handle from the correct data source block
                        username = data_source.get("ownerUsername", "")
                        author_handle = f"{username}.instagram.com" if username else "unknown.instagram.com"

                        # Map out directly to your clean database target schema
                        transformed_line = {
                            "scanned_via": self.scanned_via,
                            "author_handle": author_handle,
                            "post_url": data_source.get("url") or item.get("instagram_url") or data_source.get(
                                "postUrl"),
                            "category": self.category,
                            "text": data_source.get("caption", ""),
                            "image_urls": self._extract_images(data_source),
                            "posted_at": data_source.get("timestamp"),
                            "indexedAt": now_iso
                        }

                        f.write(json.dumps(transformed_line, ensure_ascii=False) + "\n")
                        new_count += 1

            logging.info("🎉 Done! Transformed and saved %d items to %s", new_count, self.output_file)

        except Exception as e:
            logging.error("Failed to download or transform dataset items: %s", e)


def load_urls(path: str) -> List[str]:
    return [line.strip() for line in Path(path).read_text().splitlines() if line.strip()]


def get_already_scraped_urls(output_path: Path) -> Set[str]:
    finished = set()
    if not output_path.exists(): return finished
    with open(output_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line)
                url = data.get("post_url")
                if url: finished.add(url.strip())
            except:
                continue
    return finished


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--api-key", required=True)
    p.add_argument("--input-file", required=True)
    p.add_argument("--output-file", default="instagram_transformed_results.jsonl")
    p.add_argument("--scanned-via", default="instagram_bot.bsky.social", help="Tracking identity tag")
    p.add_argument("--category", default="NEED_A_HOME", help="Default categorisation tag for batch")
    return p.parse_args()


def main():
    args = parse_args()
    output_path = Path(args.output_file)

    all_urls = load_urls(args.input_file)

    # Check tracking duplicates against the new 'post_url' key structure
    finished_urls = get_already_scraped_urls(output_path)
    to_scrape = [u for u in all_urls if u.strip() not in finished_urls]

    logging.info("Summary: %d total URLs | %d already done | %d remaining",
                 len(all_urls), len(finished_urls), len(to_scrape))

    if not to_scrape:
        logging.info("All URLs done!")
        return

    scraper = ApifyInstagramProfileScraper(
        api_token=args.api_key,
        actor_id="apify~instagram-scraper",
        output_file=args.output_file,
        scanned_via=args.scanned_via,
        category=args.category
    )

    scraper.scrape_all(to_scrape)


if __name__ == "__main__":
    main()