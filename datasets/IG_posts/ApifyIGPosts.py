import argparse
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Set

import requests


class ApifyInstagramScraper:
    BASE_URL = "https://api.apify.com/v2"

    def __init__(
        self,
        api_token: str,
        actor_id: str,
        output_file: str = "instagram_results.jsonl",
    ):
        self.api_token = api_token
        self.actor_id = actor_id
        self.output_file = output_file

    def run_actor(self, instagram_urls: List[str], results_limit: int = 1) -> List[Dict[str, Any]]:
        url = f"{self.BASE_URL}/acts/{self.actor_id}/run-sync-get-dataset-items"
        payload = {
            "directUrls": instagram_urls,
            "resultsType": "posts",
            "resultsLimit": results_limit,
        }
        response = requests.post(url, params={"token": self.api_token}, json=payload, timeout=300)
        response.raise_for_status()
        return response.json()

    def save_results_jsonl(self, results: List[Dict[str, Any]]) -> None:
        with open(self.output_file, "a", encoding="utf-8") as f:
            for item in results:
                scraped_url = item.get("inputUrl") or item.get("url") or item.get("postUrl")
                line = {"instagram_url": scraped_url, "result": item}
                f.write(json.dumps(line, ensure_ascii=False) + "\n")

    def scrape(self, instagram_urls: List[str], batch_size: int = 10, results_limit: int = 1, sleep_between_batches: float = 1.0) -> None:
        total = len(instagram_urls)
        if total == 0:
            print("[INFO] No new URLs to process.")
            return

        for i in range(0, total, batch_size):
            batch = instagram_urls[i : i + batch_size]
            print(f"[INFO] Processing batch {i // batch_size + 1} ({len(batch)} URLs)")
            try:
                results = self.run_actor(instagram_urls=batch, results_limit=results_limit)
                self.save_results_jsonl(results)
                print(f"[INFO] Saved {len(results)} results")
            except Exception as e:
                print(f"[ERROR] Batch failed: {e}")
            time.sleep(sleep_between_batches)


def get_existing_urls(output_file: str) -> Set[str]:
    """Reads the output file and returns a set of URLs already scraped."""
    path = Path(output_file)
    existing = set()
    if not path.exists():
        return existing

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
                url = obj.get("instagram_url")
                if url:
                    existing.add(url)
            except json.JSONDecodeError:
                continue
    return existing


def load_post_urls_from_jsonl(input_path: str, existing_urls: Set[str]) -> List[str]:
    """Loads URLs from input, filtering out those already in existing_urls."""
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    new_urls = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                obj = json.loads(line)
                post_url = obj.get("post_url")
                if post_url and post_url not in existing_urls:
                    new_urls.add(post_url)
            except json.JSONDecodeError:
                continue

    return list(new_urls)


def parse_args():
    parser = argparse.ArgumentParser(description="Scrape Instagram posts (Resume-friendly)")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--input-file", required=True)
    parser.add_argument("--output-file", default="instagram_results.jsonl")
    parser.add_argument("--actor-id", default="apify~instagram-api-scraper")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--results-limit", type=int, default=1)
    parser.add_argument("--sleep", type=float, default=1.0)
    return parser.parse_args()


def main():
    args = parse_args()

    # 1. Check what we've already done
    existing = get_existing_urls(args.output_file)
    if existing:
        print(f"[INFO] Detected {len(existing)} URLs already processed in {args.output_file}")

    # 2. Load only the remaining URLs
    try:
        urls_to_scrape = load_post_urls_from_jsonl(args.input_file, existing)
    except Exception as e:
        print(f"[ERROR] {e}")
        return

    print(f"[INFO] Total new URLs to scrape: {len(urls_to_scrape)}")

    scraper = ApifyInstagramScraper(
        api_token=args.api_key,
        actor_id=args.actor_id,
        output_file=args.output_file,
    )

    scraper.scrape(
        instagram_urls=urls_to_scrape,
        batch_size=args.batch_size,
        results_limit=args.results_limit,
        sleep_between_batches=args.sleep,
    )

if __name__ == "__main__":
    main()