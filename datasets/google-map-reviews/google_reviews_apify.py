import argparse
import json
from pathlib import Path
import pandas as pd
from apify_client import ApifyClient

ACTOR_ID = "compass/Google-Maps-Reviews-Scraper"


def load_place_ids_from_csv(csv_path):
    """Load place IDs from a CSV."""
    df = pd.read_csv(csv_path)

    if "place_id" not in df.columns:
        raise ValueError(f"{csv_path.name} missing place_id column")

    place_ids = df["place_id"].dropna().astype(str).unique().tolist()
    return place_ids


def run_actor_stream(client, place_ids, max_reviews=100):
    """
    Starts the actor and returns a generator that streams items
    as they become available in the dataset.
    """
    if not place_ids:
        return []

    actor_input = {
        "placeIds": place_ids,
        "maxReviews": max_reviews,
    }

    run = client.actor(ACTOR_ID).call(run_input=actor_input)
    dataset_id = run["defaultDatasetId"]

    return client.dataset(dataset_id).iterate_items()


def process_directory(input_dir, output_dir, api_token, max_reviews):
    client = ApifyClient(api_token)

    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_files = sorted(input_dir.glob("*.csv"))

    for csv_file in csv_files:
        try:
            output_file = output_dir / f"{csv_file.stem}_reviews.jsonl"

            # Check if file exists and has content (greater than 0 bytes)
            if output_file.exists() and output_file.stat().st_size > 0:
                print(f"\nSkipping {csv_file.name} — Non-empty output file '{output_file.name}' already exists.")
                continue

            print(f"\nProcessing {csv_file.name}")
            place_ids = load_place_ids_from_csv(csv_file)
            print(f"Found {len(place_ids)} Place IDs")

            if not place_ids:
                print(f"Skipping empty file: {csv_file.name}")
                continue

            review_count = 0

            # Open the file up front so we can stream directly into it
            with open(output_file, "w", encoding="utf-8") as f:

                # iterate_items() yields data in real time as Apify streams it back
                for review in run_actor_stream(client, place_ids, max_reviews):
                    essential_data = {
                        "place_id": review.get("placeId"),
                        "review_text": review.get("text"),
                        "rating": review.get("stars"),
                        "review_url": review.get("reviewIdUrl"),
                        "timestamp": review.get("publishedAtDate"),
                    }

                    f.write(json.dumps(essential_data, ensure_ascii=False) + "\n")

                    # Force Python to instantly flush the internal buffer to your hard drive
                    f.flush()

                    review_count += 1

            print(f"Saved {review_count} essential reviews → {output_file.name}")

        except Exception as e:
            print(f"Failed {csv_file.name}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Run Apify Google Maps Reviews Scraper with real-time streaming and restart-friendly tracking."
    )
    parser.add_argument("input_dir", help="Directory of CSV files")
    parser.add_argument("output_dir", help="Directory for scraped review JSONL files")
    parser.add_argument("--token", required=True, help="Apify API token")
    parser.add_argument(
        "--max-reviews",
        type=int,
        default=100,
        help="Max reviews per location",
    )

    args = parser.parse_args()
    process_directory(args.input_dir, args.output_dir, args.token, args.max_reviews)


if __name__ == "__main__":
    main()