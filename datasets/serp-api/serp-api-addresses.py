import json
import requests
from typing import Dict, List, Set, Optional


class SerpVenueExtractor:
    """
    Extracts venue names and addresses from SerpAPI results.

    Supports:
    - organic_results
    - local_results
    - places_results
    - optional enrichment via Google Places API (place_id)
    """

    def __init__(self, places_api_key: Optional[str] = None):
        self.places_api_key = places_api_key

    # -----------------------------
    # Core entry point
    # -----------------------------
    def extract_from_file(self, file_path: str) -> Dict[str, Set[str]]:
        """Load SerpAPI JSON file and extract venues + addresses."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return self.extract_from_dict(data)

    def extract_from_dict(self, data: Dict) -> Dict[str, Set[str]]:
        """Extract structured venue + address data."""

        venues = set()
        addresses = set()

        # Combine all possible result buckets
        result_sources = [
            "local_results",
            "places_results",
            "organic_results",
        ]

        for source in result_sources:
            for item in data.get(source, []):
                name = item.get("title") or item.get("name")
                address = item.get("address")

                if name:
                    venues.add(name.strip())

                if address:
                    addresses.add(address.strip())

        return {
            "venues": venues,
            "addresses": addresses,
        }

    # -----------------------------
    # Enrichment via Place ID
    # -----------------------------
    def enrich_with_place_details(self, place_id: str) -> Dict:
        """
        Optional: Fetch canonical address using Google Places API.
        Requires API key.
        """
        if not self.places_api_key:
            raise ValueError("Places API key not provided.")

        url = (
            "https://maps.googleapis.com/maps/api/place/details/json"
            f"?place_id={place_id}&key={self.places_api_key}"
        )

        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()

        result = data.get("result", {})

        return {
            "name": result.get("name"),
            "formatted_address": result.get("formatted_address"),
            "phone": result.get("formatted_phone_number"),
            "website": result.get("website"),
        }

    # -----------------------------
    # Utility: full pipeline
    # -----------------------------
    def process(self, file_path: str) -> Dict:
        """
        Full pipeline:
        - extract venues
        - extract addresses
        - return structured output
        """
        extracted = self.extract_from_file(file_path)

        return {
            "venue_count": len(extracted["venues"]),
            "address_count": len(extracted["addresses"]),
            "venues": sorted(extracted["venues"]),
            "addresses": sorted(extracted["addresses"]),
        }


# -----------------------------
# CLI usage (optional)
# -----------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SerpAPI Venue Extractor")
    parser.add_argument("file_path", help="Path to SerpAPI JSON file")

    args = parser.parse_args()

    extractor = SerpVenueExtractor()
    result = extractor.process(args.file_path)

    print(f"\n--- Found {result['venue_count']} venues ---")
    for v in result["venues"]:
        print(v)

    print(f"\n--- Found {result['address_count']} addresses ---")
    for a in result["addresses"]:
        print(a)