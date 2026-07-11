import json
import csv
import argparse
from pathlib import Path


def load_places_jsonl(jsonl_path):
    """Load Places data from a JSONL file."""
    places = []

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            places.append(json.loads(line))

    return places


def generate_review_link(place_id):
    """Convert a Place ID into a Google review link."""
    return f"https://search.google.com/local/writereview?placeid={place_id}"


def export_csv(places, output_path):
    """Write places + review links to CSV."""
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        writer.writerow([
            "name",
            "address",
            "place_id",
            "review_link"
        ])

        for place in places:
            place_id = place.get("id")
            name = place.get("displayName", {}).get("text", "")
            address = place.get("formattedAddress", "")

            if not place_id:
                continue

            writer.writerow([
                name,
                address,
                place_id,
                generate_review_link(place_id)
            ])


def process_directory(input_dir, output_dir):
    """Convert all JSONL files in a directory to CSV."""
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)

    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    jsonl_files = sorted(input_dir.glob("*.jsonl"))

    if not jsonl_files:
        print("No .jsonl files found.")
        return

    for jsonl_file in jsonl_files:
        try:
            print(f"Processing: {jsonl_file.name}")

            places = load_places_jsonl(jsonl_file)

            output_csv = output_dir / f"{jsonl_file.stem}.csv"

            export_csv(places, output_csv)

            print(
                f"Done → {output_csv.name} "
                f"({len(places)} places)"
            )

        except Exception as e:
            print(f"Failed: {jsonl_file.name}")
            print(e)


def main():
    parser = argparse.ArgumentParser(
        description="Convert Google Places JSONL files to CSV review links"
    )

    parser.add_argument(
        "input_dir",
        help="Directory containing .jsonl files"
    )

    parser.add_argument(
        "output_dir",
        help="Directory where CSV files will be written"
    )

    args = parser.parse_args()

    process_directory(
        args.input_dir,
        args.output_dir
    )


if __name__ == "__main__":
    main()